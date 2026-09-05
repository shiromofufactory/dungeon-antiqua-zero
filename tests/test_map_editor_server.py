from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

from scripts.map_pipeline import initial_worldmap_tileset, save_tileset
from tools.map_editor.server import MapEditorApplication, create_server


class MapEditorServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        content_root = self.root / "content"
        image_path = content_root / "images" / "mapchips" / "worldmap.png"
        image_path.parent.mkdir(parents=True)
        Image.new("RGBA", (64, 96), (0, 0, 0, 255)).save(image_path)
        metadata_path = content_root / "maps" / "tilesets" / "worldmap.json"
        tileset = initial_worldmap_tileset()
        save_tileset(metadata_path, tileset)
        palette_path = self.root / "palette.pyxpal"
        palette_path.write_text("000000\nFF0080\n", encoding="utf-8")
        self.application = MapEditorApplication(
            content_root,
            self.root / "runtime",
            "test_world",
            "worldmap",
            "world",
            6,
            5,
            palette_path=palette_path,
            token="test-token",
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

    def test_serves_new_document_and_requires_token(self) -> None:
        payload = self.get_json("/api/document?token=test-token")
        self.assertTrue(payload["is_new"])
        self.assertEqual(payload["data"]["format_version"], 4)
        self.assertEqual(payload["data"]["actors"], [])
        self.assertEqual(payload["data"]["event_triggers"], [])
        self.assertEqual(payload["data"]["size"], [6, 5])
        self.assertEqual(payload["data"]["sites"], [])
        self.assertEqual(payload["data"]["arrival_points"], [])
        self.assertEqual(payload["site_names_ja"], {})
        self.assertEqual(
            payload["destination_options"],
            [{"map_id": "test_world", "arrival_ids": []}],
        )
        self.assertEqual(payload["site_options"], [])
        self.assertIsNotNone(payload["resolved"])

        with self.assertRaises(HTTPError) as context:
            self.get_json("/api/document")
        self.assertEqual(context.exception.code, 403)

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
        self.assertEqual(
            runtime["event_triggers"][0]["target"],
            {"kind": "actor", "actor_id": "elder", "offsets": [[0, 0]]},
        )

    def test_rejects_invalid_world_edge_without_writing(self) -> None:
        data = self.get_json("/api/document?token=test-token")["data"]
        data["grounds"][0][0] = "plain"

        result = self.post_json("/api/save", data)

        self.assertFalse(result["saved"])
        self.assertFalse(self.application.source_path.exists())
        self.assertIn("world_edge_not_sea", {item["code"] for item in result["diagnostics"]})


if __name__ == "__main__":
    unittest.main()
