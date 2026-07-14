from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from spectrum_compressor.storage import StateStore


class StateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "state.sqlite3"
        self.store = StateStore(self.database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_sequences_select_first_file_of_each_ten(self) -> None:
        records = [self.store.register_input(f"input/{index}.txt", index, index) for index in range(11)]

        self.assertEqual(records[0].sequence, 1)
        self.assertTrue(records[0].selected)
        self.assertFalse(records[1].selected)
        self.assertEqual(records[10].sequence, 11)
        self.assertTrue(records[10].selected)

    def test_duplicate_input_keeps_original_sequence_across_restart(self) -> None:
        original = self.store.register_input("input/a.txt", 10, 100)
        reopened = StateStore(self.database_path)

        duplicate = reopened.register_input("input/a.txt", 99, 999)

        self.assertTrue(original.newly_registered)
        self.assertFalse(duplicate.newly_registered)
        self.assertEqual(duplicate.sequence, original.sequence)
        self.assertEqual(reopened.counts()["discovered"], 1)

    def test_tracks_compression_and_output_queue(self) -> None:
        record = self.store.register_input("input/a.txt", 10, 100)
        self.store.mark_input_compressed(record.path, "output/a.txt")
        output = self.store.register_output("output/a.txt")

        pending = self.store.next_pending_output(now=0)

        self.assertEqual(pending.id, output.id)
        self.assertEqual(self.store.counts()["compressed"], 1)
        self.assertEqual(self.store.counts()["pending_send"], 1)

    def test_retry_is_delayed_and_attempt_count_persists(self) -> None:
        output = self.store.register_output("output/a.txt")

        self.store.mark_output_retry(output.id, "port error", next_attempt_at=10)

        self.assertIsNone(self.store.next_pending_output(now=9))
        retry = self.store.next_pending_output(now=10)
        self.assertEqual(retry.attempts, 1)
        self.assertEqual(retry.last_error, "port error")

    def test_delayed_retry_blocks_later_files_to_preserve_queue_order(self) -> None:
        first = self.store.register_output("output/first.txt")
        self.store.register_output("output/second.txt")
        self.store.mark_output_retry(first.id, "port error", next_attempt_at=10)

        self.assertIsNone(self.store.next_pending_output(now=9))
        self.assertEqual(self.store.next_pending_output(now=10).id, first.id)

    def test_marking_output_sent_updates_counts(self) -> None:
        output = self.store.register_output("output/a.txt")

        self.store.mark_output_sent(output.id, sent_at=20)

        counts = self.store.counts()
        self.assertEqual(counts["pending_send"], 0)
        self.assertEqual(counts["sent"], 1)


if __name__ == "__main__":
    unittest.main()
