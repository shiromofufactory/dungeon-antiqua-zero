from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import load_mock_items, load_mock_skills

from auto_battle_model import AutoAction
from auto_battle_simulation import BattleForecast
from battle_commands import BattleCommand
from battle_magic import spell_reflection_chance
from member import EquipmentSlot
from monster import MonsterSpecialAction
from monster_ai import MonsterAction
from resources import load_record_array
from scenes.battle import BattleCharacter, BattleMonster, BattleScene
from spell_effect import SPELL_REFLECT_EFFECT_KEY, load_spell_effects
from tests.test_auto_battle import AutoBattleFixtures
from tests.test_battle_monster_spells import spell_scene, spellcaster


class SpellReflectionSceneTest(unittest.TestCase):
    def make_scene(self, actor):
        scene = spell_scene(actor)
        scene.active_party_index = None
        scene.defending_party_indexes = set()
        scene.spell_effects = load_spell_effects(APP_ROOT / "effects" / "spells.json")
        scene.spell_effect_renderer = Mock()
        scene._monster_base_position = Mock(return_value=(64, 64))
        scene._monster_draw_x = Mock(return_value=64)
        scene._release_palette_variant = Mock()
        scene._sync_unselectable_target_palette = Mock()
        scene._complete_current_turn = Mock()
        scene.timeline = (actor,)
        scene.target_cursor = Mock()
        scene.party_target_cursor = None
        scene._refresh_monster_name_colors = Mock()
        return scene

    def grant_reflect(self, scene, *indexes):
        skill = load_mock_skills()["Reflect"]
        for index in indexes:
            scene.party[index].skills = [skill]
            scene.defending_party_indexes.add(index)

    def test_group_spell_reflects_each_target_independently_with_one_caster_result(self):
        actor = spellcaster(magic=15, spell_key="SPARK")
        actor.state.max_hp = actor.state.hp = 200
        scene = self.make_scene(actor)
        self.grant_reflect(scene, 0, 1)
        party_hp = tuple(member.hp for member in scene.party)
        spell = scene.spells["SPARK"]

        with patch("scenes.battle.play_se") as sound:
            self.assertTrue(scene._begin_monster_spell(actor, spell))
            presentation = scene.action_presentation
            mirrors = presentation.spell_effects[:2]
            self.assertEqual(
                [(effect.target_side, effect.target_index, effect.start_frame)
                 for effect in mirrors],
                [("ally", 0, 0), ("ally", 1, 0)],
            )
            definition = mirrors[0].player.definition
            self.assertEqual(definition.spell_key, SPELL_REFLECT_EFFECT_KEY)
            self.assertEqual((definition.row, definition.frame_count, definition.total_frames), (9, 5, 10))
            returned = presentation.spell_effects[2]
            self.assertEqual((returned.target_side, returned.target_index), ("enemy", 0))
            result, = presentation.damage_results
            self.assertGreater(result.damage, 0)
            self.assertEqual(presentation.party_damage_results, ())
            self.assertEqual(actor.state.mp, actor.state.max_mp - spell.mp)

            impact = presentation.target_result_frames["enemy", 0]
            for _ in range(impact - 1):
                scene._update_action_presentation()
            self.assertEqual(actor.state.hp, actor.state.max_hp)
            scene._update_action_presentation()
            self.assertEqual(actor.state.hp, actor.state.max_hp - result.damage)
            self.assertEqual(tuple(member.hp for member in scene.party), party_hp)
            self.assertEqual(len(scene.spell_damage_popups), 1)
            self.assertEqual([call.args[0] for call in sound.call_args_list], ["spell_reflect", "spell_spark"])

    def test_direct_and_returned_results_can_share_a_target_index(self):
        actor = spellcaster(magic=15, spell_key="SPARK")
        actor.state.max_hp = actor.state.hp = 200
        scene = self.make_scene(actor)
        self.grant_reflect(scene, 1)
        hp_before = tuple(member.hp for member in scene.party)

        with patch("scenes.battle.play_se"):
            scene._begin_monster_spell(actor, scene.spells["SPARK"])
            presentation = scene.action_presentation
            direct = presentation.target_result_frames["ally", 0]
            returned = presentation.target_result_frames["enemy", 0]
            self.assertLess(direct, returned)
            for _ in range(direct):
                scene._update_action_presentation()
            self.assertLess(scene.party[0].hp, hp_before[0])
            self.assertEqual(actor.state.hp, actor.state.max_hp)
            for _ in range(returned - direct):
                scene._update_action_presentation()
            self.assertLess(actor.state.hp, actor.state.max_hp)
            self.assertEqual(scene.party[1].hp, hp_before[1])

    def test_mirror_monster_uses_defend_and_returns_party_status_spell(self):
        record = next(row for row in load_record_array("monsters.json") if row["name_en"] == "ティエンルン")
        actor = BattleMonster.from_record(record, is_front_row=True)
        scene = self.make_scene(actor)
        scene.command_window = Mock()
        scene.monster_attack_target_index = None
        scene.monster_blink_frames_remaining = 0
        scene._show_monster_action_message = Mock()
        self.assertIn(MonsterSpecialAction.MIRROR, actor.special_actions)

        with patch("monster_ai.random.choice", return_value=MonsterAction.DEFEND) as choose:
            scene._update_monster_action()
        self.assertIn(MonsterAction.DEFEND, choose.call_args.args[0])
        self.assertTrue(actor.state.is_defending)
        self.assertEqual(actor.state.mp, actor.state.max_mp)
        scene._show_monster_action_message.assert_called_once_with("battle.command.defend")

        scene.active_party_index = 0
        scene.action_targets_enemy = True
        scene.action_targets_all = True
        scene.selectable_target_indexes = (0,)
        with patch("scenes.battle.play_se"), patch("scenes.battle.random.randint", return_value=2):
            scene._begin_action_presentation(scene.spells["SLEEP"])
            presentation = scene.action_presentation
            self.assertFalse(presentation.sleep_results)
            self.assertTrue(presentation.party_sleep_results[0].success)
            for _ in range(presentation.target_result_frames["ally", 0]):
                scene._update_action_presentation()
        self.assertEqual(scene.party[0].sleeping, 2)
        self.assertEqual(actor.state.sleeping, 0)
        actor.state.apply_sleep(2)
        self.assertFalse(scene._reflects_spell("enemy", 0))

    def test_equipment_reflection_uses_da2_chance_and_skill_needs_defense(self):
        scene = self.make_scene(spellcaster(magic=10, spell_key="FIRE1"))
        self.grant_reflect(scene, 0)
        scene.defending_party_indexes.clear()
        self.assertFalse(scene._reflects_spell("ally", 0))
        member = scene.party[0]
        member.equipment = member.equipment.replaced({
            EquipmentSlot.LEFT: load_mock_items()["MIRROR SHIELD"],
        })
        with patch("scenes.battle.random.randrange", side_effect=(0, 1)):
            self.assertTrue(scene._reflects_spell("ally", 0))
            self.assertFalse(scene._reflects_spell("ally", 0))
        self.assertEqual(spell_reflection_chance(
            defending=True, has_reflect=False, equipment_reflects=True,
        ), 2)

    def test_reflected_cast_can_defeat_the_member_and_a_direct_target(self):
        reflector = spellcaster(magic=10, spell_key="FIRE1")
        reflector.state.defending = True
        direct_target = spellcaster(magic=10, spell_key="FIRE1")
        direct_target.state.hp = 1
        scene = self.make_scene(reflector)
        scene.monsters = (reflector, direct_target)
        caster = scene.party[0]
        caster.hp = 1
        caster_visual = BattleCharacter(caster, 0, 0, 0)
        scene.timeline = (caster_visual, reflector, direct_target)
        scene.active_party_index = scene.action_party_index = 0
        scene.action_targets_enemy = scene.action_targets_all = True
        scene.selectable_target_indexes = (0, 1)
        scene._begin_action_return = Mock()
        scene._begin_monster_deaths = Mock()
        scene._clear_turn_state = Mock()
        scene._start_timeline_removal_animation = Mock()
        scene._start_timeline_animation = Mock()

        with patch("scenes.battle.play_se"):
            scene._begin_action_presentation(scene.spells["SPARK"])
            for _ in range(150):
                if scene.action_presentation is None:
                    break
                scene._update_action_presentation()

        self.assertEqual(caster.hp, 0)
        self.assertFalse(direct_target.is_alive)
        self.assertTrue(reflector.is_alive)
        scene._begin_action_return.assert_not_called()
        scene._begin_monster_deaths.assert_called_once_with([1])
        BattleScene._complete_current_turn(scene)
        scene._start_timeline_removal_animation.assert_called_once_with()
        scene._start_timeline_animation.assert_not_called()

    def test_reflected_lethal_spell_removes_the_monster_timeline_head(self):
        actor = spellcaster(magic=80, spell_key="SPARK")
        actor.state.hp = 1
        scene = self.make_scene(actor)
        self.grant_reflect(scene, 0, 1)
        scene._begin_monster_deaths = Mock()

        with patch("scenes.battle.play_se"):
            scene._begin_monster_spell(actor, scene.spells["SPARK"])
            for _ in range(100):
                if scene.action_presentation is None:
                    break
                scene._update_action_presentation()
        scene._begin_monster_deaths.assert_called_once_with([0], from_timeline_head=True)
        scene._complete_current_turn.assert_not_called()


