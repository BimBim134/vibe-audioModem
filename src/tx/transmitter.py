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
from src.misc.config import DEFAULT_PACKET_CONFIG, DEFAULT_SIGNAL_CONFIG

logger = logging.getLogger(__name__)

class Transmitter(gr.top_block):
    def __init__(
        self,
        input_data: Any,
        pkt: PacketConfig,
        sig: SignalConfig,
        sender_name: str = "defaut",
        output_file: str = None,
        silence_padding: float = 0.0,
    ):
        """Baseline Transmitter: Reliable & Simple"""
        gr.top_block.__init__(self, "Transmitter", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        self.sig = sig
        self.silence_padding = silence_padding
        self.pkt = pkt
        self.input_file = prepare_data(input_data, pkt, sender_name=sender_name)
        self.access_key = "11100001010110101110100010010011"
        
        # Long preamble for loop locking + Access Key
        self.preamble_bits = [0, 1] * 32 
        self.access_key_bits = [int(b) for b in self.access_key]
        self.sync_bits = self.preamble_bits + self.access_key_bits
        self.sync_len = len(self.sync_bits)

        # FEC only on the payload
        self.cc_frame_size = pkt.total_packets_len * 8
        self.cc_enc = fec.cc_encoder_make(self.cc_frame_size, 7, 2, [79, 109], 0, fec.CC_STREAMING, False)

        # Blocks
        nb_packets = len(self.input_file) // pkt.total_packets_len
        self.sync_source = blocks.vector_source_b(self.sync_bits * nb_packets, False)
        self.sync_to_tagged = blocks.stream_to_tagged_stream(gr.sizeof_char, 1, self.sync_len, "packet_len")

        self.blocks_vector_source_x_0 = blocks.vector_source_b(self.input_file, False)
        self.blocks_unpack_k_bits_bb_0 = blocks.unpack_k_bits_bb(8)
        self.fec_extended_encoder_0 = fec.extended_encoder(encoder_obj_list=self.cc_enc, threading= None, puncpat='11')
        
        self.digital_diff_encoder_bb_0 = digital.diff_encoder_bb(2)
        self.payload_bits_len = pkt.total_packets_len * 8 * 2 # Rate 1/2
        self.payload_to_tagged = blocks.stream_to_tagged_stream(gr.sizeof_char, 1, self.payload_bits_len, "packet_len")

        self.blocks_tagged_stream_mux_0 = blocks.tagged_stream_mux(gr.sizeof_char*1, 'packet_len', 0)

        self.digital_gmsk_mod_0 = digital.gmsk_mod(
            samples_per_symbol=self.sig.sps, bt=0.35, verbose=False, log=False, do_unpack=False)
        
        self.blocks_rotator_cc_0 = blocks.rotator_cc((2 * np.pi * (self.sig.carrier_freq / self.sig.samp_rate)), False)
        self.blocks_complex_to_real_0 = blocks.complex_to_real(1)
        self.blocks_multiply_const_vxx_0 = blocks.multiply_const_ff(1.0)

        silence_samples = int(self.silence_padding * self.sig.samp_rate)
        self.blocks_head_0 = blocks.head(gr.sizeof_float*1, self.sig.beeper_nb_sample + self.get_nb_of_audio_samples() + silence_samples)
        self.analog_sig_source_x_0 = analog.sig_source_f(self.sig.samp_rate, analog.GR_SIN_WAVE, self.sig.carrier_freq, 0.77, 0, 0)

        self.blocks_stream_mux_0 = blocks.stream_mux(gr.sizeof_float*1, (self.sig.beeper_nb_sample, self.get_nb_of_audio_samples()))

        if output_file:
            self.audio_sink_0 = blocks.wavfile_sink(output_file, 1, self.sig.samp_rate, blocks.FORMAT_WAV, blocks.FORMAT_PCM_16, False)
        else:
            self.audio_sink_0 = audio.sink(self.sig.samp_rate, '', True)

        # Connections
        self.connect((self.sync_source, 0), (self.sync_to_tagged, 0))
        self.connect((self.sync_to_tagged, 0), (self.blocks_tagged_stream_mux_0, 0))

        self.connect((self.blocks_vector_source_x_0, 0), (self.blocks_unpack_k_bits_bb_0, 0))
        self.connect((self.blocks_unpack_k_bits_bb_0, 0), (self.fec_extended_encoder_0, 0))
        self.connect((self.fec_extended_encoder_0, 0), (self.digital_diff_encoder_bb_0, 0))
        self.connect((self.digital_diff_encoder_bb_0, 0), (self.payload_to_tagged, 0))
        self.connect((self.payload_to_tagged, 0), (self.blocks_tagged_stream_mux_0, 1))

        self.connect((self.blocks_tagged_stream_mux_0, 0), (self.digital_gmsk_mod_0, 0))
        self.connect((self.digital_gmsk_mod_0, 0), (self.blocks_rotator_cc_0, 0))
        self.connect((self.blocks_rotator_cc_0, 0), (self.blocks_complex_to_real_0, 0))
        self.connect((self.blocks_complex_to_real_0, 0), (self.blocks_multiply_const_vxx_0, 0))
        self.connect((self.blocks_multiply_const_vxx_0, 0), (self.blocks_stream_mux_0, 1))
        self.connect((self.blocks_stream_mux_0, 0), (self.blocks_head_0, 0))
        self.connect((self.blocks_head_0, 0), (self.audio_sink_0, 0))
        self.connect((self.analog_sig_source_x_0, 0), (self.blocks_stream_mux_0, 0))

    def get_nb_of_audio_samples(self) -> int:
        nb_packet = int(len(self.input_file) / self.pkt.total_packets_len)
        bits_per_packet = self.sync_len + (self.pkt.total_packets_len * 8 * 2)
        return int(nb_packet * bits_per_packet * self.sig.sps)


def send_data(
    input_data: Any,
    pkt: PacketConfig = DEFAULT_PACKET_CONFIG,
    sig: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    sender_name: str = "defaut",
    handle_signals: bool = True,
    cancel_event=None,
    output_file: str = None,
    silence_padding: float = 0.0,
):
    tb = Transmitter(input_data, pkt, sig, sender_name=sender_name, output_file=output_file, silence_padding=silence_padding)

    if handle_signals:
        def sig_handler(sig=None, frame=None):
            tb.stop(); tb.wait(); sys.exit(0)
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    tb.flowgraph_started.set()

    if cancel_event:
        done = threading.Event()
        def wait_for_flowgraph():
            tb.wait(); done.set()
        threading.Thread(target=wait_for_flowgraph, daemon=True).start()
        while not done.is_set():
            if cancel_event.is_set():
                tb.stop(); done.set(); return
            time.sleep(0.1)
    else:
        tb.wait()


if __name__ == "__main__":
    send_data("hello world ! this is a message transmitted using vibe-audio-modem :)")
