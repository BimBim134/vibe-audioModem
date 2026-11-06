"""The count of false alarms of the receiver in noise."""

import json

import pytest

from bench.false_alarms import count_false_alarms, main


def test_noise_alone_reports_no_message_ever():
    result = count_false_alarms("fast", hours=0.07, seed=1, ssb=False)  # 2 recordings
    assert result["reported_messages"] == 0 and result["hours"] == pytest.approx(240 / 3600)


def test_the_result_is_written_for_the_measurements(tmp_path, capsys):
    out = tmp_path / "alarms.json"
    main(["--preset", "fast", "--hours", "0.03", "--ssb", "--out", str(out)])
    result = json.loads(out.read_text())
    assert result["noise"] == "ssb" and result["preset"] == "fast"
    assert "Signals per hour" in capsys.readouterr().out


def test_a_duration_that_makes_no_sense_is_rejected(capsys):
    with pytest.raises(SystemExit):
        main(["--hours", "0"])
