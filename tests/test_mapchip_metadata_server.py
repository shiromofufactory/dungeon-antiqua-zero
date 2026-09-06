from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

from scripts.map_pipeline import (
    initial_map_source,
    initial_worldmap_tileset,
    load_map_source,
    load_tileset,
    save_map_source,
    save_tileset,
)
from tools.mapchip_metadata.server import MetadataApplication, create_server


class MapchipMetadataServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.content_root = Path(self.temporary.name)
        image_path = self.content_root / "images" / "mapchips" / "worldmap.png"
        image_path.parent.mkdir(parents=True)
        Image.new("RGBA", (64, 96), (0, 0, 0, 0)).save(image_path)
        Image.new("RGBA", (64, 96), (0, 0, 0, 0)).save(
            image_path.with_name("alternate.png")
        )
        metadata_path = self.content_root / "maps" / "tilesets" / "worldmap.json"
        save_tileset(metadata_path, initial_worldmap_tileset())

        self.application = MetadataApplication(
            self.content_root,
            "worldmap",
            token="test-token",
            runtime_root=self.content_root / "runtime",
        )
        self.server = create_server(self.application, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def get_json(self, path: str, headers: dict[str, str] | None = None) -> dict:
        request = Request(f"{self.base_url}{path}", headers=headers or {})
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read())

    def post_json(self, path: str, value: dict) -> dict:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(value).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Mapchip-Token": "test-token",
            },
        )
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read())

    def test_serves_document_and_requires_token(self) -> None:
        payload = self.get_json("/api/document?token=test-token")
        self.assertEqual(payload["data"]["tileset_id"], "worldmap")
        self.assertEqual(payload["image_info"]["columns"], 4)

        with self.assertRaises(HTTPError) as context:
            self.get_json("/api/document")
        self.assertEqual(context.exception.code, 403)

    def test_source_tiles_show_usage_category_and_unused_state(self) -> None:
        with urlopen(f"{self.base_url}/?token=test-token", timeout=2) as response:
            page = response.read().decode("utf-8")
        with urlopen(f"{self.base_url}/app.js", timeout=2) as response:
            script = response.read().decode("utf-8")

        self.assertIn('id="usage-summary"', page)
        self.assertIn('class="usage-dot ground"', page)
        self.assertIn('class="usage-dot boundary"', page)
        self.assertIn('class="usage-dot object"', page)
        self.assertIn('class="usage-dot unused"', page)
        self.assertIn('id="save-button" class="button primary" type="button" disabled', page)
        self.assertIn('byId("save-button").disabled = !canSave()', script)
        self.assertIn('if (!canSave()) return;', script)
        self.assertIn("function sourceTileUsage()", script)
        self.assertIn("function drawSourceUsage(context, zoom)", script)
        self.assertIn('addVisualUsage(usage, ground.base_visual, "ground")', script)
        self.assertIn('addVisualUsage(usage, boundary.visual, "boundary")', script)
        self.assertIn('addVisualUsage(usage, cell.visual, "object")', script)

    def test_ground_and_object_definitions_are_drag_reorderable(self) -> None:
        with urlopen(f"{self.base_url}/app.js", timeout=2) as response:
            script = response.read().decode("utf-8")

        self.assertIn('data-reorder-kind="${reorderKind}"', script)
        self.assertIn('index === baseIndex ? "" : "reorderable"', script)
        self.assertIn("function reorderDefinitions(kind, fromIndex, insertionIndex)", script)
        self.assertIn('const minimumIndex = kind === "ground" ? 1 : 0', script)
        self.assertIn("state.objectOrigins.splice(fromIndex, 1)", script)
        self.assertIn('addEventListener("pointerdown", handleDefinitionPointerDown)', script)
        self.assertIn('addEventListener("pointermove", handleDefinitionPointerMove)', script)
        self.assertIn("finishDefinitionPointerDrag(event)", script)

    def test_renews_session_token_only_for_browser_ui(self) -> None:
        with self.assertRaises(HTTPError) as context:
            self.get_json("/api/session-token")
        self.assertEqual(context.exception.code, 403)

        payload = self.get_json(
            "/api/session-token",
            headers={"X-Mapchip-Client": "mapchip-metadata-ui"},
        )
        self.assertEqual(payload["token"], "test-token")

    def test_validates_and_saves_document(self) -> None:
        data = initial_worldmap_tileset()
        data["grounds"][0]["base_visual"]["frame_interval"] = 12

        validation = self.post_json("/api/validate", {"data": data})
        self.assertFalse(validation["saved"])
        self.assertFalse(any(item["severity"] == "error" for item in validation["diagnostics"]))

        result = self.post_json("/api/save", {"data": data})
        self.assertTrue(result["saved"])
        saved = json.loads(self.application.metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["grounds"][0]["base_visual"]["frame_interval"], 12)

    def test_lists_and_creates_tileset_with_shared_source_image(self) -> None:
        catalog = self.get_json("/api/catalog?token=test-token")
        self.assertEqual(
            [item["image_id"] for item in catalog["source_images"]],
            ["mapchips/alternate", "mapchips/worldmap"],
        )
        self.assertEqual(catalog["tilesets"][0]["profile"], "world")

        created = self.post_json(
            "/api/create",
            {
                "tileset_id": "village",
                "source_image_id": "mapchips/worldmap",
                "profile": "town",
                "base_ground_id": "grass",
                "base_collision": "passable",
            },
        )
        self.assertTrue(created["is_new"])
        self.assertEqual(created["data"]["profile"], "town")
        self.assertEqual(created["data"]["grounds"][0]["id"], "grass")
        with urlopen(f"{self.base_url}{created['image_url']}", timeout=2) as response:
            self.assertEqual(response.headers.get_content_type(), "image/png")
            self.assertTrue(response.read().startswith(b"\x89PNG\r\n\x1a\n"))

        saved = self.post_json("/api/save", {"data": created["data"]})
        self.assertTrue(saved["saved"])
        reopened = self.get_json(
            "/api/document?tileset=village&token=test-token"
        )
        self.assertEqual(reopened["data"]["source_image_id"], "mapchips/worldmap")

    def test_reports_base_profile_and_source_changes(self) -> None:
        data = initial_worldmap_tileset()
        changed_base = json.loads(json.dumps(data))
        changed_base["grounds"][0]["id"] = "ocean"
        base_result = self.post_json("/api/save", {"data": changed_base})
        self.assertIn(
            "base_ground_is_immutable",
            {item["code"] for item in base_result["diagnostics"]},
        )

        changed_profile = json.loads(json.dumps(data))
        changed_profile["profile"] = "town"
        profile_result = self.post_json("/api/save", {"data": changed_profile})
        self.assertIn(
            "profile_is_immutable",
            {item["code"] for item in profile_result["diagnostics"]},
        )

        changed_source = json.loads(json.dumps(data))
        changed_source["source_image_id"] = "mapchips/alternate"
        source_result = self.post_json("/api/save", {"data": changed_source})
        self.assertIn(
            "source_image_is_immutable",
            {item["code"] for item in source_result["diagnostics"]},
        )

    def test_renames_object_references_in_all_maps_using_tileset(self) -> None:
        tileset = initial_worldmap_tileset()
        tileset["objects"] = [
            {
                "id": "w1",
                "size": [1, 1],
                "default_draw_group": "object",
                "cells": [
                    {
                        "offset": [0, 0],
                        "collision": "blocked",
                        "tile": [0, 0],
                    }
                ],
            }
        ]
        save_tileset(self.application.metadata_path, tileset)
        source_root = self.content_root / "maps" / "sources"
        for map_id in ("forest_a", "forest_b"):
            source = initial_map_source(map_id, tileset, "world", 16, 15)
            source["objects"] = [
                {
                    "id": f"{map_id}_object",
                    "definition_id": "w1",
                    "origin": [2, 2],
                    "order": 0,
                }
            ]
            save_map_source(source_root / f"{map_id}.json", source)

        renamed = json.loads(json.dumps(tileset))
        renamed["objects"][0]["id"] = "wu1"
        result = self.post_json(
            "/api/save",
            {"data": renamed, "object_id_renames": {"w1": "wu1"}},
        )

        self.assertTrue(result["saved"])
        self.assertEqual(result["updated_map_ids"], ["forest_a", "forest_b"])
        for map_id in ("forest_a", "forest_b"):
            saved_map = json.loads(
                (source_root / f"{map_id}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(saved_map["objects"][0]["definition_id"], "wu1")

    def test_regenerates_referencing_map_after_draw_group_change(self) -> None:
        tileset = initial_worldmap_tileset()
        tileset["objects"] = [
            {
                "id": "roof",
                "size": [1, 1],
                "default_draw_group": "object",
                "cells": [
                    {
                        "offset": [0, 0],
                        "collision": "passable",
                        "tile": [0, 0],
                    }
                ],
            }
        ]
        save_tileset(self.application.metadata_path, tileset)
        source = initial_map_source("forest", tileset, "world", 16, 15)
        source["objects"] = [
            {
                "id": "roof_1",
                "definition_id": "roof",
                "origin": [2, 2],
                "order": 0,
            }
        ]
        save_map_source(
            self.content_root / "maps" / "sources" / "forest.json",
            source,
        )

        first = self.post_json("/api/save", {"data": tileset})
        runtime_path = self.application.runtime_root / "forest.json"
        self.assertEqual(first["generated_map_ids"], ["forest"])
        self.assertEqual(
            json.loads(runtime_path.read_text(encoding="utf-8"))["object_tiles"][0]["draw_group"],
            "object",
        )

        changed = json.loads(json.dumps(tileset))
        changed["objects"][0]["default_draw_group"] = "object_foreground"
        result = self.post_json("/api/save", {"data": changed})

        self.assertTrue(result["saved"])
        self.assertEqual(result["generated_map_ids"], ["forest"])
        self.assertEqual(
            json.loads(runtime_path.read_text(encoding="utf-8"))["object_tiles"][0]["draw_group"],
            "object_foreground",
        )

    def test_removes_placed_objects_when_their_definition_is_removed(self) -> None:
        tileset = initial_worldmap_tileset()
        tileset["objects"] = [
            {
                "id": "tree",
                "size": [1, 1],
                "default_draw_group": "object",
                "cells": [
                    {
                        "offset": [0, 0],
                        "collision": "blocked",
                        "tile": [0, 0],
                    }
                ],
            }
        ]
        save_tileset(self.application.metadata_path, tileset)
        source = initial_map_source("forest", tileset, "world", 16, 15)
        source["objects"] = [
            {
                "id": "tree_1",
                "definition_id": "tree",
                "origin": [2, 2],
                "order": 0,
            },
            {
                "id": "already_missing_1",
                "definition_id": "already_missing",
                "origin": [3, 2],
                "order": 0,
            },
        ]
        source_path = self.content_root / "maps" / "sources" / "forest.json"
        save_map_source(source_path, source)

        changed = json.loads(json.dumps(tileset))
        changed["objects"] = []
        result = self.post_json("/api/save", {"data": changed})

        self.assertTrue(result["saved"])
        self.assertEqual(result["updated_map_ids"], ["forest"])
        self.assertEqual(result["removed_map_object_count"], 1)
        self.assertEqual(
            load_map_source(source_path)["objects"],
            [
                {
                    "id": "already_missing_1",
                    "definition_id": "already_missing",
                    "origin": [3, 2],
                    "order": 0,
                }
            ],
        )
        self.assertEqual(load_tileset(self.application.metadata_path)["objects"], [])

    def test_deletes_only_unreferenced_non_world_tileset(self) -> None:
        created = self.post_json(
            "/api/create",
            {
                "tileset_id": "village",
                "source_image_id": "mapchips/worldmap",
                "profile": "town",
                "base_ground_id": "grass",
                "base_collision": "passable",
            },
        )
        self.assertTrue(self.post_json("/api/save", {"data": created["data"]})["saved"])

        source_path = self.content_root / "maps" / "sources" / "sample_village.json"
        save_map_source(
            source_path,
            initial_map_source("sample_village", created["data"], "town", 16, 15),
        )
        with self.assertRaisesRegex(ValueError, "sample_village"):
            self.application.delete_tileset("village")
        source_path.unlink()

        deleted = self.post_json("/api/delete", {"tileset_id": "village"})
        self.assertTrue(deleted["deleted"])
        self.assertFalse(self.application.metadata_path_for("village").exists())

        with self.assertRaisesRegex(ValueError, "必須タイルセット"):
            self.application.delete_tileset("worldmap")

    def test_saves_validation_errors_for_later_correction(self) -> None:
        invalid = initial_worldmap_tileset()
        invalid["grounds"][0]["collision"] = "passable"

        result = self.post_json("/api/save", {"data": invalid})

        self.assertTrue(result["saved"])
        self.assertIn(
            "invalid_world_ground_collision",
            {item["code"] for item in result["diagnostics"]},
        )
        self.assertEqual(
            load_tileset(self.application.metadata_path)["grounds"][0]["collision"],
            "passable",
        )


if __name__ == "__main__":
    unittest.main()
