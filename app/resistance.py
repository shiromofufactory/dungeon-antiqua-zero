"""Stable resistance types shared by items, members, and battle systems."""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType


class ResistanceType(StrEnum):
    """Stable resistance identifiers matching status-screen icon tags."""

    FIRE = "FIRE"
    FREEZE = "FREEZE"
    DARK = "DARK"
    SLEEP = "SLEEP"
    POISON = "POISON"
    PARALIZE = "PARALIZE"
    CONFUSE = "CONFUSE"
    SILENCE = "SILENCE"
    DEATH = "DEATH"
    STUN = "STUN"


TOLERANCE_CHARACTER_MAP = MappingProxyType(
    {
        "炎": ResistanceType.FIRE,
        "冷": ResistanceType.FREEZE,
        "闇": ResistanceType.DARK,
        "眠": ResistanceType.SLEEP,
        "毒": ResistanceType.POISON,
        "麻": ResistanceType.PARALIZE,
        "乱": ResistanceType.CONFUSE,
        "黙": ResistanceType.SILENCE,
        "死": ResistanceType.DEATH,
        "止": ResistanceType.STUN,
    }
)


def resistances_from_tolerance(text: str) -> frozenset[ResistanceType]:
    """Parse recognized one-character tolerance codes.

    Unknown characters are ignored so unrelated or future tolerance codes do
    not accidentally grant one of the nine currently defined resistances.
    """

    if not isinstance(text, str):
        raise TypeError("tolerance text must be a string")
    return frozenset(
        resistance
        for character in text
        if (resistance := TOLERANCE_CHARACTER_MAP.get(character)) is not None
    )
