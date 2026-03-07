import sys
import numpy as np
import zmq
from PySide6 import QtWidgets, QtCore, QtUiTools
import pyqtgraph as pg
from src.config import (
    DEFAULT_SIGNAL_CONFIG,
    DEFAULT_PORTS_CONFIG,
    PortsConfig,
    SignalConfig,
)

class ZMQWorker(QtCore.QObject):
    data_received = QtCore.Signal(np.ndarray)

    def __init__(self, ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG):
        super().__init__()
        self.port = ports_conf.fft_port
        self.running = True

    @QtCore.Slot()
    def run(self):
        print(f"ZMQWorker starting on port {self.port}...")
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.setsockopt(zmq.RCVTIMEO, 1000)  # 1s timeout
        try:
            socket.set_hwm(100)
            socket.connect(f"tcp://127.0.0.1:{self.port}")
            socket.setsockopt_string(zmq.SUBSCRIBE, "")
            print(f"ZMQWorker connected to port {self.port}")
        except Exception as e:
            print(f"ZMQ Connection Error: {e}")
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
                print(f"ZMQ Error: {e}")
                break
            except Exception as e:
                print(f"Unexpected Error in ZMQWorker: {e}")
                break
        
        socket.close()
        context.term()
        print("ZMQWorker stopped")

    def stop(self):
        self.running = False

class MainWindow(QtWidgets.QMainWindow):
    def __init__(
        self,
        signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
        ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG,
    ):
        super().__init__()
        
        self.signal_conf = signal_conf
        self.ports_conf = ports_conf
        
        # Load UI
        loader = QtUiTools.QUiLoader()
        ui_file = QtCore.QFile("/home/bimbim/Codes/vibe-audioModem/src/UI/pyqt/main_window.ui")
        if not ui_file.open(QtCore.QFile.ReadOnly):
            print(f"Could not open UI file: {ui_file.errorString()}")
            return
        
        # Load the UI into a separate widget first
        self.ui_widget = loader.load(ui_file)
        ui_file.close()
        
        if not self.ui_widget:
            print("Failed to load UI widget")
            return

        # Set the loaded UI widget as the central widget
        self.setCentralWidget(self.ui_widget)
        self.setWindowTitle("Vibe Audio Modem - Signal Debugger")

        # Find and setup Pyqtgraph Spectroscope (Spectrum)
        self.spectroscope_placeholder = self.ui_widget.findChild(QtWidgets.QWidget, "spectroscopePlaceholder")
        if self.spectroscope_placeholder:
            self.spectroscope_layout = QtWidgets.QVBoxLayout(self.spectroscope_placeholder)
            self.spectroscope_plot = pg.PlotWidget(title="Audio Spectrum")
            self.spectroscope_layout.addWidget(self.spectroscope_plot)
            self.spectrum_curve = self.spectroscope_plot.plot(pen='y')
            self.spectroscope_plot.setLogMode(x=False, y=False)
            self.spectroscope_plot.setYRange(-50, 50)
            self.spectroscope_plot.setLabel('left', 'Amplitude', units='dB')
            self.spectroscope_plot.setLabel('bottom', 'Frequency', units='Hz')

        # Find and setup Pyqtgraph Spectrogram (Waterfall)
        self.spectrogram_placeholder = self.ui_widget.findChild(QtWidgets.QWidget, "spectrogramPlaceholder")
        
        # Waterfall rolling buffer
        self.n_fft = self.ports_conf.fft_size
        self.display_size = self.n_fft // 2
        self.waterfall_rows = 200
        self.waterfall_data = np.zeros((self.waterfall_rows, self.display_size), dtype=np.float32)

        # FFT Setup
        self.samp_rate = self.signal_conf.samp_rate
        # Frequency axis in Hz (0 to Fs/2)
        self.freq_axis = np.linspace(0, self.samp_rate / 2.0, self.display_size)

        if self.spectrogram_placeholder:
            self.spectrogram_layout = QtWidgets.QVBoxLayout(self.spectrogram_placeholder)
            self.spectrogram_canvas = pg.GraphicsLayoutWidget()
            self.spectrogram_layout.addWidget(self.spectrogram_canvas)
            self.spectrogram_plot = self.spectrogram_canvas.addPlot(title="Waterfall")
            
            # Initialize with data so it has the correct width right away
            self.img = pg.ImageItem(image=self.waterfall_data.T)
            self.spectrogram_plot.addItem(self.img)
            self.spectrogram_plot.setLabel('bottom', 'Frequency', units='Hz')
            self.spectrogram_plot.setLabel('left', 'Time', units='frames')
            
            # Setup Colormap/Colorbar
            colormap = pg.colormap.get('viridis')
            self.bar = pg.ColorBarItem(values=(-50, 50), colorMap=colormap)
            self.bar.setImageItem(self.img)

            # Map pixels to Hz explicitly via setRect now that the image is populated
            self.img.setRect(QtCore.QRectF(0, 0, self.samp_rate / 2.0, self.waterfall_rows))

        # ZMQ Threading
        self.thread = QtCore.QThread()
        self.worker = ZMQWorker(ports_conf=self.ports_conf)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.data_received.connect(self.update_plots)
        self.thread.start()

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

    def closeEvent(self, event):
        self.worker.stop()
        self.thread.quit()
        self.thread.wait()
        event.accept()

def run_graphics_app(
    signal_conf: SignalConfig = DEFAULT_SIGNAL_CONFIG,
    ports_conf: PortsConfig = DEFAULT_PORTS_CONFIG,
):
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow(signal_conf=signal_conf, ports_conf=ports_conf)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_graphics_app()
