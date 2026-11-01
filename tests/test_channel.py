"""Channel simulator: what comes out of apply_channel for a given config."""

import numpy as np
import pytest
from scipy import signal

from bench.channel import ChannelConfig, apply_channel

FS = 48_000


def tone(freq_hz, seconds=2.0, amplitude=0.5):
    t = np.arange(int(seconds * FS)) / FS
    return amplitude * np.sin(2 * np.pi * freq_hz * t)


def test_a_channel_with_every_impairment_off_returns_the_audio_unchanged():
    audio = tone(1000)
    out = apply_channel(audio, ChannelConfig(), seed=1)
    np.testing.assert_array_equal(out, audio)


def snr_in_2500_hz(clean, noisy):
    """Measured SNR: signal power over the noise power found in a 2,500 Hz band."""
    freqs, psd = signal.welch(noisy - clean, fs=FS, nperseg=4096)
    band = (freqs >= 300) & (freqs < 2800)
    noise_power = np.mean(psd[band]) * 2500
    return 10 * np.log10(np.mean(clean**2) / noise_power)


@pytest.mark.parametrize("snr_db", [-10, 0, 10])
def test_noise_is_added_at_the_requested_snr_in_2500_hz(snr_db):
    audio = tone(1000, seconds=20)
    noisy = apply_channel(audio, ChannelConfig(snr_db=snr_db), seed=7)
    assert snr_in_2500_hz(audio, noisy) == pytest.approx(snr_db, abs=0.3)


