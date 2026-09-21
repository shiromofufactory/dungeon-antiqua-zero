from __future__ import annotations

import math
from types import MappingProxyType
import unittest

from app.field import FieldPosition
from app.input import Direction
from app.monster import MonsterDefinition
from app.rendering import (
    ENCOUNTER_BLACK_COLOR,
    ENCOUNTER_FADE_FRAME_COUNT,
    ENCOUNTER_FINAL_SCALE,
    ENCOUNTER_ROTATION_DEGREES,
    ENCOUNTER_TRANSITION_FRAME_COUNT,
    ENCOUNTER_WHITE_COLOR,
    ENCOUNTER_WHITEOUT_FRAME_COUNT,
    EncounterTransition,
)
from app.resources import load_record_array
from app.resources.maps import (
    CompiledMap,
    MapCell,
    MapDestination,
    MapRandomEncounter,
    WorldSite,
)
from app.systems import (
    ENCOUNTER_THRESHOLD,
    EncounterGenerationError,
    EncounterSystem,
)


class FixedRandom:
    def __init__(self, value: int) -> None:
        self.value = value
        self.calls: list[tuple[int, int]] = []

    def randint(self, minimum: int, maximum: int) -> int:
        self.calls.append((minimum, maximum))
        return self.value


class ScriptedRandom:
    def __init__(
        self,
        *,
        randrange_values: tuple[int, ...],
        randint_values: tuple[int, ...],
    ) -> None:
        self.randrange_values = list(randrange_values)
        self.randint_values = list(randint_values)
        self.randrange_calls: list[int] = []
        self.randint_calls: list[tuple[int, int]] = []

    def randrange(self, stop: int) -> int:
        self.randrange_calls.append(stop)
        return self.randrange_values.pop(0)

    def randint(self, minimum: int, maximum: int) -> int:
        self.randint_calls.append((minimum, maximum))
        return self.randint_values.pop(0)


def monster(key: str, **overrides: object) -> MonsterDefinition:
    record = dict(load_record_array("monsters.json")[0])
    record.update(
        {
            "name_en": key,
            "name_ja": key,
            "lv": 3,
            "early_appear": 0,
            "max_occ": 1,
            "tribe": "ANIMAL",
            "large_animal": 1,
            "weakness": "",
            **overrides,
        }
    )
    return MonsterDefinition.from_record(record)


def encounter_settings(**overrides: object) -> MapRandomEncounter:
    values = {
        "monster_level": 3,
        "danger": "high",
        "polarity": "neutral",
        "allow_demons": True,
        "allow_humans": True,
        "allow_giants": True,
        "allow_large_animals": True,
    }
    values.update(overrides)
    return MapRandomEncounter(**values)  # type: ignore[arg-type]


def dungeon_map(
    *,
    sites: tuple[WorldSite, ...] = (),
    collision_rows: tuple[str, ...] = (
        "1111111",
        "1000001",
        "1000001",
        "1000001",
        "1110111",
    ),
) -> CompiledMap:
    width = len(collision_rows[0])
    height = len(collision_rows)
    return CompiledMap(
        map_id="test_dungeon",
        profile="dungeon",
        tileset_id="test_dungeon",
        tile_size=16,
        width=width,
        height=height,
        atlas=object(),
        atlas_columns=1,
        atlas_tile_count=1,
        ground_tiles=(0,) * (width * height),
        object_tiles=(),
        collision_rows=collision_rows,
        ground_animations=MappingProxyType({}),
        object_animations=MappingProxyType({}),
        sites=sites,
    )


