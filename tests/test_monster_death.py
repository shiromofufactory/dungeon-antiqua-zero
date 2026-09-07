from __future__ import annotations

import unittest

from app.rendering.monster_death import (
    MONSTER_DEATH_BRIGHT_COLOR,
    MONSTER_DEATH_BRIGHTEN_FRAME_COUNT,
    MONSTER_DEATH_DISSOLVE_FRAME_COUNT,
    MONSTER_DEATH_PALETTE_BASE_RATE,
    MONSTER_DEATH_TINT_COLOR,
    MONSTER_DEATH_TINT_FRAME_COUNT,
    MonsterDeathAnimation,
    MonsterDeathPhase,
)


class MonsterDeathAnimationTest(unittest.TestCase):
    def test_visual_parameters_match_battle_specification(self) -> None:
        self.assertGreaterEqual(MONSTER_DEATH_PALETTE_BASE_RATE, 0.0)
        self.assertLessEqual(MONSTER_DEATH_PALETTE_BASE_RATE, 1.0)
        self.assertEqual(MONSTER_DEATH_DISSOLVE_FRAME_COUNT, 16)

    def test_animation_runs_tint_brighten_dissolve_in_order(self) -> None:
        animation = MonsterDeathAnimation()
        self.assertIs(animation.phase, MonsterDeathPhase.TINT)
        self.assertEqual(animation.palette_target_color, MONSTER_DEATH_TINT_COLOR)
        self.assertEqual(animation.opacity, 1.0)

        for _frame in range(MONSTER_DEATH_TINT_FRAME_COUNT):
            animation.update()
        self.assertIs(animation.phase, MonsterDeathPhase.BRIGHTEN)
        self.assertNotEqual(
            animation.palette_target_color,
            MONSTER_DEATH_TINT_COLOR,
        )

        for _frame in range(MONSTER_DEATH_BRIGHTEN_FRAME_COUNT):
            animation.update()
        self.assertIs(animation.phase, MonsterDeathPhase.DISSOLVE)
        self.assertEqual(animation.palette_target_color, MONSTER_DEATH_BRIGHT_COLOR)
        self.assertEqual(animation.opacity, 1.0)

        for _frame in range(MONSTER_DEATH_DISSOLVE_FRAME_COUNT // 2):
            animation.update()
        self.assertEqual(animation.opacity, 0.5)

        for _frame in range(MONSTER_DEATH_DISSOLVE_FRAME_COUNT // 2):
            animation.update()
        self.assertIs(animation.phase, MonsterDeathPhase.FINISHED)
        self.assertEqual(animation.opacity, 0.0)

    def test_brighten_color_moves_between_tint_and_near_white(self) -> None:
        animation = MonsterDeathAnimation()
        for _frame in range(MONSTER_DEATH_TINT_FRAME_COUNT):
            animation.update()
        for _frame in range(MONSTER_DEATH_BRIGHTEN_FRAME_COUNT // 2):
            animation.update()

        color = animation.palette_target_color
        self.assertNotEqual(color, MONSTER_DEATH_TINT_COLOR)
        self.assertNotEqual(color, MONSTER_DEATH_BRIGHT_COLOR)


if __name__ == "__main__":
    unittest.main()
