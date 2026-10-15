"""Development-only event flag editor with a paged catalog."""

from collections.abc import Iterable

from input import Direction, InputAction, InputDevice, InputState
from resources import FontResources
from state import Language, SaveData
from ui import (
    DISABLED_COLOR,
    CursorTarget,
    LocalizedWindowTextFactory,
    WindowCursor,
    WindowFactory,
    input_icon_tag,
)
from ui.debug_text import DEBUG_TEXT

FLAGS_PER_PAGE = 10
FLAG_FIRST_Y = 7
FLAG_ROW_HEIGHT = 3
FLAG_ID_VISIBLE_CHARS = 27
FLAG_DETAIL_LINE_CHARS = 36


class DebugFlagsOverlay:
    """Own flag selection while editing the shared SaveData flag set."""

    def __init__(
        self, *, flag_ids: Iterable[str], save_data: SaveData,
        fonts: FontResources, alert: object,
    ) -> None:
        self.flag_ids = tuple(sorted(flag_ids))
        self.save_data = save_data
        self.alert = alert
        self.texts = LocalizedWindowTextFactory.from_language(fonts, Language.JAPANESE)
        # Use the Latin font's normal display glyphs without changing flag keys.
        self.id_texts = LocalizedWindowTextFactory.from_language(fonts, Language.ENGLISH)
        self.windows = WindowFactory(fonts.font_for(Language.JAPANESE))
        self.page = 0
        self.row = 0
        self.cursor: WindowCursor | None = None
        self._build_window()

    @property
    def page_count(self) -> int:
        return max(1, (len(self.flag_ids) + FLAGS_PER_PAGE - 1) // FLAGS_PER_PAGE)

    @property
    def visible_flags(self) -> tuple[str, ...]:
        start = self.page * FLAGS_PER_PAGE
        return self.flag_ids[start : start + FLAGS_PER_PAGE]

    def _build_window(self) -> None:
        placements = [
            self.texts.create(DEBUG_TEXT.event_flags, 4, 3),
            self.texts.create(DEBUG_TEXT.flag_page(self.page + 1, self.page_count), 44, 3),
        ]
        targets = []
        for row, flag_id in enumerate(self.visible_flags):
            y = FLAG_FIRST_Y + row * FLAG_ROW_HEIGHT
            display_id = flag_id
            if len(display_id) > FLAG_ID_VISIBLE_CHARS:
                display_id = display_id[: FLAG_ID_VISIBLE_CHARS - 3] + "..."
            placements.extend((
                self.id_texts.create(display_id, 8, y),
                self.texts.create(
                    DEBUG_TEXT.flag_on if flag_id in self.save_data.event_flags
                    else DEBUG_TEXT.flag_off,
                    50, y,
                ),
            ))
            targets.append(CursorTarget(4, y, key=flag_id))
        if not targets:
            placements.append(self.texts.create(
                DEBUG_TEXT.no_event_flags, 6, FLAG_FIRST_Y, color=DISABLED_COLOR,
            ))
        else:
            # Keep a longer selected ID readable without overlapping its state.
            flag_id = self.visible_flags[self.row]
            for line in range(2):
                start = line * FLAG_DETAIL_LINE_CHARS
                text = flag_id[start : start + FLAG_DETAIL_LINE_CHARS]
                if line == 1 and len(flag_id) > start + FLAG_DETAIL_LINE_CHARS:
                    text = text[:-3] + "..."
                placements.append(self.id_texts.create(text, 4, 39 + line * 3))
        placements.extend((
            self.texts.create(DEBUG_TEXT.flag_toggle_guide.replace(
                "%CONFIRM%", input_icon_tag(InputAction.CONFIRM, InputDevice.KEYBOARD),
            ), 4, 47),
            self.texts.create(DEBUG_TEXT.flag_page_guide, 4, 51),
            self.texts.create(DEBUG_TEXT.close_guide.replace(
                "%CANCEL%", input_icon_tag(InputAction.CANCEL, InputDevice.KEYBOARD),
            ), 34, 51),
        ))
        self.window = self.windows.create(
            2, 2, 60, 56, tuple(placements),
            horizontal_navigation=self.page_count > 1, opened=True,
        )
        self.cursor = self.window.set_cursor(tuple(targets)) if targets else None
        if self.cursor is not None:
            self.cursor.select_key(self.visible_flags[self.row])

    def _switch_page(self, distance: int) -> None:
        self.page = (self.page + distance) % self.page_count
        self.row = min(self.row, max(0, len(self.visible_flags) - 1))
        self._build_window()

    def update(self, input_state: InputState) -> bool:
        if input_state.cancel.triggered:
            return True
        if input_state.navigation is Direction.LEFT or input_state.previous_page.triggered:
            self._switch_page(-1)
        elif input_state.navigation is Direction.RIGHT or input_state.next_page.triggered:
            self._switch_page(1)
        elif input_state.confirm.triggered:
            if self.cursor is None:
                self.alert.start()
            else:
                flag_id = self.cursor.selected_key
                if flag_id in self.save_data.event_flags:
                    self.save_data.event_flags.remove(flag_id)
                else:
                    self.save_data.event_flags.add(flag_id)
                self._build_window()
        elif self.window.update(input_state.navigation) and self.cursor is not None:
            self.row = self.visible_flags.index(self.cursor.selected_key)
            self._build_window()
        return False

    def draw(self) -> None:
        self.window.draw()
