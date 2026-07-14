from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from spectrum_compressor.models import SerialSettings
from spectrum_compressor.serial_comm import HexPayloadError, SerialWorker, load_hex_payload
from spectrum_compressor.storage import StateStore


class FakeSerial:
    def __init__(self, *, failures: int = 0) -> None:
        self.failures = failures
        self.writes: list[bytes] = []
        self.flush_count = 0
        self.is_open = True

    def write(self, payload: bytes) -> int:
        if self.failures:
            self.failures -= 1
            raise OSError("simulated serial failure")
        self.writes.append(payload)
        return len(payload)

    def flush(self) -> None:
        self.flush_count += 1

    def close(self) -> None:
        self.is_open = False


class SerialCommunicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.store = StateStore(self.root / "state.sqlite3")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _worker(self, fake: FakeSerial) -> SerialWorker:
        worker = SerialWorker(self.store, serial_factory=lambda **_kwargs: fake)
        worker.open_connection(SerialSettings(port="COM_TEST"))
        return worker

    def _queue(self, name: str, content: str = "0a\n012c\n010000\nffffffff\n") -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        self.store.register_output(path)
        return path

    def test_load_payload_decodes_raw_bytes(self) -> None:
        path = self._queue("sample.txt")

        self.assertEqual(
            load_hex_payload(path),
            b"\x0a\x01\x2c\x01\x00\x00\xff\xff\xff\xff",
        )

    def test_load_payload_rejects_invalid_line_width_or_characters(self) -> None:
        for content in ("1\n", "123\n", "0000000000\n", "gg\n"):
            with self.subTest(content=content):
                path = self.root / "bad.txt"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(HexPayloadError):
                    load_hex_payload(path)

    def test_successful_send_marks_file_sent(self) -> None:
        fake = FakeSerial()
        worker = self._worker(fake)
        self._queue("sample.txt")

        worker.send_next_once(now=100, monotonic_now=10)

        self.assertEqual(
            fake.writes,
            [b"\x0a\x01\x2c\x01\x00\x00\xff\xff\xff\xff"],
        )
        self.assertEqual(fake.flush_count, 1)
        self.assertEqual(self.store.counts()["sent"], 1)

    def test_send_failure_is_retried_without_losing_queue_order(self) -> None:
        fake = FakeSerial(failures=1)
        worker = self._worker(fake)
        first_path = self._queue("first.txt")
        self._queue("second.txt", "00000002\n")

        delay = worker.send_next_once(now=100, monotonic_now=10)

        self.assertEqual(delay, 1.0)
        first = self.store.next_pending_output(now=101)
        self.assertEqual(Path(first.path), first_path.resolve())
        self.assertEqual(first.attempts, 1)

    def test_files_start_at_least_one_second_apart(self) -> None:
        fake = FakeSerial()
        worker = self._worker(fake)
        self._queue("first.txt", "00000001\n")
        self._queue("second.txt", "00000002\n")
        worker.send_next_once(now=100, monotonic_now=10)

        delay = worker.send_next_once(now=100.5, monotonic_now=10.5)

        self.assertAlmostEqual(delay, 0.5)
        self.assertEqual(len(fake.writes), 1)
        worker.send_next_once(now=101, monotonic_now=11)
        self.assertEqual(len(fake.writes), 2)

    def test_malformed_file_is_failed_and_does_not_block_queue(self) -> None:
        fake = FakeSerial()
        worker = self._worker(fake)
        self._queue("bad.txt", "bad\n")
        self._queue("good.txt", "00000002\n")

        worker.send_next_once(now=100, monotonic_now=10)
        worker.send_next_once(now=101, monotonic_now=11)

        self.assertEqual(fake.writes, [b"\x00\x00\x00\x02"])
        self.assertEqual(self.store.counts()["failed_send"], 1)

    def test_missing_output_file_becomes_retry_instead_of_escaping_worker(self) -> None:
        fake = FakeSerial()
        worker = self._worker(fake)
        path = self._queue("missing.txt", "00000001\n")
        path.unlink()

        delay = worker.send_next_once(now=100, monotonic_now=10)

        self.assertEqual(delay, 1.0)
        pending = self.store.next_pending_output(now=101)
        self.assertEqual(pending.attempts, 1)
        self.assertIn("No such file", pending.last_error)


if __name__ == "__main__":
    unittest.main()
