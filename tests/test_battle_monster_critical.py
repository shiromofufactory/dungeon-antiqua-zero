from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT  # noqa: F401
from resources import load_record_array
from scenes.battle import BattleMonster, BattlePhase, BattleScene
from state import Settings


class MonsterCriticalPresentationTest(unittest.TestCase):
    def scene(self):
        record = next(r for r in load_record_array("monsters.json") if r["name_en"] == "Behemoth")
        actor = BattleMonster.from_record(record, is_front_row=True)
        scene = BattleScene.__new__(BattleScene)
        scene.monsters = (actor,)
        scene.party = (SimpleNamespace(
            hp=100, sleeping=0, battle_stats=SimpleNamespace(defense=10, evasion=0),
        ),)
        scene.defending_party_indexes = {0}
        scene.settings = Settings()
        scene.phase = BattlePhase.MONSTER_ACTION
        scene.monster_attack_target_index = None
        scene._monster_attack_target_indexes = Mock(return_value=(0,))
        scene._monster_charge_target_indexes = Mock(return_value=(0,))
        scene._covering_member_index = Mock(return_value=0)
        scene._party_draw_position = Mock(return_value=(156, 64))
        scene._show_monster_action_message = Mock()
        scene._apply_monster_attack_damage = Mock()
        scene._apply_additional_effects_to_member = Mock()
        return scene, actor

    def begin(self, scene, actor, mode, hit_roll):
        with patch("scenes.battle.random.randint", side_effect=(hit_roll, 0)), \
                patch("scenes.battle.play_se") as sound:
            if mode == "charge":
                scene._begin_monster_charge(actor)
                presentation = scene.monster_charge_presentation
                presentation.elapsed_frame = presentation.approach_frame_count - 1
                scene._update_monster_charge()
            else:
                scene._begin_standard_monster_attack(
                    actor, **({"target_indexes": (0,)} if mode == "counter" else {}),
                )
        return sound

    def test_guarded_critical_roll_shows_miss_without_flash_smash_or_sound(self):
        for mode in ("normal", "counter", "charge"):
            with self.subTest(mode=mode):
                scene, actor = self.scene()
                sound = self.begin(scene, actor, mode, hit_roll=76)
                self.assertEqual(scene.monster_attack_damage, 0)
                self.assertFalse(scene.monster_attack_critical)
                self.assertFalse(scene._critical_flash_visible())
                sound.assert_not_called()
                scene.settings = Settings(screen_flash_enabled=False)
                with patch("scenes.battle.pyxel.blt") as blt:
                    scene._draw_critical_markers()
                blt.assert_not_called()

    def test_successful_critical_at_guard_threshold_keeps_flash_smash_and_sound(self):
        for mode in ("normal", "counter", "charge"):
            with self.subTest(mode=mode):
                scene, actor = self.scene()
                sound = self.begin(scene, actor, mode, hit_roll=75)
                self.assertGreater(scene.monster_attack_damage, 0)
                self.assertTrue(scene.monster_attack_critical)
                self.assertTrue(scene._critical_flash_visible())
                sound.assert_called_once_with("battle_hit")
                scene.settings = Settings(screen_flash_enabled=False)
                with patch("scenes.battle.pyxel.blt") as blt:
                    scene._draw_critical_markers()
                blt.assert_called_once()

    def test_zero_damage_never_displays_critical_even_if_raw_flag_remains(self):
        scene, _ = self.scene()
        scene.monster_attack_target_index = 0
        scene.monster_attack_damage = 0
        scene.monster_attack_critical = True
        scene.monster_attack_animation_frame = 0
        self.assertFalse(scene._critical_flash_visible())
        scene.settings = Settings(screen_flash_enabled=False)
        with patch("scenes.battle.pyxel.blt") as blt:
            scene._draw_critical_markers()
        blt.assert_not_called()

    def test_zero_damage_from_defense_has_no_critical_presentation_or_sound(self):
        for mode in ("normal", "counter", "charge"):
            with self.subTest(mode=mode):
                scene, actor = self.scene()
                scene.defending_party_indexes = set()
                scene.party[0].battle_stats.defense = 100
                sound = self.begin(scene, actor, mode, hit_roll=0)
                self.assertEqual(scene.monster_attack_damage, 0)
                self.assertFalse(scene.monster_attack_critical)
                self.assertFalse(scene._critical_flash_visible())
                sound.assert_not_called()


if __name__ == "__main__":
    unittest.main()
