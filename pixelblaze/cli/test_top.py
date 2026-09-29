#!/usr/bin/env python3
"""Tests for `pb top`'s display rules — the ones that decide how much of the
table rewrites itself per second.

No Pixelblaze hardware needed: every rule under test is a pure function of a
Row, which is the point of keeping them that way.

WHY THESE EXIST. `pb top` redraws once a second, and a dashboard that rewrites
half its cells every redraw is unreadable even when every number in it is
correct. Measured on a real fleet (two boards plus the emulator, 40 ticks with
nothing changing about the lights):

    SEEN cell text   39/39 redraws changed it, per healthy device
    FPS cell text    19/37 and 21/37
    error text       flapping between two wordings of one outage, which adds
                     and removes a line and so moves every row beneath it

The numbers in the docstrings below are from that capture.
"""

import time

from pixelblaze.cli.top import (
    Row,
    HEALTHY_MAX_AGE,
    STALE_MAX_AGE,
    _fmt_fps,
    _fmt_seen,
    _health,
    _push_fps,
    _record_failure,
    _row_to_dict,
)


def _row(**kw) -> Row:
    return Row(ip=kw.pop("ip", "192.168.1.34"), **kw)


def _feed(values) -> Row:
    """Push a series of raw readings and return the row."""
    r = _row()
    for v in values:
        _push_fps(r, v)
    return r


def _shown(values) -> list:
    """What the FPS cell reads after each reading in turn."""
    r = _row()
    out = []
    for v in values:
        _push_fps(r, v)
        out.append(_fmt_fps(r, 0.0))
    return out


# ── FPS: reject noise, keep signal ──────────────────────────────────────────

def test_fps_ignores_a_single_sample_dip():
    """131, 131, 131, *81*, 130 — the 81 is one bad sample, not a slowdown."""
    cells = _shown([131.0, 131.0, 131.0, 80.8, 129.6, 131.0])
    assert cells[3] == cells[2], f"the dip leaked into the cell: {cells}"
    assert set(cells) == {"131"}, cells


def test_fps_does_not_flicker_across_a_rounding_boundary():
    """131.5 and 131.7 round to 131 and 132. A steady device must not
    alternate between two cells for ever."""
    cells = _shown([131.5, 131.7, 131.6, 131.7, 131.5, 131.6, 131.7])
    assert len(set(cells)) == 1, f"cell moved on noise: {cells}"


def test_fps_tracks_a_sustained_change():
    """The deadband must not become a freeze: a real move has to land."""
    cells = _shown([131.0] * 4 + [69.0] * 4)
    assert cells[-1] == "69", cells
    # …and within a tick or two of the change, not eventually.
    assert cells[5] == "69", f"took too long to follow: {cells}"


def test_fps_shows_a_high_reading_that_is_real():
    """A board really did report ~2330 fps for a long stretch on the capture
    this was tuned against. Sustained is signal; suppressing it would be
    hiding data, which is not what smoothing is for."""
    cells = _shown([131.0] * 3 + [2330.0, 2330.0, 2334.0, 2331.0, 2330.0])
    assert cells[-1] == "2330", cells


def test_fps_keeps_the_raw_reading_for_json():
    """`--json` is for machines and must not be smoothed."""
    r = _feed([131.0, 131.0, 80.8])
    assert r.fps == 80.8, "raw last reading"
    assert _fmt_fps(r, 0.0) == "131", "but the table shows the smoothed one"
    assert _row_to_dict(r)["fps"] == 80.8


def test_fps_below_ten_keeps_a_decimal():
    """A tenth of a frame is noise at 131 fps and meaningful at 3."""
    assert _fmt_fps(_feed([3.4]), 0.0) == "3.4"
    assert _fmt_fps(_feed([131.0]), 0.0) == "131"


def test_fps_with_no_reading_is_a_dash():
    assert _fmt_fps(_row(), 0.0) == "-"


# ── SEEN: silent while there is nothing to say ──────────────────────────────

def test_seen_is_quiet_while_the_device_is_healthy():
    """The churniest cell on the table. While a row is `ok`, the age of a
    once-a-second heartbeat sampled once a second is never the same number
    twice — and STATUS already says the same thing with a green dot."""
    now = time.monotonic()
    for age in (0.05, 0.4, 1.1, 2.2, HEALTHY_MAX_AGE):
        r = _row(last_seen=now - age, connected=True)
        assert _fmt_seen(r, now) == "-", f"age {age} should print nothing"


def test_seen_speaks_up_the_moment_it_matters():
    now = time.monotonic()
    r = _row(last_seen=now - 6.0, connected=True)
    assert _fmt_seen(r, now) == "6.0s"
    r = _row(last_seen=now - 125.0, connected=False)
    assert _fmt_seen(r, now) == "2m05s"


def test_seen_says_never_when_nothing_was_ever_heard():
    assert _fmt_seen(_row(), time.monotonic()) == "never"


def test_seen_boundary_matches_the_health_boundary():
    """The cell goes quiet exactly while STATUS is green, so the two can never
    disagree about whether a device is fine."""
    now = time.monotonic()
    quiet = _row(last_seen=now - (HEALTHY_MAX_AGE - 0.01), connected=True)
    loud = _row(last_seen=now - (HEALTHY_MAX_AGE + 0.5), connected=True)
    assert _health(quiet, now)[1] == "ok" and _fmt_seen(quiet, now) == "-"
    assert _health(loud, now)[1] == "stale" and _fmt_seen(loud, now) != "-"


# ── The error line, which moves every row below it ──────────────────────────

def test_first_failure_wins_while_the_device_stays_down():
    """One board alternated between `[Errno 64] Host is down` and `timed out`
    — two wordings of one fact. Each change adds or removes the `↳` line and
    shifts every row beneath it."""
    r = _row()
    _record_failure(r, "[Errno 64] Host is down")
    _record_failure(r, "timed out")
    _record_failure(r, "[Errno 64] Host is down")
    assert r.error == "[Errno 64] Host is down"
    assert r.connected is False


def test_a_new_outage_reports_its_own_cause():
    """Holding the first message must not mean holding a stale one for ever:
    recovery clears it, so the next failure explains itself."""
    r = _row()
    _record_failure(r, "timed out")
    r.connected, r.error = True, ""       # what the worker does on reconnect
    _record_failure(r, "[Errno 54] Connection reset by peer")
    assert r.error == "[Errno 54] Connection reset by peer"


# ── Health, unchanged but worth pinning ─────────────────────────────────────

def test_health_thresholds():
    now = time.monotonic()
    assert _health(_row(last_seen=now - 1.0, connected=True), now)[1] == "ok"
    assert _health(_row(last_seen=now - 8.0, connected=True), now)[1] == "stale"
    assert _health(_row(last_seen=now - 60.0, connected=True), now)[1] == "down"
    assert _health(_row(), now)[1] == "down"
    assert STALE_MAX_AGE > HEALTHY_MAX_AGE
