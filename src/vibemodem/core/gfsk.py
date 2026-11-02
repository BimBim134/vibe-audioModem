"""GFSK: building the audio, measuring bit energies and finding a Signal.

One bit per symbol, sent as a frequency `h * baud / 2` above (bit 0) or below (bit 1) a carrier,
the frequency steps smoothed by a Gaussian filter of bandwidth-time product `bt` (GMSK is
`h = 0.5`; `bt = None` means no filter). The phase is continuous, which keeps the band narrow.

The receiver is not coherent: it does not follow the carrier's phase, so fading and an unknown
phase cost nothing extra. For each bit it measures the energy at the two frequencies over the
bit's duration and says "0" when the upper one is louder. Those two measurements are orthogonal
only for `h = 1`; for smaller indices they overlap, which the Success threshold then shows.
The audio is first brought down to 6 kHz, where all the searching is done.
"""

import math
from dataclasses import dataclass
from functools import cached_property

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy.ndimage import median_filter
from scipy.signal import resample_poly

from vibemodem.core.frame import pseudo_random_bits

SAMPLE_RATE = 48_000
AMPLITUDE = 0.5
CARRIER_HZ = 1500.0  # centre of a Signal sent as is; the receiver finds shifted ones
SEARCH_BAND_HZ = (300.0, 2700.0)
PREAMBLE_SECONDS = 2.56  # as long as the 32 symbols of the M-FSK preamble
MIN_PREAMBLE_BITS = 32
MIN_SCORE = 7.0

_DECIMATION = 8
_WORK_RATE = SAMPLE_RATE // _DECIMATION
_HOPS_PER_BIT = 4  # the search looks at a window every quarter bit
_BINS_PER_BAUD = 8  # the search transform has a bin every eighth of the baud rate
_NOISE_OFFSETS_HZ = (-400.0, -300.0, 300.0, 400.0)
_NOISE_SPAN_HZ = 600.0  # the noise level of a frequency is read over this much of the band
_BATCH = 1024  # windows transformed at a time, to bound the memory used


@dataclass(frozen=True)
class Candidate:
    """Where a Signal may start and where its carrier is."""

    start_sample: int  # at the full sample rate
    carrier_hz: float
    score: float  # how far the preamble match stands out from noise, in standard deviations


