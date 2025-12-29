import sys
import signal
import threading

import numpy as np
from gnuradio import analog, audio, blocks, digital, fec, gr, pdu, zeromq


from config import PacketConfig, SignalConfig
from config import DEFAULT_PACKET_CONFIG, DEFAULT_SIGNAL_CONFIG, DEFAULT_DQPSK_CONST


class Receiver(gr.top_block):

    def __init__(self, pkt: PacketConfig, sig: SignalConfig, constellation):
        gr.top_block.__init__(self, "receiver master", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        # Variables
        ## signal related variables
        self.sig = sig
        self.const_definition = constellation
        self.freq_deviation = 100 / self.sig.samp_rate

        ## digital communication variables
        self.pkt = pkt
        self.access_key = "11100001010110101110100010010011"
        self.hdr_format = digital.header_format_default(self.access_key, 0)
        self.cc_dec = cc_dec = fec.cc_decoder.make(
            8, 7, 2, [79, 109], 0, 0, fec.CC_STREAMING, True
        )

        # Blocks
        self.zeromq_pub_msg_sink = zeromq.pub_msg_sink("tcp://*:5555", 100, True)
        self.pdu_tagged_stream_to_pdu = pdu.tagged_stream_to_pdu(
            gr.types.byte_t, "packet_len"
        )
        self.fec_extended_decoder = fec.extended_decoder(
            decoder_obj_list=cc_dec,
            threading=None,
            ann=None,
            puncpat="11",
            integration_period=10000,
        )
        self.digital_correlate_access_code_xx_ts = digital.correlate_access_code_bb_ts(
            self.access_key, 3, "packet_len"
        )
        self.digital_constellation_receiver_cb = digital.constellation_receiver_cb(
            self.const_definition, 0.06, (-self.freq_deviation), self.freq_deviation
        )
        self.blocks_unpack_k_bits_bb = blocks.unpack_k_bits_bb(
            int(np.log2(len(self.const_definition.points())))
        )
        self.blocks_uchar_to_float = blocks.uchar_to_float()
        self.blocks_repack_bits_bb = blocks.repack_bits_bb(
            1, 8, "packet_len", True, gr.GR_MSB_FIRST
        )
        self.blocks_multiply_xx_1 = blocks.multiply_vcc(1)
        self.blocks_multiply_const_xx_1 = blocks.multiply_const_ff(2, 1)
        self.blocks_float_to_complex = blocks.float_to_complex(1)
        self.blocks_add_const_vxx = blocks.add_const_ff((-1))
        self.audio_source = audio.source(self.sig.samp_rate, "hw:4,0", True)
        self.analog_sig_source_x_1 = analog.sig_source_c(
            self.sig.samp_rate, analog.GR_SIN_WAVE, (-self.sig.carrier_freq), 1, 0, 0
        )
        self.analog_const_source_x = analog.sig_source_f(
            0, analog.GR_CONST_WAVE, 0, 0, 0
        )
        self.analog_agc_xx = analog.agc_cc((1e-4), (2 * np.sqrt(2)), 1.0, 10)

        # Connections

        self.msg_connect(
            (self.pdu_tagged_stream_to_pdu, "pdus"), (self.zeromq_pub_msg_sink, "in")
        )
        self.connect((self.analog_agc_xx, 0), (self.blocks_multiply_xx_1, 0))
        self.connect((self.analog_const_source_x, 0), (self.blocks_float_to_complex, 1))
        self.connect((self.analog_sig_source_x_1, 0), (self.blocks_multiply_xx_1, 1))
        self.connect((self.audio_source, 0), (self.blocks_float_to_complex, 0))
        self.connect((self.blocks_add_const_vxx, 0), (self.fec_extended_decoder, 0))
        self.connect((self.blocks_float_to_complex, 0), (self.analog_agc_xx, 0))
        self.connect(
            (self.blocks_multiply_const_xx_1, 0), (self.blocks_add_const_vxx, 0)
        )
        self.connect(
            (self.blocks_multiply_xx_1, 0), (self.digital_constellation_receiver_cb, 0)
        )
        self.connect(
            (self.blocks_repack_bits_bb, 0), (self.pdu_tagged_stream_to_pdu, 0)
        )
        self.connect(
            (self.blocks_uchar_to_float, 0), (self.blocks_multiply_const_xx_1, 0)
        )
        self.connect((self.blocks_unpack_k_bits_bb, 0), (self.blocks_uchar_to_float, 0))
        self.connect(
            (self.digital_constellation_receiver_cb, 0),
            (self.blocks_unpack_k_bits_bb, 0),
        )
        self.connect(
            (self.digital_correlate_access_code_xx_ts, 0),
            (self.blocks_repack_bits_bb, 0),
        )
        self.connect(
            (self.fec_extended_decoder, 0),
            (self.digital_correlate_access_code_xx_ts, 0),
        )


def receive(
    pkt_conf: PacketConfig = DEFAULT_PACKET_CONFIG,
    signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    constellation=DEFAULT_DQPSK_CONST,
):

    tb = Receiver(pkt=pkt_conf, sig=signal_conf, constellation=constellation)

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
    receive()
