"""Battle command availability rules independent of Pyxel and presentation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

if __package__ == "":
    from member import EquipmentSlot, Member, SPELL_PROFICIENCY_KINDS
else:
    from .member import EquipmentSlot, Member, SPELL_PROFICIENCY_KINDS


class BattleTarget(Protocol):
    """The formation information needed to evaluate a normal attack target."""

    @property
    def is_front_row(self) -> bool: ...

    @property
    def is_alive(self) -> bool: ...


class BattleCommand(StrEnum):
    """Stable command keys shared by battle rules and presentation."""

    ATTACK = "attack"
    AMBUSH = "ambush"
    SPELL = "spell"
    AIM = "aim"
    HIDE = "hide"
    IDENTIFY = "identify"
    PRAY = "pray"
    COVER = "cover"
    IAI = "iai"
    FOCUS = "focus"
    BREATH = "breath"
    MP_SHARE = "mp_share"
    DEFEND = "defend"
    ESCAPE = "escape"
    ITEM = "item"
    FORMATION = "formation"


@dataclass(frozen=True)
class BattleCommandContext:
    """Situation-dependent capabilities supplied by the battle scene.

    The member supplies equipment, base spell aptitude, and skill state.
    Battle state supplies temporary restrictions and the availability of
    escape and items. This boundary can incorporate new rules without
    coupling them to Pyxel or a standalone test entry point.
    """

    silenced: bool = False
    item_available: bool = True
    escape_available: bool = True
    actor_hidden: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "silenced",
            "item_available",
            "escape_available",
            "actor_hidden",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a boolean")


@dataclass(frozen=True)
class BattleCommandOption:
    """One visible battle command and whether confirmation may execute it."""

    command: BattleCommand
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.command, BattleCommand):
            raise TypeError("command must be a BattleCommand")
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a boolean")


def member_attack_reach(member: Member) -> int:
    """Return the shortest reach among weapons used by one member."""

    weapons = tuple(
        weapon
        for slot in (EquipmentSlot.RIGHT, EquipmentSlot.LEFT)
        if (weapon := member.equipment.weapon_at(slot)) is not None
    )
    if not weapons:
        raise ValueError("member must have an equipped weapon to attack")
    return min(weapon.reach for weapon in weapons)


def member_can_attack(member: Member) -> bool:
    """Return whether the member has a main-hand weapon for a normal attack."""

    return member.equipment.weapon_at(EquipmentSlot.RIGHT) is not None


def member_can_iai(member: Member, *, attacker_is_front_row: bool) -> bool:
    """Iai requires a right-hand katana usable from the current battle row."""

    weapon = member.equipment.weapon_at(EquipmentSlot.RIGHT)
    return (
        weapon is not None
        and weapon.subtype == "KATANA"
        and (attacker_is_front_row or weapon.reach >= 2)
    )


def selectable_attack_target_indexes(
    *,
    attacker_is_front_row: bool,
    weapon_reach: int,
    monsters: Sequence[BattleTarget],
    unrestricted_range: bool = False,
) -> tuple[int, ...]:
    """Return targetable monster indexes for one physical attack."""

    if not isinstance(attacker_is_front_row, bool):
        raise TypeError("attacker_is_front_row must be a boolean")
    if isinstance(weapon_reach, bool) or weapon_reach not in (1, 2, 3):
        raise ValueError("weapon_reach must be 1, 2, or 3")
    if not isinstance(unrestricted_range, bool):
        raise TypeError("unrestricted_range must be a boolean")

    if (
        not unrestricted_range
        and weapon_reach == 1
        and not attacker_is_front_row
    ):
        return ()
    can_target_back_row = unrestricted_range or weapon_reach == 3 or (
        weapon_reach == 2 and attacker_is_front_row
    )
    return tuple(
        index
        for index, monster in enumerate(monsters)
        if monster.is_alive and (monster.is_front_row or can_target_back_row)
    )


def formation_change_enabled(member: Member, party: Sequence[Member]) -> bool:
    """Return whether ``member`` may swap rows without leaving no front row."""

    if not any(candidate is member for candidate in party):
        raise ValueError("member must belong to party")
    if not member.is_front_row:
        return True
    return sum(candidate.is_front_row for candidate in party) >= 2


def member_has_spell_aptitude(member: Member) -> bool:
    """Return whether the member's base abilities permit any spell school."""

    return any(
        member.proficiency(kind).aptitude.value >= 1
        for kind in SPELL_PROFICIENCY_KINDS
    )


