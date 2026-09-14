"""Settle battle experience, proficiency, and post-battle character growth."""

from __future__ import annotations

import random
from dataclasses import dataclass
from math import isqrt
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

if __package__ == "systems":
    from item import Item
    from member import Member, ProficiencyKind
    from state import SaveData
    from systems.inventory import InventorySystem
    from systems.monster_records import MonsterRecordSystem
    from systems.shop import MAX_GOLD
else:
    from ..item import Item
    from ..member import Member, ProficiencyKind
    from ..state import SaveData
    from .inventory import InventorySystem
    from .monster_records import MonsterRecordSystem
    from .shop import MAX_GOLD


TREASURE_RATE_DENOMINATOR = 16


@dataclass(frozen=True)
class EnemyProgressionData:
    """Immutable reward fields copied from one encountered monster record."""

    level: int
    early_appear: int
    max_occurrence: int
    gold: int
    monster_key: str = ""
    treasure_item_key: str = ""
    treasure_rate: int = 0

    def __post_init__(self) -> None:
        for name in ("level", "early_appear", "gold"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if (
            isinstance(self.max_occurrence, bool)
            or not isinstance(self.max_occurrence, int)
            or self.max_occurrence <= 0
        ):
            raise ValueError("max_occurrence must be a positive integer")
        for name in ("monster_key", "treasure_item_key"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be a string")
        if bool(self.monster_key) != bool(self.treasure_item_key):
            raise ValueError(
                "monster_key and treasure_item_key must both be set or both be empty"
            )
        if (
            isinstance(self.treasure_rate, bool)
            or not isinstance(self.treasure_rate, int)
            or not 0 <= self.treasure_rate <= TREASURE_RATE_DENOMINATOR
        ):
            raise ValueError(
                f"treasure_rate must be from 0 to {TREASURE_RATE_DENOMINATOR}"
            )
        if self.treasure_rate and not self.monster_key:
            raise ValueError("positive treasure_rate requires treasure data")

    def experience(self, action_count: int) -> int:
        """Return the per-defeat reward, flooring only the final quotient."""

        if (
            isinstance(action_count, bool)
            or not isinstance(action_count, int)
            or action_count < 0
        ):
            raise ValueError("action_count must be a non-negative integer")
        level_span = max(0, self.level - self.early_appear)
        numerator = 12 * self.level * level_span * (10 + action_count)
        return numerator // (self.max_occurrence * 10)


@dataclass(frozen=True)
class ProficiencySnapshot:
    level: int
    progress: int

    @property
    def total(self) -> int:
        return self.level * 100 + self.progress


@dataclass(frozen=True)
class MemberGrowthSnapshot:
    """The values required to animate one result-panel member."""

    internal_level: int
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    proficiencies: Mapping[ProficiencyKind, ProficiencySnapshot]


@dataclass(frozen=True)
class BattleTreasureDrop:
    """One item successfully awarded by the last defeated enemy."""

    monster_key: str
    item_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.monster_key, str) or not self.monster_key:
            raise ValueError("monster_key must be a non-empty string")
        if not isinstance(self.item_key, str) or not self.item_key:
            raise ValueError("item_key must be a non-empty string")


@dataclass(frozen=True)
class BattleGrowthResult:
    """Immutable before/after settlement data used by the result screen."""

    experience_gained: int
    gold_gained: int
    before: tuple[MemberGrowthSnapshot, ...]
    after: tuple[MemberGrowthSnapshot, ...]
    treasure_drop: BattleTreasureDrop | None = None

    @property
    def has_result_growth(self) -> bool:
        """Return whether the animated result has any value to increase."""

        return any(
            old.max_hp != new.max_hp
            or old.max_mp != new.max_mp
            or any(
                old.proficiencies[kind].total
                != new.proficiencies[kind].total
                for kind in ProficiencyKind
            )
            for old, new in zip(self.before, self.after)
        )

    @property
    def has_level_up_growth(self) -> bool:
        """Return whether growth should trigger the level-up jingle and color."""

        return any(
            old.max_hp != new.max_hp
            or old.max_mp != new.max_mp
            or any(
                old.proficiencies[kind].level
                != new.proficiencies[kind].level
                for kind in ProficiencyKind
            )
            for old, new in zip(self.before, self.after)
        )


@dataclass
class _SpellUse:
    maximum_enemy_level: int = 0
    total_mp: int = 0


def _snapshot(member: Member) -> MemberGrowthSnapshot:
    return MemberGrowthSnapshot(
        internal_level=member.internal_level,
        hp=member.hp,
        max_hp=member.max_hp,
        mp=member.mp,
        max_mp=member.max_mp,
        proficiencies=MappingProxyType(
            {
                kind: ProficiencySnapshot(
                    member.proficiency(kind).level,
                    member.proficiency(kind).progress,
                )
                for kind in ProficiencyKind
            }
        ),
    )


class BattleProgression:
    """Collect one battle's action facts and atomically settle its rewards."""

    def __init__(self, enemies: Sequence[EnemyProgressionData]) -> None:
        if not enemies or not all(
            isinstance(enemy, EnemyProgressionData) for enemy in enemies
        ):
            raise TypeError("enemies must contain EnemyProgressionData")
        self.enemies = tuple(enemies)
        self._enemy_action_counts = [0] * len(self.enemies)
        self._escaped_enemy_indexes: set[int] = set()
        self._defeated_enemy_indexes: set[int] = set()
        self._last_defeated_enemy_index: int | None = None
        self._weapon_awards: dict[str, dict[ProficiencyKind, int]] = {}
        self._spell_uses: dict[str, dict[ProficiencyKind, _SpellUse]] = {}
        self._settled = False

    def record_enemy_action(self, enemy_index: int) -> None:
        """Count one actual enemy action; idle rear turns never call this."""

        self._require_enemy_index(enemy_index)
        self._enemy_action_counts[enemy_index] += 1

    def record_enemy_escape(self, enemy_index: int) -> None:
        """Exclude one escaped enemy from EXP and Gold settlement."""

        self._require_enemy_index(enemy_index)
        if enemy_index in self._defeated_enemy_indexes:
            raise ValueError("a defeated enemy cannot escape")
        self._escaped_enemy_indexes.add(enemy_index)

    def record_enemy_defeat(self, enemy_index: int) -> None:
        """Remember defeat order so only the last defeated enemy can drop."""

        self._require_enemy_index(enemy_index)
        if enemy_index in self._escaped_enemy_indexes:
            raise ValueError("an escaped enemy cannot be defeated")
        if enemy_index in self._defeated_enemy_indexes:
            return
        self._defeated_enemy_indexes.add(enemy_index)
        self._last_defeated_enemy_index = enemy_index

    def record_weapon_action(
        self,
        member: Member,
        weapons: Iterable[Item],
        enemy_levels: Iterable[int],
        *,
        defeated_enemy: bool = False,
        critical: bool = False,
    ) -> None:
        """Keep the maximum award produced by one physical or weapon-use action."""

        levels = self._enemy_levels(enemy_levels)
        if not levels:
            return
        bonus = int(defeated_enemy) + int(critical)
        awards = self._weapon_awards.setdefault(member.definition.key, {})
        for weapon in weapons:
            if not isinstance(weapon, Item) or not weapon.is_weapon:
                raise ValueError("weapons must contain weapon items")
            kind = ProficiencyKind[weapon.subtype]
            proficiency = member.proficiency(kind)
            amount = max(
                0,
                max(levels) + int(proficiency.aptitude) - proficiency.level + bonus,
            )
            awards[kind] = max(awards.get(kind, 0), amount)

    def record_spell_use(
        self,
        member: Member,
        kind: ProficiencyKind,
        enemy_levels: Iterable[int],
        *,
        mp_spent: int,
    ) -> None:
        """Accumulate paid MP and keep the highest relevant enemy level by school."""

        if not isinstance(kind, ProficiencyKind):
            raise TypeError("kind must be a ProficiencyKind")
        if kind not in (
            ProficiencyKind.MYSTIC,
            ProficiencyKind.SACRED,
            ProficiencyKind.NETHER,
        ):
            raise ValueError("kind must identify a spell school")
        if isinstance(mp_spent, bool) or not isinstance(mp_spent, int) or mp_spent < 0:
            raise ValueError("mp_spent must be a non-negative integer")
        levels = self._enemy_levels(enemy_levels)
        if not levels:
            return
        uses = self._spell_uses.setdefault(member.definition.key, {})
        usage = uses.setdefault(kind, _SpellUse())
        usage.maximum_enemy_level = max(usage.maximum_enemy_level, max(levels))
        usage.total_mp += mp_spent

    def rewards(self) -> tuple[int, int]:
        """Return total EXP and Gold without changing game state."""

        experience = sum(
            enemy.experience(action_count)
            for index, (enemy, action_count) in enumerate(
                zip(self.enemies, self._enemy_action_counts)
            )
            if index not in self._escaped_enemy_indexes
        )
        gold = sum(
            enemy.gold
            for index, enemy in enumerate(self.enemies)
            if index not in self._escaped_enemy_indexes
        )
        return experience, gold

    def settle(
        self,
        save_data: SaveData,
        members: Sequence[Member],
        *,
        ineligible_member_keys: Iterable[str] = (),
        inventory_system: InventorySystem | None = None,
        monster_record_system: MonsterRecordSystem | None = None,
    ) -> BattleGrowthResult:
        """Apply rewards once, including one HP and one eligible MP increase."""

        if self._settled:
            raise RuntimeError("battle progression has already been settled")
        if not isinstance(save_data, SaveData):
            raise TypeError("save_data must be SaveData")
        party = tuple(members)
        if not party or not all(isinstance(member, Member) for member in party):
            raise TypeError("members must contain at least one Member")
        keys = tuple(member.definition.key for member in party)
        if len(keys) != len(set(keys)):
            raise ValueError("members must not contain duplicates")
        ineligible = frozenset(ineligible_member_keys)
        if not all(isinstance(key, str) and key for key in ineligible):
            raise ValueError("ineligible_member_keys must contain strings")
        if (inventory_system is None) != (monster_record_system is None):
            raise ValueError(
                "inventory_system and monster_record_system must be supplied together"
            )
        if inventory_system is not None and not isinstance(
            inventory_system, InventorySystem
        ):
            raise TypeError("inventory_system must be an InventorySystem")
        if monster_record_system is not None and not isinstance(
            monster_record_system, MonsterRecordSystem
        ):
            raise TypeError("monster_record_system must be a MonsterRecordSystem")

        before = tuple(_snapshot(member) for member in party)
        experience_gained, gold_gained = self.rewards()
        save_data.experience += experience_gained
        save_data.gold = min(MAX_GOLD, save_data.gold + gold_gained)

        for member in party:
            member.refresh_internal_level(save_data.experience)

        eligible = {
            member.definition.key
            for member in party
            if member.definition.key not in ineligible and member.is_alive
        }
        for member in party:
            key = member.definition.key
            if key not in eligible:
                continue
            for kind, amount in self._weapon_awards.get(key, {}).items():
                member.proficiency(kind).add_progress(amount)
            for kind, usage in self._spell_uses.get(key, {}).items():
                proficiency = member.proficiency(kind)
                amount = max(
                    0,
                    usage.maximum_enemy_level
                    + int(proficiency.aptitude)
                    - proficiency.level
                    + isqrt(usage.total_mp),
                )
                proficiency.add_progress(amount)

        ordered = sorted(
            enumerate(party),
            key=lambda entry: (entry[1].internal_level, entry[0]),
        )
        spell_users = set(self._spell_uses)
        mp_growth_key: str | None = None
        for _index, member in ordered:
            key = member.definition.key
            if (
                key in eligible
                and key in spell_users
                and member.calculated_max_mp() > member.max_mp
            ):
                member.max_mp = member.calculated_max_mp()
                mp_growth_key = key
                break

        for _index, member in ordered:
            key = member.definition.key
            if (
                key in eligible
                and key != mp_growth_key
                and member.calculated_max_hp() > member.max_hp
            ):
                member.max_hp = member.calculated_max_hp()
                break

        treasure_drop = self._settle_treasure(inventory_system, party)
        if treasure_drop is not None:
            assert monster_record_system is not None
            monster_record_system.record_treasure_acquired(
                treasure_drop.monster_key
            )

        self._settled = True
        return BattleGrowthResult(
            experience_gained,
            gold_gained,
            before,
            tuple(_snapshot(member) for member in party),
            treasure_drop,
        )

    def _settle_treasure(
        self,
        inventory_system: InventorySystem | None,
        members: Sequence[Member],
    ) -> BattleTreasureDrop | None:
        if inventory_system is None or self._last_defeated_enemy_index is None:
            return None
        enemy = self.enemies[self._last_defeated_enemy_index]
        if enemy.treasure_rate == 0:
            return None
        if random.randrange(TREASURE_RATE_DENOMINATOR) >= enemy.treasure_rate:
            return None
        if not inventory_system.add(
            enemy.treasure_item_key,
            members=members,
        ):
            return None
        return BattleTreasureDrop(enemy.monster_key, enemy.treasure_item_key)

    def _require_enemy_index(self, enemy_index: int) -> None:
        if (
            isinstance(enemy_index, bool)
            or not isinstance(enemy_index, int)
            or not 0 <= enemy_index < len(self.enemies)
        ):
            raise ValueError("enemy_index must identify an encountered enemy")

    @staticmethod
    def _enemy_levels(values: Iterable[int]) -> tuple[int, ...]:
        try:
            levels = tuple(values)
        except TypeError as error:
            raise TypeError("enemy_levels must be iterable") from error
        if any(
            isinstance(level, bool) or not isinstance(level, int) or level < 0
            for level in levels
        ):
            raise ValueError("enemy_levels must contain non-negative integers")
        return levels


__all__ = [
    "BattleGrowthResult",
    "BattleProgression",
    "BattleTreasureDrop",
    "EnemyProgressionData",
    "MemberGrowthSnapshot",
    "ProficiencySnapshot",
    "TREASURE_RATE_DENOMINATOR",
]
