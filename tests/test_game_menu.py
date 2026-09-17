from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from game import Game
from input import Direction, InputButton, InputState
from rendering import FadeThroughBlack
from resources import FontResources
from scenes import BattleScene
from state import Language, Settings
from text_catalog import TextCatalog
from ui.game_menu import GameMenuAction, GameMenuOverlay
from ui.tagged_text import tagged_text_width


PRESS = InputButton(triggered=True, held=True)
HOLD = InputButton(held=True)


class GameMenuTest(unittest.TestCase):
    def game(self) -> Game:
        game = Game.__new__(Game)
        game.settings = Settings()
        game.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        game.fonts = Mock()
        game.fonts.baseline_offset_for.return_value = 0
        game.fonts.font_for.return_value.text_width.return_value = 96
        game.bgm = Mock()
        game.alert = Mock()
        game.input_reader = Mock()
        game.fade = FadeThroughBlack()
        game._update_fade = Mock(return_value=False)
        game._return_to_start_screen = Mock()
        return game

    def update(self, game: Game, state: InputState = InputState()) -> None:
        game.input_reader.poll.return_value = state
        game.update()

    def open(self, game: Game) -> GameMenuOverlay:
        self.update(game, InputState(interruption=PRESS))
        menu = game.game_menu
        self.assertIsNotNone(menu)
        self.assertIs(menu.cursor.selected_key, GameMenuAction.RESUME)
        self.update(game)  # Release opening buttons.
        return menu

    def test_interrupts_every_screen_and_restores_the_same_instance(self) -> None:
        for attribute in (
            "battle_scene", "start_screen", "shop_screen", "item_screen",
            "spell_screen", "equipment_screen", "status_screen",
            "information_screen", "save_screen", "debug_screen",
        ):
            with self.subTest(screen=attribute):
                game = self.game()
                screen = Mock()
                screen.update.return_value = False
                setattr(game, attribute, screen)
                self.open(game)
                for _ in range(3):
                    self.update(game)
                screen.update.assert_not_called()
                game.alert.update.assert_not_called()
                game.bgm.update.assert_not_called()
                game.bgm.pause.assert_called_once()
                self.update(game, InputState(cancel=PRESS))
                self.assertIsNone(game.game_menu)
                self.update(game, InputState(cancel=HOLD))
                screen.update.assert_not_called()
                game.bgm.resume.assert_not_called()
                self.update(game)
                game.bgm.resume.assert_called_once()
                self.update(game)
                screen.update.assert_called_once_with(InputState())
                self.assertIs(getattr(game, attribute), screen)

    def test_event_message_field_movement_and_treasure_timers_are_frozen(self) -> None:
        game = self.game()
        game.showing_field = True
        game.field = Mock()
        game.field_actors = Mock()
        game.field_birds = Mock()
        game.event_runner = object()
        game.event_message = Mock()
        game._update_event = Mock()
        self.open(game)
        self.update(game, InputState(confirm=PRESS))
        game.field.update.assert_not_called()
        game.field_actors.update_treasure_animations.assert_not_called()
        game.field_birds.update.assert_not_called()
        game.event_message.update.assert_not_called()
        game._update_event.assert_not_called()

    def test_opening_input_is_not_used_to_confirm_or_immediately_close(self) -> None:
        game = self.game()
        self.update(game, InputState(interruption=PRESS, confirm=PRESS))
        self.update(game, InputState(interruption=HOLD, confirm=HOLD))
        self.update(game, InputState(confirm=HOLD))
        self.assertIsNotNone(game.game_menu)
        self.update(game)
        self.update(game, InputState(interruption=PRESS))
        self.assertIsNone(game.game_menu)

    def test_title_return_waits_for_release_without_resuming_old_bgm(self) -> None:
        game = self.game()
        self.open(game)
        self.update(game, InputState(navigation=Direction.DOWN))
        self.update(game, InputState(confirm=PRESS))
        self.update(game, InputState(confirm=HOLD, interruption=HOLD))
        game._return_to_start_screen.assert_not_called()
        self.update(game)
        game._return_to_start_screen.assert_called_once()
        game.bgm.resume.assert_not_called()

    @patch("game.pyxel.quit")
    def test_quit_is_a_direct_da2_menu_action(self, quit: Mock) -> None:
        game = self.game()
        self.open(game)
        self.update(game, InputState(navigation=Direction.DOWN))
        self.update(game, InputState(navigation=Direction.DOWN))
        self.update(game, InputState(confirm=PRESS))
        quit.assert_called_once()

    def test_transitions_do_not_allow_interruption(self) -> None:
        for attribute in ("fade", "encounter_transition", "battle_return_fade",
                          "_returning_to_start", "battle_scene"):
            with self.subTest(transition=attribute):
                game = self.game()
                if attribute == "fade":
                    game.fade.start()
                elif attribute == "battle_scene":
                    game.battle_scene = Mock(is_transitioning=True)
                else:
                    setattr(game, attribute, True)
                self.assertFalse(game._update_game_menu(InputState(interruption=PRESS)))
                self.assertIsNone(getattr(game, "game_menu", None))
                game.bgm.pause.assert_not_called()

    def test_battle_exposes_all_three_transition_fades(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        for attribute in ("entrance_fade", "escape_fade", "result_transition_fade"):
            setattr(scene, attribute, FadeThroughBlack())
        self.assertFalse(scene.is_transitioning)
        for attribute in ("entrance_fade", "escape_fade", "result_transition_fade"):
            with self.subTest(fade=attribute):
                fade = getattr(scene, attribute)
                fade.start()
                self.assertTrue(scene.is_transitioning)
                for _ in range(2 * fade.frame_count):
                    fade.update()
                self.assertFalse(scene.is_transitioning)

    def test_blocked_press_is_not_reserved_after_transition(self) -> None:
        game = self.game()
        game.start_screen = Mock()
        game.fade.start()
        self.update(game, InputState(interruption=PRESS))
        for _ in range(2 * game.fade.frame_count):
            game.fade.update()
        self.update(game, InputState(interruption=HOLD))
        self.update(game)
        self.assertIsNone(getattr(game, "game_menu", None))
        game.bgm.pause.assert_not_called()
        self.open(game)

    def test_resuming_waits_for_other_actions_but_not_direction(self) -> None:
        game = self.game()
        game.start_screen = Mock()
        self.open(game)
        self.update(game, InputState(cancel=PRESS, next_page=HOLD))
        self.update(game, InputState(next_page=HOLD))
        game.bgm.resume.assert_not_called()
        self.update(game, InputState(held_direction=Direction.RIGHT))
        game.bgm.resume.assert_called_once()
        game.start_screen.update.assert_not_called()

    @patch("game.pyxel")
    def test_menu_draws_without_drawing_suspended_screen(self, pyxel: Mock) -> None:
        game = self.game()
        game.battle_scene = Mock()
        game.game_menu = Mock()
        game.draw()
        game.game_menu.draw.assert_called_once()
        game.battle_scene.draw.assert_not_called()
        pyxel.cls.assert_called_once_with(0)
        pyxel.camera.assert_called_once_with()

    def test_menu_labels_use_current_language(self) -> None:
        for language in Language:
            with self.subTest(language=language):
                game = self.game()
                game.settings = Settings(language=language)
                menu = self.open(game)
                self.assertEqual(len(menu.window.texts), 3)
                self.assertTrue(all(text.text for text in menu.window.texts))

    def test_transparent_menu_centers_left_aligned_text_block_in_each_language(self) -> None:
        for language in Language:
            with self.subTest(language=language):
                game = self.game()
                game.settings = Settings(language=language)
                game.fonts = FontResources()
                menu = self.open(game)
                self.assertTrue(menu.window.transparent)
                self.assertEqual(menu.window.pixel_width, 256)
                block_width = max(
                    tagged_text_width(
                        placement.text, placement.font, font_spans=placement.font_spans,
                    )
                    for placement in menu.window.texts
                )
                left, _y = menu.window.text_position(menu.window.texts[0])
                self.assertLessEqual(abs(2 * left + block_width - 256), 1)
                for placement, target in zip(menu.window.texts, menu.cursor.targets):
                    x, _y = menu.window.text_position(placement)
                    self.assertEqual(x, left)
                    self.assertEqual(target.x, placement.x - 4)
                for expected in (
                    GameMenuAction.RETURN_TITLE, GameMenuAction.QUIT, GameMenuAction.RESUME,
                ):
                    menu.update(InputState(navigation=Direction.DOWN))
                    self.assertIs(menu.cursor.selected_key, expected)
                menu.update(InputState(navigation=Direction.UP))
                self.assertIs(menu.cursor.selected_key, GameMenuAction.QUIT)
                self.assertIs(menu.update(InputState(confirm=PRESS)), GameMenuAction.QUIT)


if __name__ == "__main__":
    unittest.main()
