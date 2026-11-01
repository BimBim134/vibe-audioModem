# Measurements

Results of bench runs worth keeping, as the JSON written by `bench.threshold` and the HTML report made from it. A new candidate is compared against these.

## Baseline modem: Success threshold -15 dB

Candidate `vibemodem.core.baseline:BaselineModem` (8-FSK in about 100 Hz, fixed 20-byte Frame, soft-decision convolutional code, CRC-32), Preset `standard`. Files: `baseline-modem.json`, `baseline-modem.html`.

| Quantity | Value |
| :-- | :-- |
| Success threshold | **-15 dB** (SNR in a 2,500 Hz noise bandwidth) |
| Received at -15 dB | 286 of 300 (95.3%; the true rate lies between about 92.3% and 97.2% with 95% confidence) |
| First SNR with every Message received | -14 dB (300 of 300) |
| Last SNR with none received | -18 dB (0 of 300) |
| Wrong Messages handed over | 0, over 3,900 trials |
| Airtime of one Transmission | 13.6 s (2.56 s preamble, 11.04 s data) |

How to read it:

- "Never delivered" is a probability, not an absolute: a wrong Message needs a CRC-32 match (about 1 chance in 4.3 billion per decoding attempt, at most 3 attempts per recording) and a valid length byte. Over the 3,900 trials, and the noise-only and damaged-audio tests, none was handed over.
- The curve is steep: 59% of Messages arrive at -16 dB, 95% at -15 dB, 99% at -14.5 dB. The resolution of the threshold is the 0.5 dB step, and near 95% the measured rate is uncertain by about 2.4% with 300 trials. Treat differences of less than 0.5 dB between two candidates as noise.
- This is white noise only, no fading, drift, clipping or SSB filter. A real channel will be worse.
- The Signal was hidden at a random moment (up to 10 s into a 24.6 s recording) and shifted by a random frequency (-1,100 to +1,100 Hz), so the figure includes the cost of searching for it.

Reproduce it exactly (about 15 minutes; the same seed gives the same file apart from the date in the HTML):

```bash
uv run python -m bench.threshold --modem vibemodem.core.baseline:BaselineModem \
    --snr-from -18 --snr-to -12 --snr-step 0.5 --trials 300 --message-bytes 12 --seed 1 \
    --max-lead-in-s 10 --tail-s 1 --freq-offset-from -1100 --freq-offset-to 1100 \
    --out docs/measurements/baseline-modem.json --html docs/measurements/baseline-modem.html
```
