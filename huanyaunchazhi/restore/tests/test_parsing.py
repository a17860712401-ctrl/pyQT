import math
import tempfile
import unittest
from pathlib import Path

from spectrum_restore.parsing import (
    SpectrumFormatError,
    parse_compressed,
    parse_template,
)


class ParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_template_preserves_first_column_text(self) -> None:
        path = self.write("axis.txt", "400.000,9\n401.5 10\n402，11\n")

        axis = parse_template(path)

        self.assertEqual(axis.raw_values, ("400.000", "401.5", "402"))
        self.assertEqual(axis.values, (400.0, 401.5, 402.0))

    def test_template_ignores_second_and_later_columns(self) -> None:
        path = self.write("axis.txt", "1,not-used,anything\n2,also-ignored\n")

        axis = parse_template(path)

        self.assertEqual(axis.values, (1.0, 2.0))

    def test_template_rejects_headers_nonfinite_and_duplicates(self) -> None:
        cases = (
            ("波数,强度\n", "第 1 行"),
            (f"1\n{math.inf}\n", "有限"),
            ("1\n1.0\n", "重复"),
        )
        for content, message in cases:
            with self.subTest(content=content):
                path = self.write("axis.txt", content)
                with self.assertRaisesRegex(SpectrumFormatError, message):
                    parse_template(path)

    def test_template_rejects_empty_file(self) -> None:
        path = self.write("axis.txt", "\n\n")

        with self.assertRaisesRegex(SpectrumFormatError, "为空"):
            parse_template(path)

    def test_template_rejects_non_monotonic_axis(self) -> None:
        path = self.write("axis.txt", "0\n2\n1\n")

        with self.assertRaisesRegex(SpectrumFormatError, "递增或严格递减"):
            parse_template(path)

    def test_template_accepts_strictly_descending_axis(self) -> None:
        path = self.write("axis.txt", "2.000\n1.000\n0.000\n")

        axis = parse_template(path)

        self.assertEqual(axis.values, (2.0, 1.0, 0.0))

    def test_compressed_converts_hexadecimal_to_decimal(self) -> None:
        path = self.write("compressed.txt", "0a\nFF\n012c\n00010000\n")

        values = parse_compressed(path)

        self.assertEqual(values, (10, 255, 300, 65536))

    def test_compressed_rejects_invalid_lines(self) -> None:
        for token in ("1", "000", "00000", "gg", "0a ff", "0x0a", "123456789"):
            with self.subTest(token=token):
                path = self.write("compressed.txt", token + "\n")
                with self.assertRaisesRegex(SpectrumFormatError, "十六进制"):
                    parse_compressed(path)

    def test_compressed_rejects_empty_file(self) -> None:
        path = self.write("compressed.txt", "\n")

        with self.assertRaisesRegex(SpectrumFormatError, "为空"):
            parse_compressed(path)

    def test_rejects_non_utf8_input_with_chinese_message(self) -> None:
        path = self.root / "bad-encoding.txt"
        path.write_bytes(b"\xff\xfe\xff")

        with self.assertRaisesRegex(SpectrumFormatError, "UTF-8"):
            parse_template(path)


if __name__ == "__main__":
    unittest.main()
