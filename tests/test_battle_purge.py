from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import load_mock_skills

from auto_battle_simulation import BattleForecast
from battle_commands import BattleCommand
from battle_magic import MAGIC_SHIELD_ATTRIBUTES, SpellAffinity
from monster_ai import MonsterSpellAction
from resources import load_record_array
from scenes.battle import BattleMonster
from spell_effect import load_spell_effects
from tests.test_auto_battle import AutoBattleFixtures
from tests.test_battle_monster_spells import spell_scene


class PurgeSceneTest(unittest.TestCase):
    def setUp(self):
        record = next(
            record for record in load_record_array("monsters.json")
            if record["name_en"] == "ティエンルン"
        )
        self.actor = BattleMonster.from_record(record, is_front_row=True)
        self.scene = spell_scene(self.actor)
        self.scene.spell_effects = load_spell_effects(APP_ROOT / "effects" / "spells.json")
        self.scene.spell_effect_renderer = Mock()
        self.scene._monster_base_position = Mock(return_value=(64, 64))
        self.scene._monster_draw_x = Mock(return_value=64)
        self.scene._complete_current_turn = Mock()
        self.scene.active_party_index = None
        self.scene.target_cursor = Mock()
        self.scene.party_target_cursor = None
        self.scene._refresh_monster_name_colors = Mock()

    def test_tianlung_only_considers_purge_with_visible_dispellable_buffs(self):
        scene, actor = self.scene, self.actor
        spell = scene.spells["PURGE"]
        self.assertIn(spell.key, actor.spell_keys)
        scene.party[0].apply_slow(4)
        self.assertEqual(scene._targetable_monster_spell_keys(actor), ())
        scene.party[1].magic_shield = True
        self.assertEqual(scene._targetable_monster_spell_keys(actor), ("PURGE",))
        self.assertEqual(scene._monster_spell_candidates["PURGE"].targets, (0, 1))
        scene.hidden_party_indexes.add(1)
        self.assertEqual(scene._targetable_monster_spell_keys(actor), ())
        basic_actor = replace(actor, intelligence=0)
        self.assertEqual(scene._targetable_monster_spell_keys(basic_actor), ("PURGE",))
        scene.hidden_party_indexes.clear()
        actor.state.silenced = 2
        self.assertEqual(scene._targetable_monster_spell_keys(actor), ())
        actor.state.silenced = 0
        actor.state.mp = spell.mp - 1
        self.assertEqual(scene._targetable_monster_spell_keys(actor), ())

    def test_purge_uses_existing_effect_and_applies_only_at_each_impact(self):
        scene, actor = self.scene, self.actor
        first, second = scene.party
        first.apply_protection()
        first.apply_haste()
        second.magic_shield = True
        second.apply_slow(4)
        second.apply_defense_down(3)
        second.apply_poison()
        second.apply_sleep(2)
        hp = tuple(member.hp for member in scene.party)
        spell = scene.spells["PURGE"]

        with patch("scenes.battle.play_se") as play_se:
            self.assertTrue(scene._begin_monster_spell(actor, spell))
            presentation = scene.action_presentation
            first_fx, second_fx = presentation.spell_effects
            self.assertIs(first_fx.player.definition, scene.spell_effects["PURGE"])
            self.assertIs(second_fx.player.definition, first_fx.player.definition)
            self.assertEqual(actor.state.mp, actor.state.max_mp - spell.mp)
            scene._show_spell_cast_message.assert_called_once_with(spell, actor_is_enemy=True)
            first_impact = presentation.target_result_frames["ally", 0]
            second_impact = presentation.target_result_frames["ally", 1]
            self.assertLess(first_impact, second_impact)
            for _ in range(first_impact - 1):
                scene._update_action_presentation()
            self.assertEqual((first.protection_level, first.speed_modifier), (1, 1))
            scene._update_action_presentation()
            self.assertEqual((first.protection_level, first.speed_modifier), (0, 0))
            self.assertTrue(second.magic_shield)
            for _ in range(second_impact - first_impact):
                scene._update_action_presentation()
            self.assertEqual(play_se.call_args_list, [call("spell_purge"), call("spell_purge")])

        self.assertFalse(second.magic_shield)
        self.assertEqual((second.protection_level, second.speed_modifier), (-1, -1))
        self.assertEqual((second.defense_down_turns, second.slow_turns), (3, 4))
        self.assertTrue(second.poisoned)
        self.assertEqual(second.sleeping, 2)
        self.assertEqual(tuple(member.hp for member in scene.party), hp)
        self.assertEqual(scene.spell_damage_popups, [])

    def test_reflected_purge_dispels_its_caster(self):
        scene, actor = self.scene, self.actor
        actor.state.apply_protection()
        actor.state.apply_haste()
        actor.state.magic_shield = True
        reflector, direct = scene.party
        reflector.skills = [load_mock_skills()["Reflect"]]
        reflector.apply_haste()
        direct.apply_protection()
        scene.defending_party_indexes = {0}
        with patch("scenes.battle.play_se"):
            scene._begin_monster_spell(actor, scene.spells["PURGE"])
            presentation = scene.action_presentation
            self.assertEqual(presentation.purge_targets, (("ally", 1), ("enemy", 0)))
            for _ in range(presentation.target_result_frames["enemy", 0]):
                scene._update_action_presentation()
        self.assertEqual(reflector.speed_modifier, 1)
        self.assertEqual(direct.protection_level, 0)
        self.assertEqual((actor.state.defense_modifier, actor.state.speed_modifier), (0, 0))
        self.assertFalse(actor.state.magic_shield)

    def test_magic_shield_is_castable_and_purge_removes_its_spell_resistance(self):
        scene, actor = self.scene, self.actor
        member = scene.party[0]
        scene.active_party_index = 0
        scene.action_targets_enemy = False
        scene.action_targets_all = True
        scene.selectable_party_target_indexes = (0, 1)
        fire = scene.spells["FIRE1"]
        with patch("scenes.battle.play_se"), patch("scenes.battle.random.random", return_value=0.5):
            self.assertTrue(scene._begin_action_presentation(scene.spells["MAGIC SHIELD"]))
            presentation = scene.action_presentation
            for _ in range(presentation.target_result_frames["ally", 1]):
                scene._update_action_presentation()
            self.assertTrue(MAGIC_SHIELD_ATTRIBUTES <= member.spell_resistances)
            self.assertNotEqual(member.spell_resistances, member.resistances)
            shielded, = scene._resolve_monster_spell_damage_results(actor.magic, fire, (0,))

            scene.active_party_index = None
            scene._begin_monster_spell(actor, scene.spells["PURGE"])
            presentation = scene.action_presentation
            for _ in range(presentation.target_result_frames["ally", 0]):
                scene._update_action_presentation()
            unshielded, = scene._resolve_monster_spell_damage_results(actor.magic, fire, (0,))
        self.assertIs(shielded.affinity, SpellAffinity.RESIST)
        self.assertIs(unshielded.affinity, SpellAffinity.NORMAL)
        self.assertGreater(unshielded.damage, shielded.damage)


