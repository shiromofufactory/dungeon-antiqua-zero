from __future__ import annotations

import math
from types import MappingProxyType
import unittest

from app.field import FieldPosition
from app.input import Direction
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
from app.resources.maps import CompiledMap, MapCell, MapDestination, WorldSite
from app.systems import ENCOUNTER_THRESHOLD, EncounterSystem


class FixedRandom:
    def __init__(self, value: int) -> None:
        self.value = value
        self.calls: list[tuple[int, int]] = []

    def randint(self, minimum: int, maximum: int) -> int:
        self.calls.append((minimum, maximum))
        return self.value


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
