"""Draw a framed window and freely positioned text inside it."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Iterable, Protocol

import pyxel

from .tagged_text import TextFontSpan, draw_tagged_text

TEXT_GRID_X = 4
TEXT_GRID_Y = 4

FRAME_BANK = 0
FRAME_X = 16
THIN_FRAME_X = 32
FRAME_Y = 0
FRAME_TILE_SIZE = 8
FRAME_EDGE_STEP = 4
FRAME_COLKEY = 1
FRAME_Y_OFFSET = 1
GRADIENT_INSET = 4

GRADIENT_COLORS = (10, 6)
GRADIENT_DITHER_RATIOS = (1.0, 0.75, 0.5, 0.25, 0.0)
GRADIENT_STAGE_COUNT = len(GRADIENT_DITHER_RATIOS)
DEFAULT_TEXT_COLOR = 5
DEFAULT_TEXT_SHADOW_COLOR = 0

CURSOR_BANK = 0
CURSOR_X = 48
CURSOR_SHADOW_X = 64
CURSOR_INACTIVE_X = 80
CURSOR_Y = 0
CURSOR_SIZE = 16
CURSOR_COLKEY = 1
CURSOR_TEXT_OFFSET_X = -8
CURSOR_FLOAT_OFFSETS = (0, 0, 0, 1, 2, 2, 2, 1)
CURSOR_FLOAT_PHASE_FRAMES = 12

HORIZONTAL_NAVIGATION_BANK = 0
HORIZONTAL_NAVIGATION_X = 96
HORIZONTAL_NAVIGATION_Y = 0
HORIZONTAL_NAVIGATION_WIDTH = 8
HORIZONTAL_NAVIGATION_HEIGHT = 16
HORIZONTAL_NAVIGATION_COLKEY = 1

VERTICAL_NAVIGATION_BANK = 0
VERTICAL_NAVIGATION_X = 192
VERTICAL_NAVIGATION_Y = 16
VERTICAL_NAVIGATION_WIDTH = 4
VERTICAL_NAVIGATION_HEIGHT = 8
VERTICAL_NAVIGATION_PRESSED_X_OFFSET = 8
VERTICAL_NAVIGATION_COLKEY = 1
VERTICAL_NAVIGATION_FRAME_OVERLAP_X = 2
VERTICAL_NAVIGATION_TOP_OFFSET = 10
VERTICAL_NAVIGATION_BOTTOM_OFFSET = 14

WINDOW_ANIMATION_FRAME_COUNT = 8


class WindowState(Enum):
    """Current visibility and animation state of one window."""

    CLOSED = auto()
    OPENING = auto()
    OPEN = auto()
    CLOSING = auto()


class NavigationDirection(Protocol):
    """Cardinal direction shape accepted by ``WindowCursor.update``."""

    @property
    def dx(self) -> int: ...

    @property
    def dy(self) -> int: ...


@dataclass(frozen=True)
class CursorTarget:
    """A selectable position expressed in a window's 4-pixel grid."""

    x: int
    y: int
    key: Any | None = None
    selectable: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.x, int) or not isinstance(self.y, int):
            raise TypeError("cursor target grid coordinates must be integers")
        if self.x < 0 or self.y < 0:
            raise ValueError("cursor target grid coordinates must not be negative")
        if not isinstance(self.selectable, bool):
            raise TypeError("cursor target selectable must be a boolean")


@dataclass(frozen=True)
class WindowText:
    """Text placed relative to a window's frame origin.

    ``x`` and ``y`` both advance in 4-pixel units.
    A font can be assigned per text; ``None`` uses the window's default font.
    """

    text: str
    x: int
    y: int
    color: int = DEFAULT_TEXT_COLOR
    font: Any | None = None
    shadow_color: int | None = DEFAULT_TEXT_SHADOW_COLOR
    baseline_offset: int = 0
    font_spans: tuple[TextFontSpan, ...] = ()

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
        if not isinstance(self.baseline_offset, int):
            raise TypeError("text baseline offset must be an integer")
        if not isinstance(self.font_spans, tuple) or not all(
            isinstance(span, TextFontSpan) for span in self.font_spans
        ):
            raise TypeError("font_spans must contain TextFontSpan values")
        if any(span.end > len(self.text) for span in self.font_spans):
            raise ValueError("font span must fit inside text")


