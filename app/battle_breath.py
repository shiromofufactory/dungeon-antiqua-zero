"""Breath rules independent of Pyxel and presentation."""

from dataclasses import dataclass

if __package__:
    from .member import MAX_ABILITY, Member
else:
    from member import MAX_ABILITY, Member


@dataclass(frozen=True)
class BreathResult:
    damage: int
    poisoned: bool
    resisted: bool


def member_breath_attack(member: Member) -> float:
    """Use strength and internal level without any weapon bonuses."""

    strength = min(MAX_ABILITY, member.permanent_abilities.strength + sum(
        item.strength_modifier for item in member.equipment.equipped_items()
        if not item.is_weapon
    ))
    return strength * (1 + member.internal_level) / 2


def member_breath_hp_cost(current_hp: int) -> int:
    return current_hp // 5


def resolve_poison_breath(
    *, attack: int, hp: int, max_hp: int, target_spell_defense: int,
    poison_resistant: bool, random_factor: float, poison_roll: int,
) -> BreathResult:
    """Preserve DA2's 0.8 attack, missing-HP bonus and 2/10 poison roll.

    DA2 divides the already-truncated damage by four with integer division
    for poison resistance. Spell-defense buffs and physical guard do not
    affect this attack; only the supplied spell defense and poison tolerance do.
    """

    if not 0 <= poison_roll <= 9:
        raise ValueError("invalid poison-breath roll")
    return BreathResult(
        damage=_breath_damage(
            attack=attack, hp=hp, max_hp=max_hp,
            target_spell_defense=target_spell_defense, attack_multiplier=0.8,
            resisted=poison_resistant, random_factor=random_factor,
        ),
        poisoned=not poison_resistant and poison_roll < 2,
        resisted=poison_resistant,
    )


def resolve_fire_breath(
    *, attack: int | float, hp: int, max_hp: int, target_spell_defense: int,
    fire_resistant: bool, random_factor: float,
) -> BreathResult:
    """Use full attack for DA2 fire breath, with no status-effect roll."""

    return BreathResult(
        damage=_breath_damage(
            attack=attack, hp=hp, max_hp=max_hp,
            target_spell_defense=target_spell_defense, attack_multiplier=1,
            resisted=fire_resistant, random_factor=random_factor,
        ),
        poisoned=False,
        resisted=fire_resistant,
    )


def _breath_damage(
    *, attack: int | float, hp: int, max_hp: int, target_spell_defense: int,
    attack_multiplier: float, resisted: bool, random_factor: float,
) -> int:
    if attack < 0 or max_hp <= 0 or not 0 <= hp <= max_hp:
        raise ValueError("invalid breath attacker stats")
    if not 0 <= target_spell_defense <= 100:
        raise ValueError("target_spell_defense must be from 0 to 100")
    if not 0 <= random_factor <= 1:
        raise ValueError("invalid breath damage roll")
    power = attack * attack_multiplier * (100 - target_spell_defense) / 100
    damage = int(power * (0.4 + random_factor * 0.1) * (2 - hp / max_hp))
    return damage // 4 if resisted else damage
