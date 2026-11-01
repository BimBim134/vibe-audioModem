"""The contract every error-correcting code honours, checked on each code we have."""

import json

import numpy as np
import pytest

from vibemodem.core.convolutional import ConvolutionalCode
from vibemodem.core.ldpc import LdpcCode
from vibemodem.core.turbo import TurboCode

INFO_BITS = 200

CODES = [
    pytest.param(ConvolutionalCode(INFO_BITS), id="convolutional"),
    pytest.param(LdpcCode(), id="ldpc"),
    pytest.param(TurboCode(INFO_BITS), id="turbo"),
]


def random_bits(count, seed):
    return np.random.default_rng(seed).integers(0, 2, count, dtype=np.uint8)


def soft(coded_bits, confidence=1.0):
    """Soft values for coded bits: positive means 0, as a demodulator reports them."""
    return confidence * (1.0 - 2.0 * coded_bits.astype(float))


@pytest.mark.parametrize("code", CODES)
def test_a_code_says_how_many_bits_it_takes_and_gives(code):
    assert code.info_bits == INFO_BITS
    assert code.coded_bits > code.info_bits
    assert code.encode(random_bits(INFO_BITS, 1)).size == code.coded_bits


@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize("seed", range(5))
def test_what_is_encoded_comes_back_from_clean_soft_values(code, seed):
    info = random_bits(INFO_BITS, seed)
    np.testing.assert_array_equal(code.decode(soft(code.encode(info))), info)


@pytest.mark.parametrize("code", CODES)
def test_scattered_wrong_bits_are_corrected(code):
    info = random_bits(INFO_BITS, 7)
    coded = code.encode(info)
    received = soft(coded)
    wrong = np.random.default_rng(8).choice(code.coded_bits, 6, replace=False)
    received[wrong] *= -1
    np.testing.assert_array_equal(code.decode(received), info)


@pytest.mark.parametrize("code", CODES)
def test_soft_values_let_doubtful_bits_be_outvoted(code):
    # A fifth of the bits are wrong but barely believed; the others are right and firmly
    # believed. Turning soft values into hard 0/1 first would leave 80 errors, which no rate-1/2
    # code can correct.
    info = random_bits(INFO_BITS, 9)
    received = soft(code.encode(info))
    wrong = np.random.default_rng(10).choice(code.coded_bits, 80, replace=False)
    received[wrong] = -0.05 * np.sign(received[wrong])
    np.testing.assert_array_equal(code.decode(received), info)


@pytest.mark.parametrize("code", CODES)
def test_a_wrong_number_of_bits_is_refused(code):
    with pytest.raises(ValueError, match="bits"):
        code.encode(random_bits(INFO_BITS + 1, 1))
    with pytest.raises(ValueError, match="values"):
        code.decode(np.zeros(code.coded_bits + 1))


@pytest.mark.parametrize("code", CODES)
def test_plain_lists_are_accepted_as_bits_and_soft_values(code):
    info = random_bits(INFO_BITS, 11)
    coded = code.encode(info.tolist())
    np.testing.assert_array_equal(code.decode(soft(coded).tolist()), info)


@pytest.mark.parametrize("code", CODES)
def test_bits_and_soft_values_must_be_flat_lists_of_real_numbers(code):
    with pytest.raises(ValueError, match="one-dimensional"):
        code.encode(np.zeros((INFO_BITS // 2, 2)))
    with pytest.raises(ValueError, match="one-dimensional"):
        code.decode(np.zeros((code.coded_bits // 2, 2)))
    not_a_number = np.ones(code.coded_bits)
    not_a_number[3] = np.nan
    with pytest.raises(ValueError, match="finite"):
        code.decode(not_a_number)


@pytest.mark.parametrize("code", CODES)
def test_bits_other_than_0_and_1_are_refused(code):
    with pytest.raises(ValueError, match="0 or 1"):
        code.encode(np.full(INFO_BITS, 2))


@pytest.mark.parametrize("code", CODES)
def test_a_code_describes_itself_in_plain_data_for_the_result_files(code):
    description = json.loads(json.dumps(code.parameters))  # must survive a trip through JSON
    assert description["kind"] in {"convolutional", "ldpc", "turbo"}


@pytest.mark.parametrize(
    "tuned, default",
    [
        (LdpcCode(max_iterations=10), LdpcCode()),
        (LdpcCode(normalisation=0.7), LdpcCode()),
        (TurboCode(INFO_BITS, iterations=4), TurboCode(INFO_BITS)),
        (TurboCode(INFO_BITS, scaling=0.5), TurboCode(INFO_BITS)),
        (TurboCode(INFO_BITS, interleaver=range(INFO_BITS)), TurboCode(INFO_BITS)),
    ],
)
def test_a_retuned_code_does_not_describe_itself_as_the_default_one(tuned, default):
    assert tuned.parameters != default.parameters
