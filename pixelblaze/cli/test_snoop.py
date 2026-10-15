#!/usr/bin/env python3
"""Unit tests for `pb snoop`. No Pixelblaze hardware needed.

Two layers:

  * Pure construction tests — the BPF capture filter, the Wireshark display
    filter and the jq program, checked as strings.
  * A real round trip — a synthetic websocket capture is built byte by byte
    in-process, then pushed through the actual `tshark | jq` pipeline the
    command would run. That covers the parts a string comparison can't:
    that the filters compile, that `-T ek` really does keep several frames
    from one packet apart, and that the jq program parses what tshark emits.

`tshark` and `jq` are hard dependencies of the command under test, so their
absence fails the run rather than skipping it.
"""

import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import pathlib

import click

from pixelblaze.cli import cli_utils, snoop
from pixelblaze.cli.snoop import (
    _capture_filter, _display_filter, _jq_program, _jq_udp_program, _resolve_others,
    _udp_display_filter, _jq_http_program, _jq_all_program,
)

HOST = '192.168.1.67'
DEV = '192.168.1.230'
DEV2 = '192.168.1.86'

FAKE_CACHE = {
    'lastIp': None,
    'devices': {
        DEV: {'ip': DEV, 'name': 'bike1'},
        DEV2: {'ip': DEV2, 'name': 'bike2'},
    },
}


# ── Synthetic capture ───────────────────────────────────────────────────────

def _cksum(data: bytes) -> int:
    if len(data) % 2:
        data += b'\x00'
    total = 0
    for i in range(0, len(data), 2):
        total += (data[i] << 8) | data[i + 1]
    while total >> 16:
        total = (total & 0xffff) + (total >> 16)
    return (~total) & 0xffff


def _ws_frame(payload: bytes, mask: bool) -> bytes:
    """A single unfragmented websocket text frame. Client frames are masked."""
    out = bytearray([0x81])            # FIN + opcode 1 (text)
    length = len(payload)
    mask_bit = 0x80 if mask else 0
    if length < 126:
        out.append(mask_bit | length)
    else:
        out.append(mask_bit | 126)
        out += struct.pack('!H', length)
    if mask:
        key = b'\x01\x02\x03\x04'
        out += key + bytes(c ^ key[i % 4] for i, c in enumerate(payload))
    else:
        out += payload
    return bytes(out)


def _packet(src, dst, sport, dport, seq, ack, payload) -> bytes:
    ip_of = lambda s: bytes(int(o) for o in s.split('.'))
    tcp = struct.pack('!HHIIBBHHH', sport, dport, seq, ack, 5 << 4, 0x18, 8192, 0, 0)
    pseudo = ip_of(src) + ip_of(dst) + struct.pack('!BBH', 0, 6, len(tcp) + len(payload))
    tcp = tcp[:16] + struct.pack('!H', _cksum(pseudo + tcp + payload)) + tcp[18:]
    ip = (struct.pack('!BBHHHBBH', 0x45, 0, 20 + len(tcp) + len(payload), 0x1234,
                      0x4000, 64, 6, 0) + ip_of(src) + ip_of(dst))
    ip = ip[:10] + struct.pack('!H', _cksum(ip)) + ip[12:]
    eth = b'\xaa\xbb\xcc\xdd\xee\x01\xaa\xbb\xcc\xdd\xee\x02\x08\x00'
    return eth + ip + tcp + payload


# The messages the fixture capture carries, in order, as (outbound?, json).
EXPECTED = [
    (True,  '{"getConfig":true}'),
    (False, '{"fps":42.5,"vmerr":0,"mem":10000}'),
    (False, '{"fps":41.0}'),
    (False, '{"activeProgram":{"name":"sparks"}}'),
    (True,  '{"setVars":{"speed":0.5}}'),
]


