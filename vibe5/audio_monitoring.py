#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: audio_monitoring
# Author: bimbim
# GNU Radio version: 3.10.12.0

from PyQt5 import Qt
from gnuradio import qtgui
from gnuradio import audio
from gnuradio import gr
from gnuradio.filter import firdes
from gnuradio.fft import window
import sys
import signal
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
import threading
import sip
import pyqtgraph as pg
import numpy as np
from gnuradio import fft
from gnuradio import blocks


class WaterfallWidget(pg.GraphicsLayoutWidget):
    """
    Custom PyQtGraph-based waterfall display widget.
    """
    def __init__(self, n_rows=200, n_cols=512, parent=None):
        super().__init__(parent)
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.data = np.zeros((n_rows, n_cols))
        self.setBackground('transparent')
        self.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding)
        # Add a ViewBox and ImageItem
        self.view = self.addViewBox(row=0, col=0)
        self.view.setAspectLocked(False)
        self.view.setBackgroundColor('transparent')
        self.img = pg.ImageItem()
        self.view.addItem(self.img)
        # Set a matplotlib colormap (e.g., 'plasma')
        cmap = pg.colormap.get('plasma', source='matplotlib')
        self.img.setLookupTable(cmap.getLookupTable(0.0, 1.0, 256))
        self.img.setImage(self.data.T, autoLevels=False, levels=(0, 1))
        # Remove internal padding
        self.ci.setContentsMargins(0, 0, 0, 0)
        self.ci.setBorder(None)

    def add_spectrum(self, spectrum: np.ndarray):
        """
        Add a new spectrum line to the waterfall.
        """
        self.data[:-1] = self.data[1:]
        self.data[-1] = spectrum[::-1]
        self.img.setImage(np.fliplr(self.data.T), autoLevels=False, levels=(0, 1))
        self.view.setRange(xRange=(0, self.data.shape[1]), yRange=(0, self.data.shape[0]), padding=0)


