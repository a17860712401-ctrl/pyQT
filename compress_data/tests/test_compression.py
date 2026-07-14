from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from spectrum_compressor.compression import (
    SpectrumFormatError,
    compress_file,
    encode_intensity,
    parse_spectrum_lines,
    select_indexes,
)
from spectrum_compressor.models import SpectrumPoint


class CompressionTests(unittest.TestCase):
    def test_parses_supported_delimiters_and_skips_header(self) -> None:
        points, skipped = parse_spectrum_lines(
            [
                "波数,强度\n",
                "200,1.5\n",
                "800，-2.5\n",
                "1400 3.25\n",
                "\n",
            ]
        )

        self.assertEqual([point.wavenumber for point in points], [200.0, 800.0, 1400.0])
        self.assertEqual([point.intensity for point in points], [Decimal("1.5"), Decimal("-2.5"), Decimal("3.25")])
        self.assertEqual(skipped, [1])

    def test_rejects_file_without_valid_points(self) -> None:
        with self.assertRaises(SpectrumFormatError):
            parse_spectrum_lines(["波数,强度\n", "invalid\n"])

    def test_skips_non_finite_wavenumbers(self) -> None:
        points, skipped = parse_spectrum_lines(["nan,1\n", "inf,2\n", "200,3\n"])

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].wavenumber, 200.0)
        self.assertEqual(skipped, [1, 2])

    def test_selects_anchor_neighborhood_downsample_and_endpoints(self) -> None:
        points = [SpectrumPoint(float(index), Decimal(index)) for index in range(501)]

        indexes = select_indexes(points, anchors=(200.0,), radius=10, stride=30)

        self.assertIn(0, indexes)
        self.assertIn(500, indexes)
        self.assertTrue(set(range(190, 211)).issubset(indexes))
        self.assertIn(30, indexes)
        self.assertEqual(indexes, sorted(set(indexes)))

    def test_ignores_anchor_outside_wavenumber_range(self) -> None:
        points = [SpectrumPoint(float(index), Decimal(index)) for index in range(100, 151)]

        indexes = select_indexes(points, anchors=(200.0,), radius=10, stride=30)

        self.assertEqual(indexes, [0, 30, 50])

    def test_rounds_and_encodes_minimal_unsigned_whole_bytes(self) -> None:
        cases = {
            "0": "00",
            "1.5": "02",
            "10": "0a",
            "255": "ff",
            "256": "0100",
            "300": "012c",
            "65536": "010000",
            str(2**32 - 1): "ffffffff",
        }
        for raw_value, expected in cases.items():
            with self.subTest(raw_value=raw_value):
                self.assertEqual(encode_intensity(Decimal(raw_value)), expected)

    def test_rejects_negative_or_out_of_range_intensity(self) -> None:
        for value in (Decimal("-0.1"), Decimal("-1"), Decimal(2**32)):
            with self.subTest(value=value):
                with self.assertRaises(OverflowError):
                    encode_intensity(value)

    def test_compress_file_uses_same_name_and_writes_hex_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "input" / "sample.txt"
            output_directory = root / "output"
            source.parent.mkdir()
            source.write_text("0,1.5\n30,2.5\n60,300\n", encoding="utf-8")

            result = compress_file(source, output_directory, anchors=(), stride=30)

            self.assertEqual(result.output_path, output_directory / "sample.txt")
            self.assertEqual(result.kept_points, 2)
            self.assertEqual(result.output_path.read_text(encoding="utf-8"), "02\n012c\n")


if __name__ == "__main__":
    unittest.main()
