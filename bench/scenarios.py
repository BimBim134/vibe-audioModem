"""Named channels for comparing modems and codes on something closer to a radio link.

Each scenario is a ChannelConfig without its SNR (the bench sweeps that). Parasite bursts and
clipping are sized against the noise the receiver hears, as an automatic gain control would, so
they mean the same at every SNR of a sweep.
"""

from dataclasses import dataclass

from bench.channel import ChannelConfig


@dataclass(frozen=True)
class Scenario:
    description: str
    config: ChannelConfig


SCENARIOS = {
    "white": Scenario(
        "White noise only: the reference every measurement started from.",
        ChannelConfig(),
    ),
    "ssb": Scenario(
        "White noise through the 300-2,700 Hz audio passband of an SSB radio.",
        ChannelConfig(band_filter=True),
    ),
    "hf-fading": Scenario(
        "The SSB passband plus slow flat Rayleigh fading with 1 Hz of Doppler spread, a "
        "typical rate for HF: deep fades lasting a fraction of a second to a few seconds.",
        ChannelConfig(band_filter=True, fading_doppler_hz=1.0),
    ),
    "dirty": Scenario(
        "Fading as above, plus 1 ms static crashes five times a second at 20 dB over the "
        "noise, clipping at 3 times the received RMS, and a 50 ppm sound-card clock error.",
        ChannelConfig(
            band_filter=True,
            fading_doppler_hz=1.0,
            impulse_rate_hz=5.0,
            impulse_duration_s=0.001,
            impulse_over_noise_db=20.0,
            clip_rms_multiple=3.0,
            clock_drift_ppm=50.0,
        ),
    ),
}
