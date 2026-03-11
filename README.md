# TODO
- investigate why the demodulator struggle to get a fix bellow 2kHz
- add some presets for the signal configuration
  - FAST [baudrate 400, constellation = 8PSK]
  - CUSTOM
  - add the option on the GUI to select the preset
- add the option to stop the transmission in the GUI (the send button become a stop button ?)
- add a "send file" button in the GUI
- add a "send picture" button in the GUI
  - implement image dithering compression
- improve the peak detector
  - search how to better find peaks of low amplitude
  - search how to lock on a frequency even if the received signal is low (maybe a PLL ? expose error on a zmq port)
- compute noise floor for a few second before starting the peak detection
  - substract noise floor from the FFT
- expert mode ? with all the graphs
- simple mode ? just the essentials
- use a profiler to see where is the performance bottle neck for low-end devices.

# CURRENT
  - SLOW [baudrate 70, constellation = BPSK]
  - MEDIUM [baudrate 200, constellation = DQPSK]