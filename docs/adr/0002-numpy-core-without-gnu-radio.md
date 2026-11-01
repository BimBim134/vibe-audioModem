# DSP core in pure NumPy/SciPy, no GNU Radio

The new modem's core turns bytes into audio samples and audio samples into messages using NumPy/SciPy only; audio device access goes through a separate thin layer. GNU Radio is dropped from the application. The weak-signal design (correlation sync over time and frequency, soft-decision decoding, custom FSK demodulation) needs none of its blocks, and GNU Radio is the heaviest dependency to install for non-technical users on Windows and macOS. The prototype's GNU Radio Companion flowgraphs remain readable under the tag `legacy-v0` and can still be opened as an exploration tool.

## Consequences

Decoder speed is now our responsibility: the target is real-time or faster on an ordinary laptop in plain Python/NumPy, to be checked on the measurement bench before more is built on top.
