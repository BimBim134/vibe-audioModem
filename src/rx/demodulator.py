import sys
import signal
import threading
from typing import Any
import logging
import time

import numpy as np
from gnuradio import analog, audio, blocks, digital, fec, gr, pdu, zeromq
from gnuradio.filter import firdes, hilbert_fc, freq_xlating_fir_filter_ccc
from gnuradio.fft import window

from src.config import PacketConfig, SignalConfig, PortsConfig
from src.config import DEFAULT_PACKET_CONFIG, DEFAULT_SIGNAL_CONFIG, DEFAULT_DQPSK_CONST, DEFAULT_PORTS_CONFIG

logging.basicConfig(format="%(levelname)s: %(processName)s: %(module)s: %(funcName)s: %(message)s", level=logging.DEBUG)


class Demodulator(gr.top_block):
    def __init__(self, pkt: PacketConfig,
                 sig: SignalConfig,
                 constellation: Any,
                 ports_conf: PortsConfig):
        """main Demodulator class

        Args:
            pkt (PacketConfig): packet configuration
            sig (SignalConfig): signal configuration
            constellation (Any): constellation definition
            ports_conf(PortsConfig): ports configuration
        """
        gr.top_block.__init__(self, "Demodulator master", catch_exceptions=False)
        logging.info("Demodulator class instanciated")
        logging.info(pkt)
        logging.info(sig)
        logging.info(ports_conf)
        
        self.id = time.asctime()

        self.flowgraph_started = threading.Event()

        # Variables
        ## signal related variables
        self.sig = sig
        self.const_definition = constellation
        self.freq_deviation = 100 / self.sig.samp_rate
        self.decimation = int(self.sig.sps/8)
        self.variable_adaptive_algorithm_0 = digital.adaptive_algorithm_lms(
            self.const_definition, 0.001
        ).base()
        self.freq_deviation = 100/self.sig.samp_rate

        ## digital communication variables
        self.pkt = pkt
        self.access_key = "11100001010110101110100010010011"
        self.hdr_format = digital.header_format_default(self.access_key, 0)
        self.cc_dec = fec.cc_decoder.make(8, 7, 2, [79, 109], 0, 0, fec.CC_STREAMING, True)

        ## ports configuration
        self.ports = ports_conf

        # Blocks
        # self.audio_source_0 = audio.source(self.sig.samp_rate, '', True)
        self.audio_source_0 = zeromq.sub_source(gr.sizeof_float, 1, f'tcp://127.0.0.1:{self.ports.audio_port}', 100, False, (-1), '', False)
        ## signal preprocessing
        ### frequency shift
        self.hilbert_fc_0 = hilbert_fc(65, window.WIN_HAMMING, 6.76) # float -> complex
        self.freq_xlating_fir_filter_xxx_0 = freq_xlating_fir_filter_ccc(
            self.decimation,
            firdes.complex_band_pass(
                1,
                self.sig.samp_rate,
                -self.sig.samp_rate / (2 * self.decimation),
                self.sig.samp_rate / (2 * self.decimation),
                10,
            ),
            self.sig.carrier_freq,
            self.sig.samp_rate,
        )
        ### Automatic Gain Control
        self.analog_agc_xx_0 = analog.agc_cc((1e-4), np.sqrt(2), 1.0, 10)
        ### Coarse frequency correction
        self.digital_fll_band_edge_cc_0 = digital.fll_band_edge_cc(
            (self.sig.sps / self.decimation), 0.35, 44, (1e-3)
        )

        ## symbol synchronization
        self.digital_symbol_sync_xx_0 = digital.symbol_sync_cc(
            digital.TED_GARDNER,
            (self.sig.sps/self.decimation),
            0.045,
            (1/np.sqrt(2)),
            1.0,
            1.5,
            3,
            self.const_definition,
            digital.IR_PFB_NO_MF,
            128,
            )
        self.digital_linear_equalizer_0 = digital.linear_equalizer(
            15, 3, self.variable_adaptive_algorithm_0, True, [], "corr_est"
        )
        self.digital_constellation_receiver_cb_0 = digital.constellation_receiver_cb(self.const_definition, 0.06, (-self.freq_deviation), self.freq_deviation)

        ## constellation decoding
        self.digital_diff_decoder_bb_0 = digital.diff_decoder_bb(
            (2 ** self.const_definition.bits_per_symbol()), digital.DIFF_DIFFERENTIAL
        )
        self.digital_map_bb_0 = digital.map_bb(self.const_definition.pre_diff_code())

        ## convolutionnal error correction
        ### go from [0,1] to [-1, 1]
        self.blocks_unpack_k_bits_bb_0_0 = blocks.unpack_k_bits_bb(self.const_definition.bits_per_symbol())
        self.blocks_uchar_to_float_0_0_0 = blocks.uchar_to_float()
        self.blocks_multiply_const_xx_1_0_0 = blocks.multiply_const_ff(2, 1)
        self.blocks_add_const_vxx_0_0_0 = blocks.add_const_ff((-1))
        ### actual decoding
        self.fec_extended_decoder_0 = fec.extended_decoder(
            decoder_obj_list=self.cc_dec,
            threading=None,
            ann=None,
            puncpat="11",
            integration_period=10000,
        )

        ## frame synchronization
        self.digital_correlate_access_code_xx_ts_0 = digital.correlate_access_code_bb_ts(self.access_key, 3, 'packet_len')
        self.blocks_repack_bits_bb_0_0 = blocks.repack_bits_bb(1, 8, "packet_len", True, gr.GR_MSB_FIRST)
        self.pdu_tagged_stream_to_pdu_0 = pdu.tagged_stream_to_pdu(gr.types.byte_t, 'packet_len')

        ## send output packets to zmq sink
        self.pdu_meta_set_0 = pdu.pdu_meta_set(pmt.intern("key"), pmt.intern(self.id), False)
        self.zeromq_pub_msg_sink_0 = zeromq.pub_msg_sink(f"tcp://127.0.0.1:{self.ports.raw_packets_port}", 100, False)

        # Connections
        self.connect((self.audio_source_0, 0), (self.hilbert_fc_0, 0))
        self.connect((self.hilbert_fc_0, 0), (self.freq_xlating_fir_filter_xxx_0, 0))
        self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.analog_agc_xx_0, 0))
        self.connect((self.digital_fll_band_edge_cc_0, 0), (self.digital_symbol_sync_xx_0, 0))
        self.connect((self.digital_symbol_sync_xx_0, 0), (self.digital_linear_equalizer_0, 0))
        self.connect((self.digital_linear_equalizer_0, 0), (self.digital_constellation_receiver_cb_0, 0))
        self.connect((self.digital_constellation_receiver_cb_0, 0), (self.digital_diff_decoder_bb_0, 0))
        self.connect((self.digital_diff_decoder_bb_0, 0), (self.digital_map_bb_0, 0))
        self.connect((self.digital_map_bb_0, 0), (self.blocks_unpack_k_bits_bb_0_0, 0))
        self.connect((self.blocks_unpack_k_bits_bb_0_0, 0), (self.blocks_uchar_to_float_0_0_0, 0))
        self.connect((self.blocks_uchar_to_float_0_0_0, 0), (self.blocks_multiply_const_xx_1_0_0, 0))
        self.connect((self.blocks_multiply_const_xx_1_0_0, 0), (self.blocks_add_const_vxx_0_0_0, 0))
        self.connect((self.blocks_add_const_vxx_0_0_0, 0), (self.fec_extended_decoder_0, 0))
        self.connect((self.fec_extended_decoder_0, 0), (self.digital_correlate_access_code_xx_ts_0, 0))
        self.connect((self.digital_correlate_access_code_xx_ts_0, 0), (self.blocks_repack_bits_bb_0_0, 0))
        self.connect((self.blocks_repack_bits_bb_0_0, 0), (self.pdu_tagged_stream_to_pdu_0, 0))
        self.connect((self.analog_agc_xx_0, 0), (self.digital_fll_band_edge_cc_0, 0))
        self.msg_connect((self.pdu_tagged_stream_to_pdu_0, "pdus"), (self.pdu_meta_set_0, "pdus"))
        self.msg_connect((self.pdu_meta_set_0, "pdus"), (self.zeromq_pub_msg_sink_0, "in"))


