"""Development encounter configuration and session-only selection state."""

from dataclasses import dataclass, replace
from collections.abc import Callable

from input import Direction, InputState
from resources.maps import MapRandomEncounter
from ui import CursorTarget, LocalizedWindowTextFactory, WindowFactory, WindowText
from ui.debug_text import DEBUG_TEXT


@dataclass
class DebugEncounterState:
    """Retain edited settings until this Game instance is discarded."""

    settings: MapRandomEncounter = MapRandomEncounter(
        1, "low", "neutral", False, False, False, True,
    )


ENCOUNTER_OPTIONS = {
    "monster_level": tuple(range(1, 10)) + ("dynamic",),
    "danger": ("low", "high"),
    "polarity": ("yang", "neutral", "yin"),
    "allow_demons": (False, True),
    "allow_humans": (False, True),
    "allow_giants": (False, True),
    "allow_large_animals": (False, True),
}


class DebugEncounterOverlay:
    """Edit map-editor encounter options and request a generated battle."""

    def __init__(
        self, *, state: DebugEncounterState,
        texts: LocalizedWindowTextFactory, windows: WindowFactory,
        guide: WindowText, on_start: Callable[[MapRandomEncounter], bool] | None,
        alert: object,
    ) -> None:
        self.state = state
        self.texts = texts
        self.windows = windows
        self.guide = guide
        self.on_start = on_start
        self.alert = alert
        self._build_window()

    def _build_window(self, selected_key: str = "monster_level") -> None:
        placements = [self.texts.create(DEBUG_TEXT.encounter_settings, 4, 3)]
        targets = []
        for index, key in enumerate(ENCOUNTER_OPTIONS):
            y = 9 + index * 3
            value = getattr(self.state.settings, key)
            if isinstance(value, bool):
                display = DEBUG_TEXT.condition_on if value else DEBUG_TEXT.condition_off
            else:
                display = {
                    "dynamic": "変動", "low": "低", "high": "高",
                    "yang": "陽", "neutral": "中立", "yin": "陰",
                }.get(value, str(value))
            placements.extend((
                self.texts.create(getattr(DEBUG_TEXT, key), 6, y),
                self.texts.create("：", 37, y),
                self.texts.create(display, 40, y),
            ))
            targets.append(CursorTarget(4, y, key=key))
        placements.extend((
            self.texts.create(DEBUG_TEXT.encounter_start, 6, 33),
            self.texts.create(DEBUG_TEXT.encounter_change_guide, 4, 45),
            self.guide,
        ))
        targets.append(CursorTarget(4, 33, key="start"))
        self.window = self.windows.create(2, 2, 60, 56, tuple(placements), opened=True)
        self.cursor = self.window.set_cursor(tuple(targets))
        self.cursor.select_key(selected_key)

    def update(self, input_state: InputState) -> bool:
        if input_state.cancel.triggered:
            return True
        key = self.cursor.selected_key
        if key == "start" and input_state.confirm.triggered:
            if self.on_start is None or not self.on_start(self.state.settings):
                self.alert.start()
        elif key in ENCOUNTER_OPTIONS and (
            input_state.confirm.triggered
            or input_state.navigation in (Direction.LEFT, Direction.RIGHT)
        ):
            values = ENCOUNTER_OPTIONS[key]
            offset = -1 if input_state.navigation is Direction.LEFT else 1
            index = values.index(getattr(self.state.settings, key))
            value = values[(index + offset) % len(values)]
            self.state.settings = replace(self.state.settings, **{key: value})
            self._build_window(key)
        else:
            self.window.update(input_state.navigation)
        return False

    def draw(self) -> None:
        self.window.draw()
