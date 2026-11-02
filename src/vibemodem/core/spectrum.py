"""One row of the spectrum of a block of sound: the audio band in bins of 5 Hz, in dB.

A row per block of sound, one under the other, is a waterfall. The levels are relative to a
sine of full scale: a tone of amplitude 1 shows about 0 dB at its bin.
"""

import numpy as np

BAND_HZ = (300.0, 2700.0)
BIN_HZ = 5.0
BINS = round((BAND_HZ[1] - BAND_HZ[0]) / BIN_HZ)
SILENCE_DB = -120.0
SAMPLE_RATE = 48_000
MIN_SAMPLES = 480  # 10 ms: the finest resolution a bin of 5 Hz needs is 200 ms, this is a floor


def spectrum_row(block: np.ndarray) -> np.ndarray:
    """The power in each bin of 5 Hz from 300 to 2700 Hz, in dB (-120 for nothing at all)."""
    block = np.asarray(block, dtype=np.float64)
    if block.ndim != 1 or block.size < MIN_SAMPLES or not np.isfinite(block).all():
        raise ValueError(f"need one channel of at least {MIN_SAMPLES} finite samples")
    window = np.hanning(block.size)
    amplitude = np.abs(np.fft.rfft(block * window)) / (window.sum() / 2)  # a full-scale tone: 1
    frequencies = np.fft.rfftfreq(block.size, 1 / SAMPLE_RATE)
    cell = np.floor((frequencies - BAND_HZ[0]) / BIN_HZ).astype(int)
    inside = (cell >= 0) & (cell < BINS)
    # The loudest FFT bin of each cell: a tone must show its level whatever the block length.
    loudest = np.zeros(BINS)
    np.maximum.at(loudest, cell[inside], amplitude[inside] ** 2)
    return 10 * np.log10(np.maximum(loudest, 10 ** (SILENCE_DB / 10)))