@dataclass(frozen=True)
class Waveform:
    """A GFSK waveform: baud rate, modulation index and Gaussian filter."""

    baud: int = 50
    h: float = 0.5
    bt: float | None = 0.5

    def __post_init__(self):
        # A bit must hold a whole number of samples at the working rate, and a quarter bit too.
        if not isinstance(self.baud, int) or self.baud < 1 or 1500 % self.baud:
            raise ValueError(f"baud must be a whole number of bauds dividing 1500, got {self.baud}")
        if not (isinstance(self.h, (int, float)) and math.isfinite(self.h)):
            raise ValueError(f"h must be a finite number, got {self.h}")
        if self.h <= 0:
            raise ValueError(f"h must be positive, got {self.h}")
        if self.bt is not None and not (
            isinstance(self.bt, (int, float)) and math.isfinite(self.bt) and self.bt > 0
        ):
            raise ValueError(f"bt must be a positive number or None, got {self.bt}")

    @cached_property
    def samples_per_bit(self) -> int:
        return SAMPLE_RATE // self.baud

    @cached_property
    def _work_bit(self) -> int:
        return _WORK_RATE // self.baud

    @cached_property
    def _hop(self) -> int:
        return self._work_bit // _HOPS_PER_BIT

    @cached_property
    def _bin_hz(self) -> float:
        return self.baud / _BINS_PER_BAUD

    @cached_property
    def _deviation_hz(self) -> float:
        return self.h * self.baud / 2

    @cached_property
    def _probe_hz(self) -> float:
        """How far from the carrier the receiver measures: the deviation, but at least half the
        baud rate, where the two measurements do not disturb each other (a bit-long window
        cannot tell tones closer than that apart, so for a small `h` the measuring points are
        taken farther out than the tones themselves).
        """
        return max(self._deviation_hz, self.baud / 2)

    @cached_property
    def preamble_bits(self) -> np.ndarray:
        count = max(MIN_PREAMBLE_BITS, round(PREAMBLE_SECONDS * self.baud))
        return pseudo_random_bits(count, state=0x1B7)

    @cached_property
    def _gaussian(self) -> np.ndarray | None:
        if self.bt is None:
            return None
        sigma = math.sqrt(math.log(2)) / (2 * math.pi * self.bt) * self.samples_per_bit
        half = math.ceil(4 * sigma)
        kernel = np.exp(-0.5 * (np.arange(-half, half + 1) / sigma) ** 2)
        return kernel / kernel.sum()

    def synthesize(self, bits: np.ndarray) -> np.ndarray:
        """The audio of these bits: 0 above the carrier, 1 below, from phase zero."""
        steps = np.repeat(1.0 - 2.0 * np.asarray(bits, dtype=float), self.samples_per_bit)
        kernel = self._gaussian
        if kernel is not None:
            half = kernel.size // 2
            steps = np.convolve(np.pad(steps, half, mode="edge"), kernel, mode="valid")
        frequency = CARRIER_HZ + self._deviation_hz * steps
        return AMPLITUDE * np.cos(2 * np.pi * np.cumsum(frequency) / SAMPLE_RATE)

    @staticmethod
    def decimate(samples: np.ndarray) -> np.ndarray:
        """The audio at the rate the receiver works at."""
        return resample_poly(np.asarray(samples, dtype=float), 1, _DECIMATION)

    def _basis(self, carrier_hz: float) -> np.ndarray:
        """Exponentials at the two frequencies, one bit long: columns are bit 0 then bit 1."""
        n = np.arange(self._work_bit)
        rates = np.array([carrier_hz + self._probe_hz, carrier_hz - self._probe_hz])
        return np.exp(-2j * np.pi * np.outer(n, rates) / _WORK_RATE)

    def data_start(self, signal: Candidate) -> int:
        """Where the bits after this Signal's preamble begin, in samples of the working rate."""
        return signal.start_sample // _DECIMATION + self.preamble_bits.size * self._work_bit

    def data_fits(self, work: np.ndarray, signal: Candidate, bits: int) -> bool:
        """Whether the recording holds `bits` bits after the preamble of this Signal."""
        return self.data_start(signal) + bits * self._work_bit <= work.size

    def bit_energies(
        self, work: np.ndarray, start: int, carrier_hz: float, bits: int
    ) -> np.ndarray:
        """Energy at the 0 frequency and at the 1 frequency of each of `bits` bits.

        `start` counts samples of the receiver's working rate.
        """
        size = self._work_bit
        frames = work[start : start + bits * size].reshape(bits, size)
        return np.abs(frames @ self._basis(carrier_hz)) ** 2

    def noise_energy(self, work: np.ndarray, start: int, carrier_hz: float, bits: int) -> float:
        """The energy a bit-long measurement picks up from noise alone.

        Read at frequencies a few hundred Hz either side of the Signal, where it is not, so it
        stays right whatever the Signal does to its own measuring points.
        """
        readings = []
        for offset in _NOISE_OFFSETS_HZ:
            carrier = carrier_hz + offset
            if SEARCH_BAND_HZ[0] <= carrier - self._probe_hz and (
                carrier + self._probe_hz <= SEARCH_BAND_HZ[1]
            ):
                readings.append(self.bit_energies(work, start, carrier, bits).mean())
        return float(np.mean(readings)) if readings else float("nan")

    def _power(self, work: np.ndarray) -> tuple[np.ndarray, int]:
        """Energy of each bit-long window (every quarter bit) at each frequency of the band."""
        size, fft_size = self._work_bit, self._work_bit * _BINS_PER_BAUD
        first = math.ceil(SEARCH_BAND_HZ[0] / self._bin_hz)
        last = math.floor(SEARCH_BAND_HZ[1] / self._bin_hz)
        windows = sliding_window_view(work, size)[:: self._hop]
        power = np.empty((windows.shape[0], last - first + 1))
        for begin in range(0, windows.shape[0], _BATCH):
            spectrum = np.fft.rfft(windows[begin : begin + _BATCH], n=fft_size, axis=1)
            power[begin : begin + _BATCH] = np.abs(spectrum[:, first : last + 1]) ** 2
        return power, first

    def find_signals(
        self, work: np.ndarray, max_candidates: int = 3, min_score: float = MIN_SCORE
    ) -> list[Candidate]:
        """Places where the known preamble matches, over every start time and audio frequency.

        Each preamble bit adds the energy at the frequency of its value minus the one at the
        other frequency, relative to the noise level of that frequency; the sum has a spread of
        sqrt(2 * bits) in noise alone, and the score counts those spreads.

        At most `max_candidates` places are returned, best first.
        """
        bits = self.preamble_bits.size
        if work.size < (bits + 1) * self._work_bit:
            return []
        power, first = self._power(work)
        # A Signal sits on the same frequencies for its whole length, so the noise level cannot
        # be read from the quiet moments of one frequency. It is read from the neighbours: the
        # median over a span several times wider than the Signal of each frequency's mean power.
        span = 2 * round(_NOISE_SPAN_HZ / self._bin_hz / 2) + 1
        noise = median_filter(power.mean(axis=0), size=span, mode="nearest")
        relative = power / np.maximum(noise, 1e-12 * power.max() + 1e-300)

        shift = round(self._probe_hz / self._bin_hz)
        rows = relative.shape[0] - _HOPS_PER_BIT * (bits - 1)
        columns = relative.shape[1] - 2 * shift
        signs = 1.0 - 2.0 * self.preamble_bits
        match = np.zeros((rows, columns))
        for bit, sign in enumerate(signs):
            row = _HOPS_PER_BIT * bit
            upper = relative[row : row + rows, 2 * shift :]
            lower = relative[row : row + rows, :columns]
            match += sign * (upper - lower)
        scores = match / math.sqrt(2 * bits)

        found = []
        for _ in range(max_candidates):
            row, column = np.unravel_index(np.argmax(scores), scores.shape)
            if scores[row, column] < min_score:
                break
            found.append(
                Candidate(
                    start_sample=int(row * self._hop * _DECIMATION),
                    carrier_hz=float((first + column + shift) * self._bin_hz),
                    score=float(scores[row, column]),
                )
            )
            scores[
                max(0, row - _HOPS_PER_BIT) : row + _HOPS_PER_BIT + 1,
                max(0, column - shift - 1) : column + shift + 2,
            ] = -np.inf
        return found

    def refine(self, work: np.ndarray, candidate: Candidate) -> Candidate:
        """Pin the start and the carrier down more finely than the search grid."""
        bits = self.preamble_bits.size
        signs = 1.0 - 2.0 * self.preamble_bits
        centre = candidate.start_sample // _DECIMATION
        best_value, best = -np.inf, candidate
        for shift_hz in np.linspace(-self._bin_hz / 2, self._bin_hz / 2, 5):
            carrier = candidate.carrier_hz + shift_hz
            for shift in range(-self._hop // 2, self._hop // 2 + 1):
                start = centre + shift
                if start < 0 or start + bits * self._work_bit > work.size:
                    continue
                energy = self.bit_energies(work, start, carrier, bits)
                value = float(signs @ (energy[:, 0] - energy[:, 1]))
                if value > best_value:
                    best_value = value
                    best = Candidate(start * _DECIMATION, float(carrier), candidate.score)
        return best
