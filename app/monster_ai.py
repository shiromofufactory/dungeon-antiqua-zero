"""Pyxel-independent monster action selection rules."""

from __future__ import annotations

import random
from collections.abc import Sequence
from enum import StrEnum

from monster import MonsterSpecialAction


class MonsterAction(StrEnum):
    """Actions currently available to a monster on its timeline turn."""

    ATTACK = "attack"
    ESCAPE = "escape"
    CHARGE = "charge"


def select_monster_action(
    *,
    special_actions: Sequence[MonsterSpecialAction],
    is_front_row: bool,
    can_attack: bool,
    can_charge: bool,
    party_actual_attacks: Sequence[int],
    monster_attack: int,
) -> MonsterAction | None:
    """Choose one DA2-style candidate, including ZERO's charge action.

    Escape retains DA2's two-stage eligibility check: a 50% gate, followed
    by comparing one random living member's actual attack against the
    monster's attack multiplied by a random value from 1.0 through 2.0.
    Eligible specials are then chosen with the same weight as a normal
    attack.
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

    specials = tuple(special_actions)
    if any(not isinstance(action, MonsterSpecialAction) for action in specials):
        raise TypeError("special_actions must contain MonsterSpecialAction values")

    candidates: list[MonsterAction] = []
    if (
        MonsterSpecialAction.ESCAPE in specials
        and party_actual_attacks
        and random.randint(0, 1) > 0
    ):
        member_attack = random.choice(tuple(party_actual_attacks))
        if member_attack > monster_attack * random.uniform(1.0, 2.0):
            candidates.append(MonsterAction.ESCAPE)
    if MonsterSpecialAction.CHARGE in specials and can_charge:
        candidates.append(MonsterAction.CHARGE)
    if is_front_row and can_attack:
        candidates.append(MonsterAction.ATTACK)

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return random.choice(candidates)


__all__ = ["MonsterAction", "select_monster_action"]
