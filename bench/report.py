"""A human-readable HTML report of bench results.

One self-contained page: no script, no external file, no link. It opens in any browser,
offline, and can be kept as a CI artifact.
"""

import argparse
import html
import json
import math
import subprocess
from datetime import datetime
from pathlib import Path

WILSON_Z = 1.96  # 95% confidence
SUPPORTED_SCHEMA_VERSIONS = {1}

# Okabe-Ito colours, told apart by marker shape too (colour-blind safe).
SERIES_COLOURS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]
MARKERS = ["circle", "square", "triangle"]

CHART_WIDTH, CHART_HEIGHT = 760, 380
MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM = 62, 20, 16, 52

STYLE = """
:root { --bg:#ffffff; --fg:#1b1f23; --muted:#5a6570; --grid:#d5dbe1; --panel:#f4f6f8; --warn:#8a5a00; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14181c; --fg:#e6e9ec; --muted:#9aa5b1; --grid:#2f3740; --panel:#1d232a; --warn:#e6b450; }
}
body { background:var(--bg); color:var(--fg); font:16px/1.5 system-ui, sans-serif;
       max-width:56rem; margin:0 auto; padding:1.5rem 1rem 4rem; }
h1 { font-size:1.5rem; margin-bottom:0.25rem; }
h2 { font-size:1.2rem; margin-top:2.5rem; }
.meta, .note { color:var(--muted); font-size:0.9rem; }
.verdict { font-size:1.6rem; font-weight:600; margin:0.25rem 0; }
.warn { color:var(--warn); }
table { border-collapse:collapse; width:100%; margin:0.75rem 0; font-variant-numeric:tabular-nums; }
th, td { text-align:right; padding:0.3rem 0.6rem; border-bottom:1px solid var(--grid); }
th:first-child, td:first-child, td.name, th.name { text-align:left; }
tr.threshold td { font-weight:600; background:var(--panel); }
div.scroll { overflow-x:auto; }
svg { width:100%; height:auto; display:block; }
svg text { fill:var(--fg); font-size:12px; }
svg .grid { stroke:var(--grid); stroke-width:1; }
svg .target { stroke:var(--muted); stroke-width:1.5; stroke-dasharray:6 4; }
svg .frame { fill:none; stroke:var(--grid); }
.swatch { display:inline-block; width:0.8rem; height:0.8rem; border-radius:2px; margin-right:0.4rem; }
.legend { list-style:none; padding:0; display:flex; flex-wrap:wrap; gap:0.25rem 1.25rem; }
"""


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """95% confidence interval of a success rate (Wilson score), sound even at 0% and 100%."""
    rate = successes / trials
    z2 = WILSON_Z**2
    centre = (rate + z2 / (2 * trials)) / (1 + z2 / trials)
    half = WILSON_Z * math.sqrt(rate * (1 - rate) / trials + z2 / (4 * trials**2))
    half /= 1 + z2 / trials
    return max(0.0, centre - half), min(1.0, centre + half)


def _e(value) -> str:
    return html.escape(str(value))


def _db(value: float) -> str:
    return f"{value:g} dB"


def _percent(rate: float) -> str:
    return f"{100 * rate:.1f}%"


def _threshold_text(result: dict) -> str:
    snrs = [p["snr_db"] for p in result["curve"]]
    if result["threshold_db"] is None:
        return f"not reached between {_db(min(snrs))} and {_db(max(snrs))}"
    return _db(result["threshold_db"])


# ---- chart -----------------------------------------------------------------------------------


def _tick_step(span: float) -> float:
    for step in (1, 2, 5, 10, 20, 50):
        if span / step <= 10:
            return step
    return 100


def _marker(kind: str, x: float, y: float, colour: str) -> str:
    if kind == "square":
        return f'<rect x="{x - 4:.1f}" y="{y - 4:.1f}" width="8" height="8" fill="{colour}"/>'
    if kind == "triangle":
        pts = f"{x:.1f},{y - 5:.1f} {x - 5:.1f},{y + 4:.1f} {x + 5:.1f},{y + 4:.1f}"
        return f'<polygon points="{pts}" fill="{colour}"/>'
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{colour}"/>'


