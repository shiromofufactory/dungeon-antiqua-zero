"""Skill identity data independent of UI and Pyxel."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

if __package__ == "":
    from localization import Localizer
else:
    from .localization import Localizer


class SkillDataError(ValueError):
    """Raised when a skill record cannot be interpreted safely."""


@dataclass(frozen=True)
class Skill:
    """Minimal skill model with its current lookup key and localized names."""

    key: str
    names: Mapping[str, str]

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> Skill:
        """Validate and normalize the identity portion of a skill record."""

        if not isinstance(record, Mapping):
            raise SkillDataError("skill must be an object")

        key = record.get("name_en")
        if not isinstance(key, str) or not key:
            raise SkillDataError("skill.name_en must be a non-empty string")

        names: dict[str, str] = {}
        for field, value in record.items():
            if not field.startswith("name_"):
                continue
            if not isinstance(value, str):
                raise SkillDataError(f"skill.{field} must be a string")
            names[field] = value
        if not any(names.values()):
            raise SkillDataError("skill must have a non-empty localized name")

        return cls(key=key, names=MappingProxyType(names))

    def localized_name(self, localizer: Localizer) -> str:
        """Return the skill name normalized for the selected language."""

        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        try:
            name = localizer.text(self.names, "name")
        except TypeError as error:
            raise SkillDataError("localized skill name must be a string") from error
        if not name:
            raise SkillDataError(f"localized skill name is missing: {self.key}")
        return name
