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

## Four codes compared: thresholds -15, -15.5, -16 and -15.5 dB

The same modem (8-FSK in about 100 Hz, fixed Frame with a CRC-32, same preamble) with four different error-correcting codes, each of rate about 1/2 on a Frame of 200 information bits:

- **Baseline**: convolutional code, constraint length 7, soft-decision Viterbi decoding (`vibemodem.core.baseline:BaselineModem`).
- **LDPC**: repeat-accumulate LDPC code, 400 coded bits, normalised min-sum, at most 50 iterations (`vibemodem.core.ldpc_modem:LdpcModem`).
- **Turbo**: two recursive 8-state convolutional codes (4G polynomials) with a spread-8 interleaver, half the parity bits kept, trellises terminated, max-log-MAP decoding with extrinsic scaling 0.75 and at most 8 iterations (`vibemodem.core.turbo_modem:TurboModem`).
- **Long convolutional**: the code of WSPR, constraint length 32 (polynomials f2d05351 and e4613c47 in hexadecimal), 31 tail bits, decoded by the Fano sequential algorithm with soft values scaled to a mean size of 2.5, a threshold step of 3 and a budget of 1,000 steps per bit, after which it gives up (`vibemodem.core.long_convolutional_modem:LongConvolutionalModem`).

Files: `baseline-modem.json`, `ldpc-modem.json`, `turbo-modem.json`, `long-convolutional-modem.json` (and their `.html`), and `codes-comparison.html`, which puts the four curves on one chart. Each result file records the code it measured (kind, block length, coded length and its settings, with a digest of the LDPC rules or of the turbo interleaver), so a retuned code cannot pass for the one measured here.

The four runs are paired: same SNR grid (-18 to -12 dB in 0.5 dB steps), same seed, 300 Messages of 12 bytes per SNR, same hidden start and frequency shift for each trial number, same white noise at the start of each recording. What differs follows from the codes: the baseline and the turbo code send 412 coded bits (138 data symbols, 13.6 s), the LDPC code 400 (134 symbols, 3% shorter), and the long convolutional code 462 (154 symbols, 14.9 s, **9% longer**, because its tail is 31 bits).

| SNR (dB) | Baseline | LDPC | Turbo | Long convolutional |
| :-- | :-- | :-- | :-- | :-- |
| -17.5 | 7/300 (2.3%) | 15/300 (5.0%) | 31/300 (10.3%) | 28/300 (9.3%) |
| -17.0 | 44/300 (14.7%) | 78/300 (26.0%) | 121/300 (40.3%) | 143/300 (47.7%) |
| -16.5 | 108/300 (36.0%) | 197/300 (65.7%) | 246/300 (82.0%) | 240/300 (80.0%) |
| -16.0 | 178/300 (59.3%) | 269/300 (89.7%) | 287/300 (95.7%) | 283/300 (94.3%) |
| -15.5 | 255/300 (85.0%) | 290/300 (96.7%) | 300/300 (100%) | 298/300 (99.3%) |
| -15.0 | 286/300 (95.3%) | 299/300 (99.7%) | 300/300 (100%) | 300/300 (100%) |
| **Success threshold** | **-15 dB** | **-15.5 dB** | **-16 dB** | **-15.5 dB** |

How to read it, in two comparisons.

**1. In the modem, at equal SNR** (what the table above shows). Interpolating between measured points, 50% of Messages arrive at about -16.2 (baseline), -16.7 (LDPC), -16.9 (turbo) and -17.0 dB (long convolutional), and 95% at about -15.0, -15.6, -16.0 and -15.9 dB. Against the baseline the gain at 95% is about 0.6 dB for LDPC, 1.0 dB for turbo and 0.9 dB for the long code. The long code's curve is the steepest: it receives more Messages than turbo at -17 dB (143 against 121 of 300, intervals 42.1 to 53.3% and 34.9 to 46.0%, which just overlap) and a hair fewer at -16 dB (283 against 287). Its threshold is -15.5 dB because 283 of 300 at -16 dB is 94.3%, just under the 95% bar (interval 91.1 to 96.4%), so it is nearly level with turbo. **Caution:** at equal SNR its Transmission lasts 9% longer, so it carries about 0.4 dB more energy, which helps it in this comparison.

