from __future__ import annotations

import unittest

from tools._bootstrap import APP_ROOT  # noqa: F401

from battle_surprise import resolve_surprise_roll, surprise_threshold


class SurpriseThresholdTest(unittest.TestCase):
    def test_minimum_rate_is_one_of_thirty_two(self) -> None:
        self.assertEqual(surprise_threshold((20, 20), (10, 10)), 1)
        self.assertTrue(resolve_surprise_roll((20,), (10,), 0).triggered)
        self.assertFalse(resolve_surprise_roll((20,), (10,), 1).triggered)

    def test_disadvantage_raises_threshold(self) -> None:
        self.assertEqual(surprise_threshold((8, 8), (12, 12)), 3)
        self.assertTrue(resolve_surprise_roll((8, 8), (12, 12), 2).triggered)
        self.assertFalse(resolve_surprise_roll((8, 8), (12, 12), 3).triggered)

    def test_fractional_average_uses_exact_floor_division(self) -> None:
        # D = 9.5 - 12 = -2.5, so (-D) // 2 + 1 = 2.
        self.assertEqual(surprise_threshold((9, 10), (12,)), 2)

    def test_rejects_invalid_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            surprise_threshold((), (1,))
        with self.assertRaisesRegex(ValueError, "non-negative integers"):
            surprise_threshold((True,), (1,))
        with self.assertRaisesRegex(ValueError, "from 0 to 31"):
            resolve_surprise_roll((1,), (1,), 32)


if __name__ == "__main__":
    unittest.main()
