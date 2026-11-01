"""The human-readable HTML report of bench results."""

import pytest

from bench.report import render_report, wilson_interval


@pytest.mark.parametrize(
    "successes, trials, low, high",
    [(0, 10, 0.0, 0.2775), (10, 10, 0.7225, 1.0), (50, 100, 0.4038, 0.5962)],
)
def test_a_measured_rate_comes_with_a_95_percent_confidence_interval(successes, trials, low, high):
    measured_low, measured_high = wilson_interval(successes, trials)
    assert measured_low == pytest.approx(low, abs=0.0005)
    assert measured_high == pytest.approx(high, abs=0.0005)


def result(
    modem="bench.toy:ToyModem",
    points=((-10, 252), (-8, 293), (-6, 300)),
    trials=300,
    message_bytes=2,
    threshold=-8,
    false_receptions=0,
):
    return {
        "schema_version": 1,
        "modem": modem,
        "preset": "standard",
        "seed": 1,
        "trials": trials,
        "message_bytes": message_bytes,
        "reference_bandwidth_hz": 2500,
        "required_success_rate": 0.95,
        "channel": {"sample_rate": 48000, "band_filter": False},
        "curve": [
            {
                "snr_db": snr,
                "trials": trials,
                "successes": ok,
                "false_receptions": false_receptions,
                "success_rate": ok / trials,
            }
            for snr, ok in points
        ],
        "threshold_db": threshold,
    }


def test_a_single_report_shows_the_threshold_the_curve_and_the_counts():
    html = render_report([result()])
    assert "Success threshold" in html
    assert "-8 dB" in html
    assert "293/300" in html
    assert html.count("<svg") == 1
    assert "95%" in html


def test_a_threshold_that_was_not_reached_is_said_so():
    html = render_report([result(points=((-10, 10), (-6, 100)), threshold=None)])
    assert "not reached" in html


def test_what_comes_from_a_result_file_cannot_inject_markup():
    html = render_report([result(modem="<script>alert(1)</script>")])
    assert "<script" not in html
    assert "&lt;script&gt;" in html


def test_the_report_is_self_contained():
    html = render_report([result(), result(modem="other:Modem", threshold=-12)])
    assert "http" not in html  # no links, no external files, no namespace declarations
    assert "<script" not in html


def test_several_results_are_ranked_with_the_lowest_threshold_first():
    html = render_report(
        [
            result(modem="mid:Modem", threshold=-8),
            result(modem="never:Modem", threshold=None),
            result(modem="best:Modem", threshold=-12),
        ]
    )
    positions = [html.index(name) for name in ("best:Modem", "mid:Modem", "never:Modem")]
    assert positions == sorted(positions)


def test_results_measured_on_different_terms_are_flagged_as_not_comparable():
    different = render_report([result(message_bytes=2), result(modem="x:Y", message_bytes=8)])
    assert "not directly comparable" in different
    assert "message length" in different
    same = render_report([result(), result(modem="x:Y")])
    assert "not directly comparable" not in same


def test_the_report_says_when_and_from_which_commit_it_was_made():
    html = render_report([result()], generated="2026-11-01 17:00, commit abc1234")
    assert "2026-11-01 17:00, commit abc1234" in html
