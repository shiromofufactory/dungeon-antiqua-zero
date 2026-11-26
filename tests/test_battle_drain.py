from __future__ import annotations

import json
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT  # noqa: F401
from tools.screen_mocks._fixtures import load_mock_items
from auto_battle_model import AutoAction, AutoWeapon
from auto_battle_simulation import BattleForecast
from battle_commands import BattleCommand
from battle_physical import PhysicalAttackResult, drain_healing_amount, resolve_physical_attack
from item import AdditionalEffect
from member import EquipmentSlot
from monster import MonsterSpecialAction, MonsterTribe
from monster_ai import MonsterSpellAction
from resistance import ResistanceType
from resources import load_record_array
from resources.audio import sound_effect_definition
from scenes.battle import (
    BATTLE_DRAIN_SE_ID, BATTLE_HIT_SE_ID, BattleDataError, BattleMonster, MONSTER_DRAIN_HEAL_DELAY,
)
from tests.test_auto_battle import AutoBattleFixtures
from tests.test_battle_monster_spells import spell_scene


class DrainRuleTest(unittest.TestCase):
    def test_all_shared_and_runtime_monsters_can_initialize_battle_state(self):
        for path in (APP_ROOT.parent / "content/data/monsters.json",
                     APP_ROOT / "data/monsters.json"):
            for record in json.loads(path.read_text(encoding="utf-8")):
                with self.subTest(path=path, monster=record["name_en"]):
                    BattleMonster.from_record(record, is_front_row=True)

    def test_damage_is_capped_by_missing_hp_including_overkill(self):
        for damage, hp, expected in ((0, 10, 0), (7, 10, 7), (99, 10, 10),
                                     (99, 20, 0), (99, 0, 0)):
            with self.subTest(damage=damage, hp=hp):
                self.assertEqual(
                    drain_healing_amount(damage=damage, hp=hp, max_hp=20), expected
                )

    def test_drain_se_reuses_da2_sound_51(self):
        self.assertEqual(sound_effect_definition(BATTLE_DRAIN_SE_ID).sound, 51)


