# AGENTS.md

## VIBE AUDIOMODEM story
### context of project

Radio amateurs all around the world use so called "digital modes" to send text to each other.
It works by pluging directly the soundcard of your computer directly onto the radio microphone port.
the data to be sent is modulated in an audio signal that can be transmitted easily with minimal hardware change.

### Current state of the art

There is no modern solution to digital mode, Only bad and cluttered UI. The UX consist only to send your call sign and getting the other's back.
There is no conversation. There no unique solution that can send text, images, files.

### solution

vibe-audiomodem aims to resolve the lack of conversation by ressembling all modern chatting app :
* a text input where you can type what you want
* an attach file or images
* a send button
* a scrollable messages area

there will be some additionnal feature specific to audiomodem
* a simplified signal monitoring system (I don't want it to be the main part of the UI, so that the user can focus on conversation)
* some signal presets (SLOW, FAST)
* hidden on another page, an expert mode whe advanced user can select the baudrate, the constellation, packets sizes, error code correction size...)

## Setup

- Conda environment: `environment.yml` (Python 3.12, GNU Radio, PySide6)
- No pip `requirements.txt` or `pyproject.toml` — install via `conda env create -f environment.yml`

## Running

- `python main.py` — starts modem (HTTP server + receiver processes)
- `python main.py --cli` — CLI mode (cmd-based, polls HTTP API at localhost:8000)
- HTTP API on port 8000 is the primary control interface (see `docs/doc.md` for endpoints)

## Architecture

Multiprocess architecture with ZMQ IPC (ports 5555–5560):
- `src/audioModem/audioModem.py` — `ModemController`, orchestrates processes
- `src/rx/` — receiver: audio_interface, peak_detector, demodulator, packet_decoding
- `src/tx/` — transmitter: packetizer, transmitter
- `src/audioModem/http_server.py` — FastAPI server, proxies requests to `ModemController`
- `src/audioModem/cli.py` — CLI, talks to HTTP API only (no direct imports of rx/tx)

Processes: AudioInterface, PeakDetector, PacketDecoder — all launched in `start_audiomodem()`.

## Config

- `src/misc/config.py` — dataclasses: `SignalConfig`, `PacketConfig`, `PortsConfig`
- Defaults defined at module level: `DEFAULT_SIGNAL_CONFIG`, `DEFAULT_PACKET_CONFIG`, `DEFAULT_PORTS_CONFIG`
- Runtime config changes broadcast via ZMQ `config_port` (5559) using PMT serialization

## Gotchas

- Logging: writes to `audiomodem.log` (not console); configured in `src/misc/config.py:setup_logging()`
- No tests, no linter, no typechecker configured — verify by running code
- `test.py` is a scratch script, not a test suite
- GNU Radio (`gnuradio`) is a core dependency — code won't run without it
- ZMQ messages serialized with GNU Radio's `pmt` library, not plain JSON
- `grc_files/` contains GNU Radio Companion flowgraphs (not imported as Python modules)
