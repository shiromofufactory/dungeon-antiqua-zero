"""Regression coverage for the monster Black Wind action."""

from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT

from auto_battle_simulation import BattleForecast
from localization import Localizer
from monster import MonsterSpecialAction
from monster_ai import MonsterAction
from rendering.palette import PaletteShifter
from resources import load_record_array
from scenes.battle import (
    BATTLE_BACKGROUND_TINT_FRAME_COUNT,
    BLACK_WIND_EFFECT_DELAY,
    BLACK_WIND_RESULT_FRAME,
    SPELL_EFFECT_FLASH_PALETTE,
    BattleMonster,
    BattlePhase,
)
from spell_effect import BLACK_WIND_EFFECT_KEY, load_spell_effects
from state import Language
from text_catalog import TextCatalog
from tests.test_auto_battle import AutoBattleFixtures
from tests.test_battle_monster_spells import spell_scene, spellcaster


class BlackWindSceneTest(unittest.TestCase):
    def setUp(self):
        record = next(
            record for record in load_record_array("monsters.json")
            if record["name_en"] == "ニーズヘッグ"
        )
        self.actor = BattleMonster.from_record(record, is_front_row=True)
        self.scene = spell_scene(self.actor)
        self.scene.active_party_index = None
        self.scene.timeline = (self.actor,)
        self.scene.command_window = Mock()
        self.scene.monster_attack_target_index = None
        self.scene.monster_blink_frames_remaining = 0
        self.scene.progression = Mock()
        self.scene.palette_shifter = PaletteShifter([0, 0xFFFFFF], Mock())
        self.scene.spell_effect_renderer = Mock()
        self.scene.spell_effects = load_spell_effects(APP_ROOT / "effects" / "spells.json")
        self.scene._monster_base_position = Mock(side_effect=lambda index: (32 + index * 20, 40))
        self.scene._monster_draw_x = Mock(side_effect=lambda index: 32 + index * 20)
        self.scene._complete_current_turn = Mock()
        self.scene.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        self.scene.localizer = Localizer(Language.JAPANESE)
        self.scene.action_popup_window = Mock()
        self.scene.battle_popup = Mock()
        self.scene._show_battle_popup = Mock()

    def test_ai_uses_own_living_side_for_intelligence_gate(self):
        scene = self.scene
        self.assertIn(MonsterSpecialAction.BLACK_WIND, self.actor.special_actions)
        dead = spellcaster(magic=0, spell_key="FIRE1")
        dead.state.poisoned = True
        dead.state.defeat()
        scene.party[0].poisoned = True
        for intelligence, afflicted, eligible in ((0, False, True), (1, False, False), (1, True, True)):
            with self.subTest(intelligence=intelligence, afflicted=afflicted):
                actor = replace(self.actor, intelligence=intelligence)
                scene.monsters = (actor, dead)
                actor.state.silenced = 3 if afflicted else 0
                with patch("monster_ai.random.choice", side_effect=lambda options: options[0]) as choose:
                    scene._select_monster_action(actor)
                self.assertEqual(MonsterAction.BLACK_WIND in choose.call_args.args[0], eligible)

    def test_rotation_skips_black_wind_without_a_curable_condition(self):
        actor = replace(self.actor, intelligence=3)
        self.scene.monsters = (actor,)
        actor.state.action_rotation_index = 1  # Poison Breath, Black Wind, Attack.
        actor.state.stunned = True
        self.assertIs(self.scene._select_monster_action(actor), MonsterAction.ATTACK)
        self.assertEqual(actor.state.action_rotation_index, 0)
        actor.state.action_rotation_index = 1
        actor.state.apply_slow(4)
        self.assertIs(self.scene._select_monster_action(actor), MonsterAction.BLACK_WIND)
        self.assertEqual(actor.state.action_rotation_index, 2)

    def test_turn_cures_only_affected_monsters_at_impact_and_restores_background(self):
        scene, actor = self.scene, self.actor
        sleeper, confused, unaffected, dead = (
            spellcaster(magic=0, spell_key="FIRE1") for _ in range(4)
        )
        scene.monsters = (actor, sleeper, confused, unaffected, dead)
        actor.state.silenced = 1
        actor.state.apply_slow(4)
        actor.state.apply_protection()
        sleeper.state.apply_sleep(3)
        sleeper.state.apply_defense_down(4)
        confused.state.apply_confusion(3)
        confused.state.apply_poison()
        unaffected.state.apply_haste()
        unaffected.state.apply_stun()
        dead.state.apply_poison()
        dead.state.defeat()
        scene.party[0].poisoned = True
        actor.state.hp -= 10
        hp_mp = actor.state.hp, actor.state.mp

        with (
            patch("monster_ai.random.choice", return_value=MonsterAction.BLACK_WIND),
            patch("scenes.battle.play_se") as sound,
        ):
            scene._update_monster_action()
            scene.progression.record_enemy_action.assert_called_once_with(0)
            self.assertIs(scene.phase, BattlePhase.ACTION_PRESENTATION)
            presentation = scene.action_presentation
            self.assertEqual(presentation.black_wind_targets, (0, 1, 2))
            definition = presentation.spell_effects[0].player.definition
            self.assertEqual(
                (definition.spell_key, definition.image_id, definition.row,
                 definition.frame_count, definition.frames_per_pattern, definition.enemy_offset_y),
                (BLACK_WIND_EFFECT_KEY, "effects/spells32", 2, 5, 4, 16),
            )
            self.assertEqual(
                [effect.start_frame for effect in presentation.spell_effects],
                [BLACK_WIND_EFFECT_DELAY] * 3,
            )
            scene._show_battle_popup.assert_called_once_with(
                "ニーズヘッグは　くろいかぜを　まきおこした",
                BLACK_WIND_RESULT_FRAME, align_left=True,
            )
            for _ in range(BLACK_WIND_EFFECT_DELAY - 1):
                scene._update_action_presentation()
            sound.assert_not_called()
            scene._update_action_presentation()
            sound.assert_called_once_with("battle_black_wind")
            for _ in range(BATTLE_BACKGROUND_TINT_FRAME_COUNT - BLACK_WIND_EFFECT_DELAY):
                scene._update_action_presentation()
            tint = scene.palette_shifter._variants[SPELL_EFFECT_FLASH_PALETTE]
            self.assertEqual(tint.colors[1], 0x656565)
            for _ in range(BLACK_WIND_RESULT_FRAME - BATTLE_BACKGROUND_TINT_FRAME_COUNT - 1):
                scene._update_action_presentation()
            self.assertTrue(sleeper.state.sleeping)
            self.assertTrue(confused.state.confused)
            self.assertTrue(actor.state.silenced)
            scene._update_action_presentation()
            self.assertFalse(any(
                monster.state.can_recover_with_black_wind
                for monster in (actor, sleeper, confused)
            ))
            self.assertEqual(actor.state.slow_turns, 0)
            self.assertEqual(sleeper.state.defense_down_turns, 0)
            self.assertEqual(actor.state.defense_modifier, 1)
            self.assertEqual(unaffected.state.speed_modifier, 1)
            self.assertTrue(unaffected.state.stunned)
            self.assertTrue(dead.state.poisoned)
            self.assertTrue(scene.party[0].poisoned)
            self.assertEqual((actor.state.hp, actor.state.mp), hp_mp)
            scene._complete_current_turn.assert_not_called()
            for _ in range(BATTLE_BACKGROUND_TINT_FRAME_COUNT):
                scene._update_action_presentation()
            sound.assert_called_once_with("battle_black_wind")
        scene._complete_current_turn.assert_called_once_with()
        self.assertNotIn(SPELL_EFFECT_FLASH_PALETTE, scene.palette_shifter._variants)

    def test_healthy_intelligence_zero_use_has_no_target_sprite_or_sound(self):
        scene = self.scene
        with (
            patch("monster_ai.random.choice", return_value=MonsterAction.BLACK_WIND),
            patch("scenes.battle.play_se") as sound,
        ):
            scene._update_monster_action()
            self.assertEqual(scene.action_presentation.spell_effects, ())
            for _ in range(BLACK_WIND_RESULT_FRAME + BATTLE_BACKGROUND_TINT_FRAME_COUNT):
                scene._update_action_presentation()
            sound.assert_not_called()
        scene._complete_current_turn.assert_called_once_with()
        self.assertNotIn(SPELL_EFFECT_FLASH_PALETTE, scene.palette_shifter._variants)


