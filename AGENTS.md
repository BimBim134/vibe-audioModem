# AGENTS.md

## VIBE AUDIOMODEM Story
### Context of Project
Radio amateurs use "digital modes" to send text via audio signals plugged into radio microphones. vibe-audiomodem modernize this by providing a chat-like interface for text, images, and files, moving away from the cluttered, callsign-only UIs of the past.

### Solution
- **Modern UI:** Chat input, file attachments, message history.
- **Signal Monitoring:** Simplified for non-experts.
- **Expert Mode:** Advanced control over baudrate, constellation, packet size, and ECC.

---

## Technical Architecture

### Process Model
The system uses a multiprocess architecture for real-time DSP performance:
- **`AudioInterfaceProcess` (`src/rx/audio_interface.py`):** Captures audio via PortAudio, computes FFT (Blackman-Harris window), and publishes both to ZMQ.
- **`PeakDetectorProcess` (`src/rx/peak_detector.py`):** Monitors FFT for signals. Spawns `DemodulatorWorker` processes when a transmission is detected.
- **`DemodulatorWorker` (`src/rx/demodulator.py`):** Handles synchronization (Gardner TED), carrier recovery (Costas Loop), and decoding.
- **`PacketDecoderProcess` (`src/rx/packet_decoding.py`):** Reassembles fragments, handles Reed-Solomon decoding, and unscrambling.
- **`ModemController` (`src/audioModem/audioModem.py`):** Main orchestrator. Manages the TX queue and hosts the ZMQ configuration publisher.
- **HTTP Server (`src/audioModem/http_server.py`):** FastAPI interface for the UI/CLI.

### Networking (ZMQ IPC)
Processes communicate via ZMQ on `localhost` (ports 5555-5560):
| Port | Type | Description | Data Type |
| :--- | :--- | :--- | :--- |
| 5555 | PUB/SUB | Raw Audio | Float32 |
| 5556 | PUB/SUB | FFT Spectrum | Float32 Vector |
| 5557 | PUB/SUB | Raw Packets | PMT (Metadata + Bytes) |
| 5558 | PUB/SUB | Reassembled Messages | PMT (Dict) |
| 5559 | PUB/SUB | Config Broadcast | PMT (Dict) |
| 5560 | PUB/SUB | Peak Detector System | PMT (Dict) |

### Data Structures & Framing
- **Serialization:** Uses GNU Radio's `pmt` library. Messages are often dictionaries serialized to PMT strings/blobs.
- **Packet Format (`PacketConfig`):**
    - Default size: 48 bytes.
    - `[1 byte Flag] [N bytes Data] [16 bytes RS ECC]`
    - **Flags:** `0` (Preamble), `255` (Postamble), `1-N` (Data length).
- **Error Correction:** Reed-Solomon (via `reedsolo`).
- **Scrambling:** `AdditiveScrambler` (Mask: `0x48`, Seed: `0x7F`, Register: 7 bits) to ensure DC balance and transitions.

### Signal Processing Pipeline
**TX Path:**
1. PMT Dict -> Scrambler -> RS Encoder -> Packetizer.
2. Protocol Formatter (Access Key: `11100001010110101110100010010011`).
3. CC Encoder -> Constellation Modulator (BPSK/QPSK/8PSK).
4. Rotator (Carrier Freq) -> Beeper Mux -> Audio Sink.

**RX Path:**
1. Audio Source -> Freq Xlating FIR Filter -> AGC.
2. Symbol Sync (Gardner TED) -> Correlation Estimator (Access Key).
3. Linear Equalizer (CMA) -> Costas Loop.
4. Constellation Decoder -> Diff Decoder -> Map -> FEC Decoder.
5. Access Code Correlator -> Tagged Stream to PDU.

---

## Development Guide

### Key Files
- `src/misc/config.py`: Central source of truth for all configurations (Signal, Packet, Ports).
- `src/audioModem/audioModem.py`: Entry point for logic, state management, and process orchestration.
- `src/tx/transmitter.py` & `src/rx/demodulator.py`: Core GNU Radio flowgraphs.

### Adding New Modulations
1. Update `CONSTELLATION_MAP` in `src/misc/config.py`.
2. Ensure the `Demodulator` in `src/rx/demodulator.py` can resolve the constellation name.
3. Update presets if necessary.

### Modifying Packet Formats
- Adjust `PacketConfig` in `src/misc/config.py`.
- Update `PacketReassembler` in `src/rx/packet_decoding.py` if the flag logic changes.
- Update `split_payload_into_packet` in `src/tx/packetizer.py`.

---

## Gotchas
- **Logging:** Only in `audiomodem.log` by default. Change in `setup_logging()` to enable console.
- **GNU Radio:** Hard dependency. Flowgraphs are defined in Python but rely on C++ blocks.
- **PMT:** `pmt.to_python` and `pmt.to_pmt` are critical for cross-process communication.
- **ZMQ Binding:** The `PacketDecoder` *binds* to the raw packet port; `Demodulator` workers *connect* to it.

## API Reference (Port 8000)
- `GET /status`: Returns `is_transmitting` and `queue_size`.
- `GET /config`: Returns current signal and packet configurations.
- `POST /transmit`: JSON `{"message": "...", "sender_name": "..."}`.
- `POST /preset`: JSON `{"preset": "FAST"}` (Options: `FAST`, `MEDIUM`, `SLOW`).
- `POST /carrier`: JSON `{"frequency": 2500}`.
- `GET /messages`: Retrieves and flushes the received message queue.
