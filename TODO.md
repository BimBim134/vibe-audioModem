- [1. how do the audiomodem handle receiving a messages ?](#1-how-do-the-audiomodem-handle-receiving-a-messages-)
- [2. set the commands for audio modem and http server:](#2-set-the-commands-for-audio-modem-and-http-server)
  - [2.1. /POST](#21-post)
  - [2.2. /GET](#22-get)
- [3. the audiomodem needs to subscribe to fft port](#3-the-audiomodem-needs-to-subscribe-to-fft-port)
- [4. replace the CLI by a TUI](#4-replace-the-cli-by-a-tui)
- [5. create a webUI](#5-create-a-webui)
  - [5.1. add the possibility the launch only the webUI](#51-add-the-possibility-the-launch-only-the-webui)



# 1. how do the audiomodem handle receiving a messages ?
it seems audiomodem has no way to return received message to the cli

# 2. set the commands for audio modem and http server:
## 2.1. /POST
  * `transmit`
    * *sent to the modem* : any messages or bytes payload
    * *what the modem do* : it add the messages or byte payload the the queue to be treated
  
  * `receive` (`-n` : the number of workers to spawn)
  
    starts the peak detector and spawn n (or only 1 if not specified) workers ready to receive any transmission.

    it implies that :
    * the modem should take care of the number of worker to be spawn by the peak_detector
    * the peak detector should not be started at startup but only when the `receive` command is sent
    * peakdetector (and associated workers) **will be** resetted if the user wants to ajust:
      *  parameters
      *  number of workers 


  * `setup`
    * request :
      ```json
      {
          "signal": {
              "samp_rate": 48000,
              "carrier_freq": 2500,
              "beeper_duration": 3.0,
              "baudrate": 200,
              "constellation_name": "default"
          },
          "packet": {
              "total_packets_len": 48,
              "preamble_packets": 1,
              "postamble_packets": 1,
              "error_correction_len": 16
          },
          "port": {
              "audio_port": 5555,
              "fft_port": 5556,
              "fft_size": 4096,
              "raw_packets_port": 5557,
              "messages_port": 5558,
              "config_port": 5559,
              "peak_detector_system_port": 5560
          }
      }
      ```
    * *what the modem do* : it reset **completely** with the new adjusted parameters 

  * `stop`
    * `-rx` : stops the peak detectors and associated workers 
    * `-tx` : stops any transmission and clear the queue
  
  * `quit`

    closes the whole application **gracefully**

## 2.2. /GET
 * `audio`
 * `fft`
 * `messages`
 * `configuration`
 * `logs`

# 3. the audiomodem needs to subscribe to fft port
so that it an later sends fft data to the web UI

# 4. replace the CLI by a TUI
The same than CLI, but much nicer

# 5. create a webUI
it can do everything the CLI can do, but graphically, in the browser.
## 5.1. add the possibility the launch only the webUI
that way, the user can setup a distant station, and control it remotely.
