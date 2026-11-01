"""A low-density parity-check (LDPC) code, decoded by normalised min-sum.

The code is a set of parity rules over the coded bits: each rule names a few bits that must
add up to an even number. The first `info_bits` coded bits are the information itself; the
others are parity bits chained like a staircase (each rule links two neighbouring parity bits),
so they come out of a running XOR with no equation to solve. This is the repeat-accumulate
structure of satellite-TV codes. The rules on the information bits are placed one edge at a
time by the PEG algorithm, which always joins a bit to a rule that is as far from it as
possible in the graph, so that short loops (which hurt decoding) are avoided. No random
numbers are involved: the same sizes always give the same code.

Decoding passes opinions back and forth between bits and rules until every rule is satisfied.
"""

import functools

import numpy as np

from vibemodem.core.code import as_bits, as_vector

DEFAULT_INFO_BITS = 200
DEFAULT_CODED_BITS = 400
# Rules each information bit belongs to, and the min-sum normalisation, were chosen by
# simulating 200 information bits at rate 1/2 on white noise (1,000 frames per point): at 2 dB of
# Eb/N0, 6.9% of frames were lost against 18.5% for the convolutional code of the baseline;
# degree 3 lost 12.3% and degree 5 5.7% but did worse at 1.5 dB, normalisations of 0.7 and 1.0
# were worse than 0.8.
DEFAULT_INFO_DEGREE = 4
DEFAULT_MAX_ITERATIONS = 50
DEFAULT_NORMALISATION = 0.8  # min-sum overstates the opinions; this brings them back down
_HUGE = 1e30  # stands in for a missing neighbour; never the smallest opinion


@functools.lru_cache(maxsize=8)
def _rules(info_bits: int, coded_bits: int, info_degree: int) -> tuple[tuple[int, ...], ...]:
    """For each parity rule, the bits it names. Built once per size."""
    rule_count = coded_bits - info_bits
    members: list[list[int]] = [[] for _ in range(rule_count)]
    rules_of: list[list[int]] = [[] for _ in range(coded_bits)]

    def connect(rule: int, bit: int) -> None:
        members[rule].append(bit)
        rules_of[bit].append(rule)

    for step in range(rule_count):  # the staircase of parity bits
        connect(step, info_bits + step)
        if step + 1 < rule_count:
            connect(step + 1, info_bits + step)

    def furthest_rules(bit: int) -> list[int]:
        """Rules not yet linked to the bit and as far from it as the graph allows."""
        reached = set(rules_of[bit])
        layer = set(reached)
        seen_bits = {bit}
        while True:
            next_bits = {b for rule in layer for b in members[rule]} - seen_bits
            next_layer = {r for b in next_bits for r in rules_of[b]} - reached
            if not next_layer:
                return sorted(set(range(rule_count)) - reached) or sorted(layer)
            if len(reached) + len(next_layer) == rule_count:
                return sorted(next_layer)
            reached |= next_layer
            layer = next_layer
            seen_bits |= next_bits

    for bit in range(info_bits):
        for edge in range(info_degree):
            candidates = range(rule_count) if edge == 0 else furthest_rules(bit)
            connect(min(candidates, key=lambda rule: (len(members[rule]), rule)), bit)
    return tuple(tuple(sorted(rule)) for rule in members)


class LdpcCode:
    """An LDPC `Code` of `info_bits` information bits and `coded_bits` coded bits."""

    def __init__(
        self,
        info_bits: int = DEFAULT_INFO_BITS,
        coded_bits: int = DEFAULT_CODED_BITS,
        info_degree: int = DEFAULT_INFO_DEGREE,
        normalisation: float = DEFAULT_NORMALISATION,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ):
        if not 0 < info_bits < coded_bits:
            raise ValueError("need 0 < info_bits < coded_bits")
        if not 2 <= info_degree <= coded_bits - info_bits:
            raise ValueError("info_degree must be at least 2 and at most the number of rules")
        if not 0 < normalisation <= 1:
            raise ValueError("normalisation must be above 0 and at most 1")
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        self.info_bits = info_bits
        self.coded_bits = coded_bits
        self._normalisation = normalisation
        self._max_iterations = max_iterations
        self.rules = _rules(info_bits, coded_bits, info_degree)

        # The same rules as arrays for the decoder: one entry per (rule, bit) link.
        widest = max(len(rule) for rule in self.rules)
        link_count = sum(len(rule) for rule in self.rules)
        self._link_bit = np.array([bit for rule in self.rules for bit in rule])
        self._rule_links = np.full((len(self.rules), widest), link_count)  # padded
        first = 0
        for index, rule in enumerate(self.rules):
            self._rule_links[index, : len(rule)] = np.arange(first, first + len(rule))
            first += len(rule)
        self._real_link = self._rule_links < link_count
        self._slots = np.arange(widest)
        for table in (self._link_bit, self._rule_links, self._real_link, self._slots):
            table.flags.writeable = False

        # The information bits' share of each rule, to compute parity bits by accumulating.
        self._info_links = [
            np.array([bit for bit in rule if bit < info_bits], dtype=int) for rule in self.rules
        ]

    def encode(self, bits: np.ndarray) -> np.ndarray:
        bits = as_bits(bits, self.info_bits)
        rule_sums = np.array([bits[links].sum() & 1 for links in self._info_links], dtype=np.uint8)
        return np.concatenate([bits, np.bitwise_xor.accumulate(rule_sums)])

    def is_codeword(self, bits: np.ndarray) -> bool:
        """Whether every parity rule is satisfied by these coded bits."""
        return not self._violated(as_bits(bits, self.coded_bits).astype(bool)).any()

    def decode(self, soft: np.ndarray) -> np.ndarray | None:
        channel = as_vector(soft, self.coded_bits, "soft values")
        if not channel.any():
            return None  # no bit said anything, so there is nothing to decode
        guess = channel < 0
        if not self._violated(guess).any():
            return guess[: self.info_bits].astype(np.uint8)

        to_rule = channel[self._link_bit]  # what each bit tells each rule it belongs to
        for _ in range(self._max_iterations):
            to_bit = self._rule_opinions(to_rule)
            belief = channel + np.bincount(
                self._link_bit, weights=to_bit, minlength=self.coded_bits
            )
            guess = belief < 0
            if not self._violated(guess).any():
                return guess[: self.info_bits].astype(np.uint8)
            to_rule = belief[self._link_bit] - to_bit
        return None

    def _violated(self, bits: np.ndarray) -> np.ndarray:
        """For each rule, whether the bits it names add up to an odd number."""
        padded = np.append(bits[self._link_bit], False)
        return (padded[self._rule_links].sum(axis=1) & 1).astype(bool)

    def _rule_opinions(self, to_rule: np.ndarray) -> np.ndarray:
        """What each rule tells each of its bits: the sign the others imply, and how sure."""
        gathered = np.append(to_rule, _HUGE)[self._rule_links]
        signs = np.where(gathered < 0, -1.0, 1.0)
        sizes = np.abs(gathered)
        rows = np.arange(sizes.shape[0])
        smallest = sizes.argmin(axis=1)
        first = sizes[rows, smallest]
        sizes[rows, smallest] = _HUGE
        second = sizes.min(axis=1)
        others = np.where(
            self._slots[None, :] == smallest[:, None], second[:, None], first[:, None]
        )
        opinions = self._normalisation * signs.prod(axis=1)[:, None] * signs * others
        to_bit = np.zeros(self._link_bit.size)
        to_bit[self._rule_links[self._real_link]] = opinions[self._real_link]
        return to_bit
