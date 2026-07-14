

import sys
from PyQt6.QtCore import QDateTime, QTimer
from PyQt6 import uic
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

def show(label: QLabel):
    time = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
    label.setText(time)

def start(timer: QTimer, label: QLabel):   
    timer.start(1000)
    timer.timeout.connect(lambda: show(label))

def stop(timer: QTimer):
    timer.stop()
def resource_path(filename: str) -> Path:
    base_dir = Path(getattr(sys, "_MEIPASS",
                            Path(__file__).resolve().parent))
    return base_dir / filename

if __name__ == '__main__':
    app = QApplication(sys.argv)

    ui_file = resource_path("timer.ui")
    ui = uic.loadUi(ui_file)
    print(ui)

    timer = QTimer(ui)
    pushButton: QPushButton = ui.pushButton
    pushButton_2: QPushButton = ui.pushButton_2
    label: QLabel = ui.label
    
    pushButton.clicked.connect(lambda: start(timer, label))
    pushButton_2.clicked.connect(lambda: stop(timer))

    print(label.text())
    ui.show()

    sys.exit(app.exec())