# One Fragment per Frame, each Frame with its own Preamble

A Message is split into Fragments of up to 17 bytes, and each Fragment is sent as the body of one Frame: three header bytes (Message identifier, Fragment index, number of Fragments) and the bytes of the Message. The Frame already carries the length of its body and a CRC-32 over it, so the header is protected like the data. A Transmission is the Frames one after another, each with its own Preamble, so each can be found and decoded on its own. A Message holds up to 255 Fragments (4,335 bytes), and no Transmission lasts more than 30 minutes, copies included.

The sender can send the whole set of Fragments several times (`copies`, off by default, at most 8). Each copy starts at another Fragment, so that one run of lost Frames does not meet the same Fragments in each copy (only the order is tested, not the fading).

The receiver gives every Fragment it decodes to a `Reassembler`. It delivers a Message once, whatever the order and the number of copies heard, and, when the reception is over, reports a Message heard in part as `Incomplete` with the Fragments that were received and the indexes that are missing. It never presents part of a Message as the Message. A Message is known by its identifier and its number of Fragments; the identifier is one byte (`random_message_id` draws one different from the previous Message's; the sender passes it in). Several recordings of one long Transmission are received with one shared `Reassembler`.

## Why

- **A Preamble per Frame** costs 19% of the airtime (32 symbols for 138 of data) but a fade or a burst of interference loses only the Frames it hits, the receiver needs nothing it did not already have (a search for a Preamble at every time and frequency), and clock drift between two sound cards (about 90 ms over 30 minutes at 50 ppm, more than a 40 ms symbol) is re-measured at every Frame. A single Preamble followed by Frames would save 19% of the airtime, but a missed Preamble would lose the whole Message and the receiver would have to track drift.
- **The header is in the Frame's body** rather than in a layer of its own: the Frame code, the CRC and the modems are unchanged and a Frame that is received is a Fragment that was checked.
- **Incomplete Messages are reported**, with what was received, because the Fragments that arrive are individually checked and a text message cut in a place is often still readable. Gaps are shown as gaps.

## Consequences

- Capacity is 17 bytes per Frame, about 1.25 bytes per second in the standard Preset (2.2 kB in 30 minutes).
- **Known limitation, reduced:** a finished Message is remembered by (identifier, number of Fragments) and by the content of its Fragments, for the last 64 Messages. A Message that reuses one of those identifiers with other content is delivered as a new one (it showed in testing that taking it for a copy lost Messages once a few dozen had been heard: with one byte of identifier the chance of a clash is about 1 in 4 after 64 Messages). What remains: a Message that is exactly the same as a recent one and reuses its identifier is taken for a copy (1 chance in 256 for each repeat of the same text), a Message whose first Fragments equal those of a recent one is complete only when its first Fragments are heard again, and Fragments of two Messages with the same identifier and number of Fragments can be mixed if their Fragments never share an index. Possible remedies, to measure later: expire the memory after an hour, tell stations apart by audio frequency, or lengthen the identifier to two bytes (one byte of the 17 of each Fragment).
- A receiver searches a recording for as many Frames as would fill it. Recordings are limited to 10 minutes: a 30-minute Transmission must be received in pieces, which the audio layer will do.
- Optimisations to try later: a shorter Preamble after the first Frame, longer Frames (another code than the 200-bit turbo code, which changes the protocol), a repetition of only the Frames that were missing.
- The noise floor the receiver assumes was raised from 1e-6 to 1e-3 of the loudest signal. A noiseless recording of the fast Preset could otherwise show the spectral leakage of its own signal, far from its tones and tens of dB down, as a Preamble (the leakage was not measured, only its effect). On the standard Preset at -17 dB, 100 trials, the same 45 Messages were received with floors of 1e-6, 1e-5, 1e-4 and 1e-3; the full thresholds were not re-measured. The higher floor also keeps the soft values of a burst of loud noise from being extreme, so the code now recovers a 60-symbol burst of full-scale noise that it gave up on before (the test of damaged audio uses 110 symbols).

## Message size limits (ticket 15)

A Transmission is the Frames one after another with no silence, so its airtime is exactly Fragments x copies x the duration of a Frame, and the estimate equals the length of the generated audio to the sample. A Frame lasts 170 symbols (32 of Preamble, 138 of data): 54.4 s in max-range, 13.6 s in standard, 6.8 s in fast. The ceiling is 30 minutes, set by the owner as a starting figure (a user setting, bounded by memory and disk, may replace it later); `transmit` refuses a Message that would pass it, or 255 Fragments, with `MessageTooLong`, before making more than the first Frame.

| Preset | Largest Message, 1 copy | 2 copies | 8 copies |
| :-- | :-- | :-- | :-- |
| max-range | 561 bytes (33 Fragments, 1,795 s) | 272 | 68 |
| standard | 2,244 bytes (132 Fragments, 1,795 s) | 1,122 | 272 |
| fast | 4,335 bytes (255 Fragments, 1,734 s) | 2,244 | 561 |

The refusal says how long the Transmission would take, the largest Message that fits, and suggests a shorter Message, fewer copies if that is enough, and the faster Presets that would carry it (their Frame duration scaled by the symbol duration).
