from __future__ import annotations

import unittest

from app.battle_speed import modified_agility


class BattleSpeedTest(unittest.TestCase):
    def test_applies_zero_quarter_step_speed_formula(self) -> None:
        self.assertEqual(modified_agility(20, -1), 15)
        self.assertEqual(modified_agility(20, 0), 20)
        self.assertEqual(modified_agility(20, 1), 25)
        self.assertEqual(modified_agility(20, 2), 30)

    def test_effective_agility_has_a_minimum_of_one(self) -> None:
        self.assertEqual(modified_agility(0, 0), 1)
        self.assertEqual(modified_agility(1, -1), 1)

    def test_rejects_invalid_values(self) -> None:
        for base_agility in (True, -1, 1.5):
            with self.subTest(base_agility=base_agility), self.assertRaises(
                (TypeError, ValueError)
            ):
                modified_agility(base_agility, 0)
        for speed_modifier in (True, -2, 3, 0.5):
            with self.subTest(speed_modifier=speed_modifier), self.assertRaises(
                (TypeError, ValueError)
            ):
                modified_agility(20, speed_modifier)


if __name__ == "__main__":
    unittest.main()
