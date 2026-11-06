"""Build the single report of the real-world trials: docs/measurements/cable-trial/report.html.

    python -m bench.cable_report

The numbers come from `docs/measurements/cable-trial/results.json` (the cable runs) and from the
simulator's curves in `docs/measurements/presets/white-<preset>.json`; the text is written below.
The page is one self-contained file: inline SVG charts, a table under each, light and dark themes.
"""

import html
import json
from pathlib import Path

MEASUREMENTS = Path(__file__).resolve().parent.parent / "docs" / "measurements"
OUTPUT = MEASUREMENTS / "cable-trial" / "report.html"
PRESETS = ["fast", "standard", "max-range"]
REQUIRED = 0.95
SERIES_COLORS = ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6"]  # one per cable run of a Preset, in order

WIDTH, HEIGHT = 640, 300
LEFT, RIGHT, TOP, BOTTOM = 52, 16, 14, 44


def load_runs() -> list[dict]:
    return json.loads((MEASUREMENTS / "cable-trial" / "results.json").read_text())["runs"]


def load_simulator(preset: str) -> list[tuple[float, float]]:
    saved = json.loads((MEASUREMENTS / "presets" / f"white-{preset}.json").read_text())
    return [(point["snr_db"], point["success_rate"]) for point in saved["curve"]]


def threshold(levels: list[list[float]]) -> float | None:
    """The lowest SNR from which, up to the loudest level, 95 % of the Messages arrived."""
    found = None
    for snr, received, sent in sorted(levels, reverse=True):
        if received / sent < REQUIRED:
            break
        found = snr
    return found


def simulator_threshold(curve: list[tuple[float, float]]) -> float | None:
    return threshold([[snr, round(rate * 100), 100] for snr, rate in curve])


