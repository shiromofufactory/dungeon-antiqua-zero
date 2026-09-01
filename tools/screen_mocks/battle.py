"""Display the current battle-screen layout mock."""

from __future__ import annotations

import pyxel

from tools.screen_mocks._runner import run_screen_mock
from tools.screen_mocks._runtime import (
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    create_mock_input_reader,
    initialize_screen_mock,
)
from resources import (
    TRANSPARENT_INDEX,
    FontResourceError,
    FontResources,
    ImageResourceError,
    ImageResources,
)
from state import Language, Settings
from ui import CursorTarget, WindowFactory, WindowText

BACKGROUND_IMAGE_ID = "background/bg_nector"
CH_BATTLE_IMAGE_ID = "characters/ch_battle"
MONSTERS_IMAGE_IDS = ["monsters/1"]


class BattleScreenMock:
    def __init__(self) -> None:
        initialize_screen_mock("Dungeon Antiqua ZERO Battle Screen Mock")
        self.input_reader = create_mock_input_reader()

        resources = ImageResources()
        background_entry = resources.entry(BACKGROUND_IMAGE_ID)
        if (
            background_entry.width != SCREEN_WIDTH
            or background_entry.height != SCREEN_HEIGHT
        ):
            raise ImageResourceError(
                f"背景画像のサイズが画面と一致しません: {BACKGROUND_IMAGE_ID} "
                f"{background_entry.width}x{background_entry.height} / "
                f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}"
            )
        self.background = resources.image(BACKGROUND_IMAGE_ID)
        self.characters = resources.image(CH_BATTLE_IMAGE_ID)
        self.monsters = [resources.image(id) for id in MONSTERS_IMAGE_IDS]
        settings = Settings()
        fonts = FontResources()
        windows = WindowFactory(fonts.font_for(settings.language))
        font_6x8 = fonts.font_for(Language.ENGLISH)
        command_window = windows.create(
            34,
            0,
            30,
            13,
            (
                WindowText("たたかう", 4, 2),
                WindowText("ぼうぎょ", 4, 5),
                WindowText("じゅもん", 4, 8),
                WindowText("にげる", 18, 2),
                WindowText("アイテム", 18, 5),
                WindowText("こうたい", 18, 8),
            ),
            thin_frame=True,
            opened=False,
        )
        self.command_window = command_window
        self.command_cursor = command_window.set_cursor(
            (
                CursorTarget(2, 2, key="attack"),
                CursorTarget(2, 5, key="defend"),
                CursorTarget(2, 8, key="spell"),
                CursorTarget(16, 2, key="escape"),
                CursorTarget(16, 5, key="item"),
                CursorTarget(16, 8, key="formation"),
            )
        )
        self.selected_command: str | None = None
        self.windows = [command_window]

        for i in range(5):
            window = windows.create(52, 16 + i * 7, 7, 5, transparent=True)
            name = ("フィオラ", "セリオン", "アルヴァン", "エリカ", "ラグナ")[i]
            c = 5 if i == 0 else 4
            window.add_text(name, 0, 0, color=c)
            window.add_text("９９９／９９９", 0, 4, font=font_6x8, color=c)
            self.windows.append(window)
        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        input_state = self.input_reader.poll()
        if input_state.cancel.triggered:
            pyxel.quit()
            return

        if input_state.confirm.triggered:
            if self.command_window.is_closed:
                self.command_window.open()
            elif self.command_window.is_open:
                self.selected_command = self.command_cursor.selected_key
                self.command_window.close()

        self.command_window.update(input_state.navigation)

    def draw(self) -> None:
        """Draw the battle screen in explicit back-to-front order."""

        self._draw_background()
        self._draw_party()
        self._draw_monsters()
        self._draw_timeline()
        self._draw_windows()

    def _draw_background(self) -> None:
        pyxel.blt(
            0,
            0,
            self.background,
            0,
            0,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
        )

    def _draw_party(self) -> None:
        # キャラ絵（仮）
        for i in range(5):
            x = 156 + i * 4 + (16 if i in (1, 2, 4) else 0)
            pyxel.blt(
                x,
                64 + i * 28,
                self.characters,
                0,
                i * 32,
                16,
                32,
                TRANSPARENT_INDEX,
            )

    def _draw_monsters(self) -> None:
        # モンスター絵（仮）
        for i in range(5):
            x = (4, 4, 68, 68, 68)[i]
            y = (56, 120, 24, 88, 152)[i]
            pat = (0, 0, 0, 0, 0)[i]
            pyxel.blt(
                x,
                y,
                self.monsters[pat],
                0,
                0,
                64,
                64,
                TRANSPARENT_INDEX,
            )

    def _draw_timeline(self) -> None:
        # タイムライン（仮）
        base_x, base_y = 70, 220
        for i in range(6):
            u = (0, 2, 1, 3, 0, 0)[i]
            v = (3, 4, 4, 4, 0, 4)[i]
            c = 13 if i in (0, 4) else 49
            pyxel.blt(
                base_x + i * 20,
                base_y,
                1,
                u * 16,
                v * 16,
                16,
                16,
                TRANSPARENT_INDEX,
            )
            pyxel.rect(base_x + i * 20, base_y + 17, 16, 1, c)
            pyxel.rect(base_x + i * 20, base_y + 18, 16, 1, c - 1)
        pyxel.blt(
            base_x + 4,
            base_y - 8,
            0,
            88,
            16,
            8,
            8,
            TRANSPARENT_INDEX,
        )

    def _draw_windows(self) -> None:
        for window in self.windows:
            window.draw()


def main() -> int:
    return run_screen_mock(
        BattleScreenMock,
        expected_errors=(FontResourceError, ImageResourceError),
    )


if __name__ == "__main__":
    raise SystemExit(main())
