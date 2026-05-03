import sys
import signal
import threading
from typing import Any
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
    CONSTELLATION_MAP
)


def get_constellation_by_name(name):
    """Resolve constellation name to actual constellation object."""
    if name is None:
        return "default"
    return CONSTELLATION_MAP.get(name, CONSTELLATION_MAP["default"])

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

        self.id = datetime.now().isoformat()

        self.flowgraph_started = threading.Event()

        # Variables
        ## signal related variables
        self.sig = sig
        self.const_definition = constellation
        self.freq_deviation = 100 / self.sig.samp_rate
        self.decimation = int(self.sig.sps / 8)

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
        ### Frequency-translating filter: real float input → complex baseband output.
        self.freq_xlating_fir_filter_xxx_0 = freq_xlating_fir_filter_fcc(
            self.decimation,
            firdes.low_pass(
                1,
                self.sig.samp_rate,
                self.sig.samp_rate / (2 * self.decimation),
                500,
                window.WIN_HAMMING,
            ),
            self.sig.carrier_freq,
            self.sig.samp_rate,
        )
        ### Automatic Gain Control

        self.analog_agc_xx_0 = analog.agc_cc((1e-1), 1.0, 1.0, 0)

        ## GFSK Demodulation
        self.digital_gfsk_demod_0 = digital.gfsk_demod(
            samples_per_symbol=int(self.sig.sps / self.decimation),
            sensitivity=1.0,
            gain_mu=0.175,
            mu=0.5,
            omega_relative_limit=0.005,
            freq_error=0.0,
            verbose=False,
            log=False,
        )

        ## differential decoding (modulus 2 for binary GFSK)
        self.digital_diff_decoder_bb_0 = digital.diff_decoder_bb(
            2, digital.DIFF_DIFFERENTIAL
        )

        ## convolutionnal error correction
        ### go from [0,1] to [-1, 1]
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
        self.pdu_set = pdu.pdu_set(
            k=pmt.intern("demodulator_id"), v=pmt.intern(self.id)
        )
        self.pdu_set_freq = pdu.pdu_set(
            k=pmt.intern("carrier_freq"), v=pmt.from_double(float(self.sig.carrier_freq))
        )
        self.zeromq_pub_msg_sink_0 = zeromq.pub_msg_sink(
            f"tcp://127.0.0.1:{self.ports.raw_packets_port}", 100, False
        )

        # Connections
        self.connect((self.audio_source_0, 0), (self.freq_xlating_fir_filter_xxx_0, 0))
        self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.analog_agc_xx_0, 0))
        self.connect((self.analog_agc_xx_0, 0), (self.digital_gfsk_demod_0, 0))
        self.connect((self.digital_gfsk_demod_0, 0), (self.digital_diff_decoder_bb_0, 0))
        self.connect((self.digital_diff_decoder_bb_0, 0), (self.blocks_uchar_to_float_0_0_0, 0))
        self.connect((self.blocks_uchar_to_float_0_0_0, 0),(self.blocks_multiply_const_xx_1_0_0, 0),)
        self.connect((self.blocks_multiply_const_xx_1_0_0, 0),(self.blocks_add_const_vxx_0_0_0, 0),)
        self.connect((self.blocks_add_const_vxx_0_0_0, 0), (self.fec_extended_decoder_0, 0))
        self.connect((self.fec_extended_decoder_0, 0),(self.digital_correlate_access_code_xx_ts_0, 0))
        self.connect((self.digital_correlate_access_code_xx_ts_0, 0),(self.blocks_repack_bits_bb_0_0, 0),)
        self.connect((self.blocks_repack_bits_bb_0_0, 0), (self.pdu_tagged_stream_to_pdu_0, 0))
        self.msg_connect((self.pdu_tagged_stream_to_pdu_0, "pdus"), (self.pdu_set, "pdus"))
        self.msg_connect((self.pdu_set, "pdus"), (self.pdu_set_freq, "pdus"))
        self.msg_connect((self.pdu_set_freq, "pdus"), (self.zeromq_pub_msg_sink_0, "in"))


def launch_demodulator(
    pkt: PacketConfig = DEFAULT_PACKET_CONFIG,
    sig: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    constellation: Any = None,
    constellation_name: str = None,
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

    current_constellation_name = constellation_name or sig.constellation_name
    current_constellation_obj = constellation or get_constellation_by_name(current_constellation_name)
    if isinstance(current_constellation_obj, str):
        current_constellation_obj = CONSTELLATION_MAP["default"]

    current_tb = [None]

    def sig_handler(sig=None, frame=None):
        if current_tb[0] is not None:
            current_tb[0].stop()
            current_tb[0].wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    if command_queue is None:
        tb = Demodulator(pkt, signal_config, current_constellation_obj, ports_config)
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
                tb = Demodulator(pkt, signal_config, current_constellation_obj, ports_config)
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
                        new_constellation_name = cmd_queue.get("constellation_name")
                        if new_baudrate:
                            signal_config.baudrate = new_baudrate
                        if new_beeper_duration:
                            signal_config.beeper_duration = new_beeper_duration
                        if new_constellation_name:
                            current_constellation_name = new_constellation_name
                            current_constellation_obj = get_constellation_by_name(current_constellation_name)
                            signal_config.constellation_name = current_constellation_name
                        logger.info(f"Preset update received: baudrate={signal_config.baudrate}, constellation={current_constellation_name}")
                        # Restart demodulator with new settings
                        tb.stop()
                        tb.wait()
                        del tb
                        tb = Demodulator(pkt, signal_config, current_constellation_obj, ports_config)
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
