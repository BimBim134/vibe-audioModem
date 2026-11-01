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
- 2026-11-01: engineering skills configured — GitHub Issues via `gh` (repo `BimBim134/vibe-audioModem`), default triage labels, single-context domain docs (`GLOSSARY.md` + `docs/adr/` at root); triage labels created on GitHub, `gh` upgraded to 2.103.3 via the official apt source. See `AGENTS.md` and `docs/agents/*.md`.

## Open items

- Le grilling de la refonte est terminé (2026-11-01) ; prochaine étape : étape 0 de `TODO.md`, après `/to-spec` et `/to-tickets` si on veut des tickets GitHub.
- Not yet done: tests, README, LICENSE, pyproject/lockfile, cleanup of tracked binaries.

## Pitfalls for agents

- Run from repo root (absolute `from src...` imports, relative log/WAV paths).
- `--test` mode needs one TX before RX (creates `test.wav`).
- `docs/doc.md` header says branch `gfsk-test`; the code is GMSK. Some research/diagram docs are stale (see `project-map.md`).
- GNU Radio is not guaranteed installed in the agent environment; DSP changes may be untestable there.

## Refonte — décisions du grilling (2026-11-01)

- **Rewrite complet, repartir de zéro.** Le code actuel est figé sous un commit tagué (`legacy-v0`, tag à créer) et sert uniquement de lecture. Il n'est PAS un oracle : on ne suppose pas que ses signaux sont valides.
- Aucun bug P0/P1/P2 n'est corrigé dans le code legacy : ils deviennent des exigences « à ne pas reproduire » pour le nouveau code.
- Ordre : (1) spike d'empaquetage (porte GNU Radio, quelques jours, Windows puis macOS) ; (2) banc de mesure (simulateur de canal + taux de réception correcte) ; (3) cœur DSP.
- Architecture : cœur DSP sans E/S (octets → échantillons, échantillons → messages), couches séparées pour carte son / WAV / UI.
- UI unique : UI web servie sur `127.0.0.1` (pas de TUI). Le contrôle à distance = même serveur + authentification.
- « Fini » : un radioamateur installe sans terminal, choisit un preset, envoie un texte court, il arrive intact (CRC) sur un second ordinateur, en boucle WAV puis sur une vraie chaîne audio.
- Modulation : paramètre du PHY (GMSK = GFSK à h = 0,5). Le GFSK à h variable (démodulateur écrit à la main) est un candidat testé après le banc, pas avant.
- Canal cible v1 : audio SSB 300–2700 Hz. Objectif produit : décoder au plus près du plancher de bruit ; un message lent mais qui arrive vaut mieux qu'aucun message.
- KPI = **Success threshold** (SNR dans 2 500 Hz de bande de bruit pour ≥ 95 % de messages corrects). Vocabulaire fixé dans `GLOSSARY.md` (Message, Transmission, Frame, Fragment, Signal, PHY profile, Preset) ; ne plus employer « paquet », « chunk », « porteuse », « piste ».
- Famille de modulation ouverte : le banc de mesure tranche (GFSK bas débit, M-FSK non cohérent, étalement…). Contrainte forte : **bande très réduite (~200 Hz ou moins par signal)** pour que plusieurs utilisateurs partagent la même bande, à la manière de FT8 ; Olivia jugé trop large.
- Taille max d'un message dépend du preset ; durée affichée avant envoi ; plafond 30 min conservé.
- v1 : un seul signal décodé à la fois, à fréquence audio inconnue (recherche temps × fréquence). Plusieurs signaux simultanés = étape ultérieure.
- Budget de bande : **100 Hz par signal par défaut** ; presets « portée maximale » (plus étroit) et « rapide » (plus large), valeurs finales fixées par le banc.
- Le logiciel doit fonctionner **sans internet** (pas de dépendance à NTP). Synchronisation temporelle : voir la décision du tour 5 si elle est notée plus bas.
- Codes correcteurs candidats : LDPC (décision souple) ET turbocodes, comparés au banc ; tous deux alimentés en LLR.
- Décidé : **abandon de GNU Radio** dans le nouveau code (cœur NumPy/SciPy, audio via `sounddevice`) — voir `docs/adr/0002-*`. Le spike d'empaquetage porte donc sur Python + NumPy + sounddevice + serveur web local.
- Décidé : **pas de grille horaire UTC** ; début de transmission libre, détecté par corrélation sur une séquence de synchronisation connue (temps × fréquence). Doit marcher sans internet.
- Décidé : 3 presets (portée maximale / standard ≈100 Hz par défaut / rapide). Codes candidats comparés au banc : LDPC, turbocode, convolutif longue contrainte (type WSPR), interface commune en LLR.
- ADR : `docs/adr/0001` (rewrite from scratch, legacy taggé), `0002` (cœur NumPy sans GNU Radio).
- Pile : Python 3.12, NumPy/SciPy, `sounddevice`, FastAPI/Uvicorn (127.0.0.1), pytest + ruff, `pyproject.toml` + lockfile. UI web = une page HTML + JS simple, canvas pour spectre/cascade, sans npm.
- Plateformes : Windows d'abord (test via GitHub Actions), puis macOS/Linux. Dev sous Linux.
- Licence : **GPL-3.0-only, confirmée par le propriétaire (2026-11-01).** Nouveau paquet : `src/vibemodem/` (`core/` sans E/S, `io/`, `app/`) + `bench/` pour le banc de mesure.
- Roadmap : `TODO.md` réécrit (9 étapes 0–8 avec critères de fin). `TODO.md` = haut niveau ; le détail = tickets GitHub via `/to-spec` puis `/to-tickets`.
- Matériel de test réel : deux ordinateurs + câble audio ; ensuite haut-parleur/micro ; ensuite deux radios + cartes son. Le récepteur garde l'audio brut et des indicateurs de performance à chaque réception pour rejouer et affiner au banc.
