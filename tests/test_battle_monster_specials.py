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
    BattleScene,
    monster_charge_approach_distance,
    monster_charge_approach_frame_count,
)
from battle_physical import member_physical_attack
from battle_timeline import TimelineEntry, TimelineOrder
from localization import Localizer
from member import EquipmentSlot
from monster import (
    MonsterBattleState,
    MonsterCombatStats,
    MonsterDefinition,
    MonsterSpecialAction,
    promote_rear_monsters_if_front_empty,
)
from monster_ai import MonsterAction
from resources import load_record_array
from scenes.battle import (
    DA2_MONSTER_ENTRANCE_SLIDE_STEPS,
    DA2_MONSTER_ENTRANCE_STEP_DISTANCE,
    MONSTER_BLINK_FRAME_COUNT,
    MONSTER_ENTRANCE_FRAME_COUNTS,
    REINFORCEMENT_POST_ENTRANCE_WAIT_FRAME_COUNT,
    BattleMonster,
    BattlePhase,
)
from state import Language
from systems import BattleProgression, EnemyProgressionData
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


class MonsterReinforcementTest(unittest.TestCase):
    def test_reinforcement_waits_twelve_frames_after_entrance(self) -> None:
        actor = charge_monster()
        actor.special_actions = (MonsterSpecialAction.REINFORCE,)
        scene = BattleScene.__new__(BattleScene)
        scene.command_window = Mock()
        scene.monster_charge_presentation = None
        scene.monster_escape_actor_index = None
        scene.monster_attack_target_index = None
        scene.monster_blink_frames_remaining = 0
        scene.monster_confused_action_pending = False
        scene.monsters = (actor,)
        scene.monster_slot_indexes = (0, 2)
        scene.timeline = (actor,)
        scene.command_cursor = Mock()
        scene.progression = Mock()
        scene.reinforcement_entrance_frames = {}
        scene._remove_defeated_party_from_timeline = Mock()
        scene._party_is_defeated = Mock(return_value=False)
        scene._prune_surprise_pending_party = Mock(return_value=False)
        scene._begin_front_promotion_if_needed = Mock(return_value=False)
        scene._apply_turn_start_hp_change = Mock(return_value=False)
        scene._monster_can_attempt_action = Mock(return_value=True)
        scene._refresh_party_text_colors = Mock()
        events: list[str] = []

        def summon(_actor: BattleMonster) -> bool:
            events.append("reinforcement")
            scene.reinforcement_entrance_frames[1] = 0
            return True

        scene._attempt_monster_reinforcement = Mock(side_effect=summon)
        scene._select_monster_action = Mock(
            side_effect=lambda _actor: events.append("select") or MonsterAction.ATTACK
        )
        scene._begin_standard_monster_attack = Mock(
            side_effect=lambda _actor: events.append("attack")
        )

        scene._activate_timeline_head()

        self.assertEqual(events, ["reinforcement"])
        self.assertIs(scene.phase, BattlePhase.MONSTER_ACTION)
        self.assertIsNone(scene.blinking_monster_index)
        self.assertEqual(scene.monster_blink_frames_remaining, 0)
        scene.progression.record_enemy_action.assert_not_called()
        for _ in range(MONSTER_ENTRANCE_FRAME_COUNTS[2] - 1):
            scene._update_reinforcement_entrances()
            scene._update_monster_action()
            self.assertIsNone(scene.blinking_monster_index)
        self.assertEqual(events, ["reinforcement"])
        scene._attempt_monster_reinforcement.assert_called_once_with(actor)
        scene.progression.record_enemy_action.assert_not_called()

        scene._update_reinforcement_entrances()
        scene._update_monster_action()
        self.assertEqual(events, ["reinforcement"])
        self.assertEqual(scene._reinforcement_post_entrance_wait_frames, 1)
        self.assertIsNone(scene.blinking_monster_index)

        for _ in range(REINFORCEMENT_POST_ENTRANCE_WAIT_FRAME_COUNT - 1):
            scene._update_monster_action()
            self.assertIsNone(scene.blinking_monster_index)
        self.assertEqual(events, ["reinforcement"])
        self.assertEqual(
            scene._reinforcement_post_entrance_wait_frames,
            REINFORCEMENT_POST_ENTRANCE_WAIT_FRAME_COUNT,
        )
        scene._attempt_monster_reinforcement.assert_called_once_with(actor)
        scene.progression.record_enemy_action.assert_not_called()

        scene._update_monster_action()

        self.assertEqual(events, ["reinforcement"])
        self.assertEqual(scene.blinking_monster_index, 0)
        self.assertEqual(scene.monster_blink_frames_remaining, MONSTER_BLINK_FRAME_COUNT)

        for _ in range(MONSTER_BLINK_FRAME_COUNT - 1):
            scene._update_monster_action()
        self.assertEqual(events, ["reinforcement"])
        self.assertEqual(scene.monster_blink_frames_remaining, 1)

        scene._update_monster_action()

        self.assertEqual(events, ["reinforcement", "select", "attack"])
        scene.progression.record_enemy_action.assert_called_once_with(0)
        self.assertIsNone(scene._reinforcement_waiting_actor)
        self.assertEqual(scene._reinforcement_post_entrance_wait_frames, 0)

    def test_reinforcement_reuses_dead_slot_with_new_reward_and_timeline_identity(self):
        self.check_ally_insertion(same_monster=False)

    def test_call_registers_same_kind_with_independent_reward_and_timeline(self):
        self.check_ally_insertion(same_monster=True)

    def check_ally_insertion(self, *, same_monster: bool) -> None:
        records = {
            record["name_en"]: record
            for record in load_record_array("monsters.json")
            if record["name_en"] in ("Treant", "Spirit")
        }
        treant = BattleMonster.from_record(records["Treant"], is_front_row=False)
        fallen = BattleMonster.from_record(records["Spirit"], is_front_row=True)
        fallen.state.defeat()
        self.assertTrue(promote_rear_monsters_if_front_empty((treant, fallen)))
        self.assertTrue(treant.is_front_row)
        scene = BattleScene.__new__(BattleScene)
        scene.monsters = (treant, fallen)
        scene.monster_slot_indexes = (0, 2)
        scene.monster_positions = (MONSTER_POSITIONS[0], MONSTER_POSITIONS[2])
        scene.reinforcement_entrance_frames = {}
        scene.monster_definitions_by_key = {
            key: MonsterDefinition.from_record(record)
            for key, record in records.items()
        }
        scene.monster_records_by_key = records
        scene.monster_image_resources = Mock()
        scene.monster_window_factory = Mock()
        scene.monster_name_windows = []
        scene.monster_name_texts = []
        scene.monster_images = {"Treant": Mock()}
        scene.localizer = Localizer(Language.JAPANESE)
        scene.monster_record_system = Mock()
        scene.target_window = Mock()
        scene._timeline_order = TimelineOrder(
            (TimelineEntry(treant, treant.agility, 64),)
        )
        scene.timeline = scene._timeline_order.actors
        scene.progression = BattleProgression(
            tuple(
                EnemyProgressionData(
                    monster.level, monster.early_appear,
                    monster.max_occurrence, monster.gold,
                    monster.key, monster.treasure_item_key, monster.treasure_rate,
                )
                for monster in scene.monsters
            )
        )
        scene.progression.record_enemy_defeat(1)

        if same_monster:
            self.assertTrue(scene._add_monster_ally(treant, same_monster=True))
        else:
            with patch("scenes.battle.reinforcement_arrives", return_value=True):
                self.assertTrue(scene._attempt_monster_reinforcement(treant))
        expected_key = "Treant" if same_monster else "Spirit"

        self.assertEqual(len(scene.monsters), 3)
        self.assertEqual(scene.monsters[2].key, expected_key)
        self.assertIsNot(scene.monsters[2], fallen)
        self.assertFalse(treant.is_front_row)
        self.assertTrue(scene.monsters[2].is_front_row)
        self.assertEqual(scene.monster_slot_indexes, (0, 2, 2))
        self.assertEqual(scene.monster_positions[2], MONSTER_POSITIONS[2])
        self.assertEqual(scene.reinforcement_entrance_frames, {2: 0})
        self.assertEqual(scene.progression.enemies[2].monster_key, expected_key)
        self.assertIs(scene.timeline[0], treant)
        self.assertIn(scene.monsters[2], scene.timeline)
        scene.monster_record_system.register_encounter.assert_called_once_with(
            (expected_key,)
        )
        targets = scene.target_window.set_cursor.call_args.args[0]
        self.assertEqual({target.key for target in targets}, {0, 2})

        scene.phase = BattlePhase.MONSTER_ACTION
        scene.monster_charge_presentation = None
        scene.monster_escape_actor_index = None
        duration = MONSTER_ENTRANCE_FRAME_COUNTS[2]
        initial_x = (
            MONSTER_POSITIONS[2][0]
            - DA2_MONSTER_ENTRANCE_SLIDE_STEPS[2]
            * DA2_MONSTER_ENTRANCE_STEP_DISTANCE
        )
        self.assertEqual(scene._monster_draw_position(2)[0], initial_x)
        self.assertEqual(scene._monster_draw_position(2)[0], initial_x)
        self.assertEqual(scene.reinforcement_entrance_frames[2], 0)

        for _ in range(duration // 2):
            scene._update_reinforcement_entrances()
        halfway_x = scene._monster_draw_position(2)[0]
        self.assertLess(initial_x, halfway_x)
        self.assertLess(halfway_x, MONSTER_POSITIONS[2][0])

        for _ in range(duration - duration // 2):
            scene._update_reinforcement_entrances()
        self.assertEqual(scene._monster_draw_position(2), MONSTER_POSITIONS[2])
        self.assertNotIn(2, scene.reinforcement_entrance_frames)

    def test_reinforcement_recalculates_rows_when_front_slot_becomes_occupied(
        self,
    ) -> None:
        scene = BattleScene.__new__(BattleScene)
        rear_monster = SimpleNamespace(is_alive=True, is_front_row=True)
        reinforcement = SimpleNamespace(is_alive=True, is_front_row=False)
        scene.monsters = (rear_monster, reinforcement)
        scene.monster_slot_indexes = (0, 1)

        scene._refresh_monster_rows_from_slots()

        self.assertTrue(rear_monster.is_front_row)
        self.assertTrue(reinforcement.is_front_row)

        scene.monster_slot_indexes = (0, 2)
        scene._refresh_monster_rows_from_slots()

        self.assertFalse(rear_monster.is_front_row)
        self.assertTrue(reinforcement.is_front_row)


class MonsterCallTurnTest(unittest.TestCase):
    def test_call_waits_for_arrival_then_consumes_turn_without_attacking(self):
        actor = charge_monster()
        actor.special_actions = (MonsterSpecialAction.CALL,)
        scene = BattleScene.__new__(BattleScene)
        scene.monsters = scene.timeline = (actor,)
        scene.command_window = Mock()
        scene.monster_charge_presentation = None
        scene.monster_escape_actor_index = None
        scene.monster_attack_target_index = None
        scene.monster_blink_frames_remaining = 0
        scene.monster_confused_action_pending = False
        scene.reinforcement_entrance_frames = {}
        scene.progression = Mock()
        scene._select_monster_action = Mock(return_value=MonsterAction.CALL)
        scene._show_monster_action_message = Mock()
        scene._start_timeline_animation = Mock()
        scene._begin_standard_monster_attack = Mock()

        def add(_actor, *, same_monster):
            self.assertIs(_actor, actor)
            self.assertTrue(same_monster)
            scene.reinforcement_entrance_frames[1] = 0
            return True

        scene._add_monster_ally = Mock(side_effect=add)
        scene._update_monster_action()
        scene._show_monster_action_message.assert_called_once_with("battle.monster.call")
        scene.progression.record_enemy_action.assert_called_once_with(0)
        scene._update_monster_action()
        scene._start_timeline_animation.assert_not_called()
        scene.reinforcement_entrance_frames.clear()
        for _ in range(REINFORCEMENT_POST_ENTRANCE_WAIT_FRAME_COUNT):
            scene._update_monster_action()
            scene._start_timeline_animation.assert_not_called()
        scene._update_monster_action()
        scene._start_timeline_animation.assert_called_once_with()
        scene._select_monster_action.assert_called_once_with(actor)
        scene._begin_standard_monster_attack.assert_not_called()
        self.assertFalse(scene._monster_call_pending)


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
