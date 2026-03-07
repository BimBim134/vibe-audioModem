import sys
import numpy as np
import zmq
from PySide6 import QtWidgets, QtCore, QtUiTools
import pyqtgraph as pg

class ZMQWorker(QtCore.QObject):
    data_received = QtCore.Signal(np.ndarray)

    def __init__(self, port=5555):
        super().__init__()
        self.port = port
        self.running = True

    @QtCore.Slot()
    def run(self):
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(f"tcp://127.0.0.1:{self.port}")
        socket.setsockopt_string(zmq.SUBSCRIBE, "")
        
        while self.running:
            try:
                # Expecting float32 data from GNU Radio
                message = socket.recv()
                data = np.frombuffer(message, dtype=np.float32)
                if len(data) > 0:
                    self.data_received.emit(data)
            except Exception as e:
                print(f"ZMQ Error: {e}")
                break

    def stop(self):
        self.running = False

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        
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
            self.spectroscope_plot.setYRange(-100, 20)
            self.spectroscope_plot.setLabel('left', 'Amplitude', units='dB')
            self.spectroscope_plot.setLabel('bottom', 'Frequency', units='Hz')

        # Find and setup Pyqtgraph Spectrogram (Waterfall)
        self.spectrogram_placeholder = self.ui_widget.findChild(QtWidgets.QWidget, "spectrogramPlaceholder")
        if self.spectrogram_placeholder:
            self.spectrogram_layout = QtWidgets.QVBoxLayout(self.spectrogram_placeholder)
            self.spectrogram_canvas = pg.GraphicsLayoutWidget()
            self.spectrogram_layout.addWidget(self.spectrogram_canvas)
            self.spectrogram_plot = self.spectrogram_canvas.addPlot(title="Waterfall")
            self.img = pg.ImageItem()
            self.spectrogram_plot.addItem(self.img)
            
            # Setup Colormap/Colorbar
            colormap = pg.colormap.get('viridis')
            self.bar = pg.ColorBarItem(values=(-100, 20), colorMap=colormap)
            self.bar.setImageItem(self.img)

        # Waterfall rolling buffer
        self.n_fft = 1024
        self.waterfall_rows = 200
        self.waterfall_data = np.zeros((self.waterfall_rows, self.n_fft))

        # FFT Setup
        self.samp_rate = 48000
        self.freq_axis = np.fft.rfftfreq(self.n_fft, 1.0/self.samp_rate)

        # ZMQ Threading
        self.thread = QtCore.QThread()
        self.worker = ZMQWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.data_received.connect(self.update_plots)
        self.thread.start()

    @QtCore.Slot(np.ndarray)
    def update_plots(self, data):
        # Ensure we have enough data for FFT
        if len(data) < self.n_fft:
            return
            
        # Take the last n_fft samples
        chunk = data[-self.n_fft:]
        
        # Compute FFT
        win = np.hanning(self.n_fft)
        fft_data = np.fft.rfft(chunk * win)
        mag_db = 20 * np.log10(np.abs(fft_data) + 1e-10)

        # Update Spectroscope
        self.spectrum_curve.setData(self.freq_axis, mag_db)

        # Update Waterfall
        self.waterfall_data = np.roll(self.waterfall_data, -1, axis=0)
        self.waterfall_data[-1, :] = mag_db
        self.img.setImage(self.waterfall_data.T, autoLevels=False)
        self.img.setLevels([-100, 20])

    def closeEvent(self, event):
        self.worker.stop()
        self.thread.quit()
        self.thread.wait()
        event.accept()

def run_graphics_app():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    run_graphics_app()