class SpellReflectionForecastTest(AutoBattleFixtures, unittest.TestCase):
    def test_forecast_reflects_in_both_directions(self):
        spark = self.spells["SPARK"]
        ally = replace(self.specs[0], skills=frozenset(("Reflect",)), defending=True)
        monster = self.enemy(
            special_actions=(MonsterSpecialAction.MIRROR,),
            defending=True, spells=(spark,), magic=20, mp=20, max_mp=20,
        )
        forecast = BattleForecast(self.snapshot(ally, monster), 0)
        party = forecast.actors[0]
        enemy = forecast.actors[5]
        forecast.cast(party, AutoAction(BattleCommand.SPELL, (5,), spell_key="SPARK"))
        self.assertLess(party.hp, party.max_hp)
        self.assertEqual(enemy.hp, enemy.max_hp)

        forecast = BattleForecast(self.snapshot(ally, monster, active=5, gauges=((5, 64), (0, 54))), 0)
        party = forecast.actors[0]
        enemy = forecast.actors[5]
        with patch.object(forecast, "roll", return_value=0.25):
            forecast.enemy_turn(enemy)
        self.assertLess(enemy.hp, enemy.max_hp)
        self.assertEqual(party.hp, party.max_hp)

    def test_mirror_defense_halves_physical_damage(self):
        ally = self.specs[0]
        monster = self.enemy(special_actions=(MonsterSpecialAction.MIRROR,))
        forecast = BattleForecast(self.snapshot(ally, monster), 0)
        enemy = forecast.actors[5]
        actor = forecast.actors[0]
        action = AutoAction(BattleCommand.ATTACK, (5,))
        with patch.object(forecast, "roll", return_value=0.0):
            unguarded = forecast.physical_results(actor, enemy, action)[0]
            enemy.defending = True
            guarded = forecast.physical_results(actor, enemy, action)[0]
        self.assertGreater(unguarded.damage, 0)
        self.assertEqual(guarded.damage, unguarded.damage // 2)

    def test_forecast_mirror_guard_ends_at_the_monsters_next_turn(self):
        ally = self.specs[0]
        monster = self.enemy(special_actions=(MonsterSpecialAction.MIRROR,))
        forecast = BattleForecast(self.snapshot(ally, monster, active=5, gauges=((5, 64), (0, 54))), 0)
        enemy = forecast.actors[5]
        with patch.object(forecast, "roll", return_value=0.95):
            forecast.enemy_turn(enemy)
        self.assertTrue(enemy.is_defending)
        forecast.prepare_turn(enemy)
        self.assertFalse(enemy.is_defending)


if __name__ == "__main__":
    unittest.main()
