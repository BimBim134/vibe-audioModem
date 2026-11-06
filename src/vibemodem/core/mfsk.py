"""M-FSK: building the audio, measuring tone energies and finding a Signal.

One tone per symbol, tones spaced by 1 / symbol duration so they do not disturb each other in a
non-coherent receiver. The phase is continuous from one symbol to the next, which keeps the
occupied band narrow. The standard waveform is 8 tones of 80 ms, 12.5 Hz apart, in about 100 Hz;
other numbers of tones and symbol durations are there to be swept on the bench.
"""

import math
from dataclasses import dataclass
from functools import cached_property

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from vibemodem.core.frame import pseudo_random_bits

SAMPLE_RATE = 48_000
AMPLITUDE = 0.5
FIRST_TONE_HZ = 1450.0  # lowest tone of a Signal sent as is; the receiver finds shifted ones
SEARCH_BAND_HZ = (300.0, 2700.0)
PREAMBLE_SYMBOLS = 32

# A receiver never sees less noise than a small fraction of its loudest signal. Without this a
# noiseless recording would make the faintest spectral leakage look huge once divided by a
# noise level of zero: the leakage of a signal with short symbols is only about 40 dB down, and
# it follows the tones sent, so at 1e-6 it was found as a preamble where there was none. 1e-3 is
# far below any noise a weak signal sits in (30 dB under the strongest tone).
NOISE_FLOOR_RATIO = 1e-3
SYMBOL_MATCH_CAP = 16.0  # most one symbol adds to a match: a click is one loud symbol, not 32

SUPPORTED_TONES = (2, 4, 8, 16)
# The noise level of a frequency is read from a low share of the recording's windows, below the
# ones where a tone of the Signal sits. A given frequency carries a tone for about 1 / tones of
# the time, so with few tones the median would be read inside the Signal itself.
_NOISE_QUANTILE = {2: 0.25, 4: 0.375, 8: 0.5, 16: 0.5}
# The search looks at a window every quarter symbol, and the refinement tries starts an eighth
# of that apart, so a symbol must hold a multiple of 32 samples.
_SAMPLES_PER_SEARCH_STEP = 32
_SPECTROGRAM_BATCH = 256  # windows transformed at a time, to bound the memory used
_HOPS_PER_SYMBOL = 4
_BINS_PER_TONE = 2  # the FFT is twice the symbol long: bins are half a tone spacing apart


@dataclass(frozen=True)
class Candidate:
    """Where a Signal may start and where its lowest tone is."""

    start_sample: int
    first_tone_hz: float
    score: float  # how far the preamble match stands out from noise, in standard deviations
    inside_band: bool = True  # False: outside the band searched, kept for its side peaks only


