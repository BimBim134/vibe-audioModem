# Vibe AudioModem

A one-way, weak-signal data modem for radio amateurs. It sends short messages through an audio channel (typically the audio passband of an SSB radio) and aims to decode them as close to the noise floor as possible, in a narrow band, with no return channel.

> **Status:** rewrite in progress. See [`TODO.md`](TODO.md) for the roadmap, [`GLOSSARY.md`](GLOSSARY.md) for the vocabulary and [`docs/adr/`](docs/adr/) for the design decisions. The first prototype (GMSK on GNU Radio) is frozen under the git tag `legacy-v0` and is documented in [`docs/legacy/`](docs/legacy/).

## Set up (Linux, macOS, Windows)

You need [uv](https://docs.astral.sh/uv/) (it installs the right Python for you). From a fresh clone:

```bash
uv sync --locked --all-extras
```

## Check your work

Run these from the repository root. CI runs exactly the same commands on Linux, Windows and macOS.

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Layout

| Path | Role |
| :-- | :-- |
| `src/vibemodem/core/` | DSP core: Messages to audio samples and back. No devices, files or network. |
| `src/vibemodem/io/` | Audio layer: sound cards and WAV files. No DSP. |
| `src/vibemodem/app/` | Local application: loopback web server and interface. |
| `bench/` | Measurement bench: channel simulator and Success threshold tools. |
| `packaging/` | PyInstaller build and smoke test for the Windows and macOS artifacts. |
| `tests/` | Automated tests. |
| `docs/adr/` | Architecture decision records. |
| `docs/packaging/` | Packaging spike findings and the clean-machine check procedure. |
| `docs/legacy/` | Documentation of the frozen prototype (tag `legacy-v0`). |
| `docs/references/` | Papers and other background reading. |
| `docs/agents/` | Project memory and map for coding agents. |

## License

GPL-3.0 (`GPL-3.0-only`), confirmed by the project owner. See [`LICENSE`](LICENSE).
