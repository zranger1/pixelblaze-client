"""`pb top` — realtime dashboard of Pixelblaze activity, `top(1)`-style.

Discovers every Pixelblaze on the LAN, then keeps a long-lived websocket
open to each and re-renders the table on a fixed interval. Devices that
drop off the network stay on the table as `down`; if they come back
(same IP, or a beacon rediscovery finds them at a new one), the row
turns green again and stats resume.
"""

from __future__ import annotations

import json
import shutil
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import click

from pixelblaze.pixelblaze import Pixelblaze
from pixelblaze.cli.cli_utils import (
    _fetch_device_config,
    _read_cache,
    enumerate_pixelblazes,
    log,
    update_device_cache,
)


# ── ANSI helpers ────────────────────────────────────────────────────────────

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
INVERT = "\x1b[7m"
# Cursor home + erase-to-end-of-screen. Some terminals treat `\x1b[2J` (erase
# entire screen) as a scroll, which leaves ghost frames stacked in scrollback;
# home-then-erase-down redraws cleanly everywhere.
CLEAR_HOME = "\x1b[H\x1b[J"
CLEAR_LINE_END = "\x1b[K"
HIDE_CURSOR = "\x1b[?25l"
SHOW_CURSOR = "\x1b[?25h"
COLORS = {
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "red": "\x1b[31m",
    "cyan": "\x1b[36m",
    "grey": "\x1b[90m",
}


def _c(s: str, color: Optional[str], enabled: bool) -> str:
    if not enabled or not color:
        return s
    return f"{COLORS.get(color, '')}{s}{RESET}"


# ── State ───────────────────────────────────────────────────────────────────

# Health thresholds, in seconds since last successful poll.
HEALTHY_MAX_AGE = 3.0
STALE_MAX_AGE = 15.0

# ── Display smoothing for FPS ───────────────────────────────────────────────
#
# A Pixelblaze's own fps counter is noisy, and the table redraws once a second,
# so the column was rewriting itself on half of all ticks — measured on a real
# fleet of two boards plus the emulator: 19/37 and 21/37 redraws changed the
# FPS cell, over a stretch where nothing about the lights changed.
#
# Two different kinds of noise, and they need different tools:
#
#   Single-sample dips. 131, 131, 131, *81*, 130, 131 … and 131 → *45* → 69.
#   A MEDIAN over a short window drops those outright, and — unlike an average
#   — only ever displays a number the device actually reported.
#
#   Boundary flicker. 131.5 and 131.7 round to 131 and 132, so a rock-steady
#   device alternated between two cells for ever. A DEADBAND fixes what an
#   average cannot: the shown value stays put until a reading moves it by more
#   than a few percent.
#
# Measured on the same capture, the pair takes the FPS column from 19/37 and
# 21/37 changes down to 1/37 and 4/37, while still tracking every sustained
# move — 131 → 69 on one board, and a genuine sustained 2330 on the other,
# which is not a spike (it held for many ticks) and so is shown.
#
# `Row.fps` keeps the raw last reading, and that is what `--json` emits: this
# is a rule about what a human watching a table should see, not about the data.
FPS_MEDIAN_WINDOW = 3
FPS_DEADBAND = 0.03      # relative
FPS_DEADBAND_FLOOR = 1.0  # absolute, so low readings aren't pinned by the ratio


def _record_failure(row: "Row", message: str) -> None:
    """Keep the FIRST explanation of an outage, not the latest retry's.

    `_render` prints an `↳ <error>` line under any row that is not `ok`, so
    every time this text changed the table gained or lost a line and every row
    below it moved. A device that is simply off the network cycles through
    several wordings of the same fact as the reconnect loop retries — measured
    on a real fleet, one board alternated between `[Errno 64] Host is down` and
    `timed out` — and the first one is usually the informative one anyway: the
    rest are consequences of it.

    A fresh message is taken once the device has been heard from again, so a
    NEW outage always reports its own cause.
    """
    row.connected = False
    if not row.error:
        row.error = message


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _push_fps(row: "Row", value: Optional[float]) -> None:
    """Record a raw reading and decide whether the displayed one should move."""
    row.fps = value
    if value is None:
        return
    row.fps_samples.append(value)
    del row.fps_samples[:-FPS_MEDIAN_WINDOW]
    m = _median(row.fps_samples)
    if row.fps_shown is None or \
            abs(m - row.fps_shown) > max(FPS_DEADBAND_FLOOR, FPS_DEADBAND * row.fps_shown):
        row.fps_shown = m

# How often each worker re-fetches config/sequencer (stats stream freely on
# their own; only pattern/name/etc need refreshing).
CONFIG_REFRESH_SECONDS = 10.0

# How often the reconnect loop retries a dead device.
RECONNECT_BACKOFF_SECONDS = 5.0


@dataclass
class Row:
    """Everything one device row on the top table needs to render itself."""
    ip: str
    name: str = ""
    ver: str = ""
    pixel_count: Optional[int] = None
    brightness: Optional[float] = None
    active_pattern_id: str = ""
    active_pattern_name: str = ""
    fps: Optional[float] = None
    mem: Optional[int] = None
    storage_used: Optional[int] = None
    storage_size: Optional[int] = None
    uptime_ms: Optional[int] = None  # raw Pixelblaze `uptime` — milliseconds
    last_seen: float = 0.0
    connected: bool = False
    error: str = ""

    # Extended fields (populated by _refresh_config from getConfigSettings +
    # getConfigSequencer). Rendered only for opt-in columns.
    brand: str = ""
    led_type: Optional[int] = None
    data_speed: Optional[int] = None
    color_order: str = ""
    max_brightness: Optional[int] = None    # settings.maxBrightness (0-100)
    cpu_speed: str = ""                     # settings.cpuSpeed (str: "80"/"160"/"240")
    power_save: Optional[bool] = None       # settings.networkPowerSave
    discovery: Optional[bool] = None        # settings.discoveryEnable
    timezone: str = ""                      # settings.timezone
    auto_off_enable: Optional[bool] = None  # settings.autoOffEnable
    auto_off_start: str = ""                # settings.autoOffStart ("HH:MM")
    auto_off_end: str = ""                  # settings.autoOffEnd
    simple_ui: Optional[bool] = None        # settings.simpleUiMode
    learning_ui: Optional[bool] = None      # settings.learningUiMode
    sensor_input: Optional[int] = None      # settings.sensorInputSource (0=mic,1=exp)

    # Sequencer / playlist
    seq_mode: Optional[int] = None          # 0=Off, 1=ShuffleAll, 2=Playlist
    seq_state: Optional[bool] = None        # runSequencer
    seq_shuffle_ms: Optional[int] = None    # sequencer.ms — default per-item duration
    plist_index: Optional[int] = None       # active item index (Playlist mode)
    plist_size: Optional[int] = None        # total items in playlist

    # Local tracking so we can show "time left in this pattern".
    # Set the moment we observe active_pattern_id change (best-effort — if a
    # pattern was already running when pb top started we can only estimate
    # from first-observation, not true start).
    pattern_started_at: float = 0.0         # monotonic seconds

    # Display smoothing for the FPS column — see _push_fps. `fps` stays the
    # raw last reading (it is what --json emits); `fps_shown` is what the
    # table prints.
    fps_samples: list = field(default_factory=list)
    fps_shown: Optional[float] = None


