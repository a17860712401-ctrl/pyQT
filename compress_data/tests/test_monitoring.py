from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from spectrum_compressor.monitoring import FileStabilityTracker, ProcessingService, scan_txt_files
from spectrum_compressor.storage import StateStore


class CountingStore(StateStore):
    def __init__(self, database_path: Path) -> None:
        super().__init__(database_path)
        self.input_registrations = 0
        self.output_registrations = 0

    def register_input(self, path, size, mtime_ns):
        self.input_registrations += 1
        return super().register_input(path, size, mtime_ns)

    def register_output(self, path):
        self.output_registrations += 1
        return super().register_output(path)


class FileMonitoringTests(unittest.TestCase):
    def test_file_requires_two_unchanged_observations(self) -> None:
        tracker = FileStabilityTracker(required_observations=2)

        self.assertFalse(tracker.observe("a.txt", 10, 100))
        self.assertTrue(tracker.observe("a.txt", 10, 100))
        self.assertFalse(tracker.observe("a.txt", 11, 101))
        self.assertTrue(tracker.observe("a.txt", 11, 101))

    def test_scan_returns_only_txt_files_in_stable_name_order_for_ties(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "B.txt").write_text("0,1\n", encoding="utf-8")
            (root / "a.TXT").write_text("0,1\n", encoding="utf-8")
            (root / "ignore.csv").write_text("0,1\n", encoding="utf-8")
            (root / "folder.txt").mkdir()

            files = scan_txt_files(root, sort_by_time=False)

            self.assertEqual([path.name for path in files], ["a.TXT", "B.txt"])

    def test_service_processes_first_and_eleventh_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_directory = root / "input"
            output_directory = root / "output"
            input_directory.mkdir()
            for index in range(11):
                (input_directory / f"{index:02d}.txt").write_text("0,1.5\n60,2.5\n", encoding="utf-8")
            store = StateStore(root / "state.sqlite3")
            service = ProcessingService(
                input_directory,
                output_directory,
                store,
                threading.Event(),
                stability_observations=2,
            )

            service.scan_once()
            service.scan_once()

            self.assertEqual(sorted(path.name for path in output_directory.glob("*.txt")), ["00.txt", "10.txt"])
            counts = store.counts()
            self.assertEqual(counts["discovered"], 11)
            self.assertEqual(counts["compressed"], 2)
            self.assertEqual(counts["pending_send"], 2)

    def test_bad_selected_file_does_not_block_later_selected_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_directory = root / "input"
            output_directory = root / "output"
            input_directory.mkdir()
            for index in range(11):
                content = "invalid\n" if index == 0 else "0,1\n60,2\n"
                (input_directory / f"{index:02d}.txt").write_text(content, encoding="utf-8")
            store = StateStore(root / "state.sqlite3")
            service = ProcessingService(
                input_directory,
                output_directory,
                store,
                threading.Event(),
                stability_observations=2,
            )

            service.scan_once()
            service.scan_once()

            counts = store.counts()
            self.assertEqual(counts["failed"], 1)
            self.assertEqual(counts["compressed"], 1)
            self.assertTrue((output_directory / "10.txt").exists())

    def test_existing_output_is_registered_after_it_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_directory = root / "input"
            output_directory = root / "output"
            input_directory.mkdir()
            output_directory.mkdir()
            (output_directory / "external.txt").write_text("00000001\n", encoding="utf-8")
            store = StateStore(root / "state.sqlite3")
            service = ProcessingService(
                input_directory,
                output_directory,
                store,
                threading.Event(),
                stability_observations=2,
            )

            service.scan_once()
            self.assertEqual(store.counts()["pending_send"], 0)
            service.scan_once()

            self.assertEqual(store.counts()["pending_send"], 1)

    def test_known_paths_are_not_repeatedly_registered_during_long_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_directory = root / "input"
            output_directory = root / "output"
            input_directory.mkdir()
            output_directory.mkdir()
            (input_directory / "input.txt").write_text("0,1\n60,2\n", encoding="utf-8")
            (output_directory / "external.txt").write_text("00000001\n", encoding="utf-8")
            store = CountingStore(root / "state.sqlite3")
            service = ProcessingService(
                input_directory,
                output_directory,
                store,
                threading.Event(),
                stability_observations=2,
            )

            for _ in range(4):
                service.scan_once()

            self.assertEqual(store.input_registrations, 1)
            self.assertEqual(store.output_registrations, 2)


if __name__ == "__main__":
    unittest.main()
