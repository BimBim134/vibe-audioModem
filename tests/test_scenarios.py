"""The named channels the codes are compared on."""

import numpy as np
import pytest

from bench.channel import ChannelConfig, apply_channel
from bench.scenarios import SCENARIOS

FS = 48_000


def test_the_scenarios_go_from_white_noise_to_a_dirty_hf_channel():
    assert set(SCENARIOS) == {"white", "ssb", "hf-fading", "dirty"}
    assert SCENARIOS["white"].config == ChannelConfig()
    ssb, fading, dirty = (SCENARIOS[n].config for n in ("ssb", "hf-fading", "dirty"))
    assert ssb.band_filter and ssb.fading_doppler_hz is None
    assert fading.band_filter and fading.fading_doppler_hz == 1.0
    assert dirty.fading_doppler_hz == 1.0 and dirty.band_filter
    assert dirty.impulse_rate_hz > 0 and dirty.clip_rms_multiple and dirty.clock_drift_ppm


def test_every_scenario_says_in_words_what_it_does():
    assert all(len(scenario.description) > 20 for scenario in SCENARIOS.values())


@pytest.mark.parametrize("name", ["white", "ssb", "hf-fading", "dirty"])
def test_every_scenario_can_be_applied_with_a_noise_level(name):
    audio = 0.5 * np.sin(2 * np.pi * 1500 * np.arange(5 * FS) / FS)
    config = ChannelConfig(**{**SCENARIOS[name].config.__dict__, "snr_db": -10.0})
    out = apply_channel(audio, config, seed=1)
    assert out.shape == audio.shape and np.isfinite(out).all()


def test_the_harsher_scenarios_really_change_the_audio():
    audio = 0.5 * np.sin(2 * np.pi * 1500 * np.arange(10 * FS) / FS)
    heard = {}
    for name in ("white", "hf-fading", "dirty"):
        config = ChannelConfig(**{**SCENARIOS[name].config.__dict__, "snr_db": 0.0})
        heard[name] = apply_channel(audio, config, seed=1)
    assert not np.allclose(heard["white"], heard["hf-fading"])
    assert not np.allclose(heard["hf-fading"], heard["dirty"])
