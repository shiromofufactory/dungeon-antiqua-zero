"""Editable spell-effect state and conflict-safe persistence."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

from app.spell_effect import SpellEffectDefinition
from scripts.spell_effect_pipeline import (
    SpellEffectCatalogs,
    SpellEffectDiagnostic,
    SpellEffectSourceError,
    atomic_write,
    definitions_from_document,
    json_bytes,
    load_project_catalogs,
    load_source,
    save_source_and_compiled,
    source_document_from_definitions,
    source_sha256,
    validate_document,
)


DEFAULT_IMAGE_ID = "effects/spells64"
DEFAULT_FRAMES_PER_PATTERN = 4
SE_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*\Z")


@dataclass(frozen=True)
class EditorSpell:
    key: str
    name: str
    type: str
    on_battle: bool


@dataclass(frozen=True)
class SoundEffectEntry:
    se_id: str
    channel: int
    sound: int


class SpellEffectEditorStore:
    """Own effect and SE drafts, diagnostics, and conflict-safe persistence."""

    def __init__(
        self,
        project_root: Path,
        *,
        content_root: Path | None = None,
        catalogs: SpellEffectCatalogs | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.content_root = (content_root or self.project_root / "content").resolve()
        self.source_path = self.content_root / "effects" / "spells.json"
        self.runtime_path = self.project_root / "app" / "effects" / "spells.json"
        self.audio_catalog_path = self.project_root / "app" / "audio" / "catalog.json"
        self.catalogs = catalogs or load_project_catalogs(
            self.project_root, content_root=self.content_root
        )
        self.spells = self._load_editor_spells()
        self._spell_order = tuple(spell.key for spell in self.spells)
        self._loaded_hash = source_sha256(self.source_path)
        self._audio_loaded_hash = source_sha256(self.audio_catalog_path)
        self._sound_effects = self._load_sound_effects()
        source = load_source(self.source_path)
        self._definitions = dict(definitions_from_document(source, self.catalogs))
        self._diagnostics = validate_document(source, self.catalogs)
        self._effect_dirty = False
        self._audio_dirty = False

    def _load_sound_effects(self) -> dict[str, SoundEffectEntry]:
        try:
            document = json.loads(self.audio_catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SpellEffectSourceError(
                f"SEカタログを読み込めません: {self.audio_catalog_path}: {error}"
            ) from error
        records = document.get("sound_effects") if isinstance(document, dict) else None
        if (
            not isinstance(document, dict)
            or document.get("format_version") != 1
            or not isinstance(records, dict)
        ):
            raise SpellEffectSourceError("SEカタログの形式が不正です。")
        result: dict[str, SoundEffectEntry] = {}
        for se_id, record in records.items():
            channel = record.get("channel") if isinstance(record, dict) else None
            sound = record.get("sound") if isinstance(record, dict) else None
            if (
                not isinstance(se_id, str)
                or SE_ID_PATTERN.fullmatch(se_id) is None
                or isinstance(channel, bool)
                or not isinstance(channel, int)
                or channel < 0
                or isinstance(sound, bool)
                or not isinstance(sound, int)
                or sound < 0
            ):
                raise SpellEffectSourceError(f"SEカタログのレコードが不正です: {se_id}")
            result[se_id] = SoundEffectEntry(se_id, channel, sound)
        return result

    @property
    def dirty(self) -> bool:
        return self._effect_dirty or self._audio_dirty

    @property
    def sound_effects(self) -> Mapping[str, SoundEffectEntry]:
        return MappingProxyType(self._sound_effects)

    def sound_effect(self, se_id: str) -> SoundEffectEntry:
        try:
            return self._sound_effects[se_id]
        except KeyError as error:
            raise ValueError(f"未登録のSE IDです: {se_id}") from error

    def register_sound_effect(self, se_id: str, *, channel: int, sound: int) -> None:
        if not isinstance(se_id, str) or SE_ID_PATTERN.fullmatch(se_id) is None:
            raise ValueError("SE IDは英小文字で始まる英小文字・数字・_にしてください。")
        if se_id in self._sound_effects:
            raise ValueError(f"登録済みのSE IDです: {se_id}")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (channel, sound)
        ):
            raise ValueError("SEのchannelとSound番号は0以上の整数が必要です。")
        self._sound_effects[se_id] = SoundEffectEntry(se_id, channel, sound)
        self.catalogs = replace(
            self.catalogs,
            se_ids=frozenset(self._sound_effects),
        )
        self._audio_dirty = True
        self._refresh_diagnostics()

    def _load_editor_spells(self) -> tuple[EditorSpell, ...]:
        path = self.content_root / "data" / "spells.json"
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SpellEffectSourceError(
                f"呪文マスターを読み込めません: {path}: {error}"
            ) from error
        if not isinstance(records, list):
            raise SpellEffectSourceError("spells.jsonのルートは配列が必要です。")
        result: list[EditorSpell] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            key = record.get("name_en")
            name = record.get("name_ja")
            spell_type = record.get("type")
            on_battle = record.get("on_battle")
            if (
                not isinstance(key, str)
                or not key
                or not isinstance(name, str)
                or not isinstance(spell_type, str)
                or isinstance(on_battle, bool)
                or on_battle not in (0, 1)
            ):
                raise SpellEffectSourceError(f"呪文マスターの表示項目が不正です: {key}")
            result.append(EditorSpell(key, name, spell_type, bool(on_battle)))
        return tuple(result)

    @property
    def definitions(self) -> Mapping[str, SpellEffectDefinition]:
        return MappingProxyType(self._definitions)

    @property
    def diagnostics(self) -> tuple[SpellEffectDiagnostic, ...]:
        return self._diagnostics

    def diagnostics_for(self, spell_key: str) -> tuple[SpellEffectDiagnostic, ...]:
        return tuple(item for item in self._diagnostics if item.spell_key == spell_key)

    def definition(self, spell_key: str) -> SpellEffectDefinition | None:
        return self._definitions.get(spell_key)

    def preview_definition(self, spell_key: str) -> SpellEffectDefinition:
        saved = self.definition(spell_key)
        if saved is not None:
            return saved
        return SpellEffectDefinition.from_record(
            spell_key,
            {
                "kind": "target_sprite",
                "image_id": DEFAULT_IMAGE_ID,
                "row": 0,
                "frame_count": 1,
                "frames_per_pattern": DEFAULT_FRAMES_PER_PATTERN,
                "offset": {"ally": [0, 0], "enemy": [0, 0]},
                "flash_color": None,
                "se_id": None,
            },
        )

    def set_definition(self, definition: SpellEffectDefinition) -> None:
        if definition.spell_key not in self._spell_order:
            raise ValueError(f"未定義の呪文キーです: {definition.spell_key}")
        checked = SpellEffectDefinition.from_record(
            definition.spell_key,
            definition.to_runtime_record(),
        )
        if self._definitions.get(definition.spell_key) == checked:
            return
        self._definitions[definition.spell_key] = checked
        self._effect_dirty = True
        self._refresh_diagnostics()

    def remove_definition(self, spell_key: str) -> None:
        if spell_key in self._definitions:
            del self._definitions[spell_key]
            self._effect_dirty = True
            self._refresh_diagnostics()

    def _source_document(self) -> dict[str, object]:
        return source_document_from_definitions(self._definitions, self._spell_order)

    def _refresh_diagnostics(self) -> None:
        self._diagnostics = validate_document(self._source_document(), self.catalogs)

    def save(self) -> None:
        current_hash = source_sha256(self.source_path)
        if current_hash != self._loaded_hash:
            raise SpellEffectSourceError(
                "呪文エフェクト設定が外部で変更されています。再起動して読み直してください。"
            )
        current_audio_hash = source_sha256(self.audio_catalog_path)
        if current_audio_hash != self._audio_loaded_hash:
            raise SpellEffectSourceError(
                "SEカタログが外部で変更されています。再起動して読み直してください。"
            )
        source = self._source_document()
        if self._audio_dirty:
            audio_document = {
                "format_version": 1,
                "sound_effects": {
                    se_id: {
                        "channel": entry.channel,
                        "sound": entry.sound,
                    }
                    for se_id, entry in self._sound_effects.items()
                },
            }
            atomic_write(self.audio_catalog_path, json_bytes(audio_document))
            self._audio_loaded_hash = source_sha256(self.audio_catalog_path)
        save_source_and_compiled(
            self.source_path,
            self.runtime_path,
            source,
            self.catalogs,
        )
        self._loaded_hash = source_sha256(self.source_path)
        self._diagnostics = validate_document(source, self.catalogs)
        self._effect_dirty = False
        self._audio_dirty = False


__all__ = [
    "DEFAULT_FRAMES_PER_PATTERN",
    "DEFAULT_IMAGE_ID",
    "EditorSpell",
    "SE_ID_PATTERN",
    "SoundEffectEntry",
    "SpellEffectEditorStore",
]
