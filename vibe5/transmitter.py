#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: transmitter 3
# Author: bimbim
# GNU Radio version: 3.10.10.0

from gnuradio import analog
from gnuradio import blocks
from gnuradio import digital
from gnuradio import fec
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
import numpy as np
import bin2packet_block as epy_bin2packet_block  # embedded python block




class transmitter_003(gr.top_block):

    def __init__(self):
        gr.top_block.__init__(self, "transmitter 3", catch_exceptions=True)

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 44100
        self.baudrate = baudrate = 100
        self.access_key = access_key = '11100001010110101110100010010011'
        self.sps = sps = int(samp_rate/baudrate)
        self.samp_rate_0 = samp_rate_0 = 44100
        self.packet_size = packet_size = 64
        self.output_file_path = output_file_path = ""
        self.input_file_path = input_file_path = ""
        self.hdr_format = hdr_format = digital.header_format_default(access_key, 0)
        self.const_definition = const_definition = digital.constellation_calcdist([-1-1j, -1+1j, 1+1j, 1-1j], [0, 1, 3, 2],
        4, 1, digital.constellation.AMPLITUDE_NORMALIZATION).base()
        self.const_definition.set_npwr(0)
        self.const_definition.gen_soft_dec_lut(8)
        self.cc_enc = cc_enc = fec.cc_encoder_make(128,7, 2, [79,109], 0, fec.CC_STREAMING, True)
        self.carrier_freq = carrier_freq = 5000

        ##################################################
        # Blocks
        ##################################################

        self.fec_extended_encoder_0 = fec.extended_encoder(encoder_obj_list=cc_enc, threading= None, puncpat='11')
        self.epy_bin2packet_block = epy_bin2packet_block.blk(input_binary=input_file_path, packet_size=packet_size, preamble_size=3, postamble_size=6, ecc_size=10, id_len=2, data_len=1)
        self.digital_protocol_formatter_bb_0 = digital.protocol_formatter_bb(hdr_format, "packet_len")
        self.digital_constellation_modulator_0 = digital.generic_mod(
            constellation=const_definition,
            differential=True,
            samples_per_symbol=sps,
            pre_diff_code=True,
            excess_bw=0.35,
            verbose=False,
            log=False,
            truncate=True)
        self.blocks_wavfile_sink_0 = blocks.wavfile_sink(
            output_file_path,
            1,
            samp_rate,
            blocks.FORMAT_WAV,
            blocks.FORMAT_PCM_16,
            False
            )
        self.blocks_unpack_k_bits_bb_0 = blocks.unpack_k_bits_bb(8)
        self.blocks_throttle2_0 = blocks.throttle( gr.sizeof_float*1, samp_rate, True, 0 if "auto" == "auto" else max( int(float(0.1) * samp_rate) if "auto" == "time" else int(0.1), 1) )
        self.blocks_tagged_stream_mux_0 = blocks.tagged_stream_mux(gr.sizeof_char*1, 'packet_len', 0)
        self.blocks_stream_to_tagged_stream_0 = blocks.stream_to_tagged_stream(gr.sizeof_char, 1, packet_size, "packet_len")
        self.blocks_repack_bits_bb_1_0 = blocks.repack_bits_bb(1, 8, "", False, gr.GR_MSB_FIRST)
        self.blocks_multiply_xx_0 = blocks.multiply_vcc(1)
        self.blocks_complex_to_real_0 = blocks.complex_to_real(1)
        self.analog_sig_source_x_0 = analog.sig_source_c(samp_rate, analog.GR_SIN_WAVE, carrier_freq, 0.5, 0, 0)


        ##################################################
        # Connections
        ##################################################
        self.connect((self.analog_sig_source_x_0, 0), (self.blocks_multiply_xx_0, 1))
        self.connect((self.blocks_complex_to_real_0, 0), (self.blocks_throttle2_0, 0))
        self.connect((self.blocks_multiply_xx_0, 0), (self.blocks_complex_to_real_0, 0))
        self.connect((self.blocks_repack_bits_bb_1_0, 0), (self.digital_constellation_modulator_0, 0))
        self.connect((self.blocks_stream_to_tagged_stream_0, 0), (self.blocks_tagged_stream_mux_0, 1))
        self.connect((self.blocks_stream_to_tagged_stream_0, 0), (self.digital_protocol_formatter_bb_0, 0))
        self.connect((self.blocks_tagged_stream_mux_0, 0), (self.blocks_unpack_k_bits_bb_0, 0))
        self.connect((self.blocks_throttle2_0, 0), (self.blocks_wavfile_sink_0, 0))
        self.connect((self.blocks_unpack_k_bits_bb_0, 0), (self.fec_extended_encoder_0, 0))
        self.connect((self.digital_constellation_modulator_0, 0), (self.blocks_multiply_xx_0, 0))
        self.connect((self.digital_protocol_formatter_bb_0, 0), (self.blocks_tagged_stream_mux_0, 0))
        self.connect((self.epy_bin2packet_block, 0), (self.blocks_stream_to_tagged_stream_0, 0))
        self.connect((self.fec_extended_encoder_0, 0), (self.blocks_repack_bits_bb_1_0, 0))


    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.set_sps(int(self.samp_rate/self.baudrate))
        self.analog_sig_source_x_0.set_sampling_freq(self.samp_rate)
        self.blocks_throttle2_0.set_sample_rate(self.samp_rate)

    def get_baudrate(self):
        return self.baudrate

    def set_baudrate(self, baudrate):
        self.baudrate = baudrate
        self.set_sps(int(self.samp_rate/self.baudrate))

    def get_access_key(self):
        return self.access_key

    def set_access_key(self, access_key):
        self.access_key = access_key
        self.set_hdr_format(digital.header_format_default(self.access_key, 0))

    def get_sps(self):
        return self.sps

    def set_sps(self, sps):
        self.sps = sps

    def get_samp_rate_0(self):
        return self.samp_rate_0

    def set_samp_rate_0(self, samp_rate_0):
        self.samp_rate_0 = samp_rate_0

    def get_packet_size(self):
        return self.packet_size

    def set_packet_size(self, packet_size):
        self.packet_size = packet_size
        self.blocks_stream_to_tagged_stream_0.set_packet_len(self.packet_size)
        self.blocks_stream_to_tagged_stream_0.set_packet_len_pmt(self.packet_size)
        self.epy_bin2packet_block.packet_size = self.packet_size

    def get_output_file_path(self):
        return self.output_file_path

    def set_output_file_path(self, output_file_path):
        self.output_file_path = output_file_path
        self.blocks_wavfile_sink_0.open(self.output_file_path)

    def get_input_file_path(self):
        return self.input_file_path

    def set_input_file_path(self, input_file_path):
        self.input_file_path = input_file_path

    def get_hdr_format(self):
        return self.hdr_format

    def set_hdr_format(self, hdr_format):
        self.hdr_format = hdr_format
        self.digital_protocol_formatter_bb_0.set_header_format(self.hdr_format)

    def get_const_definition(self):
        return self.const_definition

    def set_const_definition(self, const_definition):
        self.const_definition = const_definition

    def get_cc_enc(self):
        return self.cc_enc

    def set_cc_enc(self, cc_enc):
        self.cc_enc = cc_enc

    def get_carrier_freq(self):
        return self.carrier_freq

    def set_carrier_freq(self, carrier_freq):
        self.carrier_freq = carrier_freq
        self.analog_sig_source_x_0.set_frequency(self.carrier_freq)




def transmit(input_file_path, output_file_path, baudrate=250, carrier_freq=2500, top_block_cls=transmitter_003, options=None):
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
    transmit()