class PurgeForecastTest(AutoBattleFixtures, unittest.TestCase):
    def test_enemy_purge_considers_magic_shield_and_preserves_debuffs(self):
        spell = self.spells["PURGE"]
        first = replace(self.specs[0], magic_shield=True, speed=-1, slow_turns=4)
        second = replace(self.specs[1], sleeping=2, protection=-1, defense_down_turns=3)
        enemy = self.enemy(spells=(spell,), intelligence=1, mp=15, max_mp=15)
        forecast = BattleForecast(self.snapshot(enemy, first, second, active=5), 0)

        with patch.object(forecast, "roll", return_value=0.0):
            forecast.enemy_turn(forecast.actors[5])
        self.assertEqual(forecast.actors[5].mp, 15 - spell.mp)
        self.assertFalse(forecast.actors[0].magic_shield)
        self.assertEqual((forecast.actors[0].speed, forecast.actors[0].slow_turns), (-1, 4))
        self.assertEqual(
            (forecast.actors[1].sleeping, forecast.actors[1].protection,
             forecast.actors[1].defense_down_turns),
            (2, -1, 3),
        )

    def test_ally_prediction_candidates_apply_shield_and_dispel(self):
        ally = self.specs[0]
        enemy = self.enemy(protection=2)
        forecast = BattleForecast(self.snapshot(ally, enemy), 0)
        active = forecast.actors[0]
        shield = self.spells["MAGIC SHIELD"]
        purge = self.spells["PURGE"]

        shield_action, = forecast.effect_candidates(active, BattleCommand.SPELL, shield)
        forecast.cast(active, shield_action)
        self.assertTrue(active.magic_shield)
        self.assertEqual(forecast.effect_candidates(active, BattleCommand.SPELL, shield), ())
        purge_action, = forecast.effect_candidates(active, BattleCommand.SPELL, purge)
        forecast.cast(active, purge_action)
        self.assertEqual(forecast.actors[5].protection, 0)
        self.assertEqual(forecast.effect_candidates(active, BattleCommand.SPELL, purge), ())


if __name__ == "__main__":
    unittest.main()
