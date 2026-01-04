import sys
import signal
from typing import Any
import threading

from gnuradio import blocks, digital, fec, gr, audio, analog
import numpy as np

from bin2packet import prepare_data
from config import PacketConfig, SignalConfig
from config import DEFAULT_PACKET_CONFIG, DEFAULT_SIGNAL_CONFIG, DEFAULT_DQPSK_CONST


class Transmitter(gr.top_block):
    def __init__(
        self,
        input_data: Any,
        pkt: PacketConfig,
        sig: SignalConfig,
        constellation:Any
    ):
        """main transmitter class

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
        self.const_definition = constellation

        ## digital communication variables
        self.pkt = pkt
        self.input_file = prepare_data(input_data, pkt)
        self.access_key = "11100001010110101110100010010011"
        self.hdr_format = digital.header_format_default(self.access_key, 0)
        self.cc_enc = fec.cc_encoder_make(pkt.total_packets_len, 7, 2, [79, 109], 0, fec.CC_STREAMING, False)

        # Blocks
        ## file source
        self.blocks_vector_source_x_0 = blocks.vector_source_b(self.input_file)

        ## protocol layer
        self.blocks_stream_to_tagged_stream_0 = blocks.stream_to_tagged_stream(gr.sizeof_char, 1, self.pkt.total_packets_len, "packet_len")
        self.digital_protocol_formatter_bb_0 = digital.protocol_formatter_bb(self.hdr_format, "packet_len")
        self.blocks_tagged_stream_mux_0 = blocks.tagged_stream_mux(gr.sizeof_char*1, 'packet_len', 0)

        ## convolutionnal error correction encoding
        self.blocks_unpack_k_bits_bb_0 = blocks.unpack_k_bits_bb(8)
        self.fec_extended_encoder_0 = fec.extended_encoder(encoder_obj_list=self.cc_enc, threading= None, puncpat='11')
        self.blocks_repack_bits_bb_1_0 = blocks.repack_bits_bb(1, 8, "", False, gr.GR_MSB_FIRST)

        ## modulation
        self.digital_constellation_modulator_0 = digital.generic_mod(
            constellation=self.const_definition,
            differential=True,
            samples_per_symbol=self.sig.sps,
            pre_diff_code=True,
            excess_bw=0.35,
            verbose=False,
            log=False,
            truncate=True)
        self.blocks_rotator_cc_0 = blocks.rotator_cc((2 * np.pi * (self.sig.carrier_freq / self.sig.samp_rate)), False)
        self.blocks_complex_to_real_0 = blocks.complex_to_real(1)
        self.blocks_multiply_const_vxx_0 = blocks.multiply_const_ff((1/4))

        ## head block to terminate cleanly the flow graph after everything is sent
        self.blocks_head_0 = blocks.head(gr.sizeof_float*1, self.get_nb_of_audio_samples())

        ## beeper to help receiver to lock to carrier frequency
        self.analog_sig_source_x_0 = analog.sig_source_f(self.sig.samp_rate, analog.GR_SIN_WAVE, self.sig.carrier_freq, 0.25, 0, 0)

        ## first beeper, then data transmission
        self.blocks_stream_mux_0 = blocks.stream_mux(gr.sizeof_float*1, (self.sig.beeper_nb_sample, self.get_nb_of_audio_samples()))

        ## out audio
        self.audio_sink_0 = audio.sink(self.sig.samp_rate, '', True)

        # Connections between blocks
        self.connect((self.blocks_vector_source_x_0, 0), (self.blocks_stream_to_tagged_stream_0, 0))
        self.connect((self.blocks_stream_to_tagged_stream_0, 0), (self.blocks_tagged_stream_mux_0, 1))
        self.connect((self.blocks_stream_to_tagged_stream_0, 0), (self.digital_protocol_formatter_bb_0, 0))
        self.connect((self.digital_protocol_formatter_bb_0, 0), (self.blocks_tagged_stream_mux_0, 0))
        self.connect((self.blocks_tagged_stream_mux_0, 0), (self.blocks_unpack_k_bits_bb_0, 0))
        self.connect((self.blocks_unpack_k_bits_bb_0, 0), (self.fec_extended_encoder_0, 0))
        self.connect((self.fec_extended_encoder_0, 0), (self.blocks_repack_bits_bb_1_0, 0))
        self.connect((self.blocks_repack_bits_bb_1_0, 0), (self.digital_constellation_modulator_0, 0))
        self.connect((self.digital_constellation_modulator_0, 0), (self.blocks_rotator_cc_0, 0))
        self.connect((self.blocks_rotator_cc_0, 0), (self.blocks_complex_to_real_0, 0))
        self.connect((self.blocks_complex_to_real_0, 0), (self.blocks_multiply_const_vxx_0, 0))
        self.connect((self.blocks_multiply_const_vxx_0, 0), (self.blocks_head_0, 0))
        self.connect((self.blocks_head_0, 0), (self.blocks_stream_mux_0, 1))
        self.connect((self.blocks_stream_mux_0, 0), (self.audio_sink_0, 0))
        self.connect((self.analog_sig_source_x_0, 0), (self.blocks_stream_mux_0, 0))

    def get_nb_of_audio_samples(self) -> int:
        """ calculate the correct number of audio sample to transmit 
        * nb_bits_transmitted = (total file length + access keys + packet_len tags) * rate FEC

        Returns:
            int: number of audio sample to transmit
        """
        nb_packet = int(len(self.input_file) / self.pkt.total_packets_len)
        nb_bits_transmitted = (
            len(self.input_file) * 8 + nb_packet * len(self.access_key) + nb_packet * 32
        ) * 2
        audio_samples_to_transmit = nb_bits_transmitted * self.sig.sps
        audio_samples_to_transmit += int(0.1 * audio_samples_to_transmit) # some extra margin (+10% samples)
        return audio_samples_to_transmit


def send_data(
    input_data: Any,
    pkt: PacketConfig = DEFAULT_PACKET_CONFIG,
    sig: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    constellation: Any = DEFAULT_DQPSK_CONST,
):
    tb = Transmitter(input_data, pkt, sig, constellation)

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
    send_data(b"hello world ! this is a message transmitted using vibe-audio-modem :)")
