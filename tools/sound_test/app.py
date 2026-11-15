"""Small Pyxel UI for comparing BGM and SE at production volume levels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pyxel

from app.audio_catalog import AudioCatalogError
from app.resources import AudioResourceError, FontResources
from app.state import Language
from tools.sound_test.model import SoundTestSession


SCREEN_WIDTH = 560
SCREEN_HEIGHT = 360
LIST_Y = 104
ROW_HEIGHT = 16
VISIBLE_ROWS = 10
PANEL_X = (12, 284)
PANEL_WIDTH = 264
TEXT_COLOR = 5
MUTED_COLOR = 4
PANEL_COLOR = 2
SELECTED_COLOR = 12
ACCENT_COLOR = 13


@dataclass(frozen=True)
class Button:
    action: str
    label: str
    x: int
    y: int
    width: int
    selected: bool = False

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + 22


class SoundTestApp:
    def __init__(self, project_root: Path) -> None:
        app_root = project_root / "app"
        pyxel.init(SCREEN_WIDTH, SCREEN_HEIGHT, title="Dungeon Antiqua ZERO Sound Test",
                   fps=60, display_scale=2, quit_key=pyxel.KEY_NONE)
        pyxel.load(str(app_root / "assets.pyxres"))
        pyxel.load_pal(str(app_root / "assets.pyxpal"))
        pyxel.mouse(True)
        self.font = FontResources(app_root / "fonts").font_for(Language.JAPANESE)
        self.session = SoundTestSession(app_root, pyxel_api=pyxel)
        self.focus = 0
        self.status = "BGMを選んで再生し、SEを試聴してください。"
        self.error = False

    def _buttons(self) -> tuple[Button, ...]:
        buttons = []
        for column, volume in enumerate((self.session.bgm.volume, self.session.se.volume)):
            for level in range(5):
                buttons.append(Button(f"volume_{column}_{level}", str(level),
                                      PANEL_X[column] + 116 + level * 30, 40, 26,
                                      selected=level == volume))
        buttons.extend((
            Button("pyxel", "Pyxel", 340, 76, 100, not self.session.use_wav),
            Button("wav", "WAV", 448, 76, 100, self.session.use_wav),
            Button("bgm_play", "BGM再生", 12, 278, 126),
            Button("bgm_stop", "BGM停止", 144, 278, 132),
            Button("se_play", "SE再生", 284, 278, 126),
            Button("se_stop", "SE停止", 416, 278, 132),
        ))
        return tuple(buttons)

    @staticmethod
    def _scroll(index: int, count: int) -> int:
        return max(0, min(index - VISIBLE_ROWS // 2, count - VISIBLE_ROWS))

    def _move_selection(self, delta: int) -> None:
        if self.focus == 0:
            self.session.select_bgm(self.session.bgm_index + delta)
        else:
            self.session.select_se(self.session.se_index + delta)

    def _activate(self, action: str) -> None:
        if action.startswith("volume_"):
            _, column, level = action.split("_")
            self.session.set_volume(bgm=column == "0", volume=int(level))
        elif action in ("pyxel", "wav"):
            self.session.use_wav = action == "wav"
            self.focus = 1
        elif action == "bgm_play":
            self.session.play_bgm()
        elif action == "bgm_stop":
            self.session.bgm.stop()
        elif action == "se_play":
            self.session.play_se()
        elif action == "se_stop":
            self.session.stop_se()

    def _handle_mouse(self) -> None:
        x, y = pyxel.mouse_x, pyxel.mouse_y
        clicked = pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT)
        if clicked:
            for button in self._buttons():
                if button.contains(x, y):
                    self._activate(button.action)
                    return
        for column, panel_x in enumerate(PANEL_X):
            if panel_x <= x < panel_x + PANEL_WIDTH and LIST_Y <= y < LIST_Y + ROW_HEIGHT * VISIBLE_ROWS:
                if clicked or pyxel.mouse_wheel:
                    self.focus = column
                if clicked:
                    count = len(self.session.bgm_ids if column == 0 else self.session.se_options)
                    index = self.session.bgm_index if column == 0 else self.session.se_index
                    row = (y - LIST_Y) // ROW_HEIGHT
                    selected = self._scroll(index, count) + row
                    if selected < count:
                        if column == 0:
                            self.session.select_bgm(selected)
                        else:
                            self.session.select_se(selected)
                elif pyxel.mouse_wheel:
                    self._move_selection(-pyxel.mouse_wheel * 3)

    def update(self) -> None:
        if pyxel.btnp(pyxel.KEY_Q) or pyxel.btnp(pyxel.KEY_ESCAPE):
            self.session.close()
            pyxel.quit()
            return
        try:
            self.session.bgm.update()
            if pyxel.btnp(pyxel.KEY_TAB):
                self.focus = 1 - self.focus
            if pyxel.btnp(pyxel.KEY_UP, 15, 4):
                self._move_selection(-1)
            elif pyxel.btnp(pyxel.KEY_DOWN, 15, 4):
                self._move_selection(1)
            elif pyxel.btnp(pyxel.KEY_PAGEUP, 15, 4):
                self._move_selection(-VISIBLE_ROWS)
            elif pyxel.btnp(pyxel.KEY_PAGEDOWN, 15, 4):
                self._move_selection(VISIBLE_ROWS)
            if self.focus == 1:
                if pyxel.btnp(pyxel.KEY_LEFT):
                    self.session.use_wav = False
                elif pyxel.btnp(pyxel.KEY_RIGHT):
                    self.session.use_wav = True
            if pyxel.btnp(pyxel.KEY_SPACE):
                self._activate("bgm_stop" if self.session.bgm.is_playing else "bgm_play")
            if pyxel.btnp(pyxel.KEY_RETURN):
                self.session.play_se()
            self._handle_mouse()
        except (AudioResourceError, AudioCatalogError, OSError, ValueError) as error:
            self.status = str(error)
            self.error = True
        else:
            if self.error:
                # Keep an error visible until the next explicit input succeeds.
                if not (pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT) or pyxel.btnp(pyxel.KEY_RETURN)
                        or pyxel.btnp(pyxel.KEY_SPACE)):
                    return
            self.error = False
            self.status = "BGMを選んで再生し、SEを試聴してください。"

    def _text(self, x: int, y: int, value: str, color: int = TEXT_COLOR) -> None:
        pyxel.text(x, y, value, color, self.font)

    def _draw_list(self, column: int, labels: tuple[str, ...], index: int) -> None:
        x = PANEL_X[column]
        pyxel.rect(x, LIST_Y, PANEL_WIDTH, VISIBLE_ROWS * ROW_HEIGHT, PANEL_COLOR)
        pyxel.rectb(x - 1, LIST_Y - 1, PANEL_WIDTH + 2, VISIBLE_ROWS * ROW_HEIGHT + 2,
                    ACCENT_COLOR if self.focus == column else 3)
        start = self._scroll(index, len(labels))
        for row, label in enumerate(labels[start:start + VISIBLE_ROWS]):
            y = LIST_Y + row * ROW_HEIGHT
            if start + row == index:
                pyxel.rect(x, y, PANEL_WIDTH, ROW_HEIGHT, SELECTED_COLOR)
            # Clip long resource names while showing all aliases in the detail line.
            pyxel.clip(x + 4, y, PANEL_WIDTH - 8, ROW_HEIGHT)
            self._text(x + 4, y + 2, label)
            pyxel.clip()
        if not labels:
            self._text(x + 8, LIST_Y + 8, "ファイルがありません", MUTED_COLOR)
        count = f"{index + 1 if labels else 0}/{len(labels)}"
        pyxel.text(x + PANEL_WIDTH - len(count) * 4,
                   LIST_Y + ROW_HEIGHT * VISIBLE_ROWS + 3, count, MUTED_COLOR)

    def draw(self) -> None:
        pyxel.cls(0)
        self._text(12, 10, "サウンドテスト", 33)
        self._text(12, 44, "BGM音量")
        self._text(284, 44, "SE音量")
        self._text(12, 81, "BGM")
        self._text(284, 81, "SE")
        for button in self._buttons():
            pyxel.rect(button.x, button.y, button.width, 22,
                       SELECTED_COLOR if button.selected else PANEL_COLOR)
            pyxel.rectb(button.x, button.y, button.width, 22,
                        ACCENT_COLOR if button.selected else 3)
            self._text(button.x + 8, button.y + 4, button.label,
                       TEXT_COLOR if button.selected else MUTED_COLOR)
        self._draw_list(0, self.session.bgm_ids, self.session.bgm_index)
        self._draw_list(1, tuple(option.label for option in self.session.se_options),
                        self.session.se_index)
        # Smaller text below the lists retains the complete catalog aliases.
        pyxel.text(12, 307, f"BGM: {self.session.bgm.current_id or 'STOPPED'}", 21)
        if self.session.se_options:
            label = self.session.se_options[self.session.se_index].label
            for line in range(2):
                pyxel.text(284, 307 + line * 8, label[line * 66:(line + 1) * 66], 21)
        self._text(12, 328, self.status[:66], 49 if self.error else MUTED_COLOR)
        pyxel.text(12, 349,
                   "Tab:List  Up/Down/Page:Select  Left/Right:SE Type  Space:BGM  Enter:SE  Q/Esc:Quit",
                   MUTED_COLOR)