def _chart(results: list[dict]) -> str:
    snrs = [p["snr_db"] for r in results for p in r["curve"]]
    low, high = min(snrs), max(snrs)
    if low == high:
        low, high = low - 1, high + 1
    plot_w = CHART_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    plot_h = CHART_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM

    def x_of(snr: float) -> float:
        return MARGIN_LEFT + (snr - low) / (high - low) * plot_w

    def y_of(rate: float) -> float:
        return MARGIN_TOP + (1 - rate) * plot_h

    parts = [
        f'<svg viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" role="img" aria-labelledby="chart-title">',
        '<title id="chart-title">Share of Messages received correctly against SNR</title>',
    ]
    for rate in (0, 0.25, 0.5, 0.75, 1):
        y = y_of(rate)
        parts.append(
            f'<line class="grid" x1="{MARGIN_LEFT}" x2="{CHART_WIDTH - MARGIN_RIGHT}" y1="{y:.1f}" y2="{y:.1f}"/>'
            f'<text x="{MARGIN_LEFT - 8}" y="{y + 4:.1f}" text-anchor="end">{round(rate * 100)}%</text>'
        )
    step = _tick_step(high - low)
    tick = math.ceil(low / step) * step
    while tick <= high + 1e-9:
        x = x_of(tick)
        parts.append(
            f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{MARGIN_TOP}" y2="{MARGIN_TOP + plot_h}"/>'
            f'<text x="{x:.1f}" y="{MARGIN_TOP + plot_h + 18}" text-anchor="middle">{tick:g}</text>'
        )
        tick += step
    target = y_of(0.95)
    parts.append(
        f'<line class="target" x1="{MARGIN_LEFT}" x2="{CHART_WIDTH - MARGIN_RIGHT}" y1="{target:.1f}" y2="{target:.1f}"/>'
        f'<text x="{MARGIN_LEFT + 6}" y="{target - 5:.1f}">95% target</text>'
    )
    parts.append(
        f'<rect class="frame" x="{MARGIN_LEFT}" y="{MARGIN_TOP}" width="{plot_w}" height="{plot_h}"/>'
        f'<text x="{MARGIN_LEFT + plot_w / 2:.1f}" y="{CHART_HEIGHT - 8}" text-anchor="middle">'
        "SNR in a 2,500 Hz noise bandwidth (dB)</text>"
        f'<text transform="translate(14 {MARGIN_TOP + plot_h / 2:.1f}) rotate(-90)" text-anchor="middle">'
        "Messages received correctly</text>"
    )
    for index, result in enumerate(results):
        colour = SERIES_COLOURS[index % len(SERIES_COLOURS)]
        marker = MARKERS[index % len(MARKERS)]
        points = sorted(result["curve"], key=lambda p: p["snr_db"])
        if result["threshold_db"] is not None:
            x = x_of(result["threshold_db"])
            parts.append(
                f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{MARGIN_TOP}" y2="{MARGIN_TOP + plot_h}" '
                f'stroke="{colour}" stroke-width="1.5" stroke-dasharray="2 4"/>'
            )
        line = " ".join(
            f"{x_of(p['snr_db']):.1f},{y_of(p['successes'] / p['trials']):.1f}" for p in points
        )
        parts.append(f'<polyline points="{line}" fill="none" stroke="{colour}" stroke-width="2"/>')
        for p in points:
            x = x_of(p["snr_db"])
            lo, hi = wilson_interval(p["successes"], p["trials"])
            parts.append(
                f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y_of(hi):.1f}" y2="{y_of(lo):.1f}" '
                f'stroke="{colour}" stroke-width="1.5" opacity="0.6"/>'
                + _marker(marker, x, y_of(p["successes"] / p["trials"]), colour)
            )
    parts.append("</svg>")
    return "".join(parts)


# ---- page ------------------------------------------------------------------------------------

_COMPARED = [
    ("preset", "Preset"),
    ("message_bytes", "message length"),
    ("channel", "channel impairments"),
    ("required_success_rate", "required success rate"),
    ("reference_bandwidth_hz", "reference bandwidth"),
]


def _not_comparable(results: list[dict]) -> str:
    differing = [
        label
        for key, label in _COMPARED
        if len({json.dumps(r[key], sort_keys=True) for r in results}) > 1
    ]
    if len(results) < 2 or not differing:
        return ""
    return (
        '<p class="warn">These results were measured on different terms '
        f"({_e(', '.join(differing))}) and are not directly comparable.</p>"
    )


def _ranked(results: list[dict]) -> list[dict]:
    unreached = float("inf")
    return sorted(
        results, key=lambda r: unreached if r["threshold_db"] is None else r["threshold_db"]
    )


def _summary(results: list[dict]) -> str:
    rows = "".join(
        f'<tr><td class="name"><span class="swatch" style="background:'
        f'{SERIES_COLOURS[results.index(r) % len(SERIES_COLOURS)]}"></span>{_e(r["modem"])}</td>'
        f"<td>{_e(r['preset'])}</td><td>{_e(_threshold_text(r))}</td>"
        f"<td>{r['trials']}</td><td>{r['message_bytes']}</td></tr>"
        for r in _ranked(results)
    )
    return (
        "<h2>Ranking</h2><p class='note'>Lowest Success threshold first: the further left, "
        "the closer to the noise floor.</p>"
        '<div class="scroll"><table><tr><th class="name">Candidate</th><th>Preset</th><th>Success threshold</th>'
        f"<th>Trials per SNR</th><th>Message bytes</th></tr>{rows}</table></div>"
    )