class EncounterSystemTest(unittest.TestCase):
    def test_adds_da1_random_amount_and_resets_at_fixed_threshold(self) -> None:
        random_source = FixedRandom(4)
        system = EncounterSystem(random_source=random_source)  # type: ignore[arg-type]

        before = system.advance(ENCOUNTER_THRESHOLD - 5)
        triggered = system.advance(before.count)

        self.assertEqual(before.count, ENCOUNTER_THRESHOLD - 1)
        self.assertFalse(before.triggered)
        self.assertEqual(triggered.count, 0)
        self.assertTrue(triggered.triggered)
        self.assertEqual(random_source.calls, [(1, 4), (1, 4)])

    def test_dynamic_level_is_provisionally_fixed_at_one(self) -> None:
        self.assertEqual(EncounterSystem.dynamic_monster_level(), 1)

    def test_accepts_a_doubled_threshold_without_changing_the_count(self) -> None:
        random_source = FixedRandom(4)
        system = EncounterSystem(random_source=random_source)  # type: ignore[arg-type]

        before = system.advance(ENCOUNTER_THRESHOLD - 1, threshold=240)
        triggered = system.advance(236, threshold=240)

        self.assertEqual(before.count, ENCOUNTER_THRESHOLD + 3)
        self.assertFalse(before.triggered)
        self.assertEqual(triggered.count, 0)
        self.assertTrue(triggered.triggered)

    def test_rejects_invalid_threshold(self) -> None:
        system = EncounterSystem()

        for threshold, error in ((True, TypeError), (1.5, TypeError), (0, ValueError)):
            with self.subTest(threshold=threshold):
                with self.assertRaises(error):
                    system.advance(0, threshold=threshold)  # type: ignore[arg-type]

    def test_high_danger_can_add_an_early_next_level_monster(self) -> None:
        random_source = ScriptedRandom(
            randrange_values=(2,),
            randint_values=(1, 5),
        )
        system = EncounterSystem(random_source=random_source)  # type: ignore[arg-type]
        monsters = (
            monster("Level 3"),
            monster("Early Level 4", lv=4, early_appear=1),
            monster("Late Level 4", lv=4, early_appear=0),
        )

        formation = system.generate_formation(
            monsters,
            encounter_settings(),
            monster_level=3,
        )

        self.assertEqual(formation.monster_keys, ("Early Level 4",))
        self.assertEqual(random_source.randrange_calls, [4])
        self.assertEqual(random_source.randint_calls, [(1, 1), (1, 5)])

    def test_low_danger_halves_max_occurrence_rounding_up(self) -> None:
        random_source = ScriptedRandom(
            randrange_values=(0,),
            randint_values=(3, 2),
        )
        system = EncounterSystem(random_source=random_source)  # type: ignore[arg-type]

        formation = system.generate_formation(
            (monster("Pack", max_occ=5),),
            encounter_settings(danger="low"),
            monster_level=3,
        )

        self.assertEqual(formation.monster_keys, ("Pack", "Pack", "Pack"))
        self.assertEqual(random_source.randint_calls, [(1, 3), (1, 4)])

    def test_high_danger_can_continue_with_a_lower_level_group(self) -> None:
        random_source = ScriptedRandom(
            randrange_values=(0, 0, 0),
            randint_values=(1, 1, 2, 3),
        )
        system = EncounterSystem(random_source=random_source)  # type: ignore[arg-type]

        formation = system.generate_formation(
            (
                monster("Level 3"),
                monster("Level 2", lv=2, max_occ=2),
            ),
            encounter_settings(),
            monster_level=3,
        )

        self.assertEqual(
            formation.monster_keys,
            ("Level 3", "Level 2", "Level 2"),
        )

    def test_stops_before_a_group_would_exceed_five_monsters(self) -> None:
        random_source = ScriptedRandom(
            randrange_values=(0, 1, 0),
            randint_values=(4, 1, 2),
        )
        system = EncounterSystem(random_source=random_source)  # type: ignore[arg-type]

        formation = system.generate_formation(
            (monster("Pack", max_occ=4),),
            encounter_settings(),
            monster_level=3,
        )

        self.assertEqual(formation.monster_keys, ("Pack",) * 4)

    def test_low_danger_stops_before_exceeding_its_four_monster_limit(self) -> None:
        random_source = ScriptedRandom(
            randrange_values=(0, 1, 0),
            randint_values=(3, 1, 2),
        )
        system = EncounterSystem(random_source=random_source)  # type: ignore[arg-type]

        formation = system.generate_formation(
            (monster("Pack", max_occ=4),),
            encounter_settings(danger="low"),
            monster_level=3,
        )

        self.assertEqual(formation.monster_keys, ("Pack",) * 3)

    def test_remaining_capacity_roll_can_end_before_another_group(self) -> None:
        random_source = ScriptedRandom(
            randrange_values=(0,),
            randint_values=(2, 4),
        )
        system = EncounterSystem(random_source=random_source)  # type: ignore[arg-type]

        formation = system.generate_formation(
            (monster("Pack", max_occ=2),),
            encounter_settings(),
            monster_level=3,
        )

        self.assertEqual(formation.monster_keys, ("Pack", "Pack"))
        self.assertEqual(random_source.randrange_calls, [2])

    def test_level_reduction_does_not_go_below_one(self) -> None:
        random_source = ScriptedRandom(
            randrange_values=(0, 0, 0),
            randint_values=(1, 1, 1, 5),
        )
        system = EncounterSystem(random_source=random_source)  # type: ignore[arg-type]

        formation = system.generate_formation(
            (monster("Level 1", lv=1),),
            encounter_settings(),
            monster_level=1,
        )

        self.assertEqual(formation.monster_keys, ("Level 1", "Level 1"))

    def test_pool_does_not_add_the_same_monster_key_twice(self) -> None:
        duplicate = monster("Duplicate")
        system = EncounterSystem()

        pool = system._weighted_pool(
            (duplicate, duplicate),
            encounter_settings(),
            3,
        )

        self.assertEqual(tuple(item.key for item, _weight in pool), ("Duplicate",))

    def test_species_switches_and_large_animal_off_follow_map_filters(self) -> None:
        system = EncounterSystem()
        settings = encounter_settings(
            allow_demons=False,
            allow_humans=False,
            allow_giants=False,
            allow_large_animals=False,
        )
        pool = system._weighted_pool(
            (
                monster("Demon", tribe="DEMON"),
                monster("Human", tribe="HUMAN"),
                monster("Mage", tribe="MAGE"),
                monster("Giant", tribe="GIANT"),
                monster("Small Animal", large_animal=0),
                monster("Large Animal", large_animal=1),
            ),
            settings,
            3,
        )

        self.assertEqual(tuple(item.key for item, _weight in pool), ("Small Animal",))

    def test_large_animal_on_adds_an_early_next_level_candidate(self) -> None:
        monsters = (
            monster("Level 3", large_animal=0),
            monster(
                "Early Large Animal",
                lv=4,
                early_appear=1,
                large_animal=1,
            ),
        )
        system = EncounterSystem()

        disabled = system._weighted_pool(
            monsters,
            encounter_settings(allow_large_animals=False),
            3,
        )
        enabled = system._weighted_pool(
            monsters,
            encounter_settings(allow_large_animals=True),
            3,
        )

        self.assertEqual(
            tuple(item.key for item, _weight in disabled),
            ("Level 3",),
        )
        self.assertEqual(
            tuple(item.key for item, _weight in enabled),
            ("Level 3", "Early Large Animal"),
        )

    def test_current_level_one_low_danger_pool_matches_master_data(self) -> None:
        monsters = tuple(
            MonsterDefinition.from_record(record)
            for record in load_record_array("monsters.json")
        )
        system = EncounterSystem()

        disabled = system._weighted_pool(
            monsters,
            encounter_settings(
                monster_level="dynamic",
                danger="low",
                allow_demons=False,
                allow_humans=False,
                allow_giants=False,
                allow_large_animals=False,
            ),
            1,
        )
        enabled = system._weighted_pool(
            monsters,
            encounter_settings(
                monster_level="dynamic",
                danger="low",
                allow_demons=False,
                allow_humans=False,
                allow_giants=False,
                allow_large_animals=True,
            ),
            1,
        )

        expected = ("Giant Spider", "Coyote", "Goblin")
        self.assertEqual(tuple(item.key for item, _weight in disabled), expected)
        self.assertEqual(tuple(item.key for item, _weight in enabled), expected)

    def test_polarity_excludes_or_halves_elemental_weakness_candidates(self) -> None:
        monsters = (
            monster("Plain"),
            monster("Fire Weak", weakness="炎"),
            monster("Freeze Weak", weakness="冷"),
        )
        system = EncounterSystem()

        yang = system._weighted_pool(
            monsters,
            encounter_settings(polarity="yang"),
            3,
        )
        yin = system._weighted_pool(
            monsters,
            encounter_settings(polarity="yin"),
            3,
        )
        neutral = system._weighted_pool(
            monsters,
            encounter_settings(polarity="neutral"),
            3,
        )

        self.assertEqual(
            tuple((item.key, weight) for item, weight in yang),
            (("Plain", 2), ("Freeze Weak", 2)),
        )
        self.assertEqual(
            tuple((item.key, weight) for item, weight in yin),
            (("Plain", 2), ("Fire Weak", 2)),
        )
        self.assertEqual(
            tuple((item.key, weight) for item, weight in neutral),
            (("Plain", 2), ("Fire Weak", 1), ("Freeze Weak", 1)),
        )

    def test_rejects_settings_with_no_eligible_first_group(self) -> None:
        system = EncounterSystem()

        with self.assertRaises(EncounterGenerationError):
            system.generate_formation(
                (monster("Demon", tribe="DEMON"),),
                encounter_settings(allow_demons=False),
                monster_level=3,
            )

    def test_finds_nearest_outward_exit_and_lands_before_trigger_cell(self) -> None:
        sites = (
            WorldSite(
                "far_exit",
                "location.far_exit",
                (MapCell(5, 4),),
                MapDestination("worldmap", "far"),
            ),
            WorldSite(
                "near_exit",
                "location.near_exit",
                (MapCell(3, 4),),
                MapDestination("worldmap", "near"),
            ),
            WorldSite(
                "local_warp",
                "location.local_warp",
                (MapCell(1, 4),),
                MapDestination("test_dungeon", "other_room"),
            ),
        )

        destination = EncounterSystem.defeat_return(
            dungeon_map(sites=sites),
            FieldPosition(2, 2),
        )

        self.assertIsNotNone(destination)
        assert destination is not None
        self.assertEqual(destination.position, FieldPosition(3, 3))
        self.assertIs(destination.facing, Direction.DOWN)

    def test_returns_none_when_map_has_no_usable_outward_exit(self) -> None:
        self.assertIsNone(
            EncounterSystem.defeat_return(
                dungeon_map(),
                FieldPosition(2, 2),
            )
        )


