"""Serve the map and event editors from one local entry point."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import parse_qs, urlencode, urlparse
import webbrowser

from scripts.event_pipeline import load_event_flags, load_event_messages
from tools.event_editor.server import EventEditorApplication
from tools.map_editor.server import MapEditorApplication


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8767
MAX_REQUEST_BYTES = {
    "event": 8 * 1024 * 1024,
    "map": 32 * 1024 * 1024,
}
STATIC_ROOTS = {
    "event": PROJECT_ROOT / "tools" / "event_editor" / "static",
    "map": PROJECT_ROOT / "tools" / "map_editor" / "static",
}
MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".gif": "image/gif",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
}
CLIENT_HEADERS = {
    "event": ("X-Event-Editor-Client", "event-editor-ui"),
    "map": ("X-Map-Editor-Client", "map-editor-ui"),
}
TOKEN_HEADERS = {
    "event": "X-Event-Editor-Token",
    "map": "X-Map-Editor-Token",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    content_root = Path(
        os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")
    ).resolve()
    parser = argparse.ArgumentParser(
        description="マップエディタとイベントエディタをまとめて起動します。"
    )
    parser.add_argument(
        "--editor",
        choices=("map", "event"),
        default="map",
        help="最初に表示するエディタ（既定: map）",
    )
    parser.add_argument(
        "--map", default="worldmap", dest="map_id", help="マップID（既定: worldmap）"
    )
    parser.add_argument(
        "--tileset",
        default="worldmap",
        help="新規マップで使うタイルセットID（既定: worldmap）",
    )
    parser.add_argument(
        "--profile", default="world", choices=("world", "dungeon", "town")
    )
    parser.add_argument("--width", type=int, default=32, help="新規マップの幅（既定: 32）")
    parser.add_argument("--height", type=int, default=24, help="新規マップの高さ（既定: 24）")
    parser.add_argument(
        "--namespace",
        default="common",
        help="最初に表示するイベントnamespace（既定: common）",
    )
    parser.add_argument(
        "--content-root", type=Path, default=content_root, help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--map-runtime-root",
        "--runtime-root",
        dest="map_runtime_root",
        type=Path,
        default=PROJECT_ROOT / "app" / "maps",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--event-runtime",
        "--runtime",
        dest="event_runtime",
        type=Path,
        default=PROJECT_ROOT / "app" / "events" / "events.json",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--app-root",
        type=Path,
        default=PROJECT_ROOT / "app",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--palette",
        type=Path,
        default=PROJECT_ROOT / "app" / "assets.pyxpal",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--no-browser", action="store_true", help="起動時にブラウザを自動で開きません。"
    )
    return parser.parse_args(argv)


def make_handler(
    map_application: MapEditorApplication,
    event_application: EventEditorApplication,
) -> type[BaseHTTPRequestHandler]:
    applications = {
        "map": map_application,
        "event": event_application,
    }
    if map_application.token != event_application.token:
        raise ValueError("統合エディタでは共通の認証トークンが必要です。")

    class EditorHandler(BaseHTTPRequestHandler):
        server_version = "DA0Editor/1"

        def log_message(self, format: str, *args: object) -> None:
            if "/api/" in self.path and args and str(args[1]) >= "400":
                super().log_message(format, *args)

        def _send_bytes(
            self,
            content: bytes,
            content_type: str,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(content)

        def _send_json(
            self, value: object, status: HTTPStatus = HTTPStatus.OK
        ) -> None:
            self._send_bytes(
                (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8"),
                "application/json; charset=utf-8",
                status,
            )

        def _error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status)

        def _redirect(self, location: str) -> None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        @staticmethod
        def _editor_route(path: str) -> tuple[str, str] | None:
            for editor in ("map", "event"):
                prefix = f"/{editor}"
                if path == prefix:
                    return editor, ""
                if path.startswith(f"{prefix}/"):
                    return editor, path[len(prefix) :]
            return None

        def _authorized(self, editor: str, parsed) -> bool:
            query_token = parse_qs(parsed.query).get("token", [None])[0]
            application = applications[editor]
            return query_token == application.token or self.headers.get(
                TOKEN_HEADERS[editor]
            ) == application.token

        def _session_allowed(self, editor: str) -> bool:
            header, expected = CLIENT_HEADERS[editor]
            host = urlparse(f"//{self.headers.get('Host', '')}").hostname
            return host == DEFAULT_HOST and self.headers.get(header) == expected

        def _serve_static(self, editor: str, path: str) -> None:
            relative = "index.html" if path in ("", "/") else path.lstrip("/")
            static_root = STATIC_ROOTS[editor].resolve()
            static_path = (static_root / relative).resolve()
            if static_root not in static_path.parents or not static_path.is_file():
                self._error(HTTPStatus.NOT_FOUND, "ページが見つかりません。")
                return
            self._send_bytes(
                static_path.read_bytes(),
                MIME_TYPES.get(
                    static_path.suffix.lower(), "application/octet-stream"
                ),
            )

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                query = f"?{parsed.query}" if parsed.query else ""
                self._redirect(f"/map/{query}")
                return
            route = self._editor_route(parsed.path)
            if route is None:
                self._error(HTTPStatus.NOT_FOUND, "ページが見つかりません。")
                return
            editor, path = route
            if not path:
                query = f"?{parsed.query}" if parsed.query else ""
                self._redirect(f"/{editor}/{query}")
                return
            application = applications[editor]
            if path == "/api/session-token":
                if not self._session_allowed(editor):
                    self._error(HTTPStatus.FORBIDDEN, "セッション更新要求が不正です。")
                    return
                self._send_json({"token": application.token})
                return
            if path == "/api/document":
                if not self._authorized(editor, parsed):
                    self._error(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                    return
                try:
                    if editor == "event":
                        namespace = parse_qs(parsed.query).get(
                            "namespace", [event_application.namespace]
                        )[0]
                        payload = event_application.document_payload(namespace)
                    else:
                        payload = map_application.document_payload()
                    self._send_json(payload)
                except (OSError, ValueError) as error:
                    self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                return
            if editor == "map" and path == "/api/source-image":
                if not self._authorized(editor, parsed):
                    self._error(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                    return
                try:
                    data, _is_new = map_application.load_source()
                    tileset = map_application.load_tileset(data["tileset_id"])
                    image_path = map_application.source_image(tileset)
                    self._send_bytes(
                        image_path.read_bytes(),
                        MIME_TYPES.get(
                            image_path.suffix.lower(), "application/octet-stream"
                        ),
                    )
                except (OSError, ValueError) as error:
                    self._error(HTTPStatus.NOT_FOUND, str(error))
                return
            self._serve_static(editor, path)

        def _read_payload(self, editor: str) -> tuple[bool, object]:
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                self._error(HTTPStatus.BAD_REQUEST, "Content-Lengthが不正です。")
                return False, None
            if length <= 0 or length > MAX_REQUEST_BYTES[editor]:
                self._error(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    "リクエストサイズが不正です。",
                )
                return False, None
            try:
                return True, json.loads(self.rfile.read(length))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._error(HTTPStatus.BAD_REQUEST, "JSONを読み込めません。")
                return False, None

        def _event_response(self, path: str, payload: object) -> object:
            data = payload.get("data") if isinstance(payload, dict) else None
            flags = payload.get("flags") if isinstance(payload, dict) else None
            messages = payload.get("messages") if isinstance(payload, dict) else None
            namespace = (
                payload.get("namespace") if isinstance(payload, dict) else None
            )
            if not isinstance(namespace, str) and isinstance(data, dict):
                namespace = data.get("namespace")
            if not isinstance(namespace, str):
                namespace = event_application.namespace
            if flags is None:
                flags = load_event_flags(event_application.content_root)
            if messages is None:
                messages = load_event_messages(event_application.content_root)
            if path == "/api/save":
                return event_application.save(
                    namespace, data, flags, messages
                )
            return {
                "saved": False,
                "diagnostics": event_application.validate(
                    namespace, data, flags, messages
                ),
            }

        def _map_response(self, path: str, payload: object) -> object:
            data = payload.get("data") if isinstance(payload, dict) else None
            site_names_ja = (
                payload.get("site_names_ja")
                if isinstance(payload, dict)
                else None
            )
            if path == "/api/save":
                return map_application.save(data, site_names_ja)
            diagnostics, image_info, resolved = map_application.validate(
                data, site_names_ja
            )
            return {
                "saved": False,
                "diagnostics": diagnostics,
                "image_info": image_info,
                "resolved": resolved,
            }

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            route = self._editor_route(parsed.path)
            if route is None:
                self._error(HTTPStatus.NOT_FOUND, "APIが見つかりません。")
                return
            editor, path = route
            allowed_paths = (
                {"/api/validate", "/api/resolve", "/api/save"}
                if editor == "map"
                else {"/api/validate", "/api/save"}
            )
            if path not in allowed_paths:
                self._error(HTTPStatus.NOT_FOUND, "APIが見つかりません。")
                return
            if not self._authorized(editor, parsed):
                self._error(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                return
            valid_payload, payload = self._read_payload(editor)
            if not valid_payload:
                return
            try:
                response = (
                    self._map_response(path, payload)
                    if editor == "map"
                    else self._event_response(path, payload)
                )
                self._send_json(response)
            except (OSError, ValueError) as error:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    return EditorHandler


def create_server(
    map_application: MapEditorApplication,
    event_application: EventEditorApplication,
    port: int,
) -> ThreadingHTTPServer:
    if not 0 <= port <= 65535:
        raise ValueError("portは0から65535で指定してください。")
    return ThreadingHTTPServer(
        (DEFAULT_HOST, port), make_handler(map_application, event_application)
    )


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parse_args(raw_argv)
    namespace_requested = any(
        argument == "--namespace" or argument.startswith("--namespace=")
        for argument in raw_argv
    )
    token = secrets.token_urlsafe(24)
    try:
        map_application = MapEditorApplication(
            args.content_root,
            args.map_runtime_root,
            args.map_id,
            args.tileset,
            args.profile,
            args.width,
            args.height,
            palette_path=args.palette,
            token=token,
        )
        event_application = EventEditorApplication(
            args.content_root,
            args.event_runtime,
            args.namespace,
            token=token,
            app_root=args.app_root,
        )
        server = create_server(map_application, event_application, args.port)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    actual_port = server.server_address[1]
    query = {"token": token}
    if args.editor == "event" and namespace_requested:
        query["namespace"] = args.namespace
    url = (
        f"http://{DEFAULT_HOST}:{actual_port}/{args.editor}/?"
        f"{urlencode(query)}"
    )
    print("Dungeon Antiqua ZERO Editorを起動しました。")
    print(url)
    print("終了するにはこのターミナルでCtrl+Cを押してください。")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n終了します。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
