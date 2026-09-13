"""Physical-attack calculations shared by battle scenes and mocks."""

from __future__ import annotations

from dataclasses import dataclass

if __package__ == "":
    from item import AdditionalEffect
else:
    from .item import AdditionalEffect


DEFENDING_HIT_VALUE_THRESHOLD = 25
DA2_CRITICAL_RATE_UNIT = 0.1
DA2_MEMBER_STATUS_BASE_RATE = 12
DA2_MONSTER_STATUS_BASE_RATE = 30
DA2_MEMBER_DEATH_BASE_RATE = 6
DA2_MONSTER_DEATH_BASE_RATE = 10

PHYSICAL_STATUS_EFFECTS = frozenset(
    (
        AdditionalEffect.SLEEP,
        AdditionalEffect.DEATH,
        AdditionalEffect.STUN,
        AdditionalEffect.POISON,
        AdditionalEffect.PARALIZE,
        AdditionalEffect.DEFENSE_DOWN,
    )
)


@dataclass(frozen=True)
class PhysicalAttackResult:
    """One DA2-compatible basic physical-attack result."""

    hit: bool
    damage: int
    adjusted_hit: float
    hit_value: float
    critical: bool = False
    critical_rate: float = 0.0


@dataclass(frozen=True)
class PhysicalAdditionalEffectResult:
    """One DA2-compatible additional-effect check after a physical hit."""

    effect: AdditionalEffect
    success: bool
    activation_points: int
    success_rate: float


def _nonnegative_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def member_physical_attack(
    weapon_attack: int,
    strength: int,
    weapon_level: int,
    internal_level: int,
) -> int:
    """Return a member's physical attack from their adjusted weapon value."""

    weapon_attack = _nonnegative_integer(weapon_attack, "weapon_attack")
    strength = _nonnegative_integer(strength, "strength")
    weapon_level = _nonnegative_integer(weapon_level, "weapon_level")
    internal_level = _nonnegative_integer(internal_level, "internal_level")
    return (
        weapon_attack
        * strength
        * (175 + weapon_level * 25 + internal_level)
        // 1250
    )


def resolve_physical_attack(
    *,
    attack: int,
    hit: int,
    agility: int,
    target_defense: int,
    target_evasion: int,
    hit_roll: int,
    target_defending: bool = False,
    target_unable_to_evade: bool = False,
    target_incapacitated: bool = False,
    attacker_hidden: bool = False,
    hit_value_bonus: int = 0,
    attacker_has_power_hit: bool = False,
    weapon_has_power_hit: bool = False,
    critical_rate_scale: float = 1.0,
    critical_roll: int | None = None,
) -> PhysicalAttackResult:
    """Resolve a physical attack, including DA2's defend-command effect."""

    attack = _nonnegative_integer(attack, "attack")
    hit = _nonnegative_integer(hit, "hit")
    agility = _nonnegative_integer(agility, "agility")
    target_defense = _nonnegative_integer(target_defense, "target_defense")
    target_evasion = _nonnegative_integer(target_evasion, "target_evasion")
    hit_roll = _nonnegative_integer(hit_roll, "hit_roll")
    hit_value_bonus = _nonnegative_integer(hit_value_bonus, "hit_value_bonus")
    if hit_roll > 99:
        raise ValueError("hit_roll must be from 0 to 99")
    if critical_roll is not None:
        critical_roll = _nonnegative_integer(critical_roll, "critical_roll")
        if critical_roll > 99:
            raise ValueError("critical_roll must be from 0 to 99")
    if not isinstance(target_defending, bool):
        raise TypeError("target_defending must be a boolean")
    if not isinstance(target_unable_to_evade, bool):
        raise TypeError("target_unable_to_evade must be a boolean")
    if not isinstance(target_incapacitated, bool):
        raise TypeError("target_incapacitated must be a boolean")
    if not isinstance(attacker_hidden, bool):
        raise TypeError("attacker_hidden must be a boolean")
    if not isinstance(attacker_has_power_hit, bool):
        raise TypeError("attacker_has_power_hit must be a boolean")
    if not isinstance(weapon_has_power_hit, bool):
        raise TypeError("weapon_has_power_hit must be a boolean")
    if isinstance(critical_rate_scale, bool) or not isinstance(
        critical_rate_scale,
        (int, float),
    ):
        raise TypeError("critical_rate_scale must be a number")
    if critical_rate_scale <= 0:
        raise ValueError("critical_rate_scale must be positive")

    adjusted_hit = float(hit)
    if agility > 20:
        adjusted_hit *= 1 + (agility - 20) / 20
    elif agility < 10:
        adjusted_hit *= 1 + (agility - 10) / 20

    has_ambush_advantage = target_incapacitated or attacker_hidden
    if has_ambush_advantage:
        # DA2 uses the same +100 accuracy, evasion bypass, and critical-rate
        # unit for an incapacitated target and an attack from hiding.
        adjusted_hit += 100
        hit_value = adjusted_hit - hit_roll + hit_value_bonus
    elif target_unable_to_evade:
        # DA2's 「まっぷたつ」 vulnerability ignores evasion and guarantees
        # at least one point of hit value after the 0-99 roll.
        hit_value = max(adjusted_hit, 100) - hit_roll + hit_value_bonus
    else:
        hit_value = (
            adjusted_hit * (100 - target_evasion) / 100
            - hit_roll
            + hit_value_bonus
        )
    if hit_value < 0:
        return PhysicalAttackResult(
            hit=False,
            damage=0,
            adjusted_hit=adjusted_hit,
            hit_value=hit_value,
        )

    critical_rate_units = (
        int(has_ambush_advantage)
        + int(attacker_has_power_hit)
        + int(weapon_has_power_hit)
    )
    critical_rate = (
        critical_rate_units
        * DA2_CRITICAL_RATE_UNIT
        * critical_rate_scale
        * max(adjusted_hit, 100)
    )
    critical = critical_roll is not None and critical_rate > critical_roll

    if target_defending and hit_value < DEFENDING_HIT_VALUE_THRESHOLD:
        return PhysicalAttackResult(
            hit=False,
            damage=0,
            adjusted_hit=adjusted_hit,
            hit_value=hit_value,
            critical=critical,
            critical_rate=critical_rate,
        )

    damage_factor = 0.8 + hit_value / 250
    reduced_attack = (
        attack * 2 if critical else max(attack - target_defense, 1)
    )
    defense_cut_rate = target_defense / 100
    damage = int(
        reduced_attack * damage_factor * (1 - defense_cut_rate) + 0.99
    )
    if target_defending:
        damage //= 2
    return PhysicalAttackResult(
        hit=not target_defending or damage > 0,
        damage=damage,
        adjusted_hit=adjusted_hit,
        hit_value=hit_value,
        critical=critical,
        critical_rate=critical_rate,
    )


