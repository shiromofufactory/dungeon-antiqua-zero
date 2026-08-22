"""Load compiled image resources for Pyxel without decoding source PNG files."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import pyxel


FORMAT_VERSION = 1
PIXEL_FORMAT = "pyxel-palette-index-u8"
TRANSPARENT_INDEX = 1
TRANSPARENT_COLOR = "#FF0080"


class ImageResourceError(RuntimeError):
    """Raised when compiled image resources are missing or inconsistent."""


@dataclass(frozen=True)
class ImageEntry:
    id: str
    source: str
    width: int
    height: int
    offset: int
    length: int


class ImageResources:
    """Own the compiled image bundle and lazily create Pyxel images from it."""

    def __init__(self, images_dir: Path | None = None, *, verify: bool = True):
        app_dir = Path(__file__).resolve().parents[1]
        self.images_dir = (images_dir or app_dir / "images").resolve()
        manifest_path = self.images_dir / "manifest.json"

        try:
            manifest_bytes = manifest_path.read_bytes()
            manifest = json.loads(manifest_bytes)
        except FileNotFoundError as error:
            raise ImageResourceError(
                f"画像生成物がありません: {manifest_path}\n"
                "npm run images:build を実行してください。"
            ) from error
        except json.JSONDecodeError as error:
            raise ImageResourceError(
                f"画像manifestを読み込めません: {manifest_path}: {error}"
            ) from error

        self._validate_manifest_header(manifest)
        bundle_name = manifest.get("bundle")
        if not isinstance(bundle_name, str) or Path(bundle_name).name != bundle_name:
            raise ImageResourceError("画像manifestのbundle名が不正です。")
        bundle_path = self.images_dir / bundle_name
        try:
            self._bundle = bundle_path.read_bytes()
        except FileNotFoundError as error:
            raise ImageResourceError(
                f"画像bundleがありません: {bundle_path}\n"
                "npm run images:build を実行してください。"
            ) from error

        if verify:
            self._verify_hash(
                self._bundle,
                manifest.get("bundle_sha256"),
                "画像bundle",
            )
            palette = manifest["palette"]
            palette_path = (self.images_dir / palette["file"]).resolve()
            try:
                palette_bytes = palette_path.read_bytes()
            except FileNotFoundError as error:
                raise ImageResourceError(
                    f"画像manifestが参照するパレットがありません: {palette_path}"
                ) from error
            self._verify_hash(
                palette_bytes,
                palette.get("sha256"),
                "画像パレット",
            )

        self._entries = self._load_entries(manifest.get("images"))
        if manifest.get("total_pixels") != len(self._bundle):
            raise ImageResourceError(
                "画像manifestのtotal_pixelsとbundleサイズが一致しません。"
            )
        self._cache: dict[str, pyxel.Image] = {}

    @staticmethod
    def _verify_hash(data: bytes, expected: object, label: str) -> None:
        actual = hashlib.sha256(data).hexdigest()
        if not isinstance(expected, str) or actual != expected:
            raise ImageResourceError(
                f"{label}のSHA-256がmanifestと一致しません。"
            )

    @staticmethod
    def _validate_manifest_header(manifest: object) -> None:
        if not isinstance(manifest, dict):
            raise ImageResourceError("画像manifestのルートはobjectである必要があります。")
        if manifest.get("format_version") != FORMAT_VERSION:
            raise ImageResourceError(
                f"未対応の画像format_versionです: {manifest.get('format_version')}"
            )
        if manifest.get("pixel_format") != PIXEL_FORMAT:
            raise ImageResourceError(
                f"未対応の画像pixel_formatです: {manifest.get('pixel_format')}"
            )
        palette = manifest.get("palette")
        if not isinstance(palette, dict):
            raise ImageResourceError("画像manifestにpalette情報がありません。")
        if (
            palette.get("transparent_index") != TRANSPARENT_INDEX
            or palette.get("transparent_color") != TRANSPARENT_COLOR
        ):
            raise ImageResourceError(
                f"透過色はパレット[{TRANSPARENT_INDEX}] "
                f"{TRANSPARENT_COLOR}である必要があります。"
            )
        if not isinstance(palette.get("file"), str):
            raise ImageResourceError("画像manifestのpalette.fileが不正です。")

    def _load_entries(self, records: object) -> dict[str, ImageEntry]:
        if not isinstance(records, list) or not records:
            raise ImageResourceError("画像manifestに画像がありません。")

        entries: dict[str, ImageEntry] = {}
        ranges = []
        for record in records:
            if not isinstance(record, dict):
                raise ImageResourceError("画像manifestのimages要素が不正です。")
            try:
                entry = ImageEntry(
                    id=record["id"],
                    source=record["source"],
                    width=record["width"],
                    height=record["height"],
                    offset=record["offset"],
                    length=record["length"],
                )
            except KeyError as error:
                raise ImageResourceError(
                    f"画像manifestに{error.args[0]}がありません。"
                ) from error

            if not entry.id or not isinstance(entry.id, str):
                raise ImageResourceError("画像IDが不正です。")
            if entry.id in entries:
                raise ImageResourceError(f"画像IDが重複しています: {entry.id}")
            if not isinstance(entry.source, str) or not entry.source:
                raise ImageResourceError(f"画像sourceが不正です: {entry.id}")
            values = (entry.width, entry.height, entry.offset, entry.length)
            if not all(isinstance(value, int) for value in values):
                raise ImageResourceError(f"画像の寸法またはoffsetが不正です: {entry.id}")
            if entry.width <= 0 or entry.height <= 0:
                raise ImageResourceError(f"画像の寸法が不正です: {entry.id}")
            if entry.length != entry.width * entry.height:
                raise ImageResourceError(f"画像の画素数が一致しません: {entry.id}")
            end = entry.offset + entry.length
            if entry.offset < 0 or end > len(self._bundle):
                raise ImageResourceError(f"画像がbundle範囲外です: {entry.id}")

            entries[entry.id] = entry
            ranges.append((entry.offset, end, entry.id))

        ranges.sort()
        for previous, current in zip(ranges, ranges[1:]):
            if previous[1] > current[0]:
                raise ImageResourceError(
                    f"画像領域が重複しています: {previous[2]}, {current[2]}"
                )
        return entries

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def entry(self, image_id: str) -> ImageEntry:
        try:
            return self._entries[image_id]
        except KeyError as error:
            raise ImageResourceError(f"未定義の画像IDです: {image_id}") from error

    def image(self, image_id: str) -> pyxel.Image:
        cached = self._cache.get(image_id)
        if cached is not None:
            return cached

        entry = self.entry(image_id)
        image = pyxel.Image(entry.width, entry.height)
        start = entry.offset
        image.data_ptr()[:] = self._bundle[start : start + entry.length]
        self._cache[image_id] = image
        return image

    def copy_to_bank(
        self,
        image_id: str,
        bank: int,
        x: int = 0,
        y: int = 0,
    ) -> ImageEntry:
        """Copy an entire resource image into a Pyxel image bank."""
        entry = self.entry(image_id)
        return self.copy_region_to_bank(
            image_id,
            bank,
            source_x=0,
            source_y=0,
            width=entry.width,
            height=entry.height,
            x=x,
            y=y,
        )

    def copy_region_to_bank(
        self,
        image_id: str,
        bank: int,
        source_x: int,
        source_y: int,
        width: int,
        height: int,
        x: int = 0,
        y: int = 0,
    ) -> ImageEntry:
        """Copy an explicit resource rectangle into a Pyxel image bank."""
        entry = self.entry(image_id)
        values = {
            "bank": bank,
            "source_x": source_x,
            "source_y": source_y,
            "width": width,
            "height": height,
            "x": x,
            "y": y,
        }
        invalid = [name for name, value in values.items() if not isinstance(value, int)]
        if invalid:
            raise ImageResourceError(
                "画像転送の引数は整数である必要があります: " + ", ".join(invalid)
            )
        if bank < 0 or bank >= len(pyxel.images):
            raise ImageResourceError(f"未定義のイメージバンクです: {bank}")
        if width <= 0 or height <= 0:
            raise ImageResourceError(
                f"画像転送サイズは正数である必要があります: {width}x{height}"
            )
        if (
            source_x < 0
            or source_y < 0
            or source_x + width > entry.width
            or source_y + height > entry.height
        ):
            raise ImageResourceError(
                f"転送元が画像範囲外です: {image_id} "
                f"({source_x}, {source_y}, {width}, {height}) / "
                f"{entry.width}x{entry.height}"
            )

        try:
            target = pyxel.images[bank]
        except IndexError as error:
            raise ImageResourceError(f"未定義のイメージバンクです: {bank}") from error
        if x < 0 or y < 0 or x + width > target.width or y + height > target.height:
            raise ImageResourceError(
                f"転送先がイメージバンク範囲外です: {image_id} "
                f"({width}x{height}) -> bank {bank} ({x}, {y}) / "
                f"{target.width}x{target.height}"
            )
        target.blt(
            x,
            y,
            self.image(image_id),
            source_x,
            source_y,
            width,
            height,
        )
        return entry

    def clear_cache(self) -> None:
        self._cache.clear()
