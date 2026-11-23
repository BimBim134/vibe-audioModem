"""The manual, written in Markdown (`manual/en.md`, `manual/fr.md`, same structure and same
anchors) and shown by the application as a page, offline."""

import html
from pathlib import Path

import markdown

MANUAL_DIR = Path(__file__).with_name("manual")
LANGUAGES = {"en": "English", "fr": "Français"}
DEFAULT_LANGUAGE = "en"
TITLES = {"en": "Vibe AudioModem — Manual", "fr": "Vibe AudioModem — Manuel"}
BACK = {"en": "Back to the application", "fr": "Retour à l'application"}


def language_of(wanted: str | None) -> str:
    """A language we have a manual in: the one asked for, or the default."""
    return wanted if wanted in LANGUAGES else DEFAULT_LANGUAGE


def render(wanted: str | None = None) -> str:
    """The whole manual as an HTML page, in the language asked for."""
    lang = language_of(wanted)
    source = (MANUAL_DIR / f"{lang}.md").read_text(encoding="utf-8")
    body = markdown.markdown(source, extensions=["tables", "fenced_code", "attr_list"])
    switch = " · ".join(
        html.escape(name)
        if code == lang
        else f'<a href="/manual?lang={code}" hreflang="{code}">{html.escape(name)}</a>'
        for code, name in LANGUAGES.items()
    )
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(TITLES[lang])}</title>
<link rel="stylesheet" href="/assets/style.css">
<link rel="stylesheet" href="/assets/manual.css">
</head>
<body class="manual">
<nav class="manual-bar"><a href="/">{html.escape(BACK[lang])}</a><span>{switch}</span></nav>
<article>
{body}
</article>
</body>
</html>
"""
