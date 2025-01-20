#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Not titled yet
# GNU Radio version: 3.10.10.0

from gnuradio import blocks
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
import completeChain_001_epy_block_0 as epy_block_0  # embedded python block
import completeChain_001_epy_block_1 as epy_block_1  # embedded python block




class completeChain_001(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "Not titled yet", catch_exceptions=True)

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 32000

        ##################################################
        # Blocks
        ##################################################

        self.epy_block_1 = epy_block_1.blk(out_filename="/home/bimbim/Codes/vibe-audioModem/GRC/test_out/test.txt", packet_size=64, ecc_size=6, id_len=2, data_len=1, verbose=False)
        self.epy_block_0 = epy_block_0.blk(input_binary="/home/bimbim/Codes/vibe-audioModem/sampleFile.txt", packet_size=64, preamble_size=3, postamble_size=3, ecc_size=6, id_len=2, data_len=1)
        self.blocks_throttle2_0 = blocks.throttle( gr.sizeof_char*1, samp_rate, True, 0 if "auto" == "auto" else max( int(float(0.1) * samp_rate) if "auto" == "time" else int(0.1), 1) )
        self.blocks_tagged_stream_align_0 = blocks.tagged_stream_align(gr.sizeof_char*1, 'packet_len')


        ##################################################
        # Connections
        ##################################################
        self.connect((self.blocks_tagged_stream_align_0, 0), (self.epy_block_1, 0))
        self.connect((self.blocks_throttle2_0, 0), (self.blocks_tagged_stream_align_0, 0))
        self.connect((self.epy_block_0, 0), (self.blocks_throttle2_0, 0))


    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.blocks_throttle2_0.set_sample_rate(self.samp_rate)




def main(top_block_cls=completeChain_001, options=None):
    tb = top_block_cls()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()

    try:
        input('Press Enter to quit: ')
    except EOFError:
        pass
    tb.stop()
    tb.wait()


if __name__ == '__main__':
    main()
