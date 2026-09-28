"""CLI utilities for Pixelblaze controller."""

from __future__ import annotations

import copy

import os
import re
import sys
import time
import socket
import click
import json5
import json
import pathlib
import datetime
import errno
import io
import select
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from functools import wraps
from typing import Callable, Optional
from pixelblaze.pixelblaze import Pixelblaze, localIPv4Interfaces

log = lambda *args, **kwargs: click.echo(*args, err=True, *kwargs)
jsons = lambda x: click.echo(json.dumps(x, separators=(',', ':')))

# Opportunistic cache refresh: skip if the entry was refreshed less than this many seconds ago.
# Override with `pb cache refresh` (force) or env PB_CACHE_TTL.
CACHE_TTL_SECONDS = 60 * 60


def get_cache_dir():
    """Get the cache directory for Pixelblaze CLI, creating it if needed."""
    # Use ~/.config/pixelblaze on Unix-like systems, ~/AppData/Local/pixelblaze on Windows
    if sys.platform == 'win32':
        cache_dir = pathlib.Path.home() / 'AppData' / 'Local' / 'pixelblaze'
    else:
        config_home = pathlib.Path.home() / '.config'
        cache_dir = config_home / 'pixelblaze'

    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


# A dotted quad, shape-checked here and range-checked in is_ipv4().
_IPV4_RE = re.compile(r'^(?:\d{1,3}\.){3}\d{1,3}$')

# Host portion of a URL pasted out of a browser's address bar.
_URL_HOST_RE = re.compile(r'^https?://([^/?#]*)', re.IGNORECASE)


def is_ipv4(value: str) -> bool:
    """True if value is a well-formed dotted-quad IPv4 address."""
    if not value or not _IPV4_RE.match(value):
        return False
    return all(int(octet) <= 255 for octet in value.split('.'))


