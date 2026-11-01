"""The interface of an error-correcting code, so a modem can use any of them."""

from typing import Protocol

import numpy as np


class Code(Protocol):
    """Turns information bits into longer coded bits, and soft values back into the bits.

    Soft values are what a demodulator can say about each coded bit: positive means "probably
    0", negative "probably 1", and the larger the number the surer it is. Only their sign and
    their size relative to each other count, not their scale.
    """

    info_bits: int
    coded_bits: int

    def encode(self, bits: np.ndarray) -> np.ndarray:
        """The `coded_bits` coded bits (0 or 1) for `info_bits` information bits."""
        ...

    def decode(self, soft: np.ndarray) -> np.ndarray | None:
        """The most likely information bits, or None when the code can tell it found none."""
        ...


def as_vector(values, size: int, what: str) -> np.ndarray:
    """`values` as a flat float array of `size` finite numbers; ValueError says what is wrong."""
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{what} must be a one-dimensional list")
    if array.size != size:
        raise ValueError(f"expected {size} {what}, got {array.size}")
    if not np.isfinite(array).all():
        raise ValueError(f"{what} must be finite numbers")
    return array


def as_bits(values, size: int) -> np.ndarray:
    """`values` as `size` bits (0 or 1) in a flat uint8 array."""
    array = as_vector(values, size, "bits")
    if not np.isin(array, (0.0, 1.0)).all():
        raise ValueError("bits must each be 0 or 1")
    return array.astype(np.uint8)
