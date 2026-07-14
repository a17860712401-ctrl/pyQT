from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from spectrum_compressor.config import AppConfig, ConfigManager
from spectrum_compressor.models import SerialSettings


class ConfigManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "config.json"
        self.manager = ConfigManager(self.path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_missing_file_returns_defaults(self) -> None:
        self.assertEqual(self.manager.load(), AppConfig())

    def test_invalid_json_returns_defaults(self) -> None:
        self.path.write_text("not-json", encoding="utf-8")

        config = self.manager.load()

        self.assertEqual(config.serial.baudrate, 115200)
        self.assertEqual(config.input_directory, "")

    def test_round_trips_user_settings(self) -> None:
        config = AppConfig(
            input_directory="C:/spectra/in",
            output_directory="C:/spectra/out",
            scan_interval_seconds=2.5,
            serial=SerialSettings(port="COM3", baudrate=9600, bytesize=7, parity="E", stopbits=2.0),
            window_geometry="encoded-geometry",
        )

        self.manager.save(config)

        self.assertEqual(self.manager.load(), config)
        parsed = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(parsed["serial"]["port"], "COM3")

    def test_invalid_field_values_fall_back_individually(self) -> None:
        self.path.write_text(
            json.dumps(
                {
                    "input_directory": 123,
                    "output_directory": "out",
                    "scan_interval_seconds": -1,
                    "serial": {"port": "COM4", "baudrate": "fast", "parity": "X"},
                }
            ),
            encoding="utf-8",
        )

        config = self.manager.load()

        self.assertEqual(config.input_directory, "")
        self.assertEqual(config.output_directory, "out")
        self.assertEqual(config.scan_interval_seconds, 1.0)
        self.assertEqual(config.serial.port, "COM4")
        self.assertEqual(config.serial.baudrate, 115200)
        self.assertEqual(config.serial.parity, "N")

    def test_unhashable_json_values_do_not_escape_validation(self) -> None:
        self.path.write_text(
            json.dumps({"serial": {"bytesize": [8], "parity": {"value": "E"}}}),
            encoding="utf-8",
        )

        config = self.manager.load()

        self.assertEqual(config.serial.bytesize, 8)
        self.assertEqual(config.serial.parity, "N")


if __name__ == "__main__":
    unittest.main()
