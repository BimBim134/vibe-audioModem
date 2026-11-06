"""A turbo code: two recursive convolutional codes in parallel, decoded by trading opinions.

The bits are encoded twice: once as they are, once shuffled by an interleaver. Each encoder is a
recursive convolutional code of 8 states (the one of 4G mobile networks: feedback 1 + D^2 + D^3,
parity 1 + D + D^3) and produces a stream of parity bits. Half of each parity stream is sent, so
the rate is about 1/2, and each encoder is brought back to its start state by a tail of bits.

Decoding runs one decoder per encoder. Each reads what the channel said about the bits and
parity it knows, plus what the other decoder concluded, and reports for each bit what it learned
beyond that (the extrinsic opinion). They trade opinions for a few rounds, until the decisions
stop changing.
"""

import hashlib
import math
from collections.abc import Sequence

import numpy as np

from vibemodem.core.code import as_bits, as_vector

MEMORY = 3  # the encoders have 2**3 = 8 states
STATES = 1 << MEMORY
MIN_INFO_BITS = 16
DEFAULT_SCALING = 0.75  # max-log opinions are too sure of themselves; this tones them down
DEFAULT_ITERATIONS = 8
_IMPOSSIBLE = -1e300  # the metric of a state that cannot be reached
MAX_SHUFFLE_RESTARTS = 1000  # a shuffle that needs more tries than this is out of reach


def _build_trellis() -> tuple[np.ndarray, np.ndarray]:
    """Next state and parity bit for each (state, input bit)."""
    next_state = np.zeros((STATES, 2), dtype=int)
    parity = np.zeros((STATES, 2), dtype=int)
    for state in range(STATES):
        first, second, third = (state >> 2) & 1, (state >> 1) & 1, state & 1
        for bit in (0, 1):
            fed_back = bit ^ second ^ third  # g0 = 1 + D^2 + D^3
            parity[state, bit] = fed_back ^ first ^ third  # g1 = 1 + D + D^3
            next_state[state, bit] = (fed_back << 2) | (first << 1) | second
    return next_state, parity


_NEXT, _PARITY = _build_trellis()
# For each state, the two (previous state, input bit) pairs that lead to it.
_PRED_STATE = np.array(
    [[s for s in range(STATES) for b in (0, 1) if _NEXT[s, b] == t] for t in range(STATES)]
)
_PRED_INPUT = np.array(
    [[b for s in range(STATES) for b in (0, 1) if _NEXT[s, b] == t] for t in range(STATES)]
)
_SIGN_INPUT = np.array([[1.0, -1.0]] * STATES)  # +1 for a 0 bit, -1 for a 1 bit
_SIGN_PARITY = 1.0 - 2.0 * _PARITY
for _table in (_NEXT, _PARITY, _PRED_STATE, _PRED_INPUT, _SIGN_INPUT, _SIGN_PARITY):
    _table.flags.writeable = False


