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
from tools.editor.server import create_server, make_handler
from tools.event_editor.server import EventEditorApplication
from tools.map_editor.server import MapEditorApplication


class EditorServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.content_root = self.root / "content"

        data_root = self.content_root / "data"
        data_root.mkdir(parents=True)
        (data_root / "characters.json").write_text("[]\n", encoding="utf-8")
        (data_root / "items.json").write_text("[]\n", encoding="utf-8")

        events_root = self.content_root / "events"
        events_root.mkdir(parents=True)
        (events_root / "flags.json").write_text("[]\n", encoding="utf-8")
        (events_root / "messages.json").write_text("[]\n", encoding="utf-8")
        (events_root / "sample.json").write_text(
            json.dumps(
                {
                    "format_version": 1,
                    "namespace": "sample",
                    "events": [{"id": "talk", "commands": []}],
                }
            ),
            encoding="utf-8",
        )

        image_path = self.content_root / "images" / "mapchips" / "worldmap.png"
        image_path.parent.mkdir(parents=True)
        Image.new("RGBA", (64, 96), (0, 0, 0, 255)).save(image_path)
        save_tileset(
            self.content_root / "maps" / "tilesets" / "worldmap.json",
            initial_worldmap_tileset(),
        )
        palette_path = self.root / "palette.pyxpal"
        palette_path.write_text("000000\nFF0080\n", encoding="utf-8")

        app_root = self.root / "app"
        (app_root / "audio").mkdir(parents=True)
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
        self.map_application = MapEditorApplication(
            self.content_root,
            app_root / "maps",
            "test_world",
            "worldmap",
            "world",
            6,
            5,
            palette_path=palette_path,
            token="shared-token",
        )
        self.event_application = EventEditorApplication(
            self.content_root,
            app_root / "events" / "events.json",
            "sample",
            token="shared-token",
            app_root=app_root,
        )
        self.server = create_server(
            self.map_application, self.event_application, 0
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def get_json(
        self, path: str, headers: dict[str, str] | None = None
    ) -> dict[str, object]:
        request = Request(f"{self.base_url}{path}", headers=headers or {})
        with urlopen(request, timeout=3) as response:
            return json.loads(response.read())

    def get_text(self, path: str) -> str:
        with urlopen(f"{self.base_url}{path}", timeout=3) as response:
            return response.read().decode("utf-8")

    def post_json(
        self, path: str, payload: object, token_header: str
    ) -> dict[str, object]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", token_header: "shared-token"},
        )
        with urlopen(request, timeout=4) as response:
            return json.loads(response.read())

    def test_serves_both_editors_and_their_static_assets(self) -> None:
        map_page = self.get_text("/map/?token=shared-token")
        event_page = self.get_text("/event/?token=shared-token")

        self.assertIn("Map Editor", map_page)
        self.assertIn("Event Editor", event_page)
        self.assertNotIn('id="validate-button"', map_page)
        self.assertNotIn('id="validate"', event_page)
        self.assertNotIn('id="document-path"', map_page)
        self.assertNotIn('id="document-path"', event_page)
        event_header = event_page.split("</header>", 1)[0]
        self.assertIn('class="header-actions"', event_header)
        self.assertIn('id="namespace-select"', event_header)
        self.assertIn('data-action="open-namespace-dialog"', event_header)
        self.assertNotIn("event-context-bar", event_page)
        self.assertIn('id="namespace-dialog"', event_page)
        self.assertIn('id="namespace-form"', event_page)
        self.assertNotIn('data-action="open-namespace"', event_page)
        self.assertIn('data-list-tab="flag"', event_page)
        self.assertIn('data-list-tab="event"', event_page)
        self.assertIn('data-list-tab="message"', event_page)
        self.assertIn('id="editor-switch"', map_page)
        self.assertIn('id="editor-switch"', event_page)
        self.assertIn("editorApiPath", self.get_text("/map/app.js"))
        self.assertIn("editorApiPath", self.get_text("/event/app.js"))
        self.assertEqual(
            self.get_text("/map/editor-header.css"),
            self.get_text("/event/editor-header.css"),
        )
        self.assertIn(
            ".namespace-dialog",
            self.get_text("/event/event-layout.css"),
        )
        event_script = self.get_text("/event/app.js")
        self.assertIn("localStorage.getItem(UI_STORAGE_KEY)", event_script)
        self.assertIn('draggable="true"', event_script)
        self.assertIn('data-drop-list-path', event_script)
        self.assertIn('data-list-item-drag', event_script)
        self.assertIn('data-list-drop-kind', event_script)
        self.assertIn('function moveListItem(', event_script)
        self.assertIn('["end_event", "イベント終了"]', event_script)
        self.assertNotIn('data-message-field="note"', event_script)
        self.assertNotIn('data-action="move-command-up"', event_script)
        self.assertNotIn('data-action="move-command-down"', event_script)
        self.assertIn(
            '$("namespace-select").addEventListener("change"',
            event_script,
        )
        self.assertIn('$("namespace-dialog").showModal()', event_script)
        self.assertIn('$("namespace-form").addEventListener("submit"', event_script)

    def test_root_redirects_to_the_map_editor(self) -> None:
        with urlopen(
            f"{self.base_url}/?token=shared-token", timeout=3
        ) as response:
            self.assertEqual(
                response.geturl(),
                f"{self.base_url}/map/?token=shared-token",
            )
            self.assertIn("Map Editor", response.read().decode("utf-8"))

    def test_routes_each_editor_api_with_one_shared_token(self) -> None:
        map_payload = self.get_json("/map/api/document?token=shared-token")
        event_payload = self.get_json(
            "/event/api/document?namespace=sample&token=shared-token"
        )

        self.assertEqual(map_payload["data"]["map_id"], "test_world")
        self.assertEqual(event_payload["data"]["namespace"], "sample")

        with self.assertRaises(HTTPError) as context:
            self.get_json("/event/api/document")
        self.assertEqual(context.exception.code, 403)

    def test_routes_validate_requests_to_the_selected_editor(self) -> None:
        map_payload = self.get_json("/map/api/document?token=shared-token")
        map_result = self.post_json(
            "/map/api/resolve",
            {"data": map_payload["data"], "site_names_ja": {}},
            "X-Map-Editor-Token",
        )
        event_payload = self.get_json(
            "/event/api/document?namespace=sample&token=shared-token"
        )
        event_result = self.post_json(
            "/event/api/validate",
            {
                "namespace": "sample",
                "data": event_payload["data"],
                "flags": event_payload["flags"],
                "messages": event_payload["messages"],
            },
            "X-Event-Editor-Token",
        )

        self.assertIsNotNone(map_result["resolved"])
        self.assertIn(
            "empty_commands",
            {item["code"] for item in event_result["diagnostics"]},
        )

    def test_refreshes_each_editor_session_token(self) -> None:
        map_token = self.get_json(
            "/map/api/session-token",
            {"X-Map-Editor-Client": "map-editor-ui"},
        )
        event_token = self.get_json(
            "/event/api/session-token",
            {"X-Event-Editor-Client": "event-editor-ui"},
        )

        self.assertEqual(map_token["token"], "shared-token")
        self.assertEqual(event_token["token"], "shared-token")

    def test_rejects_applications_with_different_tokens(self) -> None:
        self.event_application.token = "different-token"

        with self.assertRaisesRegex(ValueError, "共通の認証トークン"):
            make_handler(self.map_application, self.event_application)


if __name__ == "__main__":
    unittest.main()