def _write_fixture(path: pathlib.Path, handshake: bool = True):
    """A pcap of one websocket session between HOST and DEV on port 81.

    Frames 3 and 4 deliberately share a single TCP packet — that is the case
    `-T fields` mangles into `{...},{...}` and `-T ek` keeps separable.
    Omitting the handshake simulates attaching to an already-open connection.
    """
    packets, seq_c, seq_s, base = [], 1, 1, 1700000000

    if handshake:
        req = (b"GET / HTTP/1.1\r\nHost: %s:81\r\nUpgrade: websocket\r\n"
               b"Connection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
               b"Sec-WebSocket-Version: 13\r\n\r\n" % DEV.encode())
        resp = (b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                b"Connection: Upgrade\r\n"
                b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n")
        packets.append((base, _packet(HOST, DEV, 54321, 81, seq_c, seq_s, req)))
        seq_c += len(req)
        packets.append((base, _packet(DEV, HOST, 81, 54321, seq_s, seq_c, resp)))
        seq_s += len(resp)

    def send(outbound, msgs, offset):
        nonlocal seq_c, seq_s
        data = b''.join(_ws_frame(m.encode(), mask=outbound) for m in msgs)
        if outbound:
            packets.append((base + offset, _packet(HOST, DEV, 54321, 81, seq_c, seq_s, data)))
            seq_c += len(data)
        else:
            packets.append((base + offset, _packet(DEV, HOST, 81, 54321, seq_s, seq_c, data)))
            seq_s += len(data)

    send(True, [EXPECTED[0][1]], 1)
    send(False, [EXPECTED[1][1]], 2)
    send(False, [EXPECTED[2][1], EXPECTED[3][1]], 3)   # two frames, one packet
    send(True, [EXPECTED[4][1]], 4)

    blob = bytearray(struct.pack('!IHHiIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
    for when, raw in packets:
        blob += struct.pack('!IIII', when, 0, len(raw), len(raw)) + raw
    path.write_bytes(bytes(blob))


def _udp_packet(src, dst, sport, dport, payload) -> bytes:
    ip_of = lambda s: bytes(int(o) for o in s.split('.'))
    udp = struct.pack('!HHHH', sport, dport, 8 + len(payload), 0) + payload
    ip = (struct.pack('!BBHHHBBH', 0x45, 0, 20 + len(udp), 0x1234, 0, 64, 17, 0)
          + ip_of(src) + ip_of(dst))
    ip = ip[:10] + struct.pack('!H', _cksum(ip)) + ip[12:]
    eth = b'\xff\xff\xff\xff\xff\xff\xaa\xbb\xcc\xdd\xee\x02\x08\x00'
    return eth + ip + udp


# The discovery packets the UDP fixture carries, in order. senderId is the
# device's IPv4 in byte order; times are the low 32 bits of unix milliseconds.
UDP_EXPECTED = [
    {'kind': 'beacon', 'src': DEV2, 'sender_ip': DEV2, 'sender_ms': 0x21D28F98},
    {'kind': 'timeSync', 'src': HOST, 'dst': DEV2, 'sync_id': 890,
     'time_ms': 0x21D29000, 'sender_ip': DEV2, 'sender_ms': 0x21D28F98},
    {'kind': 'beacon', 'src': DEV, 'sender_ip': DEV, 'sender_ms': 0x21D29123},
    {'kind': 'sensor', 'src': HOST, 'dst': DEV2, 'sender_id': 0x00D0CAFE,
     'sender_ms': 0x21D29200, 'expansion': 1, 'energy': 0.25, 'max_mag': 0.5,
     'max_hz': 1170, 'light': 0.125, 'accel': [0.5, -0.25, 0.0],
     'analog': [0.75] * 5},
]


# Bin i carries i/64, so the decoded spectrum is a clean ramp: any off-by-one
# in the 16-bit offsets shows up as a shifted or scrambled band.
SENSOR_BINS = [i / 64 for i in range(32)]


def _sensor_frame() -> bytes:
    """One sensor board datagram, built the way `pb sensor sound` builds it."""
    header = struct.pack('<IIIB3x', 50, 0x00D0CAFE, 0x21D29200, 1)
    body = struct.pack(
        '<32HHHH3hH5H',
        *[int(round(v * 65536)) for v in SENSOR_BINS],
        16384,          # energyAverage -> 0.25
        32768,          # maxFrequencyMagnitude -> 0.5
        1170,           # maxFrequency, in Hz, not scaled
        16384, -8192, 0,  # accelerometer -> 0.5, -0.25, 0
        8192,           # light -> 0.125
        *[49152] * 5,   # analogInputs -> 0.75
    )
    assert len(header + body) == 104
    return header + body


def _write_udp_fixture(path: pathlib.Path):
    """A pcap of two beacons and one timeSync on UDP:1889.

    Wire format per docs/pixelblazeProtocol.md: little-endian uint32 words,
    beacon = (42, senderId, senderTimeMs), timeSync = (43, syncId, nowMs,
    senderId, senderTimeMs). One beacon goes to the subnet broadcast and one
    to 255.255.255.255, since firmware has been seen doing either.
    """
    ip_of = lambda s: bytes(int(o) for o in s.split('.'))
    base = 1700000000
    beacon = struct.pack('<L', 42) + ip_of(DEV2) + struct.pack('<L', 0x21D28F98)
    sync = (struct.pack('<LLL', 43, 890, 0x21D29000) + ip_of(DEV2)
            + struct.pack('<L', 0x21D28F98))
    beacon2 = struct.pack('<L', 42) + ip_of(DEV) + struct.pack('<L', 0x21D29123)
    packets = [
        (base, 0, _udp_packet(DEV2, '192.168.1.255', 1889, 1889, beacon)),
        (base, 10000, _udp_packet(HOST, DEV2, 54321, 1889, sync)),
        (base, 500000, _udp_packet(DEV, '255.255.255.255', 1889, 1889, beacon2)),
        (base, 600000, _udp_packet(HOST, DEV2, 54321, 1889, _sensor_frame())),
    ]
    blob = bytearray(struct.pack('!IHHiIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1))
    for when, usec, raw in packets:
        blob += struct.pack('!IIII', when, usec, len(raw), len(raw)) + raw
    path.write_bytes(bytes(blob))


# ── Filter construction ─────────────────────────────────────────────────────

def test_capture_filter():
    """BPF filters narrow by port and host, and never by direction."""
    assert _capture_filter([DEV], None, [81]) == 'tcp port 81 and host 192.168.1.230'
    assert _capture_filter([DEV, DEV2], None, [81]) == \
        'tcp port 81 and (host 192.168.1.230 or host 192.168.1.86)'
    assert _capture_filter([DEV], None, [81, 80]) == \
        '(tcp port 81 or tcp port 80) and host 192.168.1.230'
    assert _capture_filter([DEV], HOST, [81]) == \
        'tcp port 81 and host 192.168.1.230 and host 192.168.1.67'
    assert _capture_filter([], None, [81]) == 'tcp port 81'

    # Direction must never reach the capture filter: half a stream means the
    # 101 Switching Protocols reply is dropped and websocket never dissects.
    for devices in ([DEV], [DEV, DEV2], []):
        text = _capture_filter(devices, None, [81])
        assert 'dst host' not in text and 'src host' not in text, text
    print("✓ capture filters")


def test_display_filter():
    """Display filters carry the direction, and always require websocket."""
    both = _display_filter([DEV], None, [81], False, False)
    assert both == 'websocket and (ip.src == 192.168.1.230 or ip.dst == 192.168.1.230)'
    # Passing both flags is the same as passing neither.
    assert _display_filter([DEV], None, [81], True, True) == both

    assert _display_filter([DEV], None, [81], True, False) == \
        'websocket and (ip.dst == 192.168.1.230)'
    assert _display_filter([DEV], None, [81], False, True) == \
        'websocket and (ip.src == 192.168.1.230)'
    assert _display_filter([DEV, DEV2], None, [81], True, False) == \
        'websocket and (ip.dst == 192.168.1.230 or ip.dst == 192.168.1.86)'

    # --any: no device to orient by, so direction keys off the listening port,
    # which keeps "requests" meaning every client's requests rather than ours.
    assert _display_filter([], None, [81], True, False) == 'websocket and tcp.dstport == 81'
    assert _display_filter([], None, [81], False, True) == 'websocket and tcp.srcport == 81'
    assert _display_filter([], None, [81, 80], True, False) == \
        'websocket and (tcp.dstport == 81 or tcp.dstport == 80)'
    assert _display_filter([], None, [81], False, False) == 'websocket'

    assert _display_filter([DEV], HOST, [81], False, False).endswith(
        'and (ip.src == 192.168.1.67 or ip.dst == 192.168.1.67)')
    print("✓ display filters")


def test_jq_envelope_adapts():
    """Constant fields are dropped; --bare and --full override that."""
    minimal = _jq_program(False, False, False, False, False, None, None, None)
    assert minimal.rstrip().endswith('| {msg: $msg}')

    with_dir = _jq_program(False, True, False, False, False, None, None, None)
    assert 'dir: (if $out' in with_dir

    full = _jq_program(True, True, True, True, False, None, None, None)
    for field in ('ts: $clock', 'dir: ', 'peer: $peer', 'src: $src', 'dst: $dst'):
        assert field in full, field

    bare = _jq_program(True, True, True, True, True, None, None, None)
    assert bare.rstrip().endswith('| $msg')
    assert '{msg:' not in bare

    filtered = _jq_program(False, False, False, False, False, 'setVars', 'fps', None)
    assert 'select($raw | test($grep))' in filtered
    assert 'select($raw | test($exclude) | not)' in filtered

    extra = _jq_program(False, False, False, False, False, None, None, 'select(.msg.fps)')
    assert extra.rstrip().endswith('| select(.msg.fps)')

    # $raw has to be bound before the try, or `catch` sees the error message
    # instead of the payload and non-JSON frames vanish.
    assert '| . as $raw' in minimal
    assert 'try ($raw | fromjson) catch $raw' in minimal
    print("✓ jq program")


def test_resolve_others():
    """--others accepts every --ip form, dedupes, and reports its own name."""
    original_read, original_host = cli_utils._read_cache, cli_utils.get_host_ip
    cli_utils._read_cache = lambda: FAKE_CACHE
    cli_utils.get_host_ip = lambda: HOST
    try:
        assert _resolve_others(None) == []
        assert _resolve_others('') == []
        assert _resolve_others(f'{DEV2}') == [DEV2]
        assert _resolve_others('86, bike2') == [DEV2]           # same device twice
        assert _resolve_others(f'bike1,{DEV2}') == [DEV, DEV2]
        assert _resolve_others(f'http://{DEV2}/') == [DEV2]

        for spec, expected in [('auto', 'auto-discover'), ('nope', '--others'),
                               ('999', '--others')]:
            try:
                _resolve_others(spec)
            except click.ClickException as e:
                assert expected in e.message, f"{spec!r}: got {e.message!r}"
            else:
                raise AssertionError(f"--others {spec!r} should have failed")
    finally:
        cli_utils._read_cache, cli_utils.get_host_ip = original_read, original_host
    print("✓ --others resolution")


def test_udp_filters():
    """--udp swaps the protocol in the BPF filter and never filters direction."""
    assert _capture_filter([], None, [1889], proto='udp') == 'udp port 1889'
    assert _capture_filter([DEV2], HOST, [1889], proto='udp') == \
        'udp port 1889 and host 192.168.1.86 and host 192.168.1.67'

    assert _udp_display_filter([], None, [1889]) == 'udp.port == 1889'
    assert _udp_display_filter([], None, [1889, 1890]) == '(udp.port == 1889 or udp.port == 1890)'
    assert _udp_display_filter([DEV2], None, [1889]) == \
        'udp.port == 1889 and (ip.src == 192.168.1.86 or ip.dst == 192.168.1.86)'
    assert _udp_display_filter([DEV], HOST, [1889]).endswith(
        'and (ip.src == 192.168.1.67 or ip.dst == 192.168.1.67)')
    print("✓ udp filters")


def test_udp_jq_program():
    """Direction is a packet-type select; the envelope adapts like ws mode."""
    # The readable view drops the 32 raw bands a sensor frame carries; the
    # sparkline in the same record is what a human reads.
    plain = _jq_udp_program(False, False, False, None, None, None)
    assert plain.rstrip().endswith('| ($rec | del(.bins))')
    assert 'select($rec.kind' not in plain
    assert 'def le32' in plain and 'def wrap32' in plain
    assert 'def le16' in plain and 'def spark' in plain

    assert '| select($rec.kind == "timeSync" or $rec.kind == "sensor")' in \
        _jq_udp_program(False, False, False, None, None, None, direction='requests')
    assert '| select($rec.kind == "beacon")' in \
        _jq_udp_program(False, False, False, None, None, None, direction='responses')
    assert '| select($rec.kind == "sensor")' in \
        _jq_udp_program(False, False, False, None, None, None, sensor_only=True)

    full = _jq_udp_program(True, True, False, None, None, None)
    assert full.rstrip().endswith(
        '| {ts: $clock} + ($rec | del(.bins)) + {dst: $dst, sport: $sport, dport: $dport}')

    bare = _jq_udp_program(True, True, True, None, None, 'select(.kind == "beacon")')
    assert '$clock' not in bare
    assert bare.rstrip().endswith('| $rec\n| select(.kind == "beacon")')

    filtered = _jq_udp_program(False, False, False, 'bike', 'sync', None)
    assert 'select(($rec | tojson) | test($grep))' in filtered
    assert 'select(($rec | tojson) | test($exclude) | not)' in filtered
    print("✓ udp jq program")


# ── Real pipeline round trip ────────────────────────────────────────────────

def _run_pipeline(pcap, devices, host, ports, requests, responses,
                  midstream=False, **program_kwargs):
    """Run the exact tshark|jq pair the command builds, over a saved capture."""
    tshark = shutil.which('tshark')
    jq = shutil.which('jq')
    assert tshark, "tshark is required by `pb snoop` and by this test; install it"
    assert jq, "jq is required by `pb snoop` and by this test; install it"

    decode = 'websocket' if midstream else 'http'
    cmd = [tshark, '-r', str(pcap), '-l', '-n', '-q']
    for port in ports:
        cmd += ['-d', f'tcp.port=={port},{decode}']
    cmd += ['-Y', _display_filter(devices, host, ports, requests, responses), '-T', 'ek']
    for field in snoop._TSHARK_FIELDS:
        cmd += ['-e', field]

    kwargs = dict(show_time=False, show_dir=True, show_peer=False,
                  show_endpoints=False, bare=False, grep=None, exclude=None, extra=None)
    kwargs.update(program_kwargs)

    jq_cmd = [jq, '-c', '-M',
              '--argjson', 'devs', '[' + ','.join(f'"{d}"' for d in devices) + ']',
              '--argjson', 'ports', '[' + ','.join(f'"{p}"' for p in ports) + ']',
              '--arg', 'host', host or '']
    if kwargs['grep']:
        jq_cmd += ['--arg', 'grep', kwargs['grep']]
    if kwargs['exclude']:
        jq_cmd += ['--arg', 'exclude', kwargs['exclude']]
    jq_cmd += [_jq_program(**kwargs)]

    captured = subprocess.run(cmd, capture_output=True, timeout=30)
    assert captured.returncode == 0, captured.stderr.decode()
    rendered = subprocess.run(jq_cmd, input=captured.stdout, capture_output=True, timeout=30)
    assert rendered.returncode == 0, rendered.stderr.decode()
    return [line for line in rendered.stdout.decode().splitlines() if line.strip()]


def test_pipeline_round_trip():
    """Decode a real capture and check every frame, in order, with direction."""
    with tempfile.TemporaryDirectory() as tmp:
        pcap = pathlib.Path(tmp) / 'ws.pcap'
        _write_fixture(pcap)

        lines = _run_pipeline(pcap, [DEV], None, [81], False, False)
        assert len(lines) == len(EXPECTED), \
            f"expected {len(EXPECTED)} frames, got {len(lines)}: {lines}"
        for line, (outbound, _) in zip(lines, EXPECTED):
            assert ('\\u2192' in line or '→' in line) == outbound, line

        # The two frames that shared one packet must land as two records.
        assert any('"fps":41' in line for line in lines)
        assert any('activeProgram' in line for line in lines)

        # Direction filters.
        assert len(_run_pipeline(pcap, [DEV], None, [81], True, False)) == 2
        assert len(_run_pipeline(pcap, [DEV], None, [81], False, True)) == 3

        # --any orients by listening port, so it agrees with the named case.
        assert len(_run_pipeline(pcap, [], None, [81], True, False)) == 2
        assert len(_run_pipeline(pcap, [], None, [81], False, True)) == 3

        # grep / exclude / bare.
        assert _run_pipeline(pcap, [DEV], None, [81], False, False,
                             grep='setVars') == ['{"dir":"\u2192","msg":{"setVars":{"speed":0.5}}}']
        assert len(_run_pipeline(pcap, [DEV], None, [81], False, False, exclude='fps')) == 3
        assert _run_pipeline(pcap, [DEV], None, [81], False, False,
                             bare=True)[0] == '{"getConfig":true}'
    print("✓ pipeline round trip")


def _run_udp_pipeline(pcap, devices, host, requests=False, responses=False, **program_kwargs):
    """Run the tshark|jq pair `--udp` builds, over a saved capture."""
    tshark = shutil.which('tshark')
    jq = shutil.which('jq')
    assert tshark, "tshark is required by `pb snoop` and by this test; install it"
    assert jq, "jq is required by `pb snoop` and by this test; install it"

    cmd = [tshark, '-r', str(pcap), '-l', '-n', '-q',
           '-Y', _udp_display_filter(devices, host, [1889]), '-T', 'ek']
    for field in snoop._TSHARK_UDP_FIELDS:
        cmd += ['-e', field]

    kwargs = dict(show_time=False, show_endpoints=False, bare=False,
                  grep=None, exclude=None, extra=None, sensor_only=False)
    kwargs.update(program_kwargs)
    if requests != responses:
        kwargs['direction'] = 'requests' if requests else 'responses'

    jq_cmd = [jq, '-c', '-M']
    if kwargs['grep']:
        jq_cmd += ['--arg', 'grep', kwargs['grep']]
    if kwargs['exclude']:
        jq_cmd += ['--arg', 'exclude', kwargs['exclude']]
    jq_cmd += [_jq_udp_program(**kwargs)]

    captured = subprocess.run(cmd, capture_output=True, timeout=30)
    assert captured.returncode == 0, captured.stderr.decode()
    rendered = subprocess.run(jq_cmd, input=captured.stdout, capture_output=True, timeout=30)
    assert rendered.returncode == 0, rendered.stderr.decode()
    return [json.loads(line) for line in rendered.stdout.decode().splitlines() if line.strip()]


def test_udp_pipeline_round_trip():
    """Decode a real beacon capture: the jq little-endian decoder against tshark's hex."""
    with tempfile.TemporaryDirectory() as tmp:
        pcap = pathlib.Path(tmp) / 'beacons.pcap'
        _write_udp_fixture(pcap)

        records = _run_udp_pipeline(pcap, [], None)
        assert len(records) == len(UDP_EXPECTED), records
        for got, want in zip(records, UDP_EXPECTED):
            for key, value in want.items():
                assert got.get(key) == value, f"{key}: {got}"
        # senderId is the same four bytes as the dotted address, little-endian.
        assert records[0]['sender_id'] == struct.unpack('<L', bytes([192, 168, 1, 86]))[0]
        assert records[1]['sender_id'] == records[0]['sender_id']
        # Skew is a signed 32-bit difference, so it never comes out as 4e9.
        assert all(-2**31 <= r['skew_ms'] < 2**31 for r in records if r['kind'] == 'beacon')
        assert 'skew_ms' not in records[1]

        # Direction: requests go TO a Pixelblaze (timeSync and sensor frames),
        # responses come FROM one (beacons).
        assert [r['kind'] for r in _run_udp_pipeline(pcap, [], None, requests=True)] \
            == ['timeSync', 'sensor']
        assert [r['kind'] for r in _run_udp_pipeline(pcap, [], None, responses=True)] == ['beacon', 'beacon']

        # A named device keeps its beacon and everything sent to it, not others'.
        assert [r['src'] for r in _run_udp_pipeline(pcap, [DEV2], None)] == [DEV2, HOST, HOST]
        assert [r['src'] for r in _run_udp_pipeline(pcap, [DEV], None)] == [DEV]

        # grep / exclude / full / bare.
        assert [r['src'] for r in _run_udp_pipeline(pcap, [], None, grep='1\\.230')] == [DEV]
        assert len(_run_udp_pipeline(pcap, [], None, exclude='timeSync')) == 3
        full = _run_udp_pipeline(pcap, [], None, show_time=True, show_endpoints=True)[0]
        assert full['dst'] == '192.168.1.255' and full['dport'] == '1889' and 'ts' in full
        assert list(full)[0] == 'ts'
        assert 'dport' not in _run_udp_pipeline(pcap, [], None, bare=True)[0]
    print("✓ udp pipeline round trip")


def test_sensor_frame_decode():
    """Decode a sensor board datagram: 16-bit offsets, scaling and the sparkline."""
    with tempfile.TemporaryDirectory() as tmp:
        pcap = pathlib.Path(tmp) / 'sensor.pcap'
        _write_udp_fixture(pcap)

        # --sensor drops the beacons and timeSyncs.
        only = _run_udp_pipeline(pcap, [], None, sensor_only=True)
        assert [r['kind'] for r in only] == ['sensor'], only
        record = only[0]

        # Scaling: uint16 at 65536 = 1.0, accelerometer signed at 32768 = 1.0,
        # maxFrequency straight through in Hz. Measured against firmware 3.70.
        assert record['energy'] == 0.25
        assert record['max_mag'] == 0.5
        assert record['max_hz'] == 1170
        assert record['light'] == 0.125
        assert record['accel'] == [0.5, -0.25, 0.0]
        assert record['analog'] == [0.75] * 5
        assert abs(record['peak'] - SENSOR_BINS[-1]) <= 1e-4

        # --bare keeps the 32 bands; the readable view swaps them for a sparkline.
        # Values are rounded to 4 decimals on the way out, so compare loosely.
        bare = _run_udp_pipeline(pcap, [], None, sensor_only=True, bare=True)[0]
        assert len(bare['bins']) == 32, bare['bins']
        assert all(abs(got - want) <= 1e-4 for got, want in zip(bare['bins'], SENSOR_BINS)), \
            bare['bins']
        assert 'bins' not in record

        # The ramp has to read as a ramp: bands are scaled against the loudest
        # one in the frame, so band 31 is full height and band 0 is empty.
        spectrum = record['spectrum']
        assert len(spectrum) == 32, spectrum
        assert spectrum[-1] == '\u2588' and spectrum[0] == '\u2581', spectrum
        assert list(spectrum) == sorted(spectrum), spectrum
    print("✓ sensor frame decode")


def test_midstream_decode():
    """--midstream is what makes an already-open connection decodable.

    Without the HTTP upgrade in the capture, tshark's http dissector never
    hands off to websocket and nothing is decoded — the exact failure the
    flag exists to fix.
    """
    with tempfile.TemporaryDirectory() as tmp:
        pcap = pathlib.Path(tmp) / 'midstream.pcap'
        _write_fixture(pcap, handshake=False)

        assert _run_pipeline(pcap, [DEV], None, [81], False, False) == []
        assert len(_run_pipeline(pcap, [DEV], None, [81], False, False,
                                 midstream=True)) == len(EXPECTED)
    print("✓ midstream decode")


# ── Live capture path ───────────────────────────────────────────────────────

def _run_cli(args, timeout=30):
    """Invoke the real `pb` command in a subprocess.

    A subprocess rather than click's CliRunner because the output we care
    about is written to fd 1 by jq, not by Python — CliRunner would not see
    a byte of it.
    """
    code = 'from pixelblaze.cli.cli import main; main()'
    proc = subprocess.run([sys.executable, '-c', code] + args,
                          capture_output=True, timeout=timeout,
                          cwd=str(pathlib.Path(__file__).resolve().parents[2]))
    return proc


def _feed_fifo(fifo: pathlib.Path, payload: bytes):
    """Push a capture into a FIFO once tshark opens the read end.

    tshark treats a FIFO given to -i as a live interface, which exercises the
    whole live code path -- -i, the BPF capture filter, -w, the process
    plumbing -- on a machine with no capture permissions and no Pixelblaze.
    """
    def writer():
        try:
            with open(fifo, 'wb') as handle:   # blocks until tshark reads
                handle.write(payload)
        except OSError:
            pass
    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    return thread


def test_live_capture_path():
    """Exercise -i / -f / -w against a FIFO standing in for a real interface."""
    assert shutil.which('tshark'), "tshark is required by `pb snoop` and by this test"

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        pcap = tmpdir / 'ws.pcap'
        _write_fixture(pcap)
        blob = pcap.read_bytes()

        fifo = tmpdir / 'fifo'
        os.mkfifo(fifo)
        _feed_fifo(fifo, blob)
        plain = _run_cli(['--ip', DEV, 'snoop', '-i', str(fifo)])
        assert plain.returncode == 0, plain.stderr.decode()
        assert len(plain.stdout.decode().splitlines()) == len(EXPECTED), plain.stdout

        # --write is the case that bites: tshark refuses a display filter while
        # saving a live capture, so the command has to narrow with the BPF
        # filter and move the rest into jq.
        fifo2 = tmpdir / 'fifo2'
        saved = tmpdir / 'saved.pcapng'
        os.mkfifo(fifo2)
        _feed_fifo(fifo2, blob)
        written = _run_cli(['--ip', DEV, 'snoop', '-i', str(fifo2), '-w', str(saved)])
        assert written.returncode == 0, written.stderr.decode()
        assert b"aren't supported when capturing" not in written.stderr, written.stderr
        assert len(written.stdout.decode().splitlines()) == len(EXPECTED), written.stdout

        # The saved file keeps the whole stream, handshake included, so it
        # replays through --read without needing --midstream.
        assert saved.exists() and saved.stat().st_size > 0
        replayed = _run_cli(['--ip', DEV, 'snoop', '--read', str(saved)])
        assert replayed.returncode == 0, replayed.stderr.decode()
        assert len(replayed.stdout.decode().splitlines()) == len(EXPECTED), replayed.stdout

        # Direction still works while saving, now applied by jq.
        fifo3 = tmpdir / 'fifo3'
        os.mkfifo(fifo3)
        _feed_fifo(fifo3, blob)
        only_requests = _run_cli(['--ip', DEV, 'snoop', '-i', str(fifo3),
                                  '-w', str(tmpdir / 'r.pcapng'), '--requests'])
        assert only_requests.returncode == 0, only_requests.stderr.decode()
        lines = only_requests.stdout.decode().splitlines()
        assert len(lines) == 2, lines
        assert all('fps' not in line for line in lines), lines
    print("✓ live capture path")


def test_udp_live_capture_path():
    """--udp through a FIFO interface, saving, replaying, and the `watch` alias."""
    assert shutil.which('tshark'), "tshark is required by `pb snoop` and by this test"

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        pcap = tmpdir / 'beacons.pcap'
        _write_udp_fixture(pcap)
        blob = pcap.read_bytes()

        # No --ip: must not attempt discovery, must see every device.
        fifo = tmpdir / 'fifo'
        os.mkfifo(fifo)
        _feed_fifo(fifo, blob)
        plain = _run_cli(['watch', '--udp', '-i', str(fifo)])
        assert plain.returncode == 0, plain.stderr.decode()
        kinds = [json.loads(line)['kind'] for line in plain.stdout.decode().splitlines()]
        assert kinds == ['beacon', 'timeSync', 'beacon', 'sensor'], plain.stdout
        assert b'Listening for beacons' not in plain.stderr, plain.stderr

        # --write plus a direction, with the narrowing done by jq.
        fifo2 = tmpdir / 'fifo2'
        saved = tmpdir / 'saved.pcapng'
        os.mkfifo(fifo2)
        _feed_fifo(fifo2, blob)
        written = _run_cli(['snoop', '--beacons', '-i', str(fifo2), '-w', str(saved), '--responses'])
        assert written.returncode == 0, written.stderr.decode()
        assert b"aren't supported when capturing" not in written.stderr, written.stderr
        lines = written.stdout.decode().splitlines()
        assert [json.loads(line)['kind'] for line in lines] == ['beacon', 'beacon'], lines

        assert saved.exists() and saved.stat().st_size > 0
        replayed = _run_cli(['snoop', '--udp', '--read', str(saved)])
        assert replayed.returncode == 0, replayed.stderr.decode()
        assert len(replayed.stdout.decode().splitlines()) == 4, replayed.stdout

        # --sensor implies --udp and keeps only the sensor board frames.
        fifo4 = tmpdir / 'fifo4'
        os.mkfifo(fifo4)
        _feed_fifo(fifo4, blob)
        sensed = _run_cli(['snoop', '--sensor', '-i', str(fifo4)])
        assert sensed.returncode == 0, sensed.stderr.decode()
        records = [json.loads(line) for line in sensed.stdout.decode().splitlines()]
        assert [r['kind'] for r in records] == ['sensor'], records
        assert len(records[0]['spectrum']) == 32 and 'bins' not in records[0]

        # An explicit --ip narrows to that device without discovery.
        fifo3 = tmpdir / 'fifo3'
        os.mkfifo(fifo3)
        _feed_fifo(fifo3, blob)
        narrowed = _run_cli(['--ip', DEV, 'watch', '--udp', '-i', str(fifo3)])
        assert narrowed.returncode == 0, narrowed.stderr.decode()
        srcs = [json.loads(line)['src'] for line in narrowed.stdout.decode().splitlines()]
        assert srcs == [DEV], srcs
    print("✓ udp live capture path")


def main():
    test_capture_filter()
    test_display_filter()
    test_jq_envelope_adapts()
    test_resolve_others()
    test_udp_filters()
    test_udp_jq_program()
    test_pipeline_round_trip()
    test_udp_pipeline_round_trip()
    test_sensor_frame_decode()
    test_midstream_decode()
    test_live_capture_path()
    test_udp_live_capture_path()
    print("\nAll snoop tests passed.")


if __name__ == '__main__':
    main()


# ── --http and --all ────────────────────────────────────────────────────────

def _jq(program, lines):
    """Push synthetic `tshark -T ek` objects through the real jq program."""
    jq = shutil.which('jq')
    if not jq:                      # pragma: no cover - jq is a hard dep of snoop
        raise AssertionError("jq is required for these tests")
    src = "\n".join(json.dumps(l) for l in lines)
    out = subprocess.run([jq, '-c', '-M', program], input=src,
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return [json.loads(l) for l in out.stdout.splitlines() if l.strip()]


def _ek(**fields):
    """tshark -T ek wraps every field value in a list."""
    return {'layers': {k: [str(v)] for k, v in fields.items()}}


def test_http_program_decodes_requests_and_responses():
    """The firmware's endpoints — /update, /recovery.html, /wifistatus — are
    invisible to a websocket-only capture, which is the whole point of --http."""
    prog = _jq_http_program(show_time=False, bare=False, grep=None, exclude=None, extra=None)
    got = _jq(prog, [
        _ek(ip_src='10.0.0.1', ip_dst='10.0.0.5',
            http_request_method='POST', http_request_uri='/update'),
        _ek(ip_src='10.0.0.5', ip_dst='10.0.0.1',
            http_response_code='200', http_content_type='text/html',
            http_content_length='57'),
        _ek(ip_src='10.0.0.5', ip_dst='10.0.0.1'),          # neither: dropped
    ])
    assert got == [
        {'kind': 'http', 'src': '10.0.0.1', 'dst': '10.0.0.5',
         'method': 'POST', 'uri': '/update'},
        {'kind': 'http', 'src': '10.0.0.5', 'dst': '10.0.0.1',
         'status': 200, 'contentType': 'text/html', 'bytes': 57},
    ], got


def test_http_program_bare_and_filters():
    bare = _jq_http_program(show_time=False, bare=True, grep=None, exclude=None, extra=None)
    got = _jq(bare, [_ek(ip_src='a', ip_dst='b', http_request_method='GET',
                         http_request_uri='/wifistatus')])
    assert got == [{'method': 'GET', 'uri': '/wifistatus'}], got

    only = _jq_http_program(show_time=False, bare=False, grep='update',
                            exclude=None, extra=None)
    got = _jq(only, [
        _ek(ip_src='a', ip_dst='b', http_request_method='POST', http_request_uri='/update'),
        _ek(ip_src='a', ip_dst='b', http_request_method='GET', http_request_uri='/recovery.html'),
    ])
    assert [g['uri'] for g in got] == ['/update'], got


def test_all_program_tags_each_protocol():
    """One timeline, three protocols. An OTA is an HTTP POST whose real verdict
    arrives as websocket upgradeState frames — seeing one without the other is
    how you end up believing the HTTP response."""
    prog = _jq_all_program(show_time=False, grep=None, exclude=None, extra=None)
    got = _jq(prog, [
        _ek(ip_src='10.0.0.1', ip_dst='10.0.0.5',
            http_request_method='POST', http_request_uri='/update'),
        _ek(ip_src='10.0.0.5', ip_dst='10.0.0.1',
            websocket_payload_text='{"upgradeState":3}'),
        _ek(ip_src='10.0.0.5', ip_dst='10.0.0.1', http_response_code='200',
            http_content_type='text/html'),
        _ek(ip_src='10.0.0.5', ip_dst='10.0.0.1', data_data='2a000000'),
        _ek(ip_src='10.0.0.5', ip_dst='10.0.0.1'),           # nothing decodable
    ])
    assert [g['kind'] for g in got] == ['http', 'ws', 'http', 'udp'], got
    assert got[0]['uri'] == '/update'
    assert got[1]['text'] == '{"upgradeState":3}'
    assert got[2]['status'] == 200
    assert got[3]['bytes'] == 4              # 8 hex chars -> 4 bytes


def test_all_and_udp_are_mutually_exclusive():
    """They are different captures, and --all is a superset — say so rather
    than silently honouring one."""
    from click.testing import CliRunner
    from pixelblaze.cli.cli import pixelblaze
    res = CliRunner().invoke(pixelblaze, ['--ip', '10.0.0.5', 'snoop',
                                          '--all', '--udp', '--dry-run'])
    assert res.exit_code != 0
    assert 'different captures' in res.output, res.output
