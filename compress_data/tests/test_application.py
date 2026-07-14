from __future__ import annotations

import tempfile
import time
import unittest
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from spectrum_compressor.application import ApplicationController
from spectrum_compressor.storage import StateStore


class ApplicationControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.input_directory = self.root / "input"
        self.output_directory = self.root / "output"
        self.input_directory.mkdir()
        self.store = StateStore(self.root / "state.sqlite3")
        self.controller = ApplicationController(self.store)

    def tearDown(self) -> None:
        self.controller.shutdown(timeout=2)
        self.temporary_directory.cleanup()

    def test_start_and_stop_are_idempotent(self) -> None:
        self.controller.start_tasks(self.input_directory, self.output_directory, scan_interval_seconds=0.02)
        first_thread = self.controller.processing_thread
        self.controller.start_tasks(self.input_directory, self.output_directory, scan_interval_seconds=0.02)

        self.assertTrue(self.controller.is_running)
        self.assertIs(self.controller.processing_thread, first_thread)

        self.controller.stop_tasks(timeout=2)
        self.controller.stop_tasks(timeout=2)

        self.assertFalse(self.controller.is_running)

    def test_rejects_missing_or_identical_directories(self) -> None:
        with self.assertRaises(ValueError):
            self.controller.start_tasks(self.root / "missing", self.output_directory)
        with self.assertRaises(ValueError):
            self.controller.start_tasks(self.input_directory, self.input_directory)

    def test_emits_task_state_and_counts(self) -> None:
        states: list[bool] = []
        counts: list[dict[str, int]] = []
        self.controller.task_state_changed.connect(lambda running, _message: states.append(running))
        self.controller.counts_changed.connect(counts.append)

        self.controller.start_tasks(self.input_directory, self.output_directory, scan_interval_seconds=0.02)
        time.sleep(0.06)
        QApplication.processEvents()
        self.controller.stop_tasks(timeout=2)
        QApplication.processEvents()

        self.assertIn(True, states)
        self.assertEqual(states[-1], False)
        self.assertTrue(counts)
        self.assertIn("discovered", counts[-1])


if __name__ == "__main__":
    unittest.main()
