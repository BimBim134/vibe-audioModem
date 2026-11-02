"""What every modem built on a Code shares: the Frame, the order the bits are sent in, and
the loop that turns a recording into Messages.

A modem that differs from another only by its waveform or by its code comes from here, so a
difference in their Success threshold is the waveform's or the code's. A subclass says how to
build the audio of a stream of bits, how to find Signals in a recording and how to read the soft
values of a Signal's bits.
"""

import math

import numpy as np

from vibemodem.core import frame, presets
from vibemodem.core.code import Code
from vibemodem.core.modem import Detection, Reception, Report
from vibemodem.core.presets import DEFAULT_PRESET

SAMPLE_RATE = 48_000
NOISE_BANDWIDTH_HZ = 2500  # the reference bandwidth in which SNRs are quoted
# The search keeps a few arrays of (windows x frequencies) numbers; this bounds their size.
MAX_RECORDING_SECONDS = 600
MAX_REPETITIONS = 8
# A Signal that cannot be read is only reported when its Preamble stands out this much. Noise
# alone gives matches of 7 to 7.7 (the search keeps those: it costs a failed decode), while a
# Signal at the Success threshold of any Preset gives 15 or more (docs/measurements/README.md).
UNDECODED_MIN_SCORE = 10.0
_GOLDEN_RATIO_FRACTION = (math.sqrt(5) - 1) / 2


def _send_order(count: int, copy: int, interleave: bool) -> np.ndarray:
    """For each position of one copy of the coded bits as sent, which coded bit goes there.

    Without interleaving, the order of the code. With it, position j carries bit
    (j * stride) mod count, the stride being a share of `count` close to a golden-ratio multiple
    (so that bits sent next to each other are far apart in the code word, and any run of
    positions is spread evenly over it), and a different stride for each copy.
    """
    if not interleave:
        return np.arange(count)
    stride = max(1, round(count * ((copy + 1) * _GOLDEN_RATIO_FRACTION % 1)))
    while math.gcd(stride, count) != 1:
        stride += 1
    return (np.arange(count) * stride) % count


