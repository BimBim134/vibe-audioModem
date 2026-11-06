"""How fast a candidate receives, against real time."""

import json

import pytest

from bench.speed import main, measure_speed
from tests.fake_modems import PerfectModem
from vibemodem.core.ldpc_modem import LdpcModem

FS = 48_000


def test_the_recording_length_and_the_real_time_factor_follow_from_the_timings():
    result = measure_speed(PerfectModem(), repeats=3)
    # 5 s of silence in front, 6 s after, and the 480 samples a PerfectModem sends.
    assert result.recording_seconds == pytest.approx(11 + 480 / FS)
    assert result.repeats == 3
    assert result.receive_seconds > 0
    assert result.real_time_factor == pytest.approx(
        result.recording_seconds / result.receive_seconds
    )


def test_a_modem_without_a_code_has_no_code_timings():
    assert measure_speed(PerfectModem(), repeats=2).code_decode_seconds == {}


def test_a_modem_with_a_code_gets_the_timing_of_its_code_on_easy_and_hopeless_input():
    result = measure_speed(LdpcModem(), repeats=2)
    assert set(result.code_decode_seconds) == {"clean", "failing"}
    assert all(seconds > 0 for seconds in result.code_decode_seconds.values())
    assert result.recording_seconds > 20  # a whole Transmission, hidden in silence


def test_the_command_prints_the_speed_and_saves_it_with_the_machine_it_ran_on(tmp_path, capsys):
    out = tmp_path / "speed.json"
    main(["--modem", "tests.fake_modems:PerfectModem", "--repeats", "2", "--out", str(out)])

    assert "times real time" in capsys.readouterr().out
    saved = json.loads(out.read_text())
    assert saved["modem"] == "tests.fake_modems:PerfectModem"
    assert saved["repeats"] == 2
    assert {"platform", "processor", "cpu_count", "numpy"} <= set(saved["machine"])
    assert saved["real_time_factor"] > 0


@pytest.mark.parametrize("bad", [["--repeats", "0"], ["--modem", "no_such_module:X"]])
def test_arguments_that_cannot_be_timed_are_refused(tmp_path, bad, capsys):
    arguments = ["--modem", "tests.fake_modems:PerfectModem", "--out", str(tmp_path / "x.json")]
    with pytest.raises(SystemExit) as stop:
        main([*arguments, *bad])
    assert stop.value.code == 2
    assert not (tmp_path / "x.json").exists()
