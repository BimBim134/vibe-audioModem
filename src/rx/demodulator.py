import sys
import signal
import threading
from typing import Any
import logging
import time
import pmt

import numpy as np
from gnuradio import analog, audio, blocks, digital, fec, gr, pdu, zeromq
from gnuradio.filter import firdes, hilbert_fc, freq_xlating_fir_filter_ccc
from gnuradio.fft import window

from src.config import PacketConfig, SignalConfig, PortsConfig
from src.config import (
    DEFAULT_PACKET_CONFIG,
    DEFAULT_SIGNAL_CONFIG,
    DEFAULT_DQPSK_CONST,
    DEFAULT_PORTS_CONFIG,
)

logger = logging.getLogger(__name__)


class Demodulator(gr.top_block):
    def set_carrier_freq(self, freq):
        """Update the carrier frequency and retune the translating filter."""
        self.sig.carrier_freq = freq
        self.freq_xlating_fir_filter_xxx_0.set_center_freq(freq)
        logger.info("Carrier frequency set to %.2f Hz", freq)

    def __init__(
        self,
        pkt: PacketConfig,
        sig: SignalConfig,
        constellation: Any,
        ports_conf: PortsConfig,
    ):
        """main Demodulator class

        Args:
            pkt (PacketConfig): packet configuration
            sig (SignalConfig): signal configuration
            constellation (Any): constellation definition
            ports_conf(PortsConfig): ports configuration
        """
        gr.top_block.__init__(self, "Demodulator master", catch_exceptions=False)
        logger.info("Demodulator class instanciated")
        logger.info(pkt)
        logger.info(sig)
        logger.info(ports_conf)

        self.id = time.asctime()

        self.flowgraph_started = threading.Event()

        # Variables
        ## signal related variables
        self.sig = sig
        self.const_definition = constellation
        self.freq_deviation = 100 / self.sig.samp_rate
        self.decimation = int(self.sig.sps / 8)
        self.variable_adaptive_algorithm_0 = digital.adaptive_algorithm_lms(
            self.const_definition, 0.001
        ).base()
        self.freq_deviation = 100 / self.sig.samp_rate

        ## digital communication variables
        self.pkt = pkt
        self.access_key = "11100001010110101110100010010011"
        self.hdr_format = digital.header_format_default(self.access_key, 0)
        self.cc_dec = fec.cc_decoder.make(
            8, 7, 2, [79, 109], 0, 0, fec.CC_STREAMING, True
        )

        ## ports configuration
        self.ports = ports_conf

        # Blocks
        # self.audio_source_0 = audio.source(self.sig.samp_rate, '', True)
        self.audio_source_0 = zeromq.sub_source(
            gr.sizeof_float,
            1,
            f"tcp://127.0.0.1:{self.ports.audio_port}",
            100,
            False,
            (-1),
            "",
            False,
        )
        ## signal preprocessing
        ### frequency shift
        self.hilbert_fc_0 = hilbert_fc(65, window.WIN_HAMMING, 6.76)  # float -> complex
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
            (self.sig.sps / self.decimation),
            0.045,
            (1 / np.sqrt(2)),
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
        self.digital_constellation_receiver_cb_0 = digital.constellation_receiver_cb(
            self.const_definition, 0.06, (-self.freq_deviation), self.freq_deviation
        )
        self.blocks_null_sink_0_1 = blocks.null_sink(gr.sizeof_float*1)
        self.blocks_null_sink_0_0 = blocks.null_sink(gr.sizeof_float*1)
        self.blocks_null_sink_0 = blocks.null_sink(gr.sizeof_float*1)

        ## constellation decoding
        self.digital_diff_decoder_bb_0 = digital.diff_decoder_bb(
            (2 ** self.const_definition.bits_per_symbol()), digital.DIFF_DIFFERENTIAL
        )
        self.digital_map_bb_0 = digital.map_bb(self.const_definition.pre_diff_code())

        ## convolutionnal error correction
        ### go from [0,1] to [-1, 1]
        self.blocks_unpack_k_bits_bb_0_0 = blocks.unpack_k_bits_bb(
            self.const_definition.bits_per_symbol()
        )
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
        self.digital_correlate_access_code_xx_ts_0 = (
            digital.correlate_access_code_bb_ts(self.access_key, 3, "packet_len")
        )
        self.blocks_repack_bits_bb_0_0 = blocks.repack_bits_bb(
            1, 8, "packet_len", True, gr.GR_MSB_FIRST
        )
        self.pdu_tagged_stream_to_pdu_0 = pdu.tagged_stream_to_pdu(
            gr.types.byte_t, "packet_len"
        )

        ## send output packets to zmq sink
        # self.pdu_set = pdu.pdu_set(k=pmt.intern(self.id), v=pmt.intern("value"))
        self.zeromq_pub_msg_sink_0 = zeromq.pub_msg_sink(
            f"tcp://127.0.0.1:{self.ports.raw_packets_port}", 100, False
        )

        ## send constellation points to zmq sink
        self.zeromq_pub_sink_0 = zeromq.pub_sink(
            gr.sizeof_gr_complex,
            1,
            f"tcp://127.0.0.1:{self.ports.constellation_port}",
            0,
            False,
            (-1),
            "",
            True,
            True,
        )

        # Connections
        self.connect((self.audio_source_0, 0), (self.hilbert_fc_0, 0))
        self.connect((self.hilbert_fc_0, 0), (self.freq_xlating_fir_filter_xxx_0, 0))
        self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.analog_agc_xx_0, 0))
        self.connect((self.digital_fll_band_edge_cc_0, 0), (self.digital_symbol_sync_xx_0, 0))
        self.connect((self.digital_symbol_sync_xx_0, 0), (self.digital_linear_equalizer_0, 0))
        self.connect((self.digital_linear_equalizer_0, 0),(self.digital_constellation_receiver_cb_0, 0),)
        self.connect((self.digital_constellation_receiver_cb_0, 0), (self.digital_diff_decoder_bb_0, 0))
        self.connect((self.digital_constellation_receiver_cb_0, 1), (self.blocks_null_sink_0, 0))
        self.connect((self.digital_constellation_receiver_cb_0, 2), (self.blocks_null_sink_0_0, 0))
        self.connect((self.digital_constellation_receiver_cb_0, 3), (self.blocks_null_sink_0_1, 0))
        self.connect((self.digital_constellation_receiver_cb_0, 4), (self.zeromq_pub_sink_0, 0))
        self.connect((self.digital_diff_decoder_bb_0, 0), (self.digital_map_bb_0, 0))
        self.connect((self.digital_map_bb_0, 0), (self.blocks_unpack_k_bits_bb_0_0, 0))
        self.connect((self.blocks_unpack_k_bits_bb_0_0, 0), (self.blocks_uchar_to_float_0_0_0, 0))
        self.connect((self.blocks_uchar_to_float_0_0_0, 0),(self.blocks_multiply_const_xx_1_0_0, 0),)
        self.connect((self.blocks_multiply_const_xx_1_0_0, 0),(self.blocks_add_const_vxx_0_0_0, 0),)
        self.connect((self.blocks_add_const_vxx_0_0_0, 0), (self.fec_extended_decoder_0, 0))
        self.connect((self.fec_extended_decoder_0, 0),(self.digital_correlate_access_code_xx_ts_0, 0),)
        self.connect((self.digital_correlate_access_code_xx_ts_0, 0),(self.blocks_repack_bits_bb_0_0, 0),)
        self.connect((self.blocks_repack_bits_bb_0_0, 0), (self.pdu_tagged_stream_to_pdu_0, 0))
        self.connect((self.analog_agc_xx_0, 0), (self.digital_fll_band_edge_cc_0, 0))
        # self.msg_connect((self.pdu_tagged_stream_to_pdu_0, "pdus"), (self.pdu_set, "pdus"))
        # self.msg_connect((self.pdu_set, "pdus"), (self.zeromq_pub_msg_sink_0, "in"))
        self.msg_connect((self.pdu_tagged_stream_to_pdu_0, "pdus"),(self.zeromq_pub_msg_sink_0, "in"),)


