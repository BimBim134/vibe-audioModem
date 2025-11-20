#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: transmitter 3
# Author: bimbim
# GNU Radio version: 3.10.10.0

import sys
import signal
from typing import Any
import threading

from gnuradio import analog, blocks, digital, fec, gr, audio

from bin2packet import prepare_data
from config import PacketConfig, SignalConfig
from config import DEFAULT_PACKET_CONFIG, DEFAULT_SIGNAL_CONFIG


class Transmitter(gr.top_block):
    def __init__(
        self,
        input_data: Any,
        pkt: PacketConfig,
        sig: SignalConfig,
    ):
        """main transmitter class (heavily based on GRC companion output)

        Args:
            input_data (Any): input data
            pkt (PacketConfig): packet description
            sig (SignalConfig): signal description
        """
        gr.top_block.__init__(self, "Transmitter", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        # Variables
        ## signal related variables
        self.sig = sig
        self.const_definition = digital.constellation_calcdist(
            [-1 - 1j, -1 + 1j, 1 + 1j, 1 - 1j],
            [0, 1, 3, 2],
            4,
            1,
            digital.constellation.AMPLITUDE_NORMALIZATION,
        ).base()
        self.const_definition.set_npwr(0)
        self.const_definition.gen_soft_dec_lut(8)

        ## digital communication variables
        self.pkt = pkt
        self.input_file = prepare_data(input_data, pkt)
        self.access_key = "11100001010110101110100010010011"
        self.hdr_format = digital.header_format_default(self.access_key, 0)
        self.cc_enc = fec.cc_encoder_make(
            128, 7, 2, [79, 109], 0, fec.CC_STREAMING, True
        )

        # Blocks
        self.fec_extended_encoder_0 = fec.extended_encoder(
            encoder_obj_list=self.cc_enc, threading=None, puncpat="11"
        )
        self.digital_protocol_formatter_bb_0 = digital.protocol_formatter_bb(
            self.hdr_format, "packet_len"
        )
        self.digital_constellation_modulator_0 = digital.generic_mod(
            constellation=self.const_definition,
            differential=True,
            samples_per_symbol=self.sig.sps,
            pre_diff_code=True,
            excess_bw=0.35,
            verbose=False,
            log=False,
            truncate=True,
        )
        self.blocks_vector_source_x_0 = blocks.vector_source_b(
            self.input_file, False, 1, []
        )
        self.blocks_unpack_k_bits_bb_0 = blocks.unpack_k_bits_bb(8)
        self.blocks_throttle2_0 = blocks.throttle(
            gr.sizeof_float * 1,
            self.sig.samp_rate,
            True,
            (
                0
                if "auto" == "auto"
                else max(
                    (
                        int(float(0.1) * self.sig.samp_rate)
                        if "auto" == "time"
                        else int(0.1)
                    ),
                    1,
                )
            ),
        )
        self.blocks_tagged_stream_mux_0 = blocks.tagged_stream_mux(
            gr.sizeof_char * 1, "packet_len", 0
        )
        self.blocks_stream_to_tagged_stream_0 = blocks.stream_to_tagged_stream(
            gr.sizeof_char, 1, self.pkt.total_packets_len, "packet_len"
        )
        self.blocks_repack_bits_bb_1_0 = blocks.repack_bits_bb(
            1, 8, "", False, gr.GR_MSB_FIRST
        )
        self.blocks_multiply_xx_0 = blocks.multiply_vcc(1)
        self.blocks_complex_to_real_0 = blocks.complex_to_real(1)
        self.audio_sink_0 = audio.sink(self.sig.samp_rate, "", True)
        self.analog_sig_source_x_0 = analog.sig_source_c(
            self.sig.samp_rate, analog.GR_SIN_WAVE, self.sig.carrier_freq, 0.5, 0, 0
        )

        # Connections
        self.connect((self.analog_sig_source_x_0, 0),
                     (self.blocks_multiply_xx_0, 1))
        self.connect((self.blocks_complex_to_real_0, 0),
                     (self.blocks_throttle2_0, 0))
        self.connect((self.blocks_multiply_xx_0, 0),
                     (self.blocks_complex_to_real_0, 0))
        self.connect((self.blocks_repack_bits_bb_1_0, 0),
                     (self.digital_constellation_modulator_0, 0))
        self.connect((self.blocks_stream_to_tagged_stream_0, 0),
                     (self.blocks_tagged_stream_mux_0, 1))
        self.connect((self.blocks_stream_to_tagged_stream_0, 0),
                     (self.digital_protocol_formatter_bb_0, 0))
        self.connect((self.blocks_tagged_stream_mux_0, 0), 
                     (self.blocks_unpack_k_bits_bb_0, 0))
        self.connect((self.blocks_throttle2_0, 0),
                     (self.audio_sink_0, 0))
        self.connect((self.blocks_unpack_k_bits_bb_0, 0),
                     (self.fec_extended_encoder_0, 0))
        self.connect((self.blocks_vector_source_x_0, 0),
                     (self.blocks_stream_to_tagged_stream_0, 0))
        self.connect((self.digital_constellation_modulator_0, 0),
                     (self.blocks_multiply_xx_0, 0))
        self.connect((self.digital_protocol_formatter_bb_0, 0),
                     (self.blocks_tagged_stream_mux_0, 0))
        self.connect((self.fec_extended_encoder_0, 0),
                     (self.blocks_repack_bits_bb_1_0, 0))

    def get_samp_rate(self):
        return self.sig.samp_rate

    def set_samp_rate(self, samp_rate):
        self.sig.samp_rate = samp_rate
        self.set_sps(int(self.sig.samp_rate / self.sig.baudrate))
        self.analog_sig_source_x_0.set_sampling_freq(self.sig.samp_rate)
        self.blocks_throttle2_0.set_sample_rate(self.sig.samp_rate)

    def get_baudrate(self):
        return self.sig.baudrate

    def set_baudrate(self, baudrate):
        self.sig.baudrate = baudrate
        self.set_sps(int(self.sig.samp_rate / self.sig.baudrate))

    def get_access_key(self):
        return self.access_key

    def set_access_key(self, access_key):
        self.access_key = access_key
        self.set_hdr_format(digital.header_format_default(self.access_key, 0))

    def get_sps(self):
        return self.sig.sps

    def set_sps(self, sps):
        self.sig.sps = sps

    def get_packet_size(self):
        return self.pkt.total_packets_len

    def set_packet_size(self, packet_size):
        self.pkt.total_packets_len = packet_size
        self.blocks_stream_to_tagged_stream_0.set_packet_len(self.pkt.total_packets_len)
        self.blocks_stream_to_tagged_stream_0.set_packet_len_pmt(
            self.pkt.total_packets_len
        )

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
        return self.sig.carrier_freq

    def set_carrier_freq(self, carrier_freq):
        self.sig.carrier_freq = carrier_freq
        self.analog_sig_source_x_0.set_frequency(self.sig.carrier_freq)


def transmit(
    input_file: Any,
    pkt_conf: PacketConfig = DEFAULT_PACKET_CONFIG,
    signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
) -> None:
    """transmit a file over sound !

    Args:
        input_file (Any): input file
        pkt_conf (PacketConfig, optional): packet description. Defaults to DEFAULT_PACKET_CONFIG.
        signal_conf (SignalConfig, optional): signal description. Defaults to DEFAULT_SIGNAL_CONFIG.
    """
    tb = Transmitter(input_data=input_file, pkt=pkt_conf, sig=signal_conf)

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    tb.flowgraph_started.set()

    tb.wait()


if __name__ == "__main__":
    transmit(b"hello world ! this is a message transmitted using vibe-audio-modem :)")
