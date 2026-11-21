# Where the tickets stand

Last updated: 2026-11-21. Keep this page up to date whenever a ticket is opened, closed or changes place in the order. The reasons behind each decision are in the comments of the tickets and in `docs/agents/memory.md`.

Ticket links: `https://github.com/BimBim134/vibe-audioModem/issues/<number>`.

## Done

- **v1 is finished.** The spec (#1) is closed. Release `v1.0` carries the Windows and macOS archives. On the conference day, the application was tried between two pocket radios (VHF and UHF) with an audio interface, and the signals were received perfectly.
- Closed along the way: the Windows archive (#22), the Listening band (#27), the 3 to 4 dB investigation (#28).

## Now: the real-radio batch, in this order

| Order | Ticket           | What it does                                                                                                     | Waits for                             |
| :---- | :--------------- | :--------------------------------------------------------------------------------------------------------------- | :------------------------------------ |
| 1     | #52              | Keep the settings between sessions                                                                               | nothing                               |
| 2     | #53              | Callsign setting, written in front of each sent Message (`F4JBO: hello`)                                         | #52                                   |
| 3     | #49              | TX blanking: the station no longer hears its own Transmission as a received Message                              | nothing (the margin setting uses #52) |
| 4     | #45              | Lead-in: an optional tone before the Preamble, to open a squelch or a VOX                                        | nothing (the setting uses #52)        |
| 5     | #42              | PTT through Hamlib (`rigctld`)                                                                                   | #52                                   |
| 6     | #54              | Warning when sending while a Signal is arriving (never blocks)                                                   | nothing                               |
| 7     | #39              | History of Messages in a database, with the Callsign and a CSV export                                            | #52, #53                              |
| 8     | #51, #50         | The manual (French and English, F1 and PDF) and the translation of the page                                      | #52                                   |
| 9     | #29              | The page reachable from other devices on the local network, with a QR code and a token                           | #52                                   |
| 10    | #55 (parent #41) | Bench study of a faster, wider Preset ("turbo") for an FM voice channel                                          | nothing                               |
| 11    | #46, then #56    | Bench scenarios for impulsive noise and carriers, then the processing in front of the receiver if it is worth it | #56 waits for #46                     |

## Waiting for hardware or the field

- **#23, the field campaign.** Stays open for the systematic campaign. It now also holds the measure of the tail of a real radio (PTT release, squelch tail) with a borrowed interface, since there is no Digirig at home.

## Later (label `v2`)

- **Several Signals at once**, in this order: #30 (measure how they disturb each other), #31 (search rules that know about frequency), #32 (successive interference cancellation), then #34 (remove the Listening band). #44 (receive the three Presets without choosing one) and #43 (images, behind the wider Preset) come after.
- **The protocol**, to rework together: #33 (telling stations apart), #37 (locator), #47 (rooms like an IRC chat), #48 (mesh). The Callsign stays a setting that prefixes the text until then.
- **#40**, a Linux package (.deb, AppImage or another format).

## Decisions in a nutshell

- First users: FM on VHF and UHF, in a group, so one transmitter at a time on a channel. HF and several Signals at once come later.
- TX blanking is always on. Its margin is the end of playback, plus the output latency, plus 250 ms, adjustable.
- The Lead-in is off by default.
- PTT goes through Hamlib; VOX stays the default.
- The remote access is off by default, local network only, protected by a token, with no HTTPS.
- A slow, wide mode over the whole 2,400 Hz was considered and dropped: little gain, and FM threshold effects make the receiver the limit.

The words used here (Lead-in, TX blanking, Callsign, Signal, Preset...) are defined in `GLOSSARY.md`.
