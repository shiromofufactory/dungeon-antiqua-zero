"""Magic-effect calculations shared by battle scenes and tests."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

if __package__ == "":
    from resistance import ResistanceType
else:
    from .resistance import ResistanceType


DA2_DEFAULT_ITEM_SPELL_ABILITY = 20
DA2_MINIMUM_HEAL_RATE = 0.8
DA2_HEAL_RATE_RANGE = 0.4
SPELL_DAMAGE_MINIMUM_RATE = 0.20
SPELL_DAMAGE_RATE_RANGE = 0.05


class SpellAffinity(StrEnum):
    """The DA2-compatible elemental relation shown with a damage result."""

    NORMAL = "normal"
    WEAK = "weak"
    RESIST = "resist"


@dataclass(frozen=True)
class HealingResult:
    """One DA2-compatible HEAL result before it mutates its target."""

    amount: int
    cures_ailments: bool = False


@dataclass(frozen=True)
class SpellDamageResult:
    """One resolved spell-damage value and its elemental relation."""

    damage: int
    affinity: SpellAffinity = SpellAffinity.NORMAL


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


def member_spell_modifier(
    *,
    magic: int,
    spell_level: int,
    internal_level: int,
) -> float:
    """Return the character-specific modifier shared by offensive magic.

    Status spells will use the same value when their effects are implemented.
    ``spell_level`` is the member's current proficiency in the spell school.
    """

    magic = _nonnegative_integer(magic, "magic")
    spell_level = _nonnegative_integer(spell_level, "spell_level")
    internal_level = _nonnegative_integer(internal_level, "internal_level")
    return magic * (7 + spell_level + internal_level / 25) / 16


def resolve_spell_damage(
    *,
    intensity: int,
    spell_modifier: float,
    target_spell_defense: int,
    attribute: ResistanceType | None,
    target_weaknesses: frozenset[ResistanceType],
    target_resistances: frozenset[ResistanceType],
    target_is_shadow: bool = False,
    random_factor: float,
) -> SpellDamageResult:
    """Resolve DAMAGE magic with ZERO's formula and DA2's affinities."""

    intensity = _nonnegative_integer(intensity, "intensity")
    if isinstance(spell_modifier, bool) or not isinstance(
        spell_modifier,
        (int, float),
    ):
        raise TypeError("spell_modifier must be a number")
    if spell_modifier < 0:
        raise ValueError("spell_modifier must not be negative")
    target_spell_defense = _nonnegative_integer(
        target_spell_defense,
        "target_spell_defense",
    )
    if target_spell_defense > 100:
        raise ValueError("target_spell_defense must not exceed 100")
    if attribute is not None and not isinstance(attribute, ResistanceType):
        raise TypeError("attribute must be a ResistanceType or None")
    if not isinstance(target_weaknesses, frozenset) or not all(
        isinstance(value, ResistanceType) for value in target_weaknesses
    ):
        raise TypeError("target_weaknesses must be a ResistanceType frozenset")
    if not isinstance(target_resistances, frozenset) or not all(
        isinstance(value, ResistanceType) for value in target_resistances
    ):
        raise TypeError("target_resistances must be a ResistanceType frozenset")
    if not isinstance(target_is_shadow, bool):
        raise TypeError("target_is_shadow must be a boolean")
    if isinstance(random_factor, bool) or not isinstance(
        random_factor,
        (int, float),
    ):
        raise TypeError("random_factor must be a number")
    if not 0 <= random_factor <= 1:
        raise ValueError("random_factor must be from 0.0 to 1.0")

    affinity = SpellAffinity.NORMAL
    multiplier = 1.0
    if attribute is not None and attribute in target_resistances:
        affinity = SpellAffinity.RESIST
        multiplier = 0.25
    elif attribute is not None and attribute in target_weaknesses:
        affinity = SpellAffinity.WEAK
        multiplier = 4.0
    elif attribute is ResistanceType.DEATH and target_is_shadow:
        affinity = SpellAffinity.WEAK
        multiplier = 2.0

    random_rate = SPELL_DAMAGE_MINIMUM_RATE + (
        random_factor * SPELL_DAMAGE_RATE_RANGE
    )
    damage = int(
        intensity
        * spell_modifier
        * (100 - target_spell_defense)
        / 100
        * random_rate
        * multiplier
    )
    return SpellDamageResult(damage, affinity)


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
    "SPELL_DAMAGE_MINIMUM_RATE",
    "SPELL_DAMAGE_RATE_RANGE",
    "SpellAffinity",
    "SpellDamageResult",
    "member_spell_ability",
    "member_spell_modifier",
    "resolve_healing",
    "resolve_spell_damage",
]
