"""Physical-attack calculations shared by battle scenes and mocks."""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, replace

if __package__ == "":
    from item import AdditionalEffect
    from monster import MonsterTribe
    from resistance import ResistanceType
else:
    from .item import AdditionalEffect
    from .monster import MonsterTribe
    from .resistance import ResistanceType


DEFENDING_HIT_VALUE_THRESHOLD = 25
DA2_CRITICAL_RATE_UNIT = 0.1
DA2_EFFECTIVE_HIT_VALUE_BONUS = 60
DA2_MEMBER_STATUS_BASE_RATE = 12
DA2_MONSTER_STATUS_BASE_RATE = 30
STUN_BASE_RATE = 20
DA2_MEMBER_DEATH_BASE_RATE = 6
DA2_MONSTER_DEATH_BASE_RATE = 10

PHYSICAL_EFFECT_RESISTANCE = {
    AdditionalEffect.SLEEP: ResistanceType.SLEEP,
    AdditionalEffect.CONFUSE: ResistanceType.CONFUSE,
    AdditionalEffect.DEATH: ResistanceType.DEATH,
    AdditionalEffect.STUN: ResistanceType.STUN,
    AdditionalEffect.POISON: ResistanceType.POISON,
    AdditionalEffect.PARALIZE: ResistanceType.PARALIZE,
    AdditionalEffect.SILENCE: ResistanceType.SILENCE,
    AdditionalEffect.DEFENSE_DOWN: None,
}
PHYSICAL_STATUS_EFFECTS = frozenset(PHYSICAL_EFFECT_RESISTANCE)


@dataclass(frozen=True)
class PhysicalAttackResult:
    """One DA2-compatible basic physical-attack result."""

    hit: bool
    damage: int
    adjusted_hit: float
    hit_value: float
    critical: bool = False
    critical_rate: float = 0.0
    tribe_resisted: bool = False


@dataclass(frozen=True)
class PhysicalAdditionalEffectResult:
    """One DA2-compatible additional-effect check after a physical hit."""

    effect: AdditionalEffect
    success: bool
    activation_points: int
    success_rate: float


def drain_healing_amount(*, damage: int, hp: int, max_hp: int) -> int:
    """DA2 drains the resolved damage, including overkill, up to missing HP."""

    if damage < 0 or not 0 <= hp <= max_hp:
        raise ValueError("invalid drain damage or attacker HP")
    return min(damage, max_hp - hp) if hp > 0 else 0


def weapon_can_drain(
    effect: AdditionalEffect | None, target_resistances: Collection[ResistanceType],
) -> bool:
    """Dark resistance blocks a weapon's HP drain on a successful hit."""

    return effect is AdditionalEffect.DRAIN and ResistanceType.DARK not in target_resistances


