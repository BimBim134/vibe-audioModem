import logging
import sys
import signal
import threading
import time
from pathlib import Path

from gnuradio import audio
from gnuradio import blocks
from gnuradio import fft
from gnuradio.fft import window
from gnuradio import gr
from gnuradio import zeromq

from src.config import SignalConfig, PortsConfig, DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG

logging.basicConfig(format="%(asctime)s: %(levelname)s: %(processName)s: %(module)s: %(funcName)s: %(message)s", level=logging.DEBUG)

class AudioInterface(gr.top_block):

    def __init__(self, sig: SignalConfig, ports: PortsConfig, file: str|Path=None):
        """Gets input audio stream from sound card and computes its FFT. Provides audio and FFT on separated ports.

        Args:
            sig (SignalConfig): signal configuration (mainly to get samplerate)
            fft_size (int, optional): fft windows size. Defaults to 2028.
            file (str|Path, optional): path to the audio file. Defaults to None.
        """
        gr.top_block.__init__(self, "Audio interface", catch_exceptions=True)
        self.flowgraph_started = threading.Event()
        logging.info("AudioInterface class instanciated")
        logging.info(sig)
        logging.info(ports)

        # Variables
        self.sig = sig
        self.ports = ports

        # Blocks
        ## audio broadcasting
        self.audio_source = blocks.wavfile_source(str(file), False)
        self.blocks_throttle2_0 = blocks.throttle( gr.sizeof_float*1, self.sig.samp_rate, True, 0 if "auto" == "auto" else max( int(float(0.1) * self.sig.samp_rate) if "auto" == "time" else int(0.1), 1) )
        self.zeromq_pub_sink_audio = zeromq.pub_sink(
            gr.sizeof_float, 1, f"tcp://*:{self.ports.audio_port}", 0, False, (-1), "", True, True,
        )

        ## fft computing and broadcasting
        self.blocks_stream_to_vector = blocks.stream_to_vector(
            gr.sizeof_float * 1, self.ports.fft_size
        )
        self.fft_vxx = fft.fft_vfc(
            self.ports.fft_size, True, window.blackmanharris(self.ports.fft_size), True, 1
        )
        self.blocks_complex_to_mag = blocks.complex_to_mag(self.ports.fft_size)
        self.zeromq_pub_sink_fft = zeromq.pub_sink(
            gr.sizeof_float, self.ports.fft_size, f"tcp://*:{self.ports.fft_port}", 100, False, (-1), "", True, True
        )

        # Connections
        self.connect((self.audio_source, 0), (self.blocks_throttle2_0, 0))
        self.connect((self.blocks_throttle2_0, 0), (self.blocks_stream_to_vector, 0))
        self.connect((self.blocks_throttle2_0, 0), (self.zeromq_pub_sink_audio, 0))
        self.connect((self.blocks_stream_to_vector, 0), (self.fft_vxx, 0))
        self.connect((self.fft_vxx, 0), (self.blocks_complex_to_mag, 0))
        self.connect((self.blocks_complex_to_mag, 0), (self.zeromq_pub_sink_fft, 0))


def start_audio_interface(
        signal_conf:SignalConfig=DEFAULT_SIGNAL_CONFIG,
        ports_conf:PortsConfig=DEFAULT_PORTS_CONFIG,
        file: str|Path=None,
        stop_event=None
    ):
    """Starts the audio interface.

    Args:
        sig (SignalConfig): signal configuration (mainly to get samplerate)
        fft_size (int, optional): fft windows size. Defaults to 2028.
    """
    tb = AudioInterface(signal_conf, ports_conf, file)
    logging.info("audio interface initialized")

    logging.info("Waiting 10 seconds before starting")
    time.sleep(10)

    def sig_handler(sig=None, frame=None):
        logging.info("AudioInterface: SIGINT/SIGTERM received")
        tb.stop()
        tb.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    if stop_event is not None:
        def monitor_stop_event():
            while True:
                if stop_event.is_set():
                    logging.info("AudioInterface: stop_event set, stopping flowgraph")
                    tb.stop()
                    break
                time.sleep(0.1)
        
        monitor_thread = threading.Thread(target=monitor_stop_event, daemon=True)
        monitor_thread.start()

    tb.start()
    logging.info("audio interface started")
    tb.flowgraph_started.set()

    tb.wait()
    logging.info("audio interface stopped")

if __name__ == "__main__":
    pass
