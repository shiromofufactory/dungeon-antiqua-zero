"""Select and execute DA2-style field recovery for all six party members."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from collections.abc import Callable, Mapping, Sequence

from battle_magic import (
    DA2_DEFAULT_ITEM_SPELL_ABILITY,
    member_spell_ability,
    resolve_healing,
)
from member import Member, ProficiencyKind
from spell import Spell, SpellAction, SpellType
from state import AutoRecoveryConfig, AutoRecoveryMethod
from systems.inventory import InventorySystem
from systems.spell_progression import (
    MenuSpellProficiencyGrowth,
    apply_menu_spell_proficiency_growth,
)

RECOVERY_ITEM_KEYS = ("POTION", "REMEDY")


@dataclass(frozen=True)
class RecoveryStep:
    caster_index: int | None
    target_index: int
    spell: Spell
    item_key: str | None = None


@dataclass
class RecoveryResult:
    actions: int = 0
    items_used: dict[str, int] = field(default_factory=dict)
    hp_recovered: set[int] = field(default_factory=set)
    mp_spent: set[int] = field(default_factory=set)
    proficiency_growths: dict[int, MenuSpellProficiencyGrowth] = field(default_factory=dict)


def eligible_healer_keys(party: Sequence[Member]) -> tuple[str, ...]:
    """Use authored sacred aptitude, independent of current MP and learning."""

    return tuple(
        member.definition.key
        for member in party
        if member.proficiency(ProficiencyKind.SACRED).aptitude >= 1
    )


def valid_config_for_party(
    config: AutoRecoveryConfig, party: Sequence[Member]
) -> AutoRecoveryConfig:
    if config.healer_key is None or config.healer_key in eligible_healer_keys(party):
        return config
    return AutoRecoveryConfig(config.threshold, config.method)


def _can_cast(member: Member) -> bool:
    return (
        member.hp > 0
        and not member.paralyzed
        and not member.sleeping
        and not member.confused
    )


def _caster_indexes(
    party: Sequence[Member], spells: Mapping[str, Spell], config: AutoRecoveryConfig
) -> tuple[int, ...]:
    basic = spells.get("HEALING1")
    scored = []
    for index, member in enumerate(party):
        can_basic = (
            basic is not None
            and basic.is_learned_by(member)
            and member.mp >= basic.mp
            and _can_cast(member)
        )
        scored.append((index, member.mp * (0.5 if can_basic else 1)))
    ordered = sorted(scored, key=lambda pair: -pair[1])
    indexes = [index for index, _score in ordered]
    if config.healer_key is not None:
        selected = next(
            (i for i, member in enumerate(party) if member.definition.key == config.healer_key),
            None,
        )
        if selected is not None:
            indexes.remove(selected)
            indexes.insert(0, selected)
    return tuple(indexes)


def _targets(party: Sequence[Member]) -> tuple[int, ...]:
    def rank(index: int) -> float:
        member = party[index]
        if member.hp <= 0:
            return -1
        ratio = member.hp / member.max_hp
        return ratio / 2 if member.has_curable_ailment else ratio

    return tuple(sorted(range(len(party)), key=rank))


def _spell_for_target(
    caster: Member,
    target: Member,
    spells: Mapping[str, Spell],
    threshold: int,
) -> Spell | None:
    available = tuple(
        spell
        for spell in spells.values()
        if spell.type is SpellType.SACRED
        and spell.on_camp
        and not spell.to_enemy
        and spell.action in (SpellAction.HEAL, SpellAction.CURE, SpellAction.REVIVE)
        and spell.is_learned_by(caster)
        and caster.mp >= spell.mp
    )
    if target.is_dead:
        revives = (spell for spell in available if spell.action is SpellAction.REVIVE)
        return min(revives, key=lambda spell: (spell.mp, spell.level), default=None)
    if target.has_curable_ailment:
        combined = next(
            (spell for spell in available if spell.action is SpellAction.HEAL and spell.intensity == 0),
            None,
        )
        if combined is not None and target.hp < target.max_hp:
            return combined
        cures = (spell for spell in available if spell.action is SpellAction.CURE)
        cure = min(cures, key=lambda spell: spell.mp, default=None)
        if cure is not None:
            return cure
    if target.hp * 100 >= target.max_hp * threshold:
        return None
    heals = tuple(spell for spell in available if spell.action is SpellAction.HEAL)
    if not heals:
        return None
    ability = member_spell_ability(
        magic=caster.adjusted_abilities.magic,
        internal_level=caster.internal_level,
    )
    expected = tuple(
        (
            spell,
            resolve_healing(
                intensity=spell.intensity,
                ability=ability,
                current_hp=target.hp,
                max_hp=target.max_hp,
                random_factor=0.5,
            ).amount,
        )
        for spell in heals
    )
    needed = (target.max_hp * threshold + 99) // 100 - target.hp
    sufficient = [(spell, amount) for spell, amount in expected if amount >= needed]
    if sufficient:
        return min(sufficient, key=lambda pair: (pair[0].mp, pair[1]))[0]
    return max(expected, key=lambda pair: (pair[1], -pair[0].mp))[0]


def next_recovery_step(
    party: Sequence[Member],
    spells: Mapping[str, Spell],
    inventory: InventorySystem,
    config: AutoRecoveryConfig,
) -> RecoveryStep | None:
    """Choose one usable step, giving the selected method global priority."""

    config = valid_config_for_party(config, party)
    methods = (
        ("spell",)
        if config.method is AutoRecoveryMethod.SPELLS
        else ("spell", "item")
        if config.method is AutoRecoveryMethod.SPELLS_ITEMS
        else ("item", "spell")
    )
    for method in methods:
        for target_index in _targets(party):
            target = party[target_index]
            if method == "spell":
                for caster_index in _caster_indexes(party, spells, config):
                    caster = party[caster_index]
                    if not _can_cast(caster):
                        continue
                    spell = _spell_for_target(caster, target, spells, config.threshold)
                    if spell is not None:
                        return RecoveryStep(caster_index, target_index, spell)
            else:
                if target.hp <= 0:
                    continue
                keys = []
                if target.has_curable_ailment:
                    keys.append("REMEDY")
                if target.hp * 100 < target.max_hp * config.threshold:
                    keys.append("POTION")
                for key in keys:
                    if inventory.quantity(key) == 0:
                        continue
                    spell = spells.get("CURE" if key == "REMEDY" else "POTION")
                    if spell is not None:
                        return RecoveryStep(None, target_index, spell, key)
    return None


def execute_auto_recovery(
    party: Sequence[Member],
    spells: Mapping[str, Spell],
    inventory: InventorySystem,
    config: AutoRecoveryConfig,
    *,
    random_factor: Callable[[], float] = random.random,
) -> RecoveryResult:
    """Apply each step and recalculate until no usable recovery remains."""

    result = RecoveryResult()
    for _attempt in range(10_000):
        step = next_recovery_step(party, spells, inventory, config)
        if step is None:
            return result
        target = party[step.target_index]
        caster = party[step.caster_index] if step.caster_index is not None else None
        before = (target.hp, target.has_curable_ailment)
        if step.spell.action is SpellAction.HEAL:
            ability = (
                DA2_DEFAULT_ITEM_SPELL_ABILITY
                if caster is None
                else member_spell_ability(
                    magic=caster.adjusted_abilities.magic,
                    internal_level=caster.internal_level,
                )
            )
            healing = resolve_healing(
                intensity=step.spell.intensity,
                ability=ability,
                current_hp=target.hp,
                max_hp=target.max_hp,
                random_factor=random_factor(),
            )
            target.apply_healing(healing.amount, cure_ailments=healing.cures_ailments)
        elif step.spell.action is SpellAction.CURE:
            target.cure_ailments()
        elif step.spell.action is SpellAction.REVIVE:
            target.revive(step.spell.intensity)
        if (target.hp, target.has_curable_ailment) == before:
            raise RuntimeError("auto recovery action made no progress")
        if target.hp > before[0]:
            result.hp_recovered.add(step.target_index)
        if caster is not None:
            mp_before = caster.mp
            caster.mp -= step.spell.mp
            if caster.mp < mp_before:
                result.mp_spent.add(step.caster_index)
            growth = apply_menu_spell_proficiency_growth(
                caster, ProficiencyKind.SACRED, mp_spent=step.spell.mp
            )
            if growth.applied_amount > 0:
                previous = result.proficiency_growths.get(step.caster_index)
                result.proficiency_growths[step.caster_index] = (
                    growth
                    if previous is None
                    else MenuSpellProficiencyGrowth(
                        growth.kind, previous.before_total, growth.after_total
                    )
                )
        else:
            assert step.item_key is not None
            if not inventory.remove(step.item_key):
                raise RuntimeError("auto recovery item disappeared before use")
            result.items_used[step.item_key] = result.items_used.get(step.item_key, 0) + 1
        result.actions += 1
    raise RuntimeError("auto recovery exceeded its action limit")


__all__ = [
    "RECOVERY_ITEM_KEYS",
    "RecoveryResult",
    "RecoveryStep",
    "eligible_healer_keys",
    "execute_auto_recovery",
    "next_recovery_step",
    "valid_config_for_party",
]
