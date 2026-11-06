# Vibe AudioModem: the developer's guide

This is the long read for a new contributor. After it you should know what the project is for, how a Message becomes sound and sound becomes a Message again, where each piece of that lives in the repository, how to run, test and measure everything, which decisions were made and why, and which traps have already cost somebody a day.

It is written for people. The short, dense notes kept for coding agents are in `docs/agents/` (`project-map.md` is a table of every file; `memory.md` is the project's logbook, in French, one entry per ticket and per surprise). When this guide and a file under `docs/agents/` disagree, the code wins, then the ADRs, then this guide.

All code, comments, tests and documentation are in English, except `docs/agents/memory.md` and the French conference report (`docs/measurements/project-report.html`).

## Contents

1. [What the project is](#1-what-the-project-is)
2. [Get started in ten minutes](#2-get-started-in-ten-minutes)
3. [The language of the project](#3-the-language-of-the-project)
4. [The repository at a glance](#4-the-repository-at-a-glance)
5. [From a Message to sound and back: the whole chain](#5-from-a-message-to-sound-and-back-the-whole-chain)
6. [The core, module by module](#6-the-core-module-by-module)
7. [The audio layer](#7-the-audio-layer)
8. [The application](#8-the-application)
9. [The bench: how we measure](#9-the-bench-how-we-measure)
10. [The tests](#10-the-tests)
11. [Continuous integration, packaging, releases](#11-continuous-integration-packaging-releases)
12. [What was measured and decided](#12-what-was-measured-and-decided)
13. [How we work](#13-how-we-work)
14. [Recipes](#14-recipes)
15. [Traps and lessons](#15-traps-and-lessons)
16. [Where the project stands and what is next](#16-where-the-project-stands-and-what-is-next)

---

## 1. What the project is

**A one-way, weak-signal data modem for radio amateurs.** A transmitting station turns a short text into audio; the audio goes through a radio (typically the 300 to 2,700 Hz audio passband of an SSB transceiver); a receiving station, hundreds or thousands of kilometres away, turns what it hears back into the text. The receiver can never ask the sender to repeat: there is **no return channel**. The goal is to decode as close to the noise floor as possible, in a narrow band, so that a modest station can be read where a voice or a classic data mode would not be.

Think of WSPR or FT8, with these differences: the user types free text (up to 4,335 bytes), the program is a local web page rather than a desktop toolkit, and the whole signal chain is a readable NumPy code base that can be measured, replayed and changed.

Four ideas explain most of the design:

- **Everything is measured against noise.** The unit of progress is the *Success threshold*: the lowest SNR (measured in a 2,500 Hz noise bandwidth, the usual reference for SSB) at which at least 95 % of Messages arrive exactly. A modem that does not move this number is not an improvement. The `bench/` package exists to produce it, reproducibly, from a seed.
- **A wrong Message is worse than no Message.** The error-correcting code used by default (a turbo code) never says "I do not know"; the only barrier against a wrong Message is the CRC-32 of the Frame. In all measurements so far (hundreds of thousands of Messages, 80 hours of pure noise) no wrong Message was ever accepted. Keep it that way, and keep counting.
- **A Frame stands alone.** A Message is cut into Fragments, each Fragment goes in its own Frame, and each Frame has its own Preamble. A fade or a burst of interference destroys only the Frames it hits; the receiver needs no state about what came before. This costs about 19 % of airtime and buys robustness and immunity to clock drift (ADR 0005).
- **Real recordings tune the decoder.** The application can keep the sound of everything it reads or fails to read; the bench can replay those files and check that the decoder still gives the same answers. Several real defects (clicks taken for Signals, a wrong frequency grid) were found and fixed that way.

### The one-paragraph history

The first prototype was GMSK at 200 baud on GNU Radio, with six processes and ZeroMQ buses. It worked in the lab and was hard to install, to test and to trust. It is frozen under the git tag `legacy-v0` and was never used as a reference (ADR 0001). The present code was written from zero in a new package, in NumPy and SciPy only (ADR 0002). The work was tracked in GitHub tickets under the specification issue #1 and came in this order: foundation and packaging spike, channel simulator, Success threshold bench, a baseline modem, then three alternative error-correcting codes compared on the bench (turbo won), the M-FSK waveform study, the three Presets, a local web application, kept receptions and replay, real-world trials (room, then a cable), and finally small features such as the Listening band.

### Current state in four lines

- Three Presets (`max-range`, `standard`, `fast`), all 8-FSK with an interleaved turbo code: thresholds on white noise of −22, −16 and −13 dB.
- A local web application (Python server on the loopback interface, plain HTML/CSS/JS page) that sends, listens, shows a spectrum and waterfall, and keeps receptions.
- A Windows build (PyInstaller zip) checked on a clean machine; a macOS build that CI makes but nobody has tested by hand.
- Open work: the field campaign, a possible Listening band study, the page reachable from the network (see [section 16](#16-where-the-project-stands-and-what-is-next)).

---

## 2. Get started in ten minutes

### What you need

- [`uv`](https://docs.astral.sh/uv/). It installs the right Python (3.12) and the locked dependencies; you do not install Python yourself.
- For the application with a real sound card: PortAudio, which the `sounddevice` package uses. It ships in the Windows and macOS wheels; on Linux you may need your distribution's `libportaudio2`.
- Git, and `gh` (the GitHub CLI) if you want to read or write tickets.

### Set up

```bash
git clone https://github.com/BimBim134/vibe-audioModem
cd vibe-audioModem
uv sync --locked --all-extras
```

### The three commands that CI runs

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The whole test suite is about 1,090 tests and takes about three and a half minutes on a desktop computer. For daily work run only the file you are changing, for example `uv run pytest tests/test_turbo.py -q`. Before you push, run everything.

`ruff` is the only linter and formatter (line length 100; rules E, F, I, UP, B). `uv run ruff format .` fixes formatting.

### Run the application

```bash
uv run python -m vibemodem.app
```

It starts a server on `127.0.0.1` (a free port) and opens your browser. Options: `--port N`, `--no-browser`, `--receptions-dir PATH` (where kept receptions go; the default depends on the platform). The page has a **Listen** button (needs an input device), a message field with **Send** (needs an output device), and a **Settings** dialog (Preset, devices, copies, the Listening band, stored receptions, Quit).

No sound card at hand? Two instances can talk through a fake cable in the tests (`FakeAudio.connect_to`), and the "self-test" endpoint (`/api/selftest`) runs the modem against itself.

### Send a Message to yourself without hardware

```python
from vibemodem.core.turbo_modem import TurboModem
from vibemodem.core.transmission import transmit, receive

modem = TurboModem(preset="fast")
audio = transmit(modem, b"hello, world", "fast", msg_id=1)   # float samples at 48 kHz
print(len(audio) / 48_000, "seconds of sound")
for message in receive(modem, audio).complete:
    print(message.message)                              # b'hello, world'
```

Add noise with the simulator:

```python
import numpy as np
from bench.channel import ChannelConfig, apply_channel

noisy = apply_channel(audio, ChannelConfig(snr_db=-10.0), seed=1,
                      signal_power=float(np.mean(audio**2)))
print([m.message for m in receive(modem, noisy).complete])
```

### Measure a modem

```bash
uv run python -m bench.threshold --modem vibemodem.core.turbo_modem:TurboModem \
    --preset fast --snr-from -16 --snr-to -10 --snr-step 1 --trials 100 \
    --message-bytes 12 --max-lead-in-s 10 --tail-s 1 \
    --freq-offset-from -1100 --freq-offset-to 1100 --out fast.json --html fast.html
```

It prints the success rate at each SNR and the Success threshold, and writes a JSON file and an HTML report. The same seed gives the same file. See [section 9](#9-the-bench-how-we-measure).

### Where to start reading the code

In this order, about two hours: `core/frame.py` (50 lines), `core/message.py`, `core/presets.py`, `core/mfsk.py` (the waveform and the Preamble search), `core/coded_modem.py` and `core/coded_mfsk.py` (the modem), `core/transmission.py`, then `app/service.py` and `app/receiver.py`. Read the tests next to each module: they are written as specifications.

---

## 3. The language of the project

`GLOSSARY.md` at the repository root is the dictionary. Every capitalised word in code, tests, tickets and docs is defined there, and each entry lists words to *avoid* ("packet", "payload", "chunk"...). Use the words, in code identifiers too. The essentials:

| Term | Meaning |
| :-- | :-- |
| **Message** | The text or bytes a user sends, before any coding. |
| **Fragment** | The slice of a Message carried by one Frame: up to 17 bytes plus a 3-byte header. |
| **Frame** | The smallest unit on the air that the receiver can decode and verify alone; carries one Fragment and a CRC-32. |
| **Transmission** | One continuous emission of a Message: its Frames one after another (and the copies, if asked). |
| **Copy** | A further sending of all Fragments inside the same Transmission, each copy starting at another Fragment. |
| **Message identifier** | The byte in each Fragment that tells which Message it belongs to. |
| **Incomplete Message** | A Message of which only some Fragments were checked; reported as such, never as a short Message. |
| **Preamble** | The 32 symbols at the start of each Frame, known to the receiver, used to find the Frame in time and in frequency. |
| **Signal** | Sound the receiver recognises as a Frame, by its Preamble. |
| **Undecoded Signal** | A Signal found whole whose Frame could not be read (code or CRC refused it). Reported with frequency and score so that a heard-but-lost Transmission is not taken for silence. |
| **Lowest tone** | The lowest audio frequency of a Transmission; the operator chooses it per Message. |
| **Preset** | One of three named PHY profiles: `max-range`, `standard`, `fast`. |
| **PHY profile** | Number of tones, symbol duration and interleaving of a Preset. |
| **Success threshold** | Lowest SNR (2,500 Hz reference) at which at least 95 % of Messages arrive, with every higher tested SNR also passing. |
| **Code** | An error-correcting code (the `Code` interface): bits to coded bits, soft values to bits. |
| **Soft value** | A number per bit whose sign says which bit and whose size says how sure; positive means 0 in this project. |
| **Interleaver** | The permutation that spreads the coded bits over the whole Transmission so a fade hurts them evenly. |
| **Occupied bandwidth** | Width of the band holding the Signal's energy, measured at −20 dB. |
| **Candidate** | A modem under test; any class with `modulate` and `demodulate`. |
| **Reception** | One Message found in audio, with its SNR, frequency offset, sync score and start. |
| **Kept reception** | A WAV and a JSON the application saved of a Frame it read or a Signal it lost. |
| **Listening band** | The audio band inside which the receiver looks for Signals; a temporary feature. |

Two conventions on SNR: **an SNR in this project is always quoted in a 2,500 Hz noise bandwidth** (`NOISE_BANDWIDTH_HZ`), and the SNR of a Signal means signal power over noise power in that bandwidth. A Signal at −22 dB is far below what the ear can pick out.

---

## 4. The repository at a glance

```
vibe-audioModem/
├── src/vibemodem/
│   ├── core/       the DSP: Messages to samples and back. Pure NumPy/SciPy.
│   ├── io/         sound cards and WAV files. No DSP.
│   └── app/        the local application: service, receiver, store, API, web page.
├── bench/          measurement bench, simulator, trials, report builders (not shipped)
├── tests/          pytest; about a thousand tests
├── packaging/      PyInstaller spec, entry point, smoke test
├── docs/
│   ├── adr/            architecture decision records (read these)
│   ├── measurements/   every measurement kept: JSON, HTML reports, trial results
│   ├── packaging/      the packaging spike and the clean-machine procedure
│   ├── agents/         notes for coding agents (project map, memory)
│   └── for-humans/     this guide
├── .github/workflows/  ci.yml, package.yml
├── GLOSSARY.md  README.md  AGENTS.md  LICENSE (GPL-3.0-only)
└── pyproject.toml  uv.lock  .python-version
```

### Three layers, and the rule between them

```
            ┌────────────────────────────────────────────┐
            │ app/   service, receiver, store, API, page │  ← uses core and io
            └───────────────┬────────────────────────────┘
                            │
        ┌───────────────────┴───────────┐
        │ io/  audio, wav, levels       │   (no DSP)
        └───────────────────────────────┘

        core/  (DSP)   imports nothing from io, app, bench, sounddevice, fastapi, uvicorn or socket
```

The core takes bytes in and gives float arrays out, and the reverse. It never touches a device, a file or the network, so it can be tested, measured and replayed anywhere. **A test enforces this** (`tests/test_layers.py` parses every core file and fails on a forbidden import). `bench/` may import the core and the app; the core never imports the bench.

### Dependencies

Runtime: `numpy`, `scipy`, `sounddevice`, `fastapi`, `uvicorn`. Development: `pytest`, `ruff`, `httpx` (the FastAPI test client). Packaging: `pyinstaller`. That is all; do not add a dependency without a reason that fits an ADR-sized paragraph.

### Size

About 4,100 lines of Python in `core` (2,000), `io` (500) and `app` (1,650), plus 870 lines of page; 2,800 lines in `bench`; 6,700 lines of tests. The code base is small enough to read in full.

---

## 5. From a Message to sound and back: the whole chain

This section follows one Message, in the `fast` Preset, from the text box to the loudspeaker and from the microphone to the screen. Numbers for the other Presets are in the table at the end.

### 5.1 Sending

```
 text ──► Fragments ──► Frame ──► code ──► interleave ──► symbols ──► tones ──► audio
 "hello"   (≤17 B each)  (25 B)   (412 bits)  (spread)     (3 bits)     (8-FSK)   (48 kHz)
```

1. **Split into Fragments** (`core/message.py: split`). The text is encoded as UTF-8 bytes and cut into pieces of at most 17 bytes. Each piece gets a 3-byte header: the **Message identifier** (a random byte, different from the last one), the **index** of the Fragment and the **total** number of Fragments. A Message is at most 255 Fragments, 4,335 bytes. Only the last Fragment may be short.
2. **Make a Frame** (`core/frame.py: encode_frame`). A Fragment (header plus payload, at most 20 bytes) becomes a fixed 25-byte Frame: a length byte, the body padded with zeros to 20 bytes, and a CRC-32 over those 21 bytes. The 200 bits are then **whitened** by XOR with a fixed pseudo-random sequence, so long runs of zero padding do not become long runs of one tone. Every Frame is the same size, so a receiver that has found a Frame's start knows exactly how many symbols follow.
3. **Encode** (`core/turbo.py`). The 200 information bits become 412 coded bits (rate about 1/2) with the turbo code.
4. **Interleave** (`core/coded_modem.py: _send_order`). The coded bits are sent in a scrambled order (position *j* carries bit *j × stride* modulo 412, with a stride close to a golden-ratio share of 412). Bits that are neighbours on the air are far apart in the code word, so a fade that kills a stretch of the Frame damages the code evenly instead of destroying one corner of it.
5. **Group into symbols** (`core/coded_mfsk.py`). The 8 tones carry 3 bits each: 412 bits make 138 data symbols (the last one padded). A 32-symbol **Preamble** (a fixed pseudo-random tone sequence) goes first: 170 symbols per Frame.
6. **Synthesize** (`core/mfsk.py: Waveform.synthesize`). Each symbol is a sine at `lowest_tone + tone_number × spacing`, where spacing = 1 / symbol duration; the phase is continuous from one symbol to the next, which keeps the occupied band narrow. Amplitude is 0.5 of full scale. The default lowest tone is 1,450 Hz; the operator can move it within the range that keeps the whole Signal in 300 to 2,700 Hz.
7. **String the Frames** (`core/transmission.py: transmit`). One Frame per Fragment, one after the other, each with its own Preamble. With `copies` > 1 the whole set is sent again, each copy starting at another Fragment (copy *k* of *n* starts at Fragment *round(k × total / n)*), so one run of lost Frames does not meet the same Fragments each time. At most 8 copies; a Transmission may not exceed 30 minutes or 255 Fragments (`MessageTooLong` carries advice: shorter Message, fewer copies, a faster Preset).
8. **Play** (`io/audio.py`, driven by `app/service.py`). The samples go to the sound card on a thread of their own; the page can cancel.

### 5.2 Receiving

```
 audio ──► spectrogram ──► Preamble search ──► refine ──► tone energies ──► soft bits
                              (time × freq)      (finer)    (per symbol)     (per bit)
   ──► turbo decoder ──► CRC ──► Fragment ──► Reassembler ──► Message
```

1. **Spectrogram** (`mfsk.py: _spectrogram`). An FFT twice as long as a symbol, every quarter symbol, restricted to the search band (300 to 2,700 Hz). Bins are half a tone spacing apart.
2. **Noise per frequency.** For each frequency the noise level is read from a low quantile of all the windows of the recording (below the ones where a tone of the Signal sits: with 8 tones a given frequency carries a tone only 1/8 of the time, so the median is a fair noise estimate; with 2 or 4 tones a lower quantile is used). The energy is divided by it and **capped** at `SYMBOL_MATCH_CAP` (16): one loud click must not outweigh 32 weak symbols.
3. **Preamble match** (`find_signals`). For every start time and every lowest-tone frequency, add up the relative energy at the tone the Preamble has at each of its 32 symbols, minus the average of the other tones at that moment (a Preamble puts its energy on one tone; a click or a burst on all of them). In noise alone the sum has a known spread; the **score** is the match expressed in standard deviations. The best places above `min_score` = 7 are candidates (at most as many as Frames could fill the recording, plus two). Noise alone gives 7 to 7.7; a Signal at the threshold of any Preset gives 15 or more. A Signal is only *reported as lost* above `UNDECODED_MIN_SCORE` = 10.
4. **Refine** (`refine`). The search grid is a quarter symbol in time and half a tone spacing in frequency, which loses energy; nearby starts (eighths of a hop) and frequencies (eighths of a spacing) are tried and the one with the most Preamble energy is kept.
5. **Tone energies.** For each data symbol, the energy at each of the 8 tone frequencies, by correlation with complex sinusoids (a matched filter per tone).
6. **Soft bits** (`coded_mfsk.py: _soft_bits`). The noise level is read as a quantile of all the energies (below the median, where the quiet tones are); the energies are divided by it; each of the 3 bits of a symbol gets the soft value *max over tones that mean 0 minus max over tones that mean 1* (max-log). Positive means 0.
7. **Undo the interleaver and decode** (`turbo.py`). Up to 8 rounds of two max-log-MAP decoders trading extrinsic opinions (scaled by 0.75); then hard decisions.
8. **Check** (`frame.py: decode_frame`). Un-whiten, check the length byte and the CRC-32. If the CRC fails, the Frame is an **Undecoded Signal** (if its score is high enough to be worth reporting).
9. **Fragment and Reassembler** (`message.py`). A Frame's body is parsed (`Fragment.unpack` refuses nonsense). The `Reassembler` collects Fragments by (Message identifier, total); when all have arrived it returns the Message once, whatever the order and however many copies were heard; at the end of a recording `finish` reports what is still open as an `Incomplete` Message with the indexes that are missing.
10. **Metrics.** Each Reception carries an SNR estimate (mean sent-tone energy over noise, minus one, converted to the 2,500 Hz reference), the frequency offset from the nominal 1,450 Hz, the sync score and the start sample.

### 5.3 The numbers of the three Presets

| | max-range | standard | fast |
| :-- | :-- | :-- | :-- |
| Symbol duration | 320 ms | 80 ms | 40 ms |
| Tone spacing (1 / symbol) | 3.1 Hz | 12.5 Hz | 25 Hz |
| From lowest to highest tone (7 spacings) | 21.9 Hz | 87.5 Hz | 175 Hz |
| Occupied band at −20 dB | 29 Hz | 107 Hz | 212 Hz |
| One Frame (170 symbols) | 54.4 s | 13.6 s | 6.8 s |
| Longest Message in 30 minutes | 561 bytes (33 Fragments) | 2,244 bytes (132) | 4,335 bytes (255) |
| Success threshold, white noise | −22 dB | −16 dB | −13 dB |
| Success threshold, hf-fading | −16 dB | −8 dB | 95 % not reached (90 % at 0 dB) |

Every halving of the symbol duration costs about 3 dB of range: the gain of a longer symbol is purely its energy.

### 5.4 Why the receiver is built this way

- **Non-coherent 8-FSK.** No carrier phase to track on a channel whose sound cards and radios drift; with equal energy, 8 and 16 tones are the best of 2, 4, 8, 16, and 8 keeps the demodulator small. A coherent receiver and GFSK were measured and dropped (the GFSK candidate was at least 2.5 dB behind and was removed in commit `a891dee`).
- **A search over every time and frequency.** Nobody tells the receiver when or where the Signal is. The search is the most expensive part of decoding, and the live receiver repeats it on a sliding window (see [8.4](#84-the-receiver-and-its-sliding-window)).
- **The code's soft values.** Throwing away how sure each tone decision was would cost over 2 dB; the whole chain keeps it.

---

## 6. The core, module by module

All in `src/vibemodem/core/`. Nothing here imports `io`, `app`, `bench`, `sounddevice`, `fastapi`, `uvicorn` or `socket`.

### 6.1 `modem.py`: the interface

- `Modem` (a `Protocol`): `modulate(message, preset) -> samples` and `demodulate(samples) -> [Reception]`. Any class with these two methods can be put on the bench. The bench `ToyModem`, the test stand-ins in `tests/fake_modems.py` and `TurboModem` are all Modems.
- `Reception`: `message` plus optional `snr_db`, `frequency_offset_hz`, `sync_score`, `start_sample`.
- `Detection` (`start_sample`, `frequency_hz`, `sync_score`) and `Report` (`receptions`, `undecoded`, `arriving`): what `demodulate_report` of the coded modems gives. *Undecoded*: found whole, but the code or CRC refused it. *Arriving*: Preamble heard, Frame not whole yet (the live receiver uses this to show "receiving...").

### 6.2 `frame.py`

`encode_frame(message) -> bits` and `decode_frame(bits) -> bytes | None` (see 5.1). Constants: `MESSAGE_CAPACITY = 20`, `FRAME_BYTES = 25`, `FRAME_BITS = 200`. `pseudo_random_bits(count, state)` is a 15-bit LFSR (x¹⁵ + x¹⁴ + 1) used for whitening and for the Preamble tones. The CRC-32 is the only guard against a wrong Message: do not weaken it.

### 6.3 `message.py`

`Fragment(msg_id, index, total, payload)` with `pack` and `unpack`; `split`, `fragment_count`, `random_message_id`; `Complete` and `Incomplete` (with `missing` and `runs()`, the contiguous stretches that were heard); `Reassembler` with `add`, `pending`, `finish`. It remembers the last 64 finished Messages to ignore their later copies and keeps at most 64 Messages open. A Message is known by its identifier **and** its total, so two Messages that reuse an identifier with different lengths do not mix.

### 6.4 `presets.py`

`PhyProfile(tones, symbol_ms, interleave)`, `PRESETS`, `DEFAULT_PRESET = "standard"`, `profile(name)` (a `ValueError` listing the Presets for an unknown name), `frequency_range_hz(preset)` (where the lowest tone may be), `minimum_band_hz(preset)` (from lowest to highest tone: the narrowest Listening band that holds the Preset).

### 6.5 `mfsk.py`: the waveform and the search

`Waveform(tones, symbol_seconds, first_tone_hz)` is a frozen dataclass; it validates that the symbol is a whole number of samples and a multiple of 32 (the search hops by a quarter symbol and refines by an eighth of that). Cached properties give `spacing_hz`, `samples_per_symbol`, `preamble_tones`, `bit_weights`, `zero_tones`, `first_tone_range_hz`, `occupied_hz`. Methods: `synthesize`, `tone_energies`, `find_signals(samples, max_candidates, min_score, band_hz)` and `refine`. `Candidate(start_sample, first_tone_hz, score, inside_band)`.

Constants worth knowing: `SAMPLE_RATE = 48_000`, `FIRST_TONE_HZ = 1450`, `SEARCH_BAND_HZ = (300, 2700)`, `PREAMBLE_SYMBOLS = 32`, `NOISE_FLOOR_RATIO = 1e-3` (a receiver never sees less noise than a thousandth of its loudest signal: without it, a noiseless recording made the faintest leakage look like a Preamble), `SYMBOL_MATCH_CAP = 16`.

`band_hz` (the Listening band) makes `find_signals` mark candidates that are not entirely inside the band with `inside_band=False`. They are still returned, so that their side peaks are not mistaken for Signals, but they do not count in `max_candidates` and are not decoded.

### 6.6 The codes: `code.py` and its implementations

`Code` is the interface: `info_bits`, `coded_bits`, `parameters` (plain data recorded in result files), `encode(bits)`, `decode(soft values) -> bits | None`. Helpers `as_vector` and `as_bits` validate inputs. `tests/test_codes.py` runs the same contract against every implementation.

| Module | Code | Notes |
| :-- | :-- | :-- |
| `turbo.py` | **Turbo** (the default) | Two recursive 8-state encoders (4G polynomials), spread interleaver (gap 8 for 200 bits, built deterministically), half the parity kept, tails sent: 412 coded bits. Max-log-MAP, extrinsic scaling 0.75, at most 8 iterations. Never returns `None`. A test pins a digest of its parameters: changing the interleaver changes the protocol. |
| `ldpc.py` | Repeat-accumulate LDPC | 200 info bits, 400 coded, rules placed by PEG (deterministic), normalised min-sum 0.8, at most 50 iterations. Returns `None` when it has nothing to decode or its rules are not satisfied (see `decode`). Faster than turbo (about 203× real time vs 113×). |
| `convolutional.py` | Rate 1/2, constraint length 7 | Soft Viterbi. The baseline. |
| `long_convolutional.py` | The WSPR code (constraint length 32, rate 1/2) | Fano sequential decoder in pure Python, gives up after 1,000 steps per bit. 462 coded bits (a Transmission 9 % longer). |

The modem classes that attach a code to the waveform are one-liners: `turbo_modem.TurboModem`, `ldpc_modem.LdpcModem`, `long_convolutional_modem.LongConvolutionalModem`, `baseline.BaselineModem`. Only the turbo one ships in the application. The others stay, tested and measurable, as candidates to revisit (ADR 0003); none was removed.

### 6.7 `coded_modem.py` and `coded_mfsk.py`: the modem

`CodedModem` is what coded modems share: the Frame, the send order (interleaving with a stride per copy, repetition `repetitions` times), and the **reception loop** `demodulate_report`: find Signals, skip those outside the Listening band, decode each, merge receptions of the same Message (keeping the one with the best score), and sift the undecoded ones from the side peaks of a Preamble. Notable details:

- A recording may be at most `MAX_RECORDING_SECONDS` = 600 s long (the search keeps arrays of windows × frequencies; this bounds the memory). Decode longer files in overlapping chunks; the overlap must exceed one Frame.
- `_without_side_peaks` removes lost Signals that lie inside a Frame that was read, inside a stronger lost Signal, or inside a stronger one that does not fit yet. Without it every Frame produced a ghost "lost" Signal.
- `search_band_hz` (default `None`) is the Listening band; the receiver sets it before each decoding pass.

`CodedMfskModem` plugs in the waveform: `_audio` (Preamble tones + data tones), `_find` (search then refine), `_decode` (tone energies → soft bits → code → CRC) and the SNR estimate. `TurboModem(preset="fast")` builds a modem for **one** Preset; `modulate` refuses another name. Any setting given by hand (`tones=`, `symbol_ms=`, `interleave=`) overrides the profile; the bench sweeps use that.

### 6.8 `transmission.py`

`transmit(modem, message, preset, *, msg_id, copies=1)`, `receive(modem, samples, reassembler=None)` returning `Received(complete, incomplete)`, `frame_seconds`, `airtime_seconds`, `max_message_bytes`, `explain_refusal`, `check_copies`, `MessageTooLong`, and the limits `MAX_COPIES = 8` and `MAX_TRANSMISSION_SECONDS = 1800`. `transmit` builds the first Frame, checks that the whole would fit, and only then builds the rest. A long Transmission can be received in several recordings by passing the same `Reassembler` to each `receive`.

### 6.9 `spectrum.py`

`spectrum_row(block)`: the power of an audio block in 480 bins of 5 Hz from 300 to 2,700 Hz, in dB, for the waterfall (−120 for silence). `BAND_HZ` and `BIN_HZ` tell the page how to place a row.

---

## 7. The audio layer

`src/vibemodem/io/`. No DSP here: mono float samples at 48 kHz in and out.

### 7.1 `audio.py`

- **`Audio`** (a `Protocol`): `list_devices()`, `play(samples, device)`, `record(seconds, device)`, `listen(device, block_seconds, capacity) -> InputBlocks`, `stop()`. The application and the bench talk to this, never to a sound library.
- **`SoundCard`**: the real thing, through `sounddevice` (PortAudio). It imports the library lazily, so a computer without it gets `AudioLibraryUnavailableError` at the first use instead of a crash at import. `UnsupportedAudioError` means the device cannot do 48 kHz mono; `NoAudioDeviceError` means there is none. `play` uses a callback stream of its own, and `stop()` only sets a flag the callback looks at: calling `sd.stop()` from another thread once corrupted PortAudio's memory and killed the application.
- **`find_device(devices, wanted, direction)`**: a device is chosen by number or by part of its name; several matches are refused.
- **`InputBlocks`**: what `listen` returns. A bounded queue of float32 blocks. If whoever iterates is too slow the **oldest block is dropped** and counted in `dropped`; the sound card's own overruns are added with `note_lost`. It is iterable, a context manager, and `close()` ends the iteration after the queued blocks. The receiver gives it a capacity of 300 seconds of sound.
- **`FakeAudio`**: scripted input, remembers everything played, `loopback=True` hears its own output, and `connect_to(other)` wires one instance's output to another's input (a cable). Most application tests use it, so most tests need no sound hardware.

### 7.2 `wav.py` and `levels.py`

`read_wav` reads 8/16/24/32-bit integer and float WAV files (stereo is averaged; only 48 kHz is accepted, otherwise `WavError`); `write_wav` writes 16-bit mono and refuses audio beyond full scale. `check_level(samples)` returns a `LevelReport(peak, rms_dbfs, clipping, too_low)` with plain-language `messages`: clipping means 0.1 % of samples reach 99 % of full scale, too low means under −50 dBFS RMS (a radio with its band noise gives −40 to −20 dBFS).

### 7.3 Hand-testing a real sound card

`bench/audio_check.py` is a small command for a human at the keyboard: `python -m bench.audio_check --list`, `--input X --level 3` (show the input level for 3 seconds), or `--input X --output Y` (play a Transmission and receive it).

---

## 8. The application

`src/vibemodem/app/`. A single process: a **service** that knows how to send and listen, a **receiver** thread, a **store** for kept receptions, a small **HTTP API** and a **web page**, started by `main.py`.

```
 browser ──HTTP──► api.py ──► service.py ──┬─► sends: transmit() ─► audio.play (thread)
 (page)             (FastAPI)  (ModemService)│
                                            └─► receiver.py ──► decode every 2 s ──► heard.py
                                                  │  (thread)                       conversation.py
                                                  └─► keeper.py ─► store.py (WAV + JSON)
```

### 8.1 `main.py`

`main(argv)` builds the `ReceptionStore`, the `ModemService(SoundCard(), store=store)` and a uvicorn server **bound to `127.0.0.1` only**, opens the browser once the server is up, and runs. `free_port()`, `make_server(service, port)`. In the packaged, windowed build there is no console, so `_ensure_std_streams` replaces the missing `stdout`/`stderr` (some libraries crash on `None`). `python -m vibemodem.app` and the PyInstaller entry point both land here.

### 8.2 `service.py`: `ModemService`

The one object the API talks to. It holds a lock (`RLock`) and no HTTP.

- **Settings**: `Settings(preset, input_device, output_device)`. `apply_settings(**changes)` validates **all or nothing** (`SettingsError` lists every problem) and is refused while sending or listening (`BusyError`). Devices are checked against the sound card outside the lock because that call can be slow. Changing the Preset is refused if the Listening band no longer holds it.
- **Sending**: `send(text, copies, frequency_hz)` builds the whole Transmission first (so a Message that is too long is refused **before any sound**), then plays it on its own thread. `cancel()` repeats `audio.stop()` until the thread ends. `estimate(...)` says what a send would take (Fragments, airtime, longest Message, the refusal it would give, the allowed frequency range) without making a sound. Modems for sending are cached per (Preset, frequency), at most 8 (they are heavy).
- **Listening**: `start_listening()`, `stop_listening()` delegate to the `Receiver`. `received()`, `undecoded()`, `conversation()`, `spectrum(since)` expose what it saw.
- **Listening band**: `set_search_band(low, high)` / `search_band()`: 300 to 2,700 Hz, low below high, at least `minimum_band_hz(preset)` wide; applied at the next decoding pass, also while listening; global; not saved. `(None, None)` clears it.
- **Storage**: `storage()`, `set_storage(keep, limit_mb)` (together or not at all; allowed while listening), `clear_receptions()`.
- **Status**: `status()` is what the page polls: `sending`, `listening`, `settings`, `search_band`, counts of Messages received and incomplete, `blocks_lost`, `last_error`.
- **`close()`** is idempotent and stops everything; the server calls it on shutdown.

### 8.3 `api.py`: the HTTP interface

`create_app(service, on_quit=...)` returns a FastAPI app. Errors map to status codes: `SettingsError` and `MessageTooLong` → 422; `BusyError` and `Cancelled` → 409; `AudioError` → 503.

| Endpoint | What |
| :-- | :-- |
| `GET /`, `GET /assets/{name}` | The page (`index.html`, `style.css`, `script.js`), read at each request with `Cache-Control: no-cache`; `{name}` is a file directly in the assets folder, nothing else. |
| `GET /api/health`, `GET /api/status`, `GET /api/devices` | Liveness; the polled state; audio devices (or why the library is unavailable). |
| `GET/POST /api/settings` | Preset and devices (`SettingsRequest`, extra fields forbidden). |
| `POST /api/estimate`, `POST /api/send`, `POST /api/cancel` | Plan, send, cancel. |
| `POST /api/listen/start`, `/api/listen/stop` | Listening. |
| `GET/POST /api/band` | The Listening band: `low_hz`, `high_hz` (both null clears). |
| `GET/POST /api/storage`, `POST /api/storage/clear` | Keep receptions, the limit in MB, delete all. The **folder** is not settable from the page (ADR 0006). |
| `GET /api/received`, `/api/conversation`, `/api/spectrum?since=N` | What was heard; sent and heard in one list ordered by time; waterfall rows since a counter. |
| `GET /api/selftest`, `POST /api/quit` | The modem against itself; stop the server. |

**Security model.** The server listens on loopback only, and a middleware refuses a `Host` header that is not a loopback name (against DNS rebinding, 421) and an `Origin` that is not the page's own (403): a web page open in the same browser must not be able to make this computer transmit. A request with no `Origin` is another program on the same computer, which is trusted. Making the page reachable from the network is ticket #29 and must rethink all of this (authentication, HTTPS).

### 8.4 The receiver and its sliding window

`receiver.py: Receiver(audio, make_modem, ..., store=None)`. `start(preset, device)` opens the input (`audio.listen` with a 300-second queue of 0.5-second blocks) and starts a thread running `_listen`:

1. For each 0.5 s block: draw a waterfall row (`spectrum_row`), append it to a **window**, and drop old blocks so the window holds one Frame plus 12 seconds (about 19 s in fast, 26 s in standard, 66 s in max-range).
2. Every **2 seconds** of sound (`DECODE_EVERY_SECONDS`), decode the whole window with `modem.demodulate_report`, after setting `modem.search_band_hz` from the current Listening band.
3. Hand the receptions to the **`Reassembler`** (one for the whole listening, so Fragments arriving in different passes still meet), remember the quality of each Fragment (the clearest sighting counts), list Undecoded Signals once, and show "arriving" Signals only if the same one was seen in two passes in a row.
4. When the listening is stopped, decode once more with `final=True` (nothing more is coming to complete a margin) within `STOP_SECONDS` = 120.

Subtleties that bit people before: a Frame is seen by many consecutive windows, so everything must be **idempotent** (the Reassembler delivers a Message once; `heard.alike()` with a `Tolerance` of two symbols in time and one tone spacing in frequency decides that two sightings are the same Signal); a Frame **cut by the start of the window** has lost part of its Preamble, so it is not judged as lost (it was judged whole in an earlier pass); the **side peaks** of a Preamble sit a few tones from the real one and must not be reported as Signals; times are by the **audio clock** (start of the listening plus samples heard), not the wall clock. The window is also why a long Transmission works: only one Frame has to fit.

If the decoder falls more than 300 seconds behind the sound card, the oldest blocks are dropped and counted in `blocks_lost`, which the page shows in orange. On the machines tried so far a pass takes well under a second at max-range.

### 8.5 `heard.py`, `conversation.py`

`Heard` (a Message heard whole or in part, with mean SNR of its Fragments, the frequency of its lowest tone, the offset, the lowest sync score), `Undecoded`, `SpectrumRows` (a counter-based ring of 120 rows), `Quality`, `summarize`, `Tolerance`, `alike`. `conversation.py: build_conversation(sent, heard, lost, arriving)` makes the single time-ordered list the page shows: each item has a `kind` (`sent`, `received`, `incomplete`, `lost`, `arriving`), a stable `id` and a time `at`; `SentEntry` follows a Message sent from *sending* to *sent*, *cancelled* or *failed*.

### 8.6 Kept receptions: `keeper.py`, `store.py` (ADR 0006)

When the operator switches **Keep** on (off by default), the `Keeper` saves each Frame read and each Signal lost **once**, as a 16-bit mono 48 kHz WAV (the Frame with 3 s of sound on each side) and a JSON of the same name (schema version, Preset, the modem that replays it, frequency, SNR, sync score, Message identifier, index, total, the body in hex, the start sample). The piece is cut **on the search grid of its window** so that replaying it searches at the same times and reads the same figures.

`ReceptionStore(directory, max_bytes)` writes the WAV then the JSON **last, by renaming**, so a reception without its JSON is unfinished and is cleaned away. Names begin with the UTC time and end with a counter (`20261105-224432-737-0015.json`), so oldest-first is the order of the names, and **the counter starts at 0000 with each run of the application**. Only regular files named like ours are counted, read or deleted. **When the limit (200 MB by default, 10 MB to 100 GB) is passed, the oldest receptions are deleted first, silently.** Remember this the day a long trial "loses" its first Messages: that is [section 15.1](#151-the-storage-limit-silently-deletes-the-oldest-receptions). `default_directory()`: `XDG` on Linux, `Application Support` on macOS, `LOCALAPPDATA` on Windows.

### 8.7 The page: `assets/`

`index.html`, `style.css`, `script.js`, served as plain files: no build step, no framework, no network access, works offline. Two columns: charts on the left (spectrum, waterfall, frequency axis), the conversation as bubbles and the composer on the right; a top bar (state, Listen/Stop, Settings) and a Settings dialog (General: devices, Preset, repetitions; Advanced: Listening band, stored receptions, Quit).

- **Four colours only**, as RGB triples at the top of `style.css`: `--bg`, `--grey`, `--text`, `--accent`. The script reads them for the canvases. The waterfall's fixed dB range (`FLOOR_DB`, `CEILING_DB`) and its colour ramp (`RAMP`) are in the script.
- `script.js` polls `/api/status` and `/api/conversation` (`refresh`), the spectrum rows (`refreshSpectrum`) and `/api/storage`; `act(promise, then, where)` runs an action and shows its error where the person is looking. `confirmed(button, ...)` makes a destructive button ask a second click. A click on a chart places the frequency of the next Message.
- Top-level `const`/`let` names in `script.js` share one scope: a duplicate name is a `SyntaxError` that **kills the whole page** (it happened). Reload the page and read the browser console after touching it.
- There is no JavaScript test: the API behind it is tested, and the page is checked by looking at it.

---

## 9. The bench: how we measure

`bench/` is not shipped. It is where the project earns its right to claim anything. The rule: **every number in a ticket or a document must be reproducible from a command and a seed**.

### 9.1 The simulator: `channel.py`

`apply_channel(samples, ChannelConfig, seed, signal_power=None)` degrades audio like a radio link. Every impairment is off by default and draws from **its own seeded random stream** (noise 0, impulses 1, fading 2), so switching one on does not change the numbers another one sees.

`ChannelConfig`: `snr_db` (white noise, in 2,500 Hz), `fading_doppler_hz` (Rayleigh fading), `clock_drift_ppm`, `freq_offset_hz`, `impulse_rate_hz` / `impulse_duration_s` / `impulse_amplitude` / `impulse_over_noise_db`, `band_filter` (the 300 to 2,700 Hz SSB passband), `clip_level` / `clip_rms_multiple`. Impulses and clipping are sized against the noise the receiver hears (as an AGC would) so they mean the same at every SNR of a sweep.

`bench/scenarios.py` names four channels used everywhere: `white` (the reference), `ssb` (white noise through the radio passband), `hf-fading` (SSB plus slow Rayleigh fading, 1 Hz Doppler) and `dirty` (fading plus 1 ms static crashes five times a second at 20 dB over the noise, clipping, and 50 ppm of clock error).

### 9.2 The Success threshold: `threshold.py`

```bash
uv run python -m bench.threshold --modem vibemodem.core.turbo_modem:TurboModem --preset standard \
    --scenario hf-fading --snr-from -12 --snr-to -4 --snr-step 2 --trials 100 --seed 1 \
    --message-bytes 12 --max-lead-in-s 10 --tail-s 1 --freq-offset-from -1100 --freq-offset-to 1100 \
    --out standard-hf.json --html standard-hf.html
```

`measure_curve` sends `--trials` Messages at each SNR (each hidden at a random time and frequency, in a noisy recording), counts those received *exactly*, and counts wrong Messages handed over (`false_receptions`). `success_threshold` returns the lowest SNR reaching 95 % **such that every higher tested SNR also reaches it**. Statistics: near 95 %, the rate of 100 trials is known to only about ±2 %; use 300 trials and a 0.5 dB step to compare two candidates. `--set name=value` overrides a modem setting (`--set tones=4 --set interleave=true`); `--modem` takes `package.module:Class`. Output JSON has no date and no commit on purpose: the same seed gives the same file.

### 9.3 Reports and comparisons

- `bench/report.py` (`python -m bench.report a.json b.json --out r.html`): one self-contained offline HTML file with an inline SVG chart, Wilson 95 % intervals, a ranking, and a notice when results were measured on different terms.
- `bench/sweep.py`: tones × symbol duration grid → occupied bandwidth, Transmission length and the 95/90/80 % thresholds.
- `bench/bandwidth.py`: occupied bandwidth at −20 dB.
- `bench/code_curves.py`: how often a *code alone* loses a Frame on white noise vs Eb/N0 (validated against the textbook formula for an uncoded bit).
- `bench/speed.py`: median time to receive a ~24 s recording, as a multiple of real time.
- `bench/false_alarms.py`: Signals and Messages reported in noise alone (`--ssb` for filtered noise). The 3-hour white-noise runs per Preset are in `docs/measurements/false-alarms/`.
- `bench/toy.py`: `ToyModem`, coherent BPSK at 100 bit/s. It exists only to **validate the bench itself** against the textbook error curve (`tests/test_threshold.py`). Do not delete it.

### 9.4 Real recordings: replay, field check, trials

- `bench/replay.py` (`python -m bench.replay FOLDER`): decodes every kept reception again; a Frame read must give the same Message, frequency (within 1 Hz) and SNR (within 1 dB), a Signal lost must still be lost; exit status 1 on any mismatch. Run it after **any** change to the receiver.
- `bench/field_check.py` (`python -m bench.field_check FOLDER sent.txt [--preset P] [--redecode]`): compares the Messages sent (one per line) with what a receiver kept during a trial: received, missing, incomplete, heard but not listed, Signals lost, SNR range. `--redecode` decodes the kept audio again instead of trusting the stored figures.
- `bench/cable_trial.py` (`send` / `report`): a controlled test of a real sound chain. The sending computer adds white noise **digitally** at an exact SNR (also in the 2-second gaps, so the receiver's noise measurement is honest), scales to a peak of 0.9, and plays through its sound card and a cable into the receiving computer, whose application keeps its receptions. `report` counts what arrived at each SNR and compares the threshold with the simulator's. See [section 12.4](#124-real-world-trials). The report warns if the storage limit deleted receptions.
- `bench/cable_report.py` and `bench/project_report.py` build the two HTML reports in `docs/measurements/` from the stored results (`python -m bench.cable_report`, `python -m bench.project_report`).

### 9.5 Where results go

`docs/measurements/README.md` is the written record, with one section per measurement and its conclusion; raw JSON and HTML sit beside it. When you measure something, keep the command, the seed and the files, and add a section. A measurement that cannot be re-run is an anecdote.

---

## 10. The tests

About 1,090 tests in `tests/`, run by `uv run pytest` (`pythonpath = ["."]`, so `bench` and `tests` import as packages). They run in about three and a half minutes in total.

### 10.1 What each file covers

| Area | Files |
| :-- | :-- |
| Layers and purity | `test_layers.py` (layers importable; the core imports nothing forbidden) |
| Frame, Fragments, Transmission | `test_frame.py`, `test_message.py`, `test_transmission.py`, `test_limits.py` |
| Codes | `test_codes.py` (the contract of every `Code`), `test_turbo.py`, `test_ldpc.py`, `test_long_convolutional.py`; digests pin the codes |
| Waveform and modems | `test_waveform.py`, `test_mfsk_modems.py`, `test_modem_options.py`, `test_presets.py`, `test_frequency.py`, `test_search_band.py` |
| Receiver behaviour | `test_detections.py` (lost, arriving, side peaks), `test_clicks.py` (clicks are not Signals), `test_false_alarms.py`, `test_latency.py` |
| Spectrum, levels, audio, WAV | `test_spectrum.py`, `test_levels.py`, `test_audio.py`, `test_audio_check.py`, `test_wav.py` |
| Application | `test_service.py` (the biggest: sending, cancelling, listening, settings, the band), `test_api.py` (through HTTP), `test_conversation.py`, `test_keeping.py`, `test_store.py` |
| Bench | `test_channel.py`, `test_scenarios.py`, `test_threshold.py`, `test_threshold_command.py`, `test_report.py`, `test_report_command.py`, `test_sweep.py`, `test_bandwidth.py`, `test_code_curves.py`, `test_speed.py`, `test_toy_modem.py`, `test_replay.py`, `test_field_check.py`, `test_cable_trial.py`, `test_cable_report.py` |

### 10.2 How they are written

- **Behaviour through public interfaces.** A test reads like a specification (`test_a_signal_not_entirely_inside_the_band_is_ignored`) and survives a refactor. Test names are full sentences.
- **No mocking of internals.** What is faked is the outside world, in two places: `FakeAudio` (a sound card that plays into a list and hears from a script, with an optional cable between two instances) and `tests/fake_sounddevice.py` (stands in for the `sounddevice` library to test `SoundCard`). `tests/fake_modems.py` has stand-in candidates (`PerfectModem`, `DeafModem`, `WrongModem`) to test the bench.
- **Fixtures** such as `services` (makes `ModemService` objects and closes them) and `made` (a service and a `TestClient` for the API), and helpers like `listen(receiver, audio)` in `test_keeping.py`, which feeds audio through a `Receiver` synchronously (no thread, no waiting) so receiver tests are deterministic.
- **Where waiting is unavoidable**, tests use `wait_until(condition, timeout)` rather than a fixed sleep.
- **Pinned digests.** Code tests pin a hash of the codes' parameters: a change that alters the protocol (the interleaver, the polynomials) fails loudly and must be a conscious decision (ADR 0003).
- **Measurement-backed tests.** Some tests assert measured facts with a fixed seed (the toy modem follows the textbook curve within 0.05; clicks in a quiet room give neither a lost nor an arriving Signal in any of the three Presets).
- **Write the failing test first** for new behaviour, at the highest seam that observes it, then the minimum code, and run the single file often.

### 10.3 Useful invocations

```bash
uv run pytest tests/test_turbo.py -q                     # one file
uv run pytest -q -k "band"                               # by name
uv run pytest -x -q                                      # stop at the first failure
uv run pytest --collect-only -q | tail -1                # how many tests
uv run ruff check . && uv run ruff format --check .      # what CI also checks
```

---

## 11. Continuous integration, packaging, releases

### 11.1 CI (`.github/workflows/`)

- **`ci.yml`**: on every push and pull request, `uv sync --locked --all-extras`, then `ruff check`, `ruff format --check` and `pytest` on **Ubuntu and Windows**; macOS only on pull requests (its runners queue for a long time).
- **`package.yml`**: when `src/`, `packaging/`, `pyproject.toml`, `uv.lock` or the workflow changes (or on demand), on Windows **and** macOS: install with the `package` group, build with PyInstaller (`packaging/vibemodem.spec`), run the **smoke test** against the built executable, zip, and upload the artifact (`vibemodem-windows`, `vibemodem-macos`; artifacts need a GitHub login and expire after GitHub's retention period, 90 days by default).

### 11.2 The packaged application

`packaging/entry.py` is a plain script (PyInstaller needs one) calling `app.main.main`. `vibemodem.spec` builds a windowed (no console) one-folder application `VibeModem`, ships the `assets/` folder as data and collects all of `uvicorn`'s submodules; on macOS it makes `VibeModem.app` with a microphone usage description.

`packaging/smoke_test.py <executable>` starts the packaged app on port 8765 and checks that it serves the page (with its Send and Listen controls), that `style.css` and `script.js` are served, that `/api/selftest` reports a successful round trip of the modem (this proves the DSP libraries are inside the bundle), that it is not listening at start, and (on Windows and macOS) that the audio library loads. **CI has no sound card**, so what only a human can check is: double-click, page opens without a terminal, a real microphone listens, a Message is sent and heard. The procedure for that is `docs/packaging/procedure-packaging-check.md` (its first lines say which steps are historical).

The Windows zip was checked on a clean machine on 2026-11-06: it starts without a terminal and without a SmartScreen warning, listens, shows the spectrum and sends. The macOS build has never been run by hand.

To get the latest Windows build: GitHub → Actions → Package → the latest green run → artifact `vibemodem-windows`, or `gh run download <run id> -n vibemodem-windows`.

### 11.3 Branches, tags and releases

- `main` is the default branch; `dev` and `AI_deep_refactoing` carry the rewrite (the three were brought together for v1.0). The git tag `legacy-v0` freezes the old GMSK prototype.
- A **GitHub release** is a tag plus notes plus files, with a stable public URL and no login needed to download. Today nothing publishes releases automatically. The usual way: tag (`git tag v1.0 && git push --tags`), then `gh release create v1.0 vibemodem-windows.zip --title ... --notes ...`; a workflow step on `v*` tags could do it. Do not attach the macOS build to a release before it is checked.
- There is no code signing: Windows may show "unknown publisher" for a build downloaded from elsewhere, and macOS requires "Open Anyway".

---

## 12. What was measured and decided

The written record is `docs/measurements/README.md` (one section per measurement); the decisions are the ADRs. Read them: they answer most "why" questions before you ask them. The summary below is for orientation; numbers are the lowest SNR in 2,500 Hz at which 95 % of Messages arrive.

### 12.1 The ADRs

| ADR | Decision |
| :-- | :-- |
| 0001 | Rewrite from scratch; the old GMSK/GNU Radio code is kept only as the tag `legacy-v0`. |
| 0002 | The DSP core is pure NumPy/SciPy; audio devices are a thin separate layer; no GNU Radio. |
| 0003 | The turbo code is the v1 default; LDPC, the baseline convolutional code and the long convolutional code stay as measurable candidates. Turbo has no wrong-word guard of its own: the Frame CRC is the barrier. |
| 0004 | Three Presets, all 8-FSK with interleaved turbo-coded bits, differing only by symbol duration. |
| 0005 | One Fragment per Frame, each Frame with its own Preamble (19 % of airtime, robustness against fades and clock drift); optional copies. |
| 0006 | Kept receptions: a WAV and a JSON per Frame, in a folder the page cannot choose. |

### 12.2 Codes (docs/measurements/README.md, "Four codes compared")

Same modem, same channel, four codes on white noise: baseline −15 dB, LDPC −15.5, long convolutional −15.5, **turbo −16**. On radio-like channels turbo is ahead: on SSB-filtered noise it ties with the long code at −16; under hf-fading it is about 1.5 dB ahead of LDPC and 4 to 6 dB ahead of the long code at 90 %. Under fading *no* code reaches 95 % reliably; the plateau comes from the Preamble not being found after deep fades, not from the code. Speed: turbo decodes about 113× faster than real time on a desktop CPU, LDPC about 203×.

### 12.3 Waveform, Presets and false alarms

- **M-FSK sweep** (tones × symbol duration): at equal energy, 8 tones are as good as 16 and better than 4 or 2. A longer symbol only helps through its energy: +3 dB per doubling. A 160 ms symbol would give −19 dB in 64 Hz; 320 ms gives −22 dB in 31 Hz.
- **Under fading**, 8 tones with symbols of 160 ms or more remove the plateau (95 % reached at −14 dB instead of −4). **Interleaving** the coded bits gains about 1 dB but does not change the plateau; repeating the Frame twice gives nothing at equal energy.
- **GFSK** was at least 2.5 dB behind M-FSK and was removed (the measurements are kept).
- **Presets** (ADR 0004): max-range −22 dB (29 Hz, 54 s a Frame), standard −16 (107 Hz, 13.6 s), fast −13 (212 Hz, 6.8 s).
- **False alarms and clicks**: in pure noise, no Message was ever read in 80 hours, and no false alert appeared in 3 hours of white noise per Preset. A real room, though, produced 50 false "Signals lost" in 56 from clicks (a mouse, a loudspeaker pop). The score was a sum of energy relative to noise, and in a quiet room one click weighs as much as 32 symbols. The fix: cap the energy of a symbol (`SYMBOL_MATCH_CAP`) and subtract the average of the other tones at that moment. False alerts went from 40 to 7, no Message was lost, and the thresholds did not move. `tests/test_clicks.py` keeps it fixed.

### 12.4 Real-world trials

- **Loudspeaker and microphone, one room** (the owner, 117 receptions kept): every Message of one Fragment arrived; a longer Message (10 Fragments) in `fast` needed about 7 dB more SNR than the simulator, probably reverberation (not demonstrated). The recordings are not in the repository.
- **Cable trial** (ticket #21, `bench/cable_trial.py`): a laptop plays Messages at exact digital SNRs into the tower's sound card through a cable. `fast` (−13 dB) and `standard` (−16 dB) **equal the simulator**: 20 of 20 at the threshold, 0 of 20 two dB lower. The clock drift between the two sound cards was measured at 17 ppm (about 1 ms over a Transmission), the receiver's own noise floor at −103 dBFS, and the received SNR estimates were within 0.2 to 0.3 dB of the nominal values.
- **`max-range` over the cable** (ticket #28) first looked 3 to 4 dB worse than the simulator, then inconsistent from run to run. The cause was not the receiver: the application deleted the oldest receptions at its 200 MB storage limit, which were the lowest SNRs ([15.1](#151-the-storage-limit-silently-deletes-the-oldest-receptions)). Replaying the continuous recording of one run through the live receiver gave the same counts as decoding it offline. A confirmation run with the limit raised was in progress when this guide was written; the current figure is in `docs/measurements/README.md`.

Two HTML reports show all of it with charts: `docs/measurements/cable-trial/report.html` (English, the cable trial) and `docs/measurements/project-report.html` (French, the whole project, written for a conference).

---

## 13. How we work

- **Tickets** are GitHub issues in `BimBim134/vibe-audioModem`, under the specification issue #1. Labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` (`docs/agents/triage-labels.md`). Use `gh issue ...` (`docs/agents/issue-tracker.md` has the recipes). The project owner closes tickets.
- **Language.** Use the glossary's words in code, tests, commits and tickets, and avoid the words it lists to avoid.
- **Decisions** that are hard to reverse, surprising without context, and the result of a real trade-off go in an ADR (`docs/adr/NNNN-title.md`: the decision, why, consequences). Terms go in `GLOSSARY.md` the moment they are settled; the glossary is a dictionary, not a place for implementation notes.
- **Measure before claiming.** A change to the receiver comes with the Success threshold before and after, the false-alarm check and `bench.replay` on real recordings. Report what was *not* verified as plainly as what was.
- **Tests first** for new behaviour (see [10.2](#102-how-they-are-written)); `ruff` clean; the full suite green before pushing.
- **Commits** are one logical change with an imperative English subject and a body that says why (`Add the Listening band: ...`, `Rule out the detector as the cause of ...`). Measurement results are committed with the command that produced them.
- **Memory.** `docs/agents/memory.md` is the project's logbook (in French); add an entry when you learn something a later reader would otherwise rediscover. `docs/agents/project-map.md` is a table of files; keep its row for a file you add.
- **No shortcuts on the core's purity**: `tests/test_layers.py` will stop you, and it is right.

---

## 14. Recipes

### 14.1 Understand why a Message was not received

1. In **Settings → Advanced**, switch on **Keep the audio and the figures of what is received**, and raise the limit if the session is long (see 15.1). Run the session.
2. Look at the folder (`--receptions-dir`, or the default shown under the switch). Each WAV has a JSON of the same name: Preset, frequency, SNR, sync score, `decoded` true or false, the body in hex.
3. Check against what was sent: `uv run python -m bench.field_check FOLDER sent.txt --preset standard` (one Message per line in `sent.txt`) lists received, missing, incomplete, heard but not listed, and Signals lost; add `--redecode` to decode the audio again with today's code.
4. Replay all of them: `uv run python -m bench.replay FOLDER`.
5. Dig into one: 

```python
from vibemodem.io.wav import read_wav
from vibemodem.core.turbo_modem import TurboModem
report = TurboModem(preset="standard").demodulate_report(read_wav("one.wav"))
print(report.receptions, report.undecoded, report.arriving)
```

A lost Signal with a score near 10 is barely a Signal; one near 20 or more was heard and the code could not read it (too weak, a fade, interference).

### 14.2 Add a Preset

1. Choose tones (2/4/8/16) and a symbol duration that is a whole number of samples and a multiple of 32 samples (`Waveform` validates), and add a `PhyProfile` to `presets.PRESETS`.
2. Measure: `bench.bandwidth --preset`, `bench.threshold` on `white` and `hf-fading` with the Presets' usual recipe (100 trials, 1 dB steps, `--max-lead-in-s 10 --tail-s 1 --freq-offset-from -1100 --freq-offset-to 1100`), `bench.false_alarms`, `bench.speed`.
3. Add a row to `tests/test_presets.py`, the page's Preset `<select>` in `index.html`, the thresholds in `bench/cable_trial.py` (`SIMULATED_THRESHOLD_DB`), a measurements section and an ADR amendment.
4. Remember that a Preset's Frame length decides the longest Message in 30 minutes and the window the receiver keeps.

### 14.3 Add a Code

Implement `Code` (`info_bits` must be 200, the Frame size), make `tests/test_codes.py` pass for it (it runs the same contract on every code), add a one-line modem class (`class MyModem(CodedMfskModem)` as `turbo_modem.py` does), then compare it with turbo on all four scenarios with `bench.threshold` and `bench.code_curves`. A code that wins on white noise and loses under fading is not a win. Document in an ADR; if it changes the protocol, pin its digest in a test.

### 14.4 Add a setting or an endpoint (the Listening band is the worked example)

The commit that added it (`Add the Listening band ... (#27)`) touches, in this order: a test at the core (`tests/test_search_band.py`), the core (`mfsk.find_signals`, `CodedModem.search_band_hz`, `presets.minimum_band_hz`), tests at the service and the API (`test_service.py`, `test_api.py`, `test_keeping.py`), `Receiver.set_search_band`, `ModemService.set_search_band` (validation raising `SettingsError` with a message that tells the person what to do), `api.py` (a request model with `extra="forbid"` and the endpoint), the page (HTML fields, `script.js`), then `GLOSSARY.md`, `docs/agents/project-map.md` and `memory.md`. Copy that order.

### 14.5 Run a controlled trial over a cable

1. Wire the sending computer's output to the receiving computer's input through an attenuator or a volume you leave alone (the level of a Transmission of white noise at −20 dB is dominated by the noise: keep it below clipping).
2. On the receiver, start the application with `--receptions-dir` pointing to an empty folder, choose the Preset and the input, switch **Keep** on, and **raise the storage limit** (`POST /api/storage {"keep": true, "limit_mb": 3000}`), then Listen.
3. On the sender: `uv run python -m bench.cable_trial send --preset max-range --output <device> --per-level 10 --snr=-24,-23,-22,-21,-20,-19` (an equals sign for a list that starts with a minus; the same list on both sides).
4. When it ends, stop listening and run `uv run python -m bench.cable_trial report FOLDER --preset max-range --snr=... --per-level 10`.
5. Record the result in `docs/measurements/cable-trial/results.json` and rebuild the report (`python -m bench.cable_report`).

On Linux, if the sound card is "busy" because PipeWire holds it, use the input device name `pulse` instead of the hardware name.

### 14.6 Reproduce a published threshold

Open the JSON in `docs/measurements/`: it records the modem and its settings, the scenario, the seed, the number of trials and the SNR grid. Run `bench.threshold` with the same ones; the file must be identical.

### 14.7 Ship a build to someone

Find the latest green run of the *Package* workflow, download the Windows artifact, unzip, run `VibeModem.exe`. For a public link, create a GitHub release with that zip attached ([11.3](#113-branches-tags-and-releases)).

---

## 15. Traps and lessons

Each of these cost real time. They are the project's institutional memory.

### 15.1 The storage limit silently deletes the oldest receptions

`ReceptionStore` keeps at most 200 MB (default) of kept receptions and deletes **the oldest first**, without a message. In a trial that sends the weakest Messages first, the weakest levels vanish, and the report shows "0 of 10" there. A 3-to-4 dB "loss" of the `max-range` Preset on a real chain, a "live receiver weaker than offline" and an "unstable chain" were all this. The tell: the first number in the kept file names (`...-0015.json`) is not `0000`, because the counter starts at 0 with each run. `bench.cable_trial report` now prints a warning with the number deleted. For any trial: raise the limit first.

### 15.2 A measurement on white noise says nothing about clicks

The decoder passed 60 hours of white noise with no false alarm and then, in a quiet room, reported 50 false Signals in a few minutes. Measure on the channel you will use, and keep a test for each real-world surprise.

### 15.3 `sd.stop()` from another thread kills the application

PortAudio is not safe for that. `SoundCard.stop()` sets a flag the playback callback reads.

### 15.4 A recording is at most 600 seconds

`demodulate_report` raises on a longer one. Decode long recordings in overlapping chunks, with an overlap longer than one Frame (54 s at max-range) so no Frame is cut in every chunk, and de-duplicate by Message.

### 15.5 A decode that "always answers" is dangerous

Turbo never returns `None`. If you weaken or bypass the CRC-32 (the `Frame` check), wrong Messages will appear. After any change to the Frame, the code, or the soft values, run a false-alarm measurement and a threshold measurement and count `false_receptions`.

### 15.6 Changing a code's interleaver or polynomials changes the protocol

Two builds with different ones cannot talk to each other. The tests pin a digest so that it cannot happen by accident.

### 15.7 Side peaks look like Signals

A Preamble matches partly at nearby frequencies and times. `CodedModem._without_side_peaks` and the receiver's `alike()` tolerance exist for this. Anything that changes how many candidates the search returns needs `tests/test_detections.py` and a look at the false-alarm counts.

### 15.8 A Frame cut by the start of the window is not judged

The receiver's window slides; a Frame whose Preamble is partly outside it would look lost. The receiver skips judging such a Frame because an earlier pass saw it whole.

### 15.9 `bench` modules must be run from the repository root

`python -m bench.threshold` needs the root on the path. `uv run` from the root does it; `pytest` has `pythonpath = ["."]`. Outside that, set `PYTHONPATH=.`. Likewise use `uv run python` (or `.venv/bin/python`), not a bare `python`, which may not exist.

### 15.10 Times in file names are UTC

Kept receptions are named by UTC time; your clock is probably not UTC. A file stamped 22:44 is 23:44 in a France winter... and 00:44 in summer. Use the counter at the end when you need order.

### 15.11 One scope in `script.js`

A duplicate top-level name is a `SyntaxError` that stops the whole page. Open the browser console after editing it.

### 15.12 An SNR is always in 2,500 Hz

Do not compare an SNR quoted in the signal's own band with the project's. The bench's `apply_channel(..., snr_db=x)` already uses 2,500 Hz. When you add noise yourself to a trial, add it **all around** the Transmission too (the receiver measures the noise it hears over its whole recording): a quiet gap next to a noisy Transmission makes the trial easier than the simulator.

### 15.13 The receiver must know the Preset

There is no automatic detection of the Preset. The listener chooses the same one as the sender; each Preset has its own modem and its own search.

### 15.14 Floating-point equality in tests

Digests and counts are pinned; waveform values are not compared exactly. Use `pytest.approx`.

---

## 16. Where the project stands and what is next

**Done (v1.0 scope).** The modem (three Presets), the Message protocol with Fragments and copies, the local application (send, listen, spectrum, waterfall, conversation, kept receptions, replay, Listening band), the bench and its measurements, a Windows build checked on a clean machine, and two measurement reports.

**Open tickets at the time of writing** (check `gh issue list` for the truth):

- **#23, field campaign** with loudspeaker and microphone, then with radios. The owner intends to propose it at a conference to people who will run life-size studies. It needs a working prototype and a clear procedure: `bench.field_check` and the kept receptions are the tools. It is the measurement that is still missing: everything above is simulator or cable.
- **#28, `max-range` on a real chain**: the storage-limit artefact is understood; the confirmation run and the corrected reports were still to be finished.
- **#29, make the page reachable from the whole network** with a QR code: a nice to have, not a priority; it must come with authentication and HTTPS.
- **#1, the specification**, stays open until the others are done.

**Natural next steps** (ideas, not decisions):

- Reading several Signals at once; when the core can do it, the Listening band disappears.
- A measurement of the Listening band on real radio noise (low-frequency "brown" noise under 400 Hz), in the field rather than by another simulation.
- Automatic detection of the Preset.
- A manual check of the macOS build, release automation on tags, code signing if the project gets users who cannot click through a warning.

---

## Appendix A. Every Python file in one line

(Generated from each module's docstring.)

| File | What it is |
| :-- | :-- |
| `bench/__init__.py` | Measurement bench: channel simulator and Success threshold tools. |
| `bench/audio_check.py` | Try the sound card by hand: list devices, check an input's level, or send a Message through. |
| `bench/bandwidth.py` | How much bandwidth a modem's output occupies. |
| `bench/cable_report.py` | Build the single report of the real-world trials: docs/measurements/cable-trial/report.html. |
| `bench/cable_trial.py` | A trial over a real sound chain at known SNRs: send Messages at each SNR, count what arrives. |
| `bench/channel.py` | Channel simulator: what a weak-signal SSB audio channel does to a Transmission. |
| `bench/code_curves.py` | How often a code loses a frame on white noise, against Eb/N0. |
| `bench/false_alarms.py` | How often a receiver reports a Signal in noise alone. |
| `bench/field_check.py` | Check a field trial: what was sent against what a receiver kept. |
| `bench/project_report.py` | Build the report of the whole project, for a talk: docs/measurements/project-report.html. |
| `bench/replay.py` | Replay stored receptions through the decoder, to check they give what they gave live. |
| `bench/report.py` | A human-readable HTML report of bench results. |
| `bench/scenarios.py` | Named channels for comparing modems and codes on something closer to a radio link. |
| `bench/settings.py` | Settings given on a command line as name=value. |
| `bench/speed.py` | How fast a candidate receives, against real time. |
| `bench/sweep.py` | Sweep the settings of a modem: tones and symbol duration of M-FSK, or any grid you give. |
| `bench/threshold.py` | Success threshold: the lowest SNR at which a modem receives enough Messages correctly. |
| `bench/toy.py` | A deliberately simple modem that validates the bench: coherent BPSK, no synchronisation. |
| `packaging/entry.py` | Entry point of the packaged application (PyInstaller needs a plain script). |
| `packaging/smoke_test.py` | Start a packaged build, check it serves its page and runs DSP, then stop it. |
| `src/vibemodem/__init__.py` | One-way weak-signal data modem for radio amateurs. |
| `src/vibemodem/app/__init__.py` | Local application: loopback web server and user interface. |
| `src/vibemodem/app/__main__.py` | (no description) |
| `src/vibemodem/app/api.py` | The local HTTP API and its page: a thin layer over `ModemService`. |
| `src/vibemodem/app/conversation.py` | The conversation: what was sent and what was heard, in one line of time, for the page. |
| `src/vibemodem/app/heard.py` | What the application tells about what it heard: Messages, their quality, lost Signals. |
| `src/vibemodem/app/keeper.py` | Keeping receptions: each Frame read and each Signal lost, once, with sound around it. |
| `src/vibemodem/app/main.py` | Start the local application: a web page on the loopback interface, served by one process. |
| `src/vibemodem/app/receiver.py` | Listening: what is heard is decoded, kept, and drawn. No HTTP and no sending here. |
| `src/vibemodem/app/service.py` | The application's service: settings, sending and cancelling, and listening. No HTTP here. |
| `src/vibemodem/app/store.py` | Receptions kept on disk: the raw audio and the indicators of each, within a bound. |
| `src/vibemodem/core/__init__.py` | DSP core: Messages to audio samples and back. No devices, files or network. |
| `src/vibemodem/core/baseline.py` | The baseline modem: the reference every later candidate is measured against. |
| `src/vibemodem/core/code.py` | The interface of an error-correcting code, so a modem can use any of them. |
| `src/vibemodem/core/coded_mfsk.py` | An M-FSK modem that works with any error-correcting code. |
| `src/vibemodem/core/coded_modem.py` | What every modem built on a Code shares: the Frame, the order the bits are sent in, and the loop that turns a recording into Messages. |
| `src/vibemodem/core/convolutional.py` | Rate-1/2 convolutional code (constraint length 7) with a soft-decision Viterbi decoder. |
| `src/vibemodem/core/frame.py` | The fixed-size Frame: length byte, padded Message and CRC-32, whitened. |
| `src/vibemodem/core/ldpc.py` | A low-density parity-check (LDPC) code, decoded by normalised min-sum. |
| `src/vibemodem/core/ldpc_modem.py` | The baseline modem with its convolutional code replaced by an LDPC code of the same rate. |
| `src/vibemodem/core/long_convolutional.py` | A long-constraint convolutional code, decoded sequentially by the Fano algorithm. |
| `src/vibemodem/core/long_convolutional_modem.py` | The baseline modem with its code replaced by the long-constraint convolutional code. |
| `src/vibemodem/core/message.py` | The Message protocol: a Message split into Fragments, one Fragment per Frame. |
| `src/vibemodem/core/mfsk.py` | M-FSK: building the audio, measuring tone energies and finding a Signal. |
| `src/vibemodem/core/modem.py` | The interface every modem candidate implements, so the bench can measure any of them. |
| `src/vibemodem/core/presets.py` | The three Presets and the PHY profile each one names. |
| `src/vibemodem/core/spectrum.py` | One row of the spectrum of a block of sound: the audio band in bins of 5 Hz, in dB. |
| `src/vibemodem/core/transmission.py` | A Message as a Transmission of Frames, and the Messages in a recording. |
| `src/vibemodem/core/turbo.py` | A turbo code: two recursive convolutional codes in parallel, decoded by trading opinions. |
| `src/vibemodem/core/turbo_modem.py` | The baseline modem with its convolutional code replaced by a turbo code of the same rate. |
| `src/vibemodem/io/__init__.py` | Audio layer: sound cards and WAV files. Carries no DSP. |
| `src/vibemodem/io/_samples.py` | The one check every way of playing or storing audio shares. |
| `src/vibemodem/io/audio.py` | Sound cards: list, play, record and listen at the modem's sample rate, mono. No DSP. |
| `src/vibemodem/io/levels.py` | Is the input level fit for the receiver? Peak and RMS level, and warnings. |
| `src/vibemodem/io/wav.py` | WAV files: 16-bit mono at 48 kHz written; the usual formats read, at 48 kHz only. |

---

## Appendix B. Command cheat sheet

```bash
# Setup and checks
uv sync --locked --all-extras
uv run ruff check . && uv run ruff format --check . && uv run pytest

# The application
uv run python -m vibemodem.app [--port N] [--no-browser] [--receptions-dir PATH]

# Measure
uv run python -m bench.threshold --modem pkg.mod:Class --preset P --scenario white|ssb|hf-fading|dirty \
    --snr-from A --snr-to B --snr-step S --trials N --seed 1 --out x.json [--html x.html] [--set k=v]
uv run python -m bench.report a.json b.json --out compare.html
uv run python -m bench.sweep ...            # tones x symbol duration
uv run python -m bench.bandwidth --preset P  # occupied band at -20 dB
uv run python -m bench.code_curves --code pkg.mod:Class
uv run python -m bench.speed --modem pkg.mod:Class
uv run python -m bench.false_alarms --preset P --hours 3 [--ssb]

# Real recordings and trials
uv run python -m bench.audio_check --list
uv run python -m bench.replay FOLDER
uv run python -m bench.field_check FOLDER sent.txt [--preset P] [--redecode]
uv run python -m bench.cable_trial send   --preset P --output DEV --per-level N --snr=-24,-22,...
uv run python -m bench.cable_trial report FOLDER --preset P --per-level N --snr=-24,-22,...

# Reports
uv run python -m bench.cable_report      # docs/measurements/cable-trial/report.html
uv run python -m bench.project_report    # docs/measurements/project-report.html

# Tickets
gh issue list; gh issue view N; gh issue comment N -b "..."
gh run list --workflow Package; gh run download RUN_ID -n vibemodem-windows
```

## Appendix C. Reading list, in order

1. `README.md`, `GLOSSARY.md`.
2. `docs/adr/0001` to `0006` (about ten minutes).
3. `docs/measurements/README.md` (the evidence), then the two HTML reports.
4. The code in the order of [section 2](#where-to-start-reading-the-code), each module with its test file.
5. `docs/agents/memory.md` (French) for the story of every ticket, including the dead ends.
6. `docs/packaging/` if you touch the build.
