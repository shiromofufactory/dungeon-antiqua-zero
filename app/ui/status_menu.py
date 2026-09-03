"""Status-menu overlay shared by the game and development harnesses."""

from __future__ import annotations

from enum import Enum

import pyxel

from input import Direction, InputAction, InputDevice, InputState
from localization import Localizer
from member import (
    BattleStats,
    EquipmentSlot,
    Member,
    MemberDataError,
    ProficiencyAptitude,
    ProficiencyKind,
)
from resistance import ResistanceType
from resources import (
    TRANSPARENT_INDEX,
    FontResources,
)
from skill import Skill
from state import Language, Settings
from text_catalog import TextCatalog
from ui import (
    CursorTarget,
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    TEXT_ICONS,
    LocalizedWindowTextFactory,
    Window,
    WindowCursor,
    WindowFactory,
    WindowText,
    input_icon_tag,
    pad,
)

FACES_IMAGE_ID = "faces/faces_pc"
STATUS_TEXT_KEYS = {
    "label.condition": "status.condition",
    "label.strength": "status.strength",
    "label.agility": "status.agility",
    "label.magic": "status.magic",
    "label.skill": "status.skill",
    "label.equip.right": "status.equip.right",
    "label.equip.left": "status.equip.left",
    "label.equip.body": "status.equip.body",
    "label.equip.head": "status.equip.head",
    "label.equip.arm": "status.equip.arm",
    "label.attack": "status.attack",
    "label.hit": "status.hit",
    "label.defense": "status.defense",
    "label.evasion": "status.evasion",
    "label.spell_resistance": "status.spell_resistance",
    "label.tolerance": "status.tolerance",
}
LOCALIZED_POSITIONS = {
    (14, 2): "member.name",
    (14, 5): "member.race",
    (14, 8): "member.gender",
    (6, 20): "label.condition",
    (22, 20): "value.condition",
    (6, 26): "label.strength",
    (6, 29): "label.agility",
    (6, 32): "label.magic",
    (6, 38): "label.skill",
    (8, 41): "skill.0",
    (8, 44): "skill.1",
    (30, 8): "equipment.right",
    (30, 11): "equipment.left",
    (30, 14): "equipment.body",
    (30, 17): "equipment.head",
    (30, 20): "equipment.arm",
    (30, 26): "label.attack",
    (30, 29): "label.hit",
    (30, 32): "label.defense",
    (30, 35): "label.evasion",
    (30, 38): "label.spell_resistance",
    (30, 41): "label.tolerance",
}
PROFICIENCY_POSITIONS = (
    (ProficiencyKind.SWORD, "%SWORD%", 6, 49),
    (ProficiencyKind.KATANA, "%KATANA%", 20, 49),
    (ProficiencyKind.SPEAR, "%SPEAR%", 34, 49),
    (ProficiencyKind.KNIFE, "%KNIFE%", 48, 49),
    (ProficiencyKind.AXE, "%AXE%", 6, 52),
    (ProficiencyKind.HAMMER, "%HAMMER%", 20, 52),
    (ProficiencyKind.THROWING, "%THROWING%", 34, 52),
    (ProficiencyKind.ROD, "%ROD%", 48, 52),
    (ProficiencyKind.WAND, "%WAND%", 6, 55),
    (ProficiencyKind.MYSTIC, "%MYSTIC%", 20, 55),
    (ProficiencyKind.SACRED, "%SACRED%", 34, 55),
    (ProficiencyKind.NETHER, "%NETHER%", 48, 55),
)
RESISTANCE_POSITIONS = tuple(
    (resistance, 32 + index * 2, 44)
    for index, resistance in enumerate(
        (
            ResistanceType.FIRE,
            ResistanceType.FREEZE,
            ResistanceType.DARK,
            ResistanceType.SLEEP,
            ResistanceType.POISON,
            ResistanceType.PARALIZE,
            ResistanceType.CONFUSE,
            ResistanceType.SILENCE,
            ResistanceType.DEATH,
        )
    )
)
ATTACK_VALUE_X = 46
DUAL_ATTACK_VALUE_X = ATTACK_VALUE_X - 2
STATUS_WINDOW_GRID = (0, 0, 64, 60)
SKILL_GUIDE_WINDOW_GRID = (48, 1, 16, 4)
SKILL_DESCRIPTION_WINDOW_GRID = (0, 50, 64, 10)
SKILL_TEXT_X = 8
SKILL_CURSOR_X = 6
SKILL_FIRST_Y = 41
SKILL_ROW_HEIGHT = 3
DISPLAYED_SKILL_COUNT = 2


