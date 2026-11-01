- [0. Decision frame](#0-decision-frame)
- [1. Phase 0 — Stabilize (P0 bugs, tests, packaging spike)](#1-phase-0--stabilize-p0-bugs-tests-packaging-spike)
  - [1.1 P0 correctness and liveness](#11-p0-correctness-and-liveness)
  - [1.2 Validation and tests](#12-validation-and-tests)
  - [1.3 Repository hygiene and packaging spike](#13-repository-hygiene-and-packaging-spike)
- [2. Phase 1 — Collapse and harden](#2-phase-1--collapse-and-harden)
  - [2.1 Process topology](#21-process-topology)
  - [2.2 Control plane](#22-control-plane)
  - [2.3 Local-first UI boundary](#23-local-first-ui-boundary)
  - [2.4 Multi-carrier tracker](#24-multi-carrier-tracker)
  - [2.5 Presets and message budget](#25-presets-and-message-budget)
- [3. Phase 2 — Protocol v2: robustness](#3-phase-2--protocol-v2-robustness)
  - [3.1 Logical frame](#31-logical-frame)
  - [3.2 Robustness features](#32-robustness-features)
  - [3.3 Format and compression](#33-format-and-compression)
- [4. Phase 3 — DSP and detection characterization](#4-phase-3--dsp-and-detection-characterization)
  - [4.1 DSP](#41-dsp)
  - [4.2 Detection](#42-detection)
  - [4.3 Measurements](#43-measurements)
- [5. Phase 4 — Productization and UI](#5-phase-4--productization-and-ui)
- [6. Baud-rate investigation (old #3)](#6-baud-rate-investigation-old-3)
- [7. P1/P2/P3 defect backlog](#7-p1p2p3-defect-backlog)
  - [P1 — data loss and resource leaks](#p1--data-loss-and-resource-leaks)
  - [P2 — robustness and maintainability](#p2--robustness-and-maintainability)
  - [P3 — cleanup / wire-up](#p3--cleanup--wire-up)
- [8. Mapping of the previous TODO](#8-mapping-of-the-previous-todo)
- [9. Explicit non-goals and traps](#9-explicit-non-goals-and-traps)

# 0. Decision frame

These constraints from `docs/architect_opinion.md` §Product constraints drive every
priority below. Do not trade robustness for throughput.

- **One-way broadcast** for radio amateurs: no ACK/ARQ, no feedback-driven
  adaptation. Reliability comes from FEC, CRC, interleaving, repetition, diversity.
- **Dynamic multi-carrier detection is core.** Users tune arbitrarily; no fixed
  channel plan.
- **Remote station control is nice-to-have.** Local operation first. If exposed,
  auth/TLS is mandatory.
- **Robustness is the product; speed is not.** KPI is correct delivery under
  noise, fading, mistuning, and level variation.
- **Users are non-technical radio amateurs.** Easy install/run on Windows, macOS,
  Linux is a core feature.
- **Simplest thing that works.** Fewer processes, fewer transports, conservative
  defaults, one obvious way to run the app.
- **Small-message-first with a 30-minute ceiling** (~10–12 KB at the current
  default PHY before interleaving/repetition overhead).
- **Presets are the default interface**, advanced settings hidden behind a toggle.
- **Broad hardware/channel compatibility** (HF SSB, VHF FM, handheld
  speaker/mic, direct sound card), automatic level calibration, configurable
  search band.
- Keep GNU Radio while it is the most robust practical option; packaging success,
  not performance, decides whether a compiled DSP core is needed.

See `docs/doc.md` for the current code walkthrough and `docs/architect_opinion.md`
for evidence and file:line references.

---

# 1. Phase 0 — Stabilize (P0 bugs, tests, packaging spike)

Fix correctness and lifecycle before any feature work. A robust modem that drops
config or crashes on shutdown is not robust.

## 1.1 P0 correctness and liveness

- [ ] **P0-1 Shared mutable config defaults.** `ModemController` keeps
      `DEFAULT_PACKET_CONFIG` / `DEFAULT_PORTS_CONFIG` by reference and
      `handle_setup` mutates them in place, permanently changing process-wide
      defaults. Deep-copy all configs; make defaults frozen; use
      `dataclasses.replace`.
- [ ] **P0-2 Global one-shot stop events.** `STOP_EVENT` /
      `INTERNAL_STOP_EVENT` are module globals, never cleared/reset. Use
      instance-owned lifecycle and stop events; clear on start.
- [ ] **P0-3 HTTP server never stops gracefully.** `run_http_server` accepts
      `stop_event` but never uses it; Uvicorn runs in a daemon thread. Use
      `uvicorn.Server` with `should_exit` and `lifespan`; join the server thread.
- [ ] **P0-4 Blocking calls in async handlers.** `/receive`, `/setup`, `/stop`
      join/terminate processes and sleep on the event loop. Use `def` handlers or
      `asyncio.to_thread`; move state changes to a single actor.
- [ ] **P0-5 Fragile GNU Radio tag hack / PDU length ambiguity.** Remove
      `TagValueSetter`; use the correct tag; assert the PDU length; pin GNU Radio;
      add a golden test for 48/52/56-byte behavior.
- [ ] **P0-6 Idle workers drop `update_preset`.** Handle `update_preset` in the
      idle loop, acknowledge it, and version configs.
- [ ] **P0-7 Running workers retuned to global carrier.** A config update moves a
      worker off its detected peak to the controller default 2500 Hz. Preserve the
      worker's active frequency; update only baud/beeper; send a full snapshot.
- [ ] **P0-8 TX cancel sentinel race.** Replace the shared cancel event and
      `None` sentinel with per-job cancellation tokens/job IDs and an explicit TX
      state machine.
- [ ] **P0-9 Unauthenticated, unvalidated remote API.** Bind `127.0.0.1` by
      default; add auth, CORS, rate limits, body/message size limits, and input
      validation before remote use is enabled.

## 1.2 Validation and tests

- [ ] Add Pydantic validation for config and HTTP bodies with cross-field
      invariants (baud > 0, carrier < Nyquist, sane `fft_size`, chunk length,
      `nb_workers` bounds).
- [ ] Add `pytest`, `ruff`, `mypy`/`pyright`, `pre-commit`.
- [ ] Unit tests: `Scrambler` symmetry, chunk boundaries, RS encode/decode,
      `PacketReassembler` state machine, config validation, PDU size.
- [ ] Property tests (Hypothesis) for framing/reassembly round-trips, including
      payload sizes 0, 1, 30, 31, 32, 255.
- [ ] Golden test for the wire format, PDU lengths, and access-code position.
- [ ] WAV loopback integration test at 200 baud (`python main.py --test`).
- [ ] Lifecycle test: start/stop/restart 100 times with no leaked
      processes/sockets/threads.

## 1.3 Repository hygiene and packaging spike

- [ ] Add `pyproject.toml`, a lockfile, and a README.
- [ ] Pin GNU Radio and all dependencies.
- [ ] Declare `requests`; drop unused/undeclared deps (`websockets` is unused).
- [ ] Remove committed WAV/PNG/profiling binaries from Git; keep small fixtures
      or external storage.
- [ ] Remove stale generated `grc_files/*.py`; generate in CI if still needed.
- [ ] **Packaging spike:** PyInstaller / conda-pack / Briefcase on Windows first,
      then macOS/Linux; document what breaks.
- [ ] Test installation on a clean machine or VM, not the developer machine.

**Acceptance:** `pytest`, `ruff`, and type checks green; `python main.py --test`
passes; `/receive`, `/transmit`, `/stop`, `/quit` work with graceful shutdown; no
global config mutation; a non-developer can start a bundle/installer.

---

# 2. Phase 1 — Collapse and harden

Recommended target is **Option B** from `docs/architect_opinion.md` §7: one
modem/DSP process plus an optional audio-isolation process.

## 2.1 Process topology

- [ ] Collapse audio source, FFT, peak tracker, N demod chains, packet decoder,
      and message fan-out into **one GNU Radio `top_block`** with in-process
      queues.
- [ ] Remove internal ZeroMQ buses (5555–5560) from the default path.
- [ ] Keep a separate process only for audio-device isolation or hard CPU
      isolation.
- [ ] Add a supervisor that restarts the DSP process on crash.

## 2.2 Control plane

- [ ] Replace the controller with a single-threaded `ModemService` actor owning
      config, receiver state, worker state, TX queue, and message ring buffer.
- [ ] Route HTTP/CLI through a command queue; emit events to subscribers.
- [ ] Use request IDs/futures for command responses; eliminate ad-hoc locks and
      globals.
- [ ] Replace ZMQ config broadcasts with a retained, versioned config store;
      workers fetch current config on startup and ignore stale versions.
- [ ] Make config immutable and versioned: one validated `AppConfig` snapshot;
      `ConfigService.apply()` validates, diffs, stops/restarts only what is
      needed, and returns a result.
- [ ] Treat ports, sample rate, FFT size, and packet/FEC parameters as
      startup-only; require an explicit restart.
- [ ] Make `handle_setup` transactional (validate first, apply atomically,
      rollback on failure).
- [ ] Fix port-change ordering: stop children before applying new ports.

## 2.3 Local-first UI boundary

- [ ] Default application path calls `ModemService` directly in-process; no
      HTTP/Uvicorn required for local use.
- [ ] Keep FastAPI as an **optional** remote adapter (`--serve` or settings
      toggle) with `lifespan`, `uvicorn.Server` shutdown, Pydantic models, and
      non-blocking handlers.
- [ ] Bind loopback by default; `0.0.0.0` only with auth/TLS.
- [ ] Add `GET /healthz`, `GET /readyz`, `GET /metrics`.
- [ ] Replace drain-based `/messages` with a ring buffer and cursor/sequence
      (`GET /messages?since=<seq>`) plus SSE/WebSocket for push.
- [ ] Add job IDs: `POST /transmit` returns `job_id`; `GET /transmit/{id}`;
      `DELETE /transmit/{id}` cancels one job.
- [ ] Cache the latest FFT frame; remove per-request ZMQ context creation.
- [ ] Stream logs from a ring buffer; do not read the whole file per request.
- [ ] Add `--host`/`--port` flags and forward the port to the headless child.

## 2.4 Multi-carrier tracker

- [ ] Replace per-peak worker spawning with persistent **carrier tracks** keyed
      by frequency and bandwidth.
- [ ] Add hysteresis, merge/split rules, a maximum track count, and per-track
      demodulator state.
- [ ] Add CFAR/local noise estimation and an adaptive noise floor.
- [ ] Make the search band configurable and remove the hard 1 kHz cutoff as a
      default exclusion.
- [ ] Default to a small usable worker pool (e.g. 4 or CPU-count-based) and
      bound/validate `nb_workers`.
- [ ] Add worker liveness checks (`is_alive()`, heartbeat), restart dead workers,
      and expose track/worker state.

## 2.5 Presets and message budget

- [ ] Implement named, validated presets (`Robust`, `Balanced`, `Fast`) as config
      bundles; wire `presets_path` and preset selection.
- [ ] Main UI exposes only the preset selector and essentials; advanced
      overrides live behind a hidden, validated panel.
- [ ] Add an airtime estimator; show it before sending.
- [ ] Enforce the 30-minute ceiling and a hard ~10–12 KB payload limit; reject
      oversized messages with a clear error and suggestion.
- [ ] Preserve the original RX message type (`raw_string` / `raw_bytes` / `file`)
      in a separate field; add a file download path.

**Acceptance:** 1 process (or 2 with audio isolation); no internal ZMQ; no HTTP
listener in default local mode; multiple SSE clients receive all messages;
`/receive` does not block other requests; clean shutdown; metrics visible; a
non-engineer can install and run it; dynamic carriers are tracked, not spawned per
peak; presets work and advanced settings are hidden by default; oversized messages
are rejected with an airtime estimate.

---

# 3. Phase 2 — Protocol v2: robustness

Keep the working RS + convolutional code as the baseline. Add integrity and
identity before changing FEC. Airtime reduction is a bonus, never an acceptance
criterion.

## 3.1 Logical frame

- [ ] Add a logical header:
      `[magic][version][flags][msg_id][frag_index][frag_total][payload_len][payload][crc32]`.
- [ ] Add **CRC-32** over the logical frame so miscorrections are rejected, not
      delivered as data.
- [ ] Add `msg_id`, `frag_index`, `frag_total` so lost fragments, duplicates, and
      interleaved messages are detectable.
- [ ] Keep a known preamble and the GNU Radio access code; replace the 3 s beeper
      with a proper known preamble (chirp, Zadoff–Chu, or constant-amplitude
      pattern) that provides detection, AGC settling, timing, and coarse AFC.
- [ ] Remove the application postamble; replace its function with `frag_total`
      plus a short end marker.
- [ ] Remove the duplicated length in the GNU Radio header (if both ends are
      controlled) and the per-chunk length byte; keep one authoritative length.
- [ ] Replace random filler with deterministic zero padding or a shortened code.

## 3.2 Robustness features

- [ ] Add a block interleaver matched to measured burst length; measure before and
      after.
- [ ] Add optional blind repetition (N copies) with receiver-side de-duplication
      by `msg_id` and optional selection/combining by CRC.
- [ ] Characterize RS(48,32) + rate-1/2 CC: BER/SNR curve and burst tolerance.
- [ ] Only then test interleaving, soft-decision Viterbi/LDPC, stronger/low-rate
      codes, and (later) rateless/fountain coding for large files.
- [ ] Remove the no-op `puncpat='11'` wrapper or make it a real puncture pattern.
- [ ] Consider a longer sync word (64-bit) or stricter threshold; measure false
      sync rate first.

## 3.3 Format and compression

- [ ] Use PMT only inside GNU Radio. Use JSON at the local API boundary; add
      MessagePack/CBOR only if profiling shows a need.
- [ ] Compress text/file payloads only when the compressed form is smaller and
      the CPU cost cannot disturb real-time audio; fall back on failure/expansion.

**Acceptance:** corrupt/lost fragments are detected, not delivered; multiple
messages can interleave; decode probability under noise is equal or better than
before; golden/property tests pass; oversized messages are rejected with an
accurate airtime estimate.

---

# 4. Phase 3 — DSP and detection characterization

Measure before changing the PHY. Keep 200 baud as the robust default until a
faster rate matches its success probability.

## 4.1 DSP

- [ ] Replace slow `agc_cc(1e-4)` with a faster loop (`1e-2`–`1e-3`) or a
      feed-forward gain estimate from the preamble; tie the time constant to the
      symbol rate.
- [ ] Use a constant-amplitude preamble at the same amplitude as the data.
- [ ] Use `rational_resampler`/polyphase to get exactly 10 samples/symbol at every
      baud (current integer decimation gives 10.0, 10.39, 10.67).
- [ ] Use `digital.symbol_sync_cc` with Gardner/Mueller–Muller and a loop
      bandwidth scaled to the symbol rate; document/tune `gmsk_demod`.
- [ ] Note: `omega_relative_limit=0.005` is **loose** (5,000 ppm), not the main
      suspect; do not blame it without measurement.
- [ ] Consider a two-stage decimator or polyphase channelizer for CPU.
- [ ] Evaluate a DFE/equalizer for acoustic reverberation only after measurement.
- [ ] Add coarse AFC from the preamble and track residual offset.
- [ ] Support explicit frequency/time diversity, de-duplicated by `msg_id`.

## 4.2 Detection

- [ ] Replace the global-mean peak threshold with CFAR/local noise estimation.
- [ ] Adaptive noise floor (not calibrated once and frozen).
- [ ] Configurable search band; no hard 1 kHz cutoff.
- [ ] Shorter hysteresis (0.5–1 s) and an `acquiring → tracking → lost` state
      machine; current eviction is ~4.35 s.
- [ ] Bound and prioritize worker tracks by SNR/confidence and age.

## 4.3 Measurements

- [ ] Build BER/SNR and message-success curves across SNR, audio level, carrier
      offset, baud rate, and burst-noise patterns.
- [ ] Sweep baud rates 100/200/220/400/500 with fixed and live config.
- [ ] Build a channel matrix: HF SSB, VHF FM, handheld speaker/mic, direct sound
      card, with real recordings; vary level, device, frequency response, offset.
- [ ] Add automatic input-level calibration.
- [ ] Add metrics for frames received, RS/CRC errors, sync hits, peak/track
      detections, worker state, queue depth, TX duration, airtime, CPU/RSS.

**Acceptance:** documented BER/SNR and message-success curves; improved decode
probability at the target SNR across the channel matrix; no dead workers;
arbitrary carriers tracked. Higher baud rate is optional, not a goal.

---

# 5. Phase 4 — Productization and UI

- [ ] **Replace the CLI with a TUI** (old #1): same capabilities, nicer
      interaction.
- [ ] **Create a web UI** (old #2) that can do everything the CLI can, graphically.
- [ ] **Add the option to launch only the web UI** (old #2.1) for optional remote
      station control; require auth/TLS when exposed.
- [ ] **Add signal visualization** (old #4): spectrum, waterfall, detected
      carriers/tracks, FFT snapshot.
- [ ] **Add a clear-log function** (old #7).
- [ ] Preset-first workflow; hidden advanced panel; airtime estimate; message
      budget warnings.
- [ ] Message persistence (SQLite) and file download.
- [ ] Log rotation and retention; structured JSON logs with `process`, `thread`,
      `message_id`, `demod_id`, `carrier_freq`.
- [ ] Signed installers and CI release artifacts for Windows/macOS/Linux.
- [ ] Add README, LICENSE, and contributing guide.
- [ ] Remote station mode: mTLS/VPN and audit logging mandatory.

---

# 6. Baud-rate investigation (old #3)

Current experiment log (from the previous TODO):

| Test | Result |
| :--- | :--- |
| 400 baud | fail |
| 500 baud | fail |
| 100 baud | fail |
| 200 baud, carrier 2000 | pass, deltaf 3.91 Hz |
| start 500, then set 200 | pass, deltaf 3.91 Hz |
| start 200, then set 500 | fail |
| 220 baud | pass |
| decimation added | helped a little |

Do not assume a single cause. The strongest suspects in the current code:

1. **Idle workers drop `update_preset`** (matches "start 200, then set 500 fails").
2. **Running workers retuned to the global carrier** (worker moves off its peak).
3. **Slow AGC**: `agc_cc(1e-4)` needs ~2–10 s depending on baud; the 3 s beeper
   is insufficient at 100 baud and marginal at 200.
4. **Beeper amplitude 0.77 vs different data amplitude**: AGC over-reduces gain.
5. **Channel filter scales with baud**: cutoff `baudrate * 1.5`, transition
   `baudrate / 3`; filter length/decimation interact with timing.
6. **`omega_relative_limit=0.005` is loose**, not the main suspect.
7. **Loop parameters and filter are tuned for the 200-baud design point** even
   though `actual_sps` is computed, not hardcoded.

Diagnostic plan:

- [ ] Run `--test` loopback at 100/200/220/400/500 with **fixed** config; log AGC
      gain, timing error, access-code hits, PDU length, RS errors.
- [ ] Repeat with **live** `update_preset` from idle and from running to isolate
      the idle-worker bug.
- [ ] Sweep AGC rate, filter cutoff/transition, decimation, and timing-loop params.
- [ ] Measure BER vs SNR with `research/addNoise.py` at each baud.
- [ ] Replace the beeper with a constant-amplitude preamble and re-measure AGC.
- [ ] Use a rational resampler for exact 10 samples/symbol at every baud.
- [ ] Record real-chain samples and tune against the matrix.
- [ ] Keep 200 baud if it wins on message-success probability; a faster rate is a
      product tradeoff, not an automatic improvement.

---

# 7. P1/P2/P3 defect backlog

Full evidence is in `docs/architect_opinion.md` §4.

## P1 — data loss and resource leaks

- [ ] `reassemblers` global never pruned; use a bounded LRU/timeout.
- [ ] Unbounded reassembly buffer; add max size, timeout, total-length validation.
- [ ] PUB/SUB message loss; use retained config, durable message log, in-process
      queues.
- [ ] Drain-based `/messages`; replace with ring buffer + cursor.
- [ ] No worker liveness check; add `is_alive()`, heartbeat, restart policy.
- [ ] Grandchildren orphaned on hard terminate; use process groups/job objects or
      a supervisor.
- [ ] Parent does not check child exit code; log/restart/fail.
- [ ] ZMQ sockets used across threads; confine each socket to one thread and stop
      threads before closing.
- [ ] `/fft` creates a context per request; use a long-lived subscriber/cache.
- [ ] RX overwrites original message type; preserve it.
- [ ] No TX message-size limit; enforce the 10–12 KB / 30-minute budget.
- [ ] No `nb_workers` limit; validate/cap.

## P2 — robustness and maintainability

- [ ] No config validation (see Phase 0).
- [ ] Slow AGC / beeper amplitude mismatch (see Phase 3).
- [ ] Detection latency/fragility (see Phase 3).
- [ ] No CRC / message ID / interleaving (see Phase 2).
- [ ] Optional compression (see Phase 2).
- [ ] PMT used as an external format (see Phase 2).
- [ ] `Path` TX overload references undefined `filepath`; `NameError` on file send.
- [ ] `_export_to_bin` writes a NumPy array directly; use `tobytes()`.
- [ ] `visualize_bytes` prints raw arrays; format hex.
- [ ] `cancel_queue` state mismatch: `/status` says idle while audio still plays.
- [ ] Non-transactional setup; validate/apply atomically.
- [ ] Port restart ordering (see Phase 1).
- [ ] Log file shared by processes/threads; use `QueueHandler`/`QueueListener` and
      rotation.
- [ ] `datetime.now().isoformat()` used as demodulator ID; use `uuid4`.
- [ ] `AudioProbe` claims a 2 s window but uses the current block.
- [ ] Audio/WAV metadata not validated; reject wrong sample rate/channels.
- [ ] `AudioInterface` stop race; start first, then monitor, or use a state
      machine.
- [ ] `catch_exceptions=True` hides TX errors; propagate failures.
- [ ] `get_nb_of_audio_samples` integer division truncates the last frame; use
      ceil and validate length.

## P3 — cleanup / wire-up

- [ ] Wire presets (`handle_set_preset`, `presets_path`) — now a product feature.
- [ ] Decide on `handle_set_carrier_freq` and `handle_cancel_queue`: wire with
      tests or delete.
- [ ] Delete `Demodulator.set_carrier_freq` if workers always rebuild.
- [ ] Remove unused `run_http_server(stop_event=...)`.
- [ ] Remove `constellation_name` from the CLI and config display.
- [ ] Remove unused imports (`List`, `time` in `http_server.py`; `audio` in
      `demodulator.py`).
- [ ] Remove unused `freq_deviation` / `hdr_format`.
- [ ] Fix `research/architecture_diagram.md` (FFT is magnitude `float32`;
      messages are PMT, not JSON).
- [ ] Move `research/` out of the runtime package; add a README.
- [ ] Remove `research/conjecture.txt` (unrelated).

---

# 8. Mapping of the previous TODO

| Previous item | New home |
| :--- | :--- |
| #1 replace CLI by a TUI | Phase 4 |
| #2 create a web UI | Phase 4 |
| #2.1 launch only the web UI | Phase 4 (optional remote mode, with auth/TLS) |
| #3 why only 200 baud works | Phase 3 / §6 |
| #4 signal visualization in CLI | Phase 4 (and TUI/web UI) |
| #5 calibrate peak detector noise floor | Phase 1 tracker / Phase 3 detection |
| #6 improve peak detector for noisy signals | Phase 1 tracker (CFAR, hysteresis) / Phase 3 |
| #7 clear log function | Phase 4 |
| #8 full test suite | Phase 0 (then expanded in Phases 1–3) |

---

# 9. Explicit non-goals and traps

- **Do not** replace dynamic multi-carrier detection with a fixed channel plan.
- **Do not** remove the preamble as a blanket optimization; keep a known preamble
  for detection, AGC, timing, and coarse AFC.
- **Do not** trade decode probability for airtime, throughput, or latency.
- **Do not** raise the baud rate just because the receiver can be fixed; 200 baud
  may be the correct robust operating point.
- **Do not** replace RS + CC merely because it is "inefficient"; characterize it
  first.
- **Do not** choose a compiled DSP rewrite for speed; only if packaging or measured
  robustness demands it.
- **Do not** require external clients to speak PMT.
- **Do not** expose the HTTP API on `0.0.0.0` without auth/TLS.
- **Do not** schedule protocol work by airtime saved; schedule it by measured
  message-success probability.