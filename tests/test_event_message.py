from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from app.input import InputButton, InputState
from app.member import FacePosition
from app.state import Settings
from app.text_catalog import TextCatalog
from app.ui.event_message import EventMessageDataError, EventMessageOverlay


class EventMessageOverlayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.font = Mock()
        self.fonts = Mock()
        self.fonts.font_for.return_value = self.font
        self.fonts.baseline_offset_for.return_value = 0
        self.faces = object()

    def overlay(self, *, portrait: str | None = None) -> EventMessageOverlay:
        texts = TextCatalog.from_records(
            [
                {
                    "text_key": "event.sample.hello",
                    "text_ja": ["こんにちは", "ようこそ"],
                    "text_en": ["Hello", "Welcome"],
                    "text_zhcn": ["你好", "欢迎"],
                }
            ]
        )
        return EventMessageOverlay(
            text_key="event.sample.hello",
            portrait_character_key=portrait,
            settings=Settings(),
            texts=texts,
            fonts=self.fonts,
            faces=self.faces,
            face_positions={"Alvan": FacePosition(32, 64)},
        )

    def test_confirm_closes_only_on_triggered_edge(self) -> None:
        overlay = self.overlay()

        self.assertFalse(
            overlay.update(InputState(confirm=InputButton(held=True)))
        )
        self.assertTrue(
            overlay.update(
                InputState(confirm=InputButton(triggered=True, held=True))
            )
        )

    @patch("app.ui.event_message.pyxel")
    def test_draws_optional_character_face(self, pyxel: Mock) -> None:
        overlay = self.overlay(portrait="Alvan")
        overlay.window.draw = Mock()

        overlay.draw()

        self.assertIn(
            ((12, 192, self.faces, 32, 64, 32, 32, 1), {}),
            [(call.args, call.kwargs) for call in pyxel.blt.call_args_list],
        )

    def test_rejects_missing_portrait(self) -> None:
        with self.assertRaises(EventMessageDataError):
            self.overlay(portrait="Missing")

    def test_splits_long_text_into_acknowledged_pages(self) -> None:
        texts = TextCatalog.from_records(
            [{"text_key": "event.long", "text_ja": ["a"] * 5}]
        )
        overlay = EventMessageOverlay(
            text_key="event.long",
            portrait_character_key=None,
            settings=Settings(),
            texts=texts,
            fonts=self.fonts,
            faces=self.faces,
            face_positions={},
        )

        self.assertFalse(
            overlay.update(InputState(confirm=InputButton(triggered=True)))
        )
        self.assertTrue(
            overlay.update(InputState(confirm=InputButton(triggered=True)))
        )


if __name__ == "__main__":
    unittest.main()
