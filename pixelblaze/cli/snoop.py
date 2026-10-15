"""`pb snoop` — live-decode Pixelblaze websocket traffic off the wire.

Shells out to `tshark` for capture/dissection and pipes its line-delimited
JSON through `jq` for filtering and pretty-printing. Nothing is decoded in
Python; this module's whole job is to build a correct pipeline out of the
CLI's flexible IP-resolution machinery and then get out of the way.

The pipeline it builds looks like:

    tshark -i en0 -l -n -q -d tcp.port==81,http \
           -f "tcp port 81 and host 192.168.1.230" \
           -Y "websocket and (ip.src == 192.168.1.230 or ip.dst == 192.168.1.230)" \
           -T ek -e ip.src -e ip.dst -e tcp.srcport -e tcp.dstport \
                 -e frame.time_epoch -e websocket.payload.text \
      | jq -c --unbuffered --argjson devs '[...]' --arg host '...' '<program>'

`-T ek` (Elasticsearch bulk format) is used rather than the more obvious
`-T fields`, because a single TCP packet can carry several websocket frames.
`-T fields` aggregates those into one comma-joined cell — `{"fps":41},{"a":1}`
— which is not valid JSON. `-T ek` keeps them as a real array, so the jq
program can explode them into one output record each.

`--udp` (alias `--beacons`) keeps the same shape but captures the UDP:1889
discovery traffic instead — the beacon every Pixelblaze broadcasts about once
a second, and the timeSync packets Firestorm (or `PixelblazeEnumerator`)
answers with:

    tshark -i en0 -l -n -q -f "udp port 1889" -Y "udp.port == 1889" \
           -T ek -e ip.src -e ip.dst -e udp.srcport -e udp.dstport \
                 -e frame.time_epoch -e data.data
      | jq -c --unbuffered '<program>'

tshark has no dissector for these packets, so the payload arrives as a hex
string and the jq program carries a small little-endian decoder for it.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys

import click

from pixelblaze.cli.cli_utils import (
    _read_cache,
    get_host_ip,
    log,
    resolve_ip_spec,
)


# ── Dependency / permission preflight ───────────────────────────────────────

# Per-platform install hints, printed verbatim when a dependency is missing.
_INSTALL_HINTS = {
    'darwin': {
        'tshark': ("brew install wireshark              # CLI only (tshark, no GUI)",
                   "brew install --cask wireshark       # GUI app, also ships tshark"),
        'jq': ("brew install jq",),
    },
    'linux': {
        'tshark': ("sudo apt install tshark             # Debian/Ubuntu",
                   "sudo dnf install wireshark-cli      # Fedora/RHEL"),
        'jq': ("sudo apt install jq                 # Debian/Ubuntu",
               "sudo dnf install jq                 # Fedora/RHEL"),
    },
    'win32': {
        'tshark': ("choco install wireshark             # Chocolatey",
                   "winget install WiresharkFoundation.Wireshark",
                   "scoop install wireshark",
                   "",
                   "The installer may not put tshark on PATH; it lives in",
                   r"C:\Program Files\Wireshark\tshark.exe"),
        'jq': ("choco install jq                    # Chocolatey",
               "winget install jqlang.jq",
               "scoop install jq"),
    },
}


def _platform_key() -> str:
    if sys.platform == 'darwin':
        return 'darwin'
    return 'win32' if sys.platform == 'win32' else 'linux'


def _require(tool: str) -> str:
    """Return the path to `tool`, or raise with copy-pasteable install hints."""
    path = shutil.which(tool)
    if path:
        return path
    hints = _INSTALL_HINTS.get(_platform_key(), {}).get(tool, (f"install {tool}",))
    lines = '\n'.join(f"    {h}" for h in hints)
    raise click.ClickException(
        f"`{tool}` not found on PATH. `pb snoop` shells out to it.\n\nInstall it with:\n{lines}"
    )


def _can_capture() -> bool:
    """Best-effort check that we can open a capture device without sudo.

    macOS gates raw capture behind /dev/bpf*, which is root-only until
    Wireshark's ChmodBPF helper is installed — a check we can make cheaply
    and accurately. On Linux the equivalent (file capabilities on dumpcap,
    or membership in the `wireshark` group) is not reliably introspectable,
    so we assume yes and let tshark report the truth.
    """
    if sys.platform != 'darwin':
        return True
    devices = glob.glob('/dev/bpf*')
    if not devices:
        return True  # Nothing to inspect; don't block on a guess.
    return any(os.access(d, os.R_OK) for d in devices)


_PERMISSION_FIX = {
    'darwin': (
        "brew install --cask wireshark-chmodbpf   # one-time; then log out and back in",
        "pb snoop --sudo                          # or just run tshark under sudo",
    ),
    'linux': (
        "sudo usermod -aG wireshark $USER         # then log out and back in",
        "sudo setcap cap_net_raw,cap_net_admin+eip $(which dumpcap)",
        "pb snoop --sudo                          # or just run tshark under sudo",
    ),
    'win32': (
        "Install Npcap (bundled with Wireshark): choco install wireshark",
        "If Npcap was installed with 'Restrict to Administrators', re-run",
        "  pb snoop from an elevated terminal (--sudo does nothing on Windows).",
    ),
}


def _check_capture_permission():
    if _can_capture():
        return
    lines = '\n'.join(f"    {h}" for h in _PERMISSION_FIX[_platform_key()])
    raise click.ClickException(
        "No permission to capture packets (/dev/bpf* is root-only — Wireshark's "
        "ChmodBPF helper isn't installed).\n\nFix with any of:\n" + lines
    )


# ── Interface detection ─────────────────────────────────────────────────────

def _default_iface(target_ip: str | None) -> str:
    """Pick the interface the kernel would use to reach `target_ip`.

    Beats hardcoding `en0`: a Pixelblaze in AP mode, or one reached over
    Ethernet or a second adapter, lives on a different interface, and
    capturing on the wrong one silently yields zero packets.
    """
    probe = target_ip or '8.8.8.8'
    try:
        if sys.platform == 'darwin':
            out = subprocess.run(['route', '-n', 'get', probe],
                                 capture_output=True, text=True, timeout=3).stdout
            match = re.search(r'^\s*interface:\s*(\S+)', out, re.MULTILINE)
            if match:
                return match.group(1)
        else:
            out = subprocess.run(['ip', 'route', 'get', probe],
                                 capture_output=True, text=True, timeout=3).stdout
            match = re.search(r'\bdev\s+(\S+)', out)
            if match:
                return match.group(1)
    except Exception:
        pass

    # Last resort: first interface tshark lists that isn't loopback.
    try:
        out = subprocess.run([_require('tshark'), '-D'],
                             capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            name = line.split('.', 1)[-1].strip().split(' ', 1)[0]
            if name and name != 'lo0' and name != 'lo':
                return name
    except Exception:
        pass
    return 'en0'


# ── Target resolution ───────────────────────────────────────────────────────

def _device_name(ip: str) -> str:
    return (_read_cache().get('devices', {}).get(ip, {}) or {}).get('name') or ''


def _label(ip: str) -> str:
    """`192.168.1.230 (bike1)` when the cache knows the name, else bare IP."""
    name = _device_name(ip)
    return f"{ip} ({name})" if name else ip


def _resolve_others(csv: str | None) -> list[str]:
    """Resolve a CSV of extra device specs through the standard --ip machinery.

    Every form `--ip` accepts works here too, so `--others 231,kitchen,
    http://192.168.1.5/` is valid. `auto` is rejected: it means "go discover
    one", which has no sensible meaning in an additive list.
    """
    if not csv:
        return []
    resolved = []
    for raw in csv.split(','):
        spec = raw.strip()
        if not spec:
            continue
        try:
            ip = resolve_ip_spec(spec)
        except click.ClickException as e:
            # resolve_ip_spec words its errors for --ip; we called it for --others.
            raise click.ClickException(e.message.replace("--ip", "--others", 1))
        if ip is None:
            raise click.ClickException(
                f"--others '{spec}' means auto-discover, which can't be added to a "
                f"filter list. Give a concrete address, host octet, or cached name."
            )
        if ip not in resolved:
            resolved.append(ip)
    return resolved


def _resolve_host(spec: str) -> str | None:
    """Resolve the --host value. Returns None for 'any' (no host filter)."""
    if spec.lower() in ('any', 'all', '*'):
        return None
    if spec.lower() in ('me', 'self', 'here'):
        host_ip = get_host_ip()
        if not host_ip:
            raise click.ClickException(
                "--host me: could not determine this machine's IP address. "
                "Pass the address explicitly."
            )
        return host_ip
    ip = resolve_ip_spec(spec)
    if ip is None:
        raise click.ClickException("--host 'auto' is not meaningful; use 'me', 'any', or an address.")
    return ip


# ── Filter construction ─────────────────────────────────────────────────────

def _capture_filter(devices: list[str], host: str | None, ports: list[int],
                    proto: str = 'tcp') -> str:
    """BPF capture filter — cheap kernel-level narrowing before dissection.

    Deliberately NOT direction-aware. Filtering one direction out here would
    drop the server's `101 Switching Protocols` response, which is what primes
    tshark's websocket dissector; direction is applied in the display filter
    instead, after dissection has already happened. (`--udp` has no such
    handshake, but keeps the split anyway: direction there means beacon vs
    timeSync, which is only knowable after decoding.)
    """
    clauses = [' or '.join(f"{proto} port {p}" for p in ports)]
    if len(ports) > 1:
        clauses = [f"({clauses[0]})"]
    if devices:
        hosts = ' or '.join(f"host {ip}" for ip in devices)
        clauses.append(f"({hosts})" if len(devices) > 1 else hosts)
    if host:
        clauses.append(f"host {host}")
    return ' and '.join(clauses)


def _display_filter(devices: list[str], host: str | None, ports: list[int],
                    requests: bool, responses: bool) -> str:
    """Wireshark display filter — picks websocket frames and applies direction.

    Direction is applied here rather than in the capture filter on purpose:
    dropping one direction at capture time would also drop the server's
    `101 Switching Protocols` reply, which is what primes tshark's websocket
    dissector.
    """
    terms = ['websocket']

    if devices:
        if requests and not responses:
            device_term = ' or '.join(f"ip.dst == {ip}" for ip in devices)
        elif responses and not requests:
            device_term = ' or '.join(f"ip.src == {ip}" for ip in devices)
        else:
            device_term = ' or '.join(
                f"ip.src == {ip} or ip.dst == {ip}" for ip in devices)
        terms.append(f"({device_term})")
    elif requests != responses:
        # --any plus a direction: with no device named, orient by the listening
        # port instead of by our own IP. A Pixelblaze is always the websocket
        # *server*, so "toward port 81" is "toward a device" — which keeps
        # `--any --requests` meaning every client's requests, not just ours.
        side = 'dst' if requests else 'src'
        port_term = ' or '.join(f"tcp.{side}port == {p}" for p in ports)
        terms.append(f"({port_term})" if len(ports) > 1 else port_term)

    if host:
        terms.append(f"(ip.src == {host} or ip.dst == {host})")

    return ' and '.join(terms)


def _udp_display_filter(devices: list[str], host: str | None, ports: list[int]) -> str:
    """Display filter for `--udp`: port and endpoints only.

    Direction is decided by packet type (beacon vs timeSync), which lives in
    the payload, so it is applied by jq after decoding rather than here.
    """
    port_term = ' or '.join(f"udp.port == {p}" for p in ports)
    terms = [f"({port_term})" if len(ports) > 1 else port_term]
    if devices:
        device_term = ' or '.join(f"ip.src == {ip} or ip.dst == {ip}" for ip in devices)
        terms.append(f"({device_term})")
    if host:
        terms.append(f"(ip.src == {host} or ip.dst == {host})")
    return ' and '.join(terms)


# ── jq program ──────────────────────────────────────────────────────────────

# Local wall clock with milliseconds, from the epoch float bound to `$ts`.
_JQ_CLOCK = ('(($ts | strflocaltime("%H:%M:%S")) + "."'
             ' + (("00" + (($ts - ($ts | floor)) * 1000 | floor | tostring)) | .[-3:]))')

def _jq_program(show_time: bool, show_dir: bool, show_peer: bool, show_endpoints: bool,
                bare: bool, grep: str | None, exclude: str | None,
                extra: str | None, direction: str | None = None) -> str:
    """Assemble the jq filter.

    The envelope is adaptive: fields that would be constant across every line
    (the peer, when only one device is in scope; the direction, when a
    direction flag already pinned it) are omitted, so the narrow common case
    degrades to bare message JSON.
    """
    lines = [
        # `-T ek` interleaves bulk-index headers with data records; only the
        # latter carry .layers.
        'select(.layers) | .layers as $L',
        '| ($L["ip_src"][0] // "") as $src',
        '| ($L["ip_dst"][0] // "") as $dst',
        '| (($L["frame_time_epoch"][0] // "0") | tonumber) as $ts',
        '| ($L["tcp_srcport"][0] // "") as $sport',
        '| ($L["tcp_dstport"][0] // "") as $dport',
        # Outbound == "toward a Pixelblaze". Named devices settle it outright.
        # Otherwise orient by the listening port: a Pixelblaze is always the
        # websocket *server*, so the end sitting on port 81 is the device --
        # true even for traffic between two third parties, or between two
        # Pixelblazes in a sync group. Our own IP is the last resort.
        '| (if ($devs | length) > 0 then (($devs | index($dst)) != null)',
        '   elif ($ports | index($dport)) then true',
        '   elif ($ports | index($sport)) then false',
        '   else ($src == $host) end) as $out',
        '| (if $out then $dst else $src end) as $peer',
    ]

    # Normally direction is a display filter, but `tshark -w` refuses to run
    # one while saving, so it falls to us instead.
    if direction == 'requests':
        lines.append('| select($out)')
    elif direction == 'responses':
        lines.append('| select($out | not)')

    lines += [
        # One record per websocket frame, not per packet. Packets carrying no
        # websocket text at all (acks, the HTTP handshake) drop out here, which
        # is also what stands in for `-Y websocket` when there is no -Y.
        '| ($L["websocket_payload_text"] // [])[]',
        '| . as $raw',
    ]

    if grep:
        lines.append('| select($raw | test($grep))')
    if exclude:
        lines.append('| select($raw | test($exclude) | not)')

    # Pixelblaze frames are JSON, but a truncated or non-JSON frame should
    # still print rather than abort the stream. $raw must be bound outside the
    # try/catch: inside catch, `.` is the error message, not the input.
    lines.append('| (try ($raw | fromjson) catch $raw) as $msg')

    if bare:
        lines.append('| $msg')
        return '\n'.join(lines) + (f'\n| {extra}' if extra else '')

    fields = []
    if show_time:
        lines.append(f'| {_JQ_CLOCK} as $clock')
        fields.append('ts: $clock')
    if show_dir:
        fields.append('dir: (if $out then "\\u2192" else "\\u2190" end)')
    if show_peer:
        fields.append('peer: $peer')
    if show_endpoints:
        fields.append('src: $src')
        fields.append('dst: $dst')
    fields.append('msg: $msg')

    lines.append('| {' + ', '.join(fields) + '}')
    if extra:
        lines.append(f'| {extra}')
    return '\n'.join(lines)


# tshark has no dissector for the Pixelblaze discovery packets, so `-T ek`
# hands their payload over as one bare lowercase hex string under `data_data`.
# These helpers pull little-endian 32-bit words and dotted quads out of it.
_JQ_LE_HELPERS = '''\
def hexval: if . >= 97 then . - 87 elif . >= 65 then . - 55 else . - 48 end;
def hex2int: explode | map(hexval) | reduce .[] as $d (0; . * 16 + $d);
def word($i): .[($i * 8):($i * 8 + 8)];
def le32($i): word($i) as $w | ($w[6:8] + $w[4:6] + $w[2:4] + $w[0:2]) | hex2int;
def ip4($i): word($i) as $w | [$w[0:2], $w[2:4], $w[4:6], $w[6:8]] | map(hex2int | tostring) | join(".");
def wrap32: (. % 4294967296) | (if . < 0 then . + 4294967296 else . end)
  | (if . >= 2147483648 then . - 4294967296 else . end);
def byte($b): .[($b * 2):($b * 2 + 2)] | hex2int;
def le16($b): .[($b * 2):($b * 2 + 4)] as $w | ($w[2:4] + $w[0:2]) | hex2int;
def s16($b): le16($b) | (if . >= 32768 then . - 65536 else . end);
def r4: . * 10000 | round | . / 10000;
def spark: (if . > 1 then 1 elif . < 0 then 0 else . end)
  | (. * 7.999 | floor) as $i | [9601 + $i] | implode;'''

# Wire format, from docs/pixelblazeProtocol.md and PixelblazeEnumerator: every
# word is a little-endian uint32.
#   beacon   (type 42, 12 bytes): 42, senderId, senderTimeMs
#   timeSync (type 43, 20 bytes): 43, syncId, nowMs, senderId, senderTimeMs
#   sensor   (type 50, 104 bytes): 50, senderId, senderTimeMs, expansionType,
#            3 pad, then the SB1.0 frame of 16-bit readings (see SensorPacket).
# Sensor readings are uint16 at 65536 = 1.0, except maxFrequency which is Hz
# and the accelerometer which is signed at 32768 = 1.0.
# senderId is the Pixelblaze's own IPv4 address in byte order, so it is shown
# both raw (what the library keys devices by and echoes in timeSync) and dotted.
# senderTimeMs is the low 32 bits of the device's unix clock in milliseconds.
_JQ_UDP_DECODE = [
    'select(.layers) | .layers as $L',
    '| ($L["ip_src"][0] // "") as $src',
    '| ($L["ip_dst"][0] // "") as $dst',
    '| (($L["frame_time_epoch"][0] // "0") | tonumber) as $ts',
    '| ($L["udp_srcport"][0] // "") as $sport',
    '| ($L["udp_dstport"][0] // "") as $dport',
    '| (($L["data_data"] // [""])[0] | ascii_downcase) as $hex',
    '| ($hex | length / 2) as $len',
    '| (if $len >= 4 then ($hex | le32(0)) else null end) as $type',
    # A beacon carries the sender's clock; against the capture time that is the
    # skew timeSync exists to correct, so it is worth showing on every line.
    '| (($ts * 1000 | floor) % 4294967296) as $now32',
    '| (if $type == 42 and $len >= 12 then',
    '     {kind: "beacon", src: $src, sender_id: ($hex | le32(1)), sender_ip: ($hex | ip4(1)),',
    '      sender_ms: ($hex | le32(2))}',
    '     | .skew_ms = ((.sender_ms - $now32) | wrap32)',
    '   elif $type == 43 and $len >= 20 then',
    '     {kind: "timeSync", src: $src, dst: $dst, sync_id: ($hex | le32(1)), time_ms: ($hex | le32(2)),',
    '      sender_id: ($hex | le32(3)), sender_ip: ($hex | ip4(3)), sender_ms: ($hex | le32(4))}',
    '   elif $type == 50 and $len >= 104 then',
    '     [range(0; 32) as $i | ($hex | le16(16 + $i * 2)) / 65536] as $bins',
    '     | ($bins | max) as $peak',
    '     | {kind: "sensor", src: $src, dst: $dst, sender_id: ($hex | le32(1)),',
    '        sender_ms: ($hex | le32(2)), expansion: ($hex | byte(12)),',
    '        energy: ($hex | le16(80) / 65536 | r4),',
    '        max_mag: ($hex | le16(82) / 65536 | r4), max_hz: ($hex | le16(84)),',
    '        accel: [range(0; 3) as $i | ($hex | s16(86 + $i * 2)) / 32768 | r4],',
    '        light: ($hex | le16(92) / 65536 | r4),',
    '        analog: [range(0; 5) as $i | ($hex | le16(94 + $i * 2)) / 65536 | r4],',
    '        peak: ($peak | r4), bins: ($bins | map(r4)),',
    # Shape at a glance: each band scaled against the loudest one in the frame,
    # so a spectrum reads as a spectrum however quiet the source is.
    '        spectrum: (if $peak > 0 then ($bins | map(. / $peak | spark) | join(""))',
    '                   else "\u2581" * 32 end)}',
    '   else {kind: "unknown", type: $type, src: $src, dst: $dst, len: $len, hex: $hex} end) as $rec',
]


def _jq_udp_program(show_time: bool, show_endpoints: bool, bare: bool,
                    grep: str | None, exclude: str | None, extra: str | None,
                    direction: str | None = None, sensor_only: bool = False) -> str:
    """Assemble the jq filter for `--udp`.

    Every datagram is one record, decoded by packet type. "Requests" are
    packets sent TO a Pixelblaze (timeSync, and sensor board frames),
    "responses" are beacons (sent BY one), so the direction flags keep their
    meaning from websocket mode.
    """
    lines = [_JQ_LE_HELPERS] + list(_JQ_UDP_DECODE)

    if sensor_only:
        lines.append('| select($rec.kind == "sensor")')

    if direction == 'requests':
        lines.append('| select($rec.kind == "timeSync" or $rec.kind == "sensor")')
    elif direction == 'responses':
        lines.append('| select($rec.kind == "beacon")')

    # There is no raw text to match against, so grep/exclude see the decoded
    # record as JSON — `-g 1.86`-style matches on the dotted address work.
    if grep:
        lines.append('| select(($rec | tojson) | test($grep))')
    if exclude:
        lines.append('| select(($rec | tojson) | test($exclude) | not)')

    if bare:
        lines.append('| $rec')
    else:
        leading, trailing = [], []
        if show_time:
            lines.append(f'| {_JQ_CLOCK} as $clock')
            leading.append('ts: $clock')
        if show_endpoints:
            trailing += ['dst: $dst', 'sport: $sport', 'dport: $dport']
        # 32 floats per frame, 40 frames a second, is not something anyone
        # reads. The sparkline carries the shape; --bare keeps the numbers.
        record = '($rec | del(.bins))'
        if leading:
            record = '{' + ', '.join(leading) + '} + ' + record
        if trailing:
            record += ' + {' + ', '.join(trailing) + '}'
        lines.append(f'| {record}')

    if extra:
        lines.append(f'| {extra}')
    return '\n'.join(lines)


# ── Process plumbing ────────────────────────────────────────────────────────

def _restore_sigpipe():
    """Undo Python's SIGPIPE=SIG_IGN for children.

    Inherited SIG_IGN turns a closed downstream pipe into an EPIPE the child
    has to notice and report; the default disposition just kills it quietly,
    which is what a shell pipeline does and what `pb snoop | head` expects.
    """
    if hasattr(signal, 'SIGPIPE'):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)


# subprocess rejects preexec_fn outright on Windows, and there is no SIGPIPE
# there to restore anyway, so the hook has to be dropped rather than no-opped.
_POPEN_HOOK = {} if sys.platform == 'win32' else {'preexec_fn': _restore_sigpipe}


def _stop(proc: subprocess.Popen, grace: float = 3.0):
    """Terminate a child if it is still running, escalating to kill."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=grace)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=grace)
        except Exception:
            pass


