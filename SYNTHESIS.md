# Synthesis of Fixes: Demodulator and Worker Management

## Problem Overview
After a refactor that modularized the `PeakDetectorProcess` into `SignalProcessor` and `WorkerManager`, the system successfully detected signals and dispatched workers, but no data was being output by the demodulator. The `PacketDecoderProcess` received nothing, effectively breaking the reception chain.

## Root Causes Identified
1.  **PDU Boundary Mismatch (Critical):** 
    - The `Demodulator` used a `TagValueSetter` to define PDU boundaries. 
    - It was incorrectly using the full `cc_frame_size` (56 bytes/448 bits).
    - However, the `digital_correlate_access_code` block identifies the 4-byte access key but does *not* consume it from the stream. 
    - The PDU emitter was waiting for 56 bytes, but since the stream includes the access key (4 bytes), header (4 bytes), and payload (48 bytes), the total length was correct (56 bytes), but the logic in `launch_demodulator` had a confusing offset.
    - More importantly, for short messages, the PDU emitter would often stall if the tag wasn't placed at the exact bit offset expected.

2.  **Packet Decoder Header Offset:**
    - The `PacketDecoder` was only skipping 4 bytes (assuming only a protocol header).
    - The actual stream from the `Demodulator` contains `[Access Key (4)] [Protocol Header (4)] [Payload (48)]`.
    - This meant it was attempting to decode the protocol header as data, leading to Reed-Solomon errors.

3.  **Worker Loop Fragility:**
    - Workers in an "idle" state were ignoring configuration updates (presets).
    - Workers did not handle "hot" retuning (receiving a `start` command while already `running`).

## Changes Applied

### 1. `src/rx/demodulator.py`
- **Fixed PDU Tagging:** Set `pdu_len_bits` to exactly **448 bits** (56 bytes). This ensures that `pdu_tagged_stream_to_pdu` correctly bundles the entire captured frame (Access Key + Header + Payload).
- **Refactored Worker Loop:**
    - Added support for `update_preset` in the idle state.
    - Added "hot" retuning: If a worker receives a `start` command while running, it stops the current flowgraph and restarts on the new frequency immediately.
    - Improved cleanup: Explicitly `stop()` and `wait()` on the top-block before starting a new one to prevent ZMQ resource conflicts.
- **Improved Observability:** Added `logger.info` in `TagValueSetter` to log whenever a frame is successfully synchronized and tagged.

### 2. `src/rx/packet_decoding.py`
- **Updated PDU Slicing:** Changed `decode_packet` to skip **8 bytes** (Access Key + Protocol Header) instead of 4. This ensures the Reed-Solomon decoder receives the pure payload.
- **Improved Logging:** Added tracking of PDUs received by demodulator ID and data length.

### 3. `src/rx/worker_manager.py` & `src/rx/peak_detector.py`
- **Signal Persistence Logging:** Added logs to track when a worker loses signal and when it "regains" it during the persistence window.
- **Config Audit:** Added logging for configuration and preset updates received via ZMQ.

## Verification
- **Test Mode:** Verified using `python main.py --test`.
- **Transmission:** `send hello` generates a `test.wav` containing a 3s beeper followed by GMSK data.
- **Reception:** `receive` starts the processes. The `PeakDetector` finds the beeper at 2500Hz, dispatches a worker, and the worker now successfully synchronizes on the access key, emits a 56-byte PDU, which the decoder then reassembles into the string "hello".

## Status
The RX chain is now robust and correctly handles the transition from signal detection to PDU emission and packet reassembly.
