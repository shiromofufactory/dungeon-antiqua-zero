"""Spell master data, effect identity, and learning rules independent of UI."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

if __package__ == "":
    from localization import (
        LocalizedText,
        Localizer,
        format_number,
        format_text_template,
    )
    from member import Member, ProficiencyKind
    from resistance import ResistanceType, TOLERANCE_CHARACTER_MAP
else:
    from .localization import (
        LocalizedText,
        Localizer,
        format_number,
        format_text_template,
    )
    from .member import Member, ProficiencyKind
    from .resistance import ResistanceType, TOLERANCE_CHARACTER_MAP


class SpellDataError(ValueError):
    """Raised when a spell record cannot be interpreted safely."""


class SpellType(StrEnum):
    """Stable spell categories stored in spell master data."""

    MYSTIC = "mystic"
    SACRED = "sacred"
    NETHER = "nether"
    ITEM = "item"


class SpellAction(StrEnum):
    """Stable effect kinds stored by the spell master."""

    AGILITY_UP = "AGI_UP"
    BLOOD_SUCK = "BLOOD_SUCK"
    BREAK = "BREAK"
    CONFUSE = "CONFUSE"
    CURE = "CURE"
    CURSE = "CURSE"
    DAMAGE = "DAMAGE"
    FADE = "FADE"
    HASTE = "HASTE"
    HEAL = "HEAL"
    HEAVENGATE = "HEAVENGATE"
    IDENTIFY = "IDENTIFY"
    MAGIC_SHIELD = "MAGIC_SHIELD"
    MAGIC_UP = "MAG_UP"
    MANA = "MANA"
    MAX_HP_UP = "MHP_UP"
    MAX_MP_UP = "MMP_UP"
    NONE = "NONE"
    PROTECTION = "PROTECTION"
    PURGE = "PURGE"
    REVIVE = "REVIVE"
    SILENCE = "SILENCE"
    SLEEP = "SLEEP"
    SLOW = "SLOW"
    STRENGTH_UP = "STR_UP"
    TELEPORT = "TELEPORT"


SPELL_PROFICIENCY_BY_TYPE = MappingProxyType(
    {
        SpellType.MYSTIC: ProficiencyKind.MYSTIC,
        SpellType.SACRED: ProficiencyKind.SACRED,
        SpellType.NETHER: ProficiencyKind.NETHER,
    }
)
SPELL_TYPE_ICON_TAGS = MappingProxyType(
    {
        SpellType.MYSTIC: "%MYSTIC%",
        SpellType.SACRED: "%SACRED%",
        SpellType.NETHER: "%NETHER%",
    }
)


def _integer(record: Mapping[str, object], field: str, minimum: int) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SpellDataError(f"spell.{field} must be an integer")
    if value < minimum:
        raise SpellDataError(f"spell.{field} must be at least {minimum}")
    return value


def _flag(record: Mapping[str, object], field: str) -> bool:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value not in (0, 1):
        raise SpellDataError(f"spell.{field} must be 0 or 1")
    return bool(value)


@dataclass(frozen=True)
class Spell:
    """Immutable spell identity, effect metadata, and acquisition requirements."""

    key: str
    names: Mapping[str, str]
    type: SpellType
    level: int
    mp: int
    on_camp: bool
    on_battle: bool
    to_enemy: bool
    to_all: bool
    action: SpellAction
    attribute: ResistanceType | None
    intensity: int
    rate: int
    descriptions: Mapping[str, tuple[str, ...]]

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> Spell:
        """Validate and normalize one spell master-data record."""

        if not isinstance(record, Mapping):
            raise SpellDataError("spell must be an object")

        key = record.get("name_en")
        if not isinstance(key, str) or not key:
            raise SpellDataError("spell.name_en must be a non-empty string")

        names: dict[str, str] = {}
        descriptions: dict[str, tuple[str, ...]] = {}
        for field, value in record.items():
            if field.startswith("name_"):
                if not isinstance(value, str):
                    raise SpellDataError(f"spell.{field} must be a string")
                names[field] = value
            elif field.startswith("description_"):
                if not isinstance(value, list) or not all(
                    isinstance(line, str) for line in value
                ):
                    raise SpellDataError(
                        f"spell.{field} must be an array of strings"
                    )
                descriptions[field] = tuple(value)
        if not any(names.values()):
            raise SpellDataError("spell must have a non-empty localized name")

        type_value = record.get("type")
        if not isinstance(type_value, str):
            raise SpellDataError("spell.type must be a string")
        try:
            spell_type = SpellType(type_value)
        except ValueError as error:
            raise SpellDataError(f"unsupported spell.type: {type_value}") from error

        action_value = record.get("action")
        if not isinstance(action_value, str):
            raise SpellDataError("spell.action must be a string")
        try:
            action = SpellAction(action_value)
        except ValueError as error:
            raise SpellDataError(
                f"unsupported spell.action: {action_value}"
            ) from error

        level = _integer(record, "lv", 0)
        if level > 9:
            raise SpellDataError("spell.lv must be from 0 to 9")

        attribute_value = record.get("attr")
        if not isinstance(attribute_value, str):
            raise SpellDataError("spell.attr must be a string")
        attribute = None
        if attribute_value:
            if len(attribute_value) != 1:
                raise SpellDataError("spell.attr must be empty or one attribute code")
            attribute = TOLERANCE_CHARACTER_MAP.get(attribute_value)
            if attribute is None:
                raise SpellDataError(
                    f"unsupported spell.attr: {attribute_value}"
                )

        return cls(
            key=key,
            names=MappingProxyType(names),
            type=spell_type,
            level=level,
            mp=_integer(record, "mp", 0),
            on_camp=_flag(record, "on_camp"),
            on_battle=_flag(record, "on_battle"),
            to_enemy=_flag(record, "to_enemy"),
            to_all=_flag(record, "to_all"),
            action=action,
            attribute=attribute,
            intensity=_integer(record, "intensity", 0),
            rate=_integer(record, "rate", 0),
            descriptions=MappingProxyType(descriptions),
        )

    def localized_name(self, localizer: Localizer) -> str:
        """Return the spell name normalized for the selected language."""

        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        try:
            name = localizer.text(self.names, "name")
        except TypeError as error:
            raise SpellDataError("localized spell name must be a string") from error
        if not name:
            raise SpellDataError(f"localized spell name is missing: {self.key}")
        return name

    def localized_display_name(self, localizer: Localizer) -> str:
        """Return the standard spell name prefixed by its school icon."""

        name = self.localized_name(localizer)
        icon = SPELL_TYPE_ICON_TAGS.get(self.type, "")
        if not icon:
            return name
        return LocalizedText(
            f"{icon}{name}",
            prefers_wide_font=name.prefers_wide_font,
            narrow_spans=tuple(
                (start + len(icon), end + len(icon))
                for start, end in name.narrow_spans
            ),
        )

    def localized_description(self, localizer: Localizer) -> tuple[str, ...]:
        """Return localized description lines with the intensity substituted."""

        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        line_count = max((len(lines) for lines in self.descriptions.values()), default=0)
        result: list[str] = []
        intensity = format_number(self.intensity)
        for index in range(line_count):
            record = {
                field: format_text_template(
                    lines[index],
                    {"INTENSITY": intensity},
                )
                for field, lines in self.descriptions.items()
                if index < len(lines)
            }
            line = localizer.text(record, "description")
            if line:
                result.append(line)
        return tuple(result)

    def is_learned_by(
        self,
        member: Member,
        event_spell_keys: Collection[str] = (),
    ) -> bool:
        """Apply ZERO's level and event-spell acquisition rules."""

        if not isinstance(member, Member):
            raise TypeError("member must be a Member")
        if isinstance(event_spell_keys, (str, bytes)) or not all(
            isinstance(key, str) for key in event_spell_keys
        ):
            raise TypeError("event_spell_keys must contain strings")
        if self.type is SpellType.ITEM:
            return False
        if self.level == 0:
            return self.key in event_spell_keys
        proficiency_kind = SPELL_PROFICIENCY_BY_TYPE[self.type]
        return self.level <= member.proficiency(proficiency_kind).level


__all__ = [
    "SPELL_PROFICIENCY_BY_TYPE",
    "SPELL_TYPE_ICON_TAGS",
    "Spell",
    "SpellAction",
    "SpellDataError",
    "SpellType",
]
