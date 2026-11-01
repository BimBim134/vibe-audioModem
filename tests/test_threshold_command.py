"""The command that measures a candidate's Success threshold and saves the result."""

import json

import pytest

from bench.threshold import main

QUICK = ["--snr-from", "-10", "--snr-to", "-6", "--snr-step", "2", "--trials", "20", "--seed", "3"]


def run(tmp_path, modem, *extra, name="result.json"):
    out = tmp_path / name
    main(["--modem", modem, *QUICK, "--out", str(out), *extra])
    return out


def test_the_result_file_describes_the_run_and_holds_the_curve_and_the_threshold(tmp_path):
    result = json.loads(run(tmp_path, "tests.fake_modems:WrongModem").read_text())

    assert result["schema_version"] == 1
    assert result["modem"] == "tests.fake_modems:WrongModem"
    assert result["preset"] == "standard"
    assert result["seed"] == 3
    assert result["trials"] == 20
    assert result["message_bytes"] == 2
    assert result["reference_bandwidth_hz"] == 2500
    assert result["required_success_rate"] == 0.95
    assert result["curve"] == [
        {"snr_db": snr, "trials": 20, "successes": 0, "false_receptions": 20, "success_rate": 0.0}
        for snr in (-10, -8, -6)
    ]
    assert result["threshold_db"] is None


def test_a_fixed_seed_gives_a_byte_identical_file(tmp_path):
    first = run(tmp_path, "bench.toy:ToyModem", name="a.json").read_bytes()
    second = run(tmp_path, "bench.toy:ToyModem", name="b.json").read_bytes()
    assert first == second


def test_a_modem_from_any_module_plugs_in_without_changing_the_bench(tmp_path):
    result = json.loads(run(tmp_path, "tests.fake_modems:PerfectModem").read_text())
    assert result["threshold_db"] == -10


def test_the_threshold_is_null_when_the_modem_never_reaches_95_percent(tmp_path):
    result = json.loads(run(tmp_path, "tests.fake_modems:DeafModem").read_text())
    assert result["threshold_db"] is None


def test_the_curve_and_the_threshold_are_printed(tmp_path, capsys):
    run(tmp_path, "tests.fake_modems:PerfectModem")
    lines = capsys.readouterr().out.splitlines()
    assert any(line.split() == ["-8.0", "20/20"] for line in lines)
    assert lines[-1] == "Success threshold: -10 dB"


def test_a_missed_threshold_is_said_so(tmp_path, capsys):
    run(tmp_path, "tests.fake_modems:DeafModem")
    assert "not reached" in capsys.readouterr().out.splitlines()[-1]


@pytest.mark.parametrize(
    "modem",
    [
        "tests.fake_modems:NoSuchModem",
        "no_such_module:Anything",
        "missing-colon",
        "tests.fake_modems:NeedsArguments",
    ],
)
def test_a_modem_that_cannot_be_loaded_is_reported_clearly(tmp_path, modem, capsys):
    with pytest.raises(SystemExit) as stop:
        run(tmp_path, modem)
    assert stop.value.code == 2
    assert "modem" in capsys.readouterr().err


@pytest.mark.parametrize(
    "bad",
    [
        ["--snr-step", "0"],
        ["--snr-from", "0", "--snr-to", "-5"],
        ["--trials", "0"],
        ["--message-bytes", "0"],
    ],
)
def test_arguments_that_cannot_make_a_measurement_are_rejected(tmp_path, bad, capsys):
    out = tmp_path / "x.json"
    with pytest.raises(SystemExit) as stop:
        main(["--modem", "bench.toy:ToyModem", *bad, "--out", str(out)])
    assert stop.value.code == 2
    assert not out.exists()
    assert capsys.readouterr().err


def test_the_result_file_records_where_and_when_the_transmission_was_hidden(tmp_path):
    out = tmp_path / "hidden.json"
    main(
        [
            "--modem", "tests.fake_modems:PerfectModem", *QUICK, "--out", str(out),
            "--max-lead-in-s", "4", "--tail-s", "1", "--freq-offset-from", "-300",
            "--freq-offset-to", "500",
        ]
    )  # fmt: skip
    result = json.loads(out.read_text())
    assert result["max_lead_in_s"] == 4
    assert result["tail_s"] == 1
    assert result["freq_offset_range_hz"] == [-300, 500]


@pytest.mark.parametrize(
    "bad",
    [
        ["--max-lead-in-s", "-1"],
        ["--tail-s", "-1"],
        ["--freq-offset-from", "5", "--freq-offset-to", "1"],
    ],
)
def test_a_recording_that_cannot_exist_is_rejected(tmp_path, bad, capsys):
    out = tmp_path / "x.json"
    with pytest.raises(SystemExit) as stop:
        main(["--modem", "bench.toy:ToyModem", *bad, "--out", str(out)])
    assert stop.value.code == 2
    assert not out.exists()
