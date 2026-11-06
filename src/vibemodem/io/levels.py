"""Is the input level fit for the receiver? Peak and RMS level, and warnings."""

from dataclasses import dataclass

import numpy as np

CLIP_LEVEL = 0.99  # of full scale
CLIP_ONE_IN = 1000  # one clipped sample in so many (0.1%) is clipping
LOW_RMS_DBFS = -50.0  # near silence: a radio with its band noise gives -40 to -20 dBFS
SILENCE_DBFS = -120.0


@dataclass(frozen=True)
class LevelReport:
    peak: float
    rms_dbfs: float
    clipping: bool
    too_low: bool

    @property
    def messages(self) -> list[str]:
        """What to tell the operator, in words."""
        messages = []
        if self.too_low:
            messages.append(
                f"the input level is too low ({self.rms_dbfs:.0f} dBFS): raise the input gain "
                "or the radio's audio output"
            )
        if self.clipping:
            messages.append(
                "the input is clipping: lower the input gain or the radio's audio output"
            )
        return messages


def check_level(samples: np.ndarray) -> LevelReport:
    """Measure samples between -1 and 1 (full scale) and flag low levels and clipping."""
    samples = np.asarray(samples, dtype=float)
    if samples.ndim != 1 or samples.size == 0:
        raise ValueError("need audio of one channel and at least one sample")
    if not np.isfinite(samples).all():
        raise ValueError("audio samples must be finite numbers")
    rms = float(np.sqrt(np.mean(samples**2)))
    rms_dbfs = max(SILENCE_DBFS, 20 * np.log10(rms)) if rms > 0 else SILENCE_DBFS
    clipped = np.count_nonzero(np.abs(samples) >= CLIP_LEVEL)
    return LevelReport(
        peak=float(np.max(np.abs(samples))),
        rms_dbfs=float(rms_dbfs),
        clipping=clipped * CLIP_ONE_IN >= samples.size,
        too_low=rms_dbfs < LOW_RMS_DBFS,
    )
