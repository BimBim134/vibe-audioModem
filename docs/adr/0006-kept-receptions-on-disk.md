# Kept receptions: a WAV and a JSON per Frame, in a folder the page cannot choose

When the operator asks for it (off by default), the application keeps each Frame it reads and each Signal it finds but cannot read: a WAV of the sound (16-bit mono, 48 kHz, the Frame with 3 seconds around it, cut on the grid of the search of the window it came from) and a JSON of the same name with the figures (schema version, Preset, the modem to replay it with, frequency, SNR, synchronisation score, Message identifier and Fragment index, time, where the Frame starts in the WAV). A bench command, `python -m bench.replay FOLDER`, decodes them again and tells which give a different result.

## Why

- **Replaying is how real recordings tune the decoder.** A Frame read is expected to give the same Message, the same frequency (to 1 Hz) and the same SNR (to 1 dB); a Signal lost is expected to stay lost. Cutting the piece on the search grid of its window, and keeping the sound within full scale, made 30 of 30 weak receptions replay identically (-14 dB in standard, -10 dB in fast, -20 dB in max-range); without the alignment a piece cut anywhere read 1.5 dB lower.
- **Two plain files, JSON written last by renaming**: a reception without its JSON is not complete and is deleted at the next save; the names begin with the time in UTC, so "oldest first" is the order of the names, and a file that is not ours (not named like ours, a link, unreadable, not an object) is neither counted nor read nor deleted.
- **The folder is fixed per user** (by the platform's habits, or `--receptions-dir` at launch) and the page can only switch keeping on and off, set the bound (10 MB to 100 GB, 200 MB by default) and delete everything: a web page, even one of ours, must not choose where the program writes.

## Consequences

- The sound is whatever the input hears while receiving, with a microphone or a radio it can hold other people's voices. It stays on the computer; the page says so next to the switch and has a "Delete all" button.
- A Signal that was lost when it was whole, and read in a later pass, stays kept as lost (it was kept before it was read): replaying it then reports that it is now read, which is what a better decoder should show.
- Replay loads only modems of this package, whatever a file says.