@dataclass(frozen=True)
class Waveform:
    """An M-FSK waveform: how many tones, how long a symbol lasts, where the lowest tone is."""

    tones: int = 8
    symbol_seconds: float = 0.08
    first_tone_hz: float = FIRST_TONE_HZ

    def __post_init__(self):
        if self.tones not in SUPPORTED_TONES:
            raise ValueError(f"tones must be one of {SUPPORTED_TONES}, got {self.tones}")
        samples = self.symbol_seconds * SAMPLE_RATE
        if not (
            samples >= _SAMPLES_PER_SEARCH_STEP
            and math.isclose(samples, round(samples), abs_tol=1e-6)
            and round(samples) % _SAMPLES_PER_SEARCH_STEP == 0
            and self.symbol_seconds <= 1.0
        ):
            raise ValueError(
                "symbol duration must be at most 1 s and a whole number of samples that is a "
                f"multiple of {_SAMPLES_PER_SEARCH_STEP}, got {self.symbol_seconds} s"
            )
        low, high = self.first_tone_range_hz
        if not low <= self.first_tone_hz <= high:
            raise ValueError(
                f"the first tone must be between {low:g} and {high:g} Hz for this waveform "
                f"(the whole Signal in the {SEARCH_BAND_HZ[0]:g} to {SEARCH_BAND_HZ[1]:g} Hz "
                f"band), got {self.first_tone_hz}"
            )

    @cached_property
    def first_tone_range_hz(self) -> tuple[float, float]:
        """Where the lowest tone may be for the whole Signal to stay in the audio band, with two
        tone spacings to spare below the lowest tone and above the highest (the band at -20 dB
        reaches up to 1.2 spacings beyond the outer tones)."""
        return (
            SEARCH_BAND_HZ[0] + 2 * self.spacing_hz,
            SEARCH_BAND_HZ[1] - (self.tones + 1) * self.spacing_hz,
        )

    @cached_property
    def bits_per_symbol(self) -> int:
        return self.tones.bit_length() - 1

    @cached_property
    def spacing_hz(self) -> float:
        return 1 / self.symbol_seconds

    @cached_property
    def samples_per_symbol(self) -> int:
        return round(SAMPLE_RATE * self.symbol_seconds)

    @cached_property
    def bit_weights(self) -> np.ndarray:
        """A tone number written in bits, most significant first: 5 of 8 tones is 1, 0, 1."""
        weights = 2 ** np.arange(self.bits_per_symbol - 1, -1, -1)
        weights.flags.writeable = False
        return weights

    @cached_property
    def preamble_tones(self) -> np.ndarray:
        bits = pseudo_random_bits(PREAMBLE_SYMBOLS * self.bits_per_symbol, state=0x2D9)
        tones = bits.reshape(PREAMBLE_SYMBOLS, self.bits_per_symbol) @ self.bit_weights
        tones.flags.writeable = False  # shared by every modem
        return tones

    @cached_property
    def zero_tones(self) -> np.ndarray:
        """For each bit of a symbol, which tones stand for a 0."""
        zero_tones = np.array(
            [
                [(tone >> (self.bits_per_symbol - 1 - bit)) & 1 == 0 for tone in range(self.tones)]
                for bit in range(self.bits_per_symbol)
            ]
        )
        zero_tones.flags.writeable = False
        return zero_tones

    @cached_property
    def _hop(self) -> int:
        return self.samples_per_symbol // _HOPS_PER_SYMBOL

    @property
    def search_step_samples(self) -> int:
        """The step of the search for a Signal in time: the search looks at the start times of
        a recording that are multiples of it."""
        return self._hop

    @cached_property
    def _fft_size(self) -> int:
        return 2 * self.samples_per_symbol

    @cached_property
    def _bin_hz(self) -> float:
        return SAMPLE_RATE / self._fft_size

    @cached_property
    def _first_bin(self) -> int:
        return math.ceil(SEARCH_BAND_HZ[0] / self._bin_hz)

    @cached_property
    def _last_bin(self) -> int:
        return math.floor(SEARCH_BAND_HZ[1] / self._bin_hz)

    @cached_property
    def _refine_shifts_hz(self) -> tuple[float, ...]:
        # Frequencies tried around a found Signal, in eighths of the tone spacing (up to a bin).
        return tuple(step * self.spacing_hz / 8 for step in (-2, -1, 0, 1, 2))

    def synthesize(self, tones: np.ndarray) -> np.ndarray:
        """Audio for a sequence of tone numbers, one per symbol."""
        frequencies = self.first_tone_hz + self.spacing_hz * np.repeat(
            tones, self.samples_per_symbol
        )
        return AMPLITUDE * np.sin(2 * np.pi * np.cumsum(frequencies) / SAMPLE_RATE)

    def _tone_basis(self, first_tone_hz: float) -> np.ndarray:
        """One complex sinusoid per tone, as columns, to measure a symbol's energy at each tone."""
        time = np.arange(self.samples_per_symbol) / SAMPLE_RATE
        frequencies = first_tone_hz + self.spacing_hz * np.arange(self.tones)
        return np.exp(-2j * np.pi * np.outer(time, frequencies))

    def tone_energies(
        self, samples: np.ndarray, start: int, first_tone_hz: float, symbols: int
    ) -> np.ndarray:
        """Energy at each tone for consecutive symbols: shape (symbols, tones)."""
        size = self.samples_per_symbol
        frames = samples[start : start + symbols * size].reshape(symbols, size)
        return np.abs(frames @ self._tone_basis(first_tone_hz)) ** 2

    def _spectrogram(self, samples: np.ndarray) -> np.ndarray:
        """Energy per half-tone-spacing bin of the search band, a window every quarter symbol."""
        frames = sliding_window_view(samples, self.samples_per_symbol)[:: self._hop]
        power = np.empty((len(frames), self._last_bin - self._first_bin + 1))
        for low in range(0, len(frames), _SPECTROGRAM_BATCH):
            batch = frames[low : low + _SPECTROGRAM_BATCH]
            spectrum = np.fft.rfft(batch, n=self._fft_size, axis=1)
            spectrum = spectrum[:, self._first_bin : self._last_bin + 1]
            power[low : low + _SPECTROGRAM_BATCH] = spectrum.real**2 + spectrum.imag**2
        return power

    @cached_property
    def occupied_hz(self) -> float:
        """From the lowest tone to the highest."""
        return (self.tones - 1) * self.spacing_hz

    def find_signals(
        self,
        samples: np.ndarray,
        max_candidates: int = 3,
        min_score: float = 7.0,
        band_hz: tuple[float, float] | None = None,
    ) -> list[Candidate]:
        """Places where the known preamble matches, over every start time and audio frequency.

        The match adds up the energy at the expected tone of each preamble symbol, relative to
        the noise level of that frequency, minus the average of the other tones at that moment:
        a Preamble has its energy on one tone, a click or a burst of noise on all of them. In
        noise alone each term averages 0, so the sum has a spread of the square root of the
        number of symbols (and of the extra variance of the average taken off); the score counts
        those spreads. A symbol adds at most `SYMBOL_MATCH_CAP`.

        At most `max_candidates` places are returned, best first, so a recording that holds more
        Signals than that loses the weakest ones. With `band_hz`, the Signals whose tones are not
        all inside that band of audio are marked `inside_band=False` and do not count in the
        maximum; they are returned so that their side peaks are not taken for Signals. The noise
        is measured everywhere.
        """
        size = self.samples_per_symbol
        if samples.size < PREAMBLE_SYMBOLS * size:
            return []
        power = self._spectrogram(samples)
        quantile = _NOISE_QUANTILE[self.tones]
        # The q-quantile of an exponential variable is its mean * -ln(1 - q).
        noise = np.quantile(power, quantile, axis=0) / -np.log(1 - quantile)
        noise = np.maximum(noise, NOISE_FLOOR_RATIO * power.max() + 1e-300)
        relative = np.minimum(power / noise, SYMBOL_MATCH_CAP)

        rows = relative.shape[0] - _HOPS_PER_SYMBOL * (PREAMBLE_SYMBOLS - 1)
        columns = relative.shape[1] - _BINS_PER_TONE * (self.tones - 1)
        # Per start and frequency, the sum over the tones of the energy at one moment: the
        # energy of a tone minus the average of the others is tones/(tones-1) times the energy
        # of the tone minus the sum over its tones, divided by tones - 1.
        every_tone = sum(
            relative[:, _BINS_PER_TONE * tone : _BINS_PER_TONE * tone + columns]
            for tone in range(self.tones)
        )
        match = np.zeros((rows, columns))
        for symbol, tone in enumerate(self.preamble_tones):
            row = _HOPS_PER_SYMBOL * symbol
            column = _BINS_PER_TONE * tone
            match += self.tones * relative[row : row + rows, column : column + columns]
            match -= every_tone[row : row + rows]
        match /= self.tones - 1
        spread = math.sqrt(PREAMBLE_SYMBOLS * (1 + 1 / (self.tones - 1)))
        scores = match / spread

        found = []
        wanted = 0  # Signals inside the band; those outside are found too, without counting
        for _ in range(max_candidates * (1 if band_hz is None else 2)):
            row, column = np.unravel_index(np.argmax(scores), scores.shape)
            if scores[row, column] < min_score:
                break
            first_tone_hz = float((self._first_bin + column) * self._bin_hz)
            inside = band_hz is None or (
                band_hz[0] <= first_tone_hz and first_tone_hz + self.occupied_hz <= band_hz[1]
            )
            found.append(
                Candidate(int(row * self._hop), first_tone_hz, float(scores[row, column]), inside)
            )
            wanted += inside
            if wanted == max_candidates:
                break
            scores[
                max(0, row - _HOPS_PER_SYMBOL) : row + _HOPS_PER_SYMBOL + 1,
                max(0, column - 2 * _BINS_PER_TONE) : column + 2 * _BINS_PER_TONE + 1,
            ] = -np.inf
        return found

    def refine(self, samples: np.ndarray, candidate: Candidate) -> Candidate:
        """Pin the start and the frequency down more finely than the search grid.

        The grid is a quarter symbol and half a tone spacing wide, which already costs energy and
        leaks one symbol into the next; trying nearby starts and frequencies recovers it.
        """
        size = self.samples_per_symbol
        best_energy, best = -1.0, candidate
        for shift_hz in self._refine_shifts_hz:
            first_tone_hz = candidate.first_tone_hz + shift_hz
            basis = self._tone_basis(first_tone_hz)
            for shift in range(-self._hop // 2, self._hop // 2 + 1, self._hop // 8):
                start = candidate.start_sample + shift
                if start < 0 or start + PREAMBLE_SYMBOLS * size > samples.size:
                    continue
                frames = samples[start : start + PREAMBLE_SYMBOLS * size].reshape(
                    PREAMBLE_SYMBOLS, -1
                )
                energy = np.abs(frames @ basis) ** 2
                total = float(energy[np.arange(PREAMBLE_SYMBOLS), self.preamble_tones].sum())
                if total > best_energy:
                    best_energy = total
                    best = Candidate(start, first_tone_hz, candidate.score, candidate.inside_band)
        return best


STANDARD = Waveform()
