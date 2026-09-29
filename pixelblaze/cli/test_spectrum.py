#!/usr/bin/env python3
"""Unit tests for the live terminal spectrum. No terminal, no audio, no device.

    python3 -m pytest pixelblaze/cli/test_spectrum.py
"""

import math
import re

import pytest

from pixelblaze.cli import spectrum
from pixelblaze.cli.loudness import SILENT, Loudness
from pixelblaze.cli.spectrum import (NONE, PALETTE256, TRUECOLOR, PlainStatus,
                                     QuietStatus, TerminalSpectrum, fit, level,
                                     make_display)

ESCAPE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')


def plain(text: str) -> str:
    return ESCAPE.sub('', text)


@pytest.fixture
def written(monkeypatch):
    """Everything the display would have put on stderr."""
    out = []
    monkeypatch.setattr(spectrum, '_emit', out.append)
    return out


def readings(bins=None, peak_hz=1170.0, energy=0.031):
    return {"frequencyData": bins if bins is not None else [0.0] * 32,
            "energyAverage": energy,
            "maxFrequency": peak_hz,
            "maxFrequencyMagnitude": 0.5}


def test_level_is_the_dbfs_scale_the_browser_meter_uses():
    """Linear magnitudes, drawn logarithmically over -60..0 dB."""
    assert level(1.0) == 1.0                       # full scale
    assert level(0.001) == 0.0                     # -60 dB, the floor
    assert level(0.0) == 0.0
    assert level(-1.0) == 0.0                      # can't happen, mustn't crash
    assert level(0.1) == pytest.approx(2 / 3, abs=1e-9)    # -20 dB
    assert level(4.0) == 1.0, "clamped, not off the top of the plot"


def test_fit_counts_visible_characters_not_escape_sequences():
    """A line wider than the terminal wraps, the redraw then moves up one line
    too few, and the whole picture scrolls away frame by frame."""
    assert fit("abcdef", 3) == "abc\x1b[0m"
    assert fit("abc", 10) == "abc", "short lines are left alone, reset and all"
    coloured = "\x1b[38;5;27mabcdef\x1b[39m"
    assert plain(fit(coloured, 3)) == "abc"
    assert fit(coloured, 99) == coloured


def test_quiet_says_nothing_at_all(written):
    display = QuietStatus()
    display.start()
    display.update(readings())
    display.draw()
    display.finish()
    assert written == []


def test_quiet_still_passes_log_lines_through(written):
    """--quiet is about the meter; discovery still has to be able to talk."""
    QuietStatus().log("+ 192.168.1.5")
    assert written == ["+ 192.168.1.5\n"]


def test_plain_prints_one_line_a_second_with_the_lufs_figures(written):
    display = PlainStatus()
    display.fps = 40
    display.targets = 3
    display.loudness = Loudness(-14.2, -15.0, -14.8)
    display.update(readings(bins=[0.0] * 20 + [0.5] + [0.0] * 11))

    display.draw()
    assert len(written) == 1
    display.draw()
    assert len(written) == 1, "throttled to one line a second"

    line = written[0]
    assert "40 fps" in line
    assert "peak  1170 Hz (bin 20)" in line
    assert "energy 0.0310" in line
    assert "M -14.2 S -15.0 I -14.8 LUFS" in line
    assert "→ 3" in line


def test_plain_says_silent_because_that_is_the_first_question(written):
    display = PlainStatus()
    display.silent = True
    display.update(readings())
    display.draw()
    assert "silent — is anything playing?" in written[0]


def test_plain_holds_off_until_there_is_a_reading(written):
    display = PlainStatus()
    display.draw()
    assert written == []


