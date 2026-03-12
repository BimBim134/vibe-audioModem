import sys
import numpy as np
import zmq
from PySide6 import QtWidgets, QtCore, QtUiTools
import pyqtgraph as pg

# Configure PyQtGraph for Dark Theme
pg.setConfigOption('background', '#12141a')
pg.setConfigOption('foreground', '#a6adc8')

from src.config import (
    DEFAULT_SIGNAL_CONFIG,
    DEFAULT_PORTS_CONFIG,
    DEFAULT_PACKET_CONFIG,
    PortsConfig,
    SignalConfig,
    PacketConfig,
    MODULATION_PRESETS,
)
from src.tx.transmitter import send_data

from typing import Any
import logging
logger = logging.getLogger(__name__)

from datetime import datetime
import pmt

class ZMQWorker(QtCore.QObject):
    data_received = QtCore.Signal(np.ndarray)

    def __init__(self, ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG):
        super().__init__()
        self.port = ports_conf.fft_port
        self.running = True

    @QtCore.Slot()
    def run(self):
        logger.info(f"ZMQWorker starting on port {self.port}...")
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1s timeout
        try:
            socket.set_hwm(100)
            socket.connect(f"tcp://127.0.0.1:{self.port}")
            socket.setsockopt_string(zmq.SUBSCRIBE, "")
            logger.info(f"ZMQWorker connected to port {self.port}")
        except Exception as e:
            logger.info(f"ZMQ Connection Error: {e}")
            return
        
        while self.running:
            try:
                message = socket.recv()
                data = np.frombuffer(message, dtype=np.float32)
                if len(data) > 0:
                    self.data_received.emit(data)
            except zmq.Again:
                continue
            except zmq.ZMQError as e:
                logger.info(f"ZMQ Error: {e}")
                break
            except Exception as e:
                logger.info(f"Unexpected Error in ZMQWorker: {e}")
                break
        
        socket.close()
        context.term()
        logger.info("ZMQWorker stopped")

    def stop(self):
        self.running = False


class MessageZMQWorker(QtCore.QObject):
    """Worker to receive reassembled messages from the packet decoder."""
    message_received = QtCore.Signal(dict)

    def __init__(self, ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG):
        super().__init__()
        self.port = ports_conf.messages_port
        self.running = True

    @QtCore.Slot()
    def run(self):
        logger.info(f"MessageZMQWorker starting on port {self.port}...")
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.setsockopt(zmq.RCVTIMEO, 1000)
        try:
            socket.connect(f"tcp://127.0.0.1:{self.port}")
            socket.setsockopt_string(zmq.SUBSCRIBE, "")
            logger.info(f"MessageZMQWorker connected to port {self.port}")
        except Exception as e:
            logger.info(f"MessageZMQ Connection Error: {e}")
            return

        while self.running:
            try:
                received = socket.recv()
                # The packet decoder sends serialized PMT strings
                payload = pmt.to_python(pmt.deserialize_str(received))
                if isinstance(payload, dict):
                    self.message_received.emit(payload)
            except zmq.Again:
                continue
            except Exception as e:
                logger.info(f"Error in MessageZMQWorker: {e}")
                break
        
        socket.close()
        context.term()
        logger.info("MessageZMQWorker stopped")

    def stop(self):
        self.running = False


class ConstellationZMQWorker(QtCore.QObject):
    """Worker to receive constellation points (complex numbers) from the demodulator."""
    data_received = QtCore.Signal(np.ndarray)

    def __init__(self, ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG):
        super().__init__()
        self.port = ports_conf.constellation_port
        self.running = True

    @QtCore.Slot()
    def run(self):
        logger.info(f"ConstellationZMQWorker starting on port {self.port}...")
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.setsockopt(zmq.RCVTIMEO, 1000)
        try:
            socket.connect(f"tcp://127.0.0.1:{self.port}")
            socket.setsockopt_string(zmq.SUBSCRIBE, "")
            logger.info(f"ConstellationZMQWorker connected to port {self.port}")
        except Exception as e:
            logger.info(f"ConstellationZMQ Connection Error: {e}")
            return

        while self.running:
            try:
                message = socket.recv()
                # Data is gr.sizeof_gr_complex (complex64)
                data = np.frombuffer(message, dtype=np.complex64)
                if len(data) > 0:
                    self.data_received.emit(data)
            except zmq.Again:
                continue
            except Exception as e:
                logger.info(f"Error in ConstellationZMQWorker: {e}")
                break
        
        socket.close()
        context.term()
        logger.info("ConstellationZMQWorker stopped")

    def stop(self):
        self.running = False


