"""The 8-FSK modems (baseline, LDPC, turbo): sync, CRC-32, nothing wrong delivered."""

import numpy as np
import pytest

from bench.channel import REFERENCE_BANDWIDTH_HZ, ChannelConfig, apply_channel
from vibemodem.core import baseline, mfsk
from vibemodem.core.baseline import MESSAGE_CAPACITY, BaselineModem
from vibemodem.core.ldpc_modem import LdpcModem
from vibemodem.core.turbo_modem import TurboModem

FS = 48_000


@pytest.fixture(params=[BaselineModem, LdpcModem, TurboModem], ids=["baseline", "ldpc", "turbo"])
def modem_class(request):
    return request.param


def hide_in_noise(modem, message, *, lead_in_s, offset_hz, snr_db, seed=1, tail_s=1.0):
    """The Transmission at a given moment and frequency shift, in a noisy recording."""
    transmission = modem.modulate(message, "standard")
    recording = np.concatenate(
        [np.zeros(round(lead_in_s * FS)), transmission, np.zeros(round(tail_s * FS))]
    )
    config = ChannelConfig(snr_db=snr_db, freq_offset_hz=offset_hz)
    return apply_channel(recording, config, seed, signal_power=float(np.mean(transmission**2)))


@pytest.mark.parametrize(
    "message",
    [b"", b"hello", bytes(range(MESSAGE_CAPACITY)), b"\x00" * MESSAGE_CAPACITY, b"\xff" * 20],
)
def test_a_message_survives_a_noiseless_round_trip(message, modem_class):
    modem = modem_class()
    receptions = modem.demodulate(modem.modulate(message, "standard"))
    assert [r.message for r in receptions] == [message]


def test_the_modem_uses_the_sample_rate_of_the_channel_simulator():
    assert baseline.SAMPLE_RATE == ChannelConfig().sample_rate


@pytest.mark.parametrize(
    "lead_in_s, offset_hz",
    [(0.0, 0), (3.7, 0), (6.123, -900), (1.0, 850), (0.01, 400), (9.99, -1100)],
)
def test_the_signal_is_found_at_any_start_time_and_audio_frequency(
    lead_in_s, offset_hz, modem_class
):
    modem = modem_class()
    audio = hide_in_noise(
        modem, b"Hello, world", lead_in_s=lead_in_s, offset_hz=offset_hz, snr_db=0
    )
    (reception,) = modem.demodulate(audio)
    assert reception.message == b"Hello, world"
    assert reception.frequency_offset_hz == pytest.approx(offset_hz, abs=2.0)


def test_a_reception_reports_how_well_it_was_received(modem_class):
    modem = modem_class()
    audio = hide_in_noise(modem, b"metrics", lead_in_s=2.0, offset_hz=100, snr_db=-6)
    (reception,) = modem.demodulate(audio)
    assert reception.snr_db == pytest.approx(-6, abs=3)
    assert reception.sync_score is not None and reception.sync_score > 7


def test_a_message_longer_than_a_frame_is_refused_with_a_reason(modem_class):
    with pytest.raises(ValueError, match="Fragment"):
        modem_class().modulate(b"x" * (MESSAGE_CAPACITY + 1), "standard")


def test_an_unknown_preset_is_refused(modem_class):
    with pytest.raises(ValueError, match="Preset"):
        modem_class().modulate(b"hi", "maximum range")


def noise(seconds, seed, level=0.3):
    return np.random.default_rng(seed).normal(0.0, level, round(seconds * FS))


SYMBOL = mfsk.SAMPLES_PER_SYMBOL
DATA_START = mfsk.PREAMBLE_SYMBOLS * SYMBOL


@pytest.mark.parametrize("seed", range(6))
def test_noise_alone_never_produces_a_message(seed, modem_class):
    assert modem_class().demodulate(noise(16, seed)) == []


@pytest.mark.parametrize("length", [0, 1, 1000, 100_000])
def test_audio_too_short_to_hold_a_transmission_gives_nothing(length, modem_class):
    assert modem_class().demodulate(np.zeros(length)) == []


def test_a_transmission_cut_short_gives_nothing(modem_class):
    modem = modem_class()
    audio = modem.modulate(b"cut off", "standard")
    assert modem.demodulate(audio[: -20 * SYMBOL]) == []


def test_heavily_damaged_audio_is_dropped_not_guessed(modem_class):
    modem = modem_class()
    audio = modem.modulate(b"damaged", "standard")
    start = DATA_START + 20 * SYMBOL
    audio[start : start + 60 * SYMBOL] = noise(60 * SYMBOL / FS, seed=3, level=1.0)
    assert modem.demodulate(audio) == []


@pytest.mark.parametrize("seed", range(8))
def test_damage_never_turns_one_message_into_another(seed, modem_class):
    modem = modem_class()
    audio = modem.modulate(b"original", "standard")
    rng = np.random.default_rng(seed)
    for _ in range(3):  # a few bursts of loud noise at random places in the data
        start = DATA_START + int(rng.integers(0, 120)) * SYMBOL
        audio[start : start + 12 * SYMBOL] = rng.normal(0, 0.6, 12 * SYMBOL)
    assert [r.message for r in modem.demodulate(audio)] in ([], [b"original"])


def test_two_different_transmissions_spliced_together_give_no_message(modem_class):
    modem = modem_class()
    first = modem.modulate(b"first message", "standard")
    second = modem.modulate(b"second message", "standard")
    cut = DATA_START + 70 * SYMBOL
    assert modem.demodulate(np.concatenate([first[:cut], second[cut:]])) == []


def test_audio_that_is_not_a_single_channel_is_refused(modem_class):
    with pytest.raises(ValueError, match="one channel"):
        modem_class().demodulate(np.zeros((2, 100_000)))


def test_audio_with_samples_that_are_not_numbers_is_refused(modem_class):
    audio = np.zeros(20 * FS)
    audio[5] = np.nan
    with pytest.raises(ValueError, match="finite"):
        modem_class().demodulate(audio)


def test_a_recording_beyond_the_length_limit_is_refused_before_any_work_is_done(modem_class):
    too_long = np.broadcast_to(np.zeros(1), (round((baseline.MAX_RECORDING_SECONDS + 1) * FS),))
    with pytest.raises(ValueError, match="too long"):
        modem_class().demodulate(too_long)


def test_the_noise_bandwidth_is_the_one_the_bench_uses():
    assert baseline.NOISE_BANDWIDTH_HZ == REFERENCE_BANDWIDTH_HZ


def test_the_tables_every_modem_shares_cannot_be_modified():
    assert not mfsk.PREAMBLE_TONES.flags.writeable
