"""What is specific to the turbo code: its encoder, its interleaver and its stability."""

import hashlib

import numpy as np
import pytest

from vibemodem.core import turbo
from vibemodem.core.turbo import TurboCode, rsc_encode


def random_bits(count, seed):
    return np.random.default_rng(seed).integers(0, 2, count, dtype=np.uint8)


def test_the_encoder_answers_a_single_one_with_the_series_of_its_transfer_function():
    # The parity of g1/g0 with g0 = 1 + D^2 + D^3 and g1 = 1 + D + D^3 is, for a single 1 at
    # the start, the series of that fraction. Dividing the polynomials by hand gives
    # 1 + D + D^2 + D^3 + D^6 + ..., checked by multiplying back by g0 to recover g1.
    parity, _, _ = rsc_encode(np.array([1] + [0] * 7, dtype=np.uint8))
    np.testing.assert_array_equal(parity, [1, 1, 1, 1, 0, 0, 1, 0])


def test_the_encoder_ends_in_the_all_zero_state_whatever_it_was_fed():
    # In the all-zero state, zeros in give zeros out for ever. So if the tail really brings the
    # encoder back there, feeding zeros after it gives no parity at all; from any other state
    # the feedback would keep producing ones.
    for seed in range(5):
        bits = random_bits(200, seed)
        _, tail_input, tail_parity = rsc_encode(bits)
        assert tail_input.size == tail_parity.size == turbo.MEMORY
        parity, _, _ = rsc_encode(np.concatenate([bits, tail_input, np.zeros(30, dtype=np.uint8)]))
        np.testing.assert_array_equal(parity[200 : 200 + turbo.MEMORY], tail_parity)
        assert not parity[200 + turbo.MEMORY :].any()


def test_the_interleaver_is_a_permutation_that_keeps_nearby_bits_apart():
    code = TurboCode(200)
    order = np.asarray(code.interleaver)
    assert sorted(order.tolist()) == list(range(200))
    assert code.spread >= 8
    for gap in range(1, code.spread + 1):
        assert (np.abs(order[gap:] - order[:-gap]) > code.spread).all()


def test_the_spread_describes_the_interleaver_actually_used():
    identity = TurboCode(200, interleaver=range(200))  # neighbours stay neighbours
    assert identity.spread == 0


def test_the_same_sizes_always_give_the_same_code():
    assert TurboCode(200).interleaver == TurboCode(200).interleaver


def test_the_code_cannot_change_without_the_digest_below_changing():
    # Both ends must agree on the code bit for bit, so a change is a change of protocol.
    info = (np.arange(200) * 7 % 3 == 0).astype(np.uint8)
    coded = TurboCode(200).encode(info)
    assert hashlib.sha256(np.packbits(coded).tobytes()).hexdigest()[:16] == "22ecf5726ab17cca"


def test_the_code_sends_the_bits_themselves_and_the_tails_and_half_the_parity():
    code = TurboCode(200)
    info = random_bits(200, 4)
    coded = code.encode(info)
    assert code.coded_bits == 2 * 200 + 4 * turbo.MEMORY == 412
    np.testing.assert_array_equal(coded[0 : 2 * 200 : 2], info)  # a bit, then a parity, ...


@pytest.mark.parametrize(
    "arguments",
    [dict(info_bits=0), dict(info_bits=15), dict(scaling=0), dict(scaling=1.5), dict(iterations=0)],
)
def test_settings_that_cannot_make_a_code_are_refused(arguments):
    with pytest.raises(ValueError):
        TurboCode(**{"info_bits": 200, **arguments})


def test_a_decoder_that_gets_more_turns_corrects_more():
    short, long = TurboCode(200, iterations=1), TurboCode(200, iterations=8)
    wrong_short = wrong_long = 0
    for seed in range(6):  # about 3 dB of Eb/N0, several words so one lucky draw cannot decide
        info = random_bits(200, seed)
        received = 1.0 - 2.0 * long.encode(info).astype(float)
        received += np.random.default_rng(100 + seed).normal(0, 0.95, received.size)
        wrong_short += int((short.decode(received) != info).sum())
        wrong_long += int((long.decode(received) != info).sum())
    assert wrong_long < wrong_short


@pytest.mark.parametrize("info_bits", [16, 17, 40, 64, 100, 250, 400, 1000])
@pytest.mark.parametrize("amplitude", [1.0, 1e6])
def test_codes_of_any_size_decode_clean_words_whatever_the_scale_of_the_soft_values(
    info_bits, amplitude
):
    code = TurboCode(info_bits)
    info = random_bits(info_bits, info_bits)
    received = amplitude * (1.0 - 2.0 * code.encode(info).astype(float))
    np.testing.assert_array_equal(code.decode(received), info)


def test_the_decoder_stops_as_soon_as_two_rounds_agree(monkeypatch):
    calls = []
    original = turbo._soft_in_soft_out
    monkeypatch.setattr(turbo, "_soft_in_soft_out", lambda *a: calls.append(1) or original(*a))
    code = TurboCode(200)  # up to 8 rounds of two decoders, so 16 calls if it never stopped
    code.decode(1.0 - 2.0 * code.encode(random_bits(200, 2)).astype(float))
    assert len(calls) <= 6


def test_a_spread_that_cannot_be_reached_is_refused_instead_of_searched_forever():
    with pytest.raises(ValueError, match="spread"):
        turbo._spread_shuffle(200, 25, seed=1, max_restarts=30)
