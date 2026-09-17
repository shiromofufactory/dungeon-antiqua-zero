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
DA2_POISON_DAMAGE_DENOMINATOR = 16
DA2_BATTLE_HEALING_DENOMINATOR = 16


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


@dataclass(frozen=True)
class StatusSpellResult:
    """One DA2-style status-spell success check and elemental relation."""

    success: bool
    success_rate: float
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


def spell_cast_delay(*, spell_level: int, reduced_wait: bool = False) -> int:
    """Return the post-action gauge cost for the caster's spell school."""

    spell_level = _nonnegative_integer(spell_level, "spell_level")
    return 17 - spell_level - (8 if reduced_wait else 0)


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


def resolve_status_spell(
    *,
    spell_modifier: float,
    rate: int,
    target_spell_defense: int,
    attribute: ResistanceType | None,
    target_weaknesses: frozenset[ResistanceType],
    target_resistances: frozenset[ResistanceType],
    success_roll: int,
) -> StatusSpellResult:
    """Resolve DA2's status success check using ZERO's spell modifier.

    ``success_rate`` uses DA2's twenty-step scale: each point corresponds to
    five percentage points while a value above twenty is an automatic success.
    An explicit resistance still makes the effect fail before that roll.
    """

    if isinstance(spell_modifier, bool) or not isinstance(
        spell_modifier,
        (int, float),
    ):
        raise TypeError("spell_modifier must be a number")
    if spell_modifier < 0:
        raise ValueError("spell_modifier must not be negative")
    rate = _nonnegative_integer(rate, "rate")
    target_spell_defense = _nonnegative_integer(
        target_spell_defense,
        "target_spell_defense",
    )
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
    success_roll = _nonnegative_integer(success_roll, "success_roll")
    if success_roll > 19:
        raise ValueError("success_roll must be from 0 to 19")

    if attribute is not None and attribute in target_resistances:
        return StatusSpellResult(False, 0.0, SpellAffinity.RESIST)

    affinity = SpellAffinity.NORMAL
    success_rate = max(
        1.0,
        (spell_modifier - target_spell_defense) / 2 + rate,
    )
    if attribute is not None and attribute in target_weaknesses:
        affinity = SpellAffinity.WEAK
        success_rate += 10
    return StatusSpellResult(success_rate > success_roll, success_rate, affinity)


def poison_tick_damage(*, max_hp: int, weak_to_poison: bool = False) -> int:
    """Return DA2's rounded-up poison damage for one acting combatant."""

    max_hp = _nonnegative_integer(max_hp, "max_hp")
    if max_hp <= 0:
        raise ValueError("max_hp must be positive")
    if not isinstance(weak_to_poison, bool):
        raise TypeError("weak_to_poison must be a boolean")
    rate = 2 if weak_to_poison else 1
    return (
        max_hp * rate + DA2_POISON_DAMAGE_DENOMINATOR - 1
    ) // DA2_POISON_DAMAGE_DENOMINATOR


def battle_healing_amount(*, max_hp: int, healing: int) -> int:
    """Return the signed HP change for battle recovery equipment and skills."""

    max_hp = _nonnegative_integer(max_hp, "max_hp")
    if max_hp <= 0:
        raise ValueError("max_hp must be positive")
    if isinstance(healing, bool) or not isinstance(healing, int):
        raise TypeError("healing must be an integer")
    if healing == 0:
        return 0
    magnitude = (
        max_hp * abs(healing) + DA2_BATTLE_HEALING_DENOMINATOR - 1
    ) // DA2_BATTLE_HEALING_DENOMINATOR
    return magnitude if healing > 0 else -magnitude


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
    "DA2_BATTLE_HEALING_DENOMINATOR",
    "DA2_HEAL_RATE_RANGE",
    "DA2_MINIMUM_HEAL_RATE",
    "DA2_POISON_DAMAGE_DENOMINATOR",
    "HealingResult",
    "SPELL_DAMAGE_MINIMUM_RATE",
    "SPELL_DAMAGE_RATE_RANGE",
    "SpellAffinity",
    "SpellDamageResult",
    "StatusSpellResult",
    "battle_healing_amount",
    "member_spell_ability",
    "member_spell_modifier",
    "poison_tick_damage",
    "resolve_healing",
    "resolve_spell_damage",
    "resolve_status_spell",
    "spell_cast_delay",
]
