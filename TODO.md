- [1. the audiomodem needs to subscribe to fft port](#1-the-audiomodem-needs-to-subscribe-to-fft-port)
- [2. replace the CLI by a TUI](#2-replace-the-cli-by-a-tui)
- [3. create a webUI](#3-create-a-webui)
  - [3.1. add the possibility the launch only the webUI](#31-add-the-possibility-the-launch-only-the-webui)
- [4. see why it's only working at baudrate = 200](#4-see-why-its-only-working-at-baudrate--200)



# 1. the audiomodem needs to subscribe to fft port
so that it an later sends fft data to the web UI

# 2. replace the CLI by a TUI
The same than CLI, but much nicer

# 3. create a webUI
it can do everything the CLI can do, but graphically, in the browser.
## 3.1. add the possibility the launch only the webUI
that way, the user can setup a distant station, and control it remotely.

# 4. see why it's only working at baudrate = 200
test done :
* baudrate 400 : fail
* baudrate 500 : fail
* baudrate 100 : fail
* baudrate 200, carrier freq 2000 : pass deltaf : 3.91 Hz
* starting config baudrate 500, then config set baudrate 200 : pass : deltaf 3.91 Hz
* starting config baudrate 200, then config set baudrate 500 : fail