def _detail(result: dict, colour: str) -> str:
    points = sorted(result["curve"], key=lambda p: p["snr_db"])
    threshold = result["threshold_db"]
    rows = []
    for p in points:
        lo, hi = wilson_interval(p["successes"], p["trials"])
        css = ' class="threshold"' if p["snr_db"] == threshold else ""
        rows.append(
            f"<tr{css}><td>{p['snr_db']:g}</td><td>{p['successes']}/{p['trials']}</td>"
            f"<td>{_percent(p['successes'] / p['trials'])}</td>"
            f"<td>{_percent(lo)} to {_percent(hi)}</td><td>{p['false_receptions']}</td></tr>"
        )
    notes = []
    steps = sorted({b["snr_db"] - a["snr_db"] for a, b in zip(points, points[1:], strict=False)})
    if steps:
        notes.append(
            f"The threshold is only known to the step between tested SNRs ({steps[0]:g} dB)."
        )
    at_threshold = next((p for p in points if p["snr_db"] == threshold), None)
    if at_threshold:
        lo, hi = wilson_interval(at_threshold["successes"], at_threshold["trials"])
        notes.append(
            f"At the threshold, {at_threshold['successes']} of {at_threshold['trials']} Messages "
            f"were received: the true rate lies between {_percent(lo)} and {_percent(hi)} "
            "with 95% confidence."
        )
    wrong = sum(p["false_receptions"] for p in points)
    warning = (
        f'<p class="warn">{wrong} wrong Message(s) were handed over as if correct.</p>'
        if wrong
        else ""
    )
    return (
        f'<h2><span class="swatch" style="background:{colour}"></span>{_e(result["modem"])}</h2>'
        f'<p class="verdict">Success threshold: {_e(_threshold_text(result))}</p>'
        f"<p class='note'>Preset {_e(result['preset'])}, seed {result['seed']}, "
        f"{result['trials']} Messages of {result['message_bytes']} byte(s) per SNR.</p>"
        f"{warning}"
        '<div class="scroll"><table><tr><th>SNR (dB)</th><th>Received</th><th>Rate</th><th>95% interval</th>'
        f"<th>False receptions</th></tr>{''.join(rows)}</table></div>"
        + "".join(f"<p class='note'>{_e(n)}</p>" for n in notes)
    )


def render_report(results: list[dict], generated: str | None = None) -> str:
    """The HTML page for one or several result dictionaries (as written by bench.threshold)."""
    legend = "".join(
        f'<li><span class="swatch" style="background:{SERIES_COLOURS[i % len(SERIES_COLOURS)]}"></span>'
        f"{_e(r['modem'])}</li>"
        for i, r in enumerate(results)
    )
    meta = f'<p class="meta">Generated {_e(generated)}</p>' if generated else ""
    body = [
        "<h1>Vibe AudioModem: bench report</h1>",
        meta,
        _not_comparable(results),
        _summary(results) if len(results) > 1 else "",
        "<h2>Success rate against SNR</h2>",
        _chart(results),
        f'<ul class="legend">{legend}</ul>',
        '<p class="note">Dots are the measured share of Messages received correctly; the bars '
        "are their 95% confidence intervals; the dotted vertical line marks each Success "
        "threshold.</p>",
        "".join(_detail(r, SERIES_COLOURS[i % len(SERIES_COLOURS)]) for i, r in enumerate(results)),
    ]
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Vibe AudioModem bench report</title><style>{STYLE}</style></head>"
        f"<body>{''.join(body)}</body></html>"
    )


# ---- commands --------------------------------------------------------------------------------

_REQUIRED_KEYS = [
    "modem", "preset", "seed", "trials", "message_bytes", "reference_bandwidth_hz",
    "required_success_rate", "channel", "curve", "threshold_db",
]  # fmt: skip


def load_result(path: Path) -> dict:
    """Read a result file written by bench.threshold; ValueError says what is wrong with it."""
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    if (
        not isinstance(result, dict)
        or result.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS
    ):
        raise ValueError(
            f"{path}: unsupported schema_version {result.get('schema_version')!r} "
            f"(this report reads {sorted(SUPPORTED_SCHEMA_VERSIONS)})"
            if isinstance(result, dict)
            else f"{path}: not a result file"
        )
    missing = [key for key in _REQUIRED_KEYS if key not in result]
    if missing:
        raise ValueError(f"{path}: missing {', '.join(missing)}")
    return result


def generation_stamp() -> str:
    """When and from which commit a report was made (kept out of the JSON on purpose)."""
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return when
    return f"{when}, commit {commit}"


def write_report(results: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(results, generated=generation_stamp()), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Write an HTML report from one or several bench result files."
    )
    parser.add_argument("results", nargs="+", type=Path, help="JSON files from bench.threshold")
    parser.add_argument("--out", required=True, type=Path, help="HTML file to write")
    args = parser.parse_args(argv)
    try:
        results = [load_result(path) for path in args.results]
    except ValueError as error:
        parser.error(str(error))
    write_report(results, args.out)
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