def _nonnegative_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def physical_weapon_is_effective(
    *,
    effective_tribe: MonsterTribe | None,
    target_tribe: MonsterTribe | None,
    attribute: ResistanceType | None,
    target_weaknesses: Collection[ResistanceType],
    target_resistances: Collection[ResistanceType],
) -> bool:
    """Combine tribe and attribute effectiveness into one non-stacking bonus."""

    return (
        effective_tribe is not None and effective_tribe == target_tribe
    ) or (
        attribute is not None
        and attribute in target_weaknesses
        and attribute not in target_resistances
    )


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
    target_defense: int,
    target_evasion: int,
    hit_roll: int,
    target_defending: bool = False,
    target_unable_to_evade: bool = False,
    target_incapacitated: bool = False,
    attacker_hidden: bool = False,
    hit_value_bonus: int = 0,
    attacker_is_monster: bool = False,
    attacker_has_power_hit: bool = False,
    weapon_has_power_hit: bool = False,
    weapon_effective: bool = False,
    target_resists_tribe: bool = False,
    critical_rate_scale: float = 1.0,
    critical_roll: int | None = None,
) -> PhysicalAttackResult:
    """Resolve a physical attack, including DA2's defend-command effect."""

    attack = _nonnegative_integer(attack, "attack")
    hit = _nonnegative_integer(hit, "hit")
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
    if not isinstance(attacker_is_monster, bool):
        raise TypeError("attacker_is_monster must be a boolean")
    if not isinstance(attacker_has_power_hit, bool):
        raise TypeError("attacker_has_power_hit must be a boolean")
    if not isinstance(weapon_has_power_hit, bool):
        raise TypeError("weapon_has_power_hit must be a boolean")
    if not isinstance(weapon_effective, bool):
        raise TypeError("weapon_effective must be a boolean")
    if not isinstance(target_resists_tribe, bool):
        raise TypeError("target_resists_tribe must be a boolean")
    if isinstance(critical_rate_scale, bool) or not isinstance(
        critical_rate_scale,
        (int, float),
    ):
        raise TypeError("critical_rate_scale must be a number")
    if critical_rate_scale <= 0:
        raise ValueError("critical_rate_scale must be positive")

    adjusted_hit = float(hit)

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

    if weapon_effective:
        # DA2's tribe-effective weapon rule applies after the ordinary hit
        # check, then improves damage and the defend-command threshold.
        hit_value += DA2_EFFECTIVE_HIT_VALUE_BONUS

    critical_rate_units = (
        int(has_ambush_advantage)
        + int(attacker_has_power_hit)
        + int(weapon_has_power_hit)
    )
    critical_rate = (
        (1.0 if weapon_effective else critical_rate_units * DA2_CRITICAL_RATE_UNIT)
        * critical_rate_scale
        * max(adjusted_hit, 100)
    )
    if target_resists_tribe:
        critical_rate = 0.0
    critical = not target_resists_tribe and (
        weapon_effective or (critical_roll is not None and critical_rate > critical_roll)
    )

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
    critical_multiplier = 1.5 if attacker_is_monster else 2
    reduced_attack = (
        attack * critical_multiplier if critical else max(attack - target_defense, 1)
    )
    defense_cut_rate = target_defense / 100
    if target_resists_tribe:
        defense_cut_rate /= 2
    damage = int(
        reduced_attack * damage_factor * (1 - defense_cut_rate) + 0.99
    )
    if target_defending:
        damage //= 2
    if target_resists_tribe:
        damage //= 2
    return PhysicalAttackResult(
        hit=not target_defending or damage > 0,
        damage=damage,
        adjusted_hit=adjusted_hit,
        hit_value=hit_value,
        critical=critical,
        critical_rate=critical_rate,
        tribe_resisted=target_resists_tribe,
    )


def resolve_physical_additional_effect(
    *,
    effect: AdditionalEffect,
    adjusted_hit: float,
    effect_roll: int,
    target_is_member: bool,
    target_has_boss_resistance: bool = False,
    target_is_weak: bool = False,
    target_is_resistant: bool = False,
    target_defending: bool = False,
    critical: bool = False,
    attacker_hidden: bool = False,
    tribe_effective: bool = False,
    weapon_effective: bool = False,
    stacked_death: bool = False,
) -> PhysicalAdditionalEffectResult:
    """Resolve the point gate and percentage roll for one hit effect."""

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
        (target_has_boss_resistance, "target_has_boss_resistance"),
        (target_is_weak, "target_is_weak"),
        (target_is_resistant, "target_is_resistant"),
        (target_defending, "target_defending"),
        (critical, "critical"),
        (attacker_hidden, "attacker_hidden"),
        (tribe_effective, "tribe_effective"),
        (weapon_effective, "weapon_effective"),
        (stacked_death, "stacked_death"),
    ):
        if not isinstance(value, bool):
            raise TypeError(f"{name} must be a boolean")

    if effect is AdditionalEffect.PARALIZE and not target_is_member:
        return PhysicalAdditionalEffectResult(effect, False, 0, 0.0)

    is_death = effect is AdditionalEffect.DEATH
    activation_points = 2 if not is_death or stacked_death else 1
    activation_points += int(critical)
    activation_points += int(tribe_effective or weapon_effective)
    activation_points += int(attacker_hidden)
    if target_is_resistant:
        activation_points -= 1 if is_death else 2
    if target_has_boss_resistance:
        activation_points -= 3 if is_death else 1
    if target_defending:
        activation_points -= 2

    if effect is AdditionalEffect.STUN:
        base_rate = STUN_BASE_RATE
    elif is_death:
        base_rate = (
            DA2_MEMBER_DEATH_BASE_RATE
            if target_is_member
            else DA2_MONSTER_DEATH_BASE_RATE
        )
    else:
        base_rate = (
            DA2_MEMBER_STATUS_BASE_RATE
            if target_is_member
            else DA2_MONSTER_STATUS_BASE_RATE
        )
    if (
        target_has_boss_resistance
        and not is_death
        and effect is not AdditionalEffect.DEFENSE_DOWN
    ):
        base_rate /= 2
    if effect is not AdditionalEffect.STUN and (critical or target_is_weak):
        success_rate = 100.0
    else:
        success_rate = max(base_rate * adjusted_hit / 100, base_rate)

    return PhysicalAdditionalEffectResult(
        effect,
        activation_points > 0 and success_rate > effect_roll,
        activation_points,
        success_rate,
    )


