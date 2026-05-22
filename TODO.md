- [1. replace the CLI by a TUI](#1-replace-the-cli-by-a-tui)
- [2. create a webUI](#2-create-a-webui)
  - [2.1. add the possibility the launch only the webUI](#21-add-the-possibility-the-launch-only-the-webui)
- [3. see why it's only working at baudrate = 200](#3-see-why-its-only-working-at-baudrate--200)
- [4. improve frame synchronization](#4-improve-frame-synchronization)
    - [4.0.1. Path A: The "Gated" Approach (Modular)](#401-path-a-the-gated-approach-modular)
    - [4.0.2. Path B: The "Proper" Reconstruction (Discrete Blocks)](#402-path-b-the-proper-reconstruction-discrete-blocks)
    - [4.0.3. The FEC/Sync Paradox](#403-the-fecsync-paradox)


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

### 4.0.1. Path A: The "Gated" Approach (Modular)
Keep the `gmsk_demod` block but use a trigger to gate the payload.
1.  **Correlation:** Place `digital.corr_est_cc` after the AGC. It correlates against the **modulated** Access Key.
2.  **Demuxing:** Use `digital.header_payload_demux`.
    *   **Header Port:** Feed into a dedicated demodulator to extract frame metadata.
    *   **Payload Port:** Only flows when a valid correlation is found.
*Pros: Easier to implement within the current architecture.*

### 4.0.2. Path B: The "Proper" Reconstruction (Discrete Blocks)
Break open the `gmsk_demod` hierarchy to allow the correlator to guide the timing recovery.
1.  **Complex Correlation:** `digital.corr_est_cc` finds the modulated sync word and outputs a `time_est` tag.
2.  **Symbol Sync:** `digital.symbol_sync_xx` replaces the internal clock recovery. Configure it to **reset its state** when the `time_est` tag is received. This ensures perfect symbol alignment at the very start of the packet.
3.  **Demodulation:** `analog.quadrature_demod_cf` -> `digital.binary_slicer_fb`.
4.  **FEC Decoding:** Move the CC/RS decoding to the end of the chain, operating on the synchronized bitstream.
*Pros: Maximum robustness at high baudrates (500+).*

### 4.0.3. The FEC/Sync Paradox
Currently, the Access Key is encoded inside the Convolutional Code (CC).
*   **Discovery:** In `CC_STREAMING` mode, the encoded bits for the Access Key depend on the previous data sent, making correlation difficult.
*   **Solution:** In the `Transmitter`, the CC encoder should be **reset** or switched to `CC_TERMINATED` at the start of every packet. This ensures the modulated Access Key is always identical and deterministic, allowing `corr_est_cc` to find it reliably.
*   **Alternative:** Move the Access Key (or a Barker sequence preamble) *outside* the FEC-encoded block entirely.
