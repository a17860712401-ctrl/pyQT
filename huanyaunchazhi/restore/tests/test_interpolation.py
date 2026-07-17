import unittest
from unittest.mock import patch

from spectrum_restore.interpolation import (
    InterpolationError,
    interpolate_with_fallback,
    pchip_interpolate,
)


class InterpolationTests(unittest.TestCase):
    def test_pchip_passes_known_points_and_preserves_monotonicity(self) -> None:
        values = pchip_interpolate(
            (0.0, 1.0, 2.0),
            (0.0, 1.0, 1.5),
            (0.0, 0.5, 1.0, 1.5, 2.0),
        )

        self.assertEqual(values[0], 0.0)
        self.assertEqual(values[2], 1.0)
        self.assertEqual(values[4], 1.5)
        self.assertEqual(values, tuple(sorted(values)))

    def test_pchip_does_not_overshoot_peak(self) -> None:
        values = pchip_interpolate(
            (0.0, 1.0, 2.0),
            (0.0, 10.0, 0.0),
            (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0),
        )

        self.assertTrue(all(0.0 <= value <= 10.0 for value in values))
        self.assertEqual(values[4], 10.0)

    def test_query_order_is_preserved(self) -> None:
        values = pchip_interpolate(
            (0.0, 1.0, 2.0),
            (0.0, 1.0, 2.0),
            (2.0, 0.0, 1.0),
        )

        self.assertEqual(values, (2.0, 0.0, 1.0))

    def test_two_points_use_linear_interpolation(self) -> None:
        values, method, warnings = interpolate_with_fallback(
            (0.0, 2.0), (10.0, 20.0), (0.0, 1.0, 2.0)
        )

        self.assertEqual(values, (10.0, 15.0, 20.0))
        self.assertEqual(method, "线性插值")
        self.assertEqual(warnings, ())

    def test_pchip_failure_uses_linear_interpolation(self) -> None:
        with patch(
            "spectrum_restore.interpolation.pchip_interpolate",
            side_effect=ArithmeticError("计算错误"),
        ):
            values, method, warnings = interpolate_with_fallback(
                (0.0, 1.0, 2.0), (0.0, 1.0, 2.0), (0.5, 1.5)
            )

        self.assertEqual(values, (0.5, 1.5))
        self.assertEqual(method, "线性插值")
        self.assertIn("PCHIP 失败", warnings[0])

    def test_rejects_extrapolation(self) -> None:
        with self.assertRaisesRegex(InterpolationError, "范围"):
            pchip_interpolate((0.0, 1.0, 2.0), (1.0, 2.0, 3.0), (-0.1,))


if __name__ == "__main__":
    unittest.main()
