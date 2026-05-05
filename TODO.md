- [1. how do the audiomodem handle receiving a messages ?](#1-how-do-the-audiomodem-handle-receiving-a-messages-)
- [2. set the commands for audio modem and http server:](#2-set-the-commands-for-audio-modem-and-http-server)
  - [2.1. /POST](#21-post)
  - [2.2. /GET](#22-get)
- [3. the audiomodem needs to subscribe to fft port](#3-the-audiomodem-needs-to-subscribe-to-fft-port)
- [4. replace the CLI by a TUI](#4-replace-the-cli-by-a-tui)
- [5. create a webUI](#5-create-a-webui)
  - [5.1. add the possibility the launch only the webUI](#51-add-the-possibility-the-launch-only-the-webui)
- [6. performance improvements](#6-performance-improvements)
  - [6.1. Audio Modem Architecture: Low SNR Optimization Guide](#61-audio-modem-architecture-low-snr-optimization-guide)
    - [6.1.1. Executive Summary](#611-executive-summary)
    - [6.1.2. Modulation Comparison (Audio Context)](#612-modulation-comparison-audio-context)
    - [6.1.3. Analysis of the "10dB Bottleneck"](#613-analysis-of-the-10db-bottleneck)
    - [6.1.4. Proposed Architecture Upgrades](#614-proposed-architecture-upgrades)
      - [6.1.4.1. Phase A: Optimization (The "Free" Gains)](#6141-phase-a-optimization-the-free-gains)
      - [6.1.4.2. Phase B: The Acoustic Receiver Chain](#6142-phase-b-the-acoustic-receiver-chain)
    - [6.1.5. Overcoming the Noise Floor (SNR \< 0dB)](#615-overcoming-the-noise-floor-snr--0db)
      - [6.1.5.1. DSSS (Direct Sequence)](#6151-dsss-direct-sequence)
      - [6.1.5.2. CSS (Chirp Spread Spectrum)](#6152-css-chirp-spread-spectrum)
    - [6.1.6. Implementation Notes for GNU Radio](#616-implementation-notes-for-gnu-radio)
- [7. keep only quit in CLI](#7-keep-only-quit-in-cli)
- [8. improve test setup](#8-improve-test-setup)



# 1. how do the audiomodem handle receiving a messages ?
it seems audiomodem has no way to return received message to the cli

# 2. set the commands for audio modem and http server:
## 2.1. /POST
  * `transmit`
    * *sent to the modem* : any messages or bytes payload
    * *what the modem do* : it add the messages or byte payload the the queue to be treated
  
  * `receive` (`-n` : the number of workers to spawn)
  
    starts the peak detector and spawn n (or only 1 if not specified) workers ready to receive any transmission.

    it implies that :
    * the modem should take care of the number of worker to be spawn by the peak_detector
    * the peak detector should not be started at startup but only when the `receive` command is sent
    * peakdetector (and associated workers) **will be** resetted if the user wants to ajust:
      *  parameters
      *  number of workers 


  * `setup`
    * request :
      ```json
      {
          "signal": {
              "samp_rate": 48000,
              "carrier_freq": 2500,
              "beeper_duration": 3.0,
              "baudrate": 200,
              "constellation_name": "default"
          },
          "packet": {
              "total_packets_len": 48,
              "preamble_packets": 1,
              "postamble_packets": 1,
              "error_correction_len": 16
          },
          "port": {
              "audio_port": 5555,
              "fft_port": 5556,
              "fft_size": 4096,
              "raw_packets_port": 5557,
              "messages_port": 5558,
              "config_port": 5559,
              "peak_detector_system_port": 5560
          }
      }
      ```
    * *what the modem do* : it reset **completely** with the new adjusted parameters 

  * `stop`
    * `-rx` : stops the peak detectors and associated workers 
    * `-tx` : stops any transmission and clear the queue
  
  * `quit`

    closes the whole application **gracefully**

## 2.2. /GET
 * `fft`
 * `messages`
 * `configuration`
 * `logs`

# 3. the audiomodem needs to subscribe to fft port
so that it an later sends fft data to the web UI

# 4. replace the CLI by a TUI
The same than CLI, but much nicer

# 5. create a webUI
it can do everything the CLI can do, but graphically, in the browser.
## 5.1. add the possibility the launch only the webUI
that way, the user can setup a distant station, and control it remotely.


# 6. performance improvements

## 6.1. Audio Modem Architecture: Low SNR Optimization Guide

### 6.1.1. Executive Summary
While BPSK is theoretically optimal for power efficiency in a vacuum, it is poorly suited for **acoustic (audio)** environments due to phase instability, Doppler shifts, and hardware clock drift. For an audio modem operating near or below the noise floor, **GFSK (Gaussian Frequency Shift Keying)** or **CSS (Chirp Spread Spectrum)** are the preferred choices.

### 6.1.2. Modulation Comparison (Audio Context)

| Feature                 | BPSK (Current)                     | GFSK (Recommended)                | CSS/LoRa (Advanced)             |
| :---------------------- | :--------------------------------- | :-------------------------------- | :------------------------------ |
| **Information Carrier** | Phase ($180^\circ$ shifts)         | Frequency Deviation               | Frequency Slope (Chirps)        |
| **CFO Tolerance**       | **Extremely Low** (Rotation)       | **High** (Linear Shift)           | **Very High**                   |
| **Acoustic Robustness** | Poor (Echoes break phase)          | Good (Tolerates echoes)           | Excellent (Multipath resistant) |
| **Complexity**          | High (Costas Loop required)        | Low (Quadrature Demod)            | Moderate (Cross-correlation)    |
| **SNR Threshold**       | $\approx 7\text{ to }10\text{ dB}$ | $\approx 4\text{ to }6\text{ dB}$ | $\mathbf{< 0\text{ dB}}$        |

---

### 6.1.3. Analysis of the "10dB Bottleneck"
Your current "Voyager-grade" stack (Scrambling → Reed-Solomon → CC → RRC) is sophisticated, but it likely hits a wall at 10dB SNR due to:
1.  **Hard-Decision Loss:** Using a Binary Slicer before the Viterbi decoder discards $\approx 2\text{ dB}$ of "probability information."
2.  **Phase Noise:** In audio, small physical movements or reflections rotate the BPSK constellation, causing the Viterbi decoder to receive "rotated garbage" it cannot fix.
3.  **Synchronization Jitter:** At low SNR, standard clock recovery blocks struggle to find the "center" of the bit, leading to sampling errors.

---

### 6.1.4. Proposed Architecture Upgrades

#### 6.1.4.1. Phase A: Optimization (The "Free" Gains)
*   **Switch to GFSK:** Use a Modulation Index $h = 1.0$ (instead of the GMSK standard of 0.5) to increase tone separation.
*   **Soft-Decision Viterbi:** Remove the Binary Slicer. Feed raw floats from the demodulator into the `FEC Extended Decoder` (set to Soft-Decision).
*   **Correlation Estimator:** Use this instead of "Correlate Access Code" to find your 32-bit preamble. It uses complex math to find the header even when buried in noise.

#### 6.1.4.2. Phase B: The Acoustic Receiver Chain
To handle the "messy" audio environment in GNU Radio, use this specific sequence:
1.  **Frequency Xlating FIR Filter:** Centers the signal and provides initial decimation.
2.  **Quadrature Demod:** Converts frequency shifts to voltage (floats).
3.  **DC Blocker:** **CRITICAL.** Removes the offset caused by frequency drift between the speaker and mic.
4.  **Symbol Sync:** Performs timing recovery on the "clean" DC-blocked signal.

---

### 6.1.5. Overcoming the Noise Floor (SNR < 0dB)
If you need to decode when the signal is inaudible/invisible, **Spreading** is required.

#### 6.1.5.1. DSSS (Direct Sequence)
*   **Method:** Multiply each bit by a PN sequence (e.g., 11-bit Barker or 31-bit Gold code).
*   **Pro:** High processing gain.
*   **Con:** **Increases Bandwidth ($BW$) significantly.** 
*   **Equation:** $BW_{spread} = BW_{base} \times L$ (where $L$ is sequence length).

#### 6.1.5.2. CSS (Chirp Spread Spectrum)
*   **Method:** Use "up-chirps" and "down-chirps" to represent data.
*   **Pro:** Bandwidth is fixed. You gain SNR by increasing the **Time** of the chirp (integration).
*   **Why for Audio:** Best at handling the "echo-chamber" effect of indoor rooms.

---

### 6.1.6. Implementation Notes for GNU Radio
*   **Sensitivity Formula:** For the Quadrature Demod block, use $Sensitivity = \frac{Sample Rate}{2 \pi \times Deviation}$.
*   **Matched Filtering:** Ensure **Root Raised Cosine (RRC)** filters are matched on both TX and RX to minimize Inter-Symbol Interference (ISI).
*   **Sampling:** Use a standard audio rate (48kHz) but keep your symbol rate low (e.g., 100–500 baud) to allow the FEC/Spreading to do its work.

> **Final Verdict:** Stay with your FEC stack, but swap **BPSK $\to$ GFSK**, implement **Soft-Decision decoding**, and add a **DC Blocker** to your RX chain. This should push your decoding limit from 10dB down toward the 3–5dB range.


# 7. keep only quit in CLI

why is there quit, clear, ctrl+D handle ?? it needs to be simplifies

# 8. improve test setup

when `--test` is given to the CLI, the audio interface is not launched and replaced by the transmitter that sends its signals on port 5555 (audio)

to do :
* add a `--test` args to the cli
* it does not start the audio interface
* the transmitter can ouput on port 5555 and not directly on audio interface