class TopMonitor:
    """Owns the shared rows dict, one worker thread per device, and the
    rediscovery thread. Main loop just reads snapshots and renders."""

    def __init__(self, initial_devices: list[dict], rediscover_seconds: float):
        self._lock = threading.Lock()
        self._rows: dict[str, Row] = {}
        self._workers: dict[str, threading.Thread] = {}
        self._stop = threading.Event()
        self._rediscover_seconds = rediscover_seconds

        for dev in initial_devices:
            ip = dev.get("ip")
            if not ip:
                continue
            self._ensure_worker(ip)
            # If the seed came from the on-disk cache, prime the row with
            # its last-known name / pattern / etc. so the table isn't blank
            # while the worker's first config fetch is in flight.
            self._seed_row_from_cache(ip, dev)

    def _seed_row_from_cache(self, ip: str, dev: dict):
        with self._lock:
            row = self._rows.get(ip)
            if not row:
                return
            row.name = dev.get("name") or row.name
            row.ver = str(dev.get("ver") or row.ver)
            row.pixel_count = dev.get("pixelCount", row.pixel_count)
            row.brightness = dev.get("brightness", row.brightness)
            active_id = dev.get("activePatternId") or ""
            if active_id:
                row.active_pattern_id = active_id
                patterns = dev.get("patterns") or {}
                row.active_pattern_name = (
                    patterns.get(active_id)
                    or dev.get("activePatternName")
                    or row.active_pattern_name
                )
            # Extended fields — `pb find` (slow mode) persists `settings` /
            # `sequencer` sub-dicts into the cache; hydrate whatever we can
            # so custom columns aren't blank until the first live refresh.
            settings = dev.get("settings") or {}
            row.brand = dev.get("brandName") or settings.get("brandName") or row.brand
            row.led_type = settings.get("ledType", row.led_type)
            row.data_speed = settings.get("dataSpeed", row.data_speed)
            row.color_order = str(settings.get("colorOrder") or row.color_order)
            row.max_brightness = settings.get("maxBrightness", row.max_brightness)
            row.cpu_speed = str(settings.get("cpuSpeed") or row.cpu_speed)
            if "networkPowerSave" in settings:
                row.power_save = settings["networkPowerSave"]
            if "discoveryEnable" in settings:
                row.discovery = settings["discoveryEnable"]
            row.timezone = str(settings.get("timezone") or row.timezone)
            if "autoOffEnable" in settings:
                row.auto_off_enable = settings["autoOffEnable"]
            row.auto_off_start = str(settings.get("autoOffStart") or row.auto_off_start)
            row.auto_off_end = str(settings.get("autoOffEnd") or row.auto_off_end)
            if "simpleUiMode" in settings:
                row.simple_ui = settings["simpleUiMode"]
            if "learningUiMode" in settings:
                row.learning_ui = settings["learningUiMode"]
            if "sensorInputSource" in settings:
                row.sensor_input = settings["sensorInputSource"]
            sequencer = dev.get("sequencer") or {}
            if "sequencerMode" in sequencer:
                row.seq_mode = sequencer["sequencerMode"]
            if "runSequencer" in sequencer:
                row.seq_state = sequencer["runSequencer"]
            if "ms" in sequencer:
                row.seq_shuffle_ms = sequencer["ms"]
            playlist_items = ((sequencer.get("playlist") or {}).get("items")) or []
            if playlist_items:
                row.plist_size = len(playlist_items)

    def stop(self):
        self._stop.set()

    def snapshot(self) -> list[Row]:
        with self._lock:
            return list(self._rows.values())

    def _ensure_worker(self, ip: str):
        with self._lock:
            if ip in self._rows:
                return
            self._rows[ip] = Row(ip=ip)
        t = threading.Thread(target=self._worker, args=(ip,), daemon=True, name=f"pb-top-{ip}")
        self._workers[ip] = t
        t.start()

    def _set(self, ip: str, **kwargs):
        with self._lock:
            row = self._rows.get(ip)
            if not row:
                return
            for k, v in kwargs.items():
                setattr(row, k, v)

    def _push(self, ip: str, fn, *args):
        """Apply `fn(row, *args)` under the lock — for updates that read the
        row's own previous state rather than just overwriting a field."""
        with self._lock:
            row = self._rows.get(ip)
            if row:
                fn(row, *args)

    def _worker(self, ip: str):
        """Per-device: keep the socket open, drain stats frames, refresh
        config every so often. On any error, close, back off, retry.

        We don't use pb.getStatistics() because it loops forever when the
        device stops responding — its inner wsReceive returns None on
        timeout, then getStatistics just tries again. Instead we drive
        wsReceive ourselves so we can bail on staleness."""
        is_first_connect = True
        while not self._stop.is_set():
            pb: Optional[Pixelblaze] = None
            try:
                pb = Pixelblaze(ip)
                # Row visibility fast-path: a successful WS handshake IS a
                # "we heard from this device just now" signal, so seed
                # last_seen too. Without this the row shows as red `down`
                # until the first stats frame lands (up to ~3s later),
                # even though the cached name/pattern are on-screen.
                # The stale-reconnect check uses last_stats_at, not
                # last_seen, so this doesn't affect reconnect timing.
                self._set(ip, connected=True, error="", last_seen=time.monotonic())
                # Pixelblaze streams `{"fps":...}` stats frames on its own
                # every ~1s over an open socket — no explicit sendUpdates
                # request needed (and calling setSendPreviewFrames(True)
                # here would also start binary preview frames, which we'd
                # only throw away and which cost real bandwidth per device).

                # First-connect fast path: if the row was seeded from cache
                # (has a name), skip the initial config fetch entirely — the
                # cached name/pattern/etc are already on-screen, and stats
                # will stream in ~1s. Otherwise do just getConfigSettings
                # (the cheap one) to populate the name; skip the heavier
                # getPatternList until the periodic refresh. The periodic
                # refresh timer is set so a full refresh happens ~2s later.
                if is_first_connect:
                    with self._lock:
                        seeded = bool(self._rows.get(ip) and self._rows[ip].name)
                    if not seeded:
                        # No cache seed for this row — fetch just the cheap
                        # settings RPC so the name shows up; defer the heavy
                        # getPatternList to the periodic refresh below.
                        self._prime_name(pb, ip)
                    # Force the first periodic refresh soon (~2s) so we
                    # pick up any drift without paying the cost up-front.
                    last_config_refresh = time.monotonic() - (CONFIG_REFRESH_SECONDS - 2.0)
                    is_first_connect = False
                else:
                    self._refresh_config(pb, ip)
                    last_config_refresh = time.monotonic()
                last_stats_at = time.monotonic()

                while not self._stop.is_set():
                    # Drains any binary preview frames and stashes stats/
                    # sequencer text frames into pb.latestStats /
                    # pb.latestSequencer. Returns after default_recv_timeout.
                    pb.wsReceive(binaryMessageType=None)
                    now = time.monotonic()
                    if pb.latestStats:
                        try:
                            stats = json.loads(pb.latestStats)
                        except Exception:
                            stats = {}
                        pb.latestStats = None
                        # fps goes through _push_fps (raw value kept, shown
                        # value smoothed) rather than straight into the row.
                        self._push(ip, _push_fps, stats.get("fps"))
                        self._set(
                            ip,
                            mem=stats.get("mem"),
                            storage_used=stats.get("storageUsed"),
                            storage_size=stats.get("storageSize"),
                            uptime_ms=stats.get("uptime"),
                            last_seen=now,
                            connected=True,
                            error="",
                        )
                        last_stats_at = now

                    if now - last_stats_at > STALE_MAX_AGE:
                        # Peer went quiet: kick the loop so we reconnect.
                        raise ConnectionError("no stats for >{:.0f}s".format(STALE_MAX_AGE))

                    if now - last_config_refresh > CONFIG_REFRESH_SECONDS:
                        self._refresh_config(pb, ip)
                        last_config_refresh = time.monotonic()

            except Exception as e:
                self._push(ip, _record_failure, str(e).splitlines()[0][:60])
            finally:
                if pb is not None:
                    try:
                        pb._close()
                    except Exception:
                        pass

            # Backoff before reconnect.
            if self._stop.wait(RECONNECT_BACKOFF_SECONDS):
                return

    def _prime_name(self, pb: Pixelblaze, ip: str):
        """Fast first-connect populate: just the cheap RPC to get the name.
        Skips getConfigSequencer and getPatternList; the periodic refresh
        will pick those up shortly."""
        try:
            settings = pb.getConfigSettings()
            self._set(
                ip,
                name=settings.get("name") or "",
                ver=str(settings.get("ver") or ""),
                pixel_count=settings.get("pixelCount"),
                brightness=settings.get("brightness"),
            )
        except Exception:
            pass

    def _refresh_config(self, pb: Pixelblaze, ip: str):
        try:
            info = _fetch_device_config(pb, ip=ip, include_patterns=True)
        except Exception:
            return
        active_id = info.get("activePatternId", "") or ""
        patterns = info.get("patterns") or {}
        active_name = patterns.get(active_id, "") or info.get("activePatternName", "") or ""

        settings = info.get("settings") or {}
        sequencer = info.get("sequencer") or {}
        playlist = sequencer.get("playlist") or {}
        playlist_items = playlist.get("items") or []
        plist_size = len(playlist_items) if playlist_items else None
        plist_position = playlist.get("position")
        plist_index = int(plist_position) if isinstance(plist_position, int) else None

        # Detect pattern change so we can track "time left" for playlist mode.
        with self._lock:
            row = self._rows.get(ip)
            prev_id = row.active_pattern_id if row else ""
        pattern_change_kwargs = {}
        if active_id and active_id != prev_id:
            pattern_change_kwargs["pattern_started_at"] = time.monotonic()

        self._set(
            ip,
            name=info.get("name") or "",
            ver=str(info.get("ver") or ""),
            pixel_count=info.get("pixelCount"),
            brightness=info.get("brightness"),
            active_pattern_id=active_id,
            active_pattern_name=active_name,
            brand=settings.get("brandName") or "",
            led_type=settings.get("ledType"),
            data_speed=settings.get("dataSpeed"),
            color_order=str(settings.get("colorOrder") or ""),
            max_brightness=settings.get("maxBrightness"),
            cpu_speed=str(settings.get("cpuSpeed") or ""),
            power_save=settings.get("networkPowerSave"),
            discovery=settings.get("discoveryEnable"),
            timezone=str(settings.get("timezone") or ""),
            auto_off_enable=settings.get("autoOffEnable"),
            auto_off_start=str(settings.get("autoOffStart") or ""),
            auto_off_end=str(settings.get("autoOffEnd") or ""),
            simple_ui=settings.get("simpleUiMode"),
            learning_ui=settings.get("learningUiMode"),
            sensor_input=settings.get("sensorInputSource"),
            seq_mode=sequencer.get("sequencerMode"),
            seq_state=sequencer.get("runSequencer"),
            seq_shuffle_ms=sequencer.get("ms"),
            plist_index=plist_index,
            plist_size=plist_size,
            **pattern_change_kwargs,
        )
        # Also push the fresh info into the shared JSON cache so `pb find`
        # and friends immediately benefit.
        try:
            update_device_cache([info])
        except Exception:
            pass

    def rediscover_loop(self, timeout_ms: int):
        """Background: periodically re-enumerate to pick up devices that
        rejoined the network at a new IP or came online after startup.

        Runs one sweep immediately (so `pb top` doesn't start with an empty
        table when there's nothing cached) and then on a fixed interval.

        Workers are spawned via `on_ip` the instant each beacon lands —
        we don't wait for the sweep to finish. That drops first-row
        latency for a cold cache from ~sweep-duration (ad-hoc probe +
        full beacon timeout + serial peer enrichment) to ~one-beacon-
        interval (usually <1s)."""
        while not self._stop.is_set():
            try:
                # Suppress the enumerate_pixelblazes log spam by swapping
                # stderr briefly — the main loop owns the terminal now.
                _quiet_enumerate(timeout_ms, on_ip=self._ensure_worker)
            except Exception:
                pass
            if self._stop.wait(self._rediscover_seconds):
                return