def test_the_spectrum_draws_a_bar_per_bin_over_a_labelled_axis(written, monkeypatch):
    monkeypatch.setattr(spectrum.shutil, 'get_terminal_size',
                        lambda default=None: __import__('os').terminal_size((120, 24)))
    display = TerminalSpectrum(color=NONE)
    display.fps = 40
    display.targets = 2
    display.loudness = Loudness(-14.2, -15.0, -14.8)
    # One loud bin, at the 1170 Hz centre.
    display.update(readings(bins=[0.0] * 15 + [1.0] + [0.0] * 16))
    display._last_draw -= 1
    display.draw()

    lines = plain("".join(written)).split("\n")
    assert lines[0].strip().startswith("40 fps → 2")
    assert "peak  1170 Hz" in lines[0] and "energy 0.0310" in lines[0]
    assert "M -14.2" in lines[1] and "S -15.0" in lines[1] and "I -14.8" in lines[1]

    plot = [l for l in lines if l.startswith((" " * 5 + "│", "   0 ┤", " -20 ┤", " -40 ┤"))]
    assert len(plot) >= 4
    assert any("█" in l for l in plot), "a full-scale bin reaches the top"
    assert " -60 └" in "\n".join(lines)
    axis = [l for l in lines if l.rstrip().endswith("Hz")][-1]
    for mark in ("50", "100", "1k", "10k"):
        assert mark in axis
    assert axis.rstrip().endswith("10k Hz"), "the unit survives a narrow terminal"



def test_a_full_scale_bin_is_a_tall_bar_and_a_quiet_one_is_not(written, monkeypatch):
    """The whole reason the drawing is logarithmic: at a linear scale a correct
    full-scale sine is a two-cell sliver."""
    monkeypatch.setattr(spectrum.shutil, 'get_terminal_size',
                        lambda default=None: __import__('os').terminal_size((120, 24)))

    def height_of(magnitude):
        display = TerminalSpectrum(color=NONE)
        display.update(readings(bins=[magnitude] * 32))
        display._last_draw -= 1
        display.draw()
        rows = plain("".join(written)).split("\n")
        written.clear()
        return sum(1 for row in rows if "█" in row or "▄" in row or "▂" in row)

    assert height_of(1.0) > height_of(0.03) > height_of(0.0015)


def test_the_bars_never_out_run_the_terminal(written, monkeypatch):
    """Narrow, and odd-sized, because that is when the arithmetic goes wrong."""
    for columns, rows in ((40, 10), (60, 24), (200, 60), (33, 9)):
        monkeypatch.setattr(spectrum.shutil, 'get_terminal_size',
                            lambda default=None, c=columns, r=rows: __import__('os').terminal_size((c, r)))
        written.clear()
        display = TerminalSpectrum(color=TRUECOLOR)
        display.update(readings(bins=[0.5] * 32))
        display._last_draw -= 1
        display.draw()
        for line in plain("".join(written)).split("\n"):
            assert len(line) <= columns - 1, f"{columns}x{rows}: {line!r}"


# ── the transport line, keypress feedback, and the keymap overlay ──────────

class FakeTransport:
    def __init__(self, paused=False, index=0, count=3, position=83.0,
                 duration=296.0, loop=True, title="/tmp/set/Phone Down.m4a"):
        self.paused = paused
        self.index = index
        self.count = count
        self.position = position
        self.duration = duration
        self.loop = loop
        self.title = title


def wide(monkeypatch, columns=120, rows=30):
    monkeypatch.setattr(spectrum.shutil, 'get_terminal_size',
                        lambda default=None: __import__('os').terminal_size((columns, rows)))


@pytest.mark.parametrize("seconds, text", [
    (0, "0:00"), (7.9, "0:07"), (83, "1:23"), (296, "4:56"), (3723, "1:02:03"),
    (-1, "0:00"), (float('inf'), "0:00"), (None, "0:00"),
])
def test_a_position_reads_as_a_clock(seconds, text):
    assert spectrum.clock(seconds) == text


def test_the_transport_says_where_in_what_of_how_many():
    line = spectrum.transport_text(FakeTransport())
    assert line.startswith("▶")
    assert "1/3" in line, "which track, counting from one like a person does"
    assert "Phone Down.m4a" in line and "/tmp/set/" not in line
    assert "1:23 / 4:56" in line
    assert "↻" in line, "looping"

    paused = spectrum.transport_text(FakeTransport(paused=True, count=1, loop=False))
    assert paused.startswith("⏸ paused")
    assert "1/1" not in paused, "one track is not a playlist"
    assert "↻" not in paused


