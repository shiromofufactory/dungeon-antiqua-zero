"""Serve the local browser UI for map-chip metadata editing."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse
import webbrowser

from scripts.map_pipeline import (
    initial_worldmap_tileset,
    load_tileset,
    resolve_source_image,
    save_tileset,
    validate_tileset,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = Path(__file__).resolve().parent / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SESSION_CLIENT_HEADER = "mapchip-metadata-ui"
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".gif": "image/gif",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    content_root = Path(
        os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")
    ).resolve()
    parser = argparse.ArgumentParser(
        description="16x16マップチップの表示・境界・通行メタデータを編集します。"
    )
    parser.add_argument(
        "--tileset",
        default="worldmap",
        help="content/maps/tilesets内のタイルセットID（既定: worldmap）",
    )
    parser.add_argument(
        "--content-root",
        type=Path,
        default=content_root,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="起動時にブラウザを自動で開きません。",
    )
    return parser.parse_args(argv)


def _valid_tileset_name(value: str) -> bool:
    return bool(value) and value.replace("_", "a").isalnum() and value.isascii()


class MetadataApplication:
    def __init__(
        self,
        content_root: Path,
        tileset_id: str,
        token: str | None = None,
    ):
        if not _valid_tileset_name(tileset_id):
            raise ValueError("タイルセットIDが不正です。")
        self.content_root = content_root.resolve()
        self.tileset_id = tileset_id
        self.metadata_path = (
            self.content_root / "maps" / "tilesets" / f"{tileset_id}.json"
        ).resolve()
        expected_root = (self.content_root / "maps" / "tilesets").resolve()
        if expected_root not in self.metadata_path.parents:
            raise ValueError("メタデータパスがcontent/maps/tilesets外です。")
        self.palette_path = PROJECT_ROOT / "app" / "assets.pyxpal"
        self.token = token or secrets.token_urlsafe(24)

    def load(self) -> dict[str, Any]:
        if self.metadata_path.is_file():
            return load_tileset(self.metadata_path)
        if self.tileset_id == "worldmap":
            return initial_worldmap_tileset()
        raise FileNotFoundError(f"タイルセットが見つかりません: {self.metadata_path}")

    def source_image(self, data: Mapping[str, Any]) -> Path:
        image_id = data.get("source_image_id")
        if not isinstance(image_id, str):
            raise ValueError("source_image_idが不正です。")
        return resolve_source_image(self.content_root, image_id)

    def validate(self, data: object) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
        image_path: Path | None = None
        if isinstance(data, dict) and isinstance(data.get("source_image_id"), str):
            try:
                image_path = self.source_image(data)
            except (FileNotFoundError, ValueError):
                image_path = self.content_root / "images" / "__missing__.png"
        diagnostics, image_info = validate_tileset(
            data,
            image_path=image_path,
            palette_path=self.palette_path,
        )
        return (
            [diagnostic.as_dict() for diagnostic in diagnostics],
            image_info.as_dict() if image_info is not None else None,
        )

    def document_payload(self) -> dict[str, Any]:
        data = self.load()
        diagnostics, image_info = self.validate(data)
        return {
            "data": data,
            "diagnostics": diagnostics,
            "image_info": image_info,
            "image_url": f"/api/source-image?token={self.token}",
            "metadata_path": self.metadata_path.relative_to(PROJECT_ROOT).as_posix()
            if PROJECT_ROOT in self.metadata_path.parents
            else self.metadata_path.as_posix(),
        }

    def save(self, data: object) -> dict[str, Any]:
        diagnostics, image_info = self.validate(data)
        has_errors = any(item["severity"] == "error" for item in diagnostics)
        if not has_errors and isinstance(data, dict):
            save_tileset(self.metadata_path, data)
        return {
            "saved": not has_errors,
            "diagnostics": diagnostics,
            "image_info": image_info,
        }


def make_handler(application: MetadataApplication) -> type[BaseHTTPRequestHandler]:
    class MetadataHandler(BaseHTTPRequestHandler):
        server_version = "DA0MapchipMetadata/1"

        def log_message(self, format: str, *args: object) -> None:
            if self.path.startswith("/api/") and args and str(args[1]) >= "400":
                super().log_message(format, *args)

        def _authorized(self, parsed_path=None) -> bool:
            parsed = parsed_path or urlparse(self.path)
            query_token = parse_qs(parsed.query).get("token", [None])[0]
            header_token = self.headers.get("X-Mapchip-Token")
            return query_token == application.token or header_token == application.token

        def _session_token_request_allowed(self) -> bool:
            host = urlparse(f"//{self.headers.get('Host', '')}").hostname
            return (
                host == DEFAULT_HOST
                and self.headers.get("X-Mapchip-Client") == SESSION_CLIENT_HEADER
            )

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
            self,
            value: object,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            content = (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8")
            self._send_bytes(content, "application/json; charset=utf-8", status)

        def _send_error_json(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            if parsed.path == "/api/session-token":
                if not self._session_token_request_allowed():
                    self._send_error_json(HTTPStatus.FORBIDDEN, "セッション更新要求が不正です。")
                    return
                self._send_json({"token": application.token})
                return
            if parsed.path == "/api/document":
                if not self._authorized(parsed):
                    self._send_error_json(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                    return
                try:
                    self._send_json(application.document_payload())
                except (OSError, ValueError) as error:
                    self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                return
            if parsed.path == "/api/source-image":
                if not self._authorized(parsed):
                    self._send_error_json(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                    return
                try:
                    data = application.load()
                    image_path = application.source_image(data)
                    self._send_bytes(
                        image_path.read_bytes(),
                        MIME_TYPES.get(image_path.suffix.lower(), "application/octet-stream"),
                    )
                except (OSError, ValueError) as error:
                    self._send_error_json(HTTPStatus.NOT_FOUND, str(error))
                return

            relative = "index.html" if parsed.path in ("", "/") else parsed.path.lstrip("/")
            static_path = (STATIC_ROOT / relative).resolve()
            if STATIC_ROOT not in static_path.parents or not static_path.is_file():
                self._send_error_json(HTTPStatus.NOT_FOUND, "ページが見つかりません。")
                return
            self._send_bytes(
                static_path.read_bytes(),
                MIME_TYPES.get(static_path.suffix.lower(), "application/octet-stream"),
            )

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            if parsed.path not in ("/api/validate", "/api/save"):
                self._send_error_json(HTTPStatus.NOT_FOUND, "APIが見つかりません。")
                return
            if not self._authorized(parsed):
                self._send_error_json(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                return
            length_text = self.headers.get("Content-Length")
            try:
                length = int(length_text or "0")
            except ValueError:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "Content-Lengthが不正です。")
                return
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self._send_error_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "リクエストサイズが不正です。")
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_error_json(HTTPStatus.BAD_REQUEST, "JSONを読み込めません。")
                return
            data = payload.get("data") if isinstance(payload, dict) else None
            try:
                if parsed.path == "/api/save":
                    response = application.save(data)
                else:
                    diagnostics, image_info = application.validate(data)
                    response = {
                        "saved": False,
                        "diagnostics": diagnostics,
                        "image_info": image_info,
                    }
                self._send_json(response)
            except OSError as error:
                self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    return MetadataHandler


def create_server(
    application: MetadataApplication,
    port: int,
) -> ThreadingHTTPServer:
    if not 0 <= port <= 65535:
        raise ValueError("portは0から65535で指定してください。")
    return ThreadingHTTPServer((DEFAULT_HOST, port), make_handler(application))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        application = MetadataApplication(
            args.content_root,
            args.tileset,
        )
        server = create_server(application, args.port)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    actual_port = server.server_address[1]
    url = f"http://{DEFAULT_HOST}:{actual_port}/?token={application.token}"
    print("Map Chip Metadata Toolを起動しました。")
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
