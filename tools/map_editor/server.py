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
import tempfile
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
    validate_map_links,
    validate_map_event_links,
    validate_map_source,
    validate_tileset,
)
from scripts.event_pipeline import load_event_sources
from scripts.map_pipeline.tileset import Diagnostic


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = Path(__file__).resolve().parent / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8767
SESSION_CLIENT_HEADER = "map-editor-ui"
MAX_REQUEST_BYTES = 32 * 1024 * 1024
SITE_NAME_TEXT_PREFIX = "location."
ACTOR_ASSETS = {
    "prop": {
        "path": Path("actors/props.png"),
        "sprite_size": [16, 16],
    },
    "character": {
        "path": Path("actors/characters.png"),
        "sprite_size": [32, 64],
    },
}
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
        self.texts_path = (self.content_root / "data" / "texts.json").resolve()
        data_root = (self.content_root / "data").resolve()
        if data_root not in self.texts_path.parents:
            raise ValueError("文言パスがcontent/data外です。")

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

    def actor_image(self, asset_id: str) -> Path:
        asset = ACTOR_ASSETS.get(asset_id)
        if asset is None:
            raise ValueError(f"actor画像種別が不正です: {asset_id}")
        image_root = (self.content_root / "images").resolve()
        image_path = (image_root / asset["path"]).resolve()
        if image_root not in image_path.parents or not image_path.is_file():
            raise FileNotFoundError(f"actor画像が見つかりません: {image_path}")
        return image_path

    def actor_assets_payload(self) -> dict[str, dict[str, object]]:
        return {
            asset_id: {
                "image_url": f"/api/actor-image?asset={asset_id}&token={self.token}",
                "sprite_size": list(asset["sprite_size"]),
            }
            for asset_id, asset in ACTOR_ASSETS.items()
        }

    def map_sources(self, current: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
        source_dir = self.content_root / "maps" / "sources"
        loaded: dict[str, Mapping[str, Any]] = {}
        if source_dir.is_dir():
            for path in sorted(source_dir.glob("*.json")):
                source = load_map_source(path)
                map_id = source.get("map_id")
                if isinstance(map_id, str):
                    loaded[map_id] = source
        current_id = current.get("map_id")
        if isinstance(current_id, str):
            loaded[current_id] = current
        return loaded

    def destination_options(
        self,
        current: Mapping[str, Any],
    ) -> list[dict[str, object]]:
        return [
            {
                "map_id": map_id,
                "arrival_ids": [
                    arrival.get("id")
                    for arrival in source.get("arrival_points", [])
                    if isinstance(arrival, Mapping)
                    and isinstance(arrival.get("id"), str)
                ],
            }
            for map_id, source in sorted(self.map_sources(current).items())
        ]

    def site_options(self, current: Mapping[str, Any]) -> list[str]:
        return sorted(
            {
                site.get("id")
                for source in self.map_sources(current).values()
                for site in source.get("sites", [])
                if isinstance(site, Mapping) and isinstance(site.get("id"), str)
            }
        )

    def event_options(self) -> list[str]:
        return sorted(self.event_definitions())

    def event_definitions(self) -> dict[str, Mapping[str, Any]]:
        return {
            f"{source.get('namespace')}.{event.get('id')}": event
            for source in load_event_sources(self.content_root).values()
            if isinstance(source.get("namespace"), str)
            for event in source.get("events", [])
            if isinstance(event, Mapping) and isinstance(event.get("id"), str)
        }

    def load_text_records(self) -> list[dict[str, Any]]:
        if not self.texts_path.is_file():
            return []
        try:
            value = json.loads(self.texts_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"文言JSONを読み込めません: {self.texts_path}: {error}"
            ) from error
        if not isinstance(value, list) or not all(
            isinstance(record, dict) for record in value
        ):
            raise ValueError("content/data/texts.jsonはobjectの配列である必要があります。")
        return value

    @staticmethod
    def site_name_text_key(site_id: str) -> str:
        return f"{SITE_NAME_TEXT_PREFIX}{site_id}"

    def site_names_ja(self, data: Mapping[str, Any]) -> dict[str, str]:
        records = {
            record.get("text_key"): record
            for record in self.load_text_records()
            if isinstance(record.get("text_key"), str)
        }
        names: dict[str, str] = {}
        sites = data.get("sites")
        if not isinstance(sites, list):
            return names
        for site in sites:
            if not isinstance(site, Mapping) or not isinstance(site.get("id"), str):
                continue
            site_id = site["id"]
            value = records.get(self.site_name_text_key(site_id), {}).get("text_ja", "")
            names[site_id] = value if isinstance(value, str) else ""
        return names

    @staticmethod
    def _site_name_diagnostics(
        data: object,
        site_names_ja: object,
    ) -> list[Diagnostic]:
        if not isinstance(data, Mapping):
            return []
        sites = data.get("sites")
        if not isinstance(sites, list):
            return []
        if not isinstance(site_names_ja, Mapping):
            return [
                Diagnostic(
                    "error",
                    "invalid_site_names_ja",
                    "site_names_ja",
                    "拠点の日本語名が不正です。",
                )
            ]
        diagnostics = []
        for index, site in enumerate(sites):
            if not isinstance(site, Mapping) or not isinstance(site.get("id"), str):
                continue
            site_id = site["id"]
            name = site_names_ja.get(site_id)
            if not isinstance(name, str) or not name.strip():
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "missing_site_name_ja",
                        f"sites[{index}].name_ja",
                        "拠点の日本語名を入力してください。",
                    )
                )
        return diagnostics

    def validate(
        self,
        data: object,
        site_names_ja: object | None = None,
    ) -> tuple[list[dict[str, str]], dict[str, Any] | None, dict[str, Any] | None]:
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
        link_diagnostics = (
            [
                item
                for item in validate_map_links(self.map_sources(data))
                if item.path.startswith(f"{data.get('map_id')}.")
            ]
            if isinstance(data, dict)
            else []
        )
        event_link_diagnostics = (
            [
                item
                for item in validate_map_event_links(
                    self.map_sources(data), self.event_definitions()
                )
                if item.path.startswith(f"{data.get('map_id')}.")
            ]
            if isinstance(data, dict)
            else []
        )
        if site_names_ja is None and isinstance(data, Mapping):
            site_names_ja = self.site_names_ja(data)
        name_diagnostics = self._site_name_diagnostics(data, site_names_ja)
        diagnostics = [
            *tileset_diagnostics,
            *map_diagnostics,
            *link_diagnostics,
            *event_link_diagnostics,
            *name_diagnostics,
        ]
        resolved = None
        has_errors = any(item.severity == "error" for item in diagnostics)
        tileset_has_errors = any(
            item.severity == "error" for item in tileset_diagnostics
        )
        if not tileset_has_errors:
            try:
                resolved = resolve_map(data, tileset)
            except ValueError as error:
                if has_errors:
                    preview_data = {
                        **data,
                        "sites": [],
                        "arrival_points": [],
                        "actors": [],
                        "event_triggers": [],
                    }
                    try:
                        resolved = resolve_map(preview_data, tileset)
                    except ValueError:
                        pass
                else:
                    diagnostics.append(Diagnostic("error", "resolve_failed", "$", str(error)))
        return [item.as_dict() for item in diagnostics], image_info.as_dict() if image_info else None, resolved

    def document_payload(self) -> dict[str, Any]:
        data, is_new = self.load_source()
        tileset = self.load_tileset(data["tileset_id"])
        site_names_ja = self.site_names_ja(data)
        diagnostics, image_info, resolved = self.validate(data, site_names_ja)
        return {
            "data": data,
            "site_names_ja": site_names_ja,
            "destination_options": self.destination_options(data),
            "site_options": self.site_options(data),
            "event_options": self.event_options(),
            "tileset": tileset,
            "diagnostics": diagnostics,
            "resolved": resolved,
            "image_info": image_info,
            "image_url": f"/api/source-image?token={self.token}",
            "actor_assets": self.actor_assets_payload(),
            "is_new": is_new,
            "source_path": self._display_path(self.source_path),
            "runtime_path": self._display_path(self.runtime_path),
        }

    def save(
        self,
        data: object,
        site_names_ja: object,
    ) -> dict[str, Any]:
        diagnostics, image_info, resolved = self.validate(data, site_names_ja)
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
        self._save_site_names(data, site_names_ja)
        return {
            "saved": True,
            "diagnostics": diagnostics,
            "image_info": image_info,
            "resolved": resolved,
            "source_hash": compiled.runtime["source_hash"],
        }

    def _save_site_names(
        self,
        data: Mapping[str, Any],
        site_names_ja: object,
    ) -> None:
        if not isinstance(site_names_ja, Mapping):
            raise ValueError("拠点の日本語名が不正です。")
        sites = data.get("sites", [])
        if not sites:
            return
        records = self.load_text_records()
        by_key = {
            record.get("text_key"): record
            for record in records
            if isinstance(record.get("text_key"), str)
        }
        for site in sites:
            site_id = site["id"]
            key = self.site_name_text_key(site_id)
            name = site_names_ja[site_id].strip()
            record = by_key.get(key)
            if record is None:
                record = {
                    "text_key": key,
                    "text_ja": name,
                    "text_en": "",
                    "text_zhcn": "",
                }
                records.append(record)
                by_key[key] = record
            else:
                record["text_ja"] = name
                record.setdefault("text_en", "")
                record.setdefault("text_zhcn", "")
                record.pop("pending", None)
        content = (json.dumps(records, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        if self.texts_path.is_file() and self.texts_path.read_bytes() == content:
            return
        self.texts_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.texts_path.parent,
                prefix=f".{self.texts_path.name}.",
                delete=False,
            ) as temporary:
                temporary.write(content)
                temporary.flush()
                temporary_path = Path(temporary.name)
            temporary_path.replace(self.texts_path)
        except BaseException:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

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
            if parsed.path == "/api/actor-image":
                if not self._authorized(parsed):
                    self._error(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                    return
                try:
                    asset_id = parse_qs(parsed.query).get("asset", [""])[0]
                    image_path = application.actor_image(asset_id)
                    self._send_bytes(
                        image_path.read_bytes(),
                        MIME_TYPES.get(
                            image_path.suffix.lower(), "application/octet-stream"
                        ),
                    )
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
            site_names_ja = (
                payload.get("site_names_ja")
                if isinstance(payload, dict)
                else None
            )
            try:
                if parsed.path == "/api/save":
                    response = application.save(data, site_names_ja)
                else:
                    diagnostics, image_info, resolved = application.validate(
                        data,
                        site_names_ja,
                    )
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
