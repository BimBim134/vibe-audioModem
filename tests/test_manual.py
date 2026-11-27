"""The manual: Markdown in two languages with the same structure, shown by the application."""

import re

import pytest
from fastapi.testclient import TestClient

from vibemodem.app import manual
from vibemodem.app.api import create_app
from vibemodem.app.service import ModemService
from vibemodem.io.audio import FakeAudio


def source(lang):
    return (manual.MANUAL_DIR / f"{lang}.md").read_text(encoding="utf-8")


def anchors(lang):
    return re.findall(r"\{ #([a-z-]+) \}", source(lang))


def test_both_languages_have_the_same_sections_in_the_same_order():
    assert anchors("en") == anchors("fr")
    assert len(anchors("en")) >= 15


def test_every_link_inside_the_manual_goes_to_a_section_that_exists():
    for lang in manual.LANGUAGES:
        known = set(anchors(lang))
        links = set(re.findall(r"\]\(#([a-z-]+)\)", source(lang)))
        assert links <= known, (lang, links - known)


def test_the_settings_of_the_page_are_all_described():
    # The page has no explanatory text any more: the manual is where each setting is explained.
    for lang, words in (
        ("en", ["Callsign", "Preset", "Repetitions", "Listening band", "Lead-in", "Margin",
                "Push to talk", "Stored receptions", "Clear the history", "Export CSV"]),
        ("fr", ["Callsign", "Preset", "Repetitions", "Listening band", "Lead-in", "Margin",
                "Push to talk", "Stored receptions", "Clear the history", "Export CSV"]),
    ):  # fmt: skip
        for word in [*words, "Download the log"]:
            assert word in source(lang), (lang, word)


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_the_manual_is_rendered_as_a_page_with_tables_and_anchors(lang):
    page = manual.render(lang)
    assert f'<html lang="{lang}">' in page
    assert "<table>" in page and "<pre>" in page
    assert 'id="ptt"' in page and 'href="#ptt"' in page


def test_an_unknown_language_gives_the_default_one():
    assert manual.render("xx") == manual.render(manual.DEFAULT_LANGUAGE)
    assert manual.render(None) == manual.render("en")


def test_the_application_serves_the_manual_offline():
    service = ModemService(FakeAudio())
    try:
        client = TestClient(create_app(service), base_url="http://127.0.0.1")
        english = client.get("/manual")
        assert english.status_code == 200 and "Manual" in english.text
        french = client.get("/manual?lang=fr")
        assert "Manuel" in french.text and 'href="/manual?lang=en"' in french.text
        assert client.get("/assets/manual.css").status_code == 200
        assert "http://" not in re.sub(
            r"http://127\.0\.0\.1", "", english.text.split("<article>")[0]
        )
    finally:
        service.close()


def test_the_page_has_a_manual_button_and_f1():
    page = (manual.MANUAL_DIR.parent / "assets" / "index.html").read_text(encoding="utf-8")
    script = (manual.MANUAL_DIR.parent / "assets" / "script.js").read_text(encoding="utf-8")
    assert 'id="open-manual"' in page and '"F1"' in script