def _quiet_enumerate(timeout_ms: int, on_ip=None) -> list[dict]:
    """Run enumerate_pixelblazes with stderr silenced (top owns the screen)."""
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        return enumerate_pixelblazes(timeout=timeout_ms, slow=False, on_ip=on_ip)


# ── Rendering ───────────────────────────────────────────────────────────────


def _fmt_bytes(n: Optional[int]) -> str:
    if n is None:
        return "-"
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f}K"
    return f"{n / (1024 * 1024):.1f}M"


def _fmt_storage(row: Row) -> str:
    if row.storage_used is None or not row.storage_size:
        return "-"
    used = _fmt_bytes(row.storage_used)
    total = _fmt_bytes(row.storage_size)
    return f"{used}/{total}"


def _fmt_uptime(ms: Optional[int]) -> str:
    # Pixelblaze reports uptime in MILLISECONDS in its stats frames — the
    # raw value ticks up ~1000 per second. Treating it as seconds inflates
    # every reading 1000× (a 35-minute-old device would read as ~24 days).
    if ms is None:
        return "-"
    secs = int(ms) // 1000
    m, _ = divmod(secs, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}d{h:02d}h"
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m"
    return f"{secs}s"


def _fmt_fps(row: Row, _now: float) -> str:
    """The smoothed value (see _push_fps), and no decimal above 10.

    A tenth of a frame is below anything anyone acts on, and printing it meant
    a device sitting rock-steady at 131.5-131.7 fps redrew its cell every
    single tick.
    """
    v = row.fps_shown if row.fps_shown is not None else row.fps
    if v is None:
        return "-"
    return f"{v:.0f}" if v >= 10 else f"{v:.1f}"


