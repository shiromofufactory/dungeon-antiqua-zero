"""Pyxel-independent monster action selection rules."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

if __package__ == "":
    from monster import MonsterDefinition, MonsterSpecialAction
    from resistance import ResistanceType
    from spell import Spell, SpellAction
else:
    from .monster import MonsterDefinition, MonsterSpecialAction
    from .resistance import ResistanceType
    from .spell import Spell, SpellAction


class MonsterAction(StrEnum):
    """Actions currently available to a monster on its timeline turn."""

    ATTACK = "attack"
    ESCAPE = "escape"
    CHARGE = "charge"
    CALL = "call"
    POISON_BREATH = "poison_breath"
    FIRE_BREATH = "fire_breath"
    EARTHQUAKE = "earthquake"
    TEMPTATION = "temptation"
    IDLE = "idle"


@dataclass(frozen=True)
class MonsterSpellAction:
    """One exact learned spell included in a monster's action candidates."""

    spell_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.spell_key, str) or not self.spell_key:
            raise ValueError("spell_key must be a non-empty string")


MonsterActionChoice = MonsterAction | MonsterSpellAction


@dataclass(frozen=True)
class MonsterSpellTarget:
    index: int
    front: bool
    actionable: bool
    can_cast: bool
    silenced: int
    speed: int
    protection: int
    resistances: frozenset[ResistanceType]


@dataclass(frozen=True)
class MonsterSpellCandidate:
    targets: tuple[int, ...]
    priority: bool = False


def evaluate_monster_spell(
    spell: Spell, targets: Sequence[MonsterSpellTarget], *,
    intelligence: int, is_solo: bool,
    choose: Callable[[tuple[int, ...]], int] = random.choice,
) -> MonsterSpellCandidate:
    """Evaluate a hostile spell using DA2's generic intelligence rules."""

    indexes = tuple(target.index for target in targets)
    if not indexes or intelligence <= 0:
        return MonsterSpellCandidate(indexes)
    if (
        spell.action is SpellAction.BREAK
        or (spell.action is SpellAction.SLOW and not spell.to_all)
        or (spell.action is SpellAction.CONFUSE and not spell.to_all and intelligence > 1)
    ):
        selected = choose(indexes)
        target = next(target for target in targets if target.index == selected)
        if spell.action is SpellAction.BREAK:
            effective = target.front and target.protection >= 0
        elif spell.action is SpellAction.SLOW:
            effective = target.speed >= 0
        else:
            effective = spell.attribute not in target.resistances
        return MonsterSpellCandidate((selected,) if effective else ())
    if spell.to_all and spell.action in (SpellAction.SLEEP, SpellAction.SILENCE, SpellAction.SLOW):
        applicable = tuple(
            target for target in targets
            if intelligence <= 1 or spell.attribute not in target.resistances
        )
        if spell.action is SpellAction.SLEEP:
            effective_count = sum(target.actionable for target in applicable)
        elif spell.action is SpellAction.SILENCE:
            applicable = tuple(target for target in applicable if target.can_cast)
            effective_count = sum(not target.silenced for target in applicable)
        else:
            effective_count = sum(target.speed >= 0 for target in applicable)
        if not effective_count:
            return MonsterSpellCandidate(())
        if intelligence == 2:
            if effective_count == len(applicable):
                return MonsterSpellCandidate(indexes, priority=True)
            if is_solo:
                return MonsterSpellCandidate(())
    if spell.to_all and spell.action is SpellAction.PURGE and not any(
        target.protection > 0 or target.speed > 0 for target in targets
    ):
        return MonsterSpellCandidate(())
    return MonsterSpellCandidate(indexes)


def prefer_monster_targets(
    indexes: tuple[int, ...], *, intelligence: int,
    is_incapacitated: Callable[[int], bool],
) -> tuple[int, ...]:
    """Prefer sleeping or paralyzed targets within the attack's legal range."""

    if intelligence <= 1 or len(indexes) < 2:
        return indexes
    return tuple(index for index in indexes if is_incapacitated(index)) or indexes


def reinforcement_target(
    caller: MonsterDefinition,
    definitions: Sequence[MonsterDefinition],
) -> MonsterDefinition:
    """Pick the strongest lower-level monster of the caller's tribe."""

    candidates = (
        definition
        for definition in definitions
        if definition.tribe is caller.tribe and definition.level < caller.level
    )
    return max(candidates, key=lambda definition: definition.level, default=caller)


def reinforcement_arrives(living_monster_count: int) -> bool:
    """Use ZERO's 0..2 roll for one actionable monster turn."""

    if (
        isinstance(living_monster_count, bool)
        or not isinstance(living_monster_count, int)
        or living_monster_count < 1
    ):
        raise ValueError("living_monster_count must be a positive integer")
    return (
        living_monster_count < 3
        and 3 - living_monster_count > random.randint(0, 2)
    )


