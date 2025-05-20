import sys
import sip

from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from main_interface import Ui_MainWindow  # generated from your .ui file
from audio_monitoring import audio_monitoring


class MainWindow(QMainWindow):
    def __init__(self, top_block):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Wrap and embed the Waterfall (Spectrogram) widget
        audio_monitoring_widget = sip.wrapinstance(audio_monitoring.pyqwidget(), QWidget)
        layout_spectro = QVBoxLayout(self.ui.spectrogram_QFrame)
        layout_spectro.setContentsMargins(0, 0, 0, 0)
        layout_spectro.addWidget(audio_monitoring_widget)


def main():
    app = QApplication(sys.argv)

    tb = TopBlock()
    tb.start()

    win = MainWindow(tb)
    win.show()

    ret = app.exec()

    tb.stop()
    tb.wait()
    sys.exit(ret)


if __name__ == "__main__":
    main()
