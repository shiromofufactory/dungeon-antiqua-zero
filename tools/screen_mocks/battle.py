"""Display the current battle-screen layout mock."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeVar

import pyxel

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_character_records,
    load_mock_items,
    load_mock_party,
    load_mock_skills,
    load_mock_spells,
)
from tools.screen_mocks._runner import run_screen_mock
from tools.screen_mocks._runtime import (
    FPS,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    create_mock_input_reader,
    initialize_screen_mock,
)
from battle_commands import (
    BattleCommand,
    BattleCommandContext,
    BattleCommandOption,
    formation_change_enabled,
    member_attack_reach,
    resolve_battle_commands,
    selectable_attack_target_indexes,
)
from item import Item, ItemEquipType
from localization import Localizer, ascii_to_fullwidth
from member import (
    EquipmentSlot,
    MAX_INTERNAL_LEVEL,
    FormationRow,
    Member,
)
from monster import (
    MonsterBattleState,
    MonsterDataError,
    promote_rear_monsters_if_front_empty,
)
from input import Direction, InputState
from rendering import (
    DEFAULT_FADE_FRAME_COUNT,
    DIMMED_PALETTE,
    MONSTER_DEATH_PALETTE,
    MONSTER_DEATH_PALETTE_BASE_RATE,
    FadeEvent,
    FadeThroughBlack,
    MonsterDeathAnimation,
)
from resources import (
    TRANSPARENT_INDEX,
    AudioResourceError,
    BgmPlayer,
    FontResourceError,
    FontResources,
    ImageResourceError,
    ImageResources,
    load_record_array,
)
from state import Language, Settings
from spell import Spell, SpellType
from systems import InventorySystem
from text_catalog import TextCatalog, TextCatalogError
from ui import (
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    RESERVE_MEMBER_TEXT_COLOR,
    CursorTarget,
    Window,
    WindowCursor,
    WindowFactory,
    WindowText,
)
from item_detail import ItemDetailContext, item_detail_lines

BACKGROUND_IMAGE_ID = "background/bg_nector"
CH_BATTLE_IMAGE_ID = "characters/ch_battle"
BATTLE_BGM_ID = "da3-battle1"
BATTLE_MOCK_PARTY_CHARACTER_KEYS = ("Fiora", "Cerion", "Alvan")
BATTLE_MOCK_MONSTER_KEYS = (
    "Giant Spider",
    "Giant Spider",
    "Giant Spider",
    "Coyote",
    "Coyote",
)
BATTLE_MOCK_FRONT_MONSTER_INDEXES = frozenset((2, 3, 4))
BATTLE_MOCK_FRONT_CHARACTER_KEYS = frozenset(("Cerion",))
PARTY_SPRITE_Y = (64, 92, 120)
# Pyxel can remap only four 16-color palette blocks.  The battle mock does
# not use its default dimmed block, so the active-member pulse owns that slot.
ACTIVE_PARTY_PULSE_PALETTE = DIMMED_PALETTE
ACTIVE_PARTY_PULSE_TARGET_COLOR = 0xFFFFFF
ACTIVE_PARTY_PULSE_MIN_BASE_RATE = 0.5
ACTIVE_PARTY_PULSE_CYCLE_FRAME_COUNT = 90
ACTIVE_PARTY_PULSE_HALF_CYCLE_FRAME_COUNT = ACTIVE_PARTY_PULSE_CYCLE_FRAME_COUNT // 2
MONSTER_POSITIONS = ((4, 56), (4, 120), (68, 24), (68, 88), (68, 152))
TIMELINE_BASE_X = 70
TIMELINE_BASE_Y = 220
TIMELINE_SLOT_SPACING = 20
TIMELINE_VISIBLE_ENTRY_COUNT = 6
TIMELINE_ANIMATION_FRAME_COUNT = 8
TIMELINE_DROP_DISTANCE = SCREEN_HEIGHT - TIMELINE_BASE_Y
TIMELINE_INCOMING_START_X = SCREEN_WIDTH
ESCAPE_MESSAGE_WINDOW_GRID = (0, 0, 64, 7)
ESCAPE_MESSAGE_TEXT_POSITION = (2, 2)
ESCAPE_CHOICE_WINDOW_GRID = (52, 0, 12, 10)
ESCAPE_CHOICE_TEXT_X = 4
ESCAPE_CHOICE_CURSOR_X = 2
ESCAPE_YES_Y = 2
ESCAPE_NO_Y = 5
COMMAND_GUIDE_WINDOW_GRID = (0, 0, 34, 13)
ITEM_GUIDE_WINDOW_GRID = (0, 0, 32, 13)
ITEM_WINDOW_GRID = (32, 0, 32, 13)
SPELL_WINDOW_GRID = (36, 0, 28, 16)
SPELL_GUIDE_WINDOW_GRID = (0, 0, 36, 16)
SPELL_MP_WINDOW_GRID = (20, 9, 16, 7)
COMMAND_GUIDE_TEXT_X = 2
COMMAND_GUIDE_FIRST_Y = 2
COMMAND_GUIDE_LINE_SPACING = 3
COMMAND_GUIDE_MAX_LINES = 3
ITEM_VISIBLE_COUNT = 3
ITEM_TEXT_X = 4
ITEM_COUNT_X = 26
ITEM_CURSOR_X = 2
ITEM_FIRST_Y = 2
ITEM_ROW_HEIGHT = 3
SPELL_TYPE_ORDER = (
    SpellType.MYSTIC,
    SpellType.SACRED,
    SpellType.NETHER,
)
SPELL_DISPLAY_LEVELS = (*range(1, 10), 0)
SPELL_TEXT_X = 4
SPELL_CURSOR_X = 2
SPELL_FIRST_Y = 2
SPELL_ROW_HEIGHT = 3
SPELL_VISIBLE_COUNT = 4
DA2_REFERENCE_FPS = 30
DA2_ESCAPE_RUN_SPEED = 12
ESCAPE_RUN_SPEED = DA2_ESCAPE_RUN_SPEED * DA2_REFERENCE_FPS // FPS
ESCAPE_RUN_DESTINATION_X = SCREEN_WIDTH + 4
ESCAPE_RUN_PATTERN_FRAME_COUNT = FPS // DA2_REFERENCE_FPS
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
    + (len(BATTLE_MOCK_PARTY_CHARACTER_KEYS) - 1) * PARTY_ENTRANCE_STAGGER_FRAME_COUNT
)
TIMELINE_ENTRANCE_FRAME_COUNT = 10
TIMELINE_ENTRANCE_STAGGER_FRAME_COUNT = 2
TIMELINE_ENTRANCE_START_X = SCREEN_WIDTH
TIMELINE_ENTRANCE_COMPLETE_FRAME = (
    TIMELINE_ENTRANCE_FRAME_COUNT
    + (TIMELINE_VISIBLE_ENTRY_COUNT - 1) * TIMELINE_ENTRANCE_STAGGER_FRAME_COUNT
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
UNSELECTABLE_TARGET_PALETTE = "unselectable_target"
UNSELECTABLE_TARGET_PALETTE_BASE_RATE = 0.5
FORMATION_MOVE_FRAME_COUNT = 8
FORMATION_WALK_PATTERN_FRAME_COUNT = FPS // DA2_REFERENCE_FPS
COMMAND_GUIDE_DELAY_FRAME_COUNT = 15 * FPS // DA2_REFERENCE_FPS
FORMATION_SPRITE_STEP_X = 16
DEFEND_SPRITE_SOURCE_X = 16 * 7
COMMAND_TEXT_KEYS = {
    BattleCommand.ATTACK: "battle.command.attack",
    BattleCommand.SPELL: "battle.command.spell",
    BattleCommand.AIM: "battle.command.aim",
    BattleCommand.HIDE: "battle.command.hide",
    BattleCommand.IDENTIFY: "battle.command.identify",
    BattleCommand.PRAY: "battle.command.pray",
    BattleCommand.COVER: "battle.command.cover",
    BattleCommand.IAI: "battle.command.iai",
    BattleCommand.FOCUS: "battle.command.focus",
    BattleCommand.BREATH: "battle.command.breath",
    BattleCommand.MP_SHARE: "battle.command.mp_share",
    BattleCommand.DEFEND: "battle.command.defend",
    BattleCommand.ESCAPE: "battle.command.escape",
    BattleCommand.ITEM: "battle.command.item",
    BattleCommand.FORMATION: "battle.command.formation",
}
COMMAND_GUIDE_TEXT_KEYS = {
    BattleCommand.ATTACK: "battle.guide.attack",
    BattleCommand.SPELL: "battle.guide.spell",
    BattleCommand.HIDE: "battle.guide.hide",
    BattleCommand.IDENTIFY: "battle.guide.identify",
    BattleCommand.PRAY: "battle.guide.pray",
    BattleCommand.COVER: "battle.guide.cover",
    BattleCommand.DEFEND: "battle.guide.defend",
    BattleCommand.ITEM: "battle.guide.item",
}
COMMAND_TEXT_X = (4, 18)
COMMAND_CURSOR_X = (2, 16)
COMMAND_ROW_Y = (2, 5, 8)
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
    ITEM = "item"
    SPELL = "spell"
    TARGET = "target"
    ESCAPE_CONFIRMATION = "escape_confirmation"
    ESCAPE_MESSAGE = "escape_message"
    ESCAPE = "escape"
    FORMATION = "formation"
    MONSTER_DEATH = "monster_death"
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


@dataclass
class BattleMockMonster:
    """Display data paired with mutable HP and formation state for one battle."""

    key: str
    names: Mapping[str, object]
    image_id: str
    width: int
    height: int
    icon_x: int
    icon_y: int
    is_front_row: bool
    state: MonsterBattleState
    initial_is_front_row: bool = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.is_front_row, bool):
            raise TypeError("monster formation row must be a boolean")
        self.initial_is_front_row = self.is_front_row

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
            state=MonsterBattleState.from_record(record),
        )

    @property
    def image_resource_id(self) -> str:
        return f"monsters/{self.image_id}"

    def display_name(self, localizer: Localizer) -> str:
        return localizer.text(self.names, "name")

    @property
    def is_alive(self) -> bool:
        return self.state.is_alive

    def restore(self) -> None:
        """Restore mutable battle values to this encounter's initial state."""

        self.state.restore()
        self.is_front_row = self.initial_is_front_row


