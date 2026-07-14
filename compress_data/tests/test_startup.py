from __future__ import annotations

import builtins
import logging
import os
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from spectrum_compressor.logging_setup import close_application_logging, configure_logging
from spectrum_compressor.main import build_application


class StartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QApplication.instance() or QApplication([])

    def test_configure_logging_writes_rotating_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "logs" / "application.log"
            logger = configure_logging(log_path)

            logger.info("startup-test-message")
            for handler in logger.handlers:
                handler.flush()

            self.assertIn("startup-test-message", log_path.read_text(encoding="utf-8"))
            close_application_logging()

    def test_run_app_adds_src_directory_before_importing_package(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        source_directory = (project_root / "src").resolve()
        launcher_path = project_root / "run_app.py"
        original_sys_path = sys.path.copy()
        real_import = builtins.__import__

        def checking_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "spectrum_compressor.main":
                resolved_paths = {Path(entry or os.curdir).resolve() for entry in sys.path}
                self.assertIn(source_directory, resolved_paths)
                return SimpleNamespace(main=lambda: 0)
            return real_import(name, globals, locals, fromlist, level)

        try:
            sys.path[:] = [
                entry
                for entry in sys.path
                if Path(entry or os.curdir).resolve() != source_directory
            ]
            with patch("builtins.__import__", side_effect=checking_import):
                runpy.run_path(str(launcher_path), run_name="run_app_path_test")
        finally:
            sys.path[:] = original_sys_path

    def test_build_application_creates_complete_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            application, controller, window = build_application(
                config_path=root / "config.json",
                state_path=root / "state.sqlite3",
                arguments=[],
            )

            self.assertIs(application, QApplication.instance())
            self.assertEqual(window.windowTitle(), "光谱压缩串口上位机")
            self.assertIsNotNone(window.input_path_edit)
            if sys.platform == "win32":
                self.assertEqual(application.font().family(), "Microsoft YaHei UI")
            controller.shutdown(timeout=2)
            window.deleteLater()
            QApplication.processEvents()


if __name__ == "__main__":
    unittest.main()
