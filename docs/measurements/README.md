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
- **Under fading no code reliably reaches 95%.** Every curve levels off between 94% and 98% even at +SNR, far above the noise (the pilot at +12 dB lost 1 to 2% too). The failures there are not decoding errors but preambles not found after a deep fade, and nothing in the code can fix that. Ticket #11 measured an interleaver and repetition (next section): neither moves the plateau, so for fading, compare codes at 80% and 90%, not at the single 95% bar. The 95% thresholds above for LDPC and turbo (-2 and -5 dB) are crossings of a plateau, not signs of a weak code.
- **No wrong Message in any trial** (0 false receptions over all 12 measurements).
- Same caveats as above: the long code's transmission is 9% longer (about 0.4 dB), counts have an interval of a few percent at 200 trials, and differences under 0.5 dB are noise.
- Reproduce one: `python -m bench.threshold --modem vibemodem.core.turbo_modem:TurboModem --scenario hf-fading --snr-from -16 --snr-to -2 --snr-step 1 --trials 200 --message-bytes 12 --seed 1 --max-lead-in-s 10 --tail-s 1 --freq-offset-from -1100 --freq-offset-to 1100 --out ...` (ssb uses `--snr-from -18 --snr-to -13`).

## Occupied bandwidth, M-FSK sweep, interleaver and repetition (ticket #11)

**Occupied bandwidth** is the span between the outermost audio frequencies where the averaged power spectrum of the modem's output is within 20 dB of its peak, averaged over random Messages. `python -m bench.bandwidth --modem vibemodem.core.turbo_modem:TurboModem --set tones=8 --set symbol_ms=160` measures it for any modem. The band runs from the lowest to the highest frequency above that level (not necessarily contiguous), so a stray spectral line widens it. The tone spacing is not a separate parameter: it is 1 / symbol duration (orthogonal tones), so the sweep covers tones and symbol duration. The default waveform (8 tones, 80 ms) occupies about 124 Hz, a little over the 100 Hz budget.

### Sweep on white noise (turbo, 100 trials, step 1 dB, seed 1)

`python -m bench.sweep --modem vibemodem.core.turbo_modem:TurboModem --snr-from -26 --snr-to -8 --snr-step 1 --trials 100 --jobs 6 --out docs/measurements/sweep/white-turbo.json` (2.5 h). Thresholds in dB; "energy" is the 95% threshold plus 10 log10(airtime), the energy sent, which is what compares waveforms of different length.

| Tones | Symbol | Bandwidth | Airtime | 95% | 90% | 80% | Energy at 95% |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 2 | 80 ms | 26 Hz | 35 s | -14 | -15 | -16 | +1.5 |
| 2 | 320 ms | 7 Hz | 142 s | -19 | -20 | -21 | +2.5 |
| 4 | 80 ms | 55 Hz | 19 s | -17 | -17 | -17 | -4.2 |
| 4 | 320 ms | 15 Hz | 76 s | -22 | -23 | -23 | -3.2 |
| **8** | **80 ms (default)** | 124 Hz | 13.6 s | -16 | -16 | -16 | -4.7 |
| 8 | 160 ms | 64 Hz | 27 s | -19 | -19 | -19 | -4.7 |
| 8 | 320 ms | 31 Hz | 54 s | -22 | -22 | -22 | -4.6 |
| 16 | 80 ms | 226 Hz | 10.8 s | -15 | -15 | -15 | -4.7 |
| 16 | 160 ms | 114 Hz | 21.6 s | -18 | -18 | -18 | -4.7 |
| 16 | 320 ms | 57 Hz | 43 s | -21 | -21 | -21 | -4.6 |
| 16 | 40 ms | 448 Hz | 5.4 s | not reached | -8 | -12 | |

The bandwidth is measured on 3 Messages with seed 1. (All 16 combinations, including 8 tones of 40 ms (213 Hz, -12 dB), are in `docs/measurements/sweep/white-turbo.json`.)

