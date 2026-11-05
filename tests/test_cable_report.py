"""The report of the real-world trials is built from the stored results."""

from bench.cable_report import build, threshold


def test_the_threshold_is_the_lowest_level_from_which_all_louder_levels_reach_95_percent():
    levels = [[-20.0, 0, 10], [-19.0, 4, 10], [-18.0, 10, 10], [-17.0, 10, 10]]
    assert threshold(levels) == -18.0 and threshold([[-5.0, 3, 10]]) is None


def test_the_page_has_a_chart_and_a_table_for_each_preset():
    page = build()
    assert page.count("<svg") == 3 and page.count("<table>") == 4
    for preset in ("Fast", "Standard", "Max-range"):
        assert f"<h2>{preset}</h2>" in page
