from __future__ import annotations

import random
import unittest
from dataclasses import FrozenInstanceError, replace
from math import floor
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT

# isort: split
from auto_battle import (
    VALUE_WEIGHTS,
    AutoBattlePlanner,
    decide_auto_battle,
    round_score,
)
from auto_battle_model import (
    CASE_COUNT,
    AutoAction,
    AutoActionEvaluation,
    AutoBattlePolicy,
    AutoBattleSnapshot,
    AutoCombatant,
    AutoWeapon,
    ItemMode,
    quantile,
)
from auto_battle_simulation import BattleForecast, mp_cost
from battle_commands import BattleCommand
from battle_layout import MonsterPlacement
from battle_magic import member_spell_ability, resolve_healing
from battle_physical import member_physical_attack, resolve_physical_attack
from battle_timeline import TimelineEntry, TimelineOrder
from event_flags import ABYSS_NOVA_UNSEALED, REVIVE2_UNSEALED, TELEPORT_UNSEALED
from item import AdditionalEffect
from member import EquipmentSlot
from monster import MonsterSpecialAction, MonsterTribe
from monster_ai import MonsterAction, MonsterSpellAction
from resistance import ResistanceType
from spell import SpellAction, SpellType
from state import AUTO_BATTLE_ITEM_KEYS, AUTO_BATTLE_SPELL_KINDS, AutoBattleConfig

from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
    load_mock_spells,
)


class AutoBattleFixtures:
    @classmethod
    def setUpClass(cls):
        cls.items = load_mock_items()
        cls.spells = load_mock_spells()
        cls.party = load_mock_party(
            cls.items,
            load_mock_skills(),
            character_keys=("Fiora", "Cerion", "Alvan"),
            internal_level=20,
        )
        cls.specs = tuple(
            AutoCombatant.from_member(
                m,
                i,
                front=True,
                spells=tuple(
                    s
                    for s in cls.spells.values()
                    if s.on_battle
                    and s.type is not SpellType.ITEM
                    and s.is_learned_by(m)
                ),
            )
            for i, m in enumerate(cls.party)
        )

    def snapshot(self, *combatants, active=0, gauges=None, policy=None):
        if not combatants:
            combatants = (self.specs[0], self.enemy())
        if gauges is None:
            gauges = tuple(
                (c.number, 64 - i * 10) for i, c in enumerate(combatants) if c.alive
            )
        return AutoBattleSnapshot(
            tuple(combatants),
            gauges,
            active,
            tuple(self.spells.values()),
            policy or AutoBattlePolicy(),
        )

    @staticmethod
    def enemy(number=5, **changes):
        return replace(
            AutoCombatant(
                number,
                "enemy:" + str(number),
                True,
                120,
                120,
                agility=15,
                attack=20,
                hit=100,
                hp_displayed=True,
                known_fields=frozenset(("profile",)),
            ),
            **changes,
        )