- **A longer symbol lowers the threshold 3 dB per doubling, but only because the Transmission lasts longer.** For 8 and 16 tones the energy column is constant (-4.6 to -4.7 dB): at equal energy the waveforms are equivalent. The gain is real for the operator (a weaker signal is received) and costs airtime.
- **8 tones is the best number**: 2 tones is 6 dB worse in energy, 4 tones about 0.5 to 1.5 dB worse, 16 tones ties 8 but is twice as wide at the same symbol duration.
- **Inside 100 Hz**: every 8-tone point of 160 ms or more fits: 160 ms (64 Hz, -19 dB, 27 s) is the shortest Transmission that does, 320 ms (31 Hz, -22 dB) takes 54 s. 4 tones of 160 ms (29 Hz, -19 dB) needs 38 s for the same threshold. The default, at 124 Hz, is over the budget.
- Caveat: with very long Transmissions the recording is mostly signal, which degrades the receiver's noise estimate; read the 142 s and 76 s rows with that in mind.

### The same on hf-fading (turbo, 100 trials, step 2 dB; only 4 and 8 tones of 80 to 320 ms)

| Tones | Symbol | 95% | 90% | 80% | Best rate at high SNR |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 8 | 80 ms | -4 | -10 | -12 | 92-99% |
| **8** | **160 ms** | **-14** | -14 | -16 | 98-100% |
| 8 | 320 ms | -16 | -16 | -16 | 100% |
| 4 | 160 ms | not reached | -12 | -16 | 90-94% |
| 4 | 320 ms | not reached | -16 | -16 | 90-96% |
| 4 | 80 ms | not reached | not reached | -4 | 75-82% |

With 8 tones and symbols of 160 ms or more the fading plateau disappears: the 95% bar is reached 10 dB lower than the default. With 4 tones fading still costs 5 to 10% of the Messages. Files: `docs/measurements/sweep/hf-fading-turbo.json`.

### Interleaver and repetition (turbo, 80 ms, 200 trials, seed 1)

| Variant (hf-fading) | 80% | 90% | 95% |
| :-- | :-- | :-- | :-- |
| none | -12 | -11 | -5 |
| interleaver | -13 | -12 | -5 |
| repetition x2 (twice the airtime, about 3 dB of energy) | -16 | -11 | not reached |
| both | -16 | -12 | not reached |

Measured on the named channels only (no white-noise run), at 8 tones and 80 ms. dirty is the same as hf-fading to within 1 dB; ssb is unchanged by the interleaver (-16 dB).

- The interleaver gains about 1 dB on the steep part (72% against 33.5% at -14 dB) and does nothing for the plateau (94-95% before and after).
- Repetition x2 lowers the 80% level by 4 dB, but it sends twice as long: at equal energy it is a draw, and the plateau drops to 91-93% because a longer Transmission gives a deep fade more chances to hide the Preamble.
- The plateau is therefore the Preamble being missed, as suspected. The wider answer found here is not a longer Preamble but longer symbols (previous section). A doubled Preamble is left as an option, not needed for v1.

## GFSK candidate against M-FSK (ticket #12)

> The GFSK code of this section was removed from the repository after ticket #13 chose M-FSK (ADR 0004). It is in git history at commit `a891dee`; the commands below need that checkout.

`GfskModem` (`vibemodem.core.gfsk_modem:GfskModem`) is binary GFSK with the turbo code and the same Frame, preamble length (2.56 s), interleaver and repetition as the M-FSK modem. Settings: `baud`, `h` (modulation index, 0.5 is GMSK), `bt` (Gaussian filter bandwidth-time product, `null` = no filter). The receiver is written for this project and is not coherent: per bit it measures the energy at two frequencies and passes their difference to the Code as a soft value. Because a bit-long window cannot tell two tones closer than the baud rate apart, the measuring points are at least baud/2 either side of the carrier, which for `h` below 1 is farther out than the tones themselves.

Sweep on white noise (turbo, 100 trials, step 1 dB, seed 1, same procedure as the M-FSK sweep): `python -m bench.sweep --modem vibemodem.core.gfsk_modem:GfskModem --grid baud=25,50,100 --grid h=0.5,1.0 --grid bt=0.3,0.5,null --snr-from -20 --snr-to -6 --snr-step 1 --trials 100 --jobs 6 --out docs/measurements/sweep/gfsk-white-turbo.json`. Thresholds in dB; "energy" is the 95% threshold plus 10 log10(Transmission length).

