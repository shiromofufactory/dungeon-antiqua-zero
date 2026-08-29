"""Player-character identity and member state independent of UI and Pyxel."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, TypeVar

if __package__ == "":
    from localization import Localizer
    from text_catalog import TextCatalog
else:
    from .localization import Localizer
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


@dataclass(frozen=True)
class CharacterDefinition:
    """Immutable identity data loaded from one ``characters.json`` record."""

    names: Mapping[str, object]
    race: Race
    gender: Gender

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> CharacterDefinition:
        """Validate and normalize the identity portion of a character record."""

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
        return cls(MappingProxyType(names), race, gender)

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

    def __post_init__(self) -> None:
        if not isinstance(self.definition, CharacterDefinition):
            raise TypeError("definition must be a CharacterDefinition")

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> Member:
        """Create the initial member state from a character data record."""

        return cls(CharacterDefinition.from_record(record))

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
