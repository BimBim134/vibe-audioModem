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

## Three codes compared: thresholds -15 dB, -15.5 dB, -16 dB

The same modem (8-FSK in about 100 Hz, fixed Frame with a CRC-32, same preamble) with three different error-correcting codes, each rate 1/2 on a Frame of 200 information bits:

- **Baseline**: convolutional code, constraint length 7, soft-decision Viterbi decoding (`vibemodem.core.baseline:BaselineModem`).
- **LDPC**: repeat-accumulate LDPC code, 400 coded bits, normalised min-sum, at most 50 iterations (`vibemodem.core.ldpc_modem:LdpcModem`).
- **Turbo**: two recursive 8-state convolutional codes (4G polynomials) with a spread-8 interleaver, half the parity bits kept, trellises terminated, max-log-MAP decoding with extrinsic scaling 0.75 and at most 8 iterations (`vibemodem.core.turbo_modem:TurboModem`).

Files: `baseline-modem.json`, `ldpc-modem.json`, `turbo-modem.json` (and their `.html`), and `codes-comparison.html`, which puts the three curves on one chart. Each result file records the code it measured (kind, block length, coded length and its settings, with a digest of the LDPC rules or of the turbo interleaver), so a retuned code cannot pass for the one measured here.

The three runs are paired: same SNR grid (-18 to -12 dB in 0.5 dB steps), same seed, 300 Messages of 12 bytes per SNR, same hidden start and frequency shift for each trial number, same white noise at the start of each recording. What differs follows from the codes: the convolutional and the turbo code both send 412 coded bits (138 data symbols, 13.6 s), the LDPC code 400 (134 symbols, 13.3 s, 3% shorter).

| SNR (dB) | Baseline | LDPC | Turbo |
| :-- | :-- | :-- | :-- |
| -17.5 | 7/300 (2.3%) | 15/300 (5.0%) | 31/300 (10.3%) |
| -17.0 | 44/300 (14.7%) | 78/300 (26.0%) | 121/300 (40.3%) |
| -16.5 | 108/300 (36.0%) | 197/300 (65.7%) | 246/300 (82.0%) |
| -16.0 | 178/300 (59.3%) | 269/300 (89.7%) | 287/300 (95.7%) |
| -15.5 | 255/300 (85.0%) | 290/300 (96.7%) | 300/300 (100%) |
| -15.0 | 286/300 (95.3%) | 299/300 (99.7%) | 300/300 (100%) |
| **Success threshold** | **-15 dB** | **-15.5 dB** | **-16 dB** |

How to read it:

- The whole curve moves left from the baseline to LDPC to turbo. Interpolating between measured points, 50% of Messages arrive at about -16.2, -16.7 and -16.9 dB, and 95% at about -15.0, -15.6 and -16.0 dB. Against the baseline the gain at 95% is about 0.6 dB for LDPC and 1.0 dB for turbo; turbo beats LDPC by about 0.4 dB at 95% and only about 0.2 dB at 50%.
- The gaps are clear where the curves are steep: at -16 dB, 287 (turbo), 269 (LDPC) and 178 (baseline) of 300; the 95% intervals are 92.7 to 97.5%, 85.7 to 92.6% and 53.7 to 64.7%. At -16.5 dB, turbo (77.3 to 85.9%) and LDPC (60.1 to 70.8%) do not overlap either.
- The thresholds are steps of 0.5 dB, each known to about 2%, and turbo's own value is borderline: 287 of 300 at -16 dB is 95.7%, while 95% itself lies inside its interval (92.7 to 97.5%). Quote it as about -16 dB. Read the curves, not the single step; differences under 0.5 dB between candidates are noise.
- No wrong Message was handed over by any modem in any trial. The CRC-32 is the final check for all three: the LDPC decoder can settle on a wrong codeword and the turbo decoder always returns bits, and then the Frame's CRC-32 rejects them.
- These measurements are on white noise only, with no fading, drift, clipping or SSB filter, which may rank the codes differently.
- Simulating the three codes alone on white noise agrees with the ranking. `python -m bench.code_curves --code vibemodem.core.convolutional:ConvolutionalCode` (or `vibemodem.core.ldpc:LdpcCode`, `vibemodem.core.turbo:TurboCode`) `--ebn0-from 1.5 --ebn0-to 2.5 --frames 800 --seed 1` gives the share of frames lost (Eb/N0 is the energy per information bit over the noise density, so the codes' rates are accounted for):

  | Eb/N0 | Convolutional | LDPC | Turbo |
  | :-- | :-- | :-- | :-- |
  | 1.5 dB | 30.6% | 24.9% | 12.5% |
  | 2.0 dB | 16.4% | 7.0% | 2.0% |
  | 2.5 dB | 6.0% | 1.1% | 0.1% |

- The turbo interleaver: at 200 bits, shuffles with a spread of 8, 9 or 10 and the 4G polynomial interleaver all lost the same share of frames within the noise of an exploratory simulation (800 frames per point, not kept), so the choice does not matter measurably. The spread rule (four fifths of the largest reachable spread) was picked because it builds instantly for any size, and a test pins the resulting code.
- All three measurements were run again with the final code (after the modem was restructured to take any code, and after the codes learned to describe themselves in the result files) and gave exactly the same counts, point for point.
- An earlier run of the LDPC modem on a grid starting at -19 dB gave the same threshold but did not pair its noise with the baseline's, so it was replaced.

### Speed

`python -m bench.speed` times how long a candidate takes to receive a recording of about 24 s holding one Transmission (5 s of silence in front, 6 s after, noise at -14 dB, shifted by 300 Hz), as the median of 7 receptions, and the time of the code alone. The `speed-*.json` files hold the results with the machine they were measured on, an Intel Core i5-12400F desktop (12 threads); run the command again on the machines you care about.

| | Baseline | LDPC | Turbo |
| :-- | :-- | :-- | :-- |
| Whole recording | 138 ms, 178 times real time | 119 ms, 203 times real time | 218 ms, 113 times real time |
| Code alone, clean Frame | about 1 to 2 ms | 0.02 ms (stops at once) | 2.9 ms |
| Code alone, soft values that never decode | about 1 to 2 ms | 3.4 ms (the full 50 iterations) | 11.5 ms (the full 8 iterations) |

- The LDPC recording is a little shorter (24.3 s against 24.6 s) because its Transmission is. Most of the time is the search for the preamble over every start time and audio frequency (about 70 ms); decoding the code is a few to a dozen milliseconds. All three are far faster than real time, and turbo is the slowest, about twice as slow as LDPC overall.
- This is a desktop processor, faster than many laptops, and no laptop was measured: on a laptop several times slower the modems should still receive tens of times faster than real time, but that is an extrapolation, not a measurement.
