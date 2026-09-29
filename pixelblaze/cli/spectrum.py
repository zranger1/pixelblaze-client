"""The 32 sensor bins as a live terminal spectrum -- what the pattern is being
sent, drawn in place under the start line at 30 fps.

     40 fps → 3 · peak 1230 Hz · energy 0.0310 · gain x1.0 · 0:12
     LUFS ▕█████████████████┃▎·····▏ M -14.2   S -15.0   I -14.8
      0 ┤          ▂█▇
        │          ███▁
    -20 ┤         ▅████▃        ▁▁
    ...
    -60 └──────────────────────────────
         50  100  200  500  1k  2k  5k  10k Hz

Same scale as a browser's meter: dB over -60..0, so a correct full-scale sine is
a tall bar rather than a two-cell sliver (the values are linear magnitudes; only
the drawing is logarithmic). Eighth-block characters give each cell eight steps,
peak caps hold 400 ms then fall at 30 dB/s -- the browser meter's ballistics --
and the hue runs blue -> red across frequency.

Everything here writes to **stderr**, so stdout stays whatever the command
means to emit, and the bars are only drawn when stderr is a terminal: piped,
they would be escape codes in a log file, so `PlainStatus` prints one line a
second instead. `--quiet` is `QuietStatus`, which prints nothing at all.

All three share one interface, so the bridge does not care which it has:

    display.gain / .fps / .loudness / .targets / .silent   -- set by the caller
    display.start(); display.update(readings); display.draw(); display.log(...)
    display.finish()

Ported from the Swift `TerminalSpectrum` in staff-infection's `pbsensor`.
"""

import math
import os
import shutil
import sys

from pixelblaze.cli.loudness import SILENT, Loudness
from pixelblaze.cli.sensor_bridge import PB_BIN_CENTERS

FLOOR_DB = -60.0
BLOCKS = " ▁▂▃▄▅▆▇█"
BIN_COUNT = 32

# NO_COLOR is the convention (no-color.org); TERM=dumb is an Emacs shell and
# friends, which cannot do the cursor moves at all.
NONE, PALETTE256, TRUECOLOR = 'none', 'palette256', 'truecolor'


def color_mode():
    """Whether to animate at all, and in what colour. None means "don't"."""
    if not sys.stderr.isatty() or os.environ.get('TERM') == 'dumb':
        return None
    if os.environ.get('NO_COLOR'):
        return NONE
    colorterm = (os.environ.get('COLORTERM') or '').lower()
    return TRUECOLOR if colorterm in ('truecolor', '24bit') else PALETTE256


def level(magnitude: float) -> float:
    """A linear FFT magnitude as a 0..1 height on the -60..0 dB scale."""
    if magnitude <= 0:
        return 0.0
    return min(1.0, max(0.0, (20 * math.log10(magnitude) - FLOOR_DB) / -FLOOR_DB))


def hsv(h: float, s: float, v: float) -> tuple[float, float, float]:
    i = int(h * 6) % 6
    f = h * 6 - math.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]


def _emit(text: str):
    sys.stderr.write(text)
    sys.stderr.flush()


class QuietStatus:
    """`--quiet`: the readings still flow, nothing is said about them."""

    #: Whether `help_lines` can be shown as an overlay, or has to be printed.
    draws_help = False

    def __init__(self):
        self.gain = 1.0
        self.fps = 0
        self.loudness = SILENT
        self.targets = None
        self.silent = False
        #: The AGC's current multiplier, or None when AGC is off.
        self.agc = None
        #: A `Transport` (see `sensor_bridge`) while a file is playing.
        self.transport = None
        #: Set to a list of (keys, label) to show the keymap; None to hide it.
        self.help_lines = None

    def start(self):
        pass

    def update(self, readings):
        pass

    def draw(self):
        pass

    def log(self, line: str):
        _emit(line + "\n")

    def notify(self, message: str):
        """A keypress did something. Where there is no frame to hold a
        transient line, saying it once is the whole of it."""
        self.log("  " + message)

    def finish(self):
        pass


