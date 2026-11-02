"""The GFSK modem: tunable modulation index, Gaussian filter and baud rate."""

import numpy as np
import pytest

from bench.bandwidth import occupied_band
from bench.channel import ChannelConfig, apply_channel
from vibemodem.core import gfsk
from vibemodem.core.coded_gfsk import CodedGfskModem
from vibemodem.core.convolutional import ConvolutionalCode
from vibemodem.core.frame import FRAME_BITS
from vibemodem.core.gfsk_modem import GfskModem

FS = gfsk.SAMPLE_RATE


def record(modem, message, snr_db=0.0, lead_s=1.5, offset_hz=0.0):
    transmission = modem.modulate(message, "standard")
    power = float(np.mean(transmission**2))
    recording = np.concatenate([np.zeros(round(lead_s * FS)), transmission, np.zeros(FS)])
    return apply_channel(
        recording,
        ChannelConfig(snr_db=snr_db, freq_offset_hz=offset_hz),
        seed=1,
        signal_power=power,
    )


def instantaneous_frequency(samples):
    analytic = np.angle(
        np.fft.ifft(np.fft.fft(samples) * (np.arange(samples.size) < samples.size // 2) * 2)
    )
    return np.diff(np.unwrap(analytic)) * FS / (2 * np.pi)


def test_without_a_filter_the_frequency_is_the_carrier_plus_or_minus_half_h_times_baud():
    waveform = gfsk.Waveform(baud=50, h=1.0, bt=None)
    audio = waveform.synthesize(np.array([0, 1, 0, 1]))
    frequency = instantaneous_frequency(audio)
    size = waveform.samples_per_bit
    middles = [frequency[k * size + size // 4 : k * size + 3 * size // 4].mean() for k in range(4)]
    centre = gfsk.CARRIER_HZ
    assert middles == pytest.approx([centre + 25, centre - 25] * 2, abs=1.0)


def test_the_envelope_is_constant():
    audio = gfsk.Waveform(baud=50, h=0.5, bt=0.5).synthesize(np.array([0, 1, 1, 0, 1]))
    assert audio.max() == pytest.approx(gfsk.AMPLITUDE, rel=1e-3)
    assert np.sqrt(np.mean(audio**2)) == pytest.approx(gfsk.AMPLITUDE / np.sqrt(2), rel=0.02)


@pytest.mark.parametrize(
    "bad",
    [{"baud": 0}, {"baud": 33}, {"h": 0}, {"h": -0.5}, {"bt": 0}, {"bt": -1}, {"h": float("nan")}],
)
def test_a_waveform_the_receiver_cannot_search_is_refused(bad):
    with pytest.raises(ValueError):
        gfsk.Waveform(**bad)


@pytest.mark.parametrize(
    "baud, h, bt",
    [(50, 0.5, 0.5), (50, 1.0, None), (25, 1.0, 0.3), (100, 0.5, 0.3), (50, 0.7, 0.5)],
)
def test_a_message_is_received_through_noise_at_a_shifted_frequency(baud, h, bt):
    modem = GfskModem(baud=baud, h=h, bt=bt)
    (reception,) = modem.demodulate(record(modem, b"gfsk!", snr_db=-3, offset_hz=-640))
    assert reception.message == b"gfsk!"
    assert reception.frequency_offset_hz == pytest.approx(-640, abs=5)
    assert reception.snr_db == pytest.approx(-3, abs=4)


def test_pure_noise_gives_nothing():
    modem = GfskModem()
    noise = np.random.default_rng(3).normal(0, 0.1, 15 * FS)
    assert modem.demodulate(noise) == []


def test_the_parameters_are_recorded_for_the_result_file():
    modem = GfskModem(baud=25, h=0.7, bt=None, interleave=True, repetitions=2)
    assert modem.parameters == {
        "baud": 25,
        "h": 0.7,
        "bt": None,
        "interleave": True,
        "repetitions": 2,
    }


def test_it_works_with_any_code_of_the_shared_interface():
    modem = CodedGfskModem(ConvolutionalCode(FRAME_BITS), baud=50, h=1.0, bt=0.5)
    (reception,) = modem.demodulate(record(modem, b"any code", snr_db=2))
    assert reception.message == b"any code"


@pytest.mark.parametrize("interleave, repetitions", [(True, 1), (False, 2), (True, 2)])
def test_interleaving_and_repetition_carry_over(interleave, repetitions):
    modem = GfskModem(interleave=interleave, repetitions=repetitions)
    (reception,) = modem.demodulate(record(modem, b"opts", snr_db=0))
    assert reception.message == b"opts"


def test_a_transmission_lasts_its_bits_at_the_baud_rate():
    modem = GfskModem(baud=50)
    seconds = modem.modulate(b"x", "standard").size / FS
    expected = (gfsk.PREAMBLE_SECONDS * 50 + modem.code.coded_bits) / 50
    assert seconds == pytest.approx(expected, abs=0.1)


def test_a_narrower_filter_occupies_a_narrower_band():
    def band(bt):
        audio = GfskModem(baud=50, h=0.5, bt=bt).modulate(b"width test", "standard")
        low, high = occupied_band(audio, FS, 20.0)
        return high - low

    assert band(0.3) < band(0.5) < band(None)


def test_a_smaller_baud_rate_occupies_a_narrower_band():
    def band(baud):
        audio = GfskModem(baud=baud, h=0.5, bt=0.5).modulate(b"width test", "standard")
        low, high = occupied_band(audio, FS, 20.0)
        return high - low

    assert band(25) < band(50) < band(100)


def test_a_known_preamble_is_found_before_the_data_is_read_in_a_noisy_recording():
    waveform = gfsk.Waveform(baud=50, h=0.5, bt=0.5)
    audio = waveform.synthesize(waveform.preamble_bits)
    recording = np.concatenate([np.zeros(round(1.234 * FS)), audio, np.zeros(FS)])
    noisy = apply_channel(
        recording,
        ChannelConfig(snr_db=-6, freq_offset_hz=300),
        seed=2,
        signal_power=float(np.mean(audio**2)),
    )
    work = waveform.decimate(noisy)
    (found, *_) = waveform.find_signals(work)
    found = waveform.refine(work, found)
    assert abs(found.start_sample - round(1.234 * FS)) < waveform.samples_per_bit // 4
    assert found.carrier_hz == pytest.approx(gfsk.CARRIER_HZ + 300, abs=6)