# ── Command ─────────────────────────────────────────────────────────────────

_TSHARK_FIELDS = ('ip.src', 'ip.dst', 'tcp.srcport', 'tcp.dstport',
                  'frame.time_epoch', 'websocket.payload.text')
_TSHARK_UDP_FIELDS = ('ip.src', 'ip.dst', 'udp.srcport', 'udp.dstport',
                      'frame.time_epoch', 'data.data')
# HTTP is where the firmware endpoints live — /update (OTA), /recovery.html,
# /wifistatus, /wifiscan. None of it is visible in a websocket-only capture,
# and the OTA response in particular is worth seeing: the device answers a
# failed flash with 200 "Update Success! Rebooting...".
_TSHARK_HTTP_FIELDS = ('ip.src', 'ip.dst', 'tcp.srcport', 'tcp.dstport',
                       'frame.time_epoch', 'http.request.method',
                       'http.request.uri', 'http.response.code',
                       'http.content_type', 'http.content_length')
# --all: one capture, all three protocols, one timeline. Fields absent from a
# given packet simply do not appear in its `-T ek` object, so the union is safe.
_TSHARK_ALL_FIELDS = tuple(dict.fromkeys(
    _TSHARK_FIELDS + _TSHARK_UDP_FIELDS + _TSHARK_HTTP_FIELDS))