**2. Code alone, at equal energy per information bit.** `python -m bench.code_curves --code <module:Class> --ebn0-from 1.5 --ebn0-to 3 --frames 800 --seed 1` gives the share of frames lost on white noise (Eb/N0 is the energy per information bit over the noise density, so different rates and lengths are accounted for). The long code is run with `--set` defaults, the others with theirs:

| Eb/N0 | Convolutional (baseline) | LDPC | Turbo | Long convolutional |
| :-- | :-- | :-- | :-- | :-- |
| 1.5 dB | 30.6% | 24.9% | 12.5% | 17.2% |
| 2.0 dB | 16.4% | 7.0% | 2.0% | 4.4% |
| 2.5 dB | 6.0% | 1.1% | 0.1% | 1.2% |
| 3.0 dB | 1.8% | 0.1% | 0.1% | 0.2% |

Per unit of energy, the order is turbo, then the long code and LDPC (the long code ahead at 1.5 and 2.0 dB, level at 2.5 dB), then the baseline. So part of the long code's good showing in the modem comes from its longer Transmission, not from the code alone.

The same command also tells silence from error: `no_answer` counts the lost frames for which the decoder returned nothing, and the rest are frames for which it returned wrong bits. Over the 3,200 frames of the table above (800 at each Eb/N0), 438 convolutional and 118 turbo frames were lost, every one of them with a wrong answer (those decoders always answer, so only the CRC-32 stops them from being delivered); 265 LDPC frames were lost, 263 of them silently; and **all 185 lost frames of the long code were silent: it never returned a wrong word**. So for the LDPC and long codes the decoder itself catches nearly every failure, and the CRC-32 is a second line of defence rather than the only one.

Other points:

- No wrong Message was handed over by any modem in any trial. The CRC-32 is the final check for all four: the LDPC decoder can settle on a wrong codeword (2 of its 265 lost frames above), the turbo and convolutional decoders always return bits, and the long code's decoder gives up instead of answering (0 wrong answers in 185 lost frames).
- The thresholds are steps of 0.5 dB, each known to about 2%, and turbo's and the long code's own values sit on the 95% edge. Quote them as about -16 and -15.5 dB. Read the curves, not the single step; differences under 0.5 dB between candidates are noise.
- These measurements are on white noise only, with no fading, drift, clipping or SSB filter, which may rank the codes differently. A sequential decoder in particular gives up when the signal is weak, which a fading channel makes more likely.
- The turbo interleaver: at 200 bits, shuffles with a spread of 8, 9 or 10 and the 4G polynomial interleaver all lost the same share of frames within the noise of an exploratory simulation (800 frames per point, not kept), so the choice does not matter measurably; spread 8 was kept because it builds instantly for any size. The settings of the long code come from sweeps of `bench.code_curves --set` (see the comment at the top of `long_convolutional.py`).
- The first three measurements were run again with their final code and gave exactly the same counts, point for point; so was the long code's, after the fixes that followed its review.
- An earlier run of the LDPC modem on a grid starting at -19 dB gave the same threshold but did not pair its noise with the baseline's, so it was replaced.

### Speed

`python -m bench.speed` times how long a candidate takes to receive a recording of about 24 s holding one Transmission (5 s of silence in front, 6 s after, noise at -14 dB, shifted by 300 Hz), as the median of 7 receptions, and the time of the code alone. The `speed-*.json` files hold the results with the machine they were measured on, an Intel Core i5-12400F desktop (12 threads); run the command again on the machines you care about. The recordings are a little different in length because the Transmissions are.

| | Baseline | LDPC | Turbo | Long convolutional |
| :-- | :-- | :-- | :-- | :-- |
| Recording | 24.6 s | 24.3 s | 24.6 s | 25.9 s |
| Whole recording | 138 ms, 178 times real time | 119 ms, 203 times | 218 ms, 113 times | 360 ms, 72 times |
| Code alone, clean Frame | about 1 to 2 ms | 0.02 ms (stops at once) | 2.9 ms | 0.17 ms (no backing up) |
| Code alone, soft values that never decode | about 1 to 2 ms | 3.4 ms (50 iterations) | 11.5 ms (8 iterations) | 77 ms (the full budget) |