_SKILL_COMMANDS = (
    ("Aim", BattleCommand.AIM),
    ("Hide", BattleCommand.HIDE),
    ("Identify", BattleCommand.IDENTIFY),
    ("Pray", BattleCommand.PRAY),
    ("Cover", BattleCommand.COVER),
    ("Iai", BattleCommand.IAI),
    ("Focus", BattleCommand.FOCUS),
    ("Breath", BattleCommand.BREATH),
    ("MP share", BattleCommand.MP_SHARE),
)


def resolve_battle_commands(
    member: Member,
    party: Sequence[Member],
    monsters: Sequence[BattleTarget],
    *,
    context: BattleCommandContext | None = None,
    party_front_rows: Sequence[bool] | None = None,
) -> tuple[BattleCommandOption, ...]:
    """Resolve visible commands and their selectable state for one member."""

    if not party:
        raise ValueError("party must not be empty")
    if not any(candidate is member for candidate in party):
        raise ValueError("member must belong to party")
    if party_front_rows is None:
        front_rows = tuple(candidate.is_front_row for candidate in party)
    else:
        front_rows = tuple(party_front_rows)
        if len(front_rows) != len(party) or not all(
            isinstance(is_front, bool) for is_front in front_rows
        ):
            raise ValueError("party_front_rows must contain one boolean per member")
    member_index = next(
        index for index, candidate in enumerate(party) if candidate is member
    )
    member_is_front_row = front_rows[member_index]
    current = BattleCommandContext() if context is None else context
    if not isinstance(current, BattleCommandContext):
        raise TypeError("context must be a BattleCommandContext")
    left_commands: list[BattleCommandOption] = []
    normal_attack_targets = (
        selectable_attack_target_indexes(
            attacker_is_front_row=member_is_front_row,
            weapon_reach=member_attack_reach(member),
            monsters=monsters,
        )
        if member_can_attack(member)
        else ()
    )
    attack_targets = (
        selectable_attack_target_indexes(
            attacker_is_front_row=member_is_front_row,
            weapon_reach=member_attack_reach(member),
            monsters=monsters,
            unrestricted_range=True,
        )
        if current.actor_hidden and member_can_attack(member)
        else normal_attack_targets
    )
    # Keep normal attack visible even when it cannot currently reach a target.
    # A member without a main-hand weapon and a back-row member with a
    # short-range weapon cannot attack, so the option is disabled.
    attack_command = (
        BattleCommand.AMBUSH if current.actor_hidden else BattleCommand.ATTACK
    )
    left_commands.append(
        BattleCommandOption(attack_command, enabled=bool(attack_targets))
    )
    if len(left_commands) < 3 and member_has_spell_aptitude(member):
        left_commands.append(
            BattleCommandOption(
                BattleCommand.SPELL,
                enabled=not current.silenced,
            )
        )
    for skill_key, command in _SKILL_COMMANDS:
        if len(left_commands) == 3:
            break
        if (
            not member.has_skill(skill_key)
            or (command is BattleCommand.HIDE and current.actor_hidden)
            or (command is BattleCommand.COVER and len(party) <= 1)
        ):
            continue
        left_commands.append(
            BattleCommandOption(
                command,
                enabled=(
                    (
                        member_can_iai(
                            member, attacker_is_front_row=member_is_front_row
                        )
                        and any(monster.is_alive for monster in monsters)
                    )
                    if command is BattleCommand.IAI
                    else (
                        command not in (BattleCommand.AIM, BattleCommand.FOCUS)
                        or bool(normal_attack_targets)
                    )
                ),
            )
        )
    right_commands = [
        BattleCommandOption(BattleCommand.DEFEND),
        BattleCommandOption(
            BattleCommand.ITEM,
            enabled=current.item_available,
        ),
    ]
    if len(party) > 1:
        right_commands.append(
            BattleCommandOption(
                BattleCommand.FORMATION,
                enabled=(
                    not current.actor_hidden
                    and (not member_is_front_row or sum(front_rows) >= 2)
                ),
            )
        )
    return tuple((*left_commands, *right_commands))


__all__ = [
    "BattleCommand",
    "BattleCommandContext",
    "BattleCommandOption",
    "BattleTarget",
    "formation_change_enabled",
    "member_can_attack",
    "member_can_iai",
    "member_attack_reach",
    "member_has_spell_aptitude",
    "resolve_battle_commands",
    "selectable_attack_target_indexes",
]