def gain_db(freq_hz, config):
    audio = tone(freq_hz, seconds=2.0, amplitude=0.5)
    out = apply_channel(audio, config, seed=1)
    settled = slice(FS // 2, -FS // 2)  # ignore the start and end of the filtered tone
    return 20 * np.log10(np.std(out[settled]) / np.std(audio[settled]))


@pytest.mark.parametrize("freq_hz", [500, 1000, 2500])
def test_band_filter_passes_the_ssb_passband(freq_hz):
    assert gain_db(freq_hz, ChannelConfig(band_filter=True)) == pytest.approx(0, abs=1)


@pytest.mark.parametrize("freq_hz", [100, 4000])
def test_band_filter_attenuates_outside_the_ssb_passband(freq_hz):
    assert gain_db(freq_hz, ChannelConfig(band_filter=True)) < -30


def peak_frequency_hz(audio):
    spectrum = np.abs(np.fft.rfft(audio * np.hanning(audio.size)))
    return np.argmax(spectrum) * FS / audio.size


@pytest.mark.parametrize("offset_hz, expected_hz", [(50, 1050), (-30, 970)])
def test_frequency_offset_shifts_every_frequency_by_the_same_amount(offset_hz, expected_hz):
    out = apply_channel(tone(1000, seconds=10), ChannelConfig(freq_offset_hz=offset_hz), seed=1)
    assert peak_frequency_hz(out) == pytest.approx(expected_hz, abs=0.5)


@pytest.mark.parametrize("drift_ppm, expected_hz", [(2000, 1000 / 1.002), (-2000, 1000 / 0.998)])
def test_a_fast_receiver_clock_lowers_frequencies_and_a_slow_one_raises_them(
    drift_ppm, expected_hz
):
    audio = tone(1000, seconds=10)
    out = apply_channel(audio, ChannelConfig(clock_drift_ppm=drift_ppm), seed=1)
    assert out.size == audio.size
    assert peak_frequency_hz(out[: 5 * FS]) == pytest.approx(expected_hz, abs=0.5)


def test_clipping_flattens_peaks_above_the_level_and_leaves_the_rest_alone():
    out = apply_channel(tone(1000, amplitude=0.5), ChannelConfig(clip_level=0.3), seed=1)
    assert np.max(np.abs(out)) == pytest.approx(0.3)

    quiet = tone(1000, amplitude=0.2)
    np.testing.assert_array_equal(
        apply_channel(quiet, ChannelConfig(clip_level=0.3), seed=1), quiet
    )


def test_impulsive_noise_adds_short_loud_bursts_to_otherwise_silent_audio():
    config = ChannelConfig(impulse_rate_hz=5, impulse_duration_s=0.002, impulse_amplitude=0.5)
    out = apply_channel(np.zeros(10 * FS), config, seed=3)
    hit = out[out != 0]
    expected_samples = 5 * 10 * 0.002 * FS  # bursts per second x seconds x burst length
    assert 0.5 * expected_samples < hit.size < 1.5 * expected_samples
    assert np.std(hit) == pytest.approx(0.5, rel=0.1)


def envelope(audio):
    return np.abs(signal.hilbert(audio))


def test_fading_makes_the_level_vary_but_keeps_the_average_power():
    audio = tone(1000, seconds=30)
    faded = apply_channel(audio, ChannelConfig(fading_doppler_hz=2.0), seed=5)

    steady = envelope(audio)[FS:-FS]
    varying = envelope(faded)[FS:-FS]
    assert np.std(steady) / np.mean(steady) < 0.01
    assert np.std(varying) / np.mean(varying) > 0.3  # Rayleigh fading is about 0.52

    power_change_db = 10 * np.log10(np.mean(faded**2) / np.mean(audio**2))
    assert power_change_db == pytest.approx(0, abs=1)


EVERYTHING = ChannelConfig(
    snr_db=0,
    freq_offset_hz=20,
    clock_drift_ppm=100,
    clip_level=0.4,
    impulse_rate_hz=5,
    fading_doppler_hz=1.0,
    band_filter=True,
)


def test_the_same_seed_gives_the_same_output_and_another_seed_a_different_one():
    audio = tone(1000, seconds=5)
    first = apply_channel(audio, EVERYTHING, seed=11)
    np.testing.assert_array_equal(apply_channel(audio, EVERYTHING, seed=11), first)
    assert not np.array_equal(apply_channel(audio, EVERYTHING, seed=12), first)


def test_switching_one_impairment_on_does_not_change_the_random_numbers_of_another():
    audio = tone(1000, seconds=5)
    noise_only = ChannelConfig(snr_db=0)
    impulses_only = ChannelConfig(impulse_rate_hz=5)
    both = ChannelConfig(snr_db=0, impulse_rate_hz=5)

    noise = apply_channel(audio, noise_only, seed=2) - audio
    impulses = apply_channel(audio, impulses_only, seed=2) - audio
    np.testing.assert_allclose(apply_channel(audio, both, seed=2) - audio, noise + impulses)


@pytest.mark.parametrize(
    "bad",
    [
        {"sample_rate": 0},
        {"snr_db": float("nan")},
        {"snr_db": float("inf")},
        {"clip_level": 0},
        {"impulse_rate_hz": -1},
        {"impulse_duration_s": 0},
        {"impulse_amplitude": -1},
        {"fading_doppler_hz": 0},
        {"clock_drift_ppm": -1_000_000},
    ],
)
def test_an_invalid_configuration_is_rejected(bad):
    with pytest.raises(ValueError):
        ChannelConfig(**bad)


@pytest.mark.parametrize("freq_hz", [300, 2700])
def test_band_filter_edges_sit_about_6_db_down(freq_hz):
    assert gain_db(freq_hz, ChannelConfig(band_filter=True)) == pytest.approx(-6, abs=1)


def test_audio_that_is_not_a_single_channel_is_rejected():
    with pytest.raises(ValueError):
        apply_channel(np.zeros((2, 100)), ChannelConfig(), seed=1)


def test_noise_follows_the_given_signal_power_when_the_audio_is_padded_with_silence():
    burst = tone(1000, seconds=2.0, amplitude=0.5)
    padded = np.concatenate([np.zeros(10 * FS), burst, np.zeros(10 * FS)])
    noisy = apply_channel(
        padded, ChannelConfig(snr_db=0), seed=5, signal_power=float(np.mean(burst**2))
    )
    # At 0 dB in 2,500 Hz the noise power is the signal power times (fs/2) / 2,500.
    expected_std = np.sqrt(np.mean(burst**2) * (FS / 2) / 2500)
    assert np.std(noisy[: 10 * FS]) == pytest.approx(expected_std, rel=0.02)


def expected_noise_std(signal, snr_db):
    """Standard deviation of white noise at an SNR in 2,500 Hz, from the textbook scaling."""
    return float(np.sqrt(np.mean(signal**2) / 10 ** (snr_db / 10) * (FS / 2) / 2500))


def test_impulses_can_be_sized_against_the_noise_of_the_recording():
    audio = tone(1000, seconds=20)
    quiet = apply_channel(audio, ChannelConfig(snr_db=-5), seed=3)
    spiky = apply_channel(
        audio,
        ChannelConfig(snr_db=-5, impulse_rate_hz=5, impulse_over_noise_db=10),
        seed=3,
    )
    bursts = (spiky - quiet)[
        spiky != quiet
    ]  # the noise streams are the same, so only bursts remain
    assert bursts.size > 0
    assert np.std(bursts) == pytest.approx(expected_noise_std(audio, -5) * 10 ** (10 / 20), rel=0.1)


def test_clipping_can_be_set_against_the_level_of_the_received_audio():
    # In heavy noise the received audio is nearly Gaussian, so clipping at 2 standard deviations
    # flattens the share of samples beyond them: 4.55% for a normal distribution.
    audio = tone(1000, seconds=20)
    unclipped = apply_channel(audio, ChannelConfig(snr_db=-15), seed=4)
    clipped = apply_channel(audio, ChannelConfig(snr_db=-15, clip_rms_multiple=2.0), seed=4)
    limit = np.max(np.abs(clipped))
    assert limit == pytest.approx(2.0 * np.std(unclipped), rel=0.01)
    assert np.mean(np.abs(clipped) >= limit - 1e-9) == pytest.approx(0.0455, abs=0.004)


@pytest.mark.parametrize(
    "bad",
    [
        {"snr_db": 0, "clip_rms_multiple": 0},
        {"snr_db": 0, "clip_rms_multiple": 2.0, "clip_level": 0.5},  # two ways to say one thing
    ],
)
def test_clipping_has_one_definition_and_sensible_values(bad):
    with pytest.raises(ValueError):
        ChannelConfig(**bad)


def test_bursts_sized_against_the_noise_cannot_be_applied_without_a_noise():
    config = ChannelConfig(impulse_rate_hz=5, impulse_over_noise_db=10)  # fine to describe
    with pytest.raises(ValueError, match="snr_db"):
        apply_channel(tone(1000), config, seed=1)
