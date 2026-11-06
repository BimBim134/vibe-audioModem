"""The command that measures how much bandwidth a modem's output occupies."""

import json

import numpy as np
import pytest

from bench.bandwidth import main, occupied_band

FS = 48_000


def tones(*frequencies_and_levels_db, seconds=4.0):
    time = np.arange(round(seconds * FS)) / FS
    return sum(
        10 ** (level / 20) * np.sin(2 * np.pi * frequency * time)
        for frequency, level in frequencies_and_levels_db
    )


def test_a_single_tone_occupies_next_to_no_bandwidth():
    low, high = occupied_band(tones((1000, 0)), FS, drop_db=20)
    assert low == pytest.approx(1000, abs=2) and high == pytest.approx(1000, abs=2)


def test_the_band_runs_from_the_lowest_to_the_highest_frequency_even_across_a_gap():
    low, high = occupied_band(tones((1000, 0), (1300, 0)), FS, drop_db=20)
    assert low == pytest.approx(1000, abs=2) and high == pytest.approx(1300, abs=2)


def test_a_component_less_than_the_drop_below_the_maximum_counts_and_a_fainter_one_does_not():
    two = tones((1000, 0), (1200, -15))
    assert occupied_band(two, FS, drop_db=20)[1] == pytest.approx(1200, abs=2)
    faint = tones((1000, 0), (1200, -25))
    assert occupied_band(faint, FS, drop_db=20)[1] == pytest.approx(1000, abs=2)


def test_a_larger_drop_reaches_further_into_the_skirts():
    spread = tones((1000, 0), (1100, -15), (1200, -35))
    wide = occupied_band(spread, FS, drop_db=40)
    narrow = occupied_band(spread, FS, drop_db=20)
    assert wide[1] - wide[0] > narrow[1] - narrow[0] + 50


def test_audio_that_is_too_short_or_silent_is_refused():
    with pytest.raises(ValueError, match="short"):
        occupied_band(np.zeros(100), FS, drop_db=20)
    with pytest.raises(ValueError, match="silent"):
        occupied_band(np.zeros(FS * 4), FS, drop_db=20)


def test_the_command_measures_a_modem_and_writes_the_result(tmp_path, capsys):
    out = tmp_path / "bandwidth.json"
    main(["--modem", "vibemodem.core.baseline:BaselineModem", "--messages", "2", "--out", str(out)])
    result = json.loads(out.read_text())
    assert result["modem"] == "vibemodem.core.baseline:BaselineModem"
    assert result["drop_db"] == 20.0
    assert result["messages"] == 2 and result["seed"] == 1
    assert 100 < result["bandwidth_hz"] < 130  # 8 tones x 12.5 Hz plus the skirts
    assert result["bandwidth_hz"] == pytest.approx(result["high_hz"] - result["low_hz"])
    assert result["transmission_seconds"] == pytest.approx(13.6, abs=0.1)
    assert f"{result['bandwidth_hz']:.1f}" in capsys.readouterr().out


def test_the_same_seed_gives_the_same_file_and_settings_are_recorded(tmp_path):
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    arguments = ["--modem", "vibemodem.core.baseline:BaselineModem", "--messages", "2"]
    main([*arguments, "--set", "tones=4", "--set", "symbol_ms=160", "--out", str(first)])
    main([*arguments, "--set", "tones=4", "--set", "symbol_ms=160", "--out", str(second)])
    assert first.read_text() == second.read_text()
    result = json.loads(first.read_text())
    assert result["modem_options"] == {"tones": 4, "symbol_ms": 160}
    assert result["modem_parameters"]["tones"] == 4
    assert result["bandwidth_hz"] < 60  # 4 tones x 6.25 Hz


@pytest.mark.parametrize("bad", [["--messages", "0"], ["--drop-db", "0"], ["--drop-db", "-3"]])
def test_arguments_that_cannot_make_a_measurement_are_rejected(tmp_path, bad, capsys):
    out = tmp_path / "x.json"
    with pytest.raises(SystemExit) as stop:
        main(["--modem", "bench.toy:ToyModem", *bad, "--out", str(out)])
    assert stop.value.code == 2 and not out.exists() and capsys.readouterr().err


def test_a_modem_that_cannot_be_loaded_is_reported(tmp_path, capsys):
    with pytest.raises(SystemExit) as stop:
        main(["--modem", "no_such_module:Anything", "--out", str(tmp_path / "x.json")])
    assert stop.value.code == 2 and "modem" in capsys.readouterr().err
