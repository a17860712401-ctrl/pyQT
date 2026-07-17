import unittest

from spectrum_restore.compression_contract import select_indexes


class CompressionContractTests(unittest.TestCase):
    def test_keeps_stride_endpoints_and_anchor_neighborhood(self) -> None:
        axis = tuple(float(value) for value in range(950, 1051))

        indexes = select_indexes(axis, anchors=(981.0,), radius=2, stride=35)

        self.assertEqual(indexes, (0, 29, 30, 31, 32, 33, 35, 70, 100))

    def test_uses_smaller_index_for_equal_anchor_distance(self) -> None:
        axis = (970.0, 980.0, 982.0, 990.0)

        indexes = select_indexes(axis, anchors=(981.0,), radius=0, stride=99)

        self.assertEqual(indexes, (0, 1, 3))

    def test_ignores_anchor_outside_axis_range(self) -> None:
        indexes = select_indexes((100.0, 200.0, 300.0), anchors=(981.0,), stride=2)

        self.assertEqual(indexes, (0, 2))

    def test_rejects_invalid_parameters(self) -> None:
        with self.assertRaisesRegex(ValueError, "半径"):
            select_indexes((1.0,), radius=-1)
        with self.assertRaisesRegex(ValueError, "步长"):
            select_indexes((1.0,), stride=0)


if __name__ == "__main__":
    unittest.main()
