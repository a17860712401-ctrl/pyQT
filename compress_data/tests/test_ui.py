from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from spectrum_compressor.config import AppConfig, ConfigManager
from spectrum_compressor.models import SerialSettings
from spectrum_compressor.serial_comm import SerialPortInfo
from spectrum_compressor.ui.main_window import MainWindow


class FakeController(QObject):
    log_message = pyqtSignal(str, str)
    counts_changed = pyqtSignal(dict)
    task_state_changed = pyqtSignal(bool, str)
    serial_state_changed = pyqtSignal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self.is_running = False
        self.is_serial_open = False
        self.opened_with: SerialSettings | None = None
        self.shutdown_called = False

    def available_ports(self) -> list[SerialPortInfo]:
        return [SerialPortInfo("COM7", "测试串口")]

    def refresh_counts(self) -> dict[str, int]:
        counts = {"discovered": 0, "compressed": 0, "failed": 0, "pending_send": 0, "sent": 0, "failed_send": 0}
        self.counts_changed.emit(counts)
        return counts

    def open_serial(self, settings: SerialSettings) -> None:
        self.opened_with = settings

    def close_serial(self) -> None:
        self.is_serial_open = False

    def start_tasks(self, *_args, **_kwargs) -> None:
        self.is_running = True

    def stop_tasks(self, *, timeout: float = 5.0) -> bool:
        self.is_running = False
        return True

    def shutdown(self, *, timeout: float = 5.0) -> bool:
        self.shutdown_called = True
        return True


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temporary_directory.name) / "config.json"
        self.config_manager = ConfigManager(self.config_path)
        self.config_manager.save(
            AppConfig(
                input_directory="C:/input",
                output_directory="C:/output",
                serial=SerialSettings(port="COM7", baudrate=9600, bytesize=7, parity="E", stopbits=2.0),
            )
        )
        self.controller = FakeController()
        self.window = MainWindow(self.controller, self.config_manager)

    def tearDown(self) -> None:
        self.window.deleteLater()
        QApplication.processEvents()
        self.temporary_directory.cleanup()

    def test_window_contains_required_controls_and_restores_config(self) -> None:
        self.assertEqual(self.window.input_path_edit.text(), "C:/input")
        self.assertEqual(self.window.output_path_edit.text(), "C:/output")
        self.assertEqual(self.window.port_combo.currentText(), "COM7")
        self.assertEqual(self.window.baudrate_combo.currentData(), 9600)
        self.assertEqual(self.window.data_bits_combo.currentData(), 7)
        self.assertEqual(self.window.parity_combo.currentData(), "E")
        self.assertEqual(self.window.stop_bits_combo.currentData(), 2.0)
        self.assertIsNotNone(self.window.serial_button)
        self.assertIsNotNone(self.window.task_button)
        self.assertIsNotNone(self.window.log_view)

    def test_serial_state_disables_configuration_controls(self) -> None:
        self.window._on_serial_state_changed(True, "已打开 COM7")

        self.assertFalse(self.window.port_combo.isEnabled())
        self.assertFalse(self.window.baudrate_combo.isEnabled())
        self.assertEqual(self.window.serial_button.text(), "关闭串口")

        self.window._on_serial_state_changed(False, "串口已关闭")
        self.assertTrue(self.window.port_combo.isEnabled())
        self.assertEqual(self.window.serial_button.text(), "打开串口")

    def test_task_state_disables_directory_controls_and_updates_status(self) -> None:
        self.window._on_task_state_changed(True, "任务运行中")

        self.assertFalse(self.window.input_path_edit.isEnabled())
        self.assertFalse(self.window.output_path_edit.isEnabled())
        self.assertEqual(self.window.task_button.text(), "停止任务")
        self.assertEqual(self.window.task_status_label.text(), "任务运行中")

    def test_counts_and_log_are_rendered(self) -> None:
        self.window._on_counts_changed(
            {"discovered": 12, "compressed": 2, "failed": 1, "pending_send": 1, "sent": 1, "failed_send": 0}
        )
        self.window._append_log("INFO", "测试日志")

        self.assertEqual(self.window.count_labels["discovered"].text(), "12")
        self.assertEqual(self.window.count_labels["compressed"].text(), "2")
        self.assertIn("测试日志", self.window.log_view.toPlainText())
        self.assertEqual(self.window.log_view.document().maximumBlockCount(), 2000)


if __name__ == "__main__":
    unittest.main()