def monster_action_candidates(
    *, special_actions: Sequence[MonsterSpecialAction], is_front_row: bool,
    can_attack: bool, can_charge: bool, spell_keys: Sequence[str],
    escape_eligible: bool, call_eligible: bool = False,
    can_breathe: bool = False,
    intelligence: int = 0, fire_breath_effective: bool = True,
    can_earthquake: bool = False,
    can_tempt: bool = False,
    priority_spell_key: str | None = None,
) -> tuple[MonsterActionChoice, ...]:
    """Share candidate construction between live AI and deterministic forecasts."""

    if priority_spell_key is not None:
        return (MonsterSpellAction(priority_spell_key),)
    candidates: list[MonsterActionChoice] = []
    if MonsterSpecialAction.ESCAPE in special_actions and escape_eligible:
        candidates.append(MonsterAction.ESCAPE)
    if MonsterSpecialAction.CHARGE in special_actions and can_charge:
        candidates.append(MonsterAction.CHARGE)
    if MonsterSpecialAction.CALL in special_actions and call_eligible:
        candidates.append(MonsterAction.CALL)
    if MonsterSpecialAction.POISON_BREATH in special_actions and can_breathe:
        candidates.append(MonsterAction.POISON_BREATH)
    if (
        MonsterSpecialAction.FIRE_BREATH in special_actions and can_breathe
        and (intelligence != 7 or fire_breath_effective)
    ):
        candidates.append(MonsterAction.FIRE_BREATH)
    if MonsterSpecialAction.EARTHQUAKE in special_actions and can_earthquake:
        candidates.append(MonsterAction.EARTHQUAKE)
    if MonsterSpecialAction.TEMPTATION in special_actions and can_tempt:
        candidates.append(MonsterAction.TEMPTATION)
    candidates.extend(MonsterSpellAction(key) for key in spell_keys)
    if is_front_row and can_attack:
        candidates.append(MonsterAction.ATTACK)
    elif not is_front_row and (intelligence <= 1 or not candidates):
        candidates.append(MonsterAction.IDLE)
    return tuple(candidates)


def select_monster_action(
    *,
    special_actions: Sequence[MonsterSpecialAction],
    is_front_row: bool,
    can_attack: bool,
    can_charge: bool,
    party_actual_attacks: Sequence[int],
    monster_attack: int,
    spell_keys: Sequence[str] = (),
    call_slot: int | None = None,
    intelligence: int = 0,
    can_breathe: bool = False,
    fire_breath_effective: bool = True,
    can_earthquake: bool = False,
    can_tempt: bool = False,
    priority_spell_key: str | None = None,
) -> MonsterActionChoice | None:
    """Choose one DA2-style candidate, including call and ZERO's charge.

    Escape retains DA2's two-stage eligibility check: a 50% gate, followed
    by comparing one random living member's actual attack against the
    monster's attack multiplied by a random value from 1.0 through 2.0.
    Without a priority action, eligible specials and spells have the same
    weight as a normal attack. A rear-row monster receives one idle candidate
    at intelligence 0 or 1, or when no other action is available. Call uses a
    3/4 candidate gate below intelligence 2. At intelligence 2 or higher it
    takes priority when the first available slot is 0 or 1.
    """

    if not isinstance(is_front_row, bool):
        raise TypeError("is_front_row must be a boolean")
    if not isinstance(can_attack, bool):
        raise TypeError("can_attack must be a boolean")
    if not isinstance(can_charge, bool):
        raise TypeError("can_charge must be a boolean")
    if isinstance(monster_attack, bool) or not isinstance(monster_attack, int):
        raise TypeError("monster_attack must be an integer")
    if monster_attack < 0:
        raise ValueError("monster_attack must not be negative")
    if any(
        isinstance(attack, bool) or not isinstance(attack, int) or attack < 0
        for attack in party_actual_attacks
    ):
        raise ValueError("party_actual_attacks must contain non-negative integers")
    if isinstance(spell_keys, (str, bytes)) or any(
        not isinstance(key, str) or not key for key in spell_keys
    ):
        raise ValueError("spell_keys must contain non-empty strings")
    if len(spell_keys) != len(set(spell_keys)):
        raise ValueError("spell_keys must not contain duplicates")

    specials = tuple(special_actions)
    if any(not isinstance(action, MonsterSpecialAction) for action in specials):
        raise TypeError("special_actions must contain MonsterSpecialAction values")

    escape_eligible = False
    if (
        MonsterSpecialAction.ESCAPE in specials
        and party_actual_attacks
        and random.randint(0, 1) > 0
    ):
        member_attack = random.choice(tuple(party_actual_attacks))
        if member_attack > monster_attack * random.uniform(1.0, 2.0):
            escape_eligible = True
    call_eligible = False
    if MonsterSpecialAction.CALL in specials and call_slot is not None:
        if intelligence >= 2:
            if call_slot <= 1:
                return MonsterAction.CALL
        else:
            call_eligible = random.randint(0, 3) > 0
    candidates = monster_action_candidates(
        special_actions=specials, is_front_row=is_front_row,
        can_attack=can_attack, can_charge=can_charge, spell_keys=spell_keys,
        escape_eligible=escape_eligible, call_eligible=call_eligible,
        can_breathe=can_breathe,
        intelligence=intelligence, fire_breath_effective=fire_breath_effective,
        can_earthquake=can_earthquake,
        can_tempt=can_tempt,
        priority_spell_key=priority_spell_key,
    )

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return random.choice(list(candidates))


__all__ = [
    "MonsterAction",
    "MonsterActionChoice",
    "MonsterSpellAction",
    "MonsterSpellTarget",
    "MonsterSpellCandidate",
    "evaluate_monster_spell",
    "prefer_monster_targets",
    "reinforcement_arrives",
    "reinforcement_target",
    "monster_action_candidates",
    "select_monster_action",
]
