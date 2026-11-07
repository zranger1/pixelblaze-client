"""Loudness in LUFS -- ITU-R BS.1770-4 / EBU R128 -- measured live.

WHY THIS AND NOT `energyAverage`. `energyAverage` is what a pattern reads: the
mean of the 32 sensor bins, each an average linear FFT magnitude over a ~1/3
octave band. Every band counts equally however wide it is, nothing is squared,
nothing is weighted for hearing, and a pure tone is diluted by the width of the
band it lands in. It is a fine relative signal for "the music got busier" and
says almost nothing about how loud the input is. LUFS does: it is the broadcast
standard for perceived loudness, so "-14 LUFS" here means what it means on a
streaming service's normalizer or a DAW's meter.

THE MEASUREMENT, as the standard specifies it:

  1. K-weighting per channel: a high shelf (+4 dB above ~1.7 kHz, the head's
     acoustic effect) then a high-pass at ~38 Hz (the "RLB" curve). The
     coefficients BS.1770 tabulates are for 48 kHz only; `k_weighting()`
     derives them for any rate from the analog prototypes (the libebur128
     formulas), and the test checks it reproduces the table at 48 kHz.
  2. Mean square of the weighted signal, summed across channels -- each
     channel's POWER, not a mono mixdown. Averaging L and R first reads up to
     3 dB low on a wide mix and cancels out-of-phase content outright, so
     `process()` wants the channels as captured.
  3. L = -0.691 + 10*log10(power). The constant cancels K-weighting's gain at
     1 kHz, so a 1 kHz sine at -23 dBFS on both channels reads -23.0 LUFS.

  Momentary  -- the last 400 ms.  Short-term -- the last 3 s.
  Integrated -- everything since reset, gated: 400 ms blocks every 100 ms,
                drop blocks below -70 LUFS (absolute), then below 10 LU under
                the mean of what remains (relative). That is what keeps a quiet
                intro or a pause from dragging the figure down.

Each reading is -inf until its window has filled (and in true digital silence),
exactly as ffmpeg's `ebur128` filter holds off -- a 400 ms reading labelled
"3 s" would be a lie for the first three seconds.

Channel weights are all 1.0: right for mono and stereo, which is what a
microphone, an interface pair or a loopback delivers. (BS.1770 weights the
surround channels of 5.1 at 1.41 and ignores the LFE; nothing here captures
5.1.)

Ported from the Swift `LoudnessMeter` in the staff-infection PixelblazeSensor
package, which the Mac and iOS apps and its `pbsensor` CLI share.
"""

import cmath
import math
from typing import NamedTuple

import numpy as np


class Loudness(NamedTuple):
    """LUFS over the three windows the standard defines. -inf until filled."""

    momentary: float
    """LUFS over the last 400 ms."""
    shortTerm: float
    """LUFS over the last 3 s."""
    integrated: float
    """Gated LUFS since the meter was reset."""

    @staticmethod
    def text(lufs: float, width: int = 0) -> str:
        """"-14.2", or an em dash while a window hasn't filled, right-aligned."""
        s = f"{lufs:.1f}" if math.isfinite(lufs) else "—"
        return s if len(s) >= width else " " * (width - len(s)) + s


SILENT = Loudness(-math.inf, -math.inf, -math.inf)


class Biquad(NamedTuple):
    """One second-order section, normalized so a0 == 1."""

    b0: float
    b1: float
    b2: float
    a1: float
    a2: float


def k_weighting(sample_rate: float) -> tuple[Biquad, Biquad]:
    """BS.1770's two K-weighting stages, derived for any sample rate.

    Returns (pre, rlb): the high shelf, then the RLB high-pass. The RLB
    numerator is left unnormalized at 1, -2, 1 as tabulated -- the -0.691 in
    `lufs()` accounts for it.
    """
    fs = float(sample_rate)

    # Stage 1: high shelf.
    f0 = 1681.974450955533
    gain_db = 3.999843853973347
    q = 0.7071752369554196
    k = math.tan(math.pi * f0 / fs)
    vh = 10.0 ** (gain_db / 20.0)
    vb = vh ** 0.4996667741545416
    a0 = 1 + k / q + k * k
    pre = Biquad(
        b0=(vh + vb * k / q + k * k) / a0,
        b1=2 * (k * k - vh) / a0,
        b2=(vh - vb * k / q + k * k) / a0,
        a1=2 * (k * k - 1) / a0,
        a2=(1 - k / q + k * k) / a0,
    )

    # Stage 2: the RLB high-pass.
    f0 = 38.13547087602444
    q = 0.5003270373238773
    k = math.tan(math.pi * f0 / fs)
    a0 = 1 + k / q + k * k
    rlb = Biquad(b0=1.0, b1=-2.0, b2=1.0,
                 a1=2 * (k * k - 1) / a0,
                 a2=(1 - k / q + k * k) / a0)
    return pre, rlb


