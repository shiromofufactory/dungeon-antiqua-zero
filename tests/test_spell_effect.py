from __future__ import annotations

import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.spell_effect import (
    SpellEffectDataError,
    SpellEffectDefinition,
    SpellEffectPlayer,
    load_spell_effects,
)


def effect_record(**changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "kind": "target_sprite",
        "image_id": "effects/spells32",
        "row": 2,
        "frame_count": 3,
        "frames_per_pattern": 4,
        "offset": {"ally": [2, -3], "enemy": [-4, 5]},
        "flash_color": 10,
        "se_id": "spell_fire1",
    }
    record.update(changes)
    return record


class SpellEffectDefinitionTest(unittest.TestCase):
    def test_parses_timing_source_and_offsets(self) -> None:
        definition = SpellEffectDefinition.from_record("FIRE1", effect_record())

        self.assertEqual(definition.cell_size, 32)
        self.assertEqual(definition.total_frames, 12)
        self.assertEqual(definition.pattern_index_at(0), 0)
        self.assertEqual(definition.pattern_index_at(3), 0)
        self.assertEqual(definition.pattern_index_at(4), 1)
        self.assertEqual(definition.pattern_index_at(11), 2)
        self.assertIsNone(definition.pattern_index_at(12))
        self.assertEqual(definition.source_position_at(4), (32, 64))
        self.assertEqual(definition.offset_for("ally"), (2, -3))
        self.assertEqual(definition.offset_for("enemy"), (-4, 5))
        self.assertEqual(
            definition.to_source_record()["offset"],
            {"ally": [2, -3], "enemy": [-4, 5]},
        )

    def test_migrates_legacy_single_offset_to_both_sides(self) -> None:
        definition = SpellEffectDefinition.from_record(
            "FIRE1", effect_record(offset=[7, -8])
        )

        self.assertEqual(definition.offset_for("ally"), (7, -8))
        self.assertEqual(definition.offset_for("enemy"), (7, -8))

    def test_rejects_invalid_speed_and_offsets(self) -> None:
        for speed in (0, 61, True):
            with self.subTest(speed=speed), self.assertRaises(SpellEffectDataError):
                SpellEffectDefinition.from_record(
                    "FIRE1", effect_record(frames_per_pattern=speed)
                )
        with self.assertRaises(SpellEffectDataError):
            SpellEffectDefinition.from_record(
                "FIRE1",
                effect_record(offset={"ally": [0, 129], "enemy": [0, 0]}),
            )

    def test_runtime_loader_indexes_compiled_records(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spells.json"
            path.write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "effects": {"FIRE1": effect_record(offset=[2, -3])},
                    }
                ),
                encoding="utf-8",
            )

            definitions = load_spell_effects(path)

        self.assertEqual(tuple(definitions), ("FIRE1",))
        self.assertEqual(definitions["FIRE1"].frames_per_pattern, 4)
        self.assertEqual(definitions["FIRE1"].offset_for("ally"), (2, -3))
        self.assertEqual(definitions["FIRE1"].offset_for("enemy"), (2, -3))


class SpellEffectPlayerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.definition = SpellEffectDefinition.from_record("FIRE1", effect_record())
        self.player = SpellEffectPlayer(self.definition, anchor_x=100, anchor_y=80)

    def test_advances_patterns_at_configured_sixty_fps_speed(self) -> None:
        self.assertEqual(self.player.pattern_index, 0)
        for _ in range(4):
            self.player.update()
        self.assertEqual(self.player.pattern_index, 1)
        for _ in range(8):
            self.player.update()
        self.assertTrue(self.player.completed)
        self.assertIsNone(self.player.pattern_index)

    def test_reports_center_and_consumes_start_sound_once(self) -> None:
        self.assertEqual(self.player.center, (96, 85))
        self.assertEqual(self.player.take_start_sound(), "spell_fire1")
        self.assertIsNone(self.player.take_start_sound())
        self.player.restart()
        self.assertEqual(self.player.take_start_sound(), "spell_fire1")

    def test_uses_the_offset_for_the_target_side(self) -> None:
        ally = SpellEffectPlayer(
            self.definition,
            anchor_x=100,
            anchor_y=80,
            target_side="ally",
        )

        self.assertEqual(ally.center, (102, 77))
        self.assertEqual(self.player.center, (96, 85))

    def test_flash_cycle_starts_and_ends_at_the_base_palette(self) -> None:
        self.assertAlmostEqual(self.player.flash_base_rate, 1.0)
        for _ in range(self.definition.total_frames // 2):
            self.player.update()
        self.assertLess(self.player.flash_base_rate, 0.22)
        self.player.restart()
        for _ in range(self.definition.total_frames - 1):
            self.player.update()
        self.assertTrue(math.isclose(self.player.flash_base_rate, 1.0))


if __name__ == "__main__":
    unittest.main()
