#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: receiver 004
# Author: bimbim
# GNU Radio version: 3.10.10.0

from gnuradio import analog
from gnuradio import blocks
from gnuradio import digital
from gnuradio import filter
from gnuradio import fec
from gnuradio.filter import firdes
from gnuradio import gr
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
import numpy as np
import packet2bin_block as epy_packet2bin_block  # embedded python block




class receiver(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "receiver 004", catch_exceptions=True)

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 44100
        self.baudrate = baudrate = 250
        self.sps = sps = int(samp_rate/baudrate)
        self.rrc_taps = rrc_taps = firdes.root_raised_cosine(1, samp_rate,baudrate, 0.35, (51*sps))
        self.packet_size = packet_size = 64
        self.output_file_path = output_file_path = ""
        self.nfilts = nfilts = 64
        self.loop_bandwidth = loop_bandwidth = 2*np.pi*0.04
        self.const_definition = const_definition = digital.constellation_calcdist([-1-1j, -1+1j, 1+1j, 1-1j], [0, 1, 3, 2],
        4, 1, digital.constellation.AMPLITUDE_NORMALIZATION).base()
        self.const_definition.set_npwr(0)
        self.const_definition.gen_soft_dec_lut(8)
        self.cc_dec = cc_dec = fec.cc_decoder.make(8,7, 2, [79,109], 0, 0, fec.CC_STREAMING, True)
        self.carrier_freq = carrier_freq = 2500
        self.access_key = access_key = '11100001010110101110100010010011'

        ##################################################
        # Blocks
        ##################################################

        self.fft_filter_xxx_0 = filter.fft_filter_ccf(1, rrc_taps, 1)
        self.fft_filter_xxx_0.declare_sample_delay(0)
        self.fec_extended_decoder_0 = fec.extended_decoder(decoder_obj_list=cc_dec, threading= None, ann=None, puncpat='11', integration_period=10000)
        self.epy_block_1 = epy_block_1.blk(out_filename=output_file_path, packet_size=packet_size, ecc_size=10, id_len=2, data_len=1, verbose=False)
        self.digital_symbol_sync_xx_0 = digital.symbol_sync_cc(
            digital.TED_GARDNER,
            sps,
            loop_bandwidth,
            (1.0/np.sqrt(2.0)),
            1.4142,
            1.5,
            1,
            const_definition,
            digital.IR_PFB_NO_MF,
            nfilts,
            rrc_taps)
        self.digital_map_bb_1_0 = digital.map_bb(const_definition.pre_diff_code())
        self.digital_diff_decoder_bb_0_0 = digital.diff_decoder_bb(len(const_definition.points()), digital.DIFF_DIFFERENTIAL)
        self.digital_costas_loop_cc_0_0 = digital.costas_loop_cc((2*np.pi/100), len(const_definition.points()), True)
        self.digital_correlate_access_code_xx_ts_0 = digital.correlate_access_code_bb_ts(access_key,
          3, 'packet_len')
        self.digital_constellation_decoder_cb_0_0_0 = digital.constellation_decoder_cb(const_definition)
        self.blocks_unpack_k_bits_bb_0_0 = blocks.unpack_k_bits_bb(int(np.log2(len(const_definition.points()))))
        self.blocks_uchar_to_float_0_0_0 = blocks.uchar_to_float()
        self.blocks_repack_bits_bb_0_0 = blocks.repack_bits_bb(1, 8, "packet_len", True, gr.GR_MSB_FIRST)
        self.blocks_multiply_xx_1 = blocks.multiply_vcc(1)
        self.blocks_multiply_const_xx_1_0_0 = blocks.multiply_const_ff(2, 1)
        self.blocks_float_to_complex_0 = blocks.float_to_complex(1)
        self.blocks_add_const_vxx_0_0_0 = blocks.add_const_ff((-1))
        self.audio_source_0 = audio.source(samp_rate, 'plughw:0,0', True)
        self.analog_sig_source_x_1 = analog.sig_source_c(samp_rate, analog.GR_SIN_WAVE, (-carrier_freq), 1, 0, 0)
        self.analog_const_source_x_0 = analog.sig_source_f(0, analog.GR_CONST_WAVE, 0, 0, 0)
        self.analog_agc_xx_0 = analog.agc_cc((1e-4), (2*np.sqrt(2)), 1.0, 10)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.analog_agc_xx_0, 0), (self.blocks_multiply_xx_1, 0))
        self.connect((self.analog_const_source_x_0, 0), (self.blocks_float_to_complex_0, 1))
        self.connect((self.analog_sig_source_x_1, 0), (self.blocks_multiply_xx_1, 1))
        self.connect((self.audio_source_0, 0), (self.blocks_float_to_complex_0, 0))
        self.connect((self.blocks_add_const_vxx_0_0_0, 0), (self.fec_extended_decoder_0, 0))
        self.connect((self.blocks_float_to_complex_0, 0), (self.analog_agc_xx_0, 0))
        self.connect((self.blocks_multiply_const_xx_1_0_0, 0), (self.blocks_add_const_vxx_0_0_0, 0))
        self.connect((self.blocks_multiply_xx_1, 0), (self.fft_filter_xxx_0, 0))
        self.connect((self.blocks_repack_bits_bb_0_0, 0), (self.epy_block_1, 0))
        self.connect((self.blocks_uchar_to_float_0_0_0, 0), (self.blocks_multiply_const_xx_1_0_0, 0))
        self.connect((self.blocks_unpack_k_bits_bb_0_0, 0), (self.blocks_uchar_to_float_0_0_0, 0))
        self.connect((self.digital_constellation_decoder_cb_0_0_0, 0), (self.digital_diff_decoder_bb_0_0, 0))
        self.connect((self.digital_correlate_access_code_xx_ts_0, 0), (self.blocks_repack_bits_bb_0_0, 0))
        self.connect((self.digital_costas_loop_cc_0_0, 0), (self.digital_constellation_decoder_cb_0_0_0, 0))
        self.connect((self.digital_diff_decoder_bb_0_0, 0), (self.digital_map_bb_1_0, 0))
        self.connect((self.digital_map_bb_1_0, 0), (self.blocks_unpack_k_bits_bb_0_0, 0))
        self.connect((self.digital_symbol_sync_xx_0, 0), (self.digital_costas_loop_cc_0_0, 0))
        self.connect((self.fec_extended_decoder_0, 0), (self.digital_correlate_access_code_xx_ts_0, 0))
        self.connect((self.fft_filter_xxx_0, 0), (self.digital_symbol_sync_xx_0, 0))


    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_rrc_taps(firdes.root_raised_cosine(1, self.samp_rate, self.baudrate, 0.35, (51*self.sps)))
        self.set_sps(int(self.samp_rate/self.baudrate))
        self.analog_sig_source_x_1.set_sampling_freq(self.samp_rate)

    def get_baudrate(self):
        return self.baudrate

    def set_baudrate(self, baudrate):
        self.baudrate = baudrate
        self.set_rrc_taps(firdes.root_raised_cosine(1, self.samp_rate, self.baudrate, 0.35, (51*self.sps)))
        self.set_sps(int(self.samp_rate/self.baudrate))

    def get_sps(self):
        return self.sps

    def set_sps(self, sps):
        self.sps = sps
        self.set_rrc_taps(firdes.root_raised_cosine(1, self.samp_rate, self.baudrate, 0.35, (51*self.sps)))
        self.digital_symbol_sync_xx_0.set_sps(self.sps)

    def get_rrc_taps(self):
        return self.rrc_taps

    def set_rrc_taps(self, rrc_taps):
        self.rrc_taps = rrc_taps
        self.fft_filter_xxx_0.set_taps(self.rrc_taps)

    def get_packet_size(self):
        return self.packet_size

    def set_packet_size(self, packet_size):
        self.packet_size = packet_size
        self.epy_block_1.packet_size = self.packet_size

    def get_output_file_path(self):
        return self.output_file_path

    def set_output_file_path(self, output_file_path):
        self.output_file_path = output_file_path
        self.epy_block_1.out_filename = self.output_file_path

    def get_nfilts(self):
        return self.nfilts

    def set_nfilts(self, nfilts):
        self.nfilts = nfilts

    def get_loop_bandwidth(self):
        return self.loop_bandwidth

    def set_loop_bandwidth(self, loop_bandwidth):
        self.loop_bandwidth = loop_bandwidth
        self.digital_symbol_sync_xx_0.set_loop_bandwidth(self.loop_bandwidth)

    def get_const_definition(self):
        return self.const_definition

    def set_const_definition(self, const_definition):
        self.const_definition = const_definition
        self.digital_constellation_decoder_cb_0_0_0.set_constellation(self.const_definition)

    def get_cc_dec(self):
        return self.cc_dec

    def set_cc_dec(self, cc_dec):
        self.cc_dec = cc_dec

    def get_carrier_freq(self):
        return self.carrier_freq

    def set_carrier_freq(self, carrier_freq):
        self.carrier_freq = carrier_freq
        self.analog_sig_source_x_1.set_frequency((-self.carrier_freq))

    def get_access_key(self):
        return self.access_key

    def set_access_key(self, access_key):
        self.access_key = access_key




def receive(input_file_path, output_file_path, baudrate=250, carrier_freq=2500, top_block_cls=receiver, options=None):
    tb = top_block_cls()

    tb.set_baudrate(baudrate)
    tb.set_carrier_freq(carrier_freq)
    
    tb.set_input_file_path(input_file_path)
    tb.set_output_file_path(output_file_path)

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()

    tb.wait()


if __name__ == '__main__':
    receive()