#: R128's absolute gate. Below it the standard says the content does not count
#: as programme at all, so it is where a reading stops being a number.
ABSOLUTE_GATE_LUFS = -70.0


def lufs(power: float) -> float:
    """Mean square of the K-weighted signal -> LUFS, or -inf for silence.

    Silence is anything under the absolute gate, not only an exact zero. Stop a
    track and the K-weighting filters ring down rather than snapping to nothing,
    so for a second afterwards the momentary power is a denormal and the honest
    logarithm of it is `-901.4 LUFS` -- a number that is both true and useless.
    Every R128 meter draws that as nothing, and so does this.
    """
    if power <= 0:
        return -math.inf
    value = -0.691 + 10 * math.log10(power)
    return value if value > ABSOLUTE_GATE_LUFS else -math.inf


class BiquadFilter:
    """A biquad applied to float64 blocks -- vectorized, and exact.

    numpy has no IIR primitive and scipy is not a dependency of this library,
    while a per-sample Python loop at 48 kHz costs several times the FFT it
    feeds. So the denominator is factored into its two poles, and each one-pole
    recursion is evaluated in closed form:

        y[n] = x[n] + p*y[n-1]   ==>   y = p**n * (p*s + cumsum(x * p**-k))

    which numpy does in two passes. p**-k grows without bound, so a block is
    walked in chunks short enough that it cannot overflow; inside a chunk the
    largest term of the cumsum is always the newest one, so multiplying p**n
    back leaves the error at an eps of the signal rather than of the scaling.
    `test_loudness.py` checks it against a literal per-sample loop.
    """

    # Largest p**-k any chunk may reach, as a power of ten. Far enough inside
    # float64's 1e308 that the cumsum has room above it.
    _HEADROOM_DECADES = 250

    def __init__(self, q: Biquad):
        self.q = q
        self.poles = self._poles(q.a1, q.a2)
        self.complex = any(isinstance(p, complex) for p in self.poles)
        smallest = min(abs(p) for p in self.poles)
        if smallest <= 0 or smallest >= 1:
            self.chunk = 2048
        else:
            decades = self._HEADROOM_DECADES * math.log(10) / -math.log(smallest)
            self.chunk = max(64, min(2048, int(decades)))
        self.reset()

    @staticmethod
    def _poles(a1: float, a2: float):
        """Roots of 1 + a1*z^-1 + a2*z^-2, real when they are."""
        disc = a1 * a1 - 4 * a2
        if disc >= 0:
            root = math.sqrt(disc)
            return ((-a1 + root) / 2, (-a1 - root) / 2)
        root = cmath.sqrt(complex(disc))
        return ((-a1 + root) / 2, (-a1 - root) / 2)

    def reset(self):
        self._x1 = 0.0
        self._x2 = 0.0
        self._pole_state = [0j if self.complex else 0.0 for _ in self.poles]

    def process(self, x: np.ndarray) -> np.ndarray:
        """Filter one block, carrying state across calls. Returns float64."""
        x = np.asarray(x, dtype=np.float64)
        n = x.size
        if n == 0:
            return x

        # Numerator, an FIR, with the previous block's last two samples.
        padded = np.empty(n + 2, dtype=np.float64)
        padded[0] = self._x2
        padded[1] = self._x1
        padded[2:] = x
        b0, b1, b2 = self.q.b0, self.q.b1, self.q.b2
        y = b0 * padded[2:] + b1 * padded[1:-1] + b2 * padded[:-2]
        if n >= 2:
            self._x1, self._x2 = float(x[-1]), float(x[-2])
        else:
            self._x1, self._x2 = float(x[-1]), self._x1

        if self.complex:
            y = y.astype(np.complex128)
        for i, p in enumerate(self.poles):
            y = self._one_pole(y, p, i)
        return y.real if self.complex else y

    def _one_pole(self, x: np.ndarray, p, index: int) -> np.ndarray:
        if p == 0:
            return x                      # y[n] = x[n]
        out = np.empty_like(x)
        state = self._pole_state[index]
        for start in range(0, x.size, self.chunk):
            seg = x[start:start + self.chunk]
            powers = p ** np.arange(seg.size)
            chunk_out = powers * (p * state + np.cumsum(seg / powers))
            out[start:start + seg.size] = chunk_out
            state = chunk_out[-1]
        self._pole_state[index] = state
        return out


