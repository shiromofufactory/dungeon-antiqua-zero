from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import load_mock_items, load_mock_party, load_mock_skills

from battle_commands import BattleCommand
from battle_physical import member_physical_attack, resolve_physical_attack
from item import AdditionalEffect, AttackAttribute
from member import EquipmentSlot, FormationRow
from monster import MonsterTribe
from resistance import ResistanceType
from resources import load_record_array
from scenes.battle import BattleMonster, BattleScene


class BattleTribeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = load_mock_items()
        cls.skills = load_mock_skills()
        cls.goblin = next(r for r in load_record_array("monsters.json", APP_ROOT / "data")
                          if r["name_en"] == "Goblin Shaman")

    def scene(self, weapon=None, *, command=BattleCommand.ATTACK):
        member = load_mock_party(self.items, self.skills, character_keys=("Fiora",))[0]
        member.formation_row = FormationRow.FRONT
        member.equipment = member.equipment.replaced({
            EquipmentSlot.RIGHT: weapon or self.items["GOBLIN SLAYER"],
        })
        scene = BattleScene.__new__(BattleScene)
        scene.party = (member,)
        scene.active_party_index = 0
        scene.monsters = (BattleMonster.from_record(self.goblin, is_front_row=True),)
        scene.attack_poses = {}
        scene.selected_command = command
        scene.selectable_target_indexes = (0,)
        scene.selected_target_index = 0
        scene.target_cursor = Mock()
        scene.command_window = Mock()
        scene._refresh_monster_name_colors = Mock()
        scene._show_battle_popup = Mock()
        scene._command_label = Mock(return_value="")
        return scene

    def test_goblin_slayer_against_goblin_shaman_uses_da2_bonus(self):
        scene = self.scene()
        member = scene.party[0]
        self.assertIs(scene.monsters[0].tribe, MonsterTribe.GOBLIN)
        with patch("scenes.battle.random.randint", side_effect=(0, 99)):
            self.assertTrue(scene._begin_attack_presentation())
        strike = scene.attack_presentation.strikes[0]
        expected = resolve_physical_attack(
            attack=member_physical_attack(
                member.battle_stats.attack_right, member.adjusted_abilities.strength,
                member.weapon_level(self.items["GOBLIN SLAYER"]), member.internal_level,
            ),
            hit=member.battle_stats.hit_right.total,
            target_defense=scene.monsters[0].effective_defense,
            target_evasion=scene.monsters[0].combat_stats.evasion,
            hit_roll=0, weapon_effective=True,
        )
        self.assertTrue(strike.is_hit)
        self.assertTrue(strike.is_critical)
        self.assertTrue(strike.is_weak)
        self.assertEqual(strike.damage, expected.damage)

    def test_each_attack_path_combines_species_and_attribute_once(self):
        for command in (BattleCommand.ATTACK, BattleCommand.AIM, BattleCommand.FOCUS,
                        BattleCommand.AMBUSH, BattleCommand.IAI):
            results = []
            for attribute in (None, AttackAttribute.FIRE):
                weapon = replace(self.items["GOBLIN SLAYER"], attack_attribute=attribute,
                                 additional_effect=AdditionalEffect.DEATH)
                if command is BattleCommand.IAI:
                    weapon = replace(weapon, subtype="KATANA")
                scene = self.scene(weapon, command=command)
                if command is BattleCommand.IAI:
                    scene.party[0].skills.append(self.skills["Iai"])
                scene.monsters[0].weaknesses = frozenset((ResistanceType.FIRE,))
                scene.monsters[0].is_boss = True
                with patch("scenes.battle.random.randint", return_value=0):
                    self.assertTrue(scene._begin_attack_presentation())
                results.append(scene.attack_presentation.strikes[0])
            with self.subTest(command=command):
                self.assertTrue(results[0].is_critical)
                self.assertEqual(results[0].damage, results[1].damage)
                self.assertEqual(results[0].additional_effects, ())
                self.assertEqual(results[1].additional_effects, ())

    def test_dual_wield_checks_each_weapons_tribe_independently(self):
        scene = self.scene()
        member = scene.party[0]
        member.skills.append(self.skills["Dual-Wield"])
        member.equipment = member.equipment.replaced({
            EquipmentSlot.LEFT: self.items["IRON SWORD"],
        })
        with patch("scenes.battle.random.randint", return_value=0):
            self.assertTrue(scene._begin_attack_presentation())
        self.assertEqual(
            tuple((s.is_weak, s.is_critical) for s in scene.attack_presentation.strikes),
            ((True, True), (False, False)),
        )

    def test_species_bonus_does_not_turn_a_miss_into_a_hit(self):
        scene = self.scene()
        scene.monsters[0].combat_stats = replace(scene.monsters[0].combat_stats, evasion=100)
        with patch("scenes.battle.random.randint", return_value=99):
            self.assertTrue(scene._begin_attack_presentation())
        strike = scene.attack_presentation.strikes[0]
        self.assertFalse(strike.is_hit)
        self.assertFalse(strike.is_critical)
        self.assertEqual(strike.damage, 0)

    def test_species_bonus_increases_status_effect_points(self):
        weapon = replace(self.items["GOBLIN SLAYER"], additional_effect=AdditionalEffect.POISON)
        scene = self.scene(weapon)
        monster = scene.monsters[0]
        monster.is_boss = True
        monster.resistances = frozenset((ResistanceType.POISON,))
        with patch("scenes.battle.random.randint", return_value=0):
            self.assertTrue(scene._begin_attack_presentation())
        self.assertEqual(scene.attack_presentation.strikes[0].additional_effects,
                         (AdditionalEffect.POISON,))


if __name__ == "__main__":
    unittest.main()
