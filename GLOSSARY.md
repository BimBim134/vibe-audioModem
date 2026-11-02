# Vibe AudioModem

A one-way, weak-signal data modem for radio amateurs: it carries short messages through an audio channel (typically the audio passband of an SSB radio) and aims to decode them as close to the noise floor as possible, with no return channel.

## Language

**Message**:
The text or bytes a user wants to send, before any coding or framing.
_Avoid_: payload, data, packet

**Transmission**:
One continuous emission on the air of a Message, including any repetitions of it.
_Avoid_: send, burst, session

**Frame**:
The smallest unit on the air that the receiver can decode and verify on its own; it carries one Fragment and its integrity check.
_Avoid_: packet, codeword, chunk

**Fragment**:
The slice of a Message carried by one Frame.
_Avoid_: chunk, piece, segment

**Signal**:
What the receiver detects at a given audio frequency and time: a Transmission as seen from the receiving side.
_Avoid_: carrier, track, peak

**PHY profile**:
The full set of modulation and coding parameters that define how a Transmission is formed on the air.
_Avoid_: mode, config, waveform settings

**Preset**:
A named PHY profile the user picks from the interface, trading range against speed and message size.
_Avoid_: mode, setting

**Success threshold**:
The lowest signal-to-noise ratio, measured in a 2,500 Hz reference noise bandwidth, at which at least 95% of test Messages are received correctly. The project's measure of how close to the noise floor a PHY profile works.
_Avoid_: sensitivity, range, SNR limit

**Reception**:
One Message found in the audio by a receiver, together with how well it was received (estimated SNR, frequency offset, synchronisation score).
_Avoid_: decode result, packet

**Candidate**:
A modem design under evaluation on the bench, scored by its Success threshold.
_Avoid_: model, algorithm

**Preamble**:
The known sequence of symbols at the start of a Transmission, which the receiver searches for at every start time and audio frequency to find a Signal.
_Avoid_: sync word, beeper, header

**Code**:
The error-correcting code of a PHY profile: it adds redundancy to a Frame so that a receiver can repair bits the noise damaged.
_Avoid_: FEC, ECC

**Soft value**:
What a demodulator says about one coded bit: positive for "probably 0", negative for "probably 1", larger when it is surer. A Code decodes from soft values rather than from bits already decided.
_Avoid_: LLR, probability

**Occupied bandwidth**:
The span of audio frequencies, in Hz, that holds a modem's output down to 20 dB below its strongest part. What a Signal costs in the shared band, compared against the 100 Hz budget.
_Avoid_: width, footprint

**Interleaver**:
The step that spreads the coded bits of a Frame over the whole Transmission, so that a fade or an impulse damages scattered bits that the Code can repair instead of a block it cannot.
_Avoid_: scrambler, shuffle