def _fmt_seen(row: Row, now: float) -> str:
    """How long since this device last said anything — and NOTHING while it is
    saying it often enough not to care.

    This was the single churniest cell on the table: measured on a real fleet
    it changed on 39 of 39 redraws for every healthy device, because the age of
    a once-a-second heartbeat sampled once a second is never the same number
    twice. What it was telling you in that state, STATUS already says with a
    green dot, so the number is worth exactly nothing until it starts growing.
    Held back until the row is no longer `ok`, the same column changes on 1 of
    39 — and that one change is the device actually going quiet.
    """
    if not row.last_seen:
        return "never"
    age = now - row.last_seen
    if age <= HEALTHY_MAX_AGE:
        return "-"
    if age < 60:
        return f"{age:.1f}s"
    m, s = divmod(int(age), 60)
    return f"{m}m{s:02d}s"


def _health(row: Row, now: float) -> tuple[str, str, str]:
    """Returns (status glyph, health label, color name)."""
    age = now - row.last_seen if row.last_seen else 1e9
    if not row.connected and age > STALE_MAX_AGE:
        return "○", "down", "red"
    if age <= HEALTHY_MAX_AGE:
        return "●", "ok", "green"
    if age <= STALE_MAX_AGE:
        return "●", "stale", "yellow"
    return "○", "down", "red"


# ── Column registry ─────────────────────────────────────────────────────────
# A column is a tuple of (header, width, right-aligned?, getter, description).
# The getter receives (row, now_monotonic) and returns the raw string to render.
# `--list-columns` prints the registry with descriptions; `--columns` picks a
# subset by key; `--all` selects everything in registry insertion order.
# ────────────────────────────────────────────────────────────────────────────


@dataclass
class ColumnSpec:
    key: str
    header: str
    width: int
    right: bool
    get: Callable[["Row", float], str]
    desc: str
    group: str = "core"


# ── Cell formatters ─────────────────────────────────────────────────────────


LED_TYPE_NAMES = {
    0: "none", 1: "APA102", 2: "WS2812", 3: "WS2801", 4: "buf2812", 5: "OutExp",
}


def _fmt_bool(v: Optional[bool], t: str = "yes", f: str = "no") -> str:
    if v is None:
        return "-"
    return t if v else f


def _fmt_int(v: Optional[int]) -> str:
    return "-" if v is None else str(v)


def _fmt_hz(v: Optional[int]) -> str:
    if v is None:
        return "-"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.0f}k"
    return str(v)


SEQ_MODE_NAMES = {0: "off", 1: "shuffle", 2: "playlist"}


def _fmt_seq_mode(row: "Row", _now: float) -> str:
    if row.seq_mode is None:
        return "-"
    return SEQ_MODE_NAMES.get(row.seq_mode, str(row.seq_mode))


def _fmt_seq_state(row: "Row", _now: float) -> str:
    if row.seq_state is None:
        return "-"
    return "play" if row.seq_state else "pause"


def _fmt_playlist_pos(row: "Row", _now: float) -> str:
    if row.plist_size is None:
        return "-"
    idx = row.plist_index if row.plist_index is not None else 0
    return f"{idx + 1}/{row.plist_size}"


def _fmt_shuffle(row: "Row", _now: float) -> str:
    if row.seq_shuffle_ms is None:
        return "-"
    ms = int(row.seq_shuffle_ms)
    if ms >= 60_000:
        return f"{ms // 60_000}m{(ms % 60_000) // 1000:02d}s"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms}ms"


def _fmt_playlist_left(row: "Row", now: float) -> str:
    # Only meaningful if sequencer is running with a known per-item duration
    # and we've seen the pattern start (either via pattern_started_at or the
    # first observation).
    if not row.seq_state or row.seq_shuffle_ms is None or not row.pattern_started_at:
        return "-"
    total = row.seq_shuffle_ms / 1000.0
    elapsed = now - row.pattern_started_at
    remaining = max(0.0, total - elapsed)
    if remaining >= 60:
        m, s = divmod(int(remaining), 60)
        return f"{m}m{s:02d}s"
    if remaining >= 10:
        return f"{remaining:.0f}s"
    return f"{remaining:.1f}s"


def _fmt_auto_off(row: "Row", _now: float) -> str:
    if row.auto_off_enable is None:
        return "-"
    if not row.auto_off_enable:
        return "off"
    s = row.auto_off_start or "??:??"
    e = row.auto_off_end or "??:??"
    return f"{s}-{e}"


