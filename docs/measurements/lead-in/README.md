# Lead-in on the bench (ticket #45)

`bench/lead_in.py` sends the same Message through white noise with no Lead-in and with a 500 ms
Lead-in (a plain tone at the lowest tone, 1450 Hz, as loud as the Signal), 60 Transmissions per
case, at each Preset's success threshold and 2 dB above. The noise is set against the Signal
alone, so both cases have the same noise. Results: `lead-in-500ms.json`.

| Preset | SNR (dB) | Received without | Received with | Extra Signals without | Extra Signals with |
| :-- | --: | --: | --: | --: | --: |
| max-range | -22 | 59/60 | 59/60 | 1 | 1 |
| max-range | -20 | 60/60 | 60/60 | 0 | 0 |
| standard | -16 | 59/60 | 60/60 | 1 | 0 |
| standard | -14 | 60/60 | 60/60 | 0 | 0 |
| fast | -13 | 60/60 | 59/60 | 0 | 1 |
| fast | -11 | 60/60 | 60/60 | 0 | 0 |

The differences are one Transmission either way, in both directions: nothing separates the two
cases at this number of trials. The Success thresholds are unchanged and the Lead-in does not
add false alarms. The false-alarm rate in noise alone (`docs/measurements/false-alarms/`) cannot
change: the Lead-in exists only in a Transmission the station sends.

Not measured: a receiver that misses the start of the Lead-in on a real radio (a squelch that
opens late). The test suite covers the case of the first 200 ms missing.
