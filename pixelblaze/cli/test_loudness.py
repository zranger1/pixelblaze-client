#!/usr/bin/env python3
"""Unit tests for the LUFS meter. No audio hardware, no Pixelblaze.

    python3 -m pytest pixelblaze/cli/test_loudness.py
"""

import math

import numpy as np
import pytest

from pixelblaze.cli.loudness import (SILENT, BiquadFilter, Loudness, LoudnessMeter,
                                     k_weighting, lufs)

# The coefficients BS.1770-4 tabulates, for 48 kHz only. k_weighting() derives
# them from the analog prototypes at any rate; at 48 kHz it must land on these.
TABLE_48K_PRE = (1.53512485958697, -2.69169618940638, 1.19839281085285,
                 -1.69065929318241, 0.73248077421585)
TABLE_48K_RLB = (1.0, -2.0, 1.0, -1.99004745483398, 0.99007225036621)


def test_k_weighting_reproduces_the_48k_table():
    pre, rlb = k_weighting(48000)
    assert pre == pytest.approx(TABLE_48K_PRE, abs=1e-11)
    assert rlb == pytest.approx(TABLE_48K_RLB, abs=1e-11)


def test_k_weighting_is_defined_at_every_rate_a_device_might_report():
    for rate in (8000, 22050, 44100, 48000, 88200, 96000, 192000):
        pre, rlb = k_weighting(rate)
        for q in (pre, rlb):
            assert all(math.isfinite(c) for c in q)
            # Stable: both poles strictly inside the unit circle.
            assert abs(q.a2) < 1


def _naive(q, x):
    """The same biquad as a literal per-sample loop, transposed direct form II."""
    out = np.empty(len(x))
    z1 = z2 = 0.0
    for i, sample in enumerate(x):
        y = q.b0 * sample + z1
        z1 = q.b1 * sample - q.a1 * y + z2
        z2 = q.b2 * sample - q.a2 * y
        out[i] = y
    return out


@pytest.mark.parametrize("rate", [44100, 48000])
def test_vectorised_biquad_matches_a_per_sample_loop(rate):
    """The cumsum factorisation is exact, including across block boundaries."""
    rng = np.random.default_rng(7)
    signal = rng.standard_normal(5000)
    for q in k_weighting(rate):
        expected = _naive(q, signal)
        # Ragged blocks: state has to carry, and one of these is shorter than
        # the internal chunk while another is longer.
        f = BiquadFilter(q)
        actual = np.concatenate([f.process(signal[a:b]) for a, b in
                                 ((0, 1), (1, 3), (3, 1024), (1024, 3000), (3000, 5000))])
        assert actual == pytest.approx(expected, abs=1e-9, rel=1e-9)


def _sine(hz, seconds, rate, amplitude, channels=2):
    t = np.arange(int(seconds * rate)) / rate
    wave = amplitude * np.sin(2 * math.pi * hz * t)
    return np.repeat(wave[:, None], channels, axis=1)


def test_a_1khz_sine_at_minus_23_dbfs_reads_minus_23_lufs():
    """The calibration the standard is written around."""
    rate = 48000
    meter = LoudnessMeter(rate)
    block = _sine(1000, 5.0, rate, 10 ** (-23 / 20), channels=2)
    for start in range(0, len(block), 1024):
        meter.process(block[start:start + 1024])

    assert meter.loudness.momentary == pytest.approx(-23.0, abs=0.1)
    assert meter.loudness.shortTerm == pytest.approx(-23.0, abs=0.1)
    assert meter.loudness.integrated == pytest.approx(-23.0, abs=0.1)


def test_one_channel_of_the_same_sine_is_3_db_quieter():
    """Channel POWER is summed, not averaged -- that is the whole point."""
    rate = 48000
    meter = LoudnessMeter(rate)
    meter.process(_sine(1000, 4.0, rate, 10 ** (-23 / 20), channels=1))
    assert meter.loudness.momentary == pytest.approx(-26.0, abs=0.1)