class CodedModem:
    """Sends one Message per Transmission; receives every Message found in a recording.

    Receptions of the same Message (a repeated Transmission) are merged into one.
    """

    def __init__(
        self, code: Code, *, preset: str = DEFAULT_PRESET, interleave: bool, repetitions: int = 1
    ):
        if code.info_bits != frame.FRAME_BITS:
            raise ValueError(f"the code must take a Frame of {frame.FRAME_BITS} bits")
        if not isinstance(repetitions, int) or not 1 <= repetitions <= MAX_REPETITIONS:
            raise ValueError(f"repetitions must be a whole number from 1 to {MAX_REPETITIONS}")
        if not isinstance(interleave, bool):
            raise ValueError("interleave must be true or false")
        self.code = code
        self.preset = preset
        self._interleave = interleave
        self._repetitions = repetitions
        self._sent_bits = repetitions * code.coded_bits
        self._orders = [
            _send_order(code.coded_bits, copy, interleave) for copy in range(repetitions)
        ]

    def _sent_stream(self, message: bytes) -> np.ndarray:
        """The bits of a Transmission after its preamble: the coded Frame, once per copy."""
        coded = self.code.encode(frame.encode_frame(message))
        return np.concatenate([coded[order] for order in self._orders])

    def _combine(self, soft_sent: np.ndarray) -> np.ndarray:
        """The soft value of each coded bit: its copies, put back in place, added up."""
        coded = self.code.coded_bits
        combined = np.zeros(coded)
        for copy, order in enumerate(self._orders):
            combined[order] += soft_sent[copy * coded : (copy + 1) * coded]
        return combined

    def _message(self, soft_sent: np.ndarray) -> bytes | None:
        """The Message the soft values of the sent bits carry, or None if the CRC refuses it."""
        decoded = self.code.decode(self._combine(soft_sent[: self._sent_bits]))
        return None if decoded is None else frame.decode_frame(decoded)

    def _audio(self, message: bytes) -> np.ndarray:
        raise NotImplementedError

    def _find(self, samples: np.ndarray) -> list:
        """Places where a Signal may be, best first, pinned down as finely as the search can."""
        raise NotImplementedError

    def _decode(self, samples: np.ndarray, signal) -> Reception | None:
        raise NotImplementedError

    def frame_samples(self) -> int:
        """How long a Frame lasts, Preamble included."""
        raise NotImplementedError

    def search_step_samples(self) -> int:
        """The search looks for a Signal at start times that are multiples of this, from the
        start of the audio: a piece cut on such a multiple is searched on the same grid."""
        raise NotImplementedError

    def _same_signal_samples(self) -> int:
        """Two Signals closer than this are one: the preamble match has side peaks."""
        raise NotImplementedError

    def _fits(self, samples: np.ndarray, signal) -> bool:
        """Whether the whole Frame of a Signal is in the recording (it may still be arriving)."""
        return signal.start_sample + self.frame_samples() <= samples.size

    def modulate(self, message: bytes, preset: str) -> np.ndarray:
        presets.profile(preset)  # refuses a name that is no Preset
        if preset != self.preset:
            raise ValueError(f"this modem is built for the Preset {self.preset!r}, not {preset!r}")
        return self._audio(message)

    def demodulate(self, samples: np.ndarray) -> list[Reception]:
        return self.demodulate_report(samples).receptions

    def demodulate_report(self, samples: np.ndarray) -> Report:
        """The Messages in a recording, and the Signals found whole whose Message was not read."""
        samples = np.asarray(samples, dtype=float)
        if samples.ndim != 1:
            raise ValueError("audio must be one channel (a 1-D array of samples)")
        if samples.size > MAX_RECORDING_SECONDS * SAMPLE_RATE:
            raise ValueError(
                f"recording too long: at most {MAX_RECORDING_SECONDS} s can be searched at once"
            )
        if not np.isfinite(samples).all():
            raise ValueError("audio samples must be finite numbers")

        received: dict[bytes, Reception] = {}
        lost, read_at, arriving = [], [], []
        signals = self._find(samples)
        for signal in signals:
            reception = self._decode(samples, signal)
            if reception is None:
                if signal.score >= UNDECODED_MIN_SCORE:
                    seen = Detection(signal.start_sample, signal.first_tone_hz, signal.score)
                    (lost if self._fits(samples, signal) else arriving).append(seen)
                continue
            read_at.append(signal.start_sample)
            if (
                reception.message not in received
                or reception.sync_score > received[reception.message].sync_score
            ):
                received[reception.message] = reception
        found = sorted(received.values(), key=lambda r: -r.sync_score)
        # Lost and arriving Signals are told apart by whether their Frame is whole: their side
        # peaks are the same whichever it is, so both are sifted together.
        kept = self._without_side_peaks([*lost, *arriving], read_at, signals)
        return Report(
            receptions=found,
            undecoded=[d for d in kept if d in lost],
            arriving=[d for d in kept if d in arriving],
        )

    def _without_side_peaks(
        self, lost: list[Detection], read_at: list[int], signals: list
    ) -> list[Detection]:
        """The Signals lost, without the side peaks of a Preamble: those inside a Frame that was
        read, inside a stronger Signal that was lost, or inside a stronger one that does not fit
        yet (a Frame still arriving has side peaks a few symbols earlier that do fit)."""
        apart = self.frame_samples() - self._same_signal_samples()
        kept: list[Detection] = []
        for detection in sorted(lost, key=lambda d: -d.sync_score):
            stronger = [s.start_sample for s in signals if s.score > detection.sync_score]
            near = [*read_at, *stronger, *(k.start_sample for k in kept)]
            if all(abs(detection.start_sample - other) >= apart for other in near):
                kept.append(detection)
        return sorted(kept, key=lambda d: d.start_sample)