def launch_demodulator(
    pkt: PacketConfig = DEFAULT_PACKET_CONFIG,
    sig: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    constellation: Any = None,
    carrier_frequency: float | None = None,
    ports: PortsConfig = DEFAULT_PORTS_CONFIG,
    command_queue=None,
    status_queue=None,
):
    """receives an incomming transmission specified by **pkt**, **sig** and modulated using **constellation** at **carrier_frequency**.
    Outputs results on raw_packet_port defined in **ports**

    In worker mode (command_queue is not None), it waits for frequencies to tune to.
    """
    import copy

    signal_config = copy.copy(sig)
    ports_config = copy.copy(ports)

    if carrier_frequency:
        signal_config.carrier_freq = carrier_frequency

    if constellation is None:
        constellation = DEFAULT_DQPSK_CONST

    tb = Demodulator(pkt, signal_config, constellation, ports_config)

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    if command_queue is None:
        tb.start()
        tb.flowgraph_started.set()
        logger.info("Demodulator started (Legacy mode)")
        tb.wait()
    else:
        logger.info("Demodulator worker initialized and ready.")
        if status_queue:
            status_queue.put({"status": "ready"})

        while True:
            # Wait for a frequency or command
            cmd = command_queue.get()
            if cmd is None:  # Kill signal
                logger.info("Demodulator worker received kill signal.")
                break

            action = cmd.get("action", "start")

            if action == "start":
                freq = cmd.get("freq")
                if freq:
                    tb.set_carrier_freq(freq)

                tb.start()
                logger.info("Demodulator running for %.2f Hz", freq)
                if status_queue:
                    status_queue.put({"status": "running", "freq": freq})

                # Internal loop to wait for stop or kill while running
                while True:
                    cmd2 = command_queue.get()
                    if cmd2 is None:
                        tb.stop()
                        tb.wait()
                        return
                    if cmd2.get("action") == "stop":
                        tb.stop()
                        tb.wait()
                        logger.info("Demodulator stopped, returning to idle.")
                        if status_queue:
                            status_queue.put({"status": "ready"})
                        break
            elif action == "stop":
                tb.stop()
                tb.wait()
                if status_queue:
                    status_queue.put({"status": "ready"})


if __name__ == "__main__":
    pass
