# AGENTS.md

## VIBE AUDIOMODEM Story
### Context of Project
Radio amateurs use "digital modes" to send text via audio signals plugged into radio microphones. vibe-audiomodem modernizes this by providing a chat-like interface for text, images, and files, moving away from the cluttered, callsign-only UIs of the past.

### Solution
- **Modern UI:** Chat input, file attachments, message history.
- **Signal Monitoring:** Simplified for non-experts via FFT snapshots and peak detection.
- **Expert Mode:** Advanced control over baudrate, packet size, and ECC.

---

## Technical Architecture

### Process Model
The system uses a multiprocess architecture for real-time DSP performance:
- **`AudioInterfaceProcess` (`src/rx/audio_interface.py`):** Captures audio (PortAudio or WAV), computes FFT (Blackman-Harris window), and publishes both to ZMQ.
- **`PeakDetectorProcess` (`src/rx/peak_detector.py`):** Monitors FFT for signals using `scipy.signal.find_peaks`. Orchestrates persistent `DemodulatorWorker` processes.
- **`DemodulatorWorker` (`src/rx/demodulator.py`):** Persistent workers that handle GMSK demodulation, differential decoding, convolutional decoding (FEC), and frame synchronization.
- **`PacketDecoderProcess` (`src/rx/packet_decoding.py`):** Reassembles fragments, handles Reed-Solomon decoding, and unscrambling.
- **`ModemController` (`src/audioModem/audioModem.py`):** Main orchestrator. Manages the TX queue, hosts the ZMQ configuration publisher, and handles command routing from the API.
- **HTTP Server (`src/audioModem/http_server.py`):** FastAPI interface for the UI/CLI.

### Networking (ZMQ IPC)
Processes communicate via ZMQ on `localhost` (ports 5555-5560):
| Port | Type    | Description          | Data Type              |
| :--- | :------ | :------------------- | :--------------------- |
| 5555 | PUB/SUB | Raw Audio            | Float32                |
| 5556 | PUB/SUB | FFT Spectrum         | Float32 Vector         |
| 5557 | PUB/SUB | Raw Packets          | PMT (Metadata + Bytes) |
| 5558 | PUB/SUB | Reassembled Messages | PMT (Dict)             |
| 5559 | PUB/SUB | Config Broadcast     | PMT (Dict)             |
| 5560 | PUB/SUB | Peak Detector System | PMT (Dict)             |

### Data Structures & Framing
- **Serialization:** Uses GNU Radio's `pmt` library. Messages are dictionaries or lists serialized to PMT strings/blobs.
- **Packet Format (`PacketConfig`):**
    - Default size: 48 bytes.
    - `[1 byte Length Flag] [N bytes Data] [16 bytes RS ECC]`
    - **Flags:** `0` (Preamble), `255` (Postamble), `1-N` (Data length).
- **Error Correction:** Two-layer FEC:
    - Inner: Convolutional Coding (CC) via `fec.cc_encoder`.
    - Outer: Reed-Solomon (via `reedsolo`).
- **Scrambling:** `AdditiveScrambler` (Mask: `0x48`, Seed: `0x7F`, Register: 7 bits) applied to payload before RS encoding.

### Signal Processing Pipeline
**TX Path:**
1. PMT Dict -> Scrambler -> RS Encoder -> Packetizer (Frame assembly).
2. Protocol Formatter (Access Key: `11100001010110101110100010010011`).
3. Tagged Stream Mux -> CC Encoder -> Diff Encoder -> GMSK Modulator.
4. Rotator (Carrier Freq) -> Beeper Mux -> Audio Sink.

**RX Path:**
1. Audio Source (ZMQ) -> Freq Xlating FIR Filter -> AGC.
2. GMSK Demodulator -> Diff Decoder -> CC Decoder (FEC).
3. Access Code Correlator (Access Key) -> Repack bits -> Tagged Stream to PDU.
4. PDU metadata update (Demodulator ID, Frequency) -> ZMQ Pub.

---

## Development Guide

### Key Files
- `src/misc/config.py`: Central source of truth for all configurations (Signal, Packet, Ports).
- `src/audioModem/audioModem.py`: Entry point for logic, state management, and process orchestration.
- `src/tx/transmitter.py` & `src/rx/demodulator.py`: Core GNU Radio flowgraphs.
- `src/rx/peak_detector.py`: Logic for signal discovery and worker dispatching.

### Modifying Packet Formats
- Adjust `PacketConfig` in `src/misc/config.py`.
- Update `PacketReassembler` in `src/rx/packet_decoding.py` if the flag logic changes.
- Update `split_payload_into_packet` in `src/tx/packetizer.py`.

---

## Gotchas
- **Logging:** Default log file is `audiomodem.log`. Use `setup_logging(console=True)` for terminal output.
- **GNU Radio:** Hard dependency. Flowgraphs rely on C++ blocks; avoid pickling `gr` objects between processes.
- **PMT:** `pmt.to_python` and `pmt.to_pmt` are critical for cross-process communication.
- **ZMQ Binding:** The `PacketDecoder` *binds* to the raw packet port (`5557`); `Demodulator` workers *connect* to it.
- **GMSK Transition:** The codebase currently uses GMSK modulation/demodulation despite references to BPSK/QPSK in some config maps.

## API Reference (Port 8000)
- `GET /status`: Returns `is_transmitting` and `queue_size`.
- `GET /configuration`: Returns current signal, packet, and port configurations.
- `GET /messages`: Retrieves and flushes the received message queue.
- `GET /fft`: Returns a single FFT snapshot (JSON list of floats).
- `GET /logs?lines=N`: Returns the last N lines of the log file.
- `POST /transmit`: JSON `{"message": "...", "sender_name": "..."}`.
- `POST /receive`: JSON `{"nb_workers": N}` (Start receiver processes).
- `POST /setup`: JSON with partial `signal`, `packet`, or `port` config to reconfigure/reset the modem.
- `POST /stop`: JSON `{"rx": true, "tx": true}` to stop specific subsystems.
- `POST /quit`: Gracefully shuts down all processes.