def _jq_http_program(show_time: bool, bare: bool, grep: str | None,
                     exclude: str | None, extra: str | None) -> str:
    """One line per HTTP request or response, request/response paired by nothing
    at all — tshark emits them as they go past, which is the order that matters
    when you are watching an OTA and the websocket state in the same capture."""
    parts = ['select(.layers) | .layers as $L',
             '| ($L["ip_src"][0] // "") as $src',
             '| ($L["ip_dst"][0] // "") as $dst',
             '| (($L["frame_time_epoch"][0] // "0") | tonumber) as $ts',
             '| ($L["http_request_method"][0] // null) as $method',
             '| ($L["http_request_uri"][0] // null) as $uri',
             '| ($L["http_response_code"][0] // null) as $code',
             '| ($L["http_content_type"][0] // null) as $ctype',
             '| ($L["http_content_length"][0] // null) as $clen',
             '| select($method != null or $code != null)',
             '| {kind: "http", src: $src, dst: $dst}',
             '+ (if $method then {method: $method, uri: $uri} else {} end)',
             '+ (if $code then {status: ($code | tonumber)} else {} end)',
             '+ (if $ctype then {contentType: $ctype} else {} end)',
             '+ (if $clen then {bytes: ($clen | tonumber)} else {} end)']
    if show_time:
        parts.append('+ {ts: ($ts | strftime("%H:%M:%S"))}')
    if bare:
        parts.append('| {method, uri, status} | with_entries(select(.value != null))')
    prog = '\n'.join(parts)
    if grep:
        prog += f'\n| select(tostring | test({json.dumps(grep)}))'
    if exclude:
        prog += f'\n| select(tostring | test({json.dumps(exclude)}) | not)'
    if extra:
        prog += f'\n| {extra}'
    return prog


