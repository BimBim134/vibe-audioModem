# Vibe AudioModem

A one-way, weak-signal data modem for radio amateurs. It sends short messages through an audio channel (typically the audio passband of an SSB radio) and aims to decode them as close to the noise floor as possible, in a narrow band, with no return channel.

> **Status:** rewrite in progress. See [`TODO.md`](TODO.md) for the roadmap, [`GLOSSARY.md`](GLOSSARY.md) for the vocabulary and [`docs/adr/`](docs/adr/) for the design decisions. The previous GMSK/GNU Radio prototype is frozen under the git tag `legacy-v0`; its code is still in the tree (`src/audioModem`, `src/rx`, `src/tx`, `src/ui`, `src/misc`, `main.py`) for reference only and is not part of the new package.

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
| `tests/` | Automated tests. |

## License

GPL-3.0 (`GPL-3.0-only`), confirmed by the project owner. See [`LICENSE`](LICENSE).