@dataclass(frozen=True)
class BattleItemCandidate:
    """One DA2-style battle item and the place from which it is used."""

    item: Item
    equipment_slot: EquipmentSlot | None = None

    @property
    def is_equipped(self) -> bool:
        return self.equipment_slot is not None


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
        self.palette_shifter.define_mix(
            UNSELECTABLE_TARGET_PALETTE,
            base_rate=UNSELECTABLE_TARGET_PALETTE_BASE_RATE,
            target_color=self.palette_shifter.base_colors[DISABLED_COLOR],
        )
        self.input_reader = create_mock_input_reader()
        self.bgm = BgmPlayer()

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
        self.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        items = load_mock_items()
        self.spells = load_mock_spells()
        self.item_catalog = items
        # Battle mocks deliberately start with the same complete one-each
        # inventory as the standalone item and equipment mocks.
        self.inventory_system = InventorySystem.with_one_each(self.item_catalog)
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
                is_front_row=index in BATTLE_MOCK_FRONT_MONSTER_INDEXES,
            )
            for index, key in enumerate(BATTLE_MOCK_MONSTER_KEYS)
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
        command_guide_window = windows.create(
            *COMMAND_GUIDE_WINDOW_GRID,
            (),
            thin_frame=True,
            opened=False,
        )
        command_window = windows.create(
            34,
            0,
            30,
            13,
            (),
            thin_frame=True,
            opened=False,
        )
        item_guide_window = windows.create(
            *ITEM_GUIDE_WINDOW_GRID,
            (),
            thin_frame=True,
            opened=False,
        )
        item_window = windows.create(
            *ITEM_WINDOW_GRID,
            (),
            thin_frame=True,
            opened=False,
        )
        spell_window = windows.create(
            *SPELL_WINDOW_GRID,
            (),
            thin_frame=True,
            horizontal_navigation=True,
            opened=False,
        )
        spell_guide_window = windows.create(
            *SPELL_GUIDE_WINDOW_GRID,
            (),
            thin_frame=True,
            opened=False,
        )
        spell_mp_window = windows.create(
            *SPELL_MP_WINDOW_GRID,
            (),
            thin_frame=True,
            opened=False,
        )
        self.command_guide_window = command_guide_window
        self.command_window = command_window
        self.item_guide_window = item_guide_window
        self.item_window = item_window
        self.spell_window = spell_window
        self.spell_guide_window = spell_guide_window
        self.spell_mp_window = spell_mp_window
        self.command_cursor = command_window.set_cursor(())
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
                    self.texts.text("battle.escape.confirm", self.localizer),
                    *ESCAPE_MESSAGE_TEXT_POSITION,
                ),
            ),
        )
        self.escape_started_message_window = windows.create(
            *ESCAPE_MESSAGE_WINDOW_GRID,
            (
                WindowText(
                    self.texts.text("battle.escape.started", self.localizer),
                    *ESCAPE_MESSAGE_TEXT_POSITION,
                ),
            ),
        )
        self.escape_choice_window = windows.create(
            *ESCAPE_CHOICE_WINDOW_GRID,
            (
                WindowText(
                    self.texts.text("settings.yes", self.localizer),
                    ESCAPE_CHOICE_TEXT_X,
                    ESCAPE_YES_Y,
                ),
                WindowText(
                    self.texts.text("settings.no", self.localizer),
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
        self.active_party_pulse_frame = 0
        self.blinking_monster_index: int | None = None
        self.monster_blink_frames_remaining = 0
        self.timeline_animation_phase: TimelineAnimationPhase | None = None
        self.timeline_animation_frame = 0
        self.formation_animation_frame = 0
        self.formation_actor_index: int | None = None
        self.formation_start_x = 0
        self.formation_destination_x = 0
        self.escape_animation_frame = 0
        self.escape_start_x: tuple[int, ...] = ()
        self.escape_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.escape_fade_covered = False
        self.monster_death_animation: MonsterDeathAnimation | None = None
        self.dying_monster_index: int | None = None
        self.entrance_animation_frame = 0
        self.entrance_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.selected_command: str | None = None
        self.selectable_target_indexes: tuple[int, ...] = ()
        self.selected_target_index: int | None = None
        self.command_guide_command: BattleCommand | None = None
        self.command_guide_timer = 0
        self.command_guide_visible = False
        self.item_candidates: tuple[BattleItemCandidate, ...] = ()
        self.selected_item_index = 0
        self.item_scroll_offset = 0
        self.item_cursor: WindowCursor | None = None
        self.spell_candidates: tuple[Spell, ...] = ()
        self.spell_scroll_offset = 0
        self.spell_type = SpellType.MYSTIC
        self.spell_cursor: WindowCursor | None = None
        self.defending_party_indexes: set[int] = set()
        self.escaping_party_indexes: set[int] = set()
        self.windows = [
            command_guide_window,
            command_window,
            item_guide_window,
            item_window,
            spell_window,
            spell_guide_window,
            spell_mp_window,
        ]
        self.monster_name_windows: list[Window] = []
        self.monster_name_texts: list[WindowText] = []
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
            name_text = window.add_text(
                monster.display_name(self.localizer),
                0,
                0,
                color=RESERVE_MEMBER_TEXT_COLOR,
            )
            self.monster_name_windows.append(window)
            self.monster_name_texts.append(name_text)

        self._restart_battle_mock()
        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        input_state = self.input_reader.poll()
        if input_state.menu.triggered:
            self._restart_battle_mock()
            return
        if hasattr(self, "active_party_pulse_frame"):
            self._update_active_party_pulse()
        if self.phase not in (BattleMockPhase.COMMAND, BattleMockPhase.ITEM):
            self._hide_command_guide()
        if self.phase is BattleMockPhase.ENTRANCE:
            self._update_entrance_animation()
            return
        if self.phase is BattleMockPhase.MONSTER_ACTION:
            self._update_monster_action()
            return
        if self.phase is BattleMockPhase.ESCAPE_CONFIRMATION:
            self._update_escape_confirmation(input_state)
            return
        if self.phase is BattleMockPhase.ESCAPE_MESSAGE:
            self._update_escape_message(input_state)
            return
        if self.phase is BattleMockPhase.ESCAPE:
            self._update_escape_animation()
            return
        if self.phase is BattleMockPhase.FORMATION:
            self._update_formation_animation()
            return
        if self.phase is BattleMockPhase.MONSTER_DEATH:
            self._update_monster_death_animation()
            return
        if self.phase is BattleMockPhase.TIMELINE:
            self._update_timeline_animation()
            return
        if self.phase is BattleMockPhase.TARGET:
            self._update_target_selection(input_state)
            return
        if self.phase is BattleMockPhase.ITEM:
            self._update_item_selection(input_state)
            return
        if self.phase is BattleMockPhase.SPELL:
            self._update_spell_selection(input_state)
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
                if command == BattleCommand.ATTACK:
                    self._begin_attack_target_selection()
                elif command == BattleCommand.SPELL:
                    self._begin_spell_selection()
                elif command == BattleCommand.ESCAPE:
                    self._begin_escape_confirmation()
                elif command == BattleCommand.FORMATION:
                    self._begin_formation_change()
                elif command == BattleCommand.DEFEND:
                    self._begin_defense()
                elif command == BattleCommand.ITEM:
                    self._begin_item_selection()
                else:
                    self.selected_command = command
                    self._complete_current_turn()

        navigation = (
            input_state.navigation if self.phase is BattleMockPhase.COMMAND else None
        )
        self.command_window.update(navigation)
        self._update_command_guide()

    def _restart_battle_mock(self) -> None:
        """Reset the mock and replay its battle entrance presentation."""

        self._restart_battle_bgm()
        self.inventory_system = InventorySystem.with_one_each(self.item_catalog)
        for member in self.party:
            member.fully_recover()
        for monster in self.monsters:
            monster.restore()
        self.timeline = self.party_visuals + self.monsters
        self.phase = BattleMockPhase.ENTRANCE
        self.active_party_index = 0
        self.active_party_pulse_frame = 0
        self._sync_active_party_pulse_palette()
        self.blinking_monster_index = None
        self.monster_blink_frames_remaining = 0
        self.timeline_animation_phase = None
        self.timeline_animation_frame = 0
        self.formation_animation_frame = 0
        self.formation_actor_index = None
        self.formation_start_x = 0
        self.formation_destination_x = 0
        self.escape_animation_frame = 0
        self.escape_start_x = ()
        self.escape_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.escape_fade_covered = False
        self.monster_death_animation = None
        self.dying_monster_index = None
        self.entrance_animation_frame = 0
        self.selected_command = None
        self.selectable_target_indexes = ()
        self.selected_target_index = None
        self.item_candidates = ()
        self.selected_item_index = 0
        self.item_scroll_offset = 0
        self.item_cursor = None
        self.spell_candidates = ()
        self.spell_scroll_offset = 0
        self.spell_type = SpellType.MYSTIC
        self.spell_cursor = None
        self._hide_command_guide()
        self.item_guide_window.close_immediately()
        self.item_guide_window.clear_texts()
        self._close_spell_windows()
        self.defending_party_indexes.clear()
        self.escaping_party_indexes.clear()
        self.target_cursor.active = False
        self.escape_cursor.active = False
        self.command_window.close_immediately()
        self.item_window.close_immediately()
        self._refresh_command_options()
        self.command_cursor.active = False
        self._refresh_party_text_colors()
        self._refresh_monster_name_colors()
        self.entrance_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.entrance_fade.start_fade_in()
        self.palette_shifter.set_global_mix(
            base_rate=0.0,
            target_color=self.palette_shifter.base_colors[0],
        )

    def _restart_battle_bgm(self) -> None:
        """Restart the battle track from its beginning for each mock reset."""

        self.bgm.stop()
        self.bgm.play(BATTLE_BGM_ID)

    def _close_spell_windows(self) -> None:
        """Hide and clear the battle spell-selection windows."""

        for name in ("spell_window", "spell_guide_window", "spell_mp_window"):
            window = getattr(self, name, None)
            if window is not None:
                window.close_immediately()
                window.clear_texts()

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
        self.item_candidates = ()
        self.selected_item_index = 0
        self.item_scroll_offset = 0
        self.item_cursor = None
        self.spell_candidates = ()
        self.spell_scroll_offset = 0
        self.spell_type = SpellType.MYSTIC
        self.spell_cursor = None
        self.command_cursor.active = False
        self.target_cursor.active = False
        self.command_window.close_immediately()
        item_window = getattr(self, "item_window", None)
        if item_window is not None:
            item_window.close_immediately()
        item_guide_window = getattr(self, "item_guide_window", None)
        if item_guide_window is not None:
            item_guide_window.close_immediately()
            item_guide_window.clear_texts()
        self._close_spell_windows()
        self._hide_command_guide()
        self._refresh_monster_name_colors()

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
                self._accept_escape_confirmation()
            else:
                self._cancel_escape_confirmation()
            return
        self.escape_cursor.update(input_state.navigation)

    def _accept_escape_confirmation(self) -> None:
        """Put the current member into escape state and complete their turn."""

        if self.active_party_index is None:
            raise RuntimeError("escape confirmation requires an active member")
        self.escape_cursor.active = False
        all_members_ready = self._mark_party_member_escaping(self.active_party_index)
        if all_members_ready:
            self._begin_escape_animation()
            return
        self._complete_current_turn()

    def _mark_party_member_escaping(self, index: int) -> bool:
        """Reverse one member and report whether the whole party is ready."""

        self.escaping_party_indexes.add(index)
        self.defending_party_indexes.discard(index)
        return len(self.escaping_party_indexes) == len(self.party_visuals)

    def _begin_escape_animation(self) -> None:
        """Show the success message and start the DA2-style party run."""

        self.phase = BattleMockPhase.ESCAPE_MESSAGE
        self.escape_animation_frame = 0
        self.escape_start_x = tuple(
            self._party_sprite_x(index) for index in range(len(self.party_visuals))
        )
        self.escape_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.escape_fade_covered = False
        self.active_party_index = None
        self.command_cursor.active = False
        self.escape_cursor.active = False
        self._refresh_party_text_colors()
        self.bgm.stop()

    def _update_escape_message(self, input_state: InputState) -> None:
        """Keep running while the success message waits for acknowledgement."""

        self._advance_escape_run()
        if input_state.confirm.triggered or input_state.cancel.triggered:
            self.phase = BattleMockPhase.ESCAPE
            self.escape_fade.start()

    def _update_escape_animation(self) -> None:
        """Fade out after acknowledgement and finish once fully covered."""

        self._update_escape_fade()
        self._advance_escape_run()
        if self.escape_fade_covered and all(
            self._escape_party_x(index) >= ESCAPE_RUN_DESTINATION_X
            for index in range(len(self.party_visuals))
        ):
            pyxel.quit()

    def _advance_escape_run(self) -> None:
        """Advance the shared party run by one frame."""

        self.escape_animation_frame += 1

    def _update_escape_fade(self) -> None:
        """Fade to black once and hold the covered frame until mock exit."""

        if self.escape_fade_covered:
            return
        event = self.escape_fade.update()
        self.palette_shifter.set_global_mix(
            base_rate=self.escape_fade.visible_rate,
            target_color=self.palette_shifter.base_colors[0],
        )
        if event is FadeEvent.COVERED:
            self.escape_fade_covered = True

    def _cancel_escape_confirmation(self) -> None:
        self.phase = BattleMockPhase.COMMAND
        self.selected_command = None
        self.escape_cursor.active = False
        self.command_cursor.active = True
        self._hide_command_guide()
        self.command_window.open()

    def _begin_formation_change(self) -> bool:
        """Swap the active member's row and start the walking animation."""

        if self.active_party_index is None:
            return False
        index = self.active_party_index
        member = self.party[index]
        if len(self.party) <= 1 or not formation_change_enabled(
            member,
            self.party,
        ):
            return False
        self.formation_actor_index = index
        self.formation_start_x = self._party_sprite_x(index)
        member.formation_row = (
            FormationRow.BACK
            if member.formation_row is FormationRow.FRONT
            else FormationRow.FRONT
        )
        self.formation_destination_x = self._party_sprite_x(index)
        self.formation_animation_frame = 0
        self.phase = BattleMockPhase.FORMATION
        self.selected_command = BattleCommand.FORMATION
        self.command_cursor.active = False
        self.command_window.close_immediately()
        return True

    def _begin_defense(self) -> bool:
        """Keep the active member in a defensive stance until their next turn."""

        if self.active_party_index is None:
            return False
        self.defending_party_indexes.add(self.active_party_index)
        self.selected_command = BattleCommand.DEFEND
        self._complete_current_turn()
        return True

    def _update_formation_animation(self) -> None:
        """Advance one formation walk and then complete the actor's turn."""

        self.formation_animation_frame += 1
        if self.formation_animation_frame < FORMATION_MOVE_FRAME_COUNT:
            return
        self.formation_animation_frame = FORMATION_MOVE_FRAME_COUNT
        self.formation_actor_index = None
        self._complete_current_turn()

    def _active_member_item_candidates(self) -> tuple[BattleItemCandidate, ...]:
        """Return DA2-style equipment followed by owned usable consumables.

        There is no command-reservation filtering here: ZERO executes each
        party member's selected command before the next member chooses one.
        """

        if self.active_party_index is None:
            return ()
        member = self.party[self.active_party_index]
        equipped = tuple(
            BattleItemCandidate(item, slot)
            for slot in EquipmentSlot
            if (
                (item := member.equipment.item_at(slot)) is not None
                and (item.is_weapon or item.equip_type is ItemEquipType.ARM)
            )
        )
        consumables = tuple(
            BattleItemCandidate(item)
            for item in self.inventory_system.items
            if (
                item.equip_type is ItemEquipType.ITEM
                and item.subtype == "ITEM"
                and self._item_is_usable_in_battle(item)
            )
        )
        return (*equipped, *consumables)

    def _item_is_usable_in_battle(self, item: Item) -> bool:
        """Return whether an item's resolved use effect permits battle use."""

        if not item.use_spell_key:
            return False
        spell = self.spells.get(item.use_spell_key)
        return spell is not None and spell.on_battle

    @property
    def selected_item_candidate(self) -> BattleItemCandidate | None:
        """Return the selected item candidate, if its index is still valid."""

        if not 0 <= self.selected_item_index < len(self.item_candidates):
            return None
        return self.item_candidates[self.selected_item_index]

    def _begin_item_selection(self) -> bool:
        """Replace the command contents with the current actor's item list."""

        candidates = self._active_member_item_candidates()
        if not candidates:
            return False
        self.phase = BattleMockPhase.ITEM
        self.selected_command = BattleCommand.ITEM
        self.item_candidates = candidates
        self.selected_item_index = 0
        self.item_scroll_offset = 0
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self.item_window.open_immediately()
        self._hide_command_guide()
        self._refresh_item_options()
        return True

    def _refresh_item_options(self) -> None:
        """Draw up to three candidates over the command window and their guide."""

        selected = self.selected_item_candidate
        visible = self.item_candidates[
            self.item_scroll_offset : self.item_scroll_offset + ITEM_VISIBLE_COUNT
        ]
        self.item_window.vertical_navigation = (
            len(self.item_candidates) > ITEM_VISIBLE_COUNT
        )
        self.item_window.set_vertical_navigation_pressed()
        self.item_window.clear_texts()
        self.item_window.clear_cursor()
        for row, candidate in enumerate(visible):
            item = candidate.item
            y = ITEM_FIRST_Y + row * ITEM_ROW_HEIGHT
            prefix = "＃" if candidate.is_equipped else ""
            self.item_window.add_text(
                prefix + item.localized_name(self.localizer),
                ITEM_TEXT_X,
                y,
            )
            if not candidate.is_equipped:
                self.item_window.add_text(
                    ascii_to_fullwidth(str(self.inventory_system.quantity(item))),
                    ITEM_COUNT_X,
                    y,
                )
        self.item_cursor = self.item_window.set_cursor(
            tuple(
                CursorTarget(
                    ITEM_CURSOR_X,
                    ITEM_FIRST_Y + row * ITEM_ROW_HEIGHT,
                    key=self.item_scroll_offset + row,
                )
                for row in range(len(visible))
            )
        )
        if selected is not None:
            self.item_cursor.select_key(self.selected_item_index)
        self._refresh_item_guide()

    def _refresh_item_guide(self) -> None:
        """Show the battle-use effect of the selected item beside its list."""

        self.item_guide_window.close_immediately()
        self.item_guide_window.clear_texts()
        candidate = self.selected_item_candidate
        if candidate is None:
            return
        for index, line in enumerate(
            item_detail_lines(
                candidate.item,
                self.spells,
                self.localizer,
                self.texts,
                context=ItemDetailContext.BATTLE,
            )[:COMMAND_GUIDE_MAX_LINES]
        ):
            if line:
                self.item_guide_window.add_text(
                    line,
                    COMMAND_GUIDE_TEXT_X,
                    COMMAND_GUIDE_FIRST_Y + index * COMMAND_GUIDE_LINE_SPACING,
                )
        self.item_guide_window.open_immediately()

    def _move_item(self, distance: int) -> bool:
        """Move through the complete candidate list while keeping three rows visible."""

        if distance not in (-1, 1) or not self.item_candidates:
            return False
        previous = self.selected_item_index
        self.selected_item_index = (self.selected_item_index + distance) % len(
            self.item_candidates
        )
        if self.selected_item_index < self.item_scroll_offset:
            self.item_scroll_offset = self.selected_item_index
        elif self.selected_item_index >= self.item_scroll_offset + ITEM_VISIBLE_COUNT:
            self.item_scroll_offset = self.selected_item_index - ITEM_VISIBLE_COUNT + 1
        if self.selected_item_index != previous:
            self._refresh_item_options()
            return True
        return False

    def _update_item_selection(self, input_state: InputState) -> None:
        """Accept a battle item, or restore the command list on cancellation."""

        if input_state.cancel.triggered:
            self._cancel_item_selection()
            return
        if input_state.confirm.triggered:
            self._use_selected_item()
            return
        navigation = input_state.navigation
        if navigation is not None and navigation.dy:
            self._move_item(navigation.dy)
        self.item_window.set_vertical_navigation_pressed(
            0 if navigation is None else navigation.dy
        )
        if self.item_cursor is not None:
            self.item_cursor.update()

    def _cancel_item_selection(self) -> None:
        self.phase = BattleMockPhase.COMMAND
        self.selected_command = None
        self.item_candidates = ()
        self.selected_item_index = 0
        self.item_scroll_offset = 0
        self.item_cursor = None
        self.item_window.close_immediately()
        self.item_guide_window.close_immediately()
        self.item_guide_window.clear_texts()
        self._refresh_command_options()
        self.command_cursor.active = True
        self.command_cursor.select_key(BattleCommand.ITEM)
        self.command_window.open_immediately()

    def _use_selected_item(self) -> bool:
        """Consume a selected consumable or break the selected equipped item."""

        candidate = self.selected_item_candidate
        if candidate is None or self.active_party_index is None:
            return False
        item = candidate.item
        if not self._item_is_usable_in_battle(item):
            return False
        if item.breaks_on_use:
            if candidate.equipment_slot is None:
                if not self.inventory_system.remove(item):
                    return False
            else:
                member = self.party[self.active_party_index]
                member.equipment = member.equipment.replaced(
                    {candidate.equipment_slot: None}
                )
        self._complete_current_turn()
        return True

    def _active_member_spell_candidates(self) -> tuple[Spell, ...]:
        """Return the active member's learned spells that work in battle."""

        if self.active_party_index is None:
            return ()
        member = self.party[self.active_party_index]
        return tuple(
            spell
            for spell in self.spells.values()
            if (
                spell.type is not SpellType.ITEM
                and spell.on_battle
                and spell.is_learned_by(member)
            )
        )

    @property
    def selected_spell(self) -> Spell | None:
        """Return the currently selected battle spell, if one is selectable."""

        cursor = self.spell_cursor
        if cursor is None or not isinstance(cursor.selected_key, str):
            return None
        return next(
            (
                spell
                for spell in self.spell_candidates
                if spell.key == cursor.selected_key
            ),
            None,
        )

    def _begin_spell_selection(self) -> bool:
        """Open the DA2-style three-school battle spell list."""

        candidates = self._active_member_spell_candidates()
        if not candidates:
            return False
        self.phase = BattleMockPhase.SPELL
        self.selected_command = BattleCommand.SPELL
        self.spell_candidates = candidates
        self.spell_scroll_offset = 0
        member = self.party[self.active_party_index]
        self.spell_type = next(
            spell_type
            for spell_type in SPELL_TYPE_ORDER
            if any(
                spell.mp <= member.mp
                for spell in self._spell_candidates_for_type(spell_type)
            )
            or self._spell_candidates_for_type(spell_type)
        )
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self.spell_window.open_immediately()
        self._hide_command_guide()
        self._refresh_spell_options()
        return True

    def _refresh_spell_options(self) -> None:
        """Populate the active school in the four-row battle spell list."""

        if self.active_party_index is None:
            return
        member = self.party[self.active_party_index]
        cursor = getattr(self, "spell_cursor", None)
        selected_key = (
            cursor.selected_key
            if cursor is not None and isinstance(cursor.selected_key, str)
            else None
        )
        maximum_offset = len(SPELL_DISPLAY_LEVELS) - SPELL_VISIBLE_COUNT
        scroll_offset = min(
            max(getattr(self, "spell_scroll_offset", 0), 0),
            maximum_offset,
        )
        self.spell_scroll_offset = scroll_offset
        visible_levels = SPELL_DISPLAY_LEVELS[
            scroll_offset : scroll_offset + SPELL_VISIBLE_COUNT
        ]
        self.spell_window.clear_texts()
        self.spell_window.clear_cursor()
        targets: list[CursorTarget] = []
        for row, level in enumerate(visible_levels):
            y = SPELL_FIRST_Y + row * SPELL_ROW_HEIGHT
            spell = next(
                (
                    candidate
                    for candidate in self.spell_candidates
                    if candidate.type is self.spell_type and candidate.level == level
                ),
                None,
            )
            if spell is None:
                continue
            available = member.mp >= spell.mp
            self.spell_window.add_text(
                spell.localized_display_name(self.localizer),
                SPELL_TEXT_X,
                y,
                color=DEFAULT_TEXT_COLOR if available else DISABLED_COLOR,
            )
            targets.append(
                CursorTarget(
                    SPELL_CURSOR_X,
                    y,
                    key=spell.key,
                    selectable=available,
                )
            )
        self.spell_cursor = self.spell_window.set_cursor(tuple(targets))
        if selected_key is not None:
            try:
                self.spell_cursor.select_key(selected_key)
            except ValueError:
                pass
        self.spell_window.vertical_navigation = any(
            spell.level not in visible_levels
            for spell in self._spell_candidates_for_type(self.spell_type)
        )
        self.spell_window.set_vertical_navigation_pressed()
        self._refresh_spell_guide()

    def _spell_candidates_for_type(self, spell_type: SpellType) -> tuple[Spell, ...]:
        """Return one school's candidates in the menu's level order."""

        return tuple(
            spell
            for level in SPELL_DISPLAY_LEVELS
            for spell in self.spell_candidates
            if spell.type is spell_type and spell.level == level
        )

    def _ensure_selected_spell_is_visible(self, spell: Spell) -> None:
        """Scroll every school column to keep one spell's level row visible."""

        index = SPELL_DISPLAY_LEVELS.index(spell.level)
        if index < self.spell_scroll_offset:
            self.spell_scroll_offset = index
        elif index >= self.spell_scroll_offset + SPELL_VISIBLE_COUNT:
            self.spell_scroll_offset = index - SPELL_VISIBLE_COUNT + 1

    def _refresh_spell_guide(self) -> None:
        """Show a selected spell's guide, cost, and current MP in one window."""

        guide_window = self.spell_guide_window
        mp_window = self.spell_mp_window
        guide_window.close_immediately()
        guide_window.clear_texts()
        mp_window.close_immediately()
        mp_window.clear_texts()
        if self.active_party_index is None:
            return
        member = self.party[self.active_party_index]
        spell = self.selected_spell
        if spell is not None:
            for index, line in enumerate(
                spell.localized_description(self.localizer)[:2]
            ):
                guide_window.add_text(
                    line,
                    COMMAND_GUIDE_TEXT_X,
                    COMMAND_GUIDE_FIRST_Y + index * COMMAND_GUIDE_LINE_SPACING,
                )
        if spell is not None:
            cost_label = self.texts.text("spell.mp_cost", self.localizer)
            guide_window.add_text(
                ascii_to_fullwidth(cost_label.replace("%MP%", str(spell.mp))),
                COMMAND_GUIDE_TEXT_X,
                COMMAND_GUIDE_FIRST_Y + COMMAND_GUIDE_LINE_SPACING * 3,
                color=(DEFAULT_TEXT_COLOR if member.mp >= spell.mp else DISABLED_COLOR),
            )
        mp_label = self.texts.text("menu.member.mp", self.localizer)
        mp_window.add_text(
            ascii_to_fullwidth(f"{mp_label} {member.mp:03d}"),
            COMMAND_GUIDE_TEXT_X,
            COMMAND_GUIDE_FIRST_Y,
        )
        guide_window.open_immediately()
        mp_window.open_immediately()

    def _update_spell_selection(self, input_state: InputState) -> None:
        """Choose a spell or return to the active member's command list."""

        if input_state.cancel.triggered:
            self._cancel_spell_selection()
            return
        if input_state.confirm.triggered:
            self._use_selected_spell()
            return
        navigation = input_state.navigation
        if navigation is not None:
            self._move_spell(navigation)
        self.spell_window.set_vertical_navigation_pressed(
            0 if navigation is None else navigation.dy
        )
        if self.spell_cursor is not None:
            self.spell_cursor.update()

    def _move_spell(self, direction: Direction) -> bool:
        """Move within a school or switch schools with left and right."""

        current = self.selected_spell
        if current is None or self.active_party_index is None:
            return False
        member = self.party[self.active_party_index]
        if direction.dy:
            candidates = tuple(
                spell
                for spell in self._spell_candidates_for_type(current.type)
                if member.mp >= spell.mp
            )
            if not candidates:
                return False
            target = candidates[
                (candidates.index(current) + direction.dy) % len(candidates)
            ]
        elif direction.dx:
            column = SPELL_TYPE_ORDER.index(current.type)
            target = None
            for step in range(1, len(SPELL_TYPE_ORDER) + 1):
                spell_type = SPELL_TYPE_ORDER[
                    (column + direction.dx * step) % len(SPELL_TYPE_ORDER)
                ]
                candidates = tuple(
                    spell
                    for spell in self._spell_candidates_for_type(spell_type)
                    if member.mp >= spell.mp
                )
                if not candidates:
                    continue
                target = next(
                    (spell for spell in candidates if spell.level == current.level),
                    candidates[0],
                )
                break
            if target is None:
                return False
        else:
            return False
        if target is current:
            return False
        self.spell_type = target.type
        self._ensure_selected_spell_is_visible(target)
        self._refresh_spell_options()
        self.spell_cursor.select_key(target.key)
        visible_levels = SPELL_DISPLAY_LEVELS[
            self.spell_scroll_offset : self.spell_scroll_offset + SPELL_VISIBLE_COUNT
        ]
        self.spell_window.vertical_navigation = any(
            spell.level not in visible_levels
            for spell in self._spell_candidates_for_type(target.type)
        )
        self._refresh_spell_guide()
        return True

    def _cancel_spell_selection(self) -> None:
        self.phase = BattleMockPhase.COMMAND
        self.selected_command = None
        self.spell_candidates = ()
        self.spell_scroll_offset = 0
        self.spell_type = SpellType.MYSTIC
        self.spell_cursor = None
        self._close_spell_windows()
        self._refresh_command_options()
        self.command_cursor.active = True
        self.command_cursor.select_key(BattleCommand.SPELL)
        self.command_window.open_immediately()

    def _use_selected_spell(self) -> bool:
        """Spend the selected spell's MP and finish this mock battle turn."""

        if self.active_party_index is None:
            return False
        spell = self.selected_spell
        member = self.party[self.active_party_index]
        if spell is None or member.mp < spell.mp:
            return False
        member.mp -= spell.mp
        self._complete_current_turn()
        return True

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
        self._refresh_monster_name_colors()
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
            self._begin_monster_death()
            return

        navigation = input_state.navigation
        if navigation is not None:
            self._move_target(navigation)
        self.target_cursor.update()

    def _begin_monster_death(self) -> bool:
        """Set the selected target's HP to zero and start its defeat effect."""

        index = self.selected_target_index
        if index is None or index not in self.selectable_target_indexes:
            return False
        monster = self.monsters[index]
        if not monster.is_alive:
            return False

        monster.state.defeat()
        promote_rear_monsters_if_front_empty(self.monsters)
        self.phase = BattleMockPhase.MONSTER_DEATH
        self.dying_monster_index = index
        self.monster_death_animation = MonsterDeathAnimation()
        self.target_cursor.active = False
        self.command_window.close_immediately()
        self._sync_monster_death_palette()
        return True

    def _update_monster_death_animation(self) -> None:
        """Advance the death effect, remove its actor, and finish the turn."""

        animation = self.monster_death_animation
        if animation is None:
            raise RuntimeError("monster death phase requires an animation")
        animation.update()
        if not animation.is_finished:
            self._sync_monster_death_palette()
            return

        dying_index = self.dying_monster_index
        if dying_index is None:
            raise RuntimeError("monster death phase requires a target")
        defeated = self.monsters[dying_index]
        self.timeline = tuple(entry for entry in self.timeline if entry is not defeated)
        self.monster_death_animation = None
        self.dying_monster_index = None
        self._complete_current_turn()

    def _sync_monster_death_palette(self) -> None:
        animation = self.monster_death_animation
        if animation is None:
            return
        self.palette_shifter.define_mix(
            MONSTER_DEATH_PALETTE,
            base_rate=MONSTER_DEATH_PALETTE_BASE_RATE,
            target_color=animation.palette_target_color,
        )

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
        self.item_candidates = ()
        self.selected_item_index = 0
        self.item_scroll_offset = 0
        self.item_cursor = None
        self.spell_candidates = ()
        self.spell_scroll_offset = 0
        self.spell_type = SpellType.MYSTIC
        self.spell_cursor = None
        self.target_cursor.active = False
        item_window = getattr(self, "item_window", None)
        if item_window is not None:
            item_window.close_immediately()
        item_guide_window = getattr(self, "item_guide_window", None)
        if item_guide_window is not None:
            item_guide_window.close_immediately()
            item_guide_window.clear_texts()
        self._close_spell_windows()
        self.command_guide_window.close_immediately()
        self.command_guide_window.clear_texts()
        self._start_timeline_animation()

    def _start_timeline_animation(self) -> None:
        self.phase = BattleMockPhase.TIMELINE
        self.active_party_index = None
        if hasattr(self, "active_party_pulse_frame"):
            self.active_party_pulse_frame = 0
            self._sync_active_party_pulse_palette()
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self.timeline_animation_phase = TimelineAnimationPhase.DROP
        self.timeline_animation_frame = 0
        self._refresh_party_text_colors()

    def _active_party_pulse_is_visible(self) -> bool:
        """Return whether the current actor's palette pulse should be drawn."""

        return (
            self.phase
            in (
                BattleMockPhase.COMMAND,
                BattleMockPhase.ITEM,
                BattleMockPhase.SPELL,
                BattleMockPhase.TARGET,
                BattleMockPhase.ESCAPE_CONFIRMATION,
            )
            and getattr(self, "active_party_index", None) is not None
        )

    def _update_active_party_pulse(self) -> None:
        """Advance the current actor's whiteward palette pulse."""

        if self._active_party_pulse_is_visible():
            self.active_party_pulse_frame = (
                self.active_party_pulse_frame + 1
            ) % ACTIVE_PARTY_PULSE_CYCLE_FRAME_COUNT
        else:
            self.active_party_pulse_frame = 0
        self._sync_active_party_pulse_palette()

    def _sync_active_party_pulse_palette(self) -> None:
        """Apply the pulse frame as a scoped palette variant."""

        half_cycle = ACTIVE_PARTY_PULSE_HALF_CYCLE_FRAME_COUNT
        distance_from_peak = abs(half_cycle - self.active_party_pulse_frame)
        progress_to_normal = distance_from_peak / half_cycle
        base_rate = ACTIVE_PARTY_PULSE_MIN_BASE_RATE + (
            (1.0 - ACTIVE_PARTY_PULSE_MIN_BASE_RATE) * progress_to_normal
        )
        self.palette_shifter.define_mix(
            ACTIVE_PARTY_PULSE_PALETTE,
            base_rate=base_rate,
            target_color=ACTIVE_PARTY_PULSE_TARGET_COLOR,
        )

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
            self.blinking_monster_index = None
            self.monster_blink_frames_remaining = 0
            if getattr(self, "escaping_party_indexes", ()):
                all_members_ready = self._mark_party_member_escaping(
                    self.active_party_index
                )
                if all_members_ready:
                    self._begin_escape_animation()
                else:
                    self._start_timeline_animation()
                return
            self.defending_party_indexes.discard(self.active_party_index)
            self.phase = BattleMockPhase.COMMAND
            self.command_cursor.active = True
            self._hide_command_guide()
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

    def _active_member_command_options(self) -> tuple[BattleCommandOption, ...]:
        """Ask the Pyxel-independent rules for this actor's command state."""

        if self.active_party_index is None:
            return ()
        return resolve_battle_commands(
            self.party[self.active_party_index],
            self.party,
            self.monsters,
            context=BattleCommandContext(
                item_available=bool(self._active_member_item_candidates()),
            ),
        )

    def _refresh_command_options(self) -> None:
        options = self._active_member_command_options()
        right_start = next(
            (
                index
                for index, option in enumerate(options)
                if option.command is BattleCommand.ESCAPE
            ),
            len(options),
        )
        columns = (options[:right_start], options[right_start:])
        placements = []
        for column_index, visible in enumerate(columns):
            placements.extend(
                (
                    option,
                    self._command_label(option.command),
                    COMMAND_TEXT_X[column_index],
                    COMMAND_ROW_Y[row_index],
                    COMMAND_CURSOR_X[column_index],
                    COMMAND_ROW_Y[row_index],
                )
                for row_index, option in enumerate(visible)
            )
        self.command_window.vertical_navigation = False
        self.command_window.set_vertical_navigation_pressed()
        self.command_window.clear_texts()
        for option, label, text_x, text_y, _, _ in placements:
            if option.enabled:
                self.command_window.add_text(label, text_x, text_y)
            else:
                self.command_window.add_text(
                    label,
                    text_x,
                    text_y,
                    color=DISABLED_COLOR,
                )
        self.command_window.clear_cursor()
        self.command_cursor = self.command_window.set_cursor(
            tuple(
                CursorTarget(
                    cursor_x,
                    cursor_y,
                    key=option.command,
                    selectable=option.enabled,
                )
                for option, _, _, _, cursor_x, cursor_y in placements
            )
        )

    def _command_label(self, command: BattleCommand) -> str:
        """Resolve one command's localized display label from the text catalog."""

        return self.texts.text(COMMAND_TEXT_KEYS[command], self.localizer)

    def _command_guide_lines(self, command: BattleCommand) -> tuple[str, ...]:
        """Return DA2-derived guide text or the command name as a placeholder."""

        key = COMMAND_GUIDE_TEXT_KEYS.get(command, COMMAND_TEXT_KEYS[command])
        return self.texts.lines(key, self.localizer)

    def _update_command_guide(self) -> None:
        """Show a guide after the command cursor stays on one entry briefly."""

        guide_window = getattr(self, "command_guide_window", None)
        if guide_window is None:
            return
        if (
            self.phase is not BattleMockPhase.COMMAND
            or not self.command_window.is_open
            or not isinstance(self.command_cursor.selected_key, BattleCommand)
        ):
            self._hide_command_guide()
            return

        command = self.command_cursor.selected_key
        if command is not self.command_guide_command:
            self.command_guide_command = command
            self.command_guide_timer = 1
            self.command_guide_visible = False
            guide_window.close_immediately()
            guide_window.clear_texts()
        else:
            self.command_guide_timer = min(
                self.command_guide_timer + 1,
                COMMAND_GUIDE_DELAY_FRAME_COUNT,
            )

        if (
            self.command_guide_timer == COMMAND_GUIDE_DELAY_FRAME_COUNT
            and not self.command_guide_visible
        ):
            guide_window.clear_texts()
            for index, line in enumerate(
                self._command_guide_lines(command)[:COMMAND_GUIDE_MAX_LINES]
            ):
                guide_window.add_text(
                    line,
                    COMMAND_GUIDE_TEXT_X,
                    COMMAND_GUIDE_FIRST_Y + index * COMMAND_GUIDE_LINE_SPACING,
                )
            guide_window.open_immediately()
            self.command_guide_visible = True

    def _hide_command_guide(self) -> None:
        """Clear the delayed command guide outside command selection."""

        guide_window = getattr(self, "command_guide_window", None)
        if guide_window is None:
            return
        self.command_guide_command = None
        self.command_guide_timer = 0
        self.command_guide_visible = False
        guide_window.close_immediately()
        guide_window.clear_texts()

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

    def _refresh_monster_name_colors(self) -> None:
        """Reflect target availability in the monster-name colors."""

        for index, (window, placement) in enumerate(
            zip(self.monster_name_windows, self.monster_name_texts)
        ):
            selectable = (
                self.phase is not BattleMockPhase.TARGET
                or index in self.selectable_target_indexes
            )
            color = DEFAULT_TEXT_COLOR if selectable else RESERVE_MEMBER_TEXT_COLOR
            self.monster_name_texts[index] = self._replace_text_color(
                window,
                placement,
                color,
            )

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
            is_escaping = self.phase in (
                BattleMockPhase.ESCAPE_MESSAGE,
                BattleMockPhase.ESCAPE,
            ) or index in getattr(self, "escaping_party_indexes", ())
            width = -16 if is_escaping else 16
            if (
                self._active_party_pulse_is_visible()
                and index == self.active_party_index
            ):
                with self.palette_shifter.shifted(ACTIVE_PARTY_PULSE_PALETTE):
                    pyxel.blt(
                        x,
                        y,
                        self.character_sprites,
                        self._party_sprite_source_x(index),
                        visual.battle_sprite * 32,
                        width,
                        32,
                        TRANSPARENT_INDEX,
                    )
                continue
            pyxel.blt(
                x,
                y,
                self.character_sprites,
                self._party_sprite_source_x(index),
                visual.battle_sprite * 32,
                width,
                32,
                TRANSPARENT_INDEX,
            )

    def _party_draw_position(self, index: int) -> tuple[int, int] | None:
        target_x = self._party_sprite_x(index)
        target_y = PARTY_SPRITE_Y[index]
        if self.phase in (BattleMockPhase.ESCAPE_MESSAGE, BattleMockPhase.ESCAPE):
            return self._escape_party_x(index), target_y
        if (
            self.phase is BattleMockPhase.FORMATION
            and index == self.formation_actor_index
        ):
            x = self.formation_start_x + (
                (self.formation_destination_x - self.formation_start_x)
                * self.formation_animation_frame
                // FORMATION_MOVE_FRAME_COUNT
            )
            return x, target_y
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

    def _escape_party_x(self, index: int) -> int:
        """Return one member's rightward run position for the current frame."""

        return min(
            self.escape_start_x[index] + self.escape_animation_frame * ESCAPE_RUN_SPEED,
            ESCAPE_RUN_DESTINATION_X,
        )

    def _party_sprite_x(self, index: int) -> int:
        x = 156 + index * 4
        if self.party_visuals[index].member.formation_row is FormationRow.BACK:
            x += 16
        return x

    def _party_sprite_source_x(self, index: int) -> int:
        if self.phase in (BattleMockPhase.ESCAPE_MESSAGE, BattleMockPhase.ESCAPE):
            pattern = (
                self.escape_animation_frame // ESCAPE_RUN_PATTERN_FRAME_COUNT
            ) % 2
            return pattern * FORMATION_SPRITE_STEP_X
        if index in getattr(self, "escaping_party_indexes", ()):
            return 0
        if (
            self.phase is BattleMockPhase.FORMATION
            and index == self.formation_actor_index
        ):
            pattern = (
                self.formation_animation_frame // FORMATION_WALK_PATTERN_FRAME_COUNT
            ) % 2
            return pattern * FORMATION_SPRITE_STEP_X
        if index in getattr(self, "defending_party_indexes", ()):
            return DEFEND_SPRITE_SOURCE_X
        return 0

    def _draw_monsters(self) -> None:
        for index, (monster, (_, y)) in enumerate(
            zip(self.monsters, MONSTER_POSITIONS)
        ):
            is_dying = (
                self.phase is BattleMockPhase.MONSTER_DEATH
                and index == self.dying_monster_index
            )
            if not monster.is_alive and not is_dying:
                continue
            if (
                index == self.blinking_monster_index
                and self.monster_blink_frames_remaining
                and self.monster_blink_frames_remaining % MONSTER_BLINK_PERIOD
                >= MONSTER_BLINK_VISIBLE_FRAMES
            ):
                continue
            x = self._monster_draw_x(index)
            if not is_dying:
                is_unselectable_rear_target = (
                    self.phase is BattleMockPhase.TARGET
                    and not monster.is_front_row
                    and index not in self.selectable_target_indexes
                )
                if not is_unselectable_rear_target:
                    self._draw_monster_image(monster, x, y)
                    continue
                with self.palette_shifter.shifted(UNSELECTABLE_TARGET_PALETTE):
                    self._draw_monster_image(monster, x, y)
                continue
            animation = self.monster_death_animation
            if animation is None:
                raise RuntimeError("dying monster requires an animation")
            pyxel.dither(animation.opacity)
            try:
                with self.palette_shifter.shifted(MONSTER_DEATH_PALETTE):
                    self._draw_monster_image(monster, x, y)
            finally:
                pyxel.dither(1.0)

    def _draw_monster_image(
        self,
        monster: BattleMockMonster,
        x: int,
        y: int,
    ) -> None:
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
            DA2_MONSTER_ENTRANCE_SLIDE_STEPS[index] * DA2_MONSTER_ENTRANCE_STEP_DISTANCE
        )
        return target_x - initial_offset * remaining // duration

    def _draw_target_cursor(self) -> None:
        if self.phase is not BattleMockPhase.TARGET:
            return
        self.target_cursor.draw()

    def _draw_timeline(self) -> None:
        if self.phase is BattleMockPhase.ENTRANCE:
            for index, entry in enumerate(self.timeline[:TIMELINE_VISIBLE_ENTRY_COUNT]):
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
            for index, entry in enumerate(self.timeline[:TIMELINE_VISIBLE_ENTRY_COUNT]):
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
            destination_x = (
                TIMELINE_BASE_X + (visible_entry_count - 1) * TIMELINE_SLOT_SPACING
            )
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

        for index, entry in enumerate(self.timeline[:TIMELINE_VISIBLE_ENTRY_COUNT]):
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
        hide_party_status = self.phase in (
            BattleMockPhase.ESCAPE_MESSAGE,
            BattleMockPhase.ESCAPE,
        ) or (
            self.phase is BattleMockPhase.ENTRANCE
            and self.entrance_animation_frame < PARTY_ENTRANCE_COMPLETE_FRAME
        )
        for window in self.windows:
            if hide_party_status and any(
                window is status_window for status_window in self.party_status_windows
            ):
                continue
            window.draw()
        if self.phase is BattleMockPhase.TARGET or (
            self.phase is BattleMockPhase.INITIAL and self.command_window.is_closed
        ):
            for monster, window in zip(
                self.monsters,
                self.monster_name_windows,
            ):
                if monster.is_alive:
                    window.draw()
        if (
            self.phase is BattleMockPhase.ESCAPE_CONFIRMATION
            and self.command_window.is_closed
        ):
            self.escape_message_window.draw()
            self.escape_choice_window.draw()
        if self.phase is BattleMockPhase.ESCAPE_MESSAGE:
            self.escape_started_message_window.draw()


def main() -> int:
    return run_screen_mock(
        BattleScreenMock,
        expected_errors=(
            AudioResourceError,
            FontResourceError,
            ImageResourceError,
            MonsterDataError,
            TextCatalogError,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