class Window:
    """A grid-positioned text origin with an optional framed background.

    The window rectangle and its text use the same 4x4-pixel grid. Drawing
    coordinates are converted to pixels internally. A transparent window draws
    only its text and uses its top-left position as the coordinate origin.
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
        transparent: bool = False,
        thin_frame: bool = False,
        horizontal_navigation: bool = False,
        vertical_navigation: bool = False,
        active: bool = True,
        opened: bool = True,
    ) -> None:
        values = (x, y, width, height)
        if not all(isinstance(value, int) for value in values):
            raise TypeError("window position and size must be integers")
        if (
            width * TEXT_GRID_X < FRAME_TILE_SIZE * 2
            or height * TEXT_GRID_Y < FRAME_TILE_SIZE * 2
        ):
            raise ValueError("window width and height must be at least 4 grid units")
        if not isinstance(transparent, bool):
            raise TypeError("transparent must be a boolean")
        if not isinstance(thin_frame, bool):
            raise TypeError("thin_frame must be a boolean")
        if not isinstance(horizontal_navigation, bool):
            raise TypeError("horizontal_navigation must be a boolean")
        if not isinstance(vertical_navigation, bool):
            raise TypeError("vertical_navigation must be a boolean")
        if not isinstance(active, bool):
            raise TypeError("window active must be a boolean")
        if not isinstance(opened, bool):
            raise TypeError("opened must be a boolean")

        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.font = font
        self.transparent = transparent
        self.thin_frame = thin_frame
        self.horizontal_navigation = horizontal_navigation
        self.vertical_navigation = vertical_navigation
        self.active = active
        self.vertical_navigation_pressed = 0
        self._texts: list[WindowText] = []
        self._cursor: WindowCursor | None = None
        self._state = WindowState.OPEN if opened else WindowState.CLOSED
        self._visible_height = self.pixel_height if opened else 0
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

    @property
    def cursor(self) -> WindowCursor | None:
        return self._cursor

    @property
    def state(self) -> WindowState:
        return self._state

    @property
    def visible_height(self) -> int:
        """Return the currently visible height in pixels."""

        return self._visible_height

    @property
    def animation_height_step(self) -> int:
        """Return the per-frame height change for an eight-frame animation."""

        return (
            self.pixel_height + WINDOW_ANIMATION_FRAME_COUNT - 1
        ) // WINDOW_ANIMATION_FRAME_COUNT

    @property
    def is_open(self) -> bool:
        return self._state is WindowState.OPEN

    @property
    def is_closed(self) -> bool:
        return self._state is WindowState.CLOSED

    @property
    def is_animating(self) -> bool:
        return self._state in (WindowState.OPENING, WindowState.CLOSING)

    def add_text(
        self,
        text: str,
        x: int,
        y: int,
        *,
        color: int = DEFAULT_TEXT_COLOR,
        font: Any | None = None,
        shadow_color: int | None = DEFAULT_TEXT_SHADOW_COLOR,
        baseline_offset: int = 0,
        font_spans: tuple[TextFontSpan, ...] = (),
    ) -> WindowText:
        """Add text at a free position in the window's 4x4-pixel grid."""

        placement = WindowText(
            text,
            x,
            y,
            color,
            font,
            shadow_color,
            baseline_offset,
            font_spans,
        )
        self._validate_text_position(placement)
        self._texts.append(placement)
        return placement

    def remove_text(self, text: WindowText) -> None:
        self._texts.remove(text)

    def clear_texts(self) -> None:
        self._texts.clear()

    def set_cursor(
        self,
        targets: Iterable[CursorTarget],
        *,
        active: bool = True,
    ) -> WindowCursor:
        """Register selectable cursor targets relative to this window."""

        self._cursor = WindowCursor(self, targets, active=active)
        return self._cursor

    def clear_cursor(self) -> None:
        self._cursor = None

    def set_vertical_navigation_pressed(self, direction: int = 0) -> None:
        """Select the normal, pressed-up, or pressed-down arrow pattern."""

        if isinstance(direction, bool) or direction not in (-1, 0, 1):
            raise ValueError("vertical navigation direction must be -1, 0, or 1")
        self.vertical_navigation_pressed = direction

    def open(self) -> None:
        """Start opening from the window's current visible height."""

        if self._state in (WindowState.CLOSED, WindowState.CLOSING):
            self._state = WindowState.OPENING

    def open_immediately(self) -> None:
        """Open at its full height without playing the opening animation."""

        self._visible_height = self.pixel_height
        self._state = WindowState.OPEN

    def restart_opening(self) -> None:
        """Restart opening from the center without replacing window contents."""

        self._visible_height = 0
        self._state = WindowState.OPENING

    def close(self) -> None:
        """Start closing from the window's current visible height."""

        if self._state in (WindowState.OPEN, WindowState.OPENING):
            self._state = WindowState.CLOSING

    def close_immediately(self) -> None:
        """Close without playing the closing animation."""

        self._visible_height = 0
        self._state = WindowState.CLOSED

    def update(self, navigation: NavigationDirection | None = None) -> bool:
        """Advance the opening/closing animation or update the cursor.

        Cursor input is accepted only while the window is fully open. The
        return value reports whether the cursor moved.
        """

        if self._state is WindowState.OPENING:
            self._visible_height = min(
                self.pixel_height,
                self._visible_height + self.animation_height_step,
            )
            if self._visible_height == self.pixel_height:
                self._state = WindowState.OPEN
            return False

        if self._state is WindowState.CLOSING:
            self._visible_height = max(
                0,
                self._visible_height - self.animation_height_step,
            )
            if self._visible_height == 0:
                self._state = WindowState.CLOSED
            return False

        if self._state is WindowState.OPEN and self._cursor is not None:
            return self._cursor.update(navigation)
        return False

    def text_position(self, text: WindowText) -> tuple[int, int]:
        """Return the absolute pixel origin of a text placement."""

        self._validate_text_position(text)
        return (
            self.pixel_x + text.x * TEXT_GRID_X,
            self.pixel_y + text.y * TEXT_GRID_Y,
        )

    def draw(self) -> None:
        if self._visible_height == 0:
            return

        if self._visible_height == self.pixel_height:
            self._draw_contents()
            return

        frame_offset = 0 if self.transparent else FRAME_Y_OFFSET
        clip_y = (
            self.pixel_y
            + (self.pixel_height - self._visible_height) // 2
            + frame_offset
        )
        pyxel.clip(
            self.pixel_x,
            clip_y,
            self.pixel_width,
            self._visible_height,
        )
        try:
            self._draw_animation_contents()
        finally:
            pyxel.clip()

    def _draw_contents(self) -> None:
        if not self.transparent:
            self._draw_gradient()
            self._draw_frame()
        if self.horizontal_navigation and self.active:
            self._draw_horizontal_navigation()
        if self.vertical_navigation:
            self._draw_vertical_navigation()
        self._draw_texts()
        if self._cursor is not None:
            self._cursor.draw()

    def _draw_animation_contents(self) -> None:
        if self.transparent:
            self._draw_texts()
            if self._cursor is not None:
                self._cursor.draw()
            return

        self._draw_gradient()
        frame_height = max(self._visible_height, FRAME_TILE_SIZE)
        frame_top = self.pixel_y + (self.pixel_height - frame_height) // 2
        self._draw_frame(top=frame_top, height=frame_height)

    def _validate_text_position(self, text: WindowText) -> None:
        if not isinstance(text, WindowText):
            raise TypeError("texts must contain WindowText instances")
        pixel_x = text.x * TEXT_GRID_X
        pixel_y = text.y * TEXT_GRID_Y
        if pixel_x >= self.pixel_width or pixel_y >= self.pixel_height:
            raise ValueError("text origin must be inside the window area")

    def _draw_gradient(self) -> None:
        gradient_x = self.pixel_x + GRADIENT_INSET
        gradient_y = self.pixel_y + GRADIENT_INSET
        gradient_width = self.pixel_width - GRADIENT_INSET * 2
        gradient_height = (
            self.pixel_height - GRADIENT_INSET * 2 + FRAME_Y_OFFSET
        )
        foreground_color, background_color = GRADIENT_COLORS

        try:
            for stage, offset, band_height in _gradient_bands(gradient_height):
                pyxel.dither(1.0)
                pyxel.rect(
                    gradient_x,
                    gradient_y + offset,
                    gradient_width,
                    band_height,
                    background_color,
                )
                pyxel.dither(GRADIENT_DITHER_RATIOS[stage])
                pyxel.rect(
                    gradient_x,
                    gradient_y + offset,
                    gradient_width,
                    band_height,
                    foreground_color,
                )
        finally:
            pyxel.dither(1.0)

    def _draw_frame(
        self,
        *,
        top: int | None = None,
        height: int | None = None,
    ) -> None:
        left = self.pixel_x
        top = (self.pixel_y if top is None else top) + FRAME_Y_OFFSET
        height = self.pixel_height if height is None else height
        right = self.pixel_x + self.pixel_width - FRAME_TILE_SIZE
        bottom = top + height - FRAME_TILE_SIZE
        frame_x = THIN_FRAME_X if self.thin_frame else FRAME_X

        self._draw_horizontal_edges(
            left + FRAME_TILE_SIZE,
            right,
            top,
            bottom,
            frame_x,
        )
        self._draw_vertical_edges(
            top + FRAME_TILE_SIZE,
            bottom,
            left,
            right,
            frame_x,
        )

        pyxel.blt(
            left,
            top,
            FRAME_BANK,
            frame_x,
            FRAME_Y,
            FRAME_TILE_SIZE,
            FRAME_TILE_SIZE,
            FRAME_COLKEY,
        )
        pyxel.blt(
            right,
            top,
            FRAME_BANK,
            frame_x + FRAME_TILE_SIZE,
            FRAME_Y,
            FRAME_TILE_SIZE,
            FRAME_TILE_SIZE,
            FRAME_COLKEY,
        )
        pyxel.blt(
            left,
            bottom,
            FRAME_BANK,
            frame_x,
            FRAME_Y + FRAME_TILE_SIZE,
            FRAME_TILE_SIZE,
            FRAME_TILE_SIZE,
            FRAME_COLKEY,
        )
        pyxel.blt(
            right,
            bottom,
            FRAME_BANK,
            frame_x + FRAME_TILE_SIZE,
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
        frame_x: int,
    ) -> None:
        x = start
        while x < end:
            width = min(FRAME_EDGE_STEP, end - x)
            pyxel.blt(
                x,
                top,
                FRAME_BANK,
                frame_x + 6,
                FRAME_Y,
                width,
                FRAME_TILE_SIZE,
                FRAME_COLKEY,
            )
            pyxel.blt(
                x,
                bottom,
                FRAME_BANK,
                frame_x + 6,
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
        frame_x: int,
    ) -> None:
        y = start
        while y < end:
            height = min(FRAME_EDGE_STEP, end - y)
            pyxel.blt(
                left,
                y,
                FRAME_BANK,
                frame_x,
                FRAME_Y + 6,
                FRAME_TILE_SIZE,
                height,
                FRAME_COLKEY,
            )
            pyxel.blt(
                right,
                y,
                FRAME_BANK,
                frame_x + FRAME_TILE_SIZE,
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
            draw_tagged_text(
                x,
                y,
                text.text,
                text.color,
                font,
                shadow_color=text.shadow_color,
                text_y_offset=text.baseline_offset,
                font_spans=text.font_spans,
            )

    def _draw_horizontal_navigation(self) -> None:
        """Draw DA2-style previous/next indicators at both window edges."""

        y = (
            self.pixel_y
            + (self.pixel_height - HORIZONTAL_NAVIGATION_HEIGHT) // 2
            + FRAME_Y_OFFSET
        )
        pyxel.blt(
            self.pixel_x - 1,
            y,
            HORIZONTAL_NAVIGATION_BANK,
            HORIZONTAL_NAVIGATION_X,
            HORIZONTAL_NAVIGATION_Y,
            HORIZONTAL_NAVIGATION_WIDTH,
            HORIZONTAL_NAVIGATION_HEIGHT,
            HORIZONTAL_NAVIGATION_COLKEY,
        )
        pyxel.blt(
            self.pixel_x + self.pixel_width - HORIZONTAL_NAVIGATION_WIDTH + 1,
            y,
            HORIZONTAL_NAVIGATION_BANK,
            HORIZONTAL_NAVIGATION_X + HORIZONTAL_NAVIGATION_WIDTH,
            HORIZONTAL_NAVIGATION_Y,
            HORIZONTAL_NAVIGATION_WIDTH,
            HORIZONTAL_NAVIGATION_HEIGHT,
            HORIZONTAL_NAVIGATION_COLKEY,
        )

    def _draw_vertical_navigation(self) -> None:
        """Draw DA2-style up/down scroll indicators on the right frame."""

        x = (
            self.pixel_x
            + self.pixel_width
            - FRAME_TILE_SIZE
            - VERTICAL_NAVIGATION_FRAME_OVERLAP_X
        )
        frame_top = self.pixel_y + FRAME_Y_OFFSET
        up_x = VERTICAL_NAVIGATION_X + (
            VERTICAL_NAVIGATION_PRESSED_X_OFFSET
            if self.vertical_navigation_pressed < 0
            else 0
        )
        down_x = VERTICAL_NAVIGATION_X + VERTICAL_NAVIGATION_WIDTH + (
            VERTICAL_NAVIGATION_PRESSED_X_OFFSET
            if self.vertical_navigation_pressed > 0
            else 0
        )
        pyxel.blt(
            x,
            frame_top + VERTICAL_NAVIGATION_TOP_OFFSET,
            VERTICAL_NAVIGATION_BANK,
            up_x,
            VERTICAL_NAVIGATION_Y,
            VERTICAL_NAVIGATION_WIDTH,
            VERTICAL_NAVIGATION_HEIGHT,
            VERTICAL_NAVIGATION_COLKEY,
        )
        pyxel.blt(
            x,
            frame_top + self.pixel_height - VERTICAL_NAVIGATION_BOTTOM_OFFSET,
            VERTICAL_NAVIGATION_BANK,
            down_x,
            VERTICAL_NAVIGATION_Y,
            VERTICAL_NAVIGATION_WIDTH,
            VERTICAL_NAVIGATION_HEIGHT,
            VERTICAL_NAVIGATION_COLKEY,
        )


class WindowFactory:
    """Create windows that share one language-specific default font."""

    def __init__(self, default_font: Any) -> None:
        if default_font is None:
            raise ValueError("default_font must not be None")
        self.default_font = default_font

    def create(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        texts: Iterable[WindowText] = (),
        *,
        font: Any | None = None,
        transparent: bool = False,
        thin_frame: bool = False,
        horizontal_navigation: bool = False,
        vertical_navigation: bool = False,
        active: bool = True,
        opened: bool = True,
    ) -> Window:
        """Create a Window, using the factory font unless one is supplied."""

        return Window(
            x,
            y,
            width,
            height,
            texts,
            font=self.default_font if font is None else font,
            transparent=transparent,
            thin_frame=thin_frame,
            horizontal_navigation=horizontal_navigation,
            vertical_navigation=vertical_navigation,
            active=active,
            opened=opened,
        )


class WindowCursor:
    """Manage and draw one cursor attached to a window.

    Input mapping and command execution remain the responsibility of the Scene
    or Overlay that owns the window.
    """

    def __init__(
        self,
        window: Window,
        targets: Iterable[CursorTarget],
        *,
        active: bool = True,
        draw_shadow: bool = True,
    ) -> None:
        if not isinstance(active, bool):
            raise TypeError("cursor active must be a boolean")
        if not isinstance(draw_shadow, bool):
            raise TypeError("cursor draw_shadow must be a boolean")

        registered = tuple(targets)
        seen_positions: set[tuple[int, int]] = set()
        for target in registered:
            if not isinstance(target, CursorTarget):
                raise TypeError("cursor targets must contain CursorTarget instances")
            position = (target.x, target.y)
            if position in seen_positions:
                raise ValueError("cursor target positions must be unique")
            seen_positions.add(position)
            if (
                target.x * TEXT_GRID_X >= window.pixel_width
                or target.y * TEXT_GRID_Y >= window.pixel_height
            ):
                raise ValueError("cursor target origin must be inside the window area")

        self._window = window
        self._targets = registered
        self._selected_index = next(
            (
                index
                for index, target in enumerate(self._targets)
                if target.selectable
            ),
            None,
        )
        self._animation_frame = 0
        self.active = active
        self.draw_shadow = draw_shadow

    @property
    def targets(self) -> tuple[CursorTarget, ...]:
        return self._targets

    @property
    def selected_index(self) -> int | None:
        return self._selected_index

    @property
    def selected_target(self) -> CursorTarget | None:
        if self._selected_index is None:
            return None
        return self._targets[self._selected_index]

    @property
    def selected_key(self) -> Any | None:
        target = self.selected_target
        return None if target is None else target.key

    @property
    def animation_frame(self) -> int:
        return self._animation_frame

    def update(self, navigation: NavigationDirection | None = None) -> bool:
        """Apply logical navigation and advance the floating animation."""

        moved = False
        if navigation is not None:
            moved = self.move(dx=navigation.dx, dy=navigation.dy)
        if self.active and self._selected_index is not None:
            self._animation_frame += 1
        else:
            self._animation_frame = 0
        return moved

    def move_up(self) -> bool:
        return self.move(dy=-1)

    def move_down(self) -> bool:
        return self.move(dy=1)

    def move_left(self) -> bool:
        return self.move(dx=-1)

    def move_right(self) -> bool:
        return self.move(dx=1)

    def select_key(self, key: Any) -> None:
        """Select one registered selectable target by its stable key."""

        for index, target in enumerate(self._targets):
            if target.key == key and target.selectable:
                self._selected_index = index
                self._animation_frame = 0
                return
        raise ValueError(f"selectable cursor key is not registered: {key!r}")

    def move(self, *, dx: int = 0, dy: int = 0) -> bool:
        """Move to the next selectable target in one cardinal direction."""

        if (dx, dy) not in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            raise ValueError("cursor movement must be one cardinal grid step")
        if not self.active or self._selected_index is None:
            return False

        self._animation_frame = 0
        current = self._targets[self._selected_index]
        if dx:
            candidates = sorted(
                (
                    index
                    for index, target in enumerate(self._targets)
                    if target.y == current.y
                ),
                key=lambda index: self._targets[index].x,
            )
            distance = dx
        else:
            candidates = sorted(
                (
                    index
                    for index, target in enumerate(self._targets)
                    if target.x == current.x
                ),
                key=lambda index: self._targets[index].y,
            )
            distance = dy

        current_position = candidates.index(self._selected_index)
        for step in range(1, len(candidates) + 1):
            candidate_position = (current_position + distance * step) % len(
                candidates
            )
            candidate_index = candidates[candidate_position]
            if self._targets[candidate_index].selectable:
                moved = candidate_index != self._selected_index
                self._selected_index = candidate_index
                return moved
        return False

    def draw(self) -> None:
        """Draw a fixed shadow and a floating cursor at the selected target."""

        target = self.selected_target
        if target is None:
            return

        x = (
            self._window.pixel_x
            + target.x * TEXT_GRID_X
            + CURSOR_TEXT_OFFSET_X
        )
        y = self._window.pixel_y + target.y * TEXT_GRID_Y
        float_offset = 0
        if self.active:
            phase = (self._animation_frame // CURSOR_FLOAT_PHASE_FRAMES) % len(
                CURSOR_FLOAT_OFFSETS
            )
            float_offset = CURSOR_FLOAT_OFFSETS[phase]

        if self.draw_shadow:
            pyxel.blt(
                x,
                y,
                CURSOR_BANK,
                CURSOR_SHADOW_X,
                CURSOR_Y,
                CURSOR_SIZE,
                CURSOR_SIZE,
                CURSOR_COLKEY,
            )
        pyxel.blt(
            x,
            y - float_offset,
            CURSOR_BANK,
            CURSOR_X if self.active else CURSOR_INACTIVE_X,
            CURSOR_Y,
            CURSOR_SIZE,
            CURSOR_SIZE,
            CURSOR_COLKEY,
        )


def _gradient_bands(height: int) -> tuple[tuple[int, int, int], ...]:
    """Split a height into solid and dithered stages for configured colors."""

    bands: list[tuple[int, int, int]] = []
    for stage in range(GRADIENT_STAGE_COUNT):
        start = (stage * height + GRADIENT_STAGE_COUNT // 2) // GRADIENT_STAGE_COUNT
        end = ((stage + 1) * height + GRADIENT_STAGE_COUNT // 2) // GRADIENT_STAGE_COUNT
        if end > start:
            bands.append((stage, start, end - start))
    return tuple(bands)
