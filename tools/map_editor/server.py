"""Serve the local browser UI for map authoring."""

from __future__ import annotations

import argparse
from copy import deepcopy
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
    validate_area_groups,
    validate_map_event_links,
    validate_map_source,
    validate_tileset,
)
from scripts.event_pipeline import event_flag_ids, load_event_flags, load_event_sources
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
        "path": Path("actors/characters.gif"),
        "sprite_size": [48, 128],
    },
    "pc_character": {
        "path": Path("characters/ch_walk.gif"),
        "sprite_size": [48, 128],
    },
    "treasure": {
        "path": Path("actors/treasure.png"),
        "sprite_size": [48, 16],
    },
}
MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".png": "image/png",
    ".gif": "image/gif",
}
PROTECTED_MAP_IDS = frozenset(("worldmap",))


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
        audio_root: Path | None = None,
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
        self.audio_root = (audio_root or PROJECT_ROOT / "app" / "audio").resolve()
        self.source_path = (self.content_root / "maps" / "sources" / f"{map_id}.json").resolve()
        source_root = (self.content_root / "maps" / "sources").resolve()
        if source_root not in self.source_path.parents:
            raise ValueError("マップパスがcontent/maps/sources外です。")
        self.runtime_path = (self.runtime_root / f"{map_id}.json").resolve()
        if self.runtime_root not in self.runtime_path.parents:
            raise ValueError("生成先がruntime root外です。")
        self.texts_path = (self.content_root / "data" / "texts.json").resolve()
        self.items_path = (self.content_root / "data" / "items.json").resolve()
        data_root = (self.content_root / "data").resolve()
        if data_root not in self.texts_path.parents:
            raise ValueError("文言パスがcontent/data外です。")

    def load_source(self) -> tuple[dict[str, Any], bool]:
        return self.load_source_by_id(self.map_id)

    def source_path_for(self, map_id: str) -> Path:
        if not _valid_id(map_id):
            raise ValueError("マップIDはlower_snake_caseで指定してください。")
        path = (self.content_root / "maps" / "sources" / f"{map_id}.json").resolve()
        source_root = (self.content_root / "maps" / "sources").resolve()
        if source_root not in path.parents:
            raise ValueError("マップパスがcontent/maps/sources外です。")
        return path

    def runtime_path_for(self, map_id: str) -> Path:
        if not _valid_id(map_id):
            raise ValueError("マップIDはlower_snake_caseで指定してください。")
        path = (self.runtime_root / f"{map_id}.json").resolve()
        if self.runtime_root not in path.parents:
            raise ValueError("生成先がruntime root外です。")
        return path

    def load_source_by_id(self, map_id: str) -> tuple[dict[str, Any], bool]:
        source_path = self.source_path_for(map_id)
        if source_path.is_file():
            return load_map_source(source_path), False
        if map_id != self.map_id:
            raise FileNotFoundError(f"制作用マップが見つかりません: {source_path}")
        tileset = self.load_tileset(self.initial_tileset_id)
        return initial_map_source(map_id, tileset, self.profile, self.width, self.height), True

    def map_catalog(self) -> list[dict[str, object]]:
        source_dir = self.content_root / "maps" / "sources"
        catalog = []
        if source_dir.is_dir():
            for path in sorted(source_dir.glob("*.json")):
                source = load_map_source(path)
                map_id = source.get("map_id")
                if not isinstance(map_id, str) or path.stem != map_id:
                    raise ValueError(f"マップIDとファイル名が一致しません: {path}")
                catalog.append(
                    {
                        "map_id": map_id,
                        "profile": source.get("profile"),
                        "tileset_id": source.get("tileset_id"),
                        "size": source.get("size"),
                        "area_parent_id": source.get("area_parent_id"),
                        "area_name": source.get("area_name"),
                    }
                )
        if not catalog and not self.source_path.is_file():
            catalog.append(
                {
                    "map_id": self.map_id,
                    "profile": self.profile,
                    "tileset_id": self.initial_tileset_id,
                    "size": [self.width, self.height],
                    "is_new": True,
                }
            )
        return catalog

    def tileset_catalog(self) -> list[dict[str, object]]:
        tileset_dir = self.content_root / "maps" / "tilesets"
        catalog = []
        if tileset_dir.is_dir():
            for path in sorted(tileset_dir.glob("*.json")):
                tileset = load_tileset(path)
                tileset_id = tileset.get("tileset_id")
                if not isinstance(tileset_id, str) or path.stem != tileset_id:
                    raise ValueError(f"タイルセットIDとファイル名が一致しません: {path}")
                catalog.append(
                    {
                        "tileset_id": tileset_id,
                        "source_image_id": tileset.get("source_image_id"),
                        "profile": tileset.get("profile"),
                        "base_ground_id": (
                            tileset.get("grounds", [{}])[0].get("id")
                            if tileset.get("grounds")
                            else None
                        ),
                    }
                )
        return catalog

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

    def sources_with_arrival_renames(
        self,
        data: Mapping[str, Any],
        arrival_id_renames: object | None,
    ) -> tuple[dict[str, Mapping[str, Any]], dict[str, dict[str, Any]]]:
        sources = self.map_sources(data)
        if arrival_id_renames is None:
            return sources, {}
        if not isinstance(arrival_id_renames, Mapping):
            raise ValueError("到着地点IDの変更履歴が不正です。")
        if not arrival_id_renames:
            return sources, {}
        map_id = data.get("map_id")
        if not isinstance(map_id, str):
            raise ValueError("マップIDが不正です。")
        original, is_new = self.load_source_by_id(map_id)
        if is_new:
            raise ValueError("未保存マップの到着地点ID変更履歴は指定できません。")
        original_ids = {
            arrival.get("id") for arrival in original.get("arrival_points", [])
            if isinstance(arrival, Mapping)
        }
        arrival_points = data.get("arrival_points")
        if not isinstance(arrival_points, list):
            raise ValueError("到着地点の一覧が不正です。")
        current_ids = {
            arrival.get("id") for arrival in arrival_points
            if isinstance(arrival, Mapping)
        }
        for old_id, new_id in arrival_id_renames.items():
            if (
                not isinstance(old_id, str) or not isinstance(new_id, str)
                or not _valid_id(old_id) or not _valid_id(new_id)
                or old_id not in original_ids or new_id not in current_ids
            ):
                raise ValueError("到着地点IDの変更履歴が現在のマップと一致しません。")
        updates: dict[str, dict[str, Any]] = {}
        for source_id, source in sources.items():
            sites = source.get("sites")
            if not isinstance(sites, list):
                continue
            if not any(
                isinstance(site, Mapping)
                and isinstance(site.get("destination"), Mapping)
                and site["destination"].get("map_id") == map_id
                and site["destination"].get("arrival_id") in arrival_id_renames
                for site in sites
            ):
                continue
            updated = deepcopy(source)
            for site in updated["sites"]:
                destination = site.get("destination") if isinstance(site, dict) else None
                if isinstance(destination, dict) and destination.get("map_id") == map_id:
                    old_id = destination.get("arrival_id")
                    if old_id in arrival_id_renames:
                        destination["arrival_id"] = arrival_id_renames[old_id]
            sources[source_id] = updated
            if source_id != map_id:
                updates[source_id] = updated
        return sources, updates

    def destination_options(
        self,
        current: Mapping[str, Any],
    ) -> list[dict[str, object]]:
        options = []
        for map_id, source in sorted(self.map_sources(current).items()):
            option = {
                "map_id": map_id,
                "arrival_ids": [
                    arrival.get("id")
                    for arrival in source.get("arrival_points", [])
                    if isinstance(arrival, Mapping)
                    and isinstance(arrival.get("id"), str)
                ],
            }
            if source.get("area_parent_id"):
                option["label"] = f"{source['area_parent_id']} / {source.get('area_name', map_id)}"
            elif source.get("area_name"):
                option["label"] = f"{map_id} / {source['area_name']}"
            options.append(option)
        return options

    def site_options(self, current: Mapping[str, Any]) -> list[str]:
        return sorted(
            {
                site.get("id")
                for source in self.map_sources(current).values()
                if source.get("profile") == "world"
                for site in source.get("sites", [])
                if isinstance(site, Mapping) and isinstance(site.get("id"), str)
            }
        )

    def event_options(self) -> list[str]:
        return sorted(self.event_definitions())

    def item_options(self) -> list[dict[str, str]]:
        if not self.items_path.is_file():
            return []
        value = json.loads(self.items_path.read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise ValueError("content/data/items.jsonはobjectの配列である必要があります。")
        options = []
        for index, record in enumerate(value):
            if not isinstance(record, Mapping):
                raise ValueError(f"content/data/items.json[{index}]が不正です。")
            key = record.get("name_en")
            name = record.get("name_ja")
            if not isinstance(key, str) or not key or not isinstance(name, str):
                raise ValueError(f"content/data/items.json[{index}]の名称が不正です。")
            options.append({"key": key, "name_ja": name})
        return options

    def item_keys(self) -> set[str]:
        return {item["key"] for item in self.item_options()}

    def bgm_options(self) -> list[str]:
        if not self.audio_root.is_dir():
            return []
        return sorted(
            {
                path.relative_to(self.audio_root).with_suffix("").as_posix()
                for path in self.audio_root.rglob("*.ogg")
                if path.is_file() and not path.name.startswith(".")
            }
        )

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
        if data.get("profile") != "world":
            return {}
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
        if data.get("profile") != "world":
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
        arrival_id_renames: object | None = None,
    ) -> tuple[list[dict[str, str]], dict[str, Any] | None, dict[str, Any] | None]:
        if not isinstance(data, dict) or not isinstance(data.get("tileset_id"), str):
            issue = Diagnostic("error", "invalid_tileset_id", "tileset_id", "タイルセットIDが不正です。")
            return [issue.as_dict()], None, None
        if not isinstance(data.get("map_id"), str):
            issue = Diagnostic("error", "invalid_map_id", "map_id", "マップIDが不正です。")
            return [issue.as_dict()], None, None
        try:
            tileset = self.load_tileset(data["tileset_id"])
            image_path = self.source_image(tileset)
        except (OSError, ValueError) as error:
            issue = Diagnostic("error", "missing_tileset", "tileset_id", str(error))
            return [issue.as_dict()], None, None
        try:
            sources, _updates = self.sources_with_arrival_renames(data, arrival_id_renames)
        except ValueError as error:
            issue = Diagnostic("error", "invalid_arrival_renames", "arrival_points", str(error))
            return [issue.as_dict()], None, None
        current = sources[data["map_id"]]
        tileset_diagnostics, image_info = validate_tileset(tileset, image_path, self.palette_path)
        map_diagnostics = validate_map_source(
            current,
            tileset,
            bgm_ids=self.bgm_options(),
            item_keys=self.item_keys(),
            flag_ids=event_flag_ids(load_event_flags(self.content_root)),
        )
        link_diagnostics = (
            validate_map_links(sources)
            if isinstance(data, dict)
            else []
        )
        area_diagnostics = (
            [
                item for item in validate_area_groups(sources)
                if item.path.startswith(f"{data.get('map_id')}.")
            ]
            if isinstance(data, dict) else []
        )
        event_link_diagnostics = (
            [
                item
                for item in validate_map_event_links(
                    sources, self.event_definitions()
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
            *area_diagnostics,
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
                resolved = resolve_map(current, tileset)
            except ValueError as error:
                if has_errors:
                    preview_data = {
                        **current,
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

    def _document_payload(
        self,
        data: dict[str, Any],
        *,
        is_new: bool,
    ) -> dict[str, Any]:
        tileset = self.load_tileset(data["tileset_id"])
        repaired_unknown_ground_count = self._replace_unknown_grounds_with_base(
            data,
            tileset,
        )
        site_names_ja = self.site_names_ja(data)
        diagnostics, image_info, resolved = self.validate(data, site_names_ja)
        events = self.event_definitions()
        return {
            "data": data,
            "site_names_ja": site_names_ja,
            "destination_options": self.destination_options(data),
            "site_options": self.site_options(data),
            "event_options": sorted(events),
            "flag_options": load_event_flags(self.content_root),
            "event_notes": {
                event_id: event.get("note") if isinstance(event.get("note"), str) else ""
                for event_id, event in events.items()
            },
            "item_options": self.item_options(),
            "bgm_options": self.bgm_options(),
            "tileset": tileset,
            "diagnostics": diagnostics,
            "resolved": resolved,
            "image_info": image_info,
            "image_url": (
                f"/api/source-image?tileset={data['tileset_id']}&token={self.token}"
            ),
            "actor_assets": self.actor_assets_payload(),
            "is_new": is_new,
            "dirty": repaired_unknown_ground_count > 0,
            "repaired_unknown_ground_count": repaired_unknown_ground_count,
            "source_path": self._display_path(self.source_path_for(data["map_id"])),
            "runtime_path": self._display_path(self.runtime_path_for(data["map_id"])),
        }

    @staticmethod
    def _replace_unknown_grounds_with_base(
        data: dict[str, Any],
        tileset: Mapping[str, Any],
    ) -> int:
        definitions = tileset.get("grounds")
        if not isinstance(definitions, list) or not definitions:
            return 0
        first = definitions[0]
        if not isinstance(first, Mapping) or not isinstance(first.get("id"), str):
            return 0
        base_ground_id = first["id"]
        ground_ids = {
            definition.get("id")
            for definition in definitions
            if isinstance(definition, Mapping)
            and isinstance(definition.get("id"), str)
        }
        rows = data.get("grounds")
        if not isinstance(rows, list):
            return 0

        repaired = 0
        for row in rows:
            if not isinstance(row, list):
                continue
            for x, ground_id in enumerate(row):
                if isinstance(ground_id, str) and ground_id not in ground_ids:
                    row[x] = base_ground_id
                    repaired += 1
        return repaired

    def document_payload(self, map_id: str | None = None) -> dict[str, Any]:
        data, is_new = (
            self.load_source()
            if map_id is None
            else self.load_source_by_id(map_id)
        )
        return self._document_payload(data, is_new=is_new)

    def create_document_payload(
        self,
        map_id: str,
        tileset_id: str,
        profile: str,
        width: int,
        height: int,
    ) -> dict[str, Any]:
        if not isinstance(map_id, str) or not isinstance(tileset_id, str):
            raise ValueError("マップIDとタイルセットIDが不正です。")
        if not isinstance(profile, str):
            raise ValueError("profileが不正です。")
        if (
            isinstance(width, bool)
            or not isinstance(width, int)
            or isinstance(height, bool)
            or not isinstance(height, int)
        ):
            raise ValueError("マップ寸法が不正です。")
        source_path = self.source_path_for(map_id)
        if source_path.exists():
            raise ValueError(f"マップIDはすでに使用されています: {map_id}")
        tileset = self.load_tileset(tileset_id)
        if profile != tileset.get("profile"):
            raise ValueError("マップとタイルセットのprofileが一致していません。")
        data = initial_map_source(map_id, tileset, profile, width, height)
        return self._document_payload(data, is_new=True)

    def create_area_document_payload(
        self, parent_id: str, area_name: str, width: int, height: int,
    ) -> dict[str, Any]:
        if not isinstance(parent_id, str) or not _valid_id(parent_id):
            raise ValueError("親マップIDはlower_snake_caseで指定してください。")
        if not isinstance(area_name, str) or not area_name.strip():
            raise ValueError("エリア名を入力してください。")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (width, height)):
            raise ValueError("エリア寸法が不正です。")
        parent, is_new = self.load_source_by_id(parent_id)
        if is_new or parent.get("area_parent_id") is not None:
            raise ValueError("保存済みの親マップを指定してください。")
        for _attempt in range(10):
            map_id = f"{parent_id}_area_{secrets.token_hex(6)}"
            if not self.source_path_for(map_id).exists():
                break
        else:
            raise ValueError("重複しないエリアIDを生成できませんでした。")
        tileset = self.load_tileset(parent["tileset_id"])
        data = initial_map_source(map_id, tileset, parent["profile"], width, height)
        data["area_parent_id"] = parent_id
        data["area_name"] = area_name.strip()
        data["bgm_id"] = parent["bgm_id"]
        if parent["profile"] == "dungeon":
            data["random_encounter"] = dict(parent["random_encounter"])
        return self._document_payload(data, is_new=True)

    def change_tileset_document_payload(
        self,
        map_id: str,
        tileset_id: str,
    ) -> dict[str, Any]:
        if not isinstance(map_id, str) or not isinstance(tileset_id, str):
            raise ValueError("マップIDとタイルセットIDが不正です。")
        source, is_new = self.load_source_by_id(map_id)
        if is_new:
            raise ValueError("未保存マップのタイルセットは新規作成画面で選択してください。")
        if source.get("tileset_id") == tileset_id:
            raise ValueError("現在と異なるタイルセットを選択してください。")
        if source.get("area_parent_id") is not None:
            raise ValueError("マップチップは親マップから変更してください。")
        tileset = self.load_tileset(tileset_id)
        if source.get("profile") != tileset.get("profile"):
            raise ValueError("マップとタイルセットのprofileが一致していません。")
        width, height = source["size"]
        reset_source = initial_map_source(
            map_id,
            tileset,
            source["profile"],
            width,
            height,
        )
        reset_source["bgm_id"] = source["bgm_id"]
        if "area_name" in source:
            reset_source["area_name"] = source["area_name"]
        if source.get("profile") == "dungeon":
            reset_source["random_encounter"] = dict(source["random_encounter"])
        payload = self._document_payload(reset_source, is_new=False)
        payload["dirty"] = True
        return payload

    def map_delete_blockers(self, map_id: str) -> list[str]:
        target, is_new = self.load_source_by_id(map_id)
        if is_new:
            raise ValueError("未保存マップは削除対象ではありません。")
        target_site_ids = {
            site.get("id")
            for site in target.get("sites", [])
            if isinstance(site, Mapping) and isinstance(site.get("id"), str)
        }
        blockers: set[str] = set()
        for other_id, source in self.map_sources(target).items():
            if other_id == map_id:
                continue
            if source.get("area_parent_id") == map_id:
                blockers.add(f"{other_id}がこのマップのエリア")
            for site in source.get("sites", []):
                if not isinstance(site, Mapping):
                    continue
                destination = site.get("destination")
                if isinstance(destination, Mapping) and destination.get("map_id") == map_id:
                    blockers.add(f"{other_id}の移動先")
            for arrival in source.get("arrival_points", []):
                if (
                    isinstance(arrival, Mapping)
                    and arrival.get("teleport_enabled") is True
                    and arrival.get("site_id") in target_site_ids
                ):
                    blockers.add(f"{other_id}のテレポート到着地点")
        return sorted(blockers)

    def delete_map(self, map_id: str) -> dict[str, Any]:
        if not isinstance(map_id, str):
            raise ValueError("マップIDが不正です。")
        if map_id in PROTECTED_MAP_IDS:
            raise ValueError("worldmapはゲームの必須マップなので削除できません。")
        source_path = self.source_path_for(map_id)
        if not source_path.is_file():
            raise FileNotFoundError(f"制作用マップが見つかりません: {source_path}")
        blockers = self.map_delete_blockers(map_id)
        if blockers:
            raise ValueError(
                "他のマップから参照されているため削除できません: "
                + "、".join(blockers)
            )
        runtime_path = self.runtime_path_for(map_id)
        source_path.unlink()
        runtime_path.unlink(missing_ok=True)
        runtime_path.with_suffix(".bin").unlink(missing_ok=True)
        catalog = self.map_catalog()
        return {
            "deleted": True,
            "map_id": map_id,
            "next_map_id": catalog[0]["map_id"] if catalog else None,
            "maps": catalog,
        }

    def save(
        self,
        data: object,
        site_names_ja: object,
        arrival_id_renames: object | None = None,
    ) -> dict[str, Any]:
        diagnostics, image_info, resolved = self.validate(data, site_names_ja, arrival_id_renames)
        if any(item["severity"] == "error" for item in diagnostics) or not isinstance(data, dict):
            return {"saved": False, "diagnostics": diagnostics, "image_info": image_info, "resolved": resolved}
        sources, reference_updates = self.sources_with_arrival_renames(data, arrival_id_renames)
        data = sources[data["map_id"]]
        tileset = self.load_tileset(data["tileset_id"])
        updates = dict(reference_updates)
        if data.get("area_parent_id") is None:
            for child_id, original in sources.items():
                if original.get("area_parent_id") != data["map_id"]:
                    continue
                child = dict(original)
                if child.get("tileset_id") != data["tileset_id"]:
                    child = initial_map_source(child_id, tileset, data["profile"], *original["size"])
                    child["area_parent_id"] = data["map_id"]
                    child["area_name"] = original["area_name"]
                    if "random_encounter" in original and data["profile"] == "dungeon":
                        child["random_encounter"] = dict(original["random_encounter"])
                child["bgm_id"] = data["bgm_id"]
                child_issues = validate_map_source(
                    child, tileset, bgm_ids=self.bgm_options(), item_keys=self.item_keys(),
                    flag_ids=event_flag_ids(load_event_flags(self.content_root)),
                )
                if any(item.severity == "error" for item in child_issues):
                    diagnostics.extend(item.as_dict() for item in child_issues)
                    return {"saved": False, "diagnostics": diagnostics, "image_info": image_info, "resolved": resolved}
                if child != original:
                    updates[child_id] = child
        try:
            compiled = compile_map(data, tileset, self.source_image(tileset), self.palette_path)
            compiled_updates = []
            for update in updates.values():
                update_tileset = self.load_tileset(update["tileset_id"])
                update_issues = validate_map_source(
                    update, update_tileset, bgm_ids=self.bgm_options(), item_keys=self.item_keys(),
                    flag_ids=event_flag_ids(load_event_flags(self.content_root)),
                )
                if any(item.severity == "error" for item in update_issues):
                    diagnostics.extend(item.as_dict() for item in update_issues)
                    return {"saved": False, "diagnostics": diagnostics, "image_info": image_info, "resolved": resolved}
                compiled_updates.append((
                    update,
                    compile_map(update, update_tileset, self.source_image(update_tileset), self.palette_path),
                ))
        except (OSError, ValueError) as error:
            diagnostics.append(Diagnostic("error", "compile_failed", "$", str(error)).as_dict())
            return {"saved": False, "diagnostics": diagnostics, "image_info": image_info, "resolved": resolved}
        map_id = data["map_id"]
        source_path = self.source_path_for(map_id)
        runtime_path = self.runtime_path_for(map_id)
        save_map_source(source_path, data)
        save_compiled_map(runtime_path, compiled)
        for update, update_compiled in compiled_updates:
            save_map_source(self.source_path_for(update["map_id"]), update)
            save_compiled_map(self.runtime_path_for(update["map_id"]), update_compiled)
        self._save_site_names(data, site_names_ja)
        return {
            "saved": True,
            "diagnostics": diagnostics,
            "image_info": image_info,
            "resolved": resolved,
            "source_hash": compiled.runtime["source_hash"],
            **({"data": data} if arrival_id_renames else {}),
        }

    def _save_site_names(
        self,
        data: Mapping[str, Any],
        site_names_ja: object,
    ) -> None:
        if data.get("profile") != "world":
            return
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
                    map_id = parse_qs(parsed.query).get("map", [None])[0]
                    self._send_json(application.document_payload(map_id))
                except (OSError, ValueError) as error:
                    self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                return
            if parsed.path == "/api/catalog":
                if not self._authorized(parsed):
                    self._error(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                    return
                try:
                    self._send_json(
                        {
                            "maps": application.map_catalog(),
                            "tilesets": application.tileset_catalog(),
                        }
                    )
                except (OSError, ValueError) as error:
                    self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                return
            if parsed.path == "/api/source-image":
                if not self._authorized(parsed):
                    self._error(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                    return
                try:
                    tileset_id = parse_qs(parsed.query).get("tileset", [None])[0]
                    if tileset_id is None:
                        data, _is_new = application.load_source()
                        tileset_id = data["tileset_id"]
                    tileset = application.load_tileset(tileset_id)
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
            if parsed.path not in (
                "/api/validate",
                "/api/resolve",
                "/api/save",
                "/api/create",
                "/api/create-area",
                "/api/change-tileset",
                "/api/delete",
            ):
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
                if parsed.path == "/api/create":
                    if not isinstance(payload, dict):
                        raise ValueError("新規マップの設定が不正です。")
                    response = application.create_document_payload(
                        payload.get("map_id"),
                        payload.get("tileset_id"),
                        payload.get("profile"),
                        payload.get("width"),
                        payload.get("height"),
                    )
                elif parsed.path == "/api/create-area":
                    if not isinstance(payload, dict):
                        raise ValueError("新規エリアの設定が不正です。")
                    response = application.create_area_document_payload(
                        payload.get("parent_id"), payload.get("area_name"),
                        payload.get("width"), payload.get("height"),
                    )
                elif parsed.path == "/api/change-tileset":
                    if not isinstance(payload, dict):
                        raise ValueError("タイルセット変更の設定が不正です。")
                    response = application.change_tileset_document_payload(
                        payload.get("map_id"),
                        payload.get("tileset_id"),
                    )
                elif parsed.path == "/api/delete":
                    if not isinstance(payload, dict):
                        raise ValueError("削除対象マップが不正です。")
                    response = application.delete_map(payload.get("map_id"))
                elif parsed.path == "/api/save":
                    response = application.save(
                        data, site_names_ja,
                        payload.get("arrival_id_renames") if isinstance(payload, dict) else None,
                    )
                else:
                    diagnostics, image_info, resolved = application.validate(
                        data,
                        site_names_ja,
                        payload.get("arrival_id_renames") if isinstance(payload, dict) else None,
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
