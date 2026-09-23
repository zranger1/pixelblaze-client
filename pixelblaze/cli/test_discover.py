#!/usr/bin/env python3
"""Tests for the parallel, multi-source discovery behind `pb find` / `pb top`.

No Pixelblaze hardware needed. The network pieces run against loopback; the
websocket pieces are stubbed. Environment shortfalls fail, they never skip.
"""

import contextlib
import io
import socket
import struct
import threading
import time

import click

from pixelblaze import pixelblaze as lib
from pixelblaze.cli import cli_utils
from pixelblaze.cli.cli_utils import (
    _discover_devices, _explain_silent_beacons, _tcp_ports_open, update_device_cache,
)

LOOP = '127.0.0.1'


# ── helpers ─────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def tcp_listener():
    """An accepting TCP server on an ephemeral loopback port that records
    whether any client ever sent a byte."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((LOOP, 0))
    server.listen(4)
    server.settimeout(3)
    port = server.getsockname()[1]
    received = []
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            conn.settimeout(0.5)
            try:
                received.append(conn.recv(64))
            except socket.timeout:
                received.append(b'<timeout>')
            finally:
                conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield port, received
    finally:
        stop.set()
        server.close()


@contextlib.contextmanager
def patched(obj, **attrs):
    saved = {k: getattr(obj, k) for k in attrs}
    for k, v in attrs.items():
        setattr(obj, k, v)
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(obj, k, v)


def free_udp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((LOOP, 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ── _tcp_ports_open ─────────────────────────────────────────────────────────

def test_tcp_probe_is_silent():
    """Open ports are detected, closed ones are not, and nothing is ever sent."""
    with tcp_listener() as (open_port, received):
        closed_port = free_udp_port()  # nothing listens on it for TCP either
        result = _tcp_ports_open(LOOP, (open_port, closed_port), timeout=1.0)
        assert result == {open_port: True, closed_port: False}, result
        time.sleep(0.6)  # let the server's recv time out
        # The probe must look like a port scan, not a client: connect, then FIN.
        assert received == [b''], received

    # An unroutable address just times out to all-closed, within the budget.
    t0 = time.monotonic()
    result = _tcp_ports_open('10.255.255.1', (80, 81), timeout=0.5)
    assert result == {80: False, 81: False}, result
    assert time.monotonic() - t0 < 1.5
    print("✓ tcp probe is silent")


# ── beacon socket ───────────────────────────────────────────────────────────

def test_beacon_socket_loud_and_shared():
    """A foreign holder of UDP:1889 raises a clear error; our own listeners coexist."""
    foreign = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    foreign.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        foreign.bind((LOOP, lib.BEACON_PORT))
    except OSError as e:
        raise AssertionError(f"could not set up the foreign listener: {e}")
    try:
        try:
            lib.openBeaconSocket(LOOP)
        except OSError as e:
            assert 'cannot listen for Pixelblaze beacons' in str(e), e
            assert 'lsof' in str(e), e
        else:
            raise AssertionError("bind should have failed loudly")
    finally:
        foreign.close()

    a = lib.openBeaconSocket(LOOP, timeout=0.5)
    b = lib.openBeaconSocket(LOOP, timeout=0.5)
    try:
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Loopback has no broadcast, so exercise "both bound" rather than
        # "both receive one broadcast"; the LAN case is covered by hand.
        assert a.getsockname()[1] == b.getsockname()[1] == lib.BEACON_PORT
        tx.close()
    finally:
        a.close()
        b.close()
    print("✓ beacon socket: loud failure, shared bind")


def test_enumerator_ignores_junk_and_reads_types():
    """Short datagrams don't crash the listener; 42 and 43 are told apart."""
    listener = lib.Pixelblaze.EnumerateAddresses(timeout=700, hostIP=LOOP)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx.bind((LOOP, 0))
    beacon = struct.pack('<L', 42) + socket.inet_aton('192.168.1.230') + struct.pack('<L', 1234)
    sync = struct.pack('<LLL', 43, 890, 0) + socket.inet_aton('192.168.1.230') + struct.pack('<L', 1234)

    def send_all():
        time.sleep(0.1)
        tx.sendto(b'\x2a\x00', (LOOP, lib.BEACON_PORT))        # 2 bytes: junk
        tx.sendto(sync, (LOOP, lib.BEACON_PORT))               # 43 without a probe: ignored
        tx.sendto(beacon, (LOOP, lib.BEACON_PORT))             # 42: a device
    threading.Thread(target=send_all, daemon=True).start()
    found = list(listener)
    assert found == [LOOP], found
    assert listener.packetTypes == {LOOP: 42}, listener.packetTypes
    del listener

    # With probe on, a timeSync reply counts and is labelled 43.
    with patched(lib, sendBeaconProbe=lambda sock: '10.9.9.9'):
        listener = lib.Pixelblaze.EnumerateAddresses(timeout=700, hostIP=LOOP, probe=True)
    threading.Thread(target=lambda: (time.sleep(0.1), tx.sendto(sync, (LOOP, lib.BEACON_PORT))),
                     daemon=True).start()
    found = list(listener)
    assert found == [LOOP], found
    assert listener.packetTypes == {LOOP: 43}, listener.packetTypes
    tx.close()
    print("✓ enumerator ignores junk, labels packet types")


