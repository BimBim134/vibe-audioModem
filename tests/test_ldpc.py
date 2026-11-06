"""What is specific to the LDPC code: its rules, its stability and what it does with garbage."""

import hashlib

import numpy as np
import pytest

from vibemodem.core import ldpc
from vibemodem.core.ldpc import LdpcCode


def random_bits(count, seed):
    return np.random.default_rng(seed).integers(0, 2, count, dtype=np.uint8)


def test_the_same_sizes_always_give_the_same_code():
    first = LdpcCode().rules
    ldpc._rules.cache_clear()  # build it again from scratch, not from the cache
    assert LdpcCode().rules == first


def test_the_code_cannot_change_without_the_digest_below_changing():
    # A modem and its peer must agree on the code bit for bit, so a change to the rules is a
    # change to the protocol. If this fails on purpose, update the digest and say so.
    info = (np.arange(200) * 7 % 3 == 0).astype(np.uint8)
    coded = LdpcCode().encode(info)
    assert hashlib.sha256(np.packbits(coded).tobytes()).hexdigest()[:16] == "e05a70e1cc7e8e32"


@pytest.mark.parametrize("seed", range(5))
def test_every_encoded_word_satisfies_every_rule_and_one_wrong_bit_does_not(seed):
    code = LdpcCode()
    word = code.encode(random_bits(code.info_bits, seed))
    assert code.is_codeword(word)
    word[int(np.random.default_rng(seed).integers(0, code.coded_bits))] ^= 1
    assert not code.is_codeword(word)


def test_the_information_comes_first_in_the_coded_bits():
    code = LdpcCode()
    info = random_bits(code.info_bits, 3)
    np.testing.assert_array_equal(code.encode(info)[: code.info_bits], info)


def test_no_two_rules_share_two_bits():
    # Two rules naming the same pair of bits form a loop of length four, which makes the
    # opinions passed between bits and rules repeat each other instead of adding information.
    rules = [set(rule) for rule in LdpcCode().rules]
    for first in range(len(rules)):
        for second in range(first + 1, len(rules)):
            assert len(rules[first] & rules[second]) < 2


def test_every_bit_but_the_last_parity_bit_is_named_by_at_least_two_rules():
    code = LdpcCode()
    counts = np.bincount([bit for rule in code.rules for bit in rule], minlength=code.coded_bits)
    assert (counts[:-1] >= 2).all()


@pytest.mark.parametrize("seed", range(4))
def test_garbage_gives_nothing_rather_than_a_guess(seed):
    code = LdpcCode()
    garbage = np.random.default_rng(seed).normal(size=code.coded_bits)
    assert code.decode(garbage) is None


def test_soft_values_that_say_nothing_give_nothing():
    # Every bit at zero means "no idea"; all zeros satisfies every rule but proves nothing.
    code = LdpcCode()
    assert code.decode(np.zeros(code.coded_bits)) is None


def test_a_word_that_is_far_from_any_codeword_is_not_one():
    code = LdpcCode()
    assert not code.is_codeword(random_bits(code.coded_bits, 1))


@pytest.mark.parametrize(
    "arguments",
    [dict(info_bits=0), dict(info_bits=400), dict(info_degree=1), dict(info_degree=500)],
)
def test_sizes_that_cannot_make_a_code_are_refused(arguments):
    with pytest.raises(ValueError):
        LdpcCode(**arguments)


@pytest.mark.parametrize(
    "arguments", [dict(normalisation=0), dict(normalisation=1.5), dict(max_iterations=0)]
)
def test_decoder_settings_that_cannot_work_are_refused(arguments):
    with pytest.raises(ValueError):
        LdpcCode(**arguments)


def test_the_decoder_settings_belong_to_each_code_not_to_the_module():
    strict, lenient = LdpcCode(max_iterations=1), LdpcCode(max_iterations=50)
    word = lenient.encode(random_bits(lenient.info_bits, 2))
    noisy = 1.0 - 2.0 * word.astype(float)
    noisy[np.random.default_rng(6).choice(lenient.coded_bits, 25, replace=False)] *= -0.3
    assert lenient.decode(noisy) is not None  # enough iterations to repair it
    assert strict.decode(noisy) is None  # one iteration is not
