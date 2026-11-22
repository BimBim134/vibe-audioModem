"""TX blanking: the stretches of time when the input is silenced, because the station is
transmitting and its own sound comes back through the audio interface.

Times are on the wall clock, in seconds, as are the starts of the blocks of input.
"""

import threading

import numpy as np

from vibemodem.core.coded_modem import SAMPLE_RATE

REMEMBERED = 32  # the last few stretches: older ones are long gone from any window


class Blanking:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spans: list[list[float]] = []  # [start, end]; the end is infinite while playing

    def start(self, at: float) -> None:
        """The playback begins."""
        with self._lock:
            self._spans.append([at, float("inf")])
            del self._spans[:-REMEMBERED]

    def end(self, at: float) -> None:
        """The input is heard again from `at`: the end of playback, the output latency and the
        margin, added up by the caller."""
        with self._lock:
            if self._spans and self._spans[-1][1] == float("inf"):
                self._spans[-1][1] = max(at, self._spans[-1][0])

    def silence(self, block: np.ndarray, starts_at: float) -> np.ndarray:
        """The block of input that starts at `starts_at`, with the blanked samples set to zero.
        The block given is never changed."""
        with self._lock:
            spans = [tuple(span) for span in self._spans]
        ends_at = starts_at + block.size / SAMPLE_RATE
        cuts = [
            (
                max(0, round((begin - starts_at) * SAMPLE_RATE)),
                min(block.size, _upto(end - starts_at)),
            )
            for begin, end in spans
            if begin < ends_at and end > starts_at
        ]
        if not cuts:
            return block
        silenced = block.copy()
        for first, last in cuts:
            silenced[first:last] = 0.0
        return silenced


def _upto(seconds: float) -> int:
    return 2**62 if seconds == float("inf") else round(seconds * SAMPLE_RATE)
