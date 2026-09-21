"""Reusable destination selector for TELEPORT and development travel."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from input import Direction, InputAction, InputDevice, InputState
from resources import FontResources, FontRole
from state import Language, Settings
from ui import (
    DISABLED_COLOR,
    CursorTarget,
    LocalizedWindowTextFactory,
    Window,
    WindowCursor,
    WindowFactory,
    input_icon_tag,
)

TELEPORT_WINDOW_GRID = (2, 2, 60, 56)
TELEPORT_FIRST_Y = 9
TELEPORT_ROW_HEIGHT = 3
TELEPORT_VISIBLE_COUNT = 13
TELEPORT_TEXT_X = 6
TELEPORT_CURSOR_X = 4
TELEPORT_TITLE_X = 4
TELEPORT_TITLE_Y = 3
TELEPORT_GUIDE_X = 4
TELEPORT_GUIDE_Y = 49


@dataclass(frozen=True)
class TeleportTarget:
    """One stable teleport target and its already-localized display name."""

    site_id: str
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.site_id, str) or not self.site_id:
            raise ValueError("teleport site ID must be a non-empty string")
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("teleport name must be a non-empty string")


@dataclass(frozen=True)
class TeleportMenuLabels:
    """Temporary labels retained from the former debug-only selector."""

    title: str = "テレポートさき"
    empty: str = "いどうさきが　ありません"
    close_guide: str = "%CANCEL%：もどる"


class TeleportMenuOverlay:
    """Select one visited destination through the shared provisional UI."""

    def __init__(
        self,
        *,
        targets: Iterable[TeleportTarget],
        settings: Settings,
        fonts: FontResources,
        alert: object,
        on_teleport: Callable[[str], bool],
        labels: TeleportMenuLabels = TeleportMenuLabels(),
    ) -> None:
        registered_targets = tuple(targets)
        if not all(isinstance(target, TeleportTarget) for target in registered_targets):
            raise TypeError("targets must contain TeleportTarget values")
        site_ids = tuple(target.site_id for target in registered_targets)
        if len(site_ids) != len(set(site_ids)):
            raise ValueError("teleport site IDs must be unique")
        if not isinstance(settings, Settings):
            raise TypeError("settings must be Settings")
        if not isinstance(fonts, FontResources):
            raise TypeError("fonts must be FontResources")
        if not callable(getattr(alert, "start", None)):
            raise TypeError("alert must provide start()")
        if not callable(on_teleport):
            raise TypeError("on_teleport must be callable")
        if not isinstance(labels, TeleportMenuLabels):
            raise TypeError("labels must be TeleportMenuLabels")

        self.targets = registered_targets
        self.settings = settings
        self.fonts = fonts
        self.alert = alert
        self.on_teleport = on_teleport
        self.labels = labels
        self.debug_texts = LocalizedWindowTextFactory.from_language(
            fonts,
            Language.JAPANESE,
        )
        self.target_texts = LocalizedWindowTextFactory.from_language(
            fonts,
            settings.language,
            role=FontRole.LARGE,
        )
        self.windows = WindowFactory(fonts.font_for(Language.JAPANESE))
        self.index = 0
        self.scroll_offset = 0
        self.window: Window
        self.cursor: WindowCursor | None = None
        self._build_window()

    def _guide_text(self):
        return self.debug_texts.create(
            self.labels.close_guide.replace(
                "%CANCEL%",
                input_icon_tag(InputAction.CANCEL, InputDevice.KEYBOARD),
            ),
            TELEPORT_GUIDE_X,
            TELEPORT_GUIDE_Y,
        )

    def _build_window(self) -> None:
        placements = [
            self.debug_texts.create(
                self.labels.title,
                TELEPORT_TITLE_X,
                TELEPORT_TITLE_Y,
            )
        ]
        visible_targets = self.targets[
            self.scroll_offset : self.scroll_offset + TELEPORT_VISIBLE_COUNT
        ]
        cursor_targets: list[CursorTarget] = []
        if not visible_targets:
            placements.append(
                self.debug_texts.create(
                    self.labels.empty,
                    TELEPORT_TEXT_X,
                    TELEPORT_FIRST_Y,
                    color=DISABLED_COLOR,
                )
            )
        else:
            for row, target in enumerate(visible_targets):
                y = TELEPORT_FIRST_Y + row * TELEPORT_ROW_HEIGHT
                placements.append(
                    self.target_texts.create(target.name, TELEPORT_TEXT_X, y)
                )
                cursor_targets.append(
                    CursorTarget(TELEPORT_CURSOR_X, y, key=target.site_id)
                )
        placements.append(self._guide_text())
        self.window = self.windows.create(
            *TELEPORT_WINDOW_GRID,
            tuple(placements),
            vertical_navigation=len(self.targets) > TELEPORT_VISIBLE_COUNT,
            opened=True,
        )
        if not cursor_targets:
            self.cursor = None
            return
        self.cursor = self.window.set_cursor(tuple(cursor_targets))
        self.cursor.select_key(self.targets[self.index].site_id)

    def _move(self, distance: int) -> None:
        if distance not in (-1, 1):
            raise ValueError("teleport distance must be -1 or 1")
        if not self.targets:
            return
        self.index = (self.index + distance) % len(self.targets)
        if self.index < self.scroll_offset:
            self.scroll_offset = self.index
        elif self.index >= self.scroll_offset + TELEPORT_VISIBLE_COUNT:
            self.scroll_offset = self.index - TELEPORT_VISIBLE_COUNT + 1
        self._build_window()

    def _confirm(self) -> None:
        if self.cursor is None:
            self.alert.start()
            return
        site_id = self.cursor.selected_key
        if not isinstance(site_id, str) or not self.on_teleport(site_id):
            self.alert.start()

    def update(self, input_state: InputState) -> bool:
        """Advance selection and return True when the caller should close it."""

        if input_state.cancel.triggered:
            return True
        if input_state.confirm.triggered:
            self._confirm()
            return False
        if input_state.navigation is Direction.UP:
            self._move(-1)
        elif input_state.navigation is Direction.DOWN:
            self._move(1)
        else:
            self.window.update()
        return False

    def draw(self) -> None:
        self.window.draw()


__all__ = [
    "TELEPORT_VISIBLE_COUNT",
    "TELEPORT_WINDOW_GRID",
    "TeleportMenuLabels",
    "TeleportMenuOverlay",
    "TeleportTarget",
]
