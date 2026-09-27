"""Centered, confirm-driven notice for spells unlocked by proficiency growth."""

from __future__ import annotations

from collections.abc import Iterable

from input import InputState
from localization import Localizer
from member import Member, ProficiencyKind
from resources import FontResources
from spell import SPELL_PROFICIENCY_BY_TYPE, Spell, SpellType
from state import Language, Settings
from text_catalog import TextCatalog

from .localized_text import LocalizedWindowTextFactory
from .tagged_text import tagged_text_width
from .window import TEXT_GRID_X, Window, WindowFactory

SCREEN_GRID_WIDTH = 64
SCREEN_GRID_HEIGHT = 60
POPUP_BASE_HEIGHT_GRID = 7
POPUP_LINE_HEIGHT_GRID = 3
POPUP_PADDING_GRID = 2


def newly_learned_spells(
    kind: ProficiencyKind,
    before_level: int,
    after_level: int,
    spells: Iterable[Spell],
) -> tuple[Spell, ...]:
    """Return only spells first made usable by this level increase."""

    return tuple(
        sorted(
            (
                spell
                for spell in spells
                if spell.type is not SpellType.ITEM
                and SPELL_PROFICIENCY_BY_TYPE[spell.type] is kind
                and before_level < spell.level <= after_level
            ),
            key=lambda spell: spell.level,
        )
    )


class SpellLearnedPopup:
    """Show each new spell in a text-sized window until confirmed."""

    def __init__(
        self,
        notices: Iterable[tuple[Member, Spell]],
        *,
        settings: Settings,
        texts: TextCatalog,
        fonts: FontResources,
        center_y_grid: int = SCREEN_GRID_HEIGHT // 2,
    ) -> None:
        self.notices = tuple(notices)
        if not self.notices:
            raise ValueError("spell learned popup requires at least one notice")
        self.index = 0
        self.center_y_grid = center_y_grid
        self.localizer = Localizer(settings.language)
        self.texts = texts
        self.placements = LocalizedWindowTextFactory.from_language(
            fonts, settings.language
        )
        self.windows = WindowFactory(fonts.font_for(Language.JAPANESE))
        self.window = self._create_window()

    def _create_window(self) -> Window:
        member, spell = self.notices[self.index]
        message = self.texts.formatted_text(
            "spell.learned",
            self.localizer,
            {
                "MEMBER": member.definition.localized_name(self.localizer),
                "SPELL": spell.localized_display_name(self.localizer),
            },
        )
        lines = [message]
        max_text_width = (SCREEN_GRID_WIDTH - 2 * POPUP_PADDING_GRID) * TEXT_GRID_X
        if self._text_width(message) > max_text_width:
            lines = []
            current = ""
            for word in message.split():
                candidate = f"{current} {word}" if current else word
                if current and self._text_width(candidate) > max_text_width:
                    lines.append(current)
                    current = word
                else:
                    current = candidate
            lines.append(current)
        placements = tuple(
            self.placements.create(
                line, POPUP_PADDING_GRID, 2 + index * POPUP_LINE_HEIGHT_GRID
            )
            for index, line in enumerate(lines)
        )
        text_width = max(
            tagged_text_width(item.text, item.font, font_spans=item.font_spans)
            for item in placements
        )
        width = (text_width + TEXT_GRID_X - 1) // TEXT_GRID_X + 2 * POPUP_PADDING_GRID
        if width > SCREEN_GRID_WIDTH:
            raise ValueError("learned spell notice exceeds the screen width")
        height = POPUP_BASE_HEIGHT_GRID + (len(lines) - 1) * POPUP_LINE_HEIGHT_GRID
        window = self.windows.create(
            (SCREEN_GRID_WIDTH - width) // 2,
            self.center_y_grid - height // 2,
            width,
            height,
        )
        for placement in placements:
            window.add_text(
                placement.text,
                placement.x,
                placement.y,
                color=placement.color,
                font=placement.font,
                shadow_color=placement.shadow_color,
                baseline_offset=placement.baseline_offset,
                font_spans=placement.font_spans,
            )
        return window

    def _text_width(self, message: str) -> int:
        placement = self.placements.create(message, 0, 0)
        return tagged_text_width(
            placement.text, placement.font, font_spans=placement.font_spans
        )

    def update(self, input_state: InputState) -> bool:
        """Return true after the last notice receives a fresh confirm."""

        if not input_state.confirm.triggered:
            return False
        self.index += 1
        if self.index == len(self.notices):
            return True
        self.window = self._create_window()
        return False

    def draw(self) -> None:
        self.window.draw()


__all__ = ["SpellLearnedPopup", "newly_learned_spells"]
