"""Dungeon selection and explicit treasure reset confirmation."""

from input import Direction
from ui import CursorTarget
from ui.debug_text import DEBUG_TEXT


class DebugDungeonOverlay:
    PAGE_SIZE = 10

    def __init__(self, *, dungeons, texts, windows, guide, on_start, on_reset, error=None):
        self.dungeons = dungeons
        self.texts = texts
        self.windows = windows
        self.guide = guide
        self.on_start = on_start
        self.on_reset = on_reset
        self.error = error
        self.index = 0
        self.phase = "list"
        self.notice = ""
        self._build()

    def _build(self):
        placements = [self.texts.create(DEBUG_TEXT.dungeon, 4, 3), self.guide]
        targets = []
        if self.phase == "list":
            start = self.index // self.PAGE_SIZE * self.PAGE_SIZE
            for index, dungeon in enumerate(self.dungeons[start:start + self.PAGE_SIZE], start):
                y = 9 + (index - start) * 3
                placements.append(self.texts.create(dungeon.name, 6, y))
                targets.append(CursorTarget(4, y, key=index))
            if not self.dungeons:
                placements.append(self.texts.create(
                    DEBUG_TEXT.dungeon_invalid if self.error else DEBUG_TEXT.dungeon_empty, 4, 9))
        else:
            placements.append(self.texts.create(self.dungeons[self.index].name, 4, 7))
            choices = (("start", DEBUG_TEXT.dungeon_start), ("reset", DEBUG_TEXT.dungeon_reset))
            if self.phase == "confirm":
                placements.append(self.texts.create(DEBUG_TEXT.dungeon_reset_confirm, 4, 12))
                choices = (("no", DEBUG_TEXT.dungeon_no), ("yes", DEBUG_TEXT.dungeon_yes))
            for index, (key, label) in enumerate(choices):
                y = 19 + index * 4
                placements.append(self.texts.create(label, 6, y))
                targets.append(CursorTarget(4, y, key=key))
            placements.append(self.texts.create(self.notice, 4, 32))
        self.window = self.windows.create(2, 2, 60, 56, tuple(placements), opened=True)
        self.cursor = self.window.set_cursor(tuple(targets)) if targets else None
        if self.phase == "list" and self.cursor is not None:
            self.cursor.select_key(self.index)

    def update(self, input_state):
        if input_state.cancel.triggered:
            if self.phase == "list":
                return True
            self.phase = "list" if self.phase == "actions" else "actions"
            self.notice = ""
            self._build()
        elif self.cursor is not None and input_state.confirm.triggered:
            key = self.cursor.selected_key
            if self.phase == "list":
                self.index = key
                self.phase = "actions"
            elif self.phase == "confirm":
                if key == "yes":
                    self.on_reset(self.dungeons[self.index])
                    self.notice = DEBUG_TEXT.dungeon_reset_done
                self.phase = "actions"
            elif key == "start":
                self.on_start(self.dungeons[self.index])
                return False
            else:
                self.phase = "confirm"
            self._build()
        elif self.phase == "list" and self.dungeons and input_state.navigation in (Direction.UP, Direction.DOWN):
            self.index = (self.index + (-1 if input_state.navigation is Direction.UP else 1)) % len(self.dungeons)
            self._build()
        else:
            self.window.update(input_state.navigation)
        return False

    def draw(self):
        self.window.draw()
