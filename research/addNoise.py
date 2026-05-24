#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: addNoise
# GNU Radio version: 3.10.12.0

from gnuradio import analog
from gnuradio import blocks
from gnuradio import gr

import os

import threading
import argparse
from pathlib import Path


class addNoise(gr.top_block):
    def __init__(self, inputFile: Path, snr: float, outputFile: Path | None = None):
        gr.top_block.__init__(self, "addNoise", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        # Variables
        self.samp_rate = samp_rate = 48000

        if snr >= 1:
            self.noise_amplitude = 1 / snr
            self.signal_amplitude = 1
        else:
            self.noise_amplitude = 1
            self.signal_amplitude = 1 * snr

        # Derive output filename (use temp name if it matches input)
        output_file = outputFile or inputFile.with_stem(inputFile.stem + "_noisy")

        # Blocks
        self.blocks_wavfile_source_0 = blocks.wavfile_source(str(inputFile), False)
        self.blocks_multiply_const_xx_0 = blocks.multiply_const_ff(
            self.signal_amplitude
        )

        self.analog_fastnoise_source_x_0 = analog.fastnoise_source_f(
            analog.GR_UNIFORM, 1, 0, 8192
        )
        self.blocks_multiply_const_xx_0_0 = blocks.multiply_const_ff(
            self.noise_amplitude
        )

        self.blocks_add_xx_0 = blocks.add_vff(1)
        self.blocks_multiply_const_xx_0_1 = blocks.multiply_const_ff(0.75)
        self.blocks_wavfile_sink_0 = blocks.wavfile_sink(
            str(output_file),
            1, samp_rate, blocks.FORMAT_WAV, blocks.FORMAT_PCM_16, False
        )

        # Connections
        self.connect((self.analog_fastnoise_source_x_0, 0), (self.blocks_multiply_const_xx_0_0, 0))
        self.connect((self.blocks_add_xx_0, 0), (self.blocks_multiply_const_xx_0_1, 0))
        self.connect((self.blocks_multiply_const_xx_0_1, 0), (self.blocks_wavfile_sink_0, 0))
        self.connect((self.blocks_multiply_const_xx_0, 0), (self.blocks_add_xx_0, 0))
        self.connect((self.blocks_multiply_const_xx_0_0, 0), (self.blocks_add_xx_0, 1))
        self.connect((self.blocks_wavfile_source_0, 0), (self.blocks_multiply_const_xx_0, 0))


def main(inputFile:Path, snr:float):
    temp_output = inputFile.with_stem(inputFile.stem + "_noisy")
    tb = addNoise(inputFile, snr, outputFile=temp_output)

    tb.run()
    os.replace(temp_output, inputFile)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Vibe Audio Modem")
    parser.add_argument("-f", "--file", required=True, help="input file")
    parser.add_argument("-s", "--snr", required=True, type=float, help="desired SNR")
    args = parser.parse_args()
    main(Path(args.file), args.snr)