def _fmt_sensor(row: "Row", _now: float) -> str:
    if row.sensor_input is None:
        return "-"
    return "expansion" if row.sensor_input else "mic"


def _fmt_pattern(row: "Row", _now: float) -> str:
    return row.active_pattern_name or (row.active_pattern_id[:12] if row.active_pattern_id else "-")


def _fmt_bright(row: "Row", _now: float) -> str:
    return f"{int(row.brightness * 100)}%" if row.brightness is not None else "-"


def _fmt_maxbright(row: "Row", _now: float) -> str:
    return f"{row.max_brightness}%" if row.max_brightness is not None else "-"


def _fmt_led_type(row: "Row", _now: float) -> str:
    if row.led_type is None:
        return "-"
    return LED_TYPE_NAMES.get(row.led_type, f"t{row.led_type}")


def _fmt_status(row: "Row", now: float) -> str:
    glyph, label, _ = _health(row, now)
    return f"{glyph} {label}"


def _register_columns() -> "dict[str, ColumnSpec]":
    specs: list[ColumnSpec] = [
        # ── Core (default set — matches the pre-registry table) ────────────
        ColumnSpec("status",   "STATUS",   7, False, _fmt_status,
                   "Health glyph + label", "core"),
        ColumnSpec("name",     "NAME",    15, False, lambda r, _: r.name or "-",
                   "Device name", "core"),
        ColumnSpec("ip",       "IP",      15, False, lambda r, _: r.ip,
                   "IP address", "core"),
        ColumnSpec("fps",      "FPS",      5, True, _fmt_fps,
                   "Frames per second (from live stats stream)", "core"),
        ColumnSpec("pattern",  "PATTERN", 20, False, _fmt_pattern,
                   "Active pattern name (falls back to id prefix)", "core"),
        ColumnSpec("pixels",   "PIXELS",   6, True,
                   lambda r, _: _fmt_int(r.pixel_count),
                   "Configured pixel count", "core"),
        ColumnSpec("bright",   "BRIGHT",   6, True, _fmt_bright,
                   "Brightness slider position (0-100%)", "core"),
        ColumnSpec("storage",  "STORAGE", 12, False, lambda r, _: _fmt_storage(r),
                   "Flash storage used/total", "core"),
        ColumnSpec("mem",      "MEM",      5, True, lambda r, _: _fmt_bytes(r.mem),
                   "Free memory", "core"),
        ColumnSpec("uptime",   "UPTIME",   7, True, lambda r, _: _fmt_uptime(r.uptime_ms),
                   "Uptime since boot", "core"),
        ColumnSpec("ver",      "VER",      4, True, lambda r, _: r.ver or "-",
                   "Firmware version", "core"),
        ColumnSpec("seen",     "SEEN",     6, True, lambda r, now: _fmt_seen(r, now),
                   "Age of the most recent successful poll", "core"),

        # ── Configuration ─────────────────────────────────────────────────
        ColumnSpec("brand",     "BRAND",     10, False, lambda r, _: r.brand or "-",
                   "Brand name (for OEM-rebranded firmware)", "config"),
        ColumnSpec("patternid", "PATTERN-ID", 22, False,
                   lambda r, _: r.active_pattern_id or "-",
                   "Full pattern id (useful for scripting)", "config"),
        ColumnSpec("ledtype",   "LEDTYPE",    8, False, _fmt_led_type,
                   "LED type (WS2812, APA102, OutExp, …)", "config"),
        ColumnSpec("dataspeed", "DATASPEED",  9, True,
                   lambda r, _: _fmt_hz(r.data_speed),
                   "LED data rate (Hz)", "config"),
        ColumnSpec("colororder", "COLORORDER", 10, False, lambda r, _: r.color_order or "-",
                   "Color order (RGB, GRB, RGBW, …)", "config"),
        ColumnSpec("maxbright", "MAXBRIGHT",  9, True, _fmt_maxbright,
                   "Hard brightness ceiling (0-100%)", "config"),
        ColumnSpec("cpu",       "CPU",        4, True, lambda r, _: r.cpu_speed or "-",
                   "CPU clock (MHz, v3-only)", "config"),
        ColumnSpec("powersave", "PWRSAVE",    7, False,
                   lambda r, _: _fmt_bool(r.power_save, "on", "off"),
                   "Wi-Fi power-save mode", "config"),
        ColumnSpec("discovery", "DISCOVERY",  9, False,
                   lambda r, _: _fmt_bool(r.discovery, "on", "off"),
                   "Electromage discovery + time sync", "config"),
        ColumnSpec("timezone",  "TZ",        18, False, lambda r, _: r.timezone or "-",
                   "Configured timezone", "config"),
        ColumnSpec("autooff",   "AUTOOFF",   13, False, _fmt_auto_off,
                   "Auto-off window (or 'off')", "config"),
        ColumnSpec("simpleui",  "SIMPLEUI",   8, False,
                   lambda r, _: _fmt_bool(r.simple_ui, "on", "off"),
                   "Simple UI mode", "config"),
        ColumnSpec("learning",  "LEARNING",   8, False,
                   lambda r, _: _fmt_bool(r.learning_ui, "on", "off"),
                   "Learning UI mode", "config"),
        ColumnSpec("sensor",    "SENSOR",     9, False, _fmt_sensor,
                   "Sensor input source (mic/expansion)", "config"),

        # ── Sequencer / playlist ─────────────────────────────────────────
        ColumnSpec("seqmode",   "SEQMODE",    8, False, _fmt_seq_mode,
                   "off / shuffle / playlist", "sequencer"),
        ColumnSpec("seqstate",  "SEQSTATE",   8, False, _fmt_seq_state,
                   "Sequencer play/pause", "sequencer"),
        ColumnSpec("shuffle",   "SHUFFLE",    8, True, _fmt_shuffle,
                   "Per-item shuffle duration", "sequencer"),
        ColumnSpec("plpos",     "PL#",        7, True, _fmt_playlist_pos,
                   "Playlist index/total (playlist mode)", "sequencer"),
        ColumnSpec("plleft",    "PLLEFT",     8, True, _fmt_playlist_left,
                   "Approx time left in current pattern (playing sequencer)", "sequencer"),
    ]
    return {s.key: s for s in specs}


COLUMN_SPECS: "dict[str, ColumnSpec]" = _register_columns()
DEFAULT_COLUMN_KEYS: list[str] = [
    "status", "name", "ip", "fps", "pattern", "pixels", "bright",
    "storage", "mem", "uptime", "ver", "seen",
]