class EncounterTransitionTest(unittest.TestCase):
    def test_whites_out_for_32_frames_then_fades_to_black(self) -> None:
        transition = EncounterTransition(128, 120)

        for _frame in range(ENCOUNTER_WHITEOUT_FRAME_COUNT // 2):
            transition.update()
        self.assertEqual(transition.palette_base_rate, 0.5)
        self.assertEqual(transition.palette_target_color, ENCOUNTER_WHITE_COLOR)

        for _frame in range(ENCOUNTER_WHITEOUT_FRAME_COUNT // 2):
            transition.update()
        self.assertEqual(transition.palette_base_rate, 0.0)
        self.assertEqual(transition.palette_target_color, ENCOUNTER_WHITE_COLOR)

        for _frame in range(ENCOUNTER_FADE_FRAME_COUNT // 2):
            transition.update()
        self.assertEqual(transition.palette_base_rate, 0.0)
        self.assertEqual(transition.palette_target_color, 0x808080)

        for _frame in range(ENCOUNTER_FADE_FRAME_COUNT // 2):
            transition.update()

        self.assertTrue(transition.is_finished)
        self.assertEqual(transition.palette_target_color, ENCOUNTER_BLACK_COLOR)

    def test_zoom_accelerates_to_the_final_scale(self) -> None:
        transition = EncounterTransition(128, 120)
        scales = [transition.transform(256, 240).scale]

        for _segment in range(4):
            for _frame in range(ENCOUNTER_WHITEOUT_FRAME_COUNT // 4):
                transition.update()
            scales.append(transition.transform(256, 240).scale)

        increases = [
            after - before for before, after in zip(scales, scales[1:])
        ]
        self.assertEqual(scales[0], 1.0)
        self.assertEqual(scales[-1], ENCOUNTER_FINAL_SCALE)
        self.assertEqual(increases, sorted(increases))

        for _frame in range(ENCOUNTER_FADE_FRAME_COUNT):
            transition.update()
        self.assertEqual(
            transition.transform(256, 240).scale,
            ENCOUNTER_FINAL_SCALE,
        )

    def test_rotation_starts_immediately_and_accelerates_to_two_turns(self) -> None:
        transition = EncounterTransition(128, 112)
        angles = [transition.transform(256, 240).rotate]

        for _frame in range(ENCOUNTER_TRANSITION_FRAME_COUNT - 1):
            transition.update()
            angles.append(transition.transform(256, 240).rotate)

        frame_rotations = [
            after - before for before, after in zip(angles, angles[1:])
        ]
        self.assertGreater(angles[1], 0.0)
        self.assertAlmostEqual(angles[-1], ENCOUNTER_ROTATION_DEGREES)
        self.assertEqual(frame_rotations, sorted(frame_rotations))

    def test_transform_keeps_the_player_pivot_fixed(self) -> None:
        transition = EncounterTransition(48, 72)
        for _frame in range(13):
            transition.update()

        transform = transition.transform(256, 240)
        radians = math.radians(transform.rotate)
        source_x = 48 - 128
        source_y = 72 - 120
        destination_x = (
            transform.x
            + 128
            + transform.scale
            * (source_x * math.cos(radians) - source_y * math.sin(radians))
        )
        destination_y = (
            transform.y
            + 120
            + transform.scale
            * (source_x * math.sin(radians) + source_y * math.cos(radians))
        )

        self.assertAlmostEqual(destination_x, 48)
        self.assertAlmostEqual(destination_y, 72)

if __name__ == "__main__":
    unittest.main()
