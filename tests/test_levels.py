"""The input level check: too quiet, clipping, or fine."""

import numpy as np
import pytest

from vibemodem.io.levels import check_level


def noise(rms, size=48_000, seed=0):
    return np.random.default_rng(seed).normal(0.0, rms, size).clip(-1, 1)


def test_a_normal_level_raises_no_warning():
    report = check_level(noise(0.05))  # about -26 dBFS, a radio with its noise
    assert not report.clipping and not report.too_low and report.messages == []
    assert report.rms_dbfs == pytest.approx(-26, abs=0.5)
    assert 0.1 < report.peak < 0.4


def test_silence_is_too_low():
    report = check_level(np.zeros(48_000))
    assert report.too_low and not report.clipping
    assert report.rms_dbfs == -120.0  # a floor rather than minus infinity
    assert any("too low" in message for message in report.messages)


def test_a_signal_below_minus_50_dbfs_is_too_low_and_one_above_is_not():
    assert check_level(noise(10 ** (-55 / 20))).too_low
    assert not check_level(noise(10 ** (-45 / 20))).too_low


def test_a_few_samples_at_full_scale_are_not_clipping_but_many_are():
    samples = noise(0.05)
    samples[:20] = 1.0  # 20 of 48,000 samples: 0.04%
    assert not check_level(samples).clipping
    samples[:100] = 1.0  # 0.2%
    report = check_level(samples)
    assert report.clipping and any("clipping" in message for message in report.messages)


def test_negative_full_scale_counts_as_clipping_too():
    samples = noise(0.05)
    samples[:100] = -1.0
    assert check_level(samples).clipping


def test_a_loud_but_not_saturated_signal_is_fine():
    assert check_level(0.9 * np.sin(np.linspace(0, 2000, 48_000))).messages == []


@pytest.mark.parametrize("bad", [np.array([]), np.zeros((4, 2)), np.array([0.0, np.nan])])
def test_audio_that_cannot_be_measured_is_refused(bad):
    with pytest.raises(ValueError):
        check_level(bad)


def test_clipping_starts_at_exactly_one_sample_in_a_thousand():
    quiet = np.full(48_000, 0.05)
    at_boundary, below = quiet.copy(), quiet.copy()
    at_boundary[:48] = 0.99  # 48 in 48,000, and exactly at the level
    below[:47] = 0.99
    assert check_level(at_boundary).clipping and not check_level(below).clipping
    below[:48] = 0.9899
    assert not check_level(below).clipping
