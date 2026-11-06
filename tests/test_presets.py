"""The three Presets: the PHY profile each one names, and the modems that follow them."""

import json

import numpy as np
import pytest

from bench.bandwidth import SAMPLE_RATE, occupied_band
from bench.bandwidth import main as bandwidth
from bench.channel import ChannelConfig, apply_channel
from bench.threshold import load_modem
from vibemodem.core.baseline import BaselineModem
from vibemodem.core.presets import DEFAULT_PRESET, PRESETS, profile
from vibemodem.core.turbo_modem import TurboModem

NAMES = ["max-range", "standard", "fast"]


def test_there_are_three_presets_and_standard_is_the_default():
    assert list(PRESETS) == NAMES
    assert DEFAULT_PRESET == "standard"


def test_each_preset_is_fully_specified_by_its_profile():
    assert [(p.tones, p.symbol_ms, p.interleave) for p in PRESETS.values()] == [
        (8, 320.0, True),
        (8, 80.0, True),
        (8, 40.0, True),
    ]


def test_an_unknown_preset_is_refused_and_the_known_ones_are_listed():
    with pytest.raises(ValueError, match="max-range, standard, fast"):
        profile("turbo-boost")


@pytest.mark.parametrize("modem_class", [BaselineModem, TurboModem])
@pytest.mark.parametrize("name", NAMES)
def test_a_modem_follows_the_preset_it_is_built_for(modem_class, name):
    modem = modem_class(preset=name)
    chosen = PRESETS[name]
    assert modem.parameters == {
        "preset": name,
        "tones": chosen.tones,
        "symbol_ms": chosen.symbol_ms,
        "interleave": chosen.interleave,
        "repetitions": 1,
    }
    channel = ChannelConfig(snr_db=-3.0)
    transmission = modem.modulate(b"any preset", name)
    recording = np.concatenate([np.zeros(SAMPLE_RATE), transmission, np.zeros(SAMPLE_RATE)])
    noisy = apply_channel(recording, channel, seed=2, signal_power=float(np.mean(transmission**2)))
    assert [r.message for r in modem.demodulate(noisy)] == [b"any preset"]


def test_a_modem_without_a_preset_is_the_standard_one():
    assert TurboModem().parameters["preset"] == "standard"
    assert TurboModem().parameters["symbol_ms"] == 80.0


def test_the_preset_you_ask_for_must_be_the_one_the_modem_listens_for():
    with pytest.raises(ValueError, match="'standard'.*'fast'"):
        TurboModem().modulate(b"x", "fast")
    with pytest.raises(ValueError, match="unknown Preset"):
        TurboModem().modulate(b"x", "turbo-boost")


def test_a_setting_given_by_hand_overrides_the_profile():
    modem = TurboModem(preset="fast", symbol_ms=160, interleave=False)
    assert modem.parameters["tones"] == 8 and modem.parameters["symbol_ms"] == 160.0
    assert modem.parameters["interleave"] is False and modem.parameters["preset"] == "fast"


def test_a_modem_refuses_a_preset_it_does_not_know():
    with pytest.raises(ValueError, match="unknown Preset"):
        TurboModem(preset="turbo-boost")


def test_the_presets_trade_airtime_against_band():
    seconds, bands = [], []
    for name in NAMES:
        transmission = TurboModem(preset=name).modulate(b"measure", name)
        seconds.append(transmission.size / SAMPLE_RATE)
        low, high = occupied_band(transmission, SAMPLE_RATE, drop_db=20.0)
        bands.append(high - low)
    assert seconds[0] > seconds[1] > seconds[2]  # max range is the slowest
    assert bands[0] < bands[1] < bands[2]  # and the narrowest
    assert bands[0] < 40 and bands[2] < 250


def test_the_bench_builds_the_modem_for_the_preset_it_measures(tmp_path):
    assert load_modem("vibemodem.core.turbo_modem:TurboModem", preset="fast").preset == "fast"
    assert load_modem("tests.fake_modems:PerfectModem", preset="fast")  # takes no Preset itself

    out = tmp_path / "band.json"
    bandwidth(["--modem", "vibemodem.core.turbo_modem:TurboModem", "--preset", "max-range",
               "--out", str(out)])  # fmt: skip
    result = json.loads(out.read_text())
    assert result["preset"] == "max-range" and result["bandwidth_hz"] < 40