def chart(preset: str, runs: list[dict], curve: list[tuple[float, float]]) -> str:
    snrs = [snr for snr, _ in curve] + [row[0] for run in runs for row in run["levels"]]
    low, high = min(snrs) - 1, max(snrs) + 1
    x = lambda snr: LEFT + (snr - low) / (high - low) * (WIDTH - LEFT - RIGHT)  # noqa: E731
    y = lambda rate: TOP + (1 - rate) * (HEIGHT - TOP - BOTTOM)  # noqa: E731
    out = [f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Success rate against SNR, {preset}">']
    for tick in (0, 0.25, 0.5, 0.75, 1):
        out.append(f'<line class="grid" x1="{LEFT}" x2="{WIDTH - RIGHT}" y1="{y(tick):.1f}" y2="{y(tick):.1f}"/>')
        out.append(f'<text x="{LEFT - 8}" y="{y(tick) + 4:.1f}" text-anchor="end">{tick:.0%}</text>')
    step = 2 if high - low > 12 else 1
    for snr in range(int(low) + (int(low) % step), int(high) + 1, step):
        out.append(f'<text x="{x(snr):.1f}" y="{HEIGHT - BOTTOM + 18}" text-anchor="middle">{snr}</text>')
    out.append(f'<text x="{(LEFT + WIDTH - RIGHT) / 2}" y="{HEIGHT - 6}" text-anchor="middle">SNR in 2,500 Hz (dB)</text>')
    out.append(f'<line class="target" x1="{LEFT}" x2="{WIDTH - RIGHT}" y1="{y(REQUIRED):.1f}" y2="{y(REQUIRED):.1f}"/>')
    line = " ".join(f"{x(snr):.1f},{y(rate):.1f}" for snr, rate in curve)
    if curve:
        out.append(f'<polyline class="sim" points="{line}"><title>Simulator, white noise, 100 trials per level</title></polyline>')
    for index, run in enumerate(runs):
        color = SERIES_COLORS[index % len(SERIES_COLORS)]
        rows = sorted(run["levels"])
        out.append(
            f'<polyline class="cable" style="stroke:var({color})" points="'
            + " ".join(f"{x(s):.1f},{y(r / n):.1f}" for s, r, n in rows)
            + '"/>'
        )
        for snr, received, sent in rows:
            tip = f'{run["label"]}: {snr:g} dB, {received} of {sent} received'
            out.append(
                f'<circle cx="{x(snr):.1f}" cy="{y(received / sent):.1f}" r="5" style="fill:var({color})">'
                f"<title>{html.escape(tip)}</title></circle>"
            )
    out.append("</svg>")
    return "".join(out)


def legend(runs: list[dict], simulator: str | None = "Simulator (white noise)") -> str:
    items = [f'<span class="key"><i class="sw sim"></i>{simulator}</span>'] if simulator else []
    for index, run in enumerate(runs):
        color = SERIES_COLORS[index % len(SERIES_COLORS)]
        items.append(f'<span class="key"><i class="sw" style="background:var({color})"></i>{html.escape(run["label"])}</span>')
    return '<p class="legend">' + "".join(items) + "</p>"


def table(runs: list[dict]) -> str:
    snrs = sorted({row[0] for run in runs for row in run["levels"]})
    head = "".join(f"<th>{html.escape(run['label'])}</th>" for run in runs)
    body = []
    for snr in snrs:
        cells = []
        for run in runs:
            found = [row for row in run["levels"] if row[0] == snr]
            cells.append(f"<td>{found[0][1]} of {found[0][2]}</td>" if found else "<td></td>")
        body.append(f"<tr><th scope='row'>{snr:g} dB</th>{''.join(cells)}</tr>")
    return f'<div class="scroll"><table><tr><th>SNR</th>{head}</tr>{"".join(body)}</table></div>'


def summary_table(runs_by_preset: dict[str, list[dict]]) -> str:
    rows = []
    for preset in PRESETS:
        simulated = simulator_threshold(load_simulator(preset))
        for run in runs_by_preset[preset]:
            measured = None if run.get("partial") else threshold(run["levels"])
            gap = "not reached" if measured is None else f"{measured - simulated:+.0f} dB"
            shown = "none" if measured is None else f"{measured:g} dB"
            if run.get("partial"):
                gap = shown = "see text"
            rows.append(
                f"<tr><td class='name'>{preset}</td><td class='name'>{html.escape(run['label'])}</td>"
                f"<td>{simulated:g} dB</td><td>{shown}</td><td>{gap}</td></tr>"
            )
    return (
        "<div class='scroll'><table><tr><th class='name'>Preset</th><th class='name'>Run</th>"
        "<th>Simulator 95 %</th><th>Cable 95 %</th><th>Loss (cable minus simulator)</th></tr>"
        + "".join(rows)
        + "</table></div>"
    )


STYLE = """
:root { --bg:#fcfcfb; --fg:#0b0b0b; --muted:#52514e; --grid:#dddcd6; --panel:#f1f0ec;
        --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#e87ba4; --s5:#6250d6; --s6:#eda100; --sim:#8a8982; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
        --bg:#1a1a19; --fg:#f0efec; --muted:#c3c2b7; --grid:#3a3a37; --panel:#242422;
        --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#d55181; --s5:#9085e9; --s6:#c98500; --sim:#a3a299; } }
:root[data-theme="dark"] { --bg:#1a1a19; --fg:#f0efec; --muted:#c3c2b7; --grid:#3a3a37; --panel:#242422;
        --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#d55181; --s5:#9085e9; --s6:#c98500; --sim:#a3a299; }
body { background:var(--bg); color:var(--fg); font:16px/1.55 system-ui, sans-serif; max-width:56rem;
       margin:0 auto; padding:1.5rem 1rem 4rem; }
h1 { font-size:1.6rem; margin:0 0 .25rem; } h2 { font-size:1.25rem; margin-top:2.5rem; }
h3 { font-size:1.05rem; margin-top:1.6rem; } .meta, .note { color:var(--muted); font-size:.9rem; }
table { border-collapse:collapse; width:100%; margin:.75rem 0; font-variant-numeric:tabular-nums; }
th, td { text-align:right; padding:.3rem .6rem; border-bottom:1px solid var(--grid); }
th:first-child, td.name, th.name { text-align:left; } .scroll { overflow-x:auto; }
.card { background:var(--panel); border-radius:8px; padding:.8rem 1rem; margin:1rem 0; }
svg { width:100%; height:auto; display:block; } svg text { fill:var(--muted); font-size:12px; }
svg .grid { stroke:var(--grid); } svg .target { stroke:var(--muted); stroke-dasharray:6 4; }
svg .sim { fill:none; stroke:var(--sim); stroke-width:2; } svg .cable { fill:none; stroke-width:2; }
svg circle { stroke:var(--bg); stroke-width:2; }
.legend { display:flex; flex-wrap:wrap; gap:.4rem 1.2rem; font-size:.9rem; margin:.25rem 0; }
.sw { display:inline-block; width:.8rem; height:.8rem; border-radius:50%; margin-right:.4rem; }
.sw.sim { background:var(--sim); border-radius:2px; height:.25rem; vertical-align:middle; }
code { background:var(--panel); padding:0 .25rem; border-radius:4px; }
"""

INTRO = """
<p class="meta">Branch AI_deep_refactoing, trials of 5 and 6 November 2026. Tickets
<a href="https://github.com/BimBim134/vibe-audioModem/issues/21">#21</a> and
<a href="https://github.com/BimBim134/vibe-audioModem/issues/28">#28</a>.</p>
<div class="card"><strong>In short.</strong> Over a real audio cable, all three Presets reach 95 % of
Messages received at exactly the simulator's threshold (<em>fast</em> -13 dB, <em>standard</em> -16 dB,
<em>max-range</em> -22 dB): the sound cards and the cable cost nothing. An apparent loss of 3 to 4 dB in
<em>max-range</em> in the first runs was a flaw of the trial itself: the application deleted its oldest kept
receptions beyond its 200 MB limit, and the lowest levels are sent first. No Message was ever accepted
wrongly.</div>
"""

SETUP = """
<h2>What was tested</h2>
<ol>
<li><strong>Simulator thresholds</strong> (ticket #13): 100 trials per level on white noise, 12-byte Messages
hidden up to 10 s into the recording, frequency shift of &plusmn;1,100 Hz. The grey lines below.</li>
<li><strong>Over the air, in a room</strong> (two computers, loudspeakers and the microphone of a laptop, a little
background noise): the three Presets worked well. Short Messages were all received; a 10-Fragment Message
in <em>fast</em> arrived with only 5 Fragments at -5 to -7 dB, about 7 dB worse than the simulator,
probably reverberation (not demonstrated). The same recordings showed false alarms from keyboard and
loudspeaker clicks, which a detector fix removed (per-symbol cap and contrast in the Preamble search; test
<code>tests/test_clicks.py</code>), with the thresholds unchanged.</li>
<li><strong>Over a cable</strong> (this report): the sending laptop adds white noise digitally at an exact SNR
(<code>bench.cable_trial</code>), plays it through its sound card (48 kHz) and a cable into an audio
interface on the receiving tower, running the application with "Keep" on. Each Message names its own SNR, so the
report needs no list. 20 Messages per level (10 for max-range), levels from 2 dB under the simulator's
threshold to 8 dB over it.</li>
<li><strong>Checks on the max-range gap</strong>: a finer 1 dB sweep, the clock drift between the two cards,
the exact sent audio decoded again digitally (batch decoder and live receiver path), and a continuous
recording of the cable decoded offline. They led to the cause: the storage limit of the receiving
application (see the Max-range section). Run 5 repeats the sweep with the limit raised to 3,000 MB.</li>
</ol>
"""

CONCLUSIONS = """
<h2>Conclusions</h2>
<ul>
<li><strong>Fast and standard</strong> match the simulator to the 2 dB step of the trial: 20 of 20 at the
simulator's threshold, 0 of 20 two dB below. The curve is a cliff, not a slope.</li>
<li><strong>Nothing above the threshold was lost</strong> in any Preset: no sound-card gaps, no send errors, and
the SNR estimated by the receiver for the Frames read is within 0.2 dB of the one imposed.</li>
<li><strong>The cable is not the room</strong>: the 7 dB lost over the air in <em>fast</em> is acoustic
(loudspeaker, microphone, reverberation), not the modem and not the sound cards.</li>
<li><strong>Max-range</strong> matches the simulator too: with nothing deleted (run 5), 10 of 10 from -22 dB up, 6 of 10
at -23 dB, none at -24 dB: a threshold of -22 dB, 0.0 dB lost. The 3 to 4 dB loss of runs 1 and 2 and the live
receiver reading fewer Messages in run 4 were one flaw: the lowest levels, sent first, were the receptions the
storage limit deleted (<code>bench.cable_trial report</code> now warns).</li>
</ul>
<h2>Open items</h2>
<ul>
<li>The level robustness step (volume of the sender at 100 %, 25 %, 6 %) was not run: the sender's volume cannot be
set over SSH.</li>
<li>The over-the-air figures above are from the user's field trial and the analysis kept in
<code>docs/agents/memory.md</code>; the recordings are in <code>~/.local/share/vibemodem/receptions</code>.</li>
</ul>
<p class="note">Raw reports: <code>docs/measurements/cable-trial/*.txt</code> and <code>results.json</code>;
simulator curves: <code>docs/measurements/presets/</code>. Regenerate this page with
<code>python -m bench.cable_report</code>.</p>
"""

MAX_RANGE_TEXT = """
<p>The first runs seemed to lose 3 to 4 dB (threshold -18 dB in run 1, -19 dB in run 2), and in run 4 the live
receiver read 5 of 10 Messages at -22 dB that an offline decoding of the same continuous recording read 10 of 10.
The cause is the trial, not the chain: the receiving application keeps the audio of what it receives up to a limit
(200 MB by default) and deletes the oldest receptions beyond it. The Messages are sent from the lowest SNR up, so the
lowest levels were the ones deleted: 25 receptions in run 1, 36 in run 2, 15 in run 4 (the numbering of the kept
files starts at that number). They were counted as lost. The levels below show only what survived; the
Messages that survived at -20 dB were read (4 of 5 in run 1, 4 of 4 in run 2), and replaying the whole run 4 recording
through the live receiver gives the same 4, 10, 10, 10 and 9 of 10 (-23 to -19 dB) as offline decoding.
Run 5 sends 6 levels of 10 Messages with the limit raised to 3,000 MB and nothing is deleted: the threshold is
-22 dB, the simulator's.</p>
<p>Also checked, with the same audio that had been sent: decoding it again digitally (10 of 10 from -22 dB, 4 of 10 at
-23 dB), the application's live path on that audio (the same), the two cards' clocks (17 ppm, about 1 ms over a
Transmission) and the receiving card's noise (-103 dBFS). None of them was a cause. The recording of run 4 at -19 dB
offline is left out: it ended before its last Messages were played.</p>
"""


def build() -> str:
    runs = load_runs()
    by_preset = {p: [r for r in runs if r["preset"] == p] for p in PRESETS}
    sections = []
    for preset in PRESETS:
        extra = MAX_RANGE_TEXT if preset == "max-range" else ""
        sections.append(
            f"<h2>{preset.capitalize()}</h2>{extra}"
            f"{chart(preset, by_preset[preset], load_simulator(preset))}"
            f"{legend(by_preset[preset])}{table(by_preset[preset])}"
        )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Real-world trials</title><style>{STYLE}</style></head><body>"
        "<h1>Real-world trials: over the air and over a cable</h1>"
        f"{INTRO}<h2>Thresholds</h2>"
        "<p class='note'>Success threshold: the lowest SNR from which every higher level still had 95 % of "
        "the Messages received.</p>"
        f"{summary_table(by_preset)}{SETUP}{''.join(sections)}{CONCLUSIONS}</body></html>"
    )


def main() -> None:
    OUTPUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
