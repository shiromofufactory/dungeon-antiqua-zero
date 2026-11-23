"""Shared tactics overlay for the field settings and battle commands."""

from collections.abc import Mapping

from input import InputAction, InputDevice, InputState
from item import Item
from localization import Localizer
from member import Member, ProficiencyAptitude
from resources import FontResources, FontRole
from spell import SPELL_PROFICIENCY_BY_TYPE, SPELL_TYPE_ICON_TAGS
from state import AUTO_BATTLE_ITEM_KEYS, Language, SaveData
from text_catalog import TextCatalog
from ui import (
    DISABLED_COLOR,
    TEXT_GRID_X,
    CursorTarget,
    LocalizedWindowTextFactory,
    WindowFactory,
    input_icon_tag,
)
from ui.spell_menu import SPELL_TYPE_ORDER
from ui.tagged_text import ICON_SIZE


WINDOW_GRID = (1, 4, 62, 52)
HEADING_X = 2
LABEL_X = HEADING_X + 2
SPELL_X = (26, 38, 50)
ITEM_VALUE_X = 28
TITLE_Y = 2
SPELL_HEADING_Y = 6
MEMBER_FIRST_Y = 10
ITEM_HEADING_Y = 30
ITEM_FIRST_Y = 34
GUIDE_Y = 47
ROW_HEIGHT = 3
CURSOR_OFFSET = 2


class AutoBattleOverlay:
    def __init__(
        self,
        *,
        party: tuple[Member, ...],
        items: Mapping[str, Item],
        save_data: SaveData,
        localizer: Localizer,
        texts: TextCatalog,
        fonts: FontResources,
        input_device: InputDevice,
    ) -> None:
        self.party = party
        self.items = items
        self.save_data = save_data
        self.localizer = localizer
        self.texts = texts
        self.input_device = input_device
        language = localizer.language
        factory = LocalizedWindowTextFactory.from_language(fonts, language)
        self.spell_heading_font = None
        self.spell_heading_offset = 0
        if language is Language.JAPANESE:
            self.spell_heading_font = fonts.font_for(language, role=FontRole.LARGE)
            self.spell_heading_offset = fonts.baseline_offset_for(
                language, role=FontRole.LARGE
            )
        self.window = WindowFactory(factory.font, text_style=factory.apply).create(
            *WINDOW_GRID
        )
        self.spell_columns = dict(zip(SPELL_TYPE_ORDER, SPELL_X, strict=True))
        targets = [
            CursorTarget(
                x - CURSOR_OFFSET,
                MEMBER_FIRST_Y + index * ROW_HEIGHT,
                key=(member.definition.key, spell_type.value),
                selectable=(
                    member.proficiency(SPELL_PROFICIENCY_BY_TYPE[spell_type]).aptitude
                    is not ProficiencyAptitude.DISABLED
                ),
            )
            for index, member in enumerate(party)
            for spell_type, x in self.spell_columns.items()
        ]
        targets.extend(
            CursorTarget(
                ITEM_VALUE_X - CURSOR_OFFSET,
                ITEM_FIRST_Y + index * ROW_HEIGHT,
                key=key,
            )
            for index, key in enumerate(AUTO_BATTLE_ITEM_KEYS)
        )
        self.cursor = self.window.set_cursor(targets)
        self._refresh_texts()

    def _text(self, suffix: str) -> str:
        return self.texts.text(f"auto_battle.{suffix}", self.localizer)

    def _refresh_texts(self) -> None:
        config = self.save_data.auto_battle
        self.window.clear_texts()
        self.window.add_text(self._text("heading"), HEADING_X, TITLE_Y)
        self.window.add_text(self._text("spells"), HEADING_X, SPELL_HEADING_Y)
        for spell_type, x in self.spell_columns.items():
            self.window.add_text(
                SPELL_TYPE_ICON_TAGS[spell_type] + self._text(spell_type.value),
                x - ICON_SIZE // TEXT_GRID_X,
                SPELL_HEADING_Y,
                font=self.spell_heading_font,
                baseline_offset=self.spell_heading_offset,
            )
        for index, member in enumerate(self.party):
            self.window.add_text(
                member.definition.localized_name(self.localizer),
                LABEL_X,
                MEMBER_FIRST_Y + index * ROW_HEIGHT,
            )
        self.window.add_text(self._text("items"), HEADING_X, ITEM_HEADING_Y)
        for target in self.cursor.targets:
            key = target.key
            x = target.x + CURSOR_OFFSET
            if isinstance(key, tuple):
                if not target.selectable:
                    self.window.add_text("─", x, target.y, color=DISABLED_COLOR)
                    continue
                enabled = config.uses_spell(*key)
            else:
                self.window.add_text(
                    self.items[key].localized_name(self.localizer), LABEL_X, target.y
                )
                enabled = key in config.allowed_items
            self.window.add_text(self._text("use" if enabled else "skip"), x, target.y)
        guide = self._text("guide").replace(
            "%CONFIRM%", input_icon_tag(InputAction.CONFIRM, self.input_device)
        ).replace(
            "%CANCEL%", input_icon_tag(InputAction.CANCEL, self.input_device)
        )
        self.window.add_text(guide, HEADING_X, GUIDE_Y)

    def update(self, input_state: InputState) -> bool:
        """Return True when the caller should dismiss the overlay."""

        if input_state.cancel.triggered:
            return True
        device_changed = input_state.device is not self.input_device
        self.input_device = input_state.device
        if input_state.confirm.triggered:
            key = self.cursor.selected_key
            config = self.save_data.auto_battle
            self.save_data.auto_battle = (
                config.toggle_spell(*key) if isinstance(key, tuple)
                else config.toggle_item(key)
            )
            self._refresh_texts()
            return False
        if device_changed:
            self._refresh_texts()
        navigation = input_state.navigation
        if navigation is not None and navigation.dy:
            self._move_vertically(navigation.dy)
            navigation = None
        self.window.update(navigation)
        return False

    def _move_vertically(self, distance: int) -> None:
        """Move one selectable row, then choose its closest column."""

        current = self.cursor.selected_target
        selectable = [target for target in self.cursor.targets if target.selectable]
        rows = sorted({target.y for target in selectable})
        row = rows[(rows.index(current.y) + distance) % len(rows)]
        destination = min(
            (target for target in selectable if target.y == row),
            key=lambda target: (abs(target.x - current.x), target.x),
        )
        self.cursor.select_key(destination.key)

    def draw(self) -> None:
        self.window.draw()