def launch_demodulator(
    pkt: PacketConfig = DEFAULT_PACKET_CONFIG,
    sig: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    constellation: Any = DEFAULT_DQPSK_CONST,
    carrier_frequency: float | None = None,
    ports: PortsConfig = DEFAULT_PORTS_CONFIG,
):
    """receives an incomming transmission specified by **pkt**, **sig** and modulated using **constellation** at **carrier_frequency**.
    Outputs results on raw_packet_port defined in **ports**

    Args:
        pkt (PacketConfig, optional): packet configuration. Defaults to DEFAULT_PACKET_CONFIG.
        sig (SignalConfig, optional): signal configuration. Defaults to DEFAULT_SIGNAL_CONFIG.
        constellation (Any, optional): constellation definition. Defaults to DEFAULT_DQPSK_CONST.
        carrier_frequency (float | None, optionnal): carrier frequency. Defaults to None.
        ports (PortsConfig, optional): ports configuration. Defaults to DEFAULT_PORTS_CONFIG.
    """
    import copy
    signal_config = sig
    ports_config = copy.copy(ports)

    if carrier_frequency:
        signal_config.carrier_freq = carrier_frequency

    tb = Demodulator(pkt, signal_config, constellation, ports_config)

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    tb.flowgraph_started.set()
    logging.info("Demodulator started")

    tb.wait()


logging.info("Demodulator module loaded")


if __name__ == "__main__":
    pass