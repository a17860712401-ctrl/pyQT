import tempfile
import unittest
from pathlib import Path

from spectrum_restore.restoration import RestoreError, restore_batch, restore_file


class RestorationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output = self.root / "Restored"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_decodes_hex_maps_real_points_and_writes_decimal(self) -> None:
        template = self.write("template.txt", "0.000\n1.000\n2.000\n")
        compressed = self.write("sample.txt", "0a\n14\n012c\n")

        result = restore_file(
            template, compressed, self.output, anchors=(), radius=9, stride=1
        )

        self.assertEqual(result.output_path.name, "sample_restored.txt")
        self.assertEqual(
            result.output_path.read_text(encoding="utf-8"),
            "0.000,10\n1.000,20\n2.000,300\n",
        )
        self.assertNotIn("012c", result.output_path.read_text(encoding="utf-8"))

    def test_interpolates_missing_points_and_preserves_real_points(self) -> None:
        template = self.write("template.txt", "0\n1\n2\n3\n4\n")
        compressed = self.write("sample.txt", "0a\n1e\n")

        result = restore_file(template, compressed, self.output, anchors=(), stride=4)
        lines = result.output_path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(lines, ["0,10", "1,15", "2,20", "3,25", "4,30"])
        self.assertEqual(result.method, "线性插值")

    def test_preserves_original_template_order(self) -> None:
        template = self.write("template.txt", "2.000\n1.000\n0.000\n")
        compressed = self.write("sample.txt", "0a\n14\n1e\n")

        result = restore_file(template, compressed, self.output, anchors=(), stride=1)

        self.assertEqual(
            result.output_path.read_text(encoding="utf-8").splitlines(),
            ["2.000,10", "1.000,20", "0.000,30"],
        )

    def test_rejects_compressed_count_mismatch(self) -> None:
        template = self.write("template.txt", "0\n1\n2\n")
        compressed = self.write("short.txt", "0a\n14\n")

        with self.assertRaisesRegex(RestoreError, "数量"):
            restore_file(template, compressed, self.output, anchors=(), stride=1)

    def test_batch_isolates_file_failures(self) -> None:
        template = self.write("template.txt", "0\n1\n2\n")
        valid = self.write("valid.txt", "0a\n14\n1e\n")
        invalid = self.write("invalid.txt", "not-hex\n")

        successes, failures = restore_batch(
            template,
            (valid, invalid),
            self.output,
            anchors=(),
            stride=1,
        )

        self.assertEqual(tuple(item.source_path.name for item in successes), ("valid.txt",))
        self.assertEqual(tuple(item.source_path.name for item in failures), ("invalid.txt",))
        self.assertTrue((self.output / "valid_restored.txt").is_file())


if __name__ == "__main__":
    unittest.main()
