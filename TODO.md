# Roadmap — Vibe AudioModem rewrite

High-level roadmap only. Each step becomes GitHub tickets later (`/to-spec`, then `/to-tickets`). Vocabulary: `GLOSSARY.md`. Decisions: `docs/adr/` and `docs/agents/memory.md`. The previous 470-line TODO is in git history; the architecture review that motivated the rewrite is `docs/legacy/architect_opinion.md`.

## Goal

A one-way, weak-signal data modem for radio amateurs that decodes **as close to the noise floor as possible** in a narrow band (~100 Hz per signal by default), over SSB audio (300–2,700 Hz). A slow message that arrives beats a fast one that does not.

**Measure of success:** the *Success threshold* — the lowest SNR, in a 2,500 Hz reference noise bandwidth, at which at least 95% of test Messages are received correctly.

**v1 is done when** a radio amateur installs the app without a terminal, picks a Preset, sends a short text, and it arrives intact (CRC-verified) on a second computer — first through a virtual audio loop, then over a real audio chain.

## Decisions that frame everything

- Rewrite from scratch; the old code is tagged `legacy-v0` and is reference only, not an oracle (ADR 0001).
- Pure NumPy/SciPy DSP core with no I/O; no GNU Radio (ADR 0002). Audio via `sounddevice`.
- One UI: a local web page served on `127.0.0.1` (single HTML + plain JS, canvas for spectrum/waterfall, no npm). No TUI.
- Presets: *maximum range* (narrowest, slowest), *standard* (default, ~100 Hz), *fast*. Final values come from the bench. Maximum Message size depends on the Preset; airtime is shown before sending; 30-minute ceiling.
- Modulation, code and band are open until measured. Candidates: low-baud GFSK (GMSK is GFSK with h = 0.5), non-coherent M-FSK; LDPC, turbo, long-constraint convolutional, all fed with LLRs.
- Synchronisation by correlation with a known sequence over time × frequency. No UTC time grid, no internet dependency.
- v1 decodes **one** Signal at a time at an unknown audio frequency.
- Stack: Python 3.12, NumPy/SciPy, `sounddevice`, FastAPI/Uvicorn, pytest, ruff, `pyproject.toml` + lockfile. Windows first (tested via GitHub Actions), then macOS/Linux. GPL-3.0 by default, to be confirmed before importing third-party code.
- Layout: `src/vibemodem/{core,io,app}/` and `bench/`.

## Steps

Each step ends with a measurable result. Do not start the next before the previous is met.

### 0. Foundation
Tag `legacy-v0`; skeleton `src/vibemodem/` and `bench/`; `pyproject.toml` + lockfile; pytest, ruff; README; LICENSE; GitHub Actions on Linux, Windows, macOS.
**Done when:** CI is green on all three systems with a trivial test.

### 1. Packaging spike (time-boxed, a few days)
A "hello" app: Python + NumPy + `sounddevice` + local web server, packaged for Windows then macOS.
**Done when:** a non-developer double-clicks it, sees the page in their browser, and records 5 s of sound. If it fails, write an ADR before going on.

### 2. Measurement bench
Channel simulator (white noise, frequency offset, clock drift, clipping, impulsive noise, fading, SSB 300–2,700 Hz band filter), Message generator, Success threshold computation, a common `encode`/`decode` interface for candidate modems.
**Done when:** a toy modem reproduces the theoretical error curve on white noise, and results are reproducible (fixed seed).

### 3. Baseline modem
Narrow non-coherent M-FSK (~100 Hz), simple convolutional code, CRC, sync by correlation over time × frequency.
**Done when:** noiseless WAV round trip is 100% and a first Success threshold is measured.

### 4. Error-correcting codes
Common LLR interface; LDPC, turbo, long-constraint convolutional.
**Done when:** a table of Success threshold vs CPU time exists, decoding runs in real time on an ordinary laptop in plain NumPy, and the choice is recorded as an ADR.

### 5. Modulation and bandwidth
Low-baud GFSK vs M-FSK (M, tone spacing, symbol duration); interleaver; repetition; occupied bandwidth measured at −20 dB.
**Done when:** the *standard* Preset is fixed (~100 Hz) with a measured Success threshold, and *maximum range* and *fast* are sketched.

### 6. Message protocol
Frame layout, `msg_id`, fragment index and total, CRC, fragmentation, airtime estimator, maximum size per Preset, de-duplication of repetitions.
**Done when:** a multi-Fragment Message crosses the bench, a corrupted Fragment is rejected, and no CRC false positive occurs over a large number of trials.

### 7. Local application
`io` layer (sound card, WAV), local web server, UI (send, receive, spectrum/waterfall, Presets), logs. The receiver also records raw audio and per-reception metrics.
**Done when:** the v1 criterion above is met through a virtual audio loop.

### 8. Real-world validation and installer
Hardware available: two computers and an audio cable; free-field loudspeaker/microphone if the software is robust enough; later two radios with sound cards.
- 8a. Cable between two computers: measure the real Success threshold.
- 8b. Loudspeaker and microphone.
- 8c. Radio field campaign. Each reception keeps its raw audio and performance indicators (estimated SNR, frequency offset, sync score, LLR statistics, decoded or not, Message id) so recordings can be replayed on the bench to tune settings.
- Windows installer.
**Done when:** the v1 criterion is met on a real audio chain.

## After v1

Several simultaneous Signals; UTC time grid if measurement shows a gain; fountain codes; remote station control (with authentication); other channels (VHF FM, handheld).

## Requirements inherited from the legacy review

Verified by tests in the new code: no mutable global state or shared default configs; per-instance lifecycle and stop events; validated, versioned configuration; bounded buffers and queues; clean shutdown with no leaked threads or processes; no log file shared between processes; a corrupted frame is rejected, never delivered.

## Traps

- Do not trade the Success threshold for speed, airtime or latency.
- Do not fix a channel plan; the receiver searches over frequency.
- Do not replace a code or modulation on opinion; use the bench.
- Do not make the core depend on I/O, a clock, or the network.
