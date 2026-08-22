"""Draw a framed window and freely positioned text inside it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import pyxel

TEXT_GRID_X = 2
TEXT_GRID_Y = 4

FRAME_BANK = 0
FRAME_X = 16
FRAME_Y = 0
FRAME_TILE_SIZE = 8
FRAME_EDGE_STEP = 4
FRAME_COLKEY = 1
GRADIENT_INSET = 4

GRADIENT_COLORS = (10, 11)
GRADIENT_STAGE_COUNT = len(GRADIENT_COLORS) * 2 - 1
GRADIENT_DITHER = 0.5
DEFAULT_TEXT_COLOR = 5
DEFAULT_TEXT_SHADOW_COLOR = 0


@dataclass(frozen=True)
class WindowText:
    """Text placed relative to a window's content origin.

    ``x`` advances in 2-pixel units and ``y`` advances in 4-pixel units.
    A font can be assigned per text; ``None`` uses the window's default font.
    """

    text: str
    x: int
    y: int
    color: int = DEFAULT_TEXT_COLOR
    font: Any | None = None
    shadow_color: int | None = DEFAULT_TEXT_SHADOW_COLOR

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")
        if not isinstance(self.x, int) or not isinstance(self.y, int):
            raise TypeError("text grid coordinates must be integers")
        if self.x < 0 or self.y < 0:
            raise ValueError("text grid coordinates must not be negative")
        if not isinstance(self.color, int):
            raise TypeError("text color must be an integer palette index")
        if self.shadow_color is not None and not isinstance(self.shadow_color, int):
            raise TypeError(
                "text shadow color must be an integer palette index or None"
            )


class Window:
    """A grid-positioned window with a framed gradient background.

    The window rectangle and its text use the same fine grid: 2 pixels
    horizontally and 4 pixels vertically. Drawing coordinates are converted to
    pixels internally.
    """

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        texts: Iterable[WindowText] = (),
        *,
        font: Any | None = None,
    ) -> None:
        values = (x, y, width, height)
        if not all(isinstance(value, int) for value in values):
            raise TypeError("window position and size must be integers")
        if (
            width * TEXT_GRID_X < FRAME_TILE_SIZE * 2
            or height * TEXT_GRID_Y < FRAME_TILE_SIZE * 2
        ):
            raise ValueError(
                "window width must be at least 8 grid units and height at least 4"
            )

        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.font = font
        self._texts: list[WindowText] = []
        for text in texts:
            self._validate_text_position(text)
            self._texts.append(text)

    @property
    def pixel_x(self) -> int:
        return self.x * TEXT_GRID_X

    @property
    def pixel_y(self) -> int:
        return self.y * TEXT_GRID_Y

    @property
    def pixel_width(self) -> int:
        return self.width * TEXT_GRID_X

    @property
    def pixel_height(self) -> int:
        return self.height * TEXT_GRID_Y

    @property
    def content_x(self) -> int:
        return self.pixel_x + FRAME_TILE_SIZE

    @property
    def content_y(self) -> int:
        return self.pixel_y + FRAME_TILE_SIZE

    @property
    def content_width(self) -> int:
        return self.pixel_width - FRAME_TILE_SIZE * 2

    @property
    def content_height(self) -> int:
        return self.pixel_height - FRAME_TILE_SIZE * 2

    @property
    def texts(self) -> tuple[WindowText, ...]:
        return tuple(self._texts)

    def add_text(
        self,
        text: str,
        x: int,
        y: int,
        *,
        color: int = DEFAULT_TEXT_COLOR,
        font: Any | None = None,
        shadow_color: int | None = DEFAULT_TEXT_SHADOW_COLOR,
    ) -> WindowText:
        """Add text at a free position in the window's 2x4-pixel grid."""

        placement = WindowText(text, x, y, color, font, shadow_color)
        self._validate_text_position(placement)
        self._texts.append(placement)
        return placement

    def remove_text(self, text: WindowText) -> None:
        self._texts.remove(text)

    def clear_texts(self) -> None:
        self._texts.clear()

    def text_position(self, text: WindowText) -> tuple[int, int]:
        """Return the absolute pixel origin of a text placement."""

        self._validate_text_position(text)
        return (
            self.content_x + text.x * TEXT_GRID_X,
            self.content_y + text.y * TEXT_GRID_Y,
        )

    def draw(self) -> None:
        self._draw_gradient()
        self._draw_frame()
        self._draw_texts()

    def _validate_text_position(self, text: WindowText) -> None:
        if not isinstance(text, WindowText):
            raise TypeError("texts must contain WindowText instances")
        pixel_x = text.x * TEXT_GRID_X
        pixel_y = text.y * TEXT_GRID_Y
        if pixel_x >= self.content_width or pixel_y >= self.content_height:
            raise ValueError("text origin must be inside the window content area")

    def _draw_gradient(self) -> None:
        gradient_x = self.pixel_x + GRADIENT_INSET
        gradient_y = self.pixel_y + GRADIENT_INSET
        gradient_width = self.pixel_width - GRADIENT_INSET * 2
        gradient_height = self.pixel_height - GRADIENT_INSET * 2

        try:
            for stage, offset, band_height in _gradient_bands(gradient_height):
                lower_color = GRADIENT_COLORS[stage // 2]
                pyxel.dither(1.0)
                pyxel.rect(
                    gradient_x,
                    gradient_y + offset,
                    gradient_width,
                    band_height,
                    lower_color,
                )
                if stage % 2:
                    upper_color = GRADIENT_COLORS[stage // 2 + 1]
                    pyxel.dither(GRADIENT_DITHER)
                    pyxel.rect(
                        gradient_x,
                        gradient_y + offset,
                        gradient_width,
                        band_height,
                        upper_color,
                    )
        finally:
            pyxel.dither(1.0)

    def _draw_frame(self) -> None:
        left = self.pixel_x
        top = self.pixel_y
        right = self.pixel_x + self.pixel_width - FRAME_TILE_SIZE
        bottom = self.pixel_y + self.pixel_height - FRAME_TILE_SIZE

        self._draw_horizontal_edges(left + FRAME_TILE_SIZE, right, top, bottom)
        self._draw_vertical_edges(top + FRAME_TILE_SIZE, bottom, left, right)

        pyxel.blt(
            left,
            top,
            FRAME_BANK,
            FRAME_X,
            FRAME_Y,
            FRAME_TILE_SIZE,
            FRAME_TILE_SIZE,
            FRAME_COLKEY,
        )
        pyxel.blt(
            right,
            top,
            FRAME_BANK,
            FRAME_X + FRAME_TILE_SIZE,
            FRAME_Y,
            FRAME_TILE_SIZE,
            FRAME_TILE_SIZE,
            FRAME_COLKEY,
        )
        pyxel.blt(
            left,
            bottom,
            FRAME_BANK,
            FRAME_X,
            FRAME_Y + FRAME_TILE_SIZE,
            FRAME_TILE_SIZE,
            FRAME_TILE_SIZE,
            FRAME_COLKEY,
        )
        pyxel.blt(
            right,
            bottom,
            FRAME_BANK,
            FRAME_X + FRAME_TILE_SIZE,
            FRAME_Y + FRAME_TILE_SIZE,
            FRAME_TILE_SIZE,
            FRAME_TILE_SIZE,
            FRAME_COLKEY,
        )

    @staticmethod
    def _draw_horizontal_edges(
        start: int,
        end: int,
        top: int,
        bottom: int,
    ) -> None:
        x = start
        while x < end:
            width = min(FRAME_EDGE_STEP, end - x)
            pyxel.blt(
                x,
                top,
                FRAME_BANK,
                FRAME_X + 6,
                FRAME_Y,
                width,
                FRAME_TILE_SIZE,
                FRAME_COLKEY,
            )
            pyxel.blt(
                x,
                bottom,
                FRAME_BANK,
                FRAME_X + 6,
                FRAME_Y + FRAME_TILE_SIZE,
                width,
                FRAME_TILE_SIZE,
                FRAME_COLKEY,
            )
            x += width

    @staticmethod
    def _draw_vertical_edges(
        start: int,
        end: int,
        left: int,
        right: int,
    ) -> None:
        y = start
        while y < end:
            height = min(FRAME_EDGE_STEP, end - y)
            pyxel.blt(
                left,
                y,
                FRAME_BANK,
                FRAME_X,
                FRAME_Y + 6,
                FRAME_TILE_SIZE,
                height,
                FRAME_COLKEY,
            )
            pyxel.blt(
                right,
                y,
                FRAME_BANK,
                FRAME_X + FRAME_TILE_SIZE,
                FRAME_Y + 6,
                FRAME_TILE_SIZE,
                height,
                FRAME_COLKEY,
            )
            y += height

    def _draw_texts(self) -> None:
        for text in self._texts:
            x, y = self.text_position(text)
            font = text.font if text.font is not None else self.font
            if text.shadow_color is not None:
                pyxel.text(x, y + 1, text.text, text.shadow_color, font)
            pyxel.text(x, y, text.text, text.color, font)


def _gradient_bands(height: int) -> tuple[tuple[int, int, int], ...]:
    """Split a height into solid and dithered stages for configured colors."""

    bands: list[tuple[int, int, int]] = []
    for stage in range(GRADIENT_STAGE_COUNT):
        start = (stage * height + GRADIENT_STAGE_COUNT // 2) // GRADIENT_STAGE_COUNT
        end = ((stage + 1) * height + GRADIENT_STAGE_COUNT // 2) // GRADIENT_STAGE_COUNT
        if end > start:
            bands.append((stage, start, end - start))
    return tuple(bands)
