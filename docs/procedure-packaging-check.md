# Procedure: check the packaged app on a clean machine

Goal: confirm with your own eyes what CI cannot, namely that a non-developer can double-click the app, see the page, and **record 5 seconds from a real microphone**. This closes the last open point of issue #3.

Time needed: about 15 minutes. Do not fix anything while testing; write down what happens and report it (Part E).

## What you need

- A **clean test machine**: Windows 10/11 (64-bit) **or** a Mac with Apple Silicon (M1 or newer). "Clean" means no Python and no developer tools, ideally not the computer you develop on. Intel Macs are not covered by this build.
- A microphone (the built-in one is fine).
- Your development computer, to download the build, and a way to move a file between the two (USB stick, cloud drive, network share).

## Part A — Get the build (on your development computer)

1. Find the latest successful build and keep its number:

   ```bash
   gh run list --repo BimBim134/vibe-audioModem --workflow Package --branch AI_deep_refactoing --status success --limit 1 --json databaseId --jq '.[0].databaseId'
   ```

2. Download the archive for your test machine. Replace `RUN_ID` with the number from step 1, and use `vibemodem-windows` or `vibemodem-macos`:

   ```bash
   gh run download RUN_ID --repo BimBim134/vibe-audioModem -n vibemodem-windows -D ~/vibemodem-test
   ```

   Without the command line: on GitHub, open the repository, then **Actions**, then **Package**, then the latest run with a green tick, and click the artifact name at the bottom of the page.

3. You should now have one file, `vibemodem-windows.zip` or `vibemodem-macos.zip`. Copy it to the test machine.

## Part B — Start the app

### Windows

1. Right-click the zip, **Extract All...**, and extract it. Do not run the program from inside the zip.
2. Open the extracted `VibeModem` folder and double-click **VibeModem.exe**.
3. If Windows shows **"Windows protected your PC"** (SmartScreen), this is expected because the app is not signed: click **More info**, then **Run anyway**.
4. **Expected:** no black console window appears, and within about 10 seconds your browser opens a page titled **Vibe AudioModem** at an address starting with `http://127.0.0.1:`.
5. **If nothing happens after 30 seconds:** open Task Manager (Ctrl+Shift+Esc) and look for `VibeModem.exe`. Note whether it is there, then go to Part E.

### macOS

1. Double-click the zip in Finder. It produces **VibeModem.app**. Drag it to your Desktop or Applications folder.
2. Double-click **VibeModem.app**. macOS will refuse to open it ("cannot be opened because the developer cannot be verified"). This is expected because the app is not signed.
3. Open **System Settings**, then **Privacy & Security**, scroll down, and click **Open Anyway** next to the VibeModem message. Confirm with your password.
   - Alternative: right-click the app, choose **Open**, then **Open** again.
   - If macOS says the app is "damaged": in Terminal run `xattr -dr com.apple.quarantine /path/to/VibeModem.app` (write down that you had to).
4. **Expected:** no Terminal window appears, and within about 10 seconds your browser opens a page titled **Vibe AudioModem** at an address starting with `http://127.0.0.1:`.
5. **If nothing happens after 30 seconds:** open Activity Monitor, look for `VibeModem`, note whether it is there, then go to Part E.

## Part C — Check the app

Do these in order on the page that opened.

| # | Do this | Expected result | If not |
| :-- | :-- | :-- | :-- |
| 1 | Look at the **Audio input** drop-down. | Your microphone appears in the list. | Write down what the list shows. |
| 2 | Click **DSP self-test**. | The box shows `"tone_hz": 1000` and `"detected_hz": 1000.0`. | Copy what the box shows. |
| 3 | Choose your microphone, click **Record 5 seconds**, and talk or clap for the whole 5 seconds. | The box says "Recording for 5 seconds...", then after about 5 seconds shows `"samples": 240000`, and `"rms"` and `"peak"` greater than 0. | If the system asks for **microphone permission**, allow it and try again (macOS: it asks once; Windows: Settings, Privacy, Microphone, allow desktop apps). If the box shows "No usable audio input", copy the full message. |
| 4 | Record again in **silence** (do not speak). | `"samples": 240000` and a much smaller `"rms"` than in step 3. | Write down both `rms` values. |

## Part D — Stop the app

1. Click **Quit** on the page. **Expected:** the box says "Stopped. You can close this tab."
2. Wait 5 seconds, then check Task Manager (Windows) or Activity Monitor (macOS). **Expected:** `VibeModem` is no longer listed.
3. If it is still running, note it and end the process manually.

## Part E — Report

Copy the template below into a comment on [issue #3](https://github.com/BimBim134/vibe-audioModem/issues/3), filled in. Add screenshots of any error.

```text
Machine: (Windows 11 / macOS 15 ... , model, clean machine yes/no)
Build: run number RUN_ID, file name
B  Started without a console window: yes / no
B  Warning shown (SmartScreen / Gatekeeper) and how I got past it:
B  Browser opened by itself: yes / no
C1 Microphone listed: yes / no
C2 Self-test detected_hz:
C3 Recording: samples = , rms = , peak =  (or the error text)
C4 Silence recording: rms =
D  App stopped after Quit: yes / no
Anything else that needed a manual step or looked wrong:
```

**The issue can be closed when** B, C1, C2, C3 and D all pass on at least one Windows or macOS machine. If packaging looks impractical, say so in the comment and an ADR will record the alternative.
