from __future__ import annotations

import unittest
from unittest.mock import Mock

from tools._bootstrap import APP_ROOT
from game import Game
from input import Direction, InputButton, InputDevice, InputState
from rendering import FadeThroughBlack
from resources import FontResources
from state import Language, Settings
from text_catalog import TextCatalog
from ui.field_menu_guide import FIELD_MENU_GUIDE_IDLE_FRAMES, FieldMenuGuide
from ui.tagged_text import tagged_text_width


class FieldMenuGuideTest(unittest.TestCase):
    def guide(self) -> FieldMenuGuide:
        return FieldMenuGuide(
            texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
            fonts=FontResources(),
        )

    def wait(self, guide: FieldMenuGuide, frames: int = FIELD_MENU_GUIDE_IDLE_FRAMES,
             *, state: InputState = InputState(), language: Language = Language.JAPANESE) -> None:
        for _ in range(frames):
            guide.update(state, idle=True, language=language)

    def game(self) -> Game:
        game = Game.__new__(Game)
        game.settings = Settings()
        game.field_menu_guide = self.guide()
        game.showing_field = True
        game.field = Mock(is_moving=False, is_walking=False)
        game.fade = FadeThroughBlack()
        return game

    def test_appears_at_one_second_and_does_not_recreate_visible_window(self) -> None:
        guide = self.guide()
        self.wait(guide, FIELD_MENU_GUIDE_IDLE_FRAMES - 1)
        self.assertIsNone(guide.window)
        self.wait(guide, 1)
        window = guide.window
        self.assertIsNotNone(window)
        self.wait(guide, 120)
        self.assertIs(guide.window, window)
        self.assertEqual(guide.idle_frames, FIELD_MENU_GUIDE_IDLE_FRAMES)

    def test_all_languages_and_devices_show_only_menu_hint_at_top_right(self) -> None:
        for language in Language:
            for device, icon in ((InputDevice.KEYBOARD, "%KEY_S%"),
                                 (InputDevice.GAMEPAD, "%GAMEPAD_X%")):
                with self.subTest(language=language, device=device):
                    guide = self.guide()
                    self.wait(guide, state=InputState(device=device), language=language)
                    window = guide.window
                    self.assertTrue(window.transparent)
                    self.assertIsNone(window.cursor)
                    self.assertEqual(len(window.texts), 1)
                    placement = window.texts[0]
                    self.assertIn(icon, placement.text)
                    self.assertNotIn("%MENU%", placement.text)
                    x, y = window.text_position(placement)
                    width = tagged_text_width(placement.text, placement.font,
                                              font_spans=placement.font_spans)
                    self.assertEqual(x + width, 248)
                    self.assertEqual(y, 4)

    def test_direction_and_all_action_inputs_reset_and_hide_immediately(self) -> None:
        inputs = [InputState(held_direction=Direction.RIGHT),
                  InputState(navigation=Direction.DOWN)]
        for action in ("confirm", "cancel", "menu", "interruption", "previous_page", "next_page"):
            inputs.extend((InputState(**{action: InputButton(held=True)}),
                           InputState(**{action: InputButton(triggered=True)})))
        for state in inputs:
            with self.subTest(state=state):
                guide = self.guide()
                self.wait(guide)
                guide.update(state, idle=True, language=Language.JAPANESE)
                self.assertIsNone(guide.window)
                self.assertEqual(guide.idle_frames, 0)
                self.wait(guide, FIELD_MENU_GUIDE_IDLE_FRAMES - 1)
                self.assertIsNone(guide.window)

    def test_partial_wait_is_discarded_when_field_is_not_idle(self) -> None:
        guide = self.guide()
        self.wait(guide, 40)
        guide.update(InputState(), idle=False, language=Language.JAPANESE)
        self.assertEqual(guide.idle_frames, 0)
        self.wait(guide, 20)
        self.assertIsNone(guide.window)

    def test_device_or_language_change_refreshes_hint_without_changing_timer(self) -> None:
        guide = self.guide()
        self.wait(guide)
        first = guide.window
        guide.update(InputState(device=InputDevice.GAMEPAD), idle=True, language=Language.ENGLISH)
        self.assertIsNot(guide.window, first)
        self.assertIn("%GAMEPAD_X%", guide.window.texts[0].text)
        self.assertEqual(guide.idle_frames, FIELD_MENU_GUIDE_IDLE_FRAMES)

    def test_modal_field_flows_and_fades_hide_and_reset_hint(self) -> None:
        for attribute in (
            "start_screen", "shop_screen", "battle_scene", "game_menu", "event_runner",
            "event_message", "treasure_message", "field_condition_message",
            "encounter_transition", "battle_return_fade", "pending_screen_change",
            "_returning_to_start", "_game_menu_resume_waiting", "fade",
        ):
            with self.subTest(flow=attribute):
                game = self.game()
                self.wait(game.field_menu_guide)
                if attribute == "fade":
                    game.fade.start()
                else:
                    setattr(game, attribute, True)
                self.assertFalse(game._field_menu_guide_available())
                game._update_field_menu_guide(InputState())
                self.assertIsNone(game.field_menu_guide.window)
                self.assertEqual(game.field_menu_guide.idle_frames, 0)

    def test_walking_and_moving_reset_timer_even_after_input_is_released(self) -> None:
        for attribute in ("is_moving", "is_walking"):
            with self.subTest(movement=attribute):
                game = self.game()
                self.wait(game.field_menu_guide)
                setattr(game.field, attribute, True)
                game._update_field_menu_guide(InputState())
                self.assertIsNone(game.field_menu_guide.window)

    def test_game_updates_idle_hint_and_menu_input_hides_it(self) -> None:
        game = self.game()
        game.input_reader = Mock()
        game.input_reader.poll.return_value = InputState()
        game.alert = Mock()
        game._update_fade = Mock(return_value=False)
        game._update_field = Mock()
        for _ in range(FIELD_MENU_GUIDE_IDLE_FRAMES):
            game.update()
        self.assertIsNotNone(game.field_menu_guide.window)
        game.input_reader.poll.return_value = InputState(menu=InputButton(triggered=True, held=True))
        game.update()
        self.assertIsNone(game.field_menu_guide.window)

    def test_returning_to_field_requires_a_new_full_wait(self) -> None:
        game = self.game()
        self.wait(game.field_menu_guide)
        game.showing_field = False
        game._update_field_menu_guide(InputState())
        game.showing_field = True
        for _ in range(FIELD_MENU_GUIDE_IDLE_FRAMES - 1):
            game._update_field_menu_guide(InputState())
        self.assertIsNone(game.field_menu_guide.window)
        game._update_field_menu_guide(InputState())
        self.assertIsNotNone(game.field_menu_guide.window)

    def test_map_reset_discards_hint_and_idle_time(self) -> None:
        game = self.game()
        self.wait(game.field_menu_guide)
        game.current_map = None
        game._reset_field_actors()
        self.assertIsNone(game.field_menu_guide.window)
        self.assertEqual(game.field_menu_guide.idle_frames, 0)

    def test_draw_does_not_advance_timer_or_draw_a_hidden_hint(self) -> None:
        guide = self.guide()
        guide.draw()
        self.assertEqual(guide.idle_frames, 0)
        guide.window = Mock()
        guide.draw()
        guide.window.draw.assert_called_once()
        self.assertEqual(guide.idle_frames, 0)


if __name__ == "__main__":
    unittest.main()
