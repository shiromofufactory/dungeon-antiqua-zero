from __future__ import annotations

import unittest

from app.ui.text_format import pad, spacing


class TextFormatTest(unittest.TestCase):
    def test_pad_right_aligns_and_converts_to_fullwidth(self) -> None:
        self.assertEqual(pad(8, 2), "　８")
        self.assertEqual(pad(121, 3), "１２１")
        self.assertEqual(pad(2, 2, fill="0"), "０２")

    def test_spacing_left_aligns_and_converts_to_fullwidth(self) -> None:
        self.assertEqual(spacing("HP", 4), "ＨＰ　　")

    def test_overflow_keeps_fixed_width_and_rightmost_characters(self) -> None:
        self.assertEqual(pad(123, 2), "２３")
        self.assertEqual(spacing("ABCDE", 3), "ＣＤＥ")

    def test_zero_width_returns_empty_text(self) -> None:
        self.assertEqual(pad(1, 0), "")
        self.assertEqual(spacing("A", 0), "")

    def test_rejects_invalid_width_and_fill(self) -> None:
        with self.assertRaises(TypeError):
            pad(1, True)
        with self.assertRaises(ValueError):
            spacing("A", -1)
        with self.assertRaises(ValueError):
            pad(1, 2, fill="00")


if __name__ == "__main__":
    unittest.main()