class AudioMonitoring(gr.top_block, Qt.QWidget):
    """
    Main application window and GNU Radio flowgraph for audio monitoring.
    """
    def __init__(self):
        gr.top_block.__init__(self, "audio_monitoring", catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.fft_size = 1024
        self.samp_rate = 44100
        self.flowgraph_started = threading.Event()
        self.settings = Qt.QSettings("gnuradio/flowgraphs", "audio_monitoring")
        self.restore_window_geometry()
        # GUI and DSP setup
        self.setup_gui()
        self.setup_gnuradio_blocks()
        self.setup_connections()
        self.setup_timers()

    # --- GUI SETUP ---
    def setup_gui(self):
        """
        Set up the PyQt5 GUI layout and widgets.
        """
        self.setWindowTitle("audio_monitoring")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except BaseException as exc:
            print(f"Qt GUI: Could not set Icon: {str(exc)}", file=sys.stderr)
        # Main layout
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.top_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.top_scroll_layout.setSpacing(0)
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_layout.setContentsMargins(0, 0, 0, 0)
        self.top_layout.setSpacing(0)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_grid_layout.setContentsMargins(0, 0, 0, 0)
        self.top_grid_layout.setSpacing(0)
        self.top_layout.addLayout(self.top_grid_layout)
        # Waterfall
        self.pg_waterfall = WaterfallWidget(n_rows=self.fft_size, n_cols=self.fft_size // 2)
        self.pg_waterfall.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding)
        self.top_grid_layout.addWidget(self.pg_waterfall, 0, 0, 1, 1)
        # Spectrum plot
        self.pg_spectrum = pg.PlotWidget()
        self.pg_spectrum.showGrid(x=True, y=True)
        self.pg_spectrum.setYRange(-80, 0)  # dB scale
        self.pg_spectrum.setSizePolicy(Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding)
        self.pg_spectrum.setMouseEnabled(x=False, y=False)
        self.pg_spectrum.hideAxis('bottom')  # Optional: hide x-axis
        self.pg_spectrum.hideAxis('left')    # Optional: hide y-axis
        self.spectrum_curve = self.pg_spectrum.plot(pen=pg.mkPen('#88c0d0', width=1))
        self.top_grid_layout.addWidget(self.pg_spectrum, 1, 0, 1, 1)
        self.top_grid_layout.setRowStretch(0, 3)
        self.top_grid_layout.setRowStretch(1, 1)
        self.top_grid_layout.setColumnStretch(0, 1)

    # --- GNU RADIO BLOCKS SETUP ---
    def setup_gnuradio_blocks(self):
        """
        Set up GNU Radio blocks for audio input and FFT processing.
        """
        self.audio_source = audio.source(self.samp_rate, 'plughw:0,0', True)
        self.stream_to_vector = blocks.stream_to_vector(gr.sizeof_float, self.fft_size)
        self.fft_block = fft.fft_vfc(
            fft_size=self.fft_size,
            forward=True,
            window=window.rectangular(self.fft_size),
            shift=True
        )
        self.complex_to_mag = blocks.complex_to_mag(self.fft_size)
        self.fft_sink = blocks.vector_sink_f(self.fft_size)

    # --- GNU RADIO CONNECTIONS ---
    def setup_connections(self):
        """
        Connect GNU Radio blocks together.
        """
        self.connect((self.audio_source, 0), (self.stream_to_vector, 0))
        self.connect((self.stream_to_vector, 0), (self.fft_block, 0))
        self.connect((self.fft_block, 0), (self.complex_to_mag, 0))
        self.connect((self.complex_to_mag, 0), (self.fft_sink, 0))

    # --- TIMERS AND UPDATES ---
    def setup_timers(self):
        """
        Set up timers for updating the GUI with FFT data.
        """
        self.pg_timer = pg.QtCore.QTimer()
        self.pg_timer.timeout.connect(self.update_waterfall_from_fft)
        self.pg_timer.start(50)

    def update_waterfall_from_fft(self):
        """
        Fetch FFT data from the sink and update the waterfall and spectrum plots.
        """
        data = self.fft_sink.data()
        vlen = self.fft_size
        n_frames = len(data) // vlen
        if n_frames > 0:
            frames = np.array(data, dtype=np.float32).reshape((n_frames, vlen))
            for frame in frames:
                # Normalize or scale as needed
                norm_frame = np.abs(frame)
                norm_frame = np.clip(norm_frame / np.max(norm_frame), 1e-12, 1) if np.max(norm_frame) > 0 else norm_frame
                half = self.fft_size // 2
                norm_frame = norm_frame[:half]
                self.pg_waterfall.add_spectrum(norm_frame)
                # Plot spectrum in dB scale
                db_flipped = 10 * np.log10(norm_frame[::-1] + 1e-12)
                self.spectrum_curve.setData(db_flipped)
                self.pg_spectrum.setYRange(-80, 0)
                self.pg_spectrum.setXRange(0, len(db_flipped)-1, padding=0)
            self.fft_sink.reset()

    # --- WINDOW STATE ---
    def restore_window_geometry(self):
        """
        Restore window geometry from settings if available.
        """
        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except BaseException as exc:
            print(f"Qt GUI: Could not restore geometry: {str(exc)}", file=sys.stderr)

    def closeEvent(self, event):
        """
        Handle window close event: save geometry and stop flowgraph.
        """
        self.settings = Qt.QSettings("gnuradio/flowgraphs", "audio_monitoring")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()
        event.accept()

    def get_samp_rate(self) -> int:
        """
        Get the current sample rate.
        """
        return self.samp_rate

    def set_samp_rate(self, samp_rate: int):
        """
        Set a new sample rate.
        """
        self.samp_rate = samp_rate


def main(top_block_cls=AudioMonitoring, options=None):
    """
    Main entry point for the application.
    """
    qapp = Qt.QApplication(sys.argv)
    tb = top_block_cls()
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
    main()