class PlainStatus(QuietStatus):
    """One line a second -- what a pipe or a log file wants.

    `energy` is energyAverage, what a pattern reads: the mean of the 32 bins.
    It tracks "busier", not "louder", which is why the LUFS figures are here
    too -- see `loudness.py`.
    """

    INTERVAL = 1.0

    def __init__(self):
        super().__init__()
        self._latest = None
        self._last_at = 0.0

    def update(self, readings):
        self._latest = readings

    def draw(self):
        import time
        now = time.monotonic()
        if self._latest is None or now - self._last_at < self.INTERVAL:
            return
        self._last_at = now
        readings = self._latest
        bins = readings["frequencyData"]
        loudest = max(range(len(bins)), key=bins.__getitem__) if bins else 0
        line = (f"  {self.fps:4d} fps · peak {readings['maxFrequency']:5.0f} Hz "
                f"(bin {loudest:2d}) · energy {readings['energyAverage']:.4f} · "
                f"M {Loudness.text(self.loudness.momentary, 5)} "
                f"S {Loudness.text(self.loudness.shortTerm, 5)} "
                f"I {Loudness.text(self.loudness.integrated, 5)} LUFS")
        if self.transport is not None:
            line += " · " + transport_text(self.transport)
        if self.targets is not None:
            line += f" · → {self.targets}"
        if self.silent:
            line += " · silent — is anything playing?"
        _emit(line + "\n")


def clock(seconds: float) -> str:
    """m:ss, or h:mm:ss for a set rather than a track."""
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        seconds = 0.0
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def transport_text(transport) -> str:
    """`⏸ 2/7 Phone Down.m4a 1:23 / 4:56` -- what a file source is doing, in
    the one line a piped status or a narrow terminal has for it."""
    parts = ["⏸ paused" if transport.paused else "▶"]
    if transport.count > 1:
        parts.append(f"{transport.index + 1}/{transport.count}")
    title = os.path.basename(str(transport.title or "")).strip()
    if title:
        parts.append(title)
    parts.append(f"{clock(transport.position)} / {clock(transport.duration)}")
    if transport.loop:
        parts.append("↻")
    return " ".join(parts)