class LoudnessMeter:
    """Momentary / short-term / integrated LUFS, fed whatever blocks arrive."""

    def __init__(self, sample_rate: float):
        self.sample_rate = float(sample_rate)
        self.pre_filter, self.rlb_filter = k_weighting(self.sample_rate)
        # 100 ms: the gating-block step, and the rate readings update at.
        self.hop = max(1, int(round(self.sample_rate / 10)))
        self.loudness = SILENT
        self.on_update = None
        """Called with the new Loudness every 100 ms of audio, on the caller's thread."""
        self._filters = []
        self.reset()

    def reset(self):
        for pre, rlb in self._filters:
            pre.reset()
            rlb.reset()
        self._hop_power = 0.0
        self._hop_fill = 0
        self._hops = [0.0] * 30          # 3 s of hop sums, a ring
        self._hop_count = 0
        self._hop_pos = 0
        self._blocks = []                # mean power of every 400 ms gating block
        self.loudness = SILENT

    def process(self, samples):
        """One block: (frames,) mono, or (frames, channels) as captured."""
        a = np.asarray(samples, dtype=np.float64)
        if a.ndim == 1:
            a = a[:, None]
        n, channels = a.shape
        if n == 0:
            return
        if len(self._filters) != channels:
            # A different device mid-stream: new filter memory, same windows.
            self._filters = [(BiquadFilter(self.pre_filter), BiquadFilter(self.rlb_filter))
                             for _ in range(channels)]

        # One NaN would poison a filter's memory forever.
        square = np.zeros(n)
        for c, (pre, rlb) in enumerate(self._filters):
            x = np.nan_to_num(a[:, c], nan=0.0, posinf=0.0, neginf=0.0)
            y = rlb.process(pre.process(x))
            square += y * y

        pos = 0
        while pos < n:
            take = min(self.hop - self._hop_fill, n - pos)
            self._hop_power += float(square[pos:pos + take].sum())
            self._hop_fill += take
            pos += take
            if self._hop_fill >= self.hop:
                self._finish_hop()

    def _window_power(self, hops: int):
        """Mean power over the last `hops` hops, or None until they exist."""
        if self._hop_count < hops:
            return None
        total = 0.0
        for k in range(1, hops + 1):
            total += self._hops[(self._hop_pos - k) % len(self._hops)]
        return total / (hops * self.hop)

    def _finish_hop(self):
        self._hops[self._hop_pos] = self._hop_power
        self._hop_pos = (self._hop_pos + 1) % len(self._hops)
        self._hop_count += 1
        self._hop_power = 0.0
        self._hop_fill = 0

        momentary, short_term, integrated = self.loudness
        window = self._window_power(4)
        if window is not None:
            momentary = lufs(window)
            # The momentary window IS the gating block: 400 ms, stepped every
            # 100 ms, which is the 75% overlap the standard asks for.
            self._blocks.append(window)
            integrated = self._integrated()
        window = self._window_power(30)
        if window is not None:
            short_term = lufs(window)

        self.loudness = Loudness(momentary, short_term, integrated)
        if self.on_update is not None:
            self.on_update(self.loudness)

    def _integrated(self) -> float:
        """A linear pass over every gating block. An hour is 36 000 of them,
        ten times a second, which is nothing next to the filtering above."""
        # -70 LUFS as a power, so the pass compares floats and never takes a log.
        absolute_gate = 10.0 ** ((-70 + 0.691) / 10)
        above = [b for b in self._blocks if b > absolute_gate]
        if not above:
            return -math.inf
        relative_gate = sum(above) / len(above) * 0.1        # -10 LU
        gated = [b for b in above if b > relative_gate]
        return lufs(sum(gated) / len(gated)) if gated else -math.inf
