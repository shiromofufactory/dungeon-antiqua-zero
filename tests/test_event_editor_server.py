from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

from tools.event_editor.server import EventEditorApplication, create_server


class EventEditorServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.content_root = self.root / "content"
        data_root = self.content_root / "data"
        data_root.mkdir(parents=True)
        (data_root / "characters.json").write_text(
            json.dumps([{"name_en": "Fiora", "face_x": 0, "face_y": 0}]),
            encoding="utf-8",
        )
        (data_root / "items.json").write_text(
            json.dumps([{"name_en": "POTION"}]), encoding="utf-8"
        )
        (data_root / "shops.json").write_text(
            json.dumps([{"shop_key": "FAIRY_HAMLET_ITEMS"}]),
            encoding="utf-8",
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
                    "portrait_character_key": "Fiora",
                    "text_ja": ["こんにちは"],
                    "text_en": ["Hello"],
                    "text_zhcn": ["你好"],
                }
            ]),
            encoding="utf-8",
        )
        maps_root = self.content_root / "maps" / "sources"
        maps_root.mkdir(parents=True)
        (maps_root / "field.json").write_text(
            json.dumps({"actors": [{"id": "elder"}]}), encoding="utf-8"
        )
        face_path = self.content_root / "images" / "faces" / "faces.png"
        face_path.parent.mkdir(parents=True)
        Image.new("RGB", (128, 256), (255, 0, 128)).save(face_path)
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
        missions: object | None = None,
    ) -> dict:
        payload = {"data": data}
        if flags is not None:
            payload["flags"] = flags
        if messages is not None:
            payload["messages"] = messages
        if missions is not None:
            payload["missions"] = missions
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

    def test_mission_http_save_includes_conditions_and_message_reference(self) -> None:
        payload = self.get_json("/api/document?token=test-token")
        missions = [{"id": "hello", "message_id": "sample.hello"}]
        result = self.post_json("/api/save", payload["data"], flags=payload["flags"], messages=payload["messages"], missions=missions)
        self.assertTrue(result["saved"])
        self.assertEqual(self.get_json("/api/document?token=test-token")["missions"], missions)

    def test_saves_missions_and_rejects_referenced_flag_or_message_deletion(self) -> None:
        from scripts.event_pipeline import load_event_sources
        from app.resources.events import EventCatalog

        payload = self.application.document_payload()
        missions = [{"id": "find_elder", "note": "制作メモ", "condition": {"type": "not", "condition": {"type": "flag_set", "flag_id": "story.done"}}, "message_id": "sample.hello"}]
        result = self.application.save("sample", payload["data"], payload["flags"], payload["messages"], missions)
        self.assertTrue(result["saved"])
        self.assertEqual(self.application.document_payload()["missions"], missions)
        self.assertNotIn("missions", load_event_sources(self.content_root))
        runtime_before = self.application.runtime_path.read_bytes()
        catalog = EventCatalog.from_json(self.application.runtime_path)
        self.assertEqual(catalog.missions[0].id, "find_elder")
        for flags, messages in (([], payload["messages"]), (payload["flags"], [])):
            result = self.application.save("sample", payload["data"], flags, messages, missions)
            self.assertFalse(result["saved"])
            self.assertEqual(self.application.runtime_path.read_bytes(), runtime_before)
        # Old clients omitting missions retain the existing ordered definitions.
        self.assertTrue(self.application.save("sample", payload["data"], payload["flags"], payload["messages"])["saved"])
        self.assertEqual(self.application.document_payload()["missions"], missions)

    def test_serves_new_structured_document_and_requires_token(self) -> None:
        payload = self.get_json("/api/document?token=test-token")

        self.assertTrue(payload["is_new"])
        self.assertEqual(payload["data"]["namespace"], "sample")
        self.assertEqual(payload["catalogs"]["character_keys"], ["Fiora"])
        self.assertEqual(payload["catalogs"]["item_keys"], ["POTION"])
        self.assertEqual(
            payload["catalogs"]["shop_keys"], ["FAIRY_HAMLET_ITEMS"]
        )

        self.assertEqual(payload["catalogs"]["flag_ids"], ["story.done"])
        self.assertEqual(payload["flags"][0]["flag_id"], "story.done")
        self.assertEqual(payload["catalogs"]["message_ids"], ["sample.hello"])
        self.assertEqual(payload["messages"][0]["message_id"], "sample.hello")
        self.assertEqual(
            payload["messages"][0]["portrait_character_key"],
            "Fiora",
        )
        self.assertEqual(payload["catalogs"]["bgm_ids"], ["field"])
        self.assertEqual(payload["catalogs"]["se_ids"], ["confirm"])
        self.assertEqual(payload["catalogs"]["actor_ids"], ["elder"])
        self.assertEqual(
            payload["face_sheet"],
            {
                "width": 128,
                "height": 256,
                "face_size": 32,
                "character_faces": [
                    {"character_key": "Fiora", "x": 0, "y": 0}
                ],
            },
        )

        with self.assertRaises(HTTPError) as context:
            self.get_json("/api/document")
        self.assertEqual(context.exception.code, 403)

    def test_serves_face_sheet_and_visual_picker(self) -> None:
        with urlopen(
            f"{self.base_url}/api/face-sheet?token=test-token", timeout=2
        ) as response:
            self.assertEqual(response.headers.get_content_type(), "image/png")
            self.assertTrue(response.read().startswith(b"\x89PNG\r\n\x1a\n"))
        with urlopen(f"{self.base_url}/app.js", timeout=2) as response:
            script = response.read().decode("utf-8")
        with urlopen(f"{self.base_url}/?token=test-token", timeout=2) as response:
            page = response.read().decode("utf-8")

        self.assertIn("function renderFacePicker(message)", script)
        self.assertIn("function renderFacePickerControl(message)", script)
        self.assertIn('class="selected-face-preview"', script)
        self.assertIn('aria-label="選択中の顔"', script)
        self.assertIn('data-action="open-face-picker"', script)
        self.assertIn('data-action="select-message-face"', script)
        self.assertNotIn('data-message-field="portrait_character_key"', script)
        self.assertIn('id="face-picker-dialog"', page)
        self.assertIn('id="face-picker-dialog-content"', page)

    def test_save_button_is_disabled_only_without_unsaved_changes(self) -> None:
        with urlopen(f"{self.base_url}/?token=test-token", timeout=2) as response:
            page = response.read().decode("utf-8")
        with urlopen(f"{self.base_url}/app.js", timeout=2) as response:
            script = response.read().decode("utf-8")

        self.assertIn('id="save" class="primary" disabled', page)
        self.assertIn('$("save").disabled = !canSave()', script)
        self.assertIn('if (!canSave()) return false;', script)

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
                        {"command": "recover_party"},
                        {
                            "command": "open_shop",
                            "shop_key": "FAIRY_HAMLET_ITEMS",
                        },
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
        self.assertEqual(
            runtime["events"]["sample.hello"]["commands"][1:3],
            [
                {"command": "recover_party"},
                {
                    "command": "open_shop",
                    "shop_key": "FAIRY_HAMLET_ITEMS",
                },
            ],
        )
        self.assertNotIn("note", runtime["events"]["sample.hello"])
        self.assertNotIn("note", runtime_messages[0])
        self.assertEqual(
            runtime_messages[0]["portrait_character_key"],
            "Fiora",
        )

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

    def test_preserves_flag_event_and_message_order_when_saving(self) -> None:
        flags = [
            {"flag_id": "story.second", "note": "2番目"},
            {"flag_id": "story.first", "note": "1番目"},
        ]
        data = {
            "format_version": 1,
            "namespace": "sample",
            "events": [
                {"id": "second", "commands": [{"command": "end_event"}]},
                {"id": "first", "commands": [{"command": "end_event"}]},
            ],
        }
        messages = [
            {
                "message_id": "sample.second",
                "text_ja": ["2番目"],
                "text_en": [],
                "text_zhcn": [],
            },
            {
                "message_id": "sample.first",
                "text_ja": ["1番目"],
                "text_en": [],
                "text_zhcn": [],
            },
        ]

        result = self.post_json(
            "/api/save",
            data,
            flags=flags,
            messages=messages,
        )

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
            json.loads(
                self.application.source_path.read_text(encoding="utf-8")
            )["events"],
            data["events"],
        )
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
