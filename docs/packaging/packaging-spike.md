# Packaging spike — findings

Issue #3. Question: can a non-developer run a Python + NumPy/SciPy + audio + local web server application on Windows and macOS without a terminal?

**Verdict: yes, with PyInstaller.** CI builds a Windows and a macOS artifact and smoke-tests each. The owner ran the Windows build on a clean Windows machine on 2026-11-01 and reported that everything worked (page, microphone recording, quit). The macOS build was then run by hand on a Mac (reported by the owner on 2026-11-11): everything worked, with no terminal command needed, and a message was exchanged with another computer.

## What was built

- A hello application (`vibemodem.app.hello`): a page on the loopback interface only, audio input listing, a 5-second recording button, a DSP self-test (SciPy), and a Quit button.
- Packaged with PyInstaller in "one folder, no console" mode (`packaging/vibemodem.spec`). The macOS build is an `.app` bundle with a microphone usage description.
- The `Package` workflow builds on `windows-latest` and `macos-latest`, runs `packaging/smoke_test.py` against the built executable, zips it and uploads it as an artifact.

## What CI verifies on Windows and macOS

The smoke test starts the packaged executable (no console), then checks that:

1. the page is served on `127.0.0.1`;
2. the NumPy/SciPy self-test detects the 1,000 Hz test tone, so the scientific libraries are bundled;
3. the audio library (PortAudio, through `sounddevice`) loads, so it is bundled — CI has no microphone, but a missing library is reported separately from a missing device;
4. the application quits cleanly when asked.

Sizes of the uploaded archives: about 58 MB (Windows) and 35 MB (macOS). An unpacked Linux build measured locally is 169 MB.

## Not verified yet

Recording from a real microphone was confirmed on a clean Windows machine. Still open:

- ~~**macOS:** recording from a real microphone in the packaged app, and the microphone permission prompt.~~ Done on 2026-11-11 with release `v1.0`: the page, the settings and the devices all worked, and a message went between the Mac and another computer. The Mac model and macOS version were not recorded.
- Behaviour on Intel Macs: the macOS runner is Apple Silicon (arm64), so the artifact is arm64 only. An Intel build would need another runner.

### Manual check on a clean machine

Follow [`procedure-packaging-check.md`](procedure-packaging-check.md), step by step, then report the result on issue #3.

## Warnings users will see (the builds are not signed)

- **Windows:** SmartScreen may say the publisher is unknown. "More info" then "Run anyway" starts it.
- **macOS:** Gatekeeper blocks an unsigned app downloaded from the internet. Right-click the app and choose Open, or remove the quarantine flag with `xattr -dr com.apple.quarantine VibeModem.app`.
- Signing and notarisation are out of scope for v1 and left to later work.

## Problems found while packaging

- The generic `*.spec` rule in `.gitignore` hid the PyInstaller spec file, so CI could not find it. Fixed with an exception for `packaging/`.
- A windowed (no console) application has no standard output; some libraries crash on that. The app replaces missing streams with a null device at start-up.
- Uvicorn loads parts of itself dynamically, so the spec collects all its submodules explicitly.
- A missing audio library and a missing microphone looked the same to the first smoke test. The API now reports the library state separately, and the smoke test requires it on Windows and macOS.

## Decision

Packaging is practical, so no ADR on an alternative is needed. PyInstaller is the working candidate; the final installer (ticket for the Windows installer) will build on it.