# ── _discover_devices ───────────────────────────────────────────────────────

class FakeEnumerator:
    """Stands in for Pixelblaze.EnumerateAddresses: yields scripted finds."""
    script = []          # (delay, ip, packet_type)
    raise_on_start = None

    def __init__(self, timeout=1500, probe=False, **_):
        if self.raise_on_start:
            raise self.raise_on_start
        self.packetTypes = {}
        self.probe = probe

    def __iter__(self):
        for delay, ip, kind in self.script:
            time.sleep(delay)
            if kind == 43 and not self.probe:
                continue
            self.packetTypes[ip] = kind
            yield ip


class FakePixelblaze:
    """Stands in for Pixelblaze(ip) inside the peer query."""
    peers = {}           # ip -> list of peer dicts
    opened = []

    def __init__(self, ip, **_):
        self.ip = ip
        FakePixelblaze.opened.append(ip)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def getPeers(self):
        return self.peers.get(self.ip, [])


def _run_discovery(cache, ports, script, probe=True, self_ip='192.168.1.67', peers=None,
                   raise_on_start=None):
    FakeEnumerator.script = script
    FakeEnumerator.raise_on_start = raise_on_start
    FakePixelblaze.peers = peers or {}
    FakePixelblaze.opened = []
    seen = []
    err = io.StringIO()

    class PB:
        EnumerateAddresses = staticmethod(lambda **kw: FakeEnumerator(**kw))

    with patched(cli_utils,
                 _read_cache=lambda: cache,
                 get_host_ip=lambda: self_ip,
                 _tcp_ports_open=lambda ip, ports_=(80, 81), timeout=1.0: ports.get(ip, {80: False, 81: False}),
                 Pixelblaze=type('PBShim', (), {
                     'EnumerateAddresses': PB.EnumerateAddresses,
                     '__new__': lambda cls, ip, **kw: FakePixelblaze(ip, **kw),
                 })):
        with contextlib.redirect_stderr(err):
            found = _discover_devices(timeout=300, on_ip=seen.append, probe=probe)
    return found, seen, err.getvalue()


