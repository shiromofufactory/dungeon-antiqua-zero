from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from scripts.map_pipeline.tileset import (
    choose_visual_choice,
    ground_stack,
    initial_worldmap_tileset,
    inspect_source_image,
    load_tileset,
    save_tileset,
    select_boundary_rule,
    validate_tileset,
)


class MapTilesetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.image_path = self.root / "worldmap.png"
        Image.new("RGBA", (64, 96), (0, 0, 0, 0)).save(self.image_path)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_minimal_world_tileset_is_valid(self) -> None:
        diagnostics, info = validate_tileset(
            initial_worldmap_tileset(),
            image_path=self.image_path,
        )

        self.assertEqual([item for item in diagnostics if item.severity == "error"], [])
        self.assertIsNotNone(info)
        self.assertEqual((info.columns, info.rows), (4, 6))
        warning_codes = {item.code for item in diagnostics if item.severity == "warning"}
        self.assertIn("missing_world_boundaries", warning_codes)
        self.assertIn("missing_world_objects", warning_codes)

    def test_reports_invalid_graph_visual_and_world_contract(self) -> None:
        data = initial_worldmap_tileset()
        data["grounds"][0]["parent_id"] = "sand"
        data["grounds"][1]["collision"] = "blocked"
        data["grounds"][2]["base_visual"]["choices"][0]["weight"] = 0
        data["grounds"][2]["base_visual"]["choices"][0]["frames"][0]["tile"] = [9, 9]

        diagnostics, _ = validate_tileset(data, image_path=self.image_path)
        codes = {item.code for item in diagnostics if item.severity == "error"}

        self.assertIn("ground_parent_cycle", codes)
        self.assertIn("invalid_world_ground_collision", codes)
        self.assertIn("zero_total_weight", codes)
        self.assertIn("tile_out_of_bounds", codes)

    def test_warns_when_later_boundary_rule_is_shadowed(self) -> None:
        data = initial_worldmap_tileset()
        ground = data["grounds"][1]
        rule = {
            "id": "north",
            "neighbors": {
                "n": "different",
                "ne": "any",
                "e": "any",
                "se": "any",
                "s": "any",
                "sw": "any",
                "w": "any",
                "nw": "any",
            },
            "visual": deepcopy(ground["base_visual"]),
        }
        ground["boundaries"] = [rule, {**deepcopy(rule), "id": "also_north"}]

        diagnostics, _ = validate_tileset(data, image_path=self.image_path)
        error_codes = {item.code for item in diagnostics if item.severity == "error"}
        warning_codes = {item.code for item in diagnostics if item.severity == "warning"}

        self.assertNotIn("ambiguous_boundary_rules", error_codes)
        self.assertIn("unreachable_boundary_rule", warning_codes)

    def test_selects_first_matching_boundary_rule(self) -> None:
        any_neighbors = {direction: "any" for direction in ("n", "ne", "e", "se", "s", "sw", "w", "nw")}
        north = {**any_neighbors, "n": "different"}
        northwest = {**north, "w": "different"}
        rules = [
            {"id": "north", "neighbors": north},
            {"id": "corner", "neighbors": northwest},
        ]
        actual = {direction: True for direction in any_neighbors}
        actual["n"] = False
        actual["w"] = False

        selected = select_boundary_rule(rules, actual)
        self.assertEqual(selected["id"], "north")

        selected = select_boundary_rule(list(reversed(rules)), actual)
        self.assertEqual(selected["id"], "corner")

    def test_migrates_legacy_priority_to_rule_order(self) -> None:
        data = initial_worldmap_tileset()
        ground = data["grounds"][1]
        any_neighbors = {direction: "any" for direction in ("n", "ne", "e", "se", "s", "sw", "w", "nw")}
        ground["boundaries"] = [
            {"id": "general", "priority": 10, "neighbors": {**any_neighbors, "n": "different"}},
            {"id": "low", "priority": 9, "neighbors": {**any_neighbors, "e": "different"}},
            {"id": "specific", "priority": 10, "neighbors": {**any_neighbors, "n": "different", "w": "different"}},
        ]
        path = self.root / "legacy.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        loaded = load_tileset(path)

        rules = loaded["grounds"][1]["boundaries"]
        self.assertEqual([rule["id"] for rule in rules], ["specific", "general", "low"])
        self.assertTrue(all("priority" not in rule for rule in rules))

        save_tileset(path, data)
        saved = json.loads(path.read_text(encoding="utf-8"))
        saved_rules = saved["grounds"][1]["boundaries"]
        self.assertEqual([rule["id"] for rule in saved_rules], ["specific", "general", "low"])
        self.assertTrue(all("priority" not in rule for rule in saved_rules))

    def test_resolves_ground_stack_and_deterministic_weighted_choice(self) -> None:
        data = initial_worldmap_tileset()
        self.assertEqual(
            [ground["id"] for ground in ground_stack(data["grounds"], "sand")],
            ["sea", "plain", "sand"],
        )
        visual = {
            "choices": [
                {"id": "off", "weight": 0},
                {"id": "a", "weight": 7},
                {"id": "b", "weight": 2},
                {"id": "c", "weight": 1},
            ]
        }
        first = choose_visual_choice(visual, ["map", 10, 20])["id"]
        second = choose_visual_choice(visual, ["map", 10, 20])["id"]
        self.assertEqual(first, second)
        self.assertNotEqual(first, "off")

    def test_inspects_incomplete_image_margin(self) -> None:
        image = Image.new("RGBA", (33, 18), (0, 0, 0, 0))
        image.putpixel((32, 17), (255, 0, 255, 255))
        image.save(self.image_path)

        info, diagnostics = inspect_source_image(self.image_path)

        self.assertEqual((info.columns, info.rows), (2, 1))
        self.assertIn("non_transparent_image_margin", {item.code for item in diagnostics})

    def test_accepts_reserved_transparent_color_in_image_margin(self) -> None:
        Image.new("RGBA", (33, 18), (255, 0, 128, 255)).save(self.image_path)

        info, diagnostics = inspect_source_image(self.image_path)

        self.assertEqual((info.columns, info.rows), (2, 1))
        self.assertNotIn("non_transparent_image_margin", {item.code for item in diagnostics})

    def test_saves_stable_utf8_json(self) -> None:
        path = self.root / "maps" / "tilesets" / "worldmap.json"
        data = initial_worldmap_tileset()

        save_tileset(path, data)

        self.assertEqual(load_tileset(path), data)
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(json.loads(text)["tileset_id"], "worldmap")


if __name__ == "__main__":
    unittest.main()
