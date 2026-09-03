"""Spell-menu overlay shared by the game and development harnesses."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from enum import Enum

import pyxel

from ui.party_status import (
    PARTY_COLUMN_WIDTH,
    PARTY_CURSOR_Y,
    PARTY_FACE_X,
    PARTY_FACE_Y,
    PARTY_HP_Y,
    PARTY_MAX_HP_Y,
    PARTY_TEXT_X,
    PARTY_WINDOW_GRID,
    PartyStatusPanel,
)
from input import InputState
from localization import Localizer
from member import Member
from resources import TRANSPARENT_INDEX, FontResources
from spell import Spell, SpellType
from state import Language, Settings
from text_catalog import TextCatalog
from ui import (
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    CursorTarget,
    LocalizedWindowTextFactory,
    WindowCursor,
    WindowFactory,
    WindowText,
    pad,
)

FACES_IMAGE_ID = "faces/faces_pc"
MEMBER_WINDOW_GRID = (0, 0, 28, 12)
GUIDE_WINDOW_GRID = (28, 0, 36, 12)
SPELL_WINDOW_GRID = (0, 12, 64, 33)
MEMBER_FACE_X = 8
MEMBER_FACE_Y = 8
MEMBER_TEXT_X = 12
MEMBER_NAME_Y = 2
MEMBER_CURSOR_X = MEMBER_TEXT_X - 2
MEMBER_MP_LABEL_Y = 5
MEMBER_MP_VALUE_Y = 8
FACE_SIZE = 32

SPELL_TYPE_ORDER = (
    SpellType.MYSTIC,
    SpellType.SACRED,
    SpellType.NETHER,
)
SPELL_DISPLAY_LEVELS = (*range(1, 10), 0)
SPELL_TEXT_X = (4, 24, 44)
SPELL_CURSOR_X = (2, 22, 42)
SPELL_FIRST_Y = 2
SPELL_ROW_HEIGHT = 3

class SpellSelectionPhase(Enum):
    """Selection stage used by the DA2-style spell menu."""

    CASTER = "caster"
    SPELL = "spell"
    TARGET = "target"


class SpellMenuDataError(RuntimeError):
    """Raised when data required by the spell menu is unavailable."""


class SpellMenuOverlay:
    def __init__(
        self,
        *,
        party: tuple[Member, ...],
        spells: Mapping[str, Spell],
        settings: Settings,
        texts: TextCatalog,
        fonts: FontResources,
        faces: object,
        member_index: int = 0,
        event_spell_keys: Collection[str] = (),
    ) -> None:
        """Build a DA2-style spell view from menu-owned state."""

        if not party:
            raise ValueError("party must contain at least one member")
        if (
            isinstance(member_index, bool)
            or not isinstance(member_index, int)
            or not 0 <= member_index < len(party)
        ):
            raise ValueError("member_index must identify a party member")
        spell_catalog = spells
        if not isinstance(spell_catalog, Mapping) or not all(
            isinstance(key, str) and isinstance(spell, Spell)
            for key, spell in spell_catalog.items()
        ):
            raise TypeError("spells must map string keys to Spell values")
        if isinstance(event_spell_keys, (str, bytes)) or not all(
            isinstance(key, str) for key in event_spell_keys
        ):
            raise TypeError("event_spell_keys must contain strings")

        self.party = party
        self.spells = dict(spell_catalog)
        self.settings = settings
        self.texts = texts
        self.fonts = fonts
        self.faces = faces
        self.member_index = member_index
        self.event_spell_keys = frozenset(event_spell_keys)
        self.phase = SpellSelectionPhase.CASTER
        self._spells_by_position = self._index_spells()
        self._build_windows()

    @property
    def member(self) -> Member:
        """Return the party member whose spells are currently shown."""

        return self.party[self.member_index]

    @property
    def selected_spell(self) -> Spell | None:
        """Return the spell under the cursor, if this member knows one."""

        key = self.spell_cursor.selected_key
        return self.spells.get(key) if isinstance(key, str) else None

    def _index_spells(self) -> dict[tuple[SpellType, int], Spell]:
        indexed: dict[tuple[SpellType, int], Spell] = {}
        for spell in self.spells.values():
            if spell.type is SpellType.ITEM:
                continue
            position = (spell.type, spell.level)
            if position in indexed:
                raise SpellMenuDataError(
                    f"同じ種別・レベルの呪文が重複しています: "
                    f"{spell.type.value} level {spell.level}"
                )
            indexed[position] = spell
        return indexed

    def _localized_labels(self, localizer: Localizer) -> dict[str, str]:
        labels = {}
        for key in ("menu.member.hp", "menu.member.mp", "spell.mp_cost"):
            label = self.texts.text(key, localizer)
            if not label:
                raise SpellMenuDataError(f"呪文用テキストが見つかりません: {key}")
            labels[key] = label
        return labels

    def _build_windows(self) -> None:
        localizer = Localizer(self.settings.language)
        self.localizer = localizer
        self.localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )
        self.labels = self._localized_labels(localizer)
        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))

        self.member_window = windows.create(
            *MEMBER_WINDOW_GRID,
            (
                self.localized_texts.create(
                    self.member.definition.localized_name(localizer),
                    MEMBER_TEXT_X,
                    MEMBER_NAME_Y,
                ),
                self.localized_texts.create(
                    self.labels["menu.member.mp"],
                    MEMBER_TEXT_X,
                    MEMBER_MP_LABEL_Y,
                    color=(
                        DISABLED_COLOR
                        if self.member.max_mp == 0
                        else DEFAULT_TEXT_COLOR
                    ),
                ),
                self.localized_texts.create(
                    self._point_text(self.member.mp, self.member.max_mp),
                    MEMBER_TEXT_X,
                    MEMBER_MP_VALUE_Y,
                    color=(
                        DISABLED_COLOR
                        if self.member.max_mp == 0
                        else DEFAULT_TEXT_COLOR
                    ),
                ),
            ),
            horizontal_navigation=len(self.party) > 1,
            active=self.phase is SpellSelectionPhase.CASTER,
        )
        self.caster_cursor = WindowCursor(
            self.member_window,
            (
                CursorTarget(
                    MEMBER_CURSOR_X,
                    MEMBER_NAME_Y,
                    key=self.member_index,
                ),
            ),
            active=self.phase is SpellSelectionPhase.CASTER,
        )

        spell_texts, targets = self._spell_texts_and_targets()
        self.spell_window = windows.create(*SPELL_WINDOW_GRID, spell_texts)
        self.spell_cursor = WindowCursor(
            self.spell_window,
            targets,
            active=self.phase is SpellSelectionPhase.SPELL,
        )

        self.guide_window = windows.create(
            *GUIDE_WINDOW_GRID,
            self._guide_texts(),
        )
        self.party_panel = PartyStatusPanel(
            party=self.party,
            localizer=self.localizer,
            texts=self.texts,
            text_factory=self.localized_texts,
            window_factory=windows,
            faces=self.faces,
            cursor_active=self.phase is SpellSelectionPhase.TARGET,
        )
        self.party_window = self.party_panel.window
        self.member_cursor = self.party_panel.cursor
        self.windows = (
            self.member_window,
            self.guide_window,
            self.spell_window,
            self.party_window,
        )

    @staticmethod
    def _point_text(current: int, maximum: int) -> str:
        return f"{pad(current, 3)}／{pad(maximum, 3)}"

    def _spell_texts_and_targets(
        self,
    ) -> tuple[tuple[WindowText, ...], tuple[CursorTarget, ...]]:
        texts: list[WindowText] = []
        targets: list[CursorTarget] = []
        for row, level in enumerate(SPELL_DISPLAY_LEVELS):
            y = SPELL_FIRST_Y + row * SPELL_ROW_HEIGHT
            for column, spell_type in enumerate(SPELL_TYPE_ORDER):
                spell = self._spells_by_position.get((spell_type, level))
                if spell is None or not spell.is_learned_by(
                    self.member,
                    self.event_spell_keys,
                ):
                    continue
                color = (
                    DEFAULT_TEXT_COLOR
                    if spell.on_camp and self.member.mp >= spell.mp
                    else DISABLED_COLOR
                )
                texts.append(
                    self.localized_texts.create(
                        spell.localized_display_name(self.localizer),
                        SPELL_TEXT_X[column],
                        y,
                        color=color,
                    )
                )
                targets.append(
                    CursorTarget(
                        SPELL_CURSOR_X[column],
                        y,
                        key=spell.key,
                    )
                )
        return tuple(texts), tuple(targets)

    def _guide_texts(self) -> tuple[WindowText, ...]:
        if self.phase is not SpellSelectionPhase.SPELL:
            return ()
        spell = self.selected_spell
        if spell is None:
            return ()
        lines = spell.localized_description(self.localizer)
        texts = [
            self.localized_texts.create(line, 2, 2 + index * 3)
            for index, line in enumerate(lines[:2])
        ]
        texts.append(
            self.localized_texts.create(
                self.labels["spell.mp_cost"].replace("%MP%", pad(spell.mp, 2)),
                2,
                8,
            )
        )
        return tuple(texts)

    def _refresh_guide(self) -> None:
        self.guide_window.clear_texts()
        for placement in self._guide_texts():
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

    def _switch_member(self, distance: int) -> None:
        if distance not in (-1, 1):
            raise ValueError("member switch distance must be -1 or 1")
        self.member_index = (self.member_index + distance) % len(self.party)
        self._build_windows()

    def _enter_spell_selection(self) -> None:
        if self.selected_spell is None:
            return
        self.phase = SpellSelectionPhase.SPELL
        self.caster_cursor.active = False
        self.member_window.active = False
        self.spell_cursor.active = True
        self._refresh_guide()

    def _return_to_caster_selection(self) -> None:
        self.phase = SpellSelectionPhase.CASTER
        self.caster_cursor.active = True
        self.member_window.active = True
        self.spell_cursor.active = False
        self._refresh_guide()

    def _enter_target_selection(self) -> None:
        spell = self.selected_spell
        if spell is None or not spell.on_camp or self.member.mp < spell.mp:
            return
        self.phase = SpellSelectionPhase.TARGET
        self.spell_cursor.active = False
        self.member_cursor.active = True

    def _return_to_spell_selection(self) -> None:
        self.phase = SpellSelectionPhase.SPELL
        self.spell_cursor.active = True
        self.member_cursor.active = False

    def update(self, input_state: InputState) -> bool:
        """Update selection and report whether the menu should be restored."""

        if self.phase is SpellSelectionPhase.CASTER:
            self.caster_cursor.update()
            if input_state.cancel.triggered:
                return True
            if input_state.previous_page.triggered:
                self._switch_member(-1)
                return False
            if input_state.next_page.triggered:
                self._switch_member(1)
                return False
            if input_state.navigation is not None:
                if input_state.navigation.dx < 0:
                    self._switch_member(-1)
                elif input_state.navigation.dx > 0:
                    self._switch_member(1)
                return False
            if input_state.confirm.triggered:
                self._enter_spell_selection()
            return False

        if self.phase is SpellSelectionPhase.SPELL:
            if input_state.cancel.triggered:
                self._return_to_caster_selection()
                return False
            if input_state.confirm.triggered:
                self._enter_target_selection()
                return False
            if self.spell_cursor.update(input_state.navigation):
                self._refresh_guide()
            return False

        if input_state.cancel.triggered:
            self._return_to_spell_selection()
            return False
        self.member_cursor.update(input_state.navigation)
        # Confirm intentionally does nothing until spell effects are implemented.
        return False

    def draw(self) -> None:
        for window in self.windows:
            window.draw()

        face_position = self.member.face_position
        pyxel.blt(
            MEMBER_FACE_X,
            MEMBER_FACE_Y,
            self.faces,
            face_position.x,
            face_position.y,
            FACE_SIZE,
            FACE_SIZE,
            TRANSPARENT_INDEX,
        )
        self.party_panel.draw_faces()
        self.caster_cursor.draw()
        if self.phase in (
            SpellSelectionPhase.SPELL,
            SpellSelectionPhase.TARGET,
        ):
            self.spell_cursor.draw()
        if self.phase is SpellSelectionPhase.TARGET:
            self.member_cursor.draw()


__all__ = [
    "SpellMenuDataError",
    "SpellMenuOverlay",
    "SpellSelectionPhase",
]
