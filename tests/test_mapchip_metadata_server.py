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
from tools.mapchip_metadata.server import MetadataApplication, create_server


class MapchipMetadataServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.content_root = Path(self.temporary.name)
        image_path = self.content_root / "images" / "mapchips" / "worldmap.png"
        image_path.parent.mkdir(parents=True)
        Image.new("RGBA", (64, 96), (0, 0, 0, 0)).save(image_path)
        metadata_path = self.content_root / "maps" / "tilesets" / "worldmap.json"
        save_tileset(metadata_path, initial_worldmap_tileset())

        self.application = MetadataApplication(
            self.content_root,
            "worldmap",
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

    def test_rejects_invalid_save_without_replacing_file(self) -> None:
        original = self.application.metadata_path.read_text(encoding="utf-8")
        invalid = initial_worldmap_tileset()
        invalid["grounds"][0]["collision"] = "passable"

        result = self.post_json("/api/save", {"data": invalid})

        self.assertFalse(result["saved"])
        self.assertEqual(self.application.metadata_path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
