import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from spectrum_restore.ui.main_window import MainWindow


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()
        self.temporary.cleanup()

    def test_initial_state_requires_all_inputs(self) -> None:
        self.assertEqual(self.window.windowTitle(), "光谱还原")
        self.assertFalse(self.window.restore_button.isEnabled())
        self.assertEqual(self.window.progress_bar.value(), 0)
        self.assertTrue(self.window.template_path_edit.isReadOnly())
        self.assertTrue(self.window.output_path_edit.isReadOnly())

    def test_inputs_enable_restore_button(self) -> None:
        self.window.set_template_path(self.root / "template.txt")
        self.window.set_compressed_paths((self.root / "sample.txt",))

        self.assertEqual(
            self.window.output_directory,
            self.root / "Restored",
        )
        self.assertTrue(self.window.restore_button.isEnabled())

    def test_clear_compressed_files_disables_restore(self) -> None:
        self.window.set_template_path(self.root / "template.txt")
        self.window.set_compressed_paths((self.root / "a.txt", self.root / "b.txt"))

        self.window.clear_compressed_files()

        self.assertEqual(self.window.compressed_paths, ())
        self.assertEqual(self.window.file_list.count(), 0)
        self.assertFalse(self.window.restore_button.isEnabled())

    def test_running_state_locks_and_restores_inputs(self) -> None:
        self.window.set_template_path(self.root / "template.txt")
        self.window.set_compressed_paths((self.root / "sample.txt",))

        self.window.set_running(True)
        self.assertFalse(self.window.template_button.isEnabled())
        self.assertFalse(self.window.compressed_button.isEnabled())
        self.assertFalse(self.window.output_button.isEnabled())

        self.window.set_running(False)
        self.assertTrue(self.window.template_button.isEnabled())
        self.assertTrue(self.window.compressed_button.isEnabled())
        self.assertTrue(self.window.output_button.isEnabled())
        self.assertTrue(self.window.restore_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
