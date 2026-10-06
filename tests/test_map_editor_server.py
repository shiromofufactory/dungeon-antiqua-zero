from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

from scripts.map_pipeline import (
    initial_map_source,
    initial_tileset,
    initial_worldmap_tileset,
    load_map_source,
    save_map_source,
    save_tileset,
)
from tools.map_editor.server import MapEditorApplication, create_server


class MapEditorServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        content_root = self.root / "content"
        image_path = content_root / "images" / "mapchips" / "worldmap.png"
        image_path.parent.mkdir(parents=True)
        Image.new("RGBA", (64, 96), (0, 0, 0, 255)).save(image_path)
        Image.new("RGBA", (64, 96), (0, 0, 0, 255)).save(
            image_path.with_name("village.png")
        )
        actor_image_root = content_root / "images" / "actors"
        actor_image_root.mkdir(parents=True)
        Image.new("RGB", (48, 16), (255, 0, 128)).save(
            actor_image_root / "props.png"
        )
        Image.new("P", (96, 128), 1).save(
            actor_image_root / "characters.gif"
        )
        pc_image_root = content_root / "images" / "characters"
        pc_image_root.mkdir(parents=True)
        Image.new("P", (384, 384), 1).save(pc_image_root / "ch_walk.gif")
        Image.new("RGB", (48, 16), (255, 0, 128)).save(
            actor_image_root / "treasure.png"
        )
        data_root = content_root / "data"
        data_root.mkdir(parents=True)
        (data_root / "items.json").write_text(
            json.dumps([{"name_en": "POTION", "name_ja": "きずぐすり"}]),
            encoding="utf-8",
        )
        metadata_path = content_root / "maps" / "tilesets" / "worldmap.json"
        tileset = initial_worldmap_tileset()
        save_tileset(metadata_path, tileset)
        save_tileset(
            metadata_path.with_name("village.json"),
            initial_tileset(
                "village",
                "mapchips/village",
                "town",
                "grass",
                "passable",
            ),
        )
        save_tileset(
            metadata_path.with_name("village_alt.json"),
            initial_tileset(
                "village_alt",
                "mapchips/village",
                "town",
                "floor",
                "passable",
            ),
        )
        palette_path = self.root / "palette.pyxpal"
        palette_path.write_text("000000\nFF0080\n", encoding="utf-8")
        audio_root = self.root / "app" / "audio"
        audio_root.mkdir(parents=True)
        for bgm_id in ("da3-field", "da3-town"):
            (audio_root / f"{bgm_id}.ogg").write_bytes(b"")
        self.application = MapEditorApplication(
            content_root,
            self.root / "runtime",
            "test_world",
            "worldmap",
            "world",
            16,
            15,
            palette_path=palette_path,
            token="test-token",
            audio_root=audio_root,
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

    def test_object_visibility_flags_are_listed_validated_saved_and_compiled(self) -> None:
        flags_path = self.application.content_root / "events" / "flags.json"
        flags_path.parent.mkdir(parents=True, exist_ok=True)
        flags = [{"flag_id": "story.open", "note": "扉が開いた"}]
        flags_path.write_text(json.dumps(flags), encoding="utf-8")
        tileset = self.application.load_tileset("worldmap")
        tileset["objects"] = [{"id": "rock", "size": [1, 1], "default_draw_group": "object", "cells": [{"offset": [0, 0], "collision": "blocked", "tile": [0, 0]}]}]
        save_tileset(self.application.content_root / "maps" / "tilesets" / "worldmap.json", tileset)
        payload = self.application.document_payload()
        self.assertEqual(payload["flag_options"], flags)
        data = payload["data"]
        data["objects"] = [{"id": "rock_1", "definition_id": "rock", "origin": [2, 2], "order": 0, "visibility_condition": {"flag_id": "story.open", "value": False}}]
        self.assertTrue(self.application.save(data, {})["saved"])
        self.assertEqual(self.application.document_payload()["data"]["objects"], data["objects"])
        runtime = json.loads(self.application.runtime_path.read_text(encoding="utf-8"))
        self.assertEqual(runtime["object_conditions"]["rock_1"], {"flag_id": "story.open", "value": False})
        data["objects"][0]["visibility_condition"]["flag_id"] = "story.missing"
        diagnostics, _, _ = self.application.validate(data)
        self.assertIn("unknown_flag", {issue["code"] for issue in diagnostics})
        self.assertFalse(self.application.save(data, {})["saved"])

    def test_areas_keep_independent_layouts_and_share_parent_bgm(self) -> None:
        root = self.application.document_payload()["data"]
        self.assertTrue(self.application.save(root, {})["saved"])
        area = self.post_payload("/api/create-area", {
            "parent_id": "test_world",
            "area_name": "地下2階", "width": 20, "height": 18,
        })["data"]
        area_map_id = area["map_id"]
        self.assertRegex(area_map_id, r"^test_world_area_[0-9a-f]{12}$")
        self.assertEqual(area["size"], [20, 18])
        self.assertEqual(area["area_parent_id"], "test_world")
        self.assertTrue(self.application.save(area, {})["saved"])
        self.assertIn(f"{area_map_id}がこのマップのエリア", self.application.map_delete_blockers("test_world"))
        area["bgm_id"] = "da3-town"
        self.assertIn(
            "area_shared_setting_mismatch",
            {issue["code"] for issue in self.application.validate(area)[0]},
        )
        root["bgm_id"] = "da3-town"
        self.assertTrue(self.application.save(root, {})["saved"])
        self.assertEqual(
            load_map_source(self.application.source_path_for(area_map_id))["bgm_id"],
            "da3-town",
        )
        alternate = initial_worldmap_tileset()
        alternate["tileset_id"] = "world_alt"
        save_tileset(self.application.content_root / "maps" / "tilesets" / "world_alt.json", alternate)
        reset = self.application.change_tileset_document_payload("test_world", "world_alt")["data"]
        self.assertTrue(self.application.save(reset, {})["saved"])
        saved_area = load_map_source(self.application.source_path_for(area_map_id))
        self.assertEqual(saved_area["tileset_id"], "world_alt")
        self.assertEqual(saved_area["size"], [20, 18])
        self.assertEqual(saved_area["area_name"], "地下2階")

    def test_new_area_id_retries_when_generated_id_is_already_saved(self) -> None:
        root = self.application.document_payload()["data"]
        self.assertTrue(self.application.save(root, {})["saved"])
        with patch("tools.map_editor.server.secrets.token_hex", return_value="012345abcdef"):
            first = self.application.create_area_document_payload(
                "test_world", "地下1階", 16, 15,
            )["data"]
        self.assertEqual(first["map_id"], "test_world_area_012345abcdef")
        self.assertTrue(self.application.save(first, {})["saved"])
        with patch(
            "tools.map_editor.server.secrets.token_hex",
            side_effect=["012345abcdef", "fedcba543210"],
        ):
            second = self.application.create_area_document_payload(
                "test_world", "地下2階", 16, 15,
            )["data"]
        self.assertEqual(second["map_id"], "test_world_area_fedcba543210")

    def test_dungeon_area_encounters_are_independent(self) -> None:
        tileset = initial_tileset(
            "cave", "mapchips/village", "dungeon", "floor", "passable",
        )
        save_tileset(self.application.content_root / "maps" / "tilesets" / "cave.json", tileset)
        root = initial_map_source("cave", tileset, "dungeon", 16, 15)
        self.assertTrue(self.application.save(root, {})["saved"])
        area = self.application.create_area_document_payload(
            "cave", "地下2階", 32, 20,
        )["data"]
        area_map_id = area["map_id"]
        area["random_encounter"]["danger"] = "high"
        area["random_encounter"]["enabled"] = False
        self.assertTrue(self.application.save(area, {})["saved"])
        self.assertTrue(load_map_source(self.application.source_path_for("cave"))["random_encounter"]["enabled"])
        self.assertFalse(load_map_source(self.application.source_path_for(area_map_id))["random_encounter"]["enabled"])
        self.assertEqual(load_map_source(self.application.source_path_for("cave"))["random_encounter"]["danger"], "low")
        self.assertEqual(load_map_source(self.application.source_path_for(area_map_id))["random_encounter"]["danger"], "high")
        runtime = json.loads(self.application.runtime_path_for(area_map_id).read_text(encoding="utf-8"))
        self.assertEqual(runtime["map_id"], area_map_id)
        self.assertEqual(runtime["size"], [32, 20])
        self.assertEqual(runtime["random_encounter"]["danger"], "high")
        self.assertFalse(runtime["random_encounter"]["enabled"])
        self.assertEqual(runtime["bgm_id"], root["bgm_id"])
        root["random_encounter"]["danger"] = "high"
        self.assertTrue(self.application.save(root, {})["saved"])
        self.assertFalse(load_map_source(self.application.source_path_for(area_map_id))["random_encounter"]["enabled"])

    def test_renaming_area_arrival_updates_source_and_compiled_move_sources(self) -> None:
        tileset = self.application.load_tileset("village")
        parent = initial_map_source("sample_village", tileset, "town", 16, 15)
        self.assertTrue(self.application.save(parent, {})["saved"])
        area = self.application.create_area_document_payload(
            "sample_village", "地下2階", 16, 15,
        )["data"]
        area["arrival_points"] = [{
            "id": "from_a", "position": [3, 2], "facing": "up",
            "teleport_enabled": False, "site_id": None,
        }]
        self.assertTrue(self.application.save(area, {})["saved"])
        for index, position in enumerate(([2, 2], [4, 2]), start=1):
            parent["sites"].append({
                "id": f"stairs_{index}",
                "anchor": {"kind": "cell", "position": position},
                "entrance_offsets": [[0, 0]],
                "destination": {"map_id": area["map_id"], "arrival_id": "from_a"},
            })
        self.assertTrue(self.application.save(parent, {})["saved"])

        renamed = load_map_source(self.application.source_path_for(area["map_id"]))
        renamed["arrival_points"][0]["id"] = "from_b"
        body = {"data": renamed, "site_names_ja": {}, "arrival_id_renames": {"from_a": "from_b"}}
        rejected = self.post_payload("/api/save", {
            **body, "arrival_id_renames": {"missing_id": "from_b"},
        })
        self.assertFalse(rejected["saved"])
        self.assertEqual(
            load_map_source(self.application.source_path_for("sample_village"))["sites"][0]["destination"]["arrival_id"],
            "from_a",
        )
        unresolved = self.post_payload("/api/resolve", {"data": renamed, "site_names_ja": {}})
        self.assertIn("missing_destination_arrival", {item["code"] for item in unresolved["diagnostics"]})
        preview = self.post_payload("/api/resolve", body)
        self.assertNotIn("missing_destination_arrival", {item["code"] for item in preview["diagnostics"]})
        result = self.post_payload("/api/save", body)
        self.assertTrue(result["saved"], result["diagnostics"])
        saved_parent = load_map_source(self.application.source_path_for("sample_village"))
        runtime_parent = json.loads(self.application.runtime_path_for("sample_village").read_text(encoding="utf-8"))
        for source in (saved_parent, runtime_parent):
            self.assertEqual(
                [site["destination"]["arrival_id"] for site in source["sites"]],
                ["from_b", "from_b"],
            )
        self.assertEqual(
            load_map_source(self.application.source_path_for(area["map_id"]))["arrival_points"][0]["id"],
            "from_b",
        )

    def get_json(self, path: str, headers: dict[str, str] | None = None) -> dict:
        request = Request(f"{self.base_url}{path}", headers=headers or {})
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read())

    def get_text(self, path: str) -> str:
        with urlopen(f"{self.base_url}{path}", timeout=2) as response:
            return response.read().decode("utf-8")

    def post_json(
        self,
        path: str,
        data: dict,
        site_names_ja: dict[str, str] | None = None,
    ) -> dict:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(
                {"data": data, "site_names_ja": site_names_ja or {}}
            ).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "X-Map-Editor-Token": "test-token"},
        )
        with urlopen(request, timeout=4) as response:
            return json.loads(response.read())

    def post_payload(self, path: str, payload: dict) -> dict:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "X-Map-Editor-Token": "test-token"},
        )
        with urlopen(request, timeout=4) as response:
            return json.loads(response.read())

    def test_serves_new_document_and_requires_token(self) -> None:
        payload = self.get_json("/api/document?token=test-token")
        self.assertTrue(payload["is_new"])
        self.assertEqual(payload["data"]["format_version"], 8)
        self.assertEqual(payload["data"]["actors"], [])
        self.assertEqual(payload["data"]["event_triggers"], [])
        self.assertEqual(payload["data"]["size"], [16, 15])
        self.assertEqual(payload["data"]["sites"], [])
        self.assertEqual(payload["data"]["arrival_points"], [])
        self.assertEqual(payload["data"]["bgm_id"], "da3-field")
        self.assertEqual(payload["bgm_options"], ["da3-field", "da3-town"])
        self.assertEqual(payload["site_names_ja"], {})
        self.assertEqual(
            payload["destination_options"],
            [{"map_id": "test_world", "arrival_ids": []}],
        )
        self.assertEqual(payload["site_options"], [])
        self.assertEqual(payload["actor_assets"]["prop"]["sprite_size"], [16, 16])
        self.assertEqual(
            payload["actor_assets"]["character"]["sprite_size"], [48, 128]
        )
        self.assertEqual(
            payload["actor_assets"]["pc_character"]["sprite_size"], [48, 128]
        )
        self.assertEqual(
            payload["actor_assets"]["treasure"]["sprite_size"], [48, 16]
        )
        self.assertEqual(
            payload["item_options"],
            [{"key": "POTION", "name_ja": "きずぐすり"}],
        )
        self.assertIsNotNone(payload["resolved"])

        with self.assertRaises(HTTPError) as context:
            self.get_json("/api/document")
        self.assertEqual(context.exception.code, 403)

    def test_serves_actor_images_and_sprite_picker_ui(self) -> None:
        with urlopen(
            f"{self.base_url}/api/actor-image?asset=character&token=test-token",
            timeout=2,
        ) as response:
            self.assertEqual(response.headers.get_content_type(), "image/gif")
            self.assertTrue(response.read().startswith(b"GIF"))
        with urlopen(
            f"{self.base_url}/api/actor-image?asset=pc_character&token=test-token",
            timeout=2,
        ) as response:
            self.assertEqual(response.headers.get_content_type(), "image/gif")
            self.assertTrue(response.read().startswith(b"GIF"))
        with urlopen(
            f"{self.base_url}/api/actor-image?asset=prop&token=test-token",
            timeout=2,
        ) as response:
            self.assertEqual(response.headers.get_content_type(), "image/png")
            self.assertTrue(response.read().startswith(b"\x89PNG\r\n\x1a\n"))

        page = self.get_text("/")
        script = self.get_text("/app.js")
        self.assertIn('id="actor-sprite-dialog"', page)
        self.assertIn('data-action="open-actor-sprite-dialog"', script)
        self.assertIn('data-action="select-actor-sprite"', script)
        self.assertIn('["character", "pc_character"]', script)
        self.assertIn("pc_character: { image: new Image()", script)
        self.assertIn('actor.sprite_source === "pc"', script)
        self.assertIn("function drawActorOnMap(context, actor, scale, now)", script)
        self.assertIn("const rendered = drawActorOnMap(context, actor, scale, now)", script)
        self.assertIn('data-actor-field="floating"', script)
        self.assertIn("const FLOATING_PHASE_CYCLE_FRAMES = 96", script)
        self.assertIn("const FLOATING_CHARACTER_FRAMES = [2, 1, 0, 1]", script)
        self.assertIn("const FLOATING_CHARACTER_FRAME_INTERVAL = 20", script)
        self.assertIn("function stableFloatingPhase(identity)", script)
        self.assertIn("function floatingCharacterFrame(now, phaseOffset = 0)", script)
        self.assertNotIn("function floatingOffset(now", script)
        self.assertIn('`actor:${state.data.map_id}:${actor.id}`', script)
        self.assertNotIn('data-actor-field="sprite_index"', script)
        self.assertIn('id="map-select"', page)
        self.assertIn('id="new-map-dialog"', page)
        self.assertIn('id="change-map-tileset-dialog"', page)
        self.assertIn('id="delete-map-button"', page)
        self.assertIn('id="save-button" class="button primary" type="button" disabled', page)
        self.assertIn('id="ground-only-toggle"', page)
        self.assertIn('data-map-field="bgm_id"', script)
        self.assertIn('id="random-encounter-dialog"', page)
        self.assertIn('id="encounter-enabled"', page)
        self.assertIn('value="false">エンカウントなし</option>', page)
        self.assertIn('id="encounter-monster-level"', page)
        self.assertIn('id="encounter-danger"', page)
        self.assertIn('id="encounter-polarity"', page)
        self.assertIn('id="encounter-allow-demons"', page)
        self.assertIn('id="encounter-allow-humans"', page)
        self.assertIn('id="encounter-allow-giants"', page)
        self.assertIn('id="encounter-allow-large-animals"', page)
        self.assertIn('data-action="open-random-encounter-dialog"', script)
        self.assertIn("function openRandomEncounterDialog()", script)
        self.assertIn('byId("random-encounter-form").addEventListener("submit"', script)
        self.assertNotIn("変動はゲームの進行度に応じて判定します。", script)
        self.assertNotIn("低は同じレベルでも同時出現数を少なく扱います。", script)
        self.assertNotIn("DEMON", page)
        self.assertNotIn("large_animal", page)
        self.assertIn('>陽</option>', page)
        self.assertIn('>中立</option>', page)
        self.assertIn('>陰</option>', page)
        self.assertIn("function renderMapSelector()", script)
        self.assertIn('byId("save-button").disabled = !canSave()', script)
        self.assertIn('if (!canSave()) return false;', script)
        self.assertIn('api("/api/change-tileset"', script)
        self.assertIn('api("/api/delete"', script)

    def test_ground_editing_tools_and_object_footprint_preview_are_available(self) -> None:
        page = self.get_text("/")
        script = self.get_text("/app.js")

        self.assertIn("地面だけを表示する", page)
        self.assertIn('data-action="select-ground-tool"', script)
        self.assertIn('data-tool="rectangle"', script)
        self.assertIn("function paintGroundRectangle(rect)", script)
        self.assertIn('kind: "ground_rectangle"', script)
        self.assertIn("function drawGroundPaintPreview(context, scale)", script)
        self.assertIn("function drawObjectPlacementPreview(context, scale)", script)
        self.assertIn("definition.size[0] * scale", script)
        self.assertIn("context.setLineDash", script)

    def test_lists_creates_saves_and_reopens_town_map(self) -> None:
        catalog = self.get_json("/api/catalog?token=test-token")
        self.assertEqual(catalog["maps"][0]["map_id"], "test_world")
        self.assertEqual(
            [item["tileset_id"] for item in catalog["tilesets"]],
            ["village", "village_alt", "worldmap"],
        )
        self.assertEqual(
            [item["profile"] for item in catalog["tilesets"]],
            ["town", "town", "world"],
        )
        with self.assertRaisesRegex(ValueError, "profileが一致"):
            self.application.create_document_payload(
                "wrong_profile",
                "worldmap",
                "town",
                16,
                15,
            )

        created = self.post_payload(
            "/api/create",
            {
                "map_id": "sample_village",
                "tileset_id": "village",
                "profile": "town",
                "width": 16,
                "height": 15,
            },
        )
        self.assertTrue(created["is_new"])
        self.assertEqual(created["data"]["bgm_id"], "da3-town")
        self.assertEqual(created["data"]["grounds"][0], ["grass"] * 16)
        self.assertEqual(created["tileset"]["source_image_id"], "mapchips/village")

        saved = self.post_json("/api/save", created["data"])
        self.assertTrue(saved["saved"])
        reopened = self.get_json(
            "/api/document?map=sample_village&token=test-token"
        )
        self.assertFalse(reopened["is_new"])
        self.assertEqual(reopened["data"]["profile"], "town")
        self.assertTrue((self.application.runtime_root / "sample_village.json").is_file())

        changed = self.post_payload(
            "/api/change-tileset",
            {"map_id": "sample_village", "tileset_id": "village_alt"},
        )
        self.assertTrue(changed["dirty"])
        self.assertEqual(changed["data"]["tileset_id"], "village_alt")
        self.assertEqual(changed["data"]["bgm_id"], "da3-town")
        self.assertEqual(changed["data"]["grounds"][0], ["floor"] * 16)
        self.assertEqual(changed["data"]["objects"], [])
        self.assertEqual(
            load_map_source(self.application.source_path_for("sample_village"))[
                "tileset_id"
            ],
            "village",
        )
        self.assertTrue(self.post_json("/api/save", changed["data"])["saved"])

        blocker_path = self.application.source_path_for("other_world")
        blocker = changed["data"].copy()
        blocker["map_id"] = "other_world"
        blocker["sites"] = [
            {"destination": {"map_id": "sample_village"}}
        ]
        save_map_source(blocker_path, blocker)
        with self.assertRaisesRegex(ValueError, "other_worldの移動先"):
            self.application.delete_map("sample_village")
        blocker_path.unlink()

        deleted = self.post_payload("/api/delete", {"map_id": "sample_village"})
        self.assertTrue(deleted["deleted"])
        self.assertFalse(self.application.source_path_for("sample_village").exists())
        self.assertFalse((self.application.runtime_root / "sample_village.json").exists())
        self.assertFalse((self.application.runtime_root / "sample_village.bin").exists())

    def test_replaces_removed_ground_ids_with_base_ground_on_open(self) -> None:
        tileset = self.application.load_tileset("village")
        source = initial_map_source(
            "broken_village",
            tileset,
            "town",
            16,
            15,
        )
        source["grounds"][5][10] = "removed_ground"
        source_path = self.application.source_path_for("broken_village")
        save_map_source(source_path, source)

        payload = self.get_json(
            "/api/document?map=broken_village&token=test-token"
        )

        self.assertTrue(payload["dirty"])
        self.assertEqual(payload["repaired_unknown_ground_count"], 1)
        self.assertEqual(payload["data"]["grounds"][5][10], "grass")
        self.assertFalse(
            any(issue["code"] == "unknown_ground" for issue in payload["diagnostics"])
        )
        self.assertIsNotNone(payload["resolved"])
        self.assertEqual(
            load_map_source(source_path)["grounds"][5][10],
            "removed_ground",
        )

        self.assertTrue(self.post_json("/api/save", payload["data"])["saved"])
        self.assertEqual(load_map_source(source_path)["grounds"][5][10], "grass")

    def test_actor_trigger_is_automatic_and_interact_is_not_selectable(self) -> None:
        script = self.get_text("/app.js")

        self.assertIn('data-actor-event-id="true"', script)
        self.assertIn("ensureActorTrigger(actor)", script)
        self.assertIn('["step","touch"]', script)
        self.assertNotIn('data-action="add-actor-trigger"', script)
        self.assertNotIn('["step","touch","interact"]', script)

    def test_map_markers_are_emphasized_by_tab_and_right_click_selects_any_kind(self) -> None:
        script = self.get_text("/app.js")

        self.assertIn('const emphasized = state.tab === "site"', script)
        self.assertIn('const emphasized = state.tab === "event"', script)
        self.assertIn("function drawCellSelectionFrame(context, position, scale)", script)
        self.assertIn("if (selected) drawCellSelectionFrame(context, arrival.position, scale)", script)
        self.assertIn("function drawTabCellHighlights(context, scale)", script)
        self.assertIn('if (state.tab === "object")', script)
        self.assertIn("for (const actor of state.data.actors) addPosition(actor.position)", script)
        self.assertIn("for (const trigger of state.data.event_triggers)", script)
        self.assertIn('context.strokeStyle = "rgba(255,103,189,.82)"', script)
        self.assertIn("context.strokeRect(x * scale + 1, y * scale + 1, scale - 2, scale - 2)", script)
        self.assertIn("drawTabCellHighlights(context, scale)", script)
        self.assertIn("function mapSelectionCandidatesAt(cell)", script)
        self.assertIn("function prioritizeMapSelectionCandidates(candidates)", script)
        self.assertIn("candidate.tab === state.tab", script)
        self.assertIn("function selectAnyAt(cell)", script)
        self.assertIn("state.objectId = instance.definition_id", script)
        self.assertIn("selectAnyAt(drag.start)", script)

    def test_right_drag_selects_and_bulk_edits_all_placed_kinds(self) -> None:
        script = self.get_text("/app.js")

        self.assertIn("function rangeSelectionItems(rect)", script)
        self.assertIn('items.push({ kind: "object", id: instance.id })', script)
        self.assertIn('items.push({ kind: "site", id: site.id })', script)
        self.assertIn('items.push({ kind: "arrival", id: arrival.id })', script)
        self.assertIn('items.push({ kind: "actor", id: actor.id })', script)
        self.assertIn('items.push({ kind: "trigger", id: trigger.id })', script)
        self.assertIn("function beginRangeSelection(event, cell)", script)
        self.assertIn("function currentSingleSelectionItem()", script)
        self.assertIn("function singleSelectionMoveDescriptors(item)", script)
        self.assertIn("function beginSingleSelectionDrag(event, cell, item)", script)
        self.assertIn('kind: "single_selection"', script)
        self.assertIn("isMapSelectionCandidateSelected(state.pointerDrag.draggableItem)", script)
        self.assertIn("function beginBulkDrag(event, cell)", script)
        self.assertIn("function validBulkDelta(delta)", script)
        self.assertIn("function deleteBulkSelection()", script)
        self.assertIn('data-action="delete-bulk-selection"', script)
        self.assertIn('state.pointerDrag.kind === "range_selection"', script)
        self.assertIn('state.pointerDrag.kind === "bulk"', script)
        self.assertIn("drawRangeSelection(context, scale)", script)
        self.assertIn("function rightClickWithEscape(event)", script)
        self.assertIn('event.key !== "Escape"', script)
        self.assertIn('document.querySelector("dialog[open]")', script)
        self.assertIn("if (rightClickWithEscape(event)) return", script)

    def test_tab_change_clears_other_selections_and_object_trigger_has_own_tool(self) -> None:
        script = self.get_text("/app.js")

        self.assertIn("function clearSelectionsOutsideTab(tab)", script)
        self.assertIn("clearSelectionsOutsideTab(state.tab)", script)
        self.assertIn('data-action="prepare-object-trigger"', script)
        self.assertIn('state.eventTool = "create_object_trigger"', script)
        self.assertNotIn('data-action="add-object-trigger"', script)

    def test_trigger_id_is_internal_in_editor_ui(self) -> None:
        script = self.get_text("/app.js")

        self.assertNotIn('data-trigger-field="id"', script)
        self.assertNotIn("<label>trigger ID</label>", script)
        self.assertGreaterEqual(
            script.count("<strong>${escapeHtml(trigger.event_id)}</strong>"),
            2,
        )

    def test_resolves_and_saves_source_with_runtime_outputs(self) -> None:
        data = self.get_json("/api/document?token=test-token")["data"]
        data["grounds"][2][2] = "plain"
        data["arrival_points"] = [
            {
                "id": "sample_site_world",
                "position": [2, 2],
                "facing": "down",
                "teleport_enabled": True,
                "site_id": "sample_site",
            }
        ]
        data["sites"] = [
            {
                "id": "sample_site",
                "anchor": {"kind": "cell", "position": [2, 2]},
                "entrance_offsets": [[0, 0]],
                "destination": {
                    "map_id": "test_world",
                    "arrival_id": "sample_site_world",
                },
            }
        ]

        names = {"sample_site": "サンプル拠点"}
        validation = self.post_json("/api/resolve", data, names)
        result = self.post_json("/api/save", data, names)

        self.assertIsNotNone(validation["resolved"])
        self.assertTrue(result["saved"])
        self.assertTrue(self.application.source_path.is_file())
        self.assertTrue(self.application.runtime_path.is_file())
        self.assertTrue(self.application.runtime_path.with_suffix(".bin").is_file())
        saved = json.loads(self.application.source_path.read_text(encoding="utf-8"))
        runtime = json.loads(self.application.runtime_path.read_text(encoding="utf-8"))
        texts = json.loads(self.application.texts_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["sites"][0]["anchor"]["position"], [2, 2])
        self.assertNotIn("name_text_key", saved["sites"][0])
        self.assertEqual(runtime["sites"][0]["entrance_cells"], [[2, 2]])
        self.assertEqual(runtime["sites"][0]["name_text_key"], "location.sample_site")
        self.assertEqual(
            texts,
            [
                {
                    "text_key": "location.sample_site",
                    "text_ja": "サンプル拠点",
                    "text_en": "",
                    "text_zhcn": "",
                }
            ],
        )

    def test_requires_japanese_site_name(self) -> None:
        data = self.get_json("/api/document?token=test-token")["data"]
        data["grounds"][2][2] = "plain"
        data["arrival_points"] = [
            {
                "id": "sample_site_world",
                "position": [2, 2],
                "facing": "down",
                "teleport_enabled": True,
                "site_id": "sample_site",
            }
        ]
        data["sites"] = [
            {
                "id": "sample_site",
                "anchor": {"kind": "cell", "position": [2, 2]},
                "entrance_offsets": [[0, 0]],
                "destination": {
                    "map_id": "test_world",
                    "arrival_id": "sample_site_world",
                },
            }
        ]

        result = self.post_json("/api/save", data)

        self.assertFalse(result["saved"])
        self.assertIn(
            "missing_site_name_ja",
            {item["code"] for item in result["diagnostics"]},
        )
        self.assertIsNotNone(result["resolved"])

    def test_saves_unnamed_move_source_on_nonworld_map(self) -> None:
        world = self.get_json("/api/document?token=test-token")["data"]
        world["grounds"][2][2] = "plain"
        world["sites"] = [
            {
                "id": "site_1",
                "anchor": {"kind": "cell", "position": [2, 2]},
                "entrance_offsets": [[0, 0]],
                "destination": {"map_id": "", "arrival_id": ""},
            }
        ]
        save_map_source(self.application.source_path, world)

        tileset = self.application.load_tileset("village")
        data = initial_map_source(
            "sample_village",
            tileset,
            "town",
            16,
            15,
        )
        data["arrival_points"] = [
            {
                "id": "from_inside",
                "position": [3, 2],
                "facing": "down",
                "teleport_enabled": False,
                "site_id": None,
            }
        ]
        data["sites"] = [
            {
                "id": "site_1",
                "anchor": {"kind": "cell", "position": [2, 2]},
                "entrance_offsets": [[0, 0]],
                "destination": {
                    "map_id": "sample_village",
                    "arrival_id": "from_inside",
                },
            }
        ]

        result = self.post_json("/api/save", data)

        self.assertTrue(result["saved"])
        self.assertTrue(
            {
                "sites_require_world_profile",
                "duplicate_global_site_id",
                "missing_site_name_ja",
            }.isdisjoint(item["code"] for item in result["diagnostics"])
        )
        self.assertEqual(self.application.site_names_ja(data), {})
        self.assertFalse(self.application.texts_path.exists())
        self.assertEqual(self.application.site_options(data), ["site_1"])

        script = self.get_text("/app.js")
        self.assertIn('const siteLabel = isWorld ? "拠点" : "移動口"', script)
        self.assertIn("function uniqueSiteId(base)", script)
        self.assertIn("function siteDestinationSummary(site)", script)
        self.assertIn('return `移動先: ${mapId || "—"} / ${arrivalId || "—"}`', script)
        self.assertIn("座標${siteLabel}を追加", script)
        self.assertIn("この移動口の名称はゲーム中に表示されません。", script)
        self.assertNotIn("拠点はworld profileで編集します。", script)

    def test_keeps_visual_preview_for_incomplete_site(self) -> None:
        data = self.get_json("/api/document?token=test-token")["data"]
        data["grounds"][2][2] = "plain"
        data["sites"] = [
            {
                "id": "incomplete_site",
                "anchor": {"kind": "cell", "position": [2, 2]},
                "entrance_offsets": [[0, 0]],
                "destination": {"map_id": "", "arrival_id": ""},
            }
        ]

        result = self.post_json(
            "/api/resolve",
            data,
            {"incomplete_site": ""},
        )

        self.assertTrue(
            any(item["severity"] == "error" for item in result["diagnostics"])
        )
        self.assertIsNotNone(result["resolved"])
        self.assertEqual(len(result["resolved"]["ground_cells"]), 240)

        script = self.get_text("/app.js")
        self.assertIn("function applyValidationResult(result)", script)
        self.assertIn("if (result.resolved) state.resolved = result.resolved", script)

    def test_saves_actor_and_event_trigger_using_defined_event(self) -> None:
        events_dir = self.application.content_root / "events"
        events_dir.mkdir(parents=True)
        (events_dir / "sample.json").write_text(
            json.dumps(
                {
                    "format_version": 1,
                    "namespace": "sample",
                    "events": [{"id": "talk", "commands": []}],
                }
            ),
            encoding="utf-8",
        )
        payload = self.get_json("/api/document?token=test-token")
        data = payload["data"]
        data["grounds"][2][2] = "plain"
        data["actors"] = [
            {
                "id": "elder",
                "position": [2, 2],
                "kind": "stationary",
                "sprite_index": 0,
                "sprite_source": "pc",
                "facing": "down",
            }
        ]
        data["event_triggers"] = [
            {
                "id": "elder_talk",
                "event_id": "sample.talk",
                "activations": ["touch", "interact"],
                "anchor": {"kind": "actor", "actor_id": "elder"},
                "offsets": [[0, 0]],
            }
        ]

        result = self.post_json("/api/save", data)

        self.assertEqual(payload["event_options"], ["sample.talk"])
        self.assertTrue(result["saved"])
        runtime = json.loads(self.application.runtime_path.read_text(encoding="utf-8"))
        self.assertEqual(runtime["actors"][0]["id"], "elder")
        self.assertEqual(runtime["actors"][0]["sprite_source"], "pc")
        self.assertEqual(
            runtime["event_triggers"][0]["target"],
            {"kind": "actor", "actor_id": "elder", "offsets": [[0, 0]]},
        )

    def test_saves_treasure_actor_without_an_event_trigger(self) -> None:
        payload = self.get_json("/api/document?token=test-token")
        data = payload["data"]
        data["grounds"][2][2] = "plain"
        data["actors"] = [
            {
                "id": "entrance_potion",
                "position": [2, 2],
                "kind": "treasure",
                "contents": {"type": "item", "item_key": "POTION"},
            }
        ]

        result = self.post_json("/api/save", data)

        self.assertTrue(result["saved"])
        runtime = json.loads(self.application.runtime_path.read_text(encoding="utf-8"))
        self.assertEqual(runtime["actors"], data["actors"])
        self.assertEqual(runtime["event_triggers"], [])

    def test_rejects_invalid_world_edge_without_writing(self) -> None:
        data = self.get_json("/api/document?token=test-token")["data"]
        data["grounds"][0][0] = "plain"

        result = self.post_json("/api/save", data)

        self.assertFalse(result["saved"])
        self.assertFalse(self.application.source_path.exists())
        self.assertIn("map_edge_not_base_ground", {item["code"] for item in result["diagnostics"]})
        self.assertIsNotNone(result["resolved"])
        self.assertEqual(
            result["resolved"]["ground_cells"][0]["layers"][-1]["ground_id"],
            "plain",
        )


if __name__ == "__main__":
    unittest.main()
