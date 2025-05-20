# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_interface.ui'
##
## Created by: Qt User Interface Compiler version 6.9.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMenuBar, QPushButton,
    QSizePolicy, QStatusBar, QTextEdit, QToolButton,
    QVBoxLayout, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(600, 439)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.horizontalLayout_2 = QHBoxLayout(self.centralwidget)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.messaging_QWidget = QWidget(self.centralwidget)
        self.messaging_QWidget.setObjectName(u"messaging_QWidget")
        self.verticalLayout = QVBoxLayout(self.messaging_QWidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.messages_history_QTextEdit = QTextEdit(self.messaging_QWidget)
        self.messages_history_QTextEdit.setObjectName(u"messages_history_QTextEdit")

        self.verticalLayout.addWidget(self.messages_history_QTextEdit)

        self.sendin_area_QWidget = QWidget(self.messaging_QWidget)
        self.sendin_area_QWidget.setObjectName(u"sendin_area_QWidget")
        self.horizontalLayout_3 = QHBoxLayout(self.sendin_area_QWidget)
        self.horizontalLayout_3.setSpacing(5)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.horizontalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.load_file_QToolButton = QToolButton(self.sendin_area_QWidget)
        self.load_file_QToolButton.setObjectName(u"load_file_QToolButton")

        self.horizontalLayout_3.addWidget(self.load_file_QToolButton)

        self.input_message_QLineEdit = QLineEdit(self.sendin_area_QWidget)
        self.input_message_QLineEdit.setObjectName(u"input_message_QLineEdit")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.input_message_QLineEdit.sizePolicy().hasHeightForWidth())
        self.input_message_QLineEdit.setSizePolicy(sizePolicy)

        self.horizontalLayout_3.addWidget(self.input_message_QLineEdit)

        self.send_QPushButton = QPushButton(self.sendin_area_QWidget)
        self.send_QPushButton.setObjectName(u"send_QPushButton")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.send_QPushButton.sizePolicy().hasHeightForWidth())
        self.send_QPushButton.setSizePolicy(sizePolicy1)
        self.send_QPushButton.setMaximumSize(QSize(50, 16777215))

        self.horizontalLayout_3.addWidget(self.send_QPushButton)


        self.verticalLayout.addWidget(self.sendin_area_QWidget)


        self.horizontalLayout_2.addWidget(self.messaging_QWidget)

        self.monitoring_and_parameters_QWidget = QWidget(self.centralwidget)
        self.monitoring_and_parameters_QWidget.setObjectName(u"monitoring_and_parameters_QWidget")
        self.verticalLayout_2 = QVBoxLayout(self.monitoring_and_parameters_QWidget)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.monitoring_QFrame = QFrame(self.monitoring_and_parameters_QWidget)
        self.monitoring_QFrame.setObjectName(u"monitoring_QFrame")
        self.monitoring_QFrame.setFrameShape(QFrame.StyledPanel)
        self.monitoring_QFrame.setFrameShadow(QFrame.Raised)

        self.verticalLayout_2.addWidget(self.monitoring_QFrame)

        self.parameter_QGroupBox = QGroupBox(self.monitoring_and_parameters_QWidget)
        self.parameter_QGroupBox.setObjectName(u"parameter_QGroupBox")
        self.parameter_QGroupBox.setAutoFillBackground(False)
        self.parameter_QGroupBox.setFlat(False)
        self.gridLayout_2 = QGridLayout(self.parameter_QGroupBox)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.threshold_doubleSpinBox = QDoubleSpinBox(self.parameter_QGroupBox)
        self.threshold_doubleSpinBox.setObjectName(u"threshold_doubleSpinBox")

        self.gridLayout_2.addWidget(self.threshold_doubleSpinBox, 4, 1, 1, 1)

        self.threshold_QLabel = QLabel(self.parameter_QGroupBox)
        self.threshold_QLabel.setObjectName(u"threshold_QLabel")

        self.gridLayout_2.addWidget(self.threshold_QLabel, 4, 0, 1, 1)

        self.baudrate_doubleSpinBox = QDoubleSpinBox(self.parameter_QGroupBox)
        self.baudrate_doubleSpinBox.setObjectName(u"baudrate_doubleSpinBox")

        self.gridLayout_2.addWidget(self.baudrate_doubleSpinBox, 3, 1, 1, 1)

        self.baudrate_QLabel = QLabel(self.parameter_QGroupBox)
        self.baudrate_QLabel.setObjectName(u"baudrate_QLabel")

        self.gridLayout_2.addWidget(self.baudrate_QLabel, 3, 0, 1, 1)

        self.speed_QCombox = QComboBox(self.parameter_QGroupBox)
        self.speed_QCombox.addItem("")
        self.speed_QCombox.addItem("")
        self.speed_QCombox.addItem("")
        self.speed_QCombox.addItem("")
        self.speed_QCombox.setObjectName(u"speed_QCombox")

        self.gridLayout_2.addWidget(self.speed_QCombox, 2, 1, 1, 1)

        self.speed_QLabel = QLabel(self.parameter_QGroupBox)
        self.speed_QLabel.setObjectName(u"speed_QLabel")

        self.gridLayout_2.addWidget(self.speed_QLabel, 2, 0, 1, 1)

        self.carrier_frequency_QDoubleSpinBox = QDoubleSpinBox(self.parameter_QGroupBox)
        self.carrier_frequency_QDoubleSpinBox.setObjectName(u"carrier_frequency_QDoubleSpinBox")

        self.gridLayout_2.addWidget(self.carrier_frequency_QDoubleSpinBox, 0, 1, 1, 1)

        self.carrier_frequency_QLabel = QLabel(self.parameter_QGroupBox)
        self.carrier_frequency_QLabel.setObjectName(u"carrier_frequency_QLabel")

        self.gridLayout_2.addWidget(self.carrier_frequency_QLabel, 0, 0, 1, 1)


        self.verticalLayout_2.addWidget(self.parameter_QGroupBox)


        self.horizontalLayout_2.addWidget(self.monitoring_and_parameters_QWidget)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 600, 21))
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.load_file_QToolButton.setText(QCoreApplication.translate("MainWindow", u"...", None))
        self.send_QPushButton.setText(QCoreApplication.translate("MainWindow", u"Send", None))
        self.parameter_QGroupBox.setTitle(QCoreApplication.translate("MainWindow", u"parameters", None))
        self.threshold_QLabel.setText(QCoreApplication.translate("MainWindow", u"Threshold", None))
        self.baudrate_QLabel.setText(QCoreApplication.translate("MainWindow", u"baudrate", None))
        self.speed_QCombox.setItemText(0, QCoreApplication.translate("MainWindow", u"Slow", None))
        self.speed_QCombox.setItemText(1, QCoreApplication.translate("MainWindow", u"Normal", None))
        self.speed_QCombox.setItemText(2, QCoreApplication.translate("MainWindow", u"Fast", None))
        self.speed_QCombox.setItemText(3, QCoreApplication.translate("MainWindow", u"Custom", None))

        self.speed_QLabel.setText(QCoreApplication.translate("MainWindow", u"Speed", None))
        self.carrier_frequency_QLabel.setText(QCoreApplication.translate("MainWindow", u"Carrier Frequency", None))
    # retranslateUi

