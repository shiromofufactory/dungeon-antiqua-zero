"""Run and render Dungeon Antiqua ZERO battles."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Callable, TypeVar

import pyxel

from attack_pose import (
    AttackPoseDefinition,
    AttackWeaponSprite,
    attack_sequence,
    load_attack_poses,
)
from battle_commands import (
    BattleCommand,
    BattleCommandContext,
    BattleCommandOption,
    formation_change_enabled,
    member_can_attack,
    member_attack_reach,
    resolve_battle_commands,
    selectable_attack_target_indexes,
)
from battle_physical import member_physical_attack, resolve_physical_attack
from battle_timeline import (
    TimelineAdvance,
    TimelineOrder,
    complete_timeline_action,
    initialize_timeline_order,
    ready_timeline_head,
    remove_timeline_actor,
)
from item import Item, ItemEquipType
from localization import Localizer, ascii_to_fullwidth
from member import (
    EquipmentSlot,
    FormationRow,
    Member,
)
from monster import (
    MonsterBattleState,
    MonsterCombatStats,
    promote_rear_monsters_if_front_empty,
)
from input import Direction, InputAction, InputDevice, InputState
from rendering import (
    DEFAULT_FADE_FRAME_COUNT,
    DIMMED_PALETTE,
    MONSTER_DEATH_PALETTE,
    MONSTER_DEATH_PALETTE_BASE_RATE,
    SPELL_EFFECT_FLASH_PALETTE,
    FadeEvent,
    FadeThroughBlack,
    MonsterDeathAnimation,
    SpellEffectRenderer,
)
from resources import (
    TRANSPARENT_INDEX,
    BgmPlayer,
    FontResources,
    ImageResourceError,
    ImageResources,
    load_record_array,
    play_se,
)
from state import Language, Settings
from spell import Spell, SpellType
from spell_effect import (
    SpellEffectPlayer,
    load_spell_effects,
)
from systems import InventorySystem
from text_catalog import TextCatalog
from ui import (
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    RESERVE_MEMBER_TEXT_COLOR,
    CursorTarget,
    Window,
    WindowCursor,
    WindowFactory,
    WindowText,
    input_icon_tag,
)
from item_detail import ItemDetailContext, item_detail_lines

APP_ROOT = Path(__file__).resolve().parents[1]
FPS = 60
SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240

BACKGROUND_IMAGE_ID = "background/bg_nector"
CH_BATTLE_IMAGE_ID = "characters/ch_battle"
BATTLE_BGM_ID = "da3-battle1"
BATTLE_HIT_SE_ID = "battle_hit"
BATTLE_MONSTER_DEATH_SE_ID = "battle_monster_death"
ATTACK_SLASH_SE_ID = "battle_weapon_slash"
ATTACK_BLUNT_SE_ID = "battle_weapon_blunt"
PARTY_SPRITE_Y = (64, 92, 120, 148, 176)
# Pyxel can remap only four 16-color palette blocks. The battle scene does
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
TIMELINE_ICON_SIZE = 16
TIMELINE_VISIBLE_ENTRY_COUNT = 6
TIMELINE_ANIMATION_FRAME_COUNT = 8
TIMELINE_DROP_DISTANCE = SCREEN_HEIGHT - TIMELINE_BASE_Y
TIMELINE_INCOMING_START_X = SCREEN_WIDTH
TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT = 4
TIMELINE_INTERRUPT_SLIDE_FRAME_COUNT = 4
TIMELINE_INTERRUPT_OVERFLOW_FRAME_COUNT = 10
TIMELINE_INTERRUPT_OVERFLOW_JUMP_HEIGHT = 18
TIMELINE_INTERRUPT_OVERFLOW_DESTINATION_X = SCREEN_WIDTH + 16
ESCAPE_MESSAGE_WINDOW_GRID = (0, 0, 64, 7)
ESCAPE_MESSAGE_TEXT_POSITION = (2, 2)
ESCAPE_CHOICE_WINDOW_GRID = (52, 0, 12, 10)
ESCAPE_CHOICE_TEXT_X = 4
ESCAPE_CHOICE_CURSOR_X = 2
ESCAPE_YES_Y = 2
ESCAPE_NO_Y = 5
COMMAND_GUIDE_WINDOW_GRID = (0, 0, 34, 13)
GLOBAL_COMMAND_WINDOW_GRID = (49, 0, 15, 13)
INPUT_GUIDE_WINDOW_GRID = (48, 56, 16, 4)
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
    + 2 * PARTY_ENTRANCE_STAGGER_FRAME_COUNT
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
DA2_DAMAGE_VERTICAL_OFFSETS = (
    2,
    8,
    14,
    18,
    20,
    18,
    14,
    8,
    0,
    4,
    6,
    6,
    4,
    0,
    0,
    0,
)
DA2_MISS_VERTICAL_OFFSETS = (-1, 0, 5, 9, 12, 14, 12, 9, 5, 0, 0, 0, 0)
ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT = 10
DAMAGE_POPUP_LAST_FRAME_HOLD_COUNT = 3
DAMAGE_POPUP_FRAME_COUNT = (
    len(DA2_DAMAGE_VERTICAL_OFFSETS) * FPS // DA2_REFERENCE_FPS
    + DAMAGE_POPUP_LAST_FRAME_HOLD_COUNT
)
MONSTER_DAMAGE_FRAME_COUNT = DAMAGE_POPUP_FRAME_COUNT
MONSTER_MISS_FRAME_COUNT = (
    len(DA2_MISS_VERTICAL_OFFSETS) * FPS // DA2_REFERENCE_FPS
)
MONSTER_DAMAGE_SPRITE_SOURCE_X = 16 * 4
MONSTER_DAMAGE_SHAKE_X = (8, 9)
DAMAGE_NUMBER_SPRITE_Y = 48
DAMAGE_NUMBER_SPRITE_SIZE = 8
MISS_SPRITE_SOURCE_X = 80
MISS_SPRITE_WIDTH = 16
UNSELECTABLE_TARGET_PALETTE = "unselectable_target"
UNSELECTABLE_TARGET_PALETTE_BASE_RATE = 0.5
FORMATION_MOVE_FRAME_COUNT = 8
FORMATION_WALK_PATTERN_FRAME_COUNT = FPS // DA2_REFERENCE_FPS
COMMAND_GUIDE_DELAY_FRAME_COUNT = 15 * FPS // DA2_REFERENCE_FPS
FORMATION_SPRITE_STEP_X = 16
PARTY_SPRITE_WIDTH = 16
NEAR_DEATH_SPRITE_SOURCE_X = 16 * 5
DEFEND_SPRITE_SOURCE_X = 16 * 6
DEAD_SPRITE_SOURCE_X = 16 * 8
DEAD_SPRITE_WIDTH = 24
ACTION_MOVE_DISTANCE = 16
DA2_ACTION_MOVE_SPEED = 4
ACTION_MOVE_SPEED = DA2_ACTION_MOVE_SPEED * DA2_REFERENCE_FPS // FPS
BATTLE_POPUP_FRAME_COUNT = 30 * FPS // DA2_REFERENCE_FPS
SPELL_CAST_SPRITE_SOURCE_X = DEFEND_SPRITE_SOURCE_X
ATTACK_POSE_RAISE_FRAME_COUNT = 3
ATTACK_POSE_SWING_FRAME_COUNT = 8
ATTACK_MOTION_FRAME_COUNT = (
    ATTACK_POSE_RAISE_FRAME_COUNT + ATTACK_POSE_SWING_FRAME_COUNT
)
ATTACK_HIT_PATTERN_COUNT = 3
ATTACK_HIT_PATTERN_FRAME_COUNT = 5
ATTACK_HIT_FRAME_COUNT = ATTACK_HIT_PATTERN_COUNT * ATTACK_HIT_PATTERN_FRAME_COUNT
ATTACK_HIT_START_FRAME = ATTACK_POSE_RAISE_FRAME_COUNT
ATTACK_DAMAGE_FRAME_COUNT = DAMAGE_POPUP_FRAME_COUNT
ATTACK_RETURN_JUMP_FRAME_COUNT = 8
ATTACK_RETURN_JUMP_HEIGHT = 8
ATTACK_LANDING_GUARD_FRAME_COUNT = 6
ATTACK_WEAPON_SPRITE_Y = 32
ATTACK_WEAPON_SPRITE_SIZE = 16
ATTACK_EFFECT_CELL_SIZE = 64
ATTACK_EFFECT_IMAGE_ID = "effects/weapons"
ATTACK_EFFECT_ROW_BY_SUBTYPE = {
    "AXE": 0,
    "SWORD": 1,
    "KATANA": 1,
    "KNIFE": 2,
    "HAMMER": 3,
    "WAND": 3,
    "ROD": 3,
    "SPEAR": 4,
}
ATTACK_SE_ID_BY_SUBTYPE = {
    "AXE": ATTACK_SLASH_SE_ID,
    "SWORD": ATTACK_SLASH_SE_ID,
    "KATANA": ATTACK_SLASH_SE_ID,
    "KNIFE": ATTACK_SLASH_SE_ID,
    "HAMMER": ATTACK_BLUNT_SE_ID,
    "WAND": ATTACK_BLUNT_SE_ID,
    "ROD": ATTACK_BLUNT_SE_ID,
    "SPEAR": ATTACK_SLASH_SE_ID,
}
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
FORMATION_COMMAND_TEXT_KEYS = {
    True: "battle.command.retreat",
    False: "battle.command.advance",
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
GLOBAL_COMMAND_TEXT_X = 4
GLOBAL_COMMAND_CURSOR_X = 2
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


class BattleDataError(ValueError):
    """Raised when generated battle data cannot form a scene."""


class BattlePhase(StrEnum):
    """Interactive phases implemented by the battle scene."""

    ENTRANCE = "entrance"
    INITIAL = "initial"
    COMMAND = "command"
    GLOBAL_COMMAND = "global_command"
    ITEM = "item"
    SPELL = "spell"
    TARGET = "target"
    ACTION_TARGET = "action_target"
    ATTACK_PRESENTATION = "attack_presentation"
    ACTION_PRESENTATION = "action_presentation"
    ACTION_RETURN = "action_return"
    ESCAPE_CONFIRMATION = "escape_confirmation"
    ESCAPE_MESSAGE = "escape_message"
    ESCAPE = "escape"
    FORMATION = "formation"
    MONSTER_DEATH = "monster_death"
    DEFEAT_MESSAGE = "defeat_message"
    TIMELINE = "timeline"
    MONSTER_ACTION = "monster_action"


class BattleResult(StrEnum):
    """Terminal result reported to the future scene-transition owner."""

    ESCAPED = "escaped"
    VICTORY = "victory"
    DEFEAT = "defeat"


class BattleGlobalCommand(StrEnum):
    """Commands that apply to the whole party rather than one member."""

    FIGHT = "fight"
    ESCAPE = "escape"
    AUTO = "auto"


class TimelineAnimationPhase(StrEnum):
    """Movement stages between battle turns."""

    DROP = "drop"
    SLIDE = "slide"
    INTERRUPT = "interrupt"


@dataclass(frozen=True)
class BattleTargetSpellEffect:
    """Bind one effect timeline to the battle target it decorates."""

    target_side: str
    target_index: int
    player: SpellEffectPlayer


@dataclass
class BattleActionPresentation:
    """Own the visual layers that must finish before a turn advances.

    Spell sprites share one elapsed frame. Timed popups are updated separately
    because their lifetime must not delay the action or the following phase.
    """

    spell_effects: tuple[BattleTargetSpellEffect, ...]
    elapsed_frame: int = 0

    @property
    def is_complete(self) -> bool:
        return all(effect.player.completed for effect in self.spell_effects)

    def update(self) -> None:
        self.elapsed_frame += 1
        for effect in self.spell_effects:
            effect.player.update()


@dataclass
class BattleAttackPresentation:
    """Own one party member's DA2-timed weapon attack result."""

    target_index: int
    damage: int
    poses: tuple[AttackPoseDefinition, ...]
    effect_row: int | None
    is_hit: bool = True
    sound_effect_id: str = ATTACK_SLASH_SE_ID
    elapsed_frame: int = 0
    damage_applied: bool = False
    return_started: bool = False

    @property
    def pose(self) -> AttackPoseDefinition | None:
        if not self.poses or self.elapsed_frame >= ATTACK_MOTION_FRAME_COUNT:
            return None
        if len(self.poses) == 1 or self.elapsed_frame < ATTACK_POSE_RAISE_FRAME_COUNT:
            return self.poses[0]
        return self.poses[1]

    @property
    def hit_elapsed_frame(self) -> int:
        return self.elapsed_frame - ATTACK_HIT_START_FRAME

    @property
    def damage_popup_elapsed_frame(self) -> int:
        delay = ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT if self.is_hit else 0
        return self.hit_elapsed_frame - delay

    @property
    def result_complete(self) -> bool:
        frame_count = (
            ATTACK_DAMAGE_FRAME_COUNT if self.is_hit else MONSTER_MISS_FRAME_COUNT
        )
        return self.damage_popup_elapsed_frame >= frame_count


