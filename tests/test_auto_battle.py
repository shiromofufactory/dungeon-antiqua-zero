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
    AutoBattleObservations,
    AutoBattlePolicy,
    AutoBattleSnapshot,
    AutoCombatant,
    AutoWeapon,
    ItemMode,
    SpellMode,
    quantile,
)
from auto_battle_simulation import BattleForecast, ForecastActor, mp_cost
from battle_commands import BattleCommand
from battle_magic import member_spell_ability, resolve_healing
from battle_physical import member_physical_attack, resolve_physical_attack
from battle_timeline import TimelineEntry, TimelineOrder
from item import AdditionalEffect
from member import EquipmentSlot
from monster import MonsterSpecialAction
from monster_ai import MonsterSpellAction
from resistance import ResistanceType
from spell import SpellAction, SpellType

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

    def test_full_recovery_treats_current_ailments_even_at_full_hp(self):
        ring = replace(self.items["MIRACLE RING"], use_spell_key="PANACEA")
        caster = replace(
            self.specs[1],
            mp=0,
            silenced=2,
            equipment=self.specs[1].equipment.replaced({EquipmentSlot.ARM: ring}),
        )
        for field, value in (
            ("poisoned", True),
            ("sleeping", 2),
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

    def test_dedicated_cure_is_selected_for_its_four_ailments(self):
        caster = replace(
            self.specs[1],
            spells=(self.spells["CURE"],),
            mp=self.spells["CURE"].mp,
        )
        for field, value in (
            ("poisoned", True),
            ("sleeping", 2),
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
        for policy in (AutoBattlePolicy(), AutoBattlePolicy(SpellMode.NEVER)):
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
        enemy = self.enemy(attack=80, hp=1000, max_hp=1000)
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

    def test_unknown_hp_is_an_estimate_with_observation_lower_bound(self):
        enemy = self.enemy(max_hp=None, hp=None, hp_displayed=False, net_damage=999)
        for case in range(CASE_COUNT):
            actor = ForecastActor.create(enemy, 100, case)
            self.assertGreaterEqual(actor.max_hp, 1000)
            self.assertEqual(actor.hp, actor.max_hp - 999)
        actor = ForecastActor.create(
            self.enemy(max_hp=120, hp=None, net_damage=40), 100, 0
        )
        self.assertEqual(actor.hp, 80)
        actor = ForecastActor.create(
            self.enemy(max_hp=120, hp=31, net_damage=40), 100, 0
        )
        self.assertEqual(actor.hp, 31)

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

    def test_recovery_only_and_never_policies_are_independent_of_items(self):
        healer = replace(
            self.specs[1],
            hp=20,
            equipment=self.specs[1].equipment.replaced(
                {EquipmentSlot.ARM: self.items["FLAME RING"]}
            ),
        )
        for mode in SpellMode:
            forecast = BattleForecast(
                self.snapshot(
                    healer, self.enemy(), active=1, policy=AutoBattlePolicy(mode)
                ),
                0,
            )
            actions = forecast.candidates(1)
            paid = [
                self.spells[a.spell_key]
                for a in actions
                if a.command is BattleCommand.SPELL
            ]
            if mode is SpellMode.NEVER:
                self.assertFalse(paid)
            elif mode is SpellMode.RECOVERY_ONLY:
                self.assertTrue(paid)
                self.assertTrue(all(s.action is SpellAction.HEAL for s in paid))
            else:
                self.assertTrue(any(s.action is SpellAction.DAMAGE for s in paid))
            self.assertTrue(any(a.command is BattleCommand.ITEM for a in actions))

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
                    policy=AutoBattlePolicy(SpellMode.NEVER, ItemMode.NEVER),
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

    def test_enemy_turn_healing_matches_poison_net_change_and_caps_hp(self):
        for healing, poisoned, weak, hp, expected in (
            (1, False, False, 10, 18),
            (1, False, False, 119, 120),
            (1, True, False, 10, 10),
            (1, True, True, 40, 33),
            (-1, True, False, 10, 0),
        ):
            with self.subTest(healing=healing, poisoned=poisoned, weak=weak, hp=hp):
                spec = self.enemy(
                    hp=hp, healing=healing, poisoned=poisoned, sleeping=2,
                    weaknesses=frozenset((ResistanceType.POISON,)) if weak else frozenset(),
                )
                forecast = BattleForecast(self.snapshot(self.specs[0], spec), 0)
                enemy = forecast.actors[5]
                forecast.prepare_turn(enemy)
                self.assertEqual(enemy.hp, expected)
                if expected:
                    self.assertEqual(enemy.sleeping, 1)

    def test_confused_forecast_actors_attack_their_own_side(self):
        forecast = BattleForecast(
            self.snapshot(self.specs[0], self.specs[1], self.enemy(), self.enemy(6)),
            0,
        )
        forecast.roll = Mock(return_value=0.0)
        member = forecast.actors[0]
        member.confused = 2
        ally_hp = forecast.actors[1].hp

        forecast.confused_turn(member)

        self.assertEqual(member.confused, 1)
        self.assertLess(forecast.actors[1].hp, ally_hp)

        monster = forecast.actors[5]
        monster.confused = 2
        other_hp = forecast.actors[6].hp

        forecast.confused_turn(monster)

        self.assertEqual(monster.confused, 1)
        self.assertLess(forecast.actors[6].hp, other_hp)

    def test_monster_power_hit_forecasts_match_physical_attack_rules(self):
        for mode in ("attack", "charge", "confused"):
            for power_hit, sleeping, roll in (
                (False, 0, 0), (True, 0, 9), (True, 0, 10),
                (False, 2, 20), (True, 2, 39), (True, 2, 40),
            ):
                with self.subTest(
                    mode=mode, power_hit=power_hit, sleeping=sleeping, roll=roll,
                ):
                    specials = (MonsterSpecialAction.POWER_HIT,) if power_hit else ()
                    if mode == "charge":
                        specials += (MonsterSpecialAction.CHARGE,)
                    enemy = self.enemy(front=mode != "charge", special_actions=specials)
                    member = replace(
                        self.specs[0], hp=1000, max_hp=1000, defense=10,
                        evasion=0, agility=20, sleeping=sleeping,
                    )
                    other = self.enemy(
                        6, hp=1000, max_hp=1000, defense=10, sleeping=sleeping,
                    )
                    forecast = BattleForecast(self.snapshot(member, enemy, other), 0)
                    forecast.roll = Mock(
                        side_effect=lambda _actor, _target, purpose: (
                            roll / 100 if purpose == 3 else 0.0
                        ),
                    )
                    target = forecast.actors[6 if mode == "confused" else 0]
                    expected = resolve_physical_attack(
                        attack=30 if mode == "charge" else 20,
                        hit=100,
                        target_defense=10,
                        target_evasion=0,
                        hit_roll=0,
                        target_incapacitated=bool(sleeping),
                        attacker_has_power_hit=power_hit,
                        critical_roll=roll,
                    )
                    if mode == "confused":
                        forecast.confused_physical(forecast.actors[5], target)
                    else:
                        forecast.enemy_turn(forecast.actors[5])
                    self.assertEqual(target.hp, 1000 - expected.damage)

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

    def test_observations_accumulate_presented_amounts_including_overkill(self):
        observations = AutoBattleObservations()
        observations.damage(0, 40)
        observations.damage(0, 100)
        observations.spend_mp(0, 3)
        self.assertEqual(observations.enemy_net_damage, {0: 140})
        self.assertEqual(observations.enemy_mp_spent, {0: 3})

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

    def test_snapshot_masks_actual_hp_and_unrevealed_affinities(self):
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
            BattleMonster.from_record({**record, "healing": 2}, is_front_row=True),
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
            "temporary_front_party_indexes",
        ):
            setattr(scene, name, set())
        for name in (
            "cover_target_by_party_index",
            "focused_target_by_party_index",
            "surprise_original_front_rows",
        ):
            setattr(scene, name, {})
        scene.auto_battle_policy = AutoBattlePolicy()
        scene.auto_battle_observations = AutoBattleObservations()
        scene.auto_battle_observations.damage(0, 33)
        scene.auto_battle_observations.spend_mp(0, 3)
        scene.progression = BattleProgression((EnemyProgressionData(1, 0, 1, 0),))
        scene._timeline_order = TimelineOrder(
            (
                TimelineEntry(scene.party_visuals[0], 15, 64),
                TimelineEntry(scene.monsters[0], 10, 20),
            )
        )
        scene.monsters[0].state.hp = 1
        first = scene._auto_battle_snapshot()
        scene.monsters[0].state.hp = scene.monsters[0].state.max_hp
        self.assertEqual(scene._auto_battle_snapshot(), first)
        enemy = first.combatants[-1]
        self.assertIsNone(enemy.hp)
        self.assertIsNone(enemy.max_hp)
        self.assertFalse(enemy.resistances)
        self.assertFalse(enemy.weaknesses)
        self.assertEqual(enemy.net_damage, 33)
        self.assertEqual(enemy.healing, 2)
        self.assertEqual(enemy.mp, max(0, scene.monsters[0].max_mp - 3))
        scene.save_data.monster_records["Giant Spider"] = {"profile"}
        self.assertIsNotNone(scene._auto_battle_snapshot().combatants[-1].max_hp)
        scene.identified_monster_indexes.add(0)
        self.assertEqual(
            scene._auto_battle_snapshot().combatants[-1].hp, scene.monsters[0].state.hp
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

    def test_auto_identify_closes_after_sixty_frames(self):
        from input import InputState
        from scenes.battle import BattleScene

        scene = BattleScene.__new__(BattleScene)
        scene.auto_battle_active = True
        scene.identify_result_elapsed_frame = 0
        scene._finish_identify_result = Mock()
        for _ in range(59):
            scene._update_identify_result(InputState())
        scene._finish_identify_result.assert_not_called()
        scene._update_identify_result(InputState())
        scene._finish_identify_result.assert_called_once()
