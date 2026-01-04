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
        constellation
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
        self.cc_enc = fec.cc_encoder_make(
            pkt.total_packets_len, 7, 2, [79, 109], 0, fec.CC_STREAMING, False
        )

        # Blocks
        self.fec_extended_encoder_0 = fec.extended_encoder(encoder_obj_list=self.cc_enc, threading= None, puncpat='11')
        self.digital_protocol_formatter_bb_0 = digital.protocol_formatter_bb(self.hdr_format, "packet_len")
        self.digital_constellation_modulator_0 = digital.generic_mod(
            constellation=self.const_definition,
            differential=True,
            samples_per_symbol=self.sig.sps,
            pre_diff_code=True,
            excess_bw=0.35,
            verbose=False,
            log=False,
            truncate=False)
        self.blocks_vector_source_x_0 = blocks.vector_source_b(self.input_file, False, 1, [])
        self.blocks_unpack_k_bits_bb_0 = blocks.unpack_k_bits_bb(8)
        self.blocks_tagged_stream_mux_0 = blocks.tagged_stream_mux(gr.sizeof_char*1, 'packet_len', 0)
        self.blocks_stream_to_tagged_stream_0 = blocks.stream_to_tagged_stream(gr.sizeof_char, 1, self.pkt.total_packets_len, "packet_len")
        self.blocks_rotator_cc_0 = blocks.rotator_cc((2 * np.pi * (self.sig.carrier_freq / self.sig.samp_rate)), False)
        self.blocks_repack_bits_bb_1_0 = blocks.repack_bits_bb(1, 8, "", False, gr.GR_MSB_FIRST)
        self.blocks_multiply_const_vxx_0 = blocks.multiply_const_ff((1/4))
        self.blocks_head_0 = blocks.head(gr.sizeof_float*1, 1024)
        self.blocks_complex_to_real_0 = blocks.complex_to_real(1)
        self.audio_sink_0 = audio.sink(self.sig.samp_rate, '', True)

        # Connections
        self.connect((self.blocks_complex_to_real_0, 0), (self.blocks_multiply_const_vxx_0, 0))
        self.connect((self.blocks_head_0, 0), (self.audio_sink_0, 0))
        self.connect((self.blocks_multiply_const_vxx_0, 0), (self.blocks_head_0, 0))
        self.connect((self.blocks_repack_bits_bb_1_0, 0), (self.digital_constellation_modulator_0, 0))
        self.connect((self.blocks_rotator_cc_0, 0), (self.blocks_complex_to_real_0, 0))
        self.connect((self.blocks_stream_to_tagged_stream_0, 0), (self.blocks_tagged_stream_mux_0, 1))
        self.connect((self.blocks_stream_to_tagged_stream_0, 0), (self.digital_protocol_formatter_bb_0, 0))
        self.connect((self.blocks_tagged_stream_mux_0, 0), (self.blocks_unpack_k_bits_bb_0, 0))
        self.connect((self.blocks_unpack_k_bits_bb_0, 0), (self.fec_extended_encoder_0, 0))
        self.connect((self.blocks_vector_source_x_0, 0), (self.blocks_stream_to_tagged_stream_0, 0))
        self.connect((self.digital_constellation_modulator_0, 0), (self.blocks_rotator_cc_0, 0))
        self.connect((self.digital_protocol_formatter_bb_0, 0), (self.blocks_tagged_stream_mux_0, 0))
        self.connect((self.fec_extended_encoder_0, 0), (self.blocks_repack_bits_bb_1_0, 0))

    def get_nb_of_audio_samples(self) -> int:
        nb_packet = int(len(self.input_file) / self.pkt.total_packets_len)
        # nb_bits_transmitted = (total file length + access keys + packet_len tags) * rate FEC
        nb_bits_transmitted = (
            len(self.input_file) * 8 + nb_packet * len(self.access_key) + nb_packet * 32
        ) * 2
        audio_samples_to_transmit = nb_bits_transmitted * self.sig.sps
        audio_samples_to_transmit += int(0.1 * audio_samples_to_transmit) # some extra margin (+10% samples)
        time_to_transmit = audio_samples_to_transmit/self.sig.samp_rate
        print(f"{audio_samples_to_transmit} bits in {time_to_transmit} s.")
        return audio_samples_to_transmit


def transmit_data(
    input_file: Any,
    pkt_conf: PacketConfig = DEFAULT_PACKET_CONFIG,
    signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    constellation: digital.psk_constellation = DEFAULT_DQPSK_CONST,
) -> None:
    """data transmission module

    Args:
        input_file (Any): input file
        pkt_conf (PacketConfig, optional): packet description. Defaults to DEFAULT_PACKET_CONFIG.
        signal_conf (SignalConfig, optional): signal description. Defaults to DEFAULT_SIGNAL_CONFIG.
        constellation (digital.psk_constellation): constellation definition
    """
    tb = Transmitter(
        input_data=input_file,
        pkt=pkt_conf,
        sig=signal_conf,
        constellation=constellation,
    )

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    tb.flowgraph_started.set()

    tb.wait()


class beeper(gr.top_block):
    def __init__(self, sig: SignalConfig, duration: float = 1):
        """produce a single sinusoidal signal as given frequency for a given duration

        Args:
            sig (SignalConfig): signal configuration
            duration (float, optional): duration (s). Defaults to 1.
        """
        gr.top_block.__init__(self, "Not titled yet", catch_exceptions=True)
        self.flowgraph_started = threading.Event()

        # Variables
        self.sig = sig

        # Blocks
        self.analog_sig_source_x_0 = analog.sig_source_f(self.sig.samp_rate, analog.GR_SIN_WAVE, 1000, 1, 0, 0)
        self.blocks_head_0 = blocks.head(gr.sizeof_float * 1, self.sig.samp_rate * duration)
        self.audio_sink_0 = audio.sink(self.sig.samp_rate, "", True)

        # Connections
        self.connect((self.analog_sig_source_x_0, 0), (self.blocks_head_0, 0))
        self.connect((self.blocks_head_0, 0), (self.audio_sink_0, 0))


def beep(signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG, duration: float = 1):
    """beeper module

    Args:
        sig (SignalConfig): signal configuration
        duration (float, optional): duration (s). Defaults to 1.
    """
    tb = beeper(signal_conf, duration)

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()
    tb.flowgraph_started.set()

    tb.wait()


def send_data(
    input_file: Any,
    pkt_conf: PacketConfig = DEFAULT_PACKET_CONFIG,
    signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    constellation: digital.psk_constellation = DEFAULT_DQPSK_CONST,
    beep_duration=1,
) -> None:
    """send file using audio modem !
    * first produce a beep to helps receiver side to lock in to carrier frequency
    * transmit file using psk modulation

    Args:
        input_file (Any): input file
        pkt_conf (PacketConfig, optional): packet description. Defaults to DEFAULT_PACKET_CONFIG.
        signal_conf (SignalConfig, optional): signal description. Defaults to DEFAULT_SIGNAL_CONFIG.
        sig (SignalConfig): signal configuration
        constellation (digital.psk_constellation): constellation definition
        duration (float, optional): duration (s). Defaults to 1.
    """
    beep(signal_conf, beep_duration)
    transmit_data(input_file, pkt_conf, signal_conf, constellation)


if __name__ == "__main__":
    send_data(b"hello world ! this is a message transmitted using vibe-audio-modem :)")