@dataclass
class BattleTimedPopup:
    """A non-blocking battle popup whose timer survives phase changes."""

    frames_remaining: int = 0

    @property
    def visible(self) -> bool:
        return self.frames_remaining > 0

    def show(self, frame_count: int) -> None:
        if isinstance(frame_count, bool) or not isinstance(frame_count, int):
            raise TypeError("popup frame_count must be an integer")
        if frame_count <= 0:
            raise ValueError("popup frame_count must be positive")
        self.frames_remaining = frame_count

    def update(self) -> None:
        self.frames_remaining = max(0, self.frames_remaining - 1)

    def clear(self) -> None:
        self.frames_remaining = 0


def _required_text(record: Mapping[str, object], field: str, label: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise BattleDataError(f"{label}.{field} must be a non-empty string")
    return value


def _required_nonnegative_integer(
    record: Mapping[str, object],
    field: str,
    label: str,
) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BattleDataError(f"{label}.{field} must be a non-negative integer")
    return value


def _required_positive_integer(
    record: Mapping[str, object],
    field: str,
    label: str,
) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BattleDataError(f"{label}.{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class BattleCharacter:
    """One member plus immutable battle display values."""

    member: Member
    icon_x: int
    icon_y: int
    battle_sprite: int

    @classmethod
    def from_record(
        cls,
        member: Member,
        record: Mapping[str, object],
    ) -> BattleCharacter:
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

    @property
    def agility(self) -> int:
        """Return the member's current equipment-adjusted agility."""

        return self.member.adjusted_abilities.agility


@dataclass
class BattleMonster:
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
    agility: int
    combat_stats: MonsterCombatStats = field(
        default_factory=lambda: MonsterCombatStats(0, 0, 0, 0)
    )
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
    ) -> BattleMonster:
        if not isinstance(is_front_row, bool):
            raise TypeError("monster formation row must be a boolean")
        key = _required_text(record, "name_en", "monster")
        image_id = record.get("image_id")
        if isinstance(image_id, bool) or not isinstance(image_id, (str, int)):
            raise BattleDataError(f"{key}.image_id must be a string or integer")
        image_id_text = str(image_id)
        if not image_id_text:
            raise BattleDataError(f"{key}.image_id must not be empty")
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
            combat_stats=MonsterCombatStats.from_record(record),
            agility=_required_nonnegative_integer(record, "agi", key),
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
            raise BattleDataError(f"{label} key is duplicated: {key}")
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
        raise BattleDataError(f"{label} is missing: {key}") from error


@dataclass(frozen=True)
class BattleEncounter:
    """Immutable monster lineup supplied by an encounter source or test fixture."""

    monster_keys: tuple[str, ...]
    front_monster_indexes: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        if not 1 <= len(self.monster_keys) <= len(MONSTER_POSITIONS):
            raise ValueError(
                f"battle encounter must contain 1 to {len(MONSTER_POSITIONS)} monsters"
            )
        if not all(isinstance(key, str) and key for key in self.monster_keys):
            raise TypeError("battle encounter monster keys must be non-empty strings")
        if not all(
            isinstance(index, int)
            and not isinstance(index, bool)
            and 0 <= index < len(self.monster_keys)
            for index in self.front_monster_indexes
        ):
            raise ValueError("front monster indexes must refer to encounter monsters")


class BattleScene:
    """Own one battle's input, temporary state, update order, and rendering."""

    @classmethod
    def create(
        cls,
        *,
        settings: Settings,
        palette_shifter,
        bgm: BgmPlayer,
        resources: ImageResources,
        fonts: FontResources,
        texts: TextCatalog,
        item_catalog: Mapping[str, Item],
        spells: Mapping[str, Spell],
        inventory_system: InventorySystem,
        character_records: tuple[dict[str, object], ...],
        party: tuple[Member, ...],
        encounter: BattleEncounter,
    ) -> BattleScene:
        """Build a production scene from one game session and encounter."""

        windows = WindowFactory(fonts.font_for(settings.language))
        return cls(
            settings=settings,
            palette_shifter=palette_shifter,
            bgm=bgm,
            resources=resources,
            windows=windows,
            font_6x8=fonts.font_for(Language.ENGLISH),
            texts=texts,
            item_catalog=item_catalog,
            spells=spells,
            inventory_system=inventory_system,
            character_records=character_records,
            party=party,
            monster_records=tuple(load_record_array("monsters.json")),
            encounter=encounter,
            attack_poses=load_attack_poses(
                APP_ROOT / "effects" / "attack_poses.json"
            ),
            spell_effect_renderer=SpellEffectRenderer(
                resources,
                palette_shifter,
            ),
            spell_effects=load_spell_effects(
                APP_ROOT / "effects" / "spells.json"
            ),
        )

    def __init__(
        self,
        *,
        settings: Settings,
        palette_shifter,
        bgm: BgmPlayer,
        resources: ImageResources,
        windows: WindowFactory,
        font_6x8,
        texts: TextCatalog,
        item_catalog: Mapping[str, Item],
        spells: Mapping[str, Spell],
        inventory_system: InventorySystem,
        character_records: tuple[dict[str, object], ...],
        party: tuple[Member, ...],
        monster_records: tuple[dict[str, object], ...],
        encounter: BattleEncounter,
        attack_poses: Mapping[str, AttackPoseDefinition],
        spell_effect_renderer: SpellEffectRenderer,
        spell_effects: Mapping[str, object],
        restart_enabled: bool = False,
        reset_party_on_restart: bool = False,
        reset_inventory_on_restart: bool = False,
    ) -> None:
        if not isinstance(settings, Settings):
            raise TypeError("settings must be Settings")
        if not isinstance(encounter, BattleEncounter):
            raise TypeError("encounter must be a BattleEncounter")
        if not party or not all(isinstance(member, Member) for member in party):
            raise TypeError("party must contain at least one Member")
        if len(party) > len(PARTY_SPRITE_Y):
            raise ValueError(
                f"current battle layout supports at most {len(PARTY_SPRITE_Y)} members"
            )
        if not isinstance(restart_enabled, bool):
            raise TypeError("restart_enabled must be a boolean")
        if not isinstance(reset_party_on_restart, bool):
            raise TypeError("reset_party_on_restart must be a boolean")
        if not isinstance(reset_inventory_on_restart, bool):
            raise TypeError("reset_inventory_on_restart must be a boolean")

        self.restart_enabled = restart_enabled
        self.reset_party_on_restart = reset_party_on_restart
        self.reset_inventory_on_restart = reset_inventory_on_restart
        self.settings = settings
        self.palette_shifter = palette_shifter
        self.palette_shifter.define_mix(
            UNSELECTABLE_TARGET_PALETTE,
            base_rate=UNSELECTABLE_TARGET_PALETTE_BASE_RATE,
            target_color=self.palette_shifter.base_colors[DISABLED_COLOR],
        )
        self.bgm = bgm

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
        self.attack_effect_image = resources.image(ATTACK_EFFECT_IMAGE_ID)
        self.attack_poses = attack_poses
        self.spell_effect_renderer = spell_effect_renderer
        self.spell_effects = spell_effects
        self.localizer = Localizer(settings.language)
        self.texts = texts
        self.spells = dict(spells)
        self.item_catalog = dict(item_catalog)
        self.inventory_system = inventory_system
        character_records = _records_by_key(
            character_records,
            label="character",
        )
        self.party = party
        self.party_entrance_complete_frame = (
            PARTY_ENTRANCE_FRAME_COUNT
            + (len(party) - 1) * PARTY_ENTRANCE_STAGGER_FRAME_COUNT
        )
        self.party_visuals = tuple(
            BattleCharacter.from_record(
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
            monster_records,
            label="monster",
        )
        self.monsters = tuple(
            BattleMonster.from_record(
                _record_for_key(monsters_by_key, key, label="monster"),
                is_front_row=index in encounter.front_monster_indexes,
            )
            for index, key in enumerate(encounter.monster_keys)
        )
        self.monster_images = {
            monster.key: resources.image(monster.image_resource_id)
            for monster in self.monsters
        }
        self._timeline_order: TimelineOrder[BattleCharacter | BattleMonster] = (
            TimelineOrder(())
        )
        self.timeline: tuple[BattleCharacter | BattleMonster, ...] = ()
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
        global_command_window = windows.create(
            *GLOBAL_COMMAND_WINDOW_GRID,
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
        self.global_command_window = global_command_window
        self.input_guide_window = windows.create(
            *INPUT_GUIDE_WINDOW_GRID,
            (),
            transparent=True,
        )
        self.item_guide_window = item_guide_window
        self.item_window = item_window
        self.spell_window = spell_window
        self.spell_guide_window = spell_guide_window
        self.spell_mp_window = spell_mp_window
        self.command_cursor = command_window.set_cursor(())
        self.global_command_cursor: WindowCursor | None = None
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
        self.party_target_window = windows.create(0, 0, 64, 60, transparent=True)
        self.party_target_cursor: WindowCursor | None = None
        self.all_target_cursors: tuple[WindowCursor, ...] = ()
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
        self.battle_popup_window = windows.create(
            *ESCAPE_MESSAGE_WINDOW_GRID,
            (),
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
        self.phase = BattlePhase.INITIAL
        self.result: BattleResult | None = None
        self.active_party_index: int | None = 0
        self.active_party_pulse_frame = 0
        self.blinking_monster_index: int | None = None
        self.monster_blink_frames_remaining = 0
        self.monster_attack_target_index: int | None = None
        self.monster_attack_damage: int | None = None
        self.monster_attack_animation_frame = 0
        self.timeline_animation_phase: TimelineAnimationPhase | None = None
        self.timeline_animation_frame = 0
        self.timeline_advance: (
            TimelineAdvance[BattleCharacter | BattleMonster] | None
        ) = None
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
        self.escape_return_phase = BattlePhase.COMMAND
        self.auto_battle_active = False
        self.input_device = InputDevice.KEYBOARD
        self.selectable_target_indexes: tuple[int, ...] = ()
        self.selected_target_index: int | None = None
        self.selectable_party_target_indexes: tuple[int, ...] = ()
        self.selected_party_target_index: int | None = None
        self.action_targets_enemy = False
        self.action_targets_all = False
        self.pending_item_candidate: BattleItemCandidate | None = None
        self.pending_spell: Spell | None = None
        self.action_presentation: BattleActionPresentation | None = None
        self.attack_presentation: BattleAttackPresentation | None = None
        self.battle_popup = BattleTimedPopup()
        self.action_party_index: int | None = None
        self.action_offset_x = 0
        self.action_motion_frame = 0
        self.action_returning = False
        self.action_uses_cast_pose = False
        self.action_return_jump = False
        self.action_return_frame = 0
        self.action_return_start_offset = 0
        self.action_landing_guard_frames_remaining = 0
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
        self.last_command_by_party_index: dict[int, BattleCommand] = {}
        self.last_spell_key_by_party_index: dict[int, str] = {}
        self.last_item_selection_by_party_index: dict[
            int, tuple[str, EquipmentSlot | None]
        ] = {}
        self.defending_party_indexes: set[int] = set()
        self.escaping_party_indexes: set[int] = set()
        self.windows = [
            command_guide_window,
            command_window,
            global_command_window,
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
                ascii_to_fullwidth(f"{member.hp:3d}/{member.max_hp:3d}"),
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

        self._restart_battle()

    def update(self, input_state: InputState) -> None:
        """Advance the battle by one frame from an immutable input snapshot."""

        if not isinstance(input_state, InputState):
            raise TypeError("input_state must be an InputState")
        self.input_device = input_state.device
        self._refresh_input_guide()
        if getattr(self, "result", None) is not None:
            return
        if getattr(self, "restart_enabled", True) and input_state.menu.triggered:
            self._restart_battle()
            return
        battle_popup = getattr(self, "battle_popup", None)
        if battle_popup is not None:
            battle_popup.update()
        if hasattr(self, "active_party_pulse_frame"):
            self._update_active_party_pulse()
        self._update_action_motion()
        if self.phase is BattlePhase.ACTION_RETURN:
            if self.action_party_index is None:
                self._complete_current_turn()
            return
        if self.phase not in (BattlePhase.COMMAND, BattlePhase.ITEM):
            self._hide_command_guide()
        if self.phase is BattlePhase.ENTRANCE:
            self._update_entrance_animation()
            return
        if self.phase is BattlePhase.DEFEAT_MESSAGE:
            self._update_defeat_message(input_state)
            return
        if getattr(self, "auto_battle_active", False) and input_state.cancel.triggered:
            self._cancel_auto_battle()
            return
        if self.phase is BattlePhase.MONSTER_ACTION:
            self._update_monster_action()
            return
        if self.phase is BattlePhase.ESCAPE_CONFIRMATION:
            self._update_escape_confirmation(input_state)
            return
        if self.phase is BattlePhase.ESCAPE_MESSAGE:
            self._update_escape_message(input_state)
            return
        if self.phase is BattlePhase.ESCAPE:
            self._update_escape_animation()
            return
        if self.phase is BattlePhase.FORMATION:
            self._update_formation_animation()
            return
        if self.phase is BattlePhase.MONSTER_DEATH:
            self._update_monster_death_animation()
            return
        if self.phase is BattlePhase.TIMELINE:
            self._update_timeline_animation()
            return
        if self.phase is BattlePhase.TARGET:
            self._update_target_selection(input_state)
            return
        if self.phase is BattlePhase.ACTION_TARGET:
            self._update_action_target_selection(input_state)
            return
        if self.phase is BattlePhase.ACTION_PRESENTATION:
            self._update_action_presentation()
            return
        if self.phase is BattlePhase.ATTACK_PRESENTATION:
            self._update_attack_presentation()
            return
        if self.phase is BattlePhase.ITEM:
            self._update_item_selection(input_state)
            return
        if self.phase is BattlePhase.SPELL:
            self._update_spell_selection(input_state)
            return
        if self.phase is BattlePhase.GLOBAL_COMMAND:
            self._update_global_command_selection(input_state)
            return

        if input_state.cancel.triggered:
            self._open_global_command_menu()
            return

        if input_state.confirm.triggered:
            if self.command_window.is_closed:
                self.phase = BattlePhase.COMMAND
                self.command_cursor.active = True
                self.command_window.open()
            elif self.command_window.is_open:
                command = self.command_cursor.selected_key
                if isinstance(command, BattleCommand):
                    self._remember_active_command(command)
                if command == BattleCommand.ATTACK:
                    self._begin_attack_target_selection()
                elif command == BattleCommand.SPELL:
                    self._begin_spell_selection()
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
            input_state.navigation if self.phase is BattlePhase.COMMAND else None
        )
        self.command_window.update(navigation)
        self._update_command_guide()

    def _update_global_command_selection(self, input_state: InputState) -> None:
        """Choose a party-wide action or return to the current member's menu."""

        if input_state.cancel.triggered:
            self._open_member_command_menu()
            return
        if input_state.confirm.triggered and self.global_command_window.is_open:
            command = self.global_command_cursor
            if command is None:
                return
            if command.selected_key is BattleGlobalCommand.FIGHT:
                self._open_member_command_menu()
                return
            if command.selected_key is BattleGlobalCommand.ESCAPE:
                self._begin_escape_confirmation()
                return
            if command.selected_key is BattleGlobalCommand.AUTO:
                self._begin_auto_battle()
                return
        self.global_command_window.update(input_state.navigation)

    def _restart_battle(self) -> None:
        """Initialize or explicitly restart this scene and replay its entrance."""

        self._release_transient_action_palettes()
        self._restart_battle_bgm()
        if self.reset_inventory_on_restart:
            self.inventory_system = InventorySystem.with_one_each(self.item_catalog)
        if self.reset_party_on_restart:
            for member in self.party:
                member.fully_recover()
        self._prepare_party_for_restart()
        for monster in self.monsters:
            monster.restore()
        living_party = tuple(
            visual
            for visual in self.party_visuals
            if visual.member.is_alive
        )
        self._timeline_order = initialize_timeline_order(
            tuple(
                (entry, entry.agility)
                for entry in (*living_party, *self.monsters)
            )
        )
        self.timeline = self._timeline_order.actors
        self.phase = BattlePhase.ENTRANCE
        self.result = None
        self.active_party_index = None
        self.active_party_pulse_frame = 0
        self._sync_active_party_pulse_palette()
        self.blinking_monster_index = None
        self.monster_blink_frames_remaining = 0
        self.monster_attack_target_index = None
        self.monster_attack_damage = None
        self.monster_attack_animation_frame = 0
        self.timeline_animation_phase = None
        self.timeline_animation_frame = 0
        self.timeline_advance = None
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
        self.escape_return_phase = BattlePhase.COMMAND
        self.auto_battle_active = False
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
        self.last_command_by_party_index.clear()
        self.last_spell_key_by_party_index.clear()
        self.last_item_selection_by_party_index.clear()
        self.selectable_party_target_indexes = ()
        self.selected_party_target_index = None
        self.action_targets_enemy = False
        self.action_targets_all = False
        self.pending_item_candidate = None
        self.pending_spell = None
        self.action_presentation = None
        self.attack_presentation = None
        battle_popup = getattr(self, "battle_popup", None)
        if battle_popup is not None:
            battle_popup.clear()
        self._clear_action_motion_state()
        self.party_target_cursor = None
        self.all_target_cursors = ()
        self._hide_command_guide()
        self.item_guide_window.close_immediately()
        self.item_guide_window.clear_texts()
        self._close_spell_windows()
        self.defending_party_indexes.clear()
        self.escaping_party_indexes.clear()
        self.target_cursor.active = False
        self.escape_cursor.active = False
        self.command_window.close_immediately()
        global_command_window = getattr(self, "global_command_window", None)
        if global_command_window is not None:
            global_command_window.close_immediately()
        self.item_window.close_immediately()
        self._refresh_command_options()
        self.command_cursor.active = False
        self._refresh_party_text_colors()
        self._refresh_all_party_hp_texts()
        self._refresh_monster_name_colors()
        self.entrance_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.entrance_fade.start_fade_in()
        self.palette_shifter.set_global_mix(
            base_rate=0.0,
            target_color=self.palette_shifter.base_colors[0],
        )

    def _prepare_party_for_restart(self) -> None:
        """Allow a composition root to apply fixture state before gauge rolls."""

    def _restart_battle_bgm(self) -> None:
        """Restart the battle track from its beginning for this scene."""

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
            self._activate_timeline_head()

    def _open_global_command_menu(self) -> None:
        """Replace the active member's command list with party-wide commands."""

        self.phase = BattlePhase.GLOBAL_COMMAND
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
        self.global_command_window.close_immediately()
        item_window = getattr(self, "item_window", None)
        if item_window is not None:
            item_window.close_immediately()
        item_guide_window = getattr(self, "item_guide_window", None)
        if item_guide_window is not None:
            item_guide_window.close_immediately()
            item_guide_window.clear_texts()
        self._close_spell_windows()
        self._hide_command_guide()
        self._refresh_global_command_options()
        if self.global_command_cursor is not None:
            self.global_command_cursor.active = True
        self.global_command_window.open()
        self._refresh_monster_name_colors()
        self._refresh_input_guide()

    def _open_member_command_menu(self) -> None:
        """Open the current member's command list from a party-wide choice."""

        self.phase = BattlePhase.COMMAND
        if self.global_command_cursor is not None:
            self.global_command_cursor.active = False
        self.global_command_window.close_immediately()
        self.command_window.close_immediately()
        self._hide_command_guide()
        self._refresh_command_options()
        self.command_cursor.active = True
        self._select_initial_member_command()
        self.command_window.open()
        self._refresh_input_guide()

    def _refresh_global_command_options(self) -> None:
        self.global_command_window.vertical_navigation = False
        self.global_command_window.set_vertical_navigation_pressed()
        self.global_command_window.clear_texts()
        self.global_command_window.clear_cursor()
        commands = (
            BattleGlobalCommand.FIGHT,
            BattleGlobalCommand.ESCAPE,
            BattleGlobalCommand.AUTO,
        )
        for row_index, command in enumerate(commands):
            self.global_command_window.add_text(
                self.texts.text(
                    f"battle.command.{command.value}",
                    self.localizer,
                ),
                GLOBAL_COMMAND_TEXT_X,
                COMMAND_ROW_Y[row_index],
            )
        self.global_command_cursor = self.global_command_window.set_cursor(
            tuple(
                CursorTarget(
                    GLOBAL_COMMAND_CURSOR_X,
                    COMMAND_ROW_Y[row_index],
                    key=command,
                )
                for row_index, command in enumerate(commands)
            )
        )

    def _begin_auto_battle(self) -> None:
        """Start automatic normal attacks and defensive fallbacks."""

        self.auto_battle_active = True
        if self.global_command_cursor is not None:
            self.global_command_cursor.active = False
        self.global_command_window.close_immediately()
        self._begin_auto_action()
        self._refresh_input_guide()

    def _begin_auto_action(self) -> None:
        """Choose the active member's automatic action for this turn."""

        if self._active_member_attack_targets():
            self._begin_attack_target_selection()
            return
        self._begin_defense()

    def _cancel_auto_battle(self) -> None:
        """Leave auto mode without cancelling an already-running animation."""

        self.auto_battle_active = False
        if self.phase is BattlePhase.TARGET:
            self.selected_command = None
            self.selectable_target_indexes = ()
            self.selected_target_index = None
            self.target_cursor.active = False
            self._begin_action_return()
            self._open_member_command_menu()
        self._refresh_input_guide()

    def _begin_escape_confirmation(self) -> None:
        self.escape_return_phase = self.phase
        self.phase = BattlePhase.ESCAPE_CONFIRMATION
        self.selected_command = "escape"
        self.command_cursor.active = False
        self.command_window.close_immediately()
        global_command_window = getattr(self, "global_command_window", None)
        if global_command_window is not None:
            global_command_window.close_immediately()
        self.escape_cursor.select_key("yes")
        self.escape_cursor.active = True

    def _update_escape_confirmation(self, input_state: InputState) -> None:
        if input_state.cancel.triggered:
            self._cancel_escape_confirmation()
            return
        global_command_window = getattr(self, "global_command_window", None)
        if not self.command_window.is_closed or (
            global_command_window is not None and not global_command_window.is_closed
        ):
            self.command_window.update(None)
            if global_command_window is not None:
                global_command_window.update(None)
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
        return all(
            party_index in self.escaping_party_indexes
            or self._party_member_is_dead(party_index)
            for party_index in range(len(self.party_visuals))
        )

    def _begin_escape_animation(self) -> None:
        """Show the success message and start the DA2-style party run."""

        self.phase = BattlePhase.ESCAPE_MESSAGE
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
            self.phase = BattlePhase.ESCAPE
            self.escape_fade.start()

    def _update_escape_animation(self) -> None:
        """Fade out after acknowledgement and finish once fully covered."""

        self._update_escape_fade()
        self._advance_escape_run()
        if self.escape_fade_covered and all(
            self._party_member_is_dead(index)
            or self._escape_party_x(index) >= ESCAPE_RUN_DESTINATION_X
            for index in range(len(self.party_visuals))
        ):
            self.result = BattleResult.ESCAPED

    def _advance_escape_run(self) -> None:
        """Advance the shared party run by one frame."""

        self.escape_animation_frame += 1

    def _update_escape_fade(self) -> None:
        """Fade to black once and hold the covered frame for the scene owner."""

        if self.escape_fade_covered:
            return
        event = self.escape_fade.update()
        self.palette_shifter.set_global_mix(
            base_rate=self.escape_fade.visible_rate,
            target_color=self.palette_shifter.base_colors[0],
        )
        if event is FadeEvent.COVERED:
            self.escape_fade_covered = True

    def _begin_defeat_message(self) -> None:
        """Stop battle input and show DA2's persistent party-defeat message."""

        self.phase = BattlePhase.DEFEAT_MESSAGE
        self.active_party_index = None
        self.blinking_monster_index = None
        self.monster_blink_frames_remaining = 0
        self.timeline_animation_phase = None
        self.timeline_animation_frame = 0
        self.timeline_advance = None
        self.auto_battle_active = False
        self.command_cursor.active = False
        self.command_window.close_immediately()
        global_command_window = getattr(self, "global_command_window", None)
        if global_command_window is not None:
            global_command_window.close_immediately()
        self.target_cursor.active = False
        self.escape_cursor.active = False
        self.item_window.close_immediately()
        self._close_spell_windows()
        self._hide_command_guide()
        self.battle_popup.clear()
        self.battle_popup_window.clear_texts()
        self.battle_popup_window.add_text(
            self.texts.text("battle.defeat", self.localizer),
            *ESCAPE_MESSAGE_TEXT_POSITION,
        )
        self._refresh_party_text_colors()

    def _update_defeat_message(self, input_state: InputState) -> None:
        """Wait for DA2-style acknowledgement before reporting defeat."""

        if input_state.confirm.triggered or input_state.cancel.triggered:
            self._complete_defeat()

    def _complete_defeat(self) -> None:
        """Report defeat to the future battle-transition owner."""

        self.result = BattleResult.DEFEAT

    def _cancel_escape_confirmation(self) -> None:
        self.selected_command = None
        self.escape_cursor.active = False
        if (
            getattr(self, "escape_return_phase", BattlePhase.COMMAND)
            is BattlePhase.GLOBAL_COMMAND
        ):
            self._open_global_command_menu()
            return
        self._open_member_command_menu()

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
        self.phase = BattlePhase.FORMATION
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

    def _remember_active_item(self, candidate: BattleItemCandidate) -> None:
        """Keep one member's last confirmed item by stable item and slot keys."""

        if self.active_party_index is None:
            return
        selections = getattr(self, "last_item_selection_by_party_index", None)
        if selections is None:
            selections = {}
            self.last_item_selection_by_party_index = selections
        selections[self.active_party_index] = (
            candidate.item.key,
            candidate.equipment_slot,
        )

    def _remembered_item_index(
        self,
        candidates: tuple[BattleItemCandidate, ...],
    ) -> int | None:
        """Find the active member's last item when it remains usable."""

        if self.active_party_index is None:
            return None
        selection = getattr(self, "last_item_selection_by_party_index", {}).get(
            self.active_party_index
        )
        if selection is None:
            return None
        return next(
            (
                index
                for index, candidate in enumerate(candidates)
                if (candidate.item.key, candidate.equipment_slot) == selection
            ),
            None,
        )

    def _begin_item_selection(self) -> bool:
        """Replace the command contents with the current actor's item list."""

        candidates = self._active_member_item_candidates()
        if not candidates:
            return False
        self.phase = BattlePhase.ITEM
        self.selected_command = BattleCommand.ITEM
        self._begin_action_motion(use_cast_pose=False)
        self.item_candidates = candidates
        remembered_index = self._remembered_item_index(candidates)
        self.selected_item_index = 0 if remembered_index is None else remembered_index
        self.item_scroll_offset = min(
            self.selected_item_index,
            max(0, len(candidates) - ITEM_VISIBLE_COUNT),
        )
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
        self.phase = BattlePhase.COMMAND
        self.selected_command = None
        self.item_candidates = ()
        self.selected_item_index = 0
        self.item_scroll_offset = 0
        self.item_cursor = None
        self._begin_action_return()
        self.item_window.close_immediately()
        self.item_guide_window.close_immediately()
        self.item_guide_window.clear_texts()
        self._refresh_command_options()
        self.command_cursor.active = True
        self.command_cursor.select_key(BattleCommand.ITEM)
        self.command_window.open_immediately()

    def _use_selected_item(self) -> bool:
        """Begin target selection for the selected item's use effect."""

        candidate = self.selected_item_candidate
        if candidate is None or self.active_party_index is None:
            return False
        item = candidate.item
        if not self._item_is_usable_in_battle(item):
            return False
        spell = self.spells.get(item.use_spell_key)
        if spell is None:
            return False
        started = self._begin_action_target_selection(
            spell,
            item_candidate=candidate,
        )
        if started:
            self._remember_active_item(candidate)
        return started

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
        self.phase = BattlePhase.SPELL
        self.selected_command = BattleCommand.SPELL
        self._begin_action_motion(use_cast_pose=True)
        self.spell_candidates = candidates
        self.spell_scroll_offset = 0
        member = self.party[self.active_party_index]
        remembered_key = getattr(self, "last_spell_key_by_party_index", {}).get(
            self.active_party_index
        )
        remembered_spell = next(
            (spell for spell in candidates if spell.key == remembered_key),
            None,
        )
        if remembered_spell is not None and member.mp >= remembered_spell.mp:
            self.spell_type = remembered_spell.type
            self._ensure_selected_spell_is_visible(remembered_spell)
        else:
            remembered_key = None
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
        self._refresh_spell_options(preferred_key=remembered_key)
        return True

    def _refresh_spell_options(self, *, preferred_key: str | None = None) -> None:
        """Populate the active school in the four-row battle spell list."""

        active_index = getattr(self, "active_party_index", None)
        if active_index is None:
            return
        member = self.party[self.active_party_index]
        cursor = getattr(self, "spell_cursor", None)
        selected_key = preferred_key or (
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
        self.phase = BattlePhase.COMMAND
        self.selected_command = None
        self.spell_candidates = ()
        self.spell_scroll_offset = 0
        self.spell_type = SpellType.MYSTIC
        self.spell_cursor = None
        self._begin_action_return()
        self._close_spell_windows()
        self._refresh_command_options()
        self.command_cursor.active = True
        self.command_cursor.select_key(BattleCommand.SPELL)
        self.command_window.open_immediately()

    def _use_selected_spell(self) -> bool:
        """Begin target selection for the selected spell."""

        if self.active_party_index is None:
            return False
        spell = self.selected_spell
        member = self.party[self.active_party_index]
        if spell is None or member.mp < spell.mp:
            return False
        started = self._begin_action_target_selection(spell)
        if started:
            selections = getattr(self, "last_spell_key_by_party_index", None)
            if selections is None:
                selections = {}
                self.last_spell_key_by_party_index = selections
            selections[self.active_party_index] = spell.key
        return started

    def _begin_action_target_selection(
        self,
        spell: Spell,
        *,
        item_candidate: BattleItemCandidate | None = None,
    ) -> bool:
        """Select the targets specified by an item effect or a spell record."""

        if spell.to_enemy:
            selectable = tuple(
                index for index, monster in enumerate(self.monsters) if monster.is_alive
            )
            if not selectable:
                return False
            self.selectable_target_indexes = selectable
            self.selected_target_index = None if spell.to_all else selectable[-1]
            self.selectable_party_target_indexes = ()
            self.selected_party_target_index = None
            self.target_cursor.active = not spell.to_all
            if self.selected_target_index is not None:
                self.target_cursor.select_key(self.selected_target_index)
            target_positions = tuple(
                target
                for target in self.target_cursor.targets
                if target.key in selectable
            )
            self.party_target_cursor = None
            self.all_target_cursors = self._make_all_target_cursors(
                self.target_window,
                target_positions,
            )
        else:
            selectable = tuple(
                index for index, member in enumerate(self.party) if member.hp > 0
            )
            if not selectable:
                return False
            party_targets = tuple(
                CursorTarget(
                    (self._party_sprite_x(index) - 8) // 4,
                    (PARTY_SPRITE_Y[index] + 8) // 4,
                    key=index,
                )
                for index in selectable
            )
            self.selectable_target_indexes = ()
            self.selected_target_index = None
            self.selectable_party_target_indexes = selectable
            self.selected_party_target_index = None if spell.to_all else selectable[0]
            self.target_cursor.active = False
            self.party_target_cursor = WindowCursor(
                self.party_target_window,
                party_targets,
                active=not spell.to_all,
            )
            if self.selected_party_target_index is not None:
                self.party_target_cursor.select_key(self.selected_party_target_index)
            self.all_target_cursors = self._make_all_target_cursors(
                self.party_target_window,
                party_targets,
            )

        self.pending_item_candidate = item_candidate
        self.pending_spell = spell if item_candidate is None else None
        self.action_targets_enemy = spell.to_enemy
        self.action_targets_all = spell.to_all
        self.selected_command = (
            BattleCommand.ITEM if item_candidate is not None else BattleCommand.SPELL
        )
        self.phase = BattlePhase.ACTION_TARGET
        self.item_window.close_immediately()
        self.item_guide_window.close_immediately()
        self._close_spell_windows()
        self._refresh_monster_name_colors()
        return True

    @staticmethod
    def _make_all_target_cursors(
        window: Window,
        targets: tuple[CursorTarget, ...],
    ) -> tuple[WindowCursor, ...]:
        """Create one independently drawable cursor for every all-target marker."""

        return tuple(WindowCursor(window, (target,)) for target in targets)

    def _update_action_target_selection(self, input_state: InputState) -> None:
        """Confirm a spell/item target, or return to its selection window."""

        if input_state.cancel.triggered:
            self._cancel_action_target_selection()
            return
        if input_state.confirm.triggered:
            self._confirm_action_target_selection()
            return
        if not self.action_targets_all:
            navigation = input_state.navigation
            if navigation is not None:
                if self.action_targets_enemy:
                    self._move_target(navigation)
                else:
                    self._move_party_target(navigation)
        self._update_action_target_cursors()

    def _update_action_target_cursors(self) -> None:
        """Advance the selected target cursor without moving it automatically."""

        if self.action_targets_all:
            for cursor in self.all_target_cursors:
                cursor.update()
            return
        if self.action_targets_enemy:
            self.target_cursor.update()
        elif self.party_target_cursor is not None:
            self.party_target_cursor.update()

    def _move_party_target(self, direction: Direction) -> bool:
        """Cycle the selectable party targets with any directional input."""

        selected = self.selected_party_target_index
        if selected is None or not self.selectable_party_target_indexes:
            return False
        distance = direction.dx or direction.dy
        if not distance:
            return False
        candidates = self.selectable_party_target_indexes
        index = (candidates.index(selected) + distance) % len(candidates)
        target = candidates[index]
        self.selected_party_target_index = target
        if self.party_target_cursor is not None:
            self.party_target_cursor.select_key(target)
        return target != selected

    def _confirm_action_target_selection(self) -> bool:
        """Pay the selected action's cost, then start its presentation."""

        item_candidate = self.pending_item_candidate
        spell = self.pending_spell
        effect_spell = spell
        if item_candidate is not None:
            if not self._commit_item_use(item_candidate):
                return False
            self._show_item_use_message(item_candidate.item)
            use_spell_key = item_candidate.item.use_spell_key
            effect_spell = (
                getattr(self, "spells", {}).get(use_spell_key)
                if use_spell_key
                else None
            )
        elif spell is not None:
            if self.active_party_index is None:
                return False
            member = self.party[self.active_party_index]
            if member.mp < spell.mp:
                return False
            member.mp -= spell.mp
            self._show_spell_cast_message(spell)
        else:
            return False
        if effect_spell is not None and self._begin_action_presentation(effect_spell):
            return True
        if getattr(self, "action_party_index", None) is not None:
            self._begin_action_return(complete_turn=True)
            return True
        self._complete_current_turn()
        return True

    def _begin_action_presentation(
        self,
        spell: Spell,
    ) -> bool:
        """Create target effect timelines while retaining room for result layers."""

        definition = getattr(self, "spell_effects", {}).get(spell.key)
        target_side = "enemy" if self.action_targets_enemy else "ally"
        if self.action_targets_enemy:
            indexes = (
                self.selectable_target_indexes
                if self.action_targets_all
                else (
                    ()
                    if self.selected_target_index is None
                    else (self.selected_target_index,)
                )
            )
        else:
            indexes = (
                self.selectable_party_target_indexes
                if self.action_targets_all
                else (
                    ()
                    if self.selected_party_target_index is None
                    else (self.selected_party_target_index,)
                )
            )
        if not indexes:
            return False

        effects: list[BattleTargetSpellEffect] = []
        if definition is not None:
            for index in indexes:
                anchor_x, anchor_y = self._spell_effect_anchor(target_side, index)
                effects.append(
                    BattleTargetSpellEffect(
                        target_side,
                        index,
                        SpellEffectPlayer(
                            definition,
                            anchor_x=anchor_x,
                            anchor_y=anchor_y,
                            target_side=target_side,
                        ),
                    )
                )
        self.action_presentation = BattleActionPresentation(tuple(effects))
        self.phase = BattlePhase.ACTION_PRESENTATION
        self.target_cursor.active = False
        if self.party_target_cursor is not None:
            self.party_target_cursor.active = False
        self.all_target_cursors = ()
        self._refresh_monster_name_colors()

        if effects:
            first_player = effects[0].player
            se_id = first_player.take_start_sound()
            for effect in effects[1:]:
                effect.player.take_start_sound()
            if se_id is not None:
                play_se(se_id)
            self.spell_effect_renderer.prepare(first_player)
        return True

    def _show_item_use_message(self, item: Item) -> None:
        """Show DA2's timed item-use announcement in the common popup."""

        if (
            self.active_party_index is None
            or getattr(self, "battle_popup_window", None) is None
            or getattr(self, "battle_popup", None) is None
        ):
            return
        actor_name = self.party_visuals[self.active_party_index].display_name(
            self.localizer
        )
        message = self.texts.formatted_text(
            "battle.item.used",
            self.localizer,
            {
                "ACTOR": actor_name,
                "ITEM": item.localized_name(self.localizer),
            },
        )
        self._show_battle_popup(message, BATTLE_POPUP_FRAME_COUNT)

    def _show_spell_cast_message(self, spell: Spell) -> None:
        """Show DA2's timed spell announcement in the top message window."""

        if (
            self.active_party_index is None
            or getattr(self, "battle_popup_window", None) is None
            or getattr(self, "battle_popup", None) is None
        ):
            return
        actor_name = self.party_visuals[self.active_party_index].display_name(
            self.localizer
        )
        message = self.texts.formatted_text(
            "battle.spell.cast",
            self.localizer,
            {
                "ACTOR": actor_name,
                "SPELL": spell.localized_name(self.localizer),
            },
        )
        self._show_battle_popup(message, BATTLE_POPUP_FRAME_COUNT)

    def _show_battle_popup(self, message: str, frame_count: int) -> None:
        """Replace the common non-blocking battle popup and restart its timer."""

        window = getattr(self, "battle_popup_window", None)
        battle_popup = getattr(self, "battle_popup", None)
        if window is None or battle_popup is None:
            return
        window.clear_texts()
        window.add_text(message, *ESCAPE_MESSAGE_TEXT_POSITION)
        battle_popup.show(frame_count)

    def _spell_effect_anchor(self, target_side: str, index: int) -> tuple[int, int]:
        """Return the center of the target's actual battle sprite rectangle."""

        if target_side == "ally":
            return self._party_sprite_x(index) + 8, PARTY_SPRITE_Y[index] + 16
        if target_side == "enemy":
            monster = self.monsters[index]
            _target_x, target_y = MONSTER_POSITIONS[index]
            return (
                self._monster_draw_x(index) + monster.width // 2,
                target_y + monster.height // 2,
            )
        raise ValueError("target_side must be 'ally' or 'enemy'")

    def _update_action_presentation(self) -> None:
        """Advance every simultaneous layer, then complete the current turn."""

        presentation = getattr(self, "action_presentation", None)
        if presentation is None:
            self._complete_current_turn()
            return
        presentation.update()
        if presentation.is_complete:
            self.action_presentation = None
            self._release_palette_variant(SPELL_EFFECT_FLASH_PALETTE)
            if getattr(self, "action_party_index", None) is not None:
                self._begin_action_return(complete_turn=True)
            else:
                self._complete_current_turn()
            return
        if presentation.spell_effects:
            self.spell_effect_renderer.prepare(
                presentation.spell_effects[0].player
            )

    def _begin_action_motion(self, *, use_cast_pose: bool) -> None:
        """Move the active party actor toward the enemies as in DA2."""

        if self.active_party_index is None:
            return
        self.action_party_index = self.active_party_index
        self.action_returning = False
        self.action_uses_cast_pose = use_cast_pose
        self.action_return_jump = False
        self.action_return_frame = 0
        self.action_return_start_offset = 0
        self.action_landing_guard_frames_remaining = 0

    def _begin_action_return(
        self,
        *,
        complete_turn: bool = False,
        jump: bool = False,
    ) -> None:
        """Send the party actor back before optionally advancing."""

        if getattr(self, "action_party_index", None) is None:
            if complete_turn:
                self.phase = BattlePhase.ACTION_RETURN
            return
        self.action_returning = True
        self.action_return_jump = jump
        self.action_return_frame = 0
        self.action_return_start_offset = self.action_offset_x
        self.action_landing_guard_frames_remaining = 0
        if jump:
            self._advance_action_return_jump()
        if complete_turn:
            self.phase = BattlePhase.ACTION_RETURN

    def _update_action_motion(self) -> None:
        """Advance one DA2-speed forward or backward action movement."""

        if getattr(self, "action_party_index", None) is None:
            return
        landing_frames = getattr(
            self,
            "action_landing_guard_frames_remaining",
            0,
        )
        if landing_frames:
            self.action_landing_guard_frames_remaining = landing_frames - 1
            if self.action_landing_guard_frames_remaining == 0:
                self._clear_action_motion_state()
            return
        if self.action_returning and getattr(self, "action_return_jump", False):
            self._advance_action_return_jump()
            return
        destination = 0 if self.action_returning else ACTION_MOVE_DISTANCE
        distance = destination - self.action_offset_x
        if distance:
            step = min(abs(distance), ACTION_MOVE_SPEED)
            self.action_offset_x += step if distance > 0 else -step
            self.action_motion_frame += 1
        if self.action_returning and self.action_offset_x == 0:
            self._clear_action_motion_state()

    def _advance_action_return_jump(self) -> None:
        """Advance the jump immediately so it has no stationary first frame."""

        self.action_return_frame += 1
        remaining = max(
            0,
            ATTACK_RETURN_JUMP_FRAME_COUNT - self.action_return_frame,
        )
        self.action_offset_x = (
            self.action_return_start_offset
            * remaining
            // ATTACK_RETURN_JUMP_FRAME_COUNT
        )
        self.action_motion_frame += 1
        if self.action_return_frame >= ATTACK_RETURN_JUMP_FRAME_COUNT:
            self.action_return_jump = False
            self.action_landing_guard_frames_remaining = (
                ATTACK_LANDING_GUARD_FRAME_COUNT
            )

    def _clear_action_motion_state(self) -> None:
        self.action_party_index = None
        self.action_offset_x = 0
        self.action_motion_frame = 0
        self.action_returning = False
        self.action_uses_cast_pose = False
        self.action_return_jump = False
        self.action_return_frame = 0
        self.action_return_start_offset = 0
        self.action_landing_guard_frames_remaining = 0

    def _commit_item_use(self, candidate: BattleItemCandidate) -> bool:
        """Remove an item or equipped gear only when its use was confirmed."""

        item = candidate.item
        if not item.breaks_on_use:
            return True
        if candidate.equipment_slot is None:
            return self.inventory_system.remove(item)
        if self.active_party_index is None:
            return False
        member = self.party[self.active_party_index]
        member.equipment = member.equipment.replaced({candidate.equipment_slot: None})
        return True

    def _cancel_action_target_selection(self) -> None:
        """Restore the item or spell list without spending a resource."""

        item_candidate = self.pending_item_candidate
        spell = self.pending_spell
        self._clear_action_target_state()
        if item_candidate is not None:
            self.phase = BattlePhase.ITEM
            self.selected_command = BattleCommand.ITEM
            self.item_window.open_immediately()
            self._refresh_item_options()
            return
        if spell is not None:
            self.phase = BattlePhase.SPELL
            self.selected_command = BattleCommand.SPELL
            self.spell_window.open_immediately()
            self._refresh_spell_options()
            return
        self._open_member_command_menu()

    def _clear_action_target_state(self) -> None:
        """Discard transient item/spell targeting state and hide its cursors."""

        self.selectable_target_indexes = ()
        self.selected_target_index = None
        self.selectable_party_target_indexes = ()
        self.selected_party_target_index = None
        self.action_targets_enemy = False
        self.action_targets_all = False
        self.pending_item_candidate = None
        self.pending_spell = None
        self.target_cursor.active = False
        if self.party_target_cursor is not None:
            self.party_target_cursor.active = False
        self.party_target_cursor = None
        self.all_target_cursors = ()
        self._refresh_monster_name_colors()

    def _begin_attack_target_selection(self) -> bool:
        selectable = self._active_member_attack_targets()
        if not selectable:
            return False

        self.selected_command = "attack"
        self.selectable_target_indexes = selectable
        # DA2 starts enemy selection at the last selectable monster.
        self.selected_target_index = selectable[-1]
        self.phase = BattlePhase.TARGET
        self._begin_action_motion(use_cast_pose=False)
        self.command_cursor.active = False
        self.target_cursor.active = True
        self.target_cursor.select_key(self.selected_target_index)
        self._refresh_monster_name_colors()
        return True

    def _update_target_selection(self, input_state: InputState) -> None:
        if getattr(self, "auto_battle_active", False):
            self._begin_attack_presentation()
            return
        if input_state.cancel.triggered:
            self.selected_command = None
            self.selectable_target_indexes = ()
            self.selected_target_index = None
            self.phase = BattlePhase.COMMAND
            self._begin_action_return()
            self.command_cursor.active = True
            self.target_cursor.active = False
            return

        if input_state.confirm.triggered:
            self._begin_attack_presentation()
            return

        navigation = input_state.navigation
        if navigation is not None:
            self._move_target(navigation)
        self.target_cursor.update()

    def _begin_attack_presentation(self) -> bool:
        """Start the selected right-hand weapon's authored attack sequence."""

        index = self.selected_target_index
        if (
            self.active_party_index is None
            or index is None
            or index not in self.selectable_target_indexes
        ):
            return False
        monster = self.monsters[index]
        if not monster.is_alive:
            return False
        member = self.party[self.active_party_index]
        weapon = member.equipment.weapon_at(EquipmentSlot.RIGHT)
        if weapon is None:
            return False
        weapon_img = weapon.weapon_img
        poses = attack_sequence(
            getattr(self, "attack_poses", {}),
            weapon_img,
        )
        effect_row = ATTACK_EFFECT_ROW_BY_SUBTYPE.get(weapon.subtype)
        member_stats = member.battle_stats
        monster_stats = monster.combat_stats
        attack = member_physical_attack(
            weapon_attack=member_stats.attack_right,
            strength=member.adjusted_abilities.strength,
            weapon_level=member.weapon_level(weapon),
            internal_level=member.internal_level,
        )
        result = resolve_physical_attack(
            attack=attack,
            hit=member_stats.hit_right.total,
            agility=member.adjusted_abilities.agility,
            target_defense=monster_stats.defense,
            target_evasion=monster_stats.evasion,
            hit_roll=random.randint(0, 99),
        )
        self.attack_presentation = BattleAttackPresentation(
            target_index=index,
            damage=result.damage,
            poses=poses,
            effect_row=effect_row,
            is_hit=result.hit,
            sound_effect_id=ATTACK_SE_ID_BY_SUBTYPE.get(
                weapon.subtype,
                ATTACK_SLASH_SE_ID,
            ),
        )
        self.phase = BattlePhase.ATTACK_PRESENTATION
        self.target_cursor.active = False
        self.command_window.close_immediately()
        self._refresh_monster_name_colors()
        return True

    def _update_attack_presentation(self) -> None:
        """Apply the hit, show its result, and start the jumping return."""

        presentation = getattr(self, "attack_presentation", None)
        if presentation is None:
            self._complete_current_turn()
            return
        presentation.elapsed_frame += 1
        if (
            not presentation.damage_applied
            and presentation.hit_elapsed_frame >= 0
        ):
            if presentation.is_hit:
                monster = self.monsters[presentation.target_index]
                monster.state.take_damage(presentation.damage)
                promote_rear_monsters_if_front_empty(self.monsters)
                play_se(presentation.sound_effect_id)
            presentation.damage_applied = True
        if (
            not presentation.return_started
            and presentation.elapsed_frame >= ATTACK_MOTION_FRAME_COUNT
        ):
            presentation.return_started = True
            self._begin_action_return(jump=True)
        if not presentation.result_complete:
            return
        target_index = presentation.target_index
        target_is_alive = self.monsters[target_index].is_alive
        self.attack_presentation = None
        if not target_is_alive:
            self._begin_monster_death(target_index)
            return
        self._complete_current_turn()

    def _begin_monster_death(self, index: int | None = None) -> bool:
        """Start the defeat effect for a target whose HP reached zero."""

        if index is None:
            index = self.selected_target_index
        if index is None:
            return False
        monster = self.monsters[index]
        if monster.is_alive:
            monster.state.defeat()
        promote_rear_monsters_if_front_empty(self.monsters)
        self.phase = BattlePhase.MONSTER_DEATH
        self.dying_monster_index = index
        self.monster_death_animation = MonsterDeathAnimation()
        self.target_cursor.active = False
        self.command_window.close_immediately()
        self._sync_monster_death_palette()
        play_se(BATTLE_MONSTER_DEATH_SE_ID)
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
        self._timeline_order = remove_timeline_actor(self._timeline_order, defeated)
        self.timeline = self._timeline_order.actors
        self.monster_death_animation = None
        self.dying_monster_index = None
        self._release_palette_variant(MONSTER_DEATH_PALETTE)
        if self._monsters_are_defeated():
            self.result = BattleResult.VICTORY
            return
        self._complete_current_turn()

    def _monsters_are_defeated(self) -> bool:
        """Return whether every monster in this encounter has died."""

        return bool(self.monsters) and all(
            not monster.is_alive for monster in self.monsters
        )

    def _release_transient_action_palettes(self) -> None:
        """Release mutually exclusive effect blocks before restarting the scene."""

        self._release_palette_variant(SPELL_EFFECT_FLASH_PALETTE)
        self._release_palette_variant(MONSTER_DEATH_PALETTE)

    def _release_palette_variant(self, name: str) -> None:
        palette_shifter = getattr(self, "palette_shifter", None)
        if palette_shifter is not None:
            palette_shifter.remove_variant(name)

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
        self.selectable_party_target_indexes = ()
        self.selected_party_target_index = None
        self.action_targets_enemy = False
        self.action_targets_all = False
        self.pending_item_candidate = None
        self.pending_spell = None
        self.action_presentation = None
        self.attack_presentation = None
        self._clear_action_motion_state()
        if self.party_target_cursor is not None:
            self.party_target_cursor.active = False
        self.party_target_cursor = None
        self.all_target_cursors = ()
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
        actor = self._timeline_order.entries[0].actor
        self.timeline_advance = complete_timeline_action(
            self._timeline_order,
            current_agility=actor.agility,
            visible_count=TIMELINE_VISIBLE_ENTRY_COUNT,
        )
        self.phase = BattlePhase.TIMELINE
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
                BattlePhase.COMMAND,
                BattlePhase.ITEM,
                BattlePhase.SPELL,
                BattlePhase.TARGET,
                BattlePhase.ESCAPE_CONFIRMATION,
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
        phase_frame_count = (
            self._timeline_interrupt_frame_count()
            if self.timeline_animation_phase is TimelineAnimationPhase.INTERRUPT
            else TIMELINE_ANIMATION_FRAME_COUNT
        )
        if self.timeline_animation_frame < phase_frame_count:
            self.timeline_animation_frame += 1
            return
        if self.timeline_animation_phase is TimelineAnimationPhase.DROP:
            self.timeline_animation_phase = TimelineAnimationPhase.SLIDE
            self.timeline_animation_frame = 0
            return
        if self.timeline_animation_phase is TimelineAnimationPhase.SLIDE:
            advance = self.timeline_advance
            if advance is None:
                raise RuntimeError("timeline animation requires a pending advance")
            if advance.interrupt_index is not None:
                self.timeline_animation_phase = TimelineAnimationPhase.INTERRUPT
                self.timeline_animation_frame = 0
                return
        self.timeline_animation_phase = None
        self.timeline_animation_frame = 0
        self._advance_timeline()

    def _advance_timeline(self) -> None:
        advance = self.timeline_advance
        if advance is None:
            raise RuntimeError("timeline advance is not prepared")
        self._timeline_order = ready_timeline_head(advance.after)
        self.timeline = self._timeline_order.actors
        self.timeline_advance = None
        self._activate_timeline_head()

    def _timeline_interrupt_frame_count(self) -> int:
        advance = self.timeline_advance
        if advance is None or advance.interrupt_index is None:
            return 0
        interrupt_index = advance.interrupt_index
        visible_remaining_count = min(
            len(advance.remaining.entries),
            TIMELINE_VISIBLE_ENTRY_COUNT,
        )
        last_visible_index = max(interrupt_index, visible_remaining_count - 1)
        last_collision_frame = self._timeline_interrupt_collision_frame(
            last_visible_index
        )
        slide_completion = last_collision_frame + TIMELINE_INTERRUPT_SLIDE_FRAME_COUNT
        if advance.overflow_actor is None:
            return max(TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT, slide_completion)
        overflow_completion = (
            self._timeline_interrupt_collision_frame(TIMELINE_VISIBLE_ENTRY_COUNT - 1)
            + TIMELINE_INTERRUPT_OVERFLOW_FRAME_COUNT
        )
        return max(TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT, overflow_completion)

    def _timeline_interrupt_collision_frame(self, index: int) -> int:
        """Return the frame when 16x16 icon rectangles first overlap."""

        advance = self.timeline_advance
        if advance is None or advance.interrupt_index is None:
            raise RuntimeError("timeline collision requires a pending interrupt")
        interrupt_index = advance.interrupt_index
        if not interrupt_index <= index < TIMELINE_VISIBLE_ENTRY_COUNT:
            raise ValueError("timeline collision index is outside the pushed range")

        destination_x = TIMELINE_BASE_X + interrupt_index * TIMELINE_SLOT_SPACING
        collision_frame: int | None = None
        for frame in range(TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT + 1):
            actor_y = SCREEN_HEIGHT - (
                (SCREEN_HEIGHT - TIMELINE_BASE_Y)
                * frame
                // TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT
            )
            if self._timeline_icons_collide(
                destination_x,
                actor_y,
                destination_x,
                TIMELINE_BASE_Y,
            ):
                collision_frame = frame
                break
        if collision_frame is None:
            raise RuntimeError("interrupting icon never reaches the timeline")

        for pushed_index in range(interrupt_index, index):
            pushed_x = TIMELINE_BASE_X + pushed_index * TIMELINE_SLOT_SPACING
            neighbor_x = pushed_x + TIMELINE_SLOT_SPACING
            for elapsed in range(1, TIMELINE_INTERRUPT_SLIDE_FRAME_COUNT + 1):
                moving_x = pushed_x + (
                    TIMELINE_SLOT_SPACING
                    * elapsed
                    // TIMELINE_INTERRUPT_SLIDE_FRAME_COUNT
                )
                if self._timeline_icons_collide(
                    moving_x,
                    TIMELINE_BASE_Y,
                    neighbor_x,
                    TIMELINE_BASE_Y,
                ):
                    collision_frame += elapsed
                    break
            else:
                raise RuntimeError("pushed timeline icons never collide")
        return collision_frame

    @staticmethod
    def _timeline_icons_collide(
        first_x: int,
        first_y: int,
        second_x: int,
        second_y: int,
    ) -> bool:
        """Return whether two 16x16 timeline icon rectangles overlap."""

        return (
            first_x < second_x + TIMELINE_ICON_SIZE
            and first_x + TIMELINE_ICON_SIZE > second_x
            and first_y < second_y + TIMELINE_ICON_SIZE
            and first_y + TIMELINE_ICON_SIZE > second_y
        )

    def _activate_timeline_head(self) -> None:
        self._remove_defeated_party_from_timeline()
        if self._party_is_defeated():
            self._begin_defeat_message()
            return
        actor = self.timeline[0]
        if isinstance(actor, BattleCharacter):
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
            if getattr(self, "auto_battle_active", False):
                self._begin_auto_action()
                self._refresh_party_text_colors()
                return
            self.phase = BattlePhase.COMMAND
            self.command_cursor.active = True
            self._hide_command_guide()
            self._refresh_command_options()
            self._select_initial_member_command()
            self.command_window.open()
            self._refresh_input_guide()
        else:
            self.active_party_index = None
            self.command_cursor.active = False
            self.command_window.close_immediately()
            self.monster_attack_target_index = None
            self.monster_attack_damage = None
            self.monster_attack_animation_frame = 0
            if not self._monster_attack_target_indexes(actor):
                self.blinking_monster_index = None
                self.monster_blink_frames_remaining = 0
                self._start_timeline_animation()
                return
            self.phase = BattlePhase.MONSTER_ACTION
            self.blinking_monster_index = next(
                index for index, monster in enumerate(self.monsters) if monster is actor
            )
            self.monster_blink_frames_remaining = MONSTER_BLINK_FRAME_COUNT
        self._refresh_party_text_colors()

    def _monster_attack_target_indexes(
        self,
        actor: BattleMonster,
    ) -> tuple[int, ...]:
        if not actor.is_front_row:
            return ()
        return tuple(
            index
            for index, member in enumerate(self.party)
            if member.hp > 0 and member.formation_row is FormationRow.FRONT
        )

    def _active_member_attack_targets(self) -> tuple[int, ...]:
        if self.active_party_index is None:
            return ()
        actor = self.party[self.active_party_index]
        if not member_can_attack(actor):
            return ()
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
                if option.command is BattleCommand.DEFEND
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
        return options

    def _select_initial_member_command(self) -> None:
        """Restore one member's last command, or use the normal initial choice."""

        if not hasattr(self, "party"):
            return
        active_index = getattr(self, "active_party_index", None)
        remembered_command = getattr(self, "last_command_by_party_index", {}).get(
            active_index
        )
        if remembered_command is not None:
            try:
                self.command_cursor.select_key(remembered_command)
            except ValueError:
                # A remembered command can become unavailable after an item is
                # consumed or a temporary battle condition changes.
                pass
            else:
                return
        options = self._active_member_command_options()
        attack = next(
            (option for option in options if option.command is BattleCommand.ATTACK),
            None,
        )
        if attack is not None and not attack.enabled:
            self.command_cursor.select_key(BattleCommand.DEFEND)

    def _remember_active_command(self, command: BattleCommand) -> None:
        """Keep a confirmed command for its member, except formation movement."""

        active_index = getattr(self, "active_party_index", None)
        if active_index is None:
            return
        commands = getattr(self, "last_command_by_party_index", None)
        if commands is None:
            commands = {}
            self.last_command_by_party_index = commands
        if command is BattleCommand.FORMATION:
            # Retreat and advance must open at the normal initial position on
            # the member's next turn, rather than restoring an older command.
            commands.pop(active_index, None)
            return
        commands[active_index] = command

    def _command_label(self, command: BattleCommand) -> str:
        """Resolve one command's localized display label from the text catalog."""

        return self.texts.text(self._command_text_key(command), self.localizer)

    def _command_text_key(self, command: BattleCommand) -> str:
        """Resolve the context-sensitive text key for one visible command."""

        if command is BattleCommand.FORMATION and self.active_party_index is not None:
            return FORMATION_COMMAND_TEXT_KEYS[
                self.party[self.active_party_index].is_front_row
            ]
        return COMMAND_TEXT_KEYS[command]

    def _command_guide_lines(self, command: BattleCommand) -> tuple[str, ...]:
        """Return DA2-derived guide text or the command name as a placeholder."""

        key = COMMAND_GUIDE_TEXT_KEYS.get(command, self._command_text_key(command))
        return self.texts.lines(key, self.localizer)

    def _update_command_guide(self) -> None:
        """Show a guide after the command cursor stays on one entry briefly."""

        guide_window = getattr(self, "command_guide_window", None)
        if guide_window is None:
            return
        if (
            self.phase is not BattlePhase.COMMAND
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

    def _refresh_input_guide(self) -> None:
        """Keep the bottom-right contextual cancel guide device-aware."""

        guide_window = getattr(self, "input_guide_window", None)
        if guide_window is None:
            return
        label = (
            "キャンセル"
            if getattr(self, "auto_battle_active", False)
            else "ぜんたい" if self.phase is BattlePhase.COMMAND else None
        )
        guide_window.clear_texts()
        if label is None:
            return
        guide_window.add_text(
            f"{input_icon_tag(InputAction.CANCEL, self.input_device)}：{label}",
            0,
            0,
        )

    def _update_monster_action(self) -> None:
        self.command_window.update(None)
        if self.monster_attack_target_index is not None:
            self.monster_attack_animation_frame += 1
            if (
                self.monster_attack_animation_frame
                >= self._monster_attack_animation_frame_count()
            ):
                self._finish_monster_attack()
            return
        if self.monster_blink_frames_remaining > 0:
            self.monster_blink_frames_remaining -= 1
        if self.monster_blink_frames_remaining > 0:
            return
        actor = self.timeline[0]
        if not isinstance(actor, BattleMonster):
            self._start_timeline_animation()
            return
        target_indexes = self._monster_attack_target_indexes(actor)
        if not target_indexes:
            self._start_timeline_animation()
            return
        self.monster_attack_target_index = random.choice(target_indexes)
        target = self.party[self.monster_attack_target_index]
        target_stats = target.battle_stats
        result = resolve_physical_attack(
            attack=actor.combat_stats.attack,
            hit=actor.combat_stats.hit,
            agility=actor.agility,
            target_defense=target_stats.defense,
            target_evasion=target_stats.evasion,
            hit_roll=random.randint(0, 99),
        )
        self.monster_attack_damage = result.damage
        self.monster_attack_animation_frame = 0
        if result.hit:
            play_se(BATTLE_HIT_SE_ID)

    def _monster_attack_animation_frame_count(self) -> int:
        return (
            MONSTER_MISS_FRAME_COUNT
            if self.monster_attack_damage == 0
            else MONSTER_DAMAGE_FRAME_COUNT
        )

    def _finish_monster_attack(self) -> None:
        target_index = self.monster_attack_target_index
        damage = self.monster_attack_damage
        if target_index is None or damage is None:
            raise RuntimeError("monster attack requires a target and result")
        if damage > 0:
            member = self.party[target_index]
            member.hp = max(0, member.hp - damage)
            self._refresh_party_hp_text(target_index)
        self.monster_attack_target_index = None
        self.monster_attack_damage = None
        self.monster_attack_animation_frame = 0
        if damage > 0 and self._member_is_dead(self.party[target_index]):
            self.defending_party_indexes.discard(target_index)
            self._remove_defeated_party_from_timeline()
            if self._party_is_defeated():
                self._begin_defeat_message()
                return
        self._start_timeline_animation()

    def _party_is_defeated(self) -> bool:
        """Return whether every battle participant has died."""

        return bool(self.party_visuals) and all(
            self._party_member_is_dead(index)
            for index in range(len(self.party_visuals))
        )

    def _remove_defeated_party_from_timeline(self) -> None:
        """Remove dead party actors by identity while preserving gauge order."""

        defeated = tuple(
            visual
            for index, visual in enumerate(self.party_visuals)
            if self._party_member_is_dead(index)
        )
        if not defeated:
            return
        order = getattr(self, "_timeline_order", None)
        if order is None:
            self.timeline = tuple(
                actor
                for actor in self.timeline
                if all(actor is not visual for visual in defeated)
            )
            return
        for visual in defeated:
            self._timeline_order = remove_timeline_actor(
                self._timeline_order,
                visual,
            )
        self.timeline = self._timeline_order.actors

    def _refresh_all_party_hp_texts(self) -> None:
        if not hasattr(self, "party_status_texts"):
            return
        for index in range(len(self.party_status_texts)):
            self._refresh_party_hp_text(index)

    def _refresh_party_hp_text(self, index: int) -> None:
        window = self.party_status_windows[index]
        name_text, hp_text = self.party_status_texts[index]
        member = self.party[index]
        window.remove_text(hp_text)
        hp_text = window.add_text(
            ascii_to_fullwidth(f"{member.hp:3d}/{member.max_hp:3d}"),
            hp_text.x,
            hp_text.y,
            color=hp_text.color,
            font=hp_text.font,
            shadow_color=hp_text.shadow_color,
            baseline_offset=hp_text.baseline_offset,
            font_spans=hp_text.font_spans,
        )
        self.party_status_texts[index] = (name_text, hp_text)

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
                self.phase is not BattlePhase.TARGET
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
        self._draw_party_attack_effect()
        self._draw_spell_effects()
        self._draw_party_attack_damage()
        self._draw_monster_attack_result()
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
            if (
                self.phase is BattlePhase.MONSTER_ACTION
                and index == getattr(self, "monster_attack_target_index", None)
                and getattr(self, "monster_attack_damage", None)
            ):
                shake_index = (
                    self.monster_attack_animation_frame
                    * DA2_REFERENCE_FPS
                    // FPS
                ) % len(MONSTER_DAMAGE_SHAKE_X)
                x += MONSTER_DAMAGE_SHAKE_X[shake_index]
            is_escaping = self.phase in (
                BattlePhase.ESCAPE_MESSAGE,
                BattlePhase.ESCAPE,
            ) or index in getattr(self, "escaping_party_indexes", ())
            width = self._party_sprite_width(index, is_escaping=is_escaping)
            attack_presentation = getattr(self, "attack_presentation", None)
            attack_pose = (
                attack_presentation.pose
                if (
                    not self._party_member_is_dead(index)
                    and self.phase is BattlePhase.ATTACK_PRESENTATION
                    and index == getattr(self, "action_party_index", None)
                    and attack_presentation is not None
                )
                else None
            )
            if attack_pose is not None:
                self._draw_attack_composite(index, x, y, attack_pose)
                continue
            if self.phase is BattlePhase.ACTION_PRESENTATION:
                self._draw_spell_effect_target(
                    "ally",
                    index,
                    lambda: pyxel.blt(
                        x,
                        y,
                        self.character_sprites,
                        self._party_sprite_source_x(index),
                        visual.battle_sprite * 32,
                        width,
                        32,
                        TRANSPARENT_INDEX,
                    ),
                )
                continue
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

    def _draw_attack_composite(
        self,
        index: int,
        x: int,
        y: int,
        pose: AttackPoseDefinition,
    ) -> None:
        """Draw authored back weapons, character pose, then front weapons."""

        def draw_weapon(weapon: AttackWeaponSprite) -> None:
            width = (
                -ATTACK_WEAPON_SPRITE_SIZE
                if weapon.flip_x
                else ATTACK_WEAPON_SPRITE_SIZE
            )
            height = (
                -ATTACK_WEAPON_SPRITE_SIZE
                if weapon.flip_y
                else ATTACK_WEAPON_SPRITE_SIZE
            )
            pyxel.blt(
                x + weapon.position_x,
                y + weapon.position_y,
                0,
                weapon.image * ATTACK_WEAPON_SPRITE_SIZE,
                ATTACK_WEAPON_SPRITE_Y,
                width,
                height,
                TRANSPARENT_INDEX,
            )

        for weapon in pose.weapons:
            if weapon.layer == "back":
                draw_weapon(weapon)
        pyxel.blt(
            x,
            y,
            self.character_sprites,
            pose.character_pose * 16,
            self.party_visuals[index].battle_sprite * 32,
            16,
            32,
            TRANSPARENT_INDEX,
        )
        for weapon in pose.weapons:
            if weapon.layer == "front":
                draw_weapon(weapon)

    def _party_draw_position(self, index: int) -> tuple[int, int] | None:
        target_x = self._party_sprite_x(index)
        target_y = PARTY_SPRITE_Y[index]
        if self.phase in (
            BattlePhase.ESCAPE_MESSAGE,
            BattlePhase.ESCAPE,
        ) and not self._party_member_is_dead(index):
            return self._escape_party_x(index), target_y
        if (
            self.phase is BattlePhase.FORMATION
            and index == self.formation_actor_index
        ):
            x = self.formation_start_x + (
                (self.formation_destination_x - self.formation_start_x)
                * self.formation_animation_frame
                // FORMATION_MOVE_FRAME_COUNT
            )
            return x, target_y
        if self.phase is not BattlePhase.ENTRANCE:
            if index == getattr(self, "action_party_index", None):
                target_x -= self.action_offset_x
                if (
                    self.action_returning
                    and getattr(self, "action_return_jump", False)
                ):
                    elapsed = min(
                        self.action_return_frame,
                        ATTACK_RETURN_JUMP_FRAME_COUNT,
                    )
                    remaining = ATTACK_RETURN_JUMP_FRAME_COUNT - elapsed
                    jump = (
                        4
                        * ATTACK_RETURN_JUMP_HEIGHT
                        * elapsed
                        * remaining
                        // (ATTACK_RETURN_JUMP_FRAME_COUNT**2)
                    )
                    target_y -= jump
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

    def _party_member_is_dead(self, index: int) -> bool:
        member = getattr(self.party_visuals[index], "member", None)
        if member is None:
            return False
        return self._member_is_dead(member)

    @staticmethod
    def _member_is_dead(member: object) -> bool:
        if isinstance(member, Member):
            return member.is_dead
        is_dead = getattr(member, "is_dead", None)
        if is_dead is not None:
            return bool(is_dead)
        return getattr(member, "hp", 1) <= 0

    def _party_member_is_dying(self, index: int) -> bool:
        member = self.party_visuals[index].member
        if isinstance(member, Member):
            return member.is_dying
        return bool(getattr(member, "is_dying", False))

    def _party_sprite_width(self, index: int, *, is_escaping: bool) -> int:
        if self._party_member_is_dead(index):
            return DEAD_SPRITE_WIDTH
        return -PARTY_SPRITE_WIDTH if is_escaping else PARTY_SPRITE_WIDTH

    def _party_sprite_source_x(self, index: int) -> int:
        if self._party_member_is_dead(index):
            return DEAD_SPRITE_SOURCE_X
        if self.phase in (BattlePhase.ESCAPE_MESSAGE, BattlePhase.ESCAPE):
            pattern = (
                self.escape_animation_frame // ESCAPE_RUN_PATTERN_FRAME_COUNT
            ) % 2
            return pattern * FORMATION_SPRITE_STEP_X
        if index in getattr(self, "escaping_party_indexes", ()):
            return 0
        if (
            self.phase is BattlePhase.FORMATION
            and index == self.formation_actor_index
        ):
            pattern = (
                self.formation_animation_frame // FORMATION_WALK_PATTERN_FRAME_COUNT
            ) % 2
            return pattern * FORMATION_SPRITE_STEP_X
        if (
            self.phase is BattlePhase.MONSTER_ACTION
            and index == getattr(self, "monster_attack_target_index", None)
            and getattr(self, "monster_attack_damage", None)
        ):
            return MONSTER_DAMAGE_SPRITE_SOURCE_X
        if index == getattr(self, "action_party_index", None):
            if getattr(self, "action_landing_guard_frames_remaining", 0):
                return DEFEND_SPRITE_SOURCE_X
            if self.action_returning and getattr(self, "action_return_jump", False):
                return 0
            if (
                self.action_offset_x != ACTION_MOVE_DISTANCE
                or self.action_returning
            ):
                pattern = (
                    self.action_motion_frame
                    // FORMATION_WALK_PATTERN_FRAME_COUNT
                ) % 2
                return pattern * FORMATION_SPRITE_STEP_X
            return SPELL_CAST_SPRITE_SOURCE_X if self.action_uses_cast_pose else 0
        if index in getattr(self, "defending_party_indexes", ()):
            return DEFEND_SPRITE_SOURCE_X
        if self._party_member_is_dying(index):
            return NEAR_DEATH_SPRITE_SOURCE_X
        return 0

    def _draw_monster_attack_result(self) -> None:
        target_index = getattr(self, "monster_attack_target_index", None)
        damage = getattr(self, "monster_attack_damage", None)
        if (
            getattr(self, "phase", None) is not BattlePhase.MONSTER_ACTION
            or target_index is None
            or damage is None
        ):
            return
        offsets = (
            DA2_MISS_VERTICAL_OFFSETS
            if damage == 0
            else DA2_DAMAGE_VERTICAL_OFFSETS
        )
        popup_elapsed_frame = self.monster_attack_animation_frame
        reference_frame = min(
            popup_elapsed_frame * DA2_REFERENCE_FPS // FPS,
            len(offsets) - 1,
        )
        vertical_offset = offsets[reference_frame]
        if vertical_offset < 0:
            return
        target_x = self._party_sprite_x(target_index)
        target_y = PARTY_SPRITE_Y[target_index]
        anchor_x = target_x + 14
        y = target_y + 16 - vertical_offset
        if damage == 0:
            pyxel.blt(
                anchor_x - MISS_SPRITE_WIDTH // 2,
                y,
                0,
                MISS_SPRITE_SOURCE_X,
                DAMAGE_NUMBER_SPRITE_Y,
                MISS_SPRITE_WIDTH,
                DAMAGE_NUMBER_SPRITE_SIZE,
                TRANSPARENT_INDEX,
            )
            return
        digits = str(damage)
        x = anchor_x - len(digits) * DAMAGE_NUMBER_SPRITE_SIZE // 2
        for digit in digits:
            pyxel.blt(
                x,
                y,
                0,
                int(digit) * DAMAGE_NUMBER_SPRITE_SIZE,
                DAMAGE_NUMBER_SPRITE_Y,
                DAMAGE_NUMBER_SPRITE_SIZE,
                DAMAGE_NUMBER_SPRITE_SIZE,
                TRANSPARENT_INDEX,
            )
            x += DAMAGE_NUMBER_SPRITE_SIZE

    def _draw_party_attack_effect(self) -> None:
        """Draw one of the five three-pattern weapon impact rows."""

        presentation = getattr(self, "attack_presentation", None)
        if (
            getattr(self, "phase", None) is not BattlePhase.ATTACK_PRESENTATION
            or presentation is None
            or not presentation.is_hit
            or presentation.effect_row is None
            or not 0 <= presentation.hit_elapsed_frame < ATTACK_HIT_FRAME_COUNT
        ):
            return
        pattern = (
            presentation.hit_elapsed_frame // ATTACK_HIT_PATTERN_FRAME_COUNT
        )
        anchor_x, anchor_y = self._spell_effect_anchor(
            "enemy",
            presentation.target_index,
        )
        pyxel.blt(
            anchor_x - ATTACK_EFFECT_CELL_SIZE // 2,
            anchor_y - ATTACK_EFFECT_CELL_SIZE // 2 + 8,
            self.attack_effect_image,
            pattern * ATTACK_EFFECT_CELL_SIZE,
            presentation.effect_row * ATTACK_EFFECT_CELL_SIZE,
            ATTACK_EFFECT_CELL_SIZE,
            ATTACK_EFFECT_CELL_SIZE,
            TRANSPARENT_INDEX,
        )

    def _draw_party_attack_damage(self) -> None:
        """Draw a resolved damage or miss result over the target monster."""

        presentation = getattr(self, "attack_presentation", None)
        if (
            getattr(self, "phase", None) is not BattlePhase.ATTACK_PRESENTATION
            or presentation is None
            or not presentation.damage_applied
        ):
            return
        offsets = (
            DA2_DAMAGE_VERTICAL_OFFSETS
            if presentation.is_hit
            else DA2_MISS_VERTICAL_OFFSETS
        )
        frame_count = (
            ATTACK_DAMAGE_FRAME_COUNT
            if presentation.is_hit
            else MONSTER_MISS_FRAME_COUNT
        )
        popup_elapsed_frame = presentation.damage_popup_elapsed_frame
        if not 0 <= popup_elapsed_frame < frame_count:
            return
        reference_frame = min(
            popup_elapsed_frame * DA2_REFERENCE_FPS // FPS,
            len(offsets) - 1,
        )
        vertical_offset = offsets[reference_frame]
        if vertical_offset < 0:
            return
        monster = self.monsters[presentation.target_index]
        _target_x, target_y = MONSTER_POSITIONS[presentation.target_index]
        anchor_x = self._monster_draw_x(presentation.target_index) + monster.width // 2
        y = target_y + monster.height - 8 - vertical_offset
        if not presentation.is_hit:
            pyxel.blt(
                anchor_x - MISS_SPRITE_WIDTH // 2,
                y,
                0,
                MISS_SPRITE_SOURCE_X,
                DAMAGE_NUMBER_SPRITE_Y,
                MISS_SPRITE_WIDTH,
                DAMAGE_NUMBER_SPRITE_SIZE,
                TRANSPARENT_INDEX,
            )
            return
        digits = str(presentation.damage)
        x = anchor_x - len(digits) * DAMAGE_NUMBER_SPRITE_SIZE // 2
        for digit in digits:
            pyxel.blt(
                x,
                y,
                0,
                int(digit) * DAMAGE_NUMBER_SPRITE_SIZE,
                DAMAGE_NUMBER_SPRITE_Y,
                DAMAGE_NUMBER_SPRITE_SIZE,
                DAMAGE_NUMBER_SPRITE_SIZE,
                TRANSPARENT_INDEX,
            )
            x += DAMAGE_NUMBER_SPRITE_SIZE

    def _draw_monsters(self) -> None:
        for index, (monster, (_, y)) in enumerate(
            zip(self.monsters, MONSTER_POSITIONS)
        ):
            is_dying = (
                self.phase is BattlePhase.MONSTER_DEATH
                and index == self.dying_monster_index
            )
            attack_presentation = getattr(self, "attack_presentation", None)
            is_attack_target = (
                self.phase is BattlePhase.ATTACK_PRESENTATION
                and attack_presentation is not None
                and index == attack_presentation.target_index
            )
            if not monster.is_alive and not is_dying and not is_attack_target:
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
                if self.phase is BattlePhase.ACTION_PRESENTATION:
                    self._draw_spell_effect_target(
                        "enemy",
                        index,
                        lambda: self._draw_monster_image(monster, x, y),
                    )
                    continue
                is_unselectable_rear_target = (
                    self.phase is BattlePhase.TARGET
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

    def _draw_spell_effect_target(
        self,
        target_side: str,
        target_index: int,
        draw_target: Callable[[], None],
    ) -> None:
        """Draw one target normally or through its active spell flash."""

        presentation = getattr(self, "action_presentation", None)
        if presentation is None:
            draw_target()
            return
        target_effect = next(
            (
                effect
                for effect in presentation.spell_effects
                if effect.target_side == target_side
                and effect.target_index == target_index
            ),
            None,
        )
        if target_effect is None:
            draw_target()
            return
        self.spell_effect_renderer.draw_target(target_effect.player, draw_target)

    def _draw_spell_effects(self) -> None:
        """Draw effect sprites; result popups will compose after this layer."""

        presentation = getattr(self, "action_presentation", None)
        if presentation is None:
            return
        for effect in presentation.spell_effects:
            self.spell_effect_renderer.draw_effect(effect.player)

    def _draw_monster_image(
        self,
        monster: BattleMonster,
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
        if self.phase is not BattlePhase.ENTRANCE:
            return target_x

        duration = MONSTER_ENTRANCE_FRAME_COUNTS[index]
        elapsed = min(self.entrance_animation_frame, duration)
        remaining = duration - elapsed
        initial_offset = (
            DA2_MONSTER_ENTRANCE_SLIDE_STEPS[index] * DA2_MONSTER_ENTRANCE_STEP_DISTANCE
        )
        return target_x - initial_offset * remaining // duration

    def _draw_target_cursor(self) -> None:
        if self.phase is BattlePhase.TARGET:
            self.target_cursor.draw()
            return
        if self.phase is not BattlePhase.ACTION_TARGET:
            return
        if self.action_targets_all:
            # DA2 draws every cursor on alternating frames for all-target effects.
            if pyxel.frame_count % 2 == 0:
                for cursor in self.all_target_cursors:
                    cursor.draw()
            return
        if self.action_targets_enemy:
            self.target_cursor.draw()
        elif self.party_target_cursor is not None:
            self.party_target_cursor.draw()

    def _draw_timeline(self) -> None:
        if self.phase is BattlePhase.ENTRANCE:
            for index, entry in enumerate(self.timeline[:TIMELINE_VISIBLE_ENTRY_COUNT]):
                x = self._timeline_entrance_x(index)
                if x is None:
                    continue
                self._draw_timeline_entry(entry, x, TIMELINE_BASE_Y)
            return
        if self.timeline_animation_phase is TimelineAnimationPhase.DROP:
            advance = self.timeline_advance
            if advance is None:
                raise RuntimeError("timeline drop requires a pending advance")
            drop = (
                TIMELINE_DROP_DISTANCE
                * self.timeline_animation_frame
                * self.timeline_animation_frame
                // (TIMELINE_ANIMATION_FRAME_COUNT**2)
            )
            for index, entry in enumerate(
                advance.before.actors[:TIMELINE_VISIBLE_ENTRY_COUNT]
            ):
                y = TIMELINE_BASE_Y + (drop if index == 0 else 0)
                self._draw_timeline_entry(
                    entry,
                    TIMELINE_BASE_X + index * TIMELINE_SLOT_SPACING,
                    y,
                )
            return
        if self.timeline_animation_phase is TimelineAnimationPhase.SLIDE:
            advance = self.timeline_advance
            if advance is None:
                raise RuntimeError("timeline slide requires a pending advance")
            shift = (
                TIMELINE_SLOT_SPACING
                * self.timeline_animation_frame
                // TIMELINE_ANIMATION_FRAME_COUNT
            )
            remaining = advance.remaining.actors
            sliding_entries = remaining[: TIMELINE_VISIBLE_ENTRY_COUNT - 1]
            for index, entry in enumerate(sliding_entries):
                self._draw_timeline_entry(
                    entry,
                    TIMELINE_BASE_X + (index + 1) * TIMELINE_SLOT_SPACING - shift,
                    TIMELINE_BASE_Y,
                )
            incoming: BattleCharacter | BattleMonster | None = None
            if len(remaining) >= TIMELINE_VISIBLE_ENTRY_COUNT:
                incoming = remaining[TIMELINE_VISIBLE_ENTRY_COUNT - 1]
                incoming_index = TIMELINE_VISIBLE_ENTRY_COUNT - 1
            elif advance.interrupt_index is None:
                incoming = advance.completed_actor
                incoming_index = len(remaining)
            if incoming is not None:
                destination_x = TIMELINE_BASE_X + incoming_index * TIMELINE_SLOT_SPACING
                incoming_x = TIMELINE_INCOMING_START_X - (
                    (TIMELINE_INCOMING_START_X - destination_x)
                    * self.timeline_animation_frame
                    // TIMELINE_ANIMATION_FRAME_COUNT
                )
                self._draw_timeline_entry(
                    incoming,
                    incoming_x,
                    TIMELINE_BASE_Y,
                )
            return
        if self.timeline_animation_phase is TimelineAnimationPhase.INTERRUPT:
            self._draw_timeline_interrupt()
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

    def _draw_timeline_interrupt(self) -> None:
        """Draw the completed actor rising into the order and pushing neighbors."""

        advance = self.timeline_advance
        if advance is None or advance.interrupt_index is None:
            raise RuntimeError("timeline interrupt requires a pending interrupt")
        frame = self.timeline_animation_frame
        interrupt_index = advance.interrupt_index
        remaining = advance.remaining.actors[:TIMELINE_VISIBLE_ENTRY_COUNT]
        for index, entry in enumerate(remaining):
            x = TIMELINE_BASE_X + index * TIMELINE_SLOT_SPACING
            y = TIMELINE_BASE_Y
            if index >= interrupt_index:
                collision_delay = self._timeline_interrupt_collision_frame(index)
                if entry is advance.overflow_actor:
                    elapsed = max(
                        0,
                        min(
                            frame - collision_delay,
                            TIMELINE_INTERRUPT_OVERFLOW_FRAME_COUNT,
                        ),
                    )
                    duration = TIMELINE_INTERRUPT_OVERFLOW_FRAME_COUNT
                    x += (
                        (TIMELINE_INTERRUPT_OVERFLOW_DESTINATION_X - x)
                        * elapsed
                        // duration
                    )
                    jump = (
                        4
                        * TIMELINE_INTERRUPT_OVERFLOW_JUMP_HEIGHT
                        * elapsed
                        * (duration - elapsed)
                        // (duration**2)
                    )
                    fall = (
                        (SCREEN_HEIGHT + 16 - TIMELINE_BASE_Y)
                        * elapsed
                        * elapsed
                        // (duration**2)
                    )
                    y += fall - jump
                else:
                    slide_elapsed = max(
                        0,
                        min(
                            frame - collision_delay,
                            TIMELINE_INTERRUPT_SLIDE_FRAME_COUNT,
                        ),
                    )
                    x += (
                        TIMELINE_SLOT_SPACING
                        * slide_elapsed
                        // TIMELINE_INTERRUPT_SLIDE_FRAME_COUNT
                    )
            self._draw_timeline_entry(entry, x, y)

        entry_elapsed = min(frame, TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT)
        actor_y = SCREEN_HEIGHT - (
            (SCREEN_HEIGHT - TIMELINE_BASE_Y)
            * entry_elapsed
            // TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT
        )
        self._draw_timeline_entry(
            advance.completed_actor,
            TIMELINE_BASE_X + interrupt_index * TIMELINE_SLOT_SPACING,
            actor_y,
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
        entry: BattleCharacter | BattleMonster,
        x: int,
        y: int,
    ) -> None:
        color = 13 if isinstance(entry, BattleCharacter) else 49
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
            BattlePhase.ESCAPE_MESSAGE,
            BattlePhase.ESCAPE,
        ) or (
            self.phase is BattlePhase.ENTRANCE
            and self.entrance_animation_frame
            < getattr(
                self,
                "party_entrance_complete_frame",
                PARTY_ENTRANCE_COMPLETE_FRAME,
            )
        )
        for window in self.windows:
            if hide_party_status and any(
                window is status_window for status_window in self.party_status_windows
            ):
                continue
            window.draw()
        global_command_window = getattr(self, "global_command_window", None)
        show_monster_names = (
            self.phase is BattlePhase.TARGET
            or (
                self.phase is BattlePhase.ACTION_TARGET
                and self.action_targets_enemy
            )
            or (self.phase is BattlePhase.INITIAL and self.command_window.is_closed)
            or (
                self.phase is BattlePhase.GLOBAL_COMMAND
                and global_command_window is not None
                and global_command_window.is_open
            )
        )
        if show_monster_names:
            for monster, window in zip(
                self.monsters,
                self.monster_name_windows,
            ):
                if monster.is_alive:
                    window.draw()
        if (
            self.phase is BattlePhase.ESCAPE_CONFIRMATION
            and self.command_window.is_closed
            and (global_command_window is None or global_command_window.is_closed)
        ):
            self.escape_message_window.draw()
            self.escape_choice_window.draw()
        if self.phase is BattlePhase.ESCAPE_MESSAGE:
            self.escape_started_message_window.draw()
        battle_popup = getattr(self, "battle_popup", None)
        if self.phase is BattlePhase.DEFEAT_MESSAGE:
            self.battle_popup_window.draw()
        elif battle_popup is not None and battle_popup.visible:
            self.battle_popup_window.draw()
        if (
            getattr(self, "auto_battle_active", False)
            or self.phase is BattlePhase.COMMAND
        ):
            input_guide_window = getattr(self, "input_guide_window", None)
            if input_guide_window is not None:
                input_guide_window.draw()
