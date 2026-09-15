from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.resources.maps import MapCell, MapDestination, MapResourceError, MapResources


class FakeImage:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.data = bytearray(width * height)

    def data_ptr(self) -> bytearray:
        return self.data


class FakePyxel:
    def __init__(self) -> None:
        self.images: list[FakeImage] = []

    def Image(self, width: int, height: int) -> FakeImage:
        image = FakeImage(width, height)
        self.images.append(image)
        return image


class MapResourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.maps_dir = Path(self.temporary.name)
        self.atlas = bytes([0] * (32 * 16))
        (self.maps_dir / "test_map.bin").write_bytes(self.atlas)
        self.runtime = {
            "format_version": 6,
            "map_id": "test_map",
            "profile": "world",
            "tileset_id": "worldmap",
            "bgm_id": "da3-field",
            "tile_size": 16,
            "size": [2, 2],
            "atlas": {
                "file": "test_map.bin",
                "pixel_format": "pyxel-palette-index-u8",
                "width": 32,
                "height": 16,
                "columns": 2,
                "tile_count": 2,
                "sha256": hashlib.sha256(self.atlas).hexdigest(),
            },
            "ground_tiles": [0, 0, 0, 0],
            "object_tiles": [
                {
                    "instance_id": "tree_1",
                    "definition_id": "tree",
                    "position": [1, 1],
                    "draw_group": "object",
                    "order": 0,
                    "tile": 1,
                }
            ],
            "animations": [
                {
                    "target": "ground",
                    "index": 0,
                    "frames": [
                        {"duration": 2, "tile": 0},
                        {"duration": 3, "tile": 1},
                    ],
                }
            ],
            "collision_rows": ["10", "01"],
            "sites": [
                {
                    "id": "sample_town",
                    "name_text_key": "location.sample_town",
                    "entrance_cells": [[1, 0]],
                    "destination": {
                        "map_id": "sample_town",
                        "arrival_id": "from_world",
                    },
                }
            ],
            "arrival_points": [
                {
                    "id": "from_world",
                    "position": [1, 0],
                    "facing": "left",
                    "teleport_enabled": True,
                    "site_id": "sample_town",
                }
            ],
            "actors": [
                {
                    "id": "elder",
                    "position": [0, 1],
                    "kind": "stationary",
                    "sprite_index": 0,
                    "sprite_source": "pc",
                    "facing": "down",
                    "floating": True,
                },
                {
                    "id": "entrance_potion",
                    "position": [1, 0],
                    "kind": "treasure",
                    "contents": {"type": "item", "item_key": "POTION"},
                }
            ],
            "event_triggers": [
                {
                    "id": "sign",
                    "event_id": "sample.sign",
                    "activations": ["touch"],
                    "target": {"kind": "cells", "cells": [[1, 0]]},
                },
                {
                    "id": "elder_talk",
                    "event_id": "sample.elder_talk",
                    "activations": ["touch", "interact"],
                    "target": {
                        "kind": "actor",
                        "actor_id": "elder",
                        "offsets": [[0, 0]],
                    },
                },
            ],
        }
        self._write_runtime()
        self.pyxel = FakePyxel()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_runtime(self) -> None:
        (self.maps_dir / "test_map.json").write_text(
            json.dumps(self.runtime),
            encoding="utf-8",
        )

    def test_loads_atlas_collision_objects_and_animation(self) -> None:
        resources = MapResources(self.maps_dir, pyxel_api=self.pyxel)

        map_data = resources.map("test_map")

        self.assertEqual((map_data.width, map_data.height), (2, 2))
        self.assertEqual(map_data.bgm_id, "da3-field")
        self.assertEqual(map_data.ground_tiles, (0, 0, 0, 0))
        self.assertEqual(len(map_data.object_tiles), 1)
        self.assertEqual(
            (map_data.object_tiles[0].x, map_data.object_tiles[0].y),
            (1, 1),
        )
        self.assertTrue(map_data.is_blocked(0, 0))
        self.assertFalse(map_data.is_blocked(1, 0))
        self.assertTrue(map_data.is_blocked(-1, 0))
        self.assertEqual(map_data.sites[0].id, "sample_town")
        self.assertEqual(map_data.sites[0].entrance_cells, (MapCell(1, 0),))
        self.assertEqual(map_data.sites[0].destination.arrival_id, "from_world")
        self.assertEqual(map_data.arrival_points[0].position, MapCell(1, 0))
        self.assertEqual(map_data.arrival_points[0].facing, "left")
        self.assertTrue(map_data.arrival_points[0].teleport_enabled)
        self.assertEqual(map_data.arrival_points[0].site_id, "sample_town")
        self.assertEqual(
            resources.teleport_destination("sample_town"),
            MapDestination("test_map", "from_world"),
        )
        self.assertIs(map_data.arrival_point("from_world"), map_data.arrival_points[0])
        self.assertEqual(map_data.actors[0].id, "elder")
        self.assertEqual(map_data.actors[0].kind, "stationary")
        self.assertEqual(map_data.actors[0].sprite_index, 0)
        self.assertEqual(map_data.actors[0].sprite_source, "pc")
        self.assertTrue(map_data.actors[0].floating)
        self.assertEqual(map_data.actors[1].kind, "treasure")
        self.assertEqual(map_data.actors[1].contents.type, "item")
        self.assertEqual(map_data.actors[1].contents.item_key, "POTION")
        self.assertEqual(map_data.actors[1].sprite_source, "npc")
        self.assertFalse(map_data.actors[1].floating)
        self.assertEqual(
            map_data.event_trigger_at("touch", 1, 0).event_id,
            "sample.sign",
        )
        self.assertEqual(
            map_data.event_trigger_at(
                "touch",
                0,
                1,
                actor_positions={"elder": MapCell(0, 1)},
            ).event_id,
            "sample.elder_talk",
        )
        self.assertEqual(
            [map_data.ground_tile_at(0, frame) for frame in range(6)],
            [0, 0, 1, 1, 1, 0],
        )
        self.assertEqual(self.pyxel.images[0].data, self.atlas)
        self.assertIs(resources.map("test_map"), map_data)
        self.assertEqual(len(self.pyxel.images), 1)

    def test_rejects_hash_mismatch_and_invalid_runtime_shapes(self) -> None:
        self.runtime["atlas"]["sha256"] = "0" * 64
        self._write_runtime()
        with self.assertRaisesRegex(MapResourceError, "SHA-256"):
            MapResources(self.maps_dir, pyxel_api=self.pyxel).map("test_map")

        self.runtime["atlas"]["sha256"] = hashlib.sha256(self.atlas).hexdigest()
        self.runtime["collision_rows"] = ["10"]
        self._write_runtime()
        with self.assertRaisesRegex(MapResourceError, "collision_rows"):
            MapResources(self.maps_dir, pyxel_api=self.pyxel).map("test_map")

    def test_accepts_foreground_and_rejects_unknown_object_draw_group(self) -> None:
        self.runtime["object_tiles"][0]["draw_group"] = "object_foreground"
        self._write_runtime()
        loaded = MapResources(self.maps_dir, pyxel_api=self.pyxel).map("test_map")
        self.assertEqual(loaded.object_tiles[0].draw_group, "object_foreground")

        self.runtime["object_tiles"][0]["draw_group"] = "unknown"
        self._write_runtime()
        with self.assertRaisesRegex(MapResourceError, "draw_group"):
            MapResources(self.maps_dir, pyxel_api=self.pyxel).map("test_map")

    def test_rejects_missing_and_unsafe_map_ids(self) -> None:
        resources = MapResources(self.maps_dir, pyxel_api=self.pyxel)
        with self.assertRaises(MapResourceError):
            resources.map("missing")
        for map_id in ("../test_map", "/test_map", "TestMap"):
            with self.subTest(map_id=map_id), self.assertRaises(ValueError):
                resources.map(map_id)

    def test_rejects_invalid_or_non_character_floating(self) -> None:
        self.runtime["actors"][0]["floating"] = "yes"
        self._write_runtime()
        with self.assertRaisesRegex(MapResourceError, "floating"):
            MapResources(self.maps_dir, pyxel_api=self.pyxel).map("test_map")

        self.runtime["actors"][0]["floating"] = True
        self.runtime["actors"][1]["floating"] = False
        self._write_runtime()
        with self.assertRaisesRegex(MapResourceError, "floating"):
            MapResources(self.maps_dir, pyxel_api=self.pyxel).map("test_map")

    def test_requires_exact_actor_trigger_and_rejects_standalone_interact(self) -> None:
        self.runtime["event_triggers"] = self.runtime["event_triggers"][:1]
        self._write_runtime()
        with self.assertRaisesRegex(MapResourceError, "actor elder"):
            MapResources(self.maps_dir, pyxel_api=self.pyxel).map("test_map")

        self.runtime["event_triggers"][0]["activations"] = ["interact"]
        self._write_runtime()
        with self.assertRaisesRegex(MapResourceError, "actor target"):
            MapResources(self.maps_dir, pyxel_api=self.pyxel).map("test_map")


if __name__ == "__main__":
    unittest.main()
