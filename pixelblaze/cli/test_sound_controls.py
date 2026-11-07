#!/usr/bin/env python3
"""Unit tests for steering `pb sensor sound` from the keyboard.

Keys are dispatched by name, so none of this needs a terminal -- or a
Pixelblaze, or audio hardware. What it does need to be sure of is that a key
means the same thing here as the help says it does, and that keys which cannot
mean anything for a run are neither offered nor acted on.

    python3 -m pytest pixelblaze/cli/test_sound_controls.py
"""

import pytest

from pixelblaze.cli.controls import (AGC_TARGET_RANGE, GAIN_RANGE, GAIN_STEP,
                                     GATE_FLOOR, SEEK_STEPS, Controls, keymap)


class FakeSource:
    """A file source, as far as the transport keys can tell."""

    def __init__(self, duration=180.0, tracks=3):
        self.paused = False
        self.loop = True
        self.position = 30.0
        self.seeks = []
        self.moves = []

    def toggle_pause(self):
        self.paused = not self.paused
        return self.paused

    def seek(self, delta):
        self.seeks.append(delta)
        self.position = max(0.0, self.position + delta)

    def move_track(self, delta):
        self.moves.append(delta)


class FakeMonitor:
    muted = False


class FakeBridge:
    """The handful of attributes the keys turn."""

    def __init__(self, file=False, tracks=1, monitor=None):
        self.gain = 2.0
        self.agc = False
        self.agc_target = 0.15
        self.noise_gate = 0.0
        self.log_scale = False
        self.loop = True
        self.monitor = monitor
        self.samples = [0] if file else None
        self.playlist = FakePlaylist(tracks) if file and tracks > 1 else None
        self.source = FakeSource() if file else None
        self.stopped = False

    def stop(self):
        self.stopped = True


class FakePlaylist:
    def __init__(self, count):
        self.count = count
        self.index = 0
        self.title = "track.mp3"


class Recorder:
    """A display that keeps what it was told, in place of drawing it."""

    draws_help = False

    def __init__(self, draws_help=False):
        self.draws_help = draws_help
        self.messages = []
        self.logs = []
        self.help_lines = None

    def notify(self, message):
        self.messages.append(message)

    def log(self, line):
        self.logs.append(line)


def controls(file=False, tracks=1, monitor=None, on_rebind=None, display=None):
    bridge = FakeBridge(file=file, tracks=tracks, monitor=monitor)
    return Controls(bridge, display=display or Recorder(), reader=NoKeyboard(),
                    on_rebind=on_rebind)


class NoKeyboard:
    active = False
    available = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def poll(self):
        return []


# ── which keys a run is offered ─────────────────────────────────────────────

def test_a_capture_is_not_offered_transport_it_does_not_have():
    """There is no cursor to move in a microphone."""
    live = controls()
    offered = {key for binding in live.active_bindings for key in binding.keys}

    assert 'space' not in offered and 'left' not in offered and 'up' not in offered
    assert {'-', '+', 'a', 'l', 'q'} <= offered, "the knobs still apply"
    assert live.press('space') is None, "and pressing it anyway does nothing"
    assert 'space' not in live.hint()


def test_a_file_is_offered_the_transport_and_the_knobs_both():
    file = controls(file=True, tracks=4)
    offered = {key for binding in file.active_bindings for key in binding.keys}

    assert {'space', 'left', 'right', 'up', 'down', 'L'} <= offered
    assert {'-', '+', 'a', '[', ']', 'l', 'n', 'N', '0'} <= offered
    assert 'space pause' in file.hint() and '↑↓ track' in file.hint()


def test_one_track_is_not_offered_keys_for_moving_between_tracks():
    one = controls(file=True, tracks=1)
    assert one.press('down') is None
    assert '↑↓' not in one.hint()

    several = controls(file=True, tracks=2)
    assert several.press('down') == "next track"


def test_keys_that_need_something_this_run_lacks_are_hidden():
    assert controls(file=True).press('m') is None, "nothing is being played out loud"
    assert controls(file=True, monitor=FakeMonitor()).press('m').startswith("muted")

    assert controls().press('r') is None, "no transport that can rebind"
    calls = []
    assert controls(on_rebind=lambda: calls.append(1)).press('r')
    assert calls == [1]


def test_the_help_lists_what_applies_and_skips_the_aliases():
    """`shift+left` is dispatched but not listed -- the arrow row explains it."""
    listed = controls(file=True, tracks=2).help_lines()
    keys = [row[0] for row in listed]

    assert all(label for _, label in listed), "a listed key with no description"
    assert 'left / right' in keys
    assert not any('shift+left' in row for row in keys)
    assert '- / +' in keys, "the row names the key you press, not its shifted twin"

    live = [row[0] for row in controls().help_lines()]
    assert 'space' not in live and 'a' in live


def test_no_key_is_bound_twice():
    """A second binding for a key is unreachable, and the symptom is a key that
    silently does the wrong thing."""
    seen = set()
    for binding in keymap():
        for key in binding.keys:
            assert key not in seen, f"{key!r} is bound twice"
            seen.add(key)


def test_an_unknown_key_is_ignored_rather_than_an_error():
    """Terminals send things nobody typed."""
    live = controls()
    assert live.press('csi?1000h') is None
    assert live.press('f7') is None
    assert live.press('Z') is None


# ── transport ───────────────────────────────────────────────────────────────

def test_space_pauses_and_says_that_the_lights_go_quiet_too():
    file = controls(file=True)
    assert "paused" in file.press('space')
    assert file.bridge.source.paused
    assert file.press('space') == "playing"
    assert not file.bridge.source.paused