def test_discovery_merges_every_source():
    """Beacons, probe replies, cache, ad-hoc and peers land in one list, once each."""
    cache = {'devices': {
        '192.168.1.86': {'ip': '192.168.1.86', 'name': 'bike2'},
        '10.1.1.24': {'ip': '10.1.1.24', 'name': 'cascade'},
        '192.168.1.67': {'ip': '192.168.1.67'},           # us — never a device
    }}
    ports = {
        '192.168.1.86': {80: True, 81: True},
        '10.1.1.24': {80: True, 81: False},             # wedged websocket
        '192.168.4.1': {80: True, 81: True},               # ad-hoc answers too
        '192.168.1.50': {80: True, 81: True},              # only known via a peer
    }
    peers = {'192.168.1.230': [
        {'address': '192.168.1.230', 'self': True},
        {'address': '192.168.1.50'},
        {'address': '192.168.1.67'},                       # phantom: us
    ]}
    script = [(0.05, '192.168.1.230', 42), (0.05, '192.168.1.86', 43)]

    found, seen, log = _run_discovery(cache, ports, script, peers=peers)
    by_ip = {d['ip']: d for d in found}

    assert set(by_ip) == {'192.168.1.86', '10.1.1.24', '192.168.4.1',
                          '192.168.1.230', '192.168.1.50'}, by_ip
    assert by_ip['192.168.1.230'] == {'ip': '192.168.1.230', 'via': 'beacon'}
    assert by_ip['192.168.4.1']['via'] == 'adhoc'
    assert by_ip['192.168.1.50']['via'] == 'peer' and by_ip['192.168.1.50']['ws'] is True
    assert by_ip['10.1.1.24'] == {'ip': '10.1.1.24', 'via': 'cache', 'http': True, 'ws': False}
    # The device that answered both ways is listed once; the first answer names the source.
    assert by_ip['192.168.1.86']['via'] in ('cache', 'timeSync')
    assert by_ip['192.168.1.86']['ws'] is True   # port state merged in either way

    # on_ip fired exactly once per device, and never for our own address.
    assert sorted(seen) == sorted(by_ip), seen
    # A device whose websocket port is closed is never opened for a peer query.
    assert '10.1.1.24' not in FakePixelblaze.opened, FakePixelblaze.opened
    assert 'wedged' in log and 'pb reboot' in log, log
    print("✓ discovery merges every source")


def test_discovery_passive_and_silent_explanation():
    """Without the probe a follower is only found via cache, and the log says why."""
    cache = {'devices': {
        '192.168.1.86': {'ip': '192.168.1.86', 'name': 'bike2',
                         'settings': {'leaderId': 9238196, 'chipId': 14157732}},
        '192.168.1.230': {'ip': '192.168.1.230', 'name': 'bike1',
                          'settings': {'chipId': 9238196}},
    }}
    ports = {'192.168.1.86': {80: True, 81: True}}
    script = [(0.05, '192.168.1.86', 43)]   # would answer a probe; ignored when passive

    found, _, _ = _run_discovery(cache, ports, script, probe=False)
    assert [d['via'] for d in found] == ['cache'], found

    err = io.StringIO()
    with patched(cli_utils, _read_cache=lambda: cache), contextlib.redirect_stderr(err):
        _explain_silent_beacons(found)
    text = err.getvalue()
    assert 'No beacons heard' in text, text
    assert 'bike2 is a sync-group follower of bike1 (192.168.1.230), which did not answer' in text, text

    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        _explain_silent_beacons([{'ip': '1.2.3.4', 'via': 'beacon'}])
    assert err.getvalue() == '', err.getvalue()   # a beacon was heard: nothing to explain
    print("✓ passive mode and silent-LAN explanation")


def test_discovery_fails_loudly_on_bind_error():
    """A held UDP:1889 surfaces as an error, even though the probes found devices."""
    cache = {'devices': {'192.168.1.86': {'ip': '192.168.1.86'}}}
    ports = {'192.168.1.86': {80: True, 81: True}}
    try:
        _run_discovery(cache, ports, [], raise_on_start=OSError(48, 'cannot listen for Pixelblaze beacons: in use'))
    except click.ClickException as e:
        assert 'cannot listen for Pixelblaze beacons' in e.message, e.message
    else:
        raise AssertionError("a bind failure must not be swallowed")
    print("✓ bind failure is loud")


