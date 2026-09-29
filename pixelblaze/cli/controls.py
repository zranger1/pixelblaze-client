"""Steering `pb sensor sound` while it runs, from the keyboard.

Two different jobs share one keymap here, because in front of an installation
they are the same job:

**Transport** -- space, arrows -- is for a file. Pause it, seek within it, move
between the tracks `--file` named. The point of beaming a track at a room is
usually to find the bit you want to look at, and restarting the command with a
different `--from` every time is not a way to find anything.

**The knobs** -- gain, AGC, the noise gate, log scaling -- apply to whatever is
playing, file or capture. These are the settings you cannot pick in advance:
the right gain depends on the room, the source and the pattern, and the way to
find it is to watch the lights and turn it until they look right. They were
flags you had to restart to change; now they are keys.

So each binding declares a `scope`, and the ones that cannot mean anything for
this run are neither listed nor dispatched -- `space` is not offered when there
is no file to pause, and `m` is not offered when nothing is being played out of
a speaker. `help_lines()` and `hint()` describe the run in front of you, not the
union of everything.

Nothing here touches the terminal itself: `keys.py` reads it, `spectrum.py`
draws it, and this decides what a key means.
"""

#: Which runs a binding applies to. LIVE is a capture or a generated tone --
#: anything with no cursor to move.
ANY, FILE, LIVE = 'any', 'file', 'live'

#: How far the arrows seek, in seconds, by modifier. Shift is the big jump,
#: because it is the one you reach for when a track is four minutes long and
#: the drop is at three; the unmodified step is for placing yourself once you
#: are near it, and alt/ctrl is for about a bar at a time.
SEEK_STEPS = {'': 5.0, 'shift': 30.0, 'alt': 1.0, 'ctrl': 1.0}

#: Multiplicative, because loudness is: the step that takes a quiet mic
#: somewhere useful would take a hot line input off the scale.
GAIN_STEP = 1.5
GAIN_RANGE = (0.001, 1000.0)
AGC_TARGET_STEP = 1.25
AGC_TARGET_RANGE = (0.01, 1.0)
#: The gate is off at 0, and 0 does not multiply, so stepping up from off
#: starts here and doubles from there.
GATE_FLOOR = 0.0001
GATE_CEILING = 1.0


def _clamp(value, low, high):
    return max(low, min(high, value))


class Binding:
    """One key (or a few that mean the same thing), what it does, and when it
    is worth offering.

    `label` of None is an alias -- dispatched, never listed, which is how the
    modified arrows stay out of a help list that already explains them.
    """

    def __init__(self, keys, scope, label, action, requires=None, hint=None):
        self.keys = list(keys)
        self.scope = scope
        self.label = label
        self.action = action
        #: Called with the Controls; False hides the binding for this run.
        self.requires = requires
        #: Short form for the one-line hint, or None to leave it out.
        self.hint = hint