def rsc_encode(bits: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parity bits of one encoder, then the tail: the input bits and parity that end at state 0."""
    state = 0
    parity = np.empty(bits.size, dtype=np.uint8)
    for index, bit in enumerate(bits):
        parity[index] = _PARITY[state, bit]
        state = _NEXT[state, bit]
    tail_input = np.empty(MEMORY, dtype=np.uint8)
    tail_parity = np.empty(MEMORY, dtype=np.uint8)
    for index in range(MEMORY):
        bit = ((state >> 1) ^ state) & 1  # cancels the feedback so the state drains to zero
        tail_input[index] = bit
        tail_parity[index] = _PARITY[state, bit]
        state = _NEXT[state, bit]
    return parity, tail_input, tail_parity


def _spread_for(info_bits: int) -> int:
    # The largest spread a shuffle can have is about sqrt(info_bits / 2); asking for four fifths
    # of it keeps the construction instant for any size, where the maximum can take seconds or
    # fail. Simulating the code alone showed no measurable difference between spreads 8 to 10 at
    # 200 bits (see bench/code_curves.py), so nothing is lost.
    return max(2, int(0.8 * math.sqrt(info_bits / 2)))


def _interleaver(info_bits: int) -> tuple[int, ...]:
    return _spread_shuffle(info_bits, _spread_for(info_bits), seed=0x2545F491)


def _achieved_spread(order: Sequence[int]) -> int:
    """The largest S such that positions less than S apart end up more than S apart."""
    positions = np.asarray(order)
    spread = 0
    while spread + 1 < positions.size:
        wanted = spread + 1
        if all(
            (np.abs(positions[gap:] - positions[:-gap]) > wanted).all()
            for gap in range(1, wanted + 1)
        ):
            spread = wanted
        else:
            break
    return spread


def _spread_shuffle(
    info_bits: int, spread: int, seed: int, max_restarts: int = MAX_SHUFFLE_RESTARTS
) -> tuple[int, ...]:
    """A shuffle of the bit positions that keeps bits which were close, far apart afterwards.

    Spread S: two positions less than S apart are sent to positions more than S apart. Built by
    drawing candidates with a fixed generator, so the same size and seed give the same shuffle.
    """
    state = seed
    restarts = 0

    def draw(bound: int) -> int:
        nonlocal state
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        return (state >> 8) % bound

    while True:
        remaining = list(range(info_bits))
        order: list[int] = []
        while remaining:
            for _ in range(4 * len(remaining)):
                candidate = remaining[draw(len(remaining))]
                if all(abs(candidate - placed) > spread for placed in order[-spread:]):
                    order.append(candidate)
                    remaining.remove(candidate)
                    break
            else:
                break  # stuck: start the whole shuffle again from the generator's next draws
        if not remaining:
            return tuple(order)
        restarts += 1
        if restarts > max_restarts:
            raise ValueError(f"no shuffle of {info_bits} positions has a spread of {spread}")


def _soft_in_soft_out(systematic: np.ndarray, parity: np.ndarray, prior: np.ndarray) -> np.ndarray:
    """One decoder's opinion of each bit's value, all the evidence included (max-log-MAP)."""
    steps = systematic.size
    half_known = 0.5 * (systematic + prior)
    half_parity = 0.5 * parity
    # Evidence for each (step, state, input bit): the bit's soft value and the parity it implies.
    branch = (
        _SIGN_INPUT[None] * half_known[:, None, None]
        + _SIGN_PARITY[None] * half_parity[:, None, None]
    )
    # What a state is fed from each of its two predecessors, and what leaves each state on a 0
    # and on a 1, gathered once so that the two sweeps below only add and compare.
    into_first = branch[:, _PRED_STATE[:, 0], _PRED_INPUT[:, 0]]
    into_second = branch[:, _PRED_STATE[:, 1], _PRED_INPUT[:, 1]]
    out_zero, out_one = branch[:, :, 0], branch[:, :, 1]
    first_pred, second_pred = _PRED_STATE[:, 0], _PRED_STATE[:, 1]
    next_zero, next_one = _NEXT[:, 0], _NEXT[:, 1]

    forward = np.full((steps + 1, STATES), _IMPOSSIBLE)
    forward[0, 0] = 0.0
    for step in range(steps):
        before = forward[step]
        forward[step + 1] = np.maximum(
            before[first_pred] + into_first[step], before[second_pred] + into_second[step]
        )
    backward = np.full((steps + 1, STATES), _IMPOSSIBLE)
    backward[steps, 0] = 0.0  # the tail brings the encoder back to state 0
    for step in range(steps - 1, -1, -1):
        after = backward[step + 1]
        backward[step] = np.maximum(
            out_zero[step] + after[next_zero], out_one[step] + after[next_one]
        )
    paths = forward[:-1, :, None] + branch + backward[1:][:, _NEXT]
    best = paths.max(axis=1)
    return best[:, 0] - best[:, 1]


class TurboCode:
    """A turbo `Code` of `info_bits` bits, sent as 2 * info_bits + 4 * MEMORY coded bits.

    The coded bits alternate a bit and a parity bit (parity from the first encoder at even
    positions, from the second at odd ones), then the tails of both encoders.
    """

    def __init__(
        self,
        info_bits: int,
        interleaver: Sequence[int] | None = None,
        scaling: float = DEFAULT_SCALING,
        iterations: int = DEFAULT_ITERATIONS,
    ):
        if info_bits < MIN_INFO_BITS:
            raise ValueError(f"info_bits must be at least {MIN_INFO_BITS}")
        if not 0 < scaling <= 1:
            raise ValueError("scaling must be above 0 and at most 1")
        if iterations < 1:
            raise ValueError("iterations must be at least 1")
        order = tuple(interleaver) if interleaver is not None else _interleaver(info_bits)
        if sorted(order) != list(range(info_bits)):
            raise ValueError("the interleaver must be a permutation of the bit positions")
        self.info_bits = info_bits
        self.coded_bits = 2 * info_bits + 4 * MEMORY
        self.interleaver = order
        self.spread = _achieved_spread(order)
        self._order = np.array(order)
        self._scaling = scaling
        self._iterations = iterations

    @property
    def parameters(self) -> dict:
        """What a result file records so the code that was measured can be told apart."""
        return {
            "kind": "turbo",
            "memory": MEMORY,
            "polynomials_octal": ["13", "15"],  # feedback and parity of each encoder
            "interleaver_spread": self.spread,
            "interleaver_digest": hashlib.sha256(repr(self.interleaver).encode()).hexdigest()[:16],
            "scaling": self._scaling,
            "iterations": self._iterations,
        }

    def encode(self, bits: np.ndarray) -> np.ndarray:
        bits = as_bits(bits, self.info_bits)
        first, first_tail_bits, first_tail_parity = rsc_encode(bits)
        second, second_tail_bits, second_tail_parity = rsc_encode(bits[self._order])
        parity = np.where(np.arange(self.info_bits) % 2 == 0, first, second)
        coded = np.empty(2 * self.info_bits, dtype=np.uint8)
        coded[0::2], coded[1::2] = bits, parity
        return np.concatenate(
            [coded, first_tail_bits, first_tail_parity, second_tail_bits, second_tail_parity]
        )

    def decode(self, soft: np.ndarray) -> np.ndarray:
        soft = as_vector(soft, self.coded_bits, "soft values")
        n = self.info_bits
        bits, parity, tails = soft[0 : 2 * n : 2], soft[1 : 2 * n : 2], soft[2 * n :]
        even = np.arange(n) % 2 == 0
        zeros = np.zeros(MEMORY)
        one = (
            np.concatenate([bits, tails[0:3]]),
            np.concatenate([np.where(even, parity, 0.0), tails[3:6]]),
        )
        two = (
            np.concatenate([bits[self._order], tails[6:9]]),
            np.concatenate([np.where(even, 0.0, parity), tails[9:12]]),
        )

        from_second = np.zeros(n)  # what the second decoder last said, in the bits' own order
        previous = None
        for _ in range(self._iterations):
            prior = np.concatenate([self._scaling * from_second, zeros])
            first = _soft_in_soft_out(*one, prior)[:n] - one[0][:n] - prior[:n]

            prior = np.concatenate([self._scaling * first[self._order], zeros])
            second = _soft_in_soft_out(*two, prior)[:n] - two[0][:n] - prior[:n]
            from_second = np.empty(n)
            from_second[self._order] = second  # back to the bits' own order

            decisions = bits + first + from_second < 0
            if previous is not None and np.array_equal(decisions, previous):
                break
            previous = decisions
        return decisions.astype(np.uint8)
