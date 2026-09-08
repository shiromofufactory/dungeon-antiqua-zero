"""Validate and compile authoring-time spell-effect settings."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Iterable, Mapping

from app.spell_effect import (
    SPELL_EFFECT_FORMAT_VERSION,
    SPELL_EFFECT_IMAGE_CELL_SIZES,
    SUPPORTED_SPELL_EFFECT_FORMAT_VERSIONS,
    SpellEffectDataError,
    SpellEffectDefinition,
)


@dataclass(frozen=True)
class SpellEffectDiagnostic:
    severity: str
    code: str
    message: str
    spell_key: str | None = None


@dataclass(frozen=True)
class SpellCatalogEntry:
    key: str
    on_battle: bool


@dataclass(frozen=True)
class ImageCatalogEntry:
    id: str
    width: int
    height: int
    offset: int
    length: int


@dataclass(frozen=True)
class SpellEffectCatalogs:
    spells: tuple[SpellCatalogEntry, ...]
    images: Mapping[str, ImageCatalogEntry]
    palette_color_count: int
    transparent_index: int
    se_ids: frozenset[str]
    image_bundle: bytes

    @property
    def spell_keys(self) -> tuple[str, ...]:
        return tuple(spell.key for spell in self.spells)

    @property
    def battle_spell_keys(self) -> tuple[str, ...]:
        return tuple(spell.key for spell in self.spells if spell.on_battle)


class SpellEffectSourceError(ValueError):
    """Raised when spell-effect source data cannot be compiled or saved."""


def initial_document() -> dict[str, object]:
    return {"format_version": SPELL_EFFECT_FORMAT_VERSION, "effects": []}


def source_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_source(path: Path) -> dict[str, object]:
    if not path.is_file():
        return initial_document()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SpellEffectSourceError(
            f"呪文エフェクト設定を読み込めません: {path}: {error}"
        ) from error
    if not isinstance(document, dict):
        raise SpellEffectSourceError("呪文エフェクト設定のルートはobjectが必要です。")
    return document


def _load_spells(path: Path) -> tuple[SpellCatalogEntry, ...]:
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SpellEffectSourceError(f"呪文マスターを読み込めません: {path}: {error}") from error
    if not isinstance(records, list):
        raise SpellEffectSourceError("spells.jsonのルートは配列が必要です。")
    result: list[SpellCatalogEntry] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise SpellEffectSourceError(f"spells.json[{index}]はobjectが必要です。")
        key = record.get("name_en")
        on_battle = record.get("on_battle")
        if not isinstance(key, str) or not key:
            raise SpellEffectSourceError(f"spells.json[{index}].name_enが不正です。")
        if key in seen:
            raise SpellEffectSourceError(f"呪文キーが重複しています: {key}")
        if isinstance(on_battle, bool) or on_battle not in (0, 1):
            raise SpellEffectSourceError(f"{key}.on_battleは0または1が必要です。")
        seen.add(key)
        result.append(SpellCatalogEntry(key, bool(on_battle)))
    return tuple(result)


def _load_images(
    manifest_path: Path,
) -> tuple[Mapping[str, ImageCatalogEntry], int, int, Path]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SpellEffectSourceError(
            f"画像manifestを読み込めません: {manifest_path}: {error}"
        ) from error
    if not isinstance(manifest, dict):
        raise SpellEffectSourceError("画像manifestのルートはobjectが必要です。")
    palette = manifest.get("palette")
    if not isinstance(palette, dict):
        raise SpellEffectSourceError("画像manifestにpalette情報がありません。")
    color_count = palette.get("colors")
    transparent_index = palette.get("transparent_index")
    if (
        isinstance(color_count, bool)
        or not isinstance(color_count, int)
        or color_count <= 0
        or isinstance(transparent_index, bool)
        or not isinstance(transparent_index, int)
        or transparent_index < 0
    ):
        raise SpellEffectSourceError("画像manifestのpalette情報が不正です。")
    bundle_name = manifest.get("bundle")
    if not isinstance(bundle_name, str) or Path(bundle_name).name != bundle_name:
        raise SpellEffectSourceError("画像manifestのbundle名が不正です。")

    records = manifest.get("images")
    if not isinstance(records, list):
        raise SpellEffectSourceError("画像manifestのimagesは配列が必要です。")
    entries: dict[str, ImageCatalogEntry] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        values = tuple(record.get(field) for field in ("width", "height", "offset", "length"))
        image_id = record.get("id")
        if (
            not isinstance(image_id, str)
            or not image_id
            or any(isinstance(value, bool) or not isinstance(value, int) for value in values)
        ):
            raise SpellEffectSourceError("画像manifestの画像レコードが不正です。")
        width, height, offset, length = values
        if width <= 0 or height <= 0 or offset < 0 or length != width * height:
            raise SpellEffectSourceError(f"画像manifestの画像範囲が不正です: {image_id}")
        entries[image_id] = ImageCatalogEntry(
            image_id, width, height, offset, length
        )
    return (
        MappingProxyType(entries),
        color_count,
        transparent_index,
        manifest_path.parent / bundle_name,
    )


def _load_se_ids(path: Path) -> frozenset[str]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SpellEffectSourceError(f"SEカタログを読み込めません: {path}: {error}") from error
    records = document.get("sound_effects") if isinstance(document, dict) else None
    if not isinstance(records, dict):
        raise SpellEffectSourceError("SEカタログのsound_effectsが不正です。")
    return frozenset(key for key in records if isinstance(key, str) and key)


def load_project_catalogs(
    project_root: Path,
    *,
    content_root: Path | None = None,
) -> SpellEffectCatalogs:
    project_root = project_root.resolve()
    content_root = (content_root or project_root / "content").resolve()
    images, color_count, transparent_index, bundle_path = _load_images(
        project_root / "app" / "images" / "manifest.json"
    )
    try:
        bundle = bundle_path.read_bytes()
    except OSError as error:
        raise SpellEffectSourceError(
            f"画像bundleを読み込めません: {bundle_path}: {error}"
        ) from error
    if any(entry.offset + entry.length > len(bundle) for entry in images.values()):
        raise SpellEffectSourceError("画像manifestがbundle範囲外を参照しています。")
    return SpellEffectCatalogs(
        spells=_load_spells(content_root / "data" / "spells.json"),
        images=images,
        palette_color_count=color_count,
        transparent_index=transparent_index,
        se_ids=_load_se_ids(project_root / "app" / "audio" / "catalog.json"),
        image_bundle=bundle,
    )


def _empty_selected_cells(
    definition: SpellEffectDefinition,
    catalogs: SpellEffectCatalogs,
) -> tuple[int, ...]:
    entry = catalogs.images[definition.image_id]
    cell_size = definition.cell_size
    empty: list[int] = []
    for frame in range(definition.frame_count):
        source_x = frame * cell_size
        source_y = definition.row * cell_size
        has_visible_pixel = False
        for y in range(source_y, source_y + cell_size):
            start = entry.offset + y * entry.width + source_x
            row = catalogs.image_bundle[start : start + cell_size]
            if any(pixel != catalogs.transparent_index for pixel in row):
                has_visible_pixel = True
                break
        if not has_visible_pixel:
            empty.append(frame)
    return tuple(empty)


def validate_document(
    document: object,
    catalogs: SpellEffectCatalogs,
) -> tuple[SpellEffectDiagnostic, ...]:
    diagnostics: list[SpellEffectDiagnostic] = []
    if not isinstance(document, dict):
        return (
            SpellEffectDiagnostic("error", "invalid_root", "ルートはobjectが必要です。"),
        )
    format_version = document.get("format_version")
    if (
        isinstance(format_version, bool)
        or format_version not in SUPPORTED_SPELL_EFFECT_FORMAT_VERSIONS
    ):
        diagnostics.append(
            SpellEffectDiagnostic(
                "error",
                "invalid_format_version",
                f"format_versionは{SPELL_EFFECT_FORMAT_VERSION}が必要です。",
            )
        )
    elif format_version != SPELL_EFFECT_FORMAT_VERSION:
        diagnostics.append(
            SpellEffectDiagnostic(
                "warning",
                "legacy_format_version",
                "旧形式のOFFSETは味方・敵の両方へ引き継がれ、保存時に更新されます。",
            )
        )
    records = document.get("effects")
    if not isinstance(records, list):
        diagnostics.append(
            SpellEffectDiagnostic("error", "invalid_effects", "effectsは配列が必要です。")
        )
        return tuple(diagnostics)

    spell_by_key = {spell.key: spell for spell in catalogs.spells}
    seen: set[str] = set()
    configured: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            diagnostics.append(
                SpellEffectDiagnostic(
                    "error", "invalid_record", f"effects[{index}]はobjectが必要です。"
                )
            )
            continue
        spell_key = record.get("spell_key")
        key_for_diagnostic = spell_key if isinstance(spell_key, str) else None
        if not isinstance(spell_key, str) or not spell_key:
            diagnostics.append(
                SpellEffectDiagnostic(
                    "error",
                    "invalid_spell_key",
                    f"effects[{index}].spell_keyは空でない文字列が必要です。",
                )
            )
            continue
        if spell_key in seen:
            diagnostics.append(
                SpellEffectDiagnostic(
                    "error", "duplicate_spell_key", "呪文キーが重複しています。", spell_key
                )
            )
            continue
        seen.add(spell_key)
        configured.add(spell_key)
        if spell_key not in spell_by_key:
            diagnostics.append(
                SpellEffectDiagnostic(
                    "error", "unknown_spell_key", "呪文マスターに存在しません。", spell_key
                )
            )

        runtime_record = {key: value for key, value in record.items() if key != "spell_key"}
        try:
            definition = SpellEffectDefinition.from_record(spell_key, runtime_record)
        except SpellEffectDataError as error:
            diagnostics.append(
                SpellEffectDiagnostic(
                    "error", "invalid_definition", str(error), key_for_diagnostic
                )
            )
            continue

        entry = catalogs.images.get(definition.image_id)
        if entry is None:
            diagnostics.append(
                SpellEffectDiagnostic(
                    "error", "missing_image", "生成済み画像にimage_idがありません。", spell_key
                )
            )
            continue
        cell_size = SPELL_EFFECT_IMAGE_CELL_SIZES[definition.image_id]
        if (definition.row + 1) * cell_size > entry.height:
            diagnostics.append(
                SpellEffectDiagnostic(
                    "error", "row_out_of_bounds", "選択行が画像の高さを超えています。", spell_key
                )
            )
        if definition.frame_count * cell_size > entry.width:
            diagnostics.append(
                SpellEffectDiagnostic(
                    "error",
                    "frames_out_of_bounds",
                    "使用パターンが画像の完全セル範囲を超えています。",
                    spell_key,
                )
            )
        if (
            definition.flash_color is not None
            and (
                definition.flash_color >= catalogs.palette_color_count
                or definition.flash_color == catalogs.transparent_index
            )
        ):
            diagnostics.append(
                SpellEffectDiagnostic(
                    "error", "invalid_flash_color", "フラッシュ色が選択できません。", spell_key
                )
            )
        if definition.se_id is not None and definition.se_id not in catalogs.se_ids:
            diagnostics.append(
                SpellEffectDiagnostic(
                    "error", "unknown_se_id", "SEカタログに存在しません。", spell_key
                )
            )
        spell = spell_by_key.get(spell_key)
        if spell is not None and not spell.on_battle:
            diagnostics.append(
                SpellEffectDiagnostic(
                    "warning", "not_battle_spell", "戦闘外の呪文に設定されています。", spell_key
                )
            )
        if (
            (definition.row + 1) * cell_size <= entry.height
            and definition.frame_count * cell_size <= entry.width
        ):
            empty = _empty_selected_cells(definition, catalogs)
            if empty:
                diagnostics.append(
                    SpellEffectDiagnostic(
                        "warning",
                        "empty_frames",
                        "完全透過のパターンを含みます: "
                        + ", ".join(str(frame) for frame in empty),
                        spell_key,
                    )
                )

    for spell_key in catalogs.battle_spell_keys:
        if spell_key not in configured:
            diagnostics.append(
                SpellEffectDiagnostic(
                    "warning", "missing_effect", "戦闘用エフェクトが未設定です。", spell_key
                )
            )
    return tuple(diagnostics)


def definitions_from_document(
    document: object,
    catalogs: SpellEffectCatalogs,
) -> Mapping[str, SpellEffectDefinition]:
    diagnostics = validate_document(document, catalogs)
    errors = tuple(item for item in diagnostics if item.severity == "error")
    if errors:
        raise SpellEffectSourceError(
            "呪文エフェクト設定を生成できません:\n- "
            + "\n- ".join(
                f"{item.spell_key + ': ' if item.spell_key else ''}{item.message}"
                for item in errors
            )
        )
    assert isinstance(document, dict)
    records = document["effects"]
    assert isinstance(records, list)
    result: dict[str, SpellEffectDefinition] = {}
    for record in records:
        assert isinstance(record, dict)
        spell_key = record["spell_key"]
        assert isinstance(spell_key, str)
        runtime_record = {key: value for key, value in record.items() if key != "spell_key"}
        result[spell_key] = SpellEffectDefinition.from_record(spell_key, runtime_record)
    return MappingProxyType(result)


def compile_document(
    document: object,
    catalogs: SpellEffectCatalogs,
) -> dict[str, object]:
    definitions = definitions_from_document(document, catalogs)
    return {
        "format_version": SPELL_EFFECT_FORMAT_VERSION,
        "effects": {
            spell.key: definitions[spell.key].to_runtime_record()
            for spell in catalogs.spells
            if spell.key in definitions
        },
    }


def source_document_from_definitions(
    definitions: Mapping[str, SpellEffectDefinition],
    spell_order: Iterable[str],
) -> dict[str, object]:
    ordered = [key for key in spell_order if key in definitions]
    extras = sorted(key for key in definitions if key not in set(ordered))
    return {
        "format_version": SPELL_EFFECT_FORMAT_VERSION,
        "effects": [definitions[key].to_source_record() for key in (*ordered, *extras)],
    }


def json_bytes(document: object) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def save_compiled(path: Path, compiled: object) -> None:
    atomic_write(path, json_bytes(compiled))


def save_source_and_compiled(
    source_path: Path,
    runtime_path: Path,
    source_document: object,
    catalogs: SpellEffectCatalogs,
) -> None:
    compiled = compile_document(source_document, catalogs)
    # Both complete documents are prepared before either destination changes.
    source_content = json_bytes(source_document)
    runtime_content = json_bytes(compiled)
    atomic_write(source_path, source_content)
    try:
        atomic_write(runtime_path, runtime_content)
    except BaseException:
        # The source is canonical and remains valid. A later build can regenerate
        # the ignored runtime copy if the second filesystem write fails.
        raise


__all__ = [
    "ImageCatalogEntry",
    "SpellCatalogEntry",
    "SpellEffectCatalogs",
    "SpellEffectDiagnostic",
    "SpellEffectSourceError",
    "atomic_write",
    "compile_document",
    "definitions_from_document",
    "initial_document",
    "json_bytes",
    "load_project_catalogs",
    "load_source",
    "save_compiled",
    "save_source_and_compiled",
    "source_document_from_definitions",
    "source_sha256",
    "validate_document",
]
