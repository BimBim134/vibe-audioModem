# Three Presets, all 8-FSK with interleaved turbo-coded bits

The v1 modulation is non-coherent 8-FSK (tones 1 / symbol duration apart, continuous phase) for all three Presets. The turbo code (ADR 0003) protects one 412-bit Frame, and its coded bits are interleaved over the whole Transmission. The Presets differ only by the symbol duration:

| Preset                 | Symbol | Band at -20 dB | Transmission | Success threshold, white noise | Success threshold, hf-fading |
| :--------------------- | :----- | :------------- | :----------- | :----------------------------- | :--------------------------- |
| max-range              | 320 ms | 29 Hz          | 54 s         | -22 dB                         | -16 dB                       |
| **standard** (default) | 80 ms  | 107 Hz         | 13.6 s       | -16 dB                         | -8 dB                        |
| fast                   | 40 ms  | 212 Hz         | 6.8 s        | -13 dB                         | 90% at 0 dB, 95% not reached |

Thresholds are the lowest SNR in 2,500 Hz at which 95% of 100 Messages are received, same procedure as the M-FSK sweep (`docs/measurements/README.md`, "The three Presets"), on white noise and on the hf-fading channel only (not the ssb or dirty ones). No wrong Message was accepted in any trial.

## Why

- **8-FSK over the other numbers of tones, and M-FSK over GFSK.** At equal energy sent, 8 and 16 tones tie, 4 tones are 0.5 to 1.5 dB behind and 2 tones 6 dB behind; 8 tones is half as wide as 16 at the same symbol duration. The low-baud GFSK candidate (non-coherent receiver, tunable baud rate, modulation index and Gaussian filter) was 2.5 dB or more behind M-FSK at equal energy and band, and GMSK (h = 0.5) 3 to 4 dB behind h = 1. Its code was removed from the repository after the measurement and lives in git history (commit `a891dee`); the measurements stay in `docs/measurements/`. A coherent GFSK receiver was not tried.
- **A longer symbol only buys energy.** Doubling the symbol duration lowers the threshold by 3 dB, the Transmission lasts twice as long, and the energy sent (threshold plus 10 log10 of the duration) stays at about -4.7 dB for all three Presets. So the Presets are a choice of how long to stay on the air, not of efficiency.
- **Standard is 80 ms.** It was the owner's choice for the default. With the coded bits interleaved it occupies 107 Hz at -20 dB, a little over the 100 Hz budget; without interleaving the same waveform measured 124 Hz. We do not know why the band differs (the band is an average of 3 Messages and depends on their content), so 107 Hz is the figure to quote, not a guaranteed improvement. A 120 ms symbol would fit under 100 Hz, but was not measured.
- **Interleaving in every Preset.** It costs no airtime and gains about 1 dB on the steep part of the fading curve (the 80% and 90% levels). It does not move the 95% level, which sits on a plateau set by the Preamble being missed after deep fades: the 95% threshold of the standard Preset moved from -4 to -8 dB between the two measurements, but the curve is flat at 93 to 99% there, so that difference is noise.
- **Max-range** gets 320 ms, the longest tested: the narrowest band and the lowest thresholds on both channels. **Fast** keeps 8 tones at 40 ms, as wide as 16 tones at 80 ms but not worse in energy and with a shorter Transmission.

## Consequences

- Fast does not reach 95% under hf-fading in the measured range: its 40 ms symbols and 6.8 s Transmission lose too many Messages to deep fades (89 to 94% from -4 to 0 dB). Its use is for good channels.
- The interleaver changes the signal on the air: the default modem's Transmission is no longer the one measured before ticket #11. The earlier tables in `docs/measurements/` were measured without it.
- A modem is built for one Preset and refuses the others; the receiver must be told the Preset. Detecting it automatically (trying all three) is a later decision.
- Every Preset sends one Frame of at most 20 bytes. Longer Messages need Fragments, which no Preset changes yet.
- Review these values after the field campaign.