class TransmitWorker(QtCore.QObject):
    finished = QtCore.Signal()

    def __init__(self, message: Any, signal_conf: SignalConfig, pkt_conf: PacketConfig, sender_name: str = "defaut"):
        super().__init__()
        self.message = message
        self.signal_conf = signal_conf
        self.pkt_conf = pkt_conf
        self.sender_name = sender_name
 
    @QtCore.Slot()
    def run(self):
        try:
            logger.info(f"TransmitWorker starting transmission of {len(self.message)} bytes as '{self.sender_name}'...")
            send_data(self.message, pkt=self.pkt_conf, sig=self.signal_conf, sender_name=self.sender_name, handle_signals=False)
            logger.info("TransmitWorker finished transmission")
        except Exception as e:
            logger.info(f"Transmission Error: {e}")
        finally:
            self.finished.emit()

class MainWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
        ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG,
        pkt_conf: PacketConfig = DEFAULT_PACKET_CONFIG,
    ):
        super().__init__()
        
        self.signal_conf = signal_conf
        self.ports_conf = ports_conf
        self.pkt_conf = pkt_conf
        
        # Load UI
        loader = QtUiTools.QUiLoader()
        ui_file = QtCore.QFile("src/UI/pyqt/main_window.ui")
        if not ui_file.open(QtCore.QFile.ReadOnly):
            logger.info(f"Could not open UI file: {ui_file.errorString()}")
            return
        
        # Load the UI into a separate widget first
        self.ui_widget = loader.load(ui_file)
        ui_file.close()
        
        if not self.ui_widget:
            logger.info("Failed to load UI widget")
            return
 
        # Set the loaded UI widget as the central widget
        self.setCentralWidget(self.ui_widget)
        self.setWindowTitle("Vibe Audio Modem - Signal Debugger")

        # Find and setup Pyqtgraph Spectroscope (Spectrum)
        self.spectroscope_placeholder = self.ui_widget.findChild(QtWidgets.QWidget, "spectroscopePlaceholder")
        if self.spectroscope_placeholder:
            self.spectroscope_layout = QtWidgets.QVBoxLayout(self.spectroscope_placeholder)
            self.spectroscope_plot = pg.PlotWidget()
            self.spectroscope_layout.addWidget(self.spectroscope_plot)
            self.spectrum_curve = self.spectroscope_plot.plot(pen=pg.mkPen('#89b4fa', width=1))
            self.spectroscope_plot.setLogMode(x=False, y=False)
            self.spectroscope_plot.setYRange(-50, 50)
            self.spectroscope_plot.setXRange(0, 5000)
            self.spectroscope_plot.enableAutoRange(enable=False)
            self.spectroscope_plot.setMouseEnabled(x=False, y=False)

            # Hide everything except the X axis ticks (showing Hz values)
            spectroscope_axis = self.spectroscope_plot.getAxis('left')
            spectroscope_axis.setLabel('')
            spectroscope_axis.setStyle(showValues=False, tickLength=0)
            self.spectroscope_plot.setLabel('bottom', '')  # no xlabel, just ticks
            self.spectroscope_plot.showGrid(x=True, y=True, alpha=0.1)

        # Find and setup Pyqtgraph Spectrogram (Waterfall)
        self.spectrogram_placeholder = self.ui_widget.findChild(QtWidgets.QWidget, "spectrogramPlaceholder")
        
        # Waterfall rolling buffer
        self.n_fft = self.ports_conf.fft_size
        self.display_size = self.n_fft // 2
        self.waterfall_rows = 400
        self.waterfall_data = np.zeros((self.waterfall_rows, self.display_size), dtype=np.float32)

        # FFT Setup
        self.samp_rate = self.signal_conf.samp_rate
        # Frequency axis in Hz (0 to Fs/2)
        self.freq_axis = np.linspace(0, self.samp_rate / 2.0, self.display_size)

        if self.spectrogram_placeholder:
            self.spectrogram_layout = QtWidgets.QVBoxLayout(self.spectrogram_placeholder)
            self.spectrogram_canvas = pg.GraphicsLayoutWidget()
            self.spectrogram_layout.addWidget(self.spectrogram_canvas)
            self.spectrogram_plot = self.spectrogram_canvas.addPlot()
            
            # Initialize with data so it has the correct width right away
            self.img = pg.ImageItem(image=self.waterfall_data.T)
            self.spectrogram_plot.addItem(self.img)
            
            # Hide all axes so the image fills the entire frame
            for axis in ('left', 'bottom', 'right', 'top'):
                self.spectrogram_plot.hideAxis(axis)
            self.spectrogram_plot.setMouseEnabled(x=False, y=False)
            
            # Remove canvas margins
            self.spectrogram_canvas.ci.layout.setContentsMargins(0, 0, 0, 0)
            self.spectrogram_canvas.ci.layout.setSpacing(0)
            
            # Setup Colormap/Colorbar
            colormap = pg.colormap.get('viridis')
            self.bar = pg.ColorBarItem(values=(-50, 50), colorMap=colormap)
            self.bar.setImageItem(self.img)

            # ZMQ Context for configuration pub
        self.ctx = zmq.Context()
        self.config_pub_socket = self.ctx.socket(zmq.PUB)
        try:
            self.config_pub_socket.bind(f"tcp://127.0.0.1:{self.ports_conf.config_port}")
            logger.info(f"Config publisher bound to port {self.ports_conf.config_port}")
        except Exception as e:
            logger.error(f"Failed to bind config publisher: {e}")

        # Map pixels to Hz explicitly via setRect now that the image is populated
            self.img.setRect(QtCore.QRectF(0, 0, self.samp_rate / 2.0, self.waterfall_rows))

        # Find and setup UI components
        self.message_edit = self.ui_widget.findChild(QtWidgets.QTextEdit, "MessageEdit")
        self.send_button = self.ui_widget.findChild(QtWidgets.QPushButton, "SendButton")
        self.messages_boards = self.ui_widget.findChild(QtWidgets.QTextEdit, "MessagesBoards")
        self.carrier_freq_spin = self.ui_widget.findChild(QtWidgets.QDoubleSpinBox, "CarrierFrequency")
        self.sender_name_edit = self.ui_widget.findChild(QtWidgets.QLineEdit, "senderName")
        self.constellation_placeholder = self.ui_widget.findChild(QtWidgets.QWidget, "constellationDiagramPlaceholder")
        self.modulation_chooser = self.ui_widget.findChild(QtWidgets.QComboBox, "modulationChooser")

        if self.constellation_placeholder:
            self.constellation_layout = QtWidgets.QVBoxLayout(self.constellation_placeholder)
            self.constellation_plot = pg.PlotWidget()
            self.constellation_layout.addWidget(self.constellation_plot)
            
            self.constellation_scatter = pg.ScatterPlotItem(size=3, pen=pg.mkPen(None), brush=pg.mkBrush(137, 180, 250, 200))
            self.constellation_plot.addItem(self.constellation_scatter)
            
            # Fixed range, no auto-scale
            self.constellation_plot.setXRange(-2, 2, padding=0.1)
            self.constellation_plot.setYRange(-2, 2, padding=0.1)
            self.constellation_plot.enableAutoRange(enable=False)
            self.constellation_plot.setMouseEnabled(x=False, y=False)
            
            # Hide tick values and labels — keep default tick positions so the grid stays visible
            self.constellation_plot.setTitle(None)
            for axis in ('left', 'bottom', 'right', 'top'):
                ax = self.constellation_plot.getAxis(axis)
                ax.setLabel('')
                ax.setStyle(showValues=False, tickLength=0)
            
            self.constellation_plot.showGrid(x=True, y=True, alpha=0.1)
            self.constellation_plot.setAspectLocked(True)

            # Buffer for points
            self.const_buffer_size = 512
            self.const_points_i = np.zeros(self.const_buffer_size)
            self.const_points_q = np.zeros(self.const_buffer_size)

        if self.carrier_freq_spin:
            self.carrier_freq_spin.setValue(self.signal_conf.carrier_freq)
            self.carrier_freq_spin.valueChanged.connect(self.update_carrier_freq)
            logger.info(f"CarrierFrequency spinbox connected (initial: {self.signal_conf.carrier_freq})")

        if self.modulation_chooser:
            self.modulation_chooser.currentIndexChanged.connect(self.update_modulation_preset)
            logger.info("ModulationChooser connected")
            # Set initials based on combo box value
            self.update_modulation_preset(self.modulation_chooser.currentIndex())

        if self.send_button and self.message_edit:
            self.send_button.clicked.connect(self.start_transmission)
            logger.info("SendButton and MessageEdit connected")
        else:
            logger.info("Warning: SendButton or MessageEdit not found in UI")

        # ZMQ Threading for Waterfall/Spectrum
        self.thread = QtCore.QThread()
        self.worker = ZMQWorker(ports_conf=self.ports_conf)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.data_received.connect(self.update_plots)
        self.thread.start()

        # ZMQ Threading for Reassembled Messages
        self.msg_thread = QtCore.QThread()
        self.msg_worker = MessageZMQWorker(ports_conf=self.ports_conf)
        self.msg_worker.moveToThread(self.msg_thread)
        self.msg_thread.started.connect(self.msg_worker.run)
        self.msg_worker.message_received.connect(self.display_received_message)
        self.msg_thread.start()

        # ZMQ Threading for Constellation
        self.const_thread = QtCore.QThread()
        self.const_worker = ConstellationZMQWorker(ports_conf=self.ports_conf)
        self.const_worker.moveToThread(self.const_thread)
        self.const_thread.started.connect(self.const_worker.run)
        self.const_worker.data_received.connect(self.update_constellation)
        self.const_thread.start()

        # Welcome message
        if self.messages_boards:
            welcome_html = (
                '<div style="margin: 6px 0; padding: 8px 10px; '
                'background-color: #2b2f3a; border-left: 3px solid #92bfff; border-radius: 4px;">'
                '<span style="color: #92bfff; font-weight: bold; font-size: 11px;">vibe-audioModem</span>'
                '<span style="color: #686d88; font-size: 10px; margin-left: 8px;">système</span>'
                '<div style="color: #dce4f5; margin-top: 4px; font-size: 12px; white-space: pre-wrap;">'
                'Bienvenue sur vibe-audioModem 📡\nEn attente de transmission...</div>'
                '</div>'
            )
            self.messages_boards.append(welcome_html)

    @QtCore.Slot(np.ndarray)
    def update_constellation(self, data):
        """Update the constellation scatter plot."""
        if not self.constellation_placeholder:
            return

        # data is complex64
        i_data = data.real
        q_data = data.imag

        # Update rolling buffer
        n_new = len(data)
        if n_new >= self.const_buffer_size:
            self.const_points_i = i_data[-self.const_buffer_size:]
            self.const_points_q = q_data[-self.const_buffer_size:]
        else:
            self.const_points_i = np.roll(self.const_points_i, -n_new)
            self.const_points_q = np.roll(self.const_points_q, -n_new)
            self.const_points_i[-n_new:] = i_data
            self.const_points_q[-n_new:] = q_data

        self.constellation_scatter.setData(self.const_points_i, self.const_points_q)

    @QtCore.Slot(float)
    def update_carrier_freq(self, value):
        """Update the signal configuration with the new carrier frequency."""
        self.signal_conf.carrier_freq = value
        logger.info(f"Carrier frequency updated to {value} Hz")

    @QtCore.Slot(int)
    def update_modulation_preset(self, index):
        """Update the signal configuration based on the selected modulation preset."""
        if not self.modulation_chooser:
            return
        
        text = self.modulation_chooser.currentText()
        preset_name = None
        if "SLOW" in text:
            preset_name = "SLOW"
        elif "MEDIUM" in text:
            preset_name = "MEDIUM"
        elif "FAST" in text:
            preset_name = "FAST"

        if preset_name and preset_name in MODULATION_PRESETS:
            preset = MODULATION_PRESETS[preset_name]
            self.signal_conf.baudrate = preset.baudrate
            self.signal_conf.modulation_preset = preset_name
            try:
                self.config_pub_socket.send_string(f"PRESET:{preset_name}")
            except Exception as e:
                pass
            logger.info(f"Modulation preset updated to {preset_name}: baudrate={preset.baudrate}")

    @QtCore.Slot(dict)
    def display_received_message(self, payload):
        """Format and display a message received from the packet decoder."""
        if not self.messages_boards:
            return

        date_str = datetime.now().strftime("%H:%M:%S")
        sender = payload.get("sender_name", "unknown")
        carrier_freq = payload.get("carrier_freq")
        freq = f"{carrier_freq:.0f} Hz" if carrier_freq else "RX"

        data = payload.get("data")
        if isinstance(data, np.ndarray):
            msg_content = data.tobytes().decode("utf-8", errors="replace")
        else:
            msg_content = str(data)

        import html
        msg_escaped = html.escape(msg_content)

        html_block = (
            f'<div style="margin: 6px 0; padding: 8px 10px; '
            f'background-color: #2b2f3a; border-left: 3px solid #92bfff; border-radius: 4px;">'
            f'<span style="color: #92bfff; font-weight: bold; font-size: 11px;">{html.escape(sender)}</span>'
            f'<span style="color: #686d88; font-size: 10px; margin-left: 8px;">{freq} &mdash; {date_str}</span>'
            f'<div style="color: #dce4f5; margin-top: 4px; font-size: 12px; white-space: pre-wrap;">{msg_escaped}</div>'
            f'</div>'
        )
        self.messages_boards.append(html_block)

    @QtCore.Slot(np.ndarray)
    def update_plots(self, data):
        # data is already magnitude from GNU Radio (fft_size elements)
        # Shift=True in GNU Radio means DC is at center
        if len(data) == self.n_fft:
            # Take the positive frequency part (second half)
            data = data[self.n_fft // 2:]
        elif len(data) % self.n_fft == 0:
            # Handle multiple vectors
            data = data[-self.n_fft:]
            data = data[self.n_fft // 2:]
        else:
            return
            
        # Ensure we have the correct size for plotting
        if len(data) != self.display_size:
            return

        # Convert to dB
        mag_db = 20 * np.log10(data + 1e-10)

        # Update Spectroscope
        self.spectrum_curve.setData(self.freq_axis, mag_db)

        # Update Waterfall
        self.waterfall_data = np.roll(self.waterfall_data, -1, axis=0)
        self.waterfall_data[-1, :] = mag_db
        self.img.setImage(self.waterfall_data.T, autoLevels=False)
        self.img.setLevels([-100, 40]) # Adjusted levels

    @QtCore.Slot()
    def start_transmission(self):
        message_text = self.message_edit.toPlainText()
        if not message_text:
            return
 
        sender_name = self.sender_name_edit.text() if self.sender_name_edit else "Me"
 
        logger.info(f"Starting transmission: {message_text} (Sender: {sender_name})")
 
        try:
            self.config_pub_socket.send_string(f"PRESET:{self.signal_conf.modulation_preset}")
        except Exception:
            pass

        # Display sent message in the UI
        if self.messages_boards:
            import html
            date_str = datetime.now().strftime("%H:%M:%S")
            freq = f"{self.signal_conf.carrier_freq:.0f} Hz"
            msg_escaped = html.escape(message_text)
            html_block = (
                f'<div style="margin: 6px 0; padding: 8px 10px; '
                f'background-color: #252830; border-left: 3px solid #686d88; border-radius: 4px;">'
                f'<span style="color: #b8c4da; font-weight: bold; font-size: 11px;">{html.escape(sender_name)}</span>'
                f'<span style="color: #686d88; font-size: 10px; margin-left: 8px;">{freq} &mdash; {date_str}</span>'
                f'<div style="color: #dce4f5; margin-top: 4px; font-size: 12px; white-space: pre-wrap;">{msg_escaped}</div>'
                f'</div>'
            )
            self.messages_boards.append(html_block)
        
        # Disable button during transmission to avoid multiple overlapping transmissions
        self.send_button.setEnabled(False)
        
        # Create thread and worker
        self.transmit_thread = QtCore.QThread()
        self.transmit_worker = TransmitWorker(message_text, self.signal_conf, self.pkt_conf, sender_name=sender_name)
        self.transmit_worker.moveToThread(self.transmit_thread)
        
        # Connect signals
        self.transmit_thread.started.connect(self.transmit_worker.run)
        self.transmit_worker.finished.connect(self.transmit_thread.quit)
        self.transmit_worker.finished.connect(self.transmit_worker.deleteLater)
        self.transmit_thread.finished.connect(self.transmit_thread.deleteLater)
        self.transmit_thread.finished.connect(lambda: self.send_button.setEnabled(True))
        
        # Clear message edit
        self.message_edit.clear()
        
        # Start thread
        self.transmit_thread.start()

    def closeEvent(self, event):
        self.worker.stop()
        self.thread.quit()
        self.thread.wait()

        self.msg_worker.stop()
        self.msg_thread.quit()
        self.msg_thread.wait()

        self.const_worker.stop()
        self.const_thread.quit()
        self.const_thread.wait()
        
        if self.config_pub_socket:
            self.config_pub_socket.close()
        if self.ctx:
            self.ctx.term()

        event.accept()

def run_graphics_app(
    signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG,
    pkt_conf: PacketConfig = DEFAULT_PACKET_CONFIG,
):
    app = QtWidgets.QApplication(sys.argv)

    # Load QSS stylesheet
    qss_path = QtCore.QFile("src/UI/pyqt/style.qss")
    if qss_path.open(QtCore.QFile.ReadOnly | QtCore.QFile.Text):
        stream = QtCore.QTextStream(qss_path)
        app.setStyleSheet(stream.readAll())
        qss_path.close()
    else:
        logger.warning("Could not load style.qss")

    window = MainWindow(signal_conf=signal_conf, ports_conf=ports_conf, pkt_conf=pkt_conf)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_graphics_app()
