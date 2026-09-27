"""Manual auto-recovery settings and six-member status overlay."""

from __future__ import annotations

from dataclasses import replace
from collections.abc import Mapping
from collections.abc import Callable

from input import Direction, InputState
from item import Item
from localization import Localizer
from member import Member
from rendering import PaletteShifter
from resources import FontResources, play_se
from spell import Spell, SpellType
from state import AutoRecoveryMethod, Language, SaveData, Settings
from systems.auto_recovery import (
    RECOVERY_ITEM_KEYS,
    RecoveryResult,
    eligible_healer_keys,
    execute_auto_recovery,
    valid_config_for_party,
)
from systems.inventory import InventorySystem
from text_catalog import TextCatalog
from ui import (
    DISABLED_COLOR,
    CursorTarget,
    LocalizedWindowTextFactory,
    Window,
    WindowFactory,
    pad,
)
from ui.party_status import draw_member_face_at
from ui.spell_proficiency import (
    PROFICIENCY_ANIMATION_FRAME_COUNT,
    PROFICIENCY_TEXT_X,
    PROFICIENCY_TEXT_Y,
    PROFICIENCY_WINDOW_SIZE_GRID,
    displayed_proficiency_total,
    spell_proficiency_text,
)
from ui.spell_learned import SpellLearnedPopup, newly_learned_spells

SETTINGS_WINDOW_GRID = (0, 0, 64, 16)
GUIDE_WINDOW_GRID = (0, 16, 64, 10)
PARTY_WINDOW_GRID = (0, 26, 64, 34)
ROW_KEYS = ("threshold", "method", "healer", "execute")
ROW_Y = (2, 5, 8, 11)
METHODS = (
    AutoRecoveryMethod.SPELLS,
    AutoRecoveryMethod.SPELLS_ITEMS,
    AutoRecoveryMethod.ITEMS_SPELLS,
)
THRESHOLDS = (60, 70, 80, 90, 100)
FACE_X = (52, 120, 188)
FACE_Y = (112, 176)
STATUS_LABEL_X = 4
STATUS_VALUE_X = (10, 27, 44)
HP_Y = (10, 26)
MP_Y = (13, 29)


