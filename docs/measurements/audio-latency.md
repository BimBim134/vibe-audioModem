# Audio latency and TX blanking

TX blanking (ticket #49) silences the input from the start of playback until the end of playback,
plus the **output latency** the audio library reports, plus a **margin** (250 ms by default, in
the Advanced settings).

## What is measured, and where

| What | How | Status |
|---|---|---|
| Round trip of a sound card (output to input) | `bench/measure_audio_latency.py`, with a cable from the output to the input of the interface (the Scarlett at home) | **To do** |
| Tail of a real radio (PTT release, squelch tail) | In the field with a borrowed interface, ticket #23 | **To do** |

The round trip is the output latency plus the input latency. The output latency alone is what the
application adds to the end of playback; the input latency is already inside the margin. Compare
the round trip with the output latency the library reports (printed by the script) to see how
much of the 250 ms margin is left for the radio.

## Results

_Nothing measured yet. Add one row per interface: date, interface, host API, round trip (min /
median / max), output latency reported._
