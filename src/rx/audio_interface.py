import logging
import sys
import signal
import threading

from gnuradio import audio
from gnuradio import blocks
from gnuradio import fft
from gnuradio.fft import window
from gnuradio import gr
from gnuradio import zeromq

from src.config import SignalConfig, DEFAULT_SIGNAL_CONFIG

logging.basicConfig(format="%(levelname)s: %(processName)s - %(process)d: %(module)s: %(message)s", level=logging.DEBUG)

class AudioInterface(gr.top_block):

    def __init__(self, sig: SignalConfig, fft_size: int = 2028):
        """Gets input audio stream from sound card and computes its FFT. Provides audio and FFT on separated ports.

        Args:
            sig (SignalConfig): signal configuration (mainly to get samplerate)
            fft_size (int, optional): fft windows size. Defaults to 2028.
        """
        gr.top_block.__init__(self, "Audio interface", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        # Variables
        self.sig = sig
        self.fft_size = fft_size

        # Blocks
        ## audio broadcasting
        self.audio_source = audio.source(self.sig.samp_rate, "", True)
        self.zeromq_pub_sink_audio = zeromq.pub_sink(
            gr.sizeof_float, 1, "tcp://*:5556", 0, False, (-1), "", True, True,
        )

        ## fft computing and broadcasting
        self.blocks_stream_to_vector = blocks.stream_to_vector(
            gr.sizeof_float * 1, self.fft_size
        )
        self.fft_vxx = fft.fft_vfc(
            self.fft_size, True, window.blackmanharris(self.fft_size), True, 1
        )
        self.blocks_complex_to_mag = blocks.complex_to_mag(self.fft_size)
        self.zeromq_pub_sink_fft = zeromq.pub_sink(
            gr.sizeof_float, self.fft_size, "tcp://*:5555", 100, False, (-1), "", True, True
        )

        # Connections
        self.connect((self.audio_source, 0), (self.blocks_stream_to_vector, 0))
        self.connect((self.audio_source, 0), (self.zeromq_pub_sink_audio, 0))
        self.connect((self.blocks_stream_to_vector, 0), (self.fft_vxx, 0))
        self.connect((self.fft_vxx, 0), (self.blocks_complex_to_mag, 0))
        self.connect((self.blocks_complex_to_mag, 0), (self.zeromq_pub_sink_fft, 0))


def start_audio_interface(signal_conf:SignalConfig, fft_size:int):
    """Starts the audio interface.

    Args:
        sig (SignalConfig): signal configuration (mainly to get samplerate)
        fft_size (int, optional): fft windows size. Defaults to 2028.
    """
    tb = AudioInterface(signal_conf, fft_size)
    logging.info("audio interface initialized")

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    logging.info("audio interface started")
    tb.flowgraph_started.set()

    tb.wait()

logging.info("audio interface module loaded")

if __name__ == "__main__":
    start_audio_interface(DEFAULT_SIGNAL_CONFIG, 2048)