def test_cache_drops_transient_keys():
    """via/http/ws describe one run; they must not be written to cache.json."""
    written = {}
    with patched(cli_utils, _read_cache=lambda: {'lastIp': None, 'devices': {}},
                 _write_cache=lambda c: written.update(c), get_host_ip=lambda: '192.168.1.67'):
        update_device_cache([{'ip': '192.168.1.86', 'name': 'bike2', 'via': 'cache',
                              'http': True, 'ws': True, 'error': 'x'}])
    entry = written['devices']['192.168.1.86']
    assert entry == {'ip': '192.168.1.86', 'name': 'bike2', 'hostIp': '192.168.1.67'}, entry
    print("✓ cache drops transient keys")


@contextlib.contextmanager
def wedged_ws_listener():
    """A TCP server that accepts a connection and then never says anything.

    This is the real-world failure mode the firmware gets into: port 81
    accepts, the HTTP upgrade is never answered, and the socket is held
    open rather than closed. A handshake with no timeout parks in recv()
    against this forever.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((LOOP, 0))
    server.listen(4)
    server.settimeout(0.25)
    port = server.getsockname()[1]
    held = []
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except socket.timeout:
                continue
            held.append(conn)      # hold it open; send nothing, close nothing

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        stop.set()
        for conn in held:
            with contextlib.suppress(Exception):
                conn.close()
        server.close()


def test_open_times_out_on_wedged_websocket_server():
    """`Pixelblaze(ip)` must fail on a wedged websocket server, not block.

    The regression this guards: `_open()` called create_connection() without
    a `timeout`, so the handshake inherited socket.getdefaulttimeout() --
    None -- and blocked forever. Discovery runs `Pixelblaze(ip)` on a
    ThreadPoolExecutor whose threads are non-daemon and are joined by an
    atexit hook, so one parked handshake made interpreter finalization hang:
    `pb top` could not be killed with Ctrl-C, only SIGKILL.

    Note this asserts loudly rather than hanging if the timeout is dropped
    again -- a test that hangs is a test nobody can read the result of.
    """
    real_create_connection = lib.websocket.create_connection
    seen_kwargs = {}

    with wedged_ws_listener() as port:
        def shim(uri, **kwargs):
            # Record what _open() actually asked for, then point the real
            # websocket-client handshake at our never-answering server.
            seen_kwargs.update(kwargs)
            return real_create_connection(f'ws://{LOOP}:{port}', **kwargs)

        outcome = {}

        def attempt():
            started = time.monotonic()
            try:
                lib.Pixelblaze(LOOP)
            except BaseException as e:      # noqa: BLE001 - any failure beats a hang
                outcome['error'] = e
            outcome['elapsed'] = time.monotonic() - started

        with patched(lib.websocket, create_connection=shim), \
                patched(lib.Pixelblaze, default_open_timeout=0.5):
            worker = threading.Thread(target=attempt, daemon=True)
            worker.start()
            worker.join(timeout=10)

        assert not worker.is_alive(), (
            "Pixelblaze(ip) never returned against a wedged websocket server — "
            "the handshake is blocking with no timeout again. "
            f"create_connection kwargs were {seen_kwargs!r}"
        )

    assert seen_kwargs.get('timeout') == 0.5, (
        f"_open() must pass its handshake timeout through; got {seen_kwargs!r}")
    assert 'error' in outcome, "a wedged server must raise, not connect"
    # 0.5s timeout, and _open() must NOT burn max_open_retries on it.
    assert outcome['elapsed'] < 3, (
        f"handshake took {outcome['elapsed']:.1f}s — is it retrying the timeout?")
    print("✓ handshake times out on a wedged websocket server "
          f"({outcome['elapsed']:.2f}s, {type(outcome['error']).__name__})")


def main():
    test_tcp_probe_is_silent()
    test_beacon_socket_loud_and_shared()
    test_enumerator_ignores_junk_and_reads_types()
    test_discovery_merges_every_source()
    test_discovery_passive_and_silent_explanation()
    test_discovery_fails_loudly_on_bind_error()
    test_cache_drops_transient_keys()
    test_open_times_out_on_wedged_websocket_server()
    print("\nAll discovery tests passed.")


if __name__ == '__main__':
    main()
