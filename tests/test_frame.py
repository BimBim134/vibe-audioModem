"""The Frame: a body of up to 20 bytes, its length and a CRC-32, whitened."""

import numpy as np
import pytest

from vibemodem.core import frame


@pytest.mark.parametrize("size", [0, 1, 19, frame.MESSAGE_CAPACITY])
def test_a_body_survives_a_round_trip(size):
    body = bytes(range(size))
    assert frame.decode_frame(frame.encode_frame(body)) == body


def test_a_body_longer_than_the_frame_holds_is_refused():
    with pytest.raises(ValueError, match="Fragments"):
        frame.encode_frame(bytes(frame.MESSAGE_CAPACITY + 1))


def test_every_corruption_of_a_few_bits_is_rejected():
    bits = frame.encode_frame(b"\x01\x00\x01payload")
    for first in range(bits.size):  # every single flipped bit, and every pair with the next 40
        single = bits.copy()
        single[first] ^= 1
        assert frame.decode_frame(single) is None
        for second in range(first + 1, min(first + 41, bits.size)):
            double = single.copy()
            double[second] ^= 1
            assert frame.decode_frame(double) is None


def test_no_crc_false_positive_in_half_a_million_random_corruptions():
    # A CRC-32 lets a random word through with chance 2**-32, so half a million words cannot
    # show the rate; they show that no kind of corruption gets past the checks by structure.
    rng = np.random.default_rng(2024)
    bits = frame.encode_frame(b"\x07\x02\x05" + b"x" * 17)
    accepted = 0
    for _ in range(500_000):
        corrupted = bits.copy()
        flips = rng.integers(0, bits.size, rng.integers(1, 60))
        corrupted[flips] ^= 1
        accepted += (
            not np.array_equal(corrupted, bits) and frame.decode_frame(corrupted) is not None
        )
    assert accepted == 0


def test_a_frame_of_pure_noise_is_rejected():
    rng = np.random.default_rng(5)
    noise_frames = rng.integers(0, 2, (200_000, frame.FRAME_BITS), dtype=np.uint8)
    assert all(frame.decode_frame(bits) is None for bits in noise_frames)
