"""Spell-effect definitions and 60 fps playback state independent of Pyxel."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


SPELL_EFFECT_FORMAT_VERSION = 2
SUPPORTED_SPELL_EFFECT_FORMAT_VERSIONS = frozenset((1, SPELL_EFFECT_FORMAT_VERSION))
SPELL_EFFECT_KIND = "target_sprite"
BLOOD_SUCK_EFFECT_KIND = "blood_suck"
DRAIN_FLIGHT_PATTERNS = (0, 1, 2, 2, 1, 0)
DRAIN_FLIGHT_FRAMES_PER_PATTERN = 2
DRAIN_FLIGHT_FRAME_COUNT = len(DRAIN_FLIGHT_PATTERNS) * DRAIN_FLIGHT_FRAMES_PER_PATTERN
SPELL_RESULT_OVERLAP_FRAME_COUNT = 4
BLOOD_SUCK_EFFECT_FRAME_COUNT = DRAIN_FLIGHT_FRAME_COUNT + SPELL_RESULT_OVERLAP_FRAME_COUNT
SCREEN_FLASH_TRANSITION_FRAMES = 16
FLASH_SCOPE_TARGET = "target"
FLASH_SCOPE_SCREEN = "screen"
SPELL_EFFECT_IMAGE_CELL_SIZES = MappingProxyType(
    {
        "effects/spells32": 32,
        "effects/spells64": 64,
    }
)
MIN_FRAMES_PER_PATTERN = 1
MAX_FRAMES_PER_PATTERN = 60
MIN_EFFECT_OFFSET = -128
MAX_EFFECT_OFFSET = 128


class SpellEffectDataError(ValueError):
    """Raised when compiled spell-effect data cannot be interpreted safely."""


@dataclass(frozen=True)
class SpellScreenFlash:
    """Tint toward a palette color, hold through the result, then restore."""

    color_index: int
    result_frame: int

    @property
    def release_frame(self) -> int:
        return max(SCREEN_FLASH_TRANSITION_FRAMES, self.result_frame)

    @property
    def end_frame(self) -> int:
        return self.release_frame + SCREEN_FLASH_TRANSITION_FRAMES

    def base_rate_at(self, elapsed_frame: int) -> float:
        blend_frames = max(0, min(
            elapsed_frame, SCREEN_FLASH_TRANSITION_FRAMES, self.end_frame - elapsed_frame,
        ))
        return 0.7 + math.cos(math.pi * blend_frames / SCREEN_FLASH_TRANSITION_FRAMES) * 0.3


def _integer(
    record: Mapping[str, object],
    field: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpellEffectDataError(f"spell effect.{field} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        maximum_text = "" if maximum is None else f" and at most {maximum}"
        raise SpellEffectDataError(
            f"spell effect.{field} must be at least {minimum}{maximum_text}"
        )
    return value


def _offset_pair(value: object, *, field: str, spell_key: str) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(isinstance(item, bool) or not isinstance(item, int) for item in value)
        or any(item < MIN_EFFECT_OFFSET or item > MAX_EFFECT_OFFSET for item in value)
    ):
        raise SpellEffectDataError(
            f"spell effect.{field} must contain two integers from "
            f"{MIN_EFFECT_OFFSET} to {MAX_EFFECT_OFFSET}: {spell_key}"
        )
    return value[0], value[1]


@dataclass(frozen=True)
class SpellEffectDefinition:
    """Immutable visual and audio settings for one spell effect."""

    spell_key: str
    kind: str
    image_id: str | None
    row: int
    frame_count: int
    frames_per_pattern: int
    ally_offset_x: int
    ally_offset_y: int
    enemy_offset_x: int
    enemy_offset_y: int
    flash_color: int | None
    se_id: str | None
    flash_scope: str = FLASH_SCOPE_TARGET

    @classmethod
    def from_record(
        cls,
        spell_key: str,
        record: Mapping[str, object],
    ) -> SpellEffectDefinition:
        if not isinstance(spell_key, str) or not spell_key:
            raise SpellEffectDataError("spell effect key must be a non-empty string")
        if not isinstance(record, Mapping):
            raise SpellEffectDataError(f"spell effect must be an object: {spell_key}")

        kind = record.get("kind")
        if kind not in (SPELL_EFFECT_KIND, BLOOD_SUCK_EFFECT_KIND):
            raise SpellEffectDataError(
                f"unsupported spell effect kind for {spell_key}: {kind}"
            )
        flash_color = record.get("flash_color")
        if flash_color is not None and (
            isinstance(flash_color, bool)
            or not isinstance(flash_color, int)
            or flash_color < 0
        ):
            raise SpellEffectDataError(
                f"spell effect.flash_color must be null or a non-negative integer: "
                f"{spell_key}"
            )
        flash_scope = record.get("flash_scope", FLASH_SCOPE_TARGET)
        if flash_scope not in (FLASH_SCOPE_TARGET, FLASH_SCOPE_SCREEN):
            raise SpellEffectDataError(
                f"spell effect.flash_scope must be target or screen: {spell_key}"
            )
        se_id = record.get("se_id")
        if se_id is not None and (not isinstance(se_id, str) or not se_id):
            raise SpellEffectDataError(
                f"spell effect.se_id must be null or a non-empty string: {spell_key}"
            )

        if kind == BLOOD_SUCK_EFFECT_KIND:
            return cls(
                spell_key=spell_key, kind=kind, image_id=None,
                row=0, frame_count=1, frames_per_pattern=4,
                ally_offset_x=0, ally_offset_y=0, enemy_offset_x=0, enemy_offset_y=0,
                flash_color=flash_color, se_id=se_id, flash_scope=flash_scope,
            )

        image_id = record.get("image_id")
        if not isinstance(image_id, str) or image_id not in SPELL_EFFECT_IMAGE_CELL_SIZES:
            raise SpellEffectDataError(
                f"unsupported spell effect image for {spell_key}: {image_id}"
            )
        offset = record.get("offset")
        if isinstance(offset, list):
            # format_version 1 compatibility: the single pair applied to both sides.
            ally_offset = enemy_offset = _offset_pair(
                offset, field="offset", spell_key=spell_key
            )
        elif isinstance(offset, Mapping):
            ally_offset = _offset_pair(
                offset.get("ally"), field="offset.ally", spell_key=spell_key
            )
            enemy_offset = _offset_pair(
                offset.get("enemy"), field="offset.enemy", spell_key=spell_key
            )
        else:
            raise SpellEffectDataError(
                f"spell effect.offset must be an ally/enemy object: {spell_key}"
            )

        return cls(
            spell_key=spell_key,
            kind=kind,
            image_id=image_id,
            row=_integer(record, "row", minimum=0),
            frame_count=_integer(record, "frame_count", minimum=1),
            frames_per_pattern=_integer(
                record,
                "frames_per_pattern",
                minimum=MIN_FRAMES_PER_PATTERN,
                maximum=MAX_FRAMES_PER_PATTERN,
            ),
            ally_offset_x=ally_offset[0],
            ally_offset_y=ally_offset[1],
            enemy_offset_x=enemy_offset[0],
            enemy_offset_y=enemy_offset[1],
            flash_color=flash_color,
            se_id=se_id,
            flash_scope=flash_scope,
        )

    @property
    def cell_size(self) -> int:
        return SPELL_EFFECT_IMAGE_CELL_SIZES[self.image_id]

    @property
    def total_frames(self) -> int:
        if self.kind == BLOOD_SUCK_EFFECT_KIND:
            return BLOOD_SUCK_EFFECT_FRAME_COUNT
        return self.frame_count * self.frames_per_pattern

    @property
    def screen_flash(self) -> SpellScreenFlash | None:
        if self.flash_scope != FLASH_SCOPE_SCREEN or self.flash_color is None:
            return None
        return SpellScreenFlash(
            self.flash_color, max(0, self.total_frames - SPELL_RESULT_OVERLAP_FRAME_COUNT),
        )

    def pattern_index_at(self, elapsed_frame: int) -> int | None:
        if isinstance(elapsed_frame, bool) or not isinstance(elapsed_frame, int):
            raise TypeError("elapsed_frame must be an integer")
        if elapsed_frame < 0:
            raise ValueError("elapsed_frame must not be negative")
        if self.image_id is None or elapsed_frame >= self.total_frames:
            return None
        return min(elapsed_frame // self.frames_per_pattern, self.frame_count - 1)

    def source_position_at(self, elapsed_frame: int) -> tuple[int, int] | None:
        pattern = self.pattern_index_at(elapsed_frame)
        if pattern is None:
            return None
        return pattern * self.cell_size, self.row * self.cell_size

    def offset_for(self, target_side: str) -> tuple[int, int]:
        if target_side == "ally":
            return self.ally_offset_x, self.ally_offset_y
        if target_side == "enemy":
            return self.enemy_offset_x, self.enemy_offset_y
        raise ValueError("target_side must be 'ally' or 'enemy'")

    def to_runtime_record(self) -> dict[str, object]:
        record: dict[str, object] = {"kind": self.kind}
        if self.image_id is not None:
            record.update(
                image_id=self.image_id,
                row=self.row,
                frame_count=self.frame_count,
                frames_per_pattern=self.frames_per_pattern,
                offset={
                    "ally": [self.ally_offset_x, self.ally_offset_y],
                    "enemy": [self.enemy_offset_x, self.enemy_offset_y],
                },
            )
        record.update(flash_color=self.flash_color, se_id=self.se_id)
        if self.flash_scope != FLASH_SCOPE_TARGET:
            record["flash_scope"] = self.flash_scope
        return record

    def to_source_record(self) -> dict[str, object]:
        return {"spell_key": self.spell_key, **self.to_runtime_record()}


class SpellEffectPlayer:
    """Own the mutable timeline for one spell effect invocation."""

    def __init__(
        self,
        definition: SpellEffectDefinition,
        *,
        anchor_x: int,
        anchor_y: int,
        target_side: str = "enemy",
        screen_flash_enabled: bool = True,
        caster_anchor: tuple[int, int] | None = None,
    ) -> None:
        if not isinstance(definition, SpellEffectDefinition):
            raise TypeError("definition must be a SpellEffectDefinition")
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (anchor_x, anchor_y)
        ):
            raise TypeError("effect anchor must contain integers")
        if target_side not in ("ally", "enemy"):
            raise ValueError("target_side must be 'ally' or 'enemy'")
        self.definition = definition
        self.anchor_x = anchor_x
        self.anchor_y = anchor_y
        self.target_side = target_side
        self.caster_anchor = caster_anchor
        self.screen_flash = definition.screen_flash if screen_flash_enabled else None
        self.elapsed_frame = 0
        self.completed = False
        self._start_sound_pending = True

    @property
    def playback_frames(self) -> int:
        if self.screen_flash is None:
            return self.definition.total_frames
        return max(self.definition.total_frames, self.screen_flash.end_frame)

    @property
    def pattern_index(self) -> int | None:
        return self.definition.pattern_index_at(self.elapsed_frame)

    @property
    def source_position(self) -> tuple[int, int] | None:
        return self.definition.source_position_at(self.elapsed_frame)

    @property
    def center(self) -> tuple[int, int]:
        offset_x, offset_y = self.definition.offset_for(self.target_side)
        return (
            self.anchor_x + offset_x,
            self.anchor_y + offset_y,
        )

    @property
    def flash_base_rate(self) -> float:
        if self.definition.flash_color is None or self.completed:
            return 1.0
        if self.definition.total_frames <= 1:
            return 1.0
        progress = self.elapsed_frame / (self.definition.total_frames - 1)
        return 0.6 + math.cos(math.tau * progress) * 0.4

    def take_start_sound(self) -> str | None:
        if not self._start_sound_pending:
            return None
        self._start_sound_pending = False
        return self.definition.se_id

    def update(self) -> None:
        if self.completed:
            return
        self.elapsed_frame += 1
        if self.elapsed_frame >= self.playback_frames:
            self.completed = True

    def restart(self) -> None:
        self.elapsed_frame = 0
        self.completed = False
        self._start_sound_pending = True


def load_spell_effects(path: Path) -> Mapping[str, SpellEffectDefinition]:
    """Load the compiled runtime catalog indexed by stable spell key."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SpellEffectDataError(
            f"呪文エフェクト生成物を読み込めません: {path}: {error}"
        ) from error
    if not isinstance(document, dict):
        raise SpellEffectDataError("spell effect root must be an object")
    format_version = document.get("format_version")
    if (
        isinstance(format_version, bool)
        or format_version not in SUPPORTED_SPELL_EFFECT_FORMAT_VERSIONS
    ):
        raise SpellEffectDataError(
            f"unsupported spell effect format_version: "
            f"{document.get('format_version')}"
        )
    records = document.get("effects")
    if not isinstance(records, dict):
        raise SpellEffectDataError("compiled spell effects must be an object")

    definitions: dict[str, SpellEffectDefinition] = {}
    for spell_key, record in records.items():
        if not isinstance(spell_key, str):
            raise SpellEffectDataError("compiled spell effect key must be a string")
        definitions[spell_key] = SpellEffectDefinition.from_record(spell_key, record)
    return MappingProxyType(definitions)


__all__ = [
    "BLOOD_SUCK_EFFECT_KIND",
    "DRAIN_FLIGHT_FRAME_COUNT",
    "DRAIN_FLIGHT_FRAMES_PER_PATTERN",
    "DRAIN_FLIGHT_PATTERNS",
    "FLASH_SCOPE_SCREEN",
    "FLASH_SCOPE_TARGET",
    "MAX_EFFECT_OFFSET",
    "MAX_FRAMES_PER_PATTERN",
    "MIN_EFFECT_OFFSET",
    "MIN_FRAMES_PER_PATTERN",
    "SPELL_EFFECT_FORMAT_VERSION",
    "SUPPORTED_SPELL_EFFECT_FORMAT_VERSIONS",
    "SPELL_EFFECT_IMAGE_CELL_SIZES",
    "SPELL_EFFECT_KIND",
    "SPELL_RESULT_OVERLAP_FRAME_COUNT",
    "SpellEffectDataError",
    "SpellEffectDefinition",
    "SpellEffectPlayer",
    "SpellScreenFlash",
    "load_spell_effects",
]
