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


class TagValueSetter(gr.sync_block):
    """Sets the value of a specific tag."""
    def __init__(self, tag_name, value):
        gr.sync_block.__init__(self, name="TagValueSetter", in_sig=[np.uint8], out_sig=[np.uint8])
        self.tag_name = pmt.intern(tag_name)
        self.value = pmt.from_long(value)

    def work(self, input_items, output_items):
        n = len(input_items[0])
        tags = self.get_tags_in_window(0, 0, n)
        for tag in tags:
            if pmt.eq(tag.key, self.tag_name):
                self.add_item_tag(0, tag.offset, self.tag_name, self.value)
        output_items[0][:] = input_items[0][:]
        return n


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
        """Baseline Demodulator: Reliable & Correct"""
        gr.top_block.__init__(self, "Demodulator master", catch_exceptions=False)
        logger.info("Demodulator class instanciated")

        self.id = datetime.now().isoformat()
        self.flowgraph_started = threading.Event()

        # Variables
        self.sig = sig
        self.target_sps = 10
        self.decimation = int(max(1, self.sig.sps // self.target_sps))
        self.actual_sps = float(self.sig.samp_rate) / (self.decimation * self.sig.baudrate)
        logger.info(f"Decimation: {self.decimation}, Actual SPS: {self.actual_sps:.2f}")

        self.pkt = pkt
        self.access_key = "11100001010110101110100010010011"
        
        # Correct math: Tag length MUST be the number of ENCODED bits
        self.encoded_payload_bits = pkt.total_packets_len * 8 * 2 
        
        self.cc_dec = fec.cc_decoder.make(
            pkt.total_packets_len * 8, 7, 2, [79, 109], 0, 0, fec.CC_STREAMING, False
        )

        self.ports = ports_conf

        # Blocks
        self.audio_source_0 = zeromq.sub_source(
            gr.sizeof_float, 1, f"tcp://127.0.0.1:{self.ports.audio_port}", 100, False, (-1), "", False,
        )
        self.freq_xlating_fir_filter_xxx_0 = freq_xlating_fir_filter_fcc(
            self.decimation,
            firdes.low_pass(1.0, self.sig.samp_rate, self.sig.baudrate * 1.5, self.sig.baudrate / 3, window.WIN_KAISER, 6.76),
            self.sig.carrier_freq, self.sig.samp_rate,
        )
        self.analog_agc_xx_0 = analog.agc_cc(1e-4, 1.0, 1.0, 1000)

        self.digital_gmsk_demod_0 = digital.gmsk_demod(
            samples_per_symbol=self.actual_sps, gain_mu=0.175, mu=0.5, omega_relative_limit=0.005, freq_error=0.0, verbose=False, log=False,
        )

        # Bit correlator: Increased threshold for reliability
        self.digital_correlate_access_code_xx_ts_0 = digital.correlate_access_code_bb_ts(self.access_key, 8, "packet_len")
        
        # Tag Fixer: MUST set length to ENCODED bit count
        self.tag_fixer = TagValueSetter("packet_len", self.encoded_payload_bits)
        
        self.digital_diff_decoder_bb_0 = digital.diff_decoder_bb(2, digital.DIFF_DIFFERENTIAL)

        self.blocks_uchar_to_float_0_0_0 = blocks.uchar_to_float()
        self.blocks_multiply_const_xx_1_0_0 = blocks.multiply_const_ff(2, 1)
        self.blocks_add_const_vxx_0_0_0 = blocks.add_const_ff((-1))
        self.fec_extended_decoder_0 = fec.extended_decoder(decoder_obj_list=self.cc_dec, threading=None, ann=None, puncpat="11", integration_period=10000)

        self.tag_final_fixer = TagValueSetter("packet_len", pkt.total_packets_len * 8)
        self.blocks_repack_bits_bb_0_0 = blocks.repack_bits_bb(1, 8, "packet_len", True, gr.GR_MSB_FIRST)
        self.pdu_tagged_stream_to_pdu_0 = pdu.tagged_stream_to_pdu(gr.types.byte_t, "packet_len")

        self.pdu_set = pdu.pdu_set(k=pmt.intern("demodulator_id"), v=pmt.intern(self.id))
        self.pdu_set_freq = pdu.pdu_set(k=pmt.intern("carrier_freq"), v=pmt.from_double(float(self.sig.carrier_freq)))
        self.zeromq_pub_msg_sink_0 = zeromq.pub_msg_sink(f"tcp://127.0.0.1:{self.ports.raw_packets_port}", 100, False)

        # Connections
        self.connect((self.audio_source_0, 0), (self.freq_xlating_fir_filter_xxx_0, 0))
        self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.analog_agc_xx_0, 0))
        self.connect((self.analog_agc_xx_0, 0), (self.digital_gmsk_demod_0, 0))
        self.connect((self.digital_gmsk_demod_0, 0), (self.digital_correlate_access_code_xx_ts_0, 0))
        self.connect((self.digital_correlate_access_code_xx_ts_0, 0), (self.tag_fixer, 0))
        self.connect((self.tag_fixer, 0), (self.digital_diff_decoder_bb_0, 0))
        self.connect((self.digital_diff_decoder_bb_0, 0), (self.blocks_uchar_to_float_0_0_0, 0))
        self.connect((self.blocks_uchar_to_float_0_0_0, 0),(self.blocks_multiply_const_xx_1_0_0, 0))
        self.connect((self.blocks_multiply_const_xx_1_0_0, 0),(self.blocks_add_const_vxx_0_0_0, 0))
        self.connect((self.blocks_add_const_vxx_0_0_0, 0), (self.fec_extended_decoder_0, 0))
        self.connect((self.fec_extended_decoder_0, 0), (self.tag_final_fixer, 0))
        self.connect((self.tag_final_fixer, 0), (self.blocks_repack_bits_bb_0_0, 0))
        self.connect((self.blocks_repack_bits_bb_0_0, 0), (self.pdu_tagged_stream_to_pdu_0, 0))

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
        tb.wait()
    else:
        if status_queue:
            status_queue.put({"status": "ready"})
        while True:
            cmd = command_queue.get()
            if cmd is None: break
            action = cmd.get("action", "start")
            if action == "start":
                freq = cmd.get("freq")
                if freq: signal_config.carrier_freq = freq
                tb = Demodulator(pkt, signal_config, ports_config)
                current_tb[0] = tb
                tb.start()
                if status_queue: status_queue.put({"status": "running", "freq": freq})
                while True:
                    cmd_queue = command_queue.get()
                    if cmd_queue is None:
                        tb.stop(); tb.wait()
                        return
                    cmd_queue_action = cmd_queue.get("action")
                    if cmd_queue_action == "stop":
                        tb.stop(); tb.wait()
                        current_tb[0] = None; del tb
                        if status_queue: status_queue.put({"status": "ready"})
                        break
                    elif cmd_queue_action == "update_preset":
                        new_baudrate = cmd_queue.get("baudrate")
                        if new_baudrate: signal_config.baudrate = new_baudrate
                        tb.stop(); tb.wait(); del tb
                        tb = Demodulator(pkt, signal_config, ports_config)
                        current_tb[0] = tb
                        tb.start()
                        if status_queue: status_queue.put({"status": "running", "preset_updated": True})
            elif action == "stop":
                if current_tb[0] is not None:
                    current_tb[0].stop(); current_tb[0].wait(); current_tb[0] = None
                if status_queue: status_queue.put({"status": "ready"})

if __name__ == "__main__":
    pass