def get_host_ip() -> str:
    """Get the local machine's outbound IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Standard trick: connect() a UDP socket to an unroutable address —
        # no packets are actually sent; the kernel just resolves which local
        # interface WOULD be used, and getsockname() reports its IP.
        # 10.255.255.255 is the RFC 919 limited-broadcast address for the
        # 10.0.0.0/8 private range, so this works even without a default
        # gateway (e.g. when joined only to a PB's AP-mode SSID).
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ''


def get_host_ips() -> set:
    """Every address this machine answers to, not just the outbound one.

    `get_host_ip()` resolves the default route alone. On a host with more than
    one interface -- a Pi hosting an access point for its Pixelblazes while
    plugged into ethernet -- the other addresses are just as much "us", and
    treating them as devices puts the host itself in `pb find` output. It reads
    convincingly too: probe a device and it lists us among its sync-group peers
    for a while, and anything we serve on port 80 answers the probe.
    """
    addresses = {address for address, _ in localIPv4Interfaces()}
    outbound = get_host_ip()
    if outbound:
        addresses.add(outbound)
    return addresses


# ── What we know about a fleet, in two files ─────────────────────────────
#
# `devices.json` is the INVENTORY: which boards exist, what they are called,
# and every (name, address) pair each has ever been seen at, with the first
# time it was seen. All of it stable — a new row appears when a device is new,
# renamed, or has moved — which is exactly what makes it worth keeping in
# version control and pointing a symlink at.
#
# `cache.json` is the LOCAL STATE: where each board was last seen and when,
# the last device addressed, and the bulky `--full` blobs (settings, the whole
# pattern list). Volatile by nature — `lastSeenAt` moves on every run and a
# pattern list is hundreds of ids — so it stays put and stays untracked.
#
# BOTH ARE KEYED BY chipId, because an address is not an identity: one board
# is 192.168.1.24 on the router today and 192.168.4.3 once a fleet is
# re-formed behind a leader's access point. chipId is a property of the chip.
# It is NOT globally unique — these are ~23-bit values, not a 48-bit MAC — so
# it identifies a fleet's devices, not every Pixelblaze ever made, and a
# collision between two boards you own shows up as one device that keeps
# changing its name rather than silently doing the wrong thing.
CACHE_VERSION = 3


def devices_path() -> pathlib.Path:
    """The inventory file. `PB_DEVICES_FILE` moves it — e.g. into a repo."""
    override = os.environ.get('PB_DEVICES_FILE')
    return pathlib.Path(override) if override else get_cache_dir() / 'devices.json'


def _read_json(path: pathlib.Path, fallback: dict) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return dict(fallback)


def _read_devices() -> dict:
    """The tracked inventory: {chipId: {name, seen: [...]}}."""
    return _read_json(devices_path(), {'version': CACHE_VERSION, 'devices': {}})


def _read_cache() -> dict:
    """Local state: {chipId: {ip, lastSeenAt, settings, ...}} plus lastIp."""
    return _read_json(get_cache_dir() / 'cache.json',
                      {'version': CACHE_VERSION, 'lastIp': None, 'lastChip': None, 'devices': {}})


# One process writing from several threads at once is the normal case now
# that --ip fans out, and a half-written file reads as "nothing known".
_CACHE_LOCK = threading.Lock()


def _write_json(path: pathlib.Path, data: dict):
    """Write atomically, one writer at a time, and only if it changed.

    Write-if-changed matters for the inventory: it is a file in a repo, and a
    run that learned nothing should leave nothing to commit.
    """
    try:
        rendered = json.dumps(data, indent=2, sort_keys=True) + '\n'
        with _CACHE_LOCK:
            try:
                if path.exists() and path.read_text() == rendered:
                    return
            except Exception:
                pass
            path.parent.mkdir(parents=True, exist_ok=True)
            # Beside the real file, so the rename is on one filesystem and
            # therefore atomic: a reader sees the old file or the new one,
            # never a truncated one. `os.replace` through a symlink writes the
            # file it points at, which is how the repo copy gets updated.
            temporary = path.parent / f'{path.name}.{os.getpid()}.{threading.get_ident()}'
            temporary.write_text(rendered)
            os.replace(temporary, path.resolve() if path.is_symlink() else path)
    except Exception:
        pass


def _write_devices(data: dict):
    _write_json(devices_path(), data)


def _write_cache(cache: dict):
    _write_json(get_cache_dir() / 'cache.json', cache)


# Per-run discovery facts (how a device was found, which ports answered this
# time). They ride along in `pb find` output but are not durable device info.
_TRANSIENT_KEYS = frozenset(('via', 'http', 'ws', 'error'))


def chip_of(entry: dict) -> str:
    """The board an entry is, as a string key, or '' before it has said.

    `chipId` is reported by getConfig and is the only durable identity a
    Pixelblaze has. An address is not one.
    """
    chip = (entry.get('settings') or {}).get('chipId') or entry.get('chipId')
    return str(chip) if chip not in (None, '') else ''


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def record_sighting(inventory: dict, chip: str, name: str, ip: str, when: str = '') -> bool:
    """Note that `chip` was seen as (`name`, `ip`). True if that was new.

    The list is append-only and `firstSeenAt` NEVER moves: the question it
    answers is "when did this device first appear under this name at this
    address", and a device coming back is not a new answer. A device that
    moves, or is renamed, gets a new row — the old one stays, which is the
    history.
    """
    if not chip:
        return False
    entry = inventory.setdefault(chip, {'chipId': chip, 'seen': []})
    if name and entry.get('name') != name:
        entry['name'] = name            # the current name; the history keeps the rest
    seen = entry.setdefault('seen', [])
    for row in seen:
        if row.get('ip') == ip and row.get('name', '') == (name or ''):
            return False
    seen.append({'name': name or '', 'ip': ip, 'firstSeenAt': when or _now()})
    seen.sort(key=lambda r: (r.get('firstSeenAt') or '', r.get('ip') or ''))
    return True


def update_device_cache(devices: list[dict]):
    """Record what was just seen: identity to the inventory, the rest locally."""
    inventory = _read_devices()
    known = inventory.setdefault('devices', {})
    cache = _read_cache()
    state = cache.setdefault('devices', {})
    host_ip = get_host_ip()
    when = _now()
    changed = False

    for dev in devices:
        ip = dev.get('ip')
        chip = chip_of(dev)
        if not ip:
            continue
        if not chip:
            # Nothing to file it under. A fast probe that never learned who
            # answered is not a device record — it is an address, and the
            # inventory already remembers every address a board has had.
            continue
        # A NAME IS PART OF AN IDENTITY, so it only changes on evidence: this
        # record carries a chipId, so whatever it says about itself is first
        # hand. Anything that merely believes it knows who lives at an address
        # has no chipId and never gets here.
        name = dev.get('name') or (known.get(chip) or {}).get('name') or ''
        changed |= record_sighting(known, chip, name, ip, when)

        entry = state.setdefault(chip, {'chipId': chip})
        for k, v in dev.items():
            if v is None or v == '' or k in _TRANSIENT_KEYS:
                continue
            entry[k] = v
        entry['ip'] = ip
        entry['lastSeenAt'] = when
        if host_ip:
            entry['hostIp'] = host_ip

    if changed:
        inventory['version'] = CACHE_VERSION
        _write_devices(inventory)
    cache['version'] = CACHE_VERSION
    _write_cache(cache)


def cached_devices() -> list[dict]:
    """Every board known, newest sighting first, inventory and state merged.

    Each: chipId, name, ip (where it was last seen), ips (everywhere it has
    ever been, newest first), seen (the history), lastSeenAt, plus whatever
    `--full` last learned.
    """
    inventory = _read_devices().get('devices', {})
    state = _read_cache().get('devices', {})
    out = []
    for chip in set(inventory) | set(state):
        inv = inventory.get(chip, {})
        st = state.get(chip, {})
        rows = sorted(inv.get('seen', []), key=lambda r: r.get('firstSeenAt') or '', reverse=True)
        ips = []
        for ip in ([st.get('ip')] if st.get('ip') else []) + [r.get('ip') for r in rows]:
            if ip and ip not in ips:
                ips.append(ip)
        entry = dict(st)
        entry.update({
            'chipId': chip,
            'name': st.get('name') or inv.get('name') or '',
            'ip': ips[0] if ips else st.get('ip', ''),
            'ips': ips,
            'seen': rows,
        })
        out.append(entry)
    out.sort(key=lambda e: e.get('lastSeenAt') or '', reverse=True)
    return out


def cached_by_ip() -> dict:
    """`{address: entry}` for every address any board has ever answered at.

    The inventory is keyed by board; most of the CLI asks by address. An
    address a board was seen at MORE RECENTLY wins, so a reused address
    belongs to whoever has it now.
    """
    out: dict = {}
    claimed: dict = {}
    for entry in cached_devices():
        for ip in entry.get('ips', []):
            when = ''
            for row in entry.get('seen', []):
                if row.get('ip') == ip:
                    when = max(when, row.get('firstSeenAt') or '')
            if ip not in out or when > claimed.get(ip, ''):
                out[ip] = entry
                claimed[ip] = when
    return out


def cached_entry(ip: str) -> dict:
    """The board at an address, whichever of its addresses that is."""
    return cached_by_ip().get(ip, {})


def cached_names() -> dict:
    """`{ip: name}` for every address a board has ever answered at.

    `pb find` runs fast by default: it reports which addresses answered and
    says nothing about who they are, because finding that out means
    connecting to each one. But the names are already on disk from the last
    time anything did — free, and the whole reason anyone reads the output.
    """
    return {ip: e['name'] for ip, e in cached_by_ip().items() if e.get('name')}


def cached_addresses() -> list[str]:
    """Every address worth probing, most recently seen board first.

    Every address, not just current ones: an AP-mode 192.168.4.x address is
    exactly the one nothing else will ever tell you about again.
    """
    out: list[str] = []
    for entry in cached_devices():
        for ip in entry.get('ips', []):
            if ip not in out:
                out.append(ip)
    return out


def get_cached_ip():
    """Get the last used IP from cache."""
    return _read_cache().get('lastIp')


def cache_ip(ip_address):
    """Cache the IP address for future use, and the board it belongs to."""
    cache = _read_cache()
    cache['lastIp'] = ip_address
    chip = chip_of(cached_entry(ip_address))
    if chip:
        cache['lastChip'] = chip
    _write_cache(cache)


# Reusable Click options
no_save_option = click.option(
    '--no-save',
    is_flag=True,
    help='Do not save option (vars, sequencer, etc.) changes to flash (temporary only)'
)

# Reusable Click arguments
input_arg = click.argument('input', required=False)

def _check_ip_reachable(ip: str, timeout: float = 1.0) -> bool:
    """Check if a given IP has port 80 open (quick TCP connect check)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, 80))
        sock.close()
        return result == 0
    except Exception:
        return False


# The two ports a Pixelblaze answers on: 80 serves the web UI and the HTTP
# file endpoints, 81 the websocket API.
HTTP_PORT = 80
WS_PORT = 81
ADHOC_IP = "192.168.4.1"
_PROBE_TIMEOUT = 1.0
_IN_PROGRESS = {errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EAGAIN,
                getattr(errno, 'WSAEWOULDBLOCK', 10035)}


