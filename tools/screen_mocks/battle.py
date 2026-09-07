"""Display the current battle-screen layout mock."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

import pyxel

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_character_records,
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)
from tools.screen_mocks._runner import run_screen_mock
from tools.screen_mocks._runtime import (
    FPS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    create_mock_input_reader,
    initialize_screen_mock,
)
from localization import Localizer, ascii_to_fullwidth
from member import (
    EquipmentSlot,
    MAX_INTERNAL_LEVEL,
    FormationRow,
    Member,
)
from input import Direction, InputState
from rendering import DEFAULT_FADE_FRAME_COUNT, FadeThroughBlack
from resources import (
    TRANSPARENT_INDEX,
    FontResourceError,
    FontResources,
    ImageResourceError,
    ImageResources,
    load_record_array,
)
from state import Language, Settings
from text_catalog import TextCatalog, TextCatalogError
from ui import CursorTarget, Window, WindowFactory, WindowText
from ui.formation_arrow import (
    FORMATION_ARROW_BANK,
    FORMATION_ARROW_COLKEY,
    FORMATION_ARROW_FRAME_DURATION,
    FORMATION_ARROW_HEIGHT,
    FORMATION_ARROW_RIGHT_X,
    FORMATION_ARROW_WIDTH,
    FORMATION_ARROW_Y,
)

BACKGROUND_IMAGE_ID = "background/bg_nector"
CH_BATTLE_IMAGE_ID = "characters/ch_battle"
BATTLE_MOCK_PARTY_CHARACTER_KEYS = ("Fiora", "Cerion", "Alvan")
BATTLE_MOCK_MONSTER_KEYS = (
    "Giant Spider",
    "Giant Spider",
    "Giant Spider",
    "Coyote",
    "Coyote",
)
BATTLE_MOCK_FRONT_MONSTER_KEYS = frozenset(("Coyote",))
BATTLE_MOCK_FRONT_CHARACTER_KEYS = frozenset(("Cerion",))
PARTY_SPRITE_Y = (64, 92, 120)
MONSTER_POSITIONS = ((4, 56), (4, 120), (68, 24), (68, 88), (68, 152))
TIMELINE_BASE_X = 70
TIMELINE_BASE_Y = 220
TIMELINE_SLOT_SPACING = 20
TIMELINE_VISIBLE_ENTRY_COUNT = 6
TIMELINE_ANIMATION_FRAME_COUNT = 8
TIMELINE_DROP_DISTANCE = SCREEN_HEIGHT - TIMELINE_BASE_Y
TIMELINE_INCOMING_START_X = SCREEN_WIDTH
ESCAPE_MESSAGE_WINDOW_GRID = (2, 0, 56, 7)
ESCAPE_MESSAGE_TEXT_POSITION = (2, 2)
ESCAPE_CHOICE_WINDOW_GRID = (52, 0, 12, 10)
ESCAPE_CHOICE_TEXT_X = 4
ESCAPE_CHOICE_CURSOR_X = 2
ESCAPE_YES_Y = 2
ESCAPE_NO_Y = 5
DA2_REFERENCE_FPS = 30
DA2_MONSTER_ENTRANCE_SLIDE_STEPS = (8, 8, 7, 7, 6)
DA2_MONSTER_ENTRANCE_STEP_DISTANCE = 24
MONSTER_ENTRANCE_FRAME_COUNTS = tuple(
    step_count * FPS // DA2_REFERENCE_FPS
    for step_count in DA2_MONSTER_ENTRANCE_SLIDE_STEPS
)
PARTY_ENTRANCE_FRAME_COUNT = 10
PARTY_ENTRANCE_STAGGER_FRAME_COUNT = 2
PARTY_ENTRANCE_START_X = SCREEN_WIDTH
PARTY_ENTRANCE_OFFSET_Y = -24
PARTY_ENTRANCE_JUMP_HEIGHT = 24
PARTY_ENTRANCE_COMPLETE_FRAME = (
    PARTY_ENTRANCE_FRAME_COUNT
    + (len(BATTLE_MOCK_PARTY_CHARACTER_KEYS) - 1)
    * PARTY_ENTRANCE_STAGGER_FRAME_COUNT
)
TIMELINE_ENTRANCE_FRAME_COUNT = 10
TIMELINE_ENTRANCE_STAGGER_FRAME_COUNT = 2
TIMELINE_ENTRANCE_START_X = SCREEN_WIDTH
TIMELINE_ENTRANCE_COMPLETE_FRAME = (
    TIMELINE_ENTRANCE_FRAME_COUNT
    + (TIMELINE_VISIBLE_ENTRY_COUNT - 1)
    * TIMELINE_ENTRANCE_STAGGER_FRAME_COUNT
)
BATTLE_ENTRANCE_FRAME_COUNT = max(
    PARTY_ENTRANCE_COMPLETE_FRAME,
    TIMELINE_ENTRANCE_COMPLETE_FRAME,
    max(MONSTER_ENTRANCE_FRAME_COUNTS),
    DEFAULT_FADE_FRAME_COUNT,
)
DA2_BLINK_FRAME_COUNT = 11
DA2_BLINK_PERIOD = 6
DA2_BLINK_VISIBLE_FRAMES = 3
MONSTER_BLINK_FRAME_COUNT = DA2_BLINK_FRAME_COUNT * FPS // DA2_REFERENCE_FPS
MONSTER_BLINK_PERIOD = DA2_BLINK_PERIOD * FPS // DA2_REFERENCE_FPS
MONSTER_BLINK_VISIBLE_FRAMES = DA2_BLINK_VISIBLE_FRAMES * FPS // DA2_REFERENCE_FPS
COMMAND_OPTIONS = (
    ("attack", "こうげき", 4, 2, 2, 2),
    ("defend", "ぼうぎょ", 4, 5, 2, 5),
    ("spell", "じゅもん", 4, 8, 2, 8),
    ("escape", "にげる", 18, 2, 16, 2),
    ("item", "アイテム", 18, 5, 16, 5),
    ("formation", "こうたい", 18, 8, 16, 8),
)
COMMAND_OPTIONS_WITHOUT_ATTACK = (
    ("defend", "ぼうぎょ", 4, 2, 2, 2),
    ("spell", "じゅもん", 4, 5, 2, 5),
    *COMMAND_OPTIONS[3:],
)
DA2_MONSTER_TARGET_ORDER = {
    Direction.LEFT: (
        (2, 4, 1, 3),
        (3, 0, 2, 4),
        (4, 1, 3, 0),
        (0, 2, 4, 1),
        (1, 3, 0, 2),
    ),
    Direction.RIGHT: (
        (3, 1, 4, 2),
        (4, 2, 0, 3),
        (0, 3, 1, 4),
        (1, 4, 2, 0),
        (2, 0, 3, 1),
    ),
    Direction.UP: (
        (1, 2, 3, 4),
        (0, 4, 3, 2),
        (4, 0, 3, 1),
        (2, 0, 4, 1),
        (3, 1, 2, 0),
    ),
    Direction.DOWN: (
        (1, 3, 2, 4),
        (0, 2, 3, 4),
        (3, 0, 4, 1),
        (4, 1, 2, 0),
        (2, 1, 3, 0),
    ),
}
RecordValue = TypeVar("RecordValue")


class BattleMockDataError(ValueError):
    """Raised when generated battle display data cannot form the mock."""


class BattleMockPhase(StrEnum):
    """Interactive phases implemented by the standalone battle mock."""

    ENTRANCE = "entrance"
    INITIAL = "initial"
    COMMAND = "command"
    TARGET = "target"
    ESCAPE_CONFIRMATION = "escape_confirmation"
    TIMELINE = "timeline"
    MONSTER_ACTION = "monster_action"


class TimelineAnimationPhase(StrEnum):
    """Two-stage movement between battle turns."""

    DROP = "drop"
    SLIDE = "slide"


def _required_text(record: Mapping[str, object], field: str, label: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise BattleMockDataError(f"{label}.{field} must be a non-empty string")
    return value


def _required_nonnegative_integer(
    record: Mapping[str, object],
    field: str,
    label: str,
) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BattleMockDataError(f"{label}.{field} must be a non-negative integer")
    return value


def _required_positive_integer(
    record: Mapping[str, object],
    field: str,
    label: str,
) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BattleMockDataError(f"{label}.{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class BattleMockCharacter:
    """One member plus the immutable display values for the battle mock."""

    member: Member
    icon_x: int
    icon_y: int
    battle_sprite: int

    @classmethod
    def from_record(
        cls,
        member: Member,
        record: Mapping[str, object],
    ) -> BattleMockCharacter:
        key = member.definition.key
        return cls(
            member=member,
            icon_x=_required_nonnegative_integer(record, "icon_x", key),
            icon_y=_required_nonnegative_integer(record, "icon_y", key),
            battle_sprite=_required_nonnegative_integer(
                record,
                "battle_sprite",
                key,
            ),
        )

    def display_name(self, localizer: Localizer) -> str:
        return self.member.definition.localized_name(localizer)


@dataclass(frozen=True)
class BattleMockMonster:
    """Immutable monster display data resolved from one generated record."""

    key: str
    names: Mapping[str, object]
    image_id: str
    width: int
    height: int
    icon_x: int
    icon_y: int
    is_front_row: bool

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
        *,
        is_front_row: bool,
    ) -> BattleMockMonster:
        if not isinstance(is_front_row, bool):
            raise TypeError("monster formation row must be a boolean")
        key = _required_text(record, "name_en", "monster")
        image_id = record.get("image_id")
        if isinstance(image_id, bool) or not isinstance(image_id, (str, int)):
            raise BattleMockDataError(f"{key}.image_id must be a string or integer")
        image_id_text = str(image_id)
        if not image_id_text:
            raise BattleMockDataError(f"{key}.image_id must not be empty")
        return cls(
            key=key,
            names=record,
            image_id=image_id_text,
            width=_required_positive_integer(record, "width", key),
            height=_required_positive_integer(record, "height", key),
            icon_x=_required_nonnegative_integer(record, "icon_x", key),
            icon_y=_required_nonnegative_integer(record, "icon_y", key),
            is_front_row=is_front_row,
        )

    @property
    def image_resource_id(self) -> str:
        return f"monsters/{self.image_id}"

    def display_name(self, localizer: Localizer) -> str:
        return localizer.text(self.names, "name")


def member_attack_reach(member: Member) -> int:
    """Return the shortest reach among weapons used by one member."""

    weapons = tuple(
        weapon
        for slot in (EquipmentSlot.RIGHT, EquipmentSlot.LEFT)
        if (weapon := member.equipment.weapon_at(slot)) is not None
    )
    # An unarmed attack follows the same range rule as a reach-1 weapon.
    return min((weapon.reach for weapon in weapons), default=1)


def selectable_attack_target_indexes(
    *,
    attacker_is_front_row: bool,
    weapon_reach: int,
    monsters: tuple[BattleMockMonster, ...],
) -> tuple[int, ...]:
    """Return targetable monster indexes for one normal attack."""

    if not isinstance(attacker_is_front_row, bool):
        raise TypeError("attacker_is_front_row must be a boolean")
    if isinstance(weapon_reach, bool) or weapon_reach not in (1, 2, 3):
        raise ValueError("weapon_reach must be 1, 2, or 3")

    if weapon_reach == 1 and not attacker_is_front_row:
        return ()
    can_target_back_row = weapon_reach == 3 or (
        weapon_reach == 2 and attacker_is_front_row
    )
    return tuple(
        index
        for index, monster in enumerate(monsters)
        if monster.is_front_row or can_target_back_row
    )


def _records_by_key(
    records: tuple[dict[str, object], ...] | list[dict[str, object]],
    *,
    label: str,
) -> dict[str, Mapping[str, object]]:
    records_by_key: dict[str, Mapping[str, object]] = {}
    for record in records:
        key = _required_text(record, "name_en", label)
        if key in records_by_key:
            raise BattleMockDataError(f"{label} key is duplicated: {key}")
        records_by_key[key] = record
    return records_by_key


def _record_for_key(
    records_by_key: Mapping[str, RecordValue],
    key: str,
    *,
    label: str,
) -> RecordValue:
    try:
        return records_by_key[key]
    except KeyError as error:
        raise BattleMockDataError(f"{label} is missing: {key}") from error


class BattleScreenMock:
    def __init__(self) -> None:
        self.palette_shifter = initialize_screen_mock(
            "Dungeon Antiqua ZERO Battle Screen Mock"
        )
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
        self.character_sprites = resources.image(CH_BATTLE_IMAGE_ID)
        settings = Settings()
        self.localizer = Localizer(settings.language)
        texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        items = load_mock_items()
        character_records = _records_by_key(
            load_mock_character_records(),
            label="character",
        )
        self.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        for member in self.party:
            if member.definition.key in BATTLE_MOCK_FRONT_CHARACTER_KEYS:
                member.formation_row = FormationRow.FRONT
        self.party_visuals = tuple(
            BattleMockCharacter.from_record(
                member,
                _record_for_key(
                    character_records,
                    member.definition.key,
                    label="character",
                ),
            )
            for member in self.party
        )
        monsters_by_key = _records_by_key(
            load_record_array("monsters.json", APP_ROOT / "data"),
            label="monster",
        )
        self.monsters = tuple(
            BattleMockMonster.from_record(
                _record_for_key(monsters_by_key, key, label="monster"),
                is_front_row=key in BATTLE_MOCK_FRONT_MONSTER_KEYS,
            )
            for key in BATTLE_MOCK_MONSTER_KEYS
        )
        self.monster_images = {
            monster.key: resources.image(monster.image_resource_id)
            for monster in self.monsters
        }
        # The mock starts with its three party members, followed by all five monsters.
        # Rotating this tuple makes the first entry the single source of truth
        # for the current actor and the leftmost timeline icon.
        self.timeline = self.party_visuals + self.monsters
        fonts = FontResources()
        windows = WindowFactory(fonts.font_for(settings.language))
        font_6x8 = fonts.font_for(Language.ENGLISH)
        command_window = windows.create(
            34,
            0,
            30,
            13,
            tuple(
                WindowText(label, text_x, text_y)
                for _, label, text_x, text_y, _, _ in COMMAND_OPTIONS
            ),
            thin_frame=True,
            opened=False,
        )
        self.command_window = command_window
        self.command_cursor = command_window.set_cursor(
            tuple(
                CursorTarget(cursor_x, cursor_y, key=key)
                for key, _, _, _, cursor_x, cursor_y in COMMAND_OPTIONS
            )
        )
        self.target_window = windows.create(0, 0, 64, 60, transparent=True)
        self.target_cursor = self.target_window.set_cursor(
            tuple(
                CursorTarget(
                    (x + 8) // 4,
                    (y + 16) // 4,
                    key=index,
                )
                for index, (x, y) in enumerate(MONSTER_POSITIONS)
            )
        )
        self.target_cursor.active = False
        self.escape_message_window = windows.create(
            *ESCAPE_MESSAGE_WINDOW_GRID,
            (
                WindowText(
                    texts.text("battle.escape.confirm", self.localizer),
                    *ESCAPE_MESSAGE_TEXT_POSITION,
                ),
            ),
        )
        self.escape_choice_window = windows.create(
            *ESCAPE_CHOICE_WINDOW_GRID,
            (
                WindowText(
                    texts.text("settings.yes", self.localizer),
                    ESCAPE_CHOICE_TEXT_X,
                    ESCAPE_YES_Y,
                ),
                WindowText(
                    texts.text("settings.no", self.localizer),
                    ESCAPE_CHOICE_TEXT_X,
                    ESCAPE_NO_Y,
                ),
            ),
        )
        self.escape_cursor = self.escape_choice_window.set_cursor(
            (
                CursorTarget(
                    ESCAPE_CHOICE_CURSOR_X,
                    ESCAPE_YES_Y,
                    key="yes",
                ),
                CursorTarget(
                    ESCAPE_CHOICE_CURSOR_X,
                    ESCAPE_NO_Y,
                    key="no",
                ),
            )
        )
        self.escape_cursor.active = False
        self.phase = BattleMockPhase.INITIAL
        self.active_party_index: int | None = 0
        self.blinking_monster_index: int | None = None
        self.monster_blink_frames_remaining = 0
        self.timeline_animation_phase: TimelineAnimationPhase | None = None
        self.timeline_animation_frame = 0
        self.entrance_animation_frame = 0
        self.entrance_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.selected_command: str | None = None
        self.selectable_target_indexes: tuple[int, ...] = ()
        self.selected_target_index: int | None = None
        self.windows = [command_window]
        self.monster_name_windows: list[Window] = []
        self.party_status_windows: list[Window] = []
        self.party_status_texts: list[tuple[WindowText, WindowText]] = []

        for i, visual in enumerate(self.party_visuals):
            window = windows.create(52, 16 + i * 7, 7, 5, transparent=True)
            # 現在アクティブなキャラクターは白文字、それ以外は灰色
            c = 5 if i == 0 else 4
            member = visual.member
            name_text = window.add_text(
                visual.display_name(self.localizer),
                0,
                0,
                color=c,
            )
            hp_text = window.add_text(
                ascii_to_fullwidth(f"{member.hp:03d}/{member.max_hp:03d}"),
                0,
                4,
                font=font_6x8,
                color=c,
            )
            self.party_status_windows.append(window)
            self.party_status_texts.append((name_text, hp_text))
            self.windows.append(window)

        for monster, (x, y) in zip(self.monsters, MONSTER_POSITIONS):
            window = windows.create(x // 4 + 2, y // 4 + 13, 20, 4, transparent=True)
            window.add_text(monster.display_name(self.localizer), 0, 0, color=4)
            self.monster_name_windows.append(window)

        self._restart_battle_mock()
        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        input_state = self.input_reader.poll()
        if self.phase is BattleMockPhase.ENTRANCE:
            self._update_entrance_animation()
            return
        if self.phase is BattleMockPhase.MONSTER_ACTION:
            self._update_monster_action()
            return
        if self.phase is BattleMockPhase.ESCAPE_CONFIRMATION:
            self._update_escape_confirmation(input_state)
            return
        if self.phase is BattleMockPhase.TIMELINE:
            self._update_timeline_animation()
            return
        if self.phase is BattleMockPhase.TARGET:
            self._update_target_selection(input_state)
            return

        if input_state.cancel.triggered:
            self._return_to_button_wait()
            return

        if input_state.confirm.triggered:
            if self.command_window.is_closed:
                self.phase = BattleMockPhase.COMMAND
                self.command_cursor.active = True
                self.command_window.open()
            elif self.command_window.is_open:
                command = self.command_cursor.selected_key
                if command == "attack":
                    self._begin_attack_target_selection()
                elif command == "spell":
                    self._restart_battle_mock()
                    return
                elif command == "escape":
                    self._begin_escape_confirmation()
                else:
                    self.selected_command = command
                    self._complete_current_turn()

        navigation = (
            input_state.navigation if self.phase is BattleMockPhase.COMMAND else None
        )
        self.command_window.update(navigation)

    def _restart_battle_mock(self) -> None:
        """Reset the mock and replay its battle entrance presentation."""

        self.timeline = self.party_visuals + self.monsters
        self.phase = BattleMockPhase.ENTRANCE
        self.active_party_index = 0
        self.blinking_monster_index = None
        self.monster_blink_frames_remaining = 0
        self.timeline_animation_phase = None
        self.timeline_animation_frame = 0
        self.entrance_animation_frame = 0
        self.selected_command = None
        self.selectable_target_indexes = ()
        self.selected_target_index = None
        self.target_cursor.active = False
        self.escape_cursor.active = False
        self.command_window.close_immediately()
        self._refresh_command_options()
        self.command_cursor.active = False
        self._refresh_party_text_colors()
        self.entrance_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.entrance_fade.start_fade_in()
        self.palette_shifter.set_global_mix(
            base_rate=0.0,
            target_color=self.palette_shifter.base_colors[0],
        )

    def _update_entrance_animation(self) -> None:
        if self.entrance_fade.is_active:
            self.entrance_fade.update()
            self.palette_shifter.set_global_mix(
                base_rate=self.entrance_fade.visible_rate,
                target_color=self.palette_shifter.base_colors[0],
            )
        self.entrance_animation_frame += 1
        if self.entrance_animation_frame >= BATTLE_ENTRANCE_FRAME_COUNT:
            self.entrance_animation_frame = BATTLE_ENTRANCE_FRAME_COUNT
            self.phase = BattleMockPhase.COMMAND
            self.command_cursor.active = True
            self.command_window.open()

    def _return_to_button_wait(self) -> None:
        self.phase = BattleMockPhase.INITIAL
        self.selected_command = None
        self.selectable_target_indexes = ()
        self.selected_target_index = None
        self.command_cursor.active = False
        self.target_cursor.active = False
        self.command_window.close_immediately()

    def _begin_escape_confirmation(self) -> None:
        self.phase = BattleMockPhase.ESCAPE_CONFIRMATION
        self.selected_command = "escape"
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self.escape_cursor.select_key("yes")
        self.escape_cursor.active = True

    def _update_escape_confirmation(self, input_state: InputState) -> None:
        if input_state.cancel.triggered:
            self._cancel_escape_confirmation()
            return
        if not self.command_window.is_closed:
            self.command_window.update(None)
            return
        if input_state.confirm.triggered:
            if self.escape_cursor.selected_key == "yes":
                pyxel.quit()
            else:
                self._cancel_escape_confirmation()
            return
        self.escape_cursor.update(input_state.navigation)

    def _cancel_escape_confirmation(self) -> None:
        self.phase = BattleMockPhase.COMMAND
        self.selected_command = None
        self.escape_cursor.active = False
        self.command_cursor.active = True
        self.command_window.open()

    def _begin_attack_target_selection(self) -> bool:
        selectable = self._active_member_attack_targets()
        if not selectable:
            return False

        self.selected_command = "attack"
        self.selectable_target_indexes = selectable
        # DA2 starts enemy selection at the last selectable monster.
        self.selected_target_index = selectable[-1]
        self.phase = BattleMockPhase.TARGET
        self.command_cursor.active = False
        self.target_cursor.active = True
        self.target_cursor.select_key(self.selected_target_index)
        return True

    def _update_target_selection(self, input_state: InputState) -> None:
        if input_state.cancel.triggered:
            self.selected_command = None
            self.selectable_target_indexes = ()
            self.selected_target_index = None
            self.phase = BattleMockPhase.COMMAND
            self.command_cursor.active = True
            self.target_cursor.active = False
            return

        if input_state.confirm.triggered:
            self._complete_current_turn()
            return

        navigation = input_state.navigation
        if navigation is not None:
            self._move_target(navigation)
        self.target_cursor.update()

    def _move_target(self, direction: Direction) -> bool:
        selected = self.selected_target_index
        if selected is None:
            return False
        try:
            candidates = DA2_MONSTER_TARGET_ORDER[direction][selected]
        except (KeyError, IndexError):
            return False
        for candidate in candidates:
            if candidate in self.selectable_target_indexes:
                moved = candidate != selected
                self.selected_target_index = candidate
                self.target_cursor.select_key(candidate)
                return moved
        return False

    def _complete_current_turn(self) -> None:
        self.selected_command = None
        self.selectable_target_indexes = ()
        self.selected_target_index = None
        self.target_cursor.active = False
        self._start_timeline_animation()

    def _start_timeline_animation(self) -> None:
        self.phase = BattleMockPhase.TIMELINE
        self.active_party_index = None
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self.timeline_animation_phase = TimelineAnimationPhase.DROP
        self.timeline_animation_frame = 0
        self._refresh_party_text_colors()

    def _update_timeline_animation(self) -> None:
        self.command_window.update(None)
        if self.timeline_animation_frame < TIMELINE_ANIMATION_FRAME_COUNT:
            self.timeline_animation_frame += 1
            return
        if self.timeline_animation_phase is TimelineAnimationPhase.DROP:
            self.timeline_animation_phase = TimelineAnimationPhase.SLIDE
            self.timeline_animation_frame = 0
            return
        self.timeline_animation_phase = None
        self.timeline_animation_frame = 0
        self._advance_timeline()

    def _advance_timeline(self) -> None:
        self.timeline = self.timeline[1:] + self.timeline[:1]
        self._activate_timeline_head()

    def _activate_timeline_head(self) -> None:
        actor = self.timeline[0]
        if isinstance(actor, BattleMockCharacter):
            self.active_party_index = next(
                index
                for index, visual in enumerate(self.party_visuals)
                if visual is actor
            )
            self.phase = BattleMockPhase.COMMAND
            self.command_cursor.active = True
            self.blinking_monster_index = None
            self.monster_blink_frames_remaining = 0
            self._refresh_command_options()
            self.command_window.open()
        else:
            self.active_party_index = None
            self.phase = BattleMockPhase.MONSTER_ACTION
            self.command_cursor.active = False
            self.command_window.close_immediately()
            self.blinking_monster_index = next(
                index for index, monster in enumerate(self.monsters) if monster is actor
            )
            self.monster_blink_frames_remaining = MONSTER_BLINK_FRAME_COUNT
        self._refresh_party_text_colors()

    def _active_member_attack_targets(self) -> tuple[int, ...]:
        if self.active_party_index is None:
            return ()
        actor = self.party[self.active_party_index]
        return selectable_attack_target_indexes(
            attacker_is_front_row=actor.is_front_row,
            weapon_reach=member_attack_reach(actor),
            monsters=self.monsters,
        )

    def _refresh_command_options(self) -> None:
        options = (
            COMMAND_OPTIONS
            if self._active_member_attack_targets()
            else COMMAND_OPTIONS_WITHOUT_ATTACK
        )
        self.command_window.clear_texts()
        for _, label, text_x, text_y, _, _ in options:
            self.command_window.add_text(label, text_x, text_y)
        self.command_window.clear_cursor()
        self.command_cursor = self.command_window.set_cursor(
            tuple(
                CursorTarget(cursor_x, cursor_y, key=key)
                for key, _, _, _, cursor_x, cursor_y in options
            )
        )

    def _update_monster_action(self) -> None:
        self.command_window.update(None)
        if self.monster_blink_frames_remaining > 0:
            self.monster_blink_frames_remaining -= 1
        if self.monster_blink_frames_remaining == 0:
            self._start_timeline_animation()

    def _refresh_party_text_colors(self) -> None:
        for index, (window, placements) in enumerate(
            zip(self.party_status_windows, self.party_status_texts)
        ):
            color = 5 if index == self.active_party_index else 4
            recolored = tuple(
                self._replace_text_color(window, placement, color)
                for placement in placements
            )
            self.party_status_texts[index] = recolored

    @staticmethod
    def _replace_text_color(
        window: Window,
        placement: WindowText,
        color: int,
    ) -> WindowText:
        window.remove_text(placement)
        return window.add_text(
            placement.text,
            placement.x,
            placement.y,
            color=color,
            font=placement.font,
            shadow_color=placement.shadow_color,
            baseline_offset=placement.baseline_offset,
            font_spans=placement.font_spans,
        )

    def draw(self) -> None:
        """Draw the battle screen in explicit back-to-front order."""

        self._draw_background()
        self._draw_party()
        self._draw_active_party_arrow()
        self._draw_monsters()
        self._draw_timeline()
        self._draw_windows()
        self._draw_target_cursor()

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
        for index, visual in enumerate(self.party_visuals):
            position = self._party_draw_position(index)
            if position is None:
                continue
            x, y = position
            pyxel.blt(
                x,
                y,
                self.character_sprites,
                0,
                visual.battle_sprite * 32,
                16,
                32,
                TRANSPARENT_INDEX,
            )

    def _party_draw_position(self, index: int) -> tuple[int, int] | None:
        target_x = self._party_sprite_x(index)
        target_y = PARTY_SPRITE_Y[index]
        if self.phase is not BattleMockPhase.ENTRANCE:
            return target_x, target_y

        delay = index * PARTY_ENTRANCE_STAGGER_FRAME_COUNT
        elapsed = self.entrance_animation_frame - delay
        if elapsed < 0:
            return None
        elapsed = min(elapsed, PARTY_ENTRANCE_FRAME_COUNT)
        remaining = PARTY_ENTRANCE_FRAME_COUNT - elapsed
        x = target_x + (
            (PARTY_ENTRANCE_START_X - target_x)
            * remaining
            // PARTY_ENTRANCE_FRAME_COUNT
        )
        linear_y = target_y + PARTY_ENTRANCE_OFFSET_Y * remaining // (
            PARTY_ENTRANCE_FRAME_COUNT
        )
        jump = (
            4
            * PARTY_ENTRANCE_JUMP_HEIGHT
            * elapsed
            * remaining
            // (PARTY_ENTRANCE_FRAME_COUNT**2)
        )
        return x, linear_y - jump

    def _party_sprite_x(self, index: int) -> int:
        x = 156 + index * 4
        if self.party_visuals[index].member.formation_row is FormationRow.BACK:
            x += 16
        return x

    def _draw_active_party_arrow(self) -> None:
        if (
            self.phase is BattleMockPhase.ENTRANCE
            or self.active_party_index is None
        ):
            return
        index = self.active_party_index
        frame = (pyxel.frame_count // FORMATION_ARROW_FRAME_DURATION) % 2
        pyxel.blt(
            self._party_sprite_x(index) - FORMATION_ARROW_WIDTH,
            PARTY_SPRITE_Y[index] + (32 - FORMATION_ARROW_HEIGHT) // 2,
            FORMATION_ARROW_BANK,
            FORMATION_ARROW_RIGHT_X[frame],
            FORMATION_ARROW_Y,
            FORMATION_ARROW_WIDTH,
            FORMATION_ARROW_HEIGHT,
            FORMATION_ARROW_COLKEY,
        )

    def _draw_monsters(self) -> None:
        for index, (monster, (_, y)) in enumerate(
            zip(self.monsters, MONSTER_POSITIONS)
        ):
            if (
                index == self.blinking_monster_index
                and self.monster_blink_frames_remaining
                and self.monster_blink_frames_remaining % MONSTER_BLINK_PERIOD
                >= MONSTER_BLINK_VISIBLE_FRAMES
            ):
                continue
            x = self._monster_draw_x(index)
            pyxel.blt(
                x,
                y,
                self.monster_images[monster.key],
                0,
                0,
                monster.width,
                monster.height,
                TRANSPARENT_INDEX,
            )

    def _monster_draw_x(self, index: int) -> int:
        target_x = MONSTER_POSITIONS[index][0]
        if self.phase is not BattleMockPhase.ENTRANCE:
            return target_x

        duration = MONSTER_ENTRANCE_FRAME_COUNTS[index]
        elapsed = min(self.entrance_animation_frame, duration)
        remaining = duration - elapsed
        initial_offset = (
            DA2_MONSTER_ENTRANCE_SLIDE_STEPS[index]
            * DA2_MONSTER_ENTRANCE_STEP_DISTANCE
        )
        return target_x - initial_offset * remaining // duration

    def _draw_target_cursor(self) -> None:
        if self.phase is not BattleMockPhase.TARGET:
            return
        self.target_cursor.draw()

    def _draw_timeline(self) -> None:
        if self.phase is BattleMockPhase.ENTRANCE:
            for index, entry in enumerate(
                self.timeline[:TIMELINE_VISIBLE_ENTRY_COUNT]
            ):
                x = self._timeline_entrance_x(index)
                if x is None:
                    continue
                self._draw_timeline_entry(entry, x, TIMELINE_BASE_Y)
            return
        if self.timeline_animation_phase is TimelineAnimationPhase.DROP:
            drop = (
                TIMELINE_DROP_DISTANCE
                * self.timeline_animation_frame
                * self.timeline_animation_frame
                // (TIMELINE_ANIMATION_FRAME_COUNT**2)
            )
            for index, entry in enumerate(
                self.timeline[:TIMELINE_VISIBLE_ENTRY_COUNT]
            ):
                y = TIMELINE_BASE_Y + (drop if index == 0 else 0)
                self._draw_timeline_entry(
                    entry,
                    TIMELINE_BASE_X + index * TIMELINE_SLOT_SPACING,
                    y,
                )
            return
        if self.timeline_animation_phase is TimelineAnimationPhase.SLIDE:
            shift = (
                TIMELINE_SLOT_SPACING
                * self.timeline_animation_frame
                // TIMELINE_ANIMATION_FRAME_COUNT
            )
            for index, entry in enumerate(
                self.timeline[1:TIMELINE_VISIBLE_ENTRY_COUNT],
                start=1,
            ):
                self._draw_timeline_entry(
                    entry,
                    TIMELINE_BASE_X + index * TIMELINE_SLOT_SPACING - shift,
                    TIMELINE_BASE_Y,
                )
            visible_entry_count = min(
                len(self.timeline),
                TIMELINE_VISIBLE_ENTRY_COUNT,
            )
            destination_x = TIMELINE_BASE_X + (
                visible_entry_count - 1
            ) * TIMELINE_SLOT_SPACING
            incoming_x = TIMELINE_INCOMING_START_X - (
                (TIMELINE_INCOMING_START_X - destination_x)
                * self.timeline_animation_frame
                // TIMELINE_ANIMATION_FRAME_COUNT
            )
            incoming_index = (
                TIMELINE_VISIBLE_ENTRY_COUNT
                if len(self.timeline) > TIMELINE_VISIBLE_ENTRY_COUNT
                else 0
            )
            self._draw_timeline_entry(
                self.timeline[incoming_index],
                incoming_x,
                TIMELINE_BASE_Y,
            )
            return

        for index, entry in enumerate(
            self.timeline[:TIMELINE_VISIBLE_ENTRY_COUNT]
        ):
            self._draw_timeline_entry(
                entry,
                TIMELINE_BASE_X + index * TIMELINE_SLOT_SPACING,
                TIMELINE_BASE_Y,
            )
        pyxel.blt(
            TIMELINE_BASE_X + 4,
            TIMELINE_BASE_Y - 4,
            0,
            88,
            16,
            8,
            8,
            TRANSPARENT_INDEX,
        )

    def _timeline_entrance_x(self, index: int) -> int | None:
        delay = index * TIMELINE_ENTRANCE_STAGGER_FRAME_COUNT
        elapsed = self.entrance_animation_frame - delay
        if elapsed < 0:
            return None
        elapsed = min(elapsed, TIMELINE_ENTRANCE_FRAME_COUNT)
        remaining = TIMELINE_ENTRANCE_FRAME_COUNT - elapsed
        target_x = TIMELINE_BASE_X + index * TIMELINE_SLOT_SPACING
        return target_x + (
            (TIMELINE_ENTRANCE_START_X - target_x)
            * remaining
            // TIMELINE_ENTRANCE_FRAME_COUNT
        )

    @staticmethod
    def _draw_timeline_entry(
        entry: BattleMockCharacter | BattleMockMonster,
        x: int,
        y: int,
    ) -> None:
        color = 13 if isinstance(entry, BattleMockCharacter) else 49
        pyxel.blt(
            x,
            y,
            1,
            entry.icon_x,
            entry.icon_y,
            16,
            16,
            TRANSPARENT_INDEX,
        )
        pyxel.rect(x, y + 17, 16, 1, color)
        pyxel.rect(x, y + 18, 16, 1, color - 1)

    def _draw_windows(self) -> None:
        hide_party_status = (
            self.phase is BattleMockPhase.ENTRANCE
            and self.entrance_animation_frame < PARTY_ENTRANCE_COMPLETE_FRAME
        )
        for window in self.windows:
            if hide_party_status and any(
                window is status_window
                for status_window in self.party_status_windows
            ):
                continue
            window.draw()
        if self.phase is BattleMockPhase.TARGET or (
            self.phase is BattleMockPhase.INITIAL and self.command_window.is_closed
        ):
            for window in self.monster_name_windows:
                window.draw()
        if (
            self.phase is BattleMockPhase.ESCAPE_CONFIRMATION
            and self.command_window.is_closed
        ):
            self.escape_message_window.draw()
            self.escape_choice_window.draw()


def main() -> int:
    return run_screen_mock(
        BattleScreenMock,
        expected_errors=(FontResourceError, ImageResourceError, TextCatalogError),
    )


if __name__ == "__main__":
    raise SystemExit(main())