# Ordered most-likely-to-change-first, so `pb top --all` puts the busy stuff
# at the left of the table where it's easiest to scan. Identity anchors
# (status/name/ip) come first only because you need them to read any row;
# after that, columns cascade from "updates every stats frame" down through
# "changes when user reconfigures" and finally "essentially static".
ALL_COLUMN_KEYS: list[str] = [
    # Anchors — needed to read each row
    "status", "name", "ip",
    # Live stats — refreshed on every {"fps":...} frame the PB pushes
    "fps", "seen", "uptime", "mem",
    # Pattern / sequencer runtime state — flips on shuffle / playlist / UI
    "pattern", "plleft", "bright", "plpos", "seqstate", "seqmode", "shuffle",
    # Slowly-growing / semi-static
    "storage", "patternid",
    # LED hardware config (basically only when you reconfigure)
    "pixels", "ledtype", "colororder", "dataspeed", "maxbright", "cpu",
    # Firmware / branding
    "ver", "brand",
    # Input source + power / UI / scheduling (least dynamic)
    "sensor", "powersave", "discovery", "autooff", "timezone",
    "simpleui", "learning",
]
# Sanity check at import: any registered column missing from --all is a bug.
assert set(ALL_COLUMN_KEYS) == set(COLUMN_SPECS), (
    f"ALL_COLUMN_KEYS out of sync with registry: "
    f"missing={set(COLUMN_SPECS) - set(ALL_COLUMN_KEYS)}, "
    f"extra={set(ALL_COLUMN_KEYS) - set(COLUMN_SPECS)}"
)


def _resolve_columns(all_flag: bool, columns_csv: Optional[str]) -> list[ColumnSpec]:
    """Turn the CLI flags into an ordered list of ColumnSpec.
    Precedence: --columns > --all > default. Unknown keys raise ClickException."""
    if columns_csv:
        keys = [k.strip().lower() for k in columns_csv.split(",") if k.strip()]
        unknown = [k for k in keys if k not in COLUMN_SPECS]
        if unknown:
            raise click.ClickException(
                f"Unknown column(s): {', '.join(unknown)}. "
                f"Run `pb top --list-columns` to see available columns."
            )
        return [COLUMN_SPECS[k] for k in keys]
    if all_flag:
        return [COLUMN_SPECS[k] for k in ALL_COLUMN_KEYS]
    return [COLUMN_SPECS[k] for k in DEFAULT_COLUMN_KEYS]


def _print_column_registry():
    """Print the column registry to stdout, grouped by section."""
    groups: "dict[str, list[ColumnSpec]]" = {}
    for spec in COLUMN_SPECS.values():
        groups.setdefault(spec.group, []).append(spec)
    order = ["core", "config", "sequencer"]
    click.echo("Available columns (use with --columns c1,c2,...  or  --all):")
    for group in order:
        specs = groups.get(group, [])
        if not specs:
            continue
        click.echo(f"\n  {group.title()}:")
        for s in specs:
            marker = "*" if s.key in DEFAULT_COLUMN_KEYS else " "
            click.echo(f"    {marker} {s.key:<12} {s.desc}")
    click.echo("\n  (* = shown by default)")
    click.echo(
        "\nNot yet available: preview-frame metrics (e.g. count of lit pixels,"
        "\n  average color) — would require enabling binary preview frames, which"
        "\n  adds ~30 KB/s per device to keep those frames streaming. Similarly,"
        "\n  per-pattern sensor readings (audio bins, accelerometer) live inside"
        "\n  pattern-exported variables and require an extra RPC per refresh."
    )


def _pad(s: str, width: int, right: bool) -> str:
    if len(s) > width:
        s = s[: max(0, width - 1)] + "…"
    return s.rjust(width) if right else s.ljust(width)


def _fit_columns(term_width: int, columns: list[ColumnSpec]) -> list[ColumnSpec]:
    """Return the prefix of `columns` whose full-width layout fits in
    `term_width`. Guarantees we never truncate mid-column, so we never
    show half a value like `1` for a SEEN of `1.2s`."""
    sep_width = 2  # matches "  ".join(...) in _render
    picked: list[ColumnSpec] = []
    used = 0
    for spec in columns:
        add = spec.width + (sep_width if picked else 0)
        if used + add > term_width:
            break
        picked.append(spec)
        used += add
    # If even the first column can't fit (weirdly narrow terminal), still
    # show something rather than nothing.
    return picked or [columns[0]]