def test_the_spectrum_draws_the_transport_under_the_status(written, monkeypatch):
    wide(monkeypatch)
    display = TerminalSpectrum(color=NONE)
    display.transport = FakeTransport(position=148.0, duration=296.0)
    display.update(readings())
    display._last_draw -= 1
    display.draw()

    lines = plain("".join(written)).split("\n")
    assert "fps" in lines[0]
    assert "Phone Down.m4a" in lines[1]
    # A bar you can watch fill: half way through, half of it is full.
    bar = lines[1][lines[1].index("▕") + 1:lines[1].index("▏")]
    assert len(bar) > 8
    assert bar.count("█") == pytest.approx(len(bar) / 2, abs=1)


def test_a_capture_has_no_transport_line_at_all(written, monkeypatch):
    wide(monkeypatch)
    display = TerminalSpectrum(color=NONE)
    display.update(readings())
    display._last_draw -= 1
    display.draw()

    assert "▶" not in plain("".join(written))


def test_the_status_line_shows_the_gain_as_it_is_turned(written, monkeypatch):
    """It is a live knob now, so the number has to be the live one -- and AGC
    is a second gain on top of it, which is why both are named."""
    wide(monkeypatch)
    display = TerminalSpectrum(color=NONE)
    display.update(readings())
    display.gain = 12.5
    display._last_draw -= 1
    display.draw()
    assert "gain ×12.5" in plain("".join(written))
    assert "agc" not in plain("".join(written))

    written.clear()
    display.agc = 8.25
    display._last_draw -= 1
    display.draw()
    assert "gain ×12.5 · agc ×8.25" in plain("".join(written))


def test_a_keypress_is_confirmed_in_the_frame_and_then_lets_go(written, monkeypatch):
    """Logging it instead would push the animation up the screen once per
    keystroke, and finding a gain is a dozen keystrokes."""
    wide(monkeypatch)
    display = TerminalSpectrum(color=NONE)
    display.update(readings())

    display.notify("gain ×2.25")
    display._last_draw -= 1
    display.draw()
    assert "gain ×2.25" in plain("".join(written))

    written.clear()
    display._message_until -= display.MESSAGE_SECONDS + 1
    display._last_draw -= 1
    display.draw()
    assert "gain ×2.25" not in plain("".join(written))


def test_the_keymap_replaces_the_bars_rather_than_pushing_them_off(written, monkeypatch):
    wide(monkeypatch, rows=24)
    display = TerminalSpectrum(color=NONE)
    display.update(readings(bins=[1.0] * 32))
    display.help_lines = [("space", "pause / resume"), ("q", "stop")]
    display._last_draw -= 1
    display.draw()

    frame = plain("".join(written))
    assert "pause / resume" in frame and "? to put the spectrum back" in frame
    assert "-60 └" not in frame, "the plot would not have fitted under it"
    assert len(frame.split("\n")) <= 24


def test_a_frame_never_leaves_the_tail_of_a_taller_one_behind(written, monkeypatch):
    """Every line erases to its right, but not the lines below it. So any frame
    that is shorter than the last one has to erase downward, and the transport
    line, the toast and the overlay all change the height."""
    wide(monkeypatch)
    display = TerminalSpectrum(color=NONE)
    display.update(readings())

    def frame():
        written.clear()
        display._last_draw -= 1
        display.draw()
        return "".join(written)

    frame()                                   # the first one, nothing above it
    display.notify("gain ×2.25")
    taller = frame()
    assert taller.startswith("\x1b["), "it moved the cursor back up"

    display._message_until -= display.MESSAGE_SECONDS + 1
    shorter = frame()
    assert "\x1b[J" in shorter.split("\n")[0], "shorter, and it did not erase down"


def test_the_redraw_always_moves_up_by_exactly_what_it_drew(written, monkeypatch):
    """One line too few and the picture scrolls away a line at a time; one too
    many and it eats whatever was on the screen before it."""
    wide(monkeypatch)
    display = TerminalSpectrum(color=NONE)
    display.update(readings())
    display.transport = FakeTransport()

    previous = 0
    for step in range(6):
        written.clear()
        if step == 2:
            display.notify("seek +30s")
        if step == 3:
            display.help_lines = [("q", "stop")]
        if step == 4:
            display.help_lines = None
        display._last_draw -= 1
        display.draw()
        frame = "".join(written)

        moved = re.match(r'\x1b\[(\d+)A', frame)
        assert (int(moved.group(1)) if moved else 0) == previous, f"step {step}"
        previous = frame.count("\n")


