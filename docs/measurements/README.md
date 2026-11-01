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

## LDPC modem: Success threshold -15.5 dB

Candidate `vibemodem.core.ldpc_modem:LdpcModem`: the baseline with its convolutional code replaced by an LDPC code of the same rate (200 information bits, 400 coded bits, normalised min-sum decoding). Same Frame, same CRC-32, same 8-FSK, same preamble. Files: `ldpc-modem.json`, `ldpc-modem.html`, and `ldpc-vs-baseline.html`, which puts both curves on one chart.

The two runs are paired: same SNR grid (-18 to -12 dB in 0.5 dB steps), same seed, 300 Messages of 12 bytes per SNR, same hidden start and frequency shift for each trial number, same white noise at the start of each recording. One difference follows from the codes themselves: the convolutional code adds 6 tail bits, so the baseline sends 412 coded bits (138 data symbols, 13.6 s) and the LDPC modem 400 (134 symbols, 13.3 s), 3% shorter.

| SNR (dB) | Baseline | LDPC |
| :-- | :-- | :-- |
| -17.0 | 44/300 (14.7%) | 78/300 (26.0%) |
| -16.5 | 108/300 (36.0%) | 197/300 (65.7%) |
| -16.0 | 178/300 (59.3%) | 269/300 (89.7%) |
| -15.5 | 255/300 (85.0%) | 290/300 (96.7%) |
| -15.0 | 286/300 (95.3%) | 299/300 (99.7%) |
| **Success threshold** | **-15 dB** | **-15.5 dB** |

How to read it:

- The LDPC code gains about 0.5 dB, all along the curve: 50% of Messages arrive at about -16.7 dB instead of -16.2 dB, 95% at about -15.6 dB instead of -15.0 dB (straight-line interpolation between the measured points). The gap is clear where the curves are steep: at -16 dB, 269 against 178 of 300 (intervals 85.7 to 92.6% and 53.7 to 64.7%, which do not overlap).
- The two thresholds themselves are one 0.5 dB step apart, each known to about 2%; the gain comes from the whole curve, not from that one step. Treat differences under 0.5 dB between candidates as noise.
- An earlier run of the LDPC modem on a grid starting at -19 dB gave the same threshold (-15.5 dB) but did not pair the noise with the baseline's, so it was replaced by this one.
- Neither modem handed over a wrong Message in any trial. The CRC-32 is the final check for both: the LDPC decoder can settle on a wrong codeword, and then the Frame's CRC-32 rejects it.
- A simulation of the two codes alone on white noise (1,000 frames per point) agrees: at 2.0 dB of Eb/N0 the convolutional code lost 18.5% of frames, the chosen LDPC 6.9%.
- After the modem was restructured to take any code, the baseline's first seven points (-18 to -15 dB) were measured again and gave exactly the same counts as in `baseline-modem.json`.

### Speed

`python -m bench.speed` times how long a candidate takes to receive a recording of about 24 s holding one Transmission (5 s of silence in front, 6 s after, noise at -14 dB, shifted by 300 Hz), as the median of 7 receptions, and the time of the code alone. The files `speed-baseline.json` and `speed-ldpc.json` hold the results with the machine they were measured on, an Intel Core i5-12400F desktop (12 threads); run the command again on the machines you care about.

| | Baseline | LDPC |
| :-- | :-- | :-- |
| Whole recording | 138 ms, 178 times real time | 119 ms, 203 times real time |
| Code alone, clean Frame | about 1 to 2 ms | 0.02 ms (stops at once, every rule satisfied) |
| Code alone, soft values that never decode | about 1 to 2 ms | 3.4 ms (the full 50 iterations, the worst case) |

- Almost all the time is the search for the preamble over every start time and audio frequency (about 70 ms); decoding the code is a few milliseconds, so both are far faster than real time. With a single thread the LDPC modem took 112 ms.
- This is a desktop processor, faster than many laptops, and no laptop was measured: on a laptop several times slower the modem should still receive tens of times faster than real time, but that is an extrapolation, not a measurement.
