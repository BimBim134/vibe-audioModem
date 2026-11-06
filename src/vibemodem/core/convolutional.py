"""Rate-1/2 convolutional code (constraint length 7) with a soft-decision Viterbi decoder."""

import numpy as np

from vibemodem.core.code import as_bits, as_vector

CONSTRAINT_LENGTH = 7
POLYNOMIALS = (0o171, 0o133)  # the classic pair, also used by CCSDS and many radio links
TAIL_BITS = CONSTRAINT_LENGTH - 1  # zeros that bring the encoder back to state 0
_STATES = 1 << (CONSTRAINT_LENGTH - 1)


def _parity(value: int) -> int:
    return bin(value).count("1") & 1


def _output_pair(state: int, bit: int) -> int:
    """The two coded bits of one step, as the number 2*first + second."""
    register = (state << 1) | bit
    first, second = (_parity(register & polynomial) for polynomial in POLYNOMIALS)
    return 2 * first + second


# For each next state, the two states that can lead to it and what they would have output.
_PREVIOUS = np.array(
    [[next_state >> 1, (next_state >> 1) | (_STATES >> 1)] for next_state in range(_STATES)]
)
_PREVIOUS_OUTPUT = np.array(
    [
        [_output_pair(previous, next_state & 1) for previous in _PREVIOUS[next_state]]
        for next_state in range(_STATES)
    ]
)
# +1 when the coded bit is 0, -1 when it is 1: how a soft value votes for each output pair.
_VOTE = np.array([[1 - 2 * (pair >> 1), 1 - 2 * (pair & 1)] for pair in range(4)], dtype=float)
for _table in (_PREVIOUS, _PREVIOUS_OUTPUT, _VOTE):
    _table.flags.writeable = False  # shared by every decoder


def encode(bits: np.ndarray) -> np.ndarray:
    """Coded bits for `bits` followed by the tail: 2 * (len(bits) + TAIL_BITS) bits."""
    state = 0
    coded = []
    for bit in [*bits.tolist(), *([0] * TAIL_BITS)]:
        pair = _output_pair(state, bit)
        coded.extend((pair >> 1, pair & 1))
        state = ((state << 1) | bit) & (_STATES - 1)
    return np.array(coded, dtype=np.uint8)


def decode(soft: np.ndarray) -> np.ndarray:
    """The most likely information bits for soft coded values (positive means bit 0).

    `soft` holds 2 * (n + TAIL_BITS) values, the size `encode` gives for n bits.
    """
    steps = soft.size // 2
    pairs = soft.reshape(steps, 2)
    path = np.full(_STATES, -np.inf)
    path[0] = 0.0
    choices = np.empty((steps, _STATES), dtype=np.uint8)
    for step in range(steps):
        branch = _VOTE @ pairs[step]
        candidates = path[_PREVIOUS] + branch[_PREVIOUS_OUTPUT]
        choices[step] = np.argmax(candidates, axis=1)
        path = candidates.max(axis=1)
        path -= path.max()  # keep the numbers small
    bits = np.empty(steps, dtype=np.uint8)
    state = 0  # the tail forces the encoder to end in state 0
    for step in range(steps - 1, -1, -1):
        bits[step] = state & 1
        state = _PREVIOUS[state, choices[step, state]]
    return bits[: steps - TAIL_BITS]


class ConvolutionalCode:
    """The code above as a `Code`, for a Frame of `info_bits` bits."""

    def __init__(self, info_bits: int):
        self.info_bits = info_bits
        self.coded_bits = 2 * (info_bits + TAIL_BITS)

    @property
    def parameters(self) -> dict:
        """What a result file records so the code that was measured can be told apart."""
        return {
            "kind": "convolutional",
            "constraint_length": CONSTRAINT_LENGTH,
            "polynomials_octal": [f"{polynomial:o}" for polynomial in POLYNOMIALS],
            "tail_bits": TAIL_BITS,
        }

    def encode(self, bits: np.ndarray) -> np.ndarray:
        return encode(as_bits(bits, self.info_bits))

    def decode(self, soft: np.ndarray) -> np.ndarray:
        return decode(as_vector(soft, self.coded_bits, "soft values"))
