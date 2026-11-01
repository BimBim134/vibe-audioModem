"""The commands that write the HTML report."""

import json

import pytest

from bench import report
from bench.threshold import main as measure

QUICK = ["--snr-from", "-10", "--snr-to", "-6", "--snr-step", "2", "--trials", "20", "--seed", "3"]


def measure_to(tmp_path, modem, name, *extra):
    out = tmp_path / name
    measure(["--modem", modem, *QUICK, "--out", str(out), *extra])
    return out


def test_the_measurement_command_can_write_a_report_next_to_the_json(tmp_path):
    page = tmp_path / "report.html"
    measure_to(tmp_path, "tests.fake_modems:PerfectModem", "a.json", "--html", str(page))
    html = page.read_text(encoding="utf-8")
    assert "tests.fake_modems:PerfectModem" in html
    assert "Success threshold: -10 dB" in html


def test_asking_for_a_report_does_not_change_the_json(tmp_path):
    plain = measure_to(tmp_path, "bench.toy:ToyModem", "plain.json")
    with_report = measure_to(
        tmp_path, "bench.toy:ToyModem", "with.json", "--html", str(tmp_path / "r.html")
    )
    assert plain.read_bytes() == with_report.read_bytes()


def test_several_result_files_are_compared_in_one_report(tmp_path):
    first = measure_to(tmp_path, "tests.fake_modems:PerfectModem", "a.json")
    second = measure_to(tmp_path, "tests.fake_modems:DeafModem", "b.json")
    page = tmp_path / "compare.html"

    report.main([str(first), str(second), "--out", str(page)])

    html = page.read_text(encoding="utf-8")
    assert "tests.fake_modems:PerfectModem" in html
    assert "tests.fake_modems:DeafModem" in html
    assert "not reached" in html
    assert "Ranking" in html


def test_the_report_carries_a_generation_stamp(tmp_path):
    result = measure_to(tmp_path, "tests.fake_modems:PerfectModem", "a.json")
    page = tmp_path / "r.html"
    report.main([str(result), "--out", str(page)])
    assert "Generated 20" in page.read_text(encoding="utf-8")  # starts with the year


@pytest.mark.parametrize(
    "content, expected",
    [
        (None, "cannot read"),
        ("not json at all", "cannot read"),
        (json.dumps({"schema_version": 99}), "schema_version"),
        (json.dumps({"schema_version": 1}), "missing"),
    ],
)
def test_a_result_file_that_cannot_be_used_is_reported_clearly(tmp_path, capsys, content, expected):
    path = tmp_path / "bad.json"
    if content is not None:
        path.write_text(content)
    with pytest.raises(SystemExit) as stop:
        report.main([str(path), "--out", str(tmp_path / "r.html")])
    assert stop.value.code == 2
    assert expected in capsys.readouterr().err
    assert not (tmp_path / "r.html").exists()
