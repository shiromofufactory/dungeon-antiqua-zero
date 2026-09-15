from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from scripts.map_pipeline import (
    compile_map,
    initial_map_source,
    initial_tileset,
    initial_worldmap_tileset,
    resolve_map,
    validate_map_event_links,
    validate_map_links,
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
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"

        diagnostics = validate_map_source(source, self.tileset)
        first = resolve_map(source, self.tileset)
        second = resolve_map(source, self.tileset)

        self.assertEqual([item for item in diagnostics if item.severity == "error"], [])
        self.assertEqual(first, second)
        self.assertEqual(len(first["ground_cells"]), 240)
        self.assertFalse(first["collision"][2 * 16 + 2])
        self.assertEqual(first["sites"], [])
        self.assertEqual(first["arrival_points"], [])

    def test_requires_at_least_one_screen_and_uses_first_ground_as_town_edge(self) -> None:
        town_tileset = initial_tileset(
            "village",
            "mapchips/village",
            "town",
            "grass",
            "passable",
        )
        source = initial_map_source("sample_village", town_tileset, "town", 16, 15)

        self.assertTrue(
            all(
                ground_id == "grass"
                for row in source["grounds"]
                for ground_id in row
            )
        )
        source["grounds"].append(["grass"] * 16)
        source["size"] = [16, 16]
        source["grounds"][0][4] = "missing"
        codes = {item.code for item in validate_map_source(source, town_tileset)}
        self.assertIn("unknown_ground", codes)

        town_tileset["grounds"].append(
            {
                "id": "path",
                "parent_id": "grass",
                "collision": "passable",
                "base_visual": deepcopy(town_tileset["grounds"][0]["base_visual"]),
                "boundaries": [],
            }
        )
        source["grounds"][0][4] = "path"
        codes = {item.code for item in validate_map_source(source, town_tileset)}
        self.assertIn("map_edge_not_base_ground", codes)
        preview = resolve_map(
            source,
            town_tileset,
            permitted_error_codes=frozenset(("map_edge_not_base_ground",)),
        )
        self.assertEqual(preview["ground_cells"][4]["layers"][-1]["ground_id"], "path")

        with self.assertRaisesRegex(ValueError, "幅16"):
            initial_map_source("too_small", town_tileset, "town", 15, 15)

        mismatch = initial_map_source("wrong_profile", town_tileset, "dungeon", 16, 15)
        self.assertIn(
            "profile_mismatch",
            {item.code for item in validate_map_source(mismatch, town_tileset)},
        )
        with self.assertRaisesRegex(ValueError, "高さ15"):
            initial_map_source("too_short", town_tileset, "town", 16, 14)

    def test_validates_and_compiles_actors_and_event_triggers(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["grounds"][2][3] = "plain"
        source["actors"] = [
            {
                "id": "elder",
                "position": [2, 2],
                "kind": "stationary",
                "sprite_index": 0,
                "sprite_source": "pc",
                "facing": "down",
                "floating": True,
            }
        ]
        source["event_triggers"] = [
            {
                "id": "notice",
                "event_id": "sample.notice",
                "activations": ["step"],
                "anchor": {"kind": "cell", "position": [3, 2]},
                "offsets": [[0, 0]],
            },
            {
                "id": "talk_elder",
                "event_id": "sample.talk_elder",
                "activations": ["touch", "interact"],
                "anchor": {"kind": "actor", "actor_id": "elder"},
                "offsets": [[0, 0]],
            },
        ]

        diagnostics = validate_map_source(source, self.tileset)
        resolved = resolve_map(source, self.tileset)
        compiled = compile_map(
            source, self.tileset, self.image_path, self.palette_path
        )

        self.assertEqual(
            [item for item in diagnostics if item.severity == "error"], []
        )
        self.assertEqual(resolved["actors"], source["actors"])
        self.assertEqual(
            resolved["event_triggers"][0]["target"],
            {"kind": "cells", "cells": [[3, 2]]},
        )
        self.assertEqual(
            resolved["event_triggers"][1]["target"],
            {"kind": "actor", "actor_id": "elder", "offsets": [[0, 0]]},
        )
        self.assertEqual(compiled.runtime["actors"], source["actors"])

    def test_rejects_invalid_actor_sprite_sources(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["actors"] = [
            {
                "id": "elder",
                "position": [2, 2],
                "kind": "stationary",
                "sprite_index": 0,
                "sprite_source": "unknown",
                "facing": "down",
            }
        ]

        codes = {item.code for item in validate_map_source(source, self.tileset)}
        self.assertIn("invalid_actor_sprite_source", codes)

        source["actors"][0].update(
            {"kind": "prop", "sprite_source": "pc"}
        )
        source["actors"][0].pop("facing")
        codes = {item.code for item in validate_map_source(source, self.tileset)}
        self.assertIn("actor_sprite_source_requires_character", codes)

    def test_rejects_invalid_or_non_character_floating(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["actors"] = [
            {
                "id": "elder",
                "position": [2, 2],
                "kind": "stationary",
                "sprite_index": 0,
                "facing": "down",
                "floating": "yes",
            }
        ]

        codes = {item.code for item in validate_map_source(source, self.tileset)}
        self.assertIn("invalid_actor_floating", codes)

        source["actors"][0].update({"kind": "prop", "floating": False})
        source["actors"][0].pop("facing")
        codes = {item.code for item in validate_map_source(source, self.tileset)}
        self.assertIn("actor_floating_requires_character", codes)

    def test_validates_and_compiles_map_bgm(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)

        self.assertEqual(source["bgm_id"], "da3-field")
        self.assertEqual(
            [
                item.code
                for item in validate_map_source(
                    source,
                    self.tileset,
                    bgm_ids={"da3-field", "da3-town"},
                )
                if item.severity == "error"
            ],
            [],
        )
        compiled = compile_map(
            source,
            self.tileset,
            self.image_path,
            self.palette_path,
        )
        self.assertEqual(compiled.runtime["bgm_id"], "da3-field")

        source["bgm_id"] = "missing"
        self.assertIn(
            "unknown_bgm",
            {
                item.code
                for item in validate_map_source(
                    source,
                    self.tileset,
                    bgm_ids={"da3-field", "da3-town"},
                )
            },
        )

    def test_rejects_invalid_actor_and_overlapping_actor_triggers(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["actors"] = [
            {
                "id": "elder",
                "position": [0, 0],
                "kind": "stationary",
                "sprite_index": 0,
                "facing": "down",
            }
        ]
        source["event_triggers"] = [
            {
                "id": f"talk_{number}",
                "event_id": f"sample.talk_{number}",
                "activations": ["interact"],
                "anchor": {"kind": "actor", "actor_id": "elder"},
                "offsets": [[0, 0]],
            }
            for number in (1, 2)
        ]

        codes = {item.code for item in validate_map_source(source, self.tileset)}

        self.assertIn("actor_on_blocked_cell", codes)
        self.assertIn("overlapping_event_trigger", codes)

    def test_prop_actor_uses_a_sheet_index_and_rejects_facing_or_legacy_appearance(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        prop = {
            "id": "treasure_1",
            "position": [2, 2],
            "kind": "prop",
            "sprite_index": 0,
        }
        source["actors"] = [prop]
        source["event_triggers"] = [
            {
                "id": "open_treasure",
                "event_id": "sample.open_treasure",
                "activations": ["touch", "interact"],
                "anchor": {"kind": "actor", "actor_id": "treasure_1"},
                "offsets": [[0, 0]],
            }
        ]

        self.assertEqual(
            [
                item
                for item in validate_map_source(source, self.tileset)
                if item.severity == "error"
            ],
            [],
        )

        prop["facing"] = "down"
        prop["appearance_id"] = "treasure"
        codes = {item.code for item in validate_map_source(source, self.tileset)}
        self.assertIn("prop_actor_has_facing", codes)
        self.assertIn("deprecated_actor_appearance_id", codes)

    def test_requires_one_fixed_touch_interact_trigger_per_actor(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["actors"] = [
            {
                "id": "elder",
                "position": [2, 2],
                "kind": "stationary",
                "sprite_index": 0,
                "facing": "down",
            }
        ]

        codes = {item.code for item in validate_map_source(source, self.tileset)}
        self.assertIn("missing_actor_trigger", codes)

        source["event_triggers"] = [
            {
                "id": "talk_elder",
                "event_id": "sample.talk_elder",
                "activations": ["touch"],
                "anchor": {"kind": "actor", "actor_id": "elder"},
                "offsets": [[1, 0]],
            }
        ]
        codes = {item.code for item in validate_map_source(source, self.tileset)}
        self.assertIn("invalid_actor_trigger_activations", codes)
        self.assertIn("invalid_actor_trigger_offsets", codes)

        source["event_triggers"][0].update(
            {
                "activations": ["touch", "interact"],
                "offsets": [[0, 0]],
            }
        )
        self.assertEqual(
            [
                item
                for item in validate_map_source(source, self.tileset)
                if item.severity == "error"
            ],
            [],
        )

    def test_treasure_actor_requires_typed_contents_and_no_event_trigger(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["actors"] = [
            {
                "id": "entrance_potion",
                "position": [2, 2],
                "kind": "treasure",
                "contents": {"type": "item", "item_key": "POTION"},
            }
        ]

        self.assertEqual(
            [
                item
                for item in validate_map_source(
                    source,
                    self.tileset,
                    item_keys={"POTION"},
                )
                if item.severity == "error"
            ],
            [],
        )
        source["actors"][0]["contents"]["item_key"] = "UNKNOWN"
        codes = {
            item.code
            for item in validate_map_source(
                source,
                self.tileset,
                item_keys={"POTION"},
            )
        }
        self.assertIn("unknown_treasure_item_key", codes)

    def test_treasure_actor_rejects_sprite_facing_and_event_trigger(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["actors"] = [
            {
                "id": "gold_chest",
                "position": [2, 2],
                "kind": "treasure",
                "sprite_index": 0,
                "facing": "down",
                "contents": {"type": "gold", "amount": 100},
            }
        ]
        source["event_triggers"] = [
            {
                "id": "open_gold_chest",
                "event_id": "sample.open_gold_chest",
                "activations": ["touch", "interact"],
                "anchor": {"kind": "actor", "actor_id": "gold_chest"},
                "offsets": [[0, 0]],
            }
        ]

        codes = {item.code for item in validate_map_source(source, self.tileset)}

        self.assertIn("treasure_actor_has_sprite_index", codes)
        self.assertIn("treasure_actor_has_facing", codes)
        self.assertIn("treasure_actor_has_event_trigger", codes)

    def test_rejects_standalone_interact_trigger(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["event_triggers"] = [
            {
                "id": "inspect_cell",
                "event_id": "sample.inspect_cell",
                "activations": ["interact"],
                "anchor": {"kind": "cell", "position": [2, 2]},
                "offsets": [[0, 0]],
            }
        ]

        codes = {item.code for item in validate_map_source(source, self.tileset)}

        self.assertIn("interact_requires_actor_anchor", codes)

    def test_resolves_object_anchored_site_and_arrival_point(self) -> None:
        tileset = deepcopy(self.tileset)
        tileset["objects"] = [
            {
                "id": "town",
                "size": [2, 2],
                "default_draw_group": "object",
                "cells": [
                    {
                        "offset": [x, y],
                        "collision": "passable",
                        "tile": [x, y],
                    }
                    for y in range(2)
                    for x in range(2)
                ],
            }
        ]
        source = initial_map_source("test_world", tileset, "world", 16, 15)
        for x, y in ((1, 1), (2, 2), (3, 2), (2, 3), (3, 3)):
            source["grounds"][y][x] = "plain"
        source["objects"] = [
            {
                "id": "town_1",
                "definition_id": "town",
                "origin": [2, 2],
                "order": 0,
            }
        ]
        source["arrival_points"] = [
            {
                "id": "from_port",
                "position": [1, 1],
                "facing": "right",
                "teleport_enabled": True,
                "site_id": "sample_town",
            }
        ]
        source["sites"] = [
            {
                "id": "sample_town",
                "anchor": {"kind": "object", "object_id": "town_1"},
                "entrance_offsets": [[0, 0], [1, 0], [0, 1], [1, 1]],
                "destination": {
                    "map_id": "sample_town",
                    "arrival_id": "from_world",
                },
            }
        ]

        diagnostics = validate_map_source(source, tileset)
        resolved = resolve_map(source, tileset)
        compiled = compile_map(source, tileset, self.image_path, self.palette_path)

        self.assertEqual(
            [item for item in diagnostics if item.severity == "error"],
            [],
        )
        expected_site = {
            "id": "sample_town",
            "name_text_key": "location.sample_town",
            "entrance_cells": [[2, 2], [3, 2], [2, 3], [3, 3]],
            "destination": {"map_id": "sample_town", "arrival_id": "from_world"},
        }
        self.assertEqual(resolved["sites"], [expected_site])
        self.assertEqual(compiled.runtime["sites"], [expected_site])
        self.assertEqual(compiled.runtime["arrival_points"], source["arrival_points"])

    def test_allows_unnamed_move_source_on_dungeon_map(self) -> None:
        tileset = initial_tileset(
            "dungeon",
            "mapchips/dungeon",
            "dungeon",
            "floor",
            "passable",
        )
        source = initial_map_source("sample_dungeon", tileset, "dungeon", 16, 15)
        source["sites"] = [
            {
                "id": "exit_to_world",
                "anchor": {"kind": "cell", "position": [2, 2]},
                "entrance_offsets": [[0, 0]],
                "destination": {
                    "map_id": "worldmap",
                    "arrival_id": "sample_dungeon_world",
                },
            }
        ]

        diagnostics = validate_map_source(source, tileset)
        resolved = resolve_map(source, tileset)

        self.assertEqual(
            [item for item in diagnostics if item.severity == "error"],
            [],
        )
        self.assertEqual(resolved["sites"][0]["id"], "exit_to_world")
        self.assertEqual(resolved["sites"][0]["entrance_cells"], [[2, 2]])

    def test_rejects_invalid_site_cells_and_missing_anchor(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["sites"] = [
            {
                "id": "bad_site",
                "anchor": {"kind": "object", "object_id": "missing_1"},
                "entrance_offsets": [[0, 0], [0, 0]],
                "destination": {"map_id": "bad_site", "arrival_id": "from_world"},
            }
        ]
        source["arrival_points"] = [
            {
                "id": "blocked",
                "position": [0, 0],
                "facing": "north",
                "teleport_enabled": "yes",
            }
        ]

        codes = {item.code for item in validate_map_source(source, self.tileset)}

        self.assertIn("unknown_site_anchor_object", codes)
        self.assertIn("duplicate_site_entrance_offset", codes)
        self.assertIn("invalid_facing", codes)
        self.assertIn("invalid_arrival_teleport_enabled", codes)
        self.assertIn("arrival_point_blocked", codes)

    def test_reports_unselected_and_invalid_destinations_for_list_fields(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["sites"] = [
            {
                "id": "sample_site",
                "anchor": {"kind": "cell", "position": [2, 2]},
                "entrance_offsets": [[0, 0]],
                "destination": {"map_id": "", "arrival_id": ""},
            }
        ]

        diagnostics = validate_map_source(source, self.tileset)
        messages = {item.code: item.message for item in diagnostics}

        self.assertEqual(
            messages["missing_destination_map_id"],
            "移動先マップを選択してください。",
        )
        self.assertEqual(
            messages["missing_destination_arrival_id"],
            "移動先到着地点を選択してください。",
        )

        source["sites"][0]["destination"] = {
            "map_id": "BAD MAP",
            "arrival_id": "BAD ARRIVAL",
        }
        diagnostics = validate_map_source(source, self.tileset)
        messages = {item.code: item.message for item in diagnostics}

        self.assertEqual(
            messages["invalid_destination_map_id"],
            "移動先マップIDが不正です。一覧から選択し直してください。",
        )
        self.assertEqual(
            messages["invalid_destination_arrival_id"],
            "移動先到着地点IDが不正です。一覧から選択し直してください。",
        )

    def test_validates_site_destinations_across_maps(self) -> None:
        world = initial_map_source("test_world", self.tileset, "world", 16, 15)
        world["grounds"][2][2] = "plain"
        world["arrival_points"] = [
            {
                "id": "sample_town_world",
                "position": [2, 2],
                "facing": "down",
                "teleport_enabled": True,
                "site_id": "sample_town",
            }
        ]
        world["sites"] = [
            {
                "id": "sample_town",
                "anchor": {"kind": "cell", "position": [2, 2]},
                "entrance_offsets": [[0, 0]],
                "destination": {
                    "map_id": "sample_town",
                    "arrival_id": "from_world",
                },
            }
        ]

        missing_map = validate_map_links({"test_world": world})
        self.assertEqual(missing_map[0].code, "missing_destination_map")
        self.assertEqual(missing_map[0].severity, "warning")

        town = initial_map_source("sample_town", self.tileset, "town", 16, 15)
        missing_spawn = validate_map_links(
            {"test_world": world, "sample_town": town}
        )
        self.assertEqual(missing_spawn[0].code, "missing_destination_arrival")
        self.assertEqual(missing_spawn[0].severity, "error")

        town["grounds"][2][2] = "plain"
        town["arrival_points"] = [
            {
                "id": "from_world",
                "position": [2, 2],
                "facing": "down",
                "teleport_enabled": False,
                "site_id": None,
            }
        ]
        self.assertEqual(
            validate_map_links({"test_world": world, "sample_town": town}),
            [],
        )

        same_world = deepcopy(world)
        same_world["sites"][0]["destination"] = {
            "map_id": "test_world",
            "arrival_id": "sample_town_world",
        }
        self.assertEqual(validate_map_links({"test_world": same_world}), [])

    def test_reports_global_site_id_collision_for_every_owning_map(self) -> None:
        first = initial_map_source("first_world", self.tileset, "world", 16, 15)
        second = initial_map_source("second_world", self.tileset, "world", 16, 15)
        for source in (first, second):
            source["grounds"][2][2] = "plain"
            source["arrival_points"] = [
                {
                    "id": "shared_site_world",
                    "position": [2, 2],
                    "facing": "down",
                    "teleport_enabled": True,
                    "site_id": "shared_site",
                }
            ]
            source["sites"] = [
                {
                    "id": "shared_site",
                    "anchor": {"kind": "cell", "position": [2, 2]},
                    "entrance_offsets": [[0, 0]],
                    "destination": {
                        "map_id": "missing_map",
                        "arrival_id": "from_world",
                    },
                }
            ]

        diagnostics = validate_map_links(
            {"first_world": first, "second_world": second}
        )
        duplicate_paths = {
            item.path
            for item in diagnostics
            if item.code == "duplicate_global_site_id"
        }

        self.assertEqual(
            duplicate_paths,
            {"first_world.sites[0].id", "second_world.sites[0].id"},
        )

    def test_nonworld_move_source_is_not_a_global_or_teleport_site(self) -> None:
        world = initial_map_source("test_world", self.tileset, "world", 16, 15)
        world["grounds"][2][2] = "plain"
        world["sites"] = [
            {
                "id": "shared_id",
                "anchor": {"kind": "cell", "position": [2, 2]},
                "entrance_offsets": [[0, 0]],
                "destination": {"map_id": "dungeon", "arrival_id": "from_world"},
            }
        ]
        dungeon = initial_map_source("dungeon", self.tileset, "dungeon", 16, 15)
        dungeon["grounds"][2][2] = "plain"
        dungeon["arrival_points"] = [
            {
                "id": "from_world",
                "position": [2, 2],
                "facing": "down",
                "teleport_enabled": False,
                "site_id": None,
            }
        ]
        dungeon["sites"] = [
            {
                "id": "shared_id",
                "anchor": {"kind": "cell", "position": [2, 2]},
                "entrance_offsets": [[0, 0]],
                "destination": {"map_id": "test_world", "arrival_id": "return"},
            },
            {
                "id": "local_exit_only",
                "anchor": {"kind": "cell", "position": [3, 2]},
                "entrance_offsets": [[0, 0]],
                "destination": {"map_id": "test_world", "arrival_id": "return"},
            },
        ]
        world["arrival_points"] = [
            {
                "id": "return",
                "position": [3, 2],
                "facing": "down",
                "teleport_enabled": True,
                "site_id": "local_exit_only",
            }
        ]

        diagnostics = validate_map_links({"test_world": world, "dungeon": dungeon})

        codes = {item.code for item in diagnostics}
        self.assertNotIn("duplicate_global_site_id", codes)
        self.assertIn("unknown_arrival_site_id", codes)

    def test_validates_teleport_arrival_site_links(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["grounds"][2][3] = "plain"
        source["sites"] = [
            {
                "id": "sample_town",
                "anchor": {"kind": "cell", "position": [2, 2]},
                "entrance_offsets": [[0, 0]],
                "destination": {
                    "map_id": "test_world",
                    "arrival_id": "sample_town_world",
                },
            }
        ]
        source["arrival_points"] = [
            {
                "id": "sample_town_world",
                "position": [2, 2],
                "facing": "down",
                "teleport_enabled": True,
                "site_id": "unknown_site",
            },
            {
                "id": "sample_town_world_2",
                "position": [3, 2],
                "facing": "down",
                "teleport_enabled": True,
                "site_id": "unknown_site",
            },
        ]

        codes = {item.code for item in validate_map_links({"test_world": source})}

        self.assertIn("unknown_arrival_site_id", codes)
        self.assertIn("duplicate_site_teleport_arrival", codes)

    def test_validates_event_and_moved_actor_links_for_each_map(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["event_triggers"] = [
            {
                "id": "meeting",
                "event_id": "sample.meeting",
                "activations": ["interact"],
                "anchor": {"kind": "cell", "position": [2, 2]},
                "offsets": [[0, 0]],
            }
        ]
        events = {
            "sample.meeting": {
                "commands": [
                    {
                        "command": "branch",
                        "condition": {"type": "flag_set", "flag_id": "sample.met"},
                        "then": [
                            {
                                "command": "move_actor",
                                "actor_id": "elder",
                                "direction": "left",
                                "steps": 1,
                            }
                        ],
                        "else": [],
                    }
                ]
            }
        }

        codes = {
            item.code
            for item in validate_map_event_links({"test_world": source}, events)
        }

        self.assertIn("unknown_event_actor_id", codes)
        source["actors"] = [
            {
                "id": "elder",
                "position": [2, 2],
                "kind": "stationary",
                "sprite_index": 0,
                "facing": "down",
            }
        ]
        self.assertNotIn(
            "unknown_event_actor_id",
            {
                item.code
                for item in validate_map_event_links({"test_world": source}, events)
            },
        )
        source["actors"][0]["kind"] = "prop"
        del source["actors"][0]["facing"]
        self.assertIn(
            "immovable_event_actor",
            {
                item.code
                for item in validate_map_event_links({"test_world": source}, events)
            },
        )

    def test_rejects_non_sea_world_edge_and_duplicate_object_origin(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][0][1] = "plain"
        source["objects"] = [
            {"id": "rock_1", "definition_id": "rock", "origin": [2, 2], "order": 0},
            {"id": "rock_2", "definition_id": "rock", "origin": [2, 2], "order": 1},
        ]

        codes = {item.code for item in validate_map_source(source, self.tileset)}

        self.assertIn("map_edge_not_base_ground", codes)
        self.assertIn("duplicate_object_origin", codes)

    def test_allows_object_overlap_when_origins_differ_and_combines_collision(self) -> None:
        tileset = deepcopy(self.tileset)
        tileset["objects"][0]["size"] = [2, 1]
        tileset["objects"][0]["cells"] = [
            {"offset": [0, 0], "collision": "blocked", "tile": [0, 0]},
            {"offset": [1, 0], "collision": "passable", "tile": [1, 0]},
        ]
        source = initial_map_source("test_world", tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["grounds"][2][3] = "plain"
        source["grounds"][2][4] = "plain"
        source["objects"] = [
            {"id": "rock_1", "definition_id": "rock", "origin": [2, 2], "order": 0},
            {"id": "rock_2", "definition_id": "rock", "origin": [3, 2], "order": 1},
        ]

        resolved = resolve_map(source, tileset)

        self.assertEqual(len(resolved["object_cells"]), 4)
        self.assertTrue(resolved["collision"][2 * 16 + 2])
        self.assertTrue(resolved["collision"][2 * 16 + 3])
        self.assertFalse(resolved["collision"][2 * 16 + 4])

    def test_object_cells_share_one_weighted_visual_choice(self) -> None:
        tileset = deepcopy(self.tileset)
        left_visual = {
            "frame_interval": 4,
            "choices": [
                {"id": "default", "weight": 1, "frames": [{"tile": [0, 0]}]},
                {"id": "variant", "weight": 1, "frames": [{"tile": [0, 1]}]},
            ],
        }
        right_visual = deepcopy(left_visual)
        right_visual["choices"][0]["frames"][0]["tile"] = [1, 0]
        right_visual["choices"][1]["frames"][0]["tile"] = [1, 1]
        tileset["objects"][0]["size"] = [2, 1]
        tileset["objects"][0]["cells"] = [
            {"offset": [0, 0], "collision": "passable", "visual": left_visual},
            {"offset": [1, 0], "collision": "passable", "visual": right_visual},
        ]
        source = initial_map_source("test_world", tileset, "world", 16, 15)
        source["objects"] = [
            {"id": "rocks_1", "definition_id": "rock", "origin": [2, 2], "order": 0}
        ]

        resolved = resolve_map(source, tileset)
        cells = resolved["object_cells"]

        self.assertEqual([cell["choice_id"] for cell in cells], [cells[0]["choice_id"]] * 2)
        self.assertIn(
            [cell["frames"][0] for cell in cells],
            [[[0, 0], [1, 0]], [[0, 1], [1, 1]]],
        )

    def test_draws_object_with_lower_bottom_edge_in_front_regardless_of_order(self) -> None:
        tileset = deepcopy(self.tileset)
        tileset["objects"][0]["size"] = [2, 2]
        tileset["objects"][0]["cells"] = [
            {"offset": [0, 0], "collision": "passable", "tile": [0, 0]},
            {"offset": [1, 0], "collision": "passable", "tile": [1, 0]},
            {"offset": [0, 1], "collision": "passable", "tile": [0, 1]},
            {"offset": [1, 1], "collision": "passable", "tile": [1, 1]},
        ]
        source = initial_map_source("test_world", tileset, "world", 16, 15)
        source["objects"] = [
            {"id": "rock_upper", "definition_id": "rock", "origin": [2, 1], "order": 100},
            {"id": "rock_lower", "definition_id": "rock", "origin": [2, 2], "order": -100},
        ]

        resolved = resolve_map(source, tileset)
        overlapping = [
            cell["instance_id"]
            for cell in resolved["object_cells"]
            if cell["position"] == [2, 2]
        ]

        self.assertEqual(overlapping, ["rock_upper", "rock_lower"])

    def test_overlay_draws_in_front_and_overrides_blocked_collision(self) -> None:
        tileset = deepcopy(self.tileset)
        tileset["objects"][0] = {
            "id": "mountain",
            "size": [2, 3],
            "default_draw_group": "object",
            "cells": [{"offset": [1, 1], "collision": "blocked", "tile": [0, 0]}],
        }
        tileset["objects"].append({
            "id": "entrance",
            "size": [1, 1],
            "default_draw_group": "object_overlay",
            "cells": [{"offset": [0, 0], "collision": "passable_override", "tile": [1, 0]}],
        })
        source = initial_map_source("test_world", tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["objects"] = [
            {"id": "mountain_1", "definition_id": "mountain", "origin": [1, 1], "order": 100},
            {"id": "entrance_1", "definition_id": "entrance", "origin": [2, 2], "order": -100},
        ]

        resolved = resolve_map(source, tileset)
        overlapping = [
            cell["instance_id"]
            for cell in resolved["object_cells"]
            if cell["position"] == [2, 2]
        ]

        self.assertEqual(overlapping, ["mountain_1", "entrance_1"])
        self.assertFalse(resolved["collision"][2 * 16 + 2])
        self.assertNotIn(
            "passable_override_without_blocked_object",
            {item.code for item in validate_map_source(source, tileset)},
        )
        compiled = compile_map(source, tileset, self.image_path, self.palette_path)
        self.assertEqual(
            [cell["instance_id"] for cell in compiled.runtime["object_tiles"]],
            ["mountain_1", "entrance_1"],
        )
        self.assertEqual(compiled.runtime["collision_rows"][2][2], "0")

        tileset["objects"][1]["cells"][0]["collision"] = "passable"
        self.assertTrue(resolve_map(source, tileset)["collision"][2 * 16 + 2])

    def test_foreground_is_resolved_after_overlay(self) -> None:
        tileset = deepcopy(self.tileset)
        tileset["objects"] = [
            {
                "id": draw_group,
                "size": [1, 1],
                "default_draw_group": draw_group,
                "cells": [
                    {
                        "offset": [0, 0],
                        "collision": "passable",
                        "tile": [index, 0],
                    }
                ],
            }
            for index, draw_group in enumerate(
                ("object", "object_overlay", "object_foreground")
            )
        ]
        source = initial_map_source("test_world", tileset, "world", 16, 15)
        source["objects"] = [
            {
                "id": f"{draw_group}_1",
                "definition_id": draw_group,
                "origin": [2 + index, 2],
                "order": 0,
            }
            for index, draw_group in enumerate(
                ("object_foreground", "object_overlay", "object")
            )
        ]

        resolved = resolve_map(source, tileset)

        self.assertEqual(
            [cell["draw_group"] for cell in resolved["object_cells"]],
            ["object", "object_overlay", "object_foreground"],
        )

    def test_warns_when_passable_override_has_no_blocked_object_below(self) -> None:
        tileset = deepcopy(self.tileset)
        tileset["objects"].append({
            "id": "entrance",
            "size": [1, 1],
            "default_draw_group": "object_overlay",
            "cells": [{"offset": [0, 0], "collision": "passable_override", "tile": [1, 0]}],
        })
        source = initial_map_source("test_world", tileset, "world", 16, 15)
        source["objects"] = [
            {"id": "entrance_1", "definition_id": "entrance", "origin": [2, 2], "order": 0}
        ]

        warnings = {item.code for item in validate_map_source(source, tileset) if item.severity == "warning"}

        self.assertIn("passable_override_without_blocked_object", warnings)

    def test_compiles_rules_and_choices_to_runtime_atlas(self) -> None:
        source = initial_map_source("test_world", self.tileset, "world", 16, 15)
        source["grounds"][2][2] = "plain"
        source["objects"] = [
            {"id": "rock_1", "definition_id": "rock", "origin": [2, 2], "order": 0}
        ]

        compiled = compile_map(source, self.tileset, self.image_path, self.palette_path)

        self.assertEqual(compiled.runtime["size"], [16, 15])
        self.assertEqual(len(compiled.runtime["ground_tiles"]), 240)
        self.assertEqual(len(compiled.runtime["object_tiles"]), 1)
        self.assertEqual(compiled.runtime["collision_rows"][2][2], "1")
        self.assertEqual(len(compiled.atlas), compiled.runtime["atlas"]["width"] * compiled.runtime["atlas"]["height"])


if __name__ == "__main__":
    unittest.main()
