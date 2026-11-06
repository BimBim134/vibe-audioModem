"""WAV files: 16-bit mono at 48 kHz written; the usual formats read, at 48 kHz only."""

import struct
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from vibemodem.core.coded_modem import SAMPLE_RATE
from vibemodem.io._samples import checked_samples


class WavError(ValueError):
    """The file is not a WAV the modem can use."""


def write_wav(path: str | Path, samples: np.ndarray) -> None:
    """Write samples between -1 and 1 as a 16-bit mono WAV at the modem's sample rate."""
    samples = checked_samples(samples)
    wavfile.write(path, SAMPLE_RATE, np.round(samples * 32767).astype(np.int16))


def read_wav(path: str | Path) -> np.ndarray:
    """Float32 samples between -1 and 1; several channels are averaged into one."""
    try:
        rate, data = wavfile.read(path)
    except (ValueError, EOFError, struct.error) as error:  # what scipy raises on a bad file
        raise WavError(f"{path} is not a readable WAV file: {error}") from error
    if rate != SAMPLE_RATE:
        raise WavError(
            f"{path} is at {rate} Hz, the modem works at {SAMPLE_RATE} Hz: "
            "record or export it at 48000 Hz"
        )
    if data.dtype == np.uint8:
        samples = (data.astype(np.float32) - 128.0) / 128.0
    elif np.issubdtype(data.dtype, np.integer):
        samples = data.astype(np.float32) / float(np.iinfo(data.dtype).max + 1)
    else:
        samples = data.astype(np.float32)
    return samples.mean(axis=1) if samples.ndim == 2 else samples