class BlackWindForecastTest(AutoBattleFixtures, unittest.TestCase):
    def test_forecast_uses_intelligence_gate_and_cures_enemy_conditions(self):
        ally = replace(self.specs[0], poisoned=True)
        for intelligence, afflicted, uses_wind in ((0, False, True), (1, False, False), (1, True, True)):
            with self.subTest(intelligence=intelligence, afflicted=afflicted):
                caster = self.enemy(
                    intelligence=intelligence, speed=-1 if afflicted else 0, slow_turns=4 if afflicted else 0,
                    special_actions=(MonsterSpecialAction.BLACK_WIND,),
                )
                companion = self.enemy(
                    6, sleeping=3 if afflicted else 0, protection=1,
                )
                forecast = BattleForecast(
                    self.snapshot(caster, companion, ally, active=5), 0,
                )
                with (
                    patch.object(forecast, "roll", return_value=0.99),
                    patch.object(forecast, "enemy_attack", return_value=None) as attack,
                ):
                    forecast.enemy_turn(forecast.actors[5])
                self.assertEqual(attack.called, not uses_wind)
                self.assertEqual((forecast.actors[5].speed, forecast.actors[5].slow_turns), (0, 0))
                self.assertEqual(forecast.actors[6].sleeping, 0)
                self.assertEqual(forecast.actors[6].protection, 1)
                self.assertTrue(forecast.actors[0].poisoned)


if __name__ == "__main__":
    unittest.main()
