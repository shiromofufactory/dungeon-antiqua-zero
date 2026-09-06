from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from tools.screen_mocks.battle import (
    BATTLE_MOCK_PARTY_CHARACTER_KEYS,
    BattleScreenMock,
    FormationRow,
    MAX_INTERNAL_LEVEL,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    ascii_to_fullwidth,
)
from tools.screen_mocks._fixtures import load_mock_items, load_mock_party, load_mock_skills
from tools.screen_mocks._runtime import FPS
from input import Direction, InputButton, InputState


class BattleScreenMockTest(unittest.TestCase):
    def test_mock_uses_sixty_fps(self) -> None:
        self.assertEqual(FPS, 60)

    def test_draw_uses_explicit_back_to_front_order(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock._draw_background = Mock()
        mock._draw_party = Mock()
        mock._draw_monsters = Mock()
        mock._draw_timeline = Mock()
        mock._draw_windows = Mock()

        manager = Mock()
        manager.attach_mock(mock._draw_background, "background")
        manager.attach_mock(mock._draw_party, "party")
        manager.attach_mock(mock._draw_monsters, "monsters")
        manager.attach_mock(mock._draw_timeline, "timeline")
        manager.attach_mock(mock._draw_windows, "windows")

        mock.draw()

        self.assertEqual(
            manager.mock_calls,
            [
                call.background(),
                call.party(),
                call.monsters(),
                call.timeline(),
                call.windows(),
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
            [(0, 0), (224, 16), (128, 16), (224, 16), (64, 0), (224, 16)],
        )
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
        mock.timeline = (
            SimpleNamespace(icon_x=224, icon_y=16),
        )

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
                call(74, 212, 0, 88, 16, 8, 8, 1),
            ],
        )

    def test_update_passes_logical_navigation_to_open_command_window(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
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

    def test_second_confirm_obtains_key_and_closes_open_command_window(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
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

        mock.update()

        self.assertEqual(mock.selected_command, "attack")
        mock.command_window.close.assert_called_once_with()
        mock.command_window.open.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)

    def test_cancel_input_quits_before_updating_cursor(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
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
