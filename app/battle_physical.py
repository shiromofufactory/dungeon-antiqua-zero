"""Physical-attack calculations shared by battle scenes and mocks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhysicalAttackResult:
    """One DA2-compatible basic physical-attack result."""

    hit: bool
    damage: int
    adjusted_hit: float
    hit_value: float


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
) -> PhysicalAttackResult:
    """Resolve an unmodified physical attack using DA2's base calculation."""

    attack = _nonnegative_integer(attack, "attack")
    hit = _nonnegative_integer(hit, "hit")
    agility = _nonnegative_integer(agility, "agility")
    target_defense = _nonnegative_integer(target_defense, "target_defense")
    target_evasion = _nonnegative_integer(target_evasion, "target_evasion")
    hit_roll = _nonnegative_integer(hit_roll, "hit_roll")
    if hit_roll > 99:
        raise ValueError("hit_roll must be from 0 to 99")

    adjusted_hit = float(hit)
    if agility > 20:
        adjusted_hit *= 1 + (agility - 20) / 20
    elif agility < 10:
        adjusted_hit *= 1 + (agility - 10) / 20

    hit_value = adjusted_hit * (100 - target_evasion) / 100 - hit_roll
    if hit_value < 0:
        return PhysicalAttackResult(
            hit=False,
            damage=0,
            adjusted_hit=adjusted_hit,
            hit_value=hit_value,
        )

    damage_factor = 0.8 + hit_value / 250
    reduced_attack = max(attack - target_defense, 1)
    defense_cut_rate = target_defense / 100
    damage = int(
        reduced_attack * damage_factor * (1 - defense_cut_rate) + 0.99
    )
    return PhysicalAttackResult(
        hit=True,
        damage=damage,
        adjusted_hit=adjusted_hit,
        hit_value=hit_value,
    )


__all__ = [
    "PhysicalAttackResult",
    "member_physical_attack",
    "resolve_physical_attack",
]
