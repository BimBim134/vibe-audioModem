"""A long-constraint convolutional code, decoded sequentially by the Fano algorithm.

The code is the one of WSPR: each pair of coded bits depends on the last 32 information bits
(constraint length 32, rate 1/2), through two polynomials. A Viterbi decoder would have to follow
2**31 states, so the decoder instead walks the tree of possible bit sequences along one path.

At each step it tries the branch that agrees best with the received soft values. It keeps a
threshold and only enters nodes whose running score is above it, raises the threshold as it
advances, and when both branches fall short it backs up to try the other branch of the last
choice, or lowers the threshold when it cannot back up. It only ever stores the current path.
Its work depends on the noise: nearly one step per bit when the signal is good, many more when
it is weak. After a fixed budget of steps it gives up and returns nothing.
"""

import math

import numpy as np

from vibemodem.core.code import as_bits, as_vector

CONSTRAINT_LENGTH = 32
POLYNOMIALS = (0xF2D05351, 0xE4613C47)  # both end in 1, so the two branches of a node output
# complementary pairs: the decoder relies on it to compute one pair and derive the other.
TAIL_BITS = CONSTRAINT_LENGTH - 1  # zeros that let the last information bit finish its run
# Chosen by simulating 200 information bits on white noise (600 to 800 frames per point;
# reproduce with `python -m bench.code_curves --code
# vibemodem.core.long_convolutional:LongConvolutionalCode --set threshold_step=3`). A confidence
# of 2 to 3 and a step of 3 to 4 were equally good; a confidence of 1 made every frame fail, and
# 6 or more, or steps of 6 or more, lost more frames. A bigger budget loses fewer frames but a
# failing decode costs more time: at 2.0 dB of Eb/N0, 300 steps per bit lost 8.1% of frames and
# 1,000 lost 4.4%, for a worst-case decode of 23 ms and 76 ms.
DEFAULT_CONFIDENCE = 2.5
DEFAULT_THRESHOLD_STEP = 3.0
DEFAULT_MAX_CYCLES_PER_BIT = 1000
MAX_CYCLES_PER_BIT = 100_000  # about 8 s of work per decoding attempt at the very most
_MASK = (1 << CONSTRAINT_LENGTH) - 1
_CODE_RATE = 0.5  # information bits per coded bit, the bias of the Fano metric
_PARITY_OF_16_BITS = tuple(bin(value).count("1") & 1 for value in range(1 << 16))


def _parity(value: int) -> int:
    return _PARITY_OF_16_BITS[value & 0xFFFF] ^ _PARITY_OF_16_BITS[value >> 16]


def _coded_pair(register: int) -> int:
    """The two coded bits for a register of the last 32 information bits, as 2*first + second."""
    return (_parity(register & POLYNOMIALS[0]) << 1) | _parity(register & POLYNOMIALS[1])


def _fano(
    metrics: list[list[float]], info_bits: int, threshold_step: float, max_cycles: int
) -> list[int] | None:
    """The information bits of the path the Fano algorithm settles on, or None when it gives up.

    `metrics[step][pair]` is how much the received soft values favour each possible pair of coded
    bits at that step. After `info_bits` steps only 0 is possible (the tail).
    """
    steps = len(metrics)
    score = [0.0] * (steps + 1)  # running score of the path at each depth
    register = [0] * (steps + 1)  # the last 32 information bits at each depth
    attempt = [0] * steps  # 0: the better branch is selected, 1: the other one
    bit_of = [(0, 1)] * steps  # the branches' bits, better first
    metric_of = [(0.0, 0.0)] * steps
    has_alternative = [True] * steps

    def enter(depth: int) -> None:
        pair = _coded_pair((register[depth] << 1) & _MASK)
        for_zero, for_one = metrics[depth][pair], metrics[depth][pair ^ 3]
        if depth >= info_bits:  # the tail: zeros only, whatever the soft values favour
            bit_of[depth], metric_of[depth] = (0, 1), (for_zero, for_one)
            has_alternative[depth] = False
        else:
            if for_zero >= for_one:
                bit_of[depth], metric_of[depth] = (0, 1), (for_zero, for_one)
            else:
                bit_of[depth], metric_of[depth] = (1, 0), (for_one, for_zero)
            has_alternative[depth] = True
        attempt[depth] = 0

    enter(0)
    depth = 0
    threshold = 0.0
    for _ in range(max_cycles):
        reached = score[depth] + metric_of[depth][attempt[depth]]
        if reached >= threshold:
            if score[depth] < threshold + threshold_step:  # first visit: tighten the threshold
                while reached >= threshold + threshold_step:
                    threshold += threshold_step
            register[depth + 1] = ((register[depth] << 1) | bit_of[depth][attempt[depth]]) & _MASK
            score[depth + 1] = reached
            depth += 1
            if depth == steps:
                return [bit_of[step][attempt[step]] for step in range(info_bits)]
            enter(depth)
            continue
        while True:  # neither branch is good enough: back up
            if depth == 0 or score[depth - 1] < threshold:
                threshold -= threshold_step  # nowhere to back up to: accept a lower score
                attempt[depth] = 0
                break
            depth -= 1
            if attempt[depth] == 0 and has_alternative[depth]:
                attempt[depth] = 1  # try the other branch of this earlier choice
                break
    return None


