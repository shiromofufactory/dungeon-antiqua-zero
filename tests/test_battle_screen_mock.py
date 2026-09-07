from __future__ import annotations

import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from tools.screen_mocks.battle import (
    BATTLE_ENTRANCE_FRAME_COUNT,
    BATTLE_BGM_ID,
    BATTLE_MOCK_MONSTER_KEYS,
    BATTLE_MOCK_PARTY_CHARACTER_KEYS,
    COMMAND_GUIDE_DELAY_FRAME_COUNT,
    COMMAND_GUIDE_FIRST_Y,
    COMMAND_GUIDE_LINE_SPACING,
    COMMAND_GUIDE_TEXT_KEYS,
    COMMAND_GUIDE_TEXT_X,
    COMMAND_GUIDE_WINDOW_GRID,
    COMMAND_TEXT_KEYS,
    DA2_MONSTER_ENTRANCE_SLIDE_STEPS,
    DA2_MONSTER_ENTRANCE_STEP_DISTANCE,
    DEFEND_SPRITE_SOURCE_X,
    ESCAPE_RUN_DESTINATION_X,
    ESCAPE_RUN_PATTERN_FRAME_COUNT,
    ESCAPE_RUN_SPEED,
    FORMATION_MOVE_FRAME_COUNT,
    FORMATION_SPRITE_STEP_X,
    FORMATION_WALK_PATTERN_FRAME_COUNT,
    ITEM_WINDOW_GRID,
    ITEM_GUIDE_WINDOW_GRID,
    MONSTER_BLINK_FRAME_COUNT,
    MONSTER_ENTRANCE_FRAME_COUNTS,
    MONSTER_POSITIONS,
    PARTY_ENTRANCE_COMPLETE_FRAME,
    PARTY_ENTRANCE_FRAME_COUNT,
    PARTY_ENTRANCE_OFFSET_Y,
    PARTY_ENTRANCE_START_X,
    PARTY_ENTRANCE_STAGGER_FRAME_COUNT,
    BattleMockCharacter,
    BattleItemCandidate,
    BattleMockMonster,
    BattleMockPhase,
    BattleScreenMock,
    FormationRow,
    MAX_INTERNAL_LEVEL,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SPELL_GUIDE_WINDOW_GRID,
    SPELL_MP_WINDOW_GRID,
    SPELL_WINDOW_GRID,
    TIMELINE_ANIMATION_FRAME_COUNT,
    TIMELINE_ENTRANCE_COMPLETE_FRAME,
    TIMELINE_ENTRANCE_FRAME_COUNT,
    TIMELINE_ENTRANCE_STAGGER_FRAME_COUNT,
    TIMELINE_VISIBLE_ENTRY_COUNT,
    UNSELECTABLE_TARGET_PALETTE,
    UNSELECTABLE_TARGET_PALETTE_BASE_RATE,
    TimelineAnimationPhase,
    WindowText,
    ascii_to_fullwidth,
    member_attack_reach,
    selectable_attack_target_indexes,
)
from battle_commands import BattleCommand, BattleCommandOption
from localization import Localizer
from member import EquipmentSlot
from state import Language
from text_catalog import TextCatalog
from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
    load_mock_spells,
)
from tools.screen_mocks._runtime import FPS
from input import Direction, InputButton, InputState
from monster import MonsterBattleState
from rendering import (
    DEFAULT_FADE_FRAME_COUNT,
    MONSTER_DEATH_BRIGHTEN_FRAME_COUNT,
    MONSTER_DEATH_DISSOLVE_FRAME_COUNT,
    MONSTER_DEATH_PALETTE,
    MONSTER_DEATH_TINT_FRAME_COUNT,
    FadeThroughBlack,
    MonsterDeathAnimation,
)
from ui.formation_arrow import (
    FORMATION_ARROW_BANK,
    FORMATION_ARROW_COLKEY,
    FORMATION_ARROW_FRAME_DURATION,
    FORMATION_ARROW_HEIGHT,
    FORMATION_ARROW_RIGHT_X,
    FORMATION_ARROW_WIDTH,
    FORMATION_ARROW_Y,
)
from ui import Window


_JAPANESE_COMMAND_LABELS = {
    BattleCommand.ATTACK: "こうげき",
    BattleCommand.SPELL: "じゅもん",
    BattleCommand.AIM: "ねらう",
    BattleCommand.DEFEND: "ぼうぎょ",
    BattleCommand.ESCAPE: "にげる",
    BattleCommand.ITEM: "アイテム",
    BattleCommand.FORMATION: "こうたい",
}


