"""One row of the spectrum of a block of sound, to draw a spectrum and a waterfall."""

import numpy as np
import pytest

from vibemodem.core.spectrum import BAND_HZ, BIN_HZ, BINS, SILENCE_DB, spectrum_row

FS = 48_000


def tone(hz, seconds=0.5, level=0.5):
    return level * np.sin(2 * np.pi * hz * np.arange(round(seconds * FS)) / FS)


def test_a_row_covers_the_audio_band_in_bins_of_5_hz():
    assert (BAND_HZ, BIN_HZ, BINS) == ((300.0, 2700.0), 5.0, 480)
    assert spectrum_row(tone(1000)).shape == (480,)


@pytest.mark.parametrize("hz", [350.0, 1000.0, 1234.0, 2650.0])
def test_a_tone_is_the_loudest_bin_at_its_frequency(hz):
    row = spectrum_row(tone(hz))
    loudest = BAND_HZ[0] + BIN_HZ * (int(np.argmax(row)) + 0.5)
    assert abs(loudest - hz) <= BIN_HZ
    assert row.max() - np.median(row) > 40  # it stands well above the rest


def test_the_level_is_in_decibels_and_follows_the_loudness():
    quiet, loud = spectrum_row(tone(1000, level=0.01)), spectrum_row(tone(1000, level=1.0))
    assert loud.max() - quiet.max() == pytest.approx(40.0, abs=0.5)


def test_silence_is_a_floor_not_minus_infinity():
    row = spectrum_row(np.zeros(FS // 2))
    assert np.isfinite(row).all() and (row == SILENCE_DB).all()


def test_white_noise_is_flat_to_within_a_few_decibels():
    row = spectrum_row(np.random.default_rng(0).normal(0, 0.1, FS))  # 1 s of noise
    assert row.std() < 3.0


def test_a_block_of_any_length_gives_a_row():
    assert spectrum_row(tone(1000, seconds=0.1)).shape == (480,)
    assert spectrum_row(tone(1000, seconds=2.0)).shape == (480,)


@pytest.mark.parametrize(
    "bad", [np.zeros(0), np.zeros((4, 2)), np.array([0.0, np.nan]), np.zeros(10)]
)
def test_a_block_that_cannot_be_measured_is_refused(bad):
    with pytest.raises(ValueError):
        spectrum_row(bad)