def _tcp_ports_open(ip: str, ports: tuple[int, ...] = (HTTP_PORT, WS_PORT),
                    timeout: float = _PROBE_TIMEOUT) -> dict[int, bool]:
    """Is anything listening on these ports? Non-blocking connects, all at once.

    This is the cheapest "is a Pixelblaze alive here" check there is, and
    deliberately the *only* kind of contact it makes: the connection is
    closed the instant it opens, and not a byte is ever sent. That matters.
    The firmware's websocket server has a handful of connection slots and a
    client that starts a session and drops it uncleanly can leave the device
    wedged until it reboots — so a liveness probe must not look like a client
    at all. A bare connect + FIN is indistinguishable from a port scan and is
    released by the device immediately.

    Returns {port: open} for every port asked. `80 open, 81 closed` is the
    classic hung-websocket-server state and worth surfacing to the user.
    """
    result = {port: False for port in ports}
    waiting: dict[socket.socket, int] = {}
    for port in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        try:
            err = sock.connect_ex((ip, port))
        except OSError:
            sock.close()
            continue
        if err == 0:
            result[port] = True
            sock.close()
        elif err in _IN_PROGRESS:
            waiting[sock] = port
        else:
            sock.close()

    deadline = time.monotonic() + timeout
    while waiting:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        socks = list(waiting)
        # A finished connect shows up writable; on Windows a *failed* one shows
        # up in the exceptional set instead, so watch both.
        _, writable, failed = select.select([], socks, socks, remaining)
        if not writable and not failed:
            break
        for sock in set(writable) | set(failed):
            port = waiting.pop(sock)
            try:
                result[port] = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0
            except OSError:
                result[port] = False
            sock.close()
    for sock in waiting:
        sock.close()
    return result


# Top-level keys promoted out of `settings` for quick display in `pb cache ls` / `pb find`.
_SUMMARY_KEYS = (
    'name', 'brandName', 'ver', 'pixelCount', 'ledType', 'dataSpeed',
    'colorOrder', 'brightness', 'maxBrightness', 'cpuSpeed',
    'networkPowerSave', 'sensorInputSource', 'discoveryEnable', 'timezone',
)