class AutoBattleRulesTest(AutoBattleFixtures, unittest.TestCase):
    def test_forecast_resumes_rotation_and_waits_in_rear_attack_slot(self):
        freeze, confusion = (self.spells[key] for key in ("FREEZE2", "CONFUSION"))
        caster = self.enemy(
            intelligence=3, action_rotation_index=2, front=False,
            mp=20, max_mp=20, spells=(freeze, confusion),
        )
        front = self.enemy(number=6)
        forecast = BattleForecast(self.snapshot(caster, self.specs[0], front, active=5), 0)
        actor = forecast.actors[5]
        with (
            patch.object(forecast, "advance"),
            patch.object(forecast, "enemy_attack") as attack,
            patch("auto_battle_simulation.quantile", side_effect=AssertionError("already seeded")),
            patch.object(forecast, "roll", return_value=0.5),
        ):
            forecast.enemy_turn(actor)
            self.assertEqual((actor.mp, actor.action_rotation_index), (20, 0))
            self.assertFalse(actor.defending)
            attack.assert_not_called()
            forecast.enemy_turn(actor)
            self.assertEqual((actor.mp, actor.action_rotation_index), (20 - freeze.mp, 1))
            actor.silenced = 1
            forecast.enemy_turn(actor)
            self.assertEqual((actor.mp, actor.action_rotation_index), (20 - freeze.mp, 0))
            self.assertEqual(actor.silenced, 0)
            actor.front = True
            actor.mp = 0
            forecast.enemy_turn(actor)
            attack.assert_called_once()
            self.assertEqual(actor.action_rotation_index, 0)

    def test_forecast_rotating_call_adds_a_new_enemy_with_independent_rotation(self):
        caller = self.enemy(
            intelligence=3, action_rotation_index=0,
            hp=29, mp=0, max_mp=12, special_actions=(MonsterSpecialAction.CALL,),
            monster_placement=MonsterPlacement(2, 68, 16, 64, 64),
        )
        forecast = BattleForecast(self.snapshot(caller, self.specs[0], active=5), 0)
        forecast.enemy_turn(forecast.actors[5])

        newcomer = forecast.actors[6]
        self.assertIn(6, forecast.order.actors)
        self.assertEqual(newcomer.spec.monster_placement.slot, 0)
        self.assertEqual((newcomer.hp, newcomer.mp, newcomer.front), (120, 12, False))
        self.assertIsNone(newcomer.action_rotation_index)
        self.assertEqual(forecast.actors[5].action_rotation_index, 1)

        decision = decide_auto_battle(self.snapshot(self.specs[0], caller))
        self.assertTrue(decision.evaluations)

    def test_forecast_rotating_escape_removes_enemy_without_eligibility_rolls(self):
        enemy = self.enemy(
            intelligence=3, action_rotation_index=0, attack=60,
            special_actions=(MonsterSpecialAction.ESCAPE,),
        )
        ally = replace(self.specs[0], weapons=())
        forecast = BattleForecast(self.snapshot(enemy, ally, active=5), 0)
        actor = forecast.actors[5]

        with patch.object(forecast, "roll", return_value=0) as roll:
            forecast.enemy_turn(actor)

        self.assertTrue(actor.removed)
        self.assertNotIn(5, forecast.order.actors)
        self.assertEqual(actor.action_rotation_index, 1)
        roll.assert_not_called()

    def test_enemy_forecast_protection_and_healing_affect_living_monster_targets(self):
        protection, heal = (self.spells[key] for key in ("PROTECTION", "HEALING1"))
        caster = self.enemy(
            mp=20, max_mp=20, magic=12, protection=2, spells=(protection, heal),
        )
        target = self.enemy(number=6, defense=8, hp=100, protection=1)
        forecast = BattleForecast(self.snapshot(caster, self.specs[0], target, active=5), 0)
        actor = forecast.actors[5]
        target = forecast.actors[6]
        forecast.roll = Mock(return_value=0.5)

        self.assertEqual(forecast.spell_targets(actor, protection), (6,))
        with patch(
            "auto_battle_simulation.monster_action_candidates",
            return_value=(MonsterSpellAction(protection.key),),
        ):
            forecast.enemy_turn(actor)
        self.assertEqual((target.protection, target.defense), (2, 27))

        self.assertEqual(forecast.spell_targets(actor, heal), (6,))
        with patch(
            "auto_battle_simulation.monster_action_candidates",
            return_value=(MonsterSpellAction(heal.key),),
        ):
            forecast.enemy_turn(actor)
        self.assertEqual(target.hp, 120)
        self.assertEqual(actor.mp, 20 - protection.mp - heal.mp)
        self.assertEqual(forecast.spell_targets(actor, heal), ())

    def test_enemy_forecast_applies_haste_and_steals_only_hp_lost(self):
        haste = self.spells["HASTE"]
        blood_suck = self.spells["BLOOD SUCK"]
        actor_spec = self.enemy(
            hp=50, mp=11, max_mp=11, magic=15, speed=-1, slow_turns=4,
            spells=(haste, blood_suck),
        )
        waiting = self.enemy(number=6, speed=2)
        ally = replace(self.specs[0], hp=3)
        forecast = BattleForecast(self.snapshot(actor_spec, ally, waiting, active=5), 0)
        actor = forecast.actors[5]
        ally = forecast.actors[0]
        forecast.roll = Mock(return_value=0.5)

        self.assertEqual(forecast.spell_targets(actor, haste), (5,))
        with patch(
            "auto_battle_simulation.monster_action_candidates",
            return_value=(MonsterSpellAction(haste.key),),
        ):
            forecast.enemy_turn(actor)
        self.assertEqual((actor.speed, actor.slow_turns, actor.mp), (0, 0, 7))

        with patch(
            "auto_battle_simulation.monster_action_candidates",
            return_value=(MonsterSpellAction(blood_suck.key),),
        ):
            forecast.enemy_turn(actor)
        self.assertEqual((actor.hp, actor.mp, ally.hp), (53, 2, 0))

    def test_rear_ranged_enemy_forecast_can_hit_a_visible_rear_member_twice(self):
        front = self.specs[0]
        rear = replace(self.specs[1], front=False)
        hidden = replace(self.specs[2], front=False, hidden=True)
        enemy = self.enemy(
            front=False, attack=100, hit=200,
            special_actions=(MonsterSpecialAction.RANGED_ATTACK, MonsterSpecialAction.DOUBLE_ATTACK),
        )
        forecast = BattleForecast(self.snapshot(enemy, front, rear, hidden, active=5), 0)
        actor = forecast.actors[5]
        with (
            patch.object(forecast, "roll", side_effect=lambda _, __, purpose: 0.99 if purpose in (1, 6) else 0.0),
            patch.object(forecast, "enemy_physical", wraps=forecast.enemy_physical) as physical,
        ):
            forecast.enemy_turn(actor)

        self.assertEqual([call.args[1].spec.number for call in physical.call_args_list], [1, 1])
        self.assertLess(forecast.actors[1].hp, rear.hp)
        self.assertEqual(forecast.actors[0].hp, front.hp)
        self.assertEqual(forecast.actors[2].hp, hidden.hp)

    def test_enemy_double_attack_forecast_retargets_after_front_member_dies(self):
        front = replace(self.specs[0], hp=1)
        rear = replace(self.specs[1], front=False)
        enemy = self.enemy(attack=100, special_actions=(MonsterSpecialAction.DOUBLE_ATTACK,))
        forecast = BattleForecast(self.snapshot(
            enemy, front, rear, active=5,
        ), 0)
        actor = forecast.actors[5]

        with (
            patch("auto_battle_simulation.monster_action_candidates", return_value=(MonsterAction.ATTACK,)),
            patch.object(forecast, "roll", return_value=0.0) as roll,
        ):
            forecast.enemy_turn(actor)

        self.assertEqual(forecast.actors[0].hp, 0)
        self.assertLess(forecast.actors[1].hp, rear.hp)
        roll.assert_any_call(actor, 0, 2)
        roll.assert_any_call(actor, 1, 7)
        self.assertEqual(forecast.turns[5], 1)

    def test_member_snapshot_preserves_each_hands_effective_tribe(self):
        member = load_mock_party(
            self.items, load_mock_skills(), character_keys=("Fiora",)
        )[0]
        member.skills.append(load_mock_skills()["Dual-Wield"])
        member.equipment = member.equipment.replaced({
            EquipmentSlot.RIGHT: self.items["GOBLIN SLAYER"],
            EquipmentSlot.LEFT: self.items["IRON SWORD"],
        })
        spec = AutoCombatant.from_member(member, 0, front=True, spells=())
        self.assertEqual(
            tuple(w.effective_tribe for w in spec.weapons),
            (MonsterTribe.GOBLIN, None),
        )

    def test_forecast_tribe_bonus_matches_attribute_bonus_without_stacking(self):
        action = AutoAction(BattleCommand.ATTACK, (5,))
        for command in (BattleCommand.ATTACK, BattleCommand.AIM, BattleCommand.FOCUS,
                        BattleCommand.AMBUSH, BattleCommand.IAI):
            action = replace(action, command=command)
            results = []
            for tribe, attribute in (
                (None, None),
                (MonsterTribe.GOBLIN, None),
                (None, ResistanceType.FIRE),
                (MonsterTribe.GOBLIN, ResistanceType.FIRE),
            ):
                actor = replace(self.specs[0], weapons=(AutoWeapon(
                    attack=100, hit=100, iai_attack=60,
                    effective_tribe=tribe, attribute=attribute,
                ),))
                enemy = self.enemy(tribe=MonsterTribe.GOBLIN,
                                   weaknesses=frozenset((ResistanceType.FIRE,)))
                forecast = BattleForecast(self.snapshot(actor, enemy), 0)
                forecast.roll = lambda *args: 0.99
                results.append(forecast.physical_results(
                    forecast.actors[0], forecast.actors[5], action,
                )[0])
            with self.subTest(command=command):
                normal, tribe, attribute, both = results
                self.assertEqual(tribe, attribute)
                self.assertEqual(both, tribe)
                self.assertEqual(tribe.hit_value, normal.hit_value + 60)
                self.assertTrue(tribe.critical)
                self.assertGreater(tribe.damage, normal.damage)

    def test_forecast_tribe_and_attribute_additional_effects_do_not_stack(self):
        # Death resistance leaves zero points after stacked death, critical,
        # and one effectiveness bonus. A second bonus would kill the target.
        for attribute in (None, ResistanceType.FIRE):
            actor = replace(self.specs[0], weapons=(AutoWeapon(
                attack=1, hit=100, effective_tribe=MonsterTribe.GOBLIN,
                attribute=attribute, effect=AdditionalEffect.DEATH,
            ),), skills=frozenset(("Lethal",)))
            enemy = self.enemy(
                tribe=MonsterTribe.GOBLIN,
                weaknesses=frozenset((ResistanceType.FIRE,)),
                resistances=frozenset((ResistanceType.DEATH,)),
            )
            forecast = BattleForecast(self.snapshot(actor, enemy), 0)
            forecast.roll = lambda *args: 0.99
            forecast.physical(forecast.actors[0], AutoAction(BattleCommand.ATTACK, (5,)))
            self.assertTrue(forecast.actors[5].is_alive)

    def test_forecast_unrevealed_or_different_tribe_has_no_bonus(self):
        actor = replace(self.specs[0], weapons=(AutoWeapon(
            attack=100, hit=100, effective_tribe=MonsterTribe.GOBLIN,
        ),))
        for tribe in (None, MonsterTribe.ANIMAL):
            forecast = BattleForecast(self.snapshot(actor, self.enemy(tribe=tribe)), 0)
            forecast.roll = lambda *args: 0.99
            result = forecast.physical_results(
                forecast.actors[0], forecast.actors[5], AutoAction(BattleCommand.ATTACK, (5,)),
            )[0]
            self.assertEqual(result.hit_value, 1)
            self.assertFalse(result.critical)

    def test_confused_forecast_against_enemy_keeps_species_status_bonus(self):
        actor = replace(self.specs[0], weapons=(AutoWeapon(
            attack=1, hit=100, effective_tribe=MonsterTribe.GOBLIN,
            effect=AdditionalEffect.POISON,
        ),))
        enemy = self.enemy(
            tribe=MonsterTribe.GOBLIN,
            resistances=frozenset((ResistanceType.POISON, ResistanceType.DEATH)),
        )
        forecast = BattleForecast(self.snapshot(actor, enemy), 0)
        forecast.roll = lambda *args: 0.99
        forecast.confused_physical(forecast.actors[0], forecast.actors[5])
        self.assertTrue(forecast.actors[5].poisoned)

    def test_expected_damage_accounts_for_confusion_in_cached_estimates(self):
        member = replace(self.specs[0], weapons=(AutoWeapon(50, 0),))
        enemy = self.enemy(defense=0, evasion=100)
        forecast = BattleForecast(self.snapshot(member, enemy), 0)
        forecast.roll = Mock(return_value=0.99)
        attacker, target = forecast.actors[0], forecast.actors[5]
        action = AutoAction(BattleCommand.ATTACK, (5,))

        self.assertEqual(forecast.expected_damage(attacker, target, action), 0)
        target.confused = 2
        self.assertGreater(forecast.expected_damage(attacker, target, action), 0)
        forecast.physical(attacker, action)
        self.assertEqual(target.confused, 0)
        self.assertEqual(forecast.expected_damage(attacker, target, action), 0)

    def test_score_rounding_and_safety_bucket_boundaries(self):
        self.assertEqual(round_score(1.23445), 1.2345)
        self.assertEqual(round_score(-1.23445), -1.2345)
        snapshot = self.snapshot()
        safe = AutoActionEvaluation(
            AutoAction(BattleCommand.DEFEND), (), 0, 0, 0, 3 / 64, 0, 0, 15, 0
        )
        risky = replace(safe, defeat_fraction=4 / 64, score=100, rounded_score=100)
        self.assertLess(safe.selection_key(snapshot), risky.selection_key(snapshot))
        safe = replace(safe, defeat_fraction=0, new_deaths=15 / 64)
        risky = replace(risky, defeat_fraction=0, new_deaths=16 / 64)
        self.assertLess(safe.selection_key(snapshot), risky.selection_key(snapshot))
        costly = replace(safe, current_cost=1)
        self.assertLess(safe.selection_key(snapshot), costly.selection_key(snapshot))

    def test_documented_component_calculations(self):
        weights = dict(
            zip(
                (
                    "victory",
                    "defeat",
                    "deaths",
                    "health",
                    "ability",
                    "kills",
                    "damage",
                    "information",
                ),
                VALUE_WEIGHTS,
            )
        )

        def score(cost=0, **parts):
            return sum(weights[k] * v for k, v in parts.items()) - cost

        self.assertEqual(score(deaths=-0.5, health=0.2, ability=0.2, cost=5), 311)
        self.assertEqual(score(damage=0.4), 8)
        self.assertEqual(score(kills=0.4, damage=0.5), 42)
        self.assertEqual(score(kills=0.3, damage=0.6), 36)

    def test_defend_requires_better_safety_bucket_than_attack(self):
        # A durable counterattacker rewards guarding in the raw score. Only
        # an improvement in defeat/death buckets should justify that choice.
        for hp, enemy_attack, expected, safety_index in (
            (250, 30, BattleCommand.ATTACK, None),
            (100, 30, BattleCommand.ATTACK, None),
            (20, 30, BattleCommand.DEFEND, 1),
            (250, 80, BattleCommand.DEFEND, 0),
            (250, 150, BattleCommand.ATTACK, None),
        ):
            with self.subTest(hp=hp, enemy_attack=enemy_attack):
                actor = replace(
                    self.specs[0], hp=hp, max_hp=250, spells=(),
                    skills=frozenset(), weapons=(AutoWeapon(80, 100),),
                )
                ally = replace(
                    self.specs[2], hp=250, max_hp=250, spells=(),
                    skills=frozenset(),
                )
                enemy = self.enemy(
                    hp=1800, max_hp=1800, attack=enemy_attack,
                    special_actions=(
                        MonsterSpecialAction.COUNTER,
                        MonsterSpecialAction.POWER_HIT,
                    ),
                )
                snapshot = self.snapshot(
                    actor, ally, enemy,
                    gauges=((0, 64), (5, 63), (2, 62)),
                )
                result = decide_auto_battle(snapshot)
                attack = next(e for e in result.evaluations
                              if e.action.command is BattleCommand.ATTACK)
                defend = next(e for e in result.evaluations
                              if e.action.command is BattleCommand.DEFEND)
                self.assertGreater(defend.score, attack.score)
                self.assertEqual(result.action.command, expected)
                if safety_index is None:
                    self.assertEqual(defend.selection_key(snapshot)[:2],
                                     attack.selection_key(snapshot)[:2])
                    self.assertEqual(defend.exclusion,
                                     "defend_no_safety_improvement")
                else:
                    self.assertLess(defend.selection_key(snapshot)[safety_index],
                                    attack.selection_key(snapshot)[safety_index])
                    self.assertEqual(defend.exclusion, "")

    def test_resisted_spell_loses_advantage_from_leaving_breath_weaker(self):
        ally = replace(
            self.specs[1], hp=140, max_hp=200, agility=23, front=False,
            spells=(), skills=frozenset(), weapons=(AutoWeapon(40, 100),),
        )
        for spell_key, resistance, breath in (
            ("FIRE1", ResistanceType.FIRE, MonsterSpecialAction.FIRE_BREATH),
            ("POISON1", ResistanceType.POISON, MonsterSpecialAction.POISON_BREATH),
        ):
            with self.subTest(spell=spell_key):
                actor = replace(
                    self.specs[0], hp=145, max_hp=180,
                    spells=(self.spells[spell_key],), skills=frozenset(),
                    weapons=(AutoWeapon(145, 100),),
                )
                enemy = self.enemy(
                    hp=625, max_hp=700, attack=80, defense=20,
                    special_actions=(breath,), resistances=frozenset((resistance,)),
                    known_fields=frozenset(("profile", resistance.value)),
                )
                snapshot = self.snapshot(
                    actor, ally, enemy, gauges=((0, 64), (5, 63), (1, 31)),
                )

                result = decide_auto_battle(snapshot)

                self.assertEqual(result.reason, "breath_comparison")
                unadjusted = min(
                    (e for e in result.unadjusted_evaluations if not e.exclusion),
                    key=lambda e: e.selection_key(snapshot),
                )
                self.assertEqual(unadjusted.action.spell_key, spell_key)
                self.assertEqual(result.action, AutoAction(BattleCommand.ATTACK, (5,)))

    def test_defend_still_buys_time_for_healing_at_equal_breath_power(self):
        actor = replace(
            self.specs[0], hp=40, max_hp=180, spells=(), skills=frozenset(),
            weapons=(AutoWeapon(100, 100),),
        )
        ally = replace(
            self.specs[1], hp=150, max_hp=200, agility=31, front=False,
            spells=(), skills=frozenset(), weapons=(AutoWeapon(40, 100),),
        )
        enemy = self.enemy(
            attack=50, hp=500, max_hp=500, defense=5,
            special_actions=(MonsterSpecialAction.FIRE_BREATH,),
        )
        for spells, expected in (
            ((), BattleCommand.ATTACK),
            ((self.spells["HEALING1"],), BattleCommand.DEFEND),
        ):
            with self.subTest(healing_available=bool(spells)):
                snapshot = self.snapshot(
                    actor, replace(ally, spells=spells), enemy,
                    gauges=((0, 64), (5, 63), (1, 31)),
                )
                result = decide_auto_battle(snapshot)

                self.assertEqual(result.reason, "breath_comparison")
                unadjusted = min(
                    (e for e in result.unadjusted_evaluations if not e.exclusion),
                    key=lambda e: e.selection_key(snapshot),
                )
                self.assertIs(unadjusted.action.command, BattleCommand.DEFEND)
                self.assertIs(result.action.command, expected)

    def test_killing_enemy_before_breath_keeps_its_full_safety_benefit(self):
        actor = replace(
            self.specs[0], spells=(), skills=frozenset(),
            weapons=(AutoWeapon(100, 100),),
        )
        enemy = self.enemy(
            hp=20, attack=300, special_actions=(MonsterSpecialAction.FIRE_BREATH,),
        )

        result = decide_auto_battle(self.snapshot(actor, enemy))

        self.assertEqual(result.reason, "simulation")
        self.assertEqual(result.action, AutoAction(BattleCommand.ATTACK, (5,)))

    def test_hide_and_defend_use_the_same_attack_baseline(self):
        for hp, enemy_hp, enemy_attack, attack_risk, defend_risk, hide_risk, expected in (
            (250, 400, 80, (0, 0), (0, 0), (0, 0), BattleCommand.ATTACK),
            (100, 400, 55, (0, 1), (0, 1), (0, 0), BattleCommand.HIDE),
            (100, 1800, 80, (16, 8), (14, 7), (14, 7), BattleCommand.DEFEND),
            (20, 400, 150, (6, 4), (4, 3), (4, 3), BattleCommand.HIDE),
        ):
            with self.subTest(hp=hp, enemy_hp=enemy_hp, enemy_attack=enemy_attack):
                actor = replace(
                    self.specs[0], hp=hp, max_hp=250, spells=(),
                    skills=frozenset(("Hide",)), weapons=(AutoWeapon(80, 80),),
                )
                ally = replace(
                    self.specs[2], hp=250, max_hp=250, spells=(), skills=frozenset(),
                )
                enemy = self.enemy(
                    hp=enemy_hp, max_hp=enemy_hp, attack=enemy_attack,
                    special_actions=(MonsterSpecialAction.COUNTER, MonsterSpecialAction.POWER_HIT),
                )
                snapshot = self.snapshot(
                    actor, ally, enemy, gauges=((0, 64), (5, 63), (2, 62)),
                    policy=AutoBattlePolicy(item_mode=ItemMode.NEVER),
                )

                result = decide_auto_battle(snapshot)

                evaluations = {e.action.command: e for e in result.evaluations}
                attack = evaluations[BattleCommand.ATTACK]
                self.assertEqual(attack.selection_key(snapshot)[:2], attack_risk)
                for command, risk in (
                    (BattleCommand.DEFEND, defend_risk), (BattleCommand.HIDE, hide_risk),
                ):
                    evaluation = evaluations[command]
                    self.assertEqual(evaluation.selection_key(snapshot)[:2], risk)
                    self.assertEqual(
                        evaluation.exclusion,
                        f"{command.value}_no_safety_improvement" if risk >= attack_risk else "",
                    )
                if expected is BattleCommand.ATTACK:
                    self.assertGreater(evaluations[BattleCommand.HIDE].score, attack.score)
                self.assertEqual(result.action.command, expected)

    def test_defend_remains_fallback_when_no_other_action_is_available(self):
        actor = replace(
            self.specs[0], front=False, spells=(), skills=frozenset(),
            equipment=self.specs[0].equipment.replaced({
                EquipmentSlot.RIGHT: self.items["IRON SWORD"],
                EquipmentSlot.LEFT: None,
            }),
        )
        result = decide_auto_battle(self.snapshot(
            actor, self.specs[2], self.enemy(),
            policy=AutoBattlePolicy(item_mode=ItemMode.NEVER),
        ))
        self.assertEqual(result.action.command, BattleCommand.DEFEND)
        self.assertEqual(len(result.evaluations), 1)
        self.assertEqual(result.evaluations[0].exclusion, "")

    def test_hide_must_improve_on_defend_when_only_those_two_are_available(self):
        actor = replace(
            self.specs[0], front=False, hp=250, max_hp=250, spells=(),
            skills=frozenset(("Hide",)), weapons=(AutoWeapon(80, 80),),
            equipment=self.specs[0].equipment.replaced({
                EquipmentSlot.RIGHT: self.items["IRON SWORD"],
                EquipmentSlot.LEFT: None,
            }),
        )
        ally = replace(self.specs[2], hp=250, max_hp=250, spells=(), skills=frozenset())
        for enemy_attack, expected in ((30, BattleCommand.DEFEND), (150, BattleCommand.HIDE)):
            with self.subTest(enemy_attack=enemy_attack):
                snapshot = self.snapshot(
                    actor, ally, self.enemy(
                        hp=400, max_hp=400, attack=enemy_attack,
                        special_actions=(MonsterSpecialAction.COUNTER, MonsterSpecialAction.POWER_HIT),
                    ),
                    gauges=((0, 64), (5, 63), (2, 62)),
                    policy=AutoBattlePolicy(item_mode=ItemMode.NEVER),
                )

                result = decide_auto_battle(snapshot)

                evaluations = {e.action.command: e for e in result.evaluations}
                self.assertEqual(set(evaluations), {BattleCommand.DEFEND, BattleCommand.HIDE})
                self.assertEqual(evaluations[BattleCommand.DEFEND].exclusion, "")
                self.assertEqual(
                    evaluations[BattleCommand.HIDE].exclusion,
                    "hide_no_safety_improvement" if expected is BattleCommand.DEFEND else "",
                )
                self.assertEqual(result.action.command, expected)

    def test_urgent_heal_is_chosen_before_immediately_dangerous_enemy(self):
        healer = replace(self.specs[1], hp=25)
        enemy = self.enemy(attack=40, hp=1000, max_hp=1000)
        with (
            patch.object(AutoBattlePlanner, "_forecast", side_effect=AssertionError),
            patch.object(BattleForecast, "execute", side_effect=AssertionError),
            patch.object(BattleForecast, "step", side_effect=AssertionError),
        ):
            result = decide_auto_battle(self.snapshot(healer, enemy, active=1))
        self.assertEqual(result.action.spell_key, "HEALING1")
        self.assertEqual(result.reason, "recovery_urgent")
        self.assertEqual(result.evaluations, ())
        self.assertEqual((result.case_count, result.forecast_turns), (0, 0))

    def test_required_heal_is_not_skipped_even_for_immediate_victory(self):
        healer = replace(self.specs[1], hp=25, mp=3)
        snapshot = self.snapshot(healer, self.enemy(hp=1, max_hp=1), active=1)
        before = repr(snapshot)
        random_before = random.getstate()
        result = decide_auto_battle(snapshot)
        self.assertEqual(result.action.spell_key, "HEALING1")
        self.assertEqual(result.action.targets, (1,))
        self.assertEqual(repr(snapshot), before)
        self.assertEqual(random.getstate(), random_before)

    def test_current_hp_thresholds_and_no_recovery_in_simulated_candidates(self):
        for hp, reason in (
            (35, "recovery_urgent"),
            (36, "recovery_heal"),
            (59, "recovery_heal"),
            (60, "simulation"),
        ):
            with self.subTest(hp=hp):
                healer = replace(self.specs[1], hp=hp, max_hp=100)
                result = decide_auto_battle(
                    self.snapshot(healer, self.enemy(hp=1, max_hp=1), active=1)
                )
                self.assertEqual(result.reason, reason)
                if hp < 60:
                    self.assertEqual(result.action.spell_key, "HEALING1")
                else:
                    self.assertIn(("HEALING1", "recovery_not_needed"), result.excluded)
                    self.assertFalse(
                        any(
                            e.action.spell_key
                            and self.spells[e.action.spell_key].action
                            is SpellAction.HEAL
                            for e in result.evaluations
                        )
                    )

    def test_recovery_selects_adequate_heal_or_largest_available_heal(self):
        for maximum in (100, 1000):
            healer = replace(
                self.specs[1],
                hp=10,
                max_hp=maximum,
                mp=7,
                magic=10,
                spells=(self.spells["HEALING1"], self.spells["HEALING2"]),
            )
            result = decide_auto_battle(self.snapshot(healer, self.enemy(), active=1))
            self.assertEqual(result.action.spell_key, "HEALING2")

    def test_full_recovery_prioritizes_paralysis_confusion_and_stun_at_full_hp(self):
        ring = replace(self.items["MIRACLE RING"], use_spell_key="PANACEA")
        caster = replace(
            self.specs[1],
            mp=0,
            silenced=2,
            equipment=self.specs[1].equipment.replaced({EquipmentSlot.ARM: ring}),
        )
        for field, value in (
            ("paralyzed", True),
            ("confused", 2),
            ("stunned", True),
        ):
            with self.subTest(field=field):
                ally = replace(self.specs[0], **{field: value})
                with patch.object(BattleForecast, "step", side_effect=AssertionError):
                    result = decide_auto_battle(
                        self.snapshot(caster, ally, self.enemy(), active=1)
                    )
                self.assertEqual(result.reason, "recovery_cure")
                self.assertEqual(result.action.command, BattleCommand.ITEM)
                self.assertEqual(result.action.targets, (0,))
                self.assertEqual(result.action.spell_key, "PANACEA")

    def test_dedicated_cure_still_prioritizes_paralysis_and_confusion(self):
        caster = replace(
            self.specs[1],
            spells=(self.spells["CURE"],),
            mp=self.spells["CURE"].mp,
        )
        for field, value in (
            ("paralyzed", True),
            ("confused", 2),
        ):
            with self.subTest(field=field):
                ally = replace(self.specs[0], **{field: value})
                result = decide_auto_battle(
                    self.snapshot(caster, ally, self.enemy(), active=1)
                )
                self.assertEqual(result.reason, "recovery_cure")
                self.assertEqual(result.action.spell_key, "CURE")
                self.assertEqual(result.action.targets, (0,))

    def test_poison_and_sleep_treatments_compete_with_attacks_in_the_forecast(self):
        caster = replace(
            self.specs[1], spells=(self.spells["CURE"],), skills=frozenset(),
            weapons=(AutoWeapon(120, 200),),
        )
        cases = (
            ({"poisoned": True}, 1, BattleCommand.ATTACK),
            ({"poisoned": True, "stunned": True}, 1, BattleCommand.ATTACK),
            ({"sleeping": 3}, 1, BattleCommand.ATTACK),
            ({"poisoned": True, "max_hp": 320, "hp": 15}, 350, BattleCommand.SPELL),
            ({"sleeping": 3}, 350, BattleCommand.SPELL),
        )
        for ailments, enemy_hp, expected in cases:
            with self.subTest(ailments=ailments, enemy_hp=enemy_hp):
                ally = replace(
                    self.specs[0], spells=(), skills=frozenset(),
                    weapons=(AutoWeapon(170, 200),), **ailments,
                )
                enemy = self.enemy(hp=enemy_hp, max_hp=enemy_hp, attack=10)
                snapshot = self.snapshot(caster, ally, enemy, active=1)
                result = decide_auto_battle(snapshot)
                self.assertEqual(result.reason, "simulation")
                self.assertEqual(result.action.command, expected)
                self.assertEqual((result.case_count, result.forecast_turns), (8, 16))
                cure = next(e for e in result.evaluations if e.action.spell_key == "CURE")
                attack = next(e for e in result.evaluations if e.action.command is BattleCommand.ATTACK)
                self.assertEqual(cure.action.targets, (0,))
                self.assertGreater(cure.current_cost, 0)
                if expected is BattleCommand.SPELL:
                    self.assertEqual(result.action, cure.action)
                    if ally.poisoned:
                        self.assertLess(cure.new_deaths, attack.new_deaths)
                    else:
                        self.assertGreater(
                            dict(cure.components)["ability"], dict(attack.components)["ability"]
                        )

    def test_full_recovery_for_sleep_is_evaluated_even_at_full_hp(self):
        ring = replace(self.items["MIRACLE RING"], use_spell_key="PANACEA")
        caster = replace(
            self.specs[1], mp=0, skills=frozenset(), weapons=(AutoWeapon(120, 200),),
            equipment=self.specs[1].equipment.replaced({EquipmentSlot.ARM: ring}),
        )
        ally = replace(self.specs[0], sleeping=2)
        snapshot = self.snapshot(caster, ally, self.enemy(hp=1, max_hp=1), active=1)
        result = decide_auto_battle(snapshot)
        self.assertEqual(result.action.command, BattleCommand.ATTACK)
        action = AutoAction(BattleCommand.ITEM, (0,), "PANACEA", EquipmentSlot.ARM.value)
        self.assertIn(action, tuple(e.action for e in result.evaluations))
        forecast = BattleForecast(snapshot, 0)
        self.assertEqual(forecast.continuation(1, {5: 1}).command, BattleCommand.ATTACK)
        forecast.execute(1, action)
        self.assertEqual(forecast.actors[0].sleeping, 0)

    def test_revive_is_selected_for_the_first_dead_member(self):
        dead = replace(self.specs[0], hp=0, alive=False)
        caster = replace(
            self.specs[1],
            spells=(self.spells["REVIVE1"],),
            mp=self.spells["REVIVE1"].mp,
        )

        result = decide_auto_battle(
            self.snapshot(caster, dead, self.enemy(), active=1)
        )

        self.assertEqual(result.reason, "recovery_revive")
        self.assertEqual(result.action.spell_key, "REVIVE1")
        self.assertEqual(result.action.targets, (0,))

    def test_revive_prefers_the_larger_restored_hp_before_mp_cost(self):
        dead = replace(self.specs[0], hp=0, alive=False, max_hp=100)
        caster = replace(
            self.specs[1],
            spells=(self.spells["REVIVE1"], self.spells["REVIVE2"]),
            mp=99,
            max_mp=99,
        )

        result = decide_auto_battle(
            self.snapshot(caster, dead, self.enemy(), active=1)
        )

        self.assertEqual(result.action.spell_key, "REVIVE2")

    def test_forecast_revive_restores_hp_and_returns_target_to_timeline(self):
        dead = replace(self.specs[0], hp=0, alive=False, max_hp=100)
        caster = replace(
            self.specs[1],
            spells=(self.spells["REVIVE1"],),
            mp=99,
            max_mp=99,
        )
        forecast = BattleForecast(
            self.snapshot(caster, dead, self.enemy(), active=1),
            0,
        )

        forecast.cast(
            forecast.actors[1],
            AutoAction(BattleCommand.SPELL, (0,), "REVIVE1"),
        )

        self.assertEqual(forecast.actors[0].hp, 25)
        self.assertIn(0, forecast.order.actors)

    def test_forecast_applies_haste_cure_and_silence(self):
        caster = replace(
            self.specs[1],
            spells=(
                self.spells["HASTE"],
                self.spells["CURE"],
                self.spells["SILENCE"],
            ),
            mp=99,
            max_mp=99,
        )
        ally = replace(self.specs[0], poisoned=True, speed=-1)
        enemy = self.enemy(
            spells=(self.spells["SLEEP"],),
            spell_defense=0,
        )
        forecast = BattleForecast(
            self.snapshot(caster, ally, enemy, active=1),
            0,
        )
        forecast.roll = Mock(return_value=0.0)
        spell_actions = {
            (action.spell_key, action.targets)
            for action in forecast.candidates(1)
            if action.command is BattleCommand.SPELL
        }
        self.assertIn(("HASTE", (0,)), spell_actions)
        self.assertIn(("CURE", (0,)), spell_actions)
        self.assertIn(("SILENCE", (5,)), spell_actions)

        forecast.cast(
            forecast.actors[1],
            AutoAction(BattleCommand.SPELL, (0,), "HASTE"),
        )
        forecast.cast(
            forecast.actors[1],
            AutoAction(BattleCommand.SPELL, (0,), "CURE"),
        )
        forecast.cast(
            forecast.actors[1],
            AutoAction(BattleCommand.SPELL, (5,), "SILENCE"),
        )

        self.assertEqual(forecast.actors[0].speed, 0)
        self.assertFalse(forecast.actors[0].poisoned)
        self.assertEqual(forecast.actors[5].silenced, 4)

    def test_urgent_heal_precedes_treatment_of_another_ally(self):
        ring = replace(self.items["MIRACLE RING"], use_spell_key="PANACEA")
        wounded = replace(self.specs[0], hp=1)
        sleeping = replace(self.specs[2], sleeping=2)
        caster = replace(
            self.specs[1],
            equipment=self.specs[1].equipment.replaced({EquipmentSlot.ARM: ring}),
        )
        result = decide_auto_battle(
            self.snapshot(caster, wounded, sleeping, self.enemy(), active=1)
        )
        self.assertEqual(result.reason, "recovery_urgent")
        self.assertEqual(result.action.targets, (0,))

    def test_hidden_wounded_ally_does_not_block_other_recovery(self):
        hidden = replace(self.specs[0], hidden=True, hp=1)
        wounded = replace(self.specs[2], hp=20)
        result = decide_auto_battle(
            self.snapshot(self.specs[1], hidden, wounded, self.enemy(), active=1)
        )
        self.assertEqual(result.action.targets, (2,))
        self.assertEqual(result.reason, "recovery_urgent")

    def test_reusable_equipment_recovers_when_spell_is_blocked(self):
        caster = replace(
            self.specs[1],
            hp=1,
            mp=0,
            silenced=2,
            equipment=self.specs[1].equipment.replaced(
                {EquipmentSlot.ARM: self.items["MIRACLE RING"]}
            ),
        )
        for policy in (AutoBattlePolicy(), self.policy_without_spells(caster)):
            snapshot = self.snapshot(caster, self.enemy(), active=1, policy=policy)
            with patch.object(BattleForecast, "execute", side_effect=AssertionError):
                result = decide_auto_battle(snapshot)
            self.assertEqual(result.reason, "recovery_urgent")
            self.assertEqual(result.action.command, BattleCommand.ITEM)
            self.assertEqual(result.action.spell_key, "HEALING1")

    def test_unavailable_recovery_falls_back_to_simulation(self):
        caster = replace(self.specs[1], hp=1, mp=0, silenced=2)
        result = decide_auto_battle(
            self.snapshot(caster, self.enemy(hp=1, max_hp=1), active=1)
        )
        self.assertEqual(result.reason, "simulation")
        self.assertTrue(result.evaluations)
        self.assertFalse(any(e.action.spell_key for e in result.evaluations))

    def test_enemy_or_healer_acting_next_changes_recovery_evaluation(self):
        wounded = replace(self.specs[0], hp=10)
        healer = self.specs[1]
        enemy = self.enemy(attack=75, hp=1000, max_hp=1000)
        early = self.snapshot(
            wounded, healer, enemy, gauges=((0, 64), (1, 63), (5, 62))
        )
        late = replace(early, gauges=((0, 64), (5, 63), (1, 62)))
        a = decide_auto_battle(early)
        b = decide_auto_battle(late)
        guard_a = next(
            e for e in a.evaluations if e.action.command is BattleCommand.DEFEND
        )
        guard_b = next(
            e for e in b.evaluations if e.action.command is BattleCommand.DEFEND
        )
        # The final death count can coincide within a short horizon; healing
        # first still reduces the discounted time spent dead and raises value.
        self.assertLess(
            dict(guard_a.components)["deaths"], dict(guard_b.components)["deaths"]
        )
        self.assertGreater(guard_a.score, guard_b.score)

    def test_focus_not_completed_within_horizon_is_excluded(self):
        actor = replace(self.specs[0], agility=1, skills=frozenset(("Focus",)))
        enemy = self.enemy(agility=99, attack=0, hit=0, hp=10000, max_hp=10000)
        result = decide_auto_battle(self.snapshot(actor, enemy))
        focus = next(
            e for e in result.evaluations if e.action.command is BattleCommand.FOCUS
        )
        self.assertEqual(focus.exclusion, "focus_beyond_horizon")
        self.assertNotEqual(result.action.command, BattleCommand.FOCUS)

    def test_item_policy_never_excludes_reusable_equipment(self):
        actor = replace(
            self.specs[0],
            equipment=self.specs[0].equipment.replaced(
                {EquipmentSlot.ARM: self.items["FLAME RING"]}
            ),
        )
        forecast = BattleForecast(
            self.snapshot(
                actor, self.enemy(), policy=AutoBattlePolicy(item_mode=ItemMode.NEVER)
            ),
            0,
        )
        self.assertFalse(
            any(a.command is BattleCommand.ITEM for a in forecast.candidates(0))
        )

    def test_all_paralyzed_allies_end_forecast_as_defeat(self):
        forecast = BattleForecast(self.snapshot(), 0)
        forecast.actors[0].paralyzed = True
        forecast.normalize()
        self.assertTrue(forecast.ended)
        self.assertTrue(forecast.defeated)
        self.assertEqual(forecast.values({5: 1})[1], 1)
        self.assertEqual(forecast.step({5: 1}), 0)

    def test_known_poison_resistance_prevents_double_counting_status(self):
        caster = self.specs[0]
        enemy = self.enemy(resistances=frozenset((ResistanceType.POISON,)))
        forecast = BattleForecast(self.snapshot(caster, enemy), 0)
        action = AutoAction(BattleCommand.SPELL, (5,), "POISON1")
        forecast.cast(forecast.actors[0], action)
        self.assertFalse(forecast.actors[5].poisoned)

    def test_all_resistant_status_targets_are_excluded_before_evaluation(self):
        spell = self.spells["SLEEP"]
        ring = replace(self.items["MIRACLE RING"], use_spell_key=spell.key)
        caster = replace(
            self.specs[0],
            spells=(spell,),
            equipment=self.specs[0].equipment.replaced({EquipmentSlot.ARM: ring}),
        )
        enemy = self.enemy(resistances=frozenset((ResistanceType.SLEEP,)))
        result = decide_auto_battle(self.snapshot(caster, enemy))
        self.assertIn((spell.key, "known_resistance"), result.excluded)
        self.assertFalse(
            any(e.action.spell_key == spell.key for e in result.evaluations)
        )

    def test_mixed_resistance_whole_group_status_keeps_manual_targets(self):
        spell = self.spells["SLEEP"]
        caster = replace(self.specs[0], spells=(spell,))
        immune = self.enemy(resistances=frozenset((ResistanceType.SLEEP,)))
        unknown = self.enemy(6, known_fields=frozenset())
        forecast = BattleForecast(self.snapshot(caster, immune, unknown), 0)
        actions = [a for a in forecast.candidates(0) if a.spell_key == spell.key]
        self.assertEqual(actions, [AutoAction(BattleCommand.SPELL, (5, 6), spell.key)])
        forecast.cast(forecast.actors[0], actions[0])
        self.assertEqual(forecast.actors[5].sleeping, 0)

    def test_single_target_status_excludes_only_resistant_combinations(self):
        spell = replace(self.spells["SLEEP"], to_all=False)
        caster = replace(self.specs[0], spells=(spell,))
        immune = self.enemy(resistances=frozenset((ResistanceType.SLEEP,)))
        vulnerable = self.enemy(6)
        snapshot = replace(self.snapshot(caster, immune, vulnerable), spells=(spell,))
        excluded = []
        actions = BattleForecast(snapshot, 0).candidates(0, excluded)
        self.assertIn((spell.key + "@" + immune.key, "known_resistance"), excluded)
        self.assertNotIn(AutoAction(BattleCommand.SPELL, (5,), spell.key), actions)
        self.assertIn(AutoAction(BattleCommand.SPELL, (6,), spell.key), actions)

    def test_resisted_damage_with_status_and_attribute_free_slow_remain_candidates(
        self,
    ):
        caster = replace(
            self.specs[0], spells=(self.spells["POISON1"], self.spells["SLOW"])
        )
        enemy = self.enemy(
            resistances=frozenset((ResistanceType.POISON, ResistanceType.SLEEP))
        )
        actions = BattleForecast(self.snapshot(caster, enemy), 0).candidates(0)
        self.assertTrue(any(a.spell_key == "POISON1" for a in actions))
        self.assertTrue(any(a.spell_key == "SLOW" for a in actions))

    def test_break_forecast_uses_lowered_defense_and_skips_no_change_targets(self):
        spell = self.spells["ARMOR BREAK"]
        caster = replace(self.specs[0], spells=(spell,))
        enemy = self.enemy(defense=20)
        forecast = BattleForecast(self.snapshot(caster, enemy), 0)

        actions = [a for a in forecast.candidates(0) if a.spell_key == spell.key]
        self.assertEqual(
            actions,
            [AutoAction(BattleCommand.SPELL, (5,), spell.key)],
        )
        forecast.cast(forecast.actors[0], actions[0])
        self.assertEqual(forecast.actors[5].protection, -1)
        self.assertEqual(forecast.actors[5].defense, 5)

        for unusable in (
            self.enemy(defense=20, protection=-1),
            self.enemy(defense=0),
        ):
            actions = BattleForecast(
                self.snapshot(caster, unusable),
                0,
            ).candidates(0)
            self.assertFalse(any(a.spell_key == spell.key for a in actions))

    def test_confuse_is_a_supported_status_spell_in_forecasts(self):
        spell = self.spells["CONFUSION"]
        caster = replace(self.specs[0], spells=(spell,))
        enemy = self.enemy(spell_defense=0)
        forecast = BattleForecast(self.snapshot(caster, enemy), 0)
        forecast.roll = Mock(return_value=0.0)

        actions = [a for a in forecast.candidates(0) if a.spell_key == spell.key]
        self.assertEqual(
            actions,
            [AutoAction(BattleCommand.SPELL, (5,), spell.key)],
        )
        forecast.cast(forecast.actors[0], actions[0])

        self.assertEqual(forecast.actors[5].confused, 2)
        self.assertEqual(forecast.actors[5].sleeping, 0)

    def test_resistance_pruning_does_not_change_enemy_spell_choices(self):
        spell = self.spells["SLEEP"]
        ally = replace(self.specs[0], resistances=frozenset((ResistanceType.SLEEP,)))
        enemy = self.enemy(front=False, spells=(spell,), max_mp=20, mp=20)
        forecast = BattleForecast(self.snapshot(ally, enemy), 0)
        self.assertEqual(forecast.spell_targets(forecast.actors[5], spell), (0,))
        forecast.enemy_turn(forecast.actors[5])
        self.assertEqual(forecast.actors[5].mp, 20 - spell.mp)
        self.assertEqual(forecast.actors[0].sleeping, 0)

    def test_mp_cost_and_zero_mp_match_specification(self):
        self.assertAlmostEqual(mp_cost(12, 30, 3, 3), 4.128)
        self.assertAlmostEqual(mp_cost(6, 30, 3, 3), 9.472)
        self.assertEqual(mp_cost(0, 0, 0, 0), 0)
        self.assertAlmostEqual(mp_cost(4, 4, 4, 0), 15.2)

    def test_value_examples_and_enemy_damage_are_capped(self):
        forecast = BattleForecast(self.snapshot(), 0)
        ally = forecast.actors[0]
        ally.hp = ally.max_hp
        forecast.actors[5].hp = 0
        values = forecast.values({5: 1.8})
        self.assertEqual(values[5], 1.8)
        self.assertEqual(values[6], 1.8)
        # Victory + all enemy removal + full health/action capability.
        self.assertAlmostEqual(sum(v * w for v, w in zip(values, VALUE_WEIGHTS)), 2260)

    def test_quantiles_cover_each_uniform_stratum_without_game_rng(self):
        before = random.getstate()
        for purpose in range(15):
            values = [quantile(k, 2, 3, 5, purpose) for k in range(CASE_COUNT)]
            self.assertEqual(len({floor(u * CASE_COUNT) for u in values}), CASE_COUNT)
            self.assertTrue(all(0 <= u < 1 for u in values))
        self.assertEqual(random.getstate(), before)

    def test_all_cases_start_from_exact_hp_and_mp_before_disclosure(self):
        first = self.enemy(
            species_key="Imp", max_hp=280, hp=41, max_mp=16, mp=3,
            hp_displayed=False, known_fields=frozenset(),
        )
        second = replace(first, number=6, key="enemy:6", hp=280, mp=16)
        snapshot = self.snapshot(self.specs[0], first, second)
        for case in range(CASE_COUNT):
            with self.subTest(case=case):
                forecast = BattleForecast(snapshot, case)
                a, b = forecast.enemy_actors
                self.assertEqual((a.max_hp, a.hp, a.spec.max_mp, a.mp), (280, 41, 16, 3))
                self.assertEqual((b.max_hp, b.hp, b.spec.max_mp, b.mp), (280, 280, 16, 16))
                self.assertEqual((forecast.start_hp[5], forecast.start_hp[6]), (41, 280))
                self.assertFalse(forecast.hp_shown)

    def test_same_species_focuses_current_hp_on_either_slot(self):
        party = tuple(
            replace(
                actor, spells=(), skills=frozenset(),
                weapons=tuple(replace(weapon, effect=None) for weapon in actor.weapons),
            )
            for actor in self.specs
        )
        for profile_known in (False, True):
            for wounded in (5, 6):
                with self.subTest(profile_known=profile_known, wounded=wounded):
                    first, second = (
                        self.enemy(
                            number, species_key="Imp", max_hp=280,
                            hp=266 if number == wounded else 280, hp_displayed=False,
                            known_fields=frozenset(("profile",)) if profile_known else frozenset(),
                            max_mp=16, mp=16, agility=20, intelligence=1, magic=10,
                            attack=36, defense=8, evasion=10, spell_defense=10,
                            spells=(self.spells["SPARK"], self.spells["SLOW"]),
                        )
                        for number in (5, 6)
                    )
                    snapshot = self.snapshot(
                        *party, first, second, gauges=((0, 64), (5, 60), (6, 56), (1, 52), (2, 48))
                    )
                    forecast = BattleForecast(snapshot, 0)
                    self.assertEqual(
                        forecast.continuation(0, {wounded: 1.0, 11 - wounded: 1.1}).targets,
                        (wounded,),
                    )
                    self.assertEqual(
                        decide_auto_battle(snapshot).action,
                        AutoAction(BattleCommand.ATTACK, (wounded,)),
                    )

    def test_focusing_wounded_target_keeps_certain_kill_of_next_enemy_available(self):
        ally = replace(
            self.specs[0], spells=(), skills=frozenset(), weapons=(AutoWeapon(180, 150),)
        )
        first = self.enemy(hp=100, species_key="Imp")
        second = replace(first, number=6, key="enemy:6", hp=40)
        snapshot = self.snapshot(ally, first, second)
        forecast = BattleForecast(snapshot, 0)
        self.assertEqual(forecast.continuation(0, {5: 1, 6: 1}).targets, (5,))
        evaluations = {
            e.action.targets: e for e in decide_auto_battle(snapshot).evaluations
            if e.action.command is BattleCommand.ATTACK
        }
        self.assertTrue(evaluations[(5,)].stops_next_enemy_turn)
        self.assertFalse(evaluations[(5,)].exclusion)

    def test_snapshot_is_detached_from_member_status_and_proficiencies(self):
        member = load_mock_party(
            self.items, load_mock_skills(), character_keys=("Cerion",)
        )[0]
        spec = AutoCombatant.from_member(member, 0, front=True, spells=())
        member.hp = 1
        member.speed_modifier = -1
        first = next(iter(member.proficiencies.values()))
        level = spec.proficiencies[0].level
        first.level += 1
        self.assertNotEqual(spec.hp, 1)
        self.assertEqual(spec.speed, 0)
        self.assertEqual(spec.proficiencies[0].level, level)
        with self.assertRaises(FrozenInstanceError):
            spec.hp = 2

    @staticmethod
    def policy_without_spells(*actors):
        return AutoBattlePolicy(AutoBattleConfig(disabled_spells=frozenset(
            (actor.key.removeprefix("pc:"), kind)
            for actor in actors for kind in AUTO_BATTLE_SPELL_KINDS
        )))

    def test_spell_school_permissions_apply_per_actor_without_disabling_equipment(self):
        first = replace(
            self.specs[0],
            hp=20,
            spells=(self.spells["HEALING1"],),
            equipment=self.specs[0].equipment.replaced(
                {EquipmentSlot.ARM: self.items["FLAME RING"]}
            ),
        )
        second = replace(self.specs[1], spells=first.spells)
        school = first.spells[0].type.value
        config = AutoBattleConfig().toggle_spell(first.key.removeprefix("pc:"), school)
        forecast = BattleForecast(
            self.snapshot(first, second, self.enemy(), policy=AutoBattlePolicy(config)),
            0,
        )
        for continuation in (False, True):
            self.assertFalse(any(
                a.command is BattleCommand.SPELL
                for a in forecast.candidates(first.number, continuation=continuation)
            ))
            self.assertTrue(any(
                a.command is BattleCommand.SPELL
                for a in forecast.candidates(second.number, continuation=continuation)
            ))
        self.assertTrue(any(
            a.command is BattleCommand.ITEM and a.equipment_slot == EquipmentSlot.ARM
            for a in forecast.candidates(first.number)
        ))

    def test_consumable_permissions_stock_and_mana_recovery_in_forecast(self):
        actor = replace(self.specs[1], hp=1, mp=0, poisoned=True, silenced=2)
        snapshot = replace(
            self.snapshot(actor, self.enemy(), active=1),
            consumables=tuple((self.items[key], 1) for key in AUTO_BATTLE_ITEM_KEYS),
        )
        self.assertFalse(any(a.item_key for a in BattleForecast(snapshot, 0).candidates(1)))
        for key in AUTO_BATTLE_ITEM_KEYS:
            with self.subTest(key=key):
                permitted = replace(snapshot, policy=AutoBattlePolicy(
                    AutoBattleConfig().toggle_item(key)
                ))
                forecast = BattleForecast(permitted, 0)
                action, = (a for a in forecast.candidates(1) if a.item_key)
                self.assertEqual(action.item_key, key)
                forecast.execute(1, action)
                self.assertEqual(forecast.item_quantities[key], 0)
                self.assertFalse(any(a.item_key for a in forecast.candidates(1)))
                self.assertEqual(
                    {item.key: count for item, count in permitted.consumables}[key], 1
                )
                if key == "MANA DROP":
                    self.assertGreater(forecast.actors[1].mp, 0)
                elif key == "REMEDY":
                    self.assertFalse(forecast.actors[1].poisoned)
                else:
                    self.assertGreater(forecast.actors[1].hp, 1)
        potion = replace(snapshot, policy=AutoBattlePolicy(
            AutoBattleConfig().toggle_item("POTION")
        ))
        decision = decide_auto_battle(potion)
        self.assertEqual((decision.reason, decision.action.item_key), ("recovery_urgent", "POTION"))

    def test_pray_forecasts_self_recovery_even_while_silenced(self):
        spec = replace(
            self.specs[1], skills=frozenset(("Pray",)), max_mp=30, mp=29,
            magic=23, internal_level=1, silenced=2, hidden=True,
        )
        action = AutoAction(BattleCommand.PRAY, (spec.number,))
        for success_roll, expected_mp in ((0.35875, 30), (0.35885, 29)):
            with self.subTest(success_roll=success_roll):
                forecast = BattleForecast(self.snapshot(spec, self.enemy(), active=1), 0)
                self.assertIn(action, forecast.candidates(1))
                with patch.object(forecast, "roll", side_effect=(success_roll, 0.5)):
                    cost, gauge = forecast.execute(1, action)
                actor = forecast.actors[1]
                self.assertEqual((cost, gauge), (0, actor.agility))
                self.assertEqual(actor.mp, expected_mp)
                self.assertFalse(actor.hidden)
                self.assertEqual(action in forecast.candidates(1), expected_mp < 30)

    def test_panacea_is_not_selected_for_a_full_hp_target(self):
        actor = replace(self.specs[1], hp=self.specs[1].max_hp, poisoned=True)
        snapshot = replace(
            self.snapshot(actor, self.enemy(), active=1, policy=AutoBattlePolicy(
                AutoBattleConfig().toggle_item("PANACEA")
            )),
            consumables=((self.items["PANACEA"], 1),),
        )

        self.assertFalse(any(
            action.item_key == "PANACEA"
            for action in BattleForecast(snapshot, 0).candidates(1)
        ))

    def test_consumables_breaking_gear_and_unsupported_effects_are_excluded(self):
        healer = replace(
            self.specs[1],
            hp=20,
            equipment=self.specs[1].equipment.replaced(
                {EquipmentSlot.ARM: self.items["TELEPORT RING"]}
            ),
        )
        excluded = []
        actions = BattleForecast(
            self.snapshot(healer, self.enemy(), active=1), 0
        ).candidates(1, excluded)
        self.assertFalse(any(a.command is BattleCommand.ITEM for a in actions))
        self.assertIn(("TELEPORT RING", "breaks_on_use"), excluded)
        self.assertIn(("CURE", "no_targets"), excluded)
        self.assertFalse(any(a.spell_key == "POTION" for a in actions))
        self.assertFalse(any(a.command is BattleCommand.ESCAPE for a in actions))

    def test_silence_mp_and_range_leave_legal_guard_fallback(self):
        caster = replace(self.specs[0], silenced=2, mp=0, front=False)
        actions = BattleForecast(self.snapshot(caster, self.enemy()), 0).candidates(0)
        self.assertNotIn(BattleCommand.SPELL, [a.command for a in actions])
        self.assertNotIn(BattleCommand.ATTACK, [a.command for a in actions])
        self.assertIn(AutoAction(BattleCommand.DEFEND), actions)

    def test_auto_never_changes_formation_even_when_manual_command_is_enabled(self):
        for front in (True, False):
            with self.subTest(front=front):
                actor = replace(
                    self.specs[0], front=front, spells=(), skills=frozenset()
                )
                snapshot = self.snapshot(
                    actor,
                    self.specs[1],
                    self.enemy(attack=0, hit=0),
                    policy=AutoBattlePolicy(item_mode=ItemMode.NEVER),
                )
                forecast = BattleForecast(snapshot, 0)
                manual = next(
                    option
                    for option in forecast.command_options(forecast.actors[0])
                    if option.command is BattleCommand.FORMATION
                )
                self.assertTrue(manual.enabled)
                result = decide_auto_battle(snapshot)
                self.assertIn(("formation", "formation_policy"), result.excluded)
                self.assertNotEqual(result.action.command, BattleCommand.FORMATION)
                self.assertFalse(
                    any(
                        e.action.command is BattleCommand.FORMATION
                        for e in result.evaluations
                    )
                )
                if not front:
                    self.assertEqual(result.action.command, BattleCommand.DEFEND)
                forecast.execute(0, result.action)
                self.assertEqual(forecast.actors[0].front, front)
                self.assertNotEqual(
                    forecast.continuation(0, {5: 1}).command, BattleCommand.FORMATION
                )

    def test_hidden_ambush_can_reach_rear_enemies(self):
        actor = replace(self.specs[0], hidden=True, front=False)
        forecast = BattleForecast(self.snapshot(actor, self.enemy(front=False)), 0)
        self.assertIn(AutoAction(BattleCommand.AMBUSH, (5,)), forecast.candidates(0))

    def test_iai_forecast_uses_all_enemies_right_hand_and_thirty_two_delay(self):
        member = load_mock_party(
            self.items,
            load_mock_skills(),
            character_keys=("Elika",),
            internal_level=20,
        )[0]
        spec = AutoCombatant.from_member(member, 0, front=True, spells=())
        enemies = (
            self.enemy(number=5, front=False, max_hp=1000, hp=1000),
            self.enemy(number=6, front=False, max_hp=1000, hp=1000),
        )
        forecast = BattleForecast(self.snapshot(spec, *enemies), 0)
        action = AutoAction(BattleCommand.IAI, (5, 6))
        self.assertIn(action, forecast.candidates(0))
        self.assertEqual(forecast.delay(forecast.actors[0], action), -32.0)
        expected_attack = member_physical_attack(
            member.battle_stats.attack_right * 60 // 100,
            member.adjusted_abilities.strength,
            member.weapon_level(member.equipment.weapon_at(EquipmentSlot.RIGHT)),
            member.internal_level,
        )
        self.assertEqual(spec.weapons[0].iai_attack, expected_attack)
        with patch(
            "auto_battle_simulation.resolve_physical_attack",
            wraps=resolve_physical_attack,
        ) as resolver:
            forecast.execute(0, action)
        self.assertEqual(
            [call.kwargs["attack"] for call in resolver.call_args_list],
            [expected_attack, expected_attack],
        )
        self.assertLess(forecast.actors[5].hp, 1000)
        self.assertLess(forecast.actors[6].hp, 1000)

    def test_back_row_iai_candidates_require_long_range_katana(self):
        member = load_mock_party(
            self.items,
            load_mock_skills(),
            character_keys=("Elika",),
            internal_level=20,
        )[0]
        katana = member.equipment.weapon_at(EquipmentSlot.RIGHT)
        enemies = (self.enemy(number=5, front=False), self.enemy(number=6))
        action = AutoAction(BattleCommand.IAI, (5, 6))
        for reach in (1, 2, 3):
            with self.subTest(reach=reach):
                member.equipment = member.equipment.replaced(
                    {EquipmentSlot.RIGHT: replace(katana, reach=reach)}
                )
                spec = AutoCombatant.from_member(member, 0, front=False, spells=())
                forecast = BattleForecast(self.snapshot(spec, *enemies), 0)
                self.assertEqual(action in forecast.candidates(0), reach >= 2)

                forecast.actors[0].front = True
                self.assertIn(action, forecast.candidates(0))

    def test_auto_selects_iai_when_it_can_defeat_three_enemies(self):
        member = load_mock_party(
            self.items,
            load_mock_skills(),
            character_keys=("Elika",),
            internal_level=20,
        )[0]
        spec = AutoCombatant.from_member(member, 0, front=True, spells=())
        enemies = tuple(
            self.enemy(number=5 + index, max_hp=60, hp=60, attack=5)
            for index in range(3)
        )
        decision = decide_auto_battle(self.snapshot(spec, *enemies))
        self.assertEqual(
            decision.action,
            AutoAction(BattleCommand.IAI, (5, 6, 7)),
        )

    def test_only_three_visible_left_commands_are_available(self):
        actor = replace(
            self.specs[0], skills=frozenset(("Aim", "Focus", "Hide", "Identify"))
        )
        actions = BattleForecast(self.snapshot(actor, self.enemy()), 0).candidates(0)
        self.assertIn(BattleCommand.AIM, [a.command for a in actions])
        for command in (
            BattleCommand.FOCUS,
            BattleCommand.HIDE,
            BattleCommand.IDENTIFY,
        ):
            self.assertNotIn(command, [a.command for a in actions])

    def test_equipped_healing_uses_same_school_ability_and_delay_as_manual(self):
        caster = replace(
            self.specs[1],
            hp=20,
            equipment=self.specs[1].equipment.replaced(
                {EquipmentSlot.ARM: self.items["MIRACLE RING"]}
            ),
        )
        forecast = BattleForecast(self.snapshot(caster, self.enemy(), active=1), 0)
        actor = forecast.actors[1]
        action = next(
            a for a in forecast.candidates(1) if a.command is BattleCommand.ITEM
        )
        spell = self.spells[action.spell_key]
        expected = resolve_healing(
            intensity=spell.intensity,
            ability=member_spell_ability(
                magic=caster.magic, internal_level=caster.internal_level
            ),
            current_hp=20,
            max_hp=caster.max_hp,
            random_factor=0,
        )
        self.assertEqual(forecast.heal_result(actor, actor, spell, 0), expected)
        self.assertEqual(forecast.cost(actor, action), 0)
        self.assertLess(forecast.delay(actor, action), 0)

    def test_full_health_has_no_heal_and_healing_is_not_reserved(self):
        healer = self.specs[1]
        forecast = BattleForecast(self.snapshot(healer, self.enemy(), active=1), 0)
        self.assertFalse(any(a.spell_key == "HEALING1" for a in forecast.candidates(1)))
        forecast.actors[1].hp = 1
        action = forecast.continuation(1, {5: 1})
        self.assertEqual(action.spell_key, "HEALING1")
        forecast.cast(forecast.actors[1], action)
        self.assertGreater(forecast.actors[1].hp, 1)
        forecast.actors[1].hp = forecast.actors[1].max_hp
        self.assertEqual(forecast.continuation(1, {5: 1}).command, BattleCommand.ATTACK)

    def test_same_species_information_is_counted_once_but_hp_per_individual(self):
        enemy = self.enemy(
            species_key="spider", known_fields=frozenset(), hp_displayed=False
        )
        other = replace(enemy, number=6, key="enemy:6")
        forecast = BattleForecast(self.snapshot(self.specs[0], enemy, other), 0)
        forecast.identify(forecast.actors[5])
        first = forecast.info
        forecast.identify(forecast.actors[6])
        self.assertEqual(forecast.info, first + 2)
        forecast.identify(forecast.actors[6])
        self.assertEqual(forecast.info, first + 2)

    def test_dual_wield_resolves_together_but_does_not_apply_after_right_kill(self):
        actor = replace(
            self.specs[0], weapons=(AutoWeapon(100, 100), AutoWeapon(100, 100))
        )
        forecast = BattleForecast(self.snapshot(actor, self.enemy(max_hp=1, hp=1)), 0)
        target = forecast.actors[5]
        with patch.object(
            target.__class__, "damage", autospec=True, wraps=target.damage
        ) as damage:
            # Explicit wrapper is needed for autospec's class-method dispatch.
            damage.side_effect = lambda a, amount, **kw: setattr(
                a, "hp", max(0, a.hp - amount)
            )
            forecast.physical(
                forecast.actors[0], AutoAction(BattleCommand.ATTACK, (5,))
            )
        self.assertEqual(damage.call_count, 1)
        self.assertEqual(target.hp, 0)

    def test_physical_prediction_uses_live_resolver(self):
        forecast = BattleForecast(self.snapshot(), 7)
        actor, target = forecast.actors[0], forecast.actors[5]
        weapon = actor.spec.weapons[0]
        result = forecast.physical_results(
            actor, target, AutoAction(BattleCommand.ATTACK, (5,))
        )[0]
        expected = resolve_physical_attack(
            attack=weapon.attack,
            hit=weapon.hit,
            target_defense=target.defense,
            target_evasion=target.evasion,
            hit_roll=int(forecast.roll(actor, 5, 2) * 100),
            critical_roll=int(forecast.roll(actor, 5, 3) * 100),
            critical_rate_scale=weapon.critical_scale,
            attacker_has_power_hit=actor.has_skill("Power Hit"),
            weapon_has_power_hit=weapon.power_hit,
        )
        self.assertEqual(result, expected)

    def test_single_target_physical_attack_pairs_rolls_but_iai_keeps_individual_rolls(self):
        ally = replace(
            self.specs[0], weapons=(AutoWeapon(129, 104, iai_attack=80), AutoWeapon(40, 95))
        )
        first = self.enemy(defense=8, evasion=10)
        second = replace(first, number=6, key="enemy:6")
        forecast = BattleForecast(self.snapshot(ally, first, second), 0)
        attacker = forecast.actors[0]
        a, b = forecast.enemy_actors
        iai = AutoAction(BattleCommand.IAI, (5, 6))
        iai_results = []
        for case in range(CASE_COUNT):
            a_hit = forecast.physical_results(attacker, a, AutoAction(BattleCommand.ATTACK, (5,)), case)
            b_hit = forecast.physical_results(attacker, b, AutoAction(BattleCommand.ATTACK, (6,)), case)
            self.assertEqual(a_hit, b_hit)
            iai_results.append((
                forecast.physical_results(attacker, a, iai, case),
                forecast.physical_results(attacker, b, iai, case),
            ))
        self.assertTrue(any(a_hit != b_hit for a_hit, b_hit in iai_results))

    def test_single_target_damage_spell_pairs_damage_rolls(self):
        spell = self.spells["FIRE1"]
        self.assertTrue(spell.to_enemy and not spell.to_all)
        caster = self.specs[1]
        first = self.enemy(hp=200, max_hp=200)
        second = replace(first, number=6, key="enemy:6")
        snapshot = self.snapshot(caster, first, second, active=1)
        for case in range(CASE_COUNT):
            damage = []
            for n in (5, 6):
                forecast = BattleForecast(snapshot, case)
                forecast.cast(forecast.actors[1], AutoAction(BattleCommand.SPELL, (n,), spell.key))
                damage.append(200 - forecast.actors[n].hp)
            self.assertEqual(damage[0], damage[1])
            self.assertGreater(damage[0], 0)

    def test_snapshot_and_forecast_preserve_independent_debuff_durations(self):
        member = replace(self.party[0])
        member.apply_slow(5)
        member.apply_defense_down(6)
        spec = AutoCombatant.from_member(member, 0, front=True, spells=())
        self.assertEqual((spec.slow_turns, spec.defense_down_turns), (5, 6))
        forecast = BattleForecast(self.snapshot(spec, self.enemy()), 0)
        actor = forecast.actors[0]
        for turn in range(1, 7):
            forecast.execute(0, AutoAction(BattleCommand.DEFEND))
            self.assertEqual(actor.speed, -1 if turn < 5 else 0)
            self.assertEqual(actor.protection, -1 if turn < 6 else 0)
        self.assertEqual((member.slow_turns, member.defense_down_turns), (5, 6))

    def test_forecast_debuffs_expire_on_skipped_confused_and_normal_enemy_turns(self):
        for changes in ({}, {"stunned": True}, {"sleeping": 2}, {"confused": 2}):
            enemy = self.enemy(speed=-1, protection=-1, slow_turns=1,
                               defense_down_turns=1, **changes)
            forecast = BattleForecast(self.snapshot(self.specs[0], enemy,
                active=5, gauges=((5, 64), (0, 54))), 0)
            forecast.step({5: 1.0})
            actor = forecast.actors[5]
            self.assertEqual((actor.speed, actor.protection), (0, 0))
            self.assertEqual((actor.slow_turns, actor.defense_down_turns), (0, 0))

    def test_forecast_draws_debuff_duration_like_silence_and_retains_buffs(self):
        for resistances, minimum in (((), 4), ((ResistanceType.DEATH,), 3)):
            enemy = self.enemy(defense=20, spells=(self.spells["FREEZE1"],),
                               resistances=frozenset(resistances))
            for roll, duration in ((0.0, minimum), (0.999, minimum + 1)):
                for spell_key, timer in (
                    ("SLOW", "slow_turns"), ("ARMOR BREAK", "defense_down_turns"),
                    ("SILENCE", "silenced"),
                ):
                    with self.subTest(resistances=resistances, roll=roll, spell=spell_key):
                        forecast = BattleForecast(self.snapshot(self.specs[0], enemy), 0)
                        actor, target = forecast.actors[0], forecast.actors[5]
                        with (patch.object(forecast, "roll", return_value=roll),
                              patch.object(forecast, "status_success", return_value=True)):
                            forecast.cast(actor, AutoAction(BattleCommand.SPELL, (5,), spell_key))
                        self.assertEqual(getattr(target, timer), duration)
        forecast = BattleForecast(self.snapshot(replace(self.specs[0], speed=2, protection=2), self.enemy()), 0)
        actor = forecast.actors[0]
        for _ in range(7):
            forecast.execute(0, AutoAction(BattleCommand.DEFEND))
        self.assertEqual((actor.speed, actor.protection), (2, 2))

    def test_slow_delays_current_turn_and_future_reinsertion(self):
        forecast = BattleForecast(self.snapshot(
            self.specs[0], self.enemy(), self.enemy(number=6),
            gauges=((0, 64), (5, 60), (6, 56)),
        ), 0)
        enemy = forecast.actors[5]
        with patch.object(forecast, "status_success", return_value=True):
            forecast.cast(forecast.actors[0], AutoAction(BattleCommand.SPELL, (5,), spell_key="SLOW"))
        self.assertEqual(forecast.order.actors, (0, 6, 5))
        self.assertEqual(tuple(e.gauge for e in forecast.order.entries), (64, 56, 52))
        self.assertEqual(enemy.agility, 7)
        forecast.apply_slow(enemy)
        self.assertEqual(forecast.order.entries[-1].gauge, 52)
        forecast.execute(0, AutoAction(BattleCommand.DEFEND))
        self.assertEqual(forecast.order.entries[0].actor, 6)
        forecast.enemy_turn(forecast.actors[6])
        self.assertEqual(forecast.order.entries[0].actor, 5)
        forecast.enemy_turn(enemy)
        inserted = next(e for e in forecast.order.entries if e.actor == 5)
        self.assertEqual(inserted.agility, enemy.agility)

    def test_slow_cancels_haste_and_delays_the_gauge_on_each_success(self):
        forecast = BattleForecast(self.snapshot(self.specs[0], self.enemy(speed=2)), 0)
        target = forecast.actors[5]
        for stage, gauge in ((0, 46), (-1, 38), (-1, 38)):
            forecast.apply_slow(target)
            self.assertEqual(target.speed, stage)
            self.assertEqual(forecast.order.entries[1].gauge, gauge)

    def test_enemy_slow_forecast_delays_a_waiting_ally_immediately(self):
        enemy = self.enemy(spells=(self.spells["SLOW"],), magic=7, mp=12, max_mp=12)
        forecast = BattleForecast(self.snapshot(
            self.specs[0], self.specs[1], enemy, active=5,
            gauges=((5, 64), (0, 60), (1, 56)),
        ), 0)
        with (
            patch("auto_battle_simulation.monster_action_candidates", return_value=(MonsterSpellAction("SLOW"),)),
            patch.object(forecast, "status_success", return_value=True),
            patch.object(forecast, "roll", return_value=0),
        ):
            forecast.enemy_turn(forecast.actors[5])
        self.assertEqual(forecast.actors[0].speed, -1)
        self.assertEqual(forecast.actors[0].agility, max(1, self.specs[0].agility - 8))
        self.assertEqual(forecast.order.actors, (1, 0, 5))
        gauges = {entry.actor: entry.gauge for entry in forecast.order.entries}
        self.assertEqual(gauges[1] - gauges[0], 4)

    def test_haste_forecast_adds_eight_per_stage_without_changing_waiting_gauges(self):
        forecast = BattleForecast(self.snapshot(self.specs[0], self.specs[1], self.enemy()), 0)
        target = forecast.actors[1]
        order = forecast.order
        action = AutoAction(BattleCommand.SPELL, (1,), spell_key="HASTE")
        for stage in (1, 2):
            forecast.cast(forecast.actors[0], action)
            self.assertEqual(target.agility, target.spec.agility + stage * 8)
            self.assertIs(forecast.order, order)

    def test_stun_sleep_consumption_and_poison_do_not_wake(self):
        forecast = BattleForecast(self.snapshot(), 0)
        enemy = forecast.actors[5]
        enemy.stunned, enemy.sleeping, enemy.poisoned = True, 2, True
        self.assertTrue(forecast.prepare_turn(enemy))
        self.assertFalse(enemy.stunned)
        self.assertEqual(enemy.sleeping, 2)
        self.assertTrue(forecast.prepare_turn(enemy))
        self.assertEqual(enemy.sleeping, 1)
        enemy.damage(1)
        self.assertEqual(enemy.sleeping, 0)

    def test_inner_steel_recovers_before_action_and_uses_current_hp_in_forecast(self):
        spec = replace(
            self.specs[0], hp=26, max_hp=100, poisoned=True,
            sleeping=2, silenced=2, skills=self.specs[0].skills | {"Inner Steel"},
        )
        forecast = BattleForecast(self.snapshot(spec, self.enemy()), 0)
        member, enemy = forecast.actors[0], forecast.actors[5]
        action = AutoAction(BattleCommand.ATTACK, (5,))

        with patch("auto_battle_simulation.resolve_physical_attack") as resolve:
            forecast.physical_results(member, enemy, action)
            base_attack = resolve.call_args.kwargs["attack"]
            self.assertEqual(base_attack, spec.weapons[-1].attack)
            self.assertFalse(forecast.prepare_turn(member))
            self.assertTrue(member.poisoned)
            self.assertEqual(member.hp, 19)
            self.assertEqual((member.sleeping, member.silenced), (0, 0))
            forecast.physical_results(member, enemy, action)
            self.assertEqual(resolve.call_args.kwargs["attack"], base_attack * 3 // 2)
            member.hp = 26
            forecast.physical_results(member, enemy, action)
            self.assertEqual(resolve.call_args.kwargs["attack"], base_attack)

    def test_surprise_forecast_defers_rows_until_first_actionable_turn(self):
        for status, value in (
            ("sleeping", 2), ("sleeping", 1), ("paralyzed", True),
            ("confused", 2), ("stunned", True),
        ):
            with self.subTest(status=status, value=value):
                snapshot = replace(
                    self.snapshot(
                        replace(self.specs[0], front=False),
                        replace(self.specs[1], front=True, **{status: value}),
                        self.enemy(),
                    ),
                    surprise_pending=frozenset((0, 1)),
                    surprise_original_rows=((0, True), (1, False)),
                )
                forecast = BattleForecast(snapshot, 0)
                front, rear = forecast.actors[0], forecast.actors[1]
                self.assertTrue(forecast.prepare_turn(rear))
                self.assertTrue(forecast.prepare_turn(front))
                self.assertTrue(front.front)
                self.assertTrue(rear.front)
                self.assertEqual(forecast.original_rows, {1: False})

                setattr(rear, status, 0)
                forecast.normalize()
                self.assertTrue(rear.front)
                self.assertFalse(forecast.prepare_turn(rear))
                self.assertFalse(rear.front)
                self.assertEqual(forecast.original_rows, {})

    def test_surprise_forecast_keeps_deferred_rows_from_snapshot(self):
        snapshot = replace(
            self.snapshot(self.specs[0], self.specs[1], self.enemy()),
            surprise_original_rows=((1, False),),
            surprise_deferred=frozenset((1,)),
        )
        forecast = BattleForecast(snapshot, 0)
        forecast.normalize()
        self.assertTrue(forecast.actors[1].front)
        self.assertFalse(forecast.prepare_turn(forecast.actors[1]))
        self.assertFalse(forecast.actors[1].front)

    def test_enemy_turn_healing_matches_poison_net_change_and_caps_hp(self):
        for healing, poisoned, weak, is_boss, hp, expected in (
            (1, False, False, False, 10, 18),
            (1, False, False, False, 119, 120),
            (1, True, False, False, 10, 10),
            (1, True, True, False, 40, 33),
            (-1, True, False, False, 10, 0),
            (1, False, False, True, 10, 14),
            (1, True, False, True, 10, 6),
            (-1, False, False, True, 10, 6),
        ):
            with self.subTest(healing=healing, poisoned=poisoned, weak=weak, is_boss=is_boss, hp=hp):
                spec = self.enemy(
                    hp=hp, healing=healing, poisoned=poisoned, sleeping=2, is_boss=is_boss,
                    weaknesses=frozenset((ResistanceType.POISON,)) if weak else frozenset(),
                )
                forecast = BattleForecast(self.snapshot(self.specs[0], spec), 0)
                enemy = forecast.actors[5]
                forecast.prepare_turn(enemy)
                self.assertEqual(enemy.hp, expected)
                if expected:
                    self.assertEqual(enemy.sleeping, 1)

    def test_confused_forecast_actors_attack_their_own_side(self):
        for actor_number, target_number in ((0, 1), (5, 6)):
            with self.subTest(actor_number=actor_number):
                specs = (self.specs[0], self.specs[1], self.enemy(), self.enemy(6))
                gauges = ((actor_number, 64),) + tuple(
                    (spec.number, 40) for spec in specs if spec.number != actor_number
                )
                forecast = BattleForecast(
                    self.snapshot(*specs, active=actor_number, gauges=gauges), 0,
                )
                forecast.roll = Mock(return_value=0.0)
                actor = forecast.actors[actor_number]
                actor.confused = 2
                target = forecast.actors[target_number]
                health = target.hp

                forecast.step({5: 1, 6: 1})

                self.assertEqual(actor.confused, 1)
                self.assertLess(target.hp, health)

    def test_forecast_uses_normal_actions_on_the_confusion_recovery_turn(self):
        for actor_number in (0, 5):
            with self.subTest(actor_number=actor_number):
                specs = (self.specs[0], self.specs[1], self.enemy(), self.enemy(6))
                gauges = ((actor_number, 64),) + tuple(
                    (spec.number, 40) for spec in specs if spec.number != actor_number
                )
                forecast = BattleForecast(
                    self.snapshot(*specs, active=actor_number, gauges=gauges), 0,
                )
                actor = forecast.actors[actor_number]
                actor.confused = 1
                forecast.roll = Mock(return_value=0.0)
                forecast.continuation = Mock(return_value=AutoAction(BattleCommand.DEFEND))
                with patch.object(forecast, "enemy_turn", wraps=forecast.enemy_turn) as enemy_turn:
                    forecast.step({5: 1, 6: 1})
                self.assertEqual(actor.confused, 0)
                if actor.spec.enemy:
                    enemy_turn.assert_called_once_with(actor)
                    self.assertEqual(forecast.actors[6].hp, specs[3].hp)
                else:
                    self.assertTrue(actor.defending)
                    self.assertEqual(forecast.actors[1].hp, specs[1].hp)

    def test_monster_power_hit_forecasts_match_physical_attack_rules(self):
        for mode in ("attack", "charge", "confused"):
            for power_hit, status, roll, normal_damage, charge_damage in (
                (False, None, 0, 11, 22),
                (True, None, 9, 33, 49),
                (True, None, 10, 11, 22),
                (False, "sleeping", 20, 15, 29),
                (True, "sleeping", 39, 44, 65),
                (True, "sleeping", 40, 15, 29),
                (False, "confused", 19, 44, 65),
                (False, "confused", 20, 15, 29),
            ):
                with self.subTest(
                    mode=mode, power_hit=power_hit, status=status, roll=roll,
                ):
                    specials = (MonsterSpecialAction.POWER_HIT,) if power_hit else ()
                    if mode == "charge":
                        specials += (MonsterSpecialAction.CHARGE,)
                    enemy = self.enemy(front=mode != "charge", special_actions=specials)
                    statuses = dict(
                        sleeping=2 if status == "sleeping" else 0,
                        confused=2 if status == "confused" else 0,
                    )
                    evasion = 100 if status else 0
                    member = replace(
                        self.specs[0], hp=1000, max_hp=1000, defense=10,
                        evasion=evasion, agility=20, **statuses,
                    )
                    other = self.enemy(
                        6, hp=1000, max_hp=1000, defense=10, evasion=evasion, **statuses,
                    )
                    forecast = BattleForecast(self.snapshot(member, enemy, other), 0)
                    forecast.roll = Mock(
                        side_effect=lambda _actor, _target, purpose: (
                            roll / 100 if purpose == 3 else 0.0
                        ),
                    )
                    target = forecast.actors[6 if mode == "confused" else 0]
                    if mode == "confused":
                        forecast.confused_physical(forecast.actors[5], target)
                    else:
                        forecast.enemy_turn(forecast.actors[5])
                    expected_damage = charge_damage if mode == "charge" else normal_damage
                    self.assertEqual(target.hp, 1000 - expected_damage)

    def test_known_attacker_tribe_uses_equipment_resistance_in_physical_forecasts(self):
        weapon = self.items["ONIGOROSHI"]
        member = replace(
            self.specs[0], hp=1000, max_hp=1000, defense=10, evasion=0, agility=20,
            floating=False,
            equipment=self.specs[0].equipment.replaced({EquipmentSlot.RIGHT: weapon}),
        )
        for action, unresisted_damage, resisted_damage in (
            ("attack", 156, 49), ("charge", 234, 76), ("earthquake", 51, 27),
        ):
            for tribe in (None, MonsterTribe.GIANT, MonsterTribe.DRAGON):
                with self.subTest(action=action, tribe=tribe):
                    enemy = self.enemy(
                        tribe=tribe, attack=96, hit=100, front=action != "earthquake",
                        special_actions=(MonsterSpecialAction.POWER_HIT, MonsterSpecialAction.EARTHQUAKE),
                    )
                    forecast = BattleForecast(self.snapshot(member, enemy), 0)
                    forecast.roll = Mock(return_value=0.0)
                    attacker, target = forecast.actors[5], forecast.actors[0]
                    if action == "earthquake":
                        forecast.enemy_turn(attacker)
                        self.assertEqual(target.stunned, tribe is not MonsterTribe.GIANT)
                    else:
                        forecast.enemy_physical(attacker, target, charged=action == "charge")
                    expected = resisted_damage if tribe is MonsterTribe.GIANT else unresisted_damage
                    self.assertEqual(1000 - target.hp, expected)

    def test_guard_cover_and_hide_change_the_actual_damage_recipient(self):
        coverer = replace(self.specs[1], defending=True, cover=0)
        forecast = BattleForecast(
            self.snapshot(self.specs[0], coverer, self.enemy()), 0
        )
        self.assertIs(forecast.covering(0), forecast.actors[1])
        forecast.actors[1].sleeping = 1
        self.assertIs(forecast.covering(0), forecast.actors[0])
        forecast.actors[1].sleeping = 0
        for ally in forecast.allies():
            ally.hidden = True
        forecast.normalize()
        self.assertTrue(all(not a.hidden for a in forecast.allies()))

    def test_focus_is_interrupted_and_forced_attack_consumes_focus(self):
        fighter = replace(self.specs[0], focus=5)
        forecast = BattleForecast(self.snapshot(fighter, self.enemy()), 0)
        forecast.step({5: 1})
        self.assertIsNone(forecast.actors[0].focus)
        self.assertTrue(forecast.focus_completed)
        forecast = BattleForecast(self.snapshot(fighter, self.enemy()), 0)
        forecast.apply_extra(
            forecast.actors[5], forecast.actors[0], AdditionalEffect.STUN
        )
        self.assertIsNone(forecast.actors[0].focus)

    def test_enemy_damage_spell_forecast_uses_same_rule_as_live_battle(self):
        from battle_magic import resolve_spell_damage

        for key in ("FIRE1", "FREEZE1"):
            with self.subTest(spell=key):
                spell = self.spells[key]
                enemy = self.enemy(front=False, spells=(spell,), magic=10,
                                   max_mp=10, mp=10)
                forecast = BattleForecast(self.snapshot(self.specs[0], enemy), 0)
                forecast.roll = Mock(return_value=0.0)
                target = forecast.actors[0]
                hp = target.hp
                expected = resolve_spell_damage(
                    intensity=spell.intensity, spell_modifier=10,
                    target_spell_defense=target.spec.spell_defense,
                    attribute=spell.attribute,
                    target_weaknesses=target.spec.weaknesses,
                    target_resistances=target.spec.resistances,
                    random_factor=0.0,
                )
                forecast.enemy_turn(forecast.actors[5])
                self.assertEqual(forecast.actors[5].mp, 10 - spell.mp)
                self.assertEqual(target.hp, max(0, hp - expected.damage))
                self.assertLess(target.hp, hp)

    def test_enemy_poison_spell_forecast_applies_poison_only_to_unresisted_survivors(self):
        spell = self.spells["POISON2"]
        unresisted = replace(self.specs[0], resistances=frozenset())
        resistant = replace(self.specs[1], resistances=frozenset({ResistanceType.POISON}))
        dying = replace(self.specs[2], hp=1, resistances=frozenset())
        enemy = self.enemy(front=False, spells=(spell,), magic=10, max_mp=10, mp=10)
        forecast = BattleForecast(self.snapshot(unresisted, resistant, dying, enemy), 0)
        forecast.roll = Mock(return_value=0.0)

        forecast.enemy_turn(forecast.actors[5])

        for spec, poisoned in ((unresisted, True), (resistant, False), (dying, False)):
            target = forecast.actors[spec.number]
            self.assertLess(target.hp, spec.hp)
            self.assertEqual(target.poisoned, poisoned)
        self.assertEqual(forecast.actors[dying.number].hp, 0)

    def test_int_one_silenced_or_mp_empty_monster_does_not_choose_spell(self):
        spell = self.spells["FIRE1"]
        for intelligence in (0, 1):
            for condition in ("silenced", "mp"):
                with self.subTest(intelligence=intelligence, condition=condition):
                    enemy = self.enemy(front=False, spells=(spell,), intelligence=intelligence,
                                       magic=10, max_mp=10,
                                       mp=0 if condition == "mp" else 10,
                                       silenced=4 if condition == "silenced" else 0)
                    forecast = BattleForecast(self.snapshot(self.specs[0], enemy), 0)
                    forecast.roll = Mock(return_value=0.0)
                    actor = forecast.actors[5]
                    hp = forecast.actors[0].hp
                    forecast.enemy_turn(actor)
                    self.assertEqual(forecast.actors[0].hp, hp)
                    self.assertEqual(actor.mp, enemy.mp)

    def test_rear_int_two_uses_spell_even_when_wait_would_have_been_selected(self):
        spell = self.spells["FREEZE2"]
        for intelligence, silenced, mp, uses_spell in (
            (1, 0, 12, False),
            (2, 0, 12, True),
            (2, 1, 12, False),
            (2, 0, 0, False),
        ):
            with self.subTest(intelligence=intelligence, silenced=silenced, mp=mp):
                enemy = self.enemy(
                    front=False, spells=(spell,), intelligence=intelligence,
                    silenced=silenced, max_mp=12, mp=mp, magic=10,
                )
                forecast = BattleForecast(self.snapshot(self.specs[0], enemy), 0)
                with patch.object(forecast, "roll", return_value=0.99):
                    forecast.enemy_turn(forecast.actors[5])
                self.assertEqual(
                    forecast.actors[5].mp, mp - (spell.mp if uses_spell else 0),
                )

    def test_int_two_forecast_draws_sleep_and_silence_with_damage_spell(self):
        spells = tuple(self.spells[key] for key in ("SLEEP", "SILENCE", "POISON2"))
        enemy = self.enemy(front=False, intelligence=2, spells=spells, mp=20, max_mp=20)
        target = replace(self.specs[0], spells=(self.spells["FIRE1"],), resistances=frozenset())
        resistant = replace(target, resistances=frozenset((ResistanceType.SLEEP, ResistanceType.SILENCE)))
        for member, roll, expected in (
            (target, 0.0, "POISON2"), (target, 0.5, "SILENCE"),
            (target, 0.9, "SLEEP"), (resistant, 0.9, "POISON2"),
        ):
            with self.subTest(roll=roll, expected=expected):
                forecast = BattleForecast(self.snapshot(enemy, member, active=5), 0)
                with patch.object(forecast, "roll", return_value=roll):
                    forecast.enemy_turn(forecast.actors[5])
                self.assertEqual(forecast.actors[5].mp, enemy.mp - self.spells[expected].mp)

    def test_int_two_forecast_draws_call_with_damage_spell(self):
        enemy = self.enemy(
            front=False, intelligence=2, spells=(self.spells["POISON2"],), mp=20, max_mp=20,
            special_actions=(MonsterSpecialAction.CALL,),
            monster_placement=MonsterPlacement(1, 4, 112, 64, 64),
        )
        for roll, calls in ((0.0, False), (0.9, True)):
            with self.subTest(roll=roll):
                forecast = BattleForecast(self.snapshot(enemy, self.specs[0], active=5), 0)
                with patch.object(forecast, "roll", return_value=roll):
                    forecast.enemy_turn(forecast.actors[5])
                self.assertEqual(6 in forecast.actors, calls)

    def test_int_two_enemy_attack_prefers_sleeping_front_row_member(self):
        for intelligence, expected in ((1, 0), (2, 1)):
            with self.subTest(intelligence=intelligence):
                forecast = BattleForecast(self.snapshot(
                    replace(self.specs[0], front=True),
                    replace(self.specs[1], front=True, sleeping=2),
                    self.enemy(intelligence=intelligence),
                ), 0)
                with (
                    patch.object(forecast, "roll", return_value=0.0),
                    patch.object(forecast, "enemy_physical") as strike,
                ):
                    forecast.enemy_turn(forecast.actors[5])
                self.assertEqual(strike.call_args.args[1].spec.number, expected)

    def test_enemy_silence_and_ally_spell_blocking_are_forecast(self):
        spell = self.spells["SILENCE"]
        enemy = self.enemy(front=False, spells=(spell,), intelligence=1,
                           magic=17, max_mp=10, mp=10)
        ally = replace(self.specs[1], number=0, spells=(self.spells["FIRE1"],))
        forecast = BattleForecast(self.snapshot(ally, enemy), 0)
        forecast.roll = Mock(return_value=0.0)
        forecast.enemy_turn(forecast.actors[5])
        target = forecast.actors[0]
        self.assertEqual(target.silenced, 4)
        self.assertEqual(forecast.actors[5].mp, 10 - spell.mp)
        mp = target.mp
        enemy_hp = forecast.actors[5].hp
        forecast.execute(0, AutoAction(BattleCommand.SPELL, (5,), "FIRE1"))
        self.assertEqual(target.mp, mp)
        self.assertEqual(forecast.actors[5].hp, enemy_hp)
        self.assertEqual(target.silenced, 3)

    def test_int_one_break_and_single_slow_skip_invalid_preselected_target(self):
        for key, changes in (
            ("ARMOR BREAK", {"front": False}),
            ("ARMOR BREAK", {"protection": -1}),
            ("SLOW", {"speed": -1}),
        ):
            with self.subTest(spell=key, changes=changes):
                spell = self.spells[key]
                ally = replace(self.specs[0], **changes)
                enemy = self.enemy(front=False, spells=(spell,), intelligence=1,
                                   magic=17, max_mp=10, mp=10)
                forecast = BattleForecast(self.snapshot(ally, enemy), 0)
                forecast.roll = Mock(return_value=0.0)
                forecast.enemy_turn(forecast.actors[5])
                self.assertEqual(forecast.actors[5].mp, 10)
                self.assertEqual(forecast.actors[0].protection, ally.protection)
                self.assertEqual(forecast.actors[0].speed, ally.speed)

    def test_incremental_and_synchronous_planning_are_identical_and_do_not_mutate(self):
        snapshot = self.snapshot(self.specs[0], self.enemy(max_hp=20, hp=20))
        original = repr(snapshot)
        before = random.getstate()
        result = decide_auto_battle(snapshot)
        planner = AutoBattlePlanner(snapshot)
        for units in (1, 7, 31, 3):
            planner.advance(units)
        while planner.result is None:
            planner.advance(17)
        self.assertEqual(planner.result, result)
        self.assertEqual(random.getstate(), before)
        self.assertEqual(repr(snapshot), original)
        for evaluation in result.evaluations:
            self.assertAlmostEqual(
                evaluation.score,
                sum(v * w for (_, v), w in zip(evaluation.components, VALUE_WEIGHTS))
                - evaluation.cost,
            )

    def test_candidate_definition_order_does_not_change_scores(self):
        snapshot = self.snapshot(self.specs[0], self.enemy(max_hp=20, hp=20))
        reordered = replace(
            snapshot,
            spells=tuple(reversed(snapshot.spells)),
            combatants=(
                replace(
                    snapshot.combatants[0], spells=tuple(reversed(self.specs[0].spells))
                ),
                snapshot.combatants[1],
            ),
        )
        self.assertEqual(decide_auto_battle(snapshot), decide_auto_battle(reordered))

    def test_cross_case_caches_preserve_scores_and_timeline_semantics(self):
        snapshot = self.snapshot(self.specs[0], self.specs[1], self.enemy())
        cached = decide_auto_battle(snapshot)
        original = AutoBattlePlanner._forecast

        def without_shared_caches(planner, case, cache):
            forecast = original(planner, case, cache)
            forecast.expected_cache = {}
            forecast.command_cache = {}
            forecast.timeline_cache = {}
            return forecast

        with patch.object(AutoBattlePlanner, "_forecast", without_shared_caches):
            uncached = decide_auto_battle(snapshot)
        self.assertEqual(cached, uncached)

    def test_next_healer_reads_hp_after_first_heal_without_a_reservation(self):
        wounded = replace(self.specs[0], hp=self.specs[0].max_hp - 5)
        healer = self.specs[1]
        forecast = BattleForecast(self.snapshot(wounded, healer, self.enemy()), 0)
        forecast.cast(
            forecast.actors[1], AutoAction(BattleCommand.SPELL, (0,), "HEALING1")
        )
        self.assertEqual(forecast.actors[0].hp, wounded.max_hp)
        self.assertFalse(any(a.spell_key == "HEALING1" for a in forecast.candidates(1)))

    def test_air_blade_predicts_double_damage_for_flying_profiles(self):
        enemies = tuple(
            self.enemy(number, hp=10000, max_hp=10000, shadow=number != 5)
            for number in (5, 6, 7)
        )
        forecast = BattleForecast(self.snapshot(self.specs[0], *enemies), 0)
        with patch.object(forecast, "roll", return_value=0):
            forecast.cast(
                forecast.actors[0],
                AutoAction(BattleCommand.SPELL, (5, 6, 7), "AIR BLADE"),
            )
        normal, flying_one, flying_two = (
            10000 - forecast.actors[number].hp for number in (5, 6, 7)
        )
        self.assertGreater(normal, 0)
        self.assertLessEqual(abs(flying_one - normal * 2), 1)
        self.assertEqual(flying_one, flying_two)

    def test_zero_mp_and_already_dead_member_do_not_block_planning(self):
        ally = replace(self.specs[0], max_mp=0, mp=0, spells=())
        dead = replace(self.specs[1], alive=False, hp=0)
        result = decide_auto_battle(
            self.snapshot(ally, dead, self.enemy(max_hp=1, hp=1))
        )
        self.assertEqual(result.action.command, BattleCommand.ATTACK)
        self.assertTrue(
            all(dict(e.components)["deaths"] == 0 for e in result.evaluations)
        )

    def test_guard_only_fallback_remains_progressable(self):
        actor = replace(
            self.specs[0],
            weapons=(),
            spells=(),
            mp=0,
            max_mp=0,
            equipment=self.specs[0].equipment.replaced({EquipmentSlot.RIGHT: None}),
        )
        result = decide_auto_battle(self.snapshot(actor, self.enemy()))
        self.assertEqual(result.action, AutoAction(BattleCommand.DEFEND))
        self.assertEqual(len(result.evaluations), 1)

    def test_escape_comparison_uses_main_hand_only_when_left_weapon_remains(self):
        actor = replace(
            self.specs[0],
            skills=frozenset(("Dual-Wield",)),
            weapons=(AutoWeapon(100, 100),),
            equipment=self.specs[0].equipment.replaced(
                {
                    EquipmentSlot.RIGHT: None,
                    EquipmentSlot.LEFT: self.items["ICING BLADE!"],
                }
            ),
        )
        enemy = self.enemy(attack=0, special_actions=(MonsterSpecialAction.ESCAPE,))
        forecast = BattleForecast(self.snapshot(actor, enemy), 0)
        forecast.execute(0, AutoAction(BattleCommand.DEFEND))
        with patch.object(forecast, "roll", return_value=0.75):
            forecast.enemy_turn(forecast.actors[5])
        self.assertFalse(forecast.actors[5].removed)


class AutoBattleSceneIntegrationTest(AutoBattleFixtures, unittest.TestCase):
    def test_manual_and_auto_battle_share_the_spell_unlocks(self):
        from resources import load_record_array
        from scenes.battle import BattleMonster, BattleScene
        from state import SaveData

        scene = BattleScene.__new__(BattleScene)
        scene.party = self.party[:2]
        scene.spells = self.spells
        scene.save_data = SaveData()
        record = next(
            record for record in load_record_array("monsters.json") if record["name_en"] == "Giant Spider"
        )
        scene.monsters = (BattleMonster.from_record(record, is_front_row=True),)
        scene.party_visuals = tuple(Mock(member=member) for member in scene.party)
        scene.progression = Mock()
        scene.progression.used_spell_kinds.return_value = ()
        for name in (
            "escaped_party_indexes", "hidden_party_indexes", "defending_party_indexes",
            "surprise_pending_party_indexes", "surprise_deferred_party_indexes",
            "identified_monster_indexes",
        ):
            setattr(scene, name, set())
        for name in (
            "cover_target_by_party_index", "focused_target_by_party_index",
            "surprise_original_front_rows",
        ):
            setattr(scene, name, {})
        scene._party_member_is_front_row = Mock(return_value=True)

        for flag_id, spell_key, member_index in (
            (TELEPORT_UNSEALED, "TELEPORT", 0),
            (ABYSS_NOVA_UNSEALED, "ABYSS NOVA", 0),
            (REVIVE2_UNSEALED, "REVIVE2", 1),
        ):
            with self.subTest(flag_id=flag_id):
                spell = self.spells[spell_key]
                scene.active_party_index = member_index
                scene._timeline_order = TimelineOrder((
                    TimelineEntry(scene.party_visuals[member_index], 15, 64),
                    TimelineEntry(scene.monsters[0], 10, 20),
                ))
                scene.save_data.event_flags.clear()
                self.assertNotIn(spell, scene._active_member_spell_candidates())
                self.assertNotIn(spell, scene._auto_battle_snapshot().combatants[member_index].spells)

                scene.save_data.event_flags.add(flag_id)
                self.assertIn(spell, scene._active_member_spell_candidates())
                self.assertIn(spell, scene._auto_battle_snapshot().combatants[member_index].spells)

    def test_target_cursors_hidden_during_auto_and_restored_for_manual(self):
        from scenes.battle import BattlePhase, BattleScene

        cases = (
            (BattlePhase.TARGET, BattleCommand.ATTACK, False, True, "enemy"),
            (BattlePhase.TARGET, BattleCommand.IAI, True, True, "all"),
            (BattlePhase.COVER_TARGET, BattleCommand.COVER, False, False, "party"),
            (BattlePhase.ACTION_TARGET, BattleCommand.SPELL, False, True, "enemy"),
            (BattlePhase.ACTION_TARGET, BattleCommand.SPELL, False, False, "party"),
            (BattlePhase.ACTION_TARGET, BattleCommand.SPELL, True, True, "all"),
            (BattlePhase.ACTION_TARGET, BattleCommand.SPELL, True, False, "all"),
        )
        for phase, command, all_targets, enemy_targets, visible in cases:
            with self.subTest(phase=phase, command=command, visible=visible,
                              all_targets=all_targets, enemy_targets=enemy_targets):
                scene = BattleScene.__new__(BattleScene)
                scene.phase = phase
                scene.selected_command = command
                scene.action_targets_all = all_targets
                scene.action_targets_enemy = enemy_targets
                cursors = {key: Mock() for key in ("enemy", "party", "all")}
                scene.target_cursor = cursors["enemy"]
                scene.party_target_cursor = cursors["party"]
                scene.all_target_cursors = (cursors["all"],)

                with patch("scenes.battle.pyxel") as px:
                    px.frame_count = 0
                    scene.auto_battle_active = True
                    scene._draw_target_cursor()
                    for cursor in cursors.values():
                        cursor.draw.assert_not_called()

                    scene.auto_battle_active = False
                    scene._draw_target_cursor()
                    cursors[visible].draw.assert_called_once()
                    for key, cursor in cursors.items():
                        if key != visible:
                            cursor.draw.assert_not_called()

    def test_snapshot_reads_live_hp_mp_and_masks_unrevealed_affinities(self):
        from resources import load_record_array
        from scenes.battle import BattleMonster, BattleScene
        from state import SaveData
        from systems.battle_progression import BattleProgression, EnemyProgressionData

        scene = BattleScene.__new__(BattleScene)
        record = next(
            r
            for r in load_record_array("monsters.json", APP_ROOT / "data")
            if r["name_en"] == "Giant Spider"
        )
        scene.monsters = (
            BattleMonster.from_record(
                {
                    **record,
                    "healing": 2,
                    "is_boss": 1,
                    "mmp": 12,
                    "shadow": 1,
                    "tolerance": "死",
                    "weakness": "炎",
                },
                is_front_row=True,
            ),
        )
        scene.party = self.party[:1]
        scene.party_visuals = (Mock(member=scene.party[0]),)
        scene.active_party_index = 0
        scene.spells = self.spells
        scene.save_data = SaveData()
        for name in (
            "escaped_party_indexes",
            "hidden_party_indexes",
            "defending_party_indexes",
            "identified_monster_indexes",
            "surprise_pending_party_indexes",
            "surprise_deferred_party_indexes",
            "temporary_front_party_indexes",
        ):
            setattr(scene, name, set())
        for name in (
            "cover_target_by_party_index",
            "focused_target_by_party_index",
            "surprise_original_front_rows",
        ):
            setattr(scene, name, {})
        scene.progression = BattleProgression((EnemyProgressionData(1, 0, 1, 0),))
        scene._timeline_order = TimelineOrder(
            (
                TimelineEntry(scene.party_visuals[0], 15, 64),
                TimelineEntry(scene.monsters[0], 10, 20),
            )
        )
        state = scene.monsters[0].state
        initial = scene._auto_battle_snapshot().combatants[-1]
        self.assertEqual((initial.hp, initial.max_hp, initial.mp, initial.max_mp),
                         (state.max_hp, state.max_hp, 12, 12))
        state.take_damage(state.max_hp - 1)
        state.spend_mp(9)
        state.apply_confusion(2)
        enemy = scene._auto_battle_snapshot().combatants[-1]
        self.assertEqual((enemy.hp, enemy.max_hp, enemy.mp, enemy.max_mp), (1, state.max_hp, 3, 12))
        self.assertFalse(enemy.hp_displayed)
        self.assertIsNone(enemy.tribe)
        self.assertFalse(enemy.shadow)
        self.assertFalse(enemy.resistances)
        self.assertFalse(enemy.weaknesses)
        self.assertEqual(enemy.confused, 2)
        self.assertEqual(enemy.healing, 2)
        self.assertTrue(enemy.is_boss)
        self.assertEqual((initial.hp, initial.mp), (state.max_hp, 12))

        state.apply_healing(4)
        state.spend_mp(3)
        scene.save_data.monster_records["Giant Spider"] = {"profile", "DEATH", "FIRE"}
        revealed = scene._auto_battle_snapshot().combatants[-1]
        self.assertEqual((revealed.hp, revealed.mp), (5, 0))
        self.assertEqual(revealed.tribe, MonsterTribe.ANIMAL)
        self.assertTrue(revealed.shadow)
        self.assertIn(ResistanceType.DEATH, revealed.resistances)
        self.assertIn(ResistanceType.FIRE, revealed.weaknesses)
        scene.identified_monster_indexes.add(0)
        self.assertEqual(
            scene._auto_battle_snapshot().combatants[-1], replace(revealed, hp_displayed=True)
        )

    def test_game_menu_suspends_and_resumes_the_same_partial_planner(self):
        from input import InputButton, InputState
        from rendering import FadeThroughBlack
        from scenes.battle import BattlePhase, BattleScene

        from tests.test_game_menu import GameMenuTest

        fixture = GameMenuTest()
        game = fixture.game()
        scene = BattleScene.__new__(BattleScene)
        scene.phase = BattlePhase.AUTO_THINKING
        scene.result = None
        scene.entrance_fade = FadeThroughBlack()
        scene.escape_fade = FadeThroughBlack()
        scene.result_transition_fade = FadeThroughBlack()
        planner = AutoBattlePlanner(self.snapshot())
        planner.advance(5)
        scene.auto_battle_planner = planner
        scene.update = Mock(side_effect=lambda _: planner.advance())
        game.battle_scene = scene
        fixture.open(game)
        for _ in range(3):
            fixture.update(game)
        self.assertEqual(planner.completed_units, 5)
        fixture.update(game, InputState(cancel=InputButton(triggered=True)))
        fixture.update(game)  # Release all held actions before resuming.
        self.assertIs(scene.auto_battle_planner, planner)
        self.assertEqual(planner.completed_units, 5)
        fixture.update(game)
        self.assertEqual(planner.completed_units, 6)
        game.bgm.pause.assert_called_once()
        game.bgm.resume.assert_called_once()

    def test_cancel_thinking_preserves_current_actor_and_resources(self):
        from scenes.battle import BattlePhase, BattleScene

        scene = BattleScene.__new__(BattleScene)
        scene.phase = BattlePhase.AUTO_THINKING
        scene.auto_battle_active = True
        scene.auto_battle_planner = AutoBattlePlanner(self.snapshot())
        scene.active_party_index = 0
        scene._open_member_command_menu = Mock()
        scene._refresh_input_guide = Mock()
        before = (self.party[0].hp, self.party[0].mp)
        scene.auto_battle_planner.advance(10)
        scene._cancel_auto_battle()
        self.assertIsNone(scene.auto_battle_planner)
        self.assertFalse(scene.auto_battle_active)
        self.assertEqual(scene.active_party_index, 0)
        self.assertEqual((self.party[0].hp, self.party[0].mp), before)
        scene._open_member_command_menu.assert_called_once()

    def test_cancel_spell_before_payment_returns_to_commands(self):
        from scenes.battle import BattlePhase, BattleScene

        scene = BattleScene.__new__(BattleScene)
        scene.phase = BattlePhase.ACTION_TARGET
        scene.auto_battle_active = True
        scene._clear_action_target_state = Mock()
        scene._begin_action_return = Mock()
        scene._open_member_command_menu = Mock()
        scene._refresh_input_guide = Mock()
        scene._cancel_auto_battle()
        scene._clear_action_target_state.assert_called_once()
        scene._begin_action_return.assert_called_once_with()
        scene._open_member_command_menu.assert_called_once()

    def test_cancel_after_payment_keeps_running_presentation(self):
        from scenes.battle import BattlePhase, BattleScene

        scene = BattleScene.__new__(BattleScene)
        scene.phase = BattlePhase.ACTION_PRESENTATION
        scene.auto_battle_active = True
        scene.action_presentation = object()
        presentation = scene.action_presentation
        scene._begin_action_return = Mock()
        scene._refresh_input_guide = Mock()
        scene._cancel_auto_battle()
        self.assertIs(scene.action_presentation, presentation)
        self.assertIs(scene.phase, BattlePhase.ACTION_PRESENTATION)
        scene._begin_action_return.assert_not_called()

    def test_identify_waits_for_a_new_confirm_or_cancel_press(self):
        from input import InputButton, InputState
        from scenes.battle import (
            BATTLE_CONFIRM_REPEAT_DELAY_FRAME_COUNT,
            BattlePhase,
            BattleScene,
        )

        for auto_active in (False, True):
            for button in ("confirm", "cancel"):
                with self.subTest(auto_active=auto_active, button=button):
                    scene = BattleScene.__new__(BattleScene)
                    scene.phase = BattlePhase.IDENTIFY_RESULT
                    scene.auto_battle_active = auto_active
                    scene.identify_detail_window = window = Mock()
                    scene.identify_target_index = 0
                    scene.confirm_hold_frame_count = (
                        BATTLE_CONFIRM_REPEAT_DELAY_FRAME_COUNT - 1
                    )
                    held = InputState(confirm=InputButton(held=True))
                    for input_state in (held, InputState()):
                        for _ in range(120):
                            scene.update(input_state)
                        self.assertIs(scene.phase, BattlePhase.IDENTIFY_RESULT)
                        self.assertIs(scene.identify_detail_window, window)
                        window.close_immediately.assert_not_called()

                    scene.update(InputState(**{button: InputButton(triggered=True)}))

                    window.close_immediately.assert_called_once_with()
                    self.assertIsNone(scene.identify_detail_window)
                    self.assertIs(scene.phase, BattlePhase.ACTION_RETURN)
                    self.assertEqual(
                        scene.auto_battle_active, auto_active and button == "confirm"
                    )
