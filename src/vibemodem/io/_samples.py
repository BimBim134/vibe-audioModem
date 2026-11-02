"""The one check every way of playing or storing audio shares."""

import numpy as np


def checked_samples(samples: np.ndarray) -> np.ndarray:
    """The samples as floats, once known to be one channel of finite numbers within full scale."""
    samples = np.asarray(samples, dtype=np.float64)
    if samples.ndim != 1 or not np.isfinite(samples).all():
        raise ValueError("audio must be one channel of finite numbers")
    if samples.size and np.max(np.abs(samples)) > 1.0:
        raise ValueError("audio goes beyond full scale (-1 to 1) and would be clipped")
    return samples
