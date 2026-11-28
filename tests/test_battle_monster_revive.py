from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT
from auto_battle_simulation import BattleForecast
from battle_layout import MonsterPlacement, monster_layout
from battle_timeline import TimelineEntry, TimelineOrder
from monster_ai import MonsterSpellAction
from resources import load_record_array
from scenes.battle import (
    MONSTER_REVIVAL_DELAY_FRAME_COUNT,
    MONSTER_REVIVAL_FADE_FRAME_COUNT,
    BattleMonster,
)
from spell_effect import load_spell_effects
from tests.test_auto_battle import AutoBattleFixtures
from tests.test_battle_monster_spells import spell_scene


class MonsterReviveSceneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = {record["name_en"]: record for record in load_record_array("monsters.json")}

    def setUp(self):
        self.hel = BattleMonster.from_record(self.records["Hel"], is_front_row=True)
        self.hel.spell_keys = ("SLEEP", "REVIVE1")
        self.fenrir = BattleMonster.from_record(self.records["Fenrir"], is_front_row=True)
        self.fenrir.state.defeat()
        self.scene = spell_scene(self.hel)
        self.scene.monsters = (self.hel, self.fenrir)
        layout = monster_layout(self.scene.monsters)
        self.scene.monster_slot_indexes = layout.slot_indexes
        self.scene.monster_positions = layout.positions
        self.scene._timeline_order = TimelineOrder((TimelineEntry(self.hel, self.hel.agility, 64),))
        self.scene.timeline = self.scene._timeline_order.actors
        self.spell = self.scene.spells["REVIVE1"]

    def test_hel_prioritizes_revival_and_skips_ineligible_targets(self):
        scene, hel, fenrir = self.scene, self.hel, self.fenrir
        self.assertEqual(scene._targetable_monster_spell_keys(hel), ("REVIVE1",))
        self.assertEqual(scene._select_monster_action(hel), MonsterSpellAction("REVIVE1"))
        hel.state.mp = self.spell.mp - 1
        self.assertNotIn("REVIVE1", scene._targetable_monster_spell_keys(hel))
        hel.state.mp = self.spell.mp
        hel.state.apply_silence(1)
        self.assertNotIn("REVIVE1", scene._targetable_monster_spell_keys(hel))
        hel.state.elapse_silence_turn()

        scene.escaped_monster_indexes = {1}
        self.assertEqual(scene._monster_spell_target_indexes(self.spell), ())
        scene.escaped_monster_indexes.clear()
        scene.monster_slot_indexes = (0, 0)
        self.assertEqual(scene._monster_spell_target_indexes(self.spell), ())
        scene.monster_slot_indexes = (0, 1)
        scene.monster_positions = ((4, 48), (4, 80))
        self.assertEqual(scene._monster_spell_target_indexes(self.spell), ())
        scene.monster_positions = ((4, 48), (4, 112))
        fenrir.state.revive(25)
        self.assertFalse(scene._begin_monster_spell(hel, self.spell))
        self.assertEqual(hel.state.mp, self.spell.mp)

    def test_effect_precedes_appearance_and_reinserts_the_same_enemy(self):
        scene, hel, fenrir = self.scene, self.hel, self.fenrir
        scene.spell_effects = load_spell_effects(APP_ROOT / "effects" / "spells.json")
        scene.spell_effect_renderer = Mock()
        scene.progression = Mock()
        scene._complete_current_turn = Mock()
        scene.target_window = Mock()
        scene._draw_monster_shadow = Mock()
        scene._draw_monster_image = Mock()
        scene._draw_identified_monster_hp = Mock()
        scene.blinking_monster_index = None
        fenrir.state.poisoned = True
        fenrir.state.action_rotation_index = 2

        with patch("scenes.battle.play_se") as play_se:
            self.assertTrue(scene._begin_monster_spell(hel, self.spell))
            presentation = scene.action_presentation
            effect, = presentation.spell_effects
            self.assertEqual((effect.target_side, effect.target_index), ("enemy", 1))
            play_se.assert_called_once_with("spell_healing1")
            self.assertEqual(hel.state.mp, hel.max_mp - self.spell.mp)
            self.assertEqual(presentation.result_start_frame, effect.player.definition.total_frames)
            for _ in range(presentation.result_start_frame - 1):
                scene._update_action_presentation()
            self.assertFalse(fenrir.is_alive)
            scene._update_action_presentation()
            self.assertEqual(fenrir.state.hp, fenrir.state.max_hp // 4)
            self.assertFalse(fenrir.state.poisoned)
            self.assertIsNone(fenrir.state.action_rotation_index)
            self.assertIs(scene.timeline[0], hel)
            self.assertIs(scene.timeline[1], fenrir)
            self.assertEqual(scene._timeline_order.entries[1].gauge, fenrir.agility)
            self.assertEqual(presentation.monster_revival_opacity(1), 0.0)
            for _ in range(MONSTER_REVIVAL_DELAY_FRAME_COUNT + MONSTER_REVIVAL_FADE_FRAME_COUNT // 2):
                scene._update_action_presentation()
            self.assertEqual(presentation.monster_revival_opacity(1), 0.5)
            with patch("scenes.battle.pyxel.dither") as dither:
                scene._draw_monsters()
            self.assertEqual(dither.call_args_list, [call(0.5), call(1.0)])
            for _ in range(MONSTER_REVIVAL_FADE_FRAME_COUNT // 2):
                scene._update_action_presentation()

        scene.progression.record_enemy_revival.assert_called_once_with(1)
        scene._complete_current_turn.assert_called_once_with()
        self.assertIsNone(scene.action_presentation)


class MonsterReviveForecastTest(AutoBattleFixtures, unittest.TestCase):
    def test_forecast_prioritizes_revival_and_excludes_escaped_or_blocked_enemies(self):
        revive = self.spells["REVIVE1"]
        caster = self.enemy(
            intelligence=2, mp=revive.mp, max_mp=revive.mp,
            spells=(self.spells["SLEEP"], revive),
            monster_placement=MonsterPlacement(0, 4, 48, 64, 64),
        )
        defeated = self.enemy(
            6, hp=0, alive=False, mp=2, max_mp=5, action_rotation_index=1,
            monster_placement=MonsterPlacement(2, 68, 16, 64, 64),
        )
        for obstacle in (None, "escaped", "slot", "silence", "mp"):
            with self.subTest(obstacle=obstacle):
                enemy = caster
                extras = ()
                if obstacle == "slot":
                    extras = (self.enemy(7, monster_placement=defeated.monster_placement),)
                if obstacle == "silence":
                    enemy = replace(caster, silenced=1)
                if obstacle == "mp":
                    enemy = replace(caster, mp=revive.mp - 1)
                forecast = BattleForecast(self.snapshot(self.specs[0], enemy, defeated, *extras), 0)
                forecast.advance(forecast.actors[0], 0)
                self.assertEqual(forecast.order.actors[0], 5)
                if obstacle == "escaped":
                    forecast.actors[6].removed = True
                forecast.roll = lambda *args: 0.0
                forecast.enemy_turn(forecast.actors[5])
                target = forecast.actors[6]
                if obstacle is None:
                    self.assertEqual(target.hp, target.max_hp // 4)
                    self.assertEqual(target.mp, 2)
                    self.assertIsNone(target.action_rotation_index)
                    self.assertIn(6, forecast.order.actors)
                    self.assertTrue(target.front)
                    self.assertFalse(forecast.actors[5].front)
                    self.assertEqual(forecast.actors[5].mp, 0)
                else:
                    self.assertEqual(target.hp, 0)
                    self.assertNotIn(6, forecast.order.actors)