class TerminalSpectrum(QuietStatus):
    """The live bars. Only for a terminal -- see `color_mode()`."""

    draws_help = True
    #: How long a keypress's confirmation stays on screen.
    MESSAGE_SECONDS = 2.5

    FRAME_INTERVAL = 1.0 / 30
    # Bars fall at 90 dB/s rather than snapping to zero between frames; caps
    # hold 400 ms, then fall at 30 dB/s. (1.0 on this scale is 60 dB.)
    BAR_FALL = 1.5
    CAP_FALL = 0.5
    CAP_HOLD = 0.4

    AXIS_MARKS = [(50, "50"), (100, "100"), (200, "200"), (500, "500"),
                  (1000, "1k"), (2000, "2k"), (5000, "5k"), (10000, "10k")]

    def __init__(self, color=PALETTE256):
        super().__init__()
        import time
        self.color = color
        self._started = time.monotonic()
        self._latest = None
        # Loudest value per bin since the last draw -- readings can arrive
        # faster than 30 Hz, so taking only the newest would drop transients.
        self._pending = [0.0] * BIN_COUNT
        self._shown = [0.0] * BIN_COUNT
        self._peak = [0.0] * BIN_COUNT
        self._peak_held_until = [0.0] * BIN_COUNT
        self._last_draw = time.monotonic()
        self._lines_on_screen = 0
        self._last_size = (0, 0)
        self._message = None
        self._message_until = 0.0

    def notify(self, message: str):
        """A keypress's confirmation, held for a couple of seconds in the frame
        itself. Logging it instead would push the whole animation up the screen
        once per keystroke, and adjusting a gain is a dozen keystrokes."""
        import time
        self._message = message
        self._message_until = time.monotonic() + self.MESSAGE_SECONDS

    def start(self):
        _emit("\x1b[?25l")          # hide the cursor

    def finish(self):
        """Put the cursor back. Safe to call more than once."""
        _emit("\x1b[?25h")

    def log(self, line: str):
        """Print above the animation without tearing it."""
        _emit(self._erase() + line + "\n")
        self._lines_on_screen = 0

    def update(self, readings):
        self._latest = readings
        bins = readings["frequencyData"]
        for i in range(min(BIN_COUNT, len(bins))):
            self._pending[i] = max(self._pending[i], level(bins[i]))

    def draw(self):
        import time
        now = time.monotonic()
        if now - self._last_draw < self.FRAME_INTERVAL:
            return
        dt = min(0.2, now - self._last_draw)
        self._last_draw = now

        for i in range(BIN_COUNT):
            self._shown[i] = max(self._pending[i], self._shown[i] - self.BAR_FALL * dt)
            self._pending[i] = 0.0
            if self._shown[i] >= self._peak[i]:
                self._peak[i] = self._shown[i]
                self._peak_held_until[i] = now + self.CAP_HOLD
            elif now > self._peak_held_until[i]:
                self._peak[i] = max(self._shown[i], self._peak[i] - self.CAP_FALL * dt)

        size = shutil.get_terminal_size((80, 24))
        resized = size != self._last_size
        self._last_size = size

        lines = [self._status(now)]
        if self.transport is not None:
            lines.append(self._transport_line(size.columns))

        if self.help_lines:
            # The keymap instead of the bars, not as well as them: a dozen more
            # lines under a full-height plot scrolls the picture off the screen
            # on any normal terminal.
            lines += self._help_block(size.lines - len(lines) - 1)
            self._flush(lines, size, resized)
            return

        extra = len(lines) - 1 + (1 if self._message_showing(now) else 0)
        height = max(4, min(14, size.lines - 5 - extra))
        gutter = 6
        per = max(1, (size.columns - gutter - 1) // BIN_COUNT)
        bar_w, gap = (min(per - 1, 3), 1) if per >= 3 else ((1, 1) if per == 2 else (1, 0))
        plot_w = BIN_COUNT * (bar_w + gap) - gap

        lines.append(self._loudness_line(24))
        lines += self._bars(height, bar_w, gap)
        lines.append(self._dim(" -60 └" + "─" * plot_w))
        lines.append(self._dim(self._axis(gutter, plot_w, bar_w, gap) + " Hz"))
        if self._message_showing(now):
            lines.append(self._paint(" " + self._message, (0.5, 0.95, 0.6)))

        self._flush(lines, size, resized)

    def _flush(self, lines: list, size, resized: bool):
        # A frame with fewer lines than the last one leaves the tail of the old
        # one on screen -- each line erases itself to the right, but not the
        # lines below. So any change of height erases downward, and the
        # transport line, the toast and the help overlay all change it.
        out = self._erase(clear=resized or len(lines) != self._lines_on_screen)
        # A line wider than the terminal wraps, the next redraw then moves up
        # one line too few, and the whole picture scrolls away frame by frame.
        for line in lines:
            out += fit(line, size.columns - 1) + "\x1b[K\n"
        self._lines_on_screen = len(lines)
        _emit(out)

    # -- the pieces ---------------------------------------------------------

    def _message_showing(self, now: float) -> bool:
        return bool(self._message and now < self._message_until)

    def _status(self, now: float) -> str:
        readings = self._latest or {"maxFrequency": 0.0, "energyAverage": 0.0}
        seconds = int(now - self._started)
        to = f" → {self.targets}" if self.targets is not None else ""
        gain = f"gain ×{self.gain:.3g}"
        if self.agc is not None:
            gain += f" · agc ×{self.agc:.3g}"
        status = (f" {self.fps:3d} fps{to} · peak {readings['maxFrequency']:5.0f} Hz · "
                  f"energy {readings['energyAverage']:.4f} · {gain} · "
                  f"{seconds // 60}:{seconds % 60:02d}")
        if self.silent:
            status += " · " + self._paint("silent — is anything playing?", (1, 0.8, 0.2))
        return status

    def _transport_line(self, columns: int) -> str:
        """Where the track is, and a bar you can watch fill."""
        transport = self.transport
        text = transport_text(transport)
        width = max(8, min(28, columns - len(text) - 6))
        done = 0.0
        if transport.duration > 0:
            done = min(1.0, max(0.0, transport.position / transport.duration))
        filled = int(done * width)
        bar = ("█" * filled).ljust(width, "·")
        colour = (1, 0.75, 0.25) if transport.paused else (0.4, 0.9, 0.55)
        return " " + self._paint(text, colour) + "  " + self._dim("▕" + bar + "▏")

    def _help_block(self, room: int) -> list:
        lines = [self._dim(" keys — any of these, while it runs:")]
        for keys, label in (self.help_lines or [])[:max(1, room - 2)]:
            lines.append("   " + self._paint(keys.ljust(20), (0.5, 0.8, 1.0))
                         + self._dim(label))
        lines.append(self._dim(" ? to put the spectrum back"))
        return lines

    def _loudness_line(self, width: int) -> str:
        """A bar over -60..0 LUFS for momentary, a tick at short-term, and the
        three numbers."""
        def position(value):
            if not math.isfinite(value):
                return 0.0
            return min(1.0, max(0.0, (value - FLOOR_DB) / -FLOOR_DB))

        eighths = round(position(self.loudness.momentary) * width * 8)
        tick = (min(width - 1, int(position(self.loudness.shortTerm) * width))
                if math.isfinite(self.loudness.shortTerm) else -1)
        partial = " ▏▎▍▌▋▊▉"
        bar = ""
        for cell in range(width):
            fill = max(0, min(8, eighths - cell * 8))
            if cell == tick:
                # On top of the bar, not hidden under it: S usually sits right
                # beside M.
                bar += self._paint("┃", (1, 1, 1))
            elif fill == 8:
                bar += self._paint("█", (0.3, 0.85, 0.95))
            elif fill > 0:
                bar += self._paint(partial[fill], (0.3, 0.85, 0.95))
            else:
                bar += self._dim("·")
        return (self._dim(" LUFS ▕") + bar + self._dim("▏")
                + f" M {Loudness.text(self.loudness.momentary, 5)}"
                + f"   S {Loudness.text(self.loudness.shortTerm, 5)}"
                + f"   I {Loudness.text(self.loudness.integrated, 5)}")

    def _bars(self, height: int, bar_w: int, gap: int) -> list:
        labels = {0: "0", height // 3: "-20", (2 * height) // 3: "-40"}
        lines = []
        for row in range(height):
            from_bottom = height - 1 - row
            label = labels.get(row)
            line = self._dim((label or "").rjust(4) + (" ┤" if label else " │"))
            for i in range(BIN_COUNT):
                eighths = round(self._shown[i] * height * 8)
                filled = max(0, min(8, eighths - from_bottom * 8))
                cap_row = min(height - 1, int(self._peak[i] * height))
                if filled > 0:
                    hue = 0.62 - 0.62 * i / (BIN_COUNT - 1)
                    # Brighter toward the top of the plot: a glow, not a slab.
                    value = 0.55 + 0.45 * (from_bottom + 1) / height
                    line += self._paint(BLOCKS[filled] * bar_w, hsv(hue, 0.8, value))
                elif self._peak[i] > 0.02 and cap_row == from_bottom and eighths <= from_bottom * 8:
                    line += self._paint("▁" * bar_w, (1, 1, 1))
                else:
                    line += " " * bar_w
                if gap and i < BIN_COUNT - 1:
                    line += " "
            lines.append(line)
        return lines

    def _axis(self, gutter: int, plot_w: int, bar_w: int, gap: int) -> str:
        axis = [" "] * (gutter + plot_w + 4)
        free_from = 0
        for hz, label in self.AXIS_MARKS:
            nearest = min(range(len(PB_BIN_CENTERS)),
                          key=lambda b: abs(math.log(PB_BIN_CENTERS[b] / hz)))
            column = gutter + nearest * (bar_w + gap)
            if column < free_from or column + len(label) > len(axis):
                continue
            axis[column:column + len(label)] = label
            free_from = column + len(label) + 1
        # Trailing padding, and then the unit -- rstripped so "Hz" is not the
        # thing `fit` truncates on a terminal only just wide enough.
        return "".join(axis).rstrip()

    # -- terminal -----------------------------------------------------------

    def _erase(self, clear: bool = True) -> str:
        if self._lines_on_screen <= 0:
            return ""
        return f"\x1b[{self._lines_on_screen}A\r" + ("\x1b[J" if clear else "")

    def _dim(self, text: str) -> str:
        return text if self.color == NONE else "\x1b[2m" + text + "\x1b[22m"

    def _paint(self, text: str, fg) -> str:
        if self.color == NONE:
            return text
        if self.color == TRUECOLOR:
            r, g, b = (int(c * 255) for c in fg)
            return f"\x1b[38;2;{r};{g};{b}m{text}\x1b[39m"
        # The 6x6x6 cube. Terminal.app took until recently to do 24-bit colour
        # and still maps it approximately, so this is the default.
        r, g, b = (round(c * 5) for c in fg)
        return f"\x1b[38;5;{16 + 36 * r + 6 * g + b}m{text}\x1b[39m"


def fit(text: str, columns: int) -> str:
    """Truncate to `columns` visible characters, skipping escape sequences."""
    out = []
    visible = 0
    in_escape = False
    truncated = False
    for ch in text:
        if in_escape:
            out.append(ch)
            if ch.isalpha():
                in_escape = False
            continue
        if ch == "\x1b":
            in_escape = True
            out.append(ch)
            continue
        if visible >= columns:
            truncated = True
            continue
        out.append(ch)
        visible += 1
    return "".join(out) + ("\x1b[0m" if truncated else "")


def make_display(quiet: bool = False, plain: bool = False, gain: float = 1.0,
                 targets=None):
    """The right display for how this run was invoked and where stderr goes."""
    mode = None if (quiet or plain) else color_mode()
    if quiet:
        display = QuietStatus()
    elif mode is None:
        display = PlainStatus()
    else:
        display = TerminalSpectrum(color=mode)
    display.gain = gain
    display.targets = targets
    return display
