from __future__ import annotations

import unittest

from app.rendering.floating import (
    FLOATING_CHARACTER_CYCLE_FRAMES,
    FLOATING_CHARACTER_FRAME_INTERVAL,
    FLOATING_CHARACTER_FRAMES,
    FLOATING_CYCLE_FRAMES,
    FLOATING_OFFSETS,
    FLOATING_PHASE_FRAMES,
    floating_character_frame,
    floating_offset,
    floating_phase_offset,
)


class FloatingAnimationTest(unittest.TestCase):
    def test_repeats_the_cursor_pattern_every_96_frames(self) -> None:
        self.assertEqual(FLOATING_OFFSETS, (0, 0, 0, 1, 2, 2, 2, 1))
        self.assertEqual(FLOATING_PHASE_FRAMES, 12)
        self.assertEqual(FLOATING_CYCLE_FRAMES, 96)
        self.assertEqual(
            [floating_offset(frame) for frame in range(0, 109, 12)],
            [0, 0, 0, 1, 2, 2, 2, 1, 0, 0],
        )

    def test_rejects_invalid_frame_counts(self) -> None:
        for value in (True, 1.5, "1"):
            with self.subTest(value=value), self.assertRaises(TypeError):
                floating_offset(value)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            floating_offset(-1)

    def test_floating_character_cycles_more_slowly_than_world_map_player(self) -> None:
        self.assertEqual(FLOATING_CHARACTER_FRAMES, (2, 1, 0, 1))
        self.assertEqual(FLOATING_CHARACTER_FRAME_INTERVAL, 20)
        self.assertEqual(FLOATING_CHARACTER_CYCLE_FRAMES, 80)
        self.assertEqual(
            [floating_character_frame(frame) for frame in range(0, 101, 20)],
            [2, 1, 0, 1, 2, 1],
        )

    def test_floating_character_frame_uses_the_entity_phase(self) -> None:
        phase = floating_phase_offset("pc:Fiora")

        self.assertEqual(floating_character_frame(0, phase_offset=phase), 1)

    def test_rejects_invalid_floating_character_frames(self) -> None:
        for value in (True, 1.5, "1"):
            with self.subTest(value=value), self.assertRaises(TypeError):
                floating_character_frame(value)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            floating_character_frame(-1)
        for value in (None, 1.5, True):
            with self.subTest(value=value), self.assertRaises(TypeError):
                floating_character_frame(0, phase_offset=value)  # type: ignore[arg-type]

    def test_derives_stable_full_cycle_phases_from_entity_identity(self) -> None:
        self.assertEqual(floating_phase_offset("pc:Fiora"), 77)
        self.assertEqual(
            floating_phase_offset("actor:fairy_village:actor_1"),
            68,
        )
        self.assertNotEqual(
            floating_phase_offset("pc:Fiora"),
            floating_phase_offset("pc:Cerion"),
        )
        self.assertEqual(
            floating_offset(
                0,
                phase_offset=floating_phase_offset("pc:Fiora"),
            ),
            2,
        )

    def test_rejects_invalid_identity_and_phase_offset(self) -> None:
        for value in (None, 1, True):
            with self.subTest(value=value), self.assertRaises(TypeError):
                floating_phase_offset(value)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            floating_phase_offset("")
        for value in (None, 1.5, True):
            with self.subTest(value=value), self.assertRaises(TypeError):
                floating_offset(0, phase_offset=value)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
