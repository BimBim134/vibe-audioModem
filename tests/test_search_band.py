"""The audio band the receiver listens in: a Signal is read only if all of it is inside."""

import numpy as np
import pytest

from vibemodem.core import mfsk, presets
from vibemodem.core.turbo_modem import TurboModem

FS = mfsk.SAMPLE_RATE
# A fast Signal sent as is has its eight tones, 25 Hz apart, from 1450 to 1625 Hz.


@pytest.fixture(scope="module")
def heard():
    modem = TurboModem(preset="fast")
    quiet = np.zeros(2 * FS)
    return np.concatenate([quiet, modem.modulate(b"in band", "fast"), quiet])


def listen(heard, band):
    modem = TurboModem(preset="fast")
    modem.search_band_hz = band
    return modem.demodulate_report(heard)


def test_a_signal_inside_the_band_is_read(heard):
    assert [r.message for r in listen(heard, (1000.0, 2000.0)).receptions] == [b"in band"]


def test_no_band_is_the_whole_audio_band(heard):
    assert [r.message for r in listen(heard, None).receptions] == [b"in band"]


@pytest.mark.parametrize(
    "band",
    [(300.0, 1400.0), (1700.0, 2700.0), (1550.0, 2700.0), (300.0, 1550.0)],
    ids=["below", "above", "cut at the low tones", "cut at the high tones"],
)
def test_a_signal_not_entirely_inside_the_band_is_ignored(heard, band):
    report = listen(heard, band)
    assert report.receptions == [] and report.undecoded == [] and report.arriving == []


def test_the_narrowest_band_that_holds_a_preset_is_its_tones_span():
    assert presets.minimum_band_hz("fast") == pytest.approx(175.0)
    assert presets.minimum_band_hz("max-range") == pytest.approx(7 / 0.32)
