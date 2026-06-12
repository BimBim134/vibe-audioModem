import logging
import os
import sys
import signal
import threading

import numpy as np
from gnuradio import audio
from gnuradio import blocks
from gnuradio import fft
from gnuradio.fft import window
from gnuradio import gr
from gnuradio import zeromq

from src.misc.config import SignalConfig, PortsConfig, DEFAULT_SIGNAL_CONFIG, DEFAULT_PORTS_CONFIG


class AudioProbe(gr.sync_block):
    """Pass-through block that periodically logs audio stream stats."""
    def __init__(self, label, interval_sec=2.0, samp_rate=48000):
        gr.sync_block.__init__(
            self, name=f"AudioProbe({label})", in_sig=[np.float32], out_sig=[np.float32]
        )
        self._label = label
        self.interval = int(interval_sec * samp_rate)
        self.counter = 0
        self.samp_rate = samp_rate

    def work(self, input_items, output_items):
        output_items[0][:] = input_items[0][:]
        n = len(input_items[0])
        self.counter += n
        if self.counter >= self.interval:
            block = input_items[0][:self.interval]
            rms = float(np.sqrt(np.mean(block**2)))
            peak = float(np.max(np.abs(block)))
            logging.info(
                "AudioProbe %s mode: %.1fs, RMS=%.4f, peak=%.4f",
                self._label,
                self.counter / self.samp_rate,
                rms,
                peak,
            )
            self.counter = 0
        return n


class AudioInterface(gr.top_block):

    def __init__(self, sig: SignalConfig, ports: PortsConfig, input_file: str = None):
        """Gets input audio stream from sound card and computes its FFT. Provides audio and FFT on separated ports.

        Args:
            sig (SignalConfig): signal configuration (mainly to get samplerate)
            fft_size (int, optional): fft windows size. Defaults to 2028.
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
        if input_file:
            self.audio_source = blocks.wavfile_source(input_file, False)
            self.blocks_throttle = blocks.throttle(
                gr.sizeof_float * 1, self.sig.samp_rate, True
            )
            self.audio_probe = AudioProbe("file", samp_rate=self.sig.samp_rate)
        else:
            self.audio_source = audio.source(self.sig.samp_rate, "", True)
            self.audio_probe = AudioProbe("live", samp_rate=self.sig.samp_rate)
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
        if input_file:
            self.connect((self.audio_source, 0), (self.blocks_throttle, 0))
            self.connect((self.blocks_throttle, 0), (self.audio_probe, 0))
            self.connect((self.audio_probe, 0), (self.blocks_stream_to_vector, 0))
            self.connect((self.audio_probe, 0), (self.zeromq_pub_sink_audio, 0))
        else:
            self.connect((self.audio_source, 0), (self.audio_probe, 0))
            self.connect((self.audio_probe, 0), (self.blocks_stream_to_vector, 0))
            self.connect((self.audio_probe, 0), (self.zeromq_pub_sink_audio, 0))
        self.connect((self.blocks_stream_to_vector, 0), (self.fft_vxx, 0))
        self.connect((self.fft_vxx, 0), (self.blocks_complex_to_mag, 0))
        self.connect((self.blocks_complex_to_mag, 0), (self.zeromq_pub_sink_fft, 0))


def start_audio_interface(
        signal_conf:SignalConfig=DEFAULT_SIGNAL_CONFIG,
        ports_conf:PortsConfig=DEFAULT_PORTS_CONFIG,
        stop_event=None,
        input_file: str = None,
    ):
    """Starts the audio interface.

    Args:
        sig (SignalConfig): signal configuration (mainly to get samplerate)
        fft_size (int, optional): fft windows size. Defaults to 2028.
    """
    if input_file and not os.path.exists(input_file):
        logging.error(f"Input file '{input_file}' not found")
        return
    if input_file:
        import wave
        with wave.open(input_file, "r") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            channels = wf.getnchannels()
            sw = wf.getsampwidth()
            logging.info(
                "WAV file: %s, rate=%d, channels=%d, sampwidth=%d, frames=%d, duration=%.1fs",
                input_file, rate, channels, sw, frames, frames / rate if rate else 0,
            )
    tb = AudioInterface(signal_conf, ports_conf, input_file=input_file)
    logging.info("audio interface initialized")

    def sig_handler(sig=None, frame=None):
        logging.info("AudioInterface: SIGINT/SIGTERM received")
        tb.stop()
        tb.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    if stop_event is not None:
        def monitor_stop_event():
            while not stop_event.is_set():
                import time
                time.sleep(0.5)
            
            if tb.flowgraph_started.is_set():
                logging.info("AudioInterface: stop_event set, stopping flowgraph")
                tb.stop()
                tb.wait()
        
        monitor_thread = threading.Thread(target=monitor_stop_event, daemon=True)
        monitor_thread.start()

    tb.start()
    logging.info("audio interface started")
    tb.flowgraph_started.set()

    tb.wait()
    tb.flowgraph_started.clear()
    logging.info("audio interface stopped")
    if input_file and stop_event is not None:
        logging.info("File playback complete.")

if __name__ == "__main__":
    start_audio_interface()