def resolve_physical_additional_effect(
    *,
    effect: AdditionalEffect,
    adjusted_hit: float,
    effect_roll: int,
    target_is_member: bool,
    target_is_boss: bool = False,
    target_is_weak: bool = False,
    target_is_resistant: bool = False,
    target_defending: bool = False,
    critical: bool = False,
    attacker_hidden: bool = False,
    tribe_effective: bool = False,
    stacked_death: bool = False,
) -> PhysicalAdditionalEffectResult:
    """Resolve DA2's point gate and percentage roll for one hit effect.

    ZERO intentionally gives STUN the ordinary non-death status calculation,
    rather than DA2's special Pinshot percentages.  Like DA2, PARALIZE never
    affects a monster target.
    """

    if not isinstance(effect, AdditionalEffect):
        raise TypeError("effect must be an AdditionalEffect")
    if effect not in PHYSICAL_STATUS_EFFECTS:
        raise ValueError("effect is not a supported physical status effect")
    if isinstance(adjusted_hit, bool) or not isinstance(
        adjusted_hit,
        (int, float),
    ):
        raise TypeError("adjusted_hit must be a number")
    if adjusted_hit < 0:
        raise ValueError("adjusted_hit must not be negative")
    effect_roll = _nonnegative_integer(effect_roll, "effect_roll")
    if effect_roll > 99:
        raise ValueError("effect_roll must be from 0 to 99")
    for value, name in (
        (target_is_member, "target_is_member"),
        (target_is_boss, "target_is_boss"),
        (target_is_weak, "target_is_weak"),
        (target_is_resistant, "target_is_resistant"),
        (target_defending, "target_defending"),
        (critical, "critical"),
        (attacker_hidden, "attacker_hidden"),
        (tribe_effective, "tribe_effective"),
        (stacked_death, "stacked_death"),
    ):
        if not isinstance(value, bool):
            raise TypeError(f"{name} must be a boolean")

    if effect is AdditionalEffect.PARALIZE and not target_is_member:
        return PhysicalAdditionalEffectResult(effect, False, 0, 0.0)

    is_death = effect is AdditionalEffect.DEATH
    activation_points = 2 if not is_death or stacked_death else 1
    activation_points += int(critical)
    activation_points += int(tribe_effective)
    activation_points += int(attacker_hidden)
    if target_is_resistant:
        activation_points -= 1 if is_death else 2
    if target_is_boss:
        activation_points -= 3 if is_death else 1
    if target_defending:
        activation_points -= 2

    if critical or target_is_weak:
        success_rate = 100.0
    elif is_death:
        base_rate = (
            DA2_MEMBER_DEATH_BASE_RATE
            if target_is_member
            else DA2_MONSTER_DEATH_BASE_RATE
        )
        success_rate = max(base_rate * adjusted_hit / 100, base_rate)
    else:
        base_rate = (
            DA2_MEMBER_STATUS_BASE_RATE
            if target_is_member
            else DA2_MONSTER_STATUS_BASE_RATE
        )
        if (
            target_is_boss
            and effect is not AdditionalEffect.DEFENSE_DOWN
        ):
            base_rate /= 2
        success_rate = max(base_rate * adjusted_hit / 100, base_rate)

    return PhysicalAdditionalEffectResult(
        effect,
        activation_points > 0 and success_rate > effect_roll,
        activation_points,
        success_rate,
    )


__all__ = [
    "DA2_CRITICAL_RATE_UNIT",
    "DA2_MEMBER_DEATH_BASE_RATE",
    "DA2_MEMBER_STATUS_BASE_RATE",
    "DA2_MONSTER_DEATH_BASE_RATE",
    "DA2_MONSTER_STATUS_BASE_RATE",
    "DEFENDING_HIT_VALUE_THRESHOLD",
    "PHYSICAL_STATUS_EFFECTS",
    "PhysicalAdditionalEffectResult",
    "PhysicalAttackResult",
    "member_physical_attack",
    "resolve_physical_additional_effect",
    "resolve_physical_attack",
]
