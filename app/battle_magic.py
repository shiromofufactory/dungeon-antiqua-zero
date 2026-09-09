"""Magic-effect calculations shared by battle scenes and tests."""

from __future__ import annotations

from dataclasses import dataclass


DA2_DEFAULT_ITEM_SPELL_ABILITY = 20
DA2_MINIMUM_HEAL_RATE = 0.8
DA2_HEAL_RATE_RANGE = 0.4


@dataclass(frozen=True)
class HealingResult:
    """One DA2-compatible HEAL result before it mutates its target."""

    amount: int
    cures_ailments: bool = False


def _nonnegative_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def member_spell_ability(*, magic: int, internal_level: int) -> int:
    """Return DA2's level-adjusted spell ability using ZERO's magic stat."""

    magic = _nonnegative_integer(magic, "magic")
    internal_level = _nonnegative_integer(internal_level, "internal_level")
    return magic * (51 + internal_level) // 50


def resolve_healing(
    *,
    intensity: int,
    ability: int,
    current_hp: int,
    max_hp: int,
    random_factor: float,
) -> HealingResult:
    """Resolve DA2's HEAL amount, including its full-heal special case.

    ``random_factor`` is normalized to 0.0–1.0 so callers can inject a
    deterministic roll. The corresponding DA2 recovery multiplier is 0.8–1.2.
    """

    intensity = _nonnegative_integer(intensity, "intensity")
    ability = _nonnegative_integer(ability, "ability")
    current_hp = _nonnegative_integer(current_hp, "current_hp")
    max_hp = _nonnegative_integer(max_hp, "max_hp")
    if current_hp > max_hp:
        raise ValueError("current_hp must not exceed max_hp")
    if isinstance(random_factor, bool) or not isinstance(
        random_factor,
        (int, float),
    ):
        raise TypeError("random_factor must be a number")
    if not 0 <= random_factor <= 1:
        raise ValueError("random_factor must be from 0.0 to 1.0")

    if intensity == 0:
        return HealingResult(max_hp - current_hp, cures_ailments=True)

    rate = DA2_MINIMUM_HEAL_RATE + random_factor * DA2_HEAL_RATE_RANGE
    amount = int(intensity * ability / 10 * rate + 1)
    return HealingResult(amount)


__all__ = [
    "DA2_DEFAULT_ITEM_SPELL_ABILITY",
    "DA2_HEAL_RATE_RANGE",
    "DA2_MINIMUM_HEAL_RATE",
    "HealingResult",
    "member_spell_ability",
    "resolve_healing",
]