def _fetch_device_config(pb: Pixelblaze, ip: str, include_patterns: bool = True) -> dict:
    """Fetch full basic config from a connected Pixelblaze.

    Each sub-call is wrapped so a partial failure still persists what we got.
    `include_patterns=False` skips the heavier getPatternList() call (the existing
    cached pattern list, if any, is preserved by update_device_cache's merge).
    """
    info = {'ip': ip}

    # getConfigSettings primes pb.latestSequencer, so getConfigSequencer below is ~free.
    try:
        settings = pb.getConfigSettings()
        for key in _SUMMARY_KEYS:
            if key in settings:
                info[key] = settings[key]
        info['settings'] = settings
    except Exception as e:
        info['settingsError'] = str(e)

    try:
        seq = pb.getConfigSequencer()
        info['sequencer'] = seq
        active = seq.get('activeProgram', {}) if isinstance(seq, dict) else {}
        info['activePatternId'] = active.get('activeProgramId', '') or ''
    except Exception as e:
        info['sequencerError'] = str(e)

    if include_patterns:
        try:
            patterns = pb.getPatternList()
            info['patterns'] = patterns
            active_id = info.get('activePatternId', '')
            if active_id and active_id in patterns:
                info['activePatternName'] = patterns[active_id]
        except Exception as e:
            info['patternsError'] = str(e)

    info['lastSeenAt'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return info


def _get_device_info(ip: str) -> dict:
    """Connect to a Pixelblaze and return a full device info dict (parallel-safe)."""
    try:
        with Pixelblaze(ip) as pb:
            return _fetch_device_config(pb, ip=ip, include_patterns=True)
    except Exception:
        return {'ip': ip, 'name': ''}


def _cache_is_fresh(ip: str, ttl_seconds: int = CACHE_TTL_SECONDS) -> bool:
    """Return True if cache entry for ip exists, has a config snapshot, and is within ttl."""
    entry = cached_entry(ip)
    if not entry or 'settings' not in entry:
        return False
    last_seen = entry.get('lastSeenAt')
    if not last_seen:
        return False
    try:
        dt = datetime.datetime.fromisoformat(last_seen)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds()
        return age < ttl_seconds
    except Exception:
        return False


def maybe_refresh_cache(pb: Pixelblaze, ip: str, force: bool = False) -> bool:
    """Opportunistically refresh cached config for `ip` using an already-connected pb.

    Silent on any failure. Returns True if a refresh was attempted.
    Skips the patternList fetch on routine refreshes (when patterns are already cached)
    to keep the post-command cost minimal; `force=True` always re-fetches everything.
    """
    try:
        if not ip:
            return False
        if not force and _cache_is_fresh(ip):
            return False
        existing = cached_entry(ip)
        include_patterns = force or 'patterns' not in existing
        info = _fetch_device_config(pb, ip=ip, include_patterns=include_patterns)
        update_device_cache([info])
        return True
    except Exception:
        return False


def _subnet(ip: str) -> str:
    """The /24 an address is on, or '' if it isn't an address."""
    return ip.rsplit('.', 1)[0] if is_ipv4(ip) else ''


def _last_seen(entry: dict) -> str:
    """`lastSeenAt` as a sortable string. Missing sorts oldest."""
    return str(entry.get('lastSeenAt') or '')


def rank_matches(matches: list) -> list:
    """Order (ip, entry) pairs best-first, and say why the winner won.

    Returns [(ip, entry, reason), ...].

    Several cached devices can legitimately answer to one name: the same
    Pixelblaze moved between networks and left an entry behind on each, two
    really are called the same thing, or a device was on an ad-hoc AP once and
    a house network since. Refusing to choose is the wrong answer when exactly
    one of them is on the subnet this machine is on *right now* and the rest
    are from another building.

    So, best first:
      1. On this machine's /24 -- the one a packet can actually reach.
      2. Last seen from this machine's address (`hostIp`), which is weaker
         evidence of the same thing and covers a /24 we have since left.
      3. Most recently seen (`lastSeenAt`), newest first.
      4. The address, so the answer is stable when nothing else separates them.
    """
    host_ip = get_host_ip()
    here = _subnet(host_ip)

    def reason(ip, entry):
        if here and _subnet(ip) == here:
            return f"on this machine's subnet {here}.x"
        if host_ip and entry.get('hostIp') == host_ip:
            return "last seen from this machine"
        if _last_seen(entry):
            return f"most recently seen ({_last_seen(entry)[:19]})"
        return "first by address"

    def key(pair):
        ip, entry = pair
        return (0 if here and _subnet(ip) == here else 1,
                0 if host_ip and entry.get('hostIp') == host_ip else 1,
                # Newest first: strings sort ascending, so invert by negating
                # the comparison with a reversed sort on this field alone.
                _invert(_last_seen(entry)),
                ip)

    ranked = sorted(matches, key=key)
    return [(ip, entry, reason(ip, entry)) for ip, entry in ranked]


def ranked_pairs(ranked: list) -> list:
    """`rank_matches` output back to (ip, entry) pairs."""
    return [(ip, entry) for ip, entry, _why in ranked]


def _invert(text: str) -> tuple:
    """A sort key that orders strings descending inside an ascending sort."""
    return tuple(-ord(c) for c in text)


def _also_matched(chosen_ip: str, ranked: list) -> str:
    """The runners-up, for the log line -- never silently dropped.

    One per BOARD: the chosen device's own other addresses are not runners-up,
    they are the same Pixelblaze.
    """
    chosen_chip = ''
    for ip, entry, _why in ranked:
        if ip == chosen_ip:
            chosen_chip = chip_of(entry)
    out, seen = [], set()
    for ip, entry, _why in ranked:
        chip = chip_of(entry)
        if ip == chosen_ip or (chip and chip == chosen_chip) or chip in seen:
            continue
        if chip:
            seen.add(chip)
        out.append(f"{entry.get('name', '?')} ({ip})")
    return ', '.join(out)


def lookup_cached_device(query: str) -> tuple[str, dict]:
    """Look up a cached device by exact IP or case-insensitive name substring.

    When several devices match, the most reachable-looking one wins and the
    others are logged -- see `rank_matches`.

    Raises click.ClickException if nothing matches.
    """
    devices = cached_by_ip()
    if not devices:
        raise click.ClickException("No cached devices. Run `pb find` first.")
    if query in devices:
        return query, devices[query]
    q = query.lower()
    matches = [(ip, e) for ip, e in devices.items() if q in (e.get('name') or '').lower()]
    if not matches:
        raise click.ClickException(f"No cached device matches '{query}'.")
    ranked = rank_matches(matches)
    ip, entry, why = ranked[0]
    boards = {chip_of(e) or a for a, e in ranked_pairs(ranked)}
    if len(boards) > 1:
        log(f"'{query}' matched {len(boards)} devices; using {entry.get('name', '?')} "
            f"({ip}) — {why}. Also matched: {_also_matched(ip, ranked)}.")
    return ip, entry


def _describe_ports(ports: dict) -> str:
    """`http+ws open`, or a warning when the websocket server isn't answering."""
    http, ws = ports.get('http'), ports.get('ws')
    if http and ws:
        return 'http+ws open'
    if http and not ws:
        return 'http open, ws port 81 CLOSED — websocket server may be wedged, try `pb reboot`'
    if ws and not http:
        return 'ws open, http port 80 closed'
    return 'no ports open'


def _discover_devices(
    timeout: int = 2000,
    on_ip: Optional[Callable[[str], None]] = None,
    probe: bool = True,
) -> list[dict]:
    """
    Find every Pixelblaze on the network, using every source at once.

    All of these run in parallel from the first millisecond, so the answer
    takes as long as the slowest source (the beacon listen), never the sum:

      * UDP beacons — listen for `timeout` ms. With `probe`, also broadcast
        one beacon of our own: every Pixelblaze answers with a timeSync
        packet, *including sync-group followers, which never beacon* and
        are otherwise invisible here (see `sendBeaconProbe`).
      * Known addresses — the ad-hoc address and every device in the cache
        get a TCP connect on ports 80 and 81 (`_tcp_ports_open`: nothing is
        sent, so this is safe to do to a device in any state). Catches
        devices on a quiet or broadcast-filtered network.
      * Sync-group peers — each device found, from any source, is asked for
        its peer list; new addresses are probed the same way.

    Args:
        timeout: Beacon listen timeout in milliseconds.
        on_ip: Optional callback invoked with each newly-discovered IP the
            instant it's found — before the sweep completes. Lets callers
            (e.g. `pb top`) fire workers against a device as soon as it
            answers. Callback exceptions are logged and swallowed.
        probe: Broadcast a beacon to solicit timeSync replies. Default on.

    Returns:
        list[dict]: One per device, in the order they answered:
            ip (str)
            via (str): 'beacon', 'timeSync' (answered our probe), 'adhoc',
                'cache', or 'peer'.
            http, ws (bool): present when the device was TCP-probed —
                whether ports 80 / 81 accepted a connection.

    Raises:
        click.ClickException: If the beacon port cannot be bound (another
            listener holds UDP:1889). Not swallowed: a listener that never
            bound looks exactly like an empty network.
    """
    found: dict[str, dict] = {}
    pending: list = []
    lock = threading.Lock()
    pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix='pb-discover')

    def submit(fn, *args):
        with lock:
            pending.append(pool.submit(fn, *args))

    def report(ip: str):
        if on_ip is None:
            return
        try:
            on_ip(ip)
        except Exception as e:
            log(f"  on_ip callback failed for {ip}: {e}")

    # Names from the last time anything connected. A fast `pb find` never
    # connects, so this is the only way it can say who answered — and "who"
    # is the question being asked.
    known_names = cached_names()

    def add(ip: str, via: str, detail: str = '', **ports) -> bool:
        with lock:
            if ip in found:
                # Already known; just remember port state if this is the probe.
                found[ip].update(ports)
                return False
            record = {'ip': ip, 'via': via, **ports}
            name = known_names.get(ip)
            if name:
                record['name'] = name
            found[ip] = record
        extra = f"; {_describe_ports(ports)}" if ports else ''
        who = f"{name} @ " if name else '@ '
        log(f"  Found {who}{ip} ({detail or via}{extra})")
        report(ip)
        submit(ask_peers, ip)
        return True

    def listen():
        enumerator = Pixelblaze.EnumerateAddresses(timeout=timeout, probe=probe)
        for ip in enumerator:
            if enumerator.packetTypes.get(ip) == 43:
                add(ip, 'timeSync', 'answered our probe beacon')
            else:
                add(ip, 'beacon')

    def probe_tcp(ip: str, via: str, detail: str = ''):
        ports = _tcp_ports_open(ip)
        if ports[HTTP_PORT] or ports[WS_PORT]:
            add(ip, via, detail, http=ports[HTTP_PORT], ws=ports[WS_PORT])
        elif via == 'peer':
            log(f"  {ip} ({detail}) did not answer on ports 80/81")

    def ask_peers(ip: str):
        # Followers don't beacon, but every peer knows about them. This is
        # the one place discovery opens a websocket, and it is closed
        # cleanly by the context manager. Skip it entirely when the probe
        # already showed the websocket server isn't answering — poking a
        # wedged server helps nothing.
        with lock:
            if found[ip].get('ws') is False:
                return
        try:
            with Pixelblaze(ip) as pb:
                peers = pb.getPeers()
        except Exception as e:
            log(f"  Peer query failed on {ip}: {e}")
            return
        for peer in peers:
            peer_ip = peer.get('address')
            if not peer_ip or peer.get('self') or peer_ip in self_ips:
                continue
            with lock:
                known = peer_ip in found
            if not known:
                submit(probe_tcp, peer_ip, 'peer', f"via {ip} sync group")

    # Our own address is never a device: a probe beacon makes devices list
    # us as a peer for a while, and a stale cache may carry that over.
    self_ips = get_host_ips()
    candidates = [ADHOC_IP]
    for cached_ip in cached_addresses():
        if cached_ip not in candidates and cached_ip not in self_ips:
            candidates.append(cached_ip)

    log(f"Listening for beacons ({timeout}ms){' + probing' if probe else ''}, "
        f"checking {len(candidates)} known address(es)...")
    try:
        submit(listen)
        for ip in candidates:
            submit(probe_tcp, ip, 'adhoc' if ip == ADHOC_IP else 'cache')

        # Tasks spawn tasks (a found device queues a peer query, a peer queues
        # a probe), so keep draining until nothing is in flight.
        while True:
            with lock:
                live = [f for f in pending if not f.done()]
            if not live:
                break
            wait(live, return_when=FIRST_COMPLETED)
    finally:
        pool.shutdown(wait=True)

    # Loud failure. The only task that raises rather than logs is the beacon
    # listener, when UDP:1889 could not be bound.
    for future in pending:
        exc = future.exception()
        if exc is not None:
            raise click.ClickException(str(exc))

    return list(found.values())


