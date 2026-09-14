"""Surprise-attack rules independent of Pyxel presentation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


SURPRISE_ROLL_MAX = 31
VIGILANCE_SKILL_KEY = "Vigilance"


@dataclass(frozen=True)
class SurpriseRoll:
    """One resolved surprise draw before Vigilance is applied."""

    threshold: int
    roll: int

    @property
    def triggered(self) -> bool:
        return self.threshold > self.roll


def surprise_threshold(
    party_agilities: Sequence[int],
    enemy_agilities: Sequence[int],
) -> int:
    """Return ``max((-D) // 2, 0) + 1`` without float rounding.

    ``D`` is the party's mean agility minus the enemies' mean agility.
    Keeping both means as an exact fraction preserves Python floor division
    when either mean is non-integral.
    """

    _validate_agilities(party_agilities, "party")
    _validate_agilities(enemy_agilities, "enemy")
    party_count = len(party_agilities)
    enemy_count = len(enemy_agilities)
    disadvantage_numerator = (
        sum(enemy_agilities) * party_count
        - sum(party_agilities) * enemy_count
    )
    if disadvantage_numerator <= 0:
        return 1
    return (
        disadvantage_numerator // (2 * party_count * enemy_count)
        + 1
    )


def resolve_surprise_roll(
    party_agilities: Sequence[int],
    enemy_agilities: Sequence[int],
    roll: int,
) -> SurpriseRoll:
    """Resolve one inclusive 0..31 draw against the surprise threshold."""

    if isinstance(roll, bool) or not isinstance(roll, int):
        raise TypeError("surprise roll must be an integer")
    if not 0 <= roll <= SURPRISE_ROLL_MAX:
        raise ValueError(
            f"surprise roll must be from 0 to {SURPRISE_ROLL_MAX}"
        )
    return SurpriseRoll(
        surprise_threshold(party_agilities, enemy_agilities),
        roll,
    )


def _validate_agilities(agilities: Sequence[int], label: str) -> None:
    if not agilities:
        raise ValueError(f"{label} agility list must not be empty")
    if not all(
        isinstance(agility, int)
        and not isinstance(agility, bool)
        and agility >= 0
        for agility in agilities
    ):
        raise ValueError(f"{label} agilities must be non-negative integers")


__all__ = [
    "SURPRISE_ROLL_MAX",
    "SurpriseRoll",
    "VIGILANCE_SKILL_KEY",
    "resolve_surprise_roll",
    "surprise_threshold",
]