class BattleScreenMockTest(unittest.TestCase):
    def _mock_command_labels(self, mock: BattleScreenMock) -> None:
        mock._command_label = Mock(side_effect=_JAPANESE_COMMAND_LABELS.__getitem__)

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

    def test_battle_fixture_uses_requested_three_members_at_level_ninety_nine(self) -> None:
        self.assertEqual(
            BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            ("Fiora", "Cerion", "Alvan"),
        )
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
        self.assertEqual(len(party), 3)
        self.assertTrue(
            all(member.internal_level == MAX_INTERNAL_LEVEL for member in party)
        )

    def test_mock_initializes_display_data_from_generated_records(self) -> None:
        with (
            patch("tools.screen_mocks.battle.initialize_screen_mock") as initialize,
            patch("tools.screen_mocks.battle.create_mock_input_reader"),
            patch("tools.screen_mocks.battle.BgmPlayer"),
            patch("tools.screen_mocks.battle.ImageResources") as images,
            patch("tools.screen_mocks.battle.FontResources") as fonts,
            patch("tools.screen_mocks.battle.WindowFactory") as windows,
            patch("tools.screen_mocks.battle.pyxel.run"),
        ):
            images.return_value.entry.return_value = SimpleNamespace(
                width=SCREEN_WIDTH,
                height=SCREEN_HEIGHT,
            )
            palette_shifter = Mock(
                base_colors=(0x000000, 0xFF0080, 0x4C4C4C, 0x858585),
            )
            initialize.return_value = palette_shifter
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = object()
            windows.return_value.create.return_value = Mock()
            command_cursor = Mock()
            target_cursor = Mock()
            escape_cursor = Mock()
            restarted_command_cursor = Mock()
            windows.return_value.create.return_value.set_cursor.side_effect = (
                command_cursor,
                target_cursor,
                escape_cursor,
                restarted_command_cursor,
            )

            mock = BattleScreenMock()

        guide_window_call = windows.return_value.create.call_args_list[0]
        self.assertEqual(
            guide_window_call.args[:4],
            COMMAND_GUIDE_WINDOW_GRID,
        )
        self.assertFalse(guide_window_call.kwargs["opened"])
        item_guide_window_call = windows.return_value.create.call_args_list[2]
        self.assertEqual(
            item_guide_window_call.args[:4],
            ITEM_GUIDE_WINDOW_GRID,
        )
        self.assertFalse(item_guide_window_call.kwargs["opened"])
        self.assertEqual(
            windows.return_value.create.call_args_list[4].args[:4],
            SPELL_WINDOW_GRID,
        )
        self.assertEqual(
            windows.return_value.create.call_args_list[5].args[:4],
            SPELL_GUIDE_WINDOW_GRID,
        )
        self.assertEqual(
            windows.return_value.create.call_args_list[6].args[:4],
            SPELL_MP_WINDOW_GRID,
        )

        self.assertEqual(
            tuple(member.definition.key for member in mock.party),
            BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        self.assertTrue(
            all(member.internal_level == MAX_INTERNAL_LEVEL for member in mock.party)
        )
        self.assertEqual(
            [visual.battle_sprite for visual in mock.party_visuals],
            [0, 1, 2],
        )
        self.assertEqual(
            [(entry.icon_x, entry.icon_y) for entry in mock.timeline],
            [
                (0, 0),
                (16, 0),
                (32, 0),
                (128, 16),
                (128, 16),
                (128, 16),
                (224, 16),
                (224, 16),
            ],
        )
        self.assertEqual(
            tuple(monster.key for monster in mock.monsters),
            BATTLE_MOCK_MONSTER_KEYS,
        )
        self.assertTrue(all(monster.state.hp == 2 for monster in mock.monsters))
        self.assertEqual(mock.timeline, mock.party_visuals + mock.monsters)
        self.assertEqual(
            mock.inventory_system.catalog_count,
            len(load_mock_items()),
        )
        self.assertTrue(
            all(
                mock.inventory_system.quantity(item) == 1
                for item in load_mock_items().values()
            )
        )
        self.assertIs(mock.phase, BattleMockPhase.ENTRANCE)
        self.assertEqual(mock.entrance_animation_frame, 0)
        self.assertTrue(mock.entrance_fade.is_active)
        self.assertFalse(mock.command_cursor.active)
        palette_shifter.set_global_mix.assert_called_with(
            base_rate=0.0,
            target_color=0x000000,
        )
        palette_shifter.define_mix.assert_called_once_with(
            UNSELECTABLE_TARGET_PALETTE,
            base_rate=UNSELECTABLE_TARGET_PALETTE_BASE_RATE,
            target_color=0x858585,
        )
        self.assertIs(mock.party[1].formation_row, FormationRow.FRONT)
        self.assertEqual(
            [monster.is_front_row for monster in mock.monsters],
            [False, False, True, True, True],
        )
        self.assertEqual(member_attack_reach(mock.party[0]), 1)
        self.assertEqual(mock._active_member_attack_targets(), (2, 3, 4))
        mock.active_party_index = 1
        self.assertEqual(mock._active_member_attack_targets(), (0, 1, 2, 3, 4))
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
        self.assertFalse(mock.escape_cursor.active)
        self.assertEqual(mock.escape_animation_frame, 0)
        self.assertEqual(mock.escape_start_x, ())
        self.assertEqual(mock.escaping_party_indexes, set())
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
        created_texts = [
            placement.text
            for create_call in windows.return_value.create.call_args_list
            for placement in (
                create_call.args[4]
                if len(create_call.args) >= 5
                else ()
            )
        ]
        self.assertIn("ほんとうに　にげて　いいですか？", created_texts)
        self.assertIn(ascii_to_fullwidth("にげだした..."), created_texts)
        self.assertIn("はい", created_texts)
        self.assertIn("いいえ", created_texts)

    def test_entrance_blocks_input_until_all_animations_finish(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ENTRANCE
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock._update_entrance_animation = Mock()
        mock.command_window = Mock()

        mock.update()

        mock._update_entrance_animation.assert_called_once_with()
        mock.command_window.open.assert_not_called()

    def test_entrance_fades_in_then_opens_first_command_turn(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ENTRANCE
        mock.entrance_animation_frame = 0
        mock.entrance_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        mock.entrance_fade.start_fade_in()
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock()

        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_entrance_animation()

        self.assertIs(mock.phase, BattleMockPhase.ENTRANCE)
        self.assertFalse(mock.entrance_fade.is_active)
        mock.palette_shifter.set_global_mix.assert_called_with(
            base_rate=1.0,
            target_color=0x000000,
        )

        for _frame in range(
            BATTLE_ENTRANCE_FRAME_COUNT - DEFAULT_FADE_FRAME_COUNT
        ):
            mock._update_entrance_animation()

        self.assertEqual(
            mock.entrance_animation_frame,
            BATTLE_ENTRANCE_FRAME_COUNT,
        )
        self.assertIs(mock.phase, BattleMockPhase.COMMAND)
        self.assertTrue(mock.command_cursor.active)
        mock.command_window.open.assert_called_once_with()

    def test_party_sprites_use_formation_and_defense_source_images(self) -> None:
        self.assertEqual(DEFEND_SPRITE_SOURCE_X, 16 * 7)
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
        mock.phase = BattleMockPhase.COMMAND
        mock.defending_party_indexes = {1}

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party()

        self.assertEqual(
            blt.call_args_list,
            [
                call(156, 64, mock.character_sprites, 0, 64, 16, 32, 1),
                call(
                    176,
                    92,
                    mock.character_sprites,
                    DEFEND_SPRITE_SOURCE_X,
                    128,
                    16,
                    32,
                    1,
                ),
            ],
        )

    def test_party_entrance_jumps_quickly_with_two_frame_stagger(
        self,
    ) -> None:
        self.assertEqual(PARTY_ENTRANCE_START_X, SCREEN_WIDTH)
        self.assertEqual(PARTY_ENTRANCE_FRAME_COUNT, 10)
        self.assertEqual(PARTY_ENTRANCE_STAGGER_FRAME_COUNT, 2)
        self.assertEqual(PARTY_ENTRANCE_COMPLETE_FRAME, 14)
        self.assertEqual(BATTLE_ENTRANCE_FRAME_COUNT, 20)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ENTRANCE
        mock.party_visuals = tuple(
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT)
            )
            for _index in range(3)
        )

        mock.entrance_animation_frame = 0
        self.assertEqual(
            mock._party_draw_position(0),
            (PARTY_ENTRANCE_START_X, 64 + PARTY_ENTRANCE_OFFSET_Y),
        )
        self.assertIsNone(mock._party_draw_position(1))

        mock.entrance_animation_frame = PARTY_ENTRANCE_STAGGER_FRAME_COUNT
        self.assertEqual(
            mock._party_draw_position(1),
            (PARTY_ENTRANCE_START_X, 92 + PARTY_ENTRANCE_OFFSET_Y),
        )

        mock.entrance_animation_frame = PARTY_ENTRANCE_FRAME_COUNT // 2
        midpoint = mock._party_draw_position(0)
        self.assertIsNotNone(midpoint)
        assert midpoint is not None
        self.assertGreater(midpoint[0], 156)
        self.assertLess(midpoint[0], PARTY_ENTRANCE_START_X)
        self.assertLess(midpoint[1], 64 + PARTY_ENTRANCE_OFFSET_Y)

        for index in range(3):
            mock.entrance_animation_frame = (
                PARTY_ENTRANCE_FRAME_COUNT
                + index * PARTY_ENTRANCE_STAGGER_FRAME_COUNT
            )
            self.assertEqual(
                mock._party_draw_position(index),
                (156 + index * 4, (64, 92, 120)[index]),
            )

    def test_monster_images_and_timeline_icons_use_display_data(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        image = object()
        mock.monsters = (
            SimpleNamespace(key="Coyote", width=96, height=64, is_alive=True),
        )
        mock.monster_images = {"Coyote": image}
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock.phase = BattleMockPhase.COMMAND
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

    def test_monster_entrance_matches_da2_slide_timing_at_sixty_fps(self) -> None:
        self.assertEqual(MONSTER_ENTRANCE_FRAME_COUNTS, (16, 16, 14, 14, 12))
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ENTRANCE
        mock.entrance_animation_frame = 0

        for index, ((target_x, _target_y), slide_steps) in enumerate(
            zip(MONSTER_POSITIONS, DA2_MONSTER_ENTRANCE_SLIDE_STEPS)
        ):
            self.assertEqual(
                mock._monster_draw_x(index),
                target_x - slide_steps * DA2_MONSTER_ENTRANCE_STEP_DISTANCE,
            )

        for index, duration in enumerate(MONSTER_ENTRANCE_FRAME_COUNTS):
            mock.entrance_animation_frame = duration
            self.assertEqual(mock._monster_draw_x(index), MONSTER_POSITIONS[index][0])

    def test_attack_reach_and_rows_determine_selectable_targets(self) -> None:
        monsters = tuple(
            SimpleNamespace(is_front_row=is_front_row, is_alive=True)
            for is_front_row in (False, False, False, True, True)
        )
        expected = {
            (True, 1): (3, 4),
            (False, 1): (),
            (True, 2): (0, 1, 2, 3, 4),
            (False, 2): (3, 4),
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
            SimpleNamespace(is_front_row=is_front_row, is_alive=True)
            for is_front_row in (False, False, False, True, True)
        )
        mock.command_cursor = SimpleNamespace(active=True)
        mock.target_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.phase = BattleMockPhase.COMMAND
        mock.selected_command = None
        mock.selectable_target_indexes = ()
        mock.selected_target_index = None
        mock._refresh_monster_name_colors = Mock()

        with patch("tools.screen_mocks.battle.member_attack_reach", return_value=1):
            self.assertTrue(mock._begin_attack_target_selection())

        self.assertEqual(mock.selectable_target_indexes, (3, 4))
        self.assertEqual(mock.selected_target_index, 4)
        self.assertEqual(mock.selected_command, "attack")
        self.assertIs(mock.phase, BattleMockPhase.TARGET)
        self.assertFalse(mock.command_cursor.active)
        self.assertTrue(mock.target_cursor.active)
        mock.target_cursor.select_key.assert_called_once_with(4)
        mock._refresh_monster_name_colors.assert_called_once_with()
        mock.command_window.close_immediately.assert_not_called()

    def test_reach_one_back_row_member_cannot_start_target_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (SimpleNamespace(is_front_row=False),)
        mock.active_party_index = 0
        mock.monsters = tuple(
            SimpleNamespace(is_front_row=is_front_row, is_alive=True)
            for is_front_row in (False, False, False, True, True)
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
        mock.selectable_target_indexes = (3, 4)
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
        mock.selectable_target_indexes = (3, 4)
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

    def test_target_confirm_sets_hp_to_zero_and_starts_death_animation(self) -> None:
        monsters = tuple(
            BattleMockMonster(
                key=f"monster-{index}",
                names={},
                image_id=str(index),
                width=64,
                height=64,
                icon_x=index * 16,
                icon_y=16,
                is_front_row=True,
                state=MonsterBattleState(max_hp=2),
            )
            for index in range(5)
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_cursor = SimpleNamespace(active=False)
        mock.target_cursor = SimpleNamespace(active=True)
        mock.command_window = Mock()
        mock.palette_shifter = Mock()
        mock.monsters = monsters
        actor = object()
        mock.timeline = (actor, *monsters)
        mock.phase = BattleMockPhase.TARGET
        mock.selected_command = "attack"
        mock.selectable_target_indexes = (2, 3, 4)
        mock.selected_target_index = 4
        mock._complete_current_turn = Mock()

        mock._update_target_selection(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertFalse(mock.target_cursor.active)
        self.assertEqual(monsters[4].state.hp, 0)
        self.assertFalse(monsters[4].is_alive)
        mock.command_window.close_immediately.assert_called_once_with()
        self.assertIs(mock.phase, BattleMockPhase.MONSTER_DEATH)
        self.assertEqual(mock.dying_monster_index, 4)
        self.assertIsInstance(
            mock.monster_death_animation,
            MonsterDeathAnimation,
        )
        mock.palette_shifter.define_mix.assert_called_once()

        frame_count = (
            MONSTER_DEATH_TINT_FRAME_COUNT
            + MONSTER_DEATH_BRIGHTEN_FRAME_COUNT
            + MONSTER_DEATH_DISSOLVE_FRAME_COUNT
        )
        for _frame in range(frame_count):
            mock._update_monster_death_animation()

        self.assertNotIn(monsters[4], mock.timeline)
        self.assertEqual(mock.timeline[0], actor)
        self.assertIsNone(mock.dying_monster_index)
        self.assertIsNone(mock.monster_death_animation)
        mock._complete_current_turn.assert_called_once_with()

    def test_monster_death_draw_uses_shifted_palette_and_dither(self) -> None:
        monster = BattleMockMonster(
            key="Coyote",
            names={},
            image_id="3",
            width=64,
            height=64,
            icon_x=224,
            icon_y=16,
            is_front_row=True,
            state=MonsterBattleState(max_hp=2),
        )
        monster.state.defeat()
        animation = MonsterDeathAnimation()
        for _frame in range(
            MONSTER_DEATH_TINT_FRAME_COUNT
            + MONSTER_DEATH_BRIGHTEN_FRAME_COUNT
            + MONSTER_DEATH_DISSOLVE_FRAME_COUNT // 2
        ):
            animation.update()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (monster,)
        mock.monster_images = {"Coyote": object()}
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock.phase = BattleMockPhase.MONSTER_DEATH
        mock.dying_monster_index = 0
        mock.monster_death_animation = animation
        mock.palette_shifter = Mock()
        mock.palette_shifter.shifted.return_value = nullcontext()

        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.dither") as dither,
        ):
            mock._draw_monsters()

        mock.palette_shifter.shifted.assert_called_once_with(
            MONSTER_DEATH_PALETTE
        )
        self.assertEqual(dither.call_args_list, [call(0.5), call(1.0)])
        blt.assert_called_once_with(
            4,
            56,
            mock.monster_images["Coyote"],
            0,
            0,
            64,
            64,
            1,
        )

    def test_defeating_last_front_monster_promotes_living_rear_monsters(
        self,
    ) -> None:
        rear_monster = BattleMockMonster(
            key="rear",
            names={},
            image_id="1",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=False,
            state=MonsterBattleState(max_hp=2),
        )
        front_monster = BattleMockMonster(
            key="front",
            names={},
            image_id="2",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=2),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (rear_monster, front_monster)
        mock.selectable_target_indexes = (1,)
        mock.selected_target_index = 1
        mock.target_cursor = SimpleNamespace(active=True)
        mock.command_window = Mock()
        mock.palette_shifter = Mock()

        self.assertTrue(mock._begin_monster_death())

        self.assertFalse(front_monster.is_alive)
        self.assertTrue(rear_monster.is_front_row)

        rear_monster.restore()
        self.assertTrue(rear_monster.is_alive)
        self.assertFalse(rear_monster.is_front_row)

    def test_unselectable_rear_monster_uses_gray_palette_during_target_selection(
        self,
    ) -> None:
        monsters = (
            BattleMockMonster(
                key="rear",
                names={},
                image_id="1",
                width=64,
                height=64,
                icon_x=0,
                icon_y=0,
                is_front_row=False,
                state=MonsterBattleState(max_hp=2),
            ),
            BattleMockMonster(
                key="front",
                names={},
                image_id="2",
                width=64,
                height=64,
                icon_x=0,
                icon_y=0,
                is_front_row=True,
                state=MonsterBattleState(max_hp=2),
            ),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = monsters
        mock.monster_images = {"rear": object(), "front": object()}
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock.phase = BattleMockPhase.TARGET
        mock.selectable_target_indexes = (1,)
        mock.dying_monster_index = None
        mock.palette_shifter = Mock()
        mock.palette_shifter.shifted.return_value = nullcontext()

        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.dither") as dither,
        ):
            mock._draw_monsters()

        mock.palette_shifter.shifted.assert_called_once_with(
            UNSELECTABLE_TARGET_PALETTE,
        )
        dither.assert_not_called()
        self.assertEqual(blt.call_count, 2)

    def test_non_item_non_attack_command_also_completes_current_turn(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock()
        mock.command_cursor.selected_key = "hide"
        mock.command_window = Mock()
        mock.command_window.is_closed = False
        mock.command_window.is_open = True
        mock.selected_command = None
        mock._complete_current_turn = Mock()

        mock.update()

        self.assertEqual(mock.selected_command, "hide")
        mock._complete_current_turn.assert_called_once_with()

    def test_item_command_opens_item_selection_instead_of_completing_turn(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock(selected_key=BattleCommand.ITEM)
        mock.command_window = Mock(is_closed=False, is_open=True)
        mock._begin_item_selection = Mock(return_value=True)
        mock._complete_current_turn = Mock()

        mock.update()

        mock._begin_item_selection.assert_called_once_with()
        mock._complete_current_turn.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)

    def test_item_candidates_use_equipment_then_owned_consumables(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        member = mock.party[0]
        member.equipment = member.equipment.replaced(
            {EquipmentSlot.ARM: items["TELEPORT RING"]}
        )
        mock.active_party_index = 0
        from systems import InventorySystem

        mock.inventory_system = InventorySystem.with_one_each(items)
        mock.spells = load_mock_spells()

        candidates = mock._active_member_item_candidates()

        self.assertEqual(
            tuple(candidate.item.key for candidate in candidates[:7]),
            (
                "DAGGER",
                "TELEPORT RING",
                "POTION",
                "REMEDY",
                "MANA DROP",
                "PANACEA",
                "DIVINE TEAR",
            ),
        )
        self.assertTrue(candidates[0].is_equipped)
        self.assertTrue(candidates[1].is_equipped)
        self.assertTrue(all(not candidate.is_equipped for candidate in candidates[2:]))
        candidate_keys = {candidate.item.key for candidate in candidates}
        self.assertNotIn("FRUIT of STR", candidate_keys)
        self.assertNotIn("FRUIT of AGI", candidate_keys)
        self.assertNotIn("FRUIT of MAG", candidate_keys)
        self.assertNotIn("NECTOR", candidate_keys)

    def test_item_list_uses_its_own_wider_window_with_three_candidates(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.item_candidates = tuple(
            BattleItemCandidate(items[key])
            for key in ("POTION", "REMEDY", "MANA DROP", "PANACEA")
        )
        mock.selected_item_index = 0
        mock.item_scroll_offset = 0
        from systems import InventorySystem

        mock.inventory_system = InventorySystem.with_one_each(items)
        mock.localizer = Localizer(Language.JAPANESE)
        mock.item_window = Mock()
        mock.item_window.set_cursor.return_value = Mock()
        mock._refresh_item_guide = Mock()

        mock._refresh_item_options()

        self.assertEqual(ITEM_WINDOW_GRID, (32, 0, 32, 13))
        self.assertEqual(mock.item_window.add_text.call_count, 6)
        self.assertTrue(mock.item_window.vertical_navigation)
        targets = mock.item_window.set_cursor.call_args.args[0]
        self.assertEqual(len(targets), 3)
        self.assertEqual(tuple(target.key for target in targets), (0, 1, 2))
        mock._refresh_item_guide.assert_called_once_with()

    def test_item_guide_stays_open_while_item_selection_is_active(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ITEM
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState()
        mock.item_guide_window = Mock()
        mock._update_item_selection = Mock()

        mock.update()

        mock.item_guide_window.close_immediately.assert_not_called()
        mock._update_item_selection.assert_called_once_with(
            mock.input_reader.poll.return_value
        )

    def test_item_guide_opens_immediately_in_its_own_window(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.item_candidates = (BattleItemCandidate(items["POTION"]),)
        mock.selected_item_index = 0
        mock.spells = load_mock_spells()
        mock.localizer = Localizer(Language.JAPANESE)
        mock.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        mock.item_guide_window = Mock()
        mock.command_guide_window = Mock()

        mock._refresh_item_guide()

        self.assertEqual(ITEM_GUIDE_WINDOW_GRID, (0, 0, 32, 13))
        mock.item_guide_window.open_immediately.assert_called_once_with()
        self.assertGreater(mock.item_guide_window.add_text.call_count, 0)
        mock.command_guide_window.open_immediately.assert_not_called()

    def test_spell_candidates_are_learned_battle_spells_only(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.spells = load_mock_spells()

        candidates = mock._active_member_spell_candidates()

        self.assertTrue(candidates)
        self.assertTrue(all(spell.on_battle for spell in candidates))
        self.assertTrue(
            all(spell.is_learned_by(mock.party[0]) for spell in candidates)
        )
        self.assertTrue(all(spell.type != "item" for spell in candidates))

    def test_spell_list_uses_the_item_window_width_for_one_school(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.spell_candidates = tuple(
            load_mock_spells()[key] for key in ("FIRE1", "HEALING1", "POISON1")
        )
        mock.localizer = Localizer(Language.JAPANESE)
        mock.spell_window = Mock()
        mock.spell_window.set_cursor.return_value = Mock()
        mock.spell_cursor = None
        mock.spell_scroll_offset = 0
        mock.spell_type = mock.spell_candidates[0].type
        mock._refresh_spell_guide = Mock()

        mock._refresh_spell_options()

        self.assertEqual(SPELL_WINDOW_GRID, (36, 0, 28, 16))
        self.assertEqual(mock.spell_window.add_text.call_count, 1)
        targets = mock.spell_window.set_cursor.call_args.args[0]
        self.assertEqual(
            [(target.x, target.y, target.key) for target in targets],
            [(2, 2, "FIRE1")],
        )

    def test_left_and_right_switch_the_displayed_spell_school(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        spells = load_mock_spells()
        mock.spell_candidates = tuple(
            spells[key]
            for key in (
                "FIRE1",
                "SLOW",
                "SPARK",
                "FREEZE1",
                "HEALING1",
                "PROTECTION",
                "CURE",
                "SILENCE",
                "POISON1",
                "SLEEP",
                "ARMOR BREAK",
                "FADE",
            )
        )
        mock.spell_scroll_offset = 0
        mock.spell_cursor = None
        mock.spell_type = spells["FIRE1"].type
        mock.localizer = Localizer(Language.JAPANESE)
        mock.spell_window = Window(*SPELL_WINDOW_GRID)
        mock._refresh_spell_guide = Mock()

        mock._refresh_spell_options()
        self.assertTrue(mock._move_spell(Direction.RIGHT))

        self.assertIs(mock.spell_type, spells["HEALING1"].type)
        self.assertEqual(
            [target.key for target in mock.spell_cursor.targets],
            ["HEALING1", "PROTECTION", "CURE", "SILENCE"],
        )

    def test_spell_mp_window_overlays_the_guide_bottom_right(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.spell_candidates = (load_mock_spells()["FIRE1"],)
        mock.spell_cursor = Mock(selected_key="FIRE1")
        mock.localizer = Localizer(Language.JAPANESE)
        mock.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        mock.spell_guide_window = Mock()
        mock.spell_mp_window = Mock()

        mock._refresh_spell_guide()

        self.assertEqual(SPELL_GUIDE_WINDOW_GRID, (0, 0, 36, 16))
        self.assertEqual(SPELL_MP_WINDOW_GRID, (20, 9, 16, 7))
        mock.spell_guide_window.open_immediately.assert_called_once_with()
        mock.spell_mp_window.open_immediately.assert_called_once_with()
        self.assertEqual(mock.spell_guide_window.add_text.call_count, 3)
        self.assertEqual(mock.spell_guide_window.add_text.call_args_list[2].args[2], 11)
        self.assertEqual(
            mock.spell_mp_window.add_text.call_args.args[0],
            ascii_to_fullwidth(f"ＭＰ {mock.party[0].mp:03d}"),
        )

    def test_using_a_spell_spends_mp_and_finishes_the_turn(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        spell = load_mock_spells()["FIRE1"]
        mock.spell_candidates = (spell,)
        mock.spell_cursor = Mock(selected_key=spell.key)
        mock._complete_current_turn = Mock()
        before_mp = mock.party[0].mp

        self.assertTrue(mock._use_selected_spell())
        self.assertEqual(mock.party[0].mp, before_mp - spell.mp)
        mock._complete_current_turn.assert_called_once_with()

    def test_using_a_breaking_consumable_removes_it_after_selection(self) -> None:
        items = load_mock_items()
        potion = items["POTION"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.item_candidates = (BattleItemCandidate(potion),)
        mock.selected_item_index = 0
        mock.active_party_index = 0
        mock.spells = load_mock_spells()
        from systems import InventorySystem

        mock.inventory_system = InventorySystem.with_one_each(items)
        mock._complete_current_turn = Mock()

        self.assertTrue(mock._use_selected_item())
        self.assertEqual(mock.inventory_system.quantity(potion), 0)
        mock._complete_current_turn.assert_called_once_with()

    def test_equipment_without_a_use_effect_stays_selectable_but_is_not_used(self) -> None:
        items = load_mock_items()
        dagger = items["DAGGER"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.item_candidates = (
            BattleItemCandidate(dagger, EquipmentSlot.RIGHT),
        )
        mock.selected_item_index = 0
        mock.active_party_index = 0
        mock.spells = load_mock_spells()
        mock._complete_current_turn = Mock()

        self.assertFalse(mock._use_selected_item())
        mock._complete_current_turn.assert_not_called()

    def test_defense_persists_until_the_member_next_becomes_active(self) -> None:
        visual = BattleMockCharacter(
            SimpleNamespace(definition=SimpleNamespace(key="Fiora")),
            0,
            0,
            0,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 0
        mock.defending_party_indexes = set()
        mock.selected_command = None
        mock._complete_current_turn = Mock()

        self.assertTrue(mock._begin_defense())
        self.assertEqual(mock.defending_party_indexes, {0})
        self.assertIs(mock.selected_command, BattleCommand.DEFEND)
        mock._complete_current_turn.assert_called_once_with()

        mock.timeline = (visual,)
        mock.party_visuals = (visual,)
        mock.phase = BattleMockPhase.TIMELINE
        mock.command_cursor = Mock()
        mock.command_window = Mock()
        mock._refresh_command_options = Mock()
        mock._refresh_party_text_colors = Mock()

        mock._activate_timeline_head()

        self.assertEqual(mock.defending_party_indexes, set())
        self.assertIs(mock.phase, BattleMockPhase.COMMAND)

    def test_spell_command_opens_spell_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock(selected_key="spell")
        mock.command_window = Mock(is_closed=False, is_open=True)
        mock.selected_command = None
        mock._begin_spell_selection = Mock(return_value=True)
        mock._complete_current_turn = Mock()

        mock.update()

        mock._begin_spell_selection.assert_called_once_with()
        mock._complete_current_turn.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)

    def test_menu_input_restarts_the_mock_from_any_phase(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.SPELL
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            menu=InputButton(triggered=True, held=True)
        )
        mock._restart_battle_mock = Mock()

        mock.update()

        mock._restart_battle_mock.assert_called_once_with()

    def test_battle_bgm_restarts_from_the_beginning_for_each_mock_reset(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.bgm = Mock()

        mock._restart_battle_bgm()

        mock.bgm.stop.assert_called_once_with()
        mock.bgm.play.assert_called_once_with(BATTLE_BGM_ID)

    def test_timeline_cycles_through_every_combatant_and_returns_actor_to_tail(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        members = tuple(
            SimpleNamespace(definition=SimpleNamespace(key=key))
            for key in BATTLE_MOCK_PARTY_CHARACTER_KEYS
        )
        mock.party_visuals = tuple(
            BattleMockCharacter(member, index * 16, 0, index)
            for index, member in enumerate(members)
        )
        monsters = tuple(
            BattleMockMonster(
                key=key,
                names={},
                image_id=f"n-{index + 1}",
                width=64,
                height=64,
                icon_x=128 if key == "Giant Spider" else 224,
                icon_y=16,
                is_front_row=key == "Coyote",
                state=MonsterBattleState(max_hp=2),
            )
            for index, key in enumerate(BATTLE_MOCK_MONSTER_KEYS)
        )
        mock.monsters = monsters
        initial_timeline = mock.party_visuals + monsters
        mock.timeline = initial_timeline
        mock.active_party_index = 0
        mock.phase = BattleMockPhase.INITIAL
        mock.command_cursor = SimpleNamespace(active=True)
        mock.command_window = Mock()
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock.defending_party_indexes = set()
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

        for expected_index in range(1, len(members)):
            mock._advance_timeline()
            self.assertIs(mock.timeline[0], mock.party_visuals[expected_index])
            self.assertEqual(mock.active_party_index, expected_index)
            self.assertIs(mock.phase, BattleMockPhase.COMMAND)
            self.assertEqual(
                [texts[0].color for texts in mock.party_status_texts],
                [
                    5 if index == expected_index else 4
                    for index in range(len(members))
                ],
            )

        mock._advance_timeline()

        self.assertIs(mock.timeline[0], monsters[0])
        self.assertIs(mock.timeline[-1], mock.party_visuals[-1])
        self.assertEqual(mock.command_window.open.call_count, len(members) - 1)
        self.assertIsNone(mock.active_party_index)
        self.assertIs(mock.phase, BattleMockPhase.MONSTER_ACTION)
        self.assertEqual(mock.blinking_monster_index, 0)
        self.assertEqual(
            mock.monster_blink_frames_remaining,
            MONSTER_BLINK_FRAME_COUNT,
        )
        self.assertEqual(
            [texts[0].color for texts in mock.party_status_texts],
            [4, 4, 4],
        )
        mock.command_window.close_immediately.assert_called_once_with()

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

        self.assertIs(mock.timeline[0], monsters[1])
        self.assertIs(mock.timeline[-1], monsters[0])
        self.assertEqual(mock.blinking_monster_index, 1)

        for expected_monster_index in range(2, len(monsters)):
            completed_actor = mock.timeline[0]
            mock._advance_timeline()
            self.assertIs(mock.timeline[0], monsters[expected_monster_index])
            self.assertIs(mock.timeline[-1], completed_actor)
            self.assertEqual(
                mock.blinking_monster_index,
                expected_monster_index,
            )

        completed_actor = mock.timeline[0]
        mock._advance_timeline()

        self.assertIs(mock.timeline[0], mock.party_visuals[0])
        self.assertIs(mock.timeline[-1], completed_actor)
        self.assertEqual(mock.timeline, initial_timeline)
        self.assertEqual(mock.active_party_index, 0)
        self.assertIs(mock.phase, BattleMockPhase.COMMAND)
        self.assertEqual(mock.command_window.open.call_count, len(members))
        self.assertEqual(
            mock.command_window.close_immediately.call_count,
            len(monsters) + 1,
        )
        self.assertIsNone(mock.blinking_monster_index)
        self.assertEqual(
            [texts[0].color for texts in mock.party_status_texts],
            [5, 4, 4],
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
        mock.phase = BattleMockPhase.COMMAND

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

    def test_timeline_displays_six_entries_and_brings_seventh_into_view(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.timeline = tuple(
            SimpleNamespace(icon_x=index * 16, icon_y=0)
            for index in range(8)
        )
        mock.timeline_animation_phase = TimelineAnimationPhase.DROP
        mock.timeline_animation_frame = TIMELINE_ANIMATION_FRAME_COUNT // 2

        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()

        icon_calls = blt.call_args_list
        self.assertEqual(len(icon_calls), TIMELINE_VISIBLE_ENTRY_COUNT)
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
        self.assertEqual(blt.call_args_list[-1].args[3], 96)

        mock.timeline_animation_phase = None
        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()

        self.assertEqual(
            [draw_call.args[:2] for draw_call in blt.call_args_list[:-1]],
            [(70 + index * 20, 220) for index in range(6)],
        )
        self.assertEqual(len(blt.call_args_list), TIMELINE_VISIBLE_ENTRY_COUNT + 1)

    def test_timeline_enters_from_right_with_two_frame_stagger(self) -> None:
        self.assertEqual(TIMELINE_ENTRANCE_FRAME_COUNT, 10)
        self.assertEqual(TIMELINE_ENTRANCE_STAGGER_FRAME_COUNT, 2)
        self.assertEqual(TIMELINE_ENTRANCE_COMPLETE_FRAME, 20)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ENTRANCE
        mock.timeline = tuple(
            SimpleNamespace(icon_x=index * 16, icon_y=0)
            for index in range(8)
        )
        mock.timeline_animation_phase = None

        mock.entrance_animation_frame = 0
        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()
        self.assertEqual(
            [entry.args[:2] for entry in blt.call_args_list],
            [(256, 220)],
        )

        mock.entrance_animation_frame = 2
        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()
        self.assertEqual(len(blt.call_args_list), 2)
        self.assertEqual(blt.call_args_list[-1].args[:2], (256, 220))

        mock.entrance_animation_frame = TIMELINE_ENTRANCE_COMPLETE_FRAME
        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()
        self.assertEqual(
            [entry.args[:2] for entry in blt.call_args_list],
            [(70 + index * 20, 220) for index in range(6)],
        )

    def test_monster_blink_uses_da2_six_frame_visibility_cycle(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        image = object()
        mock.monsters = (
            SimpleNamespace(
                key="Giant Spider",
                width=64,
                height=64,
                is_alive=True,
            ),
        )
        mock.monster_images = {"Giant Spider": image}
        mock.blinking_monster_index = 0
        mock.phase = BattleMockPhase.MONSTER_ACTION

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
        self._mock_command_labels(mock)
        new_cursor = Mock()
        mock.command_window.set_cursor.return_value = new_cursor
        mock._active_member_command_options = Mock(
            return_value=(
                BattleCommandOption(BattleCommand.SPELL),
                BattleCommandOption(BattleCommand.DEFEND),
                BattleCommandOption(BattleCommand.ESCAPE),
                BattleCommandOption(BattleCommand.ITEM),
                BattleCommandOption(BattleCommand.FORMATION),
            )
        )

        mock._refresh_command_options()

        self.assertEqual(
            mock.command_window.add_text.call_args_list,
            [
                call("じゅもん", 4, 2),
                call("ぼうぎょ", 4, 5),
                call("にげる", 18, 2),
                call("アイテム", 18, 5),
                call("こうたい", 18, 8),
            ],
        )
        targets = mock.command_window.set_cursor.call_args.args[0]
        self.assertEqual(
            [(target.key, target.x, target.y) for target in targets],
            [
                ("spell", 2, 2),
                ("defend", 2, 5),
                ("escape", 16, 2),
                ("item", 16, 5),
                ("formation", 16, 8),
            ],
        )
        mock.command_window.clear_texts.assert_called_once_with()
        mock.command_window.clear_cursor.assert_called_once_with()
        self.assertIs(mock.command_cursor, new_cursor)

    def test_single_member_defend_uses_the_third_right_column_slot(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_window = Mock()
        self._mock_command_labels(mock)
        mock.command_window.set_cursor.return_value = Mock()
        mock._active_member_command_options = Mock(
            return_value=(
                BattleCommandOption(BattleCommand.ATTACK),
                BattleCommandOption(BattleCommand.SPELL),
                BattleCommandOption(BattleCommand.AIM),
                BattleCommandOption(BattleCommand.ESCAPE),
                BattleCommandOption(BattleCommand.ITEM),
                BattleCommandOption(BattleCommand.DEFEND),
            )
        )

        mock._refresh_command_options()

        self.assertIn(
            call("ぼうぎょ", 18, 8),
            mock.command_window.add_text.call_args_list,
        )

    def test_disabled_formation_is_grey_and_not_selectable(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_window = Mock()
        self._mock_command_labels(mock)
        mock.command_window.set_cursor.return_value = Mock()
        mock._active_member_command_options = Mock(
            return_value=(
                BattleCommandOption(BattleCommand.ATTACK),
                BattleCommandOption(BattleCommand.DEFEND),
                BattleCommandOption(BattleCommand.SPELL),
                BattleCommandOption(BattleCommand.ESCAPE),
                BattleCommandOption(BattleCommand.ITEM),
                BattleCommandOption(BattleCommand.FORMATION, enabled=False),
            )
        )

        mock._refresh_command_options()

        self.assertIn(
            call("こうたい", 18, 8, color=3),
            mock.command_window.add_text.call_args_list,
        )
        targets = mock.command_window.set_cursor.call_args.args[0]
        formation = next(
            target for target in targets if target.key is BattleCommand.FORMATION
        )
        self.assertFalse(formation.selectable)

    def test_each_command_uses_a_battle_text_key(self) -> None:
        self.assertEqual(
            set(COMMAND_TEXT_KEYS),
            set(BattleCommand),
        )
        self.assertTrue(
            all(
                key.startswith("battle.command.")
                for key in COMMAND_TEXT_KEYS.values()
            )
        )
        texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        localizer = Localizer(Language.JAPANESE)
        self.assertTrue(
            all(
                texts.text(key, localizer)
                for key in COMMAND_TEXT_KEYS.values()
            )
        )

    def test_command_guide_waits_at_the_same_command_then_shows_three_lines(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.command_window = Mock(is_open=True)
        mock.command_cursor = Mock(selected_key=BattleCommand.ATTACK)
        mock.command_guide_window = Mock()
        mock.command_guide_command = None
        mock.command_guide_timer = 0
        mock.command_guide_visible = False
        mock._command_guide_lines = Mock(
            return_value=("line one", "line two", "line three", "line four")
        )

        for _frame in range(COMMAND_GUIDE_DELAY_FRAME_COUNT):
            mock._update_command_guide()

        self.assertEqual(COMMAND_GUIDE_DELAY_FRAME_COUNT, 30)
        self.assertIs(mock.command_guide_command, BattleCommand.ATTACK)
        self.assertTrue(mock.command_guide_visible)
        mock.command_guide_window.add_text.assert_has_calls(
            [
                call("line one", COMMAND_GUIDE_TEXT_X, COMMAND_GUIDE_FIRST_Y),
                call(
                    "line two",
                    COMMAND_GUIDE_TEXT_X,
                    COMMAND_GUIDE_FIRST_Y + COMMAND_GUIDE_LINE_SPACING,
                ),
                call(
                    "line three",
                    COMMAND_GUIDE_TEXT_X,
                    COMMAND_GUIDE_FIRST_Y + COMMAND_GUIDE_LINE_SPACING * 2,
                ),
            ]
        )
        self.assertNotIn(
            call(
                "line four",
                COMMAND_GUIDE_TEXT_X,
                COMMAND_GUIDE_FIRST_Y + COMMAND_GUIDE_LINE_SPACING * 3,
            ),
            mock.command_guide_window.add_text.call_args_list,
        )
        mock.command_guide_window.open_immediately.assert_called_once_with()
        mock.command_guide_window.open.assert_not_called()

        mock.command_cursor.selected_key = BattleCommand.FOCUS
        mock._update_command_guide()

        self.assertIs(mock.command_guide_command, BattleCommand.FOCUS)
        self.assertEqual(mock.command_guide_timer, 1)
        self.assertFalse(mock.command_guide_visible)

    def test_guide_reuses_da2_text_and_falls_back_to_new_command_name(self) -> None:
        self.assertEqual(
            COMMAND_GUIDE_TEXT_KEYS[BattleCommand.DEFEND],
            "battle.guide.defend",
        )
        self.assertNotIn(BattleCommand.FOCUS, COMMAND_GUIDE_TEXT_KEYS)
        texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        localizer = Localizer(Language.JAPANESE)
        self.assertEqual(
            texts.lines(COMMAND_GUIDE_TEXT_KEYS[BattleCommand.ATTACK], localizer),
            (
                ascii_to_fullwidth("もっている ぶきで"),
                ascii_to_fullwidth("てきを こうげきする"),
            ),
        )
        self.assertEqual(
            texts.lines(COMMAND_TEXT_KEYS[BattleCommand.FOCUS], localizer),
            ("ためる",),
        )

    def test_formation_walk_swaps_row_and_uses_alternate_sprite(self) -> None:
        party = list(
            load_mock_party(
                load_mock_items(),
                load_mock_skills(),
                character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
                internal_level=MAX_INTERNAL_LEVEL,
            )
        )
        for member in party:
            member.formation_row = FormationRow.FRONT
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = tuple(party)
        mock.party_visuals = tuple(
            SimpleNamespace(member=member)
            for member in party
        )
        mock.monsters = tuple(
            SimpleNamespace(is_front_row=True)
            for _index in range(2)
        )
        mock.active_party_index = 0
        mock.phase = BattleMockPhase.COMMAND
        mock.selected_command = None
        mock.command_cursor = Mock(active=True)
        mock.command_window = Mock()
        mock._complete_current_turn = Mock()

        self.assertTrue(mock._begin_formation_change())

        self.assertIs(party[0].formation_row, FormationRow.BACK)
        self.assertIs(mock.phase, BattleMockPhase.FORMATION)
        self.assertEqual(mock.formation_start_x, 156)
        self.assertEqual(mock.formation_destination_x, 172)
        self.assertEqual(mock._party_draw_position(0), (156, 64))
        self.assertEqual(mock._party_sprite_source_x(0), 0)
        mock.formation_animation_frame = FORMATION_WALK_PATTERN_FRAME_COUNT
        self.assertEqual(
            mock._party_sprite_source_x(0),
            FORMATION_SPRITE_STEP_X,
        )
        self.assertEqual(mock._party_draw_position(0), (160, 64))
        mock.formation_animation_frame = 0

        for _frame in range(FORMATION_MOVE_FRAME_COUNT):
            mock._update_formation_animation()

        self.assertIsNone(mock.formation_actor_index)
        mock._complete_current_turn.assert_called_once_with()
        mock.command_window.close_immediately.assert_called_once_with()

    def test_disabled_formation_does_not_start_animation(self) -> None:
        party = list(
            load_mock_party(
                load_mock_items(),
                load_mock_skills(),
                character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
                internal_level=MAX_INTERNAL_LEVEL,
            )
        )
        party[0].formation_row = FormationRow.BACK
        party[1].formation_row = FormationRow.BACK
        party[2].formation_row = FormationRow.FRONT
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = tuple(party)
        mock.monsters = tuple(
            SimpleNamespace(is_front_row=True)
            for _index in range(2)
        )
        mock.active_party_index = 2
        mock.command_window = Mock()

        self.assertFalse(mock._begin_formation_change())

        self.assertIs(party[2].formation_row, FormationRow.FRONT)
        mock.command_window.close_immediately.assert_not_called()

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
        mock.command_window.close_immediately.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)
        self.assertTrue(mock.command_cursor.active)
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
        mock.command_window.close_immediately.assert_not_called()
        mock.command_window.open.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)

    def test_escape_command_always_starts_confirmation(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock(selected_key="escape")
        mock.command_window = Mock(is_closed=False, is_open=True)
        mock.selected_command = None
        mock._begin_escape_confirmation = Mock()
        mock._complete_current_turn = Mock()

        mock.update()

        mock._begin_escape_confirmation.assert_called_once_with()
        mock._complete_current_turn.assert_not_called()

    def test_escape_confirmation_closes_command_and_defaults_to_yes(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.selected_command = None
        mock.command_cursor = Mock(active=True)
        mock.command_window = Mock()
        mock.escape_cursor = Mock(active=False)

        mock._begin_escape_confirmation()

        self.assertIs(mock.phase, BattleMockPhase.ESCAPE_CONFIRMATION)
        self.assertEqual(mock.selected_command, "escape")
        self.assertFalse(mock.command_cursor.active)
        self.assertTrue(mock.escape_cursor.active)
        mock.command_window.close_immediately.assert_called_once_with()
        mock.escape_cursor.select_key.assert_called_once_with("yes")

    def test_confirming_escape_yes_marks_the_current_member_without_running(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.escape_cursor = Mock(selected_key="yes")
        mock.command_window = Mock(is_closed=True)
        mock._accept_escape_confirmation = Mock()

        with patch("tools.screen_mocks.battle.pyxel.quit") as quit_game:
            mock._update_escape_confirmation(
                InputState(confirm=InputButton(triggered=True, held=True))
            )

        mock._accept_escape_confirmation.assert_called_once_with()
        quit_game.assert_not_called()

    def test_first_escape_member_reverses_and_completes_their_turn(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = (object(), object(), object())
        mock.active_party_index = 0
        mock.escaping_party_indexes = set()
        mock.defending_party_indexes = {0}
        mock.escape_cursor = Mock(active=True)
        mock._complete_current_turn = Mock()
        mock._begin_escape_animation = Mock()

        mock._accept_escape_confirmation()

        self.assertEqual(mock.escaping_party_indexes, {0})
        self.assertEqual(mock.defending_party_indexes, set())
        self.assertFalse(mock.escape_cursor.active)
        mock._complete_current_turn.assert_called_once_with()
        mock._begin_escape_animation.assert_not_called()

    def test_later_party_turns_automatically_join_escape_state(self) -> None:
        visuals = tuple(
            BattleMockCharacter(
                SimpleNamespace(definition=SimpleNamespace(key=str(index))),
                0,
                0,
                index,
            )
            for index in range(3)
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.timeline = (visuals[1],)
        mock.party_visuals = visuals
        mock.escaping_party_indexes = {0}
        mock.defending_party_indexes = {1}
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.blinking_monster_index = 0
        mock.monster_blink_frames_remaining = 1
        mock._start_timeline_animation = Mock()
        mock._begin_escape_animation = Mock()

        mock._activate_timeline_head()

        self.assertEqual(mock.escaping_party_indexes, {0, 1})
        self.assertEqual(mock.defending_party_indexes, set())
        self.assertEqual(mock.active_party_index, 1)
        self.assertIsNone(mock.blinking_monster_index)
        mock._start_timeline_animation.assert_called_once_with()
        mock._begin_escape_animation.assert_not_called()
        mock.command_window.open.assert_not_called()

    def test_last_party_member_starts_run_when_everyone_is_ready(self) -> None:
        visuals = tuple(
            BattleMockCharacter(
                SimpleNamespace(definition=SimpleNamespace(key=str(index))),
                0,
                0,
                index,
            )
            for index in range(3)
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.timeline = (visuals[2],)
        mock.party_visuals = visuals
        mock.escaping_party_indexes = {0, 1}
        mock.defending_party_indexes = set()
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock._start_timeline_animation = Mock()
        mock._begin_escape_animation = Mock()

        mock._activate_timeline_head()

        self.assertEqual(mock.escaping_party_indexes, {0, 1, 2})
        mock._begin_escape_animation.assert_called_once_with()
        mock._start_timeline_animation.assert_not_called()
        mock.command_window.open.assert_not_called()

    def test_escape_animation_hides_selection_and_stops_bgm(self) -> None:
        members = (
            SimpleNamespace(formation_row=FormationRow.FRONT),
            SimpleNamespace(formation_row=FormationRow.BACK),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = tuple(
            SimpleNamespace(member=member)
            for member in members
        )
        mock.phase = BattleMockPhase.ESCAPE_CONFIRMATION
        mock.active_party_index = 0
        mock.command_cursor = Mock(active=False)
        mock.escape_cursor = Mock(active=True)
        mock._refresh_party_text_colors = Mock()
        mock.bgm = Mock()

        mock._begin_escape_animation()

        self.assertIs(mock.phase, BattleMockPhase.ESCAPE_MESSAGE)
        self.assertEqual(mock.escape_animation_frame, 0)
        self.assertEqual(mock.escape_start_x, (156, 176))
        self.assertFalse(mock.escape_fade.is_active)
        self.assertEqual(mock.escape_fade.visible_rate, 1.0)
        self.assertFalse(mock.escape_fade_covered)
        self.assertIsNone(mock.active_party_index)
        self.assertFalse(mock.command_cursor.active)
        self.assertFalse(mock.escape_cursor.active)
        mock._refresh_party_text_colors.assert_called_once_with()
        mock.bgm.stop.assert_called_once_with()

    def test_escape_message_keeps_running_until_a_button_is_pressed(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ESCAPE_MESSAGE
        mock.escape_animation_frame = 0
        mock.escape_fade = Mock()

        mock._update_escape_message(InputState())

        self.assertIs(mock.phase, BattleMockPhase.ESCAPE_MESSAGE)
        self.assertEqual(mock.escape_animation_frame, 1)
        mock.escape_fade.start.assert_not_called()

        mock._update_escape_message(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertIs(mock.phase, BattleMockPhase.ESCAPE)
        self.assertEqual(mock.escape_animation_frame, 2)
        mock.escape_fade.start.assert_called_once_with()

    def test_escape_message_accepts_cancel_button_for_acknowledgement(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ESCAPE_MESSAGE
        mock.escape_animation_frame = 0
        mock.escape_fade = Mock()

        mock._update_escape_message(
            InputState(cancel=InputButton(triggered=True, held=True))
        )

        self.assertIs(mock.phase, BattleMockPhase.ESCAPE)
        mock.escape_fade.start.assert_called_once_with()

    def test_member_waiting_to_escape_faces_right_without_walking(self) -> None:
        member = SimpleNamespace(formation_row=FormationRow.FRONT)
        visual = SimpleNamespace(member=member, battle_sprite=2)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = (visual,)
        mock.character_sprites = object()
        mock.phase = BattleMockPhase.TIMELINE
        mock.escaping_party_indexes = {0}

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party()

        blt.assert_called_once_with(
            156,
            64,
            mock.character_sprites,
            0,
            64,
            -16,
            32,
            1,
        )

    def test_escape_run_uses_da2_speed_walk_pattern_and_right_facing_sprite(
        self,
    ) -> None:
        member = SimpleNamespace(formation_row=FormationRow.FRONT)
        visual = SimpleNamespace(member=member, battle_sprite=2)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = (visual,)
        mock.character_sprites = object()
        mock.phase = BattleMockPhase.ESCAPE
        mock.escape_start_x = (156,)
        mock.escape_animation_frame = ESCAPE_RUN_PATTERN_FRAME_COUNT

        self.assertGreater(ESCAPE_RUN_SPEED, 0)
        self.assertEqual(
            mock._party_draw_position(0),
            (
                156 + ESCAPE_RUN_SPEED * ESCAPE_RUN_PATTERN_FRAME_COUNT,
                64,
            ),
        )
        self.assertEqual(mock._party_sprite_source_x(0), 16)

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party()

        blt.assert_called_once_with(
            156 + ESCAPE_RUN_SPEED * ESCAPE_RUN_PATTERN_FRAME_COUNT,
            64,
            mock.character_sprites,
            16,
            64,
            -16,
            32,
            1,
        )

    def test_escape_run_quits_after_every_member_reaches_da2_destination(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = (object(), object())
        mock.escape_start_x = (
            ESCAPE_RUN_DESTINATION_X - ESCAPE_RUN_SPEED,
            ESCAPE_RUN_DESTINATION_X - ESCAPE_RUN_SPEED * 2,
        )
        mock.escape_animation_frame = 0
        mock.escape_fade_covered = True
        mock._update_escape_fade = Mock()

        with patch("tools.screen_mocks.battle.pyxel.quit") as quit_game:
            mock._update_escape_animation()
            quit_game.assert_not_called()
            mock._update_escape_animation()

        self.assertEqual(mock.escape_animation_frame, 2)
        self.assertEqual(mock._update_escape_fade.call_count, 2)
        quit_game.assert_called_once_with()

    def test_escape_fade_reaches_black_and_does_not_fade_back_in(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.escape_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        mock.escape_fade.start()
        mock.escape_fade_covered = False
        mock.palette_shifter = Mock(base_colors=(0x000000,))

        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_escape_fade()

        self.assertTrue(mock.escape_fade_covered)
        self.assertEqual(mock.escape_fade.visible_rate, 0.0)
        mock.palette_shifter.set_global_mix.assert_called_with(
            base_rate=0.0,
            target_color=0x000000,
        )
        update_count = mock.palette_shifter.set_global_mix.call_count

        mock._update_escape_fade()

        self.assertEqual(
            mock.palette_shifter.set_global_mix.call_count,
            update_count,
        )

    def test_escape_fade_starts_only_after_escape_message_acknowledgement(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.escape_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        mock.escape_fade_covered = False
        mock.palette_shifter = Mock(base_colors=(0x000000,))

        self.assertFalse(mock.escape_fade.is_active)
        mock.palette_shifter.set_global_mix.assert_not_called()

        mock.escape_fade.start()
        mock._update_escape_fade()

        self.assertTrue(mock.escape_fade.is_active)
        mock.palette_shifter.set_global_mix.assert_called_once()

    def test_escape_no_returns_to_command_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ESCAPE_CONFIRMATION
        mock.selected_command = "escape"
        mock.escape_cursor = Mock(selected_key="no", active=True)
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock(is_closed=True)

        mock._update_escape_confirmation(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertIs(mock.phase, BattleMockPhase.COMMAND)
        self.assertIsNone(mock.selected_command)
        self.assertFalse(mock.escape_cursor.active)
        self.assertTrue(mock.command_cursor.active)
        mock.command_window.open.assert_called_once_with()

    def test_monster_names_only_draw_for_targeting_and_button_wait(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        base_window = Mock()
        monster_name = Mock()
        mock.windows = [base_window]
        mock.party_status_windows = []
        mock.monsters = (SimpleNamespace(is_alive=True),)
        mock.monster_name_windows = [monster_name]
        mock.escape_message_window = Mock()
        mock.escape_started_message_window = Mock()
        mock.escape_choice_window = Mock()
        mock.command_window = Mock(is_closed=False)

        mock.phase = BattleMockPhase.COMMAND
        mock._draw_windows()
        monster_name.draw.assert_not_called()

        mock.phase = BattleMockPhase.TARGET
        mock._draw_windows()
        monster_name.draw.assert_called_once_with()

        monster_name.reset_mock()
        mock.phase = BattleMockPhase.INITIAL
        mock.command_window.is_closed = True
        mock._draw_windows()
        monster_name.draw.assert_called_once_with()

        monster_name.reset_mock()
        mock.phase = BattleMockPhase.ESCAPE_CONFIRMATION
        mock.command_window.is_closed = False
        mock._draw_windows()
        monster_name.draw.assert_not_called()
        mock.escape_message_window.draw.assert_not_called()
        mock.escape_choice_window.draw.assert_not_called()

        mock.command_window.is_closed = True
        mock._draw_windows()
        mock.escape_message_window.draw.assert_called_once_with()
        mock.escape_choice_window.draw.assert_called_once_with()

        mock.phase = BattleMockPhase.ESCAPE_MESSAGE
        mock._draw_windows()
        mock.escape_started_message_window.draw.assert_called_once_with()

    def test_monster_name_colors_follow_target_availability_and_button_wait(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monster_name_windows = [Mock() for _index in range(3)]
        for window in mock.monster_name_windows:
            window.add_text.side_effect = (
                lambda text, x, y, **kwargs: WindowText(
                    text,
                    x,
                    y,
                    **kwargs,
                )
            )
        mock.monster_name_texts = [
            WindowText(f"monster-{index}", 0, 0, color=4)
            for index in range(3)
        ]
        mock.phase = BattleMockPhase.TARGET
        mock.selectable_target_indexes = (0, 2)

        mock._refresh_monster_name_colors()

        self.assertEqual(
            [placement.color for placement in mock.monster_name_texts],
            [5, 4, 5],
        )

        mock.phase = BattleMockPhase.INITIAL
        mock.selectable_target_indexes = ()
        mock._refresh_monster_name_colors()

        self.assertEqual(
            [placement.color for placement in mock.monster_name_texts],
            [5, 5, 5],
        )

    def test_party_status_appears_after_every_party_member_lands(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        command_window = Mock()
        party_status_windows = [Mock(), Mock(), Mock()]
        mock.windows = [command_window, *party_status_windows]
        mock.party_status_windows = party_status_windows
        mock.monster_name_windows = []
        mock.escape_message_window = Mock()
        mock.escape_started_message_window = Mock()
        mock.escape_choice_window = Mock()
        mock.command_window = command_window
        mock.phase = BattleMockPhase.ENTRANCE

        mock.entrance_animation_frame = PARTY_ENTRANCE_COMPLETE_FRAME - 1
        mock._draw_windows()
        command_window.draw.assert_called_once_with()
        for status_window in party_status_windows:
            status_window.draw.assert_not_called()

        mock.entrance_animation_frame = PARTY_ENTRANCE_COMPLETE_FRAME
        mock._draw_windows()
        for status_window in party_status_windows:
            status_window.draw.assert_called_once_with()

        for status_window in party_status_windows:
            status_window.reset_mock()
        mock.phase = BattleMockPhase.ESCAPE_MESSAGE
        mock._draw_windows()
        for status_window in party_status_windows:
            status_window.draw.assert_not_called()

        mock.phase = BattleMockPhase.ESCAPE
        mock._draw_windows()
        for status_window in party_status_windows:
            status_window.draw.assert_not_called()

    def test_cancel_input_closes_command_and_returns_to_button_wait(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock(active=True)
        mock.target_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.selected_command = "defend"
        mock.selectable_target_indexes = (2, 3, 4)
        mock.selected_target_index = 4
        mock._refresh_monster_name_colors = Mock()

        with patch("tools.screen_mocks.battle.pyxel.quit") as quit_game:
            mock.update()

        quit_game.assert_not_called()
        self.assertIs(mock.phase, BattleMockPhase.INITIAL)
        self.assertFalse(mock.command_cursor.active)
        self.assertIsNone(mock.selected_command)
        self.assertIsNone(mock.selected_target_index)
        mock.command_window.close_immediately.assert_called_once_with()
        mock._refresh_monster_name_colors.assert_called_once_with()
        mock.command_window.update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