def _explain_silent_beacons(found: list[dict]):
    """When no beacon was heard, say why the devices that did answer were quiet.

    The usual reason is a sync group whose leader is off: followers never
    beacon, so `pb find` used to come up empty while the web UI worked fine.
    Everything here comes from the cache, so it costs nothing.
    """
    if any(d['via'] == 'beacon' for d in found):
        return
    if not found:
        log("No beacons heard, and no known address answered on ports 80/81.")
        return
    cache = cached_by_ip()
    by_chip = {}
    for ip, entry in cache.items():
        chip = chip_of(entry)
        if not chip:
            continue
        # A board is in here once per address it has ever had; name it by
        # where it is now, not by whichever address iterated last.
        if chip in by_chip and entry.get('ip') != ip:
            continue
        by_chip[chip] = (ip, entry)
    found_ips = {d['ip'] for d in found}
    log("No beacons heard; the device(s) above answered a direct probe instead.")
    for d in found:
        entry = cache.get(d['ip']) or {}
        leader = (entry.get('settings') or {}).get('leaderId') or entry.get('leaderId')
        if not leader:
            continue
        name = entry.get('name') or d['ip']
        # chipId is a string key everywhere (it is an identity, not a number
        # to do arithmetic with), and `leaderId` arrives from the wire as an
        # int — so this lookup has to say which it is.
        leader_ip, leader_entry = by_chip.get(str(leader), (None, {}))
        who = (f"{leader_entry.get('name') or leader_ip} ({leader_ip})" if leader_ip
               else f"chip {leader}")
        gone = ', which did not answer' if leader_ip and leader_ip not in found_ips else ''
        log(f"  {name} is a sync-group follower of {who}{gone} — followers don't beacon.")


