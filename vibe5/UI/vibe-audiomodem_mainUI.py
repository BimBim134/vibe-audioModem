import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout
from main_interface import Ui_MainWindow
from audio_monitoring import AudioMonitoring

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.audio_monitor_widget = AudioMonitoring()
        self.audio_monitor_widget.setParent(self.ui.monitoring_QFrame)
        layout = QVBoxLayout(self.ui.monitoring_QFrame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.audio_monitor_widget)
        self.audio_monitor_widget.start()

    def closeEvent(self, event):
        self.audio_monitor_widget.stop()
        self.audio_monitor_widget.wait()
        event.accept()

def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()