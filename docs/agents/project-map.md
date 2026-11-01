# Project map — Vibe AudioModem

Concise map of the repository. Details live in `docs/doc.md` (code walkthrough, ~1500 lines) and `docs/architect_opinion.md` (review + defect register, ~1200 lines). Read those only for the area you touch.

**What it is:** experimental one-way data modem over audio (sound card or WAV), built on GNU Radio. GMSK @ 200 baud, 2500 Hz carrier, 48 kHz audio. Python 3.12, Conda env `vibe-audiomodem` (`environment.yml`). Status: research prototype, no tests, no CI.

## Layout

| Path | What is there |
| :-- | :-- |
| `main.py` | Entry point. `--cli` (in-process + terminal CLI), `--test` (TX writes `test.wav`, RX reads it). Headless = child process running `start_audiomodem`. |
| `src/audioModem/audioModem.py` (596 l) | `ModemController`: config, TX queue/thread, RX subprocess lifecycle, ZMQ sockets, `start_audiomodem()`. |
| `src/audioModem/http_server.py` | FastAPI + Uvicorn thread, port 8000. Routes: `/status /configuration /messages /fft /logs /receive /setup /transmit /stop /quit`. |
| `src/ui/cli.py` | Click CLI talking to the HTTP API (`send`, `receive`, `config`, `stop`, `fft`, `logs`, `exit`). |
| `src/tx/packetizer.py` | Payload → PMT → scramble → 31-byte chunks → Reed–Solomon(48,32) → preamble/postamble frames. |
| `src/tx/transmitter.py` | GNU Radio TX flowgraph: GR header, conv. code 1/2 K=7, diff encode, `gmsk_mod` (240 sps, BT 0.35), rotator to carrier, 3 s beeper, audio/WAV sink. |
| `src/rx/audio_interface.py` | Audio/WAV source; publishes audio (ZMQ 5555) and 4096-pt FFT magnitude (5556). |
| `src/rx/peak_detector.py`, `signal_processor.py`, `worker_manager.py` | FFT → peaks (averaging, persistence) → dispatch demodulator workers. |
| `src/rx/demodulator.py` | GNU Radio RX flowgraph: freq-xlating FIR, AGC, `gmsk_demod`, diff/conv decode, access-code sync, PDU → 5557. |
| `src/rx/packet_decoding.py` | RS decode, `PacketReassembler` (preamble 0 / data 1..31 / postamble 255), unscramble, publish on 5558. |
| `src/misc/config.py`, `scrambling.py` | `SignalConfig`/`PacketConfig`/`PortsConfig` dataclasses + defaults + logging; 7-bit LFSR scrambler. |
| `grc_files/` | GNU Radio Companion flowgraphs (TX/RX masters, GFSK vs GMSK comparison, peak detect, beeper…). Not used at runtime. `**/*py` generated files are gitignored. |
| `research/` (24 MB) | Experiments and analysis scripts, test WAVs, PNGs, `architecture_diagram.md` (partly stale). Not runtime. |
| `profile_memory.py`, `view_profile.py`, `profiling` | tracemalloc wrapper, cProfile viewer, a 1.2 MB profile dump (tracked in git). |
| `docs/` | `doc.md`, `architect_opinion.md`, `gardner1986.pdf` (symbol timing), `agents/` (this folder). |
| `TODO.md` | Phased roadmap (Phase 0 stabilise → 4 productisation), derived from the architect review. |
| `tests/` | Empty, not tracked. No pytest config. |
| `.vscode/launch.json` | Debug `main.py --cli --test`. |

## Runtime in one paragraph

`ModemController` spawns, on `POST /receive`: AudioInterface, PeakDetector (which pre-spawns N demodulator worker processes) and PacketDecoder processes. Everything between them goes through ZeroMQ on localhost: 5555 audio, 5556 FFT, 5557 raw PDUs, 5558 decoded messages, 5559 config (PUB from controller), 5560 detector status (no consumer). About 6 OS processes at steady state with 1 worker.

## Key numbers (defaults)

- 48 kHz, 200 baud, 240 sps TX, ~10 sps RX (decimation 24), carrier 2500 Hz, FFT bin 11.72 Hz.
- RS codeword 48 B (31 payload + 1 length + 16 parity); physical frame 56 B; 4.48 s airtime per frame.
- Fixed overhead per message ≈ 12 s (3 s beeper + preamble + postamble frames). Throughput ≈ 6.9 B/s max.

## Commands

```bash
conda env create -f environment.yml && conda activate vibe-audiomodem
python main.py --cli --test   # local loopback via test.wav (send once before receive)
python main.py                # headless, HTTP on :8000
```

## Known state (as of 2026-11-01)

- Only 200 baud (and 220) decodes reliably; 100/400/500 fail (see `TODO.md` §6 for suspects: idle worker drops `update_preset`, workers retuned to global carrier, slow AGC).
- Code is still GMSK. GFSK is only explored in `grc_files/gfsk_*.grc` and branch `GFSK-migration`/`gfsk-test`.
- Known broken: `Path` TX overload (`filepath` undefined), unrouted `handle_set_preset/set_carrier_freq/cancel_queue`.
- Repo hygiene: WAV/PNG/profiling binaries are tracked despite `.gitignore`; no README/LICENSE/pyproject.
- Many feature branches (`dev`, `GFSK-migration`, `PSK-cleaning`, `frame-sync-improv`, …). Current working branch: `AI_deep_refactoing`; main branch: `main`.

## Rewrite in progress

The code above is the legacy prototype, to be tagged `legacy-v0` and replaced by `src/vibemodem/` (see `TODO.md`, `docs/adr/`, `GLOSSARY.md`). The map above describes the legacy code.