def _render(rows: list[Row], color: bool, sort_key: str,
            active_only: bool = False,
            columns: Optional[list[ColumnSpec]] = None,
            truncate_to_terminal: bool = True) -> str:
    """Render rows to a string frame.

    truncate_to_terminal=True (live-tty mode): drop trailing columns that don't
    fit the current terminal width, so the table never wraps.
    truncate_to_terminal=False (piped / --once mode): render the full column
    set at its natural width — `pb top --all | less -S` should show everything.
    """
    if columns is None:
        columns = [COLUMN_SPECS[k] for k in DEFAULT_COLUMN_KEYS]
    now = time.monotonic()

    # Health rank: ok=0, stale=1, down=2. Used to pin live devices to the
    # top of the table, both as the default sort and as a secondary key on
    # every other sort — a dead row shouldn't leapfrog a live one just
    # because its name happens to be alphabetically earlier.
    health_rank = {"ok": 0, "stale": 1, "down": 2}
    def _health_key(r: Row) -> int:
        return health_rank[_health(r, now)[1]]

    hidden = 0
    if active_only:
        kept = [r for r in rows if _health(r, now)[1] != "down"]
        hidden = len(rows) - len(kept)
        rows = kept

    def _name_key(r: Row) -> str:
        return (r.name or "~").lower()

    def sort_val(r: Row):
        if sort_key == "fps":
            # The value on screen, not the raw one — `--sort fps` on the raw
            # readings reshuffles rows on noise the column no longer shows.
            return (_health_key(r), -(r.fps_shown if r.fps_shown is not None else (r.fps or 0)),
                    _name_key(r))
        if sort_key == "ip":
            octets = tuple(int(p) if p.isdigit() else 0 for p in r.ip.split("."))
            return (_health_key(r), octets)
        if sort_key == "pattern":
            return (_health_key(r), (r.active_pattern_name or "~").lower(), _name_key(r))
        if sort_key == "name":
            return (_health_key(r), _name_key(r))
        # Default "active": actives at the top, then alphabetical by name.
        return (_health_key(r), _name_key(r))

    rows = sorted(rows, key=sort_val)

    term_width = shutil.get_terminal_size((120, 40)).columns
    if truncate_to_terminal:
        columns = _fit_columns(term_width, columns)
    lines = []
    if not rows:
        empty_msg = (
            "no active devices"
            if active_only and hidden
            else "waiting for discovery… (nothing cached)"
        )
        lines.append(_c(
            " pb top  " + time.strftime("%H:%M:%S")
            + f"   {empty_msg}"
            + (f"  (hidden: {hidden} down)" if hidden else "")
            + CLEAR_LINE_END, "grey", color))
        lines.append(_c("  (q or ^C to quit)", "grey", color) + CLEAR_LINE_END)
        return "\n".join(lines)

    # Header line.
    total = len(rows)
    up = sum(1 for r in rows if _health(r, now)[1] == "ok")
    stale = sum(1 for r in rows if _health(r, now)[1] == "stale")
    down = total - up - stale
    ts = time.strftime("%H:%M:%S")
    banner = (
        f" pb top  {ts}   devices: {total}  "
        f"{_c(f'up {up}', 'green', color)}  "
        f"{_c(f'stale {stale}', 'yellow', color)}  "
        f"{_c(f'down {down}', 'red', color)}"
    )
    if active_only and hidden:
        banner += _c(f"  (hidden: {hidden} down)", "grey", color)
    lines.append(_c(banner + CLEAR_LINE_END, None, color))
    lines.append("")

    # Column headers.
    header = "  ".join(_pad(spec.header, spec.width, spec.right) for spec in columns)
    lines.append(_c(header, "grey", color))
    lines.append(_c("─" * len(header), "grey", color))

    for row in rows:
        _, label, color_name = _health(row, now)
        line = "  ".join(
            _pad(spec.get(row, now), spec.width, spec.right) for spec in columns
        )
        # Color the whole row by status color (down = red, stale = yellow, ok = default).
        row_color = None if label == "ok" else color_name
        lines.append(_c(line, row_color, color) + CLEAR_LINE_END)

        if row.error and label != "ok":
            err_text = f"    ↳ {row.error}"
            if len(err_text) > term_width:
                err_text = err_text[: max(0, term_width - 1)] + "…"
            lines.append(_c(err_text, "grey", color) + CLEAR_LINE_END)

    lines.append("")
    lines.append(_c("  (q or ^C to quit)", "grey", color) + CLEAR_LINE_END)
    return "\n".join(lines)


# ── Command ────────────────────────────────────────────────────────────────


