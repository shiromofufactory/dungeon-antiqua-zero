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

    def post_json(self, path: str, data: dict) -> dict:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps({"data": data}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "X-Map-Editor-Token": "test-token"},
        )
        with urlopen(request, timeout=4) as response:
            return json.loads(response.read())

    def test_serves_new_document_and_requires_token(self) -> None:
        payload = self.get_json("/api/document?token=test-token")
        self.assertTrue(payload["is_new"])
        self.assertEqual(payload["data"]["size"], [6, 5])
        self.assertIsNotNone(payload["resolved"])

        with self.assertRaises(HTTPError) as context:
            self.get_json("/api/document")
        self.assertEqual(context.exception.code, 403)

    def test_resolves_and_saves_source_with_runtime_outputs(self) -> None:
        data = self.get_json("/api/document?token=test-token")["data"]
        data["grounds"][2][2] = "plain"

        validation = self.post_json("/api/resolve", data)
        result = self.post_json("/api/save", data)

        self.assertIsNotNone(validation["resolved"])
        self.assertTrue(result["saved"])
        self.assertTrue(self.application.source_path.is_file())
        self.assertTrue(self.application.runtime_path.is_file())
        self.assertTrue(self.application.runtime_path.with_suffix(".bin").is_file())

    def test_rejects_invalid_world_edge_without_writing(self) -> None:
        data = self.get_json("/api/document?token=test-token")["data"]
        data["grounds"][0][0] = "plain"

        result = self.post_json("/api/save", data)

        self.assertFalse(result["saved"])
        self.assertFalse(self.application.source_path.exists())
        self.assertIn("world_edge_not_sea", {item["code"] for item in result["diagnostics"]})


if __name__ == "__main__":
    unittest.main()