class LongConvolutionalCode:
    """A `Code` for `info_bits` bits sent as 2 * (info_bits + 31) coded bits.

    `confidence` is the average size the soft values are given before they are read as
    likelihoods (the Fano score adds up logarithms of how likely each coded bit is, so unlike
    min-sum it needs soft values on a calibrated scale). `threshold_step` is the Fano step, in
    bits of score. `max_cycles_per_bit` bounds the work: the decoder gives up after that many
    steps per bit of the frame.
    """

    def __init__(
        self,
        info_bits: int,
        confidence: float = DEFAULT_CONFIDENCE,
        threshold_step: float = DEFAULT_THRESHOLD_STEP,
        max_cycles_per_bit: int = DEFAULT_MAX_CYCLES_PER_BIT,
    ):
        if info_bits < 1:
            raise ValueError("info_bits must be at least 1")
        if not 0 < confidence < math.inf:
            raise ValueError("confidence must be a finite number above 0")
        if not 0 < threshold_step < math.inf:
            raise ValueError("threshold_step must be a finite number above 0")
        if not 1 <= max_cycles_per_bit <= MAX_CYCLES_PER_BIT:
            raise ValueError(f"max_cycles_per_bit must be from 1 to {MAX_CYCLES_PER_BIT}")
        self.info_bits = info_bits
        self.coded_bits = 2 * (info_bits + TAIL_BITS)
        self._confidence = confidence
        self._threshold_step = threshold_step
        self._max_cycles_per_bit = max_cycles_per_bit

    @property
    def parameters(self) -> dict:
        """What a result file records so the code that was measured can be told apart."""
        return {
            "kind": "long-convolutional",
            "constraint_length": CONSTRAINT_LENGTH,
            "polynomials_hex": [f"{polynomial:x}" for polynomial in POLYNOMIALS],
            "tail_bits": TAIL_BITS,
            "decoder": "fano",
            "confidence": self._confidence,
            "threshold_step": self._threshold_step,
            "max_cycles_per_bit": self._max_cycles_per_bit,
        }

    def encode(self, bits: np.ndarray) -> np.ndarray:
        bits = as_bits(bits, self.info_bits)
        coded = np.empty(self.coded_bits, dtype=np.uint8)
        register = 0
        for step, bit in enumerate([*bits.tolist(), *([0] * TAIL_BITS)]):
            register = ((register << 1) | bit) & _MASK
            pair = _coded_pair(register)
            coded[2 * step], coded[2 * step + 1] = pair >> 1, pair & 1
        return coded

    def decode(self, soft: np.ndarray) -> np.ndarray | None:
        soft = as_vector(soft, self.coded_bits, "soft values")
        size = np.abs(soft).mean()
        if size == 0:
            return None  # no bit said anything, so there is nothing to decode
        calibrated = soft / size * self._confidence  # divide first: `size` can be tiny
        # Fano metric of a coded bit being 0 or 1: log2 of how much likelier the received value
        # makes it than a coin toss, minus the rate.
        if_zero = _CODE_RATE - np.logaddexp(0.0, -calibrated) / np.log(2)
        if_one = _CODE_RATE - np.logaddexp(0.0, calibrated) / np.log(2)
        zero, one = if_zero.reshape(-1, 2), if_one.reshape(-1, 2)
        metrics = np.stack(
            [
                zero[:, 0] + zero[:, 1],
                zero[:, 0] + one[:, 1],
                one[:, 0] + zero[:, 1],
                one[:, 0] + one[:, 1],
            ],
            axis=1,
        ).tolist()
        steps = self.info_bits + TAIL_BITS
        decoded = _fano(
            metrics, self.info_bits, self._threshold_step, self._max_cycles_per_bit * steps
        )
        return None if decoded is None else np.array(decoded, dtype=np.uint8)
