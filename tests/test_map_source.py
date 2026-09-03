from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from scripts.map_pipeline import (
    compile_map,
    initial_map_source,
    initial_worldmap_tileset,
    resolve_map,
    validate_map_source,
)


class MapSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.image_path = self.root / "worldmap.png"
        Image.new("RGBA", (64, 96), (0, 0, 0, 255)).save(self.image_path)
        self.palette_path = self.root / "palette.pyxpal"
        self.palette_path.write_text("000000\nFF0080\n", encoding="utf-8")
        self.tileset = initial_worldmap_tileset()
        self.tileset["objects"] = [
            {
                "id": "rock",
                "size": [1, 1],
                "default_draw_group": "object",
                "cells": [{"offset": [0, 0], "collision": "blocked", "tile": [0, 0]}],
            }
        ]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_initial_world_map_is_valid_and_resolves_deterministically(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 6, 5)
        source["grounds"][2][2] = "plain"

        diagnostics = validate_map_source(source, self.tileset)
        first = resolve_map(source, self.tileset)
        second = resolve_map(source, self.tileset)

        self.assertEqual([item for item in diagnostics if item.severity == "error"], [])
        self.assertEqual(first, second)
        self.assertEqual(len(first["ground_cells"]), 30)
        self.assertFalse(first["collision"][2 * 6 + 2])

    def test_rejects_non_sea_world_edge_and_duplicate_object_origin(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 6, 5)
        source["grounds"][0][1] = "plain"
        source["objects"] = [
            {"id": "rock_1", "definition_id": "rock", "origin": [2, 2], "order": 0},
            {"id": "rock_2", "definition_id": "rock", "origin": [2, 2], "order": 1},
        ]

        codes = {item.code for item in validate_map_source(source, self.tileset)}

        self.assertIn("world_edge_not_sea", codes)
        self.assertIn("duplicate_object_origin", codes)

    def test_allows_object_overlap_when_origins_differ_and_combines_collision(self) -> None:
        tileset = deepcopy(self.tileset)
        tileset["objects"][0]["size"] = [2, 1]
        tileset["objects"][0]["cells"] = [
            {"offset": [0, 0], "collision": "blocked", "tile": [0, 0]},
            {"offset": [1, 0], "collision": "passable", "tile": [1, 0]},
        ]
        source = initial_map_source("test_world", tileset, "world", 6, 5)
        source["grounds"][2][2] = "plain"
        source["grounds"][2][3] = "plain"
        source["grounds"][2][4] = "plain"
        source["objects"] = [
            {"id": "rock_1", "definition_id": "rock", "origin": [2, 2], "order": 0},
            {"id": "rock_2", "definition_id": "rock", "origin": [3, 2], "order": 1},
        ]

        resolved = resolve_map(source, tileset)

        self.assertEqual(len(resolved["object_cells"]), 4)
        self.assertTrue(resolved["collision"][2 * 6 + 2])
        self.assertTrue(resolved["collision"][2 * 6 + 3])
        self.assertFalse(resolved["collision"][2 * 6 + 4])

    def test_compiles_rules_and_choices_to_runtime_atlas(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 6, 5)
        source["grounds"][2][2] = "plain"
        source["objects"] = [
            {"id": "rock_1", "definition_id": "rock", "origin": [2, 2], "order": 0}
        ]

        compiled = compile_map(source, self.tileset, self.image_path, self.palette_path)

        self.assertEqual(compiled.runtime["size"], [6, 5])
        self.assertEqual(len(compiled.runtime["ground_tiles"]), 30)
        self.assertEqual(len(compiled.runtime["object_tiles"]), 1)
        self.assertEqual(compiled.runtime["collision_rows"][2][2], "1")
        self.assertEqual(len(compiled.atlas), compiled.runtime["atlas"]["width"] * compiled.runtime["atlas"]["height"])


if __name__ == "__main__":
    unittest.main()
