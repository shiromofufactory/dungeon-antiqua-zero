"""Serve the local browser UI for composing battle attack poses."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tomllib
from typing import Any
from urllib.parse import parse_qs, urlparse
import webbrowser
import zipfile

from PIL import Image

from app.attack_pose import (
    ATTACK_POSE_FORMAT_VERSION,
    AttackPoseDataError,
    RACE_KEYS,
    parse_attack_poses,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = Path(__file__).resolve().parent / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8769
MAX_REQUEST_BYTES = 1024 * 1024
TRANSPARENT_INDEX = 1
CHARACTER_KEYS = ("Fiora", "Cerion", "Alvan", "Elika")
WEAPON_IMG_PATTERN = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
BRANCH_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    content_root = Path(
        os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")
    ).resolve()
    parser = argparse.ArgumentParser(
        description="戦闘用キャラクターと武器の攻撃ポーズを1px単位で調整します。"
    )
    parser.add_argument("--content-root", type=Path, default=content_root, help=argparse.SUPPRESS)
    parser.add_argument("--app-root", type=Path, default=PROJECT_ROOT / "app", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args(argv)


def initial_document() -> dict[str, object]:
    return {
        "format_version": 1,
        "poses": [
            {
                "id": "SWORD-1_1",
                "weapon_img": "SWORD-1",
                "branch": "1",
                "character_pose": 0,
                "weapons": [
                    {
                        "image": 0,
                        "position": [0, 0],
                        "layer": "front",
                        "flip_x": False,
                        "flip_y": False,
                    }
                ],
            }
        ],
    }


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def pose_id(weapon_img: str, branch: str) -> str:
    return f"{weapon_img}_{branch}"


def validate_document(
    data: object,
    weapon_img_options: set[str] | None = None,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def error(code: str, path: str, message: str) -> None:
        issues.append({"severity": "error", "code": code, "path": path, "message": message})

    if not isinstance(data, dict):
        error("invalid_root", "", "JSONのルートはobjectである必要があります。")
        return issues
    if data.get("format_version") != 1:
        error("invalid_format_version", "format_version", "format_versionは1である必要があります。")
    poses = data.get("poses")
    if not isinstance(poses, list):
        error("invalid_poses", "poses", "posesは配列である必要があります。")
        return issues
    if not poses:
        error("empty_poses", "poses", "ポーズを1件以上登録してください。")
        return issues

    seen_ids: set[str] = set()
    for index, pose in enumerate(poses):
        path = f"poses[{index}]"
        if not isinstance(pose, dict):
            error("invalid_pose", path, "ポーズはobjectである必要があります。")
            continue
        saved_pose_id = pose.get("id")
        weapon_img = pose.get("weapon_img")
        branch = pose.get("branch")
        if not isinstance(weapon_img, str) or WEAPON_IMG_PATTERN.fullmatch(weapon_img) is None:
            error("invalid_weapon_img", f"{path}.weapon_img", "weapon_imgが不正です。")
        elif weapon_img_options is not None and weapon_img not in weapon_img_options:
            error("unknown_weapon_img", f"{path}.weapon_img", f"items.jsonにないweapon_imgです: {weapon_img}")
        if not isinstance(branch, str) or BRANCH_PATTERN.fullmatch(branch) is None:
            error("invalid_branch", f"{path}.branch", "枝番は英数字、ハイフン、アンダースコアで指定してください。")
        expected_id = (
            pose_id(weapon_img, branch)
            if isinstance(weapon_img, str) and isinstance(branch, str)
            else None
        )
        if not isinstance(saved_pose_id, str) or saved_pose_id != expected_id:
            error("invalid_id", f"{path}.id", "IDはweapon_imgと枝番から生成した値にしてください。")
        elif saved_pose_id in seen_ids:
            error("duplicate_id", f"{path}.id", f"IDが重複しています: {saved_pose_id}")
        else:
            seen_ids.add(saved_pose_id)
        character_pose = pose.get("character_pose")
        if not _integer(character_pose) or not 0 <= character_pose <= 8:
            error("invalid_character_pose", f"{path}.character_pose", "キャラポーズは0〜8で指定してください。")
        race_y_offsets = pose.get("race_y_offsets", {})
        if not isinstance(race_y_offsets, dict):
            error("invalid_race_y_offsets", f"{path}.race_y_offsets", "種族別Y補正はobjectで指定してください。")
        else:
            for race, offset in race_y_offsets.items():
                if race not in RACE_KEYS or not _integer(offset) or not -128 <= offset <= 128:
                    error("invalid_race_y_offset", f"{path}.race_y_offsets.{race}", "種族別Y補正は対応する種族の-128〜128の整数で指定してください。")
        weapons = pose.get("weapons")
        if not isinstance(weapons, list) or not 1 <= len(weapons) <= 2:
            error("invalid_weapons", f"{path}.weapons", "武器は1〜2件の配列で指定してください。")
            continue
        for weapon_index, weapon in enumerate(weapons):
            weapon_path = f"{path}.weapons[{weapon_index}]"
            if not isinstance(weapon, dict):
                error("invalid_weapon", weapon_path, "武器はobjectである必要があります。")
                continue
            weapon_image = weapon.get("image")
            if not _integer(weapon_image) or not 0 <= weapon_image <= 15:
                error("invalid_weapon_image", f"{weapon_path}.image", "武器画像番号は0〜15で指定してください。")
            position = weapon.get("position")
            if not (
                isinstance(position, list)
                and len(position) == 2
                and all(_integer(value) and -128 <= value <= 128 for value in position)
            ):
                error("invalid_position", f"{weapon_path}.position", "武器座標は-128〜128の整数2要素で指定してください。")
            if weapon.get("layer") not in ("front", "back"):
                error("invalid_weapon_layer", f"{weapon_path}.layer", "武器の重なりはfrontまたはbackで指定してください。")
            for field, label in (("flip_x", "左右反転"), ("flip_y", "上下反転")):
                if not isinstance(weapon.get(field), bool):
                    error("invalid_weapon_flip", f"{weapon_path}.{field}", f"武器の{label}はbooleanで指定してください。")
    return issues


def _read_palette(path: Path) -> list[tuple[int, int, int]]:
    colors: list[tuple[int, int, int]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = raw_line.strip()
        if not value or value.startswith("//"):
            continue
        value = value.removeprefix("#")
        if re.fullmatch(r"[0-9a-fA-F]{6}", value) is None:
            raise ValueError(f"{path}:{line_number}: パレット色が不正です。")
        colors.append(tuple(bytes.fromhex(value)))
    if len(colors) <= TRANSPARENT_INDEX:
        raise ValueError("パレットに透過色index 1がありません。")
    return colors


def weapon_strip_png(resource_path: Path, palette_path: Path) -> bytes:
    with zipfile.ZipFile(resource_path) as archive:
        document = tomllib.loads(archive.read("pyxel_resource.toml").decode("utf-8"))
    images = document.get("images")
    if not isinstance(images, list) or not images:
        raise ValueError("assets.pyxresにイメージバンク0がありません。")
    bank = images[0]
    rows = bank.get("data")
    if not isinstance(rows, list) or bank.get("width") != 256 or bank.get("height") != 256:
        raise ValueError("assets.pyxresのイメージバンク0が256×256ではありません。")
    palette = _read_palette(palette_path)
    image = Image.new("RGBA", (256, 16), (0, 0, 0, 0))
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(32, 48):
        row = rows[y] if y < len(rows) and isinstance(rows[y], list) else []
        for x in range(256):
            color_index = row[x] if x < len(row) else 0
            if not _integer(color_index) or not 0 <= color_index < len(palette):
                raise ValueError(f"イメージバンク0 ({x}, {y}) の色番号が不正です。")
            red, green, blue = palette[color_index]
            pixels.append((red, green, blue, 0 if color_index == TRANSPARENT_INDEX else 255))
    image.putdata(pixels)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def character_sheet_png(path: Path) -> bytes:
    with Image.open(path) as source:
        if source.width < 160 or source.height < 128:
            raise ValueError("ch_battle.gifに4人分の10ポーズがありません。")
        image = source.convert("RGBA")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class AttackPoseApplication:
    def __init__(
        self,
        content_root: Path,
        app_root: Path,
        *,
        token: str | None = None,
    ) -> None:
        self.content_root = content_root.resolve()
        self.app_root = app_root.resolve()
        self.source_path = (self.content_root / "battle" / "attack_poses.json").resolve()
        self.generated_path = (self.app_root / "effects" / "attack_poses.json").resolve()
        expected_root = (self.content_root / "battle").resolve()
        if expected_root not in self.source_path.parents:
            raise ValueError("保存先がcontent/battle外です。")
        self.character_path = self.content_root / "images" / "characters" / "ch_battle.gif"
        self.character_data_path = self.content_root / "data" / "characters.json"
        self.text_data_path = self.content_root / "data" / "texts.json"
        self.item_data_path = self.content_root / "data" / "items.json"
        self.resource_path = self.app_root / "assets.pyxres"
        self.palette_path = self.app_root / "assets.pyxpal"
        self.token = token or secrets.token_urlsafe(24)

    def character_catalog(self) -> list[dict[str, object]]:
        records = json.loads(self.character_data_path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("characters.jsonのルートが配列ではありません。")
        by_key = {
            record.get("name_en"): record
            for record in records
            if isinstance(record, dict) and isinstance(record.get("name_en"), str)
        }
        catalog: list[dict[str, object]] = []
        for key in CHARACTER_KEYS:
            record = by_key.get(key)
            if not isinstance(record, dict):
                raise ValueError(f"characters.jsonに{key}がありません。")
            battle_sprite = record.get("battle_sprite")
            if not _integer(battle_sprite) or battle_sprite < 0:
                raise ValueError(f"{key}.battle_spriteが不正です。")
            race = record.get("race")
            if race not in RACE_KEYS:
                raise ValueError(f"{key}.raceが不正です。")
            catalog.append({
                "key": key,
                "name": record.get("name_ja", key),
                "battle_sprite": battle_sprite,
                "race": race,
            })
        return catalog

    def race_catalog(self) -> list[dict[str, str]]:
        records = json.loads(self.text_data_path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("texts.jsonのルートが配列ではありません。")
        labels = {
            record.get("text_key"): record.get("text_ja")
            for record in records
            if isinstance(record, dict)
        }
        return [
            {"key": race, "name": labels.get(f"race.{race}") or race}
            for race in RACE_KEYS
        ]

    def weapon_img_catalog(self) -> list[str]:
        records = json.loads(self.item_data_path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("items.jsonのルートが配列ではありません。")
        values: list[str] = []
        seen: set[str] = set()
        for record in records:
            value = record.get("weapon_img") if isinstance(record, dict) else None
            if not isinstance(value, str):
                raise ValueError("items.jsonのweapon_imgは文字列である必要があります。")
            if not value or value in seen:
                continue
            if WEAPON_IMG_PATTERN.fullmatch(value) is None:
                raise ValueError(f"items.jsonのweapon_imgが不正です: {value}")
            seen.add(value)
            values.append(value)
        if "SWORD-1" not in seen:
            raise ValueError("items.jsonに初期weapon_imgのSWORD-1がありません。")
        return values

    def validate(self, data: object) -> list[dict[str, str]]:
        return validate_document(data, set(self.weapon_img_catalog()))

    def load(self) -> tuple[dict[str, object], bool]:
        if not self.source_path.is_file():
            return initial_document(), True
        data = json.loads(self.source_path.read_text(encoding="utf-8"))
        issues = self.validate(data)
        if issues:
            raise ValueError(issues[0]["message"])
        return data, False

    def document_payload(self) -> dict[str, object]:
        data, is_new = self.load()
        return {
            "data": data,
            "characters": self.character_catalog(),
            "races": self.race_catalog(),
            "weapon_img_options": self.weapon_img_catalog(),
            "character_image_url": f"/api/characters.png?token={self.token}",
            "weapon_image_url": f"/api/weapons.png?token={self.token}",
            "source_path": self.source_path.relative_to(PROJECT_ROOT).as_posix()
            if self.source_path.is_relative_to(PROJECT_ROOT)
            else str(self.source_path),
            "is_new": is_new,
            "diagnostics": self.validate(data),
        }

    def save(self, data: object) -> dict[str, object]:
        issues = self.validate(data)
        if issues or not isinstance(data, dict):
            return {"saved": False, "diagnostics": issues}
        try:
            poses = parse_attack_poses(data)
        except AttackPoseDataError as error:
            return {"saved": False, "diagnostics": [{
                "severity": "error", "code": "invalid_attack_pose", "path": "poses",
                "message": str(error),
            }]}
        generated = {
            "format_version": ATTACK_POSE_FORMAT_VERSION,
            "poses": [pose.to_record() for pose in poses.values()],
        }
        self.source_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.source_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(self.source_path)
        try:
            self.generated_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_generated_path = self.generated_path.with_suffix(".json.tmp")
            temporary_generated_path.write_text(
                json.dumps(generated, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_generated_path.replace(self.generated_path)
        except OSError as error:
            return {
                "saved": True,
                "compiled": False,
                "diagnostics": [],
                "error": f"正本は保存しましたが、ゲーム用データを更新できませんでした: {error}",
                "source_path": str(self.source_path),
            }
        return {
            "saved": True,
            "compiled": True,
            "diagnostics": [],
            "source_path": str(self.source_path),
        }


def create_handler(application: AttackPoseApplication) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: HTTPStatus, payload: object) -> None:
            self._send(
                status,
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8",
            )

        def _authorized_query(self, query: dict[str, list[str]]) -> bool:
            return query.get("token", [None])[0] == application.token

        def _authorized_post(self) -> bool:
            return secrets.compare_digest(
                self.headers.get("X-Attack-Pose-Token", ""),
                application.token,
            )

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                if parsed.path == "/api/document":
                    if not self._authorized_query(query):
                        self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                        return
                    self._json(HTTPStatus.OK, application.document_payload())
                    return
                if parsed.path == "/api/characters.png":
                    if not self._authorized_query(query):
                        self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                        return
                    self._send(HTTPStatus.OK, character_sheet_png(application.character_path), "image/png")
                    return
                if parsed.path == "/api/weapons.png":
                    if not self._authorized_query(query):
                        self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                        return
                    self._send(
                        HTTPStatus.OK,
                        weapon_strip_png(application.resource_path, application.palette_path),
                        "image/png",
                    )
                    return

                relative = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
                static_path = (STATIC_ROOT / relative).resolve()
                if STATIC_ROOT not in static_path.parents or not static_path.is_file():
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
                self._send(
                    HTTPStatus.OK,
                    static_path.read_bytes(),
                    MIME_TYPES.get(static_path.suffix.lower(), "application/octet-stream"),
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as error:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized_post():
                self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
                return
            if urlparse(self.path).path != "/api/save":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_REQUEST_BYTES:
                    raise ValueError("リクエストサイズが不正です。")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("リクエストのルートはobjectである必要があります。")
                self._json(HTTPStatus.OK, application.save(payload.get("data")))
            except (ValueError, json.JSONDecodeError, OSError) as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def create_server(application: AttackPoseApplication, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((DEFAULT_HOST, port), create_handler(application))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    application = AttackPoseApplication(args.content_root, args.app_root)
    try:
        server = create_server(application, args.port)
    except OSError as error:
        print(f"サーバーを起動できません: {error}", file=sys.stderr)
        return 1
    host, port = server.server_address
    url = f"http://{host}:{port}/?token={application.token}"
    print(f"Attack Pose Editor: {url}")
    print("終了するには Ctrl+C を押してください。")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
