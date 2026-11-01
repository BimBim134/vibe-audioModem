"""8-FSK in about 100 Hz: building the audio, measuring tone energies and finding a Signal.

Eight tones 12.5 Hz apart, one tone per 80 ms symbol (spacing = 1 / symbol duration, so the
tones do not disturb each other in a non-coherent receiver). The phase is continuous from one
symbol to the next, which keeps the occupied band narrow.
"""

import math
from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from vibemodem.core.frame import pseudo_random_bits

SAMPLE_RATE = 48_000
TONES = 8
BITS_PER_SYMBOL = 3
TONE_SPACING_HZ = 12.5
SYMBOL_SECONDS = 1 / TONE_SPACING_HZ
SAMPLES_PER_SYMBOL = round(SAMPLE_RATE * SYMBOL_SECONDS)
AMPLITUDE = 0.5
FIRST_TONE_HZ = 1450.0  # lowest tone of a Signal sent as is; the receiver finds shifted ones

SEARCH_BAND_HZ = (300.0, 2700.0)

# A receiver never sees less noise than a small fraction of its loudest signal (real audio has
# a floor about 90 dB down), and without this a noiseless recording would make the faintest
# spectral leakage look huge once divided by a noise level of zero.
NOISE_FLOOR_RATIO = 1e-6

# A tone number written in bits, most significant first: 5 is 1, 0, 1.
BIT_WEIGHTS = 2 ** np.arange(BITS_PER_SYMBOL - 1, -1, -1)
BIT_WEIGHTS.flags.writeable = False

PREAMBLE_SYMBOLS = 32
_PREAMBLE_BITS = pseudo_random_bits(PREAMBLE_SYMBOLS * BITS_PER_SYMBOL, state=0x2D9)
PREAMBLE_TONES = _PREAMBLE_BITS.reshape(PREAMBLE_SYMBOLS, BITS_PER_SYMBOL) @ BIT_WEIGHTS
PREAMBLE_TONES.flags.writeable = False  # shared by every modem

# The search looks at a window every quarter symbol and every half tone spacing.
_HOP = SAMPLES_PER_SYMBOL // 4
_FFT_SIZE = 2 * SAMPLES_PER_SYMBOL
_BIN_HZ = SAMPLE_RATE / _FFT_SIZE
_FIRST_BIN = math.ceil(SEARCH_BAND_HZ[0] / _BIN_HZ)
_LAST_BIN = math.floor(SEARCH_BAND_HZ[1] / _BIN_HZ)
_BINS_PER_TONE = round(TONE_SPACING_HZ / _BIN_HZ)  # 2
_HOPS_PER_SYMBOL = SAMPLES_PER_SYMBOL // _HOP  # 4
_SPECTROGRAM_BATCH = 256  # windows transformed at a time, to bound the memory used

# Frequencies tried around a found Signal, in eighths of the tone spacing (up to a half bin).
_REFINE_SHIFTS_HZ = tuple(step * TONE_SPACING_HZ / 8 for step in (-2, -1, 0, 1, 2))


def synthesize(tones: np.ndarray) -> np.ndarray:
    """Audio for a sequence of tone numbers (0 to 7), one per symbol."""
    frequencies = FIRST_TONE_HZ + TONE_SPACING_HZ * np.repeat(tones, SAMPLES_PER_SYMBOL)
    return AMPLITUDE * np.sin(2 * np.pi * np.cumsum(frequencies) / SAMPLE_RATE)


def _tone_basis(first_tone_hz: float) -> np.ndarray:
    """One complex sinusoid per tone, as columns, to measure a symbol's energy at each tone."""
    time = np.arange(SAMPLES_PER_SYMBOL) / SAMPLE_RATE
    frequencies = first_tone_hz + TONE_SPACING_HZ * np.arange(TONES)
    return np.exp(-2j * np.pi * np.outer(time, frequencies))


def tone_energies(
    samples: np.ndarray, start: int, first_tone_hz: float, symbols: int
) -> np.ndarray:
    """Energy at each of the 8 tones for consecutive symbols: shape (symbols, 8)."""
    frames = samples[start : start + symbols * SAMPLES_PER_SYMBOL].reshape(
        symbols, SAMPLES_PER_SYMBOL
    )
    return np.abs(frames @ _tone_basis(first_tone_hz)) ** 2


