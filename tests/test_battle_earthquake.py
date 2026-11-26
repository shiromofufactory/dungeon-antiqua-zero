from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, PropertyMock, call, patch

from tools._bootstrap import APP_ROOT  # noqa: F401
from tools.screen_mocks._fixtures import load_mock_items
from auto_battle_simulation import BattleForecast
from battle_magic import SpellAffinity
from battle_physical import resolve_earthquake_attack
from game import Game
from member import EquipmentSlot, FormationRow, Race
from monster import MonsterSpecialAction, MonsterTribe
from monster_ai import MonsterAction, monster_action_candidates
from resistance import ResistanceType
from resources import load_record_array
from scenes.battle import (
    BattleMonster, DAMAGE_POPUP_FRAME_COUNT, EARTHQUAKE_SHAKE_FRAME_COUNT,
    EARTHQUAKE_SHAKE_AMPLITUDE,
)
from tests import test_battle_poison_breath as poison_tests
from tests.test_auto_battle import AutoBattleFixtures


class EarthquakeRuleTest(unittest.TestCase):
    def test_floating_targets_always_miss(self):
        result = resolve_earthquake_attack(
            attack=96, hit=100, target_defense=0, hit_roll=0, target_floating=True,
        )
        self.assertFalse(result.hit)
        self.assertEqual(result.damage, 0)

    def test_sixty_percent_physical_defense_always_hits_without_critical(self):
        for roll in range(100):
            for defending in (False, True):
                result = resolve_earthquake_attack(
                    attack=96, hit=100, target_defense=10,
                    hit_roll=roll, target_defending=defending,
                )
                expected = int((57 - 10) * (0.8 + (100 - roll) / 250) * 0.9 + 0.99)
                self.assertTrue(result.hit)
                self.assertFalse(result.critical)
                self.assertEqual(result.damage, expected // 2 if defending else expected)
        result = resolve_earthquake_attack(
            attack=96, hit=0, target_defense=100, hit_roll=99, target_defending=True,
        )
        self.assertTrue(result.hit)
        self.assertEqual(result.damage, 0)

    def test_registered_behemoth_has_counter_power_hit_and_earthquake(self):
        record = next(r for r in load_record_array("monsters.json") if r["name_en"] == "Behemoth")
        actor = BattleMonster.from_record(record, is_front_row=True)
        self.assertEqual(actor.special_actions, (
            MonsterSpecialAction.COUNTER, MonsterSpecialAction.POWER_HIT,
            MonsterSpecialAction.EARTHQUAKE,
        ))

    def test_earthquake_is_one_candidate_and_counter_remains_passive(self):
        for front in (False, True):
            for targets in (False, True):
                self.assertEqual(monster_action_candidates(
                    special_actions=(MonsterSpecialAction.EARTHQUAKE, MonsterSpecialAction.COUNTER),
                    is_front_row=front, can_attack=front, can_charge=False,
                    spell_keys=(), escape_eligible=False, can_earthquake=targets,
                ), (*((MonsterAction.EARTHQUAKE,) if targets else ()),
                    MonsterAction.ATTACK if front else MonsterAction.IDLE))


class EarthquakeSceneTest(unittest.TestCase):
    def scene(self):
        scene, actor = poison_tests.PoisonBreathSceneTest().scene()
        for member in scene.party:
            member.definition = replace(member.definition, race=Race.HUMAN)
        return scene, actor

    def begin(self, scene, actor, *, stun_roll=0):
        actor.special_actions = (MonsterSpecialAction.POWER_HIT, MonsterSpecialAction.EARTHQUAKE)
        actor.state.silenced = 3
        with patch("scenes.battle.random.randint", side_effect=(99, stun_roll, 99, stun_roll)), \
                patch("scenes.battle.play_se") as sound:
            self.assertTrue(scene._begin_monster_earthquake(actor))
        sound.assert_called_once_with("battle_earthquake")

    def test_shake_finishes_before_damage_popups_then_waits_for_their_completion(self):
        scene, actor = self.scene()
        scene.defending_party_indexes = set()
        hp = tuple(m.hp for m in scene.party)
        self.begin(scene, actor)
        presentation = scene.action_presentation
        scene._show_monster_action_message.assert_called_once_with("battle.monster.earthquake")
        self.assertEqual(actor.state.mp, 0)
        self.assertEqual(scene.spell_damage_popups, [])
        self.assertFalse(presentation.party_damage_motion_visible(0))
        with patch("scenes.battle.random.randint", return_value=2) as shake_roll:
            for _ in range(EARTHQUAKE_SHAKE_FRAME_COUNT - 1):
                scene._update_action_presentation()
            shake_roll.assert_called_with(-EARTHQUAKE_SHAKE_AMPLITUDE, EARTHQUAKE_SHAKE_AMPLITUDE)
        self.assertEqual(tuple(m.hp for m in scene.party), hp)
        self.assertFalse(any(m.stunned for m in scene.party))
        self.assertEqual(scene.screen_shake_offset, (2, 2))
        scene._update_action_presentation()
        for i, result in enumerate(presentation.party_damage_results):
            self.assertEqual(scene.party[i].hp, max(0, hp[i] - result.damage))
            self.assertTrue(scene.party[i].stunned)
        self.assertEqual(len(scene.spell_damage_popups), 2)
        self.assertEqual(scene.screen_shake_offset, (0, 0))
        self.assertTrue(presentation.party_damage_motion_visible(0))
        scene._complete_current_turn.assert_not_called()
        with patch("scenes.battle.random.randint") as shake_roll:
            for _ in range(DAMAGE_POPUP_FRAME_COUNT):
                scene._update_spell_damage_popups()
                scene._update_action_presentation()
            shake_roll.assert_not_called()
        self.assertEqual(scene.spell_damage_popups, [])
        scene._complete_current_turn.assert_called_once_with()

    def test_stun_uses_updated_probability_resistance_and_guard(self):
        for roll, resistances, defending, success in (
            (19, (), False, True), (20, (), False, False),
            (9, (ResistanceType.DEATH,), False, True),
            (10, (ResistanceType.DEATH,), False, False),
            (0, (ResistanceType.STUN,), False, False), (0, (), True, False),
        ):
            scene, actor = self.scene()
            scene.defending_party_indexes = {0, 1} if defending else set()
            with patch.object(type(scene.party[0]), "resistances", new_callable=PropertyMock,
                              return_value=frozenset(resistances)):
                self.begin(scene, actor, stun_roll=roll)
            self.assertEqual(tuple(r.success for r in scene.action_presentation.party_stun_results), (success, success))

    def test_matching_tribe_reduces_damage_and_blocks_earthquake_stun_on_impact(self):
        scene, actor = self.scene()
        actor.tribe = MonsterTribe.GIANT
        member = scene.party[0]
        member.equipment = member.equipment.replaced({EquipmentSlot.RIGHT: load_mock_items()["ONIGOROSHI"]})
        scene.defending_party_indexes = set()
        self.begin(scene, actor)
        hit = scene.action_presentation.party_damage_results[0]
        base_attack = actor.combat_stats.attack * 3 // 5
        defense = member.battle_stats.defense
        hit_value = max(actor.combat_stats.hit, 100) - 99
        expected = int((base_attack - defense) * (0.8 + hit_value / 250)
                       * (1 - defense / 200) + 0.99) // 2
        self.assertEqual(hit.damage, expected)
        self.assertEqual(hit.affinity, SpellAffinity.RESIST)
        self.assertFalse(scene.action_presentation.party_stun_results[0].success)
        self.assertEqual(scene.affinity_popups, [])
        with patch("scenes.battle.random.randint", return_value=0):
            for _ in range(EARTHQUAKE_SHAKE_FRAME_COUNT):
                scene._update_action_presentation()
        self.assertEqual([popup.affinity for popup in scene.affinity_popups], [SpellAffinity.RESIST])

    def test_hidden_and_rear_grounded_members_remain_targets(self):
        scene, actor = self.scene()
        scene.defending_party_indexes = set()
        scene.hidden_party_indexes.add(0)
        scene.party[1].formation_row = FormationRow.BACK
        scene._party_draw_position = Mock(return_value=None)
        self.begin(scene, actor)
        self.assertEqual(tuple(r.target_index for r in scene.action_presentation.party_damage_results), (0, 1))
        scene._apply_action_results(scene.action_presentation)
        self.assertTrue(all(m.stunned for m in scene.party))

    def test_fairy_miss_after_shake_preserves_hp_conditions_and_pose(self):
        scene, actor = self.scene()
        member = scene.party[0]
        member.definition = replace(member.definition, race=Race.FAIRY)
        member.sleeping = 2
        member.confused = 2
        hp = member.hp
        scene.defending_party_indexes = set()
        scene.focused_target_by_party_index = {0: 0}
        with patch("scenes.battle.random.randint", return_value=0), patch("scenes.battle.play_se"):
            self.assertTrue(scene._begin_monster_earthquake(actor))
            presentation = scene.action_presentation
            self.assertEqual(scene.spell_damage_popups, [])
            for _ in range(EARTHQUAKE_SHAKE_FRAME_COUNT):
                scene._update_action_presentation()
        self.assertEqual(member.hp, hp)
        self.assertEqual((member.sleeping, member.confused), (2, 2))
        self.assertFalse(member.stunned)
        self.assertEqual(scene.focused_target_by_party_index[0], 0)
        self.assertTrue(scene.spell_damage_popups[0].is_miss)
        self.assertFalse(scene.spell_damage_popups[1].is_miss)
        self.assertFalse(presentation.party_damage_motion_visible(0))
        self.assertTrue(presentation.party_damage_motion_visible(1))

    def test_dead_and_escaped_members_are_excluded_and_no_targets_skips(self):
        for condition in ("dead", "escaped"):
            scene, actor = self.scene()
            scene.defending_party_indexes = set()
            if condition == "dead":
                scene.party[1].defeat()
            else:
                scene.escaped_party_indexes.add(1)
            with patch("scenes.battle.random.randint", return_value=0), patch("scenes.battle.play_se"):
                self.assertTrue(scene._begin_monster_earthquake(actor))
            self.assertEqual(len(scene.action_presentation.party_damage_results), 1)
        scene, actor = self.scene()
        for member in scene.party:
            member.defeat()
        with patch("scenes.battle.play_se") as sound:
            self.assertFalse(scene._begin_monster_earthquake(actor))
        sound.assert_not_called()

    def test_lethal_damage_does_not_stun_a_dead_target(self):
        scene, actor = self.scene()
        scene.defending_party_indexes = set()
        for member in scene.party:
            member.hp = 1
        self.begin(scene, actor)
        scene._apply_action_results(scene.action_presentation)
        self.assertTrue(all(m.hp == 0 and not m.stunned for m in scene.party))

    def test_shake_composes_with_game_camera_and_draw_does_not_advance(self):
        scene, actor = self.scene()
        scene.defending_party_indexes = set()
        self.begin(scene, actor)
        scene.action_presentation.shake_offset = (2, -2)
        scene.draw = Mock()
        game = Game.__new__(Game)
        game.alert = Mock(camera_x=1)
        game.battle_scene = scene
        with patch("game.pyxel.camera") as camera, patch("game.pyxel.cls"):
            game.draw()
            game.draw()
        self.assertEqual(camera.call_args_list, [call(3, -2), call(), call(3, -2), call()])
        self.assertEqual(scene.action_presentation.elapsed_frame, 0)
        self.assertEqual(scene.screen_shake_offset, (2, -2))


class EarthquakeForecastTest(AutoBattleFixtures, unittest.TestCase):
    def test_forecast_has_guaranteed_physical_damage_and_ordinary_stun(self):
        enemy = self.enemy(front=False, attack=96,
                           special_actions=(MonsterSpecialAction.POWER_HIT, MonsterSpecialAction.EARTHQUAKE))
        ally = replace(self.specs[0], hp=100, max_hp=100, defense=10, evasion=1000, hidden=True, floating=False)
        immune = replace(self.specs[1], hp=100, max_hp=100, defense=10,
                         resistances=frozenset((ResistanceType.STUN,)), floating=False)
        forecast = BattleForecast(self.snapshot(ally, immune, enemy), 0)
        forecast.roll = lambda actor, target, purpose: 0.99 if purpose == 2 else 0.0
        forecast.enemy_turn(forecast.actors[5])
        expected = resolve_earthquake_attack(attack=96, hit=100, target_defense=10, hit_roll=99).damage
        self.assertEqual(forecast.actors[0].hp, 100 - expected)
        self.assertTrue(forecast.actors[0].stunned)
        self.assertFalse(forecast.actors[1].stunned)

    def test_member_snapshot_and_forecast_keep_fairies_immune_to_damage_and_stun(self):
        fairy = self.specs[0]
        self.assertTrue(fairy.floating)
        grounded = replace(self.specs[1], floating=False, hp=100, max_hp=100, defense=10)
        enemy = self.enemy(front=False, attack=96,
                           special_actions=(MonsterSpecialAction.EARTHQUAKE,))
        forecast = BattleForecast(self.snapshot(fairy, grounded, enemy), 0)
        forecast.roll = lambda *args: 0.0
        forecast.actors[0].sleeping = 2
        forecast.actors[0].focus = 5
        forecast.enemy_turn(forecast.actors[5])
        self.assertEqual(forecast.actors[0].hp, fairy.hp)
        self.assertEqual(forecast.actors[0].sleeping, 2)
        self.assertEqual(forecast.actors[0].focus, 5)
        self.assertFalse(forecast.actors[0].stunned)
        self.assertLess(forecast.actors[1].hp, 100)
        self.assertTrue(forecast.actors[1].stunned)


if __name__ == "__main__":
    unittest.main()
