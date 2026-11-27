# Vibe AudioModem — Manual { #top }

Vibe AudioModem sends short text messages through the **audio** of a radio and decodes them very close to the noise floor. It is one-way: there is no return channel, no acknowledgement and no retry. It was made for radio amateurs, first on FM VHF and UHF between a few stations in a group.

Press **F1** in the application to open this manual at any time.

## Contents { #contents }

1. [How it works](#how-it-works)
2. [Install and start](#install)
3. [The page](#page)
4. [Connect a radio](#radio)
5. [Send a message](#send)
6. [Receive](#receive)
7. [Settings](#settings)
8. [Push to talk with Hamlib](#ptt)
9. [Lead-in and TX blanking](#lead-in-blanking)
10. [History and CSV export](#history)
11. [Stored receptions (debug)](#stored)
12. [Quit](#quit)
13. [The log and bug reports](#log)
14. [Problems](#problems)
15. [Words used](#words)

## How it works { #how-it-works }

A **Message** is cut into **Fragments** of at most 17 bytes. Each Fragment is sent in its own **Frame**: a **Preamble** that the receiver recognises, then the data, protected by an error-correcting code (a turbo code) and a CRC. The sound is made of eight tones (8-FSK); the **Preset** sets how long each symbol lasts.

| Preset | Symbol | One Frame lasts | Width of the Signal | Reads down to about |
| :-- | --: | --: | --: | --: |
| Slow – Maximum Range | 320 ms | 54 s | 29 Hz | −22 dB |
| Standard | 80 ms | 14 s | 107 Hz | −16 dB |
| Fast – Good Conditions | 40 ms | 7 s | 212 Hz | −13 dB |

The last column is the signal-to-noise ratio, in a 2,500 Hz noise bandwidth, at which at least 95 % of Messages arrive in the bench simulations. Real channels are worse than a simulated one: count on a few dB less. A slow Preset reaches further and takes longer; a fast one needs a clearer channel.

The Signal always stays inside 300 to 2,700 Hz, the audio band of an SSB or FM radio. The lowest tone is at **1,450 Hz** unless you choose another frequency.

## Install and start { #install }

**Windows.** Download the archive of the latest release, unpack it, and run `VibeModem.exe`. The page opens in your browser. The application is not signed: if Windows SmartScreen says the publisher is unknown, choose *More info*, then *Run anyway*.

**macOS.** Unpack the archive. macOS blocks an unsigned application: right-click the application and choose *Open*, or remove the quarantine flag in a terminal with `xattr -dr com.apple.quarantine VibeModem.app`. The package has been checked by automatic tests only; it has not been tried by hand on a Mac.

**Linux.** There is no package yet. From a copy of the sources, with [uv](https://docs.astral.sh/uv/) installed:

```bash
uv sync --locked --all-extras
uv run python -m vibemodem.app
```

The application runs on your computer only and serves its page on `127.0.0.1`: nothing is reachable from the network. Press **Ctrl+C** in the terminal, or the power button of the page, to stop it.

## The page { #page }

- **Top bar.** The listening state, **Listen** / **Stop listening**, **Settings**, **Manual** (also F1) and the power button, which quits the application.
- **Spectrum and waterfall.** What the sound card hears, from 300 to 2,700 Hz. The waterfall shows the last minute, newest at the top. A Signal shows as a bright line.
- **Conversation.** The Messages sent (right) and received (left), in time order, with how each was received. Above it, filters, and the **Export CSV** link.
- **Composer.** The frequency to send at, the text, **Send** and, while sending, **Cancel**.

## Connect a radio { #radio }

You need an audio path both ways between the computer and the radio: an audio interface (a USB sound card, or an interface made for amateur radio such as a Digirig), or the computer's own sound card with cables.

1. **Output** of the computer to the **microphone or data input** of the radio. **Input** of the computer to the **speaker or data output** of the radio.
2. In **Settings → General → Audio device**, choose the input and the output, then **Apply**. The sound card must accept 48,000 Hz, one channel.
3. Set the levels. On the way out, raise the volume until the radio shows a normal modulation, **not more**: a Signal that is overdriven spreads over other frequencies and reads worse. On the way in, the spectrum should show the noise clearly without filling the whole window.
4. Choose how the radio is keyed: with its **VOX**, or with **Push to talk** through Hamlib (see [below](#ptt)).

Test first on a dummy load or with two radios close together, at low power, and within your licence.

## Send a message { #send }

1. Write the text. The line under it shows how many Fragments it makes and how long it will be on the air.
2. Optionally change **Send at**: the frequency of the lowest tone, within the range shown. Change it to avoid a signal already there.
3. Press **Send** (or Enter). **Cancel** cuts the Transmission, even in the middle of the sound.

A Message that is too long for the Preset is refused, and the line says what to do (a shorter text, a faster Preset or fewer repetitions).

With **Repetitions** above 1, every Fragment is sent several times, in another order each time. It costs airtime and helps when some Frames are lost.

If a Signal is arriving, a line says so and **Send** becomes **Send anyway**. It only warns: on a shared channel, wait for the end of the other station, but nothing stops you from sending.

## Receive { #receive }

Press **Listen**. The application listens to the input, finds the Preambles and decodes the Frames. The Preset must be the one the other station uses: it is chosen in the settings, and cannot change while listening.

- A Message appears when all of its Fragments are read. It shows its frequency and its SNR.
- A Message of which only some Fragments were read shows **incomplete**, with the parts read and the Fragments missing.
- **Receiving a signal at … Hz** means a Preamble was heard and the Frame is still coming.
- A Signal that was found but could not be read is shown as **not decoded** (a grey line). Untick **Not decoded** to hide them.
- **Signals from … to … Hz** hides what is outside a range of frequencies.

When the listening stops, the last pass decodes what was heard.

## Settings { #settings }

Open **Settings**. **Apply** is needed for the Preset and the devices. The other settings take effect when you change them. All are kept between sessions in `settings.json`. The Preset and the devices cannot change while sending or listening; the others can.

### General

| Setting | Default | What it does |
| :-- | :-- | :-- |
| **Callsign** | none | Your call sign, 3 to 12 letters and digits, written in capitals. It is written in front of every Message you send: `F4JBO: hello`. Add `/P` when you operate portable (`F4JBO/P`). The history keeps it. The prefix counts in the 17 bytes of a Fragment. |
| **Audio device — Input / Output** | default | The sound card used. A device that is not there at the next start is ignored and kept for when it is back. |
| **Preset** | Standard | See [How it works](#how-it-works). The other station must use the same. |
| **Repetitions** | 1 (1 to 8) | How many times the Message is sent. |

### Advanced

| Setting | Default | What it does |
| :-- | :-- | :-- |
| **Listening band — From / To** | empty | Only Signals **entirely inside** this band are read. Use it to leave out the low-frequency noise of a radio, or to pick the part of the audio where the conversation takes place. It applies to the next pass, also while listening. Empty: everything. It is not kept between sessions. |
| **Lead-in — Length** | 0 ms (0 to 5,000) | A tone before the Preamble. See [Lead-in](#lead-in-blanking). |
| **Push to talk** | off | Keys the radio through Hamlib. See [Push to talk](#ptt). |
| **TX blanking — Margin** | 250 ms (0 to 10,000) | Silence after your own Transmission. See [TX blanking](#lead-in-blanking). |
| **Stored receptions** | off, 200 MB | See [Stored receptions](#stored). |

### History

**Clear the history** deletes every Message kept, after a second click to confirm. See [History](#history).

## Push to talk with Hamlib { #ptt }

With a **VOX**, the radio keys itself when it hears sound; leave **Push to talk** off. Otherwise the application asks **Hamlib** to key the radio. It talks to **`rigctld`**, a small program of Hamlib that you start for your radio. `rigctld` can key a radio through its CAT control, or a serial line (RTS or DTR) such as the one of a Digirig.

**Install Hamlib.**

- Linux: `sudo apt install libhamlib-utils` (Debian and Ubuntu); the package has another name on other distributions.
- macOS: `brew install hamlib`.
- Windows: download the Hamlib release for Windows from the Hamlib project and unpack it; `rigctld.exe` is in its `bin` folder.

**Start `rigctld`** in a terminal, and leave it running. `rigctl -l` lists the radio models and their numbers. Examples, to adapt to your radio and port:

```bash
rigctld -m 1                                   # a dummy radio, to try without a radio
rigctld -m <model> -r /dev/ttyUSB0 -s 9600     # a radio with CAT control
rigctld -m <model> -P RTS -p /dev/ttyUSB0      # key the RTS line of a serial port
```

Check with `rigctl -m 2 -r localhost:4532 T 1` and `... T 0` that the radio keys, before using the application. These commands depend on your radio and interface; check Hamlib's own documentation for yours.

**In the application**, open **Settings → Advanced → Push to talk**, tick **Use rigctld**, and give the address (`127.0.0.1` when `rigctld` runs on this computer) and the port (`4532`, the default of `rigctld`). The two delays are the time between the key-down and the first sound, and between the last sound and the key-up (100 ms each by default). Lengthen them if the start or the end of your Messages is cut.

The radio is keyed **before** the Lead-in and released after the end of the sound, **also** if the sound card fails or if you cancel. If `rigctld` cannot be reached, nothing is played, the Message shows as failed and the reason is written on the page.

## Lead-in and TX blanking { #lead-in-blanking }

**Lead-in.** A plain tone, at the frequency of the lowest tone, sent before the Preamble. It gives a **squelch** that opens late, or a **VOX** that cuts the start of the sound, time to open before the Preamble begins. It is off by default; try 300 to 500 ms. Its time counts in the airtime shown, and the receiver ignores it. On the bench it changed neither the reception nor the false alarms.

**TX blanking.** While your station transmits, its own sound comes back through the audio interface. The receiver ignores it, so your own Transmission is never shown as received. Your Messages stay in the conversation as **sent**. The input is deaf from the start of the transmission until the end of the sound, plus the delay of the sound card, plus the **Margin** (250 ms by default). Raise the Margin if your radio has a long squelch tail. Lower it if a station answers at once and you lose the start of its Preamble. TX blanking is always on.

## History and CSV export { #history }

Every Message, sent or received, is written to `history.sqlite3` in the application's data folder as it happens, and shown again when the application starts (the last 1,000). Only text and figures are kept, never sound. The file stays on your computer.

Each line holds the time, the direction, the Callsign of the sender, the text, the frequency, the SNR, the Preset and the state (*complete* or *incomplete* for what was received; *sent*, *cancelled* or *failed* for what was sent). The Callsign is read from the `CALLSIGN: ` prefix, `/P` included.

**Export CSV** (above the conversation) downloads the whole history as a file for a spreadsheet: UTF-8 with a byte order mark, columns separated by `;` (it opens correctly in French spreadsheets), time in UTC. A text that starts with `=`, `+`, `-` or `@` gets an apostrophe in front, so a spreadsheet never runs it as a formula.

**Clear the history** (Settings → General) deletes the file's content and empties the conversation.

## Stored receptions (debug) { #stored }

For debugging, each reception can be kept as a sound file with 3 seconds around each Signal, and a file of the figures of the reception. This is off by default. Tick **Keep the audio and the figures of what is received** and set a limit in MB; the oldest are deleted first when the limit is reached. **Delete all stored receptions** empties the folder.

They are in the folder of the application's data, next to the history and the settings:

| System | Folder |
| :-- | :-- |
| Linux | `~/.local/share/vibemodem/receptions` |
| macOS | `~/Library/Application Support/VibeModem/receptions` |
| Windows | `%LOCALAPPDATA%\VibeModem\receptions` |

The option `--receptions-dir <folder>` chooses another folder when the application is started from a terminal.

## Quit { #quit }

Use the power button (top right) and click again to confirm. If the application is still listening, it says so: quitting stops the listening. **Closing the browser tab does not stop the application**: it goes on listening and sending. From a terminal, **Ctrl+C** stops it cleanly.

## The log and bug reports { #log }

The application writes a **log file**, `vibemodem.log`, in its data folder (see [Stored receptions](#stored) for where). It is cut into five files of at most 1 MB each: the oldest part is forgotten. It tells what the application did and what went wrong: the version, the system, the audio libraries and devices seen, the settings changed, each Message sent (the Preset, the number of Fragments, the length on the air, how it ended), the PTT, the Messages received (their figures), and every error with its trace. It holds **no sound and no text of a Message**.

**To report a bug**, press **Settings → Advanced → Log → Download the log** and attach the file to the report, with a line on what you did and what you saw. The release number, and the git state if you run from the sources, are at the foot of the Settings window and at the top of the log.

When the application is started from a terminal, `--log-level debug` makes the log much more detailed (every step of the sound card, for example); use it when asked to look for a bug. Warnings and errors also appear in the terminal.

## Problems { #problems }

| What you see | What to do |
| :-- | :-- |
| *the … device cannot be opened at 48000 Hz in mono* | Choose another device, or set the sound card to 48,000 Hz. |
| No device in the lists | Plug the interface in and restart the application. |
| *Stop listening and sending to change these* | The Preset and the devices cannot change while listening or sending. |
| A Message is refused as too long | Shorten it, choose a faster Preset or lower the Repetitions. |
| Nothing is received | Check that both stations use the same Preset, that the level is right (the spectrum moves), that the **Listening band** is empty or holds the Signal, and the frequency of the other station. |
| A Message is received incomplete | Ask for another Transmission; use more Repetitions; widen the margins of your PTT delays. |
| *PTT: cannot talk to rigctld…* | Start `rigctld`, check the address and the port, then try again. |
| The start of the Messages is cut on the air | Add a Lead-in, or a longer delay before the sound (PTT). |
| History not written | The error shows on the page; check that the data folder can be written. |

## Words used { #words }

- **Message**: the text you send, up to a few kilobytes.
- **Fragment**: a piece of a Message, at most 17 bytes, sent in one Frame.
- **Frame**: the sound of one Fragment: a Preamble and the coded data.
- **Transmission**: everything the station sends for one Message, with its repetitions.
- **Preamble**: the part of a Frame the receiver recognises.
- **Signal**: what the receiver finds in the audio: a Frame, readable or not.
- **Preset**: Maximum Range, Standard or Fast; the speed of the symbols.
- **Lowest tone**: the lowest of the eight tones of a Signal; the frequency you choose to send at.
- **Listening band**: the part of the audio where the receiver looks for Signals.
- **Lead-in**: an optional tone before the Preamble.
- **TX blanking**: the receiver ignoring the station's own sound.
- **Callsign**: your call sign, written in front of your Messages.
