from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tools.event_editor.server import EventEditorApplication, create_server


class EventEditorServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.content_root = self.root / "content"
        data_root = self.content_root / "data"
        data_root.mkdir(parents=True)
        (data_root / "characters.json").write_text(
            json.dumps([{"name_en": "Fiora"}]), encoding="utf-8"
        )
        (data_root / "items.json").write_text(
            json.dumps([{"name_en": "POTION"}]), encoding="utf-8"
        )
        (data_root / "texts.json").write_text(
            json.dumps([{"text_key": "event.sample.hello"}]), encoding="utf-8"
        )
        maps_root = self.content_root / "maps" / "sources"
        maps_root.mkdir(parents=True)
        (maps_root / "field.json").write_text(
            json.dumps({"actors": [{"id": "elder"}]}), encoding="utf-8"
        )
        app_root = self.root / "app"
        (app_root / "audio").mkdir(parents=True)
        (app_root / "audio" / "field.ogg").write_bytes(b"")
        (app_root / "audio" / "catalog.json").write_text(
            json.dumps(
                {
                    "format_version": 1,
                    "sound_effects": {
                        "confirm": {"channel": 1, "sound": 9}
                    },
                }
            ),
            encoding="utf-8",
        )
        self.application = EventEditorApplication(
            self.content_root,
            app_root / "events" / "events.json",
            "sample",
            token="test-token",
            app_root=app_root,
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

    def get_json(self, path: str) -> dict:
        with urlopen(f"{self.base_url}{path}", timeout=2) as response:
            return json.loads(response.read())

    def post_json(self, path: str, data: object) -> dict:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps({"data": data}).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Event-Editor-Token": "test-token",
            },
        )
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read())

    def test_serves_new_structured_document_and_requires_token(self) -> None:
        payload = self.get_json("/api/document?token=test-token")

        self.assertTrue(payload["is_new"])
        self.assertEqual(payload["data"]["namespace"], "sample")
        self.assertEqual(payload["catalogs"]["character_keys"], ["Fiora"])
        self.assertEqual(payload["catalogs"]["item_keys"], ["POTION"])
        self.assertEqual(payload["catalogs"]["bgm_ids"], ["field"])
        self.assertEqual(payload["catalogs"]["se_ids"], ["confirm"])
        self.assertEqual(payload["catalogs"]["actor_ids"], ["elder"])

        with self.assertRaises(HTTPError) as context:
            self.get_json("/api/document")
        self.assertEqual(context.exception.code, 403)

    def test_validates_saves_and_compiles_event_source(self) -> None:
        data = {
            "format_version": 1,
            "namespace": "sample",
            "flags": [{"id": "done", "note": "完了"}],
            "events": [
                {
                    "id": "hello",
                    "note": "挨拶",
                    "commands": [
                        {"command": "message", "text_key": "event.sample.hello"},
                        {"command": "set_flag", "flag_id": "sample.done"},
                    ],
                }
            ],
        }

        result = self.post_json("/api/save", data)

        self.assertTrue(result["saved"])
        saved = json.loads(self.application.source_path.read_text(encoding="utf-8"))
        runtime = json.loads(self.application.runtime_path.read_text(encoding="utf-8"))
        self.assertEqual(saved, data)
        self.assertIn("sample.hello", runtime["events"])
        self.assertNotIn("note", runtime["events"]["sample.hello"])

    def test_does_not_write_invalid_reference(self) -> None:
        data = {
            "format_version": 1,
            "namespace": "sample",
            "flags": [],
            "events": [
                {
                    "id": "bad",
                    "commands": [
                        {"command": "join_party", "character_key": "Missing"}
                    ],
                }
            ],
        }

        result = self.post_json("/api/save", data)

        self.assertFalse(result["saved"])
        self.assertFalse(self.application.source_path.exists())
        self.assertIn(
            "unknown_character",
            {item["code"] for item in result["diagnostics"]},
        )


if __name__ == "__main__":
    unittest.main()
