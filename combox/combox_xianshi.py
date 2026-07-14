import sys
from PyQt6 import uic
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QComboBox, QLabel

if __name__ == '__main__':
    app = QApplication(sys.argv)

    
    ui_file = Path(__file__).with_name("combox.ui")
    ui = uic.loadUi(ui_file)
    myCombox: QComboBox = ui.comboBox
    myCombox.addItem("选项1")
    list  = ["选项2", "选项3", "选项4"]
    myCombox.addItems(list)
    ui.show()
    print("当前选中项的索引:", myCombox.currentText(), myCombox.currentIndex())
    sys.exit(app.exec())