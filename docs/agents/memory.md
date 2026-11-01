# Project memory (portable)

This file replaces the agent's local memory directory. **Keep durable project context here, in git**, so it follows the repo to any machine. Do not write memories under `~/.claude/...` for this project. Update this file (and `project-map.md`) instead; keep entries short and dated.

## Owner / working style

- Owner: maxiBimbim (GitHub `BimBim134`), French speaker. Chat in French; repo docs and code in English.
- Migrated an existing codebase to Claude Code on 2026-11-01. New to the `mattpocock-skills` workflow: explain steps, guide step by step.
- Wants to be asked questions first (`/grill-with-docs`) before building the glossary/ADRs.
- When told "do nothing for now", do nothing until asked.

## Product constraints (from `docs/architect_opinion.md`, confirmed by owner)

One-way broadcast for radio amateurs (no ACK/ARQ). Robustness over speed (KPI = correct delivery under noise). Dynamic multi-carrier detection is core (no fixed channel plan). Non-technical users → easy install on Windows/macOS/Linux. Simplest architecture that works. Small messages first, 30-minute transmission ceiling (~10–12 KB). Presets by default, advanced settings hidden. Must work across HF SSB, VHF FM, handheld, direct sound card. Remote control is optional and needs auth/TLS. Keep GNU Radio unless packaging proves impractical.

## Decisions and direction

- 2026-10-31: independent architecture review written (`docs/architect_opinion.md`); roadmap in `TODO.md` (Phase 0 P0 bugs + tests + packaging spike first).
- Target topology: one DSP process, in-process queues, optional FastAPI adapter; protocol v2 adds CRC-32, msg_id, fragment index/total, interleaver, optional repetition; keep RS + convolutional code until characterised.
- Do NOT: fix a channel plan, drop the known preamble, trade decode probability for airtime, raise baud rate just because it can be fixed.
- 2026-11-01: engineering skills configured — GitHub Issues via `gh` (repo `BimBim134/vibe-audioModem`), default triage labels, single-context domain docs (`GLOSSARY.md` + `docs/adr/` at root, not created yet). See `AGENTS.md` and `docs/agents/*.md`.

## Open items

- `gh` CLI on the owner's machine is too old for `gh label`; triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) are not created on GitHub yet.
- `GLOSSARY.md` and `docs/adr/` do not exist yet — next planned step is a `/grill-with-docs` session on the modem domain.
- Not yet done: tests, README, LICENSE, pyproject/lockfile, cleanup of tracked binaries.

## Pitfalls for agents

- Run from repo root (absolute `from src...` imports, relative log/WAV paths).
- `--test` mode needs one TX before RX (creates `test.wav`).
- `docs/doc.md` header says branch `gfsk-test`; the code is GMSK. Some research/diagram docs are stale (see `project-map.md`).
- GNU Radio is not guaranteed installed in the agent environment; DSP changes may be untestable there.