def _discover_ips(
    timeout: int = 2000,
    on_ip: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """Discover Pixelblaze IP addresses. See `_discover_devices` for how.

    Kept for callers that only want addresses; the order is the order in
    which devices answered.
    """
    return [d['ip'] for d in _discover_devices(timeout=timeout, on_ip=on_ip)]


def enumerate_pixelblazes(
    timeout: int = 3000,
    slow: bool = False,
    on_ip: Optional[Callable[[str], None]] = None,
    probe: bool = True,
) -> list[dict]:
    """
    Discover all Pixelblazes on the network.

    Beacons, a probe broadcast, the ad-hoc address, every cached address and
    sync-group peer lists are all tried in parallel — see `_discover_devices`.
    In fast mode (default), returns minimal dicts: the IP, how it was found,
    and which ports answered. In slow mode, also connects to each device in
    parallel to fetch name, config, version, etc.

    Args:
        timeout: Beacon listen timeout in milliseconds.
        slow: If True, connect to each device to fetch full config info.
        on_ip: Optional per-IP callback fired the instant each device is
            found (before the sweep returns). See `_discover_devices`.
        probe: Broadcast a beacon so followers answer. Default on.

    Returns:
        list[dict]: Device info dicts. Fast mode: ip, via, (when probed)
                    http / ws, and `name` when the cache remembers one for
                    that address — REMEMBERED, not fetched: fast mode never
                    connects, so the name is as true as the last time
                    something did. Slow mode connects and adds the live name,
                    pixelCount, brightness, ver, brandName, hostIp.
    """
    found = _discover_devices(timeout=timeout, on_ip=on_ip, probe=probe)
    _explain_silent_beacons(found)

    if not found:
        return []

    ips = [d['ip'] for d in found]
    by_ip = {d['ip']: d for d in found}
    host_ip = get_host_ip()

    if not slow:
        devices = [dict(d) for d in found]
        # A REMEMBERED NAME IS NOT AN OBSERVATION. Fast mode never connected,
        # so its `name` came out of this very cache — writing it back lets a
        # stale alias overwrite the stored identity of whatever is actually at
        # that address, which is how one device ends up wearing another's
        # name. Report it; never learn from it.
        update_device_cache([{k: v for k, v in d.items() if k != 'name'} for d in devices])
        return devices

    # Slow mode: connect to each device to get full info, in parallel. A
    # device whose websocket port did not answer is reported from cache
    # rather than connected to — it would only time out, and a wedged
    # server is not improved by more clients.
    log(f"Fetching device info from {len(ips)} device(s)...")
    devices = []

    def fetch(ip: str) -> dict:
        if by_ip[ip].get('ws') is False:
            cached = cached_entry(ip)
            return {'ip': ip, 'name': cached.get('name', ''),
                    'error': 'websocket port 81 not answering; details from cache'}
        return _get_device_info(ip)

    with ThreadPoolExecutor(max_workers=min(len(ips), 8)) as pool:
        futures = {pool.submit(fetch, ip): ip for ip in ips}
        for future in as_completed(futures):
            info = future.result()
            if info:
                if host_ip:
                    info['hostIp'] = host_ip
                for key in ('via', 'http', 'ws'):
                    if key in by_ip[info['ip']]:
                        info[key] = by_ip[info['ip']][key]
                devices.append(info)
                name = info.get('name', '?')
                if name:
                    log(f"  {info['ip']}: {name}")

    # Preserve discovery order
    ip_order = {ip: i for i, ip in enumerate(ips)}
    devices.sort(key=lambda d: ip_order.get(d['ip'], 999))

    update_device_cache(devices)
    return devices


# Shortest name fragment accepted by resolve_ip_spec() — below this a query is
# too likely to sweep in unrelated devices.
MIN_NAME_QUERY_LEN = 3


def _resolve_subnet_octet(octet: int) -> str:
    """Expand a bare host octet into a full address on the local /24 subnet."""
    host_ip = get_host_ip()
    if not is_ipv4(host_ip):
        raise click.ClickException(
            f"Cannot expand --ip '{octet}': failed to determine this machine's subnet. "
            f"Pass the full address instead."
        )
    return '.'.join(host_ip.split('.')[:3] + [str(octet)])


def _resolve_cached_name(query: str) -> Optional[str]:
    """Find a cached device IP by case-insensitive name match.

    An exact (case-insensitive) name wins outright; otherwise the query is
    taken as a substring. Several matches are not an error -- the most
    reachable-looking one is used and the rest are logged, see `rank_matches`.
    Returns None when nothing matches, so callers can report why the whole
    --ip value failed to resolve.
    """
    devices = cached_by_ip()
    q = query.lower()

    def _choose(matches):
        ranked = rank_matches(matches)
        ip, entry, why = ranked[0]
        # AMBIGUOUS MEANS SEVERAL BOARDS, not several addresses. One
        # Pixelblaze that has been on three networks is still one answer, and
        # saying "matched 3 devices" about it sent people hunting for two
        # devices they do not own.
        boards = {chip_of(e) or a for a, e in ranked_pairs(ranked)}
        if len(boards) > 1:
            log(f"--ip '{query}' matched {len(boards)} devices; using {ip} "
                f"({entry.get('name', '?')}) — {why}. "
                f"Also matched: {_also_matched(ip, ranked)}. "
                f"Give a longer fragment, an IP, or a comma-separated list to "
                f"reach more than one.")
        return ip

    exact = [(ip, e) for ip, e in devices.items() if (e.get('name') or '').lower() == q]
    if exact:
        return _choose(exact)

    matches = [(ip, e) for ip, e in devices.items() if q in (e.get('name') or '').lower()]
    if matches:
        return _choose(matches)
    return None


def resolve_ip_spec(spec: Optional[str]) -> Optional[str]:
    """Resolve a flexible --ip value into a concrete address.

    Accepted forms, tried in this order:

        (none) / '' / 'auto'      -> None; the caller falls back to discovery
        '192.168.1.230'           -> used as-is (fast path, no cache or network)
        'http://192.168.1.230/'   -> the host from a URL pasted out of a browser
        '230'                     -> that host octet on this machine's /24 subnet
        'kitch'                   -> case-insensitive name fragment (>= 3 chars)
                                     looked up against cached devices

    Args:
        spec: The raw --ip value.

    Returns:
        Optional[str]: A concrete address, or None to mean "auto discover".

    Raises:
        click.ClickException: If the value looks like one of the supported
            forms but cannot be resolved (unknown name, ambiguous fragment,
            undeterminable subnet, etc).
    """
    if spec is None:
        return None
    spec = spec.strip()
    if not spec or spec.lower() == 'auto':
        return None

    # Exact IP — the common case, resolved without touching the cache.
    if is_ipv4(spec):
        return spec
    if _IPV4_RE.match(spec):
        raise click.ClickException(f"--ip '{spec}' is not a valid IP: each octet must be 0-255.")

    # A URL copied from a browser: http(s)://[user@]host[:port]/path?query
    url_match = _URL_HOST_RE.match(spec)
    if url_match:
        host = url_match.group(1).rsplit('@', 1)[-1].split(':', 1)[0]
        if not host:
            raise click.ClickException(f"No host found in --ip URL '{spec}'.")
        log(f"--ip '{spec}' -> {host} (from URL)")
        return host

    # A bare host number: fill in this machine's subnet around it.
    if spec.isdigit():
        if int(spec) > 255:
            raise click.ClickException(
                f"--ip '{spec}' is out of range: a bare host number must be 0-255."
            )
        resolved = _resolve_subnet_octet(int(spec))
        log(f"--ip '{spec}' -> {resolved} (local subnet)")
        return resolved

    # Otherwise treat it as a device name fragment and consult the cache.
    if len(spec) < MIN_NAME_QUERY_LEN:
        raise click.ClickException(
            f"--ip '{spec}' is not an IP, and name matching needs at least "
            f"{MIN_NAME_QUERY_LEN} characters."
        )

    resolved = _resolve_cached_name(spec)
    if resolved:
        name = cached_entry(resolved).get('name', '')
        log(f"--ip '{spec}' -> {resolved}" + (f" ({name})" if name else "") + " (cached name)")
        return resolved

    raise click.ClickException(
        f"Could not resolve --ip '{spec}': not an IP address, and no cached device "
        f"name matches it. Run `pb find --full` to refresh the cache, or `pb cache ls` "
        f"to see what is known."
    )


def resolve_ip_specs(spec) -> list:
    """Resolve a --ip value into zero or more concrete addresses.

    A comma-separated list resolves each part exactly the way `resolve_ip_spec`
    resolves one, so every form mixes freely:

        --ip 192.168.1.5,porch,230,http://10.0.0.4/

    `all` expands to every cached device, ordered by `rank_matches` so the ones
    this machine can actually reach come first. Duplicates collapse and order is
    kept, so the answer reads the way it was typed.

    An empty list means "nothing was named" -- the caller discovers, the way it
    always has.
    """
    if spec is None:
        return []
    addresses = []
    for part in [p.strip() for p in str(spec).split(',')]:
        if not part:
            continue
        for address in _resolve_one_spec(part):
            if address not in addresses:
                addresses.append(address)
    return addresses


def _resolve_one_spec(part: str) -> list:
    if part.lower() == 'all':
        devices = cached_by_ip()
        if not devices:
            raise click.ClickException(
                "--ip all: no devices are cached yet. Run `pb find` first.")
        return [ip for ip, _, _ in rank_matches(list(devices.items()))]
    resolved = resolve_ip_spec(part)
    return [resolved] if resolved else []


class _ThreadRoutedStream(io.TextIOBase):
    """A stdout/stderr stand-in that sends each thread's writes to its own buffer.

    Installed for the life of a fan-out. A thread that has not asked for a
    buffer -- the main one, or anything a library spawns -- writes straight
    through, so nothing is swallowed by accident.
    """

    def __init__(self, real):
        self._real = real
        self._local = threading.local()

    @property
    def _buffer(self):
        return getattr(self._local, 'buffer', None)

    def capture(self, buffer):
        self._local.buffer = buffer

    def release(self):
        self._local.buffer = None

    def write(self, text):
        return (self._buffer or self._real).write(text)

    def flush(self):
        if self._buffer is None:
            self._real.flush()

    def isatty(self):
        # Captured output is on its way into a string: colour codes, spinners
        # and progress bars would be noise in the middle of a grouped block.
        return self._buffer is None and self._real.isatty()

    def writable(self):
        return True

    def fileno(self):
        return self._real.fileno()

    @property
    def encoding(self):
        return getattr(self._real, 'encoding', 'utf-8')


def run_per_address(addresses: list, run: Callable, workers: int = 8,
                    out=None, err=None, prefix: bool = False) -> list:
    """Run `run(address)` once per address, in parallel, output kept together.

    Each worker's stdout and stderr go to buffers of its own, and a worker's
    whole output is released the instant that worker finishes -- so the first
    device to answer prints straight away and a wedged one never holds up the
    rest. That does mean **completion order, not the order given**: staring at
    nothing because the first address in the list is off is worse than reading
    the results out of order, and every block is labelled.

    stdout and stderr stay separate all the way through, so
    `pb --ip all ls | jq` still gets only the devices' stdout. The label goes
    on stderr for the same reason.

    `prefix` puts the address in front of every stdout line as well, for the
    case the label on stderr cannot serve: a piped run whose output is scalars
    (`pb --ip all --prefix pixels | ...`) where nothing else says which device
    said what.

    `out` / `err` are where the grouped blocks end up, defaulting to this
    process's own; they are arguments so this is testable without reaching into
    `sys`, which pytest also owns.

    Returns [(address, result, error)] in the order given. Failures do not stop
    the others; the caller decides what a partial run means.
    """
    out = _ThreadRoutedStream(sys.stdout if out is None else out)
    err = _ThreadRoutedStream(sys.stderr if err is None else err)
    emit_lock = threading.Lock()
    results = {}
    names = cached_names()

    def label(address: str) -> str:
        name = names.get(address)
        return f"── {address}{f' ({name})' if name else ''} " + "─" * 8

    def worker(address: str):
        captured_out, captured_err = io.StringIO(), io.StringIO()
        out.capture(captured_out)
        err.capture(captured_err)
        try:
            return run(address), None
        except Exception as e:                      # noqa: BLE001 - reported below
            return None, e
        finally:
            out.release()
            err.release()
            # One lock around the whole group: two workers finishing together
            # must not shuffle their lines into each other.
            with emit_lock:
                err.write(label(address) + "\n")
                err.write(captured_err.getvalue())
                err.flush()
                written = captured_out.getvalue()
                if prefix and written:
                    complete = written.endswith("\n")
                    body = written[:-1] if complete else written
                    written = "\n".join(f"{address}\t{line}" for line in body.split("\n"))
                    written += "\n" if complete else ""
                out.write(written)
                out.flush()

    real_out, real_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        with ThreadPoolExecutor(max_workers=min(len(addresses), workers),
                                thread_name_prefix='pb-ip') as pool:
            futures = {pool.submit(worker, address): address for address in addresses}
            for future in as_completed(futures):
                results[futures[future]] = future.result()
    finally:
        sys.stdout, sys.stderr = real_out, real_err

    return [(address,) + results.get(address, (None, None)) for address in addresses]


def fan_out(addresses: list, run: Callable, out=None, err=None,
            prefix: bool = False) -> list:
    """`run_per_address`, plus the summary and the exit code.

    Every address is attempted whatever the others do -- a fan-out that stopped
    at the first failure would be a worse version of running the command once.
    """
    outcomes = run_per_address(addresses, run, out=out, err=err, prefix=prefix)
    stream = sys.stderr if err is None else err
    failed = [(address, error) for address, _, error in outcomes if error is not None]
    stream.write(f"── {len(addresses) - len(failed)}/{len(addresses)} succeeded "
                 + ("─" * 8 if not failed else "") + "\n")
    for address, error in failed:
        stream.write(f"   ✗ {address}: {type(error).__name__}: {error}\n")
    stream.flush()
    if failed:
        raise click.ClickException(
            f"{len(failed)} of {len(addresses)} failed: "
            + ', '.join(address for address, _ in failed))
    return [result for _, result, _ in outcomes]


def discover_pixelblaze(ctx: click.Context) -> str:
    """
    Discovers a Pixelblaze IP address using the specified strategy.

    An explicit --ip is resolved through resolve_ip_spec(), so it may be a
    plain address, a browser URL, a bare host octet, or a cached device name
    fragment. Otherwise falls back to cached IP, ad-hoc check, then beacon
    enumeration, returning the first reachable IP and caching it.

    Args:
        ctx: Click context containing the --ip value in ctx.obj['ip']

    Returns:
        str: The discovered or specified IP address

    Raises:
        click.ClickException: If --ip cannot be resolved or no Pixelblaze is found
    """
    addresses = ctx.obj.get('ips')
    if addresses is None:
        addresses = resolve_ip_specs(ctx.obj.get('ip', 'auto'))

    if addresses:
        # More than one only reaches here from a command that opted out of
        # fanning out and then asked for a single device anyway; the first is
        # the one `rank_matches` put first, which is the reachable one.
        ip_address = addresses[0]
        # A fan-out worker must not scribble its own address into lastIp --
        # N workers racing to set "the" default IP is meaningless.
        if not ctx.obj.get('fanning_out'):
            cache_ip(ip_address)
        return ip_address

    # Try cached IP first
    cached = get_cached_ip()
    if cached:
        log(f"Trying cached IP {cached}...")
        if _check_ip_reachable(cached):
            log(f"Found Pixelblaze at {cached} (cached)")
            return cached
        log(f"Cached IP {cached} not responding, searching...")

    # Full enumeration — return first found (fast, no websocket connects)
    ips = _discover_ips(timeout=2000)
    if ips:
        update_device_cache([{'ip': ip} for ip in ips])
        cache_ip(ips[0])
        return ips[0]

    raise click.ClickException(
        "No Pixelblaze found. Specify an IP address with --ip or ensure a Pixelblaze is on the network."
    )


def read_input(value: Optional[str], name: str = "input", required: bool = True, binary: bool = False) -> tuple[str | bytes, bool]:
    """
    Read input from stdin, file path, or value string.

    Checks stdin first (if piped), then file path, then treats value as inline content.

    Args:
        value: The input value (can be None, a file path, or content string)
        name: Name for error messages (e.g., "code", "map")
        required: Whether input is required (raises if no input provided)
        binary: If True, read files and stdin in binary mode (returns bytes)

    Returns:
        tuple[str | bytes, bool]: (content, is_stdin) where:
            - content: The input data (str in text mode, bytes in binary mode)
            - is_stdin: True if content came from stdin, False otherwise

    Raises:
        click.ClickException: If no input provided and required=True
    """
    # If an explicit value was provided, check file path first (before stdin)
    if value is not None:
        # Check if it's an existing file path
        if os.path.isfile(value):
            mode = 'rb' if binary else 'r'
            with open(value, mode) as f:
                content = f.read()
                return (content if binary else content.strip(), False)
        # Otherwise treat it as the content itself (text mode only)
        if binary:
            raise click.ClickException(
                f"Cannot use inline content in binary mode. Provide a file path or pipe via stdin."
            )
        return (value, False)

    # No explicit value — check stdin if it's piped (not a TTY)
    if not sys.stdin.isatty():
        if binary:
            return (sys.stdin.buffer.read(), True)
        else:
            return (sys.stdin.read().strip(), True)

    # No stdin, no value
    if required:
        raise click.ClickException(
            f"No {name} provided. Supply {name} as text, a file path, or pipe via stdin."
        )
    else:
        return (None, False)


def parse_json(text: str):
    """
    Parse JSON-like text using json5 (supports single quotes, unquoted keys, etc).

    Args:
        text: JSON5 string to parse

    Returns:
        Parsed object/array

    Raises:
        click.ClickException: If parsing fails
    """
    try:
        return json5.loads(text)
    except Exception as e:
        raise click.ClickException(f"Invalid JSON: {e}")


def check(condition, error_message: str):
    """
    Ensure a condition is true, otherwise raise a ClickException.

    Args:
        condition: The condition to check
        error_message: Error message to display if condition is false

    Raises:
        click.ClickException: If condition is false

    Example:
        ensure(len(items) > 0, "No items found")
        ensure(value >= 0 and value <= 1, "Value must be between 0 and 1")
    """
    if not condition:
        raise click.ClickException(error_message)


def parse_vars(args):
    """
    Parse variable arguments in flexible formats.

    Supports:
    - key value pairs: ('foo', 'bar') → {foo: "bar"}
    - colon-separated: ('foo:bar baz',) → {foo: "bar baz"}
    - JSON5 objects: ('{a:1, b:2}',) → {a: 1, b: 2}
    - mixed: ('foo', '2', 'bar:3', '{baz:true}') → {foo: 2, bar: 3, baz: true}

    Args:
        args: Tuple or list of argument strings

    Returns:
        dict: Parsed variables

    Raises:
        click.ClickException: If parsing fails or args are malformed

    Examples:
        parse_vars(['foo', 'bar']) → {'foo': 'bar'}
        parse_vars(['foo', '1']) → {'foo': 1}
        parse_vars(['foo:bar']) → {'foo': 'bar'}
        parse_vars(['{a:1}']) → {'a': 1}
        parse_vars(['foo', '2', 'bar:3']) → {'foo': 2, 'bar': 3}
    """
    variables = {}

    i = 0
    while i < len(args):
        arg = args[i]

        # Try to parse as JSON5 object/array
        if arg.startswith('{') or arg.startswith('['):
            try:
                parsed = parse_json(arg)
                if isinstance(parsed, dict):
                    variables.update(parsed)
                    i += 1
                    continue
            except:
                pass

        # Check for colon-separated key:value
        if ':' in arg:
            key, value = arg.split(':', 1)
            try:
                variables[key] = float(value)
            except ValueError:
                variables[key] = value
            i += 1
            continue

        # Otherwise, treat as key with next arg as value
        check(i + 1 < len(args), f"Missing value for key '{arg}'")
        key = arg
        value = args[i + 1]
        try:
            variables[key] = float(value)
        except ValueError:
            variables[key] = value
        i += 2

    return variables


def get_pixelblaze(ctx: click.Context) -> Pixelblaze:
    """
    Gets a Pixelblaze instance from the context, handling discovery if needed.

    Args:
        ctx: Click context containing the IP address

    Returns:
        Pixelblaze: Connected Pixelblaze instance

    Raises:
        click.ClickException: If connection fails
    """
    discovered_ip = discover_pixelblaze(ctx)
    ctx.obj['ip'] = discovered_ip  # Update with actual IP used
    timeout = ctx.obj.get('timeout', 5.0)
    Pixelblaze.default_recv_timeout = timeout
    pb = Pixelblaze(discovered_ip)
    ctx.obj['pixelblaze'] = pb
    return pb



# Transient errors that warrant a retry
_RETRYABLE = (
    ConnectionError,
    ConnectionResetError,
    TimeoutError,
    OSError,
)

try:
    import websocket
    _RETRYABLE = _RETRYABLE + (websocket._exceptions.WebSocketTimeoutException,
                                websocket._exceptions.WebSocketConnectionClosedException,)
except Exception:
    pass

try:
    import requests as _req
    _RETRYABLE = _RETRYABLE + (_req.ConnectionError, _req.Timeout,)
except Exception:
    pass


def _run_with_retries(ctx: click.Context, fn, *args, **kwargs):
    """Run fn with retry logic on transient connection errors."""
    max_retries = ctx.obj.get('retries', 3)
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except _RETRYABLE as e:
            if attempt >= max_retries:
                raise
            delay = 0.5 * (attempt + 1)
            log(f"Connection error ({type(e).__name__}), retry {attempt + 1}/{max_retries} in {delay:.1f}s...")
            time.sleep(delay)


def context_for(ctx: click.Context, address: str) -> click.Context:
    """A copy of `ctx` aimed at exactly one device.

    Shallow, with its own `obj`: every command reads its destination out of
    `ctx.obj`, so a worker that has one address in there behaves precisely as
    if that had been the only `--ip` given. Nothing below the fan-out has to
    know it is inside one.
    """
    clone = copy.copy(ctx)
    clone.obj = dict(ctx.obj, ip=address, ips=[address], fanning_out=True)
    return clone


def cli(cli_group, conn=True, fan_out_ips=True, **click_kwargs) -> Callable:
    """
    Factory function to create a cli decorator bound to a Click CLI group.

    Returns a decorator that combines @click.command() and @click.pass_context functionality,
    automatically injecting a connected Pixelblaze instance as the first argument
    and wrapping the function body in a context manager.

    Automatically retries on transient connection errors (ConnectionResetError,
    timeouts, etc.) using the --retries global option.

    Usage:
        @cli(pixelblaze)
        @click.argument('level', type=float, required=False)
        @click.option('--no-save', is_flag=True)
        def brightness(pb, level, no_save):
            pb.setBrightnessSlider(level)

        @cli(pixelblaze, conn=False)
        def reboot(ctx, wait):
            # Handle connection manually
            pass

    Args:
        cli_group: The CLI group to add the command to
        conn: If True (default), automatically connects and passes Pixelblaze instance.
              If False, passes context and lets function handle connection.
        fan_out_ips: If True (default), a `--ip` naming several devices runs the
              command once per device, in parallel, with each one's output kept
              together (see `fan_out`). Set False for a command that means to
              handle the whole list itself -- `pb sensor sound` streams one
              capture to all of them at once, which is not the same thing as
              running it N times.
        **click_kwargs: Additional kwargs to pass to @cli.command()

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(ctx: click.Context, *args, **kwargs):
            def _once(context: click.Context):
                def _run():
                    if conn:
                        with get_pixelblaze(context) as pb:
                            result = func(pb, *args, **kwargs)
                            maybe_refresh_cache(pb, context.obj.get('ip', ''))
                            return result
                    else:
                        return func(context, *args, **kwargs)
                return _run_with_retries(context, _run)

            ctx.obj['ips'] = addresses = resolve_ip_specs(ctx.obj.get('ip', 'auto'))
            if fan_out_ips and len(addresses) > 1:
                return fan_out(addresses,
                               lambda address: _once(context_for(ctx, address)),
                               prefix=ctx.obj.get('prefix', False))
            return _once(ctx)

        # Apply click.pass_context and cli.command() decorators
        wrapper = click.pass_context(wrapper)
        wrapper = cli_group.command(**click_kwargs)(wrapper)

        return wrapper

    return decorator