class MonsterDrainTest(unittest.TestCase):
    def scene(self, *, hp=1, monster_key="ヴァンパイアバット"):
        record = next(r for r in load_record_array("monsters.json")
                      if r["name_en"] == monster_key)
        actor = BattleMonster.from_record(record, is_front_row=True)
        self.assertEqual(actor.additional_effects, (AdditionalEffect.DRAIN,))
        actor.state.hp = hp
        actor.combat_stats = replace(actor.combat_stats, attack=40, hit=100)
        scene = spell_scene(actor)
        scene.healing_popups = []
        scene.defending_party_indexes = set()
        scene._monster_attack_target_indexes = Mock(return_value=(0,))
        scene._monster_charge_target_indexes = Mock(return_value=(0,))
        scene._covering_member_index = Mock(return_value=0)
        scene._monster_base_position = Mock(return_value=(4, 56))
        scene._show_monster_action_message = Mock()
        scene._member_focus_is_interrupted = Mock(return_value=False)
        scene._reveal_hidden_party_if_all_unavailable = Mock()
        scene._party_is_defeated = Mock(return_value=False)
        scene._start_timeline_animation = Mock()
        return scene, actor

    def begin(self, scene, actor):
        with patch("scenes.battle.random.randint", return_value=0), \
             patch("scenes.battle.random.choice", return_value=0), \
             patch("scenes.battle.play_se") as sound:
            scene._begin_standard_monster_attack(actor)
        return sound

    def test_attack_recovers_hp_once(self):
        for key in ("ヴァンパイアバット", "Lesser Vampire"):
            with self.subTest(monster=key):
                scene, actor = self.scene(monster_key=key)
                sound = self.begin(scene, actor)
                damage = scene.monster_attack_damage
                amount = min(damage, actor.state.max_hp - 1)
                presentation = scene.monster_drain_presentation
                self.assertEqual(actor.state.hp, 1)
                sound.assert_called_once_with(BATTLE_DRAIN_SE_ID)
                hp = scene.party[0].hp
                scene._finish_monster_attack()
                scene._apply_monster_drain_healing()
                self.assertEqual(scene.party[0].hp, max(0, hp - damage))
                self.assertEqual(actor.state.hp, 1 + amount)
                self.assertTrue(presentation.healing_applied)

    def test_critical_hits_keep_hit_or_drain_sound_for_every_monster_attack_path(self):
        for mode in ("attack", "charge", "confused"):
            for extra, full_hp, expected_healing in (
                ((), False, 0),
                ((AdditionalEffect.DRAIN,), False, 7),
                ((AdditionalEffect.DRAIN,), True, 0),
            ):
                with self.subTest(mode=mode, extra=extra, full_hp=full_hp):
                    scene, actor = self.scene()
                    actor.additional_effects = extra
                    if full_hp:
                        actor.state.hp = actor.state.max_hp
                    starting_hp = actor.state.hp
                    scene.monsters = (actor,)
                    result = PhysicalAttackResult(True, 7, 100.0, 100.0, critical=True)
                    with patch("scenes.battle.resolve_physical_attack", return_value=result), \
                         patch("scenes.battle.random.choice", side_effect=lambda indexes: indexes[0]), \
                         patch("scenes.battle.play_se") as sound:
                        if mode == "attack":
                            scene._begin_standard_monster_attack(actor)
                            scene._finish_monster_attack()
                        elif mode == "charge":
                            scene._begin_monster_charge(actor)
                            presentation = scene.monster_charge_presentation
                            for _ in range(presentation.approach_frame_count - 1):
                                scene._update_monster_charge()
                            sound.assert_not_called()
                            scene._update_monster_charge()
                            scene._update_monster_charge()
                        else:
                            target = replace(actor, state=replace(actor.state, hp=20))
                            scene.monsters = (actor, target)
                            scene._monster_draw_x = Mock(return_value=4)
                            scene._begin_confused_monster_action(actor)
                            self.assertTrue(scene.action_presentation.confused_attack_results[0].is_critical)
                            scene._apply_action_results(scene.action_presentation)
                            scene._apply_action_results(scene.action_presentation)
                        sound.assert_called_once_with(
                            BATTLE_DRAIN_SE_ID if expected_healing else BATTLE_HIT_SE_ID
                        )
                    self.assertEqual(actor.state.hp, starting_hp + expected_healing)

    def test_full_hp_uses_hit_sound_and_omits_flight_and_recovery(self):
        scene, actor = self.scene()
        actor.state.hp = actor.state.max_hp
        sound = self.begin(scene, actor)
        sound.assert_called_once_with(BATTLE_HIT_SE_ID)
        self.assertIsNone(getattr(scene, "monster_drain_presentation", None))
        scene._finish_monster_attack()
        self.assertEqual(actor.state.hp, actor.state.max_hp)
        self.assertEqual(scene.healing_popups, [])

    def test_matching_tribe_blocks_drain_from_a_damaging_hit(self):
        for charged in (False, True):
            with self.subTest(charged=charged):
                scene, actor = self.scene()
                actor.tribe = MonsterTribe.GIANT
                scene.monsters = (actor,)
                target = scene.party[0]
                target.equipment = target.equipment.replaced({
                    EquipmentSlot.RIGHT: load_mock_items()["ONIGOROSHI"],
                })
                hp = target.hp
                scene.affinity_popups = []
                with patch("scenes.battle.random.randint", return_value=0), \
                     patch("scenes.battle.play_se") as sound:
                    if charged:
                        scene._begin_monster_charge(actor)
                        for _ in range(scene.monster_charge_presentation.approach_frame_count):
                            scene._update_monster_charge()
                    else:
                        scene._begin_standard_monster_attack(actor)
                        scene._finish_monster_attack()
                self.assertLess(target.hp, hp)
                self.assertIsNone(getattr(scene, "monster_drain_presentation", None))
                self.assertEqual(actor.state.hp, 1)
                sound.assert_called_once_with(BATTLE_HIT_SE_ID)

    def test_miss_never_drains_or_plays_hit_sound(self):
        scene, actor = self.scene()
        actor.combat_stats = replace(actor.combat_stats, hit=0)
        with patch("scenes.battle.random.randint", return_value=99), \
             patch("scenes.battle.random.choice", return_value=0), \
             patch("scenes.battle.play_se") as sound:
            scene._begin_standard_monster_attack(actor)
        self.assertEqual(scene.monster_attack_damage, 0)
        self.assertIsNone(getattr(scene, "monster_drain_presentation", None))
        scene._finish_monster_attack()
        self.assertEqual(actor.state.hp, 1)
        sound.assert_not_called()

    def test_cover_uses_coverer_anchor_and_guard_reduced_damage(self):
        scene, actor = self.scene()
        scene._covering_member_index.return_value = 1
        scene.defending_party_indexes = {1}
        self.begin(scene, actor)
        self.assertEqual(scene.monster_attack_target_index, 1)
        presentation = scene.monster_drain_presentation
        self.assertEqual((presentation.start_x, presentation.start_y), (202, 108))
        self.assertEqual(presentation.amount, min(scene.monster_attack_damage,
                                                actor.state.max_hp - 1))

    def test_lethal_attack_recovers_resolved_damage_without_target_hp_cap(self):
        scene, actor = self.scene()
        scene.party[0].hp = 1
        scene._remove_defeated_party_from_timeline = Mock()
        scene._prune_surprise_pending_party = Mock(return_value=False)
        scene._begin_front_promotion_if_needed = Mock(return_value=False)
        self.begin(scene, actor)
        damage = scene.monster_attack_damage
        self.assertGreater(damage, 1)
        scene._finish_monster_attack()
        self.assertEqual(scene.party[0].hp, 0)
        self.assertEqual(actor.state.hp, min(actor.state.max_hp, 1 + damage))

    def test_flight_patterns_size_bank_and_delayed_number_match_da2(self):
        scene, actor = self.scene()
        self.begin(scene, actor)
        presentation = scene.monster_drain_presentation
        for step, pattern in enumerate((0, 1, 2, 2, 1, 0)):
            presentation.elapsed_frame = step * 2
            with patch("scenes.battle.pyxel.blt") as blt:
                scene._draw_monster_drain()
                scene._draw_monster_drain()  # draw must not advance time
            x = 202 + (36 - 202) * step / 5
            y = 80 + (96 - 80) * step / 5
            self.assertEqual(blt.call_args.args[:8],
                             (x - 12, y - 8, 0, pattern * 24, 48, 24, 16, 1))
            self.assertEqual(presentation.elapsed_frame, step * 2)
        presentation.elapsed_frame = 0
        for _ in range(MONSTER_DRAIN_HEAL_DELAY - 1):
            scene._update_monster_drain()
        self.assertEqual(scene.healing_popups, [])
        scene._update_monster_drain()
        popup = scene.healing_popups[0]
        self.assertEqual((popup.x, popup.y, popup.amount),
                         (36, 112, presentation.amount))
        scene._update_monster_drain()
        self.assertEqual(len(scene.healing_popups), 1)
        scene._apply_monster_drain_healing()
        scene._update_monster_drain()
        self.assertIsNone(scene.monster_drain_presentation)

    def test_charge_drains_at_impact_only_once(self):
        scene, actor = self.scene()
        actor.additional_effects += (AdditionalEffect.POISON,)
        with patch("scenes.battle.random.randint", return_value=0), \
             patch("scenes.battle.random.choice", return_value=0), \
             patch("scenes.battle.resolve_physical_attack", return_value=PhysicalAttackResult(
                 True, 1, 100.0, 100.0,
             )):
            scene._begin_monster_charge(actor)
        presentation = scene.monster_charge_presentation
        for _ in range(presentation.approach_frame_count - 1):
            scene._update_monster_charge()
        self.assertEqual(actor.state.hp, 1)
        with patch("scenes.battle.play_se") as sound:
            scene._update_monster_charge()
        sound.assert_called_once_with(BATTLE_DRAIN_SE_ID)
        self.assertTrue(scene.party[0].poisoned)
        recovered_hp = actor.state.hp
        self.assertEqual(recovered_hp, min(actor.state.max_hp, 1 + presentation.damage))
        for _ in range(5):
            scene._update_monster_charge()
        self.assertEqual(actor.state.hp, recovered_hp)

    def test_confused_monster_drains_from_another_monster(self):
        scene, actor = self.scene()
        target = replace(actor, state=replace(actor.state, hp=1))
        scene.monsters = (actor, target)
        scene._monster_draw_x = Mock(return_value=4)
        with patch("scenes.battle.random.randint", return_value=0), \
             patch("scenes.battle.random.choice", return_value=1):
            scene._begin_confused_monster_action(actor)
        presentation = scene.action_presentation
        with patch("scenes.battle.play_se") as sound:
            scene._apply_action_results(presentation)
            scene._apply_action_results(presentation)
        sound.assert_called_once_with(BATTLE_DRAIN_SE_ID)
        self.assertEqual(target.state.hp, 0)
        damage = presentation.confused_attack_results[0].damage
        self.assertEqual(actor.state.hp, min(actor.state.max_hp, 1 + damage))

    def test_sheet_effect_codes_apply_poison_and_confusion_after_an_attack(self):
        scene, _ = self.scene()
        record = next(r for r in load_record_array("monsters.json") if r["name_en"] == "Ean Si")
        with self.assertRaisesRegex(BattleDataError, "extra"):
            BattleMonster.from_record({**record, "extra": "毒眠幻"}, is_front_row=True)
        actor = BattleMonster.from_record({**record, "extra": "毒眠乱"}, is_front_row=True)
        scene.monsters = (actor,)
        self.assertEqual(actor.additional_effects, (
            AdditionalEffect.POISON, AdditionalEffect.SLEEP, AdditionalEffect.CONFUSE,
        ))

        hit = PhysicalAttackResult(True, 1, 100.0, 100.0)
        with patch("scenes.battle.resolve_physical_attack", return_value=hit):
            self.begin(scene, actor)
        with patch("scenes.battle.random.randint", return_value=2):
            scene._finish_monster_attack()

        self.assertTrue(scene.party[0].poisoned)
        self.assertEqual(scene.party[0].sleeping, 0)
        self.assertEqual(scene.party[0].confused, 2)