| Baud | h | bt | Bandwidth | Transmission | 95% | 90% | Energy at 95% |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 25 | 1 | none | 45 Hz | 19 s | -15 | -15 | -2.2 |
| 25 | 1 | 0.5 | 40 Hz | 19 s | -14 | -15 | -1.2 |
| 25 | 1 | 0.3 | 37 Hz | 19 s | -13 | -13 | -0.2 |
| 25 | 0.5 | none | 32 Hz | 19 s | -12 | -12 | +0.8 |
| 25 | 0.5 | 0.5 | 29 Hz | 19 s | -10 | -11 | +2.8 |
| 25 | 0.5 | 0.3 | 26 Hz | 19 s | -9 | -9 | +3.8 |
| 50 | 1 | none | 81 Hz | 10.8 s | -12 | -12 | -1.7 |
| 50 | 1 | 0.5 | 67 Hz | 10.8 s | -11 | -12 | -0.7 |
| 50 | 0.5 (GMSK) | 0.5 | 59 Hz | 10.8 s | -8 | -8 | +2.3 |
| 100 | 1 | none | 136 Hz | 6.7 s | -9 | -9 | -0.8 |
| 100 | 0.5 | none | 127 Hz | 6.7 s | -6 | -6 | +2.2 |
| 100 | 0.5 | 0.5 | 117 Hz | 6.7 s | not reached | not reached | |

(All 18 are in `docs/measurements/sweep/gfsk-white-turbo.json`.)

On hf-fading (100 trials, step 2 dB, `docs/measurements/sweep/gfsk-hf-fading-turbo.json`):

| Baud | h | bt | 95% | 90% | 80% |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 25 | 1 | none | not reached (92-97%) | -10 | -12 |
| 25 | 1 | 0.5 | not reached | -10 | -10 |
| 50 | 1 | none | -6 | -8 | -8 |
| 50 | 1 | 0.5 | -6 | -8 | -8 |

Only h = 1 was run under fading; GMSK (h = 0.5) was not, since it is already 3 to 4 dB behind on white noise. The M-FSK figures quoted below are from the sweep above (8 tones, 80 ms: 95% at -4, 90% at -10, 80% at -12; 160 ms: -14, -14, -16).

What it shows:

- **GFSK is behind M-FSK at the same band and energy.** The best GFSK point (25 Bd, h = 1, no filter: 45 Hz, -15 dB, 19 s, energy -2.2 dB) is about 2.5 dB worse in energy than 8-FSK (-4.7 dB), and 4 dB short of the 8-tone 160 ms point (64 Hz, -19 dB, 27 s). That is the textbook cost of choosing between two frequencies per bit without following the phase, instead of one of eight.
- **GMSK (h = 0.5) is the weakest setting here**: 3 to 4 dB behind h = 1 at the same baud rate and filter. A non-coherent receiver cannot use the narrower tone spacing; a coherent one (Viterbi over the phase trellis) could, but it is more fragile under fading and was left out. This is the receiver's limit, not necessarily the modulation's.
- **The Gaussian filter trades 1 to 2 dB of threshold per step (none, 0.5, 0.3) for 7 to 19% of bandwidth** (at 50 Bd with h = 1 the two filters occupy the same 67 Hz), and costs nothing visible under fading.
- **Under fading** the fastest setting does best at 95% (50 Bd reaches -6 dB, against -4 dB for the default M-FSK) because its Transmission is short, but the M-FSK 8-tone points with symbols of 160 ms or more reach -14 dB and above 95% at high SNR; slow GFSK stays on the 92-97% plateau.
- The bandwidth budget is the same ~100 Hz as for M-FSK: at 100 Bd every GFSK setting is over it (117 to 136 Hz) and most do not reach 95%. The soft value passed to the Code is the difference of the two energies divided by the noise energy, not a calibrated log-likelihood ratio; the turbo code does not need one.
- Same caveats as for the M-FSK sweep (100 trials per point, band from 3 Messages, long Transmissions fill the recording and degrade the noise estimate).

