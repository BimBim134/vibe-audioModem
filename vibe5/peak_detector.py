#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: peak_detector
# Author: bimbim
# GNU Radio version: 3.10.10.0

from gnuradio import audio
from gnuradio import blocks
from gnuradio import fft
from gnuradio.fft import window
from gnuradio import gr
from gnuradio.filter import firdes
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation

import numpy as np
from scipy.signal import find_peaks


class peak_frequency_detector(gr.sync_block):
    """Peak Frequency Detector"""

    def __init__(self, sample_rate=48000, fft_size=1024, threshold=10):
        gr.sync_block.__init__(
            self,
            name="Peak Frequency Detector",
            in_sig=[(np.float32, fft_size)],  # Accepts vector of fft_size elements
            out_sig=None,
        )
        self.sample_rate = sample_rate
        self.fft_size = fft_size
        self.threshold = threshold

    def work(self, input_items, output_items):
        for spectrum in input_items[0]:  # Iterate over vector batches
            freqs = np.fft.rfftfreq(self.fft_size, 1.0 / self.sample_rate)

            # Find all local peaks above threshold
            peaks, props = find_peaks(spectrum, height=self.threshold)

            if peaks.size > 0:
                max_peak_idx = peaks[np.argmax(props["peak_heights"])]
                try:
                    peak_freq = freqs[max_peak_idx]
                    print(f"Detected Peak Frequency: {peak_freq:.2f} Hz")
                except IndexError:
                    pass
            else:
                pass

        return len(input_items[0])


class peak_detector(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "peak_detector", catch_exceptions=True)

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 44100

        ##################################################
        # Blocks
        ##################################################

        self.fft_vxx_0 = fft.fft_vfc(1024, True, window.blackmanharris(1024), False, 5)
        self.detector = peak_frequency_detector(
            sample_rate=samp_rate, fft_size=1024, threshold=10
        )
        self.blocks_stream_to_vector_0 = blocks.stream_to_vector(
            gr.sizeof_float * 1, 1024
        )
        self.blocks_complex_to_mag_0 = blocks.complex_to_mag(1024)
        self.audio_source_0_0 = audio.source(samp_rate, "", True)

        ##################################################
        # Connections
        ##################################################
        self.connect((self.audio_source_0_0, 0), (self.blocks_stream_to_vector_0, 0))
        self.connect((self.blocks_complex_to_mag_0, 0), (self.detector, 0))
        self.connect((self.blocks_stream_to_vector_0, 0), (self.fft_vxx_0, 0))
        self.connect((self.fft_vxx_0, 0), (self.blocks_complex_to_mag_0, 0))

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.detector.sample_rate = self.samp_rate


def detect_frequency_peak():
    """
    This function sets up and runs the flow graph to detect frequency peaks in an audio stream.
    It listens for audio input from a source, computes its FFT, and then identifies the peak frequency
    above a specified threshold. The process can be interrupted by pressing Enter or receiving a SIGINT/SIGTERM signal.
    """
    tb = peak_detector()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()

    try:
        input("Press Enter to quit: ")
    except EOFError:
        pass
    tb.stop()
    tb.wait()


if __name__ == "__main__":
    detect_frequency_peak()
