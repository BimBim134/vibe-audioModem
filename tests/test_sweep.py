"""The sweep of M-FSK settings: Success threshold against occupied bandwidth."""

import json
import math

import pytest

from bench.sweep import main

MODEM = "tests.fake_modems:ComboModem"
QUICK = [
    "--modem", MODEM,
    "--tones", "2,4",
    "--symbol-ms", "40,80",
    "--snr-from", "-10", "--snr-to", "-6", "--snr-step", "2",
    "--trials", "5", "--seed", "3",
]  # fmt: skip


def run(tmp_path, *extra, name="sweep.json"):
    out = tmp_path / name
    main([*QUICK, "--out", str(out), *extra])
    return json.loads(out.read_text())


def test_every_combination_of_tones_and_symbol_duration_is_measured(tmp_path):
    result = run(tmp_path)
    assert [(c["tones"], c["symbol_ms"]) for c in result["configurations"]] == [
        (2, 40.0),
        (2, 80.0),
        (4, 40.0),
        (4, 80.0),
    ]


def test_each_configuration_has_its_bandwidth_airtime_curve_and_thresholds(tmp_path):
    first, *_, last = run(tmp_path)["configurations"]
    assert first["bandwidth_hz"] < last["bandwidth_hz"]  # 2 tones against 4 tones
    assert first["transmission_seconds"] == pytest.approx(2.0)
    assert [p["snr_db"] for p in first["curve"]] == [-10.0, -8.0, -6.0]
    assert all(p["trials"] == 5 and p["successes"] == 5 for p in first["curve"])
    assert first["thresholds_db"] == {"0.8": -10.0, "0.9": -10.0, "0.95": -10.0}
    # The SNR of the threshold plus the duration in dB: the energy sent, to compare waveforms
    # whose Transmissions differ in length (2 s here).
    assert first["energy_db"]["0.95"] == pytest.approx(-10.0 + 10 * math.log10(2.0))


def test_the_result_records_the_measurement_that_was_run(tmp_path):
    result = run(tmp_path, "--scenario", "ssb")
    assert result["schema_version"] == 1
    assert result["modem"] == MODEM
    assert result["scenario"] == "ssb"
    assert result["seed"] == 3 and result["trials"] == 5
    assert result["drop_db"] == 20.0


def test_fixed_settings_are_given_to_every_configuration(tmp_path):
    result = run(tmp_path, "--set", "interleave=true")
    assert result["modem_options"] == {"interleave": True}
    assert all(c["modem_parameters"]["interleave"] is True for c in result["configurations"])


def test_the_same_seed_gives_the_same_file_whatever_the_number_of_processes(tmp_path):
    alone = run(tmp_path, "--jobs", "1", name="one.json")
    together = run(tmp_path, "--jobs", "2", name="two.json")
    assert alone == together
    assert (tmp_path / "one.json").read_text() == (tmp_path / "two.json").read_text()


def test_the_table_is_printed(tmp_path, capsys):
    run(tmp_path)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == [
        "tones",
        "symbol_ms",
        "bandwidth_hz",
        "transmission_s",
        "95%",
        "90%",
        "80%",
    ]
    assert len(lines) == 5


@pytest.mark.parametrize(
    "bad", [["--tones", "x"], ["--jobs", "0"], ["--trials", "0"], ["--snr-step", "0"]]
)
def test_arguments_that_cannot_make_a_measurement_are_rejected(tmp_path, bad, capsys):
    out = tmp_path / "x.json"
    with pytest.raises(SystemExit) as stop:
        main([*QUICK, *bad, "--out", str(out)])
    assert stop.value.code == 2 and not out.exists() and capsys.readouterr().err


@pytest.mark.parametrize(
    "bad, word", [(["--tones", "3"], "tones"), (["--symbol-ms", "0.5"], "symbol")]
)
def test_a_waveform_the_modem_cannot_use_is_refused_before_any_work_is_done(
    tmp_path, bad, word, capsys
):
    out = tmp_path / "x.json"
    with pytest.raises(SystemExit) as stop:
        main(["--modem", "vibemodem.core.baseline:BaselineModem", *bad, "--out", str(out)])
    assert stop.value.code == 2 and not out.exists()
    assert word in capsys.readouterr().err


def test_any_setting_can_be_swept_with_a_grid(tmp_path):
    out = tmp_path / "grid.json"
    main(
        [
            "--modem", MODEM, "--grid", "tones=2,4", "--grid", "symbol_ms=40",
            "--snr-from", "-10", "--snr-to", "-6", "--snr-step", "2",
            "--trials", "3", "--out", str(out),
        ]
    )  # fmt: skip
    configurations = json.loads(out.read_text())["configurations"]
    assert [(c["tones"], c["symbol_ms"]) for c in configurations] == [(2, 40), (4, 40)]


def test_a_grid_prints_its_own_columns(tmp_path, capsys):
    main(
        [
            "--modem", MODEM, "--grid", "interleave=false,true",
            "--snr-from", "-10", "--snr-to", "-10", "--trials", "2",
            "--out", str(tmp_path / "g.json"),
        ]
    )  # fmt: skip
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split()[0] == "interleave"
    assert [line.split()[0] for line in lines[1:]] == ["False", "True"]


@pytest.mark.parametrize("bad", ["tones", "=2", "tones=", "tones=oops"])
def test_a_grid_that_is_not_a_name_and_values_is_rejected(tmp_path, bad, capsys):
    with pytest.raises(SystemExit) as stop:
        main([*QUICK, "--grid", bad, "--out", str(tmp_path / "x.json")])
    assert stop.value.code == 2 and capsys.readouterr().err
