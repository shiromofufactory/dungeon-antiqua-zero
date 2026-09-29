from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)

from attack_pose import load_attack_poses
from auto_battle_model import AutoAction
from battle_commands import BattleCommand
from battle_physical import PhysicalAttackResult, member_physical_attack
from input import InputButton, InputState
from member import EquipmentSlot
from scenes.battle import (
    ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT,
    ATTACK_POSE_RAISE_FRAME_COUNT,
    BattlePhase,
    BattleScene,
    IAI_GAUGE_ADJUSTMENT,
)


class IaiBattleTest(unittest.TestCase):
    def test_auto_iai_uses_all_target_scene_path(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        scene._remember_active_command = Mock()
        scene._begin_attack_target_selection = Mock(return_value=True)
        scene.target_cursor = Mock()

        scene._execute_auto_action(AutoAction(BattleCommand.IAI, (5, 6)))

        scene._begin_attack_target_selection.assert_called_once_with(
            command=BattleCommand.IAI
        )
        scene.target_cursor.select_key.assert_not_called()

    def test_iai_target_selection_marks_all_enemies_and_can_cancel(self) -> None:
        items = load_mock_items()
        skills = load_mock_skills()
        member = load_mock_party(items, skills, character_keys=("Fiora",))[0]
        member.equipment = member.equipment.replaced(
            {EquipmentSlot.RIGHT: items["KATANA"]}
        )
        scene = BattleScene.__new__(BattleScene)
        scene.active_party_index = 0
        scene.party = (member,)
        scene.monsters = (
            SimpleNamespace(is_alive=True),
            SimpleNamespace(is_alive=False),
            SimpleNamespace(is_alive=True),
        )
        scene.target_cursor = Mock(
            targets=tuple(SimpleNamespace(key=index) for index in range(3))
        )
        scene.target_window = Mock()
        scene.command_cursor = Mock()
        scene._begin_action_motion = Mock()
        scene._begin_action_return = Mock()
        scene._refresh_monster_name_colors = Mock()
        cursors = (Mock(), Mock())
        scene._make_all_target_cursors = Mock(return_value=cursors)

        self.assertTrue(scene._begin_attack_target_selection(command=BattleCommand.IAI))
        self.assertEqual(scene.selectable_target_indexes, (0, 2))
        self.assertIsNone(scene.selected_target_index)
        self.assertIs(scene.phase, BattlePhase.TARGET)
        self.assertFalse(scene.target_cursor.active)
        self.assertEqual(scene.all_target_cursors, cursors)
        scene._begin_action_motion.assert_called_once_with(use_cast_pose=False, jump=False)
        scene._update_target_selection(InputState())
        for cursor in cursors:
            cursor.update.assert_called_once()

        scene._update_target_selection(InputState(cancel=InputButton(triggered=True)))
        self.assertIs(scene.phase, BattlePhase.COMMAND)
        self.assertEqual(scene.all_target_cursors, ())
        scene._begin_action_return.assert_called_once()

    def test_iai_uses_katana_poses_and_hits_every_enemy_at_sixty_percent(self) -> None:
        items = load_mock_items()
        skills = load_mock_skills()
        member = load_mock_party(items, skills, character_keys=("Fiora",))[0]
        member.equipment = member.equipment.replaced(
            {EquipmentSlot.RIGHT: items["KATANA"]}
        )
        member.skills.append(skills["Iai"])

        def monster() -> SimpleNamespace:
            state = SimpleNamespace(hp=999, sleeping=0)
            state.take_damage = lambda amount: setattr(state, "hp", state.hp - amount)
            return SimpleNamespace(
                is_alive=True,
                is_front_row=True,
                state=state,
                combat_stats=SimpleNamespace(evasion=0),
                effective_defense=0,
                weaknesses=frozenset(),
                resistances=frozenset(),
                key="Coyote",
                level=1,
            )

        scene = BattleScene.__new__(BattleScene)
        scene.active_party_index = 0
        scene.action_party_index = 0
        scene.party = (member,)
        scene.monsters = (monster(), monster())
        scene.selectable_target_indexes = (0, 1)
        scene.selected_command = BattleCommand.IAI
        scene.hidden_party_indexes = set()
        scene.attack_poses = load_attack_poses(
            APP_ROOT / "effects" / "attack_poses.json"
        )
        scene.target_cursor = Mock()
        scene.command_window = Mock()
        scene._refresh_monster_name_colors = Mock()
        scene._resolve_member_attack_additional_effects = Mock(return_value=())

        result = PhysicalAttackResult(True, 12, 100.0, 100.0)
        with patch("scenes.battle.resolve_physical_attack", return_value=result) as resolver:
            self.assertTrue(scene._begin_attack_presentation())

        expected_attack = member_physical_attack(
            member.battle_stats.attack_right * 60 // 100,
            member.adjusted_abilities.strength,
            member.weapon_level(items["KATANA"]),
            member.internal_level,
        )
        self.assertEqual([call.kwargs["attack"] for call in resolver.call_args_list],
                         [expected_attack, expected_attack])
        self.assertEqual(scene.action_gauge_adjustment, IAI_GAUGE_ADJUSTMENT)
        self.assertIs(scene.phase, BattlePhase.ATTACK_PRESENTATION)
        self.assertEqual(
            tuple(strike.target_index for strike in scene.attack_presentation.strikes),
            (0, 1),
        )
        self.assertEqual(
            tuple(pose.branch for pose in scene.attack_presentation.strikes[0].poses),
            ("5", "6"),
        )
        self.assertEqual(
            tuple(strike.hit_start_frame for strike in scene.attack_presentation.strikes),
            (ATTACK_POSE_RAISE_FRAME_COUNT, ATTACK_POSE_RAISE_FRAME_COUNT + 2),
        )
        self.assertEqual(
            tuple(strike.pose_end_frame for strike in scene.attack_presentation.strikes),
            (13, 13),
        )
        first, second = scene.attack_presentation.strikes
        scene.attack_presentation.elapsed_frame = second.hit_start_frame - 1
        self.assertEqual(scene.attack_presentation.pose.branch, "5")
        scene.attack_presentation.elapsed_frame = second.hit_start_frame
        self.assertEqual(scene.attack_presentation.pose.branch, "6")
        popup_start = first.hit_start_frame + ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT
        self.assertEqual(first.damage_popup_elapsed_frame(popup_start), 0)
        self.assertEqual(second.damage_popup_elapsed_frame(popup_start), -2)
        scene.attack_presentation.elapsed_frame = 2
        with patch("scenes.battle.play_se") as sound:
            scene._update_attack_presentation()
            self.assertEqual(
                tuple(enemy.state.hp for enemy in scene.monsters), (987, 999)
            )
            sound.assert_not_called()
            scene._update_attack_presentation()
            sound.assert_not_called()
            scene._update_attack_presentation()
        sound.assert_called_once()
        self.assertEqual(tuple(enemy.state.hp for enemy in scene.monsters), (987, 987))

        scene.action_returning = False
        scene.action_offset_x = 16
        scene.action_forward_jump = True
        scene._begin_action_return = Mock()
        while scene.attack_presentation.elapsed_frame < 13:
            scene._update_attack_presentation()
        scene._begin_action_return.assert_called_once_with(jump=True)

        scene.action_returning = True
        self.assertEqual(scene._party_attack_pose(0).branch, "6")
        scene.action_offset_x = 0
        self.assertIsNone(scene._party_attack_pose(0))


if __name__ == "__main__":
    unittest.main()
