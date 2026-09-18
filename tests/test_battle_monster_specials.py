from __future__ import annotations

import unittest
from math import ceil, hypot
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT  # noqa: F401 - add app to sys.path
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)
from tools.screen_mocks.battle import (
    AIM_GAUGE_ADJUSTMENT,
    BATTLE_POPUP_FRAME_COUNT,
    BATTLE_HIT_SE_ID,
    BATTLE_MONSTER_ESCAPE_SE_ID,
    MONSTER_CHARGE_APPROACH_ACCELERATION,
    MONSTER_CHARGE_APPROACH_ACCELERATION_INTERVAL,
    MONSTER_CHARGE_APPROACH_INITIAL_SPEED,
    MONSTER_CHARGE_ATTACK_MULTIPLIER_DENOMINATOR,
    MONSTER_CHARGE_ATTACK_MULTIPLIER_NUMERATOR,
    MONSTER_CHARGE_MAX_JUMP_HEIGHT,
    MONSTER_CHARGE_RETURN_SPEED,
    MONSTER_ESCAPE_SPEED,
    MONSTER_ESCAPE_START_DELAY_FRAME_COUNT,
    MONSTER_POSITIONS,
    BattleTimedPopup,
    BattleMonsterChargePresentation,
    BattleScreenMock,
    BattleMockMonster,
    monster_charge_approach_distance,
    monster_charge_approach_frame_count,
)
from battle_physical import member_physical_attack
from member import EquipmentSlot
from monster import MonsterBattleState, MonsterCombatStats, MonsterSpecialAction
from ui import Window


def charge_monster(*, is_front_row: bool = True) -> BattleMockMonster:
    return BattleMockMonster(
        key="charger",
        names={"name_en": "charger"},
        image_id="1",
        width=64,
        height=64,
        icon_x=0,
        icon_y=0,
        is_front_row=is_front_row,
        state=MonsterBattleState(max_hp=20),
        agility=12,
        special_actions=(MonsterSpecialAction.CHARGE,),
        combat_stats=MonsterCombatStats(attack=10, hit=100, defense=0, evasion=0),
    )


