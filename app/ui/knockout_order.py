"""Select the party's temporary fighting order for a knockout battle."""

from input import InputState
from localization import Localizer
from member import Member
from resources import FontResources
from state import Settings
from text_catalog import TextCatalog
from ui import (
    DEFAULT_TEXT_COLOR, DISABLED_COLOR, CursorTarget, LocalizedWindowTextFactory, WindowFactory,
)


class KnockoutOrderOverlay:
    """Show eligible fighters and assign each a distinct position."""

    def __init__(
        self, *, candidates: tuple[Member, ...], settings: Settings,
        fonts: FontResources, texts: TextCatalog,
    ) -> None:
        self.candidates = candidates
        self.order: list[int] = []
        self.localizer = Localizer(settings.language)
        self.texts = texts
        placements = LocalizedWindowTextFactory.from_language(fonts, settings.language)
        self.window = WindowFactory(placements.font, text_style=placements.apply).create(
            4, 10, 56, 40 if candidates else 14,
        )
        self._refresh()
        self.window.open_immediately()

    def _refresh(self) -> None:
        self.window.clear_texts()
        self.window.clear_cursor()
        key = "battle.knockout.order" if self.candidates else "battle.knockout.no_fighters"
        self.window.add_text(self.texts.text(key, self.localizer), 4, 3)
        if not self.candidates:
            return

        targets = []
        for index, member in enumerate(self.candidates):
            y = 9 + index * 4
            chosen = index in self.order
            name = member.definition.localized_name(self.localizer)
            self.window.add_text(name, 8, y)
            if chosen:
                self.window.add_text(str(self.order.index(index) + 1), 5, y)
            targets.append(CursorTarget(4, y, key=index, selectable=not chosen))

        ready = len(self.order) == len(self.candidates)
        start = self.texts.text("battle.knockout.start", self.localizer)
        self.window.add_text(start, 8, 31, color=DEFAULT_TEXT_COLOR if ready else DISABLED_COLOR)
        targets.append(CursorTarget(4, 31, key="start", selectable=ready))
        self.cursor = self.window.set_cursor(targets)

    def update(self, input_state: InputState) -> tuple[Member, ...] | None:
        """Return the chosen lineup or an empty tuple when the player backs out."""

        if input_state.cancel.triggered:
            if not self.order:
                return ()
            previous = self.order.pop()
            self._refresh()
            self.cursor.select_key(previous)
        elif input_state.confirm.triggered:
            if not self.candidates:
                return ()
            selected = self.cursor.selected_key
            if selected == "start":
                return tuple(self.candidates[index] for index in self.order)
            if isinstance(selected, int):
                self.order.append(selected)
                self._refresh()
        else:
            self.window.update(input_state.navigation)
        return None

    def draw(self) -> None:
        self.window.draw()
