from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.resources.maps import MapResourceError, MapResources


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
            "format_version": 1,
            "map_id": "test_map",
            "profile": "world",
            "tileset_id": "worldmap",
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
        self.assertEqual(map_data.ground_tiles, (0, 0, 0, 0))
        self.assertEqual(len(map_data.object_tiles), 1)
        self.assertEqual(
            (map_data.object_tiles[0].x, map_data.object_tiles[0].y),
            (1, 1),
        )
        self.assertTrue(map_data.is_blocked(0, 0))
        self.assertFalse(map_data.is_blocked(1, 0))
        self.assertTrue(map_data.is_blocked(-1, 0))
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

    def test_rejects_missing_and_unsafe_map_ids(self) -> None:
        resources = MapResources(self.maps_dir, pyxel_api=self.pyxel)
        with self.assertRaises(MapResourceError):
            resources.map("missing")
        for map_id in ("../test_map", "/test_map", "TestMap"):
            with self.subTest(map_id=map_id), self.assertRaises(ValueError):
                resources.map(map_id)


if __name__ == "__main__":
    unittest.main()