def test_the_piped_status_line_carries_the_transport_too(written):
    """Half of watching a set from a log file is knowing where in it you are."""
    display = PlainStatus()
    display.transport = FakeTransport(paused=True)
    display.update(readings())
    display._last_at -= 2
    display.draw()

    line = "".join(written)
    assert "⏸ paused" in line and "1/3" in line and "1:23 / 4:56" in line


def test_a_keypress_on_a_display_with_no_frame_is_simply_printed(written):
    for display in (QuietStatus(), PlainStatus()):
        written.clear()
        display.notify("AGC on")
        assert "AGC on" in "".join(written)
        assert not display.draws_help


def test_a_log_line_erases_the_animation_first_so_it_does_not_tear(written):
    display = TerminalSpectrum(color=NONE)
    display._lines_on_screen = 7
    display.log("+ 192.168.1.5 — found by rescan")
    assert written[0].startswith("\x1b[7A\r\x1b[J")
    assert written[0].endswith("+ 192.168.1.5 — found by rescan\n")
    assert display._lines_on_screen == 0


def test_the_cursor_is_hidden_while_drawing_and_always_put_back(written):
    display = TerminalSpectrum(color=NONE)
    display.start()
    assert written == ["\x1b[?25l"]
    display.finish()
    display.finish()
    assert written[1:] == ["\x1b[?25h", "\x1b[?25h"], "safe to call more than once"


def test_draws_are_throttled_to_30_a_second(written):
    display = TerminalSpectrum(color=NONE)
    display.update(readings())
    display.draw()
    drawn = len(written)
    display.draw()
    assert len(written) == drawn


@pytest.mark.parametrize("colour, expected", [
    (NONE, "abc"),
    (PALETTE256, "\x1b[38;5;196mabc\x1b[39m"),
    (TRUECOLOR, "\x1b[38;2;255;0;0mabc\x1b[39m"),
])
def test_colour_modes(colour, expected):
    assert TerminalSpectrum(color=colour)._paint("abc", (1.0, 0.0, 0.0)) == expected


def test_no_color_and_dumb_terminals_are_respected(monkeypatch):
    monkeypatch.setattr(spectrum.sys.stderr, 'isatty', lambda: True, raising=False)
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.delenv('COLORTERM', raising=False)
    monkeypatch.setenv('TERM', 'xterm-256color')
    assert spectrum.color_mode() == PALETTE256

    monkeypatch.setenv('COLORTERM', 'truecolor')
    assert spectrum.color_mode() == TRUECOLOR

    monkeypatch.setenv('NO_COLOR', '1')
    assert spectrum.color_mode() == NONE

    monkeypatch.delenv('NO_COLOR')
    monkeypatch.setenv('TERM', 'dumb')
    assert spectrum.color_mode() is None, "an Emacs shell can't do cursor moves"


def test_piped_output_gets_the_status_line_not_escape_codes(monkeypatch):
    """Otherwise a log file fills with cursor moves."""
    monkeypatch.setattr(spectrum.sys.stderr, 'isatty', lambda: False, raising=False)
    assert isinstance(make_display(), PlainStatus)

    monkeypatch.setattr(spectrum.sys.stderr, 'isatty', lambda: True, raising=False)
    monkeypatch.setenv('TERM', 'xterm-256color')
    assert isinstance(make_display(), TerminalSpectrum)
    assert isinstance(make_display(plain=True), PlainStatus)
    assert isinstance(make_display(quiet=True), QuietStatus)


def test_make_display_carries_gain_and_target_count_through():
    display = make_display(quiet=True, gain=12.5, targets=4)
    assert (display.gain, display.targets) == (12.5, 4)
    assert display.loudness is SILENT
    assert math.isinf(display.loudness.momentary)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
