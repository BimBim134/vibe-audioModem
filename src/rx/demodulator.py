import sys
import signal
import threading
import logging
from datetime import datetime
import pmt

import numpy as np
from gnuradio import analog, audio, blocks, digital, fec, gr, pdu, zeromq
from gnuradio.filter import firdes, freq_xlating_fir_filter_fcc
from gnuradio.fft import window

from src.misc.config import PacketConfig, SignalConfig, PortsConfig
from src.misc.config import (
    DEFAULT_PACKET_CONFIG,
    DEFAULT_SIGNAL_CONFIG,
    DEFAULT_PORTS_CONFIG,
)


logger = logging.getLogger(__name__)


def generate_modulated_sync_word(pkt: PacketConfig, sig: SignalConfig, access_key: str):
    """Generates the GMSK-modulated complex symbols for the FEC-encoded header."""
    header_bytes = []
    # 1. Access Key
    for i in range(0, len(access_key), 8):
        header_bytes.append(int(access_key[i:i+8], 2))
    
    # 2. Length info (as added by digital.protocol_formatter_bb)
    packet_len = pkt.total_packets_len
    header_bytes.append(packet_len & 0xFF)
    header_bytes.append((packet_len >> 8) & 0xFF)
    header_bytes.append(packet_len & 0xFF)
    header_bytes.append((packet_len >> 8) & 0xFF)
    
    tb = gr.top_block()
    src = blocks.vector_source_b(header_bytes, False)
    unpack = blocks.unpack_k_bits_bb(8)
    
    header_len_bits = len(header_bytes) * 8
    cc_enc = fec.cc_encoder_make(header_len_bits, 7, 2, [79, 109], 0, fec.CC_TERMINATED, False)
    enc = fec.extended_encoder(encoder_obj_list=cc_enc, threading=None, puncpat='11')
    diff = digital.diff_encoder_bb(2)
    
    mod = digital.gmsk_mod(samples_per_symbol=sig.sps, bt=0.35, verbose=False, log=False, do_unpack=False)
    sink = blocks.vector_sink_c()
    
    tb.connect(src, unpack, enc, diff, mod, sink)
    tb.run()
    
    return sink.data()


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
        ports_conf: PortsConfig,
    ):
        """main Demodulator class

        Args:
            pkt (PacketConfig): packet configuration
            sig (SignalConfig): signal configuration
            ports_conf(PortsConfig): ports configuration
        """
        gr.top_block.__init__(self, "Demodulator master", catch_exceptions=False)
        logger.info("Demodulator Path B (Protocol Parser) instanciated")
        
        self.id = datetime.now().isoformat()
        self.flowgraph_started = threading.Event()

        # Variables
        self.sig = sig
        self.pkt = pkt
        self.access_key = "11100001010110101110100010010011"
        
        # Matches TX: 8 bytes Header + 48 bytes RS Block
        self.header_len = 8
        self.cc_frame_size = (pkt.total_packets_len + self.header_len) * 8
        self.cc_dec = fec.cc_decoder.make(
            self.cc_frame_size, 7, 2, [79, 109], 0, 0, fec.CC_TERMINATED, False
        )

        # Header format for parser
        self.hdr_format = digital.header_format_default(self.access_key, 0)

        self.ports = ports_conf

        # Blocks
        self.audio_source_0 = zeromq.sub_source(
            gr.sizeof_float, 1, f"tcp://127.0.0.1:{self.ports.audio_port}", 100, False, (-1), "", False
        )

        ### Frequency-translating filter
        self.freq_xlating_fir_filter_xxx_0 = freq_xlating_fir_filter_fcc(
            1,
            firdes.low_pass(1.0, self.sig.samp_rate, self.sig.baudrate * 1.5, self.sig.baudrate / 3, window.WIN_KAISER, 6.76),
            self.sig.carrier_freq,
            self.sig.samp_rate,
        )

        ### Automatic Gain Control
        self.analog_agc_xx_0 = analog.agc_cc(1e-4, 1.0, 1.0, 1000)

        ## Sync & Demod Chain
        self.sync_taps = generate_modulated_sync_word(self.pkt, self.sig, self.access_key)
        self.digital_corr_est_cc_0 = digital.corr_est_cc(
            self.sync_taps,
            self.sig.sps,
            mark_delay=int(len(self.sync_taps)/self.sig.sps - 4),
            threshold=0.7,
            threshold_method=digital.THRESHOLD_ABSOLUTE
        )

        self.digital_symbol_sync_xx_0 = digital.symbol_sync_cc(
            detector_type=digital.TED_GARDNER,
            sps=float(self.sig.sps),
            loop_bw=0.045,
            damping_factor=1.0,
            ted_gain=1.0,
            max_deviation=1.5,
            osps=1,
            slicer=None,
            interp_type=digital.IR_MMSE_8TAP,
            n_filters=128,
            taps=[]
        )

        self.analog_quadrature_demod_cf_0 = analog.quadrature_demod_cf(1.0 / (np.pi / 2.0))
        self.digital_binary_slicer_fb_0 = digital.binary_slicer_fb()
        self.digital_diff_decoder_bb_0 = digital.diff_decoder_bb(2, digital.DIFF_DIFFERENTIAL)

        ## Decoding Chain
        self.fec_extended_decoder_0 = fec.extended_decoder(
            decoder_obj_list=self.cc_dec,
            threading=None,
            ann=None,
            puncpat="11",
            integration_period=10000,
        )

        ## Protocol Parser (Idiomatic replacement for correlate_access_code + tag_fixer + repack)
        # Consumes bits, finds sync key, parses length, outputs tagged stream of bytes.
        self.digital_protocol_parser_b_0 = digital.protocol_parser_b(self.hdr_format)
        
        # PDU Conversion
        self.pdu_tagged_stream_to_pdu_0 = pdu.tagged_stream_to_pdu(gr.types.byte_t, "packet_len")

        ## Output
        self.pdu_set = pdu.pdu_set(k=pmt.intern("demodulator_id"), v=pmt.intern(self.id))
        self.pdu_set_freq = pdu.pdu_set(k=pmt.intern("carrier_freq"), v=pmt.from_double(float(self.sig.carrier_freq)))
        self.zeromq_pub_msg_sink_0 = zeromq.pub_msg_sink(f"tcp://127.0.0.1:{self.ports.raw_packets_port}", 100, False)

        # Connections
        self.connect((self.audio_source_0, 0), (self.freq_xlating_fir_filter_xxx_0, 0))
        self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.analog_agc_xx_0, 0))
        
        # Sync & Demod
        self.connect((self.analog_agc_xx_0, 0), (self.digital_corr_est_cc_0, 0))
        self.connect((self.digital_corr_est_cc_0, 0), (self.digital_symbol_sync_xx_0, 0))
        self.connect((self.digital_symbol_sync_xx_0, 0), (self.analog_quadrature_demod_cf_0, 0))
        self.connect((self.analog_quadrature_demod_cf_0, 0), (self.digital_binary_slicer_fb_0, 0))
        self.connect((self.digital_binary_slicer_fb_0, 0), (self.digital_diff_decoder_bb_0, 0))
        
        # Decoding & Parsing
        self.connect((self.digital_diff_decoder_bb_0, 0), (self.fec_extended_decoder_0, 0))
        self.connect((self.fec_extended_decoder_0, 0), (self.digital_protocol_parser_b_0, 0))
        self.connect((self.digital_protocol_parser_b_0, 0), (self.pdu_tagged_stream_to_pdu_0, 0))

        # PDU Path
        self.msg_connect((self.pdu_tagged_stream_to_pdu_0, "pdus"), (self.pdu_set, "pdus"))
        self.msg_connect((self.pdu_set, "pdus"), (self.pdu_set_freq, "pdus"))
        self.msg_connect((self.pdu_set_freq, "pdus"), (self.zeromq_pub_msg_sink_0, "in"))


