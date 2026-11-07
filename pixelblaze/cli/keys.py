"""Single keypresses from the terminal, without blocking the thing that is running.

`pb sensor sound` is a long-running loop that has to keep pushing frames at a
fixed rate, so the keyboard cannot be read the way a prompt reads it. This puts
the terminal in cbreak mode -- keys arrive as they are typed, unbuffered and
unechoed -- and `poll()` returns whatever has been typed since the last call,
never waiting for any of it.

cbreak rather than raw, deliberately: raw mode would swallow Ctrl-C, and Ctrl-C
is how this program has always been stopped. ISIG stays on, SIGINT is still
delivered, and the `finally` that restores the terminal still runs.

Where there is no terminal to read -- piped stdin, a cron job, a test -- the
reader is simply inactive and `poll()` returns nothing, so every caller works
unchanged with no keyboard at all.

    with KeyReader() as keys:
        while running:
            for key in keys.poll():
                ...
            do_the_actual_work()

Keys come back as names: a single character for printable ones, and otherwise
`space`, `enter`, `esc`, `tab`, `backspace`, `up`/`down`/`left`/`right`,
`home`/`end`/`pgup`/`pgdn`/`delete`, each optionally prefixed with `ctrl+`,
`alt+` and `shift+` in that order (`shift+left`, `ctrl+shift+right`).
"""

import os
import select
import sys
import time

#: A lone ESC and the start of an escape sequence are the same byte. Nothing can
#: tell them apart except waiting to see whether more follows -- every terminal
#: program picks a number here, and this is ours.
ESC_TIMEOUT = 0.05

_FINAL_KEYS = {'A': 'up', 'B': 'down', 'C': 'right', 'D': 'left',
               'H': 'home', 'F': 'end'}
_TILDE_KEYS = {'1': 'home', '3': 'delete', '4': 'end', '5': 'pgup', '6': 'pgdn',
               '7': 'home', '8': 'end'}
# rxvt says shift+up with a lowercase letter where xterm sends a modifier
# parameter, and ctrl+up as SS3 with that same lowercase letter.
_RXVT_KEYS = {'a': 'up', 'b': 'down', 'c': 'right', 'd': 'left'}
_CONTROL_KEYS = {'\r': 'enter', '\n': 'enter', '\t': 'tab', ' ': 'space',
                 '\x7f': 'backspace', '\x08': 'backspace', '\x1b': 'esc'}

#: xterm's modifier parameter is 1 + a bitmask, so `1;6C` is ctrl+shift+right.
#: Named in the order keybindings are conventionally written, not bit order.
_MODIFIERS = [(4, 'ctrl'), (2, 'alt'), (1, 'shift')]


def _modified(name: str, parameter: str) -> str:
    try:
        bits = int(parameter) - 1
    except ValueError:
        return name
    prefix = ''.join(f"{label}+" for bit, label in _MODIFIERS if bits & bit)
    return prefix + name


def parse_key(buffer: str):
    """The first key in `buffer`, as (name, characters consumed).

    Returns `(None, 0)` when the buffer holds the start of an escape sequence
    but not yet all of it -- the caller should read more and try again, or give
    up after `ESC_TIMEOUT` and treat it as a bare `esc`.
    """
    if not buffer:
        return None, 0

    head = buffer[0]
    if head != '\x1b':
        return _CONTROL_KEYS.get(head, head), 1

    if len(buffer) == 1:
        return None, 0                      # ESC, or the start of something

    # SS3: what the arrows become in "application cursor" mode, which plenty of
    # terminals switch into. Same keys, different introducer.
    if buffer[1] == 'O':
        if len(buffer) < 3:
            return None, 0
        final = buffer[2]
        if final in _RXVT_KEYS:
            return f"ctrl+{_RXVT_KEYS[final]}", 3
        return _FINAL_KEYS.get(final, f"esc+O{final}"), 3

    if buffer[1] != '[':
        return f"alt+{buffer[1]}", 2        # ESC-prefixed: what Alt sends

    # CSI: ESC [ <parameters> <intermediates> <final>, as ECMA-48 defines them
    # -- parameters 0x30-0x3F, intermediates 0x20-0x2F, final 0x40-0x7E. Worth
    # doing properly rather than scanning for digits, because the private forms
    # are exactly what a terminal sends unasked: `ESC [ ? 1 0 0 0 h` would
    # otherwise end at the `?` and leave `1000h` to be read as five keystrokes,
    # one of which is bound.
    index = 2
    while index < len(buffer) and '\x30' <= buffer[index] <= '\x3f':
        index += 1
    while index < len(buffer) and '\x20' <= buffer[index] <= '\x2f':
        index += 1
    if index >= len(buffer):
        return None, 0                      # still reading the parameters
    parameters, final, consumed = buffer[2:index], buffer[index], index + 1
    if not '\x40' <= final <= '\x7e':
        return f"csi{parameters}{final}", consumed   # malformed; consume it anyway

    if final == '~':
        name = _TILDE_KEYS.get(parameters.split(';')[0])
        if name is None:
            return f"csi~{parameters}", consumed
        parts = parameters.split(';')
        return (_modified(name, parts[1]) if len(parts) > 1 else name), consumed

    if final in _RXVT_KEYS:
        return f"shift+{_RXVT_KEYS[final]}", consumed

    name = _FINAL_KEYS.get(final)
    if name is None:
        return f"csi{parameters}{final}", consumed
    parts = parameters.split(';')
    return (_modified(name, parts[1]) if len(parts) > 1 else name), consumed


class KeyReader:
    """Keys typed since the last `poll()`, or nothing at all when there is no
    terminal to read. Use as a context manager: the terminal mode it sets has
    to be put back."""

    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stdin
        self.active = False
        self._fd = None
        self._saved = None
        self._pending = ''
        self._pending_since = 0.0

    @property
    def available(self) -> bool:
        """Can this terminal be read at all? False for a pipe, a redirect, a
        test, or Windows (no termios)."""
        try:
            self._fd = self.stream.fileno()
        except (AttributeError, ValueError, OSError):
            return False
        import importlib.util
        if importlib.util.find_spec('termios') is None:
            return False                                       # Windows
        try:
            return os.isatty(self._fd)
        except OSError:
            return False

    def __enter__(self):
        if not self.available:
            return self
        import termios
        import tty
        try:
            self._saved = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        except termios.error:
            self._saved = None
            return self
        self.active = True
        return self

    def __exit__(self, *exc):
        if self._saved is not None:
            import termios
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
            except termios.error:
                pass
        self.active = False
        return False

    def poll(self) -> list:
        """Every complete key typed since the last call. Never blocks."""
        if not self.active:
            return []

        while select.select([self._fd], [], [], 0)[0]:
            try:
                chunk = os.read(self._fd, 1024)
            except OSError:
                break
            if not chunk:
                break
            if not self._pending:
                self._pending_since = time.monotonic()
            self._pending += chunk.decode('utf-8', 'replace')

        keys = []
        while self._pending:
            name, consumed = parse_key(self._pending)
            if name is None:
                # A partial escape sequence: wait for the rest, unless it has
                # been sitting there long enough that it was just the ESC key.
                if time.monotonic() - self._pending_since < ESC_TIMEOUT:
                    break
                name, consumed = 'esc', 1
            self._pending = self._pending[consumed:]
            self._pending_since = time.monotonic()
            keys.append(name)
        return keys