class StatusSelectionPhase(Enum):
    """Current interaction layer of the status screen."""

    STATUS = "status"
    SKILL = "skill"


class StatusMenuDataError(RuntimeError):
    """Raised when localized data required by the status view is unavailable."""


def proficiency_display(member: Member, kind: ProficiencyKind) -> str:
    """Format one member proficiency with fullwidth fixed-width numbers."""

    proficiency = member.proficiency(kind)
    level = pad(proficiency.level, 1, fill="0")
    progress = pad(proficiency.progress, 2, fill="0")
    return f"{level}－{progress}"


def attack_display(stats: BattleStats) -> str:
    """Format one- or two-weapon attack values."""

    right = pad(stats.attack_right, 2)
    if stats.attack_left is None:
        return right
    return f"{pad(stats.attack_right, 3)}－{pad(stats.attack_left, 3)}"


def hit_display(stats: BattleStats) -> str:
    """Format hit and its equipped-weapon level bonus."""

    bonus = stats.hit_bonus
    sign = "＋" if bonus >= 0 else "－"
    return f"{pad(stats.hit, 3)}" f"（{sign}{pad(abs(bonus), 2)}）"


def resistance_icon_tag(
    member: Member,
    resistance: ResistanceType,
) -> str:
    """Return the enabled or disabled icon tag for one resistance."""

    if resistance in member.resistances:
        return f"%{resistance.value}%"
    return f"%{resistance.value}_DISABLED%"


