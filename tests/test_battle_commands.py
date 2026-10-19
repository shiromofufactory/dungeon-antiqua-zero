from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

from tools._bootstrap import APP_ROOT

from battle_commands import (
    BattleCommand,
    BattleCommandContext,
    BattleCommandOption,
    formation_change_enabled,
    member_has_spell_aptitude,
    resolve_battle_commands,
    selectable_attack_target_indexes,
)
from member import EquipmentSlot, FormationRow, MAX_INTERNAL_LEVEL
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)


class BattleCommandRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.party = list(
            load_mock_party(
                load_mock_items(),
                load_mock_skills(),
                character_keys=("Fiora", "Cerion", "Alvan"),
                internal_level=MAX_INTERNAL_LEVEL,
            )
        )
        for member in self.party:
            member.formation_row = FormationRow.FRONT
        self.monsters = tuple(
            SimpleNamespace(is_front_row=is_front_row, is_alive=True)
            for is_front_row in (False, False, False, True, True)
        )

    def test_resolver_uses_equipment_and_rows_for_attack_availability(self) -> None:
        commands = resolve_battle_commands(
            self.party[0],
            self.party,
            self.monsters,
        )
        self.assertEqual(commands[0].command, BattleCommand.ATTACK)

        self.party[0].formation_row = FormationRow.BACK
        commands = resolve_battle_commands(
            self.party[0],
            self.party,
            self.monsters,
        )
        self.assertEqual(commands[0].command, BattleCommand.ATTACK)
        self.assertFalse(commands[0].enabled)
        self.assertIn(
            BattleCommandOption(BattleCommand.DEFEND),
            commands,
        )

    def test_dead_monsters_are_not_attack_targets(self) -> None:
        monsters = tuple(
            SimpleNamespace(is_front_row=True, is_alive=index == 1)
            for index in range(2)
        )

        self.assertEqual(
            selectable_attack_target_indexes(
                attacker_is_front_row=True,
                weapon_reach=1,
                monsters=monsters,
            ),
            (1,),
        )

    def test_unrestricted_attack_range_targets_every_living_row(self) -> None:
        self.assertEqual(
            selectable_attack_target_indexes(
                attacker_is_front_row=False,
                weapon_reach=1,
                monsters=self.monsters,
                unrestricted_range=True,
            ),
            (0, 1, 2, 3, 4),
        )

    def test_unarmed_member_cannot_select_attack(self) -> None:
        self.party[0].equipment = self.party[0].equipment.replaced(
            {EquipmentSlot.RIGHT: None}
        )

        attack = next(
            option
            for option in resolve_battle_commands(
                self.party[0],
                self.party,
                self.monsters,
            )
            if option.command is BattleCommand.ATTACK
        )

        self.assertFalse(attack.enabled)

    def test_formation_is_disabled_for_the_only_front_member(self) -> None:
        self.party[0].formation_row = FormationRow.BACK
        self.party[1].formation_row = FormationRow.BACK

        self.assertFalse(formation_change_enabled(self.party[2], self.party))
        option = next(
            option
            for option in resolve_battle_commands(
                self.party[2],
                self.party,
                self.monsters,
            )
            if option.command is BattleCommand.FORMATION
        )
        self.assertFalse(option.enabled)

    def test_back_member_can_always_move_to_front(self) -> None:
        self.party[0].formation_row = FormationRow.BACK
        self.party[1].formation_row = FormationRow.BACK

        self.assertTrue(formation_change_enabled(self.party[0], self.party))

    def test_resolver_accepts_battle_only_front_rows(self) -> None:
        self.party[0].formation_row = FormationRow.BACK
        self.party[1].formation_row = FormationRow.BACK

        commands = resolve_battle_commands(
            self.party[0],
            self.party[:2],
            self.monsters,
            party_front_rows=(True, True),
        )

        attack = next(
            option for option in commands if option.command is BattleCommand.ATTACK
        )
        formation = next(
            option
            for option in commands
            if option.command is BattleCommand.FORMATION
        )
        self.assertTrue(attack.enabled)
        self.assertTrue(formation.enabled)
        self.assertIs(self.party[0].formation_row, FormationRow.BACK)

    def test_single_member_party_does_not_show_formation(self) -> None:
        commands = resolve_battle_commands(
            self.party[0],
            self.party[:1],
            self.monsters,
        )

        self.assertNotIn(
            BattleCommand.FORMATION,
            tuple(option.command for option in commands),
        )

    def test_left_column_evaluates_in_order_and_stops_after_three(self) -> None:
        skills = load_mock_skills()
        self.party[0].skills.extend(
            (skills["Focus"], skills["Aim"], skills["Hide"])
        )

        commands = resolve_battle_commands(
            self.party[0],
            self.party,
            self.monsters,
        )

        self.assertEqual(
            tuple(option.command for option in commands),
            (
                BattleCommand.ATTACK,
                BattleCommand.SPELL,
                BattleCommand.AIM,
                BattleCommand.DEFEND,
                BattleCommand.ITEM,
                BattleCommand.FORMATION,
            ),
        )

    def test_unreachable_attack_is_disabled_without_rearranging_the_left_column(self) -> None:
        skills = load_mock_skills()
        self.party[0].formation_row = FormationRow.BACK
        self.party[0].skills.extend((skills["Aim"], skills["Hide"]))

        commands = resolve_battle_commands(
            self.party[0],
            self.party,
            self.monsters,
        )

        self.assertEqual(
            tuple(option.command for option in commands[:3]),
            (BattleCommand.ATTACK, BattleCommand.SPELL, BattleCommand.AIM),
        )
        self.assertFalse(commands[0].enabled)
        aim = next(
            option for option in commands if option.command is BattleCommand.AIM
        )
        self.assertFalse(aim.enabled)

    def test_focus_is_disabled_when_normal_attack_cannot_reach(self) -> None:
        skills = load_mock_skills()
        self.party[0].formation_row = FormationRow.BACK
        self.party[0].skills.append(skills["Focus"])

        commands = resolve_battle_commands(
            self.party[0],
            self.party,
            self.monsters,
        )

        focus = next(
            option for option in commands if option.command is BattleCommand.FOCUS
        )
        self.assertFalse(focus.enabled)

    def test_iai_requires_right_hand_katana(self) -> None:
        skills = load_mock_skills()
        items = load_mock_items()
        member = self.party[0]
        member.skills.append(skills["Iai"])

        def iai_enabled() -> bool:
            options = resolve_battle_commands(member, self.party, self.monsters)
            return next(option.enabled for option in options if option.command is BattleCommand.IAI)

        self.assertFalse(iai_enabled())
        member.equipment = member.equipment.replaced(
            {EquipmentSlot.RIGHT: items["KATANA"]}
        )
        self.assertTrue(iai_enabled())
        member.equipment = member.equipment.replaced(
            {EquipmentSlot.RIGHT: None}
        )
        self.assertFalse(iai_enabled())

    def test_iai_availability_uses_battle_row_and_right_hand_reach(self) -> None:
        member = self.party[0]
        member.skills.append(load_mock_skills()["Iai"])
        katana = load_mock_items()["KATANA"]
        # Even when only rear enemies remain, an available Iai reaches them.
        monsters = (SimpleNamespace(is_front_row=False, is_alive=True),)
        for stored_row in (FormationRow.FRONT, FormationRow.BACK):
            for battle_front in (True, False):
                for reach in (1, 2, 3):
                    with self.subTest(
                        stored_row=stored_row, battle_front=battle_front, reach=reach
                    ):
                        member.formation_row = stored_row
                        member.equipment = member.equipment.replaced(
                            {EquipmentSlot.RIGHT: replace(katana, reach=reach)}
                        )
                        options = resolve_battle_commands(
                            member,
                            self.party,
                            monsters,
                            party_front_rows=(battle_front, True, True),
                        )
                        iai = next(
                            option for option in options
                            if option.command is BattleCommand.IAI
                        )
                        self.assertEqual(iai.enabled, battle_front or reach >= 2)

    def test_silence_disables_visible_spell_without_hiding_it(self) -> None:
        commands = resolve_battle_commands(
            self.party[0],
            self.party,
            self.monsters,
            context=BattleCommandContext(
                silenced=True,
                item_available=False,
                escape_available=False,
            ),
        )
        enabled_by_command = {
            option.command: option.enabled
            for option in commands
        }

        self.assertFalse(enabled_by_command[BattleCommand.SPELL])
        self.assertFalse(enabled_by_command[BattleCommand.ITEM])

    def test_base_spell_aptitude_shows_spell_without_spell_catalog(self) -> None:
        commands = resolve_battle_commands(
            self.party[0],
            self.party,
            self.monsters,
        )

        spell = next(
            option
            for option in commands
            if option.command is BattleCommand.SPELL
        )
        self.assertTrue(spell.enabled)
        self.assertTrue(member_has_spell_aptitude(self.party[0]))

    def test_single_member_keeps_defend_at_the_start_of_the_right_column(self) -> None:
        skills = load_mock_skills()
        self.party[0].skills.append(skills["Aim"])

        commands = resolve_battle_commands(
            self.party[0],
            self.party[:1],
            self.monsters,
        )

        self.assertEqual(
            tuple(option.command for option in commands),
            (
                BattleCommand.ATTACK,
                BattleCommand.SPELL,
                BattleCommand.AIM,
                BattleCommand.DEFEND,
                BattleCommand.ITEM,
            ),
        )

    def test_single_member_party_does_not_show_cover(self) -> None:
        skills = load_mock_skills()
        self.party[0].skills.append(skills["Cover"])

        commands = resolve_battle_commands(
            self.party[0],
            self.party[:1],
            self.monsters,
        )

        self.assertNotIn(
            BattleCommand.COVER,
            tuple(option.command for option in commands),
        )

    def test_hidden_member_uses_ambush_instead_of_attack_or_hide(self) -> None:
        skills = load_mock_skills()
        self.party[0].skills.append(skills["Hide"])
        self.party[0].formation_row = FormationRow.BACK

        commands = resolve_battle_commands(
            self.party[0],
            self.party,
            self.monsters,
            context=BattleCommandContext(actor_hidden=True),
        )
        command_keys = tuple(option.command for option in commands)

        self.assertEqual(command_keys[0], BattleCommand.AMBUSH)
        self.assertTrue(commands[0].enabled)
        self.assertNotIn(BattleCommand.ATTACK, command_keys)
        self.assertNotIn(BattleCommand.HIDE, command_keys)
        formation = next(
            option
            for option in commands
            if option.command is BattleCommand.FORMATION
        )
        self.assertFalse(formation.enabled)


if __name__ == "__main__":
    unittest.main()