class Controls:
    """The keymap, bound to a running `SoundBridge`.

    `poll()` is called from the bridge's run loop; it reads whatever has been
    typed and applies it. Everything it changes is a plain attribute on the
    bridge, its source or its monitor, read fresh on the next block -- there is
    no restart, no reconfiguration and nothing to keep in step.
    """

    def __init__(self, bridge, display=None, reader=None, on_rebind=None):
        self.bridge = bridge
        self.display = display
        self.on_rebind = on_rebind
        self.helping = False
        if reader is None:
            from pixelblaze.cli.keys import KeyReader
            reader = KeyReader()
        self.reader = reader
        self.bindings = keymap()
        self._by_key = {key: binding for binding in self.bindings
                        for key in binding.keys}
        #: What `0` goes back to, so a run can always be put back how it started.
        self.gain_at_start = bridge.gain

    # -- what this run can be told ------------------------------------------

    @property
    def scope(self) -> str:
        has_file = (self.bridge.samples is not None
                    or getattr(self.bridge, 'playlist', None) is not None)
        return FILE if has_file else LIVE

    @property
    def source(self):
        return self.bridge.source

    @property
    def tracks(self) -> int:
        playlist = getattr(self.bridge, 'playlist', None)
        return playlist.count if playlist is not None else 1

    def applies(self, binding: Binding) -> bool:
        if binding.scope != ANY and binding.scope != self.scope:
            return False
        return binding.requires is None or bool(binding.requires(self))

    @property
    def active_bindings(self) -> list:
        return [b for b in self.bindings if self.applies(b)]

    def help_lines(self) -> list:
        """(keys, label) for everything this run can be told, for a display."""
        return [(' / '.join(b.keys), b.label)
                for b in self.active_bindings if b.label]

    def hint(self) -> str:
        """One line for the start banner -- the keys worth knowing up front."""
        parts = [b.hint for b in self.active_bindings if b.hint]
        return "Keys: " + "  ·  ".join(parts) if parts else ""

    # -- running -------------------------------------------------------------

    def __enter__(self):
        self.reader.__enter__()
        return self

    def __exit__(self, *exc):
        return self.reader.__exit__(*exc)

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.reader, 'active', False))

    def poll(self):
        for key in self.reader.poll():
            self.press(key)

    def press(self, key: str):
        """Apply one key by name. Returns what it did, or None if that key does
        nothing here -- unknown keys are ignored rather than complained about,
        because a terminal sends all sorts of things nobody typed."""
        binding = self._by_key.get(key)
        if binding is None or not self.applies(binding):
            return None
        message = binding.action(self, key)
        if message:
            self.say(message)
        return message

    def say(self, message: str):
        if self.display is not None:
            self.display.notify(message)

    # -- the actions ---------------------------------------------------------

    def _toggle_pause(self, _key):
        if self.source is None:
            return None
        return "paused — sending silence" if self.source.toggle_pause() else "playing"

    def _seek(self, key):
        if self.source is None:
            return None
        modifier, _, arrow = key.rpartition('+')
        step = SEEK_STEPS.get(modifier, SEEK_STEPS[''])
        delta = step if arrow == 'right' else -step
        self.source.seek(delta)
        return f"seek {delta:+.0f}s"

    def _track(self, key):
        if self.source is None:
            return None
        delta = -1 if key == 'up' else 1
        self.source.move_track(delta)
        return "previous track" if delta < 0 else "next track"

    def _loop(self, _key):
        if self.source is None:
            return None
        self.source.loop = not self.source.loop
        self.bridge.loop = self.source.loop
        return f"loop {'on' if self.source.loop else 'off'}"

    def _gain(self, key):
        up = key in ('+', '=')
        self.bridge.gain = _clamp(self.bridge.gain * (GAIN_STEP if up else 1 / GAIN_STEP),
                                  *GAIN_RANGE)
        return (f"gain ×{self.bridge.gain:.3g}"
                + (" (AGC is on — `a` to turn it off)" if self.bridge.agc else ""))

    def _gain_reset(self, _key):
        self.bridge.gain = self.gain_at_start
        return f"gain ×{self.bridge.gain:.3g} (back to --gain)"

    def _agc(self, _key):
        self.bridge.agc = not self.bridge.agc
        if not self.bridge.agc:
            return f"AGC off — gain ×{self.bridge.gain:.3g}"
        return f"AGC on — holding peaks near {self.bridge.agc_target:.3g}"

    def _agc_target(self, key):
        up = key == ']'
        self.bridge.agc_target = _clamp(
            self.bridge.agc_target * (AGC_TARGET_STEP if up else 1 / AGC_TARGET_STEP),
            *AGC_TARGET_RANGE)
        return (f"AGC target {self.bridge.agc_target:.3g}"
                + ("" if self.bridge.agc else " (AGC is off — `a` to turn it on)"))

    def _log_scale(self, _key):
        self.bridge.log_scale = not self.bridge.log_scale
        return f"log scaling {'on' if self.bridge.log_scale else 'off'}"

    def _gate(self, key):
        gate = self.bridge.noise_gate
        if key == 'N':
            gate = GATE_FLOOR if gate <= 0 else min(gate * 2, GATE_CEILING)
        else:
            gate = 0.0 if gate <= GATE_FLOOR else gate / 2
        self.bridge.noise_gate = gate
        return f"noise gate {gate:.3g}" if gate else "noise gate off"

    def _mute(self, _key):
        monitor = self.bridge.monitor
        monitor.muted = not monitor.muted
        return ("muted — still streaming to the lights" if monitor.muted else "unmuted")

    def _rebind(self, _key):
        self.on_rebind()
        return "reloading the pattern on every target"

    def _help(self, _key):
        self.helping = not self.helping
        if self.display is None:
            return None
        if getattr(self.display, 'draws_help', False):
            self.display.help_lines = self.help_lines() if self.helping else None
            return None
        # A display with nowhere to hold an overlay says it once instead.
        self.helping = False
        for keys, label in self.help_lines():
            self.display.log(f"    {keys:<22} {label}")
        return None

    def _quit(self, _key):
        self.bridge.stop()
        return "stopping"