## The three Presets (ticket #13)

Each Preset measured as a modem built for it (`--preset`), with the turbo code, interleaved coded bits, 100 trials, seed 1, Messages of 12 bytes hidden up to 10 s into the recording, frequency shift of -1100 to +1100 Hz, 1 dB steps on white noise and 2 dB steps on hf-fading. Command, for each Preset and scenario: `python -m bench.threshold --modem vibemodem.core.turbo_modem:TurboModem --preset fast --scenario white --snr-from -17 --snr-to -7 --snr-step 1 --trials 100 --message-bytes 12 --max-lead-in-s 10 --tail-s 1 --freq-offset-from -1100 --freq-offset-to 1100 --out docs/measurements/presets/white-fast.json`. The band is `python -m bench.bandwidth --preset fast --messages 3` (same 3 Messages as the sweep). Files: `docs/measurements/presets/`.

| Preset | Band at -20 dB | Transmission | White 95/90/80% | Energy at 95% | hf-fading 95/90/80% |
| :-- | :-- | :-- | :-- | :-- | :-- |
| max-range (8 tones, 320 ms) | 29 Hz | 54.4 s | -22 / -22 / -22 | -4.6 | -16 / -16 / -18 |
| **standard** (8 tones, 80 ms) | 107 Hz | 13.6 s | -16 / -16 / -16 | -4.7 | -8 / -12 / -12 |
| fast (8 tones, 40 ms) | 212 Hz | 6.8 s | -13 / -13 / -13 | -4.7 | not reached / 0 / -8 |

- **No Message was ever accepted wrongly**, in any of the roughly 5,900 trials.
- **Equal energy again**: -4.6 to -4.7 dB for the three Presets on white noise. The Presets trade airtime for sensitivity, 3 dB per doubling of the symbol.
- **Standard is 107 Hz, not 124 Hz.** The earlier figure was for the same waveform without interleaving. We do not know the cause: the band is an average of only 3 Messages and depends on their content, so read 107 Hz as the figure measured, not as a proven gain.
- **The interleaver on hf-fading** gives about 1 to 2 dB at 90% (standard: -12 dB, against -10 to -11 without), as in the interleaver table above. The 95% level moved from -4 to -8 dB, but the standard curve is flat at 93 to 99% from -12 dB up, so that move is plateau noise, not a gain. Max-range at -16 dB equals the non-interleaved 320 ms result.
- **Fast under hf-fading** passes 90% only at 0 dB and never reaches 95% (89 to 94% from -4 to 0 dB): 6.8 s is too short to ride out the fades.
- The earlier sweep tables (white-turbo, hf-fading-turbo, GFSK) were measured without interleaving.

## Signals found but not read, and false alarms (ticket #18)

The receiver reports a **Signal it found whole but could not read** (its Preamble matched, its Frame did not pass the checksum), so that a Transmission that was heard but lost is not taken for silence. A report is a false alarm when there was only noise. The search keeps every Preamble match of 7 or more (it costs one failed decode), so the question is the score above which a lost Signal is worth telling the operator about.

**Scores** (turbo, 60 recordings of 120 s of white noise per Preset for the noise, 40 Transmissions at the Success threshold of the Preset for the Signal; best Preamble match of each):

| Preset | Matches in noise alone (3 hours of it) | Best match of a Signal at the Success threshold (minimum, 5th percentile, median) |
| :-- | :-- | :-- |
| max-range (-22 dB) | 1 match, 7.2 | 15.1, 16.0, 19.5 |
| standard (-16 dB) | 6 matches, 7.0 to 7.5 | 15.4, 16.4, 19.4 |
| fast (-13 dB) | 13 matches, 7.0 to 7.7 | 15.7, 18.0, 21.5 |

Noise only ever scores between 7 and 7.7, a Signal at the Success threshold never under 15: **a lost Signal is reported from a score of 10**, which leaves a margin on both sides (`UNDECODED_MIN_SCORE`). A Signal about 3 to 4 dB below the Success threshold may match under 10 and not be reported.