def _jq_all_program(show_time: bool, grep: str | None, exclude: str | None,
                    extra: str | None) -> str:
    """websocket + HTTP + UDP:1889 on one timeline, each line tagged by `kind`.

    The point is correlation: an OTA is an HTTP POST whose real verdict arrives
    as websocket `upgradeState` frames, and a sync group is UDP. Watching any
    one of the three in isolation is how you end up believing the HTTP response.
    """
    parts = ['select(.layers) | .layers as $L',
             '| ($L["ip_src"][0] // "") as $src',
             '| ($L["ip_dst"][0] // "") as $dst',
             '| (($L["frame_time_epoch"][0] // "0") | tonumber) as $ts',
             '| ($L["websocket_payload_text"][0] // null) as $ws',
             '| ($L["http_request_method"][0] // null) as $method',
             '| ($L["http_response_code"][0] // null) as $code',
             '| ($L["data_data"][0] // null) as $udp',
             '| (if $ws then {kind: "ws", text: $ws}',
             '   elif $method then {kind: "http", method: $method, uri: ($L["http_request_uri"][0] // "")}',
             '   elif $code then {kind: "http", status: ($code | tonumber), contentType: ($L["http_content_type"][0] // null)}',
             '   elif $udp then {kind: "udp", bytes: (($udp | length) / 2 | floor)}',
             '   else empty end)',
             '| . + {src: $src, dst: $dst}']
    if show_time:
        parts.append('| . + {ts: ($ts | strftime("%H:%M:%S"))}')
    prog = '\n'.join(parts)
    if grep:
        prog += f'\n| select(tostring | test({json.dumps(grep)}))'
    if exclude:
        prog += f'\n| select(tostring | test({json.dumps(exclude)}) | not)'
    if extra:
        prog += f'\n| {extra}'
    return prog


