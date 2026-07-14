

import sys
from PyQt6 import uic
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QLabel

if __name__ == '__main__':
    app = QApplication(sys.argv)

    
    ui_file = Path(__file__).with_name("biaoqian_wenben.ui")
    ui = uic.loadUi(ui_file)
    mylabel: QLabel = ui.label
    print(mylabel.text())
    ui.show()

    sys.exit(app.exec())