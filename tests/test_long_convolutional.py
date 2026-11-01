"""What is specific to the long-constraint convolutional code and its sequential decoder."""

import hashlib

import numpy as np
import pytest

from vibemodem.core.long_convolutional import LongConvolutionalCode

FIRST, SECOND = 0xF2D05351, 0xE4613C47  # the polynomials of WSPR (Layland-Lushbaugh, K = 32)


def random_bits(count, seed):
    return np.random.default_rng(seed).integers(0, 2, count, dtype=np.uint8)


def pair_stream(coded):
    return coded[0::2], coded[1::2]


def test_a_single_one_comes_out_as_the_polynomials_themselves():
    # The impulse response of a convolutional code is its polynomials: the first coded bit of
    # step j is bit j of the first polynomial, the second one bit j of the second.
    code = LongConvolutionalCode(64)
    info = np.zeros(64, dtype=np.uint8)
    info[0] = 1
    first, second = pair_stream(code.encode(info))
    np.testing.assert_array_equal(first[:32], [(FIRST >> j) & 1 for j in range(32)])
    np.testing.assert_array_equal(second[:32], [(SECOND >> j) & 1 for j in range(32)])
    assert not first[32:].any() and not second[32:].any()


def test_the_tail_is_long_enough_for_the_last_information_bit_to_finish_its_run():
    code = LongConvolutionalCode(64)
    info = np.zeros(64, dtype=np.uint8)
    info[63] = 1
    first, second = pair_stream(code.encode(info))
    np.testing.assert_array_equal(first[63:95], [(FIRST >> j) & 1 for j in range(32)])
    np.testing.assert_array_equal(second[63:95], [(SECOND >> j) & 1 for j in range(32)])
    assert code.coded_bits == 2 * (64 + 31)


def test_encoding_is_linear_over_bits():
    code = LongConvolutionalCode(200)
    a, b = random_bits(200, 1), random_bits(200, 2)
    np.testing.assert_array_equal(code.encode(a ^ b), code.encode(a) ^ code.encode(b))
    assert not code.encode(np.zeros(200, dtype=np.uint8)).any()


def test_the_code_cannot_change_without_the_digest_below_changing():
    # Both ends must agree on the code bit for bit, so a change is a change of protocol.
    info = (np.arange(200) * 7 % 3 == 0).astype(np.uint8)
    coded = LongConvolutionalCode(200).encode(info)
    assert hashlib.sha256(np.packbits(coded).tobytes()).hexdigest()[:16] == "8511cc0f3c142a77"


def noisy_frames(count, seed, ebn0_db=3.0):
    """Frames of the code at a given Eb/N0 on white noise: (information bits, soft values)."""
    code = LongConvolutionalCode(200)
    sigma = (1 / (2 * (200 / code.coded_bits) * 10 ** (ebn0_db / 10))) ** 0.5
    rng = np.random.default_rng(seed)
    for _ in range(count):
        info = rng.integers(0, 2, 200, dtype=np.uint8)
        sent = 1.0 - 2.0 * code.encode(info).astype(float)
        yield info, 2 * (sent + sigma * rng.normal(size=sent.size)) / sigma**2


def test_a_decoder_with_no_budget_for_backing_up_decodes_far_fewer_noisy_words():
    # One step per bit and tail is exactly what walking straight to the end takes: no backing up.
    default, none = LongConvolutionalCode(200), LongConvolutionalCode(200, max_cycles_per_bit=1)
    frames = list(noisy_frames(20, seed=4))
    decoded = lambda code: sum(  # noqa: E731
        (out := code.decode(soft)) is not None and np.array_equal(out, info)
        for info, soft in frames
    )
    assert decoded(default) >= 17
    assert decoded(none) <= 8


def test_garbage_gives_nothing_rather_than_a_guess():
    code = LongConvolutionalCode(200, max_cycles_per_bit=5)
    garbage = np.random.default_rng(5).normal(size=code.coded_bits)
    assert code.decode(garbage) is None


def test_soft_values_that_say_nothing_give_nothing():
    code = LongConvolutionalCode(200)
    assert code.decode(np.zeros(code.coded_bits)) is None


@pytest.mark.parametrize(
    "arguments",
    [
        dict(info_bits=0),
        dict(confidence=0),
        dict(threshold_step=0),
        dict(max_cycles_per_bit=0),
        dict(max_cycles_per_bit=10**9),
        dict(confidence=float("nan")),
        dict(confidence=float("inf")),
        dict(threshold_step=float("nan")),
        dict(threshold_step=float("inf")),
    ],
)
def test_settings_that_cannot_work_are_refused(arguments):
    with pytest.raises(ValueError):
        LongConvolutionalCode(**{"info_bits": 200, **arguments})


def test_the_tail_is_forced_to_zeros_so_a_wrong_word_cannot_slip_in_at_the_end():
    # A decoder that let the tail steps pick whichever bit scored best accepted paths that
    # differed from the truth in the last 30 bits (about one frame in six at this noise level).
    # Giving up is allowed; returning a wrong word is not.
    wrong = 0
    for info, soft in noisy_frames(150, seed=11):
        decoded = LongConvolutionalCode(200).decode(soft)
        wrong += decoded is not None and not np.array_equal(decoded, info)
    assert wrong == 0


@pytest.mark.filterwarnings("error")  # an overflow while rescaling must not pass silently
@pytest.mark.parametrize("scale", [1e-320, 1e-300, 1e-12, 1.0, 1e12, 1e300])
def test_the_scale_of_the_soft_values_does_not_matter(scale):
    code = LongConvolutionalCode(200)
    info = random_bits(200, 12)
    received = scale * (1.0 - 2.0 * code.encode(info).astype(float))
    np.testing.assert_array_equal(code.decode(received), info)