class MonsterChargePresentationTest(unittest.TestCase):
    def test_approach_starts_at_eight_and_accelerates_every_two_frames(
        self,
    ) -> None:
        distances = tuple(
            monster_charge_approach_distance(frame)
            for frame in range(6)
        )
        per_frame = tuple(
            current - previous
            for previous, current in zip(distances, distances[1:])
        )

        self.assertEqual(MONSTER_CHARGE_APPROACH_INITIAL_SPEED, 8)
        self.assertEqual(MONSTER_CHARGE_APPROACH_ACCELERATION_INTERVAL, 2)
        self.assertEqual(MONSTER_CHARGE_APPROACH_ACCELERATION, 1)
        self.assertEqual(per_frame, (8, 8, 9, 9, 10))
        self.assertEqual(monster_charge_approach_frame_count(34), 4)
        self.assertEqual(monster_charge_approach_frame_count(35), 5)

    def test_escape_comparison_uses_total_attack_not_status_weapon_value(self) -> None:
        member = load_mock_party(load_mock_items(), load_mock_skills())[0]
        weapon = member.equipment.weapon_at(EquipmentSlot.RIGHT)
        assert weapon is not None

        actual = BattleScreenMock._member_actual_physical_attack(member)

        self.assertEqual(
            actual,
            member_physical_attack(
                weapon_attack=member.battle_stats.attack_right,
                strength=member.adjusted_abilities.strength,
                weapon_level=member.weapon_level(weapon),
                internal_level=member.internal_level,
            ),
        )
        self.assertNotEqual(actual, member.battle_stats.attack_right)

    def test_charge_uses_1_5_attack_and_distance_based_round_trip(self) -> None:
        actor = charge_monster()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (actor,)
        mock.action_gauge_adjustment = 0.0
        mock._monster_charge_target_indexes = Mock(return_value=(0, 1, 2, 3, 4))
        result = SimpleNamespace(damage=17, critical=False)
        mock._resolve_monster_attack = Mock(return_value=(4, result))
        mock._party_draw_position = Mock(return_value=(188, 176))
        mock._show_monster_action_message = Mock()

        mock._begin_monster_charge(actor)

        expected_target = (136, 160)
        expected_distance = hypot(
            expected_target[0] - MONSTER_POSITIONS[0][0],
            expected_target[1] - MONSTER_POSITIONS[0][1],
        )
        expected_frames = monster_charge_approach_frame_count(expected_distance)
        self.assertEqual(
            mock._resolve_monster_attack.call_args.kwargs["attack"],
            10
            * MONSTER_CHARGE_ATTACK_MULTIPLIER_NUMERATOR
            // MONSTER_CHARGE_ATTACK_MULTIPLIER_DENOMINATOR,
        )
        presentation = mock.monster_charge_presentation
        assert presentation is not None
        self.assertEqual(
            (presentation.target_x, presentation.target_y),
            expected_target,
        )
        self.assertEqual(presentation.approach_frame_count, expected_frames)
        self.assertEqual(
            presentation.return_frame_count,
            ceil(expected_distance / MONSTER_CHARGE_RETURN_SPEED),
        )
        self.assertEqual(mock.action_gauge_adjustment, AIM_GAUGE_ADJUSTMENT)
        self.assertEqual(
            presentation.jump_height,
            MONSTER_CHARGE_MAX_JUMP_HEIGHT,
        )
        mock._show_monster_action_message.assert_called_once_with(
            "battle.monster.charge"
        )

    def test_damage_occurs_at_arrival_and_return_arc_rises_above_linear_path(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        member = SimpleNamespace(hp=30)
        mock.party = (member,)
        mock.monster_charge_presentation = BattleMonsterChargePresentation(
            actor_index=0,
            target_index=0,
            damage=15,
            is_critical=False,
            start_x=0,
            start_y=40,
            target_x=16,
            target_y=40,
            travel_distance=16,
            approach_frame_count=2,
            return_frame_count=2,
            jump_height=32,
        )
        mock.monster_attack_target_index = None
        mock.monster_attack_damage = None
        mock.monster_attack_critical = False
        mock.monster_attack_animation_frame = 0
        mock.monster_attack_damage_applied = False
        mock.focused_target_by_party_index = {}
        mock._refresh_party_hp_text = Mock()
        mock._member_focus_is_interrupted = Mock(return_value=False)
        mock._finish_monster_attack = Mock()

        with patch("scenes.battle.play_se") as play_se:
            mock._update_monster_charge()
            self.assertEqual(member.hp, 30)
            mock._update_monster_charge()

        self.assertEqual(member.hp, 15)
        self.assertEqual(mock.monster_attack_target_index, 0)
        self.assertEqual(mock.monster_attack_damage, 15)
        play_se.assert_called_once_with(BATTLE_HIT_SE_ID)
        presentation = mock.monster_charge_presentation
        assert presentation is not None
        presentation.elapsed_frame = 3
        x, y = presentation.position()
        self.assertEqual(x, 8)
        self.assertLess(y, 40)


class MonsterEscapePresentationTest(unittest.TestCase):
    def test_identical_monsters_escape_and_record_the_actual_individual(self) -> None:
        first, second = charge_monster(), charge_monster()
        self.assertEqual(first, second)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (first, second)
        mock.escaped_monster_indexes = set()
        mock.progression = Mock()
        mock._show_monster_action_message = Mock()
        with patch("scenes.battle.play_se"):
            mock._begin_monster_escape(second)
        self.assertTrue(first.is_alive)
        self.assertFalse(second.is_alive)
        self.assertEqual(mock.monster_escape_actor_index, 1)
        self.assertEqual(mock.escaped_monster_indexes, {1})
        mock.progression.record_enemy_escape.assert_called_once_with(1)

    def test_escape_moves_left_after_da2_delay_and_excludes_rewards(self) -> None:
        actor = charge_monster()
        actor.special_actions = (MonsterSpecialAction.ESCAPE,)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (actor,)
        mock.escaped_monster_indexes = set()
        mock.progression = Mock()
        mock._show_monster_action_message = Mock()

        with patch("scenes.battle.play_se") as play_se:
            mock._begin_monster_escape(actor)

        self.assertFalse(actor.is_alive)
        self.assertEqual(mock.escaped_monster_indexes, {0})
        mock.progression.record_enemy_escape.assert_called_once_with(0)
        mock._show_monster_action_message.assert_called_once_with(
            "battle.monster.escape"
        )
        play_se.assert_called_once_with(BATTLE_MONSTER_ESCAPE_SE_ID)

        mock.monster_escape_animation_frame = MONSTER_ESCAPE_START_DELAY_FRAME_COUNT
        self.assertEqual(mock._monster_escape_x(0), MONSTER_POSITIONS[0][0])
        mock.monster_escape_animation_frame += 1
        self.assertEqual(
            mock._monster_escape_x(0),
            MONSTER_POSITIONS[0][0] - MONSTER_ESCAPE_SPEED,
        )

    def test_monster_action_popup_is_placed_at_upper_left(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        font = Mock()
        font.text_width.side_effect = lambda text: len(text) * 8
        mock.action_popup_window = Window(60, 0, 4, 7, font=font)
        mock.battle_popup = BattleTimedPopup()

        mock._show_battle_popup(
            "とうそう",
            BATTLE_POPUP_FRAME_COUNT,
            align_left=True,
        )

        self.assertEqual(mock.action_popup_window.x, 0)
        self.assertEqual(
            mock.battle_popup.frames_remaining,
            BATTLE_POPUP_FRAME_COUNT,
        )

    def test_last_escaped_monster_finishes_the_battle_without_death_effect(
        self,
    ) -> None:
        actor = charge_monster()
        actor.state.defeat()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (actor,)
        mock.monster_escape_actor_index = 0
        mock.monster_escape_animation_frame = (
            MONSTER_ESCAPE_START_DELAY_FRAME_COUNT
            + ceil((MONSTER_POSITIONS[0][0] + actor.width) / MONSTER_ESCAPE_SPEED)
            - 1
        )
        mock.monster_action = None
        mock._begin_victory_summary = Mock()
        mock._start_timeline_removal_animation = Mock()

        mock._update_monster_escape()

        mock._begin_victory_summary.assert_called_once_with()
        mock._start_timeline_removal_animation.assert_not_called()

    def test_escaping_monster_image_faces_left_like_da2(self) -> None:
        actor = charge_monster()
        image = object()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monster_images = {actor.key: image}

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_monster_image(actor, 4, 56, flip_x=True)

        self.assertEqual(blt.call_args.args[5], -actor.width)


if __name__ == "__main__":
    unittest.main()
