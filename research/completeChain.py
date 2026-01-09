from typing import Any
from pathlib import Path

from PyQt5 import Qt
from gnuradio import qtgui
from gnuradio import analog
from gnuradio import blocks
import pmt
from gnuradio import channels
from gnuradio import digital
from gnuradio import filter
from gnuradio import fec
from gnuradio.filter import firdes
from gnuradio import gr
from gnuradio.fft import window
import sys
import signal
from PyQt5 import Qt
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
from gnuradio import gr, pdu
from gnuradio import zeromq
import numpy as np
import sip
import threading

from src.config import PacketConfig, SignalConfig
from src.config import DEFAULT_PACKET_CONFIG, DEFAULT_SIGNAL_CONFIG, DEFAULT_DQPSK_CONST
from src.bin2packet import prepare_data


class completeChain(gr.top_block, Qt.QWidget):

    def __init__(self, pkt:PacketConfig, sig: SignalConfig, constellation:Any, data):
        gr.top_block.__init__(self, "completeChain", catch_exceptions=True)

        # GUI stuff
        Qt.QWidget.__init__(self)
        self.setWindowTitle("completeChain")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except BaseException as exc:
            print(f"Qt GUI: Could not set Icon: {str(exc)}", file=sys.stderr)
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("gnuradio/flowgraphs", "completeChain")

        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except BaseException as exc:
            print(f"Qt GUI: Could not restore geometry: {str(exc)}", file=sys.stderr)
        self.flowgraph_started = threading.Event()

        # Variables
        self.sig = sig
        self.pkt = pkt
        self.const_definition = constellation
        self.access_key = '11100001010110101110100010010011'
        self.variable_adaptive_algorithm_0 = digital.adaptive_algorithm_lms( self.const_definition, .001).base()
        self.hdr_format = digital.header_format_default(self.access_key, 0)
        self.freq_deviation = 100/self.sig.samp_rate
        self.decimation = int(self.sig.sps/8)
        self.cc_enc = fec.cc_encoder_make(128,7, 2, [79,109], 0, fec.CC_STREAMING, True)
        self.cc_dec = fec.cc_decoder.make(8,7, 2, [79,109], 0, 0, fec.CC_STREAMING, True)
        self.input_file = prepare_data(data, self.pkt)

        # Blocks
        ## transmitter side
        ### file source
        self.blocks_file_source_0 = blocks.vector_source_b(self.input_file)

        ### protocol formatting
        self.blocks_stream_to_tagged_stream_0 = blocks.stream_to_tagged_stream(gr.sizeof_char, 1, self.pkt.total_packets_len, "packet_len")
        self.digital_protocol_formatter_bb_0 = digital.protocol_formatter_bb(self.hdr_format, "packet_len")
        self.blocks_tagged_stream_mux_0 = blocks.tagged_stream_mux(gr.sizeof_char*1, 'packet_len', 0)

        ### FEC encoding
        self.blocks_unpack_k_bits_bb_0 = blocks.unpack_k_bits_bb(8)
        self.fec_extended_encoder_0 = fec.extended_encoder(encoder_obj_list=self.cc_enc, threading= None, puncpat='11')
        self.blocks_repack_bits_bb_1_0 = blocks.repack_bits_bb(1, 8, "", False, gr.GR_MSB_FIRST)

        ### modulation
        self.digital_constellation_modulator_0 = digital.generic_mod(
            constellation=self.const_definition,
            differential=True,
            samples_per_symbol=self.sig.sps,
            pre_diff_code=True,
            excess_bw=0.35,
            verbose=False,
            log=False,
            truncate=False)
        self.blocks_rotator_cc_0 = blocks.rotator_cc((2 * np.pi * (self.sig.carrier_freq / self.sig.samp_rate)), False)
        self.blocks_complex_to_real_0 = blocks.complex_to_real(1)
        self.blocks_multiply_const_vxx_0 = blocks.multiply_const_ff((1/4))

        # WELCOME TO THE REAL WORLD WHERE NOISE HAPPEN
        self.analog_nbfm_tx_0 = analog.nbfm_tx(
            audio_rate=self.sig.samp_rate,
            quad_rate=(self.sig.samp_rate * 4),
            tau=(75e-6),
            max_dev=5e3,
            fh=(-1.0),
        )
        self.channels_channel_model_0 = channels.channel_model(
            noise_voltage=(1e-2),
            frequency_offset=0.25,
            epsilon=1.01,
            taps=[1.0],
            noise_seed=0,
            block_tags=True,
        )
        self.analog_nbfm_rx_0 = analog.nbfm_rx(
            audio_rate=self.sig.samp_rate,
            quad_rate=(self.sig.samp_rate * 4),
            tau=(75e-6),
            max_dev=5e3,
        )
        self.blocks_throttle2_1 = blocks.throttle(
            gr.sizeof_float * 1,
            self.sig.samp_rate,
            True,
            (
                0
                if "auto" == "auto"
                else max(
                    int(float(0.1) * self.sig.samp_rate) if "auto" == "time" else int(0.1), 1
                )
            ),
        )

        ## receiver side
        ### audio in
        self.hilbert_fc_0 = filter.hilbert_fc(65, window.WIN_HAMMING, 6.76)

        ## frequency shifting and antialiasing filtering
        self.freq_xlating_fir_filter_xxx_0 = filter.freq_xlating_fir_filter_ccc(
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

        ## Automatic Gain Control
        self.analog_agc_xx_0 = analog.agc_cc((1e-4), np.sqrt(2), 1.0, 10)

        ## frequency coarse correction
        self.digital_fll_band_edge_cc_0 = digital.fll_band_edge_cc((self.sig.sps/self.decimation), 0.35, 44, (1e-3))

        ## demodulation
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
        self.digital_linear_equalizer_0 = digital.linear_equalizer(15, 3, self.variable_adaptive_algorithm_0, True, [ ], 'corr_est')
        self.digital_constellation_receiver_cb_0 = digital.constellation_receiver_cb(self.const_definition, 1, (-self.freq_deviation), self.freq_deviation)

        ## differential decoding
        self.digital_diff_decoder_bb_0 = digital.diff_decoder_bb((2**self.const_definition.bits_per_symbol()), digital.DIFF_DIFFERENTIAL)

        ## FEC error decoding
        ### signal shaping
        self.digital_map_bb_0 = digital.map_bb(self.const_definition.pre_diff_code())
        self.blocks_unpack_k_bits_bb_0_0 = blocks.unpack_k_bits_bb(self.const_definition.bits_per_symbol())
        self.blocks_uchar_to_float_0_0_0 = blocks.uchar_to_float()
        self.blocks_multiply_const_xx_1_0_0 = blocks.multiply_const_ff(2, 1)
        self.blocks_add_const_vxx_0_0_0 = blocks.add_const_ff((-1))
        ### correction
        self.fec_extended_decoder_0 = fec.extended_decoder(decoder_obj_list=self.cc_dec, threading= None, ann=None, puncpat='11', integration_period=10000)

        ## frame synchronization
        self.digital_correlate_access_code_xx_ts_0 = digital.correlate_access_code_bb_ts(self.access_key, 3, 'packet_len')
        self.blocks_repack_bits_bb_0_0 = blocks.repack_bits_bb(1, 8, "packet_len", True, gr.GR_MSB_FIRST)

        ## export to zmq server
        self.pdu_tagged_stream_to_pdu_0 = pdu.tagged_stream_to_pdu(gr.types.byte_t, 'packet_len')
        self.zeromq_pub_msg_sink_0 = zeromq.pub_msg_sink("tcp://*:5555", 100, True)

        self.blocks_null_sink_0_1 = blocks.null_sink(gr.sizeof_float*1)
        self.blocks_null_sink_0_0 = blocks.null_sink(gr.sizeof_float*1)
        self.blocks_null_sink_0 = blocks.null_sink(gr.sizeof_float*1)

        # GUI STUFF
        self.qtgui_freq_sink_x_0 = qtgui.freq_sink_c(
            1024, #size
            window.WIN_BLACKMAN_hARRIS, #wintype
            0, #fc
            self.sig.samp_rate, #bw
            "", #name
            2,
            None # parent
        )
        self.qtgui_freq_sink_x_0.set_update_time(0.10)
        self.qtgui_freq_sink_x_0.set_y_axis((-140), 10)
        self.qtgui_freq_sink_x_0.set_y_label('Relative Gain', 'dB')
        self.qtgui_freq_sink_x_0.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.qtgui_freq_sink_x_0.enable_autoscale(False)
        self.qtgui_freq_sink_x_0.enable_grid(False)
        self.qtgui_freq_sink_x_0.set_fft_average(1.0)
        self.qtgui_freq_sink_x_0.enable_axis_labels(True)
        self.qtgui_freq_sink_x_0.enable_control_panel(False)
        self.qtgui_freq_sink_x_0.set_fft_window_normalized(False)

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ["blue", "red", "green", "black", "cyan",
            "magenta", "yellow", "dark red", "dark green", "dark blue"]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(2):
            if len(labels[i]) == 0:
                self.qtgui_freq_sink_x_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_freq_sink_x_0.set_line_label(i, labels[i])
            self.qtgui_freq_sink_x_0.set_line_width(i, widths[i])
            self.qtgui_freq_sink_x_0.set_line_color(i, colors[i])
            self.qtgui_freq_sink_x_0.set_line_alpha(i, alphas[i])

        self._qtgui_freq_sink_x_0_win = sip.wrapinstance(self.qtgui_freq_sink_x_0.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_freq_sink_x_0_win)
        self.qtgui_const_sink_x_0_2_1_0 = qtgui.const_sink_c(
            128, #size
            "", #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_const_sink_x_0_2_1_0.set_update_time(0.10)
        self.qtgui_const_sink_x_0_2_1_0.set_y_axis((-2), 2)
        self.qtgui_const_sink_x_0_2_1_0.set_x_axis((-2), 2)
        self.qtgui_const_sink_x_0_2_1_0.set_trigger_mode(qtgui.TRIG_MODE_FREE, qtgui.TRIG_SLOPE_POS, 0.0, 0, "")
        self.qtgui_const_sink_x_0_2_1_0.enable_autoscale(False)
        self.qtgui_const_sink_x_0_2_1_0.enable_grid(False)
        self.qtgui_const_sink_x_0_2_1_0.enable_axis_labels(True)

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ["blue", "red", "green", "black", "cyan",
            "magenta", "yellow", "dark red", "dark green", "dark blue"]
        styles = [0, 0, 0, 0, 0,
            0, 0, 0, 0, 0]
        markers = [0, 0, 0, 0, 0,
            0, 0, 0, 0, 0]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_const_sink_x_0_2_1_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_const_sink_x_0_2_1_0.set_line_label(i, labels[i])
            self.qtgui_const_sink_x_0_2_1_0.set_line_width(i, widths[i])
            self.qtgui_const_sink_x_0_2_1_0.set_line_color(i, colors[i])
            self.qtgui_const_sink_x_0_2_1_0.set_line_style(i, styles[i])
            self.qtgui_const_sink_x_0_2_1_0.set_line_marker(i, markers[i])
            self.qtgui_const_sink_x_0_2_1_0.set_line_alpha(i, alphas[i])

        self._qtgui_const_sink_x_0_2_1_0_win = sip.wrapinstance(self.qtgui_const_sink_x_0_2_1_0.qwidget(), Qt.QWidget)
        self.top_layout.addWidget(self._qtgui_const_sink_x_0_2_1_0_win)

        # Connections
        self.msg_connect((self.pdu_tagged_stream_to_pdu_0, 'pdus'), (self.zeromq_pub_msg_sink_0, 'in'))
        self.connect((self.analog_agc_xx_0, 0), (self.digital_fll_band_edge_cc_0, 0))
        self.connect((self.analog_agc_xx_0, 0), (self.qtgui_freq_sink_x_0, 0))
        self.connect((self.analog_nbfm_rx_0, 0), (self.blocks_throttle2_1, 0))
        self.connect((self.analog_nbfm_tx_0, 0), (self.channels_channel_model_0, 0))
        self.connect((self.blocks_add_const_vxx_0_0_0, 0), (self.fec_extended_decoder_0, 0))
        self.connect((self.blocks_complex_to_real_0, 0), (self.blocks_multiply_const_vxx_0, 0))
        self.connect((self.blocks_file_source_0, 0), (self.blocks_stream_to_tagged_stream_0, 0))
        self.connect((self.blocks_multiply_const_vxx_0, 0), (self.analog_nbfm_tx_0, 0))
        self.connect((self.blocks_multiply_const_xx_1_0_0, 0), (self.blocks_add_const_vxx_0_0_0, 0))
        self.connect((self.blocks_repack_bits_bb_0_0, 0), (self.pdu_tagged_stream_to_pdu_0, 0))
        self.connect((self.blocks_repack_bits_bb_1_0, 0), (self.digital_constellation_modulator_0, 0))
        self.connect((self.blocks_rotator_cc_0, 0), (self.blocks_complex_to_real_0, 0))
        self.connect((self.blocks_stream_to_tagged_stream_0, 0), (self.blocks_tagged_stream_mux_0, 1))
        self.connect((self.blocks_stream_to_tagged_stream_0, 0), (self.digital_protocol_formatter_bb_0, 0))
        self.connect((self.blocks_tagged_stream_mux_0, 0), (self.blocks_unpack_k_bits_bb_0, 0))
        self.connect((self.blocks_throttle2_1, 0), (self.hilbert_fc_0, 0))
        self.connect((self.blocks_uchar_to_float_0_0_0, 0), (self.blocks_multiply_const_xx_1_0_0, 0))
        self.connect((self.blocks_unpack_k_bits_bb_0, 0), (self.fec_extended_encoder_0, 0))
        self.connect((self.blocks_unpack_k_bits_bb_0_0, 0), (self.blocks_uchar_to_float_0_0_0, 0))
        self.connect((self.channels_channel_model_0, 0), (self.analog_nbfm_rx_0, 0))
        self.connect((self.digital_constellation_modulator_0, 0), (self.blocks_rotator_cc_0, 0))
        self.connect((self.digital_constellation_receiver_cb_0, 1), (self.blocks_null_sink_0, 0))
        self.connect((self.digital_constellation_receiver_cb_0, 2), (self.blocks_null_sink_0_0, 0))
        self.connect((self.digital_constellation_receiver_cb_0, 3), (self.blocks_null_sink_0_1, 0))
        self.connect((self.digital_constellation_receiver_cb_0, 0), (self.digital_diff_decoder_bb_0, 0))
        self.connect((self.digital_constellation_receiver_cb_0, 4), (self.qtgui_const_sink_x_0_2_1_0, 0))
        self.connect((self.digital_correlate_access_code_xx_ts_0, 0), (self.blocks_repack_bits_bb_0_0, 0))
        self.connect((self.digital_diff_decoder_bb_0, 0), (self.digital_map_bb_0, 0))
        self.connect((self.digital_fll_band_edge_cc_0, 0), (self.digital_symbol_sync_xx_0, 0))
        self.connect((self.digital_fll_band_edge_cc_0, 0), (self.qtgui_freq_sink_x_0, 1))
        self.connect((self.digital_linear_equalizer_0, 0), (self.digital_constellation_receiver_cb_0, 0))
        self.connect((self.digital_map_bb_0, 0), (self.blocks_unpack_k_bits_bb_0_0, 0))
        self.connect((self.digital_protocol_formatter_bb_0, 0), (self.blocks_tagged_stream_mux_0, 0))
        self.connect((self.digital_symbol_sync_xx_0, 0), (self.digital_linear_equalizer_0, 0))
        self.connect((self.fec_extended_decoder_0, 0), (self.digital_correlate_access_code_xx_ts_0, 0))
        self.connect((self.fec_extended_encoder_0, 0), (self.blocks_repack_bits_bb_1_0, 0))
        self.connect((self.freq_xlating_fir_filter_xxx_0, 0), (self.analog_agc_xx_0, 0))
        self.connect((self.hilbert_fc_0, 0), (self.freq_xlating_fir_filter_xxx_0, 0))

    def closeEvent(self, event):
        self.settings = Qt.QSettings("gnuradio/flowgraphs", "completeChain")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()


def complete_chain(data):
    qapp = Qt.QApplication(sys.argv)

    tb = completeChain(DEFAULT_PACKET_CONFIG, DEFAULT_SIGNAL_CONFIG, DEFAULT_DQPSK_CONST, data)

    tb.start()
    tb.flowgraph_started.set()

    tb.show()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    qapp.exec_()

if __name__ == '__main__':
    data = Path("C:/Users/microbimbim/Codes/vibe-audioModem/research/conjecture.txt")
    complete_chain(data)
