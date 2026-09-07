from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from tools.screen_mocks.battle import (
    BATTLE_MOCK_PARTY_CHARACTER_KEYS,
    MONSTER_BLINK_FRAME_COUNT,
    BattleMockCharacter,
    BattleMockMonster,
    BattleMockPhase,
    BattleScreenMock,
    FormationRow,
    MAX_INTERNAL_LEVEL,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TIMELINE_ANIMATION_FRAME_COUNT,
    TimelineAnimationPhase,
    WindowText,
    ascii_to_fullwidth,
    member_attack_reach,
    selectable_attack_target_indexes,
)
from tools.screen_mocks._fixtures import load_mock_items, load_mock_party, load_mock_skills
from tools.screen_mocks._runtime import FPS
from input import Direction, InputButton, InputState
from ui.formation_arrow import (
    FORMATION_ARROW_BANK,
    FORMATION_ARROW_COLKEY,
    FORMATION_ARROW_FRAME_DURATION,
    FORMATION_ARROW_HEIGHT,
    FORMATION_ARROW_RIGHT_X,
    FORMATION_ARROW_WIDTH,
    FORMATION_ARROW_Y,
)


class BattleScreenMockTest(unittest.TestCase):
    def test_mock_uses_sixty_fps(self) -> None:
        self.assertEqual(FPS, 60)

    def test_draw_uses_explicit_back_to_front_order(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock._draw_background = Mock()
        mock._draw_party = Mock()
        mock._draw_active_party_arrow = Mock()
        mock._draw_monsters = Mock()
        mock._draw_target_cursor = Mock()
        mock._draw_timeline = Mock()
        mock._draw_windows = Mock()

        manager = Mock()
        manager.attach_mock(mock._draw_background, "background")
        manager.attach_mock(mock._draw_party, "party")
        manager.attach_mock(mock._draw_active_party_arrow, "actor_arrow")
        manager.attach_mock(mock._draw_monsters, "monsters")
        manager.attach_mock(mock._draw_target_cursor, "target")
        manager.attach_mock(mock._draw_timeline, "timeline")
        manager.attach_mock(mock._draw_windows, "windows")

        mock.draw()

        self.assertEqual(
            manager.mock_calls,
            [
                call.background(),
                call.party(),
                call.actor_arrow(),
                call.monsters(),
                call.timeline(),
                call.windows(),
                call.target(),
            ],
        )

    def test_draw_background_is_opaque(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.background = object()

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_background()

        blt.assert_called_once_with(
            0,
            0,
            mock.background,
            0,
            0,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
        )

    def test_battle_fixture_uses_current_five_members_at_level_ninety_nine(self) -> None:
        party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )

        self.assertEqual(
            tuple(member.definition.key for member in party),
            BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        self.assertEqual(len(party), 5)
        self.assertTrue(
            all(member.internal_level == MAX_INTERNAL_LEVEL for member in party)
        )

    def test_mock_initializes_display_data_from_generated_records(self) -> None:
        with (
            patch("tools.screen_mocks.battle.initialize_screen_mock"),
            patch("tools.screen_mocks.battle.create_mock_input_reader"),
            patch("tools.screen_mocks.battle.ImageResources") as images,
            patch("tools.screen_mocks.battle.FontResources") as fonts,
            patch("tools.screen_mocks.battle.WindowFactory") as windows,
            patch("tools.screen_mocks.battle.pyxel.run"),
        ):
            images.return_value.entry.return_value = SimpleNamespace(
                width=SCREEN_WIDTH,
                height=SCREEN_HEIGHT,
            )
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = object()
            windows.return_value.create.return_value = Mock()
            command_cursor = Mock()
            target_cursor = Mock()
            windows.return_value.create.return_value.set_cursor.side_effect = (
                command_cursor,
                target_cursor,
            )

            mock = BattleScreenMock()

        self.assertEqual(
            tuple(member.definition.key for member in mock.party),
            BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        self.assertTrue(
            all(member.internal_level == MAX_INTERNAL_LEVEL for member in mock.party)
        )
        self.assertEqual(
            [visual.battle_sprite for visual in mock.party_visuals],
            [0, 1, 2, 3, 4],
        )
        self.assertEqual(
            [(entry.icon_x, entry.icon_y) for entry in mock.timeline],
            [(0, 0), (16, 0), (32, 0), (64, 0), (48, 0), (128, 16)],
        )
        self.assertIs(mock.timeline[-1], mock.monsters[0])
        self.assertIs(mock.party[1].formation_row, FormationRow.FRONT)
        self.assertEqual(
            [monster.is_front_row for monster in mock.monsters],
            [False, False, True, True, True],
        )
        self.assertEqual(member_attack_reach(mock.party[0]), 1)
        mock.active_party_index = 1
        self.assertEqual(mock._active_member_attack_targets(), (0, 1, 2, 3, 4))
        mock.active_party_index = 3
        self.assertEqual(mock._active_member_attack_targets(), ())
        mock.active_party_index = 0
        target_definitions = (
            windows.return_value.create.return_value.set_cursor.call_args_list[1]
            .args[0]
        )
        self.assertEqual(
            [(target.x, target.y, target.key) for target in target_definitions],
            [(3, 18, 0), (3, 34, 1), (19, 10, 2), (19, 26, 3), (19, 42, 4)],
        )
        self.assertFalse(mock.target_cursor.active)
        first_member = mock.party[0]
        self.assertIn(
            ascii_to_fullwidth(
                f"{first_member.hp:03d}/{first_member.max_hp:03d}"
            ),
            [
                call.args[0]
                for call in windows.return_value.create.return_value.add_text.call_args_list
            ],
        )

    def test_party_sprites_use_member_formation_and_data_sprite_index(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.character_sprites = object()
        mock.party_visuals = (
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT),
                battle_sprite=2,
            ),
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.BACK),
                battle_sprite=4,
            ),
        )

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party()

        self.assertEqual(
            blt.call_args_list,
            [
                call(156, 64, mock.character_sprites, 0, 64, 16, 32, 1),
                call(176, 92, mock.character_sprites, 0, 128, 16, 32, 1),
            ],
        )

    def test_monster_images_and_timeline_icons_use_display_data(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        image = object()
        mock.monsters = (
            SimpleNamespace(key="Coyote", width=96, height=64),
        )
        mock.monster_images = {"Coyote": image}
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock.timeline = (
            SimpleNamespace(icon_x=224, icon_y=16),
        )
        mock.timeline_animation_phase = None

        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_monsters()
            mock._draw_timeline()

        self.assertEqual(
            blt.call_args_list,
            [
                call(4, 56, image, 0, 0, 96, 64, 1),
                call(70, 220, 1, 224, 16, 16, 16, 1),
                call(74, 216, 0, 88, 16, 8, 8, 1),
            ],
        )

    def test_attack_reach_and_rows_determine_selectable_targets(self) -> None:
        monsters = tuple(
            SimpleNamespace(is_front_row=is_front_row)
            for is_front_row in (False, False, True, True, True)
        )
        expected = {
            (True, 1): (2, 3, 4),
            (False, 1): (),
            (True, 2): (0, 1, 2, 3, 4),
            (False, 2): (2, 3, 4),
            (True, 3): (0, 1, 2, 3, 4),
            (False, 3): (0, 1, 2, 3, 4),
        }

        for (is_front_row, reach), target_indexes in expected.items():
            with self.subTest(is_front_row=is_front_row, reach=reach):
                self.assertEqual(
                    selectable_attack_target_indexes(
                        attacker_is_front_row=is_front_row,
                        weapon_reach=reach,
                        monsters=monsters,
                    ),
                    target_indexes,
                )

    def test_attack_starts_at_last_selectable_target_and_keeps_command_open(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (SimpleNamespace(is_front_row=True),)
        mock.active_party_index = 0
        mock.monsters = tuple(
            SimpleNamespace(is_front_row=is_front_row)
            for is_front_row in (False, False, True, True, True)
        )
        mock.command_cursor = SimpleNamespace(active=True)
        mock.target_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.phase = BattleMockPhase.COMMAND
        mock.selected_command = None
        mock.selectable_target_indexes = ()
        mock.selected_target_index = None

        with patch("tools.screen_mocks.battle.member_attack_reach", return_value=1):
            self.assertTrue(mock._begin_attack_target_selection())

        self.assertEqual(mock.selectable_target_indexes, (2, 3, 4))
        self.assertEqual(mock.selected_target_index, 4)
        self.assertEqual(mock.selected_command, "attack")
        self.assertIs(mock.phase, BattleMockPhase.TARGET)
        self.assertFalse(mock.command_cursor.active)
        self.assertTrue(mock.target_cursor.active)
        mock.target_cursor.select_key.assert_called_once_with(4)
        mock.command_window.close.assert_not_called()

    def test_reach_one_back_row_member_cannot_start_target_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (SimpleNamespace(is_front_row=False),)
        mock.active_party_index = 0
        mock.monsters = tuple(
            SimpleNamespace(is_front_row=is_front_row)
            for is_front_row in (False, False, True, True, True)
        )
        mock.command_cursor = SimpleNamespace(active=True)
        mock.target_cursor = Mock(active=False)
        mock.phase = BattleMockPhase.COMMAND
        mock.selected_command = None
        mock.selectable_target_indexes = ()
        mock.selected_target_index = None

        with patch("tools.screen_mocks.battle.member_attack_reach", return_value=1):
            self.assertFalse(mock._begin_attack_target_selection())

        self.assertIs(mock.phase, BattleMockPhase.COMMAND)
        self.assertTrue(mock.command_cursor.active)
        self.assertIsNone(mock.selected_target_index)

    def test_target_navigation_uses_da2_order_and_skips_unreachable_enemies(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.selectable_target_indexes = (2, 3, 4)
        mock.selected_target_index = 4
        mock.target_cursor = Mock()

        self.assertTrue(mock._move_target(Direction.LEFT))
        self.assertEqual(mock.selected_target_index, 3)
        self.assertTrue(mock._move_target(Direction.RIGHT))
        self.assertEqual(mock.selected_target_index, 4)

    def test_requested_direction_mapping_matches_numbered_monster_layout(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.selectable_target_indexes = (0, 1, 2, 3, 4)
        mock.target_cursor = Mock()

        expected_from_four = {
            Direction.UP: 2,
            Direction.DOWN: 4,
            Direction.RIGHT: 1,
            Direction.LEFT: 0,
        }
        for direction, expected_index in expected_from_four.items():
            with self.subTest(origin=4, direction=direction):
                mock.selected_target_index = 3
                self.assertTrue(mock._move_target(direction))
                self.assertEqual(mock.selected_target_index, expected_index)

        expected_from_two = {
            Direction.UP: 0,
            Direction.DOWN: 0,
            Direction.RIGHT: 4,
            Direction.LEFT: 3,
        }
        for direction, expected_index in expected_from_two.items():
            with self.subTest(origin=2, direction=direction):
                mock.selected_target_index = 1
                self.assertTrue(mock._move_target(direction))
                self.assertEqual(mock.selected_target_index, expected_index)

        mock.selected_target_index = 4
        self.assertTrue(mock._move_target(Direction.LEFT))
        self.assertEqual(mock.selected_target_index, 1)

    def test_horizontal_target_navigation_cycles_in_both_directions(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.selectable_target_indexes = (0, 1, 2, 3, 4)
        mock.target_cursor = Mock()

        # Display numbers 1 -> 4 -> 2 -> 5 -> 3 -> 1.
        right_cycle = (0, 3, 1, 4, 2, 0)
        mock.selected_target_index = right_cycle[0]
        for expected_index in right_cycle[1:]:
            self.assertTrue(mock._move_target(Direction.RIGHT))
            self.assertEqual(mock.selected_target_index, expected_index)

        # LEFT follows the exact reverse path.
        left_cycle = tuple(reversed(right_cycle))
        for expected_index in left_cycle[1:]:
            self.assertTrue(mock._move_target(Direction.LEFT))
            self.assertEqual(mock.selected_target_index, expected_index)

    def test_fiora_right_skips_monster_two_and_moves_from_four_to_five(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.selectable_target_indexes = (2, 3, 4)
        mock.selected_target_index = 3
        mock.target_cursor = Mock()

        self.assertTrue(mock._move_target(Direction.RIGHT))

        self.assertEqual(mock.selected_target_index, 4)
        mock.target_cursor.select_key.assert_called_once_with(4)

    def test_target_cancel_returns_to_command_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_cursor = SimpleNamespace(active=False)
        mock.target_cursor = SimpleNamespace(active=True)
        mock.phase = BattleMockPhase.TARGET
        mock.selected_command = "attack"
        mock.selectable_target_indexes = (2, 3, 4)
        mock.selected_target_index = 4

        mock._update_target_selection(
            InputState(cancel=InputButton(triggered=True, held=True))
        )

        self.assertIs(mock.phase, BattleMockPhase.COMMAND)
        self.assertTrue(mock.command_cursor.active)
        self.assertFalse(mock.target_cursor.active)
        self.assertIsNone(mock.selected_command)
        self.assertIsNone(mock.selected_target_index)

    def test_target_confirm_closes_command_and_starts_timeline_animation(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_cursor = SimpleNamespace(active=False)
        mock.target_cursor = SimpleNamespace(active=True)
        mock.command_window = Mock()
        mock.phase = BattleMockPhase.TARGET
        mock.selected_command = "attack"
        mock.selectable_target_indexes = (2, 3, 4)
        mock.selected_target_index = 4
        mock._refresh_party_text_colors = Mock()

        mock._update_target_selection(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertFalse(mock.target_cursor.active)
        self.assertIsNone(mock.selected_command)
        self.assertIsNone(mock.selected_target_index)
        mock.command_window.close.assert_called_once_with()
        self.assertIs(mock.phase, BattleMockPhase.TIMELINE)
        self.assertIsNone(mock.active_party_index)
        self.assertIs(
            mock.timeline_animation_phase,
            TimelineAnimationPhase.DROP,
        )
        self.assertEqual(mock.timeline_animation_frame, 0)

    def test_non_attack_command_also_completes_current_turn(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock()
        mock.command_cursor.selected_key = "defend"
        mock.command_window = Mock()
        mock.command_window.is_closed = False
        mock.command_window.is_open = True
        mock.selected_command = None
        mock._complete_current_turn = Mock()

        mock.update()

        self.assertEqual(mock.selected_command, "defend")
        mock._complete_current_turn.assert_called_once_with()

    def test_timeline_cycles_through_party_and_blinks_first_monster(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        members = tuple(
            SimpleNamespace(definition=SimpleNamespace(key=key))
            for key in BATTLE_MOCK_PARTY_CHARACTER_KEYS
        )
        mock.party_visuals = tuple(
            BattleMockCharacter(member, index * 16, 0, index)
            for index, member in enumerate(members)
        )
        spider = BattleMockMonster(
            key="Giant Spider",
            names={},
            image_id="n-1",
            width=64,
            height=64,
            icon_x=128,
            icon_y=16,
            is_front_row=False,
        )
        mock.monsters = (spider,)
        mock.timeline = mock.party_visuals + (spider,)
        mock.active_party_index = 0
        mock.phase = BattleMockPhase.INITIAL
        mock.command_cursor = SimpleNamespace(active=True)
        mock.command_window = Mock()
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock._refresh_command_options = Mock()
        mock.party_status_windows = [Mock() for _ in members]
        for window in mock.party_status_windows:
            window.add_text.side_effect = (
                lambda text, x, y, **kwargs: WindowText(text, x, y, **kwargs)
            )
        mock.party_status_texts = [
            (WindowText(key, 0, 0, color=4), WindowText("ＨＰ", 0, 4, color=4))
            for key in BATTLE_MOCK_PARTY_CHARACTER_KEYS
        ]

        for expected_index in range(1, 5):
            mock._advance_timeline()
            self.assertIs(mock.timeline[0], mock.party_visuals[expected_index])
            self.assertEqual(mock.active_party_index, expected_index)
            self.assertIs(mock.phase, BattleMockPhase.COMMAND)
            self.assertEqual(
                [texts[0].color for texts in mock.party_status_texts],
                [5 if index == expected_index else 4 for index in range(5)],
            )

        mock._advance_timeline()

        self.assertIs(mock.timeline[0], spider)
        self.assertEqual(mock.command_window.open.call_count, 4)
        self.assertIsNone(mock.active_party_index)
        self.assertIs(mock.phase, BattleMockPhase.MONSTER_ACTION)
        self.assertEqual(mock.blinking_monster_index, 0)
        self.assertEqual(
            mock.monster_blink_frames_remaining,
            MONSTER_BLINK_FRAME_COUNT,
        )
        self.assertEqual(
            [texts[0].color for texts in mock.party_status_texts],
            [4, 4, 4, 4, 4],
        )
        mock.command_window.close.assert_called_once_with()

        for _ in range(MONSTER_BLINK_FRAME_COUNT - 1):
            mock._update_monster_action()
        self.assertIs(mock.phase, BattleMockPhase.MONSTER_ACTION)
        self.assertEqual(mock.monster_blink_frames_remaining, 1)

        mock._update_monster_action()

        self.assertIs(mock.phase, BattleMockPhase.TIMELINE)
        self.assertIs(
            mock.timeline_animation_phase,
            TimelineAnimationPhase.DROP,
        )
        for _ in range(2 * (TIMELINE_ANIMATION_FRAME_COUNT + 1)):
            mock._update_timeline_animation()

        self.assertIs(mock.timeline[0], mock.party_visuals[0])
        self.assertEqual(mock.active_party_index, 0)
        self.assertIs(mock.phase, BattleMockPhase.COMMAND)
        self.assertEqual(mock.command_window.open.call_count, 5)
        self.assertIsNone(mock.blinking_monster_index)
        self.assertEqual(
            [texts[0].color for texts in mock.party_status_texts],
            [5, 4, 4, 4, 4],
        )

    def test_active_member_draws_shared_blinking_right_arrow(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 1
        mock.party_visuals = (
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT)
            ),
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT)
            ),
        )

        with (
            patch(
                "tools.screen_mocks.battle.pyxel.frame_count",
                FORMATION_ARROW_FRAME_DURATION,
            ),
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
        ):
            mock._draw_active_party_arrow()

        blt.assert_called_once_with(
            160 - FORMATION_ARROW_WIDTH,
            92 + (32 - FORMATION_ARROW_HEIGHT) // 2,
            FORMATION_ARROW_BANK,
            FORMATION_ARROW_RIGHT_X[1],
            FORMATION_ARROW_Y,
            FORMATION_ARROW_WIDTH,
            FORMATION_ARROW_HEIGHT,
            FORMATION_ARROW_COLKEY,
        )

    def test_timeline_drop_then_slide_draws_requested_paths(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.timeline = tuple(
            SimpleNamespace(icon_x=index * 16, icon_y=0)
            for index in range(6)
        )
        mock.timeline_animation_phase = TimelineAnimationPhase.DROP
        mock.timeline_animation_frame = TIMELINE_ANIMATION_FRAME_COUNT // 2

        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()

        icon_calls = blt.call_args_list
        self.assertEqual(icon_calls[0].args[:2], (70, 225))
        self.assertEqual(icon_calls[1].args[:2], (90, 220))

        mock.timeline_animation_phase = TimelineAnimationPhase.SLIDE
        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()

        self.assertEqual(
            [draw_call.args[:2] for draw_call in blt.call_args_list],
            [
                (80, 220),
                (100, 220),
                (120, 220),
                (140, 220),
                (160, 220),
                (213, 220),
            ],
        )

    def test_monster_blink_uses_da2_six_frame_visibility_cycle(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        image = object()
        mock.monsters = (
            SimpleNamespace(key="Giant Spider", width=64, height=64),
        )
        mock.monster_images = {"Giant Spider": image}
        mock.blinking_monster_index = 0

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock.monster_blink_frames_remaining = MONSTER_BLINK_FRAME_COUNT
            mock._draw_monsters()
            blt.assert_not_called()

            mock.monster_blink_frames_remaining = 5
            mock._draw_monsters()
            blt.assert_called_once_with(4, 56, image, 0, 0, 64, 64, 1)

    def test_unable_to_attack_removes_attack_and_moves_left_commands_up(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_window = Mock()
        new_cursor = Mock()
        mock.command_window.set_cursor.return_value = new_cursor
        mock._active_member_attack_targets = Mock(return_value=())

        mock._refresh_command_options()

        self.assertEqual(
            mock.command_window.add_text.call_args_list,
            [
                call("ぼうぎょ", 4, 2),
                call("じゅもん", 4, 5),
                call("にげる", 18, 2),
                call("アイテム", 18, 5),
                call("こうたい", 18, 8),
            ],
        )
        targets = mock.command_window.set_cursor.call_args.args[0]
        self.assertEqual(
            [(target.key, target.x, target.y) for target in targets],
            [
                ("defend", 2, 2),
                ("spell", 2, 5),
                ("escape", 16, 2),
                ("item", 16, 5),
                ("formation", 16, 8),
            ],
        )
        mock.command_window.clear_texts.assert_called_once_with()
        mock.command_window.clear_cursor.assert_called_once_with()
        self.assertIs(mock.command_cursor, new_cursor)

    def test_target_cursor_uses_window_cursor_rendering(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.TARGET
        mock.target_cursor = Mock()

        mock._draw_target_cursor()

        mock.target_cursor.draw.assert_called_once_with()

    def test_update_passes_logical_navigation_to_open_command_window(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            navigation=Direction.RIGHT,
            held_direction=Direction.RIGHT,
        )
        mock.command_window = Mock()
        mock.command_window.is_closed = False
        mock.command_window.is_open = True
        mock.command_cursor = Mock()
        mock.selected_command = None

        mock.update()

        mock.command_window.update.assert_called_once_with(Direction.RIGHT)

    def test_first_confirm_opens_closed_command_window(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.INITIAL
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock()
        mock.command_cursor.selected_key = "attack"
        mock.command_window = Mock()
        mock.command_window.is_closed = True
        mock.command_window.is_open = False
        mock.selected_command = None

        mock.update()

        mock.command_window.open.assert_called_once_with()
        mock.command_window.close.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)
        self.assertIsNone(mock.selected_command)

    def test_second_confirm_starts_attack_target_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock()
        mock.command_cursor.selected_key = "attack"
        mock.command_window = Mock()
        mock.command_window.is_closed = False
        mock.command_window.is_open = True
        mock.selected_command = None
        mock._begin_attack_target_selection = Mock(return_value=True)

        mock.update()

        mock._begin_attack_target_selection.assert_called_once_with()
        mock.command_window.close.assert_not_called()
        mock.command_window.open.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)

    def test_cancel_input_quits_before_updating_cursor(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.INITIAL
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock()
        mock.command_window = Mock()

        with patch("tools.screen_mocks.battle.pyxel.quit") as quit_game:
            mock.update()

        quit_game.assert_called_once_with()
        mock.command_window.update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
