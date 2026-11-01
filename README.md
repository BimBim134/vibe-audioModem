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

## Measure a modem

The bench sends random Messages through the channel simulator at a range of SNRs and reports the **Success threshold**: the lowest SNR (in a 2,500 Hz noise bandwidth) at which at least 95% of Messages arrive correctly. A candidate is a class with `modulate` and `demodulate` methods (see `src/vibemodem/core/modem.py`); name it as `package.module:ClassName`.

```bash
uv run python -m bench.threshold --modem bench.toy:ToyModem --snr-from -14 --snr-to -4 --trials 300 --seed 1 --out result.json
```

A real candidate does not know when or where its Signal is. Hide it at a random moment and audio frequency with:

```bash
uv run python -m bench.threshold --modem vibemodem.core.baseline:BaselineModem --snr-from -18 --snr-to -12 --snr-step 0.5 \
    --trials 300 --message-bytes 12 --max-lead-in-s 10 --tail-s 1 --freq-offset-from -1100 --freq-offset-to 1100 \
    --out baseline.json --html baseline.html
```

It prints the curve and the threshold and writes everything to `result.json`. The same seed gives the same file (it holds no date or commit on purpose).

Add `--html report.html` to also write a human-readable report (success-rate curve with 95% confidence bars, counts, threshold). To compare several candidates on one chart, ranked by threshold:

```bash
uv run python -m bench.report toy.json other.json --out compare.html
```

The report is a single offline HTML file (no script, no link), so it can be opened anywhere and kept as a CI artifact. It flags results measured on different terms (message length, channel, Preset) as not directly comparable.

Two companion commands: `python -m bench.speed --modem pkg.mod:Class` times how fast a candidate receives against real time, and `python -m bench.code_curves --code pkg.mod:Class` measures how often an error-correcting code alone loses a frame on white noise. Past results are kept in [`docs/measurements/`](docs/measurements/README.md).

How to read the result:

- A trial counts as received only if the candidate returns exactly the Message that was sent. A wrong Message handed over, even next to the right one, makes the trial fail and is counted in `false_receptions`.
- The threshold is the lowest tested SNR that reaches 95% *and* is not followed by a higher tested SNR that falls short. Its resolution is the `--snr-step` (1 dB by default).
- Near 95% the measured rate is only known to about 1/sqrt(trials), roughly 2% with 100 trials. Use more trials (300 or more) and a finer step around the threshold before comparing two candidates.
- The toy modem (`bench.toy:ToyModem`, coherent BPSK) validates the bench: its measured success rate must follow the textbook formula within 0.05 (see `tests/test_threshold.py`).

## Layout

| Path | Role |
| :-- | :-- |
| `src/vibemodem/core/` | DSP core: Messages to audio samples and back, and the `Modem` interface candidates implement. No devices, files or network. |
| `src/vibemodem/io/` | Audio layer: sound cards and WAV files. No DSP. |
| `src/vibemodem/app/` | Local application: loopback web server and interface. |
| `bench/` | Measurement bench: channel simulator, Success threshold command, and a toy modem that validates the bench. |
| `packaging/` | PyInstaller build and smoke test for the Windows and macOS artifacts. |
| `tests/` | Automated tests. |
| `docs/adr/` | Architecture decision records. |
| `docs/packaging/` | Packaging spike findings and the clean-machine check procedure. |
| `docs/legacy/` | Documentation of the frozen prototype (tag `legacy-v0`). |
| `docs/references/` | Papers and other background reading. |
| `docs/agents/` | Project memory and map for coding agents. |

## License

GPL-3.0 (`GPL-3.0-only`), confirmed by the project owner. See [`LICENSE`](LICENSE).
