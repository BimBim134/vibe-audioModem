"""The options of the M-FSK modems: waveform, interleaving of the coded bits, repetition."""

import numpy as np
import pytest

from bench.channel import ChannelConfig, apply_channel
from vibemodem.core import mfsk
from vibemodem.core.baseline import BaselineModem
from vibemodem.core.coded_mfsk import MAX_REPETITIONS, _send_order
from vibemodem.core.turbo_modem import TurboModem

FS = mfsk.SAMPLE_RATE
PREAMBLE = mfsk.PREAMBLE_SYMBOLS


def record(modem, message, burst=None, snr_db=0.0):
    """The Transmission in a noisy recording, with `burst` = (first data symbol, symbols) lost."""
    transmission = modem.modulate(message, "standard")
    power = float(np.mean(transmission**2))
    if burst:
        size = modem.waveform.samples_per_symbol
        start, end = (PREAMBLE + burst[0]) * size, (PREAMBLE + burst[0] + burst[1]) * size
        transmission = transmission.copy()
        transmission[start:end] = np.random.default_rng(5).normal(0.0, 1.0, end - start)
    recording = np.concatenate([np.zeros(2 * FS), transmission, np.zeros(FS)])
    return apply_channel(recording, ChannelConfig(snr_db=snr_db), seed=1, signal_power=power)


@pytest.mark.parametrize("tones, symbol_ms", [(2, 160), (4, 80), (16, 80), (8, 40), (4, 320)])
@pytest.mark.parametrize("modem_class", [BaselineModem, TurboModem])
def test_a_message_is_received_at_any_waveform(modem_class, tones, symbol_ms):
    modem = modem_class(tones=tones, symbol_ms=symbol_ms)
    (reception,) = modem.demodulate(record(modem, b"sweep"))
    assert reception.message == b"sweep"


@pytest.mark.parametrize("interleave, repetitions", [(True, 1), (False, 2), (True, 2), (True, 3)])
def test_a_message_survives_a_noiseless_round_trip_with_interleaving_and_repetition(
    interleave, repetitions
):
    modem = BaselineModem(interleave=interleave, repetitions=repetitions)
    (reception,) = modem.demodulate(modem.modulate(b"spread", "standard"))
    assert reception.message == b"spread"


def test_a_repeated_message_lasts_for_all_its_copies():
    one = BaselineModem().modulate(b"x", "standard").size
    two = BaselineModem(repetitions=2).modulate(b"x", "standard").size
    symbols = lambda size: size // mfsk.STANDARD.samples_per_symbol  # noqa: E731
    assert symbols(one) == PREAMBLE + 138  # 412 bits in 3 bits per symbol
    assert symbols(two) == PREAMBLE + 275  # 824 bits


def test_interleaving_changes_the_order_of_the_symbols_not_their_number():
    plain = BaselineModem().modulate(b"x", "standard")
    spread = BaselineModem(interleave=True).modulate(b"x", "standard")
    assert plain.size == spread.size
    assert not np.allclose(plain, spread)
    size = mfsk.STANDARD.samples_per_symbol
    assert np.allclose(plain[: PREAMBLE * size], spread[: PREAMBLE * size])  # same preamble


@pytest.mark.parametrize("count", [1, 2, 7, 400, 412, 462])
@pytest.mark.parametrize("copy", [0, 1, 2])
def test_every_coded_bit_is_sent_exactly_once_in_each_copy(count, copy):
    order = _send_order(count, copy, interleave=True)
    assert sorted(order.tolist()) == list(range(count))


def test_without_interleaving_the_bits_are_sent_in_the_order_of_the_code():
    assert _send_order(10, 0, interleave=False).tolist() == list(range(10))


def test_interleaving_puts_neighbouring_bits_far_apart_and_each_copy_differently():
    first, second = (_send_order(412, copy, interleave=True) for copy in (0, 1))
    gaps = np.abs(np.diff(first.astype(int)))
    assert gaps.min() > 40
    assert not np.array_equal(first, second)


def test_a_burst_that_defeats_the_plain_code_is_survived_when_interleaved():
    # 30 symbols in a row are lost: 90 consecutive coded bits, a fifth of the code word.
    plain, spread = BaselineModem(), BaselineModem(interleave=True)
    assert plain.demodulate(record(plain, b"burst", burst=(50, 30))) == []
    received = spread.demodulate(record(spread, b"burst", burst=(50, 30)))
    assert [r.message for r in received] == [b"burst"]


def test_a_second_copy_makes_up_for_a_lost_first_one():
    modem = BaselineModem(repetitions=2)
    received = modem.demodulate(record(modem, b"twice", burst=(0, 138)))
    assert [r.message for r in received] == [b"twice"]
    single = BaselineModem()
    assert single.demodulate(record(single, b"twice", burst=(0, 138))) == []


def test_the_options_are_reported_for_the_result_files():
    modem = TurboModem(tones=4, symbol_ms=160, interleave=True, repetitions=2)
    assert modem.parameters == {
        "tones": 4,
        "symbol_ms": 160.0,
        "interleave": True,
        "repetitions": 2,
    }


@pytest.mark.parametrize("repetitions", [0, -1, MAX_REPETITIONS + 1, 2.0, "2"])
def test_a_number_of_repetitions_that_makes_no_sense_is_refused(repetitions):
    with pytest.raises(ValueError, match="repetitions"):
        BaselineModem(repetitions=repetitions)


@pytest.mark.parametrize("interleave", [1, "yes", None])
def test_interleave_must_be_true_or_false(interleave):
    with pytest.raises(ValueError, match="interleave"):
        BaselineModem(interleave=interleave)


def test_a_waveform_the_receiver_cannot_search_is_refused_by_the_modem():
    with pytest.raises(ValueError, match="tones"):
        BaselineModem(tones=5)
    with pytest.raises(ValueError, match="symbol"):
        BaselineModem(symbol_ms=0.5)
