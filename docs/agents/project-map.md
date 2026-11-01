# Project map — Vibe AudioModem

Concise map of the repository as it is now. The roadmap is `TODO.md`, the vocabulary `GLOSSARY.md`, the decisions `docs/adr/` and `docs/agents/memory.md`.

**What it is:** a one-way, weak-signal data modem for radio amateurs, being rewritten from scratch. Python 3.12, NumPy/SciPy core, `uv` for dependencies, no GNU Radio. The first prototype is frozen under the git tag `legacy-v0`; see `docs/legacy/` for its documentation, and read its files with `git show legacy-v0:<path>`.

## Layout

| Path | What is there |
| :-- | :-- |
| `src/vibemodem/core/modem.py` | The candidate interface: `Modem` protocol (`modulate(message, preset)`, `demodulate(samples)`) and `Reception` (message plus optional metrics). The rest of the core is empty so far. Imports nothing from `io`, `app`, `bench`, the network or audio libraries; enforced by a test. |
| `src/vibemodem/io/recorder.py` | Spike-grade audio input: list devices, record N seconds. Reports a missing audio library separately from a missing device. |
| `src/vibemodem/app/hello.py` | Packaging-spike app: loopback web page (record 5 s, DSP self-test, quit), `create_app` with injected recorder for tests. `python -m vibemodem.app` runs it. |
| `bench/channel.py` | Channel simulator: `apply_channel(samples, ChannelConfig, seed)`; fading, frequency offset, white noise at an SNR in 2,500 Hz, impulses, 300–2,700 Hz filter, clipping, clock drift. All off by default, each with its own seeded stream. |
| `bench/toy.py` | `ToyModem`: coherent BPSK at 100 bit/s, no sync, no coding. Exists only to validate the bench against the textbook error curve. |
| `bench/threshold.py` | `measure_curve`, `success_threshold` (lowest SNR reaching 95%, with every higher tested SNR also passing) and the command `python -m bench.threshold --modem pkg.mod:Class --out file.json`. |
| `bench/report.py` | Self-contained HTML report (inline SVG chart, Wilson 95% intervals, ranking, not-comparable notice) from result JSON files: `render_report`, and the command `python -m bench.report a.json b.json --out r.html`; also reached through `--html` on the threshold command. |
| `packaging/` | `vibemodem.spec` (PyInstaller, windowed), `entry.py`, `smoke_test.py` (run against the built executable in CI). |
| `tests/` | `test_layers.py` (layers importable, core stays pure), `test_channel.py`, `test_hello_app.py`, `test_toy_modem.py`, `test_threshold.py` (threshold logic, toy modem vs theory), `test_threshold_command.py`, `test_report.py`, `test_report_command.py`; `fake_modems.py` holds stand-in candidates. |
| `.github/workflows/` | `ci.yml` (ruff + pytest on Linux/Windows/macOS), `package.yml` (build, smoke-test and upload Windows/macOS artifacts). |
| `docs/` | `adr/` (decisions), `packaging/` (spike findings, manual check procedure), `legacy/` (prototype docs), `references/` (papers), `agents/` (this folder). |

## Commands

```bash
uv sync --locked --all-extras              # set up
uv run ruff check . && uv run ruff format --check . && uv run pytest
uv run python -m vibemodem.app             # run the spike app
```

## State (2026-11-01)

- Roadmap steps 0–1 done (foundation, packaging spike) and the channel simulator (part of step 2). Success threshold measurement and the candidate interface (issue #5) are done. Next: the baseline modem (issue #6).
- Work is tracked as GitHub issues under the spec issue #1; the labels `ready-for-agent` / `ready-for-human` mark who picks them up.
- Branch `AI_deep_refactoing` carries the rewrite; `main` is the default branch.