_WS_PORT = 81        # Pixelblaze websocket API
_HTTP_PORT = 80      # /update, /recovery.html, /wifistatus, /wifiscan
_BEACON_PORT = 1889  # discovery beacons and timeSync


def register(cli_group):
    """Attach `snoop` to the given click group.

    Kept in a sibling module (like `pb top`) so cli.py stays navigable.
    """

    @cli_group.command()
    @click.option('-u', '--udp', '--beacons', 'udp_mode', is_flag=True,
                  help='Capture the UDP:1889 discovery traffic instead of websocket frames: '
                       'the beacon every Pixelblaze broadcasts about once a second, and the '
                       'timeSync packets Firestorm answers with. Broadcast, so this sees '
                       'every device on the LAN, not only ones this machine talks to. '
                       'Shows all devices unless --ip or --others narrows it.')
    @click.option('-H', '--http', 'http_mode', is_flag=True,
                  help='Capture the HTTP endpoints instead of websocket frames: /update '
                       '(OTA), /recovery.html, /wifistatus, /wifiscan. Invisible to a '
                       'websocket-only capture, and the OTA response is worth seeing — a '
                       'failed flash is answered with 200 "Update Success! Rebooting...".')
    @click.option('-A', '--all', 'all_mode', is_flag=True,
                  help='Everything this device says, on one timeline: websocket frames, '
                       'HTTP, and UDP:1889, each line tagged with "kind". Use when the '
                       'answer spans protocols — an OTA is an HTTP POST whose real verdict '
                       'arrives as websocket upgradeState frames.')
    @click.option('-S', '--sensor', 'sensor_only', is_flag=True,
                  help='Implies --udp and shows only sensor board frames: the UDP:1889 '
                       'audio/accelerometer/light datagrams a sync group leader — or '
                       '`pb sensor sound` — streams to Pixelblazes. Each line carries a '
                       'sparkline of the 32 frequency bands; --bare adds the raw numbers.')
    @click.option('-a', '--any', 'any_device', is_flag=True,
                  help='Do not filter by device at all, and skip IP resolution entirely. '
                       'Shows every websocket conversation on the interface.')
    @click.option('-o', '--others', default=None, metavar='CSV',
                  help='Additional devices to include, comma-separated. Each accepts the '
                       'same forms as --ip (address, pasted URL, bare host octet, cached '
                       'name fragment), e.g. --others 231,kitchen,http://192.168.1.5/')
    @click.option('--host', 'host_spec', default='any', show_default=True, metavar='SPEC',
                  help='Restrict the non-Pixelblaze end of the conversation. "any" shows '
                       'every client talking to the device; "me" restricts to this '
                       'machine; anything else is resolved like --ip.')
    @click.option('-q', '--requests', is_flag=True,
                  help='Only frames sent TO a Pixelblaze (host -> device).')
    @click.option('-s', '--responses', is_flag=True,
                  help='Only frames sent BY a Pixelblaze (device -> host).')
    @click.option('-i', '--iface', default=None, metavar='NAME',
                  help='Capture interface. Default: whichever one the kernel routes to '
                       'the target (so AP mode and Ethernet just work).')
    @click.option('-p', '--port', 'ports_csv', default=None, metavar='CSV',
                  help='Port(s) to capture, comma-separated. Default 81, the Pixelblaze '
                       'websocket API (add 80 to also catch the HTTP file endpoints); '
                       'with --udp, default 1889.')
    @click.option('-m', '--midstream', is_flag=True,
                  help='Decode port traffic as websocket directly instead of waiting for an '
                       'HTTP upgrade handshake. Needed when the connection you want to watch '
                       'was already open before snooping started. Do NOT use it when the '
                       'handshake is captured — tshark will try to parse it as frames.')
    @click.option('-g', '--grep', default=None, metavar='RE',
                  help='Only show frames whose raw payload matches this regex.')
    @click.option('-v', '--exclude', default=None, metavar='RE',
                  help='Hide frames whose raw payload matches this regex (e.g. -v fps).')
    @click.option('-j', '--jq', 'jq_prog', default=None, metavar='PROG',
                  help='Extra jq program appended to the pipeline, e.g. '
                       '--jq \'select(.msg.activeProgram)\'')
    @click.option('-t', '--time', 'show_time', is_flag=True,
                  help='Prefix each frame with a local clock timestamp.')
    @click.option('-b', '--bare', is_flag=True,
                  help='Emit only the decoded message, with no envelope — the raw '
                       'stream of Pixelblaze protocol JSON.')
    @click.option('-f', '--full', is_flag=True,
                  help='Always include ts, dir, peer, src and dst, even when they would '
                       'be constant.')
    @click.option('-c', '--count', type=int, default=None, metavar='N',
                  help='Stop after N captured packets (not frames — a packet may carry '
                       'several).')
    @click.option('-d', '--duration', type=float, default=None, metavar='SECS',
                  help='Stop after SECS seconds.')
    @click.option('--read', 'read_file', default=None,
                  type=click.Path(exists=True, dir_okay=False),
                  help='Decode a saved capture instead of going live. No permissions needed.')
    @click.option('-w', '--write', 'write_file', default=None,
                  type=click.Path(dir_okay=False),
                  help='Also save raw captured packets to this pcapng, while still '
                       'streaming decoded output.')
    @click.option('--color', 'color_mode',
                  type=click.Choice(['auto', 'always', 'never']), default='auto',
                  show_default=True,
                  help='Colorize output. "auto" colors only when stdout is a terminal '
                       'and NO_COLOR is unset.')
    @click.option('--no-color', is_flag=True, help='Alias for --color never.')
    @click.option('-n', '--dry-run', is_flag=True,
                  help='Print the tshark | jq pipeline that would run, then exit. '
                       'Copy, tweak, run it yourself.')
    @click.option('--sudo', 'use_sudo', is_flag=True,
                  help='Run tshark under sudo, for when the capture device is root-only.')
    @click.pass_context
    def snoop(ctx, udp_mode, http_mode, all_mode, sensor_only, any_device, others, host_spec, requests, responses, iface,
              ports_csv, midstream, grep, exclude, jq_prog, show_time, bare, full, count,
              duration, read_file, write_file, color_mode, no_color, dry_run, use_sudo):
        """
        Watch Pixelblaze traffic live, decoded to JSON. Alias: pb watch.

        Wraps `tshark` (capture + dissection) piped into `jq` (filtering +
        pretty-printing); both must be installed. Every websocket text frame
        to or from the device is printed as one JSON line as it happens —
        the exact protocol chatter the web UI and this CLI generate. With
        --udp it is the discovery beacons on UDP:1889 instead.

        \b
        Requests vs responses:
            A "request" is a frame going TO a Pixelblaze, a "response" one
            coming FROM it. Both are shown by default.

        \b
        Which device:
            Uses the same flexible resolution as --ip (address, pasted URL,
            bare host octet, cached name fragment). --others adds more
            devices to the same capture; --any drops the device filter
            entirely and skips resolution.

        \b
        Timing matters for decoding:
            By default tshark identifies websocket streams by watching for
            the HTTP upgrade handshake, so start `pb snoop` BEFORE the
            traffic you want to see. To attach to a connection that is
            already open (a browser tab you left running), pass --midstream.

        \b
        HTTP endpoints (--http) and everything (--all):
            --http decodes the firmware's HTTP side — /update (OTA),
            /recovery.html, /wifistatus, /wifiscan — which a websocket
            capture cannot see at all. Worth knowing when reading an OTA:
            the device answers a *failed* flash with 200 "Update Success!
            Rebooting...", so the HTTP response alone will lie to you.
            --all captures websocket, HTTP and UDP:1889 together and tags
            each line with "kind", which is what you want when the answer
            spans protocols: an OTA is an HTTP POST whose real verdict
            arrives as websocket upgradeState frames.

        \b
        Discovery beacons (--udp, alias --beacons):
            Every Pixelblaze that is not a sync-group follower broadcasts a
            beacon on UDP:1889 about once a second, and Firestorm answers
            each with a timeSync. --udp decodes both instead of websocket
            frames. Being broadcast, they are visible from anywhere on the
            LAN, which makes this the way to check what `pb find` can hear.
            --requests keeps only timeSync packets, --responses only beacons.
            Each beacon line carries skew_ms, the sender's clock minus ours.

        \b
        Examples:
            pb snoop                             # both directions, resolved device
            pb snoop --responses                 # only what the Pixelblaze says
            pb snoop --requests -t               # only what we send, timestamped
            pb --ip kitchen snoop                # by cached name
            pb snoop --others 231,bike2          # several devices at once
            pb snoop --any                       # every websocket on the wire
            pb snoop --http -t                   # the HTTP endpoints, timestamped
            pb snoop --all -t                    # ws + HTTP + UDP on one timeline
            pb snoop --host me                   # ignore other clients
            pb snoop -v '"fps"'                  # hide the periodic status spam
            pb snoop -g setVars                  # only variable writes
            pb snoop --jq 'select(.msg.fps)'     # arbitrary jq
            pb snoop --bare > session.jsonl      # clean protocol log
            pb snoop --midstream                 # attach to an open connection
            pb snoop --dry-run                   # show the pipeline, run it yourself
            pb snoop --udp                       # every discovery beacon on the LAN
            pb snoop --beacons -t                # ...timestamped, with clock skew
            pb --ip bike2 snoop --udp            # one device's beacons and timeSyncs
            pb watch --udp --requests            # only timeSync packets
        """
        tshark_bin = _require('tshark')
        jq_bin = _require('jq')

        # --sensor is --udp narrowed to one packet type; nothing else about
        # the capture differs, so just turn udp mode on.
        udp_mode = udp_mode or sensor_only

        chosen = [n for n, on in (('--udp', udp_mode), ('--http', http_mode),
                                  ('--all', all_mode)) if on]
        if len(chosen) > 1:
            raise click.ClickException(
                f"{' and '.join(chosen)} are different captures — pick one. "
                f"--all already includes what the others show.")
        if all_mode:
            # One capture covering all three, so the ports have to cover them too.
            udp_mode = False

        live = read_file is None
        if not live and (write_file or count or duration):
            log("Note: --write/--count/--duration apply to live capture; ignored with --read.")

        if ports_csv is None:
            if all_mode:
                ports_csv = f'{_HTTP_PORT},{_WS_PORT}'      # UDP:1889 added to the filter below
            elif http_mode:
                ports_csv = str(_HTTP_PORT)
            else:
                ports_csv = str(_BEACON_PORT if udp_mode else _WS_PORT)
        try:
            ports = [int(p.strip()) for p in ports_csv.split(',') if p.strip()]
        except ValueError:
            raise click.ClickException(f"--port must be a comma-separated list of numbers, got '{ports_csv}'")
        if not ports:
            raise click.ClickException("--port needs at least one port.")

        if udp_mode and midstream:
            log("Note: --midstream only affects websocket decoding; ignored with --udp.")

        # ── Work out who we're watching ──────────────────────────────────
        devices: list[str] = []
        if any_device:
            if others:
                raise click.ClickException("--any and --others are mutually exclusive: "
                                           "--any already captures every device.")
        elif udp_mode:
            # Beacons are broadcast, so "every device" is the natural default —
            # and running discovery to pick one would be circular when the point
            # is usually to see whether any beacons exist at all. Only an
            # explicit --ip (or --others) narrows the capture.
            explicit = resolve_ip_spec(ctx.obj.get('ip', 'auto'))
            if explicit:
                devices.append(explicit)
            for ip in _resolve_others(others):
                if ip not in devices:
                    devices.append(ip)
        else:
            # Import here so `--any` never pays for (or fails on) discovery.
            from pixelblaze.cli.cli_utils import discover_pixelblaze
            devices.append(discover_pixelblaze(ctx))
            for ip in _resolve_others(others):
                if ip not in devices:
                    devices.append(ip)

        host = _resolve_host(host_spec)

        capture_filter = ''
        if live:
            if all_mode:
                # Both transports in one BPF expression: the TCP endpoints plus
                # the beacon port, still narrowed to the devices we care about.
                tcp_part = _capture_filter([], None, ports, proto='tcp')
                both = f'(({tcp_part}) or udp port {_BEACON_PORT})'
                who = ' or '.join(f'host {ip}' for ip in devices)
                capture_filter = f'{both} and ({who})' if devices else both
            else:
                capture_filter = _capture_filter(devices, host, ports,
                                                 proto='udp' if udp_mode else 'tcp')

        # `tshark -w` and `-Y` are mutually exclusive on a live capture, so when
        # saving we narrow with the BPF capture filter alone and let jq do the
        # rest. The saved file is the better for it: it keeps the whole TCP
        # stream including the HTTP upgrade, so `--read` can replay it without
        # needing --midstream.
        saving_live = bool(live and write_file)
        wants_direction = requests != responses
        if all_mode:
            # Let everything through and tag it in jq; a per-protocol display
            # filter would be three filters and could only drop things.
            who = ' or '.join(f'ip.addr == {ip}' for ip in devices)
            expr = '(websocket or http or udp.port == %d)' % _BEACON_PORT
            display_filter = None if saving_live else (
                f'{expr} and ({who})' if devices else expr)
            jq_direction = None
        elif http_mode:
            who = ' or '.join(f'ip.addr == {ip}' for ip in devices)
            display_filter = None if saving_live else (
                f'http and ({who})' if devices else 'http')
            jq_direction = None
        elif udp_mode:
            # Direction is a packet-type question here, so jq always owns it.
            display_filter = None if saving_live else _udp_display_filter(devices, host, ports)
            jq_direction = ('requests' if requests else 'responses') if wants_direction else None
        else:
            display_filter = None if saving_live else _display_filter(
                devices, host, ports, requests, responses)
            jq_direction = None
            if saving_live and wants_direction:
                jq_direction = 'requests' if requests else 'responses'

        if iface is None and live:
            iface = _default_iface(devices[0] if devices else None)

        # ── Build the tshark side ────────────────────────────────────────
        decode_proto = 'websocket' if midstream else 'http'
        tshark_cmd = [tshark_bin]
        if live:
            tshark_cmd += ['-i', iface]
        else:
            tshark_cmd += ['-r', read_file]
        tshark_cmd += ['-l', '-n', '-q']
        if not udp_mode:
            for port in ports:
                tshark_cmd += ['-d', f'tcp.port=={port},{decode_proto}']
        if live and capture_filter:
            tshark_cmd += ['-f', capture_filter]
        if display_filter is not None:
            tshark_cmd += ['-Y', display_filter]
        tshark_cmd += ['-T', 'ek']
        fields = (_TSHARK_ALL_FIELDS if all_mode else
                  _TSHARK_HTTP_FIELDS if http_mode else
                  _TSHARK_UDP_FIELDS if udp_mode else _TSHARK_FIELDS)
        for field in fields:
            tshark_cmd += ['-e', field]
        if live and write_file:
            tshark_cmd += ['-w', write_file]
        if live and count:
            tshark_cmd += ['-c', str(count)]
        if live and duration:
            tshark_cmd += ['-a', f'duration:{duration}']
        if use_sudo:
            tshark_cmd = ['sudo'] + tshark_cmd

        # ── Build the jq side ────────────────────────────────────────────
        both_directions = requests == responses  # neither flag, or both
        multi_peer = any_device or len(devices) > 1
        if all_mode:
            program = _jq_all_program(
                show_time=show_time or full, grep=grep, exclude=exclude, extra=jq_prog)
        elif http_mode:
            program = _jq_http_program(
                show_time=show_time or full, bare=bare,
                grep=grep, exclude=exclude, extra=jq_prog)
        elif udp_mode:
            program = _jq_udp_program(
                show_time=show_time or full,
                show_endpoints=full,
                bare=bare,
                grep=grep, exclude=exclude, extra=jq_prog,
                direction=jq_direction, sensor_only=sensor_only,
            )
        else:
            program = _jq_program(
                show_time=show_time or full,
                show_dir=full or both_directions,
                show_peer=full or multi_peer,
                show_endpoints=full or any_device,
                bare=bare,
                grep=grep, exclude=exclude, extra=jq_prog,
                direction=jq_direction,
            )

        if no_color:
            color_mode = 'never'
        if color_mode == 'auto':
            use_color = sys.stdout.isatty() and not os.environ.get('NO_COLOR')
        else:
            use_color = color_mode == 'always'

        jq_cmd = [jq_bin, '-c', '--unbuffered', '-C' if use_color else '-M']
        jq_cmd += ['--argjson', 'devs', '[' + ','.join(f'"{ip}"' for ip in devices) + ']']
        jq_cmd += ['--argjson', 'ports', '[' + ','.join(f'"{p}"' for p in ports) + ']']
        jq_cmd += ['--arg', 'host', host or get_host_ip() or '']
        if grep:
            jq_cmd += ['--arg', 'grep', grep]
        if exclude:
            jq_cmd += ['--arg', 'exclude', exclude]
        jq_cmd += [program]

        pipeline = f"{shlex.join(tshark_cmd)} \\\n  | {shlex.join(jq_cmd)}"

        if dry_run:
            click.echo(pipeline)
            return

        # ── Report what we're doing, then hand off ───────────────────────
        if live:
            # A FIFO or file path passed to -i is read directly, with no
            # capture device involved, so the BPF check doesn't apply.
            if not use_sudo and not os.path.exists(iface):
                _check_capture_permission()
            target = ', '.join(_label(ip) for ip in devices) if devices else 'any device'
            port_list = ','.join(str(p) for p in ports)
            if udp_mode:
                direction = ('sensor board frames only (-> device)' if sensor_only else
                             'timeSync + sensor only (-> device)' if requests and not responses else
                             'beacons only (<- device)' if responses and not requests else
                             'beacons + timeSync + sensor')
                log(f"snoop: iface {iface}, udp port {port_list}, {target}, {direction}")
                if sensor_only:
                    log("       nothing shows until something streams sensor data — a sync "
                        "group leader, or `pb sensor sound`")
                else:
                    log("       every Pixelblaze that is not a sync-group follower beacons "
                        "about once a second")
            else:
                direction = ('requests only (-> device)' if requests and not responses else
                             'responses only (<- device)' if responses and not requests else
                             'both directions')
                log(f"snoop: iface {iface}, port {port_list}, {target}, {direction}")
            if host:
                log(f"       other end restricted to {_label(host)}")
            if saving_live:
                log(f"       saving raw packets to {write_file} (filtering moves to jq, "
                    f"since tshark won't take a display filter while saving)")
            if not midstream and not udp_mode:
                log("       decoding via the HTTP upgrade handshake — pass --midstream "
                    "to attach to an already-open connection")
            log("       Ctrl+C to stop\n")

        try:
            capture = subprocess.Popen(tshark_cmd, stdout=subprocess.PIPE,
                                       **_POPEN_HOOK)
        except OSError as e:
            raise click.ClickException(f"Could not start tshark: {e}")

        try:
            render = subprocess.Popen(jq_cmd, stdin=capture.stdout, **_POPEN_HOOK)
        except OSError as e:
            capture.kill()
            raise click.ClickException(f"Could not start jq: {e}")

        # Close our copy of the pipe so tshark sees jq's exit as a real EOF.
        capture.stdout.close()

        interrupted = False
        try:
            render.wait()
        except KeyboardInterrupt:
            interrupted = True
            _stop(render)

        # jq is gone; tshark has nowhere to write. It would normally take a
        # SIGPIPE on its next packet, but a quiet network means there may not
        # be a next packet for a long time — so end it explicitly rather than
        # leaving a capture running behind a returned command.
        _stop(capture)

        if interrupted:
            log("\nStopped.")
            return

        if live and capture.returncode not in (0, None, -signal.SIGTERM):
            raise click.ClickException(
                f"tshark exited {capture.returncode}. Re-run with --dry-run to see the "
                f"exact command, or --sudo if this is a permissions problem."
            )

    # `pb watch` is the same command under a friendlier name.
    cli_group.add_command(snoop, name='watch')
    return snoop
