"""Where in the audio band a Signal is sent: the frequency of its lowest tone."""

import numpy as np
import pytest

from bench.channel import ChannelConfig, apply_channel
from vibemodem.core import mfsk, presets
from vibemodem.core.turbo_modem import TurboModem

FS = mfsk.SAMPLE_RATE


@pytest.mark.parametrize(
    "preset, low, high",
    [("max-range", 306.25, 2671.875), ("standard", 325.0, 2587.5), ("fast", 350.0, 2475.0)],
)
def test_each_preset_may_be_sent_where_its_whole_signal_fits_with_two_tone_spacings_to_spare(
    preset, low, high
):
    assert presets.frequency_range_hz(preset) == (low, high)


def test_the_default_frequency_is_inside_every_range():
    for name in presets.PRESETS:
        low, high = presets.frequency_range_hz(name)
        assert low <= mfsk.FIRST_TONE_HZ <= high


@pytest.mark.parametrize("hz", [100.0, 324.0, 2588.0, 3000.0, float("nan"), float("inf")])
def test_a_waveform_that_would_leave_the_band_is_refused(hz):
    with pytest.raises(ValueError, match="first tone"):
        mfsk.Waveform(first_tone_hz=hz)


def test_the_lowest_tone_is_sent_at_the_frequency_asked_for():
    waveform = mfsk.Waveform(first_tone_hz=900.0)
    sound = waveform.synthesize(np.zeros(40, dtype=int))  # only the lowest tone
    spectrum = np.abs(np.fft.rfft(sound))
    assert np.fft.rfftfreq(sound.size, 1 / FS)[np.argmax(spectrum)] == pytest.approx(900.0, abs=1.0)


@pytest.mark.parametrize("preset", list(presets.PRESETS))
def test_a_message_is_received_at_either_end_of_the_range_of_each_preset(preset):
    low, high = presets.frequency_range_hz(preset)
    for first_tone_hz in (low, high):
        modem = TurboModem(preset=preset, first_tone_hz=first_tone_hz)
        sound = modem.modulate(b"band edge", preset)
        recording = np.concatenate([np.zeros(FS), sound, np.zeros(FS)])
        noisy = apply_channel(
            recording, ChannelConfig(snr_db=0.0), seed=3, signal_power=float(np.mean(sound**2))
        )
        (heard,) = TurboModem(preset=preset).demodulate(noisy)  # the receiver is not told
        assert heard.message == b"band edge"
        assert heard.frequency_offset_hz == pytest.approx(first_tone_hz - mfsk.FIRST_TONE_HZ, abs=3)


def test_the_signal_stays_inside_the_audio_band_at_the_ends_of_the_range():
    from bench.bandwidth import occupied_band

    for preset in presets.PRESETS:
        low, high = presets.frequency_range_hz(preset)
        for first_tone_hz in (low, high):
            modem = TurboModem(preset=preset, first_tone_hz=first_tone_hz)
            band = occupied_band(modem.modulate(b"in the band", preset), FS, drop_db=20.0)
            assert 300.0 <= band[0] and band[1] <= 2700.0, (preset, first_tone_hz, band)
