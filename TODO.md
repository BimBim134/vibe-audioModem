- [1. replace the CLI by a TUI](#1-replace-the-cli-by-a-tui)
- [2. create a webUI](#2-create-a-webui)
  - [2.1. add the possibility the launch only the webUI](#21-add-the-possibility-the-launch-only-the-webui)
- [3. see why it's only working at baudrate = 200](#3-see-why-its-only-working-at-baudrate--200)
- [4. add some sort of signal vizualisation in CLI](#4-add-some-sort-of-signal-vizualisation-in-cli)
- [5. option to calibrate the peak detector by measure the ambiant noise to estimate the noise floor so it can be substracted](#5-option-to-calibrate-the-peak-detector-by-measure-the-ambiant-noise-to-estimate-the-noise-floor-so-it-can-be-substracted)
- [6. improve the peak detector for noisy signal](#6-improve-the-peak-detector-for-noisy-signal)
- [7. add a clear log function](#7-add-a-clear-log-function)
- [8. full test suite to validate/caracterize the app](#8-full-test-suite-to-validatecaracterize-the-app)


# 1. replace the CLI by a TUI
The same than CLI, but much nicer

# 2. create a webUI
it can do everything the CLI can do, but graphically, in the browser.
## 2.1. add the possibility the launch only the webUI
that way, the user can setup a distant station, and control it remotely.

# 3. see why it's only working at baudrate = 200
test done :
* baudrate 400 : fail
* baudrate 500 : fail
* baudrate 100 : fail
* baudrate 200, carrier freq 2000 : pass deltaf : 3.91 Hz
* starting config baudrate 500, then config set baudrate 200 : pass : deltaf 3.91 Hz
* starting config baudrate 200, then config set baudrate 500 : fail
* baudrate 220 : pass

added decimation, seemed to help a little bit.

# 4. add some sort of signal vizualisation in CLI

# 5. option to calibrate the peak detector by measure the ambiant noise to estimate the noise floor so it can be substracted

# 6. improve the peak detector for noisy signal

# 7. add a clear log function

# 8. full test suite to validate/caracterize the app