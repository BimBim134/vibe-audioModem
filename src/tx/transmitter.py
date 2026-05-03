import sys
import signal
import time
from typing import Any
import threading
import logging

from gnuradio import blocks, digital, fec, gr, audio, analog
import numpy as np

from src.tx.packetizer import prepare_data
from src.misc.config import PacketConfig, SignalConfig
from src.misc.config import DEFAULT_PACKET_CONFIG, DEFAULT_SIGNAL_CONFIG, BPSK_CONST

logger = logging.getLogger(__name__)

class Transmitter(gr.top_block):
    def __init__(
        self,
        input_data: Any,
        pkt: PacketConfig,
        sig: SignalConfig,
        constellation:Any,
        sender_name: str = "defaut"
    ):
        """main transmitter class

        Args:
            input_data (Any): input data
            pkt (PacketConfig): packet description
            sig (SignalConfig): signal description
            constellation (Any): constellation definition
            sender_name (str): name of the sender
        """
        gr.top_block.__init__(self, "Transmitter", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        # Variables
        ## signal related variables
        self.sig = sig
        self.const_definition = constellation

        ## digital communication variables
        self.pkt = pkt
        self.input_file = prepare_data(input_data, pkt, sender_name=sender_name)
        self.access_key = "11100001010110101110100010010011"
        self.hdr_format = digital.header_format_default(self.access_key, 0)
        len_after_mux = pkt.total_packets_len + len(self.access_key) // 8 + 4
        self.cc_enc = fec.cc_encoder_make(len_after_mux * 8, 7, 2, [79, 109], 0, fec.CC_STREAMING, False)

        # Blocks
        ## file source
        self.blocks_vector_source_x_0 = blocks.vector_source_b(self.input_file, True)

        ## protocol layer
        self.blocks_stream_to_tagged_stream_0 = blocks.stream_to_tagged_stream(gr.sizeof_char, 1, self.pkt.total_packets_len, "packet_len")
        self.digital_protocol_formatter_bb_0 = digital.protocol_formatter_bb(self.hdr_format, "packet_len")
        self.blocks_tagged_stream_mux_0 = blocks.tagged_stream_mux(gr.sizeof_char*1, 'packet_len', 0)

        ## convolutionnal error correction encoding
        self.blocks_unpack_k_bits_bb_0 = blocks.unpack_k_bits_bb(8)
        self.fec_extended_encoder_0 = fec.extended_encoder(encoder_obj_list=self.cc_enc, threading= None, puncpat='11')

        ## modulation
        self.digital_diff_encoder_bb_0 = digital.diff_encoder_bb(2)
        self.digital_gfsk_mod_0 = digital.gfsk_mod(
            samples_per_symbol=self.sig.sps,
            sensitivity=1.0,
            bt=0.35,
            verbose=False,
            log=False,
            do_unpack=True)
        self.blocks_rotator_cc_0 = blocks.rotator_cc((2 * np.pi * (self.sig.carrier_freq / self.sig.samp_rate)), False)
        self.blocks_complex_to_real_0 = blocks.complex_to_real(1)
        self.blocks_multiply_const_vxx_0 = blocks.multiply_const_ff((1/4))

        ## head block to terminate cleanly the flow graph after everything is sent
        self.blocks_head_0 = blocks.head(gr.sizeof_float*1, self.sig.beeper_nb_sample + self.get_nb_of_audio_samples())

        ## beeper to help receiver to lock to carrier frequency
        self.analog_sig_source_x_0 = analog.sig_source_f(self.sig.samp_rate, analog.GR_SIN_WAVE, self.sig.carrier_freq, 0.77, 0, 0)

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
        self.connect((self.fec_extended_encoder_0, 0), (self.digital_diff_encoder_bb_0, 0))
        self.connect((self.digital_diff_encoder_bb_0, 0), (self.digital_gfsk_mod_0, 0))
        self.connect((self.digital_gfsk_mod_0, 0), (self.blocks_rotator_cc_0, 0))
        self.connect((self.blocks_rotator_cc_0, 0), (self.blocks_complex_to_real_0, 0))
        self.connect((self.blocks_complex_to_real_0, 0), (self.blocks_multiply_const_vxx_0, 0))
        self.connect((self.blocks_multiply_const_vxx_0, 0), (self.blocks_stream_mux_0, 1))
        self.connect((self.blocks_stream_mux_0, 0), (self.blocks_head_0, 0))
        self.connect((self.blocks_head_0, 0), (self.audio_sink_0, 0))
        self.connect((self.analog_sig_source_x_0, 0), (self.blocks_stream_mux_0, 0))

    def get_nb_of_audio_samples(self) -> int:
        """ calculate the correct number of audio sample to transmit
        
        Returns:
            int: number of audio sample to transmit
        """
        nb_packet = int(len(self.input_file) / self.pkt.total_packets_len)
        nb_bits_transmitted = (
            len(self.input_file) * 8 + nb_packet * len(self.access_key) + nb_packet * self.pkt.error_correction_len * 8
        ) * 2
        
        nb_symbols_transmitted = nb_bits_transmitted # GFSK is 1 bit per symbol
        
        audio_samples_to_transmit = int(nb_symbols_transmitted * self.sig.sps)
        return audio_samples_to_transmit


def send_data(
    input_data: Any,
    pkt: PacketConfig = DEFAULT_PACKET_CONFIG,
    sig: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    constellation: Any = None,
    sender_name: str = "defaut",
    handle_signals: bool = True,
    cancel_event=None,
):
    if constellation is None:
        if hasattr(sig, 'constellation') and sig.constellation is not None:
            constellation = sig.constellation
        else:
            constellation = BPSK_CONST

    tb = Transmitter(input_data, pkt, sig, constellation, sender_name=sender_name)

    if handle_signals:
        def sig_handler(sig=None, frame=None):
            tb.stop()
            tb.wait()

            sys.exit(0)

        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    tb.flowgraph_started.set()

    if cancel_event:
        done = threading.Event()

        def wait_for_flowgraph():
            tb.wait()
            done.set()

        wait_thread = threading.Thread(target=wait_for_flowgraph, daemon=True)
        wait_thread.start()

        while not done.is_set():
            if cancel_event.is_set():
                tb.stop()
                done.set()
                wait_thread.join(timeout=2.0)
                logger.info("Transmission cancelled mid-flight")
                return
            time.sleep(0.1)
    else:
        tb.wait()


if __name__ == "__main__":
    send_data("hello world ! this is a message transmitted using vibe-audio-modem :)")