class AutoRecoveryOverlay:
    def __init__(
        self,
        *,
        party: tuple[Member, ...],
        spells: Mapping[str, Spell],
        items: Mapping[str, Item],
        inventory: InventorySystem,
        save_data: SaveData,
        settings: Settings,
        texts: TextCatalog,
        fonts: FontResources,
        faces: object,
        palette_shifter: PaletteShifter | None = None,
        on_spell_level_up: Callable[[], None] | None = None,
    ) -> None:
        self.party = party
        self.spells = spells
        self.items = items
        self.inventory = inventory
        self.save_data = save_data
        self.settings = settings
        self.fonts = fonts
        self.on_spell_level_up = on_spell_level_up
        self.localizer = Localizer(settings.language)
        self.texts = texts
        self.faces = faces
        self.palette_shifter = palette_shifter
        self.factory = LocalizedWindowTextFactory.from_language(
            fonts, settings.language
        )
        self.number_font = fonts.font_for(Language.JAPANESE)
        windows = WindowFactory(fonts.font_for(Language.JAPANESE))
        self.window_factory = windows
        self.settings_window = windows.create(*SETTINGS_WINDOW_GRID)
        self.guide_window = windows.create(*GUIDE_WINDOW_GRID)
        self.party_window = windows.create(*PARTY_WINDOW_GRID)
        self.cursor = self.settings_window.set_cursor(
            tuple(
                CursorTarget(2, y, key=key)
                for key, y in zip(ROW_KEYS, ROW_Y, strict=True)
            )
        )
        self.cursor.select_key("execute")
        self.result: RecoveryResult | None = None
        self.proficiency_windows: dict[int, Window] = {}
        self._proficiency_frame: int | None = None
        self.spell_learned_popup: SpellLearnedPopup | None = None
        self.save_data.auto_recovery = valid_config_for_party(
            self.save_data.auto_recovery, self.party
        )
        self._refresh()

    def _label(self, key: str) -> str:
        return self.texts.text(key, self.localizer)

    def _healer_keys(self) -> tuple[str | None, ...]:
        return (None, *eligible_healer_keys(self.party))

    def _row_shift_grid(self, row: int) -> int:
        member_count = len(self.party[row * 3 : row * 3 + 3])
        return (3 - member_count) * 17 // 2

    def _value(self, key: str) -> str:
        config = self.save_data.auto_recovery
        if key == "threshold":
            return self._label(f"auto_recovery.threshold.{config.threshold}")
        if key == "method":
            return self._label(f"auto_recovery.method.{config.method.value}")
        if key == "healer":
            if config.healer_key is None:
                return self._label("auto_recovery.healer.balance")
            member = next(
                (
                    member
                    for member in self.party
                    if member.definition.key == config.healer_key
                ),
                None,
            )
            return (
                member.definition.localized_name(self.localizer)
                if member is not None
                else self._label("auto_recovery.healer.balance")
            )
        raise ValueError(f"unsupported auto recovery row: {key}")

    def _refresh(self) -> None:
        placements = []
        for key, y in zip(ROW_KEYS[:3], ROW_Y[:3], strict=True):
            placements.append(
                self.factory.create(self._label(f"auto_recovery.{key}.label"), 5, y)
            )
            placements.append(self.factory.create("：", 30, y))
            placements.append(self.factory.create(self._value(key), 34, y))
        placements.append(
            self.factory.create(self._label("auto_recovery.execute"), 5, ROW_Y[3])
        )
        if self.result is None:
            lines = self.texts.lines(
                f"auto_recovery.guide.{self.cursor.selected_key}", self.localizer
            )
        elif self.result.actions == 0:
            lines = (self._label("auto_recovery.result.none"),)
        else:
            lines = tuple(
                self.texts.formatted_text(
                    "auto_recovery.result.used",
                    self.localizer,
                    {
                        "ITEM": self.items[key].localized_name(self.localizer),
                        "USED": str(self.result.items_used.get(key, 0)),
                        "LEFT": str(self.inventory.quantity(key)),
                    },
                )
                for key in RECOVERY_ITEM_KEYS
                if self.result.items_used.get(key, 0) > 0
            )
        self.settings_window.clear_texts()
        for placement in placements:
            self.settings_window.add_text(
                placement.text,
                placement.x,
                placement.y,
                color=placement.color,
                font=placement.font,
                shadow_color=placement.shadow_color,
                baseline_offset=placement.baseline_offset,
                font_spans=placement.font_spans,
            )
        self.guide_window.clear_texts()
        for index, line in enumerate(lines[:2]):
            placement = self.factory.create(line, 4, 2 + index * 3)
            self.guide_window.add_text(
                placement.text,
                placement.x,
                placement.y,
                color=placement.color,
                font=placement.font,
                shadow_color=placement.shadow_color,
                baseline_offset=placement.baseline_offset,
                font_spans=placement.font_spans,
            )
        self.party_window.clear_texts()
        for row in range((min(len(self.party), 6) + 2) // 3):
            shift = self._row_shift_grid(row)
            self.party_window.add_text(
                "ＨＰ", STATUS_LABEL_X + shift, HP_Y[row], font=self.number_font, shadow_color=None
            )
            self.party_window.add_text(
                "ＭＰ", STATUS_LABEL_X + shift, MP_Y[row], font=self.number_font, shadow_color=None
            )
        for index, member in enumerate(self.party[:6]):
            row, col = divmod(index, 3)
            shift = self._row_shift_grid(row)
            for y, current, maximum, is_mp in (
                (HP_Y[row], member.hp, member.max_hp, False),
                (MP_Y[row], member.mp, member.max_mp, True),
            ):
                current_text = pad(current, 3)
                if self.result is not None:
                    if is_mp and index in self.result.mp_spent:
                        current_text = f"%COL_BLUE%{current_text}%COL_END%"
                    elif not is_mp and index in self.result.hp_recovered:
                        current_text = f"%COL_POSITIVE%{current_text}%COL_END%"
                self.party_window.add_text(
                    f"{current_text}／{pad(maximum, 3)}",
                    STATUS_VALUE_X[col] + shift,
                    y,
                    font=self.number_font,
                    color=DISABLED_COLOR if is_mp and maximum == 0 else 5,
                    shadow_color=None,
                )

    def _refresh_proficiency_windows(self) -> None:
        if self.result is None or self._proficiency_frame is None:
            return
        for index, window in self.proficiency_windows.items():
            growth = self.result.proficiency_growths[index]
            total = displayed_proficiency_total(growth, self._proficiency_frame)
            window.clear_texts()
            window.add_text(
                spell_proficiency_text(
                    SpellType.SACRED,
                    total,
                    previous_total=growth.before_total,
                ),
                PROFICIENCY_TEXT_X,
                PROFICIENCY_TEXT_Y,
            )

    def _start_proficiency_animation(self) -> None:
        self.proficiency_windows.clear()
        self._proficiency_frame = None
        if self.result is None:
            return
        for index in self.result.proficiency_growths:
            row, col = divmod(index, 3)
            shift = self._row_shift_grid(row)
            window = self.window_factory.create(
                STATUS_VALUE_X[col] + shift,
                PARTY_WINDOW_GRID[1] + HP_Y[row] - PROFICIENCY_WINDOW_SIZE_GRID[1],
                *PROFICIENCY_WINDOW_SIZE_GRID,
            )
            window.open_immediately()
            self.proficiency_windows[index] = window
        if self.proficiency_windows:
            self._proficiency_frame = 0
            self._refresh_proficiency_windows()

    def _clear_result(self) -> None:
        self.result = None
        self.proficiency_windows.clear()
        self._proficiency_frame = None
        self.spell_learned_popup = None

    def _show_learned_spells(self) -> None:
        if self.result is None:
            return
        notices = tuple(
            (self.party[index], spell)
            for index, growth in sorted(self.result.proficiency_growths.items())
            for spell in newly_learned_spells(
                growth.kind,
                growth.before_total // 100,
                growth.after_total // 100,
                self.spells.values(),
            )
        )
        if notices:
            self.spell_learned_popup = SpellLearnedPopup(
                notices,
                settings=self.settings,
                texts=self.texts,
                fonts=self.fonts,
                center_y_grid=GUIDE_WINDOW_GRID[1] + GUIDE_WINDOW_GRID[3] // 2,
            )

    def _cycle(self, key: str, direction: int) -> None:
        config = self.save_data.auto_recovery
        if key == "threshold":
            values = THRESHOLDS
            config = replace(
                config,
                threshold=values[
                    (values.index(config.threshold) + direction) % len(values)
                ],
            )
        elif key == "method":
            values = METHODS
            config = replace(
                config,
                method=values[(values.index(config.method) + direction) % len(values)],
            )
        elif key == "healer":
            values = self._healer_keys()
            config = replace(
                config,
                healer_key=values[
                    (values.index(config.healer_key) + direction) % len(values)
                ],
            )
        self.save_data.auto_recovery = config
        self._clear_result()
        self._refresh()

    def update(self, input_state: InputState) -> bool:
        """Return True when the user closes the overlay."""

        if self.spell_learned_popup is not None:
            if self.spell_learned_popup.update(input_state):
                self.spell_learned_popup = None
            return False
        if self._proficiency_frame is not None:
            if self._proficiency_frame < PROFICIENCY_ANIMATION_FRAME_COUNT:
                self._proficiency_frame += 1
                self._refresh_proficiency_windows()
                if (
                    self._proficiency_frame == PROFICIENCY_ANIMATION_FRAME_COUNT
                    and self.result is not None
                    and any(
                        growth.after_total // 100 > growth.before_total // 100
                        for growth in self.result.proficiency_growths.values()
                    )
                    and self.on_spell_level_up is not None
                ):
                    self.on_spell_level_up()
            else:
                self._proficiency_frame = None
                self._show_learned_spells()
            return False
        if input_state.cancel.triggered:
            return True
        key = self.cursor.selected_key
        if (
            input_state.navigation in (Direction.LEFT, Direction.RIGHT)
            and key != "execute"
        ):
            self._cycle(key, -1 if input_state.navigation is Direction.LEFT else 1)
            return False
        if input_state.confirm.triggered:
            if key == "execute":
                self.result = execute_auto_recovery(
                    self.party,
                    self.spells,
                    self.inventory,
                    self.save_data.auto_recovery,
                )
                if self.result.actions:
                    play_se("spell_healing1")
                self._refresh()
                self._start_proficiency_animation()
            else:
                self.cursor.select_key("execute")
                self._clear_result()
                self._refresh()
            return False
        if self.settings_window.update(input_state.navigation):
            self._clear_result()
            self._refresh()
        self.guide_window.update()
        self.party_window.update()
        return False

    def draw(self) -> None:
        self.settings_window.draw()
        self.guide_window.draw()
        self.party_window.draw()
        if not self.party_window.is_open:
            return
        for index, member in enumerate(self.party[:6]):
            row, col = divmod(index, 3)
            draw_member_face_at(
                member,
                x=FACE_X[col] + self._row_shift_grid(row) * 4,
                y=FACE_Y[row],
                faces=self.faces,
                palette_shifter=self.palette_shifter,
            )
        for window in self.proficiency_windows.values():
            window.draw()
        if self.spell_learned_popup is not None:
            self.spell_learned_popup.draw()


__all__ = ["AutoRecoveryOverlay"]
