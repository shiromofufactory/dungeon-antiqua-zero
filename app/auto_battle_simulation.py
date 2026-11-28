"""Bounded battle forecasts using the live physical, magic, and gauge rules."""

from __future__ import annotations

from dataclasses import dataclass, replace

if __package__:
    from .battle_breath import member_breath_hp_cost, resolve_fire_breath, resolve_poison_breath
    from .auto_battle_model import (
        CASE_COUNT,
        AutoAction,
        AutoBattleSnapshot,
        AutoCombatant,
        ItemMode,
        quantile,
    )
    from .battle_commands import (
        BattleCommand,
        BattleCommandContext,
        member_attack_reach,
        member_can_attack,
        resolve_battle_commands,
        selectable_attack_target_indexes,
    )
    from .battle_layout import MonsterPlacement, find_monster_placement, monster_revival_placement_available
    from .battle_magic import (
        DA2_DEFAULT_ITEM_SPELL_ABILITY,
        MAX_PROTECTION_LEVEL,
        PRAY_SUCCESS_ROLL_COUNT,
        SPELL_REFLECTION_ROLL_COUNT,
        battle_healing_amount,
        black_wind_has_effect,
        TEMPTATION_RATE,
        debuff_turn_range,
        has_dispellable_buffs,
        member_spell_ability,
        member_spell_modifier,
        modified_defense,
        poison_tick_damage,
        resolve_healing,
        resolve_pray_recovery,
        resolve_recovery_amount,
        resolve_spell_damage,
        resolve_status_spell,
        spell_cast_delay,
        spell_reflection_chance,
        spell_resistances,
    )
    from .battle_physical import (
        CONSTRICTION_HIT_ROLL_COUNT,
        INNER_STEEL_SKILL_KEY,
        PHYSICAL_EFFECT_RESISTANCE,
        PHYSICAL_HIT_ROLL_COUNT,
        PHYSICAL_STATUS_EFFECTS,
        drain_healing_amount,
        inner_steel_attack,
        physical_weapon_is_effective,
        resolve_monster_attack_effects,
        resolve_physical_additional_effect,
        resolve_physical_attack,
        counter_attack_succeeds,
        resolve_earthquake_attack,
        weapon_can_drain,
    )
    from .battle_speed import MAX_SPEED_MODIFIER, SLOW_GAUGE_ADJUSTMENT, modified_agility
    from .battle_timeline import (
        GAUGE_READY_VALUE,
        TimelineEntry,
        TimelineOrder,
        adjust_timeline_entry_gauge,
        complete_timeline_action,
        insert_timeline_actor,
        ready_timeline_head,
    )
    from .item import AdditionalEffect, ItemEquipType, ItemSpecial
    from .member import EquipmentSlot, Gender
    from .monster import MonsterSpecialAction, promote_rear_monsters_if_front_empty
    from .monster_ai import (
        MonsterAction, MonsterAreaAttackCooldown, MonsterSpellAction, MonsterSpellTarget,
        evaluate_monster_spell, evaluate_monster_support_spell,
        is_monster_area_attack_spell,
        monster_action_candidates, monster_attack_targets, monster_spell_evaluation_order,
        prefer_monster_targets, rotate_monster_action,
    )
    from .resistance import ResistanceType
    from .spell import SPELL_PROFICIENCY_BY_TYPE, Spell, SpellAction, SpellType
else:
    from battle_breath import member_breath_hp_cost, resolve_fire_breath, resolve_poison_breath
    from auto_battle_model import (
        CASE_COUNT,
        AutoAction,
        AutoBattleSnapshot,
        AutoCombatant,
        ItemMode,
        quantile,
    )
    from battle_commands import (
        BattleCommand,
        BattleCommandContext,
        member_attack_reach,
        member_can_attack,
        resolve_battle_commands,
        selectable_attack_target_indexes,
    )
    from battle_layout import MonsterPlacement, find_monster_placement, monster_revival_placement_available
    from battle_magic import (
        DA2_DEFAULT_ITEM_SPELL_ABILITY,
        MAX_PROTECTION_LEVEL,
        PRAY_SUCCESS_ROLL_COUNT,
        SPELL_REFLECTION_ROLL_COUNT,
        battle_healing_amount,
        black_wind_has_effect,
        TEMPTATION_RATE,
        debuff_turn_range,
        has_dispellable_buffs,
        member_spell_ability,
        member_spell_modifier,
        modified_defense,
        poison_tick_damage,
        resolve_healing,
        resolve_pray_recovery,
        resolve_recovery_amount,
        resolve_spell_damage,
        resolve_status_spell,
        spell_cast_delay,
        spell_reflection_chance,
        spell_resistances,
    )
    from battle_physical import (
        CONSTRICTION_HIT_ROLL_COUNT,
        INNER_STEEL_SKILL_KEY,
        PHYSICAL_EFFECT_RESISTANCE,
        PHYSICAL_HIT_ROLL_COUNT,
        PHYSICAL_STATUS_EFFECTS,
        drain_healing_amount,
        inner_steel_attack,
        physical_weapon_is_effective,
        resolve_monster_attack_effects,
        resolve_physical_additional_effect,
        resolve_physical_attack,
        counter_attack_succeeds,
        resolve_earthquake_attack,
        weapon_can_drain,
    )
    from battle_speed import MAX_SPEED_MODIFIER, SLOW_GAUGE_ADJUSTMENT, modified_agility
    from battle_timeline import (
        GAUGE_READY_VALUE,
        TimelineEntry,
        TimelineOrder,
        adjust_timeline_entry_gauge,
        complete_timeline_action,
        insert_timeline_actor,
        ready_timeline_head,
    )
    from item import AdditionalEffect, ItemEquipType, ItemSpecial
    from member import EquipmentSlot, Gender
    from monster import MonsterSpecialAction, promote_rear_monsters_if_front_empty
    from monster_ai import (
        MonsterAction, MonsterAreaAttackCooldown, MonsterSpellAction, MonsterSpellTarget,
        evaluate_monster_spell, evaluate_monster_support_spell,
        is_monster_area_attack_spell,
        monster_action_candidates, monster_attack_targets, monster_spell_evaluation_order,
        prefer_monster_targets, rotate_monster_action,
    )
    from resistance import ResistanceType
    from spell import SPELL_PROFICIENCY_BY_TYPE, Spell, SpellAction, SpellType


# Kept deliberately separate because monster casters support fewer actions.
ALLY_SPELL_ACTIONS = frozenset(
    (
        SpellAction.HEAL,
        SpellAction.MANA,
        SpellAction.DAMAGE,
        SpellAction.BLOOD_SUCK,
        SpellAction.SLEEP,
        SpellAction.CONFUSE,
        SpellAction.SLOW,
        SpellAction.BREAK,
        SpellAction.PROTECTION,
        SpellAction.MAGIC_SHIELD,
        SpellAction.PURGE,
        SpellAction.IDENTIFY,
        SpellAction.HASTE,
        SpellAction.SILENCE,
        SpellAction.CURE,
        SpellAction.REVIVE,
    )
)
ENEMY_SPELL_ACTIONS = frozenset(
    (SpellAction.SLEEP, SpellAction.CONFUSE, SpellAction.SLOW, SpellAction.BREAK, SpellAction.SILENCE)
)
RECOVERY_ACTIONS = frozenset(
    (SpellAction.HEAL, SpellAction.CURE, SpellAction.REVIVE)
)
DIRECT_COMMANDS = frozenset(
    (
        BattleCommand.ATTACK,
        BattleCommand.AMBUSH,
        BattleCommand.AIM,
        BattleCommand.FOCUS,
        BattleCommand.HIDE,
        BattleCommand.IDENTIFY,
        BattleCommand.COVER,
        BattleCommand.DEFEND,
    )
)
@dataclass(slots=True)
class ForecastActor:
    spec: AutoCombatant
    hp: int
    max_hp: int
    mp: int
    front: bool
    poisoned: bool
    sleeping: int
    silenced: int
    paralyzed: bool
    confused: int
    stunned: bool
    protection: int
    speed: int
    hidden: bool
    defending: bool
    cover: int | None
    focus: int | None
    removed: bool = False
    magic_shield: bool = False
    slow_turns: int = 0
    defense_down_turns: int = 0
    action_rotation_index: int | None = None

    @classmethod
    def create(cls, spec: AutoCombatant) -> ForecastActor:
        return cls(
            spec,
            spec.hp,
            spec.max_hp,
            spec.mp,
            spec.front,
            spec.poisoned,
            spec.sleeping,
            spec.silenced,
            spec.paralyzed,
            spec.confused,
            spec.stunned,
            spec.protection,
            spec.speed,
            spec.hidden,
            spec.defending,
            spec.cover,
            spec.focus,
            magic_shield=spec.magic_shield,
            slow_turns=spec.slow_turns,
            defense_down_turns=spec.defense_down_turns,
            action_rotation_index=spec.action_rotation_index,
        )

    @property
    def is_alive(self) -> bool:
        return self.hp > 0 and not self.removed

    @property
    def is_front_row(self) -> bool:
        return self.front

    @is_front_row.setter
    def is_front_row(self, value: bool) -> None:
        self.front = value

    @property
    def equipment(self):
        return self.spec.equipment

    def proficiency(self, kind):
        return next(p for p in self.spec.proficiencies if p.kind is kind)

    def has_skill(self, key: str) -> bool:
        return key in self.spec.skills

    def weapon_attack(self, attack: int) -> int:
        if self.has_skill(INNER_STEEL_SKILL_KEY):
            return inner_steel_attack(attack, self.hp, self.max_hp)
        return attack

    @property
    def agility(self) -> int:
        return modified_agility(self.spec.agility, self.speed)

    @property
    def defense(self) -> int:
        return modified_defense(self.spec.defense, self.protection)

    @property
    def spell_resistances(self) -> frozenset[ResistanceType]:
        return spell_resistances(self.spec.resistances, self.magic_shield)

    @property
    def evasion(self) -> int:
        return (
            self.spec.evasion
            if self.spec.enemy
            else max(0, self.spec.evasion + max(0, (self.agility - 20) * 2))
        )

    @property
    def actionable(self) -> bool:
        return self.is_alive and not (
            self.sleeping or self.paralyzed or self.stunned or self.confused
        )

    @property
    def is_defending(self) -> bool:
        return self.defending and self.actionable

    @property
    def incapacitated_for_physical_hit(self) -> bool:
        return bool(self.sleeping or self.confused)

    def focus_group(self) -> tuple:
        """Combat state that must agree before HP can decide between targets."""

        return (
            self.spec.species_key or self.spec.key, self.max_hp, self.front,
            self.spec.attack, self.spec.hit, self.defense, self.evasion,
            self.spec.spell_defense, self.spec.resistances, self.spec.weaknesses,
            self.spec.tribe, self.spec.shadow, self.agility, self.mp, self.defending,
            self.poisoned, self.sleeping, self.confused, self.paralyzed, self.stunned,
            self.silenced, self.speed, self.protection, self.slow_turns, self.defense_down_turns,
            self.magic_shield,
            self.action_rotation_index,
        )

    def damage(self, amount: int, *, poison: bool = False) -> int:
        old = self.hp
        self.hp = max(0, self.hp - amount)
        if amount > 0 and not poison:
            self.sleeping = self.confused = 0
        if self.hp == 0:
            self.clear_defeated_conditions()
        return old - self.hp

    def clear_defeated_conditions(self) -> None:
        self.poisoned = self.paralyzed = self.stunned = self.hidden = False
        self.magic_shield = self.defending = False
        self.sleeping = self.confused = self.silenced = 0
        self.protection = self.speed = self.slow_turns = self.defense_down_turns = 0
        self.focus = self.cover = None

    def drain(self, damage: int) -> None:
        self.hp += drain_healing_amount(damage=damage, hp=self.hp, max_hp=self.max_hp)

    def apply_haste(self) -> None:
        self.speed = min(MAX_SPEED_MODIFIER, self.speed + 1)
        self.slow_turns = 0

    def apply_protection(self) -> None:
        self.protection = min(MAX_PROTECTION_LEVEL, self.protection + 1)
        self.defense_down_turns = 0

    def purge_buffs(self) -> None:
        self.protection = min(self.protection, 0)
        self.speed = min(self.speed, 0)
        self.magic_shield = False

    @property
    def can_recover_with_black_wind(self) -> bool:
        return self.is_alive and black_wind_has_effect(
            poisoned=self.poisoned, sleeping=self.sleeping,
            confused=self.confused, silenced=self.silenced,
            defense_modifier=self.protection, speed_modifier=self.speed,
        )

    def recover_with_black_wind(self) -> None:
        self.poisoned = False
        self.sleeping = self.confused = self.silenced = 0
        if self.protection < 0:
            self.protection = self.defense_down_turns = 0
        if self.speed < 0:
            self.speed = self.slow_turns = 0

    def interrupt_focus(self) -> None:
        if (
            not self.is_alive
            or self.sleeping
            or self.paralyzed
            or self.stunned
            or self.confused
        ):
            self.focus = None


