"""Player-character identity and member state independent of UI and Pyxel."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, TypeVar

if __package__ == "":
    from localization import Localizer, format_number
    from text_catalog import TextCatalog
else:
    from .localization import Localizer, format_number
    from .text_catalog import TextCatalog


class MemberDataError(ValueError):
    """Raised when a character record cannot be converted into a member."""


class Race(StrEnum):
    """Stable race identifiers stored in character and save data."""

    FAIRY = "FAIRY"
    HUMAN = "HUMAN"
    DRAGONEWT = "DRAGONEWT"
    ELF = "ELF"
    DWARF = "DWARF"
    ROBOT = "ROBOT"


class Gender(StrEnum):
    """Stable gender identifiers stored in character and save data."""

    MALE = "MALE"
    FEMALE = "FEMALE"
    NONE = "NONE"


EnumValue = TypeVar("EnumValue", bound=StrEnum)

INITIAL_HP = 999
INITIAL_MAX_HP = 999
INITIAL_MP = 255
INITIAL_MAX_MP = 255


def _validate_ability_value(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MemberDataError(f"character.{name} must be an integer")
    if value < 0:
        raise MemberDataError(f"character.{name} must not be negative")
    return value


@dataclass(frozen=True)
class BaseAbilities:
    """Immutable ability values read directly from character master data."""

    strength: int
    agility: int
    magic: int


@dataclass(frozen=True)
class AdjustedAbilities:
    """Current ability values after applying runtime adjustments."""

    strength: int
    agility: int
    magic: int


@dataclass(frozen=True)
class CharacterDefinition:
    """Immutable master data loaded from one ``characters.json`` record."""

    names: Mapping[str, object]
    race: Race
    gender: Gender
    base_abilities: BaseAbilities

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> CharacterDefinition:
        """Validate and normalize one character master-data record."""

        if not isinstance(record, Mapping):
            raise MemberDataError("character must be an object")

        names: dict[str, str] = {}
        for key, value in record.items():
            if not key.startswith("name_"):
                continue
            if not isinstance(value, str):
                raise MemberDataError(f"character.{key} must be a string")
            names[key] = value
        if not names:
            raise MemberDataError("character must have at least one localized name")
        if not any(names.values()):
            raise MemberDataError("character must have a non-empty localized name")

        race = cls._enum_value(record, "race", Race)
        gender = cls._enum_value(record, "gender", Gender)
        base_abilities = BaseAbilities(
            strength=_validate_ability_value("base_str", record.get("base_str")),
            agility=_validate_ability_value("base_agi", record.get("base_agi")),
            magic=_validate_ability_value("base_mag", record.get("base_mag")),
        )
        return cls(MappingProxyType(names), race, gender, base_abilities)

    @staticmethod
    def _enum_value(
        record: Mapping[str, object],
        field: str,
        enum_type: type[EnumValue],
    ) -> EnumValue:
        value = record.get(field)
        if not isinstance(value, str):
            raise MemberDataError(f"character.{field} must be a string")
        try:
            return enum_type(value)
        except ValueError as error:
            raise MemberDataError(
                f"unsupported character.{field}: {value}"
            ) from error

    def localized_name(self, localizer: Localizer) -> str:
        """Return the character name for the selected language."""

        try:
            return localizer.text(self.names, "name")
        except TypeError as error:
            raise MemberDataError(
                "localized character name must be a string"
            ) from error


@dataclass(frozen=True)
class MemberDisplayIdentity:
    """Localized identity values ready for presentation by a screen."""

    name: str
    race: str
    gender: str


@dataclass
class Member:
    """Current player-character state backed by an immutable definition."""

    definition: CharacterDefinition
    hp: int = INITIAL_HP
    max_hp: int = INITIAL_MAX_HP
    mp: int = INITIAL_MP
    max_mp: int = INITIAL_MAX_MP
    poisoned: bool = False
    paralyzed: bool = False
    sleeping: int = 0
    confused: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.definition, CharacterDefinition):
            raise TypeError("definition must be a CharacterDefinition")
        for name in ("hp", "max_hp", "mp", "max_mp"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        if self.hp > self.max_hp:
            raise ValueError("hp must not exceed max_hp")
        if self.mp > self.max_mp:
            raise ValueError("mp must not exceed max_mp")
        for name in ("poisoned", "paralyzed"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean")
        for name in ("sleeping", "confused"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must not be negative")

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> Member:
        """Create the initial member state from a character data record."""

        return cls(CharacterDefinition.from_record(record))

    @property
    def adjusted_abilities(self) -> AdjustedAbilities:
        """Return current abilities without mutating their master-data base."""

        base = self.definition.base_abilities
        return AdjustedAbilities(
            strength=base.strength,
            agility=base.agility,
            magic=base.magic,
        )

    def status(
        self,
        localizer: Localizer,
        texts: TextCatalog,
        *,
        show_ok: bool = False,
        show_mhp: bool = True,
    ) -> str:
        """Return the localized condition or the healthy maximum-HP display."""

        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        if not isinstance(texts, TextCatalog):
            raise TypeError("texts must be a TextCatalog")
        if not isinstance(show_ok, bool):
            raise TypeError("show_ok must be a boolean")
        if not isinstance(show_mhp, bool):
            raise TypeError("show_mhp must be a boolean")

        text_key = None
        if self.hp <= 0:
            text_key = "status.dead"
        elif self.paralyzed:
            text_key = "status.paralyzed"
        elif self.sleeping:
            text_key = "status.sleeping"
        elif self.confused:
            text_key = "status.confused"
        elif self.poisoned:
            text_key = "status.poisoned"
        elif show_ok:
            text_key = "status.ok"

        if text_key is not None:
            value = texts.text(text_key, localizer)
            if not value:
                raise MemberDataError(
                    f"localized member text is missing: {text_key}"
                )
            return value
        if show_mhp:
            return format_number(self.max_hp)
        return ""

    def display_identity(
        self,
        localizer: Localizer,
        texts: TextCatalog,
    ) -> MemberDisplayIdentity:
        """Resolve name, race, and gender without retaining language state."""

        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        if not isinstance(texts, TextCatalog):
            raise TypeError("texts must be a TextCatalog")

        name = self.definition.localized_name(localizer)
        race_key = f"race.{self.definition.race.value}"
        gender_key = f"gender.{self.definition.gender.value}"
        race = texts.text(race_key, localizer)
        gender = texts.text(gender_key, localizer)
        required_text = (
            ("character.name", name),
            (race_key, race),
            (gender_key, gender),
        )
        for key, value in required_text:
            if not value:
                raise MemberDataError(f"localized member text is missing: {key}")

        return MemberDisplayIdentity(name=name, race=race, gender=gender)
