# TODO
- investigate why the demodulator struggle to get a fix bellow 2kHz
- add some presets for the signal configuration
  - SLOW [baudrate 70, constellation = BPSK]
  - MEDIUM [baudrate 200, constellation = QPSK]
  - FAST [baudrate 400, constellation = 8PSK]
  - CUSTOM
  - add the option on the GUI to select the preset
- add the option to stop the transmission in the GUI (the send button become a stop button ?)
- add a "send file" button in the GUI
- add a "send picture" button in the GUI
  - implement image dithering compression
- improve the peak detector
  - wait that several peak of same frequency has been detected before starting a demodulator
    - keep last n fft, compute the mean (a filtering that will lower noiser floor) and looks for peaks from here.
  - search how to better find peaks of low amplitude
  - search how to lock on a frequency even if the received signal is low (maybe a PLL ? expose error on a zmq port)
- compute noise floor for a few second before starting the peak detection
  - substract noise floor from the FFT
- expert mode ? with all the graphs
- simple mode ? just the essentials
- use a profiler to see where is the performance bottle neck for low-end devices.

# CURRENT
- the "gap" need to be fixed (the 55ms time laps between the last pramble and the first data packet)
  - OK : check in the packetizer how file is converted to a PDU then packets
  - FINDING : the packetization somehow output a group of zero mid packet (probably due to the PDU serialization process)
  - FINDING : the convolutionnal encoder also ouput zeros if only zeros are given as an input
  - TEST PENDING : add a scrambler in `packetizer` and a descrambler in `packet_decoding`