- Most of the time is not the code: the baseline's code takes 1 to 2 ms of its 138 ms, the rest is the search for the preamble over every start time and audio frequency. All four are far faster than real time. The long code is the slowest, and its decoding time depends on the noise, from 0.17 ms on a clean word to the full budget (77 ms) when it gives up. The modem may try up to three places per recording, so the worst case is the search plus about 3 x 77 ms; the 360 ms above is one recording at -14 dB, not a worst case.
- This is a desktop processor, faster than many laptops, and no laptop was measured: on a laptop several times slower the modems should still receive tens of times faster than real time, but that is an extrapolation, not a measurement.

## Four codes on radio-like channels: turbo ahead under fading

The same four modems on three named channels (`bench/scenarios.py`, `--scenario`), 200 Messages of 12 bytes per SNR, seed 1, hidden start up to 10 s, frequency shift of +-1100 Hz, the same noise and the same start for each trial number across codes. Files: `scenarios/<scenario>-<code>.json` and `.html`, and `scenarios/<scenario>-comparison.html` with the four curves.

- **ssb**: white noise through the 300 to 2,700 Hz band filter of an SSB receiver (grid -18 to -13 dB).
- **hf-fading**: the same plus Rayleigh fading at 1 Hz Doppler (grid -16 to -2 dB).
- **dirty**: hf-fading plus 5 impulses per second of 1 ms at 20 dB over the noise, clipping at 3 times the RMS and 50 ppm of clock drift (grid -16 to -2 dB).

| Level reached | Scenario | Baseline | LDPC | Turbo | Long convolutional |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 95% (the Success threshold) | ssb | -14 | -15 | **-16** | **-16** |
| 95% | hf-fading | not reached | -2 | **-5** | not reached |
| 95% | dirty | -3 | -2 | **-5** | not reached |
| 90% (interpolated) | ssb | -15.1 | -16.0 | **-16.1** | **-16.1** |
| 90% | hf-fading | -5.8 | -10.0 | **-11.5** | -7.0 |
| 90% | dirty | -5.8 | -9.6 | **-11.3** | -5.5 |
| 80% (interpolated) | hf-fading | -8.1 | -11.4 | **-12.4** | -8.9 |
| 80% | dirty | -7.5 | -11.1 | **-12.1** | -8.6 |

Number of Messages received out of 200, selected SNRs (dB):

| Scenario | SNR | Baseline | LDPC | Turbo | Long convolutional |
| :-- | :-- | :-- | :-- | :-- | :-- |
| ssb | -16 | 137 | 180 | 194 | 195 |
| ssb | -17 | 27 | 56 | 72 | 81 |
| hf-fading | -13 | 19 | 116 | 144 | 73 |
| hf-fading | -10 | 111 | 180 | 188 | 156 |
| hf-fading | -5 | 189 | 193 | 191 | 185 |
| dirty | -13 | 9 | 100 | 129 | 59 |
| dirty | -10 | 94 | 173 | 187 | 148 |
| dirty | -5 | 188 | 194 | 191 | 181 |

What it shows:

- **Turbo is first or tied in every scenario.** On ssb it ties with the long code (about 1.5 dB over the baseline at 95%). Under fading it is about 1.5 dB ahead of LDPC and 4 to 6 dB ahead of the long code at 90%.
- **The long code loses its edge under fading.** Its steep white-noise curve flattens: when fading drops the signal, the sequential decoder spends its budget and gives up, so it ends below LDPC.
- **Under fading no code reliably reaches 95%.** Every curve levels off between 94% and 98% even at +SNR, far above the noise (the pilot at +12 dB lost 1 to 2% too). The failures there are not decoding errors but preambles not found after a deep fade, and nothing in the code can fix that. A time interleaver and repetition (ticket #11) are the answer, so for fading, compare codes at 80% and 90%, not at the single 95% bar. The 95% thresholds above for LDPC and turbo (-2 and -5 dB) are crossings of a plateau, not signs of a weak code.
- **No wrong Message in any trial** (0 false receptions over all 12 measurements).
- Same caveats as above: the long code's transmission is 9% longer (about 0.4 dB), counts have an interval of a few percent at 200 trials, and differences under 0.5 dB are noise.
- Reproduce one: `python -m bench.threshold --modem vibemodem.core.turbo_modem:TurboModem --scenario hf-fading --snr-from -16 --snr-to -2 --snr-step 1 --trials 200 --message-bytes 12 --seed 1 --max-lead-in-s 10 --tail-s 1 --freq-offset-from -1100 --freq-offset-to 1100 --out ...` (ssb uses `--snr-from -18 --snr-to -13`).