@dataclass(frozen=True)
class Candidate:
    """Where a Signal may start and where its lowest tone is."""

    start_sample: int
    first_tone_hz: float
    score: float  # how far the preamble match stands out from noise, in standard deviations


def _spectrogram(samples: np.ndarray) -> np.ndarray:
    """Energy per 6.25 Hz bin of the search band, for a window every quarter symbol."""
    frames = sliding_window_view(samples, SAMPLES_PER_SYMBOL)[::_HOP]
    power = np.empty((len(frames), _LAST_BIN - _FIRST_BIN + 1))
    for low in range(0, len(frames), _SPECTROGRAM_BATCH):
        batch = frames[low : low + _SPECTROGRAM_BATCH]
        spectrum = np.fft.rfft(batch, n=_FFT_SIZE, axis=1)
        spectrum = spectrum[:, _FIRST_BIN : _LAST_BIN + 1]
        power[low : low + _SPECTROGRAM_BATCH] = spectrum.real**2 + spectrum.imag**2
    return power


def find_signals(
    samples: np.ndarray, max_candidates: int = 3, min_score: float = 7.0
) -> list[Candidate]:
    """Places where the known preamble matches, over every start time and audio frequency.

    The match adds up the energy at the expected tone of each preamble symbol, relative to the
    noise level of that frequency. In noise alone each term averages 1, so the sum averages
    the number of symbols with a spread of its square root; the score counts those spreads.

    At most `max_candidates` places are returned, best first, so a recording that holds more
    Signals than that loses the weakest ones.
    """
    preamble_symbols = PREAMBLE_SYMBOLS
    if samples.size < SAMPLES_PER_SYMBOL + (preamble_symbols - 1) * SAMPLES_PER_SYMBOL:
        return []
    power = _spectrogram(samples)
    noise = np.median(power, axis=0) / np.log(2)  # the median of an exponential is mean * ln 2
    noise = np.maximum(noise, NOISE_FLOOR_RATIO * power.max() + 1e-300)
    relative = power / noise

    rows = relative.shape[0] - _HOPS_PER_SYMBOL * (preamble_symbols - 1)
    columns = relative.shape[1] - _BINS_PER_TONE * (TONES - 1)
    match = np.zeros((rows, columns))
    for symbol, tone in enumerate(PREAMBLE_TONES):
        row = _HOPS_PER_SYMBOL * symbol
        column = _BINS_PER_TONE * tone
        match += relative[row : row + rows, column : column + columns]
    scores = (match - preamble_symbols) / math.sqrt(preamble_symbols)

    found = []
    for _ in range(max_candidates):
        row, column = np.unravel_index(np.argmax(scores), scores.shape)
        if scores[row, column] < min_score:
            break
        found.append(
            Candidate(
                start_sample=int(row * _HOP),
                first_tone_hz=float((_FIRST_BIN + column) * _BIN_HZ),
                score=float(scores[row, column]),
            )
        )
        scores[
            max(0, row - _HOPS_PER_SYMBOL) : row + _HOPS_PER_SYMBOL + 1,
            max(0, column - 2 * _BINS_PER_TONE) : column + 2 * _BINS_PER_TONE + 1,
        ] = -np.inf
    return found


def refine(samples: np.ndarray, candidate: Candidate) -> Candidate:
    """Pin the start and the frequency down more finely than the search grid.

    The grid is a quarter symbol and 6.25 Hz wide, which already costs energy and leaks one
    symbol into the next; trying nearby starts and frequencies recovers it.
    """
    preamble_symbols = PREAMBLE_SYMBOLS
    best_energy, best = -1.0, candidate
    for shift_hz in _REFINE_SHIFTS_HZ:
        first_tone_hz = candidate.first_tone_hz + shift_hz
        basis = _tone_basis(first_tone_hz)
        for shift in range(-_HOP // 2, _HOP // 2 + 1, _HOP // 8):
            start = candidate.start_sample + shift
            if start < 0 or start + preamble_symbols * SAMPLES_PER_SYMBOL > samples.size:
                continue
            frames = samples[start : start + preamble_symbols * SAMPLES_PER_SYMBOL].reshape(
                preamble_symbols, -1
            )
            energy = np.abs(frames @ basis) ** 2
            total = float(energy[np.arange(preamble_symbols), PREAMBLE_TONES].sum())
            if total > best_energy:
                best_energy = total
                best = Candidate(start, first_tone_hz, candidate.score)
    return best
