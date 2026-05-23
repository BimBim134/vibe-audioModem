- [1. replace the CLI by a TUI](#1-replace-the-cli-by-a-tui)
- [2. create a webUI](#2-create-a-webui)
  - [3.1. add the possibility the launch only the webUI](#31-add-the-possibility-the-launch-only-the-webui)
- [3. see why it's only working at baudrate = 200](#3-see-why-its-only-working-at-baudrate--200)
- [4. improve frame synchronization](#4-improve-frame-synchronization)
    - [4.1. Path A: The "Gated" Approach (Modular)](#41-path-a-the-gated-approach-modular)
    - [4.2. Path B: The "Proper" Reconstruction (Discrete Blocks)](#42-path-b-the-proper-reconstruction-discrete-blocks)
    - [4.3. The FEC/Sync Paradox](#43-the-fecsync-paradox)
    - [4.4. Path B Post-Mortem (Attempted May 2026)](#44-path-b-post-mortem-attempted-may-2026)


# 1. replace the CLI by a TUI
The same than CLI, but much nicer

# 2. create a webUI
it can do everything the CLI can do, but graphically, in the browser.
## 2.1. add the possibility the launch only the webUI
that way, the user can setup a distant station, and control it remotely.

# 3. see why it's only working at baudrate = 200
test done :
* baudrate 400 : fail
* baudrate 500 : fail
* baudrate 100 : fail
* baudrate 200, carrier freq 2000 : pass deltaf : 3.91 Hz
* starting config baudrate 500, then config set baudrate 200 : pass : deltaf 3.91 Hz
* starting config baudrate 200, then config set baudrate 500 : fail

# 4. improve frame synchronization
Current synchronization uses `digital.correlate_access_code_bb_ts` which operates on bits *after* demodulation. This is sensitive to noise and timing jitter, likely contributing to the baudrate limitations.

**Proper implementation plan:**

### 4.1. Path A: The "Gated" Approach (Modular)
Keep the `gmsk_demod` block but use a trigger to gate the payload.
1.  **Correlation:** Place `digital.corr_est_cc` after the AGC. It correlates against the **modulated** Access Key.
2.  **Demuxing:** Use `digital.header_payload_demux`.
    *   **Header Port:** Feed into a dedicated demodulator to extract frame metadata.
    *   **Payload Port:** Only flows when a valid correlation is found.
*Pros: Easier to implement within the current architecture.*

### 4.2. Path B: The "Proper" Reconstruction (Discrete Blocks)
Break open the `gmsk_demod` hierarchy to allow the correlator to guide the timing recovery.
1.  **Complex Correlation:** `digital.corr_est_cc` finds the modulated sync word and outputs a `time_est` tag.
2.  **Symbol Sync:** `digital.symbol_sync_xx` replaces the internal clock recovery. Configure it to **reset its state** when the `time_est` tag is received. This ensures perfect symbol alignment at the very start of the packet.
3.  **Demodulation:** `analog.quadrature_demod_cf` -> `digital.binary_slicer_fb`.
4.  **FEC Decoding:** Move the CC/RS decoding to the end of the chain, operating on the synchronized bitstream.
*Pros: Maximum robustness at high baudrates (500+).*

### 4.3. The FEC/Sync Paradox
Currently, the Access Key is encoded inside the Convolutional Code (CC).
*   **Discovery:** In `CC_STREAMING` mode, the encoded bits for the Access Key depend on the previous data sent, making correlation difficult.
*   **Solution:** In the `Transmitter`, the CC encoder should be **reset** or switched to `CC_TERMINATED` at the start of every packet. This ensures the modulated Access Key is always identical and deterministic, allowing `corr_est_cc` to find it reliably.
*   **Alternative:** Move the Access Key (or a Barker sequence preamble) *outside* the FEC-encoded block entirely.

### 4.4. Path B Post-Mortem (Attempted May 2026)
Implementation of Path B was attempted but found to be non-viable in the current architecture.
**Encountered Problems:**
- **Symbol Sync Instability:** The `digital.symbol_sync_cc` block (Gardner TED) proved significantly more sensitive to initial frequency offsets and gain variations than the integrated M&M loop in `gmsk_demod`. Without AGC and FLL perfectly tuned, timing lock was frequently lost.
- **FEC Tail-Bit Truncation:** Switching to `CC_TERMINATED` to solve the Sync Paradox introduced 12 extra bits (for K=7, Rate 1/2) that required surgical updates to the `Transmitter` sample counting.
- **PDU Alignment Ambiguity:** There was persistent confusion between `correlate_access_code_bb_ts` and `protocol_parser_b`. The parser strips the header automatically, while the correlator only tags it. This led to "off-by-8-bytes" errors in the Reed-Solomon decoder.
- **Differential Decoder Necessity:** Confirmed that FM-demodulated GMSK still requires a `diff_decoder_bb` if the transmitter uses a `diff_encoder_bb`, but the interaction between differential decoding and Viterbi (FEC) decoding makes bit-slips catastrophic for the entire frame.
- **Python Complexity:** Managing the `mark_delay` and oversampling (SPS) reference taps in a pure-Python `gr.top_block` is brittle compared to using GRC-generated hierarchical blocks.
