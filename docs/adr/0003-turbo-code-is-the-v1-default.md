# Turbo code as the v1 default error-correcting code

The v1 modem uses the turbo code (two recursive 8-state convolutional codes, spread interleaver, max-log-MAP decoding) as its default error-correcting code. The other three, the convolutional baseline, the LDPC code and the long-constraint convolutional code with Fano decoding, stay in the repository behind the common `Code` interface, tested and measurable, as candidates to revisit; none is removed.

We compared the four on the same bench: white noise, SSB-filtered noise, HF fading, and a "dirty" channel with fading, impulses, clipping and clock drift (`docs/measurements/README.md`). Turbo reached the lowest Success threshold on white noise (-16 dB, tied with the long code on the SSB-filtered channel) and was ahead in both fading scenarios by about 1.5 dB over LDPC and 4 to 6 dB over the long code at 90% of Messages received. The long code, steepest on white noise, loses under fading because its sequential decoder gives up. LDPC is the fastest to decode and abstains rather than answering wrong, but is behind turbo everywhere.

## Consequences

- Turbo has no wrong-word guard of its own: it always answers, so the CRC-32 of the Frame is the only barrier against a wrong Message. It held in every trial (no false reception across all measurements); the field campaign should keep counting them.
- Turbo is slower than LDPC (about 113 times real time against 203 on a desktop processor) and fixes the transmission at 412 coded bits. Changing its interleaver or settings changes the protocol.
- Under fading no code reaches 95% reliably; the plateau comes from the preamble not being found after deep fades. This decision is to be reviewed once the interleaving and repetition of ticket #11 exist, because they may change the ranking under fading, and again if the field campaign contradicts the bench.
