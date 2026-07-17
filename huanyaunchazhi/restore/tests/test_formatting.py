import unittest

from spectrum_restore.formatting import format_intensity


class FormattingTests(unittest.TestCase):
    def test_formats_decimal_intensities_with_at_most_four_places(self) -> None:
        cases = (
            (300, "300"),
            (1.2, "1.2"),
            (1.23456, "1.2346"),
            (1.2300, "1.23"),
            (0.00004, "0"),
        )

        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(format_intensity(value), expected)


if __name__ == "__main__":
    unittest.main()
