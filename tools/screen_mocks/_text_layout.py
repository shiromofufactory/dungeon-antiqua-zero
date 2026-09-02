"""Small text-placement helpers shared by screen mocks."""

from __future__ import annotations

from typing import Protocol

from tools._bootstrap import APP_ROOT
from ui import TEXT_GRID_X


class TextWidthFont(Protocol):
    def text_width(self, text: str) -> int: ...


def right_aligned_grid_x(
    text: str,
    *,
    reference_text: str,
    reference_x: int,
    font: TextWidthFont,
) -> int:
    """Align ``text`` to the right edge of reference text on the text grid."""

    right_edge = reference_x * TEXT_GRID_X + font.text_width(reference_text)
    return (
        right_edge - font.text_width(text) + TEXT_GRID_X // 2
    ) // TEXT_GRID_X
