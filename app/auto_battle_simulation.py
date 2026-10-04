"""Bounded battle forecasts using the live physical, magic, and gauge rules."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor

if __package__:
    from .auto_battle_model import (
        CASE_COUNT,
        AutoAction,
        AutoBattleSnapshot,
        AutoCombatant,
        ItemMode,
        SpellMode,
        quantile,
    )
    from .battle_commands import (
        BattleCommand,
        BattleCommandContext,
        member_attack_reach,
        resolve_battle_commands,
        selectable_attack_target_indexes,
    )
    from .battle_magic import (
        battle_healing_amount,
        member_spell_ability,
        member_spell_modifier,
        poison_tick_damage,
        resolve_healing,
        resolve_spell_damage,
        resolve_status_spell,
        spell_cast_delay,
    )
    from .battle_physical import (
        PHYSICAL_STATUS_EFFECTS,
        resolve_physical_additional_effect,
        resolve_physical_attack,
    )
    from .battle_speed import modified_agility
    from .battle_timeline import (
        GAUGE_READY_VALUE,
        TimelineEntry,
        TimelineOrder,
        complete_timeline_action,
        insert_timeline_actor,
        ready_timeline_head,
    )
    from .item import AdditionalEffect, ItemEquipType, ItemSpecial
    from .member import EquipmentSlot
    from .monster import MonsterSpecialAction, promote_rear_monsters_if_front_empty
    from .monster_ai import MonsterAction, MonsterSpellAction, monster_action_candidates
    from .resistance import ResistanceType
    from .spell import SPELL_PROFICIENCY_BY_TYPE, Spell, SpellAction, SpellType
else:
    from auto_battle_model import (
        CASE_COUNT,
        AutoAction,
        AutoBattleSnapshot,
        AutoCombatant,
        ItemMode,
        SpellMode,
        quantile,
    )
    from battle_commands import (
        BattleCommand,
        BattleCommandContext,
        member_attack_reach,
        resolve_battle_commands,
        selectable_attack_target_indexes,
    )
    from battle_magic import (
        battle_healing_amount,
        member_spell_ability,
        member_spell_modifier,
        poison_tick_damage,
        resolve_healing,
        resolve_spell_damage,
        resolve_status_spell,
        spell_cast_delay,
    )
    from battle_physical import (
        PHYSICAL_STATUS_EFFECTS,
        resolve_physical_additional_effect,
        resolve_physical_attack,
    )
    from battle_speed import modified_agility
    from battle_timeline import (
        GAUGE_READY_VALUE,
        TimelineEntry,
        TimelineOrder,
        complete_timeline_action,
        insert_timeline_actor,
        ready_timeline_head,
    )
    from item import AdditionalEffect, ItemEquipType, ItemSpecial
    from member import EquipmentSlot
    from monster import MonsterSpecialAction, promote_rear_monsters_if_front_empty
    from monster_ai import MonsterAction, MonsterSpellAction, monster_action_candidates
    from resistance import ResistanceType
    from spell import SPELL_PROFICIENCY_BY_TYPE, Spell, SpellAction, SpellType


# Kept deliberately separate because monster casters support fewer actions.
ALLY_SPELL_ACTIONS = frozenset(
    (
        SpellAction.HEAL,
        SpellAction.DAMAGE,
        SpellAction.SLEEP,
        SpellAction.CONFUSE,
        SpellAction.SLOW,
        SpellAction.BREAK,
        SpellAction.PROTECTION,
        SpellAction.IDENTIFY,
        SpellAction.HASTE,
        SpellAction.SILENCE,
        SpellAction.CURE,
        SpellAction.REVIVE,
    )
)
ENEMY_SPELL_ACTIONS = frozenset(
    (SpellAction.SLEEP, SpellAction.CONFUSE, SpellAction.SLOW, SpellAction.BREAK)
)
RECOVERY_ACTIONS = frozenset(
    (SpellAction.HEAL, SpellAction.CURE, SpellAction.REVIVE, SpellAction.MANA)
)
PRIORITY_RECOVERY_ACTIONS = frozenset(
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
EFFECT_RESISTANCE = {
    AdditionalEffect.SLEEP: ResistanceType.SLEEP,
    AdditionalEffect.CONFUSE: ResistanceType.CONFUSE,
    AdditionalEffect.POISON: ResistanceType.POISON,
    AdditionalEffect.PARALIZE: ResistanceType.PARALIZE,
    AdditionalEffect.SILENCE: ResistanceType.SILENCE,
    AdditionalEffect.DEATH: ResistanceType.DEATH,
    AdditionalEffect.STUN: ResistanceType.STUN,
    AdditionalEffect.DEFENSE_DOWN: None,
}


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

    @classmethod
    def create(cls, spec: AutoCombatant, prior: float, case: int) -> ForecastActor:
        maximum = spec.max_hp
        if maximum is None:
            u = quantile(case, spec.number, 0, spec.number, 9)
            maximum = max(floor(prior * (0.75 + 0.75 * u)), spec.net_damage + 1, 1)
        hp = spec.hp
        if hp is None:
            hp = max(1, min(maximum, maximum - spec.net_damage)) if spec.alive else 0
        return cls(
            spec,
            hp,
            maximum,
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

    @property
    def agility(self) -> int:
        return modified_agility(self.spec.agility, self.speed)

    @property
    def defense(self) -> int:
        base = self.spec.defense
        if self.spec.enemy:
            return max(0, int((base - 10) * 0.5)) if self.protection < 0 else base
        d = -2 if self.protection < 0 else self.protection
        return max(0, int((base + 5 * d) * (1 + d / 4)))

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

    def damage(self, amount: int, *, poison: bool = False) -> int:
        old = self.hp
        self.hp = max(0, self.hp - amount)
        if amount > 0 and not poison:
            self.sleeping = self.confused = 0
        if self.hp == 0:
            self.poisoned = self.paralyzed = self.stunned = self.hidden = False
            self.sleeping = self.confused = self.silenced = self.protection = (
                self.speed
            ) = 0
            self.focus = self.cover = None
        return old - self.hp

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
            c.number: ForecastActor.create(c, snapshot.hp_prior, case)
            for c in snapshot.combatants
        }
        self.order = TimelineOrder(
            tuple(
                TimelineEntry(n, self.actors[n].agility, g) for n, g in snapshot.gauges
            )
        )
        self.spells = {s.key: s for s in snapshot.spells}
        self.turns = {n: 0 for n in self.actors}
        self.start_hp = {n: a.hp for n, a in self.actors.items()}
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
        self.original_rows = dict(snapshot.surprise_original_rows)
        self.info = 0.0
        self.died: set[int] = set()
        self.defeated = False
        self.focus_completed = False
        self.expected_cache: dict[tuple, float] = {}
        self.command_cache: dict[tuple, tuple] = {}
        self.timeline_cache: dict[tuple, TimelineOrder] = {}
        self.ally_actors = tuple(a for a in self.actors.values() if not a.spec.enemy)
        self.enemy_actors = tuple(a for a in self.actors.values() if a.spec.enemy)

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
            targets = (
                tuple(a for a in self.allies() if not a.hidden)
                if spell.to_enemy
                else self.enemies()
            )
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
                targets = tuple(a for a in targets if a.protection < 2)
            elif spell.action is SpellAction.HASTE:
                targets = tuple(a for a in targets if a.speed < 2)
            elif spell.action is SpellAction.CURE:
                targets = tuple(a for a in targets if self.cure_spell_curable(a))
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
            elif command is BattleCommand.IDENTIFY:
                actions.extend(
                    AutoAction(command, (a.spec.number,)) for a in self.enemies()
                )
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
                    if continuation and spell.action not in (
                        SpellAction.HEAL,
                        SpellAction.CURE,
                        SpellAction.REVIVE,
                    ):
                        continue
                    if self.snapshot.policy.spell_mode is SpellMode.NEVER:
                        reject(spell.key, "spell_policy")
                        continue
                    if (
                        self.snapshot.policy.spell_mode is SpellMode.RECOVERY_ONLY
                        and spell.action not in RECOVERY_ACTIONS
                    ):
                        reject(spell.key, "recovery_only")
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
                        and spell.action
                        not in (
                            SpellAction.HEAL,
                            SpellAction.CURE,
                            SpellAction.REVIVE,
                        )
                    ):
                        continue
                    if spell is not None:
                        actions.extend(
                            self.effect_candidates(
                                actor, command, spell, slot.value, reject
                            )
                        )
            else:
                reject(command.value, "unsupported_command")
        return tuple(sorted(set(actions), key=lambda a: a.stable_key(self.snapshot)))

    def effect_candidates(self, actor, command, spell, slot="", reject=lambda *_: None):
        if not spell.on_battle or spell.action not in ALLY_SPELL_ACTIONS:
            reject(spell.key, "unsupported_effect")
            return ()
        targets = self.spell_targets(actor, spell)
        if not targets:
            reject(spell.key, "no_targets")
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
                if spell.attribute not in self.actors[n].spec.resistances
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
        # Full health can still be a useful HEAL when its full-recovery effect cures.
        if spell.action is SpellAction.HEAL:
            targets = tuple(
                n
                for n in targets
                if self.actors[n].hp < self.actors[n].max_hp
                or (spell.intensity == 0 and self.curable(self.actors[n]))
            )
        if not targets:
            reject(spell.key, "no_change")
            return ()
        if spell.to_all:
            # Apply a whole-party spell to the same full legal set as manual use.
            return (
                AutoAction(command, self.spell_targets(actor, spell), spell.key, slot),
            )
        return tuple(AutoAction(command, (n,), spell.key, slot) for n in targets)

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
        q = 0
        if self.snapshot.policy.spell_mode is not SpellMode.NEVER:
            costs = [
                s.mp
                for s in actor.spec.spells
                if s.action in (SpellAction.HEAL, SpellAction.CURE, SpellAction.REVIVE)
                and s.action in ALLY_SPELL_ACTIONS
            ]
            q = min(costs, default=0)
        return mp_cost(actor.mp, actor.spec.max_mp, m, q)

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
                    key=lambda a: (
                        not (a.sleeping or a.paralyzed or a.confused or a.stunned),
                        ordering.get(a.spec.number, 999),
                        a.spec.number,
                    )
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
                if stage == "cure" and not self.curable(target):
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
                        a
                        for a in (*heals, *cures)
                        if target.spec.number in a.targets
                        and (
                            self.spells[a.spell_key].action is SpellAction.CURE
                            or self.spells[a.spell_key].intensity == 0
                        )
                    ]
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
        attacks = [a for a in actions if a.command is command]
        if attacks:
            values = {
                a: self.expected_damage(actor, self.actors[a.targets[0]], a)
                for a in attacks
            }
            kill = [a for a in attacks if values[a] >= self.actors[a.targets[0]].hp]
            if kill:
                return min(kill, key=lambda a: (-weights[a.targets[0]], a.targets))
            return min(
                attacks,
                key=lambda a: (
                    -weights[a.targets[0]]
                    * min(values[a], self.actors[a.targets[0]].hp)
                    / self.actors[a.targets[0]].max_hp,
                    a.targets,
                ),
            )
        return AutoAction(BattleCommand.DEFEND)

    def expected_damage(self, actor, target, action):
        key = (
            actor.spec.number,
            target.spec.number,
            actor.agility,
            target.defense,
            target.evasion,
            bool(target.sleeping),
            actor.hidden,
            action.command,
            self.turns[actor.spec.number],
        )
        if key not in self.expected_cache:
            self.expected_cache[key] = (
                sum(
                    sum(
                        r.damage
                        for r in self.physical_results(actor, target, action, k)
                    )
                    for k in range(CASE_COUNT)
                )
                / CASE_COUNT
            )
        return self.expected_cache[key]

    def physical_results(self, actor, target, action, case=None):
        results = []
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
            elif action.command is BattleCommand.FOCUS:
                attack *= 2
            effective = (
                weapon.attribute is not None
                and weapon.attribute in target.spec.weaknesses
                and weapon.attribute not in target.spec.resistances
            )
            results.append(
                resolve_physical_attack(
                    attack=attack,
                    hit=weapon.hit,
                    target_defense=target.defense,
                    target_evasion=target.evasion,
                    hit_roll=int(
                        self.roll(actor, target.spec.number, 2 + hand * 3, case) * 100
                    ),
                    target_incapacitated=bool(target.sleeping),
                    attacker_hidden=actor.hidden,
                    hit_value_bonus=100 if action.command is BattleCommand.AIM else 0,
                    attacker_has_power_hit=actor.has_skill("Power Hit"),
                    weapon_has_power_hit=weapon.power_hit,
                    weapon_effective=effective,
                    critical_rate_scale=weapon.critical_scale,
                    critical_roll=int(
                        self.roll(actor, target.spec.number, 3 + hand * 3, case) * 100
                    ),
                )
            )
        return results

    def physical(self, actor, action):
        for number in action.targets:
            self._physical_target(actor, self.actors[number], action)
        actor.hidden = False

    def _physical_target(self, actor, target, action):
        # Live execution resolves both hands before applying either result.
        results = self.physical_results(actor, target, action)
        hidden = actor.hidden
        for hand, (weapon, result) in enumerate(zip(actor.spec.weapons, results)):
            self.reveal(target, "profile")
            if weapon.attribute is not None:
                self.reveal(target, weapon.attribute.value)
            if not target.is_alive or not result.hit:
                continue
            target.damage(result.damage)
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
                resistance = EFFECT_RESISTANCE[effect]
                successful = resolve_physical_additional_effect(
                    effect=effect,
                    adjusted_hit=result.adjusted_hit,
                    effect_roll=int(
                        self.roll(actor, target.spec.number, 4 + hand * 3) * 100
                    ),
                    target_is_member=False,
                    target_is_boss=target.spec.boss,
                    target_is_weak=resistance in target.spec.weaknesses,
                    target_is_resistant=resistance in target.spec.resistances,
                    critical=result.critical,
                    attacker_hidden=hidden,
                    weapon_effective=weapon.attribute in target.spec.weaknesses
                    and weapon.attribute not in target.spec.resistances,
                    stacked_death=stacked,
                ).success
                if successful and target.is_alive:
                    self.apply_extra(actor, target, effect)

    def apply_extra(self, actor, target, effect):
        if effect is AdditionalEffect.DEATH:
            target.damage(target.hp)
        elif effect is AdditionalEffect.SLEEP:
            target.sleeping = max(
                target.sleeping, 2 + int(self.roll(actor, target.spec.number, 11) * 2)
            )
            target.confused = 0
        elif effect is AdditionalEffect.CONFUSE:
            target.confused = max(
                target.confused,
                2 + int(self.roll(actor, target.spec.number, 11) * 2),
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
            and target.spec.enemy
            and target.spec.spells
        ):
            target.silenced = max(
                target.silenced, 4 + int(self.roll(actor, target.spec.number, 11) * 3)
            )
        elif effect is AdditionalEffect.DEFENSE_DOWN:
            target.protection = max(-1, target.protection - 1)
        target.interrupt_focus()

    def heal_result(self, actor, target, spell, u):
        ability = (
            20
            if spell.type is SpellType.ITEM
            else member_spell_ability(
                magic=actor.spec.magic, internal_level=actor.spec.internal_level
            )
        )
        return resolve_healing(
            intensity=spell.intensity,
            ability=ability,
            current_hp=target.hp,
            max_hp=target.max_hp,
            random_factor=u,
        )

    def cast(self, actor, action):
        spell = self.spells[action.spell_key]
        for n in action.targets:
            target = self.actors[n]
            if target.spec.enemy:
                self.reveal(target, "profile")
                if spell.attribute is not None:
                    self.reveal(target, spell.attribute.value)
            u = self.roll(actor, n, 8)
            if spell.action is SpellAction.HEAL:
                result = self.heal_result(actor, target, spell, u)
                target.hp = min(target.max_hp, target.hp + result.amount)
                if result.cures_ailments:
                    target.poisoned = target.paralyzed = target.stunned = False
                    target.sleeping = target.confused = 0
            elif spell.action is SpellAction.PROTECTION:
                target.protection = min(2, target.protection + 1)
            elif spell.action is SpellAction.HASTE:
                target.speed = min(2, target.speed + 1)
            elif spell.action is SpellAction.CURE:
                target.poisoned = target.paralyzed = False
                target.sleeping = target.confused = 0
            elif spell.action is SpellAction.REVIVE:
                target.hp = max(1, target.max_hp * spell.intensity // 100)
                target.poisoned = target.paralyzed = target.stunned = False
                target.sleeping = target.confused = target.silenced = 0
                target.protection = target.speed = 0
                target.hidden = False
                target.focus = target.cover = None
                if target.spec.number not in self.order.actors:
                    self.order = insert_timeline_actor(
                        self.order,
                        target.spec.number,
                        agility=target.agility,
                        gauge=min(float(target.agility), GAUGE_READY_VALUE),
                    )
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
                if spell.action is SpellAction.DAMAGE:
                    result = resolve_spell_damage(
                        intensity=spell.intensity,
                        spell_modifier=modifier,
                        target_spell_defense=target.spec.spell_defense,
                        attribute=spell.attribute,
                        target_weaknesses=target.spec.weaknesses,
                        target_resistances=target.spec.resistances,
                        target_is_shadow=target.spec.shadow,
                        random_factor=u,
                    )
                    target.damage(result.damage)
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
                    successful = self.status_success(actor, target, spell, modifier)
                    if (
                        spell.action is SpellAction.SILENCE
                        and not target.spec.spells
                    ):
                        successful = False
                    if successful:
                        if spell.action is SpellAction.SLEEP:
                            self.apply_extra(actor, target, AdditionalEffect.SLEEP)
                        elif spell.action is SpellAction.CONFUSE:
                            self.apply_extra(actor, target, AdditionalEffect.CONFUSE)
                        elif spell.action is SpellAction.SLOW:
                            target.speed = 0 if target.speed > 0 else -1
                        elif spell.action is SpellAction.BREAK:
                            target.protection = (
                                0 if target.protection > 0 else -1
                            )
                        elif spell.action is SpellAction.SILENCE:
                            target.silenced = max(
                                target.silenced,
                                4
                                + int(
                                    self.roll(actor, target.spec.number, 11) * 3
                                ),
                            )
                        if spell.attribute is ResistanceType.POISON:
                            target.poisoned = True
        actor.hidden = False

    def status_success(self, actor, target, spell, modifier):
        return resolve_status_spell(
            spell_modifier=modifier,
            rate=spell.rate,
            target_spell_defense=target.spec.spell_defense,
            attribute=spell.attribute,
            target_weaknesses=target.spec.weaknesses,
            target_resistances=target.spec.resistances,
            success_roll=int(self.roll(actor, target.spec.number, 10) * 20),
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
        if action.command is BattleCommand.SPELL:
            actor.mp -= self.spells[action.spell_key].mp
        if action.command in (
            BattleCommand.ATTACK,
            BattleCommand.AMBUSH,
            BattleCommand.AIM,
            BattleCommand.IAI,
        ):
            self.physical(actor, action)
        elif action.command is BattleCommand.FOCUS:
            actor.focus = action.targets[0]
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
        elif action.command is BattleCommand.FORMATION:
            actor.front = not actor.front
        self.normalize()
        self.advance(actor, delay)
        return cost, actor.agility + delay

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
        available = tuple(a for a in self.allies() if not a.hidden)
        melee = tuple(a for a in available if a.front) if actor.front else ()
        escape = False
        if (
            MonsterSpecialAction.ESCAPE in actor.spec.special_actions
            and self.allies()
            and self.roll(actor, 0, 12) >= 0.5
        ):
            allies = self.allies()
            member = allies[int(self.roll(actor, 0, 13) * len(allies))]
            physical = (
                member.spec.weapons[0].attack
                if member.spec.weapons
                and member.equipment.weapon_at(EquipmentSlot.RIGHT) is not None
                else 0
            )
            escape = physical > actor.spec.attack * (1 + self.roll(actor, 0, 14))
        spell_keys = tuple(
            s.key for s in actor.spec.spells if self.spell_targets(actor, s)
        )
        candidates = monster_action_candidates(
            special_actions=actor.spec.special_actions,
            is_front_row=actor.front,
            can_attack=bool(melee),
            can_charge=bool(available),
            spell_keys=spell_keys,
            escape_eligible=escape,
        )
        silenced = actor.silenced > 0
        actor.silenced = max(0, actor.silenced - 1)
        if not candidates:
            self.advance(actor, 0)
            return
        key = lambda a: a.spell_key if isinstance(a, MonsterSpellAction) else a.value
        candidates = tuple(sorted(candidates, key=key))
        action = candidates[int(self.roll(actor, 0, 0) * len(candidates))]
        delay = 0
        if action is MonsterAction.ESCAPE:
            actor.removed = True
        elif isinstance(action, MonsterSpellAction):
            spell = self.spells[action.spell_key]
            if not silenced and actor.mp >= spell.mp:
                actor.mp -= spell.mp
                targets = self.spell_targets(actor, spell)
                if not spell.to_all:
                    targets = (targets[int(self.roll(actor, 0, 1) * len(targets))],)
                if spell.to_enemy and spell.action is SpellAction.DAMAGE:
                    for n in targets:
                        target = self.actors[n]
                        result = resolve_spell_damage(
                            intensity=spell.intensity,
                            spell_modifier=actor.spec.magic,
                            target_spell_defense=target.spec.spell_defense,
                            attribute=spell.attribute,
                            target_weaknesses=target.spec.weaknesses,
                            target_resistances=target.spec.resistances,
                            random_factor=self.roll(actor, target.spec.number, 5),
                        )
                        target.damage(result.damage)
                        target.interrupt_focus()
                if spell.to_enemy and spell.action in ENEMY_SPELL_ACTIONS:
                    for n in targets:
                        target = self.actors[n]
                        if (
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
                        ):
                            if spell.action is SpellAction.SLEEP:
                                self.apply_extra(actor, target, AdditionalEffect.SLEEP)
                            elif spell.action is SpellAction.CONFUSE:
                                self.apply_extra(
                                    actor,
                                    target,
                                    AdditionalEffect.CONFUSE,
                                )
                            elif spell.action is SpellAction.SLOW:
                                target.speed = 0 if target.speed > 0 else -1
                            else:
                                target.protection = (
                                    0 if target.protection > 0 else -1
                                )
        elif action in (MonsterAction.ATTACK, MonsterAction.CHARGE):
            targets = available if action is MonsterAction.CHARGE else melee
            protected = targets[int(self.roll(actor, 0, 1) * len(targets))]
            target = self.covering(protected.spec.number)
            if target is not protected:
                target.hidden = False
            charged = action is MonsterAction.CHARGE
            result = resolve_physical_attack(
                attack=int(actor.spec.attack * (1.5 if charged else 1)),
                hit=actor.spec.hit,
                target_defense=target.defense,
                target_evasion=target.evasion,
                target_defending=target.defending,
                target_unable_to_evade=target.focus is not None,
                target_incapacitated=bool(target.sleeping),
                hit_roll=int(self.roll(actor, target.spec.number, 2) * 100),
                critical_roll=int(self.roll(actor, target.spec.number, 3) * 100)
                if target.sleeping
                else None,
            )
            effect = actor.spec.effect
            if effect in PHYSICAL_STATUS_EFFECTS and (
                result.hit or (target.defending and result.hit_value >= 0)
            ):
                success = resolve_physical_additional_effect(
                    effect=effect,
                    adjusted_hit=result.adjusted_hit,
                    effect_roll=int(self.roll(actor, target.spec.number, 4) * 100),
                    target_is_member=True,
                    target_is_resistant=EFFECT_RESISTANCE[effect]
                    in target.spec.resistances,
                    target_defending=target.defending,
                    critical=result.critical,
                ).success
            else:
                success = False
            target.damage(result.damage)
            if success and target.is_alive:
                self.apply_extra(actor, target, effect)
            target.interrupt_focus()
            delay = -16 if charged else 0
        self.normalize()
        self.advance(actor, delay)

    def confused_turn(self, actor: ForecastActor) -> None:
        """Forecast DA2's forced same-side basic attack for one confused actor."""

        actor.confused = max(0, actor.confused - 1)
        if actor.spec.enemy:
            actor.silenced = max(0, actor.silenced - 1)
            friendly = tuple(a for a in self.enemies() if a is not actor)
            if friendly:
                targets = friendly
            else:
                visible = tuple(a for a in self.allies() if not a.hidden)
                targets = tuple(a for a in visible if a.front) if actor.front else ()
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
            target = targets[int(self.roll(actor, 0, 15) * len(targets))]
            self.confused_physical(actor, target)
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
            results = (
                resolve_physical_attack(
                    attack=actor.spec.attack,
                    hit=actor.spec.hit,
                    target_defense=target.defense,
                    target_evasion=target.evasion,
                    hit_roll=int(self.roll(actor, target.spec.number, 2) * 100),
                    target_defending=target.defending,
                    target_incapacitated=bool(target.sleeping),
                    critical_roll=(
                        int(self.roll(actor, target.spec.number, 3) * 100)
                        if target.sleeping
                        else None
                    ),
                ),
            )
            effect_sources = (
                ((actor.spec.effect, False),)
                if actor.spec.effect in PHYSICAL_STATUS_EFFECTS
                else (),
            )
        else:
            results = tuple(
                self.physical_results(
                    actor,
                    target,
                    AutoAction(BattleCommand.ATTACK, (target.spec.number,)),
                )
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
                if (
                    actor.has_skill("Lethal")
                    and weapon.effect is not AdditionalEffect.DEATH
                ):
                    candidates.append((AdditionalEffect.DEATH, False))
                effect_sources.append(tuple(candidates))

        for hand, (result, candidates) in enumerate(zip(results, effect_sources)):
            if not target.is_alive or not result.hit:
                continue
            target.damage(result.damage)
            for effect, stacked in candidates:
                if not target.is_alive:
                    break
                resistance = EFFECT_RESISTANCE[effect]
                success = resolve_physical_additional_effect(
                    effect=effect,
                    adjusted_hit=result.adjusted_hit,
                    effect_roll=int(
                        self.roll(actor, target.spec.number, 4 + hand * 3) * 100
                    ),
                    target_is_member=not target.spec.enemy,
                    target_is_boss=target.spec.boss,
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
                    stacked_death=stacked,
                ).success
                if success:
                    self.apply_extra(actor, target, effect)
        target.interrupt_focus()

    def prepare_turn(self, actor) -> bool:
        if not actor.spec.enemy:
            actor.defending = False
            actor.cover = None
        poison = (
            poison_tick_damage(
                max_hp=actor.max_hp,
                weak_to_poison=actor.spec.enemy
                and ResistanceType.POISON in actor.spec.weaknesses,
            )
            if actor.poisoned
            else 0
        )
        recovery = (
            battle_healing_amount(max_hp=actor.max_hp, healing=actor.spec.healing)
            if not actor.spec.enemy
            else 0
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
            self.surprise.discard(actor.spec.number)
            skipped = True
        if skipped and not actor.spec.enemy:
            actor.focus = None
        if skipped and actor.spec.enemy:
            actor.silenced = max(0, actor.silenced - 1)
        if delta or skipped or not actor.is_alive:
            self.normalize()
        return skipped or not actor.is_alive

    def normalize(self):
        for n, a in self.actors.items():
            if not a.is_alive and n in self.original_alive:
                self.died.add(n)
        allies = self.allies()
        self.defeated |= not allies or all(a.paralyzed for a in allies)
        self.surprise.intersection_update(a.spec.number for a in allies)
        if not self.surprise and self.original_rows:
            for n, front in self.original_rows.items():
                self.actors[n].front = front
            self.original_rows.clear()
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
