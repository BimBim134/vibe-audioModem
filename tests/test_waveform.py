"""The M-FSK waveform with adjustable tones and symbol duration."""

import hashlib

import numpy as np
import pytest

from bench.channel import ChannelConfig, apply_channel
from vibemodem.core import mfsk
from vibemodem.core.baseline import BaselineModem
from vibemodem.core.turbo_modem import TurboModem

FS = mfsk.SAMPLE_RATE


def digest(samples: np.ndarray) -> str:
    return hashlib.sha256(np.round(samples * 1e6).astype(np.int64).tobytes()).hexdigest()[:16]


@pytest.mark.parametrize(
    "modem_class, expected",
    [(BaselineModem, "d13a99a184162ecd"), (TurboModem, "d935404d6cb3dc95")],
)
def test_the_default_waveform_is_the_one_measured_before_it_became_adjustable(
    modem_class, expected
):
    assert digest(modem_class().modulate(b"hello", "standard")) == expected


def test_the_default_waveform_is_8_tones_of_80_ms_spaced_12_5_hz():
    waveform = mfsk.STANDARD
    assert (waveform.tones, waveform.bits_per_symbol) == (8, 3)
    assert waveform.spacing_hz == pytest.approx(12.5)
    assert waveform.samples_per_symbol == 3840


@pytest.mark.parametrize(
    "tones, symbol_seconds, bits, spacing, samples",
    [(2, 0.32, 1, 3.125, 15360), (4, 0.16, 2, 6.25, 7680), (16, 0.04, 4, 25.0, 1920)],
)
def test_the_tone_spacing_follows_the_symbol_duration(
    tones, symbol_seconds, bits, spacing, samples
):
    waveform = mfsk.Waveform(tones=tones, symbol_seconds=symbol_seconds)
    assert waveform.bits_per_symbol == bits
    assert waveform.spacing_hz == pytest.approx(spacing)
    assert waveform.samples_per_symbol == samples


@pytest.mark.parametrize("tones", [0, 1, 3, 6, 32, 64])
def test_a_number_of_tones_other_than_2_4_8_or_16_is_refused(tones):
    with pytest.raises(ValueError, match="tones"):
        mfsk.Waveform(tones=tones)


@pytest.mark.parametrize("symbol_seconds", [0.0, -0.08, 0.0123, 0.001, 1.5])
def test_a_symbol_duration_the_receiver_cannot_search_is_refused(symbol_seconds):
    with pytest.raises(ValueError, match="symbol"):
        mfsk.Waveform(symbol_seconds=symbol_seconds)


@pytest.mark.parametrize("tones, symbol_seconds", [(2, 0.16), (4, 0.08), (16, 0.08), (8, 0.04)])
def test_every_tone_is_measured_where_it_was_sent(tones, symbol_seconds):
    waveform = mfsk.Waveform(tones=tones, symbol_seconds=symbol_seconds)
    sent = np.arange(tones)
    audio = waveform.synthesize(sent)
    energy = waveform.tone_energies(audio, 0, mfsk.FIRST_TONE_HZ, tones)
    assert (energy.argmax(axis=1) == sent).all()
    assert (energy.max(axis=1) > 100 * np.sort(energy, axis=1)[:, -2]).all()


@pytest.mark.parametrize("tones, symbol_seconds", [(2, 0.16), (4, 0.08), (16, 0.08), (8, 0.04)])
def test_the_preamble_is_found_at_any_start_and_frequency(tones, symbol_seconds):
    waveform = mfsk.Waveform(tones=tones, symbol_seconds=symbol_seconds)
    transmission = waveform.synthesize(waveform.preamble_tones)
    lead_in = round(1.234 * FS)
    recording = np.concatenate([np.zeros(lead_in), transmission, np.zeros(FS)])
    shifted = apply_channel(
        recording,
        ChannelConfig(snr_db=0, freq_offset_hz=-700),
        1,
        signal_power=float(np.mean(transmission**2)),
    )
    (found, *_) = waveform.find_signals(shifted)
    found = waveform.refine(shifted, found)
    assert found.first_tone_hz == pytest.approx(mfsk.FIRST_TONE_HZ - 700, abs=2.0)
    assert abs(found.start_sample - lead_in) < waveform.samples_per_symbol // 8
