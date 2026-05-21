- [1. the audiomodem needs to subscribe to fft port](#1-the-audiomodem-needs-to-subscribe-to-fft-port)
- [2. replace the CLI by a TUI](#2-replace-the-cli-by-a-tui)
- [3. create a webUI](#3-create-a-webui)
  - [3.1. add the possibility the launch only the webUI](#31-add-the-possibility-the-launch-only-the-webui)
- [4. see why it's only working at baudrate = 200](#4-see-why-its-only-working-at-baudrate--200)
- [5. improve frame synchronization](#5-improve-frame-synchronization)



# 1. the audiomodem needs to subscribe to fft port
so that it an later sends fft data to the web UI

# 2. replace the CLI by a TUI
The same than CLI, but much nicer

# 3. create a webUI
it can do everything the CLI can do, but graphically, in the browser.
## 3.1. add the possibility the launch only the webUI
that way, the user can setup a distant station, and control it remotely.

# 4. see why it's only working at baudrate = 200
test done :
* baudrate 400 : fail
* baudrate 500 : fail
* baudrate 100 : fail
* baudrate 200, carrier freq 2000 : pass deltaf : 3.91 Hz
* starting config baudrate 500, then config set baudrate 200 : pass : deltaf 3.91 Hz
* starting config baudrate 200, then config set baudrate 500 : fail

# 5. improve frame synchronization
Current synchronization uses `digital.correlate_access_code_bb_ts` which operates on bits *after* demodulation. This is sensitive to noise and timing jitter, likely contributing to the baudrate limitations.

**Proper implementation plan:**
- **Transition to Complex Correlation:** Replace bit-level correlation with `digital.corr_est_cc` (Complex Correlation Estimator) on the baseband signal. This is much more robust as it uses signal energy before slicing.
- **Implement Header-Payload Demux:** Use `digital.header_payload_demux` to properly separate the frame header from the payload. This is the idiomatic GNU Radio way to handle bursty data.
- **Review FEC Placement:** The Access Key is currently inside the Convolutional Code. Investigate if moving the Access Key (or a preamble) *outside* the FEC would improve locking speed at high baudrates.
- **Remove "Tag Fixer" hacks:** The `TagValueSetter` in `demodulator.py` is a workaround for `correlate_access_code_bb_ts` bugs; structured demuxing will eliminate the need for it.
- **Tune Symbol Sync:** If using `corr_est_cc`, the timing estimate can be used to reset the `digital.symbol_sync_xx` block for perfect alignment on every burst.
