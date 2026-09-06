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
from urllib.parse import parse_qs, urlencode, urlparse
import webbrowser

from scripts.map_pipeline import (
    compile_map,
    CompiledMap,
    Diagnostic,
    initial_tileset,
    initial_worldmap_tileset,
    load_map_source,
    load_tileset,
    resolve_source_image,
    save_compiled_map,
    save_map_source,
    save_tileset,
    validate_tileset,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = Path(__file__).resolve().parent / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SESSION_CLIENT_HEADER = "mapchip-metadata-ui"
MAX_REQUEST_BYTES = 4 * 1024 * 1024
PROTECTED_TILESET_IDS = frozenset(("worldmap",))
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
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=PROJECT_ROOT / "app" / "maps",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="起動時にブラウザを自動で開きません。",
    )
    return parser.parse_args(argv)


def _valid_tileset_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value.replace("_", "a").isalnum()
        and value.isascii()
    )


class MetadataApplication:
    def __init__(
        self,
        content_root: Path,
        tileset_id: str,
        token: str | None = None,
        palette_path: Path | None = None,
        runtime_root: Path | None = None,
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
        self.palette_path = (
            palette_path or PROJECT_ROOT / "app" / "assets.pyxpal"
        ).resolve()
        self.runtime_root = runtime_root.resolve() if runtime_root is not None else None
        self.token = token or secrets.token_urlsafe(24)

    def metadata_path_for(self, tileset_id: str) -> Path:
        if not _valid_tileset_name(tileset_id):
            raise ValueError("タイルセットIDが不正です。")
        path = (
            self.content_root / "maps" / "tilesets" / f"{tileset_id}.json"
        ).resolve()
        expected_root = (self.content_root / "maps" / "tilesets").resolve()
        if expected_root not in path.parents:
            raise ValueError("メタデータパスがcontent/maps/tilesets外です。")
        return path

    def load(self, tileset_id: str | None = None) -> dict[str, Any]:
        target_id = tileset_id or self.tileset_id
        metadata_path = self.metadata_path_for(target_id)
        if metadata_path.is_file():
            return load_tileset(metadata_path)
        if target_id == self.tileset_id == "worldmap":
            return initial_worldmap_tileset()
        raise FileNotFoundError(f"タイルセットが見つかりません: {metadata_path}")

    def source_image_catalog(self) -> list[dict[str, object]]:
        image_root = (self.content_root / "images" / "mapchips").resolve()
        catalog = []
        if not image_root.is_dir():
            return catalog
        seen: set[str] = set()
        for path in sorted(image_root.iterdir()):
            if path.suffix.lower() not in (".png", ".gif"):
                continue
            image_id = f"mapchips/{path.stem}"
            if image_id in seen:
                raise ValueError(f"同じ画像IDのPNGとGIFが存在します: {image_id}")
            seen.add(image_id)
            catalog.append({"image_id": image_id, "file_name": path.name})
        return catalog

    def tileset_catalog(self) -> list[dict[str, object]]:
        references: dict[str, list[str]] = {}
        map_root = self.content_root / "maps" / "sources"
        if map_root.is_dir():
            for path in sorted(map_root.glob("*.json")):
                source = load_map_source(path)
                map_id = source.get("map_id")
                tileset_id = source.get("tileset_id")
                if isinstance(map_id, str) and isinstance(tileset_id, str):
                    references.setdefault(tileset_id, []).append(map_id)
        tileset_root = self.content_root / "maps" / "tilesets"
        catalog = []
        if tileset_root.is_dir():
            for path in sorted(tileset_root.glob("*.json")):
                data = load_tileset(path)
                tileset_id = data.get("tileset_id")
                if not isinstance(tileset_id, str) or path.stem != tileset_id:
                    raise ValueError(f"タイルセットIDとファイル名が一致しません: {path}")
                grounds = data.get("grounds", [])
                catalog.append(
                    {
                        "tileset_id": tileset_id,
                        "source_image_id": data.get("source_image_id"),
                        "profile": data.get("profile"),
                        "base_ground_id": (
                            grounds[0].get("id")
                            if grounds and isinstance(grounds[0], Mapping)
                            else None
                        ),
                        "map_ids": references.get(tileset_id, []),
                    }
                )
        return catalog

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
        if isinstance(data, dict) and isinstance(data.get("tileset_id"), str):
            existing_path = self.metadata_path_for(data["tileset_id"])
            if existing_path.is_file():
                existing = load_tileset(existing_path)
                existing_grounds = existing.get("grounds", [])
                candidate_grounds = data.get("grounds", [])
                existing_base_id = (
                    existing_grounds[0].get("id")
                    if existing_grounds and isinstance(existing_grounds[0], Mapping)
                    else None
                )
                candidate_base_id = (
                    candidate_grounds[0].get("id")
                    if candidate_grounds and isinstance(candidate_grounds[0], Mapping)
                    else None
                )
                if existing_base_id != candidate_base_id:
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "base_ground_is_immutable",
                            "grounds[0].id",
                            "作成済みタイルセットのベース地面は変更できません。",
                        )
                    )
                if existing.get("profile") != data.get("profile"):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "profile_is_immutable",
                            "profile",
                            "作成済みタイルセットのprofileは変更できません。",
                        )
                    )
                if existing.get("source_image_id") != data.get("source_image_id"):
                    diagnostics.append(
                        Diagnostic(
                            "error",
                            "source_image_is_immutable",
                            "source_image_id",
                            "作成済みタイルセットのソース画像は変更できません。",
                        )
                    )
        return (
            [diagnostic.as_dict() for diagnostic in diagnostics],
            image_info.as_dict() if image_info is not None else None,
        )

    def _document_payload(self, data: dict[str, Any], *, is_new: bool) -> dict[str, Any]:
        diagnostics, image_info = self.validate(data)
        return {
            "data": data,
            "diagnostics": diagnostics,
            "image_info": image_info,
            "image_url": f"/api/source-image?{urlencode({'source': data['source_image_id'], 'token': self.token})}",
            "is_new": is_new,
        }

    def document_payload(self, tileset_id: str | None = None) -> dict[str, Any]:
        target_id = tileset_id or self.tileset_id
        data = self.load(target_id)
        return self._document_payload(
            data,
            is_new=not self.metadata_path_for(target_id).is_file(),
        )

    def create_document_payload(
        self,
        tileset_id: str,
        source_image_id: str,
        profile: str,
        base_ground_id: str,
        base_collision: str,
    ) -> dict[str, Any]:
        if not isinstance(tileset_id, str) or not isinstance(source_image_id, str):
            raise ValueError("タイルセットIDまたはソース画像IDが不正です。")
        if not isinstance(base_ground_id, str) or not isinstance(base_collision, str):
            raise ValueError("ベース地面の設定が不正です。")
        path = self.metadata_path_for(tileset_id)
        if path.exists():
            raise ValueError(f"タイルセットIDはすでに使用されています: {tileset_id}")
        if not isinstance(profile, str):
            raise ValueError("profileが不正です。")
        resolve_source_image(self.content_root, source_image_id)
        data = initial_tileset(
            tileset_id,
            source_image_id,
            profile,
            base_ground_id,
            base_collision,
        )
        return self._document_payload(data, is_new=True)

    def _prepare_map_object_updates(
        self,
        data: Mapping[str, Any],
        object_id_renames: object,
    ) -> tuple[
        list[tuple[Path, dict[str, Any], dict[str, Any]]],
        list[dict[str, str]],
        int,
    ]:
        diagnostics: list[dict[str, str]] = []
        if object_id_renames is None:
            renames: Mapping[object, object] = {}
        elif isinstance(object_id_renames, Mapping):
            renames = object_id_renames
        else:
            diagnostics.append(
                Diagnostic(
                    "error",
                    "invalid_object_id_renames",
                    "object_id_renames",
                    "オブジェクトIDの変更情報が不正です。",
                ).as_dict()
            )
            return [], diagnostics, 0

        tileset_id = data.get("tileset_id")
        metadata_path = (
            self.metadata_path_for(tileset_id)
            if isinstance(tileset_id, str)
            else None
        )
        previous_ids: set[str] = set()
        if metadata_path is not None and metadata_path.is_file():
            previous_ids = {
                item.get("id")
                for item in load_tileset(metadata_path).get("objects", [])
                if isinstance(item, Mapping) and isinstance(item.get("id"), str)
            }
        object_definitions = data.get("objects")
        has_object_definition_list = isinstance(object_definitions, list)
        can_reconcile_object_definitions = (
            has_object_definition_list
            and all(
                isinstance(item, Mapping) and isinstance(item.get("id"), str)
                for item in object_definitions
            )
        )
        current_ids = {
            item.get("id")
            for item in object_definitions
            if isinstance(item, Mapping) and isinstance(item.get("id"), str)
        } if has_object_definition_list else set()
        normalized_renames: dict[str, str] = {}
        for old_id, new_id in renames.items():
            if not isinstance(old_id, str) or not isinstance(new_id, str):
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "invalid_object_id_rename",
                        "object_id_renames",
                        "オブジェクトIDの変更元と変更先は文字列で指定してください。",
                    ).as_dict()
                )
                continue
            if old_id == new_id:
                continue
            if old_id not in previous_ids or new_id not in current_ids:
                diagnostics.append(
                    Diagnostic(
                        "error",
                        "invalid_object_id_rename",
                        f"object_id_renames.{old_id}",
                        f"オブジェクトIDの変更を確認できません: {old_id} → {new_id}",
                    ).as_dict()
                )
                continue
            normalized_renames[old_id] = new_id
        if diagnostics or not isinstance(tileset_id, str):
            return [], diagnostics, 0

        removed_definition_ids = (
            previous_ids - current_ids if can_reconcile_object_definitions else set()
        )
        updates: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
        removed_instance_count = 0
        source_root = self.content_root / "maps" / "sources"
        if not source_root.is_dir():
            return updates, diagnostics, removed_instance_count
        for path in sorted(source_root.glob("*.json")):
            original = load_map_source(path)
            if original.get("tileset_id") != tileset_id:
                continue
            updated = json.loads(json.dumps(original))
            changed = False
            instances = updated.get("objects")
            if not isinstance(instances, list):
                continue
            retained_instances = []
            for instance in instances:
                if not isinstance(instance, dict):
                    retained_instances.append(instance)
                    continue
                definition_id = instance.get("definition_id")
                if definition_id in normalized_renames:
                    instance["definition_id"] = normalized_renames[definition_id]
                    definition_id = instance["definition_id"]
                    changed = True
                if definition_id in removed_definition_ids:
                    removed_instance_count += 1
                    changed = True
                    continue
                retained_instances.append(instance)
            updated["objects"] = retained_instances
            if changed:
                updates.append((path, original, updated))
        return updates, diagnostics, removed_instance_count

    def _compile_referencing_maps(
        self,
        data: Mapping[str, Any],
        map_updates: list[tuple[Path, dict[str, Any], dict[str, Any]]],
        diagnostics: list[dict[str, str]],
    ) -> list[tuple[str, CompiledMap]]:
        if self.runtime_root is None or any(
            item.get("severity") == "error" for item in diagnostics
        ):
            return []
        tileset_id = data.get("tileset_id")
        if not isinstance(tileset_id, str):
            return []
        replacements = {path: updated for path, _original, updated in map_updates}
        source_root = self.content_root / "maps" / "sources"
        if not source_root.is_dir():
            return []
        image_path = self.source_image(data)
        compiled_maps = []
        for path in sorted(source_root.glob("*.json")):
            source = replacements.get(path)
            if source is None:
                source = load_map_source(path)
            if source.get("tileset_id") != tileset_id:
                continue
            map_id = source.get("map_id", path.stem)
            try:
                compiled = compile_map(source, data, image_path, self.palette_path)
            except (OSError, ValueError) as error:
                diagnostics.append(
                    Diagnostic(
                        "warning",
                        "referencing_map_not_generated",
                        f"maps/sources/{path.name}",
                        f"参照マップ{map_id}のゲーム用データは更新できませんでした: {error}",
                    ).as_dict()
                )
                continue
            compiled_maps.append((str(map_id), compiled))
        return compiled_maps

    def save(
        self,
        data: object,
        object_id_renames: object = None,
    ) -> dict[str, Any]:
        diagnostics, image_info = self.validate(data)
        if not isinstance(data, dict):
            return {
                "saved": False,
                "diagnostics": diagnostics,
                "image_info": image_info,
                "updated_map_ids": [],
                "removed_map_object_count": 0,
            }
        try:
            metadata_path = self.metadata_path_for(data.get("tileset_id"))
        except (TypeError, ValueError):
            return {
                "saved": False,
                "diagnostics": diagnostics,
                "image_info": image_info,
                "updated_map_ids": [],
                "removed_map_object_count": 0,
            }

        map_updates: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
        map_updates, update_diagnostics, removed_instance_count = (
            self._prepare_map_object_updates(data, object_id_renames)
        )
        diagnostics.extend(update_diagnostics)
        compiled_maps = self._compile_referencing_maps(
            data,
            map_updates,
            diagnostics,
        )
        written_maps: list[tuple[Path, dict[str, Any]]] = []
        try:
            for path, original, updated in map_updates:
                save_map_source(path, updated)
                written_maps.append((path, original))
            save_tileset(metadata_path, data)
            if self.runtime_root is not None:
                for map_id, compiled in compiled_maps:
                    save_compiled_map(self.runtime_root / f"{map_id}.json", compiled)
        except BaseException:
            for path, original in written_maps:
                save_map_source(path, original)
            raise
        return {
            "saved": True,
            "diagnostics": diagnostics,
            "image_info": image_info,
            "updated_map_ids": [
                updated.get("map_id", path.stem)
                for path, _original, updated in map_updates
            ],
            "generated_map_ids": [map_id for map_id, _compiled in compiled_maps],
            "removed_map_object_count": removed_instance_count,
        }

    def delete_tileset(self, tileset_id: str) -> dict[str, Any]:
        if not isinstance(tileset_id, str):
            raise ValueError("タイルセットIDが不正です。")
        if tileset_id in PROTECTED_TILESET_IDS:
            raise ValueError("worldmapはゲームの必須タイルセットなので削除できません。")
        metadata_path = self.metadata_path_for(tileset_id)
        if not metadata_path.is_file():
            raise FileNotFoundError(f"タイルセットが見つかりません: {metadata_path}")
        record = next(
            (
                item
                for item in self.tileset_catalog()
                if item["tileset_id"] == tileset_id
            ),
            None,
        )
        map_ids = record.get("map_ids", []) if record else []
        if map_ids:
            raise ValueError(
                "次のマップで使用中のため削除できません: " + "、".join(map_ids)
            )
        metadata_path.unlink()
        catalog = self.tileset_catalog()
        return {
            "deleted": True,
            "tileset_id": tileset_id,
            "next_tileset_id": catalog[0]["tileset_id"] if catalog else None,
            "tilesets": catalog,
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
                    tileset_id = parse_qs(parsed.query).get("tileset", [None])[0]
                    self._send_json(application.document_payload(tileset_id))
                except (OSError, ValueError) as error:
                    self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                return
            if parsed.path == "/api/catalog":
                if not self._authorized(parsed):
                    self._send_error_json(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                    return
                try:
                    self._send_json(
                        {
                            "tilesets": application.tileset_catalog(),
                            "source_images": application.source_image_catalog(),
                        }
                    )
                except (OSError, ValueError) as error:
                    self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                return
            if parsed.path == "/api/source-image":
                if not self._authorized(parsed):
                    self._send_error_json(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                    return
                try:
                    query = parse_qs(parsed.query)
                    source_image_id = query.get("source", [None])[0]
                    if source_image_id is not None:
                        image_path = application.source_image(
                            {"source_image_id": source_image_id}
                        )
                    else:
                        tileset_id = query.get("tileset", [None])[0]
                        data = application.load(tileset_id)
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
            if parsed.path not in (
                "/api/validate",
                "/api/save",
                "/api/create",
                "/api/delete",
            ):
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
                if parsed.path == "/api/create":
                    if not isinstance(payload, dict):
                        raise ValueError("新規タイルセットの設定が不正です。")
                    response = application.create_document_payload(
                        payload.get("tileset_id"),
                        payload.get("source_image_id"),
                        payload.get("profile"),
                        payload.get("base_ground_id"),
                        payload.get("base_collision"),
                    )
                elif parsed.path == "/api/delete":
                    if not isinstance(payload, dict):
                        raise ValueError("削除対象タイルセットが不正です。")
                    response = application.delete_tileset(payload.get("tileset_id"))
                elif parsed.path == "/api/save":
                    response = application.save(
                        data,
                        payload.get("object_id_renames")
                        if isinstance(payload, dict)
                        else None,
                    )
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
            runtime_root=args.runtime_root,
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
