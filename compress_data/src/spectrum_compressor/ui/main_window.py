from __future__ import annotations

from base64 import b64decode, b64encode
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ..application import ApplicationController
from ..config import AppConfig, ConfigManager
from ..models import SerialSettings


class MainWindow(QMainWindow):
    """Complete single-page operator interface."""

    def __init__(self, controller: ApplicationController, config_manager: ConfigManager) -> None:
        super().__init__()
        self.controller = controller
        self.config_manager = config_manager
        self.config = self.config_manager.load()
        self._task_running = bool(controller.is_running)
        self._serial_open = bool(controller.is_serial_open)
        self.count_labels: dict[str, QLabel] = {}
        self._serial_parameter_widgets: list[QWidget] = []
        self._directory_widgets: list[QWidget] = []

        self.setWindowTitle("光谱压缩串口上位机")
        self.setMinimumSize(900, 680)
        self.resize(1080, 780)
        self._build_ui()
        self._connect_signals()
        self._apply_config(self.config)
        self.refresh_serial_ports()
        self._set_port(self.config.serial.port)
        self._on_task_state_changed(self._task_running, "任务运行中" if self._task_running else "任务已停止")
        self._on_serial_state_changed(self._serial_open, "串口已打开" if self._serial_open else "串口已关闭")
        self.controller.refresh_counts()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(20, 16, 20, 16)
        root_layout.setSpacing(12)

        title = QLabel("光谱压缩串口上位机")
        title.setObjectName("titleLabel")
        subtitle = QLabel("光谱文件自动抽样压缩 · 串口队列发送 · 运行状态持久化")
        subtitle.setObjectName("subtitleLabel")
        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)
        root_layout.addWidget(self._build_directory_group())
        root_layout.addWidget(self._build_serial_group())
        root_layout.addLayout(self._build_action_row())
        root_layout.addWidget(self._build_status_group())
        root_layout.addWidget(self._build_log_group(), stretch=1)

        self.setCentralWidget(central)
        self.statusBar().showMessage("就绪")
        self._apply_styles()

    def _build_directory_group(self) -> QGroupBox:
        group = QGroupBox("数据文件夹")
        layout = QGridLayout(group)
        self.input_path_edit = QLineEdit()
        self.input_path_edit.setPlaceholderText("请选择原始光谱 txt 文件夹")
        self.input_browse_button = QPushButton("浏览…")
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText("请选择压缩文件输出文件夹")
        self.output_browse_button = QPushButton("浏览…")
        layout.addWidget(QLabel("输入文件夹"), 0, 0)
        layout.addWidget(self.input_path_edit, 0, 1)
        layout.addWidget(self.input_browse_button, 0, 2)
        layout.addWidget(QLabel("输出文件夹"), 1, 0)
        layout.addWidget(self.output_path_edit, 1, 1)
        layout.addWidget(self.output_browse_button, 1, 2)
        layout.setColumnStretch(1, 1)
        self._directory_widgets = [
            self.input_path_edit,
            self.input_browse_button,
            self.output_path_edit,
            self.output_browse_button,
        ]
        return group

    def _build_serial_group(self) -> QGroupBox:
        group = QGroupBox("串口配置")
        layout = QGridLayout(group)
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.refresh_ports_button = QPushButton("刷新串口")
        self.baudrate_combo = QComboBox()
        for baudrate in (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600):
            self.baudrate_combo.addItem(str(baudrate), baudrate)
        self.data_bits_combo = QComboBox()
        for bits in (5, 6, 7, 8):
            self.data_bits_combo.addItem(str(bits), bits)
        self.parity_combo = QComboBox()
        for label, value in (("无校验", "N"), ("偶校验", "E"), ("奇校验", "O"), ("标记", "M"), ("空格", "S")):
            self.parity_combo.addItem(label, value)
        self.stop_bits_combo = QComboBox()
        for label, value in (("1", 1.0), ("1.5", 1.5), ("2", 2.0)):
            self.stop_bits_combo.addItem(label, value)

        layout.addWidget(QLabel("串口"), 0, 0)
        layout.addWidget(self.port_combo, 0, 1)
        layout.addWidget(self.refresh_ports_button, 0, 2)
        layout.addWidget(QLabel("波特率"), 0, 3)
        layout.addWidget(self.baudrate_combo, 0, 4)
        layout.addWidget(QLabel("数据位"), 1, 0)
        layout.addWidget(self.data_bits_combo, 1, 1)
        layout.addWidget(QLabel("校验位"), 1, 2)
        layout.addWidget(self.parity_combo, 1, 3)
        layout.addWidget(QLabel("停止位"), 1, 4)
        layout.addWidget(self.stop_bits_combo, 1, 5)
        layout.setColumnStretch(1, 2)
        layout.setColumnStretch(4, 1)
        self._serial_parameter_widgets = [
            self.port_combo,
            self.refresh_ports_button,
            self.baudrate_combo,
            self.data_bits_combo,
            self.parity_combo,
            self.stop_bits_combo,
        ]
        return group

    def _build_action_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.serial_status_label = QLabel("串口已关闭")
        self.serial_status_label.setObjectName("statusPill")
        self.serial_button = QPushButton("打开串口")
        self.serial_button.setObjectName("secondaryButton")
        self.task_status_label = QLabel("任务已停止")
        self.task_status_label.setObjectName("statusPill")
        self.task_button = QPushButton("启动任务")
        self.task_button.setObjectName("primaryButton")
        layout.addWidget(QLabel("串口状态："))
        layout.addWidget(self.serial_status_label)
        layout.addWidget(self.serial_button)
        layout.addItem(QSpacerItem(24, 1, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        layout.addWidget(QLabel("任务状态："))
        layout.addWidget(self.task_status_label)
        layout.addWidget(self.task_button)
        return layout

    def _build_status_group(self) -> QGroupBox:
        group = QGroupBox("运行状态")
        layout = QGridLayout(group)

        definitions = (
            ("discovered", "已发现"),
            ("compressed", "已压缩"),
            ("pending_send", "待发送"),
            ("sent", "发送成功"),
            ("failed", "压缩失败"),
            ("failed_send", "发送文件错误"),
        )

        for column, (key, title) in enumerate(definitions):
            frame = QFrame()
            frame.setObjectName("metricCard")
            card_layout = QVBoxLayout(frame)

            value_label = QLabel("0")
            value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_label.setObjectName("metricValue")

            title_label = QLabel(title)
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_label.setObjectName("metricTitle")

            card_layout.addWidget(value_label)
            card_layout.addWidget(title_label)
            layout.addWidget(frame, 0, column)
            self.count_labels[key] = value_label

        self.reset_all_button = QPushButton("清空并重新开始")
        self.reset_all_button.setObjectName("dangerButton")
        layout.addWidget(
            self.reset_all_button,
            1,
            0,
            1,
            len(definitions),
            Qt.AlignmentFlag.AlignRight,
        )

        return group

    def _build_log_group(self) -> QGroupBox:
        group = QGroupBox("运行日志")
        layout = QVBoxLayout(group)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("最多显示 2000 行，完整日志写入滚动文件"))
        toolbar.addStretch(1)
        self.clear_log_button = QPushButton("清空显示")
        toolbar.addWidget(self.clear_log_button)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_view.document().setMaximumBlockCount(2000)
        layout.addLayout(toolbar)
        layout.addWidget(self.log_view)
        return group

    def _connect_signals(self) -> None:
        self.input_browse_button.clicked.connect(lambda: self._browse_directory(self.input_path_edit, "选择输入文件夹"))
        self.output_browse_button.clicked.connect(lambda: self._browse_directory(self.output_path_edit, "选择输出文件夹"))
        self.refresh_ports_button.clicked.connect(self.refresh_serial_ports)
        self.serial_button.clicked.connect(self._toggle_serial)
        self.task_button.clicked.connect(self._toggle_tasks)
        self.clear_log_button.clicked.connect(self.log_view.clear)
        self.reset_all_button.clicked.connect(self._reset_all_data)
        self.controller.log_message.connect(self._append_log)
        self.controller.counts_changed.connect(self._on_counts_changed)
        self.controller.task_state_changed.connect(self._on_task_state_changed)
        self.controller.serial_state_changed.connect(self._on_serial_state_changed)

    def refresh_serial_ports(self) -> None:
        previous = self.port_combo.currentText().strip() or self.config.serial.port
        self.port_combo.clear()
        ports = self.controller.available_ports()
        for port in ports:
            self.port_combo.addItem(port.device, port.device)
            index = self.port_combo.count() - 1
            self.port_combo.setItemData(index, port.description, Qt.ItemDataRole.ToolTipRole)
        if previous:
            self._set_port(previous)
        elif ports:
            self.port_combo.setCurrentIndex(0)
        else:
            self.port_combo.setEditText("")
        message = f"检测到 {len(ports)} 个串口" if ports else "未检测到串口，可手动输入端口名"
        self.statusBar().showMessage(message, 4000)

    def _set_port(self, port: str) -> None:
        if not port:
            return
        index = self.port_combo.findData(port)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)
        else:
            self.port_combo.setEditText(port)

    def _toggle_serial(self) -> None:
        if self._serial_open:
            self.controller.close_serial()
            return
        settings = self._current_serial_settings()
        if not settings.port:
            QMessageBox.warning(self, "串口配置", "请选择或输入串口名称。")
            return
        try:
            self._save_config()
            self.controller.open_serial(settings)
            self.statusBar().showMessage("正在打开串口…", 3000)
        except Exception as error:
            QMessageBox.critical(self, "打开串口失败", str(error))

    def _toggle_tasks(self) -> None:
        if self._task_running:
            if not self.controller.stop_tasks(timeout=5):
                QMessageBox.warning(self, "停止任务", "后台任务仍在退出，请稍后再试。")
            return
        input_directory = self.input_path_edit.text().strip()
        output_directory = self.output_path_edit.text().strip()
        if not input_directory or not output_directory:
            QMessageBox.warning(self, "文件夹配置", "请先选择输入文件夹和输出文件夹。")
            return
        try:
            self._save_config()
            self.controller.start_tasks(
                input_directory,
                output_directory,
                scan_interval_seconds=self.config.scan_interval_seconds,
            )
        except Exception as error:
            QMessageBox.critical(self, "启动任务失败", str(error))
    
    def _reset_all_data(self) -> None:
        if self._task_running:
            QMessageBox.warning(
                self,
                "无法清空",
                "请先手动停止处理任务，然后再执行清空操作。",
            )
            return

        if self._serial_open:
            QMessageBox.warning(
                self,
                "无法清空",
                "请先手动关闭串口，然后再执行清空操作。",
            )
            return

        input_directory = self.input_path_edit.text().strip()
        output_directory = self.output_path_edit.text().strip()

        if not input_directory or not output_directory:
            QMessageBox.warning(
                self,
                "文件夹配置",
                "请先选择输入文件夹和输出文件夹。",
            )
            return

        confirmation = QMessageBox.warning(
            self,
            "确认清空并重新开始",
            (
                "该操作不可恢复，将执行以下操作：\n\n"
                "1. 删除输入文件夹第一层的全部 TXT 文件；\n"
                "2. 删除输出文件夹第一层的全部 TXT 文件；\n"
                "3. 清空全部处理和串口发送记录；\n"
                "4. 清空当前日志和全部历史日志；\n"
                "5. 所有统计数字归零，文件序号重新从 1 开始。\n\n"
                f"输入文件夹：\n{input_directory}\n\n"
                f"输出文件夹：\n{output_directory}\n\n"
                "确定继续吗？"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirmation != QMessageBox.StandardButton.Yes:
            return

        try:
            self._save_config()

            deleted_input, deleted_output = self.controller.reset_all_data(
                input_directory,
                output_directory,
            )

            self.log_view.clear()
            self.controller.refresh_counts()

            message = (
                f"清空完成：删除输入 TXT {deleted_input} 个，"
                f"删除输出 TXT {deleted_output} 个。"
            )
            self.statusBar().showMessage(message, 8000)

            QMessageBox.information(
                self,
                "清空完成",
                (
                    f"输入文件夹删除了 {deleted_input} 个 TXT 文件。\n"
                    f"输出文件夹删除了 {deleted_output} 个 TXT 文件。\n\n"
                    "处理记录、发送记录和运行日志均已清空。\n"
                    "现在可以重新打开串口并启动任务。"
                ),
            )
        except Exception as error:
            QMessageBox.critical(
                self,
                "清空失败",
                (
                    f"清空过程中发生错误：\n{error}\n\n"
                    "请检查文件是否被其他程序占用，"
                    "并确认输入输出文件夹具有删除权限。"
                ),
            )

    def _current_serial_settings(self) -> SerialSettings:
        return SerialSettings(
            port=self.port_combo.currentText().strip(),
            baudrate=int(self.baudrate_combo.currentData()),
            bytesize=int(self.data_bits_combo.currentData()),
            parity=str(self.parity_combo.currentData()),
            stopbits=float(self.stop_bits_combo.currentData()),
        )

    def _browse_directory(self, target: QLineEdit, title: str) -> None:
        initial = target.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, title, initial)
        if selected:
            target.setText(selected)
            self._save_config()

    def _apply_config(self, config: AppConfig) -> None:
        self.input_path_edit.setText(config.input_directory)
        self.output_path_edit.setText(config.output_directory)
        _set_combo_data(self.baudrate_combo, config.serial.baudrate)
        _set_combo_data(self.data_bits_combo, config.serial.bytesize)
        _set_combo_data(self.parity_combo, config.serial.parity)
        _set_combo_data(self.stop_bits_combo, config.serial.stopbits)
        if config.window_geometry:
            try:
                self.restoreGeometry(QByteArray(b64decode(config.window_geometry)))
            except Exception:
                pass

    def _save_config(self) -> None:
        self.config = AppConfig(
            input_directory=self.input_path_edit.text().strip(),
            output_directory=self.output_path_edit.text().strip(),
            scan_interval_seconds=self.config.scan_interval_seconds,
            serial=self._current_serial_settings(),
            window_geometry=b64encode(bytes(self.saveGeometry())).decode("ascii"),
        )
        self.config_manager.save(self.config)

    def _on_task_state_changed(self, running: bool, message: str) -> None:
        self._task_running = running
        self.task_status_label.setText(message)
        self.task_status_label.setProperty("active", running)
        self.task_button.setText("停止任务" if running else "启动任务")
        for widget in self._directory_widgets:
            widget.setEnabled(not running)
        self._refresh_status_style(self.task_status_label)
        self._update_reset_button_state()

    def _on_serial_state_changed(self, opened: bool, message: str) -> None:
        self._serial_open = opened
        self.serial_status_label.setText(message)
        self.serial_status_label.setProperty("active", opened)
        self.serial_button.setText("关闭串口" if opened else "打开串口")
        for widget in self._serial_parameter_widgets:
            widget.setEnabled(not opened)
        self._refresh_status_style(self.serial_status_label)
        self._update_reset_button_state()

    def _update_reset_button_state(self) -> None:
        can_reset = not self._task_running and not self._serial_open
        self.reset_all_button.setEnabled(can_reset)

        if can_reset:
            self.reset_all_button.setToolTip(
                "删除工作目录中的TXT文件并清空全部历史记录"
            )
        else:
            self.reset_all_button.setToolTip(
                "请先停止任务并关闭串口"
            ) 
      
    def _on_counts_changed(self, counts: dict[str, int]) -> None:
        for key, label in self.count_labels.items():
            label.setText(str(counts.get(key, 0)))

    def _append_log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}] [{level}] {message}")
        self.statusBar().showMessage(message, 5000)

    def closeEvent(self, event: QCloseEvent) -> None:
        try:
            self._save_config()
        except Exception as error:
            self._append_log("ERROR", f"保存配置失败：{error}")
        if self.controller.shutdown(timeout=5):
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "后台线程仍在运行",
            "后台线程未能及时停止。是否仍然退出程序？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()

    def _refresh_status_style(self, label: QLabel) -> None:
        label.style().unpolish(label)
        label.style().polish(label)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f4f7fb; color: #172033; font-size: 13px; }
            QLabel#titleLabel { font-size: 24px; font-weight: 700; color: #102a56; }
            QLabel#subtitleLabel { color: #63708a; margin-bottom: 4px; }
            QGroupBox { background: white; border: 1px solid #dce3ef; border-radius: 8px;
                        margin-top: 10px; padding: 12px 10px 10px 10px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #24446f; }
            QLineEdit, QComboBox, QPlainTextEdit { background: white; border: 1px solid #c8d2e1;
                                                   border-radius: 5px; padding: 6px; }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #3478d4; }
            QPushButton { background: #e8eef7; border: 1px solid #c6d2e3; border-radius: 5px;
                          padding: 7px 16px; font-weight: 600; }
            QPushButton:hover { background: #dbe7f7; }
            QPushButton:disabled { color: #9ba6b5; background: #eef1f5; }
            QPushButton#primaryButton { color: white; background: #246bce; border-color: #246bce; min-width: 100px; }
            QPushButton#primaryButton:hover { background: #185bb6; }
            QPushButton#secondaryButton { min-width: 100px; }
            QPushButton#dangerButton {
                color: white;
                background: #c63d3d;
                border-color: #c63d3d;
                margin-top: 8px;
            }
            QPushButton#dangerButton:hover {
                background: #ab2f2f;
            }
            QPushButton#dangerButton:disabled {
                color: #9ba6b5;
                background: #eef1f5;
                border-color: #d6dce5;
            }        
                
            QLabel#statusPill { background: #e8edf4; color: #59677c; border-radius: 10px; padding: 4px 10px; }
            QLabel#statusPill[active="true"] { background: #dff5e8; color: #167344; }
            QFrame#metricCard { background: #f7f9fc; border: 1px solid #e2e7f0; border-radius: 6px; }
            QLabel#metricValue { font-size: 21px; font-weight: 700; color: #245fa8; }
            QLabel#metricTitle { color: #6b7688; font-size: 12px; }
            QStatusBar { background: white; border-top: 1px solid #dce3ef; }
            """
        )


def _set_combo_data(combo: QComboBox, value: Any) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)