def resolve_monster_attack_effects(
    effects: tuple[AdditionalEffect, ...],
    result: PhysicalAttackResult,
    *,
    roll_effect: Callable[[], int],
    target_is_member: bool,
    target_resistances: Collection[ResistanceType],
    target_weaknesses: Collection[ResistanceType] = (),
    target_defending: bool = False,
) -> tuple[AdditionalEffect, ...]:
    """Resolve one monster hit using a shared roll and DA2's status priorities."""

    if not result.hit and not (target_defending and result.hit_value >= 0):
        return ()
    candidates = tuple(effect for effect in effects if effect in PHYSICAL_STATUS_EFFECTS)
    if not candidates:
        return ()

    effect_roll = roll_effect()
    successful: list[AdditionalEffect] = []
    for effect in candidates:
        resistance = PHYSICAL_EFFECT_RESISTANCE[effect]
        resolution = resolve_physical_additional_effect(
            effect=effect,
            adjusted_hit=result.adjusted_hit,
            effect_roll=effect_roll,
            target_is_member=target_is_member,
            target_has_boss_resistance=ResistanceType.DEATH in target_resistances,
            target_is_weak=resistance is not None and resistance in target_weaknesses,
            target_is_resistant=(
                result.tribe_resisted
                or (resistance is not None and resistance in target_resistances)
            ),
            target_defending=target_defending,
            critical=result.critical,
        )
        if resolution.success:
            if effect is AdditionalEffect.DEATH:
                return (effect,)
            successful.append(effect)

    if AdditionalEffect.CONFUSE in successful and AdditionalEffect.SLEEP in successful:
        successful.remove(AdditionalEffect.SLEEP)
    return tuple(successful)


def resolve_earthquake_attack(
    *, attack: int, hit: int, target_defense: int, hit_roll: int,
    target_defending: bool = False, target_floating: bool = False,
    target_resists_tribe: bool = False,
) -> PhysicalAttackResult:
    """Miss floating targets; otherwise use 60% attack without evasion or criticals.

    Guard halves damage without its extra evasion check, so even a zero-
    damage result remains a hit for the ordinary additional-effect rules.
    """

    if target_floating:
        return PhysicalAttackResult(hit=False, damage=0, adjusted_hit=float(hit), hit_value=0)
    result = resolve_physical_attack(
        attack=_nonnegative_integer(attack, "attack") * 3 // 5,
        hit=hit, target_defense=target_defense, target_evasion=0,
        hit_roll=hit_roll, target_unable_to_evade=True,
        target_resists_tribe=target_resists_tribe,
    )
    return replace(result, damage=result.damage // 2 if target_defending else result.damage)


def counter_attack_succeeds(
    *, attacker_agility: int, defender_agility: int,
    attacker_front: bool, defender_front: bool, defender_actionable: bool,
    roll: int, defender_reach: int = 1,
) -> bool:
    """DA2's twenty-step speed-ratio check; misses can also provoke a counter."""

    if not 0 <= roll <= 19:
        raise ValueError("counter roll must be from 0 to 19")
    if not defender_actionable or (
        defender_reach < 2 and not (attacker_front and defender_front)
    ):
        return False
    attacker_agility = max(1, attacker_agility)
    defender_agility = max(1, defender_agility)
    return int(10 * defender_agility / (attacker_agility + defender_agility)) > roll


__all__ = [
    "DA2_CRITICAL_RATE_UNIT",
    "DA2_EFFECTIVE_HIT_VALUE_BONUS",
    "DA2_MEMBER_DEATH_BASE_RATE",
    "DA2_MEMBER_STATUS_BASE_RATE",
    "DA2_MONSTER_DEATH_BASE_RATE",
    "DA2_MONSTER_STATUS_BASE_RATE",
    "DEFENDING_HIT_VALUE_THRESHOLD",
    "PHYSICAL_EFFECT_RESISTANCE",
    "PHYSICAL_STATUS_EFFECTS",
    "PhysicalAdditionalEffectResult",
    "PhysicalAttackResult",
    "drain_healing_amount",
    "counter_attack_succeeds",
    "resolve_earthquake_attack",
    "resolve_monster_attack_effects",
    "member_physical_attack",
    "physical_weapon_is_effective",
    "resolve_physical_additional_effect",
    "resolve_physical_attack",
    "weapon_can_drain",
]