def keymap() -> list:
    """Every binding, in the order a help list should read."""
    return [
        Binding(['space'], FILE,
                'pause / resume — sends silence, so the lights go quiet '
                'rather than latching',
                Controls._toggle_pause, hint='space pause'),
        Binding(['left', 'right'], FILE,
                f"seek ∓{SEEK_STEPS['']:.0f}s  ·  shift ∓{SEEK_STEPS['shift']:.0f}s  ·  "
                f"alt/ctrl ∓{SEEK_STEPS['alt']:.0f}s",
                Controls._seek, hint='←→ seek'),
        Binding(['shift+left', 'shift+right', 'alt+left', 'alt+right',
                 'ctrl+left', 'ctrl+right'], FILE, None, Controls._seek),
        Binding(['up', 'down'], FILE, 'previous / next track',
                Controls._track, requires=lambda c: c.tracks > 1, hint='↑↓ track'),
        Binding(['L'], FILE, 'loop on / off', Controls._loop),
        Binding(['-', '+'], ANY, f"gain down / up (×{GAIN_STEP:g} a press)",
                Controls._gain, hint='-/+ gain'),
        Binding(['_', '='], ANY, None, Controls._gain),   # the same two keys, shifted
        Binding(['0'], ANY, 'gain back to what --gain set', Controls._gain_reset),
        Binding(['a'], ANY, 'AGC on / off', Controls._agc, hint='a agc'),
        Binding(['[', ']'], ANY, 'AGC target level down / up', Controls._agc_target),
        Binding(['l'], ANY, 'log scaling on / off', Controls._log_scale),
        Binding(['n', 'N'], ANY, 'noise gate down / up', Controls._gate),
        Binding(['m'], ANY, 'mute what you hear — keeps streaming',
                Controls._mute, requires=lambda c: c.bridge.monitor is not None,
                hint='m mute'),
        Binding(['r'], ANY,
                'reload the pattern on every target, so the firmware binds it '
                'to this stream',
                Controls._rebind, requires=lambda c: c.on_rebind is not None,
                hint='r rebind'),
        Binding(['?', 'h'], ANY, 'this list', Controls._help, hint='? help'),
        Binding(['q'], ANY, 'stop', Controls._quit, hint='q quit'),
    ]


def _check_keys_are_unique():
    """Two bindings claiming one key makes the second unreachable, and the
    symptom is a key that silently does the wrong thing. Checked at import."""
    seen = {}
    for binding in keymap():
        for key in binding.keys:
            if key in seen:
                raise AssertionError(f"key {key!r} is bound twice: "
                                     f"{seen[key]} and {binding.action.__name__}")
            seen[key] = binding.action.__name__
    return seen


KEYS = _check_keys_are_unique()
