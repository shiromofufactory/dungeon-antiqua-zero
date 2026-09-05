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
        events_root = self.content_root / "events"
        events_root.mkdir(parents=True)
        (events_root / "flags.json").write_text(
            json.dumps([{"flag_id": "story.done", "note": "完了"}]),
            encoding="utf-8",
        )
        (events_root / "messages.json").write_text(
            json.dumps([
                {
                    "message_id": "sample.hello",
                    "text_ja": ["こんにちは"],
                    "text_en": ["Hello"],
                    "text_zhcn": ["你好"],
                    "note": "挨拶",
                }
            ]),
            encoding="utf-8",
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

    def post_json(
        self,
        path: str,
        data: object,
        *,
        flags: object | None = None,
        messages: object | None = None,
        namespace: str | None = None,
    ) -> dict:
        payload = {"data": data}
        if flags is not None:
            payload["flags"] = flags
        if messages is not None:
            payload["messages"] = messages
        if namespace is not None:
            payload["namespace"] = namespace
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
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
        self.assertEqual(payload["catalogs"]["flag_ids"], ["story.done"])
        self.assertEqual(payload["flags"][0]["flag_id"], "story.done")
        self.assertEqual(payload["catalogs"]["message_ids"], ["sample.hello"])
        self.assertEqual(payload["messages"][0]["message_id"], "sample.hello")
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
            "events": [
                {
                    "id": "hello",
                    "note": "挨拶",
                    "commands": [
                        {"command": "message", "message_id": "sample.hello"},
                        {"command": "set_flag", "flag_id": "story.done"},
                    ],
                }
            ],
        }

        result = self.post_json("/api/save", data)

        self.assertTrue(result["saved"])
        saved = json.loads(self.application.source_path.read_text(encoding="utf-8"))
        runtime = json.loads(self.application.runtime_path.read_text(encoding="utf-8"))
        runtime_messages = json.loads(
            self.application.runtime_messages_path.read_text(encoding="utf-8")
        )
        self.assertEqual(saved, data)
        self.assertEqual(runtime["flags"], ["story.done"])
        self.assertIn("sample.hello", runtime["events"])
        self.assertNotIn("note", runtime["events"]["sample.hello"])
        self.assertNotIn("note", runtime_messages[0])

    def test_saves_global_flag_and_cross_namespace_reference_together(self) -> None:
        flags = [{"flag_id": "quest.alvan_joined", "note": "加入済み"}]
        data = {
            "format_version": 1,
            "namespace": "sample",
            "events": [{
                "id": "join_complete",
                "commands": [{
                    "command": "set_flag",
                    "flag_id": "quest.alvan_joined",
                }],
            }],
        }

        result = self.post_json("/api/save", data, flags=flags)

        self.assertTrue(result["saved"])
        self.assertEqual(
            json.loads(
                (self.content_root / "events" / "flags.json").read_text(
                    encoding="utf-8"
                )
            ),
            flags,
        )
        self.assertEqual(
            json.loads(self.application.runtime_path.read_text(encoding="utf-8"))[
                "flags"
            ],
            ["quest.alvan_joined"],
        )

    def test_saves_new_message_and_its_event_reference_together(self) -> None:
        messages = [
            {
                "message_id": "shared.new_message",
                "text_ja": ["新しいメッセージ"],
                "text_en": [],
                "text_zhcn": [],
                "note": "同じ保存操作で追加",
            }
        ]
        data = {
            "format_version": 1,
            "namespace": "sample",
            "events": [{
                "id": "new_message",
                "commands": [{
                    "command": "message",
                    "message_id": "shared.new_message",
                }],
            }],
        }

        result = self.post_json("/api/save", data, messages=messages)

        self.assertTrue(result["saved"])
        self.assertEqual(
            json.loads(
                (self.content_root / "events" / "messages.json").read_text(
                    encoding="utf-8"
                )
            ),
            messages,
        )

    def test_switches_existing_namespace_and_prepares_new_source(self) -> None:
        other = {
            "format_version": 1,
            "namespace": "common",
            "events": [],
        }
        (self.content_root / "events" / "common.json").write_text(
            json.dumps(other), encoding="utf-8"
        )

        existing = self.get_json(
            "/api/document?namespace=common&token=test-token"
        )
        new = self.get_json(
            "/api/document?namespace=new_story&token=test-token"
        )

        self.assertFalse(existing["is_new"])
        self.assertEqual(existing["data"], other)
        self.assertEqual(existing["flags"], new["flags"])
        self.assertIn("common", existing["namespace_options"])
        self.assertTrue(new["is_new"])
        self.assertEqual(new["data"]["namespace"], "new_story")
        self.assertNotIn("flags", new["data"])

    def test_does_not_write_invalid_reference(self) -> None:
        data = {
            "format_version": 1,
            "namespace": "sample",
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