def test_readings_hold_off_until_their_window_has_filled():
    """A 400 ms figure labelled "3 s" would be a lie for the first three seconds."""
    rate = 48000
    meter = LoudnessMeter(rate)
    assert meter.loudness == SILENT

    meter.process(_sine(1000, 0.35, rate, 0.5))
    assert meter.loudness == SILENT, "nothing before the first 400 ms block"

    meter.process(_sine(1000, 0.2, rate, 0.5))
    assert math.isfinite(meter.loudness.momentary)
    assert meter.loudness.shortTerm == -math.inf, "3 s window is not full yet"

    meter.process(_sine(1000, 3.0, rate, 0.5))
    assert math.isfinite(meter.loudness.shortTerm)


def test_digital_silence_is_minus_infinity_not_a_very_small_number():
    meter = LoudnessMeter(48000)
    meter.process(np.zeros((48000 * 4, 2)))
    assert meter.loudness == SILENT
    assert lufs(0.0) == -math.inf


def test_a_filter_ringing_down_after_the_music_stops_reads_as_silence():
    """Pause a track and the K-weighting filters decay rather than snapping to
    zero, so the momentary power spends a second as a denormal. Reported
    honestly that is `-901.4 LUFS`, which is no use to anybody -- R128's
    absolute gate is where a reading stops being a number."""
    rate = 48000
    meter = LoudnessMeter(rate)
    meter.process(_sine(1000, 1.0, rate, 10 ** (-23 / 20)))
    assert meter.loudness.momentary == pytest.approx(-23, abs=0.5)

    meter.process(np.zeros((rate // 2, 2)))
    assert meter.loudness.momentary == -math.inf, "a decaying tail is not a level"

    assert lufs(10 ** ((-69 + 0.691) / 10)) == pytest.approx(-69, abs=0.01)
    assert lufs(10 ** ((-71 + 0.691) / 10)) == -math.inf


def test_the_gate_keeps_a_long_pause_from_dragging_the_integrated_figure_down():
    """-70 LUFS absolute, then -10 LU relative: EBU R128's whole purpose."""
    rate = 48000
    meter = LoudnessMeter(rate)
    meter.process(_sine(1000, 4.0, rate, 10 ** (-23 / 20)))
    while_playing = meter.loudness.integrated
    meter.process(np.zeros((rate * 20, 2)))

    assert meter.loudness.momentary == -math.inf, "silence now"
    # Not bit-identical: the three 400 ms blocks straddling the cut are part
    # sine and stay above the gate, which is correct and worth a tenth or two.
    assert meter.loudness.integrated == pytest.approx(while_playing, abs=0.3), \
        "20 s of silence must not move the gated figure"

    # And the gate is what did it: averaging every block would read far lower.
    ungated = lufs(sum(meter._blocks) / len(meter._blocks))
    assert ungated < meter.loudness.integrated - 5


def test_reset_clears_the_windows_and_the_filter_memory():
    rate = 48000
    meter = LoudnessMeter(rate)
    meter.process(_sine(1000, 4.0, rate, 0.5))
    assert math.isfinite(meter.loudness.integrated)
    meter.reset()
    assert meter.loudness == SILENT
    meter.process(np.zeros((rate, 2)))
    assert meter.loudness == SILENT, "no ringing left over from the loud pass"


def test_on_update_fires_every_100ms_of_audio():
    rate = 48000
    meter = LoudnessMeter(rate)
    seen = []
    meter.on_update = seen.append
    meter.process(_sine(1000, 1.0, rate, 0.25))
    assert len(seen) == 10
    assert all(isinstance(l, Loudness) for l in seen)


def test_text_right_aligns_and_says_em_dash_before_a_window_fills():
    assert Loudness.text(-14.23, width=5) == "-14.2"
    assert Loudness.text(-9.0, width=5) == " -9.0"
    assert Loudness.text(-math.inf, width=5) == "    —"
    assert Loudness.text(-math.inf) == "—"


def test_a_nan_from_a_wedged_input_does_not_poison_the_filter():
    rate = 48000
    meter = LoudnessMeter(rate)
    bad = _sine(1000, 0.5, rate, 0.5)
    bad[100, 0] = math.nan
    bad[200, 1] = math.inf
    meter.process(bad)
    meter.process(_sine(1000, 4.0, rate, 10 ** (-23 / 20)))
    assert meter.loudness.momentary == pytest.approx(-23.0, abs=0.1)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
