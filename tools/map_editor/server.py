"""Serve the local browser UI for map authoring."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sys
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse
import webbrowser

from scripts.map_pipeline import (
    compile_map,
    initial_map_source,
    load_map_source,
    load_tileset,
    resolve_map,
    resolve_source_image,
    save_compiled_map,
    save_map_source,
    validate_map_source,
    validate_tileset,
)
from scripts.map_pipeline.tileset import Diagnostic


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = Path(__file__).resolve().parent / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8767
SESSION_CLIENT_HEADER = "map-editor-ui"
MAX_REQUEST_BYTES = 32 * 1024 * 1024
MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".gif": "image/gif",
}


def _valid_id(value: str) -> bool:
    return re.fullmatch(r"[a-z][a-z0-9_]*", value) is not None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    content_root = Path(os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")).resolve()
    parser = argparse.ArgumentParser(description="地面とオブジェクトを配置してマップを制作します。")
    parser.add_argument("--map", default="worldmap", dest="map_id", help="マップID（既定: worldmap）")
    parser.add_argument("--tileset", default="worldmap", help="新規マップで使うタイルセットID（既定: worldmap）")
    parser.add_argument("--profile", default="world", choices=("world", "dungeon", "town"))
    parser.add_argument("--width", type=int, default=32, help="新規マップの幅（既定: 32）")
    parser.add_argument("--height", type=int, default=24, help="新規マップの高さ（既定: 24）")
    parser.add_argument("--content-root", type=Path, default=content_root, help=argparse.SUPPRESS)
    parser.add_argument("--runtime-root", type=Path, default=PROJECT_ROOT / "app" / "maps", help=argparse.SUPPRESS)
    parser.add_argument("--palette", type=Path, default=PROJECT_ROOT / "app" / "assets.pyxpal", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="起動時にブラウザを自動で開きません。")
    return parser.parse_args(argv)


class MapEditorApplication:
    def __init__(
        self,
        content_root: Path,
        runtime_root: Path,
        map_id: str,
        tileset_id: str,
        profile: str,
        width: int,
        height: int,
        palette_path: Path | None = None,
        token: str | None = None,
    ):
        if not _valid_id(map_id) or not _valid_id(tileset_id):
            raise ValueError("マップIDとタイルセットIDはlower_snake_caseで指定してください。")
        self.content_root = content_root.resolve()
        self.runtime_root = runtime_root.resolve()
        self.map_id = map_id
        self.initial_tileset_id = tileset_id
        self.profile = profile
        self.width = width
        self.height = height
        self.palette_path = (palette_path or PROJECT_ROOT / "app" / "assets.pyxpal").resolve()
        self.token = token or secrets.token_urlsafe(24)
        self.source_path = (self.content_root / "maps" / "sources" / f"{map_id}.json").resolve()
        source_root = (self.content_root / "maps" / "sources").resolve()
        if source_root not in self.source_path.parents:
            raise ValueError("マップパスがcontent/maps/sources外です。")
        self.runtime_path = (self.runtime_root / f"{map_id}.json").resolve()
        if self.runtime_root not in self.runtime_path.parents:
            raise ValueError("生成先がruntime root外です。")

    def load_source(self) -> tuple[dict[str, Any], bool]:
        if self.source_path.is_file():
            return load_map_source(self.source_path), False
        tileset = self.load_tileset(self.initial_tileset_id)
        return initial_map_source(self.map_id, tileset, self.profile, self.width, self.height), True

    def load_tileset(self, tileset_id: str) -> dict[str, Any]:
        path = (self.content_root / "maps" / "tilesets" / f"{tileset_id}.json").resolve()
        tileset_root = (self.content_root / "maps" / "tilesets").resolve()
        if tileset_root not in path.parents or not path.is_file():
            raise FileNotFoundError(f"タイルセットが見つかりません: {path}")
        return load_tileset(path)

    def source_image(self, tileset: Mapping[str, Any]) -> Path:
        image_id = tileset.get("source_image_id")
        if not isinstance(image_id, str):
            raise ValueError("source_image_idが不正です。")
        return resolve_source_image(self.content_root, image_id)

    def validate(self, data: object) -> tuple[list[dict[str, str]], dict[str, Any] | None, dict[str, Any] | None]:
        if not isinstance(data, dict) or not isinstance(data.get("tileset_id"), str):
            issue = Diagnostic("error", "invalid_tileset_id", "tileset_id", "タイルセットIDが不正です。")
            return [issue.as_dict()], None, None
        try:
            tileset = self.load_tileset(data["tileset_id"])
            image_path = self.source_image(tileset)
        except (OSError, ValueError) as error:
            issue = Diagnostic("error", "missing_tileset", "tileset_id", str(error))
            return [issue.as_dict()], None, None
        tileset_diagnostics, image_info = validate_tileset(tileset, image_path, self.palette_path)
        map_diagnostics = validate_map_source(data, tileset)
        diagnostics = [*tileset_diagnostics, *map_diagnostics]
        resolved = None
        if not any(item.severity == "error" for item in diagnostics):
            try:
                resolved = resolve_map(data, tileset)
            except ValueError as error:
                diagnostics.append(Diagnostic("error", "resolve_failed", "$", str(error)))
        return [item.as_dict() for item in diagnostics], image_info.as_dict() if image_info else None, resolved

    def document_payload(self) -> dict[str, Any]:
        data, is_new = self.load_source()
        tileset = self.load_tileset(data["tileset_id"])
        diagnostics, image_info, resolved = self.validate(data)
        return {
            "data": data,
            "tileset": tileset,
            "diagnostics": diagnostics,
            "resolved": resolved,
            "image_info": image_info,
            "image_url": f"/api/source-image?token={self.token}",
            "is_new": is_new,
            "source_path": self._display_path(self.source_path),
            "runtime_path": self._display_path(self.runtime_path),
        }

    def save(self, data: object) -> dict[str, Any]:
        diagnostics, image_info, resolved = self.validate(data)
        if any(item["severity"] == "error" for item in diagnostics) or not isinstance(data, dict):
            return {"saved": False, "diagnostics": diagnostics, "image_info": image_info, "resolved": resolved}
        tileset = self.load_tileset(data["tileset_id"])
        try:
            compiled = compile_map(data, tileset, self.source_image(tileset), self.palette_path)
        except (OSError, ValueError) as error:
            diagnostics.append(Diagnostic("error", "compile_failed", "$", str(error)).as_dict())
            return {"saved": False, "diagnostics": diagnostics, "image_info": image_info, "resolved": resolved}
        save_map_source(self.source_path, data)
        save_compiled_map(self.runtime_path, compiled)
        return {
            "saved": True,
            "diagnostics": diagnostics,
            "image_info": image_info,
            "resolved": resolved,
            "source_hash": compiled.runtime["source_hash"],
        }

    @staticmethod
    def _display_path(path: Path) -> str:
        return path.relative_to(PROJECT_ROOT).as_posix() if PROJECT_ROOT in path.parents else path.as_posix()


def make_handler(application: MapEditorApplication) -> type[BaseHTTPRequestHandler]:
    class MapEditorHandler(BaseHTTPRequestHandler):
        server_version = "DA0MapEditor/1"

        def log_message(self, format: str, *args: object) -> None:
            if self.path.startswith("/api/") and args and str(args[1]) >= "400":
                super().log_message(format, *args)

        def _authorized(self, parsed=None) -> bool:
            parsed = parsed or urlparse(self.path)
            query_token = parse_qs(parsed.query).get("token", [None])[0]
            return query_token == application.token or self.headers.get("X-Map-Editor-Token") == application.token

        def _session_allowed(self) -> bool:
            host = urlparse(f"//{self.headers.get('Host', '')}").hostname
            return host == DEFAULT_HOST and self.headers.get("X-Map-Editor-Client") == SESSION_CLIENT_HEADER

        def _send_bytes(self, content: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(content)

        def _send_json(self, value: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send_bytes((json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8"), "application/json; charset=utf-8", status)

        def _error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/session-token":
                if not self._session_allowed():
                    self._error(HTTPStatus.FORBIDDEN, "セッション更新要求が不正です。")
                    return
                self._send_json({"token": application.token})
                return
            if parsed.path == "/api/document":
                if not self._authorized(parsed):
                    self._error(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                    return
                try:
                    self._send_json(application.document_payload())
                except (OSError, ValueError) as error:
                    self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                return
            if parsed.path == "/api/source-image":
                if not self._authorized(parsed):
                    self._error(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                    return
                try:
                    data, _is_new = application.load_source()
                    tileset = application.load_tileset(data["tileset_id"])
                    image_path = application.source_image(tileset)
                    self._send_bytes(image_path.read_bytes(), MIME_TYPES.get(image_path.suffix.lower(), "application/octet-stream"))
                except (OSError, ValueError) as error:
                    self._error(HTTPStatus.NOT_FOUND, str(error))
                return
            relative = "index.html" if parsed.path in ("", "/") else parsed.path.lstrip("/")
            static_path = (STATIC_ROOT / relative).resolve()
            if STATIC_ROOT not in static_path.parents or not static_path.is_file():
                self._error(HTTPStatus.NOT_FOUND, "ページが見つかりません。")
                return
            self._send_bytes(static_path.read_bytes(), MIME_TYPES.get(static_path.suffix.lower(), "application/octet-stream"))

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path not in ("/api/validate", "/api/resolve", "/api/save"):
                self._error(HTTPStatus.NOT_FOUND, "APIが見つかりません。")
                return
            if not self._authorized(parsed):
                self._error(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                self._error(HTTPStatus.BAD_REQUEST, "Content-Lengthが不正です。")
                return
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "リクエストサイズが不正です。")
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._error(HTTPStatus.BAD_REQUEST, "JSONを読み込めません。")
                return
            data = payload.get("data") if isinstance(payload, dict) else None
            try:
                if parsed.path == "/api/save":
                    response = application.save(data)
                else:
                    diagnostics, image_info, resolved = application.validate(data)
                    response = {"saved": False, "diagnostics": diagnostics, "image_info": image_info, "resolved": resolved}
                self._send_json(response)
            except (OSError, ValueError) as error:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    return MapEditorHandler


def create_server(application: MapEditorApplication, port: int) -> ThreadingHTTPServer:
    if not 0 <= port <= 65535:
        raise ValueError("portは0から65535で指定してください。")
    return ThreadingHTTPServer((DEFAULT_HOST, port), make_handler(application))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        application = MapEditorApplication(
            args.content_root,
            args.runtime_root,
            args.map_id,
            args.tileset,
            args.profile,
            args.width,
            args.height,
            palette_path=args.palette,
        )
        server = create_server(application, args.port)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    actual_port = server.server_address[1]
    url = f"http://{DEFAULT_HOST}:{actual_port}/?token={application.token}"
    print("Map Editorを起動しました。")
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
