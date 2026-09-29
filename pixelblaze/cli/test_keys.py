#!/usr/bin/env python3
"""Unit tests for reading single keypresses (`pixelblaze.cli.keys`).

No terminal required: the escape-sequence parser is pure, and the reader is
driven over a pty, which is a real terminal as far as termios is concerned.

    python3 -m pytest pixelblaze/cli/test_keys.py
"""

import os
import pty
import time

import pytest

from pixelblaze.cli.keys import ESC_TIMEOUT, KeyReader, parse_key


@pytest.mark.parametrize("sequence, key", [
    ("a", "a"),
    ("Z", "Z"),
    ("?", "?"),
    (" ", "space"),
    ("\r", "enter"),
    ("\n", "enter"),
    ("\t", "tab"),
    ("\x7f", "backspace"),
    # The arrows, as a terminal in its normal mode sends them...
    ("\x1b[A", "up"),
    ("\x1b[B", "down"),
    ("\x1b[C", "right"),
    ("\x1b[D", "left"),
    # ...and in application cursor mode, which plenty of terminals switch into.
    ("\x1bOA", "up"),
    ("\x1bOD", "left"),
    # Modifiers are a parameter, not a different key: 1 + a bitmask.
    ("\x1b[1;2C", "shift+right"),
    ("\x1b[1;3D", "alt+left"),
    ("\x1b[1;5C", "ctrl+right"),
    ("\x1b[1;6D", "ctrl+shift+left"),
    # rxvt says shift+up with a lowercase letter, and ctrl+up as SS3 with it.
    ("\x1b[a", "shift+up"),
    ("\x1bOc", "ctrl+right"),
    ("\x1b[5~", "pgup"),
    ("\x1b[6~", "pgdn"),
    ("\x1b[3~", "delete"),
    ("\x1b[H", "home"),
    ("\x1b[1;2F", "shift+end"),
])
def test_a_terminal_speaks_in_escape_sequences(sequence, key):
    assert parse_key(sequence) == (key, len(sequence))


def test_a_half_arrived_sequence_waits_for_the_rest():
    """A key arrives in however many reads the kernel felt like. Consuming a
    partial sequence would turn one arrow into a stray `[` and a stray `C`."""
    for partial in ("\x1b", "\x1b[", "\x1b[1", "\x1b[1;", "\x1b[1;2", "\x1bO"):
        assert parse_key(partial) == (None, 0), partial

    assert parse_key("\x1b[1;2C") == ("shift+right", 6)


def test_keys_are_taken_one_at_a_time_from_a_burst():
    """Holding a key down, or a fast paste, delivers several at once."""
    buffer = "\x1b[Cab\x1b[1;2D "
    keys = []
    while buffer:
        name, consumed = parse_key(buffer)
        assert name is not None
        keys.append(name)
        buffer = buffer[consumed:]
    assert keys == ["right", "a", "b", "shift+left", "space"]


def test_an_unknown_sequence_is_named_rather_than_mistaken_for_keys():
    """Terminals send things nobody typed -- a mouse report, a paste bracket, a
    cursor-position reply. Whatever it is, it must not come back as the letters
    inside it."""
    name, consumed = parse_key("\x1b[200~")
    assert name.startswith("csi") and consumed == 6

    name, consumed = parse_key("\x1b[?1000h")
    assert "1000" in name and consumed == 8


# ── the reader, over a pty ──────────────────────────────────────────────────

class FakeTerminal:
    """A pty: a real terminal to termios, with a handle to type into it."""

    def __init__(self):
        self.primary, self.secondary = pty.openpty()
        self.stream = os.fdopen(self.secondary, 'rb', buffering=0)

    def type(self, text: str):
        os.write(self.primary, text.encode())
        time.sleep(0.02)          # let the kernel hand it over

    def close(self):
        try:
            self.stream.close()
        except OSError:
            pass
        os.close(self.primary)


def test_the_reader_returns_what_was_typed_and_never_waits():
    terminal = FakeTerminal()
    try:
        with KeyReader(terminal.stream) as reader:
            assert reader.active, "a pty is a terminal"
            assert reader.poll() == [], "nothing typed yet, and it did not block"

            terminal.type("a\x1b[C \x1b[1;2B")
            assert reader.poll() == ["a", "right", "space", "shift+down"]
            assert reader.poll() == []
    finally:
        terminal.close()


def test_a_lone_escape_is_the_escape_key_once_nothing_follows_it():
    """ESC and the start of an arrow are the same byte; only time tells."""
    terminal = FakeTerminal()
    try:
        with KeyReader(terminal.stream) as reader:
            terminal.type("\x1b")
            assert reader.poll() == [], "it might still be the start of an arrow"
            time.sleep(ESC_TIMEOUT + 0.02)
            assert reader.poll() == ["esc"]
    finally:
        terminal.close()


def test_the_terminal_is_put_back_the_way_it_was_found():
    """cbreak turns off echo and line buffering. Leaving it that way leaves the
    user's shell unusable, which is why this is a context manager at all."""
    import termios

    terminal = FakeTerminal()
    try:
        before = termios.tcgetattr(terminal.stream.fileno())
        with KeyReader(terminal.stream) as reader:
            during = termios.tcgetattr(terminal.stream.fileno())
            assert during != before, "cbreak did not take"
            assert reader.active
        assert termios.tcgetattr(terminal.stream.fileno()) == before
    finally:
        terminal.close()


def test_ctrl_c_is_still_a_signal_and_not_a_key():
    """cbreak rather than raw, deliberately: Ctrl-C is how this has always been
    stopped, and raw mode would deliver it as a byte instead of a SIGINT."""
    import termios

    terminal = FakeTerminal()
    try:
        with KeyReader(terminal.stream):
            attrs = termios.tcgetattr(terminal.stream.fileno())
            assert attrs[3] & termios.ISIG, "signals were turned off"
    finally:
        terminal.close()


def test_no_terminal_means_no_keyboard_rather_than_an_error(tmp_path):
    """Piped stdin, a service, a cron job: every caller has to work unchanged."""
    path = tmp_path / "stdin"
    path.write_text("aaaa")
    with open(path) as handle:
        reader = KeyReader(handle)
        assert not reader.available
        with reader:
            assert not reader.active
            assert reader.poll() == []


def test_a_stream_with_no_file_descriptor_at_all_is_handled():
    """`pytest` and friends replace stdin with something that is not a file."""
    import io

    reader = KeyReader(io.StringIO("abc"))
    assert not reader.available
    with reader:
        assert reader.poll() == []
