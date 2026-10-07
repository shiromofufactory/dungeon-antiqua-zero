from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from app.input import InputButton, InputState
from app.member import FacePosition
from app.resources import FontRole
from app.resources.event_messages import EventMessageCatalog
from app.state import Language, Settings
from app.ui.event_message import EventMessageDataError, EventMessageOverlay, MessageOverlay
from app.ui.window import WINDOW_ANIMATION_FRAME_COUNT, WindowState


class EventMessageOverlayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.font = Mock()
        self.fonts = Mock()
        self.fonts.font_for.return_value = self.font
        self.fonts.baseline_offset_for.return_value = 0
        self.faces = object()

    def overlay(
        self,
        *,
        portrait: str | None = None,
        portrait_position: tuple[int, int] | None = None,
        language: Language = Language.JAPANESE,
    ) -> EventMessageOverlay:
        messages = EventMessageCatalog.from_records(
            [
                {
                    "message_id": "sample.hello",
                    **(
                        {"portrait_character_key": portrait}
                        if portrait is not None
                        else {}
                    ),
                    **(
                        {
                            "portrait_x": portrait_position[0],
                            "portrait_y": portrait_position[1],
                        }
                        if portrait_position is not None
                        else {}
                    ),
                    "text_ja": ["こんにちは", "ようこそ"],
                    "text_en": ["Hello", "Welcome"],
                    "text_zhcn": ["你好", "欢迎"],
                }
            ]
        )
        return EventMessageOverlay(
            message_id="sample.hello",
            settings=Settings(language=language),
            messages=messages,
            fonts=self.fonts,
            faces=self.faces,
            face_positions={"Alvan": FacePosition(32, 64)},
        )

    def finish_opening(self, overlay: EventMessageOverlay) -> None:
        for _ in range(WINDOW_ANIMATION_FRAME_COUNT):
            self.assertFalse(overlay.update(InputState()))

    def test_uses_same_large_japanese_font_role_as_site_names(self) -> None:
        overlay = self.overlay()

        self.fonts.font_for.assert_any_call(
            Language.JAPANESE,
            role=FontRole.LARGE,
        )
        self.assertIs(overlay.window.font, self.font)

    def test_line_count_and_spacing_follow_language_font_height(self) -> None:
        messages = EventMessageCatalog.from_records(
            [{
                "message_id": "sample.layout",
                "text_ja": ["日一", "日二", "日三", "日四"],
                "text_en": ["one", "two", "three", "four"],
                "text_zhcn": ["中一", "中二", "中三", "中四"],
            }]
        )

        for language, expected_y_positions in (
            (Language.JAPANESE, (2, 6)),
            (Language.SIMPLIFIED_CHINESE, (2, 6)),
            (Language.ENGLISH, (2, 5, 8)),
        ):
            with self.subTest(language=language):
                overlay = EventMessageOverlay(
                    message_id="sample.layout",
                    settings=Settings(language=language),
                    messages=messages,
                    fonts=self.fonts,
                    faces=self.faces,
                    face_positions={},
                )

                self.assertEqual(
                    tuple(text.y for text in overlay.window.texts),
                    expected_y_positions,
                )

    def test_internal_blank_line_occupies_a_row_and_counts_towards_pagination(self) -> None:
        messages = EventMessageCatalog.from_records([{
            "message_id": "sample.blank_line",
            "text_ja": ["あいうえお", "", "かきくけこ", "さしすせそ"],
            "text_en": [], "text_zhcn": [],
        }])
        overlay = EventMessageOverlay(
            message_id="sample.blank_line", settings=Settings(), messages=messages,
            fonts=self.fonts, faces=self.faces, face_positions={},
        )
        self.finish_opening(overlay)
        for _ in range(5):
            self.assertFalse(overlay.update(InputState()))
        self.assertEqual(tuple((text.text, text.y) for text in overlay.window.texts), (("あいうえお", 2), ("", 6)))
        self.assertFalse(overlay.update(InputState(confirm=InputButton(triggered=True, held=True))))
        for _ in range(3):
            self.assertFalse(overlay.update(InputState()))
        for _ in range(10):
            self.assertFalse(overlay.update(InputState()))
        self.assertEqual(tuple((text.text, text.y) for text in overlay.window.texts), (("かきくけこ", 2), ("さしすせそ", 6)))
        self.assertTrue(overlay.update(InputState(confirm=InputButton(triggered=True, held=True))))

    def test_opens_before_revealing_text_or_accepting_confirm(self) -> None:
        overlay = self.overlay()

        self.assertEqual(overlay.window.state, WindowState.OPENING)
        self.assertEqual(overlay.window.visible_height, 0)
        for _ in range(WINDOW_ANIMATION_FRAME_COUNT):
            self.assertFalse(overlay.update(
                InputState(confirm=InputButton(triggered=True, held=True))
            ))

        self.assertEqual(overlay.window.state, WindowState.OPEN)
        self.assertEqual(
            tuple(text.text for text in overlay.window.texts),
            ("", ""),
        )
        self.assertFalse(overlay.update(InputState()))
        self.assertEqual(
            tuple(text.text for text in overlay.window.texts),
            ("こ", ""),
        )

    def test_reveals_one_character_per_frame_across_lines(self) -> None:
        overlay = self.overlay()
        self.finish_opening(overlay)

        self.assertEqual(
            tuple(text.text for text in overlay.window.texts),
            ("", ""),
        )
        self.assertFalse(overlay.update(InputState()))
        self.assertEqual(
            tuple(text.text for text in overlay.window.texts),
            ("こ", ""),
        )
        self.assertFalse(overlay.update(InputState()))
        self.assertEqual(
            tuple(text.text for text in overlay.window.texts),
            ("こん", ""),
        )

        for _ in range(3):
            self.assertFalse(overlay.update(InputState()))
        self.assertEqual(
            tuple(text.text for text in overlay.window.texts),
            ("こんにちは", ""),
        )
        self.assertFalse(overlay.update(InputState()))
        self.assertEqual(
            tuple(text.text for text in overlay.window.texts),
            ("こんにちは", "よ"),
        )

    def test_held_confirm_reveals_two_characters_without_acknowledging(self) -> None:
        overlay = self.overlay()
        self.finish_opening(overlay)

        self.assertFalse(
            overlay.update(
                InputState(confirm=InputButton(triggered=True, held=True))
            )
        )
        self.assertEqual(
            tuple(text.text for text in overlay.window.texts),
            ("こん", ""),
        )

    def test_confirm_closes_only_after_all_text_is_visible(self) -> None:
        overlay = self.overlay()
        self.finish_opening(overlay)

        for _ in range(len("こんにちはようこそ")):
            self.assertFalse(overlay.update(InputState()))
        self.assertFalse(
            overlay.update(InputState(confirm=InputButton(held=True)))
        )
        self.assertTrue(
            overlay.update(
                InputState(confirm=InputButton(triggered=True, held=True))
            )
        )

    @patch("app.ui.event_message.pyxel")
    def test_draws_blinking_wait_arrow_after_text_is_complete(
        self,
        pyxel: Mock,
    ) -> None:
        overlay = self.overlay()
        overlay.window.draw = Mock()

        overlay.draw()
        pyxel.blt.assert_not_called()

        self.finish_opening(overlay)
        for _ in range(len("こんにちはようこそ")):
            overlay.update(InputState())
        overlay.draw()
        pyxel.blt.assert_called_once_with(
            242,
            34,
            0,
            88,
            16,
            8,
            8,
            1,
        )

        pyxel.blt.reset_mock()
        for _ in range(30):
            overlay.update(InputState())
        overlay.draw()
        pyxel.blt.assert_not_called()

        for _ in range(30):
            overlay.update(InputState())
        overlay.draw()
        pyxel.blt.assert_called_once_with(
            242,
            34,
            0,
            88,
            16,
            8,
            8,
            1,
        )

    @patch("app.ui.event_message.pyxel")
    def test_draws_optional_character_face(self, pyxel: Mock) -> None:
        overlay = self.overlay(portrait="Alvan")
        overlay.window.draw = Mock()

        overlay.draw()

        pyxel.blt.assert_not_called()
        self.finish_opening(overlay)
        overlay.draw()

        self.assertIn(
            ((8, 8, self.faces, 32, 64, 32, 32, 1), {}),
            [(call.args, call.kwargs) for call in pyxel.blt.call_args_list],
        )

    @patch("app.ui.event_message.pyxel")
    def test_draws_optional_sheet_face(self, pyxel: Mock) -> None:
        overlay = self.overlay(portrait_position=(96, 224))
        overlay.window.draw = Mock()

        self.finish_opening(overlay)
        overlay.draw()

        self.assertIn(
            ((8, 8, self.faces, 96, 224, 32, 32, 1), {}),
            [(call.args, call.kwargs) for call in pyxel.blt.call_args_list],
        )

    def test_rejects_missing_portrait(self) -> None:
        with self.assertRaises(EventMessageDataError):
            self.overlay(portrait="Missing")

    def test_splits_long_text_into_acknowledged_pages(self) -> None:
        messages = EventMessageCatalog.from_records(
            [{
                "message_id": "event.long",
                "text_ja": ["a"] * 5,
                "text_en": [],
                "text_zhcn": [],
            }]
        )
        overlay = EventMessageOverlay(
            message_id="event.long",
            settings=Settings(),
            messages=messages,
            fonts=self.fonts,
            faces=self.faces,
            face_positions={},
        )
        self.finish_opening(overlay)

        for _ in range(2):
            self.assertFalse(overlay.update(InputState()))
        self.assertFalse(overlay.update(
            InputState(confirm=InputButton(triggered=True, held=True))
        ))
        self.assertEqual(overlay.window.state, WindowState.OPEN)
        self.assertEqual(
            tuple(text.text for text in overlay.window.texts),
            ("ａ", "ａ"),
        )
        for _ in range(3):
            self.assertFalse(overlay.update(InputState()))
        self.assertEqual(
            tuple(text.text for text in overlay.window.texts),
            ("", ""),
        )
        for _ in range(2):
            self.assertFalse(overlay.update(InputState()))
        self.assertFalse(overlay.update(
            InputState(confirm=InputButton(triggered=True, held=True))
        ))
        for _ in range(3):
            self.assertFalse(overlay.update(InputState()))
        self.assertEqual(
            tuple(text.text for text in overlay.window.texts),
            ("",),
        )
        self.assertFalse(overlay.update(InputState()))
        self.assertTrue(
            overlay.update(
                InputState(confirm=InputButton(triggered=True, held=True))
            )
        )

    def test_page_scroll_finishes_before_next_page_reveals_text(self) -> None:
        for language, page_line_count, scroll_frame_count in (
            (Language.JAPANESE, 2, 4),
            (Language.SIMPLIFIED_CHINESE, 2, 4),
            (Language.ENGLISH, 3, 5),
        ):
            with self.subTest(language=language):
                lines = ("一行目", "二行目", "三行目", "四行目")
                overlay = MessageOverlay(
                    lines=lines,
                    settings=Settings(language=language),
                    fonts=self.fonts,
                )
                self.finish_opening(overlay)
                old_page = lines[:page_line_count]
                for _ in range(sum(map(len, old_page))):
                    overlay.update(InputState())

                press = InputState(confirm=InputButton(triggered=True, held=True))
                for frame in range(1, scroll_frame_count):
                    self.assertFalse(overlay.update(press))
                    self.assertEqual(
                        tuple(text.text for text in overlay.window.texts),
                        old_page,
                    )
                    with patch.object(overlay.window, "draw") as draw_window:
                        overlay.draw()
                        overlay.draw()
                    self.assertEqual(draw_window.call_count, 2)
                    draw_window.assert_called_with(text_offset_y=-8 * frame)
                    self.assertEqual(overlay.window.state, WindowState.OPEN)

                self.assertFalse(overlay.update(press))
                self.assertEqual(
                    tuple(text.text for text in overlay.window.texts),
                    ("",) * (len(lines) - page_line_count),
                )
                self.assertFalse(overlay.update(InputState()))
                self.assertEqual(overlay.window.texts[0].text, lines[page_line_count][0])

    @patch("app.ui.event_message.pyxel")
    def test_scroll_keeps_face_stationary_and_hides_wait_arrow(self, pyxel: Mock) -> None:
        overlay = MessageOverlay(
            lines=("one", "two", "three"),
            settings=Settings(),
            fonts=self.fonts,
            faces=self.faces,
            face_position=FacePosition(32, 64),
        )
        self.finish_opening(overlay)
        for _ in range(6):
            overlay.update(InputState())
        overlay.update(InputState(confirm=InputButton(triggered=True)))

        with patch.object(overlay.window, "draw") as draw_window:
            overlay.draw()

        draw_window.assert_called_once_with(text_offset_y=-8)
        pyxel.blt.assert_called_once_with(8, 8, self.faces, 32, 64, 32, 32, 1)

    def test_page_with_only_internal_blank_lines_waits_for_confirm(self) -> None:
        overlay = MessageOverlay(
            lines=("一行目", "二行目", "", "", "最後"),
            settings=Settings(),
            fonts=self.fonts,
        )
        self.finish_opening(overlay)
        for _ in range(6):
            overlay.update(InputState())
        overlay.update(InputState(confirm=InputButton(triggered=True)))
        for _ in range(3):
            overlay.update(InputState())
        for _ in range(20):
            self.assertFalse(overlay.update(InputState()))
        self.assertEqual(tuple(text.text for text in overlay.window.texts), ("", ""))

        overlay.update(InputState(confirm=InputButton(triggered=True)))
        for _ in range(3):
            overlay.update(InputState())
        self.assertEqual(tuple(text.text for text in overlay.window.texts), ("",))
        overlay.update(InputState())
        self.assertEqual(overlay.window.texts[0].text, "最")


if __name__ == "__main__":
    unittest.main()
