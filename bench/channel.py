"""Channel simulator: what a weak-signal SSB audio channel does to a Transmission."""

from dataclasses import dataclass

import numpy as np
from scipy import interpolate, signal

REFERENCE_BANDWIDTH_HZ = 2500

# Each random impairment draws from its own stream, so switching one on or off does not
# change the random numbers another one sees.
NOISE_STREAM = 0
IMPULSE_STREAM = 1
FADING_STREAM = 2

SSB_PASSBAND_HZ = (300, 2700)
SSB_FILTER_ORDER = 12  # -6 dB at the nominal 300 and 2,700 Hz edges once applied zero-phase


@dataclass(frozen=True)
class ChannelConfig:
    """Which impairments to apply. Every impairment is off by default."""

    sample_rate: float = 48_000
    snr_db: float | None = None  # white noise, SNR in a 2,500 Hz reference bandwidth
    fading_doppler_hz: float | None = None  # Rayleigh fading; bandwidth of the gain variation
    clock_drift_ppm: float = 0.0  # > 0: the receiver's sample clock runs fast
    freq_offset_hz: float = 0.0  # radios mistuned: every frequency shifts by this amount
    impulse_rate_hz: float = 0.0  # bursts per second of impulsive noise (static crashes)
    impulse_duration_s: float = 0.001
    impulse_amplitude: float = 1.0  # standard deviation inside a burst, in sample units
    band_filter: bool = False  # keep only the 300-2,700 Hz SSB audio passband
    clip_level: float | None = None  # hard clipping of the receiver's audio input

    def __post_init__(self) -> None:
        problems = []
        if self.snr_db is not None and not np.isfinite(self.snr_db):
            problems.append("snr_db must be a finite number")
        if self.sample_rate <= 0:
            problems.append("sample_rate must be positive")
        if self.clip_level is not None and self.clip_level <= 0:
            problems.append("clip_level must be positive")
        if self.impulse_rate_hz < 0:
            problems.append("impulse_rate_hz must not be negative")
        if self.impulse_duration_s <= 0:
            problems.append("impulse_duration_s must be positive")
        if self.impulse_amplitude < 0:
            problems.append("impulse_amplitude must not be negative")
        if self.fading_doppler_hz is not None and self.fading_doppler_hz <= 0:
            problems.append("fading_doppler_hz must be positive")
        if self.clock_drift_ppm <= -1_000_000:
            problems.append("clock_drift_ppm must be above -1,000,000")
        if problems:
            raise ValueError("; ".join(problems))


def _rng(seed: int, stream: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence(seed, spawn_key=(stream,)))


def _add_noise(samples: np.ndarray, config: ChannelConfig, seed: int) -> np.ndarray:
    signal_power = np.mean(samples**2)
    noise_power_in_reference = signal_power / 10 ** (config.snr_db / 10)
    # White noise spreads its power evenly over 0..fs/2.
    total_noise_power = noise_power_in_reference * (config.sample_rate / 2) / REFERENCE_BANDWIDTH_HZ
    noise = _rng(seed, NOISE_STREAM).normal(0.0, np.sqrt(total_noise_power), samples.shape)
    return samples + noise


def _fade(samples: np.ndarray, config: ChannelConfig, seed: int) -> np.ndarray:
    """Multiply by a slowly varying complex Gaussian gain (flat Rayleigh fading)."""
    rng = _rng(seed, FADING_STREAM)
    # Build the gain at a low rate, 20 samples per Doppler period, then interpolate up.
    gain_rate = 20 * config.fading_doppler_hz
    seconds = samples.size / config.sample_rate
    count = int(np.ceil(seconds * gain_rate)) + 2
    white = rng.normal(size=count) + 1j * rng.normal(size=count)
    sos = signal.butter(2, config.fading_doppler_hz, fs=gain_rate, output="sos")
    gain = signal.sosfilt(sos, white)
    gain /= np.sqrt(np.mean(np.abs(gain) ** 2))  # unit average power
    times = np.arange(count) / gain_rate
    at = np.arange(samples.size) / config.sample_rate
    smooth = interpolate.CubicSpline(times, gain)(at)
    return np.real(signal.hilbert(samples) * smooth)


def _drift_clock(samples: np.ndarray, config: ChannelConfig) -> np.ndarray:
    ratio = 1 + config.clock_drift_ppm * 1e-6
    # Receiver sample n is taken at input time n / ratio. The output keeps the input length:
    # if the receiver clock runs slow, the tail past the end of the input is silence.
    positions = np.arange(samples.size) / ratio
    spline = interpolate.CubicSpline(np.arange(samples.size), samples)
    return np.where(positions <= samples.size - 1, spline(positions), 0.0)


def _shift_frequency(samples: np.ndarray, config: ChannelConfig) -> np.ndarray:
    t = np.arange(samples.size) / config.sample_rate
    analytic = signal.hilbert(samples)
    return np.real(analytic * np.exp(2j * np.pi * config.freq_offset_hz * t))


def _add_impulses(samples: np.ndarray, config: ChannelConfig, seed: int) -> np.ndarray:
    rng = _rng(seed, IMPULSE_STREAM)
    seconds = samples.size / config.sample_rate
    burst_length = max(1, round(config.impulse_duration_s * config.sample_rate))
    out = samples.copy()
    for start in rng.integers(0, samples.size, rng.poisson(config.impulse_rate_hz * seconds)):
        stop = min(start + burst_length, samples.size)
        out[start:stop] += rng.normal(0.0, config.impulse_amplitude, stop - start)
    return out


def _band_filter(samples: np.ndarray, config: ChannelConfig) -> np.ndarray:
    sos = signal.butter(
        SSB_FILTER_ORDER, SSB_PASSBAND_HZ, btype="bandpass", fs=config.sample_rate, output="sos"
    )
    return signal.sosfiltfilt(sos, samples)  # zero phase: adds no delay


def apply_channel(samples: np.ndarray, config: ChannelConfig, seed: int) -> np.ndarray:
    """Pass audio through the channel, in the order a real signal meets each stage."""
    out = np.array(samples, dtype=float)
    if out.ndim != 1:
        raise ValueError("samples must be a single channel (1-D array)")
    if config.fading_doppler_hz:
        out = _fade(out, config, seed)
    if config.freq_offset_hz:
        out = _shift_frequency(out, config)
    if config.snr_db is not None:
        out = _add_noise(out, config, seed)
    if config.impulse_rate_hz:
        out = _add_impulses(out, config, seed)
    if config.band_filter:
        out = _band_filter(out, config)
    if config.clip_level is not None:
        out = np.clip(out, -config.clip_level, config.clip_level)
    if config.clock_drift_ppm:
        out = _drift_clock(out, config)
    return out
