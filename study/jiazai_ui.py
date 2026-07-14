from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6 import uic
import sys

if __name__ == "__main__":
    app = QApplication(sys.argv)
 
    ui_file = Path(__file__).with_name("trans_ui.ui")
    ui = uic.loadUi(ui_file)
    ui.show()

    sys.exit(app.exec())

