## Project context (read first)

- `docs/agents/memory.md`: portable project memory (owner preferences, decisions, open items). Update it there, not in `~/.claude`.
- `docs/agents/project-map.md`: concise map of the repository and runtime.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (BimBim134/vibe-audioModem), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
