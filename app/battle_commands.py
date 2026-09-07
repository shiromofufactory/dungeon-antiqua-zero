"""Battle command availability rules independent of Pyxel and screen mocks."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

if __package__ == "":
    from member import EquipmentSlot, Member
    from spell import Spell
else:
    from .member import EquipmentSlot, Member
    from .spell import Spell


class BattleTarget(Protocol):
    """The formation information needed to evaluate a normal attack target."""

    @property
    def is_front_row(self) -> bool: ...

    @property
    def is_alive(self) -> bool: ...


class BattleCommand(StrEnum):
    """Stable command keys shared by battle rules and presentation."""

    ATTACK = "attack"
    DEFEND = "defend"
    SPELL = "spell"
    ESCAPE = "escape"
    ITEM = "item"
    FORMATION = "formation"


@dataclass(frozen=True)
class BattleCommandContext:
    """Situation-dependent capabilities supplied by the battle scene.

    The member supplies equipment and skill state. The spell catalog and
    event-acquired keys let the resolver apply learning, battle-use, and MP
    rules. Item and escape flags remain explicit battle-state inputs. This
    boundary can incorporate new rules without coupling them to Pyxel or a
    screen mock.
    """

    spells: tuple[Spell, ...] = ()
    event_spell_keys: frozenset[str] = frozenset()
    spell_available: bool | None = None
    item_available: bool = True
    escape_available: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.spells, tuple) or not all(
            isinstance(spell, Spell) for spell in self.spells
        ):
            raise TypeError("spells must be a tuple of Spell values")
        if not isinstance(self.event_spell_keys, frozenset) or not all(
            isinstance(key, str) for key in self.event_spell_keys
        ):
            raise TypeError("event_spell_keys must be a frozenset of strings")
        if self.spell_available is not None and not isinstance(
            self.spell_available,
            bool,
        ):
            raise TypeError("spell_available must be a boolean or None")
        for field_name in (
            "item_available",
            "escape_available",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a boolean")


@dataclass(frozen=True)
class BattleCommandOption:
    """One visible battle command and whether the cursor may select it."""

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
    # An unarmed attack follows the same range rule as a reach-1 weapon.
    return min((weapon.reach for weapon in weapons), default=1)


def selectable_attack_target_indexes(
    *,
    attacker_is_front_row: bool,
    weapon_reach: int,
    monsters: Sequence[BattleTarget],
) -> tuple[int, ...]:
    """Return targetable monster indexes for one normal attack."""

    if not isinstance(attacker_is_front_row, bool):
        raise TypeError("attacker_is_front_row must be a boolean")
    if isinstance(weapon_reach, bool) or weapon_reach not in (1, 2, 3):
        raise ValueError("weapon_reach must be 1, 2, or 3")

    if weapon_reach == 1 and not attacker_is_front_row:
        return ()
    can_target_back_row = weapon_reach == 3 or (
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


def member_can_cast_battle_spell(
    member: Member,
    spells: Collection[Spell],
    *,
    event_spell_keys: Collection[str] = (),
) -> bool:
    """Return whether the member knows an affordable battle spell."""

    return any(
        spell.on_battle
        and member.mp >= spell.mp
        and spell.is_learned_by(member, event_spell_keys)
        for spell in spells
    )


def resolve_battle_commands(
    member: Member,
    party: Sequence[Member],
    monsters: Sequence[BattleTarget],
    *,
    context: BattleCommandContext | None = None,
) -> tuple[BattleCommandOption, ...]:
    """Resolve visible commands and their selectable state for one member."""

    if not party:
        raise ValueError("party must not be empty")
    if not any(candidate is member for candidate in party):
        raise ValueError("member must belong to party")
    current = BattleCommandContext() if context is None else context
    if not isinstance(current, BattleCommandContext):
        raise TypeError("context must be a BattleCommandContext")
    spell_available = current.spell_available
    if spell_available is None:
        spell_available = member_can_cast_battle_spell(
            member,
            current.spells,
            event_spell_keys=current.event_spell_keys,
        )

    commands: list[BattleCommandOption] = []
    attack_targets = selectable_attack_target_indexes(
        attacker_is_front_row=member.is_front_row,
        weapon_reach=member_attack_reach(member),
        monsters=monsters,
    )
    # The existing battle UI removes normal attack rather than greying it out
    # when no valid target exists.
    if attack_targets:
        commands.append(BattleCommandOption(BattleCommand.ATTACK))
    commands.extend(
        (
            BattleCommandOption(BattleCommand.DEFEND),
            BattleCommandOption(
                BattleCommand.SPELL,
                enabled=spell_available,
            ),
            BattleCommandOption(
                BattleCommand.ESCAPE,
                enabled=current.escape_available,
            ),
            BattleCommandOption(
                BattleCommand.ITEM,
                enabled=current.item_available,
            ),
        )
    )
    if len(party) > 1:
        commands.append(
            BattleCommandOption(
                BattleCommand.FORMATION,
                enabled=formation_change_enabled(member, party),
            )
        )
    return tuple(commands)


__all__ = [
    "BattleCommand",
    "BattleCommandContext",
    "BattleCommandOption",
    "BattleTarget",
    "formation_change_enabled",
    "member_attack_reach",
    "member_can_cast_battle_spell",
    "resolve_battle_commands",
    "selectable_attack_target_indexes",
]