class StatusMenuOverlay:
    def __init__(
        self,
        *,
        party: tuple[Member, ...],
        settings: Settings,
        texts: TextCatalog,
        fonts: FontResources,
        faces: object,
        member_index: int = 0,
        input_device: InputDevice = InputDevice.KEYBOARD,
        window_factory_class: type[WindowFactory] = WindowFactory,
        window_cursor_class: type[WindowCursor] = WindowCursor,
    ) -> None:
        """Build a status view, reusing menu-owned state when supplied."""

        if not party:
            raise ValueError("party must contain at least one member")
        if (
            isinstance(member_index, bool)
            or not isinstance(member_index, int)
            or not 0 <= member_index < len(party)
        ):
            raise ValueError("member_index must identify a party member")
        if not isinstance(input_device, InputDevice):
            raise TypeError("input_device must be an InputDevice")
        self.party = party
        self.settings = settings
        self.texts = texts
        self.member_index = member_index
        self.fonts = fonts
        self.faces = faces
        self.input_device = input_device
        self.window_factory_class = window_factory_class
        self.window_cursor_class = window_cursor_class
        self.phase = StatusSelectionPhase.STATUS
        self._build_windows()

    @property
    def member(self) -> Member:
        """Return the party member currently shown by the status menu."""

        return self.party[self.member_index]

    @property
    def displayed_skills(self) -> tuple[Skill, ...]:
        """Return the skills that fit in the status screen's two rows."""

        return tuple(self.member.skills[:DISPLAYED_SKILL_COUNT])

    @property
    def selected_skill(self) -> Skill | None:
        """Return the displayed skill currently selected by the cursor."""

        selected_index = self.skill_cursor.selected_index
        if selected_index is None:
            return None
        return self.displayed_skills[selected_index]

    def _build_window(self) -> Window:
        """Build the complete status window for the current member."""

        localizer = Localizer(self.settings.language)
        localized = self._localized_texts(localizer)
        abilities = self.member.adjusted_abilities
        battle_stats = self.member.battle_stats
        localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )

        windows = self.window_factory_class(self.fonts.font_for(Language.JAPANESE))
        return windows.create(
            *STATUS_WINDOW_GRID,
            (
                localized_texts.create(localized["member.name"], 14, 2),
                localized_texts.create(localized["member.race"], 14, 5),
                localized_texts.create(localized["member.gender"], 14, 8),
                WindowText(
                    f"ＨＰ　{pad(self.member.hp, 3)}" f"／{pad(self.member.max_hp, 3)}",
                    6,
                    14,
                ),
                WindowText(
                    f"ＭＰ　{pad(self.member.mp, 3)}" f"／{pad(self.member.max_mp, 3)}",
                    6,
                    17,
                    color=(
                        DISABLED_COLOR
                        if self.member.max_mp == 0
                        else DEFAULT_TEXT_COLOR
                    ),
                ),
                localized_texts.create(localized["label.condition"], 6, 20),
                localized_texts.create(localized["value.condition"], 22, 20),
                localized_texts.create(localized["label.strength"], 6, 26),
                WindowText(pad(abilities.strength, 2), 20, 26),
                localized_texts.create(localized["label.agility"], 6, 29),
                WindowText(pad(abilities.agility, 2), 20, 29),
                localized_texts.create(localized["label.magic"], 6, 32),
                WindowText(pad(abilities.magic, 2), 20, 32),
                localized_texts.create(localized["label.skill"], 6, 38),
                localized_texts.create(
                    localized["skill.0"],
                    SKILL_TEXT_X,
                    SKILL_FIRST_Y,
                ),
                localized_texts.create(
                    localized["skill.1"],
                    SKILL_TEXT_X,
                    SKILL_FIRST_Y + SKILL_ROW_HEIGHT,
                ),
                localized_texts.create(localized["equipment.right"], 30, 8),
                localized_texts.create(localized["equipment.left"], 30, 11),
                localized_texts.create(localized["equipment.body"], 30, 14),
                localized_texts.create(localized["equipment.head"], 30, 17),
                localized_texts.create(localized["equipment.arm"], 30, 20),
                localized_texts.create(localized["label.attack"], 30, 26),
                WindowText(
                    attack_display(battle_stats),
                    (
                        DUAL_ATTACK_VALUE_X
                        if battle_stats.attack_left is not None
                        else ATTACK_VALUE_X
                    ),
                    26,
                ),
                localized_texts.create(localized["label.hit"], 30, 29),
                WindowText(hit_display(battle_stats), 44, 29),
                localized_texts.create(localized["label.defense"], 30, 32),
                WindowText(pad(battle_stats.defense, 2), 46, 32),
                localized_texts.create(localized["label.evasion"], 30, 35),
                WindowText(pad(battle_stats.evasion, 2), 46, 35),
                localized_texts.create(localized["label.spell_resistance"], 30, 38),
                WindowText(
                    pad(battle_stats.spell_resistance, 2),
                    46,
                    38,
                ),
                localized_texts.create(localized["label.tolerance"], 30, 41),
                *(
                    WindowText(
                        resistance_icon_tag(self.member, resistance),
                        x,
                        y,
                    )
                    for resistance, x, y in RESISTANCE_POSITIONS
                ),
                *(
                    WindowText(
                        f"{icon}：{proficiency_display(self.member, kind)}",
                        x,
                        y,
                        color=(
                            DISABLED_COLOR
                            if self.member.proficiency(kind).aptitude
                            is ProficiencyAptitude.DISABLED
                            else DEFAULT_TEXT_COLOR
                        ),
                    )
                    for kind, icon, x, y in PROFICIENCY_POSITIONS
                ),
                *(
                    WindowText("%FAVORED%", x - 2, y)
                    for kind, _icon, x, y in PROFICIENCY_POSITIONS
                    if self.member.proficiency(kind).aptitude
                    is ProficiencyAptitude.FAVORED
                ),
            ),
            horizontal_navigation=len(self.party) > 1,
            active=self.phase is StatusSelectionPhase.STATUS,
        )

    def _build_skill_guide_window(self) -> Window | None:
        """Build the discoverability guide only for members with skills."""

        if not self.displayed_skills:
            return None
        localizer = Localizer(self.settings.language)
        guide = self.texts.text("status.skill_guide", localizer)
        if not guide:
            raise StatusMenuDataError(
                "ステータス用テキストが見つかりません: status.skill_guide"
            )
        localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )
        windows = self.window_factory_class(self.fonts.font_for(Language.JAPANESE))
        return windows.create(
            *SKILL_GUIDE_WINDOW_GRID,
            (
                localized_texts.create(
                    guide.replace(
                        "%CONFIRM%",
                        input_icon_tag(InputAction.CONFIRM, self.input_device),
                    ),
                    2,
                    0,
                ),
            ),
            transparent=True,
        )

    def _build_skill_description_window(self) -> Window:
        """Build the DA2-style bottom guide for the selected skill."""

        localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )
        skill = self.selected_skill
        lines = (
            ()
            if skill is None
            else skill.localized_description(Localizer(self.settings.language))
        )
        windows = self.window_factory_class(self.fonts.font_for(Language.JAPANESE))
        return windows.create(
            *SKILL_DESCRIPTION_WINDOW_GRID,
            tuple(
                localized_texts.create(line, 2, 2 + index * 3)
                for index, line in enumerate(lines[:2])
            ),
        )

    def _build_windows(self) -> None:
        """Build status, guide, cursor, and any active description window."""

        self.status_window = self._build_window()
        self.skill_cursor = self.window_cursor_class(
            self.status_window,
            tuple(
                CursorTarget(
                    SKILL_CURSOR_X,
                    SKILL_FIRST_Y + index * SKILL_ROW_HEIGHT,
                    key=skill.key,
                )
                for index, skill in enumerate(self.displayed_skills)
            ),
            active=self.phase is StatusSelectionPhase.SKILL,
        )
        self.skill_guide_window = self._build_skill_guide_window()
        self.skill_description_window = (
            self._build_skill_description_window()
            if self.phase is StatusSelectionPhase.SKILL
            else None
        )
        self._refresh_visible_windows()

    def _refresh_visible_windows(self) -> None:
        """Keep overlays ordered above the full-screen status window."""

        windows = [self.status_window]
        if (
            self.phase is StatusSelectionPhase.STATUS
            and self.skill_guide_window is not None
        ):
            windows.append(self.skill_guide_window)
        if self.skill_description_window is not None:
            windows.append(self.skill_description_window)
        self.windows = windows

    def _localized_texts(self, localizer: Localizer) -> dict[str, str]:
        """Resolve all names and labels currently switched by this mock."""

        identity = self.member.display_identity(localizer, self.texts)
        localized = {
            "member.name": identity.name,
            "member.race": identity.race,
            "member.gender": identity.gender,
        }
        for index in range(DISPLAYED_SKILL_COUNT):
            localized[f"skill.{index}"] = (
                self.member.skills[index].localized_name(localizer)
                if index < len(self.member.skills)
                else ""
            )

        for display_key, text_key in STATUS_TEXT_KEYS.items():
            text = self.texts.text(text_key, localizer)
            if not text:
                raise StatusMenuDataError(
                    f"ステータス用テキストが見つかりません: {text_key}"
                )
            localized[display_key] = text
        localized["value.condition"] = self.member.status(
            localizer,
            self.texts,
            show_ok=True,
        )
        for slot in EquipmentSlot:
            slot_name = slot.value.lower()
            item = self.member.equipment.item_at(slot)
            icon = ""
            if item is not None:
                candidate = f"%{item.subtype}%"
                if candidate in TEXT_ICONS:
                    icon = candidate
            localized[f"equipment.{slot_name}"] = (
                localized[f"label.equip.{slot_name}"]
                + icon
                + (item.localized_name(localizer) if item is not None else "")
            )
        return localized

    def _rebuild_window(self) -> None:
        """Rebuild all values for the current member and language."""

        self._build_windows()

    def _enter_skill_selection(self) -> None:
        """Focus the first displayed skill and show its description."""

        if not self.displayed_skills:
            return
        self.phase = StatusSelectionPhase.SKILL
        self.status_window.active = False
        self.skill_cursor.active = True
        self.skill_description_window = self._build_skill_description_window()
        self._refresh_visible_windows()

    def _leave_skill_selection(self) -> None:
        """Return focus to the member-level status view."""

        self.phase = StatusSelectionPhase.STATUS
        self.status_window.active = True
        self.skill_cursor.active = False
        self.skill_description_window = None
        self._refresh_visible_windows()

    def _refresh_skill_description(self) -> None:
        """Replace the bottom guide after the skill cursor moves."""

        self.skill_description_window = self._build_skill_description_window()
        self._refresh_visible_windows()

    def _switch_member(self, distance: int) -> None:
        """Move through the mock party, wrapping at both ends."""

        if distance not in (-1, 1):
            raise ValueError("member switch distance must be -1 or 1")
        self.member_index = (self.member_index + distance) % len(self.party)
        self._rebuild_window()

    def update(self, input_state: InputState) -> bool:
        """Update the view and report whether it should return to the menu."""

        if self.phase is StatusSelectionPhase.SKILL:
            if input_state.cancel.triggered:
                self._leave_skill_selection()
                return False
            if self.skill_cursor.update(input_state.navigation):
                self._refresh_skill_description()
            return False

        if input_state.cancel.triggered:
            return True

        if (
            input_state.navigation is Direction.LEFT
            or input_state.previous_page.triggered
        ):
            self._switch_member(-1)
        elif (
            input_state.navigation is Direction.RIGHT or input_state.next_page.triggered
        ):
            self._switch_member(1)
        elif input_state.confirm.triggered:
            self._enter_skill_selection()
        return False

    def draw(self) -> None:
        # ウィンドウ
        for window in self.windows:
            window.draw()
        # 顔
        face_position = self.member.face_position
        pyxel.blt(
            16,
            10,
            self.faces,
            face_position.x,
            face_position.y,
            32,
            32,
            TRANSPARENT_INDEX,
        )
        if self.phase is StatusSelectionPhase.SKILL:
            self.skill_cursor.draw()