class DrainForecastTest(AutoBattleFixtures, unittest.TestCase):
    def test_party_forecast_dark_resistance_blocks_spell_hit_and_weapon_drain(self):
        spell = self.spells["BLOOD SUCK"]
        member = replace(self.specs[0], hp=1, magic=20, weapons=(AutoWeapon(
            attack=30, hit=100, attribute=ResistanceType.DARK, effect=AdditionalEffect.DRAIN,
        ),))
        for resistant in (False, True):
            resistances = frozenset({ResistanceType.DARK}) if resistant else frozenset()
            for command in (BattleCommand.ATTACK, BattleCommand.SPELL):
                with self.subTest(command=command, resistant=resistant):
                    enemy = self.enemy(resistances=resistances)
                    forecast = BattleForecast(self.snapshot(member, enemy), 0)
                    forecast.roll = Mock(return_value=0.5)
                    actor, target = forecast.actors[0], forecast.actors[5]
                    if command is BattleCommand.SPELL:
                        forecast.cast(actor, AutoAction(command, (5,), spell_key=spell.key))
                    else:
                        forecast.physical(actor, AutoAction(command, (5,)))
                    damage = enemy.hp - target.hp
                    if resistant and command is BattleCommand.SPELL:
                        self.assertEqual(damage, 0)
                    else:
                        self.assertGreater(damage, 0)
                    self.assertEqual(actor.hp, 1 if resistant else min(actor.max_hp, 1 + damage))

    def test_enemy_spell_forecast_misses_resistant_targets(self):
        spell = self.spells["BLOOD SUCK"]
        enemy = self.enemy(hp=25, mp=10, max_mp=10, magic=20, spells=(spell,))
        member = replace(self.specs[0], resistances=frozenset({ResistanceType.DARK}))
        forecast = BattleForecast(self.snapshot(enemy, member, active=5), 0)
        forecast.roll = Mock(return_value=0.5)

        with patch("auto_battle_simulation.monster_action_candidates", return_value=(MonsterSpellAction(spell.key),)):
            forecast.enemy_turn(forecast.actors[5])

        self.assertEqual(forecast.actors[0].hp, member.hp)
        self.assertEqual(forecast.actors[5].hp, enemy.hp)

    def test_forecast_recovers_for_attack_charge_and_confusion(self):
        for mode in ("attack", "charge", "confused"):
            for hp, defense in ((1, 0), (119, 0), (120, 0), (1, 100)):
                with self.subTest(mode=mode, hp=hp, defense=defense):
                    enemy = self.enemy(hp=hp,
                        additional_effects=(AdditionalEffect.DRAIN, AdditionalEffect.POISON),
                        special_actions=(MonsterSpecialAction.CHARGE,)
                        if mode == "charge" else ())
                    member = replace(self.specs[0], hp=1000, max_hp=1000,
                                     defense=defense, resistances=frozenset((ResistanceType.DARK,)))
                    other = self.enemy(6, hp=1000, max_hp=1000, defense=defense)
                    forecast = BattleForecast(self.snapshot(member, enemy, other), 0)
                    forecast.roll = Mock(side_effect=lambda _actor, _target, purpose:
                        0.99 if mode == "charge" and purpose == 0 else 0.0)
                    target = forecast.actors[6 if mode == "confused" else 0]
                    actor = forecast.actors[5]
                    expected = resolve_physical_attack(
                        attack=30 if mode == "charge" else 20,
                        hit=100, target_defense=target.defense,
                        target_evasion=target.evasion, hit_roll=0,
                    ).damage
                    if mode == "confused":
                        forecast.confused_physical(actor, target)
                    else:
                        forecast.enemy_turn(actor)
                    damage = 1000 - target.hp
                    self.assertEqual(damage, expected)
                    self.assertEqual(actor.hp, min(120, hp + damage))
                    self.assertTrue(target.poisoned)
                    if defense == 0:
                        self.assertGreater(damage, 0)
                    else:
                        self.assertEqual(damage, 0)


if __name__ == "__main__":
    unittest.main()