def register(cli_group):
    """Attach `top` command to the given click group.

    Kept as a function so cli.py can import and register without pulling the
    entire implementation into module import at click's decoration time."""

    @cli_group.command()
    @click.option("--interval", "-n", type=float, default=1.0, show_default=True,
                  help="Redraw interval in seconds.")
    @click.option("--once", is_flag=True,
                  help="Do a single discovery + render pass, then exit (scripting mode).")
    @click.option("--rediscover", "-r", type=float, default=30.0, show_default=True,
                  help="Re-run beacon discovery every N seconds to pick up new devices.")
    @click.option("--scan-timeout", type=int, default=2000, show_default=True,
                  help="Beacon listen timeout for each discovery round (ms).")
    @click.option("--sort", "sort_key",
                  type=click.Choice(["active", "name", "ip", "fps", "pattern"]),
                  default="active", show_default=True,
                  help="Sort rows. Every option pins active devices above stale/down; "
                       "`active` (default) then breaks ties by name.")
    @click.option("--active", "-a", "active_only", is_flag=True,
                  help="Only show devices currently responding (hides `down` rows). "
                       "Cached devices we've never reached this session are hidden too.")
    @click.option("--no-color", is_flag=True, help="Disable ANSI color output.")
    @click.option("--json", "json_out", is_flag=True,
                  help="Emit JSON to stdout instead of the terminal table. "
                       "Without --once, streams one JSON array-of-rows per "
                       "--interval tick (ndjson-style, ideal for `| jq -c`). "
                       "With --once, emits a single snapshot and exits. "
                       "JSON always includes every field, regardless of "
                       "--columns / --all (those only affect the text table).")
    @click.option("--all", "all_columns", is_flag=True,
                  help="Show every registered column, ordered by how dynamic "
                       "each field is (busy stuff on the left). Overridden by "
                       "--columns if that is also given.")
    @click.option("--columns", "columns_csv", type=str, default=None,
                  help="Comma-separated column keys to render, in order "
                       "(e.g. `--columns name,ip,fps,seqmode,plleft`). "
                       "Run `pb top --list-columns` to see all keys.")
    @click.option("--list-columns", "list_columns", is_flag=True,
                  help="Print available columns and exit.")
    def top(interval, once, rediscover, scan_timeout, sort_key, active_only,
            no_color, json_out, all_columns, columns_csv, list_columns):
        """
        Realtime dashboard of every Pixelblaze on the network.

        Like Linux `top`, but for Pixelblazes: renders a live table with
        FPS, free storage, active pattern, uptime, and more. Devices that
        drop off the WiFi stay on the table as `down` and pop back to green
        when they rejoin.

        Starts instantly — the initial table is seeded from the on-disk
        device cache (whatever `pb find` / previous CLI calls last saw),
        and a background thread runs beacon discovery on a loop to pick
        up new/moved devices. Rows appear the moment their worker connects.

        \b
        Examples:
            pb top                                    # Live dashboard, 1s redraw
            pb top -n 0.5                             # Faster redraw
            pb top --sort fps                         # Sort by frames-per-second
            pb top --once                             # One snapshot, exit
            pb top --once --json                      # One JSON snapshot, exit
            pb top --json | jq -c '.[] | .name'       # Stream JSON per tick
            pb top --json -n 5                        # Stream JSON every 5s
            pb top -r 10                              # Rediscover every 10s
            pb top --active                           # Hide `down` rows
            pb top --all                              # Every column, busy first
            pb top --all | less -S                    # Wide dump, one screen
            pb top --columns name,ip,fps,seqmode,plleft
            pb top --list-columns                     # Show the column registry
        """
        if list_columns:
            _print_column_registry()
            return

        columns = _resolve_columns(all_columns, columns_csv)
        is_tty = sys.stdout.isatty()
        color = is_tty and not no_color

        # UX guard: `pb top --all | less` should give ONE full-width dump and
        # exit, not a stream of CLEAR_HOME frames that less can't scroll. When
        # stdout isn't a terminal and the user didn't already ask for --json
        # or --once, treat it as a one-shot snapshot.
        if not is_tty and not json_out and not once:
            once = True

        def _wait_for_first_stats(monitor: TopMonitor, budget_s: float):
            """Block up to `budget_s` for every seeded row to produce a stats
            frame. Uses fps-is-not-None (real stats push) as the settle signal
            — not `last_seen`, because that's now set on WS-connect too and
            would return immediately with an empty stats block."""
            deadline = time.monotonic() + budget_s
            while time.monotonic() < deadline:
                snap = monitor.snapshot()
                if snap and all(r.fps is not None for r in snap):
                    return
                time.sleep(0.1)

        def _filter_active(snap: list[Row]) -> list[Row]:
            if not active_only:
                return snap
            _now = time.monotonic()
            return [r for r in snap if _health(r, _now)[1] != "down"]

        if once:
            # One-shot: blocking discovery so the exit snapshot reflects the
            # current LAN, not just cached IPs.
            log("Discovering Pixelblazes…")
            initial = enumerate_pixelblazes(timeout=scan_timeout, slow=False)
            if not initial:
                raise click.ClickException("No Pixelblazes found on the network.")
            monitor = TopMonitor(initial, rediscover_seconds=rediscover)
            _wait_for_first_stats(monitor, budget_s=6.0)
            snap = _filter_active(monitor.snapshot())
            monitor.stop()
            if json_out:
                click.echo(json.dumps([_row_to_dict(r) for r in snap], separators=(",", ":")))
            else:
                # No column truncation when piped / one-shot — the user
                # explicitly asked for what they asked for.
                click.echo(_render(snap, color=color, sort_key=sort_key,
                                    columns=columns, truncate_to_terminal=is_tty))
            return

        # Live mode: seed from on-disk cache so the table (or JSON) draws
        # instantly, then let the rediscovery thread find/update everything
        # else in the background.
        cached = _read_cache().get("devices", {}) or {}
        seed = list(cached.values())
        monitor = TopMonitor(seed, rediscover_seconds=rediscover)

        threading.Thread(
            target=monitor.rediscover_loop, args=(scan_timeout,),
            daemon=True, name="pb-top-rediscover",
        ).start()

        # SIGINT / SIGTERM → clean exit that still runs the finally block
        # below, so we always restore the cursor before returning.
        #
        # The handler also re-arms SIG_DFL on its way out, so a *second*
        # interrupt is a hard kill. That matters more than it looks: the
        # render loop is not the only thing that can keep this process
        # alive. Discovery runs its tasks on a ThreadPoolExecutor, whose
        # threads are non-daemon and are joined by an atexit hook — so one
        # task blocked in a socket read wedges interpreter *finalization*,
        # long after the loop and the finally block are done. Ctrl-C then
        # goes to a handler that only sets a flag nobody is reading any
        # more, and the only way out is SIGKILL from another terminal.
        # (`pb top` hung exactly this way; see _open()'s handshake timeout
        # for the specific blocking call that caused it.) With SIG_DFL
        # armed, a second Ctrl-C always ends the process.
        stop_flag = {"stop": False}
        cursor_hidden = {"yes": False}

        def handle_signal(_signum, _frame):
            stop_flag["stop"] = True
            # Put the cursor back now, not in the finally — a force-quit
            # may never reach the finally, and an invisible cursor in the
            # user's shell outlives this process.
            if cursor_hidden["yes"]:
                sys.stdout.write(SHOW_CURSOR)
                sys.stdout.flush()
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        if json_out:
            # Streaming JSON: one array-per-tick, ndjson-style. No terminal
            # escape codes, no cursor hiding — this stream is meant to be
            # consumed by `jq`, not eyeballed.
            try:
                while not stop_flag["stop"]:
                    snap = _filter_active(monitor.snapshot())
                    click.echo(json.dumps([_row_to_dict(r) for r in snap],
                                          separators=(",", ":")))
                    sys.stdout.flush()
                    time.sleep(interval)
            finally:
                monitor.stop()
            return

        # Live TTY render loop.
        if color:
            sys.stdout.write(HIDE_CURSOR)
            sys.stdout.flush()
            cursor_hidden["yes"] = True

        try:
            while not stop_flag["stop"]:
                frame = _render(monitor.snapshot(), color=color, sort_key=sort_key,
                                active_only=active_only, columns=columns)
                sys.stdout.write(CLEAR_HOME + frame)
                sys.stdout.flush()
                time.sleep(interval)
        finally:
            monitor.stop()
            if cursor_hidden["yes"]:
                sys.stdout.write(SHOW_CURSOR + "\n")
                sys.stdout.flush()
                cursor_hidden["yes"] = False

    return top


def _row_to_dict(r: Row) -> dict:
    return {
        "ip": r.ip,
        "name": r.name,
        "ver": r.ver,
        "pixelCount": r.pixel_count,
        "brightness": r.brightness,
        "activePatternId": r.active_pattern_id,
        "activePatternName": r.active_pattern_name,
        "fps": r.fps,
        "mem": r.mem,
        "storageUsed": r.storage_used,
        "storageSize": r.storage_size,
        "uptimeMs": r.uptime_ms,
        "lastSeenMonotonic": r.last_seen,
        "connected": r.connected,
        "error": r.error,
        # Extended fields (populated once _refresh_config has run at least once).
        "brandName": r.brand,
        "ledType": r.led_type,
        "dataSpeed": r.data_speed,
        "colorOrder": r.color_order,
        "maxBrightness": r.max_brightness,
        "cpuSpeed": r.cpu_speed,
        "networkPowerSave": r.power_save,
        "discoveryEnable": r.discovery,
        "timezone": r.timezone,
        "autoOffEnable": r.auto_off_enable,
        "autoOffStart": r.auto_off_start,
        "autoOffEnd": r.auto_off_end,
        "simpleUiMode": r.simple_ui,
        "learningUiMode": r.learning_ui,
        "sensorInputSource": r.sensor_input,
        "sequencerMode": r.seq_mode,
        "sequencerState": r.seq_state,
        "sequencerShuffleMs": r.seq_shuffle_ms,
        "playlistIndex": r.plist_index,
        "playlistSize": r.plist_size,
    }