class BattleForecast:
    """One independent case; only its private actors and timeline are mutated."""

    def __init__(self, snapshot: AutoBattleSnapshot, case: int) -> None:
        self.snapshot = snapshot
        self.case = case
        self.actors = {
            c.number: ForecastActor.create(c) for c in snapshot.combatants
        }
        self.order = TimelineOrder(
            tuple(
                TimelineEntry(n, self.actors[n].agility, g) for n, g in snapshot.gauges
            )
        )
        self.spells = {s.key: s for s in snapshot.spells}
        self.consumables = tuple(
            (item.key, self.spells[item.use_spell_key])
            for item, count in snapshot.consumables
            if count > 0
            and item.key in snapshot.policy.config.allowed_items
            and item.use_spell_key in self.spells
        )
        self.item_quantities = {item.key: count for item, count in snapshot.consumables}
        self.turns = {n: 0 for n in self.actors}
        self.start_hp = {n: a.hp for n, a in self.actors.items()}
        self.fixed_breath_hp = False
        self.breath_hp: dict[tuple[int, int, MonsterAction], int] = {}
        self.original_alive = frozenset(
            n for n, a in self.actors.items() if not a.spec.enemy and a.is_alive
        )
        self.original_enemies = frozenset(
            n for n, a in self.actors.items() if a.spec.enemy and a.is_alive
        )
        self.known = {}
        for actor in self.actors.values():
            if actor.spec.enemy:
                species = actor.spec.species_key or actor.spec.key
                self.known.setdefault(species, set()).update(actor.spec.known_fields)
        self.hp_shown = {n for n, a in self.actors.items() if a.spec.hp_displayed}
        self.surprise = set(snapshot.surprise_pending)
        self.surprise_deferred = set(snapshot.surprise_deferred)
        self.original_rows = dict(snapshot.surprise_original_rows)
        self.monster_area_attack_cooldown = MonsterAreaAttackCooldown(
            snapshot.monster_area_attack_attacker,
        )
        self.info = 0.0
        self.died: set[int] = set()
        self.defeated = False
        self.focus_completed = False
        self.expected_cache: dict[tuple, tuple[int, ...]] = {}
        self.command_cache: dict[tuple, tuple] = {}
        self.timeline_cache: dict[tuple, TimelineOrder] = {}
        self.ally_actors = tuple(a for a in self.actors.values() if not a.spec.enemy)
        self.enemy_actors = tuple(a for a in self.actors.values() if a.spec.enemy)
        # Use a fixed slot for alternative single-target attacks in every case.
        self.single_enemy_roll_target = min(a.spec.number for a in self.enemy_actors)

    def allies(self) -> tuple[ForecastActor, ...]:
        return tuple(a for a in self.ally_actors if a.is_alive)

    def enemies(self) -> tuple[ForecastActor, ...]:
        return tuple(a for a in self.enemy_actors if a.is_alive)

    @property
    def ended(self) -> bool:
        return self.party_defeated or not self.enemies()

    @property
    def party_defeated(self) -> bool:
        allies = self.allies()
        return not allies or all(a.paralyzed for a in allies)

    def roll(
        self, actor: ForecastActor, target: int, purpose: int, case: int | None = None
    ) -> float:
        return quantile(
            self.case if case is None else case,
            actor.spec.number,
            self.turns[actor.spec.number],
            target,
            purpose,
        )

    def attack_targets(
        self, actor: ForecastActor, command: BattleCommand
    ) -> tuple[int, ...]:
        if not actor.spec.weapons:
            return ()
        enemies = self.enemies()
        if command is BattleCommand.IAI:
            return tuple(enemy.spec.number for enemy in enemies)
        indexes = selectable_attack_target_indexes(
            attacker_is_front_row=actor.front,
            weapon_reach=member_attack_reach(actor),
            monsters=enemies,
            unrestricted_range=command is BattleCommand.AMBUSH,
        )
        return tuple(enemies[i].spec.number for i in indexes)

    def spell_targets(self, actor: ForecastActor, spell: Spell) -> tuple[int, ...]:
        if actor.spec.enemy:
            if not spell.to_enemy and spell.action is SpellAction.REVIVE:
                return self.monster_revival_targets()
            targets = (
                tuple(a for a in self.allies() if not a.hidden)
                if spell.to_enemy
                else self.enemies()
            )
            if spell.action is SpellAction.HASTE:
                targets = tuple(a for a in targets if a.speed < MAX_SPEED_MODIFIER)
            elif spell.action is SpellAction.PROTECTION:
                targets = tuple(a for a in targets if a.protection < MAX_PROTECTION_LEVEL)
            elif spell.action is SpellAction.HEAL:
                targets = tuple(a for a in targets if a.hp < a.max_hp)
        elif spell.to_enemy:
            targets = self.enemies()
            if spell.action is SpellAction.SLOW:
                targets = tuple(a for a in targets if a.speed > -1)
            elif spell.action is SpellAction.BREAK:
                targets = tuple(
                    a
                    for a in targets
                    if a.protection > -1 and a.defense > 0
                )
            elif spell.action is SpellAction.SILENCE:
                targets = tuple(
                    a for a in targets if a.spec.spells and a.silenced <= 0
                )
        else:
            if spell.action is SpellAction.REVIVE:
                targets = tuple(
                    a for a in self.ally_actors if not a.is_alive and not a.removed
                )
            else:
                targets = tuple(
                    a
                    for a in self.allies()
                    if not a.hidden or (not spell.to_all and a is actor)
                )
            if spell.action is SpellAction.PROTECTION:
                targets = tuple(a for a in targets if a.protection < MAX_PROTECTION_LEVEL)
            elif spell.action is SpellAction.HASTE:
                targets = tuple(a for a in targets if a.speed < MAX_SPEED_MODIFIER)
            elif spell.action is SpellAction.CURE:
                targets = tuple(a for a in targets if self.cure_spell_curable(a))
            elif spell.action is SpellAction.MANA:
                targets = tuple(
                    a
                    for a in targets
                    if a.mp < a.spec.max_mp
                    and any(
                        a.proficiency(kind).level > 0
                        for kind in SPELL_PROFICIENCY_BY_TYPE.values()
                    )
                )
        if spell.action is SpellAction.MAGIC_SHIELD:
            targets = tuple(a for a in targets if not a.magic_shield)
        return tuple(a.spec.number for a in targets)

    def command_options(self, actor):
        allies, enemies = self.allies(), self.enemies()
        key = (
            actor.spec.number,
            actor.front,
            actor.hidden,
            bool(actor.silenced),
            tuple((a.spec.number, a.front) for a in allies),
            tuple((a.spec.number, a.front) for a in enemies),
        )
        if key not in self.command_cache:
            self.command_cache[key] = resolve_battle_commands(
                actor,
                allies,
                enemies,
                context=BattleCommandContext(
                    actor_hidden=actor.hidden,
                    silenced=bool(actor.silenced),
                    item_available=True,
                ),
                party_front_rows=tuple(a.front for a in allies),
            )
        return self.command_cache[key]

    def candidates(
        self, number: int, excluded: list | None = None, *, continuation: bool = False
    ) -> tuple[AutoAction, ...]:
        actor = self.actors[number]

        def reject(key, reason):
            if excluded is not None:
                excluded.append((key, reason))

        actions: list[AutoAction] = []
        for option in self.command_options(actor):
            command = option.command
            if command is BattleCommand.FORMATION:
                reject(command.value, "formation_policy")
                continue
            if continuation and command not in (
                BattleCommand.ATTACK,
                BattleCommand.AMBUSH,
                BattleCommand.SPELL,
                BattleCommand.ITEM,
                BattleCommand.DEFEND,
            ):
                continue
            if not option.enabled:
                reject(command.value, "disabled")
                continue
            if command in (
                BattleCommand.ATTACK,
                BattleCommand.AMBUSH,
                BattleCommand.AIM,
                BattleCommand.FOCUS,
            ):
                actions.extend(
                    AutoAction(command, (n,))
                    for n in self.attack_targets(actor, command)
                )
            elif command is BattleCommand.IAI:
                targets = self.attack_targets(actor, command)
                if targets:
                    actions.append(AutoAction(command, targets))
            elif command is BattleCommand.BREATH:
                actions.append(AutoAction(command, tuple(a.spec.number for a in self.enemies())))
            elif command is BattleCommand.IDENTIFY:
                actions.extend(
                    AutoAction(command, (a.spec.number,)) for a in self.enemies()
                )
            elif command is BattleCommand.PRAY:
                if actor.mp < actor.spec.max_mp:
                    actions.append(AutoAction(command, (number,)))
            elif command is BattleCommand.COVER:
                actions.extend(
                    AutoAction(command, (a.spec.number,))
                    for a in self.allies()
                    if a is not actor and not a.hidden
                )
            elif command in DIRECT_COMMANDS:
                actions.append(AutoAction(command))
            elif command is BattleCommand.SPELL:
                for spell in actor.spec.spells:
                    if continuation and spell.action not in RECOVERY_ACTIONS:
                        continue
                    if not self.spell_allowed(actor, spell):
                        reject(spell.key, "spell_policy")
                        continue
                    if spell.mp > actor.mp:
                        reject(spell.key, "mp_lack")
                        continue
                    actions.extend(
                        self.effect_candidates(actor, command, spell, reject=reject)
                    )
            elif command is BattleCommand.ITEM:
                if self.snapshot.policy.item_mode is ItemMode.NEVER:
                    reject(command.value, "item_policy")
                    continue
                for slot in EquipmentSlot:
                    item = actor.equipment.item_at(slot)
                    if item is None or not (
                        item.is_weapon or item.equip_type is ItemEquipType.ARM
                    ):
                        continue
                    if item.breaks_on_use:
                        reject(item.key, "breaks_on_use")
                        continue
                    spell = self.spells.get(item.use_spell_key)
                    if (
                        continuation
                        and spell is not None
                        and spell.action not in RECOVERY_ACTIONS
                    ):
                        continue
                    if spell is not None:
                        actions.extend(
                            self.effect_candidates(
                                actor, command, spell, slot.value, reject
                            )
                        )
                for item_key, spell in self.consumables:
                    if self.item_quantities[item_key] <= 0:
                        continue
                    if continuation and spell.action not in RECOVERY_ACTIONS:
                        continue
                    actions.extend(
                        self.effect_candidates(
                            actor, command, spell, reject=reject, item_key=item_key
                        )
                    )
            else:
                reject(command.value, "unsupported_command")
        target_keys = {number: combatant.spec.key for number, combatant in self.actors.items()}
        return tuple(sorted(
            set(actions), key=lambda action: action.stable_key(self.snapshot, target_keys=target_keys),
        ))

    def spell_allowed(self, actor: ForecastActor, spell: Spell) -> bool:
        return self.snapshot.policy.config.uses_spell(
            actor.spec.key.removeprefix("pc:"), spell.type.value
        )

    def effect_candidates(
        self, actor, command, spell, slot="", reject=lambda *_: None, *, item_key=""
    ):
        if not spell.on_battle or spell.action not in ALLY_SPELL_ACTIONS:
            reject(spell.key, "unsupported_effect")
            return ()
        targets = self.spell_targets(actor, spell)
        if not targets:
            reject(spell.key, "no_targets")
            return ()
        if spell.action is SpellAction.PURGE and not any(
            has_dispellable_buffs(target.protection, target.speed, target.magic_shield)
            for target in (self.actors[number] for number in targets)
        ):
            reject(spell.key, "no_change")
            return ()
        if spell.action in (
            SpellAction.SLEEP,
            SpellAction.CONFUSE,
            SpellAction.SLOW,
            SpellAction.BREAK,
            SpellAction.SILENCE,
        ):
            effective = tuple(
                n
                for n in targets
                if spell.attribute not in self.actors[n].spell_resistances
            )
            if spell.to_all:
                # Mixed groups still use the full manual target set; only an
                # entirely resistant group makes the whole action pointless.
                if not effective:
                    reject(spell.key, "known_resistance")
                    return ()
            else:
                for n in targets:
                    if n not in effective:
                        reject(
                            spell.key + "@" + self.actors[n].spec.key,
                            "known_resistance",
                        )
                targets = effective
                if not targets:
                    return ()
        # Single-target consumables must pass battle's missing-HP check.
        if spell.action is SpellAction.HEAL:
            targets = tuple(
                n
                for n in targets
                if self.actors[n].hp < self.actors[n].max_hp
                or (
                    (not item_key or spell.to_all)
                    and spell.intensity == 0
                    and self.curable(self.actors[n])
                )
            )
        if not targets:
            reject(spell.key, "no_change")
            return ()
        if spell.to_all:
            # Apply a whole-party spell to the same full legal set as manual use.
            return (
                AutoAction(command, self.spell_targets(actor, spell), spell.key, slot, item_key),
            )
        return tuple(AutoAction(command, (n,), spell.key, slot, item_key) for n in targets)

    @staticmethod
    def curable(actor) -> bool:
        return bool(
            actor.poisoned
            or actor.sleeping
            or actor.paralyzed
            or actor.confused
            or actor.stunned
        )

    @staticmethod
    def cure_spell_curable(actor) -> bool:
        """Return whether dedicated CURE can remove one of its four ailments."""

        return bool(
            actor.poisoned
            or actor.sleeping
            or actor.paralyzed
            or actor.confused
        )

    def treats_poison_or_sleep(self, action: AutoAction) -> bool:
        spell = self.spells[action.spell_key]
        return (
            spell.action is SpellAction.CURE
            or (spell.action is SpellAction.HEAL and spell.intensity == 0)
        ) and any(
            self.actors[n].poisoned or self.actors[n].sleeping for n in action.targets
        )

    def delay(self, actor: ForecastActor, action: AutoAction) -> float:
        if action.command is BattleCommand.AIM:
            return -16.0
        if action.command is BattleCommand.IAI:
            return -32.0
        if action.spell_key:
            spell = self.spells[action.spell_key]
            if spell.type is SpellType.ITEM:
                return 0.0
            level = actor.proficiency(SPELL_PROFICIENCY_BY_TYPE[spell.type]).level
            reduced = any(
                i.special is ItemSpecial.SPL_REDUCE_WT
                for i in actor.equipment.equipped_items()
            )
            return -float(spell_cast_delay(spell_level=level, reduced_wait=reduced))
        return 0.0

    def cost(self, actor: ForecastActor, action: AutoAction) -> float:
        if action.command is not BattleCommand.SPELL:
            return 0.0
        m = self.spells[action.spell_key].mp
        if not m:
            return 0.0
        costs = (
            s.mp
            for s in actor.spec.spells
            if s.action in RECOVERY_ACTIONS and self.spell_allowed(actor, s)
        )
        return mp_cost(actor.mp, actor.spec.max_mp, m, min(costs, default=0))

    def recovery_action(
        self, number: int, actions: tuple[AutoAction, ...]
    ) -> tuple[AutoAction, str] | None:
        """Choose mandatory recovery from current allies without advancing time."""

        actor = self.actors[number]
        heals = [
            a
            for a in actions
            if a.spell_key and self.spells[a.spell_key].action is SpellAction.HEAL
        ]
        cures = [
            a
            for a in actions
            if a.spell_key and self.spells[a.spell_key].action is SpellAction.CURE
        ]
        revives = [
            a
            for a in actions
            if a.spell_key and self.spells[a.spell_key].action is SpellAction.REVIVE
        ]
        for stage in ("urgent", "cure", "heal", "revive"):
            targets = list(
                (a for a in self.ally_actors if not a.is_alive and not a.removed)
                if stage == "revive"
                else self.allies()
            )
            if stage == "cure":
                ordering = {e.actor: i for i, e in enumerate(self.order.entries)}
                targets.sort(
                    key=lambda a: (ordering.get(a.spec.number, 999), a.spec.number)
                )
            elif stage != "revive":
                targets.sort(key=lambda a: (a.hp / a.max_hp, a.spec.number))
            else:
                targets.sort(key=lambda a: a.spec.number)
            for target in targets:
                if stage == "urgent" and target.hp * 100 > target.max_hp * 35:
                    continue
                if stage == "heal" and target.hp * 100 >= target.max_hp * 60:
                    continue
                if stage == "cure" and not (target.paralyzed or target.confused or target.stunned):
                    continue
                if stage == "revive":
                    available = [
                        a for a in revives if target.spec.number in a.targets
                    ]
                    if not available:
                        continue
                    action = min(
                        available,
                        key=lambda a: (
                            -max(
                                1,
                                target.max_hp
                                * self.spells[a.spell_key].intensity
                                // 100,
                            ),
                            self.cost(actor, a),
                            -self.delay(actor, a),
                            a.stable_key(self.snapshot),
                        ),
                    )
                    return action, stage
                if stage == "cure":
                    available = [
                        a for a in heals
                        if target.spec.number in a.targets and self.spells[a.spell_key].intensity == 0
                    ]
                    if target.paralyzed or target.confused:
                        available.extend(a for a in cures if target.spec.number in a.targets)
                else:
                    available = [
                        a for a in heals if target.spec.number in a.targets
                    ]
                if not available:
                    continue

                def recovery(a, target=target):
                    spell = self.spells[a.spell_key]
                    if spell.action is SpellAction.CURE:
                        return 0
                    return self.heal_result(actor, target, spell, 0.0).amount

                adequate = [
                    a
                    for a in available
                    if (target.hp + recovery(a)) * 100 >= target.max_hp * 60
                ]
                pool = adequate or available
                action = min(
                    pool,
                    key=lambda a: (
                        0
                        if adequate or stage == "cure"
                        else -min(recovery(a), target.max_hp - target.hp),
                        bool(a.item_key),
                        self.cost(actor, a),
                        -self.delay(actor, a),
                        a.stable_key(self.snapshot),
                    ),
                )
                return action, stage
        return None

    def continuation(self, number: int, weights: dict[int, float]) -> AutoAction:
        actor = self.actors[number]
        actions = self.candidates(number, continuation=True)
        recovery = self.recovery_action(number, actions)
        if recovery is not None:
            return recovery[0]
        command = BattleCommand.AMBUSH if actor.hidden else BattleCommand.ATTACK
        targets = {}
        for action in actions:
            if action.command is command:
                target = self.actors[action.targets[0]]
                targets.setdefault(target.focus_group(), []).append(action)
        if not targets:
            return AutoAction(BattleCommand.DEFEND)

        def priority(action):
            target = self.actors[action.targets[0]]
            samples = self.physical_damage_samples(actor, target, action)
            weight = weights.get(target.spec.number, 1)
            return (
                -weight * sum(damage >= target.hp for damage in samples) / CASE_COUNT,
                -weight * min(self.expected_damage(actor, target, action), target.hp)
                / target.max_hp,
                action.targets,
            )

        next_actors = self.order.actors[1:2]

        def focus_priority(action):
            target = self.actors[action.targets[0]]
            stops_next_turn = action.targets == next_actors and all(
                damage >= target.hp for damage in self.physical_damage_samples(actor, target, action)
            )
            return not stops_next_turn, target.hp, action.targets

        # Focus equivalent targets before comparing their sampled threat weights.
        attacks = (min(group, key=focus_priority) for group in targets.values())
        return min(attacks, key=priority)

    def expected_damage(self, actor, target, action):
        return sum(self.physical_damage_samples(actor, target, action)) / CASE_COUNT

    def physical_damage_samples(self, actor, target, action) -> tuple[int, ...]:
        key = (
            actor.spec.number,
            target.spec.number,
            target.spec.key,
            actor.agility,
            target.defense,
            target.evasion,
            target.incapacitated_for_physical_hit,
            target.spec.tribe,
            target.spec.weaknesses,
            target.spec.resistances,
            actor.hidden,
            action.command,
            self.turns[actor.spec.number],
        )
        if key not in self.expected_cache:
            self.expected_cache[key] = tuple(
                sum(
                    r.damage for r in self.physical_results(actor, target, action, k)
                )
                for k in range(CASE_COUNT)
            )
        return self.expected_cache[key]

    def _physical_roll_target(self, action: AutoAction, target: ForecastActor) -> int:
        if action.command is not BattleCommand.IAI and target.spec.enemy:
            return self.single_enemy_roll_target
        return target.spec.number

    def physical_results(self, actor, target, action, case=None, *, roll_target=None):
        results = []
        if roll_target is None:
            roll_target = self._physical_roll_target(action, target)
        weapons = (
            actor.spec.weapons[:1]
            if action.command is BattleCommand.IAI
            else actor.spec.weapons
        )
        for hand, weapon in enumerate(weapons):
            attack = weapon.attack
            if action.command is BattleCommand.IAI:
                if weapon.iai_attack is None:
                    raise ValueError("Iai requires a right-hand katana attack value")
                attack = weapon.iai_attack
            attack = actor.weapon_attack(attack)
            if action.command is BattleCommand.FOCUS:
                attack *= 2
            effective = physical_weapon_is_effective(
                effective_tribe=weapon.effective_tribe,
                target_tribe=target.spec.tribe,
                attribute=weapon.attribute,
                target_weaknesses=target.spec.weaknesses,
                target_resistances=target.spec.resistances,
            )
            results.append(
                resolve_physical_attack(
                    attack=attack,
                    hit=weapon.hit,
                    target_defense=target.defense,
                    target_evasion=target.evasion,
                    target_defending=target.is_defending,
                    hit_roll=int(
                        self.roll(actor, roll_target, 2 + hand * 3, case) * 100
                    ),
                    target_incapacitated=target.incapacitated_for_physical_hit,
                    attacker_hidden=actor.hidden,
                    hit_value_bonus=100 if action.command is BattleCommand.AIM else 0,
                    attacker_has_power_hit=actor.has_skill("Power Hit"),
                    weapon_has_power_hit=weapon.power_hit,
                    weapon_effective=effective,
                    critical_rate_scale=weapon.critical_scale,
                    critical_roll=int(
                        self.roll(actor, roll_target, 3 + hand * 3, case) * 100
                    ),
                )
            )
        return results

    def physical(self, actor, action):
        counters = []
        for number in action.targets:
            target = self.actors[number]
            if self._physical_target(actor, target, action):
                counters.append(target)
            promote_rear_monsters_if_front_empty(self.enemy_actors)
        actor.hidden = False
        for defender in counters:
            if not actor.is_alive:
                break
            if not defender.is_alive or defender.sleeping or defender.confused or defender.stunned:
                continue
            target = self.covering(actor.spec.number)
            target.hidden = False
            self.enemy_physical(defender, target)

    def _physical_target(self, actor, target, action, *, is_counter=False):
        # Live execution resolves both hands before applying either result.
        roll_target = (
            target.spec.number if is_counter else self._physical_roll_target(action, target)
        )
        results = self.physical_results(actor, target, action, roll_target=roll_target)
        hidden = actor.hidden
        defending = target.is_defending
        counter = False
        for hand, (weapon, result) in enumerate(zip(actor.spec.weapons, results)):
            self.reveal(target, "profile")
            if weapon.attribute is not None:
                self.reveal(target, weapon.attribute.value)
            if not target.is_alive:
                continue
            if result.hit:
                target.damage(result.damage)
                if weapon_can_drain(weapon.effect, target.spec.resistances):
                    actor.drain(result.damage)
            if (
                hand == 0 and not is_counter and target.spec.enemy
                and MonsterSpecialAction.COUNTER in target.spec.special_actions
            ):
                counter = counter_attack_succeeds(
                    attacker_agility=actor.agility, defender_agility=target.agility,
                    attacker_front=actor.front, defender_front=target.front,
                    defender_actionable=target.is_alive and not (
                        target.sleeping or target.confused or target.stunned
                    ),
                    roll=int(self.roll(actor, roll_target, 16) * 20),
                )
            if not result.hit:
                continue
            effects = []
            if weapon.effect in PHYSICAL_STATUS_EFFECTS:
                effects.append(
                    (
                        weapon.effect,
                        weapon.effect is AdditionalEffect.DEATH
                        and actor.has_skill("Lethal"),
                    )
                )
            if (
                actor.has_skill("Lethal")
                and weapon.effect is not AdditionalEffect.DEATH
            ):
                effects.append((AdditionalEffect.DEATH, False))
            for effect, stacked in effects:
                resistance = PHYSICAL_EFFECT_RESISTANCE[effect]
                successful = resolve_physical_additional_effect(
                    effect=effect,
                    adjusted_hit=result.adjusted_hit,
                    effect_roll=int(
                        self.roll(actor, roll_target, 4 + hand * 3) * 100
                    ),
                    target_is_member=False,
                    target_has_boss_resistance=ResistanceType.DEATH in target.spec.resistances,
                    target_is_weak=resistance in target.spec.weaknesses,
                    target_is_resistant=resistance in target.spec.resistances,
                    target_defending=defending,
                    critical=result.critical,
                    attacker_hidden=hidden,
                    weapon_effective=physical_weapon_is_effective(
                        effective_tribe=weapon.effective_tribe,
                        target_tribe=target.spec.tribe,
                        attribute=weapon.attribute,
                        target_weaknesses=target.spec.weaknesses,
                        target_resistances=target.spec.resistances,
                    ),
                    stacked_death=stacked,
                ).success
                if successful and target.is_alive:
                    self.apply_extra(actor, target, effect, roll_target=roll_target)
        return counter

    def apply_extra(self, actor, target, effect, *, roll_target=None):
        if roll_target is None:
            roll_target = target.spec.number
        if effect is AdditionalEffect.DEATH:
            target.damage(target.hp)
        elif effect is AdditionalEffect.SLEEP:
            target.sleeping = max(
                target.sleeping, 2 + int(self.roll(actor, roll_target, 11) * 2)
            )
            target.confused = 0
        elif effect is AdditionalEffect.CONFUSE:
            target.confused = max(
                target.confused,
                2 + int(self.roll(actor, roll_target, 11) * 2),
            )
            target.sleeping = 0
        elif effect is AdditionalEffect.POISON:
            target.poisoned = True
        elif effect is AdditionalEffect.STUN:
            target.stunned = True
        elif effect is AdditionalEffect.PARALIZE and not target.spec.enemy:
            target.paralyzed = True
        elif (
            effect is AdditionalEffect.SILENCE
            and target.spec.spells
        ):
            target.silenced = max(
                target.silenced, self.debuff_turns(actor, target, roll_target=roll_target)
            )
        elif effect is AdditionalEffect.DEFENSE_DOWN:
            if target.protection > -1:
                target.protection -= 1
                target.defense_down_turns = (
                    self.debuff_turns(actor, target, roll_target=roll_target)
                    if target.protection < 0 else 0
                )
        target.interrupt_focus()

    def heal_result(self, actor, target, spell, u):
        if spell.type is SpellType.ITEM:
            ability = DA2_DEFAULT_ITEM_SPELL_ABILITY
        elif actor.spec.enemy:
            ability = actor.spec.magic
        else:
            ability = member_spell_ability(
                magic=actor.spec.magic, internal_level=actor.spec.internal_level
            )
        return resolve_healing(
            intensity=spell.intensity,
            ability=ability,
            current_hp=target.hp,
            max_hp=target.max_hp,
            random_factor=u,
        )

    def apply_spell_healing(self, actor, target, spell, u):
        result = self.heal_result(actor, target, spell, u)
        target.hp = min(target.max_hp, target.hp + result.amount)
        if result.cures_ailments:
            target.poisoned = target.paralyzed = target.stunned = False
            target.sleeping = target.confused = target.silenced = 0

    def spell_recipient(self, actor: ForecastActor, target: ForecastActor) -> ForecastActor:
        if target.spec.enemy:
            chance = spell_reflection_chance(
                defending=target.is_defending,
                has_reflect=MonsterSpecialAction.MIRROR in target.spec.special_actions,
            )
        else:
            chance = spell_reflection_chance(
                defending=target.is_defending,
                has_reflect=target.has_skill("Reflect"),
                equipment_reflects=any(
                    item.special is ItemSpecial.REFLECT for item in target.equipment.equipped_items()
                ),
            )
        if chance == SPELL_REFLECTION_ROLL_COUNT or (
            chance > 0
            and self.roll(actor, target.spec.number, 17) * SPELL_REFLECTION_ROLL_COUNT < chance
        ):
            return actor
        return target

    def cast(self, actor, action):
        spell = self.spells[action.spell_key]
        reflected_damage = 0
        for n in action.targets:
            target = self.actors[n]
            roll_target = (
                self.single_enemy_roll_target if spell.to_enemy and not spell.to_all else n
            )
            if target.spec.enemy:
                self.reveal(target, "profile")
                if spell.attribute is not None:
                    self.reveal(target, spell.attribute.value)
            if spell.to_enemy and spell.action is not SpellAction.IDENTIFY:
                target = self.spell_recipient(actor, target)
            u = self.roll(actor, roll_target, 8)
            if spell.action is SpellAction.HEAL:
                self.apply_spell_healing(actor, target, spell, u)
            elif spell.action is SpellAction.MANA:
                amount = resolve_recovery_amount(
                    intensity=spell.intensity,
                    ability=DA2_DEFAULT_ITEM_SPELL_ABILITY,
                    random_factor=u,
                )
                target.mp = min(target.spec.max_mp, target.mp + amount)
            elif spell.action is SpellAction.PROTECTION:
                target.apply_protection()
            elif spell.action is SpellAction.MAGIC_SHIELD:
                target.magic_shield = True
            elif spell.action is SpellAction.PURGE:
                target.purge_buffs()
            elif spell.action is SpellAction.HASTE:
                target.apply_haste()
            elif spell.action is SpellAction.CURE:
                target.poisoned = target.paralyzed = False
                target.sleeping = target.confused = 0
            elif spell.action is SpellAction.REVIVE:
                self.revive_spell_target(target, spell)
            elif spell.action is SpellAction.IDENTIFY:
                self.identify(target)
            else:
                level = (
                    spell.level
                    if spell.type is SpellType.ITEM
                    else actor.proficiency(SPELL_PROFICIENCY_BY_TYPE[spell.type]).level
                )
                modifier = member_spell_modifier(
                    magic=actor.spec.magic,
                    spell_level=level,
                    internal_level=actor.spec.internal_level,
                )
                if spell.action in (SpellAction.DAMAGE, SpellAction.BLOOD_SUCK):
                    result = resolve_spell_damage(
                        intensity=spell.intensity,
                        spell_modifier=modifier,
                        target_spell_defense=target.spec.spell_defense,
                        attribute=spell.attribute,
                        target_weaknesses=target.spec.weaknesses,
                        target_resistances=target.spell_resistances,
                        target_is_shadow=target.spec.shadow,
                        flying_effective=spell.effective_race == "FLYING",
                        dark_resistance_causes_miss=spell.action is SpellAction.BLOOD_SUCK,
                        random_factor=u,
                    )
                    if result.is_miss:
                        continue
                    if target is actor:
                        reflected_damage += result.damage
                    else:
                        drained = target.damage(result.damage)
                        if spell.action is SpellAction.BLOOD_SUCK:
                            actor.drain(drained)
                if target.is_alive and (
                    spell.action
                    in (
                        SpellAction.SLEEP,
                        SpellAction.CONFUSE,
                        SpellAction.SLOW,
                        SpellAction.BREAK,
                        SpellAction.SILENCE,
                    )
                    or spell.attribute is ResistanceType.POISON
                ):
                    successful = self.status_success(
                        actor, target, spell, modifier, roll_target=roll_target
                    )
                    if spell.action is SpellAction.SILENCE and not target.spec.spells:
                        successful = False
                    elif spell.action is SpellAction.BREAK and (
                        target.protection < 0 or target.defense <= 0
                    ):
                        successful = False
                    if successful:
                        if spell.action is SpellAction.SLEEP:
                            self.apply_extra(
                                actor, target, AdditionalEffect.SLEEP, roll_target=roll_target
                            )
                        elif spell.action is SpellAction.CONFUSE:
                            self.apply_extra(
                                actor, target, AdditionalEffect.CONFUSE, roll_target=roll_target
                            )
                        elif spell.action is SpellAction.SLOW:
                            self.apply_slow(target, actor, roll_target=roll_target)
                        elif spell.action is SpellAction.BREAK:
                            target.protection = (
                                0 if target.protection > 0 else -1
                            )
                            target.defense_down_turns = (
                                self.debuff_turns(actor, target, roll_target=roll_target)
                                if target.protection < 0 else 0
                            )
                        elif spell.action is SpellAction.SILENCE:
                            target.silenced = max(
                                target.silenced,
                                self.debuff_turns(actor, target, roll_target=roll_target),
                            )
                        if spell.attribute is ResistanceType.POISON:
                            target.poisoned = True
        if reflected_damage:
            drained = actor.damage(reflected_damage)
            if spell.action is SpellAction.BLOOD_SUCK:
                actor.drain(drained)
        actor.hidden = False

    def debuff_turns(
        self, actor: ForecastActor, target: ForecastActor, *, roll_target: int | None = None,
    ) -> int:
        if roll_target is None:
            roll_target = target.spec.number
        minimum, maximum = debuff_turn_range(target.spec.resistances)
        return minimum + int(
            self.roll(actor, roll_target, 11) * (maximum - minimum + 1)
        )

    def apply_slow(
        self, target: ForecastActor, actor: ForecastActor | None = None,
        *, roll_target: int | None = None,
    ) -> None:
        """Use the live speed stages and immediate waiting-gauge penalty."""

        if not target.is_alive or target.speed <= -1:
            return
        target.speed = 0 if target.speed > 0 else -1
        target.slow_turns = (
            self.debuff_turns(actor or target, target, roll_target=roll_target)
            if target.speed < 0 else 0
        )
        for index, entry in enumerate(self.order.entries):
            if entry.actor == target.spec.number:
                self.order = adjust_timeline_entry_gauge(
                    self.order,
                    entry_index=index,
                    gauge_adjustment=SLOW_GAUGE_ADJUSTMENT,
                )
                return

    def status_success(self, actor, target, spell, modifier, *, roll_target=None):
        if roll_target is None:
            roll_target = target.spec.number
        return resolve_status_spell(
            spell_modifier=modifier,
            rate=spell.rate,
            target_spell_defense=target.spec.spell_defense,
            attribute=spell.attribute,
            target_weaknesses=target.spec.weaknesses,
            target_resistances=target.spell_resistances,
            success_roll=int(self.roll(actor, roll_target, 10) * 20),
        ).success

    def reveal(self, actor, field):
        known = self.known[actor.spec.species_key or actor.spec.key]
        if field not in known:
            self.info += (
                2.0
                if field == "profile"
                else 1.0
                if field == "treasure_identified"
                else 0.4
            )
            known.add(field)

    def identify(self, target):
        self.reveal(target, "profile")
        for resistance in ResistanceType:
            self.reveal(target, resistance.value)
        self.reveal(target, "treasure_identified")
        if target.spec.number not in self.hp_shown:
            self.hp_shown.add(target.spec.number)
            self.info += 2

    def execute(self, number: int, action: AutoAction) -> tuple[float, float]:
        actor = self.actors[number]
        delay = self.delay(actor, action)
        cost = self.cost(actor, action)
        if action.command is BattleCommand.SPELL and actor.silenced:
            self.advance(actor, 0)
            return 0.0, actor.agility
        if action.command is BattleCommand.SPELL:
            actor.mp -= self.spells[action.spell_key].mp
        if action.item_key:
            self.item_quantities[action.item_key] -= 1
        if action.command in (
            BattleCommand.ATTACK,
            BattleCommand.AMBUSH,
            BattleCommand.AIM,
            BattleCommand.IAI,
        ):
            self.physical(actor, action)
        elif action.command is BattleCommand.FOCUS:
            actor.focus = action.targets[0]
        elif action.command is BattleCommand.BREATH:
            self.member_breath(actor, action.targets)
        elif action.spell_key:
            self.cast(actor, action)
        elif action.command is BattleCommand.HIDE:
            actor.hidden = True
        elif action.command is BattleCommand.DEFEND:
            actor.defending = True
        elif action.command is BattleCommand.COVER:
            actor.defending = True
            actor.cover = action.targets[0]
        elif action.command is BattleCommand.IDENTIFY:
            self.identify(self.actors[action.targets[0]])
            actor.hidden = False
        elif action.command is BattleCommand.PRAY:
            actor.hidden = False
            amount = resolve_pray_recovery(
                magic=actor.spec.magic,
                internal_level=actor.spec.internal_level,
                success_roll=int(self.roll(actor, number, 10) * PRAY_SUCCESS_ROLL_COUNT),
                random_factor=self.roll(actor, number, 8),
            )
            if amount is not None:
                actor.mp = min(actor.spec.max_mp, actor.mp + amount)
        elif action.command is BattleCommand.FORMATION:
            actor.front = not actor.front
        self.normalize()
        self.advance(actor, delay)
        return cost, actor.agility + delay

    def member_breath(self, actor: ForecastActor, targets: tuple[int, ...]) -> None:
        hp = actor.hp
        actor.hp -= member_breath_hp_cost(hp)
        actor.hidden = False
        for number in targets:
            target = self.actors[number]
            result = resolve_fire_breath(
                attack=actor.spec.breath_attack, hp=hp, max_hp=actor.max_hp,
                target_spell_defense=target.spec.spell_defense,
                fire_resistant=ResistanceType.FIRE in target.spell_resistances,
                random_factor=self.roll(actor, number, 5),
            )
            target.damage(result.damage)
            self.reveal(target, "profile")
            self.reveal(target, ResistanceType.FIRE.value)

    def covering(self, number):
        target = self.actors[number]
        allies = self.allies()

        def can_cover(a):
            return not (a.paralyzed or a.sleeping or a.confused)

        for a in allies:
            if a is not target and a.cover == number and can_cover(a):
                return a
        if target.hp <= target.max_hp // 4 or target.sleeping or target.paralyzed:
            for a in allies:
                if (
                    a is not target
                    and a.has_skill("Cover")
                    and can_cover(a)
                    and a.hp > a.max_hp // 4
                ):
                    return a
        return target

    def enemy_turn(self, actor):
        allies = self.allies()
        available = tuple(a for a in allies if not a.hidden)
        temptation_targets = tuple(a for a in allies if a.spec.gender is Gender.MALE)
        attack_targets = self._enemy_attack_targets(actor, allies)
        intelligence = actor.spec.intelligence
        allow_area_attacks = self.monster_area_attack_cooldown.permits(intelligence)
        escape = False
        if (
            intelligence != 3
            and MonsterSpecialAction.ESCAPE in actor.spec.special_actions
            and allies
            and self.roll(actor, 0, 12) >= 0.5
        ):
            member = allies[int(self.roll(actor, 0, 13) * len(allies))]
            physical = (
                member.weapon_attack(member.spec.weapons[0].attack)
                if member.spec.weapons
                and member.equipment.weapon_at(EquipmentSlot.RIGHT) is not None
                else 0
            )
            escape = physical > actor.spec.attack * (1 + self.roll(actor, 0, 14))
        spell_targets = {}
        priority_spell_key = None
        enemies = self.enemies()
        for spell in monster_spell_evaluation_order(actor.spec.spells, intelligence):
            if not allow_area_attacks and is_monster_area_attack_spell(spell):
                continue
            if intelligence > 0 and (actor.silenced or actor.mp < spell.mp):
                continue
            indexes = self.spell_targets(actor, spell)
            if intelligence > 0 and spell.to_enemy:
                states = tuple(
                    MonsterSpellTarget(
                        n, self.actors[n].front,
                        not (self.actors[n].sleeping or self.actors[n].paralyzed
                             or self.actors[n].confused),
                        bool(self.actors[n].spec.spells), self.actors[n].silenced,
                        self.actors[n].speed, self.actors[n].protection,
                        self.actors[n].spell_resistances,
                        magic_shield=self.actors[n].magic_shield,
                    )
                    for n in indexes
                )
                indexes = evaluate_monster_spell(
                    spell, states, intelligence=intelligence,
                    choose=lambda values: values[int(self.roll(actor, 0, 15) * len(values))],
                ).targets
            elif not spell.to_enemy and evaluate_monster_support_spell(
                spell, indexes, intelligence=intelligence,
            ).priority:
                priority_spell_key = spell.key
            if indexes:
                spell_targets[spell.key] = indexes
            if priority_spell_key is not None:
                break
        spell_keys = tuple(spell_targets)
        call_placement = None
        if (
            intelligence in (2, 3) and MonsterSpecialAction.CALL in actor.spec.special_actions
            and actor.spec.monster_placement is not None
        ):
            occupied = tuple(
                enemy.spec.monster_placement for enemy in enemies
                if enemy.spec.monster_placement is not None
            )
            call_placement = find_monster_placement(actor.spec.monster_placement, occupied)
            if call_placement is not None and call_placement.slot > 1:
                call_placement = None
        candidates = monster_action_candidates(
            special_actions=actor.spec.special_actions,
            is_front_row=actor.front,
            can_attack=bool(attack_targets),
            can_charge=bool(available),
            can_breathe=bool(available),
            can_earthquake=bool(allies),
            can_tempt=bool(temptation_targets),
            black_wind_has_targets=(
                MonsterSpecialAction.BLACK_WIND in actor.spec.special_actions
                and any(enemy.can_recover_with_black_wind for enemy in enemies)
            ),
            intelligence=intelligence,
            fire_breath_effective=any(
                ResistanceType.FIRE not in target.spell_resistances
                for target in available
            ),
            spell_keys=spell_keys,
            escape_eligible=escape,
            call_eligible=call_placement is not None,
            priority_spell_key=priority_spell_key,
            allow_area_attacks=allow_area_attacks,
        )
        silenced = actor.silenced > 0
        if intelligence == 3:
            action, actor.action_rotation_index = rotate_monster_action(
                special_actions=actor.spec.special_actions,
                spell_keys=tuple(spell.key for spell in actor.spec.spells),
                candidates=candidates, is_front_row=actor.front,
                next_index=actor.action_rotation_index,
                choose_start=lambda count: int(
                    quantile(self.case, actor.spec.number, 0, 0, 0) * count
                ),
            )
        elif candidates:
            key = lambda a: a.spell_key if isinstance(a, MonsterSpellAction) else a.value
            candidates = tuple(sorted(candidates, key=key))
            action = candidates[int(self.roll(actor, 0, 0) * len(candidates))]
        else:
            action = None
        if action is not MonsterAction.BLACK_WIND:
            actor.silenced = max(0, actor.silenced - 1)
        if action is None:
            self.advance(actor, 0)
            return
        delay = 0
        if action is MonsterAction.DEFEND:
            actor.defending = True
        elif action is MonsterAction.ESCAPE:
            actor.removed = True
        elif action is MonsterAction.CALL and call_placement is not None:
            self.enemy_call(actor, call_placement)
        elif action is MonsterAction.BLACK_WIND:
            for target in enemies:
                if target.can_recover_with_black_wind:
                    target.recover_with_black_wind()
        elif action is MonsterAction.EARTHQUAKE:
            self.record_monster_area_attack(actor)
            for target in allies:
                result = resolve_earthquake_attack(
                    attack=actor.spec.attack, hit=actor.spec.hit,
                    target_defense=target.defense, target_defending=target.defending,
                    hit_roll=int(self.roll(actor, target.spec.number, 2) * 100),
                    target_floating=target.spec.floating,
                    target_resists_tribe=target.spec.equipment.resists_tribe(actor.spec.tribe),
                )
                if not result.hit:
                    continue
                stun = resolve_physical_additional_effect(
                    effect=AdditionalEffect.STUN, adjusted_hit=result.adjusted_hit,
                    effect_roll=int(self.roll(actor, target.spec.number, 4) * 100),
                    target_is_member=True,
                    target_has_boss_resistance=ResistanceType.DEATH in target.spec.resistances,
                    target_is_resistant=(
                        result.tribe_resisted or ResistanceType.STUN in target.spec.resistances
                    ),
                    target_defending=target.defending,
                ).success
                target.damage(result.damage)
                if stun and target.is_alive:
                    target.stunned = True
                target.interrupt_focus()
        elif action is MonsterAction.TEMPTATION:
            for target in temptation_targets:
                if resolve_status_spell(
                    spell_modifier=actor.spec.magic,
                    rate=TEMPTATION_RATE,
                    target_spell_defense=target.spec.spell_defense,
                    attribute=ResistanceType.CONFUSE,
                    target_weaknesses=frozenset(),
                    target_resistances=target.spec.resistances,
                    success_roll=int(self.roll(actor, target.spec.number, 10) * 20),
                ).success:
                    self.apply_extra(actor, target, AdditionalEffect.CONFUSE)
        elif action in (MonsterAction.POISON_BREATH, MonsterAction.FIRE_BREATH):
            self.record_monster_area_attack(actor)
            number = actor.spec.number
            hp = actor.hp
            if self.fixed_breath_hp:
                hp = self.start_hp[number]
            else:
                self.breath_hp[number, self.turns[number], action] = hp
            for target in available:
                arguments = dict(
                    attack=actor.spec.attack,
                    hp=hp,
                    max_hp=actor.max_hp,
                    target_spell_defense=target.spec.spell_defense,
                    random_factor=self.roll(actor, target.spec.number, 5),
                )
                if action is MonsterAction.POISON_BREATH:
                    result = resolve_poison_breath(
                        **arguments,
                        poison_resistant=ResistanceType.POISON in target.spec.resistances,
                        poison_roll=int(self.roll(actor, target.spec.number, 4) * 10),
                    )
                else:
                    result = resolve_fire_breath(
                        **arguments,
                        fire_resistant=ResistanceType.FIRE in target.spell_resistances,
                    )
                target.damage(result.damage)
                if result.poisoned and target.is_alive:
                    target.poisoned = True
                if result.damage > 0:
                    target.interrupt_focus()
        elif isinstance(action, MonsterSpellAction):
            spell = self.spells[action.spell_key]
            if not silenced and actor.mp >= spell.mp:
                actor.mp -= spell.mp
                if is_monster_area_attack_spell(spell):
                    self.record_monster_area_attack(actor)
                targets = spell_targets[spell.key]
                if spell.to_enemy and not spell.to_all:
                    targets = self.preferred_monster_party_targets(actor, targets)
                if not spell.to_all and len(targets) > 1:
                    targets = (targets[int(self.roll(actor, 0, 1) * len(targets))],)
                if not spell.to_enemy:
                    for n in targets:
                        target = self.actors[n]
                        if spell.action is SpellAction.HASTE:
                            target.apply_haste()
                        elif spell.action is SpellAction.PROTECTION:
                            target.apply_protection()
                        elif spell.action is SpellAction.MAGIC_SHIELD:
                            target.magic_shield = True
                        elif spell.action is SpellAction.HEAL:
                            self.apply_spell_healing(actor, target, spell, self.roll(actor, n, 8))
                        elif spell.action is SpellAction.REVIVE and n in self.monster_revival_targets():
                            self.revive_spell_target(target, spell)
                if spell.to_enemy:
                    recipients = tuple(
                        (n, self.spell_recipient(actor, self.actors[n])) for n in targets
                    )
                if spell.to_enemy and spell.action is SpellAction.PURGE:
                    for _, target in recipients:
                        target.purge_buffs()
                if spell.to_enemy and spell.action in (SpellAction.DAMAGE, SpellAction.BLOOD_SUCK):
                    reflected_damage = 0
                    for n, target in recipients:
                        result = resolve_spell_damage(
                            intensity=spell.intensity,
                            spell_modifier=actor.spec.magic,
                            target_spell_defense=target.spec.spell_defense,
                            attribute=spell.attribute,
                            target_weaknesses=target.spec.weaknesses,
                            target_resistances=target.spell_resistances,
                            dark_resistance_causes_miss=spell.action is SpellAction.BLOOD_SUCK,
                            target_is_shadow=target.spec.shadow,
                            flying_effective=spell.effective_race == "FLYING",
                            random_factor=self.roll(actor, n, 5),
                        )
                        if result.is_miss:
                            continue
                        if target is actor:
                            reflected_damage += result.damage
                            continue
                        drained = target.damage(result.damage)
                        if spell.action is SpellAction.BLOOD_SUCK:
                            actor.drain(drained)
                        target.interrupt_focus()
                    if reflected_damage:
                        drained = actor.damage(reflected_damage)
                        if spell.action is SpellAction.BLOOD_SUCK:
                            actor.drain(drained)
                if spell.to_enemy and spell.action in ENEMY_SPELL_ACTIONS:
                    for n, target in recipients:
                        if target.is_alive and (
                            spell.action is not SpellAction.BREAK
                            or (
                                target.protection > -1
                                and target.defense > 0
                            )
                        ) and self.status_success(
                            actor,
                            target,
                            spell,
                            actor.spec.magic,
                            roll_target=n,
                        ):
                            if spell.action is SpellAction.SLEEP:
                                self.apply_extra(actor, target, AdditionalEffect.SLEEP, roll_target=n)
                            elif spell.action is SpellAction.CONFUSE:
                                self.apply_extra(
                                    actor,
                                    target,
                                    AdditionalEffect.CONFUSE, roll_target=n,
                                )
                            elif spell.action is SpellAction.SILENCE:
                                self.apply_extra(actor, target, AdditionalEffect.SILENCE, roll_target=n)
                            elif spell.action is SpellAction.SLOW:
                                self.apply_slow(target, actor, roll_target=n)
                            else:
                                target.protection = (
                                    0 if target.protection > 0 else -1
                                )
                                target.defense_down_turns = (
                                    self.debuff_turns(actor, target, roll_target=n)
                                    if target.protection < 0 else 0
                                )
                if spell.to_enemy and spell.attribute is ResistanceType.POISON:
                    for n, target in recipients:
                        if target.is_alive and self.status_success(
                            actor, target, spell, actor.spec.magic, roll_target=n,
                        ):
                            target.poisoned = True
        elif action in (MonsterAction.ATTACK, MonsterAction.CHARGE, MonsterAction.CONSTRICTION):
            charged = action is MonsterAction.CHARGE
            normal_attack = action is MonsterAction.ATTACK
            countering_member = self.enemy_attack(
                actor, available if charged else attack_targets, charged=charged,
                constricting=action is MonsterAction.CONSTRICTION,
                allow_counter=normal_attack and not self.surprise,
            )
            if normal_attack and MonsterSpecialAction.DOUBLE_ATTACK in actor.spec.special_actions:
                self.normalize()
                targets = self._enemy_attack_targets(actor, self.allies())
                if targets and not self.party_defeated:
                    self.enemy_attack(actor, targets, roll_offset=5)
            if countering_member is not None and countering_member.actionable:
                self._physical_target(
                    countering_member, actor,
                    AutoAction(BattleCommand.ATTACK, (actor.spec.number,)),
                    is_counter=True,
                )
            delay = -16 if charged else 0
        self.normalize()
        self.advance(actor, delay)

    def record_monster_area_attack(self, actor: ForecastActor) -> None:
        self.monster_area_attack_cooldown = self.monster_area_attack_cooldown.after_attack(
            actor.spec.number, actor.spec.intelligence,
        )

    def monster_revival_targets(self) -> tuple[int, ...]:
        occupied = tuple(
            placement for enemy in self.enemies()
            if (placement := enemy.spec.monster_placement) is not None
        )
        return tuple(
            enemy.spec.number for enemy in self.enemy_actors
            if not enemy.is_alive and not enemy.removed and (
                (placement := enemy.spec.monster_placement) is None
                or monster_revival_placement_available(placement, occupied)
            )
        )

    def revive_spell_target(self, target: ForecastActor, spell: Spell) -> None:
        target.hp = max(1, target.max_hp * spell.intensity // 100)
        target.clear_defeated_conditions()
        if target.spec.enemy:
            target.action_rotation_index = None
            self.refresh_placed_enemy_rows()
        if target.spec.number not in self.order.actors:
            self.order = insert_timeline_actor(
                self.order,
                target.spec.number,
                agility=target.agility,
                gauge=min(float(target.agility), GAUGE_READY_VALUE),
            )

    def enemy_call(self, caller: ForecastActor, placement: MonsterPlacement) -> None:
        number = max(self.actors) + 1
        species_key = caller.spec.species_key or caller.spec.key
        spec = replace(
            caller.spec, number=number, key=f"enemy:{species_key}:{number - 5}",
            species_key=species_key, hp=caller.max_hp, mp=caller.spec.max_mp,
            front=placement.slot >= 2, hp_displayed=False,
            magic_shield=False,
            poisoned=False, sleeping=0, silenced=0, paralyzed=False, defending=False,
            confused=0, stunned=False, protection=0, speed=0,
            slow_turns=0, defense_down_turns=0, action_rotation_index=None,
            monster_placement=placement,
        )
        newcomer = ForecastActor.create(spec)
        self.actors[number] = newcomer
        self.enemy_actors += (newcomer,)
        self.turns[number] = 0
        self.start_hp[number] = newcomer.hp
        self.refresh_placed_enemy_rows()
        self.order = insert_timeline_actor(
            self.order, number, agility=newcomer.agility,
            gauge=min(float(newcomer.agility), GAUGE_READY_VALUE),
        )

    def refresh_placed_enemy_rows(self) -> None:
        placed_enemies = tuple(
            (enemy, enemy.spec.monster_placement.slot) for enemy in self.enemies()
            if enemy.spec.monster_placement is not None
        )
        front_slot_occupied = any(slot >= 2 for _, slot in placed_enemies)
        for enemy, slot in placed_enemies:
            enemy.front = slot >= 2 or not front_slot_occupied

    def preferred_monster_party_targets(
        self, actor: ForecastActor, indexes: tuple[int, ...],
    ) -> tuple[int, ...]:
        def is_incapacitated(index: int) -> bool:
            target = self.actors[index]
            return not target.confused and bool(target.sleeping or target.paralyzed)

        return prefer_monster_targets(
            indexes, intelligence=actor.spec.intelligence,
            is_incapacitated=is_incapacitated,
        )

    def _enemy_attack_targets(
        self, actor: ForecastActor, allies: tuple[ForecastActor, ...],
    ) -> tuple[ForecastActor, ...]:
        return monster_attack_targets(
            (ally for ally in allies if not ally.hidden),
            special_actions=actor.spec.special_actions,
            is_front_row=actor.front,
            target_is_front_row=lambda ally: ally.front,
        )

    def enemy_attack(
        self, actor, targets, *, charged=False, constricting=False, roll_offset=0, allow_counter=False,
    ):
        indexes = self.preferred_monster_party_targets(
            actor, tuple(target.spec.number for target in targets),
        )
        protected = indexes[int(self.roll(actor, 0, 1 + roll_offset) * len(indexes))]
        target = self.covering(protected)
        if target.spec.number != protected:
            target.hidden = False
        if self.enemy_physical(
            actor, target, charged=charged, constricting=constricting,
            roll_offset=roll_offset, allow_counter=allow_counter,
        ):
            return target
        return None

    def enemy_physical(
        self, actor, target, *, charged=False, constricting=False, roll_offset=0, allow_counter=False,
    ):
        power_hit = MonsterSpecialAction.POWER_HIT in actor.spec.special_actions
        defending = target.is_defending if target.spec.enemy else target.defending
        roll_count = CONSTRICTION_HIT_ROLL_COUNT if constricting else PHYSICAL_HIT_ROLL_COUNT
        result = resolve_physical_attack(
            attack=int(actor.spec.attack * (1.5 if charged else 1)),
            hit=actor.spec.hit,
            target_defense=target.defense,
            target_evasion=target.evasion,
            target_defending=defending,
            target_unable_to_evade=target.focus is not None,
            target_incapacitated=target.incapacitated_for_physical_hit,
            attacker_is_monster=True,
            attacker_has_power_hit=power_hit,
            target_resists_tribe=(
                not target.spec.enemy and target.spec.equipment.resists_tribe(actor.spec.tribe)
            ),
            hit_roll=int(self.roll(actor, target.spec.number, 2 + roll_offset) * roll_count),
            constricting=constricting,
            critical_roll=int(self.roll(actor, target.spec.number, 3 + roll_offset) * 100)
            if power_hit or target.incapacitated_for_physical_hit
            else None,
        )
        effects = resolve_monster_attack_effects(
            actor.spec.additional_effects,
            result,
            roll_effect=lambda: int(
                self.roll(actor, target.spec.number, 4 + roll_offset) * 100
            ),
            target_is_member=not target.spec.enemy,
            target_resistances=target.spec.resistances,
            target_weaknesses=target.spec.weaknesses if target.spec.enemy else (),
            target_defending=defending,
            constricting=constricting,
        )
        if (
            not constricting and not result.tribe_resisted
            and AdditionalEffect.DRAIN in actor.spec.additional_effects
        ):
            actor.drain(result.damage)
        was_actionable = target.actionable
        target.damage(result.damage)
        counter = (
            allow_counter and was_actionable and target.actionable
            and target.has_skill("Retaliate")
            and member_can_attack(target)
            and counter_attack_succeeds(
                attacker_agility=actor.agility, defender_agility=target.agility,
                attacker_front=actor.front, defender_front=target.front,
                defender_actionable=True, defender_reach=member_attack_reach(target),
                roll=int(self.roll(actor, target.spec.number, 16) * 20),
            )
        )
        if target.is_alive:
            for effect in effects:
                self.apply_extra(actor, target, effect)
        target.interrupt_focus()
        return counter

    def confused_turn(self, actor: ForecastActor) -> None:
        """Forecast DA2's forced same-side basic attack for one confused actor."""

        if actor.spec.enemy:
            actor.silenced = max(0, actor.silenced - 1)
            friendly = tuple(a for a in self.enemies() if a is not actor)
            if friendly:
                targets = friendly
            else:
                targets = self._enemy_attack_targets(actor, self.allies())
        else:
            friendly = tuple(
                a
                for a in self.allies()
                if a is not actor
                and not a.hidden
                and not (a.sleeping or a.paralyzed or a.confused)
            )
            if friendly:
                targets = friendly
            else:
                targets = tuple(
                    self.actors[number]
                    for number in self.attack_targets(actor, BattleCommand.ATTACK)
                )
        if targets:
            indexes = tuple(target.spec.number for target in targets)
            if actor.spec.enemy and not friendly:
                indexes = self.preferred_monster_party_targets(actor, indexes)
            target = indexes[int(self.roll(actor, 0, 15) * len(indexes))]
            self.confused_physical(actor, self.actors[target])
        actor.hidden = False
        self.normalize()
        self.advance(actor, 0)

    def confused_physical(
        self,
        actor: ForecastActor,
        target: ForecastActor,
    ) -> None:
        """Apply one forced basic attack without assuming the target's side."""

        if actor.spec.enemy:
            if target.is_alive:
                self.enemy_physical(actor, target)
            return

        results = self.physical_results(
            actor,
            target,
            AutoAction(BattleCommand.ATTACK, (target.spec.number,)),
            roll_target=target.spec.number,
        )
        effect_sources = []
        for weapon in actor.spec.weapons:
            candidates = []
            if weapon.effect in PHYSICAL_STATUS_EFFECTS:
                candidates.append(
                    (
                        weapon.effect,
                        weapon.effect is AdditionalEffect.DEATH
                        and actor.has_skill("Lethal"),
                    )
                )
            if actor.has_skill("Lethal") and weapon.effect is not AdditionalEffect.DEATH:
                candidates.append((AdditionalEffect.DEATH, False))
            effect_sources.append(tuple(candidates))

        for hand, (result, candidates) in enumerate(zip(results, effect_sources)):
            if not target.is_alive or not result.hit:
                continue
            weapon = actor.spec.weapons[hand]
            target.damage(result.damage)
            if weapon_can_drain(weapon.effect, target.spec.resistances):
                actor.drain(result.damage)
            for effect, stacked in candidates:
                if not target.is_alive:
                    break
                resistance = PHYSICAL_EFFECT_RESISTANCE[effect]
                success = resolve_physical_additional_effect(
                    effect=effect,
                    adjusted_hit=result.adjusted_hit,
                    effect_roll=int(
                        self.roll(actor, target.spec.number, 4 + hand * 3) * 100
                    ),
                    target_is_member=not target.spec.enemy,
                    target_has_boss_resistance=ResistanceType.DEATH in target.spec.resistances,
                    target_is_weak=(
                        resistance is not None
                        and resistance in target.spec.weaknesses
                    ),
                    target_is_resistant=(
                        resistance is not None
                        and resistance in target.spec.resistances
                    ),
                    target_defending=target.defending,
                    critical=result.critical,
                    weapon_effective=(
                        target.spec.enemy
                        and physical_weapon_is_effective(
                            effective_tribe=weapon.effective_tribe,
                            target_tribe=target.spec.tribe,
                            attribute=weapon.attribute,
                            target_weaknesses=target.spec.weaknesses,
                            target_resistances=target.spec.resistances,
                        )
                    ),
                    stacked_death=stacked,
                ).success
                if success:
                    self.apply_extra(actor, target, effect)
        target.interrupt_focus()

    def prepare_turn(self, actor) -> bool:
        if actor.spec.enemy:
            self.monster_area_attack_cooldown = self.monster_area_attack_cooldown.release(
                actor.spec.number,
            )
        actor.defending = False
        if not actor.spec.enemy:
            actor.cover = None
            if actor.is_alive and actor.has_skill(INNER_STEEL_SKILL_KEY):
                actor.sleeping = actor.confused = actor.silenced = 0
            if not self.surprise:
                self.restore_surprise_rows((actor,), after_confusion_tick=True)
        poison = (
            poison_tick_damage(
                max_hp=actor.max_hp,
                weak_to_poison=actor.spec.enemy
                and ResistanceType.POISON in actor.spec.weaknesses,
            )
            if actor.poisoned
            else 0
        )
        recovery = battle_healing_amount(
            max_hp=actor.max_hp,
            healing=actor.spec.healing,
            is_boss=actor.spec.is_boss,
        )
        delta = recovery - poison
        if delta < 0:
            actor.damage(-delta, poison=True)
        elif delta > 0:
            actor.hp = min(actor.max_hp, actor.hp + delta)
        actor.interrupt_focus()
        skipped = False
        if actor.stunned:
            actor.stunned = False
            skipped = True
        elif actor.paralyzed:
            skipped = True
        elif actor.sleeping:
            actor.sleeping -= 1
            skipped = True
        if not actor.spec.enemy and self.surprise:
            # While anyone still owes a surprise skip, repeated fast turns skip too.
            if skipped or actor.confused:
                self.surprise_deferred.add(actor.spec.number)
            self.surprise.discard(actor.spec.number)
            if not self.surprise:
                self.restore_surprise_rows(
                    a for a in self.allies()
                    if a.spec.number not in self.surprise_deferred
                )
            skipped = True
        if skipped and not actor.spec.enemy:
            actor.focus = None
        if skipped and actor.spec.enemy:
            actor.silenced = max(0, actor.silenced - 1)
        if delta or skipped or not actor.is_alive:
            self.normalize()
        return skipped or not actor.is_alive

    def restore_surprise_rows(self, actors, *, after_confusion_tick=False):
        restored = []
        for actor in actors:
            if (
                actor.spec.number in self.original_rows
                and actor.is_alive
                and not (actor.sleeping or actor.paralyzed or actor.stunned)
                and actor.confused <= int(after_confusion_tick)
            ):
                actor.front = self.original_rows.pop(actor.spec.number)
                self.surprise_deferred.discard(actor.spec.number)
                restored.append(actor)
        if restored and not any(a.front for a in self.allies()):
            for actor in restored:
                actor.front = True

    def normalize(self):
        attacker = self.monster_area_attack_cooldown.attacker
        if attacker is not None and not self.actors[attacker].is_alive:
            self.monster_area_attack_cooldown = self.monster_area_attack_cooldown.release(attacker)
        for n, a in self.actors.items():
            if not a.is_alive and n in self.original_alive:
                self.died.add(n)
        allies = self.allies()
        self.defeated |= not allies or all(a.paralyzed for a in allies)
        surprise_was_active = bool(self.surprise)
        self.surprise.intersection_update(a.spec.number for a in allies)
        if surprise_was_active and not self.surprise:
            self.restore_surprise_rows(
                a for a in allies if a.spec.number not in self.surprise_deferred
            )
        if allies and not any(a.front for a in allies):
            for a in allies:
                a.front = True
        promote_rear_monsters_if_front_empty(self.enemy_actors)
        visible = [
            a
            for a in allies
            if not a.hidden and not (a.sleeping or a.paralyzed or a.confused)
        ]
        if not visible:
            for a in allies:
                a.hidden = False

    def advance(self, actor, delay):
        for modifier, timer in (
            ("speed", "slow_turns"), ("protection", "defense_down_turns"),
        ):
            remaining = max(0, getattr(actor, timer) - 1)
            setattr(actor, timer, remaining)
            if remaining == 0 and getattr(actor, modifier) < 0:
                setattr(actor, modifier, 0)
        if not actor.spec.enemy:
            actor.silenced = max(0, actor.silenced - 1)
        key = (
            self.order,
            actor.agility,
            delay,
            tuple(n for n, a in self.actors.items() if not a.is_alive),
        )
        cached = self.timeline_cache.get(key)
        self.turns[actor.spec.number] += 1
        if cached is not None:
            self.order = cached
            return
        remaining = tuple(
            e for e in self.order.entries[1:] if self.actors[e.actor].is_alive
        )
        entries = (self.order.entries[0],) + remaining
        if actor.is_alive:
            self.order = complete_timeline_action(
                TimelineOrder(entries),
                current_agility=actor.agility,
                gauge_adjustment=delay,
                visible_count=6,
            ).after
        else:
            self.order = TimelineOrder(remaining)
        if self.order.entries:
            self.order = ready_timeline_head(self.order)
        # Limit memory; eviction affects speed only, never forecasting semantics.
        if len(self.timeline_cache) >= 8192:
            self.timeline_cache.clear()
        self.timeline_cache[key] = self.order

    def step(self, weights) -> float:
        if self.ended:
            return 0.0
        actor = self.actors[self.order.entries[0].actor]
        if self.prepare_turn(actor):
            self.advance(actor, 0)
            return 0.0
        if actor.confused:
            actor.confused -= 1
            if actor.confused:
                self.confused_turn(actor)
                return 0.0
        if actor.spec.enemy:
            self.enemy_turn(actor)
            return 0.0
        if actor.focus is not None:
            targets = self.attack_targets(actor, BattleCommand.ATTACK)
            stored = actor.focus
            actor.focus = None
            if targets:
                target = stored if stored in targets else targets[0]
                self.physical(actor, AutoAction(BattleCommand.FOCUS, (target,)))
                self.focus_completed |= actor.spec.number == self.snapshot.active_number
                self.normalize()
                self.advance(actor, 0)
                return 0.0
        action = self.continuation(actor.spec.number, weights)
        return self.execute(actor.spec.number, action)[0]

    def values(self, weights) -> tuple[float, ...]:
        victory = float(not self.enemies())
        defeat = float(self.party_defeated)
        deaths = sum(not self.actors[n].is_alive for n in self.original_alive)
        health = sum(a.hp / a.max_hp for a in self.ally_actors)
        ability = sum(a.actionable for a in self.ally_actors)
        killed = sum(
            weights[n] for n in self.original_enemies if not self.actors[n].is_alive
        )
        damage = sum(
            weights[n]
            * max(
                -1,
                min(
                    1,
                    (
                        self.start_hp[n]
                        - (self.actors[n].hp if self.actors[n].is_alive else 0)
                    )
                    / self.actors[n].max_hp,
                ),
            )
            for n in self.original_enemies
        )
        return (
            victory,
            defeat,
            float(deaths),
            health,
            float(ability),
            killed,
            damage,
            self.info,
        )


def mp_cost(mp: int, maximum: int, spent: int, cheapest_recovery: int) -> float:
    if not spent:
        return 0.0
    ratio = max(0, min(1, mp / max(maximum, 1)))
    reserve = min(maximum, 2 * cheapest_recovery)
    return (
        spent * (0.8 + 1.6 * (1 - ratio) ** 2)
        + 8 * max(0, reserve - (mp - spent)) / max(reserve, 1)
        + 12 * int(mp - spent == 0)
    )
