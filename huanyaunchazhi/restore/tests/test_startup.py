import unittest

from PyQt6.QtWidgets import QApplication


class StartupTests(unittest.TestCase):
    def test_package_exposes_version(self) -> None:
        import spectrum_restore

        self.assertEqual(spectrum_restore.__version__, "1.0.0")

    def test_build_application_creates_main_window(self) -> None:
        from spectrum_restore.main import build_application

        app, window = build_application([])
        try:
            self.assertIsInstance(app, QApplication)
            self.assertEqual(window.windowTitle(), "光谱还原")
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