**Reports in noise alone**, counted over independent recordings of 120 s (`python -m bench.false_alarms --preset fast --hours 10 [--ssb]`, files in `docs/measurements/false-alarms/`):

| Preset | White noise, from a score of 7 | SSB noise (300-2,700 Hz), from 7 | From a score of 10, white or SSB |
| :-- | :-- | :-- | :-- |
| max-range | 2.1 per hour | 1.9 per hour | 0 in 20 hours |
| standard | 3.5 per hour | 3.6 per hour | 0 in 20 hours |
| fast | 3.6 per hour | 3.8 per hour | 0 in 20 hours |

The application listens to a sliding window, which sees the same noise again and again, and it lists a Signal once (the same time and frequency, to two symbols and a tone spacing, count as one); so what an operator sees is at most these rates. No Message was ever read from noise (CRC-32), in any of the 80 hours. The first row of numbers was measured before the threshold of 10 existed; the second after it.


## Field trial protocol

1. On the receiving computer: Settings, Advanced settings, switch "Keep" on (clear the stored
   receptions first), choose the Preset, start listening.
2. On the sending computer: choose the same Preset and send about ten Messages of various sizes
   (a few characters, 17, 40, 200 bytes), at 1 and at 3 copies. Write them, one per line, in
   `sent.txt` (the page's conversation can be copied).
3. Back on the receiver, after the last Message: `python -m bench.field_check
   ~/.local/share/vibemodem/receptions sent.txt --preset standard`, then again with `--redecode`.
4. Repeat for each Preset, clearing the stored receptions between them.

## Cable trial (ticket #21)

Two computers, an audio cable from the output of the sender to the input of the receiver (use the line-in or a mic input with a low level; a headphone output into a microphone input needs an attenuator).

1. Receiver: Advanced settings, clear the stored receptions, switch "Keep" on, choose the Preset, listen.
2. Sender: `python -m bench.cable_trial send --preset fast --output "<part of the device name>" --per-level 20`
   (`--snr=-16,-14,...` to choose the levels; the default is from 2 dB under the simulator's threshold to 8 dB over it). Times for the default 6 levels of 20 Messages: fast about 20 min, standard about 35 min; for max-range use `--per-level 10` (about 60 min).
3. Receiver, at the end: `python -m bench.cable_trial report ~/.local/share/vibemodem/receptions --preset fast --per-level 20` (same `--snr` and `--per-level` as the sender).
4. Clear the stored receptions, change the Preset on both sides, repeat. Keep the folder of receptions of each Preset (copy it aside) for replay with `bench.replay`.

## Real-world trials (tickets #21 and #28)

The whole story, with charts, is in two reports built from the stored results:

- `docs/measurements/project-report.html` (French): the project from the goal to the trials, for a talk.
- `docs/measurements/cable-trial/report.html` (English): the cable trial alone. Data: `cable-trial/results.json`
  and the raw reports `cable-trial/*.txt`. Regenerate with `python -m bench.project_report` and
  `python -m bench.cable_report`.

Summary (95 % of Messages received, white noise added digitally at a known SNR, laptop to Scarlett 2i2 by cable):

| Preset | Simulator | Cable |
| :-- | :-- | :-- |
| fast | -13 dB | -13 dB |
| standard | -16 dB | -16 dB |
| max-range | -22 dB | -22 dB (run 5) |

All three Presets match the simulator. Max-range appeared to lose 3 to 4 dB in runs 1 and 2, and the live receiver
to read fewer Messages than an offline decoding in run 4: the receiving application had deleted its oldest kept
receptions beyond its 200 MB limit, which are the lowest SNRs, sent first (the kept files were numbered from 25, 36
and 15). Run 5, with the limit raised to 3,000 MB and nothing deleted: 0, 6, 10, 10, 10, 10 of 10 from -24 to -19 dB
(`cable-trial/max-range-run5.txt`). `bench.cable_trial report` now warns when receptions were deleted; raise the limit
(`limit_mb` of `/api/storage`) before a trial. The raw reports of runs 1 and 2 keep the wrong zeros.