def test_the_arrows_seek_and_the_modifier_decides_how_far():
    file = controls(file=True)

    file.press('right')
    file.press('left')
    file.press('shift+right')
    file.press('shift+left')
    file.press('alt+right')
    file.press('ctrl+left')

    assert file.bridge.source.seeks == [
        SEEK_STEPS[''], -SEEK_STEPS[''],
        SEEK_STEPS['shift'], -SEEK_STEPS['shift'],
        SEEK_STEPS['alt'], -SEEK_STEPS['ctrl'],
    ]
    assert SEEK_STEPS['shift'] > SEEK_STEPS[''] > SEEK_STEPS['alt']


def test_up_and_down_move_through_the_playlist():
    file = controls(file=True, tracks=5)
    assert file.press('down') == "next track"
    assert file.press('up') == "previous track"
    assert file.bridge.source.moves == [1, -1]


def test_loop_can_be_turned_off_mid_track():
    file = controls(file=True)
    assert file.press('L') == "loop off"
    assert file.bridge.source.loop is False and file.bridge.loop is False
    assert file.press('L') == "loop on"


# ── the knobs ───────────────────────────────────────────────────────────────

def test_gain_steps_multiplicatively_and_comes_back_to_where_it_started():
    live = controls()
    start = live.bridge.gain

    live.press('+')
    assert live.bridge.gain == pytest.approx(start * GAIN_STEP)
    live.press('-')
    assert live.bridge.gain == pytest.approx(start)

    live.press('=')                       # the same key, shifted
    assert live.bridge.gain == pytest.approx(start * GAIN_STEP)
    live.press('_')
    assert live.bridge.gain == pytest.approx(start)

    for _ in range(10):
        live.press('+')
    assert live.bridge.gain > start
    assert live.press('0') == f"gain ×{start:.3g} (back to --gain)"
    assert live.bridge.gain == start


def test_gain_cannot_be_turned_past_where_it_stops_meaning_anything():
    live = controls()
    for _ in range(60):
        live.press('+')
    assert live.bridge.gain == GAIN_RANGE[1]
    for _ in range(120):
        live.press('-')
    assert live.bridge.gain == GAIN_RANGE[0]


def test_turning_the_gain_while_agc_is_on_says_why_it_may_do_nothing():
    """AGC is a gain of its own, and a puzzled user turning a knob that the
    loop immediately undoes is the whole reason to say so."""
    live = controls()
    live.press('a')
    assert "AGC is on" in live.press('+')
    live.press('a')
    assert "AGC is on" not in live.press('+')


def test_agc_and_its_target_can_be_turned_on_and_moved():
    live = controls()
    assert "AGC on" in live.press('a') and live.bridge.agc
    assert "AGC off" in live.press('a') and not live.bridge.agc

    before = live.bridge.agc_target
    live.press(']')
    assert live.bridge.agc_target > before
    live.press('[')
    assert live.bridge.agc_target == pytest.approx(before)

    assert "AGC is off" in live.press('['), "it has no effect until AGC is on"

    for _ in range(40):
        live.press(']')
    assert live.bridge.agc_target == AGC_TARGET_RANGE[1]
    for _ in range(60):
        live.press('[')
    assert live.bridge.agc_target == AGC_TARGET_RANGE[0]


def test_the_noise_gate_steps_up_from_off_and_back_down_to_it():
    """0 does not multiply, so a gate that is off needs somewhere to start."""
    live = controls()
    assert live.bridge.noise_gate == 0

    assert live.press('N') == f"noise gate {GATE_FLOOR:.3g}"
    assert live.bridge.noise_gate == GATE_FLOOR
    live.press('N')
    assert live.bridge.noise_gate == pytest.approx(GATE_FLOOR * 2)

    live.press('n')
    assert live.bridge.noise_gate == pytest.approx(GATE_FLOOR)
    assert live.press('n') == "noise gate off"
    assert live.bridge.noise_gate == 0
    assert live.press('n') == "noise gate off", "and it stays off"


def test_log_scaling_toggles():
    live = controls()
    assert live.press('l') == "log scaling on" and live.bridge.log_scale
    assert live.press('l') == "log scaling off" and not live.bridge.log_scale


def test_mute_keeps_streaming_to_the_lights():
    monitor = FakeMonitor()
    file = controls(file=True, monitor=monitor)

    assert "still streaming" in file.press('m')
    assert monitor.muted
    assert file.press('m') == "unmuted" and not monitor.muted


def test_q_stops_the_run():
    live = controls()
    assert live.press('q') == "stopping"
    assert live.bridge.stopped


# ── saying what it did ──────────────────────────────────────────────────────

def test_every_press_that_does_something_says_so():
    display = Recorder()
    file = controls(file=True, tracks=2, display=display)

    for key in ('space', 'right', 'down', '+', 'a', 'l', 'N'):
        file.press(key)
    assert len(display.messages) == 7, display.messages

    file.press('unbound')
    assert len(display.messages) == 7, "an ignored key says nothing"


def test_help_is_an_overlay_where_there_is_a_frame_to_hold_it():
    display = Recorder(draws_help=True)
    file = controls(file=True, display=display)

    file.press('?')
    assert display.help_lines and file.helping
    file.press('?')
    assert display.help_lines is None and not file.helping


def test_help_is_printed_where_there_is_not():
    """Piped or --quiet: no frame to hold an overlay, so say it once."""
    display = Recorder(draws_help=False)
    live = controls(display=display)

    live.press('h')
    assert display.logs, "nothing was printed"
    assert any('AGC on / off' in line for line in display.logs)
    assert not live.helping, "nothing is holding it open"
