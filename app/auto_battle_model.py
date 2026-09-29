"""Immutable inputs and results for automatic battle decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import floor
from statistics import median

if __package__:
    from .battle_commands import BattleCommand
    from .battle_physical import member_physical_attack
    from .item import AdditionalEffect, ItemSpecial
    from .member import (
        EquipmentSet,
        EquipmentSlot,
        Member,
        ProficiencyAptitude,
        ProficiencyKind,
    )
    from .monster import MonsterSpecialAction
    from .resistance import ResistanceType
    from .spell import Spell
    from .state import SpellMode
else:
    from battle_commands import BattleCommand
    from battle_physical import member_physical_attack
    from item import AdditionalEffect, ItemSpecial
    from member import (
        EquipmentSet,
        EquipmentSlot,
        Member,
        ProficiencyAptitude,
        ProficiencyKind,
    )
    from monster import MonsterSpecialAction
    from resistance import ResistanceType
    from spell import Spell
    from state import SpellMode


CASE_COUNT = 8
FORECAST_TURNS = 16
DISCOUNT = 0.95
EFFECT_VERSION = 2


class ItemMode(StrEnum):
    REUSABLE_EQUIPMENT = "reusable_equipment"
    NEVER = "never"


@dataclass(frozen=True)
class AutoBattlePolicy:
    spell_mode: SpellMode = SpellMode.USE
    item_mode: ItemMode = ItemMode.REUSABLE_EQUIPMENT

    def __post_init__(self) -> None:
        if not isinstance(self.spell_mode, SpellMode):
            raise TypeError("spell_mode must be SpellMode")
        if not isinstance(self.item_mode, ItemMode):
            raise TypeError("item_mode must be ItemMode")


@dataclass(frozen=True)
class AutoWeapon:
    attack: int
    hit: int
    critical_scale: float = 1.0
    power_hit: bool = False
    attribute: ResistanceType | None = None
    effect: AdditionalEffect | None = None
    iai_attack: int | None = None


@dataclass(frozen=True)
class AutoProficiency:
    kind: ProficiencyKind
    level: int
    aptitude: ProficiencyAptitude


@dataclass(frozen=True)
class AutoCombatant:
    """No live member, scene, hidden enemy HP, or hidden affinities."""

    number: int
    key: str
    enemy: bool
    max_hp: int | None
    hp: int | None
    max_mp: int = 0
    mp: int = 0
    front: bool = True
    alive: bool = True
    agility: int = 1
    magic: int = 0
    internal_level: int = 1
    defense: int = 0
    evasion: int = 0
    spell_defense: int = 0
    attack: int = 0
    hit: int = 0
    weapons: tuple[AutoWeapon, ...] = ()
    equipment: EquipmentSet = field(default_factory=EquipmentSet)
    proficiencies: tuple[AutoProficiency, ...] = ()
    skills: frozenset[str] = frozenset()
    spells: tuple[Spell, ...] = ()
    special_actions: tuple[MonsterSpecialAction, ...] = ()
    effect: AdditionalEffect | None = None
    resistances: frozenset[ResistanceType] = frozenset()
    weaknesses: frozenset[ResistanceType] = frozenset()
    shadow: bool = False
    boss: bool = False
    poisoned: bool = False
    sleeping: int = 0
    silenced: int = 0
    paralyzed: bool = False
    confused: int = 0
    stunned: bool = False
    protection: int = 0
    speed: int = 0
    healing: int = 0
    hidden: bool = False
    defending: bool = False
    cover: int | None = None
    focus: int | None = None
    known_fields: frozenset[str] = frozenset()
    hp_displayed: bool = False
    net_damage: int = 0
    species_key: str = ""

    @classmethod
    def from_member(
        cls,
        member: Member,
        number: int,
        *,
        front: bool,
        spells: tuple[Spell, ...],
        hidden: bool = False,
        defending: bool = False,
        cover: int | None = None,
        focus: int | None = None,
    ) -> AutoCombatant:
        stats = member.battle_stats
        weapons = []
        for slot in (EquipmentSlot.RIGHT, EquipmentSlot.LEFT):
            weapon = member.equipment.weapon_at(slot)
            if weapon is None:
                continue
            if slot is EquipmentSlot.LEFT and not member.has_skill("Dual-Wield"):
                continue
            attack = (
                stats.attack_right if slot is EquipmentSlot.RIGHT else stats.attack_left
            )
            hit = stats.hit_right if slot is EquipmentSlot.RIGHT else stats.hit_left
            if attack is None or hit is None:
                continue
            weapons.append(
                AutoWeapon(
                    attack=member_physical_attack(
                        attack,
                        member.adjusted_abilities.strength,
                        member.weapon_level(weapon),
                        member.internal_level,
                    ),
                    hit=hit.total,
                    critical_scale=1.5
                    if member.uses_two_handed_weapon(weapon)
                    else 1.0,
                    power_hit=weapon.special is ItemSpecial.POWER_HIT,
                    attribute=(
                        ResistanceType(weapon.attack_attribute.value)
                        if weapon.attack_attribute is not None
                        else None
                    ),
                    effect=weapon.additional_effect,
                    iai_attack=(
                        member_physical_attack(
                            attack * 60 // 100,
                            member.adjusted_abilities.strength,
                            member.weapon_level(weapon),
                            member.internal_level,
                        )
                        if slot is EquipmentSlot.RIGHT and weapon.subtype == "KATANA"
                        else None
                    ),
                )
            )
        armor = member.equipment.armor_items()
        keys = (
            "Aim",
            "Hide",
            "Identify",
            "Pray",
            "Cover",
            "Iai",
            "Focus",
            "Breath",
            "MP share",
            "Power Hit",
            "Lethal",
            "Dual-Wield",
        )
        return cls(
            number=number,
            key=f"pc:{member.definition.key}",
            enemy=False,
            max_hp=member.max_hp,
            hp=member.hp,
            max_mp=member.max_mp,
            mp=member.mp,
            front=front,
            alive=member.is_alive,
            agility=member.adjusted_abilities.agility,
            magic=member.adjusted_abilities.magic,
            internal_level=member.internal_level,
            defense=sum(item.defense for item in armor),
            evasion=sum(item.evasion for item in armor),
            spell_defense=stats.spell_resistance,
            weapons=tuple(weapons),
            equipment=member.equipment,
            proficiencies=tuple(
                AutoProficiency(k, p.level, p.aptitude)
                for k, p in member.proficiencies.items()
            ),
            skills=frozenset(k for k in keys if member.has_skill(k)),
            spells=spells,
            resistances=member.resistances,
            poisoned=member.poisoned,
            sleeping=member.sleeping,
            paralyzed=member.paralyzed,
            confused=member.confused,
            stunned=member.stunned,
            protection=member.protection_level,
            speed=member.speed_modifier,
            healing=member.battle_healing,
            hidden=hidden,
            defending=defending,
            cover=cover,
            focus=focus,
        )


@dataclass(frozen=True)
class AutoBattleSnapshot:
    combatants: tuple[AutoCombatant, ...]
    gauges: tuple[tuple[int, float], ...]
    active_number: int
    spells: tuple[Spell, ...]
    policy: AutoBattlePolicy = field(default_factory=AutoBattlePolicy)
    surprise_pending: frozenset[int] = frozenset()
    surprise_original_rows: tuple[tuple[int, bool], ...] = ()
    used_spell_types: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        numbers = {c.number for c in self.combatants}
        if len(numbers) != len(self.combatants):
            raise ValueError("duplicate combatant number")
        if not self.gauges or self.gauges[0][0] != self.active_number:
            raise ValueError("active combatant must lead timeline")
        if any(n not in numbers for n, _ in self.gauges):
            raise ValueError("timeline refers to an unknown combatant")
        if not any(not c.enemy and c.alive for c in self.combatants):
            raise ValueError("cannot decide after defeat")
        if not any(c.enemy and c.alive for c in self.combatants):
            raise ValueError("cannot decide after victory")

    @property
    def hp_prior(self) -> float:
        return median(c.max_hp for c in self.combatants if not c.enemy and c.alive)


@dataclass(frozen=True)
class AutoAction:
    command: BattleCommand
    targets: tuple[int, ...] = ()
    spell_key: str = ""
    equipment_slot: str = ""

    def stable_key(self, snapshot: AutoBattleSnapshot) -> tuple:
        keys = {c.number: c.key for c in snapshot.combatants}
        return (
            self.command.value,
            self.spell_key,
            self.equipment_slot,
            tuple(keys[n] for n in self.targets),
        )


@dataclass(frozen=True)
class AutoActionEvaluation:
    action: AutoAction
    components: tuple[tuple[str, float], ...]
    cost: float
    score: float
    rounded_score: float
    defeat_fraction: float
    new_deaths: float
    current_cost: float
    next_gauge: float
    first_spell_types: int
    exclusion: str = ""

    def selection_key(self, snapshot: AutoBattleSnapshot) -> tuple:
        """Safety buckets first; exact risk and expenditure break score ties."""

        return (
            floor(16 * self.defeat_fraction),
            floor(4 * self.new_deaths),
            -self.rounded_score,
            self.defeat_fraction,
            self.new_deaths,
            self.current_cost,
            -self.next_gauge,
            -self.first_spell_types,
            self.action.stable_key(snapshot),
        )


@dataclass(frozen=True)
class AutoBattleDecision:
    action: AutoAction
    evaluations: tuple[AutoActionEvaluation, ...]
    excluded: tuple[tuple[str, str], ...]
    effect_version: int = EFFECT_VERSION
    case_count: int = CASE_COUNT
    forecast_turns: int = FORECAST_TURNS
    discount: float = DISCOUNT
    reason: str = "simulation"


@dataclass(frozen=True)
class AutoBattleLogEntry:
    sequence: int
    snapshot: AutoBattleSnapshot
    decision: AutoBattleDecision


class AutoBattleObservations:
    """Battle-only accounting from presented results, never HP differences."""

    def __init__(self) -> None:
        self.enemy_net_damage: dict[int, int] = {}
        self.enemy_mp_spent: dict[int, int] = {}

    def damage(self, index: int, amount: int) -> None:
        self.enemy_net_damage[index] = self.enemy_net_damage.get(index, 0) + amount

    def spend_mp(self, index: int, amount: int) -> None:
        self.enemy_mp_spent[index] = self.enemy_mp_spent.get(index, 0) + amount


def quantile(case: int, number: int, turn: int, target: int, purpose: int) -> float:
    j = ((turn * 10 + number) * 10 + target) * 16 + purpose
    return ((case + 0.5) / CASE_COUNT + ((37 * j) % 101) / 101) % 1.0
