"""Pyxel-independent definitions shared by runtime audio and authoring tools."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Mapping


SE_CATALOG_FORMAT_VERSION = 2
SE_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]*\Z")


class AudioCatalogError(ValueError):
    """Raised when an SE definition or its referenced asset is invalid."""


@dataclass(frozen=True)
class SoundEffectDefinition:
    se_id: str
    sound: int | None = None
    wav: str | None = None

    @classmethod
    def from_record(cls, se_id: str, record: object) -> SoundEffectDefinition:
        if not isinstance(se_id, str) or SE_ID_PATTERN.fullmatch(se_id) is None:
            raise AudioCatalogError("SE IDは英小文字で始まる英小文字・数字・_にしてください。")
        if not isinstance(record, dict) or set(record) not in ({"sound"}, {"wav"}):
            raise AudioCatalogError(f"SEにはsoundまたはwavの一方だけを指定してください: {se_id}")
        if "sound" in record:
            sound = record["sound"]
            if isinstance(sound, bool) or not isinstance(sound, int) or sound < 0:
                raise AudioCatalogError(f"SEのSound番号は0以上の整数が必要です: {se_id}")
            return cls(se_id, sound=sound)
        wav = record["wav"]
        if (
            not isinstance(wav, str)
            or not wav
            or "\\" in wav
            or PurePosixPath(wav).is_absolute()
            or any(part in ("", ".", "..") for part in wav.split("/"))
            or PurePosixPath(wav).suffix.lower() != ".wav"
        ):
            raise AudioCatalogError(f"SEのwavにはapp/se内のWAV相対パスが必要です: {se_id}")
        return cls(se_id, wav=wav)

    def to_record(self) -> dict[str, object]:
        return {"sound": self.sound} if self.wav is None else {"wav": self.wav}

    def wav_path(self, se_dir: Path) -> Path:
        root = se_dir.resolve()
        path = (root / self.wav).resolve() if self.wav is not None else root
        if self.wav is None or not path.is_relative_to(root) or not path.is_file():
            raise AudioCatalogError(f"SEのWAVが見つかりません: {self.se_id}: {self.wav}")
        return path


def load_sound_effects(
    path: Path, *, se_dir: Path | None = None,
) -> Mapping[str, SoundEffectDefinition]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AudioCatalogError(f"SEカタログを読み込めません: {path}: {error}") from error
    if (
        not isinstance(document, dict)
        or document.get("format_version") != SE_CATALOG_FORMAT_VERSION
    ):
        raise AudioCatalogError("SEカタログのformat_versionが不正です。")
    records = document.get("sound_effects")
    if not isinstance(records, dict) or not records:
        raise AudioCatalogError("SEカタログのsound_effectsが不正です。")
    root = se_dir or path.parent.parent / "se"
    definitions: dict[str, SoundEffectDefinition] = {}
    for se_id, record in records.items():
        definition = SoundEffectDefinition.from_record(se_id, record)
        if definition.wav is not None:
            definition.wav_path(root)
        definitions[se_id] = definition
    return MappingProxyType(definitions)