def launch_demodulator(
    pkt: PacketConfig = DEFAULT_PACKET_CONFIG,
    sig: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    carrier_frequency: float | None = None,
    ports: PortsConfig = DEFAULT_PORTS_CONFIG,
    command_queue=None,
    status_queue=None,
):
    """receives an incomming transmission specified by **pkt**, **sig** at **carrier_frequency**.
    Outputs results on raw_packet_port defined in **ports**
    """
    import copy

    signal_config = copy.copy(sig)
    ports_config = copy.copy(ports)

    if carrier_frequency:
        signal_config.carrier_freq = carrier_frequency

    current_tb = [None]

    def sig_handler(sig=None, frame=None):
        if current_tb[0] is not None:
            current_tb[0].stop()
            current_tb[0].wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    if command_queue is None:
        tb = Demodulator(pkt, signal_config, ports_config)
        current_tb[0] = tb
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
                    signal_config.carrier_freq = freq

                # Create a fresh Demodulator to ensure clean algorithm state
                tb = Demodulator(pkt, signal_config, ports_config)
                current_tb[0] = tb

                tb.start()
                logger.info("Demodulator running for %.2f Hz", freq)
                if status_queue:
                    status_queue.put({"status": "running", "freq": freq})

                # Internal loop to wait for stop or kill while running
                while True:
                    cmd_queue = command_queue.get()
                    if cmd_queue is None:
                        tb.stop()
                        tb.wait()
                        return
                    cmd_queue_action = cmd_queue.get("action")

                    if cmd_queue_action == "stop":
                        tb.stop()
                        tb.wait()
                        current_tb[0] = None  # Allow garbage collection
                        del tb  # Force immediate destruction and ZMQ unbound
                        logger.info("Demodulator stopped, returning to idle.")
                        if status_queue:
                            status_queue.put({"status": "ready"})
                        break
                    elif cmd_queue_action == "update_preset":
                        new_baudrate = cmd_queue.get("baudrate")
                        new_beeper_duration = cmd_queue.get("beeper_duration")
                        if new_baudrate:
                            signal_config.baudrate = new_baudrate
                        if new_beeper_duration:
                            signal_config.beeper_duration = new_beeper_duration
                        logger.info(f"Preset update received: baudrate={signal_config.baudrate}")
                        # Restart demodulator with new settings
                        tb.stop()
                        tb.wait()
                        del tb
                        tb = Demodulator(pkt, signal_config, ports_config)
                        current_tb[0] = tb
                        tb.start()
                        logger.info("Demodulator restarted with new preset")
                        if status_queue:
                            status_queue.put({"status": "running", "preset_updated": True})
            elif action == "stop":
                if current_tb[0] is not None:
                    current_tb[0].stop()
                    current_tb[0].wait()
                    current_tb[0] = None
                if status_queue:
                    status_queue.put({"status": "ready"})


if __name__ == "__main__":
    pass
