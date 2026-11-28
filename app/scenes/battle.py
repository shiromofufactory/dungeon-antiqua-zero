"""Run and render Dungeon Antiqua ZERO battles."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from math import ceil, cos, hypot, pi
from pathlib import Path
from time import perf_counter
from typing import Callable, Protocol, TypeVar

import pyxel

from battle_layout import (
    MONSTER_POSITIONS,
    MonsterPlacement,
    find_monster_placement,
    monster_revival_placement_available,
    monster_layout,
)
from auto_battle import AutoBattlePlanner
from auto_battle_model import (
    AutoAction,
    AutoBattleLogEntry,
    AutoBattlePolicy,
    AutoBattleSnapshot,
    AutoCombatant,
)
from attack_pose import (
    AttackPoseDefinition,
    AttackWeaponSprite,
    attack_sequence,
    load_attack_poses,
    throwing_projectile_sequence,
)
from battle_command_memory import BattleCommandMemory
from battle_breath import (
    member_breath_attack,
    member_breath_hp_cost,
    resolve_fire_breath,
    resolve_poison_breath,
)
from battle_commands import (
    BattleCommand,
    BattleCommandContext,
    BattleCommandOption,
    member_can_attack,
    member_can_iai,
    member_attack_reach,
    resolve_battle_commands,
    selectable_attack_target_indexes,
)
from battle_magic import (
    DA2_DEFAULT_ITEM_SPELL_ABILITY,
    PRAY_SUCCESS_ROLL_COUNT,
    SPELL_REFLECTION_ROLL_COUNT,
    TEMPTATION_RATE,
    SpellAffinity,
    battle_healing_amount,
    debuff_turn_range,
    member_spell_ability,
    member_spell_modifier,
    poison_tick_damage,
    resolve_healing,
    resolve_pray_recovery,
    resolve_recovery_amount,
    resolve_spell_damage,
    resolve_status_spell,
    spell_cast_delay,
    spell_reflection_chance,
    spell_resistances,
)
from monster_ai import (
    MonsterAction,
    MonsterActionChoice,
    MonsterSpellAction,
    MonsterSpellCandidate,
    MonsterSpellTarget,
    evaluate_monster_spell,
    evaluate_monster_support_spell,
    monster_attack_targets,
    monster_spell_evaluation_order,
    prefer_monster_targets,
    reinforcement_arrives,
    reinforcement_target,
    select_monster_action,
)
from battle_speed import (
    MAX_SPEED_MODIFIER,
    MIN_SPEED_MODIFIER,
    SLOW_GAUGE_ADJUSTMENT,
    modified_agility,
)
from battle_physical import (
    CONSTRICTION_HIT_ROLL_COUNT,
    INNER_STEEL_SKILL_KEY,
    PHYSICAL_EFFECT_RESISTANCE,
    PHYSICAL_HIT_ROLL_COUNT,
    PHYSICAL_STATUS_EFFECTS,
    counter_attack_succeeds,
    resolve_earthquake_attack,
    PhysicalAttackResult,
    drain_healing_amount,
    inner_steel_attack,
    member_physical_attack,
    physical_weapon_is_effective,
    resolve_monster_attack_effects,
    resolve_physical_additional_effect,
    resolve_physical_attack,
    weapon_can_drain,
)
from battle_timeline import (
    GAUGE_READY_VALUE,
    TimelineAdvance,
    TimelineOrder,
    adjust_timeline_entry_gauge,
    complete_timeline_action,
    initialize_timeline_order,
    insert_timeline_actor,
    ready_timeline_head,
    remove_timeline_actor,
    remove_timeline_head,
)
from battle_surprise import (
    SURPRISE_ROLL_MAX,
    VIGILANCE_SKILL_KEY,
    SurpriseRoll,
    resolve_surprise_roll,
)
from item import (
    AdditionalEffect,
    AttackAttribute,
    Item,
    ItemDataError,
    ItemEquipType,
    ItemSpecial,
    monster_additional_effects_from_codes,
)
from localization import LocalizedText, Localizer, ascii_to_fullwidth, format_number
from member import (
    BATTLE_PARTY_MEMBER_COUNT,
    EquipmentSlot,
    FormationRow,
    Gender,
    MAX_PROTECTION_LEVEL,
    Member,
    Race,
)
from monster import (
    MonsterDataError,
    MonsterDefinition,
    MonsterBattleState,
    MonsterCombatStats,
    MonsterSpecialAction,
    MonsterTribe,
    monster_shadow_from_record,
    monster_spell_keys_from_record,
    monster_special_actions_from_record,
    promote_rear_monsters_if_front_empty,
)
from resistance import ResistanceType, resistances_from_tolerance
from input import Direction, InputAction, InputDevice, InputState
from rendering import (
    DEFAULT_FADE_FRAME_COUNT,
    DIMMED_PALETTE,
    MONOCHROME_PALETTE,
    MONSTER_DEATH_PALETTE,
    MONSTER_DEATH_PALETTE_BASE_RATE,
    SPELL_EFFECT_FLASH_PALETTE,
    FadeEvent,
    FadeThroughBlack,
    MonsterDeathAnimation,
    MosaicFadeOut,
    SpellEffectRenderer,
    draw_character_shadow,
    floating_offset,
    floating_phase_offset,
)
from rendering.spell_effect import draw_drain_flight
from resources import (
    TRANSPARENT_INDEX,
    BgmPlayer,
    FontResources,
    ImageResourceError,
    ImageResources,
    load_record_array,
    play_se,
)
from state import Language, SaveData, Settings
from spell import (
    SPELL_PROFICIENCY_BY_TYPE,
    SPELL_TYPE_ICON_TAGS,
    Spell,
    SpellAction,
    SpellType,
)
from spell_effect import (
    BLACK_WIND_EFFECT_KEY,
    BLOOD_SUCK_EFFECT_KIND,
    DRAIN_FLIGHT_FRAME_COUNT,
    SPELL_RESULT_OVERLAP_FRAME_COUNT,
    SPELL_REFLECT_EFFECT_KEY,
    SpellEffectPlayer,
    SpellScreenFlash,
    load_spell_effects,
)
from systems import (
    BattleGrowthResult,
    BattleProgression,
    EnemyProgressionData,
    InventorySystem,
    MonsterRecordSystem,
)
from text_catalog import TextCatalog
from ui import (
    DEFAULT_TEXT_COLOR,
    BattleResultOverlay,
    LocalizedWindowTextFactory,
    DISABLED_COLOR,
    RESERVE_MEMBER_TEXT_COLOR,
    TEXT_GRID_X,
    CursorTarget,
    Window,
    WindowCursor,
    WindowFactory,
    WindowText,
    input_icon_tag,
    monster_detail_texts,
    tagged_text_width,
)
from item_detail import ItemDetailContext, item_detail_lines
from ui.auto_battle import AutoBattleOverlay
from ui.text_layout import right_aligned_grid_x
from rendering.victory_pose import (
    VICTORY_MOTION_LIMIT,
    VICTORY_SPRITE_SOURCE_X,
    victory_sprite_source_x,
)

APP_ROOT = Path(__file__).resolve().parents[1]
FPS = 60
SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240

BACKGROUND_IMAGE_ID = "background/bg_nector"
MONSTER_SHADOW_IMAGE_ID = "background/shadow"
MONSTER_SHADOW_WIDTH = 64
MONSTER_SHADOW_HEIGHT = 5
MONSTER_SHADOW_OFFSET_Y = -4
MONSTER_FLOATING_OFFSETS = (-2, -2, -2, -1, 0, 0, 0, -1)
MONSTER_FLOATING_PATTERN_FRAME_COUNT = 12  # DA2's six frames at twice its FPS.
CH_BATTLE_IMAGE_ID = "characters/ch_battle"
BATTLE_BGM_ID = "da3-battle1"
BATTLE_BOSS_BGM_ID = "da3-battle2"
BATTLE_WIN_BGM_ID = "da3-win"
BATTLE_LEVEL_UP_BGM_ID = "da3-lvup"
BATTLE_HIT_SE_ID = "battle_hit"
BATTLE_DRAIN_SE_ID = "battle_drain"
MONSTER_DRAIN_HEAL_DELAY = 10  # DA2's five frames at 60 fps.
BATTLE_POISON_BREATH_SE_ID = "battle_poison_breath"
BATTLE_FIRE_BREATH_SE_ID = "battle_fire_breath"
BATTLE_EARTHQUAKE_SE_ID = "battle_earthquake"
EARTHQUAKE_SHAKE_AMPLITUDE = 2
EARTHQUAKE_SHAKE_FRAME_COUNT = 35
TEMPTATION_FLASH_COLOR = 57
BATTLE_BACKGROUND_TINT_FRAME_COUNT = 16
BLACK_WIND_TINT_COLOR = 0x000000
# DA2 palette color 2; ZERO's reordered palette uses gray at that index.
POISON_BREATH_TINT_COLOR = 0x7E2072
# DA2 palette color 30, independent of ZERO's palette ordering.
FIRE_BREATH_TINT_COLOR = 0x990000
BREATH_WAVE_STRIP_HEIGHT = 2
BREATH_WAVE_FRAMES_PER_STEP = 2
BREATH_WAVE_OFFSETS = (0, 3, 4, 3, 0, -3, -4, -3)
ALL_ENEMY_TARGET_COMMANDS = (BattleCommand.IAI, BattleCommand.BREATH)
BATTLE_MONSTER_DEATH_SE_ID = "battle_monster_death"
BOSS_MONSTER_DEATH_DELAY_FRAME_COUNT = 12
MONSTER_REVIVAL_DELAY_FRAME_COUNT = 16
MONSTER_REVIVAL_FADE_FRAME_COUNT = 16
BATTLE_MONSTER_ESCAPE_SE_ID = "battle_monster_escape"
BATTLE_ESCAPE_SE_ID = "battle_escape"
BATTLE_FOCUS_SE_ID = "spell_haste"
BATTLE_HIDE_SE_ID = "battle_hide"
BATTLE_IDENTIFY_SE_ID = "battle_identify"
ATTACK_SLASH_SE_ID = "battle_weapon_slash"
ATTACK_BLUNT_SE_ID = "battle_weapon_blunt"
ATTACK_LIGHT_SE_ID = "battle_weapon_light"
FADE_ESCAPE_BGM_FADE_FRAME_COUNT = DEFAULT_FADE_FRAME_COUNT
PARTY_SPRITE_Y = (64, 92, 120, 148, 176)
# Reuse the battle's otherwise unused dimmed block, as the former actor pulse did.
ACTIVE_PARTY_CURSOR_PALETTE = DIMMED_PALETTE
ACTIVE_PARTY_CURSOR_TARGET_COLOR = 0xFFFFFF
ACTIVE_PARTY_CURSOR_MIN_BASE_RATE = 0.5
ACTIVE_PARTY_CURSOR_CYCLE_FRAME_COUNT = 90
ACTIVE_PARTY_CURSOR_HALF_CYCLE_FRAME_COUNT = ACTIVE_PARTY_CURSOR_CYCLE_FRAME_COUNT // 2
ACTIVE_PARTY_CURSOR_OFFSETS = ((-8, 0), (16, 0), (-8, 24), (16, 24))
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
BATTLE_ACTION_POPUP_HEIGHT = 7
BATTLE_ACTION_POPUP_TEXT_POSITION = (2, 2)
BATTLE_ACTION_POPUP_HORIZONTAL_PADDING_GRID = 4
ESCAPE_CHOICE_WINDOW_GRID = (52, 0, 12, 10)
ESCAPE_CHOICE_TEXT_X = 4
ESCAPE_CHOICE_CURSOR_X = 2
ESCAPE_YES_Y = 2
ESCAPE_NO_Y = 5
COMMAND_GUIDE_WINDOW_GRID = (0, 0, 34, 13)
GLOBAL_COMMAND_WINDOW_GRID = (47, 0, 17, 16)
INPUT_GUIDE_WINDOW_GRID = (48, 56, 16, 4)
ITEM_GUIDE_WINDOW_GRID = (0, 0, 34, 13)
ITEM_WINDOW_GRID = (33, 0, 31, 13)
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
INNER_STEEL_PALETTE = "inner_steel"
INNER_STEEL_TINT_COLOR = 0xFF3333  # DA2's palette color 24
DA2_INNER_STEEL_TINT_FRAMES = 24
DA2_INNER_STEEL_PAUSE_FRAMES = 4
INNER_STEEL_CYCLE_FRAMES = (
    (DA2_INNER_STEEL_TINT_FRAMES + DA2_INNER_STEEL_PAUSE_FRAMES) * FPS // DA2_REFERENCE_FPS
)
DA2_CONFIRM_REPEAT_DELAY_FRAME_COUNT = 10
DA2_CONFIRM_REPEAT_INTERVAL_FRAME_COUNT = 2
BATTLE_CONFIRM_REPEAT_DELAY_FRAME_COUNT = (
    DA2_CONFIRM_REPEAT_DELAY_FRAME_COUNT * FPS // DA2_REFERENCE_FPS
)
BATTLE_CONFIRM_REPEAT_INTERVAL_FRAME_COUNT = (
    DA2_CONFIRM_REPEAT_INTERVAL_FRAME_COUNT * FPS // DA2_REFERENCE_FPS
)
DA2_ESCAPE_RUN_SPEED = 12
ESCAPE_RUN_SPEED = DA2_ESCAPE_RUN_SPEED * DA2_REFERENCE_FPS // FPS
ESCAPE_RUN_DESTINATION_X = SCREEN_WIDTH + 4
ESCAPE_RUN_PATTERN_FRAME_COUNT = FPS // DA2_REFERENCE_FPS
ESCAPE_MEMBER_STAGGER_FRAME_COUNT = 4
DA2_MONSTER_ENTRANCE_SLIDE_STEPS = (8, 8, 7, 7, 6)
DA2_MONSTER_ENTRANCE_STEP_DISTANCE = 24
MONSTER_ENTRANCE_FRAME_COUNTS = tuple(
    step_count * FPS // DA2_REFERENCE_FPS
    for step_count in DA2_MONSTER_ENTRANCE_SLIDE_STEPS
)
REINFORCEMENT_POST_ENTRANCE_WAIT_FRAME_COUNT = 12
PARTY_ENTRANCE_FRAME_COUNT = 10
KNOCKOUT_HANDOFF_HALF_FRAMES = 12
PARTY_ENTRANCE_STAGGER_FRAME_COUNT = 2
PARTY_ENTRANCE_START_X = SCREEN_WIDTH
PARTY_ENTRANCE_OFFSET_Y = -24
PARTY_ENTRANCE_JUMP_HEIGHT = 24
PARTY_ENTRANCE_COMPLETE_FRAME = (
    PARTY_ENTRANCE_FRAME_COUNT + 2 * PARTY_ENTRANCE_STAGGER_FRAME_COUNT
)
DA2_VICTORY_RETURN_SPEED = 4
VICTORY_RETURN_SPEED = 2 * DA2_VICTORY_RETURN_SPEED * DA2_REFERENCE_FPS // FPS
VICTORY_RETURN_START_X = SCREEN_WIDTH
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
# Monster special-action tuning values. Charge accelerates only on approach;
# return movement remains constant-speed. Its return arc scales from the
# actual approach frame count so the longest layout-supported trip reaches
# approximately the configured maximum height.
MONSTER_CHARGE_APPROACH_INITIAL_SPEED = 8
MONSTER_CHARGE_APPROACH_ACCELERATION_INTERVAL = 2
MONSTER_CHARGE_APPROACH_ACCELERATION = 1
MONSTER_CHARGE_RETURN_SPEED = 8
MONSTER_CHARGE_MAX_JUMP_HEIGHT = 64
MONSTER_CHARGE_ATTACK_MULTIPLIER_NUMERATOR = 3
MONSTER_CHARGE_ATTACK_MULTIPLIER_DENOMINATOR = 2
MONSTER_CHARGE_TARGET_CENTER_OFFSET_X = 4
DA2_MONSTER_ESCAPE_SPEED = 16
MONSTER_ESCAPE_SPEED = DA2_MONSTER_ESCAPE_SPEED * DA2_REFERENCE_FPS // FPS
DA2_MONSTER_ESCAPE_START_DELAY_FRAME_COUNT = 3
MONSTER_ESCAPE_START_DELAY_FRAME_COUNT = (
    DA2_MONSTER_ESCAPE_START_DELAY_FRAME_COUNT * FPS // DA2_REFERENCE_FPS
)
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
MONSTER_MISS_FRAME_COUNT = len(DA2_MISS_VERTICAL_OFFSETS) * FPS // DA2_REFERENCE_FPS
MONSTER_DAMAGE_SPRITE_SOURCE_X = 16 * 5
MONSTER_DAMAGE_SHAKE_X = (8, 9)
COVER_POSITION_OFFSET_X = 26
IDENTIFY_EFFECT_SOURCE_Y = 144
IDENTIFY_EFFECT_CENTER_SOURCE_X = 64
IDENTIFY_EFFECT_TILE_SIZE = 16
IDENTIFY_EFFECT_TRANSPARENT_INDEX = TRANSPARENT_INDEX
DA2_IDENTIFY_EFFECT_FRAME_COUNT = 12
IDENTIFY_EFFECT_FRAME_COUNT = DA2_IDENTIFY_EFFECT_FRAME_COUNT * FPS // DA2_REFERENCE_FPS
IDENTIFY_DETAIL_SMALL_WINDOW_GRID = (10, 0, 44)
IDENTIFY_DETAIL_LARGE_WINDOW_GRID = (4, 0, 56)
IDENTIFY_DETAIL_TEXT_X = 2
IDENTIFY_DETAIL_FIRST_Y = 2
IDENTIFY_DETAIL_ROW_HEIGHT = 3
IDENTIFY_DETAIL_SMALL_IMAGE_X = 96
IDENTIFY_DETAIL_LARGE_IMAGE_X = 112
IDENTIFY_DETAIL_IMAGE_Y = -2
IDENTIFIED_MONSTER_HP_LABEL_OFFSET_X = 8
IDENTIFIED_MONSTER_HP_VALUE_OFFSET_X = 20
IDENTIFIED_MONSTER_HP_OFFSET_Y = 2
IDENTIFIED_MONSTER_HP_EDGE_COLOR = 0
DAMAGE_NUMBER_SPRITE_X = 128
DAMAGE_NUMBER_SPRITE_Y = 0
DAMAGE_NUMBER_SPRITE_SIZE = 8
HEALING_NUMBER_SPRITE_Y = DAMAGE_NUMBER_SPRITE_Y + DAMAGE_NUMBER_SPRITE_SIZE
AFFINITY_ICON_SOURCE_X = 232
WEAK_ICON_SOURCE_Y = 16
RESIST_ICON_SOURCE_Y = 24
AFFINITY_ICON_WIDTH = 24
AFFINITY_ICON_HEIGHT = 8
VOID_ICON_SOURCE_X = 208
VOID_ICON_SOURCE_Y = 16
AFFINITY_POPUP_FRAME_COUNT = len(DA2_DAMAGE_VERTICAL_OFFSETS) * FPS // DA2_REFERENCE_FPS
TARGET_AFFINITY_BLINK_FRAME_COUNT = 15 * FPS // DA2_REFERENCE_FPS
TARGET_AFFINITY_VISIBLE_FRAME_COUNT = 12 * FPS // DA2_REFERENCE_FPS
CRITICAL_FLASH_COLOR = 33
CRITICAL_FLASH_FRAME_COUNT = 2
CRITICAL_MARKER_SOURCE_X = 204
CRITICAL_MARKER_SOURCE_Y = 24
CRITICAL_MARKER_WIDTH = 28
CRITICAL_MARKER_HEIGHT = 8
CRITICAL_MARKER_FRAME_COUNT = MONSTER_MISS_FRAME_COUNT
STUN_MARKER_SOURCE_X = 208
STUN_MARKER_SOURCE_Y = 8
DEFENSE_DOWN_MARKER_SOURCE_X = 224
DEFENSE_DOWN_MARKER_SOURCE_Y = 8
ADDITIONAL_EFFECT_MARKER_WIDTH = 16
ADDITIONAL_EFFECT_MARKER_HEIGHT = 8
ADDITIONAL_EFFECT_MARKER_FRAME_COUNT = CRITICAL_MARKER_FRAME_COUNT
SLEEP_ICON_SOURCE_X = 32
SLEEP_ICON_SOURCE_Y = 136
SLEEP_ICON_SIZE = 8
SLEEP_ICON_PATTERN_COUNT = 4
SLEEP_ICON_PATTERN_FRAME_COUNT = 4 * FPS // DA2_REFERENCE_FPS
SLEEP_MIN_TURNS = 2
SLEEP_MAX_TURNS = 3
CONFUSE_MIN_TURNS = 2
CONFUSE_MAX_TURNS = 3
CONFUSE_ICON_SOURCE_X = 128
CONFUSE_ICON_SOURCE_Y = 128
CONFUSE_ICON_SIZE = 8
CONFUSE_ICON_PATTERN_COUNT = 4
CONFUSE_ICON_PATTERN_FRAME_COUNT = 4 * FPS // DA2_REFERENCE_FPS
SILENCE_ICON_SOURCE_X = 56
SILENCE_ICON_SOURCE_Y = 16
SILENCE_ICON_SIZE = 8
POISON_ICON_SOURCE_X = 32
POISON_ICON_SOURCE_Y = 16
POISON_ICON_SIZE = 8
POISON_ICON_PATTERN_FRAME_COUNT = 4 * FPS // DA2_REFERENCE_FPS
POISON_ICON_DITHER_RATES = (0.0, 0.5, 1.0, 0.5)
PARALYZE_ICON_SOURCE_X = 40
PARALYZE_ICON_SOURCE_Y = 16
PARALYZE_ICON_SIZE = 8
STUN_ICON_SOURCE_X = 224
STUN_ICON_SOURCE_Y = 16
STUN_ICON_SIZE = 8
MAGIC_SHIELD_ICON_SOURCE_X = 128
MAGIC_SHIELD_ICON_SOURCE_Y = 136
MAGIC_SHIELD_ICON_PATTERN_COUNT = 3
MAGIC_SHIELD_ICON_PATTERN_FRAME_COUNT = 3 * FPS // DA2_REFERENCE_FPS
MONSTER_CONDITION_ICON_OFFSET_X = 24
MONSTER_CONDITION_ICON_FIELDS = (
    "poisoned",
    "sleeping",
    "confused",
    "silenced",
    "stunned",
    "defense_modifier",
    "speed_modifier",
    "magic_shield",
)
PARTY_CONDITION_ICON_OFFSET_X = 12
PARTY_CONDITION_ICON_FIELDS = (
    "silenced",
    "poisoned",
    "sleeping",
    "confused",
    "paralyzed",
    "stunned",
    "magic_shield",
)
SPEED_ICON_SOURCE_X = 96
SPEED_ICON_POSITIVE_SOURCE_Y = 128
SPEED_ICON_NEGATIVE_SOURCE_Y = 136
SPEED_ICON_SIZE = 8
SPEED_ICON_PATTERN_COUNT = 4
SLOW_ICON_PATTERN_FRAME_COUNT = 8 * FPS // DA2_REFERENCE_FPS
HASTE_ICON_PATTERN_FRAME_COUNTS = (
    4 * FPS // DA2_REFERENCE_FPS,
    2 * FPS // DA2_REFERENCE_FPS,
)
SPEED_ICON_TRANSPARENT_INDEX = TRANSPARENT_INDEX
PROTECTION_ICON_SOURCE_X = 64
PROTECTION_ICON_SOURCE_Y = 128
DEFENSE_DOWN_ICON_SOURCE_Y = 136
PROTECTION_ICON_SIZE = 8
PROTECTION_ICON_PATTERN_COUNT = 3
PROTECTION_ICON_PATTERN_FRAME_COUNTS = (
    6 * FPS // DA2_REFERENCE_FPS,
    3 * FPS // DA2_REFERENCE_FPS,
)
DEFENSE_DOWN_ICON_PATTERN_FRAME_COUNT = 6 * FPS // DA2_REFERENCE_FPS
PROTECTION_ICON_NAME_OFFSET_X = -PROTECTION_ICON_SIZE
MISS_SPRITE_SOURCE_X = DAMAGE_NUMBER_SPRITE_X + DAMAGE_NUMBER_SPRITE_SIZE * 10
MISS_SPRITE_WIDTH = 16
UNSELECTABLE_TARGET_PALETTE = "unselectable_target"
UNSELECTABLE_TARGET_PALETTE_BASE_RATE = 0.5
FORMATION_MOVE_FRAME_COUNT = 8
FORMATION_WALK_PATTERN_FRAME_COUNT = FPS // DA2_REFERENCE_FPS
HIDE_PRESENTATION_FRAME_COUNT = 7 * FPS // DA2_REFERENCE_FPS
HIDE_REFERENCE_OFFSETS = (
    (0, 0),
    (10, -4),
    (20, -7),
    (30, -9),
    (40, -10),
    (50, -10),
    (60, -9),
)
COMMAND_GUIDE_DELAY_FRAME_COUNT = 30 * FPS // DA2_REFERENCE_FPS
FORMATION_SPRITE_STEP_X = 16
PARTY_SPRITE_WIDTH = 16
NEAR_DEATH_SPRITE_SOURCE_X = 16 * 6
DEFEND_SPRITE_SOURCE_X = 16 * 7
DEAD_SPRITE_SOURCE_X = 16 * 9
DEAD_SPRITE_WIDTH = 32
ACTION_MOVE_DISTANCE = 16
DA2_ACTION_MOVE_SPEED = 4
ACTION_MOVE_SPEED = DA2_ACTION_MOVE_SPEED * DA2_REFERENCE_FPS // FPS
BATTLE_POPUP_FRAME_COUNT = 30 * FPS // DA2_REFERENCE_FPS
MONSTER_SPELL_FAILURE_FRAME_COUNT = 12 * FPS // DA2_REFERENCE_FPS
MONSTER_DEFEND_WAIT_FRAME_COUNT = 18 * FPS // DA2_REFERENCE_FPS
BLACK_WIND_EFFECT_DELAY = 4 * FPS // DA2_REFERENCE_FPS
BLACK_WIND_RESULT_FRAME = 20 * FPS // DA2_REFERENCE_FPS
SPELL_REFLECTION_CAST_WAIT_FRAME_COUNT = 6 * FPS // DA2_REFERENCE_FPS
FOCUS_PRESENTATION_FRAME_COUNT = 36
FOCUS_EFFECT_WIDTH = 16
FOCUS_EFFECT_HEIGHT = 32
FOCUS_ACTIVATION_EFFECT_SOURCE_Y = 160
FOCUS_ACTIVATION_EFFECT_PATTERN_COUNT = 4
FOCUS_ACTIVATION_EFFECT_PATTERN_FRAME_COUNT = 6
FOCUS_WAIT_EFFECT_DELAY_FRAME_COUNT = 6
FOCUS_WAIT_EFFECT_SOURCE_Y = 192
FOCUS_WAIT_EFFECT_WIDTH = 32
FOCUS_WAIT_EFFECT_PATTERN_COUNT = 3
FOCUS_WAIT_EFFECT_PATTERN_FRAME_COUNT = 12
FOCUS_WAIT_EFFECT_FLOATING_OFFSET_Y = 4
FOCUS_ATTACK_MULTIPLIER = 2
SPELL_CAST_SPRITE_SOURCE_X = DEFEND_SPRITE_SOURCE_X
SPELL_POST_EFFECT_WAIT_FRAME_COUNT = 12
MISSED_ACTION_RETURN_WAIT_FRAME_COUNT = 18
SPELL_TARGET_INTERVAL_FRAME_COUNT = 2 * FPS // DA2_REFERENCE_FPS
ATTACK_POSE_RAISE_FRAME_COUNT = 3
ATTACK_POSE_SWING_FRAME_COUNT = 8
ATTACK_MOTION_FRAME_COUNT = (
    ATTACK_POSE_RAISE_FRAME_COUNT + ATTACK_POSE_SWING_FRAME_COUNT
)
THROWING_PROJECTILE_SPEED = 16
THROWING_PROJECTILE_PATTERN_FRAME_COUNT = FPS // DA2_REFERENCE_FPS
DUAL_WIELD_ATTACK_INTERVAL_FRAME_COUNT = 3
MONSTER_DOUBLE_ATTACK_HIT_INTERVAL = (
    ATTACK_MOTION_FRAME_COUNT + DUAL_WIELD_ATTACK_INTERVAL_FRAME_COUNT
)
ATTACK_HIT_PATTERN_COUNT = 3
ATTACK_HIT_PATTERN_FRAME_COUNT = 5
ATTACK_HIT_FRAME_COUNT = ATTACK_HIT_PATTERN_COUNT * ATTACK_HIT_PATTERN_FRAME_COUNT
ATTACK_HIT_START_FRAME = ATTACK_POSE_RAISE_FRAME_COUNT
ATTACK_DAMAGE_FRAME_COUNT = DAMAGE_POPUP_FRAME_COUNT
ATTACK_RETURN_JUMP_FRAME_COUNT = 8
ATTACK_RETURN_JUMP_HEIGHT = 8
ATTACK_FORWARD_JUMP_HEIGHT = 8
JUMP_ATTACK_RETURN_WAIT_FRAME_COUNT = 6
FOCUSED_ATTACK_RETURN_WAIT_FRAME_COUNT = 18
ATTACK_LANDING_GUARD_FRAME_COUNT = 6
AIM_HIT_VALUE_BONUS = 100
AIM_GAUGE_ADJUSTMENT = -16.0
IAI_GAUGE_ADJUSTMENT = -32.0
IAI_TARGET_STAGGER_FRAME_COUNT = 2
AIM_GUARD_WAIT_FRAME_COUNT = 12
AIM_RETICLE_START_DISTANCE = 32
AIM_RETICLE_END_DISTANCE = 8
AIM_RETICLE_MOVE_SPEED = 6
AIM_RETICLE_MOVE_FRAME_COUNT = (
    AIM_RETICLE_START_DISTANCE - AIM_RETICLE_END_DISTANCE
) // AIM_RETICLE_MOVE_SPEED
AIM_RETICLE_START_FRAME = AIM_GUARD_WAIT_FRAME_COUNT
AIM_RETICLE_END_FRAME = AIM_RETICLE_START_FRAME + AIM_RETICLE_MOVE_FRAME_COUNT
AIM_RETICLE_HOLD_FRAME_COUNT = 6
AIM_ATTACK_HIT_START_FRAME = AIM_RETICLE_END_FRAME + AIM_RETICLE_HOLD_FRAME_COUNT
AIM_RETICLE_CORNER_SIZE = 8
AIM_RETICLE_CORNER_SOURCES = (
    (0, 128, -1, -1),
    (8, 128, 1, -1),
    (0, 136, -1, 1),
    (8, 136, 1, 1),
)
AIM_RETICLE_CENTER_SOURCE = (16, 128)
AIM_RETICLE_CENTER_SIZE = 16
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
CONFUSED_MONSTER_ATTACK_EFFECT_ROW = ATTACK_EFFECT_ROW_BY_SUBTYPE["WAND"]
ATTACK_SE_ID_BY_SUBTYPE = {
    "AXE": ATTACK_SLASH_SE_ID,
    "SWORD": ATTACK_SLASH_SE_ID,
    "KATANA": ATTACK_SLASH_SE_ID,
    "KNIFE": ATTACK_SLASH_SE_ID,
    "HAMMER": ATTACK_BLUNT_SE_ID,
    "WAND": ATTACK_LIGHT_SE_ID,
    "ROD": ATTACK_LIGHT_SE_ID,
    "SPEAR": ATTACK_SLASH_SE_ID,
}
WEAPON_ATTRIBUTE_RESISTANCE = {
    AttackAttribute.FIRE: ResistanceType.FIRE,
    AttackAttribute.FREEZE: ResistanceType.FREEZE,
    AttackAttribute.DARK: ResistanceType.DARK,
}
ADDITIONAL_EFFECT_MARKER_SOURCE = {
    AdditionalEffect.STUN: (STUN_MARKER_SOURCE_X, STUN_MARKER_SOURCE_Y),
    AdditionalEffect.DEFENSE_DOWN: (
        DEFENSE_DOWN_MARKER_SOURCE_X,
        DEFENSE_DOWN_MARKER_SOURCE_Y,
    ),
}
COMMAND_TEXT_KEYS = {
    BattleCommand.ATTACK: "battle.command.attack",
    BattleCommand.AMBUSH: "battle.command.ambush",
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
    BattleCommand.AMBUSH: "battle.guide.ambush",
    BattleCommand.SPELL: "battle.guide.spell",
    BattleCommand.AIM: "battle.guide.aim",
    BattleCommand.HIDE: "battle.guide.hide",
    BattleCommand.IDENTIFY: "battle.guide.identify",
    BattleCommand.PRAY: "battle.guide.pray",
    BattleCommand.COVER: "battle.guide.cover",
    BattleCommand.IAI: "battle.guide.iai",
    BattleCommand.FOCUS: "battle.guide.focus",
    BattleCommand.BREATH: "battle.guide.breath",
    BattleCommand.MP_SHARE: "battle.guide.mp_share",
    BattleCommand.DEFEND: "battle.guide.defend",
    BattleCommand.ITEM: "battle.guide.item",
}
FORMATION_COMMAND_GUIDE_TEXT_KEYS = {
    True: "battle.guide.retreat",
    False: "battle.guide.advance",
}
COMMAND_TEXT_X = (4, 18)
COMMAND_CURSOR_X = (2, 16)
COMMAND_ROW_Y = (2, 5, 8)
GLOBAL_COMMAND_TEXT_X = 4
GLOBAL_COMMAND_CURSOR_X = 2
GLOBAL_COMMAND_ROW_Y = (2, 5, 8, 11)
RecordValue = TypeVar("RecordValue")


def monster_charge_approach_distance(frame_count: int) -> int:
    """Return distance covered by ZERO's accelerating charge approach."""

    if isinstance(frame_count, bool) or not isinstance(frame_count, int):
        raise TypeError("charge frame_count must be an integer")
    if frame_count < 0:
        raise ValueError("charge frame_count must not be negative")
    return sum(
        MONSTER_CHARGE_APPROACH_INITIAL_SPEED
        + frame
        // MONSTER_CHARGE_APPROACH_ACCELERATION_INTERVAL
        * MONSTER_CHARGE_APPROACH_ACCELERATION
        for frame in range(frame_count)
    )


def monster_charge_approach_frame_count(distance: float) -> int:
    """Return frames needed for the accelerating approach to cover distance."""

    if isinstance(distance, bool) or not isinstance(distance, (int, float)):
        raise TypeError("charge distance must be numeric")
    if distance < 0:
        raise ValueError("charge distance must not be negative")
    frame_count = 1
    while monster_charge_approach_distance(frame_count) < distance:
        frame_count += 1
    return frame_count


class BattleDataError(ValueError):
    """Raised when generated battle data cannot form a scene."""


class BattlePhase(StrEnum):
    """Interactive phases implemented by the battle scene."""

    ENTRANCE = "entrance"
    BOSS_INTRO = "boss_intro"
    SURPRISE_NOTICE = "surprise_notice"
    SURPRISE_PREVENTED = "surprise_prevented"
    INITIAL = "initial"
    COMMAND = "command"
    GLOBAL_COMMAND = "global_command"
    AUTO_THINKING = "auto_thinking"
    ITEM = "item"
    SPELL = "spell"
    TARGET = "target"
    COVER_TARGET = "cover_target"
    ACTION_TARGET = "action_target"
    ATTACK_PRESENTATION = "attack_presentation"
    FOCUS_PRESENTATION = "focus_presentation"
    HIDE_PRESENTATION = "hide_presentation"
    IDENTIFY_PRESENTATION = "identify_presentation"
    IDENTIFY_RESULT = "identify_result"
    ACTION_PRESENTATION = "action_presentation"
    ACTION_RETURN = "action_return"
    ESCAPE_CONFIRMATION = "escape_confirmation"
    ESCAPE_MEMBER = "escape_member"
    ESCAPE_MESSAGE = "escape_message"
    ESCAPE = "escape"
    FADE_ESCAPE = "fade_escape"
    FORMATION = "formation"
    MONSTER_DEATH = "monster_death"
    DEFEAT_MESSAGE = "defeat_message"
    KNOCKOUT_HANDOFF = "knockout_handoff"
    TIMELINE = "timeline"
    MONSTER_ACTION = "monster_action"
    VICTORY_SUMMARY = "victory_summary"
    RESULT_TRANSITION = "result_transition"
    RESULT = "result"


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
    TACTICS = "tactics"


class TimelineAnimationPhase(StrEnum):
    """Movement stages between battle turns."""

    DROP = "drop"
    SLIDE = "slide"
    INTERRUPT = "interrupt"


@dataclass
class TimelineRemovalAnimation:
    """Keep removed icons visible while they fall and the remaining gaps close."""

    before: tuple[BattleCharacter | BattleMonster, ...]
    after: tuple[BattleCharacter | BattleMonster, ...]
    elapsed_frame: int = 0


class FormationAnimationCompletion(StrEnum):
    """Continuation to run after manual or automatic row movement."""

    COMPLETE_CURRENT_TURN = "complete_current_turn"
    START_TIMELINE = "start_timeline"
    START_TIMELINE_REMOVAL = "start_timeline_removal"
    ACTIVATE_TIMELINE_HEAD = "activate_timeline_head"
    CONTINUE_MONSTER_ATTACK = "continue_monster_attack"


@dataclass(frozen=True)
class BattleTargetSpellEffect:
    """Bind one effect timeline to the battle target it decorates."""

    target_side: str
    target_index: int
    player: SpellEffectPlayer
    start_frame: int = 0


class _TargetedResult(Protocol):
    @property
    def target_index(self) -> int: ...


TargetedResult = TypeVar("TargetedResult", bound=_TargetedResult)


@dataclass(frozen=True)
class BattleHealingResult:
    """A resolved HEAL value waiting for its DA2-timed application."""

    target_index: int
    amount: int
    cures_ailments: bool
    popup_x: int
    popup_y: int
    target_is_monster: bool = False


@dataclass(frozen=True)
class BattleManaResult:
    """An MP recovery roll waiting for its timed application."""

    target_index: int
    amount: int | None
    popup_x: int
    popup_y: int
    show_rolled_amount: bool = False


@dataclass
class BattleHealingPopup:
    """One non-blocking recovery number animated with DA2's offsets."""

    x: int
    y: int
    amount: int
    elapsed_frame: int = 0

    @property
    def completed(self) -> bool:
        return self.elapsed_frame >= DAMAGE_POPUP_FRAME_COUNT

    def update(self) -> None:
        self.elapsed_frame += 1


@dataclass(frozen=True)
class BattleSpellDamageResult:
    """Resolved DAMAGE magic waiting for its timed application."""

    target_index: int
    damage: int
    affinity: SpellAffinity
    popup_x: int
    popup_y: int
    affinity_x: int
    affinity_y: int
    is_miss: bool = False


@dataclass(frozen=True)
class BattleSleepResult:
    """Resolved SLEEP magic waiting for its timed application."""

    target_index: int
    success: bool
    turns: int
    affinity: SpellAffinity
    popup_x: int
    popup_y: int
    affinity_x: int
    affinity_y: int


@dataclass(frozen=True)
class BattleConfuseResult:
    """Resolved CONFUSE magic waiting for its timed application."""

    target_index: int
    success: bool
    turns: int
    affinity: SpellAffinity
    popup_x: int
    popup_y: int
    affinity_x: int
    affinity_y: int


@dataclass(frozen=True)
class BattleSlowResult:
    """Resolved SLOW magic waiting for its timed application."""

    target_index: int
    success: bool
    popup_x: int
    popup_y: int


@dataclass(frozen=True)
class BattleBreakResult:
    """Resolved BREAK magic waiting for application to a monster."""

    target_index: int
    success: bool
    popup_x: int
    popup_y: int


@dataclass(frozen=True)
class BattlePoisonResult:
    """Resolved poison application waiting for its timed application."""

    target_index: int
    success: bool


@dataclass(frozen=True)
class BattlePartyStunResult:
    target_index: int
    success: bool


@dataclass(frozen=True)
class BattleProtectionResult:
    """One guaranteed PROTECTION stage waiting for its timed application."""

    target_index: int
    target_is_monster: bool = False


@dataclass(frozen=True)
class BattleHasteResult:
    """One guaranteed HASTE stage waiting for its timed application."""

    target_index: int
    target_is_monster: bool = False


@dataclass(frozen=True)
class BattleCureResult:
    """One CURE application waiting for its timed ailment removal."""

    target_index: int


@dataclass(frozen=True)
class BattleReviveResult:
    """One dead ally and authored HP percentage waiting for revival."""

    target_index: int
    hp_percentage: int
    target_is_monster: bool = False


@dataclass(frozen=True)
class BattleSilenceResult:
    """Resolved SILENCE magic waiting for its timed application."""

    target_index: int
    success: bool
    turns: int
    affinity: SpellAffinity
    popup_x: int
    popup_y: int
    affinity_x: int
    affinity_y: int


@dataclass(frozen=True)
class BattlePartySleepResult:
    """Resolved monster SLEEP result waiting for application to a member."""

    target_index: int
    success: bool
    turns: int
    popup_x: int
    popup_y: int


@dataclass(frozen=True)
class BattlePartySilenceResult(BattlePartySleepResult):
    """Resolved monster SILENCE result waiting for application to a member."""


@dataclass(frozen=True)
class BattlePartyConfuseResult:
    """Resolved monster CONFUSE result waiting for application to a member."""

    target_index: int
    success: bool
    turns: int
    popup_x: int
    popup_y: int


@dataclass(frozen=True)
class BattlePartySlowResult:
    """Resolved monster SLOW result waiting for application to a member."""

    target_index: int
    success: bool
    popup_x: int
    popup_y: int


@dataclass(frozen=True)
class BattlePartyBreakResult:
    """Resolved monster BREAK result waiting for application to a member."""

    target_index: int
    success: bool
    popup_x: int
    popup_y: int


@dataclass
class BattleSpellDamagePopup:
    """One non-blocking spell-damage number animated with DA2's offsets."""

    x: int
    y: int
    damage: int
    is_miss: bool = False
    elapsed_frame: int = 0

    @property
    def completed(self) -> bool:
        frame_count = (
            MONSTER_MISS_FRAME_COUNT if self.is_miss else DAMAGE_POPUP_FRAME_COUNT
        )
        return self.elapsed_frame >= frame_count

    def update(self) -> None:
        self.elapsed_frame += 1


@dataclass
class BattleAffinityPopup:
    """A non-blocking DA2-style WEAK or RESIST marker."""

    x: int
    y: int
    affinity: SpellAffinity
    elapsed_frame: int = 0

    @property
    def completed(self) -> bool:
        return self.elapsed_frame >= AFFINITY_POPUP_FRAME_COUNT

    def update(self) -> None:
        self.elapsed_frame += 1


@dataclass(frozen=True)
class BattleConfusedAttackResult:
    """One same-side basic attack forced by confusion."""

    target_side: str
    target_index: int
    damage: int
    is_hit: bool
    popup_x: int
    popup_y: int
    effect_row: int | None
    additional_effects: tuple[AdditionalEffect, ...] = ()
    drain_actor_index: int | None = None
    is_critical: bool = False


@dataclass
class BattleMonsterDrainPresentation:
    """DA2's six-step flight and delayed recovery number for one enemy hit."""

    actor_index: int
    amount: int
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    elapsed_frame: int = 0
    healing_applied: bool = False
    popup_started: bool = False


@dataclass
class BattleActionPresentation:
    """Own the visual layers that must finish before a turn advances.

    Each target's effects and results can start at a different frame. Timed
    popups continue independently after the action ends.
    """

    spell_effects: tuple[BattleTargetSpellEffect, ...]
    healing_results: tuple[BattleHealingResult, ...] = ()
    mana_results: tuple[BattleManaResult, ...] = ()
    damage_results: tuple[BattleSpellDamageResult, ...] = ()
    sleep_results: tuple[BattleSleepResult, ...] = ()
    confuse_results: tuple[BattleConfuseResult, ...] = ()
    poison_results: tuple[BattlePoisonResult, ...] = ()
    slow_results: tuple[BattleSlowResult, ...] = ()
    break_results: tuple[BattleBreakResult, ...] = ()
    protection_results: tuple[BattleProtectionResult, ...] = ()
    haste_results: tuple[BattleHasteResult, ...] = ()
    magic_shield_targets: tuple[tuple[str, int], ...] = ()
    purge_targets: tuple[tuple[str, int], ...] = ()
    cure_results: tuple[BattleCureResult, ...] = ()
    revive_results: tuple[BattleReviveResult, ...] = ()
    silence_results: tuple[BattleSilenceResult, ...] = ()
    party_damage_results: tuple[BattleSpellDamageResult, ...] = ()
    party_poison_results: tuple[BattlePoisonResult, ...] = ()
    party_stun_results: tuple[BattlePartyStunResult, ...] = ()
    black_wind_targets: tuple[int, ...] = ()
    earthquake: bool = False
    shake_offset: tuple[int, int] = (0, 0)
    background_tint_color: int | None = None
    wave_enemy_sprites: bool = False
    party_silence_results: tuple[BattlePartySilenceResult, ...] = ()
    party_sleep_results: tuple[BattlePartySleepResult, ...] = ()
    party_confuse_results: tuple[BattlePartyConfuseResult, ...] = ()
    party_slow_results: tuple[BattlePartySlowResult, ...] = ()
    party_break_results: tuple[BattlePartyBreakResult, ...] = ()
    confused_attack_results: tuple[BattleConfusedAttackResult, ...] = ()
    drain_party_index: int | None = None
    drain_monster_index: int | None = None
    fade_escape: bool = False
    result_start_frame: int = 0
    target_result_frames: dict[tuple[str, int], int] = field(default_factory=dict)
    applied_spell_targets: set[tuple[str, int]] = field(default_factory=set)
    pending_affinity_popups: dict[int, list[BattleAffinityPopup]] = field(
        default_factory=dict,
    )
    post_effect_wait_frame_count: int = SPELL_POST_EFFECT_WAIT_FRAME_COUNT
    results_applied: bool = False
    elapsed_frame: int = 0
    post_effect_elapsed_frame: int = 0
    screen_flash: SpellScreenFlash | None = None
    screen_flash_start_frame: int = 0

    @property
    def effects_complete(self) -> bool:
        return all(effect.player.completed for effect in self.spell_effects)

    def schedule_spell_results(
        self, target_start_frames: Mapping[tuple[str, int], int], *,
        overlap_frame_count: int = SPELL_RESULT_OVERLAP_FRAME_COUNT,
    ) -> None:
        self.target_result_frames = dict(target_start_frames)
        for effect in self.spell_effects:
            if effect.player.definition.spell_key != SPELL_REFLECT_EFFECT_KEY:
                target = effect.target_side, effect.target_index
                impact_delay = max(
                    0, effect.player.definition.total_frames - overlap_frame_count,
                )
                self.target_result_frames[target] = effect.start_frame + impact_delay
        self.result_start_frame = min(self.target_result_frames.values(), default=0)

    def monster_revival_opacity(self, index: int) -> float:
        if not any(result.target_is_monster and result.target_index == index for result in self.revive_results):
            return 1.0
        start = self.target_result_frames[("enemy", index)] + MONSTER_REVIVAL_DELAY_FRAME_COUNT
        return min(1.0, max(0.0, (self.elapsed_frame - start) / MONSTER_REVIVAL_FADE_FRAME_COUNT))

    def party_damage_motion_visible(self, index: int) -> bool:
        visible = (
            self.elapsed_frame < self.result_start_frame
            if self.background_tint_color is not None
            else self.results_applied or ("ally", index) in self.applied_spell_targets
        )
        return visible and any(
            result.target_index == index
            and not result.is_miss
            and (self.background_tint_color is not None or self.earthquake or result.damage > 0)
            for result in self.party_damage_results
        )

    @property
    def background_tint_progress(self) -> float:
        duration = BATTLE_BACKGROUND_TINT_FRAME_COUNT
        if self.elapsed_frame >= self.result_start_frame:
            return max(0.0, 1 - (self.elapsed_frame - self.result_start_frame) / duration)
        return min(self.elapsed_frame / duration, 1.0)

    @property
    def is_complete(self) -> bool:
        return (
            self.effects_complete
            and self.post_effect_elapsed_frame >= self.post_effect_wait_frame_count
            and (not self.target_result_frames or self.results_applied)
            and (
                self.background_tint_color is None
                or self.elapsed_frame >= self.result_start_frame + BATTLE_BACKGROUND_TINT_FRAME_COUNT
            )
            and (
                self.screen_flash is None
                or self.elapsed_frame >= self.screen_flash_start_frame + self.screen_flash.end_frame
            )
        )

    def update(self) -> None:
        effects_were_complete = self.effects_complete
        self.elapsed_frame += 1
        for effect in self.spell_effects:
            if self.elapsed_frame > effect.start_frame:
                effect.player.update()
        if effects_were_complete:
            self.post_effect_elapsed_frame += 1


def throwing_projectile_frame_count(
    start: tuple[int, int],
    end: tuple[int, int],
) -> int:
    """Return endpoint-inclusive frames for one constant-speed throw."""

    distance = hypot(end[0] - start[0], end[1] - start[1])
    return max(2, ceil(distance / THROWING_PROJECTILE_SPEED) + 1)


def throwing_projectile_position(
    start: tuple[int, int],
    end: tuple[int, int],
    elapsed_frame: int,
) -> tuple[int, int]:
    """Advance a projectile at a fixed Euclidean speed, clamped at its target."""

    offset_x = end[0] - start[0]
    offset_y = end[1] - start[1]
    distance = hypot(offset_x, offset_y)
    if distance == 0:
        return end
    travelled = min(distance, elapsed_frame * THROWING_PROJECTILE_SPEED)
    return (
        round(start[0] + offset_x * travelled / distance),
        round(start[1] + offset_y * travelled / distance),
    )


@dataclass
class BattleAttackStrike:
    """Own one independently resolved hand strike on the shared timeline."""

    damage: int
    poses: tuple[AttackPoseDefinition, ...]
    effect_row: int | None
    motion_start_frame: int
    hit_start_frame: int
    pose_change_frame: int | None = None
    projectile_sprites: tuple[AttackWeaponSprite, ...] = ()
    projectile_frame_count: int = 0
    effect_flip_x: bool = False
    is_hit: bool = True
    is_critical: bool = False
    is_weak: bool = False
    additional_effects: tuple[AdditionalEffect, ...] = ()
    sound_effect_id: str = ATTACK_SLASH_SE_ID
    target_index: int | None = None
    damage_applied: bool = False
    affinity_popup_started: bool = False
    drains_hp: bool = False

    def pose_at(self, elapsed_frame: int) -> AttackPoseDefinition | None:
        if (
            not self.poses
            or elapsed_frame < self.motion_start_frame
            or elapsed_frame >= self.pose_end_frame
        ):
            return None
        if len(self.poses) == 1 or elapsed_frame < self.swing_start_frame:
            return self.poses[0]
        return self.poses[1]

    @property
    def swing_start_frame(self) -> int:
        return (
            self.hit_start_frame
            if self.pose_change_frame is None
            else self.pose_change_frame
        )

    @property
    def pose_end_frame(self) -> int:
        return self.swing_start_frame + ATTACK_POSE_SWING_FRAME_COUNT

    @property
    def projectile_start_frame(self) -> int | None:
        return (
            self.pose_end_frame
            if self.projectile_sprites and self.projectile_frame_count > 0
            else None
        )

    @property
    def projectile_end_frame(self) -> int | None:
        start_frame = self.projectile_start_frame
        if start_frame is None:
            return None
        return start_frame + self.projectile_frame_count

    def projectile_at(self, elapsed_frame: int) -> AttackWeaponSprite | None:
        start_frame = self.projectile_start_frame
        end_frame = self.projectile_end_frame
        if (
            start_frame is None
            or end_frame is None
            or not start_frame <= elapsed_frame < end_frame
        ):
            return None
        pattern = (
            (elapsed_frame - start_frame) // THROWING_PROJECTILE_PATTERN_FRAME_COUNT
        ) % len(self.projectile_sprites)
        return self.projectile_sprites[pattern]

    @property
    def motion_end_frame(self) -> int:
        return self.projectile_end_frame or self.pose_end_frame

    def hit_elapsed_frame(self, elapsed_frame: int) -> int:
        return elapsed_frame - self.hit_start_frame

    def damage_popup_elapsed_frame(self, elapsed_frame: int) -> int:
        delay = ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT if self.is_hit else 0
        return self.hit_elapsed_frame(elapsed_frame) - delay

    def result_complete(self, elapsed_frame: int) -> bool:
        frame_count = (
            ATTACK_DAMAGE_FRAME_COUNT if self.is_hit else MONSTER_MISS_FRAME_COUNT
        )
        return self.damage_popup_elapsed_frame(elapsed_frame) >= frame_count


@dataclass
class BattleAttackPresentation:
    """Own one party member's DA2-timed one- or two-weapon attack."""

    target_index: int
    strikes: tuple[BattleAttackStrike, ...]
    target_side: str = "enemy"
    is_aimed: bool = False
    is_focused: bool = False
    is_iai: bool = False
    elapsed_frame: int = 0
    return_started: bool = False
    progression_recorded: bool = False
    sound_played: bool = False
    is_counter: bool = False

    def __post_init__(self) -> None:
        if not self.strikes:
            raise ValueError("an attack presentation requires at least one strike")
        if self.target_side not in ("ally", "enemy"):
            raise ValueError("attack target side must be ally or enemy")

    @property
    def pose(self) -> AttackPoseDefinition | None:
        if self.aim_guard_pose_visible:
            return None
        for strike in reversed(self.strikes):
            if (pose := strike.pose_at(self.elapsed_frame)) is not None:
                return pose
        return None

    @property
    def hit_start_frame(self) -> int:
        return self.strikes[0].hit_start_frame

    @property
    def motion_frame_count(self) -> int:
        return self.strikes[-1].motion_end_frame

    @property
    def hit_elapsed_frame(self) -> int:
        return self.strikes[0].hit_elapsed_frame(self.elapsed_frame)

    @property
    def aim_reticle_distance(self) -> int | None:
        if (
            not self.is_aimed
            or self.elapsed_frame < AIM_RETICLE_START_FRAME
            or self.elapsed_frame >= self.hit_start_frame
        ):
            return None
        moved = min(
            (self.elapsed_frame - AIM_RETICLE_START_FRAME) * AIM_RETICLE_MOVE_SPEED,
            AIM_RETICLE_START_DISTANCE - AIM_RETICLE_END_DISTANCE,
        )
        return AIM_RETICLE_START_DISTANCE - moved

    @property
    def aim_reticle_moving(self) -> bool:
        return (
            self.is_aimed
            and AIM_RETICLE_START_FRAME <= self.elapsed_frame < AIM_RETICLE_END_FRAME
        )

    @property
    def aim_guard_pose_visible(self) -> bool:
        return self.is_aimed and self.elapsed_frame < AIM_RETICLE_END_FRAME

    @property
    def aim_reticle_center_visible(self) -> bool:
        return (
            self.is_aimed
            and AIM_RETICLE_END_FRAME <= self.elapsed_frame < self.hit_start_frame
        )

    @property
    def damage_popup_elapsed_frame(self) -> int:
        return self.strikes[0].damage_popup_elapsed_frame(self.elapsed_frame)

    @property
    def result_complete(self) -> bool:
        return all(
            strike.result_complete(self.elapsed_frame) for strike in self.strikes
        )

    def latest_result_strike(self) -> BattleAttackStrike | None:
        """Return the newest strike with an active result-marker interval."""

        for strike in reversed(self.strikes):
            popup_frame = strike.damage_popup_elapsed_frame(self.elapsed_frame)
            if strike.damage_applied and 0 <= popup_frame < CRITICAL_MARKER_FRAME_COUNT:
                return strike
        return None

    def visible_result_strikes(self) -> tuple[BattleAttackStrike, ...]:
        """Expose simultaneous Iai results while retaining dual-wield priority."""

        if not self.is_iai:
            latest = self.latest_result_strike()
            return () if latest is None else (latest,)
        return tuple(
            strike
            for strike in self.strikes
            if strike.damage_applied
            and 0
            <= strike.damage_popup_elapsed_frame(self.elapsed_frame)
            < CRITICAL_MARKER_FRAME_COUNT
        )


@dataclass(frozen=True)
class BattleMonsterAttackPopup:
    """The first hit's display at the start of a monster's follow-up."""

    target_index: int
    damage: int
    is_critical: bool
    position: tuple[int, int]
    elapsed_frame: int


@dataclass
class BattleMonsterChargePresentation:
    """Own ZERO's approach, impact, and parabolic charge return."""

    actor_index: int
    target_index: int
    damage: int
    is_critical: bool
    start_x: int
    start_y: int
    target_x: int
    target_y: int
    travel_distance: float
    approach_frame_count: int
    return_frame_count: int
    jump_height: int
    additional_effects: tuple[AdditionalEffect, ...] = ()
    draining: bool = False
    tribe_resisted: bool = False
    elapsed_frame: int = 0
    damage_applied: bool = False

    def __post_init__(self) -> None:
        if self.approach_frame_count <= 0:
            raise ValueError("charge approach_frame_count must be positive")
        if self.return_frame_count <= 0:
            raise ValueError("charge return_frame_count must be positive")
        if self.travel_distance < 0:
            raise ValueError("charge travel_distance must not be negative")
        if self.jump_height < 0:
            raise ValueError("charge jump_height must not be negative")

    @property
    def impact_reached(self) -> bool:
        return self.elapsed_frame >= self.approach_frame_count

    @property
    def motion_complete(self) -> bool:
        return self.elapsed_frame >= (
            self.approach_frame_count + self.return_frame_count
        )

    @property
    def result_elapsed_frame(self) -> int:
        return self.elapsed_frame - self.approach_frame_count

    @property
    def result_complete(self) -> bool:
        frame_count = (
            MONSTER_MISS_FRAME_COUNT if self.damage == 0 else MONSTER_DAMAGE_FRAME_COUNT
        )
        return self.result_elapsed_frame >= frame_count

    @property
    def completed(self) -> bool:
        return self.motion_complete and self.result_complete

    def position(self) -> tuple[int, int]:
        """Return the current straight approach or parabolic return position."""

        approach_duration = self.approach_frame_count
        if self.elapsed_frame <= approach_duration:
            if self.elapsed_frame >= approach_duration or self.travel_distance == 0:
                return self.target_x, self.target_y
            traveled = min(
                monster_charge_approach_distance(self.elapsed_frame),
                self.travel_distance,
            )
            progress = traveled / self.travel_distance
            x = round(self.start_x + (self.target_x - self.start_x) * progress)
            y = round(self.start_y + (self.target_y - self.start_y) * progress)
            return x, y

        return_duration = self.return_frame_count
        elapsed = min(self.elapsed_frame - approach_duration, return_duration)
        x = self.target_x + (self.start_x - self.target_x) * elapsed // return_duration
        linear_y = (
            self.target_y + (self.start_y - self.target_y) * elapsed // return_duration
        )
        remaining = return_duration - elapsed
        jump = 4 * self.jump_height * elapsed * remaining // (return_duration**2)
        return x, linear_y - jump


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
        """Return the member's battle-modified effective agility."""

        return self.member.effective_agility


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
    is_boss: bool = False
    additional_effects: tuple[AdditionalEffect, ...] = ()
    special_actions: tuple[MonsterSpecialAction, ...] = ()
    level: int = 1
    early_appear: int = 0
    max_occurrence: int = 1
    gold: int = 0
    treasure_item_key: str = ""
    treasure_rate: int = 0
    max_mp: int = 0
    magic: int = 0
    intelligence: int = 0
    spell_keys: tuple[str, ...] = ()
    combat_stats: MonsterCombatStats = field(
        default_factory=lambda: MonsterCombatStats(0, 0, 0, 0)
    )
    weaknesses: frozenset[ResistanceType] = field(default_factory=frozenset)
    resistances: frozenset[ResistanceType] = field(default_factory=frozenset)
    shadow: int = 0
    tribe: MonsterTribe | None = None
    initial_is_front_row: bool = field(init=False)

    @property
    def spell_resistances(self) -> frozenset[ResistanceType]:
        return spell_resistances(self.resistances, self.state.magic_shield)

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
        try:
            tribe = MonsterTribe(record.get("tribe"))
        except (TypeError, ValueError) as error:
            raise BattleDataError(f"{key}.tribe is invalid") from error
        image_id = record.get("image_id")
        if isinstance(image_id, bool) or not isinstance(image_id, (str, int)):
            raise BattleDataError(f"{key}.image_id must be a string or integer")
        image_id_text = str(image_id)
        if not image_id_text:
            raise BattleDataError(f"{key}.image_id must not be empty")
        weakness = record.get("weakness")
        if not isinstance(weakness, str):
            raise BattleDataError(f"{key}.weakness must be a string")
        tolerance = record.get("tolerance")
        if not isinstance(tolerance, str):
            raise BattleDataError(f"{key}.tolerance must be a string")
        try:
            shadow = monster_shadow_from_record(record)
        except MonsterDataError as error:
            raise BattleDataError(f"{key}.shadow must be 0, 1 or 2") from error
        is_boss = record.get("is_boss")
        if (
            isinstance(is_boss, bool)
            or not isinstance(is_boss, int)
            or is_boss not in (0, 1)
        ):
            raise BattleDataError(f"{key}.is_boss must be 0 or 1")
        try:
            additional_effects = monster_additional_effects_from_codes(record.get("extra"))
        except ItemDataError as error:
            raise BattleDataError(f"{key}.extra is invalid") from error
        treasure_item_key = _required_text(record, "treasure_item", key)
        treasure_rate = _required_nonnegative_integer(record, "treasure_rate", key)
        if treasure_rate > 16:
            raise BattleDataError(f"{key}.treasure_rate must be from 0 to 16")
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
            is_boss=bool(is_boss),
            additional_effects=additional_effects,
            special_actions=monster_special_actions_from_record(record),
            level=_required_nonnegative_integer(record, "lv", key),
            early_appear=_required_nonnegative_integer(record, "early_appear", key),
            max_occurrence=_required_positive_integer(record, "max_occ", key),
            gold=_required_nonnegative_integer(record, "gold", key),
            treasure_item_key=treasure_item_key,
            treasure_rate=treasure_rate,
            max_mp=_required_nonnegative_integer(record, "mmp", key),
            magic=_required_nonnegative_integer(record, "mag", key),
            intelligence=_required_nonnegative_integer(record, "int", key),
            spell_keys=monster_spell_keys_from_record(record),
            weaknesses=resistances_from_tolerance(weakness),
            resistances=resistances_from_tolerance(tolerance),
            shadow=shadow,
            tribe=tribe,
        )

    @property
    def is_shadow(self) -> bool:
        """Keep both flying modes effective for spells and identification."""

        return self.shadow != 0

    @property
    def image_resource_id(self) -> str:
        return f"monsters/{self.image_id}"

    def display_name(self, localizer: Localizer) -> str:
        return localizer.text(self.names, "name")

    @property
    def is_alive(self) -> bool:
        return self.state.is_alive

    @property
    def effective_agility(self) -> int:
        """Return master agility with ZERO's current battle modifier."""

        return modified_agility(self.agility, self.state.speed_modifier)

    @property
    def effective_defense(self) -> int:
        """Return master defense with ZERO's current battle modifier."""

        return self.state.modified_defense(self.combat_stats.defense)

    def restore(self) -> None:
        """Restore mutable battle values to this encounter's initial state."""

        self.state.restore()
        self.is_front_row = self.initial_is_front_row


def identify_detail_texts(
    *,
    number: int,
    definition: MonsterDefinition,
    revealed_fields: set[str],
    items: Mapping[str, Item],
    texts: TextCatalog,
    localizer: Localizer,
    text_factory: LocalizedWindowTextFactory,
) -> tuple[WindowText, ...]:
    """Place bestiary information in DA2's battle Identify layout."""

    return monster_detail_texts(
        number=number,
        monster=definition,
        revealed_fields=revealed_fields,
        items=items,
        texts=texts,
        localizer=localizer,
        text_factory=text_factory,
        text_x=IDENTIFY_DETAIL_TEXT_X,
        first_y=IDENTIFY_DETAIL_FIRST_Y,
        row_height=IDENTIFY_DETAIL_ROW_HEIGHT,
    )


def identify_detail_layout(
    monster: BattleMonster,
    line_count: int,
) -> tuple[tuple[int, int, int, int], int]:
    """Translate DA2's dynamic Identify window and image offset to ZERO's grid."""

    if isinstance(line_count, bool) or not isinstance(line_count, int):
        raise TypeError("line_count must be an integer")
    if line_count <= 0:
        raise ValueError("line_count must be positive")
    content_rows = max(line_count - 1, monster.height // 16)
    x, y, width = (
        IDENTIFY_DETAIL_SMALL_WINDOW_GRID
        if monster.width <= 64
        else IDENTIFY_DETAIL_LARGE_WINDOW_GRID
    )
    image_x = (
        IDENTIFY_DETAIL_SMALL_IMAGE_X
        if monster.width <= 64
        else IDENTIFY_DETAIL_LARGE_IMAGE_X
    )
    return (x, y, width, content_rows * IDENTIFY_DETAIL_ROW_HEIGHT + 6), image_x


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
    """Immutable lineup and rules supplied by an encounter source or test fixture."""

    monster_keys: tuple[str, ...]
    surprise_enabled: bool = False
    escape_command_enabled: bool = True

    def __post_init__(self) -> None:
        if not 1 <= len(self.monster_keys) <= len(MONSTER_POSITIONS):
            raise ValueError(
                f"battle encounter must contain 1 to {len(MONSTER_POSITIONS)} monsters"
            )
        if not all(isinstance(key, str) and key for key in self.monster_keys):
            raise TypeError("battle encounter monster keys must be non-empty strings")
        if not isinstance(self.surprise_enabled, bool):
            raise TypeError("surprise_enabled must be a boolean")
        if not isinstance(self.escape_command_enabled, bool):
            raise TypeError("escape_command_enabled must be a boolean")


def _battle_start_front_monster_indexes(
    slot_indexes: Sequence[int],
) -> frozenset[int]:
    """Resolve rows from display slots, promoting a lineup with no front slot."""

    front_indexes = frozenset(
        index for index, slot_index in enumerate(slot_indexes) if slot_index >= 2
    )
    if front_indexes:
        return front_indexes
    return frozenset(range(len(slot_indexes)))


def _battle_bgm_id(is_boss: bool) -> str:
    return BATTLE_BOSS_BGM_ID if is_boss else BATTLE_BGM_ID


def monster_slot_indexes(monsters: Sequence[object]) -> tuple[int, ...]:
    """Select presentation slots for the encountered monster image sizes."""

    return monster_layout(monsters).slot_indexes


class BattleScene:
    """Own one battle's input, temporary state, update order, and rendering."""

    proficiency_level_limit: int | None = None
    experience_limit: int | None = None
    character_states: Mapping[str, Member] | None = None
    next_knockout_bgm_id: str | None = None

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
        save_data: SaveData,
        result_party: tuple[Member, ...],
        return_bgm_id: str | None,
        return_bgm_start_sec: float = 0.0,
        command_memory: BattleCommandMemory | None = None,
        on_invalid_action: Callable[[], None] | None = None,
        proficiency_level_limit: int | None = None,
        experience_limit: int | None = None,
        character_states: Mapping[str, Member] | None = None,
        knockout_party: tuple[Member, ...] = (),
        next_knockout_enemy_key: str | None = None,
    ) -> BattleScene:
        """Build a production scene from one game session and encounter."""

        text_factory = LocalizedWindowTextFactory.from_language(fonts, settings.language)
        windows = WindowFactory(
            fonts.font_for(settings.language),
            text_style=(
                text_factory.apply
                if settings.language is Language.SIMPLIFIED_CHINESE
                else None
            ),
        )
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
            save_data=save_data,
            result_party=result_party,
            return_bgm_id=return_bgm_id,
            return_bgm_start_sec=return_bgm_start_sec,
            fonts=fonts,
            attack_poses=load_attack_poses(APP_ROOT / "effects" / "attack_poses.json"),
            spell_effect_renderer=SpellEffectRenderer(
                resources,
                palette_shifter,
            ),
            spell_effects=load_spell_effects(APP_ROOT / "effects" / "spells.json"),
            command_memory=command_memory,
            on_invalid_action=on_invalid_action,
            proficiency_level_limit=proficiency_level_limit,
            experience_limit=experience_limit,
            character_states=character_states,
            knockout_party=knockout_party,
            next_knockout_enemy_key=next_knockout_enemy_key,
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
        save_data: SaveData | None = None,
        result_party: tuple[Member, ...] | None = None,
        return_bgm_id: str | None = None,
        return_bgm_start_sec: float = 0.0,
        fonts: FontResources | None = None,
        command_memory: BattleCommandMemory | None = None,
        on_invalid_action: Callable[[], None] | None = None,
        proficiency_level_limit: int | None = None,
        experience_limit: int | None = None,
        character_states: Mapping[str, Member] | None = None,
        knockout_party: tuple[Member, ...] = (),
        next_knockout_enemy_key: str | None = None,
    ) -> None:
        if not isinstance(settings, Settings):
            raise TypeError("settings must be Settings")
        if command_memory is not None and not isinstance(
            command_memory, BattleCommandMemory
        ):
            raise TypeError("command_memory must be BattleCommandMemory or None")
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
        if on_invalid_action is not None and not callable(on_invalid_action):
            raise TypeError("on_invalid_action must be callable or None")

        self.restart_enabled = restart_enabled
        self.reset_party_on_restart = reset_party_on_restart
        self.reset_inventory_on_restart = reset_inventory_on_restart
        self.on_invalid_action = on_invalid_action
        self.proficiency_level_limit = proficiency_level_limit
        self.experience_limit = experience_limit
        self.character_states = character_states
        self.settings = settings
        self.fonts = FontResources() if fonts is None else fonts
        self.window_factory = windows
        self.save_data = SaveData() if save_data is None else save_data
        self.monster_record_system = MonsterRecordSystem(self.save_data)
        if return_bgm_id is not None and (
            not isinstance(return_bgm_id, str) or not return_bgm_id
        ):
            raise ValueError("return_bgm_id must be a non-empty string or None")
        self.return_bgm_id = return_bgm_id
        self.return_bgm_start_sec = return_bgm_start_sec
        self.palette_shifter = palette_shifter
        self.inner_steel_frame: int | None = None
        self.inner_steel_flashing_indexes: tuple[int, ...] = ()
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
        self.monster_shadow = resources.image(MONSTER_SHADOW_IMAGE_ID)
        self.character_sprites = resources.image(CH_BATTLE_IMAGE_ID)
        self.attack_effect_image = resources.image(ATTACK_EFFECT_IMAGE_ID)
        self.attack_poses = attack_poses
        self.spell_effect_renderer = spell_effect_renderer
        self.spell_effects = spell_effects
        self.localizer = Localizer(settings.language)
        self.identify_text_factory: LocalizedWindowTextFactory | None = None
        self.texts = texts
        self.spells = dict(spells)
        self.item_catalog = dict(item_catalog)
        self.inventory_system = inventory_system
        character_records = _records_by_key(
            character_records,
            label="character",
        )
        self.party = party
        self.encounter = encounter
        self.result_party = party if result_party is None else result_party
        if (
            not self.result_party
            or len(self.result_party) > 6
            or not all(isinstance(member, Member) for member in self.result_party)
        ):
            raise ValueError("result_party must contain from 1 to 6 members")
        if knockout_party:
            if (
                len(encounter.monster_keys) != 1
                or party != knockout_party[:1]
                or len({id(member) for member in knockout_party}) != len(knockout_party)
                or not all(
                    member in self.result_party[:BATTLE_PARTY_MEMBER_COUNT]
                    for member in knockout_party
                )
            ):
                raise ValueError("a knockout battle requires one enemy and an ordered battle party")
        elif tuple(self.result_party[: len(party)]) != party:
            raise ValueError("battle party must be the leading result party members")
        self.party_entrance_complete_frame = (
            PARTY_ENTRANCE_FRAME_COUNT
            + (len(party) - 1) * PARTY_ENTRANCE_STAGGER_FRAME_COUNT
        )
        ordered_visuals = tuple(
            BattleCharacter.from_record(
                member,
                _record_for_key(
                    character_records,
                    member.definition.key,
                    label="character",
                ),
            )
            for member in (knockout_party or party)
        )
        self.knockout_battle = bool(knockout_party)
        self.knockout_queue = ordered_visuals[1:] if knockout_party else ()
        self.party_visuals = ordered_visuals[: len(party)]
        monsters_by_key = _records_by_key(
            monster_records,
            label="monster",
        )
        self.monster_records_by_key = monsters_by_key
        self.monster_image_resources = resources
        self.monster_window_factory = windows
        self.monster_book_number_by_key = {
            key: number for number, key in enumerate(monsters_by_key, start=1)
        }
        self.monster_definitions_by_key = {
            key: MonsterDefinition.from_record(record)
            for key, record in monsters_by_key.items()
        }
        if next_knockout_enemy_key is not None:
            next_enemy = _record_for_key(
                self.monster_definitions_by_key, next_knockout_enemy_key,
                label="monster definition",
            )
            self.next_knockout_bgm_id = _battle_bgm_id(next_enemy.is_boss)
        encounter_definitions = tuple(
            _record_for_key(
                self.monster_definitions_by_key,
                key,
                label="monster definition",
            )
            for key in encounter.monster_keys
        )
        layout = monster_layout(encounter_definitions)
        if not layout.monster_indexes:
            raise BattleDataError("no enemy image fits the battle screen")
        self.monster_slot_indexes = layout.slot_indexes
        self.monster_positions = layout.positions
        front_monster_indexes = _battle_start_front_monster_indexes(
            self.monster_slot_indexes
        )
        self.monsters = tuple(
            BattleMonster.from_record(
                monsters_by_key[encounter_definitions[encounter_index].key],
                is_front_row=index in front_monster_indexes,
            )
            for index, encounter_index in enumerate(layout.monster_indexes)
        )
        self.initial_monsters = self.monsters
        if knockout_party:
            monster = self.monsters[0]
            monster.special_actions = tuple(
                action for action in monster.special_actions
                if action not in (MonsterSpecialAction.CALL, MonsterSpecialAction.REINFORCE)
            )
        self.reinforcement_entrance_frames: dict[int, int] = {}
        self._monster_call_pending = False
        self._reinforcement_waiting_actor: BattleMonster | None = None
        self._reinforcement_post_entrance_wait_frames = 0
        for monster in self.monsters:
            unknown_spell_keys = tuple(
                key for key in monster.spell_keys if key not in self.spells
            )
            if unknown_spell_keys:
                raise BattleDataError(
                    f"{monster.key}.spells contains unknown spell keys: "
                    f"{', '.join(unknown_spell_keys)}"
                )
        self.monster_record_system.register_encounter(
            monster.key for monster in self.monsters
        )
        self.progression = BattleProgression(
            tuple(
                EnemyProgressionData(
                    monster.level,
                    monster.early_appear,
                    monster.max_occurrence,
                    monster.gold,
                    monster.key,
                    monster.treasure_item_key,
                    monster.treasure_rate,
                )
                for monster in self.monsters
            )
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
                for index, (x, y) in enumerate(self.monster_positions)
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
        self.action_popup_window = windows.create(
            SCREEN_WIDTH // TEXT_GRID_X - BATTLE_ACTION_POPUP_HORIZONTAL_PADDING_GRID,
            0,
            BATTLE_ACTION_POPUP_HORIZONTAL_PADDING_GRID,
            BATTLE_ACTION_POPUP_HEIGHT,
            (),
            thin_frame=True,
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
        self.active_party_cursor_frame = 0
        self.blinking_monster_index: int | None = None
        self.monster_blink_frames_remaining = 0
        self.monster_confused_action_pending = False
        self.monster_attack_target_index: int | None = None
        self.monster_attack_damage: int | None = None
        self.monster_attack_critical = False
        self.monster_attack_additional_effects: tuple[AdditionalEffect, ...] = ()
        self.monster_attack_animation_frame = 0
        self.monster_attack_damage_applied = False
        self.monster_previous_attack_popup: BattleMonsterAttackPopup | None = None
        self.monster_drain_presentation: BattleMonsterDrainPresentation | None = None
        self.pending_monster_counters: list[tuple[int, int]] = []
        self.pending_party_counter_index: int | None = None
        self.monster_counter_actor_index: int | None = None
        self.monster_counter_target_index: int | None = None
        self.counter_defeated_turn_actor = False
        self.monster_action: MonsterActionChoice | None = None
        self.monster_charge_presentation: BattleMonsterChargePresentation | None = None
        self.monster_escape_actor_index: int | None = None
        self.monster_escape_animation_frame = 0
        self.escaped_monster_indexes: set[int] = set()
        self.timeline_animation_phase: TimelineAnimationPhase | None = None
        self.timeline_animation_frame = 0
        self.timeline_advance: (
            TimelineAdvance[BattleCharacter | BattleMonster] | None
        ) = None
        self.formation_animation_frame = 0
        self.formation_actor_index: int | None = None
        self.formation_actor_indexes: tuple[int, ...] = ()
        self.formation_start_x = 0
        self.formation_destination_x = 0
        self.formation_start_x_by_index: dict[int, int] = {}
        self.formation_destination_x_by_index: dict[int, int] = {}
        self.formation_animation_completion = (
            FormationAnimationCompletion.COMPLETE_CURRENT_TURN
        )
        self.escape_animation_frame = 0
        self.escape_start_x: tuple[int, ...] = ()
        self.escape_requested = False
        self.escape_actor_index: int | None = None
        self.escape_start_frame_by_party_index: dict[int, int] = {}
        self.escape_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.escape_fade_covered = False
        self.monster_death_animation: MonsterDeathAnimation | None = None
        self.monster_death_delay_frames_remaining = 0
        self.dying_monster_indexes: tuple[int, ...] = ()
        self.monster_death_from_timeline_head = False
        self.entrance_animation_frame = 0
        self.entrance_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.selected_command: str | None = None
        self.escape_return_phase = BattlePhase.COMMAND
        self.auto_battle_active = False
        self.auto_battle_screen: AutoBattleOverlay | None = None
        self.auto_battle_planner: AutoBattlePlanner | None = None
        self.auto_battle_log: list[AutoBattleLogEntry] = []
        self.auto_battle_sequence = 0
        self.input_device = InputDevice.KEYBOARD
        self.confirm_hold_frame_count = 0
        self.selectable_target_indexes: tuple[int, ...] = ()
        self.selected_target_index: int | None = None
        self.selectable_party_target_indexes: tuple[int, ...] = ()
        self.selected_party_target_index: int | None = None
        self.action_targets_enemy = False
        self.action_targets_all = False
        self.pending_item_candidate: BattleItemCandidate | None = None
        self.pending_spell: Spell | None = None
        self.party_status_shows_mp = False
        self.pending_action_effect_spell: Spell | None = None
        self.action_presentation: BattleActionPresentation | None = None
        self.fade_escape_transition: MosaicFadeOut | None = None
        self.fade_escape_snapshot = None
        self.fade_escape_bgm_fade_frame = 0
        self.healing_popups: list[BattleHealingPopup] = []
        self.spell_damage_popups: list[BattleSpellDamagePopup] = []
        self.affinity_popups: list[BattleAffinityPopup] = []
        self.attack_presentation: BattleAttackPresentation | None = None
        self.action_gauge_adjustment = 0.0
        self.battle_popup = BattleTimedPopup()
        self.focused_target_by_party_index: dict[int, int] = {}
        self.focus_presentation_elapsed_frame = 0
        self.focus_wait_animation_frame = 0
        self.hidden_party_indexes: set[int] = set()
        self.hide_presentation_elapsed_frame = 0
        self.identify_target_index: int | None = None
        self.identify_effect_elapsed_frame = 0
        self.identify_detail_window: Window | None = None
        self.identified_monster_indexes: set[int] = set()
        self.victory_returning_party_indexes: set[int] = set()
        self.victory_return_frame = 0
        self.action_party_index: int | None = None
        self.action_stationary = False
        self.action_offset_x = 0
        self.action_motion_frame = 0
        self.action_returning = False
        self.action_uses_cast_pose = False
        self.action_forward_jump = False
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
        self.command_memory = (
            command_memory if command_memory is not None else BattleCommandMemory()
        )
        self.last_global_command: BattleGlobalCommand | None = None
        self.initial_global_command_pending = False
        self.last_spell_key_by_party_index: dict[int, str] = {}
        self.last_item_selection_by_party_index: dict[
            int, tuple[str, EquipmentSlot | None]
        ] = {}
        self.last_cover_target_by_party_index: dict[int, int] = {}
        self.defending_party_indexes: set[int] = set()
        self.cover_target_by_party_index: dict[int, int] = {}
        self.protected_party_index: int | None = None
        self.covering_party_index: int | None = None
        self.escaped_party_indexes: set[int] = set()
        self.temporary_front_party_indexes: set[int] = set()
        self.surprise_roll: SurpriseRoll | None = None
        self.surprise_prevented_by_index: int | None = None
        self.surprise_pending_party_indexes: set[int] = set()
        self.surprise_turned_party_indexes: set[int] = set()
        self.surprise_deferred_party_indexes: set[int] = set()
        self.surprise_original_front_rows: dict[int, bool] = {}
        self.surprise_front_party_indexes: set[int] | None = None
        self.surprise_temporary_front_party_indexes: set[int] = set()
        self.surprise_active = False
        self.victory_motion_frame = 0
        self.victory_summary_window: Window | None = None
        self.result_overlay: BattleResultOverlay | None = None
        self.result_transition_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.result_transition_covered = False
        self.growth_jingle_played = False
        self.victory_exit_pending = False
        self.result_outcome = BattleResult.VICTORY
        self.action_progression_weapon: Item | None = None
        self.action_progression_enemy_levels: tuple[int, ...] = ()
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

        for monster, (x, y) in zip(self.monsters, self.monster_positions):
            name_x, name_y = self._monster_name_window_grid_position(
                monster,
                x,
                y,
            )
            window = windows.create(name_x, name_y, 20, 4, transparent=True)
            name_text = window.add_text(
                monster.display_name(self.localizer),
                0,
                0,
                color=RESERVE_MEMBER_TEXT_COLOR,
            )
            self.monster_name_windows.append(window)
            self.monster_name_texts.append(name_text)

        self._restart_battle()

    @property
    def is_transitioning(self) -> bool:
        """Expose transition blocking without leaking battle timers to Game."""

        return (
            any(
                fade.is_active
                for fade in (
                    self.entrance_fade,
                    self.escape_fade,
                    self.result_transition_fade,
                )
            )
            or getattr(self, "phase", None) is BattlePhase.FADE_ESCAPE
            or getattr(self, "phase", None) is BattlePhase.KNOCKOUT_HANDOFF
        )

    @property
    def knockout_survivors(self) -> tuple[Member, ...]:
        """Return the current fighter followed by the remaining entrants."""

        return (*self.party, *(visual.member for visual in self.knockout_queue))

    @property
    def is_party_command_ready(self) -> bool:
        """Report that a living party member's command window is fully open."""

        if getattr(self, "active_party_index", None) is None:
            return False
        if self.phase is BattlePhase.GLOBAL_COMMAND:
            return self.global_command_window.is_open
        if self.phase is BattlePhase.COMMAND:
            return self.command_window.is_open
        return False

    @property
    def is_party_command_pending(self) -> bool:
        """Report the first party command held for a battle-start event."""

        return getattr(self, "_pending_first_party_command", False)

    def defer_first_party_command(self) -> None:
        """Hold the first command menu until the battle-start event finishes."""

        self._defer_first_party_command = True

    def open_pending_party_command(self) -> None:
        """Open the command menu after the battle-start event and hint."""

        if not self.is_party_command_pending:
            return
        self._pending_first_party_command = False
        if self.initial_global_command_pending:
            self.initial_global_command_pending = False
            self._open_global_command_menu()
        else:
            self._open_member_command_menu()

    def update(self, input_state: InputState) -> None:
        """Advance the battle by one frame from an immutable input snapshot."""

        if not isinstance(input_state, InputState):
            raise TypeError("input_state must be an InputState")
        was_targeting = getattr(self, "phase", None) is BattlePhase.TARGET
        self._update_battle(input_state)
        if getattr(self, "phase", None) is BattlePhase.TARGET:
            self._stop_inner_steel_palette()
            self._sync_unselectable_target_palette()
        elif was_targeting:
            self._release_palette_variant(UNSELECTABLE_TARGET_PALETTE)
        self._update_inner_steel_palette()

    def _update_battle(self, input_state: InputState) -> None:
        auto_battle_screen = getattr(self, "auto_battle_screen", None)
        if auto_battle_screen is not None:
            self.input_device = input_state.device
            if auto_battle_screen.update(input_state):
                self.auto_battle_screen = None
                self.global_command_cursor.active = True
            return
        if self._update_timeline_removal_animation():
            self.input_device = input_state.device
            return
        if getattr(self, "phase", None) is BattlePhase.VICTORY_SUMMARY:
            self.input_device = input_state.device
            self._update_victory_summary(input_state)
            return
        if getattr(self, "phase", None) is BattlePhase.RESULT_TRANSITION:
            self.input_device = input_state.device
            self._update_result_transition()
            return
        if getattr(self, "phase", None) is BattlePhase.RESULT:
            self.input_device = input_state.device
            self._update_result(input_state)
            return
        if getattr(self, "phase", None) is BattlePhase.KNOCKOUT_HANDOFF:
            self.input_device = input_state.device
            self._update_knockout_handoff()
            return
        if getattr(self, "phase", None) in (
            BattlePhase.BOSS_INTRO,
            BattlePhase.IDENTIFY_RESULT,
        ):
            self.confirm_hold_frame_count = 0
        else:
            input_state = self._apply_confirm_repeat(input_state)
        self.input_device = input_state.device
        self._refresh_input_guide()
        if getattr(self, "result", None) is not None:
            return
        if self.is_party_command_pending:
            return
        if getattr(self, "restart_enabled", True) and input_state.menu.triggered:
            self._restart_battle()
            return
        self._update_reinforcement_entrances()
        battle_popup = getattr(self, "battle_popup", None)
        if battle_popup is not None:
            battle_popup.update()
        self._clear_interrupted_focus_states()
        self._update_focus_wait_animation()
        self._update_healing_popups()
        self._update_monster_drain()
        self._update_spell_damage_popups()
        self._update_affinity_popups()
        if hasattr(self, "active_party_cursor_frame"):
            self._update_active_party_cursor()
        if getattr(self, "auto_battle_active", False) and input_state.cancel.triggered:
            self._cancel_auto_battle()
            return
        if self.phase is not BattlePhase.ESCAPE_MEMBER and getattr(
            self, "escape_start_frame_by_party_index", {}
        ):
            # A following ally may skip their turn or start a different action.
            # Finish the preceding runs before advancing that pending phase.
            self._update_party_escape_runs()
            if not self._active_party_indexes():
                self._remove_defeated_party_from_timeline()
                self._begin_escape_animation()
            return
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
        if self.phase is BattlePhase.BOSS_INTRO:
            self._update_boss_intro(input_state)
            return
        if self.phase is BattlePhase.SURPRISE_NOTICE:
            self._update_surprise_notice()
            return
        if self.phase is BattlePhase.SURPRISE_PREVENTED:
            self._update_surprise_prevented(input_state)
            return
        if self.phase is BattlePhase.DEFEAT_MESSAGE:
            self._update_defeat_message(input_state)
            return
        if self.phase is BattlePhase.AUTO_THINKING:
            self._update_auto_thinking()
            return
        if self.phase is BattlePhase.MONSTER_ACTION:
            self._update_monster_action()
            return
        if self.phase is BattlePhase.ESCAPE_CONFIRMATION:
            self._update_escape_confirmation(input_state)
            return
        if self.phase is BattlePhase.ESCAPE_MEMBER:
            self._update_party_member_escape()
            return
        if self.phase is BattlePhase.ESCAPE_MESSAGE:
            self._update_escape_message(input_state)
            return
        if self.phase is BattlePhase.ESCAPE:
            self._update_escape_animation()
            return
        if self.phase is BattlePhase.FADE_ESCAPE:
            self._update_fade_escape()
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
        if self.phase is BattlePhase.COVER_TARGET:
            self._update_cover_target_selection(input_state)
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
        if self.phase is BattlePhase.FOCUS_PRESENTATION:
            self._update_focus_presentation()
            return
        if self.phase is BattlePhase.HIDE_PRESENTATION:
            self._update_hide_presentation()
            return
        if self.phase is BattlePhase.IDENTIFY_PRESENTATION:
            self._update_identify_presentation()
            return
        if self.phase is BattlePhase.IDENTIFY_RESULT:
            self._update_identify_result(input_state)
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
                    options = getattr(self, "_command_options", None)
                    if options is not None and not any(
                        option.command is command and option.enabled
                        for option in options
                    ):
                        self._notify_invalid_action()
                        return
                    self._remember_active_command(command)
                if command == BattleCommand.ATTACK:
                    self._begin_attack_target_selection()
                elif command == BattleCommand.AMBUSH:
                    self._begin_attack_target_selection(command=BattleCommand.AMBUSH)
                elif command == BattleCommand.AIM:
                    self._begin_attack_target_selection(command=BattleCommand.AIM)
                elif command == BattleCommand.IAI:
                    self._begin_attack_target_selection(command=BattleCommand.IAI)
                elif command == BattleCommand.BREATH:
                    self._begin_attack_target_selection(command=BattleCommand.BREATH)
                elif command == BattleCommand.FOCUS:
                    self._begin_attack_target_selection(command=BattleCommand.FOCUS)
                elif command == BattleCommand.SPELL:
                    self._begin_spell_selection()
                elif command == BattleCommand.FORMATION:
                    self._begin_formation_change()
                elif command == BattleCommand.DEFEND:
                    self._begin_defense()
                elif command == BattleCommand.HIDE:
                    self._begin_hide()
                elif command == BattleCommand.IDENTIFY:
                    self._begin_identify_target_selection()
                elif command == BattleCommand.PRAY:
                    self._begin_pray()
                elif command == BattleCommand.COVER:
                    self._begin_cover_target_selection()
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

    def _apply_confirm_repeat(self, input_state: InputState) -> InputState:
        """Repeat held battle confirmations at DA2-equivalent timing."""

        confirm = input_state.confirm
        if confirm.triggered:
            self.confirm_hold_frame_count = 0
            return input_state
        if not confirm.held:
            self.confirm_hold_frame_count = 0
            return input_state

        held_frames = getattr(self, "confirm_hold_frame_count", 0) + 1
        self.confirm_hold_frame_count = held_frames
        should_repeat = (
            held_frames >= BATTLE_CONFIRM_REPEAT_DELAY_FRAME_COUNT
            and (held_frames - BATTLE_CONFIRM_REPEAT_DELAY_FRAME_COUNT)
            % BATTLE_CONFIRM_REPEAT_INTERVAL_FRAME_COUNT
            == 0
        )
        if not should_repeat:
            return input_state
        return replace(input_state, confirm=replace(confirm, triggered=True))

    def _update_global_command_selection(self, input_state: InputState) -> None:
        """Choose a party-wide action or return to the current member's menu."""

        if input_state.cancel.triggered:
            self._open_member_command_menu()
            return
        if input_state.confirm.triggered and self.global_command_window.is_open:
            command = self.global_command_cursor
            if command is None:
                return
            if (
                command.selected_key is BattleGlobalCommand.ESCAPE
                and not self.encounter.escape_command_enabled
            ):
                self._notify_invalid_action()
                return
            if command.selected_key is BattleGlobalCommand.TACTICS:
                self.auto_battle_screen = AutoBattleOverlay(
                    party=self.result_party,
                    items=self.item_catalog,
                    save_data=self.save_data,
                    localizer=self.localizer,
                    texts=self.texts,
                    fonts=self.fonts,
                    input_device=input_state.device,
                )
                self.confirm_hold_frame_count = 0
                command.active = False
                return
            if (
                isinstance(command.selected_key, BattleGlobalCommand)
                and self._command_memory_enabled
            ):
                self.last_global_command = command.selected_key
                self._sync_command_memory()
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

    def _notify_invalid_action(self) -> None:
        """Play the battle's shared alert for an unavailable selection."""

        callback = getattr(self, "on_invalid_action", None)
        if callback is not None:
            callback()

    def _restart_battle(self) -> None:
        """Initialize or explicitly restart this scene and replay its entrance."""

        self._defer_first_party_command = False
        self._pending_first_party_command = False
        self.inner_steel_recovery_index: int | None = None
        self.auto_battle_planner = None
        self.auto_battle_log = []
        self.auto_battle_sequence = 0
        self.reinforcement_entrance_frames.clear()
        self._reinforcement_waiting_actor = None
        self._monster_call_pending = False
        self._reinforcement_post_entrance_wait_frames = 0

        if len(self.monsters) > len(self.initial_monsters):
            initial_count = len(self.initial_monsters)
            self.monsters = self.initial_monsters
            self.monster_slot_indexes = self.monster_slot_indexes[:initial_count]
            self.monster_positions = self.monster_positions[:initial_count]
            self.monster_name_windows = self.monster_name_windows[:initial_count]
            self.monster_name_texts = self.monster_name_texts[:initial_count]
            self._refresh_monster_target_cursor()

        self._release_transient_action_palettes()
        self._restart_battle_bgm()
        if self.reset_inventory_on_restart:
            self.inventory_system = InventorySystem.with_one_each(self.item_catalog)
        self._consumed_items: Counter[str] = Counter()
        self._broken_equipment: dict[tuple[int, EquipmentSlot], Item] = {}
        if self.reset_party_on_restart:
            for member in self.party:
                member.fully_recover()
        self._prepare_party_for_restart()
        for monster in self.monsters:
            monster.restore()
        self.progression = BattleProgression(
            tuple(
                EnemyProgressionData(
                    monster.level,
                    monster.early_appear,
                    monster.max_occurrence,
                    monster.gold,
                    monster.key,
                    monster.treasure_item_key,
                    monster.treasure_rate,
                )
                for monster in self.monsters
            )
        )
        living_party = tuple(
            visual for visual in self.party_visuals if visual.member.is_alive
        )
        self._timeline_order = initialize_timeline_order(
            tuple(
                (entry, self._actor_agility(entry))
                for entry in (*living_party, *self.monsters)
            )
        )
        self.timeline = self._timeline_order.actors
        self.phase = BattlePhase.ENTRANCE
        self.result = None
        self.active_party_index = None
        self.active_party_cursor_frame = 0
        self._sync_active_party_cursor_palette()
        self.blinking_monster_index = None
        self.monster_blink_frames_remaining = 0
        self.monster_attack_target_index = None
        self.monster_attack_damage = None
        self.monster_attack_critical = False
        self.monster_attack_additional_effects = ()
        self.monster_attack_animation_frame = 0
        self.monster_attack_damage_applied = False
        self.monster_previous_attack_popup = None
        self.monster_drain_presentation = None
        self.pending_monster_counters: list[tuple[int, int]] = []
        self.pending_party_counter_index = None
        self.monster_counter_actor_index: int | None = None
        self.monster_counter_target_index: int | None = None
        self.counter_defeated_turn_actor = False
        self.monster_action = None
        self.monster_charge_presentation = None
        self.monster_escape_actor_index = None
        self.monster_escape_animation_frame = 0
        self.escaped_monster_indexes.clear()
        self.timeline_animation_phase = None
        self.timeline_animation_frame = 0
        self.timeline_advance = None
        self.timeline_removal_animation = None
        self.formation_animation_frame = 0
        self.formation_actor_index = None
        self.formation_actor_indexes = ()
        self.formation_start_x = 0
        self.formation_destination_x = 0
        self.formation_start_x_by_index = {}
        self.formation_destination_x_by_index = {}
        self.formation_animation_completion = (
            FormationAnimationCompletion.COMPLETE_CURRENT_TURN
        )
        self.escape_animation_frame = 0
        self.escape_start_x = ()
        self.escape_requested = False
        self.escape_actor_index = None
        self.escape_start_frame_by_party_index = {}
        self.escape_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.escape_fade_covered = False
        self.fade_escape_transition = None
        self.fade_escape_snapshot = None
        self.fade_escape_bgm_fade_frame = 0
        self.monster_death_animation = None
        self.monster_death_delay_frames_remaining = 0
        self.dying_monster_indexes = ()
        self.monster_death_from_timeline_head = False
        self.entrance_animation_frame = 0
        self.selected_command = None
        self.escape_return_phase = BattlePhase.COMMAND
        self.auto_battle_active = False
        self.confirm_hold_frame_count = 0
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
        self.last_cover_target_by_party_index.clear()
        self._restore_command_memory()
        self.selectable_party_target_indexes = ()
        self.selected_party_target_index = None
        self.action_targets_enemy = False
        self.action_targets_all = False
        self.pending_item_candidate = None
        self.pending_spell = None
        self.party_status_shows_mp = False
        self.pending_action_effect_spell = None
        self.action_presentation = None
        self.healing_popups.clear()
        self.spell_damage_popups.clear()
        self.affinity_popups.clear()
        self.attack_presentation = None
        self.action_gauge_adjustment = 0.0
        self.focused_target_by_party_index.clear()
        self.focus_presentation_elapsed_frame = 0
        self.focus_wait_animation_frame = 0
        self.hidden_party_indexes.clear()
        self.hide_presentation_elapsed_frame = 0
        self.identify_target_index = None
        self.identify_effect_elapsed_frame = 0
        self.identified_monster_indexes.clear()
        if self.identify_detail_window is not None:
            self.identify_detail_window.close_immediately()
        self.identify_detail_window = None
        self.victory_returning_party_indexes.clear()
        self.victory_return_frame = 0
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
        self.cover_target_by_party_index.clear()
        self.protected_party_index = None
        self.covering_party_index = None
        self.escaped_party_indexes.clear()
        self.temporary_front_party_indexes.clear()
        if getattr(self, "knockout_battle", False):
            self.temporary_front_party_indexes.add(0)
            self.knockout_participant_keys = {self.party[0].definition.key}
        self._prepare_surprise()
        self.victory_motion_frame = 0
        self.victory_summary_window = None
        self.result_overlay = None
        self.result_transition_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.result_transition_covered = False
        self.growth_jingle_played = False
        self.victory_exit_pending = False
        self.result_outcome = BattleResult.VICTORY
        self.action_progression_weapon = None
        self.action_progression_enemy_levels = ()
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

    def _prepare_surprise(self) -> None:
        """Roll and prepare battle-local surprise state for random encounters."""

        self.surprise_roll = None
        self.surprise_prevented_by_index = None
        self.surprise_pending_party_indexes = set()
        self.surprise_turned_party_indexes = set()
        self.surprise_deferred_party_indexes = set()
        self.surprise_original_front_rows = {}
        self.surprise_front_party_indexes = None
        self.surprise_temporary_front_party_indexes = set(
            getattr(self, "temporary_front_party_indexes", set())
        )
        self.surprise_active = False
        if not self.encounter.surprise_enabled:
            return

        living_indexes = tuple(
            index for index, member in enumerate(self.party) if member.is_alive
        )
        if not living_indexes or not self.monsters:
            return
        result = resolve_surprise_roll(
            tuple(member.adjusted_abilities.agility for member in self.party),
            tuple(monster.agility for monster in self.monsters),
            pyxel.rndi(0, SURPRISE_ROLL_MAX),
        )
        self.surprise_roll = result
        if not result.triggered:
            return

        vigilant_index = next(
            (
                index
                for index in living_indexes
                if self.party[index].has_skill(VIGILANCE_SKILL_KEY)
            ),
            None,
        )
        if vigilant_index is not None:
            self.surprise_prevented_by_index = vigilant_index
            return

        original_rows = {
            index: self._party_member_is_front_row(index) for index in living_indexes
        }
        all_front = all(original_rows.values())
        self.surprise_original_front_rows = original_rows
        self.surprise_front_party_indexes = (
            set(living_indexes)
            if all_front
            else {index for index, was_front in original_rows.items() if not was_front}
        )
        self.surprise_pending_party_indexes = set(living_indexes)
        self.surprise_active = True

    def _show_surprise_notice(self) -> bool:
        """Show a surprise result and report whether timeline activation waits."""

        prevented_by_index = getattr(
            self,
            "surprise_prevented_by_index",
            None,
        )
        if prevented_by_index is not None:
            member = self.party[prevented_by_index]
            message = self.texts.formatted_text(
                "battle.surprise.prevented",
                self.localizer,
                {"MEMBER": member.definition.localized_name(self.localizer)},
            )
            self.phase = BattlePhase.SURPRISE_PREVENTED
            self.battle_popup.clear()
            self.battle_popup_window.clear_texts()
            self.battle_popup_window.add_text(
                message,
                *ESCAPE_MESSAGE_TEXT_POSITION,
            )
            return True
        elif getattr(self, "surprise_active", False):
            message = self.texts.text("battle.surprise", self.localizer)
        else:
            return False
        self.phase = BattlePhase.SURPRISE_NOTICE
        self._show_battle_popup(
            message,
            BATTLE_POPUP_FRAME_COUNT,
            align_left=True,
        )
        return True

    def _prepare_party_for_restart(self) -> None:
        """Allow a composition root to apply fixture state before gauge rolls."""

    def _restart_battle_bgm(self) -> None:
        """Start a battle track or keep the one carried over from the result."""

        bgm_id = _battle_bgm_id(self.monsters[0].is_boss)
        if getattr(self, "knockout_battle", False):
            self.bgm.set_fade_rate(1.0)
            self.bgm.transition_to(bgm_id)
            return
        self.bgm.stop()
        self.bgm.set_fade_rate(1.0)
        self.bgm.play(bgm_id)

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
            if self.monsters[0].is_boss:
                self.phase = BattlePhase.BOSS_INTRO
                return
            if self._show_surprise_notice():
                return
            self._activate_timeline_head()

    def _update_boss_intro(self, input_state: InputState) -> None:
        """Hold the completed entrance with enemy names until acknowledged."""

        if not (input_state.confirm.triggered or input_state.cancel.triggered):
            return
        if self._show_surprise_notice():
            return
        self._activate_timeline_head()

    def _update_surprise_prevented(self, input_state: InputState) -> None:
        """Wait for acknowledgement before activating the first actor."""

        if not (input_state.confirm.triggered or input_state.cancel.triggered):
            return
        self.battle_popup.clear()
        self._activate_timeline_head()

    def _update_surprise_notice(self) -> None:
        """Start the first handoff after the timed surprise notice closes."""

        if self.battle_popup.visible:
            return
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
            BattleGlobalCommand.TACTICS,
        )
        escape_enabled = self.encounter.escape_command_enabled
        for row_index, command in enumerate(commands):
            label = self.texts.text(
                f"battle.command.{command.value}",
                self.localizer,
            )
            if command is BattleGlobalCommand.ESCAPE and not escape_enabled:
                self.global_command_window.add_text(
                    label,
                    GLOBAL_COMMAND_TEXT_X,
                    GLOBAL_COMMAND_ROW_Y[row_index],
                    color=DISABLED_COLOR,
                )
            else:
                self.global_command_window.add_text(
                    label,
                    GLOBAL_COMMAND_TEXT_X,
                    GLOBAL_COMMAND_ROW_Y[row_index],
                )
        self.global_command_cursor = self.global_command_window.set_cursor(
            tuple(
                CursorTarget(
                    GLOBAL_COMMAND_CURSOR_X,
                    GLOBAL_COMMAND_ROW_Y[row_index],
                    key=command,
                )
                for row_index, command in enumerate(commands)
            )
        )
        remembered = getattr(self, "last_global_command", None)
        if (
            self._command_memory_enabled
            and remembered is not None
            and (remembered is not BattleGlobalCommand.ESCAPE or escape_enabled)
        ):
            self.global_command_cursor.select_key(remembered)

    def _begin_auto_battle(self) -> None:
        """Start planning one action at a time from current battle state."""

        self.auto_battle_active = True
        if self.global_command_cursor is not None:
            self.global_command_cursor.active = False
        self.global_command_window.close_immediately()
        self._begin_auto_action()
        self._refresh_input_guide()

    def _begin_auto_action(self) -> None:
        """Capture the battle state and start a cancellable, private forecast."""

        self.auto_battle_planner = AutoBattlePlanner(self._auto_battle_snapshot())
        self.auto_battle_sequence += 1
        self.phase = BattlePhase.AUTO_THINKING
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self._hide_command_guide()

    def _auto_battle_snapshot(self) -> AutoBattleSnapshot:
        """Capture exact HP/MP and apply the encounter's disclosure rules."""

        combatants = []
        for index, member in enumerate(self.party):
            if index in self.escaped_party_indexes:
                continue
            learned = tuple(
                s
                for s in self.spells.values()
                if s.type is not SpellType.ITEM
                and self._party_spell_is_usable(s)
                and s.is_learned_by(member)
            )
            combatants.append(
                AutoCombatant.from_member(
                    member,
                    index,
                    front=self._party_member_is_front_row(index),
                    spells=learned,
                    hidden=index in self.hidden_party_indexes,
                    defending=index in self.defending_party_indexes,
                    cover=self.cover_target_by_party_index.get(index),
                    focus=(
                        5 + self.focused_target_by_party_index[index]
                        if index in self.focused_target_by_party_index
                        else None
                    ),
                )
            )
        for index, monster in enumerate(self.monsters):
            if index in getattr(self, "escaped_monster_indexes", ()):
                continue
            fields = frozenset(self.save_data.monster_records.get(monster.key, ()))
            state = monster.state
            assert state.hp is not None and state.mp is not None
            combatants.append(
                AutoCombatant(
                    number=5 + index,
                    key=f"enemy:{monster.key}:{index}",
                    species_key=monster.key,
                    enemy=True,
                    max_hp=state.max_hp,
                    hp=state.hp,
                    alive=monster.is_alive,
                    max_mp=state.max_mp,
                    mp=state.mp,
                    front=monster.is_front_row,
                    agility=monster.agility,
                    magic=monster.magic,
                    intelligence=monster.intelligence,
                    defense=monster.combat_stats.defense,
                    evasion=monster.combat_stats.evasion,
                    spell_defense=monster.combat_stats.spell_resistance,
                    attack=monster.combat_stats.attack,
                    hit=monster.combat_stats.hit,
                    spells=tuple(self.spells[k] for k in monster.spell_keys),
                    special_actions=monster.special_actions,
                    additional_effects=monster.additional_effects,
                    resistances=frozenset(
                        r for r in monster.resistances if r.value in fields
                    ),
                    weaknesses=frozenset(
                        r for r in monster.weaknesses if r.value in fields
                    ),
                    shadow=monster.is_shadow if "profile" in fields else False,
                    tribe=monster.tribe if "profile" in fields else None,
                    poisoned=monster.state.poisoned,
                    healing=monster.combat_stats.healing,
                    is_boss=monster.is_boss,
                    sleeping=monster.state.sleeping,
                    confused=monster.state.confused,
                    silenced=monster.state.silenced,
                    stunned=monster.state.stunned,
                    protection=monster.state.defense_modifier,
                    speed=monster.state.speed_modifier,
                    magic_shield=monster.state.magic_shield,
                    slow_turns=monster.state.slow_turns,
                    defense_down_turns=monster.state.defense_down_turns,
                    defending=monster.state.is_defending,
                    action_rotation_index=monster.state.action_rotation_index,
                    monster_placement=self._monster_placement(index),
                    known_fields=fields,
                    hp_displayed=index in self.identified_monster_indexes,
                )
            )
        numbers = {id(visual): i for i, visual in enumerate(self.party_visuals)}
        numbers.update({id(monster): 5 + i for i, monster in enumerate(self.monsters)})
        used = self.progression.used_spell_kinds(
            self.party[self.active_party_index].definition.key
        )
        config = self.save_data.auto_battle
        consumables = tuple(
            (item, quantity)
            for key in sorted(config.allowed_items)
            if (item := self.item_catalog.get(key)) is not None
            and self._item_is_usable_in_battle(item)
            and (quantity := self.inventory_system.quantity(key)) > 0
        )
        return AutoBattleSnapshot(
            tuple(combatants),
            tuple(
                (numbers[id(e.actor)], e.gauge) for e in self._timeline_order.entries
            ),
            self.active_party_index,
            tuple(self.spells.values()),
            AutoBattlePolicy(config=config),
            frozenset(self.surprise_pending_party_indexes),
            tuple(self.surprise_original_front_rows.items()),
            frozenset(
                t.value for t, k in SPELL_PROFICIENCY_BY_TYPE.items() if k in used
            ),
            surprise_deferred=frozenset(self.surprise_deferred_party_indexes),
            consumables=consumables,
        )

    def _update_auto_thinking(self) -> None:
        """Keep input responsive without dropping or reordering candidates."""

        deadline = perf_counter() + 0.008
        planner = self.auto_battle_planner
        if planner is None:
            return
        while planner.result is None and perf_counter() < deadline:
            planner.advance()
        if planner.result is not None:
            decision = planner.result
            self.auto_battle_log.append(
                AutoBattleLogEntry(
                    self.auto_battle_sequence, planner.snapshot, decision
                )
            )
            del self.auto_battle_log[:-16]
            self.auto_battle_planner = None
            self._execute_auto_action(decision.action)

    def _execute_auto_action(self, action: AutoAction) -> None:
        """Use the manual command/target paths, including cost and progression."""

        command = action.command
        self._remember_active_command(command)
        if command in (
            BattleCommand.ATTACK,
            BattleCommand.AMBUSH,
            BattleCommand.AIM,
            BattleCommand.IAI,
            BattleCommand.FOCUS,
            BattleCommand.BREATH,
        ):
            self._begin_attack_target_selection(command=command)
            if command not in ALL_ENEMY_TARGET_COMMANDS:
                self.selected_target_index = action.targets[0] - 5
                self.target_cursor.select_key(self.selected_target_index)
        elif command is BattleCommand.IDENTIFY:
            self._begin_identify_target_selection()
            self.selected_target_index = action.targets[0] - 5
            self.target_cursor.select_key(self.selected_target_index)
        elif command is BattleCommand.PRAY:
            self._begin_pray()
        elif command in (BattleCommand.SPELL, BattleCommand.ITEM):
            spell = self.spells[action.spell_key]
            candidate = None
            if command is BattleCommand.ITEM:
                if action.item_key:
                    candidate = BattleItemCandidate(self.item_catalog[action.item_key])
                else:
                    slot = EquipmentSlot(action.equipment_slot)
                    candidate = BattleItemCandidate(
                        self.party[self.active_party_index].equipment.item_at(slot), slot
                    )
                self._remember_active_item(candidate)
            elif self._command_memory_enabled:
                self.last_spell_key_by_party_index[self.active_party_index] = spell.key
                self._sync_command_memory()
            self._begin_action_motion(use_cast_pose=command is BattleCommand.SPELL)
            self._begin_action_target_selection(spell, item_candidate=candidate)
            if not spell.to_all:
                if spell.to_enemy:
                    self.selected_target_index = action.targets[0] - 5
                    self.target_cursor.select_key(self.selected_target_index)
                else:
                    self.selected_party_target_index = action.targets[0]
                    self.party_target_cursor.select_key(
                        self.selected_party_target_index
                    )
        elif command is BattleCommand.COVER:
            self._begin_cover_target_selection()
            self.selected_party_target_index = action.targets[0]
            self._confirm_cover_target_selection()
        elif command is BattleCommand.HIDE:
            self._begin_hide()
        elif command is BattleCommand.FORMATION:
            self._begin_formation_change()
        else:
            self._begin_defense()

    def _cancel_auto_battle(self) -> None:
        """Leave auto mode without cancelling an already-running animation."""

        self.auto_battle_active = False
        self.auto_battle_planner = None
        self.initial_global_command_pending = False
        if self._command_memory_enabled:
            self.last_global_command = BattleGlobalCommand.FIGHT
            self._sync_command_memory()
        if self.phase is BattlePhase.AUTO_THINKING:
            self._open_member_command_menu()
        elif self.phase is BattlePhase.ACTION_TARGET:
            self._clear_action_target_state()
            self.selected_command = None
            self._begin_action_return()
            self._open_member_command_menu()
        elif self.phase is BattlePhase.IDENTIFY_RESULT:
            self._finish_identify_result()
        elif self.phase is BattlePhase.TARGET:
            self.selected_command = None
            self.selectable_target_indexes = ()
            self.selected_target_index = None
            self.target_cursor.active = False
            self.all_target_cursors = ()
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
        """Start the current member's escape and commit the party to follow."""

        self.auto_battle_active = False
        self.auto_battle_planner = None

        if self.active_party_index is None:
            raise RuntimeError("escape confirmation requires an active member")
        self.escape_cursor.active = False
        self.escape_requested = True
        self._begin_party_member_escape(self.active_party_index)

    def _begin_party_member_escape(self, index: int) -> None:
        """Run one member off the battlefield on that member's turn."""

        escaped = getattr(self, "escaped_party_indexes", None)
        if escaped is None:
            escaped = set()
            self.escaped_party_indexes = escaped
        if index in escaped or self._party_member_is_dead(index):
            raise ValueError("only an active living member can escape")
        start_frames = getattr(self, "escape_start_frame_by_party_index", None)
        if start_frames is None:
            start_frames = {}
            self.escape_start_frame_by_party_index = start_frames
        if not start_frames:
            self.escape_animation_frame = 0
            self.escape_start_x = tuple(
                self._party_sprite_x(party_index)
                for party_index in range(len(self.party_visuals))
            )
        start_frames[index] = self.escape_animation_frame
        play_se(BATTLE_ESCAPE_SE_ID)
        self.phase = BattlePhase.ESCAPE_MEMBER
        self.escape_actor_index = index
        getattr(self, "defending_party_indexes", set()).discard(index)
        getattr(self, "cover_target_by_party_index", {}).pop(index, None)
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self._refresh_party_text_colors()

    def _update_party_member_escape(self) -> None:
        """Stagger consecutive allies while waiting for runs before enemy turns."""

        index = self.escape_actor_index
        if index is None:
            raise RuntimeError("member escape phase requires an actor")
        self._update_party_escape_runs()
        start_frames = self.escape_start_frame_by_party_index
        if start_frames:
            if (
                index in start_frames
                and self.escape_animation_frame - start_frames[index]
                >= ESCAPE_MEMBER_STAGGER_FRAME_COUNT
                and len(self._timeline_order.entries) > 1
                and isinstance(self._timeline_order.entries[1].actor, BattleCharacter)
            ):
                # Consecutive escape turns share their running presentation;
                # their intermediate timeline handoff does not add a wait.
                advance = remove_timeline_head(self._timeline_order)
                self._timeline_order = ready_timeline_head(advance.after)
                self.timeline = self._timeline_order.actors
                self.escape_actor_index = None
                self._activate_timeline_head()
            return
        self.escape_actor_index = None
        self.active_party_index = None
        if not self._active_party_indexes():
            self._timeline_order = remove_timeline_actor(
                self._timeline_order,
                self.party_visuals[index],
            )
            self.timeline = self._timeline_order.actors
            self._begin_escape_animation()
            return
        if self._begin_front_promotion_if_needed(
            FormationAnimationCompletion.START_TIMELINE_REMOVAL
        ):
            return
        self._start_timeline_removal_animation()

    def _update_party_escape_runs(self) -> None:
        """Advance each running member and exclude them only on arrival."""

        self.escape_animation_frame += 1
        start_frames = self.escape_start_frame_by_party_index
        arrived = tuple(
            index
            for index in start_frames
            if self._escape_party_x(index) >= ESCAPE_RUN_DESTINATION_X
        )
        for index in arrived:
            self.escaped_party_indexes.add(index)
            del start_frames[index]

    def _party_member_is_escaping(self, index: int) -> bool:
        return index in getattr(self, "escape_start_frame_by_party_index", {})

    def _begin_escape_animation(self) -> None:
        """Show escape success after the final active member has left."""

        self.phase = BattlePhase.ESCAPE_MESSAGE
        self.escape_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.escape_fade_covered = False
        self.active_party_index = None
        self.command_cursor.active = False
        self.escape_cursor.active = False
        self._refresh_party_text_colors()

    def _update_escape_message(self, input_state: InputState) -> None:
        """Wait for acknowledgement after every active member has escaped."""

        if input_state.confirm.triggered or input_state.cancel.triggered:
            self.bgm.stop()
            self.phase = BattlePhase.ESCAPE
            self.escape_fade.start()

    def _update_escape_animation(self) -> None:
        """Fade out after acknowledgement and open escape growth at black."""

        self._update_escape_fade()
        if self.escape_fade_covered:
            self._begin_escape_result()

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

        if getattr(self, "knockout_queue", ()):
            self._begin_knockout_handoff()
            return

        self.phase = BattlePhase.DEFEAT_MESSAGE
        self.active_party_index = None
        self.blinking_monster_index = None
        self.monster_blink_frames_remaining = 0
        self.timeline_animation_phase = None
        self.timeline_animation_frame = 0
        self.timeline_advance = None
        self.auto_battle_active = False
        self.auto_battle_planner = None
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

    def _begin_knockout_handoff(self) -> None:
        """Keep the opponent in place while the outgoing fighter fades out."""

        self._clear_turn_state()
        self._remove_timeline_actors(self.party_visuals)
        self.timeline_removal_animation = None
        self.timeline_animation_phase = None
        self.timeline_advance = None
        self.active_party_index = None
        self.blinking_monster_index = None
        self.monster_blink_frames_remaining = 0
        self.monster_attack_target_index = None
        self.monster_attack_damage = None
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self.global_command_window.close_immediately()
        self.battle_popup.clear()
        self.healing_popups.clear()
        self.spell_damage_popups.clear()
        self.affinity_popups.clear()
        self.pending_party_counter_index = None
        self.pending_monster_counters.clear()
        self.counter_defeated_turn_actor = False
        self.monster_previous_attack_popup = None
        self.monster_drain_presentation = None
        self.auto_battle_planner = None
        self.knockout_handoff_frame = 0
        self.phase = BattlePhase.KNOCKOUT_HANDOFF
        self._refresh_party_hp_text(0)
        self._refresh_party_text_colors()

    def _update_knockout_handoff(self) -> None:
        self.knockout_handoff_frame += 1
        if self.knockout_handoff_frame == KNOCKOUT_HANDOFF_HALF_FRAMES:
            self._replace_knockout_fighter()
        if self.knockout_handoff_frame == 2 * KNOCKOUT_HANDOFF_HALF_FRAMES:
            self._timeline_order = initialize_timeline_order(
                tuple(
                    (actor, self._actor_agility(actor))
                    for actor in (*self.party_visuals, *self.monsters)
                )
            )
            self.timeline = self._timeline_order.actors
            self._activate_timeline_head()

    def _replace_knockout_fighter(self) -> None:
        self.party[0].clear_temporary_battle_conditions()
        entrant, *waiting = self.knockout_queue
        self.knockout_queue = tuple(waiting)
        self.party = (entrant.member,)
        self.knockout_participant_keys.add(entrant.member.definition.key)
        self.party_visuals = (entrant,)
        self.defending_party_indexes.clear()
        self.cover_target_by_party_index.clear()
        self.protected_party_index = None
        self.covering_party_index = None
        self.focused_target_by_party_index.clear()
        self.hidden_party_indexes.clear()
        self.formation_actor_indexes = ()
        self.last_command_by_party_index.clear()
        self.last_spell_key_by_party_index.clear()
        self.last_item_selection_by_party_index.clear()
        self.last_cover_target_by_party_index.clear()
        pending_global_command = self.initial_global_command_pending
        self._restore_command_memory()
        self.initial_global_command_pending = pending_global_command
        window = self.party_status_windows[0]
        name, hp = self.party_status_texts[0]
        window.remove_text(name)
        name = window.add_text(
            entrant.display_name(self.localizer), name.x, name.y, color=name.color,
        )
        self.party_status_texts[0] = (name, hp)
        self._refresh_party_hp_text(0)

    def _complete_defeat(self) -> None:
        """Restore spent items and report defeat to the transition owner."""

        for key, quantity in self._consumed_items.items():
            if not self.inventory_system.add(key, quantity):
                raise RuntimeError(f"cannot restore {quantity} consumed copies of {key!r}")
        for (index, slot), item in self._broken_equipment.items():
            member = getattr(self, "result_party", self.party)[index]
            member.equipment = member.equipment.replaced({slot: item})
        self._consumed_items.clear()
        self._broken_equipment.clear()
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
        if index in getattr(self, "hidden_party_indexes", set()):
            return False
        member = self.party[index]
        active_indexes = self._active_party_indexes()
        is_front = self._party_member_is_front_row(index)
        if len(active_indexes) <= 1 or (
            is_front
            and sum(
                self._party_member_is_front_row(party_index)
                for party_index in active_indexes
            )
            < 2
        ):
            return False
        self.formation_actor_index = index
        self.formation_start_x = self._party_sprite_x(index)
        self.formation_actor_indexes = (index,)
        self.formation_start_x_by_index = {index: self.formation_start_x}
        if is_front:
            temporary_front = getattr(
                self,
                "temporary_front_party_indexes",
                set(),
            )
            if index in temporary_front:
                temporary_front.discard(index)
            else:
                member.formation_row = FormationRow.BACK
        else:
            member.formation_row = FormationRow.FRONT
            getattr(self, "temporary_front_party_indexes", set()).discard(index)
        self.formation_destination_x = self._party_sprite_x(index)
        self.formation_destination_x_by_index = {index: self.formation_destination_x}
        self.formation_animation_frame = 0
        self.formation_animation_completion = (
            FormationAnimationCompletion.COMPLETE_CURRENT_TURN
        )
        self.phase = BattlePhase.FORMATION
        self.selected_command = BattleCommand.FORMATION
        self.command_cursor.active = False
        self.command_window.close_immediately()
        return True

    def _active_party_indexes(self) -> tuple[int, ...]:
        """Return living members that have not left this battle."""

        escaped = getattr(self, "escaped_party_indexes", set())
        party_count = len(getattr(self, "party_visuals", getattr(self, "party", ())))
        return tuple(
            index
            for index in range(party_count)
            if index not in escaped and not self._party_member_is_dead(index)
        )

    def _party_member_is_front_row(self, index: int) -> bool:
        """Return a member's effective row, including battle-only promotion."""

        if index in getattr(self, "temporary_front_party_indexes", set()):
            return True
        surprise_rows = getattr(self, "surprise_front_party_indexes", None)
        original_rows = getattr(self, "surprise_original_front_rows", {})
        if surprise_rows is not None and index in original_rows:
            return index in surprise_rows
        visuals = getattr(self, "party_visuals", ())
        member = visuals[index].member if visuals else self.party[index]
        formation_row = getattr(member, "formation_row", None)
        if formation_row is not None:
            return formation_row is FormationRow.FRONT
        return bool(getattr(member, "is_front_row", True))

    def _prune_surprise_pending_party(
        self,
        completion: FormationAnimationCompletion,
    ) -> bool:
        """Drop unavailable members and restore rows when none remain pending."""

        if not getattr(self, "surprise_active", False):
            return False
        pending = self.surprise_pending_party_indexes
        pending.intersection_update(self._active_party_indexes())
        if pending:
            return False
        self._restore_surprise_formation(completion)
        return True

    def _skip_surprised_party_turn(
        self, party_index: int, *, status_skips_turn: bool = False,
    ) -> bool:
        """Consume one surprise handoff, including repeated-turn failsafe skips."""

        if not getattr(self, "surprise_active", False):
            return False
        if status_skips_turn or self._member_focus_is_interrupted(self.party[party_index]):
            self.surprise_deferred_party_indexes.add(party_index)
        self.surprise_pending_party_indexes.discard(party_index)
        if self.surprise_pending_party_indexes:
            self._start_timeline_animation()
        else:
            self._restore_surprise_formation(
                FormationAnimationCompletion.START_TIMELINE,
            )
        return True

    def _restore_surprise_formation(
        self,
        completion: FormationAnimationCompletion,
        *,
        party_indexes: tuple[int, ...] | None = None,
    ) -> None:
        """Restore ready members, retaining back-attack rows until recovery."""

        active_indexes = self._active_party_indexes()
        restoring_indexes = tuple(
            index
            for index in (active_indexes if party_indexes is None else party_indexes)
            if index in self.surprise_original_front_rows
            and (
                party_indexes is not None
                or index not in getattr(self, "surprise_deferred_party_indexes", set())
            )
            and not self._member_focus_is_interrupted(
                self.party[index], after_confusion_tick=party_indexes is not None,
            )
        )
        start_x_by_index = {
            index: self._party_sprite_x(index) for index in active_indexes
        }
        self.surprise_active = False
        self.surprise_pending_party_indexes.clear()
        for index in restoring_indexes:
            self.surprise_original_front_rows.pop(index)
            getattr(self, "surprise_deferred_party_indexes", set()).discard(index)
            if index in self.surprise_temporary_front_party_indexes:
                self.temporary_front_party_indexes.add(index)
            else:
                self.temporary_front_party_indexes.discard(index)
        if not self.surprise_original_front_rows:
            self.surprise_front_party_indexes = None
        if active_indexes and not any(
            self._party_member_is_front_row(index) for index in active_indexes
        ):
            # Preserve the ordinary battle invariant without walking a member
            # backward only to promote them again on the next handoff.
            self.temporary_front_party_indexes.update(restoring_indexes)
        destination_x_by_index = {
            index: self._party_sprite_x(index) for index in active_indexes
        }
        moving_indexes = tuple(
            index
            for index in active_indexes
            if start_x_by_index[index] != destination_x_by_index[index]
        )
        if not moving_indexes:
            self._continue_after_formation(completion)
            return

        self.formation_actor_index = None
        self.formation_actor_indexes = moving_indexes
        self.formation_start_x_by_index = {
            index: start_x_by_index[index] for index in moving_indexes
        }
        self.formation_destination_x_by_index = {
            index: destination_x_by_index[index] for index in moving_indexes
        }
        self.formation_animation_frame = 0
        self.formation_animation_completion = completion
        self.phase = BattlePhase.FORMATION
        self.active_party_index = None
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self._refresh_party_text_colors()

    def _begin_front_promotion_if_needed(
        self,
        completion: FormationAnimationCompletion,
    ) -> bool:
        """Animate battle-only promotion when no active front member remains."""

        active_indexes = self._active_party_indexes()
        visible_indexes = tuple(
            index
            for index in active_indexes
            if index not in getattr(self, "hidden_party_indexes", set())
        )
        if not visible_indexes or any(
            self._party_member_is_front_row(index) for index in visible_indexes
        ):
            return False
        start_x_by_index = {
            index: self._party_sprite_x(index) for index in active_indexes
        }
        temporary_front = getattr(self, "temporary_front_party_indexes", None)
        if temporary_front is None:
            temporary_front = set()
            self.temporary_front_party_indexes = temporary_front
        temporary_front.update(active_indexes)
        self.formation_actor_index = None
        self.formation_actor_indexes = active_indexes
        self.formation_start_x_by_index = start_x_by_index
        self.formation_destination_x_by_index = {
            index: self._party_sprite_x(index) for index in active_indexes
        }
        self.formation_animation_frame = 0
        self.formation_animation_completion = completion
        self.phase = BattlePhase.FORMATION
        self.active_party_index = None
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self._refresh_party_text_colors()
        return True

    def _begin_defense(self) -> bool:
        """Keep the active member in a defensive stance until their next turn."""

        if self.active_party_index is None:
            return False
        self.defending_party_indexes.add(self.active_party_index)
        self.selected_command = BattleCommand.DEFEND
        self._complete_current_turn()
        return True

    def _begin_cover_target_selection(self) -> bool:
        """Select one visible ally to protect with DA2's Cover command."""

        party_index = self.active_party_index
        if party_index is None or not self.party[party_index].has_skill("Cover"):
            return False
        hidden = getattr(self, "hidden_party_indexes", set())
        selectable = tuple(
            index
            for index in self._active_party_indexes()
            if index == party_index or index not in hidden
        )
        if not selectable:
            return False
        targets = tuple(
            CursorTarget(
                self._party_target_cursor_x(index) // 4,
                (PARTY_SPRITE_Y[index] + 8) // 4,
                key=index,
            )
            for index in selectable
        )
        remembered = (
            getattr(self, "last_cover_target_by_party_index", {}).get(party_index)
            if self._command_memory_enabled
            else None
        )
        selected = remembered if remembered in selectable else selectable[0]
        self.selectable_party_target_indexes = selectable
        self.selected_party_target_index = selected
        self.party_target_cursor = WindowCursor(
            self.party_target_window,
            targets,
            active=True,
        )
        self.party_target_cursor.select_key(selected)
        self.selected_command = BattleCommand.COVER
        self.phase = BattlePhase.COVER_TARGET
        self.command_cursor.active = False
        return True

    def _update_cover_target_selection(self, input_state: InputState) -> None:
        """Confirm a Cover target or return to the member command list."""

        if input_state.cancel.triggered:
            self._cancel_cover_target_selection()
            return
        if input_state.confirm.triggered:
            self._confirm_cover_target_selection()
            return
        if input_state.navigation is not None:
            self._move_party_target(input_state.navigation)
        if self.party_target_cursor is not None:
            self.party_target_cursor.update()

    def _cancel_cover_target_selection(self) -> None:
        """Close the Cover cursor without consuming the current turn."""

        self.phase = BattlePhase.COMMAND
        self.selected_command = None
        self.selectable_party_target_indexes = ()
        self.selected_party_target_index = None
        if self.party_target_cursor is not None:
            self.party_target_cursor.active = False
        self.party_target_cursor = None
        self.command_cursor.active = True

    def _confirm_cover_target_selection(self) -> bool:
        """Protect the selected ally, treating self-selection as Defend."""

        party_index = self.active_party_index
        target_index = self.selected_party_target_index
        if (
            party_index is None
            or target_index is None
            or target_index not in self.selectable_party_target_indexes
        ):
            return False
        remembered = getattr(self, "last_cover_target_by_party_index", None)
        if remembered is None:
            remembered = {}
            self.last_cover_target_by_party_index = remembered
        if self._command_memory_enabled:
            remembered[party_index] = target_index
        if target_index == party_index:
            return self._begin_defense()

        cover_targets = getattr(self, "cover_target_by_party_index", None)
        if cover_targets is None:
            cover_targets = {}
            self.cover_target_by_party_index = cover_targets
        cover_targets[party_index] = target_index
        self.defending_party_indexes.add(party_index)
        self.selected_command = BattleCommand.COVER
        self._complete_current_turn()
        return True

    def _begin_hide(self) -> bool:
        """Start DA2's disappearing motion and mark the actor untargetable."""

        index = self.active_party_index
        hidden = getattr(self, "hidden_party_indexes", None)
        if hidden is None:
            hidden = set()
            self.hidden_party_indexes = hidden
        if index is None or index in hidden:
            return False
        if not self.party[index].has_skill("Hide"):
            return False
        hidden.add(index)
        self.hide_presentation_elapsed_frame = 0
        self.phase = BattlePhase.HIDE_PRESENTATION
        self.selected_command = BattleCommand.HIDE
        self.command_cursor.active = False
        self.command_window.close_immediately()
        play_se(BATTLE_HIDE_SE_ID)
        self._refresh_party_text_colors()
        return True

    def _update_hide_presentation(self) -> None:
        """Finish hiding after the DA2 motion converted to ZERO's frame rate."""

        self.hide_presentation_elapsed_frame += 1
        if self.hide_presentation_elapsed_frame < HIDE_PRESENTATION_FRAME_COUNT:
            return
        self.hide_presentation_elapsed_frame = HIDE_PRESENTATION_FRAME_COUNT
        index = self.active_party_index
        if index is not None:
            self._show_battle_popup(
                self.texts.text("battle.command.hide", self.localizer),
                12 * FPS // DA2_REFERENCE_FPS,
            )
        self._reveal_hidden_party_if_all_unavailable()
        self._complete_current_turn()

    def _begin_pray(self) -> None:
        """Move the caster into position for a self-targeted prayer."""

        self.selected_command = BattleCommand.PRAY
        self.phase = BattlePhase.ACTION_PRESENTATION
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self.hidden_party_indexes.discard(self.active_party_index)
        self._begin_action_motion(use_cast_pose=True)

    def _start_pray_presentation(self, index: int) -> None:
        """Play the shared MP effect on success, or show a miss on failure."""

        member = self.party[index]
        amount = resolve_pray_recovery(
            magic=member.adjusted_abilities.magic,
            internal_level=member.internal_level,
            success_roll=random.randrange(PRAY_SUCCESS_ROLL_COUNT),
            random_factor=random.random(),
        )
        x, y = self._party_effect_position(index)
        effects = (
            () if amount is None else self._build_target_spell_effects(
                "MANA DROP", "ally", (index,), caster=("ally", index),
            )
        )
        self.action_presentation = BattleActionPresentation(
            effects,
            mana_results=(
                BattleManaResult(index, amount, x + 6, y + 16, show_rolled_amount=True),
            ),
            post_effect_wait_frame_count=(
                MISSED_ACTION_RETURN_WAIT_FRAME_COUNT if amount is None else 0
            ),
            screen_flash=effects[0].player.screen_flash if effects else None,
        )
        self.action_presentation.schedule_spell_results({})
        self._show_battle_popup(
            self.texts.text("battle.command.pray", self.localizer),
            BATTLE_POPUP_FRAME_COUNT,
        )
        self._start_target_spell_effects(effects)

    def _begin_member_breath(self) -> None:
        """Confirm the all-enemy breath and wait for the actor to step forward."""

        self.phase = BattlePhase.ACTION_PRESENTATION
        self.command_window.close_immediately()
        self.all_target_cursors = ()
        self.hidden_party_indexes.discard(self.active_party_index)
        self._refresh_monster_name_colors()

    def _start_member_breath_presentation(self, party_index: int) -> None:
        """Pay HP once and resolve every living enemy's fire damage."""

        member = self.party[party_index]
        hp = member.hp
        attack = member_breath_attack(member)
        hp_cost = member_breath_hp_cost(hp)
        member.hp -= hp_cost
        self._refresh_party_hp_text(party_index)
        if hp_cost:
            x, y = self._party_effect_position(party_index)
            self.spell_damage_popups.append(BattleSpellDamagePopup(x + 6, y + 16, hp_cost))
        damages = []
        for index in self.selectable_target_indexes:
            monster = self.monsters[index]
            if not monster.is_alive:
                continue
            result = resolve_fire_breath(
                attack=attack, hp=hp, max_hp=member.max_hp,
                target_spell_defense=monster.combat_stats.spell_resistance,
                fire_resistant=ResistanceType.FIRE in monster.spell_resistances,
                random_factor=random.random(),
            )
            _x, y = self._monster_base_position(index)
            center_x = self._monster_draw_x(index) + monster.width // 2
            damages.append(BattleSpellDamageResult(
                index, result.damage,
                SpellAffinity.RESIST if result.resisted else SpellAffinity.NORMAL,
                center_x, y + monster.height - 8,
                center_x - AFFINITY_ICON_WIDTH // 2, y + 20,
            ))
            self.monster_record_system.reveal_profile(monster.key)
            self.monster_record_system.reveal_affinity(monster.key, ResistanceType.FIRE)

        presentation = BattleActionPresentation(
            (), damage_results=tuple(damages), background_tint_color=FIRE_BREATH_TINT_COLOR,
            wave_enemy_sprites=True,
            result_start_frame=DAMAGE_POPUP_FRAME_COUNT, post_effect_wait_frame_count=0,
        )
        self.action_presentation = presentation
        self._queue_spell_affinity_popups(damages, {})
        self._sync_action_background(presentation)
        self._show_battle_popup(
            self._command_label(BattleCommand.BREATH), BATTLE_POPUP_FRAME_COUNT,
        )
        play_se(BATTLE_FIRE_BREATH_SE_ID)

    def _begin_focus_presentation(self) -> bool:
        """Store a charged attack and hold the guard pose for 36 frames."""

        party_index = self.active_party_index
        target_index = self.selected_target_index
        if (
            party_index is None
            or target_index is None
            or target_index not in self.selectable_target_indexes
            or not self.monsters[target_index].is_alive
        ):
            return False
        focused_targets = getattr(self, "focused_target_by_party_index", None)
        if focused_targets is None:
            focused_targets = {}
            self.focused_target_by_party_index = focused_targets
        focused_targets[party_index] = target_index
        self._record_equipped_weapon_action(
            party_index,
            (getattr(self.monsters[target_index], "level", 1),),
        )
        self.focus_presentation_elapsed_frame = 0
        self.phase = BattlePhase.FOCUS_PRESENTATION
        self.command_cursor.active = False
        self.target_cursor.active = False
        self.command_window.close_immediately()
        self._show_battle_popup(
            self._command_label(BattleCommand.FOCUS),
            FOCUS_PRESENTATION_FRAME_COUNT,
        )
        play_se(BATTLE_FOCUS_SE_ID)
        self._refresh_monster_name_colors()
        return True

    def _update_focus_presentation(self) -> None:
        """Finish the no-op charging turn after its authored hold."""

        self.focus_presentation_elapsed_frame += 1
        if self.focus_presentation_elapsed_frame < FOCUS_PRESENTATION_FRAME_COUNT:
            return
        self.focus_presentation_elapsed_frame = FOCUS_PRESENTATION_FRAME_COUNT
        self._complete_current_turn()

    def _update_focus_wait_animation(self) -> None:
        """Advance the looping aura only while the battle scene updates."""

        if getattr(self, "focused_target_by_party_index", {}):
            cycle_frames = (
                FOCUS_WAIT_EFFECT_PATTERN_COUNT * FOCUS_WAIT_EFFECT_PATTERN_FRAME_COUNT
            )
            self.focus_wait_animation_frame = (
                getattr(self, "focus_wait_animation_frame", 0) + 1
            ) % cycle_frames
        else:
            self.focus_wait_animation_frame = 0

    @staticmethod
    def _member_focus_is_interrupted(
        member: object, *, after_confusion_tick: bool = False,
    ) -> bool:
        """Return whether death or an incapacitating ailment cancels focus."""

        return (
            BattleScene._member_is_dead(member)
            or bool(getattr(member, "paralyzed", False))
            or bool(getattr(member, "sleeping", 0))
            or getattr(member, "confused", 0) > int(after_confusion_tick)
            or bool(getattr(member, "stunned", False))
        )

    def _clear_interrupted_focus_states(self) -> None:
        """Drop charged attacks whose owner can no longer maintain them."""

        focused_targets = getattr(self, "focused_target_by_party_index", None)
        if not focused_targets:
            return
        for index in tuple(focused_targets):
            if index >= len(self.party) or self._member_focus_is_interrupted(
                self.party[index]
            ):
                focused_targets.pop(index, None)

    def _begin_focused_attack(self) -> bool:
        """Consume the active member's focus and begin its automatic attack."""

        party_index = self.active_party_index
        focused_targets = getattr(self, "focused_target_by_party_index", {})
        if party_index is None or party_index not in focused_targets:
            return False
        if self._member_focus_is_interrupted(self.party[party_index]):
            focused_targets.pop(party_index, None)
            return False
        selectable = self._active_member_attack_targets()
        if not selectable:
            focused_targets.pop(party_index, None)
            return False
        stored_target = focused_targets.pop(party_index)
        target_index = stored_target if stored_target in selectable else selectable[0]
        self.selected_command = BattleCommand.FOCUS
        self.selectable_target_indexes = selectable
        self.selected_target_index = target_index
        self._begin_action_motion(use_cast_pose=False, jump=True)
        return self._begin_attack_presentation()

    def _update_formation_animation(self) -> None:
        """Advance manual or automatic formation walking, then continue."""

        self.formation_animation_frame += 1
        if self.formation_animation_frame < FORMATION_MOVE_FRAME_COUNT:
            return
        self.formation_animation_frame = FORMATION_MOVE_FRAME_COUNT
        self.formation_actor_index = None
        self.formation_actor_indexes = ()
        self.formation_start_x_by_index = {}
        self.formation_destination_x_by_index = {}
        completion = self.formation_animation_completion
        self.formation_animation_completion = (
            FormationAnimationCompletion.COMPLETE_CURRENT_TURN
        )
        if self.phase is BattlePhase.FORMATION:
            self._continue_after_formation(completion)

    def _continue_after_formation(
        self,
        completion: FormationAnimationCompletion,
    ) -> None:
        """Resume the operation that requested a formation walk."""

        if completion is FormationAnimationCompletion.COMPLETE_CURRENT_TURN:
            self._complete_current_turn()
        elif completion is FormationAnimationCompletion.START_TIMELINE:
            if not self._begin_pending_party_counter():
                self._start_timeline_animation()
        elif completion is FormationAnimationCompletion.START_TIMELINE_REMOVAL:
            self._start_timeline_removal_animation()
        elif completion is FormationAnimationCompletion.ACTIVATE_TIMELINE_HEAD:
            self._activate_timeline_head()
        elif completion is FormationAnimationCompletion.CONTINUE_MONSTER_ATTACK:
            actor = self.timeline[0]
            targets = self._monster_attack_target_indexes(actor)
            if targets:
                self.phase = BattlePhase.MONSTER_ACTION
                self._begin_standard_monster_attack(actor, target_indexes=targets)
            else:
                self.monster_previous_attack_popup = None
                self._continue_after_formation(FormationAnimationCompletion.START_TIMELINE)
        else:
            raise RuntimeError("unknown formation animation completion")

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
                and self._item_is_usable_in_battle(item)
            )
        )
        return (*equipped, *consumables)

    def _item_is_usable_in_battle(self, item: Item) -> bool:
        """Return whether an item's resolved use effect permits battle use."""

        if not item.use_spell_key:
            return False
        spell = self.spells.get(item.use_spell_key)
        return spell is not None and self._party_spell_is_usable(spell)

    def _party_spell_is_usable(self, spell: Spell) -> bool:
        return spell.on_battle and (
            not getattr(self, "knockout_battle", False)
            or spell.action not in (SpellAction.FADE, SpellAction.TELEPORT)
        )

    @property
    def selected_item_candidate(self) -> BattleItemCandidate | None:
        """Return the selected item candidate, if its index is still valid."""

        if not 0 <= self.selected_item_index < len(self.item_candidates):
            return None
        return self.item_candidates[self.selected_item_index]

    def _remember_active_item(self, candidate: BattleItemCandidate) -> None:
        """Keep one member's last confirmed item by stable item and slot keys."""

        if self.active_party_index is None or not self._command_memory_enabled:
            return
        selections = getattr(self, "last_item_selection_by_party_index", None)
        if selections is None:
            selections = {}
            self.last_item_selection_by_party_index = selections
        selections[self.active_party_index] = (
            candidate.item.key,
            candidate.equipment_slot,
        )
        self._sync_command_memory()

    def _remembered_item_index(
        self,
        candidates: tuple[BattleItemCandidate, ...],
    ) -> int | None:
        """Find the active member's last item when it remains usable."""

        if self.active_party_index is None or not self._command_memory_enabled:
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
        count_texts = LocalizedWindowTextFactory.from_language(
            self.fonts, self.settings.language
        )
        for row, candidate in enumerate(visible):
            item = candidate.item
            y = ITEM_FIRST_Y + row * ITEM_ROW_HEIGHT
            prefix = "＃" if candidate.is_equipped else ""
            self.item_window.add_text(
                prefix + item.localized_name(self.localizer),
                ITEM_TEXT_X,
                y,
                color=(
                    DEFAULT_TEXT_COLOR
                    if self._item_is_usable_in_battle(item)
                    else DISABLED_COLOR
                ),
            )
            if not candidate.is_equipped:
                count_text = ascii_to_fullwidth(str(self.inventory_system.quantity(item)))
                self.item_window.add_text(
                    count_text,
                    right_aligned_grid_x(
                        count_text,
                        reference_text="０",
                        reference_x=ITEM_COUNT_X,
                        font=count_texts,
                    ),
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
        """Return learned battle spells to display, including blocked FADE."""

        if self.active_party_index is None:
            return ()
        member = self.party[self.active_party_index]
        return tuple(
            spell
            for spell in self.spells.values()
            if (
                spell.type is not SpellType.ITEM
                and (
                    self._party_spell_is_usable(spell)
                    or (spell.on_battle and spell.action is SpellAction.FADE)
                )
                and spell.is_learned_by(member)
            )
        )

    def _can_cast_party_spell(self, member: Member, spell: Spell) -> bool:
        """Check whether a spell in the party command list can be confirmed."""

        return (
            member.mp >= spell.mp
            and self._party_spell_is_usable(spell)
            and not (
                spell.action is SpellAction.FADE
                and self.monsters
                and self.monsters[0].is_boss
            )
        )

    @property
    def selected_spell(self) -> Spell | None:
        """Return the battle spell under the cursor, if any."""

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
            self._notify_invalid_action()
            return False
        self.phase = BattlePhase.SPELL
        self.selected_command = BattleCommand.SPELL
        self._begin_action_motion(use_cast_pose=True)
        self.spell_candidates = candidates
        self.spell_scroll_offset = 0
        # A cursor from the previous menu is not a confirmed member choice.
        self.spell_cursor = None
        member = self.party[self.active_party_index]
        remembered_key = (
            getattr(self, "last_spell_key_by_party_index", {}).get(
                self.active_party_index
            )
            if self._command_memory_enabled
            else None
        )
        remembered_spell = next(
            (spell for spell in candidates if spell.key == remembered_key),
            None,
        )
        if remembered_spell is not None and self._can_cast_party_spell(
            member, remembered_spell
        ):
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
            available = self._can_cast_party_spell(member, spell)
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
            ascii_to_fullwidth(f"{mp_label} {member.mp:3d}"),
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
        if direction.dy:
            candidates = self._spell_candidates_for_type(current.type)
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
                candidates = self._spell_candidates_for_type(spell_type)
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
        if spell is None:
            return False
        if not self._can_cast_party_spell(member, spell):
            self._notify_invalid_action()
            return False
        started = self._begin_action_target_selection(spell)
        if started and self._command_memory_enabled:
            selections = getattr(self, "last_spell_key_by_party_index", None)
            if selections is None:
                selections = {}
                self.last_spell_key_by_party_index = selections
            selections[self.active_party_index] = spell.key
            self._sync_command_memory()
        return started

    def _begin_action_target_selection(
        self,
        spell: Spell,
        *,
        item_candidate: BattleItemCandidate | None = None,
    ) -> bool:
        """Select the targets specified by an item effect or a spell record."""

        if spell.to_enemy:
            selectable = self._selectable_enemy_indexes_for_spell(spell)
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
            selectable = self._selectable_party_indexes_for_spell(spell)
            if not selectable:
                return False
            party_targets = tuple(
                CursorTarget(
                    self._party_target_cursor_x(index) // 4,
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
        self.party_status_shows_mp = (
            item_candidate is not None and spell.action is SpellAction.MANA
        )
        if self.party_status_shows_mp:
            self._refresh_all_party_hp_texts()
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

    def _party_target_cursor_x(self, index: int) -> int:
        """Place an ally cursor beside its action-position sprite."""

        x = self._party_sprite_x(index)
        if index == getattr(self, "action_party_index", None):
            x -= ACTION_MOVE_DISTANCE
        return x - 8

    def _selectable_enemy_indexes_for_spell(self, spell: Spell) -> tuple[int, ...]:
        """Allow every living enemy, including targets marked VOID."""

        return tuple(
            index for index, monster in enumerate(self.monsters) if monster.is_alive
        )

    def _enemy_spell_is_void(self, spell: Spell, index: int) -> bool:
        """Identify redundant debuffs independently of cursor eligibility."""

        if spell.action is SpellAction.SLOW:
            return self.monsters[index].state.speed_modifier <= MIN_SPEED_MODIFIER
        if spell.action is SpellAction.BREAK:
            return self.monsters[index].state.defense_modifier < 0
        return False

    def _selectable_party_indexes_for_spell(self, spell: Spell) -> tuple[int, ...]:
        """Return allies the target cursor can visit for this spell."""

        if spell.action in (SpellAction.FADE, SpellAction.TELEPORT):
            active_index = getattr(self, "active_party_index", None)
            if (
                active_index is None
                or active_index in getattr(self, "escaped_party_indexes", set())
                or self._party_member_is_dead(active_index)
            ):
                return ()
            return (active_index,)
        if spell.action is SpellAction.REVIVE:
            escaped = getattr(self, "escaped_party_indexes", set())
            party_count = len(
                getattr(self, "party_visuals", getattr(self, "party", ()))
            )
            return tuple(index for index in range(party_count) if index not in escaped)
        hidden = getattr(self, "hidden_party_indexes", set())
        indexes = tuple(
            index
            for index in self._active_party_indexes()
            if index not in hidden
            or (not spell.to_all and index == self.active_party_index)
        )
        if spell.action is SpellAction.PROTECTION:
            return tuple(
                index
                for index in indexes
                if self.party[index].protection_level < MAX_PROTECTION_LEVEL
            )
        if spell.action is SpellAction.HASTE:
            return tuple(
                index
                for index in indexes
                if self.party[index].speed_modifier < MAX_SPEED_MODIFIER
            )
        if spell.action is SpellAction.MAGIC_SHIELD:
            return tuple(index for index in indexes if not self.party[index].magic_shield)
        return indexes

    def _selected_party_target_can_receive_spell(self, spell: Spell) -> bool:
        """Check single-target recovery before paying an item or spell cost."""

        if (
            spell.to_enemy
            or spell.to_all
            or spell.action
            not in (
                SpellAction.HEAL,
                SpellAction.MANA,
                SpellAction.CURE,
                SpellAction.REVIVE,
            )
        ):
            return True
        index = getattr(self, "selected_party_target_index", None)
        if index is None or index not in getattr(
            self, "selectable_party_target_indexes", ()
        ):
            return False
        target = self.party[index]
        if spell.action is SpellAction.HEAL:
            return target.is_alive and target.hp < target.max_hp
        if spell.action is SpellAction.MANA:
            return target.can_receive_mana
        if spell.action is SpellAction.CURE:
            return target.is_alive and target.has_curable_ailment
        return target.is_dead

    @staticmethod
    def _make_all_target_cursors(
        window: Window,
        targets: tuple[CursorTarget, ...],
    ) -> tuple[WindowCursor, ...]:
        """Create one independently drawable cursor for every all-target marker."""

        return tuple(WindowCursor(window, (target,)) for target in targets)

    def _update_action_target_selection(self, input_state: InputState) -> None:
        if getattr(self, "auto_battle_active", False):
            if self.action_offset_x >= ACTION_MOVE_DISTANCE:
                self._confirm_action_target_selection()
            return
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
        use_spell_key = item_candidate.item.use_spell_key if item_candidate else None
        effect_spell = (
            getattr(self, "spells", {}).get(use_spell_key) if use_spell_key else spell
        )
        if (
            effect_spell is not None
            and not self._selected_party_target_can_receive_spell(effect_spell)
        ):
            if getattr(self, "on_invalid_action", None) is not None:
                self.on_invalid_action()
            return False
        gauge_adjustment = 0.0
        if item_candidate is not None:
            if item_candidate.item.equip_type is not ItemEquipType.ITEM:
                gauge_adjustment = self._spell_gauge_adjustment(effect_spell)
            if not self._commit_item_use(item_candidate):
                return False
            self._show_item_use_message(item_candidate.item)
            if (
                item_candidate.item.is_weapon
                and self.active_party_index is not None
                and hasattr(self, "progression")
            ):
                levels = self._current_action_enemy_levels()
                self.progression.record_weapon_action(
                    self.party[self.active_party_index],
                    (item_candidate.item,),
                    levels,
                )
                self.action_progression_weapon = item_candidate.item
                self.action_progression_enemy_levels = levels
        elif spell is not None:
            if self.active_party_index is None:
                return False
            member = self.party[self.active_party_index]
            if member.silenced:
                self.action_presentation = BattleActionPresentation(
                    (),
                    post_effect_wait_frame_count=MONSTER_SPELL_FAILURE_FRAME_COUNT,
                )
                self.phase = BattlePhase.ACTION_PRESENTATION
                self._show_monster_spell_sealed_message(actor_is_enemy=False)
                return True
            if member.mp < spell.mp:
                return False
            gauge_adjustment = self._spell_gauge_adjustment(spell)
            member.mp -= spell.mp
            self._show_spell_cast_message(spell)
            if spell.type is not SpellType.ITEM and hasattr(self, "progression"):
                self.progression.record_spell_use(
                    member,
                    SPELL_PROFICIENCY_BY_TYPE[spell.type],
                    self._current_action_enemy_levels(),
                    mp_spent=spell.mp,
                )
        else:
            return False
        self.action_gauge_adjustment = gauge_adjustment
        if self.active_party_index is not None:
            getattr(self, "hidden_party_indexes", set()).discard(
                self.active_party_index
            )
        if effect_spell is not None and effect_spell.action is SpellAction.IDENTIFY:
            return self._begin_identify_presentation()
        if effect_spell is not None:
            self._record_action_target_information(effect_spell)
            if (
                not effect_spell.to_enemy
                and getattr(self, "action_party_index", None) is not None
                and self.action_offset_x < ACTION_MOVE_DISTANCE
            ):
                # A self-targeted effect anchors to the caster's final position.
                self.pending_action_effect_spell = effect_spell
                self.phase = BattlePhase.ACTION_PRESENTATION
                return True
        return self._start_confirmed_action_presentation(effect_spell)

    def _start_confirmed_action_presentation(self, effect_spell: Spell | None) -> bool:
        if effect_spell is not None and self._begin_action_presentation(effect_spell):
            return True
        if getattr(self, "action_party_index", None) is not None:
            self._begin_action_return(complete_turn=True)
            return True
        self._complete_current_turn()
        return True

    def _spell_gauge_adjustment(self, spell: Spell | None) -> float:
        """Capture the caster's delay before costs can remove equipped gear."""

        if spell is None or spell.type is SpellType.ITEM:
            return 0.0
        if self.active_party_index is None:
            raise RuntimeError("spell casting requires an active party member")
        member = self.party[self.active_party_index]
        return -float(
            spell_cast_delay(
                spell_level=member.proficiency(
                    SPELL_PROFICIENCY_BY_TYPE[spell.type]
                ).level,
                reduced_wait=any(
                    item.special is ItemSpecial.SPL_REDUCE_WT
                    for item in member.equipment.equipped_items()
                ),
            )
        )

    def _record_action_target_information(self, spell: Spell) -> None:
        """Reveal enemy profiles and tested attributes after confirmation."""

        records = getattr(self, "monster_record_system", None)
        if records is None or not self.action_targets_enemy:
            return
        indexes = (
            self.selectable_target_indexes
            if self.action_targets_all
            else (
                ()
                if self.selected_target_index is None
                else (self.selected_target_index,)
            )
        )
        for index in indexes:
            monster_key = self.monsters[index].key
            records.reveal_profile(monster_key)
            if spell.attribute is not None:
                records.reveal_affinity(monster_key, spell.attribute)

    def _target_affinities(self, index: int) -> tuple[SpellAffinity, ...]:
        """Return distinct known affinities for one current enemy target."""

        if index not in self.selectable_target_indexes:
            return ()

        attributes: tuple[ResistanceType, ...] = ()
        flying_effective = False
        if self.phase is BattlePhase.TARGET:
            if (
                self.selected_command
                not in (
                    BattleCommand.ATTACK,
                    BattleCommand.AMBUSH,
                    BattleCommand.AIM,
                    BattleCommand.FOCUS,
                )
                or self.active_party_index is None
            ):
                return ()
            member = self.party[self.active_party_index]
            weapon_slots = [EquipmentSlot.RIGHT]
            if getattr(member, "has_skill", lambda _key: False)("Dual-Wield"):
                weapon_slots.append(EquipmentSlot.LEFT)
            selected_attributes: list[ResistanceType] = []
            for slot in weapon_slots:
                weapon = member.equipment.weapon_at(slot)
                if weapon is None:
                    continue
                attribute = WEAPON_ATTRIBUTE_RESISTANCE.get(weapon.attack_attribute)
                if attribute is not None and attribute not in selected_attributes:
                    selected_attributes.append(attribute)
            attributes = tuple(selected_attributes)
        elif self.phase is BattlePhase.ACTION_TARGET and self.action_targets_enemy:
            spell = self.pending_spell
            if spell is None and self.pending_item_candidate is not None:
                use_spell_key = self.pending_item_candidate.item.use_spell_key
                spell = getattr(self, "spells", {}).get(use_spell_key)
            if spell is not None and spell.attribute is not None:
                attributes = (spell.attribute,)
            if spell is not None:
                flying_effective = getattr(spell, "effective_race", "") == "FLYING"
        else:
            return ()

        records = getattr(self, "monster_record_system", None)
        monster = self.monsters[index]
        if records is None:
            return ()
        affinities: list[SpellAffinity] = []
        if (
            flying_effective
            and monster.is_shadow
            and "profile" in records.save_data.monster_records.get(monster.key, ())
        ):
            affinities.append(SpellAffinity.WEAK)
        for attribute in attributes:
            if not records.affinity_is_revealed(monster.key, attribute):
                continue
            affinity = SpellAffinity.NORMAL
            if attribute in monster.resistances:
                affinity = SpellAffinity.RESIST
            elif attribute in monster.weaknesses:
                affinity = SpellAffinity.WEAK
            if affinity is not SpellAffinity.NORMAL and affinity not in affinities:
                affinities.append(affinity)
        return tuple(affinities)

    def _target_affinity(self, index: int) -> SpellAffinity:
        """Return the first affinity, retaining the single-marker query API."""

        return next(iter(self._target_affinities(index)), SpellAffinity.NORMAL)

    def _current_action_enemy_levels(self) -> tuple[int, ...]:
        """Resolve enemy levels for the currently confirmed spell/item action."""

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
            return tuple(getattr(self.monsters[index], "level", 1) for index in indexes)
        living = tuple(
            getattr(monster, "level", 1)
            for monster in self.monsters
            if monster.is_alive
        )
        return () if not living else (max(living),)

    def _record_equipped_weapon_action(
        self,
        party_index: int,
        enemy_levels: tuple[int, ...],
        *,
        defeated_enemy_keys: tuple[str, ...] = (),
        critical: bool = False,
        right_hand_only: bool = False,
    ) -> None:
        """Record the physical command's equipped attacking hands."""

        if not hasattr(self, "progression") or not hasattr(self, "party"):
            return
        member = self.party[party_index]
        if not hasattr(member, "equipment"):
            return
        weapons = tuple(
            weapon
            for slot in (
                (EquipmentSlot.RIGHT,)
                if right_hand_only
                else (EquipmentSlot.LEFT, EquipmentSlot.RIGHT)
            )
            if (weapon := member.equipment.weapon_at(slot)) is not None
        )
        if weapons:
            self.progression.record_weapon_action(
                member,
                weapons,
                enemy_levels,
                defeated_enemy_keys=defeated_enemy_keys,
                critical=critical,
            )

    def _begin_action_presentation(
        self,
        spell: Spell,
    ) -> bool:
        """Create target effect timelines while retaining room for result layers."""

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

        self._prepare_spell_presentation(spell, indexes, ("ally", self.active_party_index))
        self.phase = BattlePhase.ACTION_PRESENTATION
        self.target_cursor.active = False
        if self.party_target_cursor is not None:
            self.party_target_cursor.active = False
        self.all_target_cursors = ()
        self._refresh_monster_name_colors()

        self._start_target_spell_effects(self.action_presentation.spell_effects)
        return True

    def _member_cast_modifier(self, spell: Spell) -> int:
        index = self.active_party_index
        if index is None:
            raise RuntimeError("a party spell requires an active member")
        actor = self.party[index]
        spell_level = (
            spell.level
            if spell.type is SpellType.ITEM
            else actor.proficiency(SPELL_PROFICIENCY_BY_TYPE[spell.type]).level
        )
        return member_spell_modifier(
            magic=actor.adjusted_abilities.magic,
            spell_level=spell_level,
            internal_level=actor.internal_level,
        )

    def _reflects_spell(self, side: str, index: int) -> bool:
        if side == "enemy":
            monster = self.monsters[index]
            # Only monsters with the Mirror action can defend.
            return monster.state.is_defending

        member = self.party[index]
        defending = (
            index in getattr(self, "defending_party_indexes", ())
            and not self._member_focus_is_interrupted(member)
        )
        chance = spell_reflection_chance(
            defending=defending,
            has_reflect=defending and member.has_skill("Reflect"),
            equipment_reflects=isinstance(member, Member) and any(
                item.special is ItemSpecial.REFLECT for item in member.equipment.equipped_items()
            ),
        )
        return chance == SPELL_REFLECTION_ROLL_COUNT or (
            chance > 0 and random.randrange(SPELL_REFLECTION_ROLL_COUNT) < chance
        )

    def _resolve_spell_hit_group(
        self,
        presentation: BattleActionPresentation,
        spell: Spell,
        indexes: tuple[int, ...],
        target_side: str,
        *,
        modifier: int,
    ) -> tuple[
        tuple[int, ...],
        tuple[BattleSpellDamageResult | BattleConfuseResult | BattleSleepResult | BattleSilenceResult, ...],
    ]:
        if target_side == "enemy":
            damage = self._resolve_spell_damage_results(spell, indexes, modifier=modifier)
            presentation.damage_results = damage
            presentation.poison_results = self._resolve_poison_results(spell, indexes, modifier=modifier)
            presentation.sleep_results = self._resolve_sleep_results(spell, indexes, modifier=modifier)
            presentation.confuse_results = self._resolve_confuse_results(spell, indexes, modifier=modifier)
            presentation.slow_results = self._resolve_slow_results(spell, indexes, modifier=modifier)
            presentation.break_results = self._resolve_break_results(spell, indexes, modifier=modifier)
            presentation.silence_results = self._resolve_silence_results(spell, indexes, modifier=modifier)
            statuses = (
                presentation.sleep_results or presentation.confuse_results
                or presentation.slow_results or presentation.break_results or presentation.silence_results
            )
            affinities = (
                *damage, *presentation.sleep_results,
                *presentation.confuse_results, *presentation.silence_results,
            )
        else:
            damage = self._resolve_monster_spell_damage_results(modifier, spell, indexes)
            presentation.party_damage_results = damage
            presentation.party_poison_results = self._resolve_monster_poison_results(modifier, spell, indexes)
            presentation.party_sleep_results = self._resolve_monster_sleep_results(modifier, spell, indexes)
            if spell.action is SpellAction.CONFUSE:
                presentation.party_confuse_results = self._resolve_monster_confuse_results(
                    modifier, indexes, rate=spell.rate, attribute=spell.attribute,
                )
            presentation.party_slow_results = self._resolve_monster_slow_results(modifier, spell, indexes)
            presentation.party_break_results = self._resolve_monster_break_results(modifier, spell, indexes)
            presentation.party_silence_results = self._resolve_monster_silence_results(modifier, spell, indexes)
            statuses = (
                presentation.party_sleep_results or presentation.party_confuse_results
                or presentation.party_slow_results or presentation.party_break_results
                or presentation.party_silence_results
            )
            affinities = damage
        if statuses:
            effect_indexes = tuple(result.target_index for result in statuses if result.success)
        elif damage:
            effect_indexes = tuple(result.target_index for result in damage if not result.is_miss)
        else:
            effect_indexes = indexes
        return effect_indexes, affinities

    def _prepare_spell_presentation(
        self, spell: Spell, indexes: tuple[int, ...], caster: tuple[str, int],
    ) -> None:
        caster_side, caster_index = caster
        caster_is_monster = caster_side == "enemy"
        monster_caster = self.monsters[caster_index] if caster_is_monster else None
        target_side = caster_side
        if spell.to_enemy:
            target_side = "ally" if caster_is_monster else "enemy"
        fade_escape = not caster_is_monster and spell.action in (SpellAction.FADE, SpellAction.TELEPORT)
        monster_revival = caster_is_monster and spell.action is SpellAction.REVIVE and not spell.to_enemy
        presentation = BattleActionPresentation(
            (),
            fade_escape=fade_escape,
            post_effect_wait_frame_count=(
                SPELL_POST_EFFECT_WAIT_FRAME_COUNT
                if caster_is_monster or spell.to_enemy or fade_escape else 0
            ),
        )
        if monster_revival:
            presentation.post_effect_wait_frame_count = (
                MONSTER_REVIVAL_DELAY_FRAME_COUNT + MONSTER_REVIVAL_FADE_FRAME_COUNT
            )
        self.action_presentation = presentation

        if not spell.to_enemy:
            presentation.healing_results = self._resolve_healing_results(
                spell, indexes, monster_caster=monster_caster,
            )
            presentation.protection_results = self._resolve_protection_results(
                spell, indexes, target_is_monster=caster_is_monster,
            )
            presentation.haste_results = self._resolve_haste_results(
                spell, indexes, target_is_monster=caster_is_monster,
            )
            if spell.action is SpellAction.MAGIC_SHIELD:
                presentation.magic_shield_targets = tuple((target_side, index) for index in indexes)
            presentation.revive_results = self._resolve_revive_results(
                spell, indexes, target_is_monster=caster_is_monster,
            )
            if not caster_is_monster:
                presentation.mana_results = self._resolve_mana_results(spell, indexes)
                presentation.cure_results = self._resolve_cure_results(spell, indexes)
            reflected = ()
        else:
            reflected = tuple(index for index in indexes if self._reflects_spell(target_side, index))
            if spell.action is SpellAction.BLOOD_SUCK:
                if caster_is_monster:
                    presentation.drain_monster_index = caster_index
                else:
                    presentation.drain_party_index = caster_index

        mirror_effects = self._build_target_spell_effects(
            SPELL_REFLECT_EFFECT_KEY, target_side, reflected, caster=caster,
        )
        mirror_duration = mirror_effects[0].player.definition.total_frames if mirror_effects else 0
        direct = tuple(index for index in indexes if index not in reflected)
        target_groups = [(target_side, direct)]
        if reflected:
            target_groups.append((caster_side, (caster_index,) * len(reflected)))

        effects = []
        result_frames = {}
        any_hit = False
        for side, targets in target_groups:
            if not targets:
                continue
            if spell.action is SpellAction.PURGE:
                presentation.purge_targets += tuple((side, index) for index in dict.fromkeys(targets))
                hits, affinities = targets, ()
            elif spell.to_enemy:
                modifier = (
                    monster_caster.magic
                    if monster_caster is not None
                    else self._member_cast_modifier(spell)
                )
                hits, affinities = self._resolve_spell_hit_group(
                    presentation, spell, targets, side, modifier=modifier,
                )
            else:
                hits, affinities = targets, ()
            unique_targets = tuple(dict.fromkeys(targets))
            hits = tuple(dict.fromkeys(hits))
            if len(unique_targets) < len(targets):
                # Several reflected portions land on one caster. Keep their damage in one popup.
                damage = (
                    presentation.damage_results
                    if side == "enemy" else presentation.party_damage_results
                )
                landed = tuple(result for result in damage if not result.is_miss)
                if damage:
                    total = (
                        replace(landed[0], damage=sum(result.damage for result in landed))
                        if landed else damage[0]
                    )
                    if side == "enemy":
                        presentation.damage_results = (total,)
                    else:
                        presentation.party_damage_results = (total,)
                    affinities = (total,)
                elif affinities:
                    affinities = affinities[:1]
            any_hit = any_hit or bool(hits)
            starts = self._spell_target_start_frames(spell, unique_targets, hits)
            cast_wait = 0
            if reflected:
                cast_wait = SPELL_REFLECTION_CAST_WAIT_FRAME_COUNT
                if side == caster_side:
                    cast_wait += mirror_duration
            starts = {index: cast_wait + starts.get(index, 0) for index in unique_targets}
            result_frames.update({(side, index): frame for index, frame in starts.items()})
            self._queue_spell_affinity_popups(affinities, starts)
            group_effects = self._build_target_spell_effects(
                spell.key, side, hits, caster=caster, target_start_frames=starts,
            )
            if group_effects and presentation.screen_flash is None:
                presentation.screen_flash = group_effects[0].player.screen_flash
                presentation.screen_flash_start_frame = group_effects[0].start_frame
            effects.extend(group_effects)

        if not caster_is_monster and not any_hit:
            presentation.post_effect_wait_frame_count += MISSED_ACTION_RETURN_WAIT_FRAME_COUNT
        presentation.spell_effects = (*mirror_effects, *effects)
        presentation.schedule_spell_results(
            result_frames, overlap_frame_count=0 if monster_revival else SPELL_RESULT_OVERLAP_FRAME_COUNT,
        )

    def _resolve_healing_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
        *,
        monster_caster: BattleMonster | None = None,
    ) -> tuple[BattleHealingResult, ...]:
        """Resolve each HEAL target without mutating its state yet."""

        if spell.action is not SpellAction.HEAL:
            return ()
        if spell.to_enemy:
            raise BattleDataError("HEAL spells must target allies")
        if spell.type is SpellType.ITEM:
            ability = DA2_DEFAULT_ITEM_SPELL_ABILITY
        elif monster_caster is not None:
            ability = monster_caster.magic
        else:
            if self.active_party_index is None:
                raise RuntimeError("HEAL requires an active party member")
            actor = self.party[self.active_party_index]
            ability = member_spell_ability(
                magic=actor.adjusted_abilities.magic,
                internal_level=actor.internal_level,
            )
        results: list[BattleHealingResult] = []
        for index in indexes:
            if monster_caster is not None:
                monster = self.monsters[index]
                target = monster.state
                _, y = self._monster_base_position(index)
                popup_x = self._monster_draw_x(index) + monster.width // 2
                popup_y = y + monster.height - 8
            else:
                target = self.party[index]
                position = self._party_draw_position(index)
                if position is None:
                    continue
                x, y = position
                popup_x, popup_y = x + 6, y + 16
            resolution = resolve_healing(
                intensity=spell.intensity,
                ability=ability,
                current_hp=target.hp,
                max_hp=target.max_hp,
                random_factor=random.random(),
            )
            results.append(
                BattleHealingResult(
                    target_index=index,
                    amount=resolution.amount,
                    cures_ailments=resolution.cures_ailments,
                    popup_x=popup_x,
                    popup_y=popup_y,
                    target_is_monster=monster_caster is not None,
                )
            )
        return tuple(results)

    def _resolve_mana_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
    ) -> tuple[BattleManaResult, ...]:
        """Resolve DA2's fixed-ability MP recovery before applying it."""

        if spell.action is not SpellAction.MANA:
            return ()
        if spell.to_enemy:
            raise BattleDataError("MANA spells must target allies")
        results: list[BattleManaResult] = []
        for index in indexes:
            position = self._party_draw_position(index)
            if position is None:
                continue
            x, y = position
            results.append(
                BattleManaResult(
                    target_index=index,
                    amount=resolve_recovery_amount(
                        intensity=spell.intensity,
                        ability=DA2_DEFAULT_ITEM_SPELL_ABILITY,
                        random_factor=random.random(),
                    ),
                    popup_x=x + 6,
                    popup_y=y + 16,
                )
            )
        return tuple(results)

    def _resolve_slow_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
        *,
        modifier: int | None = None,
    ) -> tuple[BattleSlowResult, ...]:
        """Resolve SLOW with the shared DA2-style status success rule."""

        if spell.action is not SpellAction.SLOW:
            return ()
        if not spell.to_enemy:
            raise BattleDataError("SLOW spells must target enemies")
        if modifier is None:
            modifier = self._member_cast_modifier(spell)
        results: list[BattleSlowResult] = []
        for index in indexes:
            monster = self.monsters[index]
            success = False
            if not self._enemy_spell_is_void(spell, index):
                success = resolve_status_spell(
                    spell_modifier=modifier,
                    rate=spell.rate,
                    target_spell_defense=monster.combat_stats.spell_resistance,
                    attribute=spell.attribute,
                    target_weaknesses=monster.weaknesses,
                    target_resistances=monster.spell_resistances,
                    success_roll=random.randint(0, 19),
                ).success
            _base_x, base_y = self._monster_base_position(index)
            center_x = self._monster_draw_x(index) + monster.width // 2
            results.append(
                BattleSlowResult(
                    target_index=index,
                    success=success,
                    popup_x=center_x,
                    popup_y=base_y + monster.height - 8,
                )
            )
        return tuple(results)

    def _resolve_break_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
        *,
        modifier: int | None = None,
    ) -> tuple[BattleBreakResult, ...]:
        """Resolve BREAK with DA2's status check and zero-defense immunity."""

        if spell.action is not SpellAction.BREAK:
            return ()
        if not spell.to_enemy:
            raise BattleDataError("BREAK spells must target enemies")
        if modifier is None:
            modifier = self._member_cast_modifier(spell)
        results: list[BattleBreakResult] = []
        for index in indexes:
            monster = self.monsters[index]
            success = False
            if monster.state.defense_modifier >= 0 and monster.effective_defense > 0:
                success = resolve_status_spell(
                    spell_modifier=modifier,
                    rate=spell.rate,
                    target_spell_defense=monster.combat_stats.spell_resistance,
                    attribute=spell.attribute,
                    target_weaknesses=monster.weaknesses,
                    target_resistances=monster.spell_resistances,
                    success_roll=random.randint(0, 19),
                ).success
            _base_x, base_y = self._monster_base_position(index)
            center_x = self._monster_draw_x(index) + monster.width // 2
            results.append(
                BattleBreakResult(
                    target_index=index,
                    success=success,
                    popup_x=center_x,
                    popup_y=base_y + monster.height - 8,
                )
            )
        return tuple(results)

    def _resolve_poison_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
        *,
        modifier: int | None = None,
    ) -> tuple[BattlePoisonResult, ...]:
        """Resolve poison attached to a poison-attribute enemy spell."""

        if spell.attribute is not ResistanceType.POISON:
            return ()
        if not spell.to_enemy:
            raise BattleDataError("poison-attribute spells must target enemies")
        if modifier is None:
            modifier = self._member_cast_modifier(spell)
        results: list[BattlePoisonResult] = []
        for index in indexes:
            monster = self.monsters[index]
            resolution = resolve_status_spell(
                spell_modifier=modifier,
                rate=spell.rate,
                target_spell_defense=monster.combat_stats.spell_resistance,
                attribute=spell.attribute,
                target_weaknesses=monster.weaknesses,
                target_resistances=monster.spell_resistances,
                success_roll=(
                    0
                    if spell.attribute in monster.spell_resistances
                    else random.randint(0, 19)
                ),
            )
            results.append(BattlePoisonResult(index, resolution.success))
        return tuple(results)

    def _resolve_protection_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
        *,
        target_is_monster: bool = False,
    ) -> tuple[BattleProtectionResult, ...]:
        """Resolve DA2's guaranteed one-stage defense increase."""

        if spell.action is not SpellAction.PROTECTION:
            return ()
        if spell.to_enemy:
            raise BattleDataError("PROTECTION spells must target allies")
        return tuple(BattleProtectionResult(index, target_is_monster) for index in indexes)

    def _resolve_haste_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
        *,
        target_is_monster: bool = False,
    ) -> tuple[BattleHasteResult, ...]:
        """Resolve DA2's guaranteed one-stage speed increase."""

        if spell.action is not SpellAction.HASTE:
            return ()
        if spell.to_enemy:
            raise BattleDataError("HASTE spells must target allies")
        return tuple(BattleHasteResult(index, target_is_monster) for index in indexes)

    def _resolve_cure_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
    ) -> tuple[BattleCureResult, ...]:
        """Resolve CURE without changing HP or battle-only buffs."""

        if spell.action is not SpellAction.CURE:
            return ()
        if spell.to_enemy:
            raise BattleDataError("CURE spells must target allies")
        return tuple(BattleCureResult(index) for index in indexes)

    def _resolve_revive_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
        *,
        target_is_monster: bool = False,
    ) -> tuple[BattleReviveResult, ...]:
        """Resolve REVIVE from its authored maximum-HP percentage."""

        if spell.action is not SpellAction.REVIVE:
            return ()
        if spell.to_enemy:
            raise BattleDataError("REVIVE spells must target allies")
        if not 1 <= spell.intensity <= 100:
            raise BattleDataError("REVIVE intensity must be from 1 to 100")
        return tuple(BattleReviveResult(index, spell.intensity, target_is_monster) for index in indexes)

    def _resolve_silence_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
        *,
        modifier: int | None = None,
    ) -> tuple[BattleSilenceResult, ...]:
        """Resolve SILENCE with the shared DA2-style status success rule."""

        if spell.action is not SpellAction.SILENCE:
            return ()
        if not spell.to_enemy:
            raise BattleDataError("SILENCE spells must target enemies")
        if modifier is None:
            modifier = self._member_cast_modifier(spell)
        results: list[BattleSilenceResult] = []
        for index in indexes:
            monster = self.monsters[index]
            if monster.spell_keys:
                resolution = resolve_status_spell(
                    spell_modifier=modifier,
                    rate=spell.rate,
                    target_spell_defense=monster.combat_stats.spell_resistance,
                    attribute=spell.attribute,
                    target_weaknesses=monster.weaknesses,
                    target_resistances=monster.spell_resistances,
                    success_roll=random.randint(0, 19),
                )
                success = resolution.success
                affinity = resolution.affinity
            else:
                success = False
                affinity = SpellAffinity.NORMAL
            _base_x, base_y = self._monster_base_position(index)
            center_x = self._monster_draw_x(index) + monster.width // 2
            results.append(
                BattleSilenceResult(
                    target_index=index,
                    success=success,
                    turns=(
                        random.randint(*debuff_turn_range(monster.resistances))
                        if success
                        else 0
                    ),
                    affinity=affinity,
                    popup_x=center_x,
                    popup_y=base_y + monster.height - 8,
                    affinity_x=center_x - AFFINITY_ICON_WIDTH // 2,
                    affinity_y=base_y + 20,
                )
            )
        return tuple(results)

    def _resolve_spell_damage_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
        *,
        modifier: int | None = None,
    ) -> tuple[BattleSpellDamageResult, ...]:
        """Resolve each DAMAGE target without mutating monster state yet."""

        if spell.action not in (SpellAction.DAMAGE, SpellAction.BLOOD_SUCK):
            return ()
        if not spell.to_enemy:
            raise BattleDataError("DAMAGE spells must target enemies")
        if modifier is None:
            modifier = self._member_cast_modifier(spell)
        results: list[BattleSpellDamageResult] = []
        for index in indexes:
            monster = self.monsters[index]
            resolution = resolve_spell_damage(
                intensity=spell.intensity,
                spell_modifier=modifier,
                target_spell_defense=monster.combat_stats.spell_resistance,
                attribute=spell.attribute,
                target_weaknesses=monster.weaknesses,
                target_resistances=monster.spell_resistances,
                target_is_shadow=monster.is_shadow,
                flying_effective=spell.effective_race == "FLYING",
                dark_resistance_causes_miss=spell.action is SpellAction.BLOOD_SUCK,
                random_factor=random.random(),
            )
            _base_x, base_y = self._monster_base_position(index)
            center_x = self._monster_draw_x(index) + monster.width // 2
            results.append(
                BattleSpellDamageResult(
                    target_index=index,
                    damage=resolution.damage,
                    affinity=resolution.affinity,
                    popup_x=center_x,
                    popup_y=base_y + monster.height - 8,
                    affinity_x=center_x - AFFINITY_ICON_WIDTH // 2,
                    affinity_y=base_y + 20,
                    is_miss=resolution.is_miss,
                )
            )
        return tuple(results)

    def _resolve_sleep_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
        *,
        modifier: int | None = None,
    ) -> tuple[BattleSleepResult, ...]:
        """Resolve SLEEP success and duration without mutating monsters yet."""

        if spell.action is not SpellAction.SLEEP:
            return ()
        if not spell.to_enemy:
            raise BattleDataError("SLEEP spells must target enemies")
        if modifier is None:
            modifier = self._member_cast_modifier(spell)
        results: list[BattleSleepResult] = []
        for index in indexes:
            monster = self.monsters[index]
            resolution = resolve_status_spell(
                spell_modifier=modifier,
                rate=spell.rate,
                target_spell_defense=monster.combat_stats.spell_resistance,
                attribute=spell.attribute,
                target_weaknesses=monster.weaknesses,
                target_resistances=monster.spell_resistances,
                success_roll=(
                    0
                    if spell.attribute is not None
                    and spell.attribute in monster.spell_resistances
                    else random.randint(0, 19)
                ),
            )
            _base_x, base_y = self._monster_base_position(index)
            center_x = self._monster_draw_x(index) + monster.width // 2
            results.append(
                BattleSleepResult(
                    target_index=index,
                    success=resolution.success,
                    turns=(
                        random.randint(SLEEP_MIN_TURNS, SLEEP_MAX_TURNS)
                        if resolution.success
                        else 0
                    ),
                    affinity=resolution.affinity,
                    popup_x=center_x,
                    popup_y=base_y + monster.height - 8,
                    affinity_x=center_x - AFFINITY_ICON_WIDTH // 2,
                    affinity_y=base_y + 20,
                )
            )
        return tuple(results)

    def _resolve_confuse_results(
        self,
        spell: Spell,
        indexes: tuple[int, ...],
        *,
        modifier: int | None = None,
    ) -> tuple[BattleConfuseResult, ...]:
        """Resolve CONFUSE success and duration without mutating monsters yet."""

        if spell.action is not SpellAction.CONFUSE:
            return ()
        if not spell.to_enemy:
            raise BattleDataError("CONFUSE spells must target enemies")
        if modifier is None:
            modifier = self._member_cast_modifier(spell)
        results: list[BattleConfuseResult] = []
        for index in indexes:
            monster = self.monsters[index]
            resolution = resolve_status_spell(
                spell_modifier=modifier,
                rate=spell.rate,
                target_spell_defense=monster.combat_stats.spell_resistance,
                attribute=spell.attribute,
                target_weaknesses=monster.weaknesses,
                target_resistances=monster.spell_resistances,
                success_roll=(
                    0
                    if spell.attribute is not None
                    and spell.attribute in monster.spell_resistances
                    else random.randint(0, 19)
                ),
            )
            _base_x, base_y = self._monster_base_position(index)
            center_x = self._monster_draw_x(index) + monster.width // 2
            results.append(
                BattleConfuseResult(
                    target_index=index,
                    success=resolution.success,
                    turns=(
                        random.randint(CONFUSE_MIN_TURNS, CONFUSE_MAX_TURNS)
                        if resolution.success
                        else 0
                    ),
                    affinity=resolution.affinity,
                    popup_x=center_x,
                    popup_y=base_y + monster.height - 8,
                    affinity_x=center_x - AFFINITY_ICON_WIDTH // 2,
                    affinity_y=base_y + 20,
                )
            )
        return tuple(results)

    def _apply_action_results(self, presentation: BattleActionPresentation) -> None:
        """Apply resolved state changes and start independent result popups."""

        if presentation.results_applied:
            return
        ready_targets = None
        if presentation.target_result_frames:
            ready_targets = {
                index for index, frame in presentation.target_result_frames.items()
                if frame <= presentation.elapsed_frame
                and index not in presentation.applied_spell_targets
            }
            if not ready_targets:
                return
            presentation.applied_spell_targets.update(ready_targets)
        presentation.results_applied = (
            len(presentation.applied_spell_targets) == len(presentation.target_result_frames)
        )
        for index in presentation.black_wind_targets:
            self.monsters[index].state.recover_with_black_wind()
        for side, index in presentation.magic_shield_targets:
            if ready_targets is None or (side, index) in ready_targets:
                target = self.monsters[index].state if side == "enemy" else self.party[index]
                target.magic_shield = True
        for side, index in presentation.purge_targets:
            if ready_targets is None or (side, index) in ready_targets:
                target = self.monsters[index].state if side == "enemy" else self.party[index]
                target.purge_buffs()

        def ready(
            results: Iterable[TargetedResult], side: str,
        ) -> Iterable[TargetedResult]:
            if ready_targets is None:
                return results
            return (result for result in results if (side, result.target_index) in ready_targets)

        popups = getattr(self, "healing_popups", None)
        if popups is None:
            popups = []
            self.healing_popups = popups
        for result in presentation.healing_results:
            target_side = "enemy" if result.target_is_monster else "ally"
            if ready_targets is not None and (target_side, result.target_index) not in ready_targets:
                continue
            index = result.target_index
            target = self.monsters[index].state if result.target_is_monster else self.party[index]
            target.apply_healing(
                result.amount, cure_ailments=result.cures_ailments,
            )
            if not result.target_is_monster:
                self._refresh_party_hp_text(index)
            if result.amount > 0:
                popups.append(
                    BattleHealingPopup(
                        result.popup_x,
                        result.popup_y,
                        result.amount,
                    )
                )
        damage_popups = getattr(self, "spell_damage_popups", None)
        if damage_popups is None:
            damage_popups = []
            self.spell_damage_popups = damage_popups
        for result in ready(presentation.mana_results, "ally"):
            if result.amount is None:
                damage_popups.append(
                    BattleSpellDamagePopup(result.popup_x, result.popup_y, 0, is_miss=True)
                )
                continue
            member = self.party[result.target_index]
            restored = min(result.amount, member.max_mp - member.mp)
            member.mp += restored
            if getattr(self, "party_status_shows_mp", False):
                self._refresh_party_hp_text(result.target_index)
            popup_amount = result.amount if result.show_rolled_amount else restored
            if popup_amount > 0:
                popups.append(
                    BattleHealingPopup(
                        result.popup_x,
                        result.popup_y,
                        popup_amount,
                    )
                )
        drained = 0
        for result in ready(presentation.damage_results, "enemy"):
            if not result.is_miss:
                monster = self.monsters[result.target_index]
                damage = monster.state.take_damage(result.damage)
                drained += damage
            damage_popups.append(
                BattleSpellDamagePopup(
                    result.popup_x,
                    result.popup_y,
                    result.damage,
                    is_miss=result.is_miss,
                )
            )
        for result in ready(presentation.sleep_results, "enemy"):
            monster = self.monsters[result.target_index]
            if result.success:
                monster.state.apply_sleep(result.turns)
            else:
                damage_popups.append(
                    BattleSpellDamagePopup(
                        result.popup_x,
                        result.popup_y,
                        0,
                        is_miss=True,
                    )
                )
        for result in ready(presentation.confuse_results, "enemy"):
            monster = self.monsters[result.target_index]
            if result.success:
                monster.state.apply_confusion(result.turns)
            else:
                damage_popups.append(
                    BattleSpellDamagePopup(
                        result.popup_x,
                        result.popup_y,
                        0,
                        is_miss=True,
                    )
                )
        for result in ready(presentation.poison_results, "enemy"):
            monster = self.monsters[result.target_index]
            if result.success and monster.is_alive:
                monster.state.apply_poison()
        for result in ready(presentation.slow_results, "enemy"):
            monster = self.monsters[result.target_index]
            if result.success and monster.state.apply_slow(
                random.randint(*debuff_turn_range(monster.resistances))
            ):
                self._delay_slow_target(monster)
            else:
                damage_popups.append(
                    BattleSpellDamagePopup(
                        result.popup_x,
                        result.popup_y,
                        0,
                        is_miss=True,
                    )
                )
        for result in ready(presentation.break_results, "enemy"):
            monster = self.monsters[result.target_index]
            if result.success:
                monster.state.apply_defense_down(
                    random.randint(*debuff_turn_range(monster.resistances)),
                    armor_break=True,
                )
            else:
                damage_popups.append(
                    BattleSpellDamagePopup(
                        result.popup_x,
                        result.popup_y,
                        0,
                        is_miss=True,
                    )
                )
        for result in presentation.protection_results:
            target_side = "enemy" if result.target_is_monster else "ally"
            if ready_targets is not None and (target_side, result.target_index) not in ready_targets:
                continue
            target = (
                self.monsters[result.target_index].state
                if result.target_is_monster
                else self.party[result.target_index]
            )
            target.apply_protection()
        for result in presentation.haste_results:
            target_side = "enemy" if result.target_is_monster else "ally"
            if ready_targets is not None and (target_side, result.target_index) not in ready_targets:
                continue
            target = (
                self.monsters[result.target_index].state
                if result.target_is_monster
                else self.party[result.target_index]
            )
            target.apply_haste()
        for result in ready(presentation.cure_results, "ally"):
            self.party[result.target_index].cure_ailments()
        for result in presentation.revive_results:
            index = result.target_index
            side = "enemy" if result.target_is_monster else "ally"
            if ready_targets is not None and (side, index) not in ready_targets:
                continue
            if result.target_is_monster:
                self._revive_monster(index, result.hp_percentage)
                continue
            member = self.party[index]
            if member.revive(result.hp_percentage) > 0:
                self._refresh_party_hp_text(index)
                visuals = getattr(self, "party_visuals", ())
                if index < len(visuals):
                    self._reinsert_revived_actor(visuals[index])
        for result in ready(presentation.silence_results, "enemy"):
            monster = self.monsters[result.target_index]
            if result.success:
                monster.state.apply_silence(result.turns)
            else:
                damage_popups.append(
                    BattleSpellDamagePopup(
                        result.popup_x,
                        result.popup_y,
                        0,
                        is_miss=True,
                    )
                )

        for result in ready(presentation.party_damage_results, "ally"):
            if not result.is_miss:
                damage = self._apply_monster_attack_damage(result.target_index, result.damage)
                drained += damage
            if presentation.background_tint_color is None:
                damage_popups.append(
                    BattleSpellDamagePopup(result.popup_x, result.popup_y, result.damage, is_miss=result.is_miss)
                )
        if presentation.drain_party_index is not None and drained:
            self._apply_party_drain(presentation.drain_party_index, drained)
        if presentation.drain_monster_index is not None and drained:
            index = presentation.drain_monster_index
            actor = self.monsters[index]
            restored = drain_healing_amount(
                damage=drained, hp=actor.state.hp, max_hp=actor.state.max_hp,
            )
            if restored:
                actor.state.apply_healing(restored)
                x, y = self._monster_base_position(index)
                popups.append(BattleHealingPopup(
                    x + actor.width // 2, y + actor.height - 8, restored,
                ))

        for result in ready(presentation.party_poison_results, "ally"):
            if result.success:
                self.party[result.target_index].apply_poison()

        for result in ready(presentation.party_stun_results, "ally"):
            if result.success:
                self._apply_additional_effects_to_member(result.target_index, (AdditionalEffect.STUN,))

        for result in ready(presentation.party_silence_results, "ally"):
            if result.success:
                self.party[result.target_index].apply_silence(result.turns)
            else:
                damage_popups.append(
                    BattleSpellDamagePopup(
                        result.popup_x, result.popup_y, 0, is_miss=True
                    )
                )

        for result in ready(presentation.party_sleep_results, "ally"):
            member = self.party[result.target_index]
            if result.success:
                member.apply_sleep(result.turns)
            else:
                damage_popups.append(
                    BattleSpellDamagePopup(
                        result.popup_x,
                        result.popup_y,
                        0,
                        is_miss=True,
                    )
                )
        for result in ready(presentation.party_confuse_results, "ally"):
            member = self.party[result.target_index]
            if result.success:
                member.apply_confusion(result.turns)
            else:
                damage_popups.append(
                    BattleSpellDamagePopup(
                        result.popup_x,
                        result.popup_y,
                        0,
                        is_miss=True,
                    )
                )
        for result in ready(presentation.party_slow_results, "ally"):
            member = self.party[result.target_index]
            if result.success and member.apply_slow(
                random.randint(*debuff_turn_range(member.resistances))
            ):
                self._delay_slow_target(member)
            else:
                damage_popups.append(
                    BattleSpellDamagePopup(
                        result.popup_x,
                        result.popup_y,
                        0,
                        is_miss=True,
                    )
                )
        for result in ready(presentation.party_break_results, "ally"):
            member = self.party[result.target_index]
            if result.success:
                member.apply_armor_break(
                    random.randint(*debuff_turn_range(member.resistances))
                )
            else:
                damage_popups.append(
                    BattleSpellDamagePopup(
                        result.popup_x,
                        result.popup_y,
                        0,
                        is_miss=True,
                    )
                )
        for result in presentation.confused_attack_results:
            if result.target_side == "ally":
                member = self.party[result.target_index]
                member.take_damage(result.damage)
                applied_effects = self._apply_additional_effects_to_member(
                    result.target_index,
                    result.additional_effects,
                )
                self._refresh_party_hp_text(result.target_index)
            elif result.target_side == "enemy":
                monster = self.monsters[result.target_index]
                monster.state.take_damage(result.damage)
                applied_effects = self._apply_additional_effects_to_monster(
                    result.target_index,
                    result.additional_effects,
                )
                promote_rear_monsters_if_front_empty(self.monsters)
            else:
                raise RuntimeError("confused attack target side must be ally or enemy")
            if AdditionalEffect.DEATH in applied_effects:
                self._show_instant_death_message(actor_is_enemy=True)
            damage_popups.append(
                BattleSpellDamagePopup(
                    result.popup_x,
                    result.popup_y,
                    result.damage,
                    is_miss=not result.is_hit,
                )
            )
            if result.is_hit:
                hit_se = BATTLE_HIT_SE_ID
                if result.drain_actor_index is not None:
                    actor = self.monsters[result.drain_actor_index]
                    if self._begin_monster_drain(
                        actor, result.damage, result.popup_x, result.popup_y
                    ):
                        self._apply_monster_drain_healing()
                        hit_se = BATTLE_DRAIN_SE_ID
                play_se(hit_se)

    def _delay_slow_target(self, target: Member | BattleMonster) -> None:
        """Reflect a successful SLOW in its target's waiting turn immediately."""

        order = getattr(self, "_timeline_order", None)
        if order is None:
            return
        for index, entry in enumerate(order.entries):
            actor = entry.actor
            if actor is target or (
                isinstance(actor, BattleCharacter) and actor.member is target
            ):
                self._timeline_order = adjust_timeline_entry_gauge(
                    order,
                    entry_index=index,
                    gauge_adjustment=SLOW_GAUGE_ADJUSTMENT,
                )
                self.timeline = self._timeline_order.actors
                return

    def _revive_monster(self, index: int, hp_percentage: int) -> None:
        if index not in self._monster_revival_target_indexes():
            return
        monster = self.monsters[index]
        if monster.state.revive(hp_percentage) == 0:
            return
        if hasattr(self, "progression"):
            self.progression.record_enemy_revival(index)
        self._refresh_monster_rows_from_slots()
        self._reinsert_revived_actor(monster)
        self._refresh_monster_target_cursor()

    def _reinsert_revived_actor(self, actor: BattleCharacter | BattleMonster) -> None:
        """Return a revived combatant to the current timeline at a reset gauge."""

        order = getattr(self, "_timeline_order", None)
        if order is None or any(entry.actor is actor for entry in order.entries):
            return
        agility = self._actor_agility(actor)
        self._timeline_order = insert_timeline_actor(
            order,
            actor,
            agility=agility,
            gauge=min(float(agility), GAUGE_READY_VALUE),
        )
        self.timeline = self._timeline_order.actors

    def _show_item_use_message(self, item: Item) -> None:
        """Show the used item, including a spell-school icon for weapons."""

        if (
            getattr(self, "action_popup_window", None) is None
            or getattr(self, "battle_popup", None) is None
        ):
            return
        name = item.localized_name(self.localizer)
        message = name
        if item.is_weapon and item.use_spell_key:
            spell = getattr(self, "spells", {}).get(item.use_spell_key)
            icon = SPELL_TYPE_ICON_TAGS.get(spell.type, "") if spell else ""
            if icon:
                message = LocalizedText(
                    f"{icon}{name}",
                    prefers_wide_font=name.prefers_wide_font,
                    narrow_spans=tuple(
                        (start + len(icon), end + len(icon))
                        for start, end in name.narrow_spans
                    ),
                )
        self._show_battle_popup(message, BATTLE_POPUP_FRAME_COUNT)

    def _show_spell_cast_message(
        self,
        spell: Spell,
        *,
        actor_is_enemy: bool = False,
    ) -> None:
        """Show a spell popup on the acting side's top screen edge."""

        if (
            getattr(self, "action_popup_window", None) is None
            or getattr(self, "battle_popup", None) is None
        ):
            return
        self._show_battle_popup(
            spell.localized_display_name(self.localizer),
            BATTLE_POPUP_FRAME_COUNT,
            align_left=actor_is_enemy,
        )

    def _show_monster_action_message(self, text_key: str) -> None:
        """Show one content-sized monster action popup at the upper left."""

        if (
            getattr(self, "action_popup_window", None) is None
            or getattr(self, "battle_popup", None) is None
        ):
            return
        self._show_battle_popup(
            self.texts.text(text_key, self.localizer),
            BATTLE_POPUP_FRAME_COUNT,
            align_left=True,
        )

    def _show_instant_death_message(self, *, actor_is_enemy: bool) -> None:
        """Show the applied instant-death effect on the attacker's side."""

        if (
            getattr(self, "action_popup_window", None) is None
            or getattr(self, "battle_popup", None) is None
        ):
            return
        self._show_battle_popup(
            self.texts.text("battle.attack.instant_death", self.localizer),
            BATTLE_POPUP_FRAME_COUNT,
            align_left=actor_is_enemy,
        )

    def _show_monster_spell_mp_lack_message(self, actor: BattleMonster) -> None:
        """Show DA2's localized insufficient-MP result on the enemy side."""

        if (
            getattr(self, "action_popup_window", None) is None
            or getattr(self, "battle_popup", None) is None
        ):
            return
        self._show_battle_popup(
            self.texts.formatted_text(
                "battle.monster.mp_lack",
                self.localizer,
                {"MONSTER": actor.display_name(self.localizer)},
            ),
            MONSTER_SPELL_FAILURE_FRAME_COUNT,
            align_left=True,
        )

    def _show_monster_spell_sealed_message(
        self, *, actor_is_enemy: bool = True
    ) -> None:
        """Show DA2's sealed-spell result on the enemy side."""

        if (
            getattr(self, "action_popup_window", None) is None
            or getattr(self, "battle_popup", None) is None
        ):
            return
        self._show_battle_popup(
            self.texts.text("battle.monster.spell_sealed", self.localizer),
            MONSTER_SPELL_FAILURE_FRAME_COUNT,
            align_left=actor_is_enemy,
        )

    def _show_battle_popup(
        self,
        message: str,
        frame_count: int,
        *,
        align_left: bool = False,
    ) -> None:
        """Place a content-sized action popup and restart its timer."""

        window = getattr(self, "action_popup_window", None)
        battle_popup = getattr(self, "battle_popup", None)
        if window is None or battle_popup is None:
            return
        window.clear_texts()
        placement = window.add_text(message, *BATTLE_ACTION_POPUP_TEXT_POSITION)
        text_width = tagged_text_width(
            placement.text,
            placement.font if placement.font is not None else window.font,
            font_spans=placement.font_spans,
        )
        window.width = min(
            SCREEN_WIDTH // TEXT_GRID_X,
            BATTLE_ACTION_POPUP_HORIZONTAL_PADDING_GRID
            + (text_width + TEXT_GRID_X - 1) // TEXT_GRID_X,
        )
        window.x = 0 if align_left else SCREEN_WIDTH // TEXT_GRID_X - window.width
        battle_popup.show(frame_count)

    def _party_effect_position(self, index: int) -> tuple[int, int]:
        return self._party_draw_position(index) or (
            self._party_sprite_x(index), PARTY_SPRITE_Y[index]
        )

    def _spell_effect_anchor(self, target_side: str, index: int) -> tuple[int, int]:
        """Return the sprite center, using the normal position for a hidden ally."""

        if target_side == "ally":
            x, y = self._party_effect_position(index)
            return x + 8, y + 16
        if target_side == "enemy":
            monster = self.monsters[index]
            _target_x, target_y = self._monster_base_position(index)
            return (
                self._monster_draw_x(index) + monster.width // 2,
                target_y + monster.height // 2,
            )
        raise ValueError("target_side must be 'ally' or 'enemy'")

    def _spell_target_start_frames(
        self, spell: Spell, indexes: tuple[int, ...], effect_indexes: tuple[int, ...],
    ) -> dict[int, int]:
        definition = getattr(self, "spell_effects", {}).get(spell.key)
        if (
            len(indexes) < 2
            or not effect_indexes
            or definition is None
            or definition.kind == BLOOD_SUCK_EFFECT_KIND
            or spell.action in (SpellAction.HEAVENGATE, SpellAction.BLOOD_SUCK)
        ):
            return {}
        start_frames = {}
        start_frame = 0
        has_landed = False
        for index in indexes:
            # As in DA2, misses before the first success share its start frame.
            start_frames[index] = start_frame
            has_landed = has_landed or index in effect_indexes
            if has_landed:
                start_frame += SPELL_TARGET_INTERVAL_FRAME_COUNT
        return start_frames

    def _queue_spell_affinity_popups(
        self,
        results: Iterable[
            BattleSpellDamageResult | BattleConfuseResult | BattleSleepResult | BattleSilenceResult
        ],
        target_start_frames: Mapping[int, int],
    ) -> None:
        affinity_popups = getattr(self, "affinity_popups", None)
        if affinity_popups is None:
            affinity_popups = []
            self.affinity_popups = affinity_popups
        for result in results:
            if result.affinity is SpellAffinity.NORMAL:
                continue
            popup = BattleAffinityPopup(result.affinity_x, result.affinity_y, result.affinity)
            start_frame = target_start_frames.get(result.target_index, 0)
            if start_frame:
                pending = self.action_presentation.pending_affinity_popups
                pending.setdefault(start_frame, []).append(popup)
            else:
                affinity_popups.append(popup)

    def _build_target_spell_effects(
        self, effect_key: str, target_side: str, indexes: tuple[int, ...],
        *, caster: tuple[str, int | None], target_start_frames: Mapping[int, int] | None = None,
    ) -> tuple[BattleTargetSpellEffect, ...]:
        definition = getattr(self, "spell_effects", {}).get(effect_key)
        if definition is None:
            return ()
        settings = getattr(self, "settings", None)
        screen_flash_enabled = settings is None or settings.screen_flash_enabled
        caster_side, caster_index = caster
        caster_anchor = (
            self._spell_effect_anchor(caster_side, caster_index)
            if definition.kind == BLOOD_SUCK_EFFECT_KIND and caster_index is not None else None
        )
        effects = []
        for order, index in enumerate(indexes):
            anchor_x, anchor_y = self._spell_effect_anchor(target_side, index)
            if effect_key == SPELL_REFLECT_EFFECT_KEY and target_side == "enemy":
                anchor_x += self.monsters[index].width // 2
            effects.append(BattleTargetSpellEffect(
                target_side,
                index,
                SpellEffectPlayer(
                    definition, anchor_x=anchor_x, anchor_y=anchor_y, target_side=target_side,
                    screen_flash_enabled=screen_flash_enabled and order == 0,
                    caster_anchor=caster_anchor,
                ),
                start_frame=target_start_frames.get(index, 0) if target_start_frames else 0,
            ))
        return tuple(effects)

    def _start_target_spell_effects(
        self, effects: tuple[BattleTargetSpellEffect, ...],
    ) -> None:
        if not effects:
            return
        self._stop_inner_steel_palette()
        self._release_palette_variant(UNSELECTABLE_TARGET_PALETTE)
        self._prepare_target_spell_effects(effects, 0)

    def _prepare_target_spell_effects(
        self, effects: tuple[BattleTargetSpellEffect, ...], elapsed_frame: int,
    ) -> None:
        start_sound = None
        active_players = []
        for effect in effects:
            if effect.start_frame == elapsed_frame:
                sound = effect.player.take_start_sound()
                if start_sound is None:
                    start_sound = sound
            if effect.start_frame <= elapsed_frame and not effect.player.completed:
                active_players.append(effect.player)
        if start_sound is not None:
            play_se(start_sound)
        if active_players:
            # Use a single palette for overlapping target flashes within Pyxel's color limit.
            strongest_flash = min(active_players, key=lambda player: player.flash_base_rate)
            self.spell_effect_renderer.prepare(strongest_flash)

    def sync_action_screen_flash(self, *, suspended: bool = False) -> None:
        """Apply the current tint only while the battle owns the screen."""

        presentation = getattr(self, "action_presentation", None)
        if presentation is not None and presentation.screen_flash is not None:
            self.spell_effect_renderer.prepare_screen_flash(
                None if suspended or presentation.elapsed_frame < presentation.screen_flash_start_frame
                else presentation.screen_flash,
                presentation.elapsed_frame - presentation.screen_flash_start_frame,
            )

    def _update_action_presentation(self) -> None:
        """Advance the action's effect and result layers, then complete the turn."""

        pending_spell = getattr(self, "pending_action_effect_spell", None)
        if pending_spell is not None:
            if self.action_offset_x == ACTION_MOVE_DISTANCE:
                self.pending_action_effect_spell = None
                self._start_confirmed_action_presentation(pending_spell)
            return
        presentation = getattr(self, "action_presentation", None)
        if presentation is None:
            command = getattr(self, "selected_command", None)
            if command in (BattleCommand.PRAY, BattleCommand.BREATH):
                index = self.action_party_index
                if index is not None and self.action_offset_x == ACTION_MOVE_DISTANCE:
                    if command is BattleCommand.PRAY:
                        self._start_pray_presentation(index)
                    else:
                        self._start_member_breath_presentation(index)
            else:
                self._complete_current_turn()
            return
        presentation.update()
        affinity_popups = presentation.pending_affinity_popups.pop(presentation.elapsed_frame, ())
        if affinity_popups:
            self.affinity_popups.extend(affinity_popups)
        if presentation.earthquake:
            presentation.shake_offset = (
                (
                    random.randint(-EARTHQUAKE_SHAKE_AMPLITUDE, EARTHQUAKE_SHAKE_AMPLITUDE),
                    random.randint(-EARTHQUAKE_SHAKE_AMPLITUDE, EARTHQUAKE_SHAKE_AMPLITUDE),
                )
                if presentation.elapsed_frame < presentation.result_start_frame else (0, 0)
            )
        if presentation.background_tint_color is not None:
            self._sync_action_background(presentation)
        self.sync_action_screen_flash()
        if (
            not presentation.results_applied
            and presentation.elapsed_frame >= presentation.result_start_frame
        ):
            self._apply_action_results(presentation)
        if presentation.is_complete:
            self._apply_action_results(presentation)
            defeated_indexes = [
                result.target_index
                for result in presentation.damage_results
                if not self.monsters[result.target_index].is_alive
            ]
            defeated_indexes.extend(
                result.target_index
                for result in presentation.confused_attack_results
                if result.target_side == "enemy"
                and not self.monsters[result.target_index].is_alive
            )
            defeated_indexes = list(dict.fromkeys(defeated_indexes))
            self.action_presentation = None
            progression_weapon = getattr(self, "action_progression_weapon", None)
            if defeated_indexes and progression_weapon is not None:
                party_index = getattr(self, "action_party_index", None)
                if party_index is not None:
                    self.progression.record_weapon_action(
                        self.party[party_index],
                        (progression_weapon,),
                        getattr(self, "action_progression_enemy_levels", ()),
                        defeated_enemy_keys=tuple(
                            self.monsters[index].key for index in defeated_indexes
                        ),
                    )
            self.action_progression_weapon = None
            self.action_progression_enemy_levels = ()
            self._release_palette_variant(SPELL_EFFECT_FLASH_PALETTE)
            if presentation.fade_escape:
                self._begin_fade_escape()
                return
            active_index = getattr(self, "active_party_index", None)
            party_caster_defeated = (
                active_index is not None and self._party_member_is_dead(active_index)
            )
            if (
                (party_caster_defeated or (defeated_indexes and presentation.party_damage_results))
                and self._party_is_defeated()
            ):
                self._clear_turn_state()
                self._begin_defeat_message()
                return
            if party_caster_defeated:
                self._clear_action_motion_state()
            if defeated_indexes:
                if getattr(self, "action_party_index", None) is not None:
                    self._begin_action_return()
                timeline = getattr(self, "timeline", ())
                if timeline and any(
                    self.monsters[index] is timeline[0] for index in defeated_indexes
                ):
                    self._begin_monster_deaths(defeated_indexes, from_timeline_head=True)
                else:
                    self._begin_monster_deaths(defeated_indexes)
                return
            if getattr(self, "action_party_index", None) is not None:
                self._begin_action_return(complete_turn=True)
                return
            self._complete_current_turn()
            return
        if presentation.spell_effects:
            self._release_palette_variant(UNSELECTABLE_TARGET_PALETTE)
            self._prepare_target_spell_effects(presentation.spell_effects, presentation.elapsed_frame)

    def _begin_fade_escape(self) -> None:
        """Freeze the completed battle frame for FADE's mosaic escape."""

        self.phase = BattlePhase.FADE_ESCAPE
        self.fade_escape_transition = MosaicFadeOut()
        self.fade_escape_snapshot = None
        self.fade_escape_bgm_fade_frame = 0
        self.palette_shifter.set_global_mix(
            base_rate=1.0,
            target_color=self.palette_shifter.base_colors[0],
        )

    def _update_fade_escape(self) -> None:
        """Grow the mosaic while fading the captured battle frame to black."""

        transition = getattr(self, "fade_escape_transition", None)
        if transition is None:
            raise RuntimeError("FADE escape phase requires a mosaic transition")
        if getattr(self, "fade_escape_snapshot", None) is None:
            return
        if not transition.is_finished:
            transition.update()
            self.palette_shifter.set_global_mix(
                base_rate=transition.visible_rate,
                target_color=self.palette_shifter.base_colors[0],
            )
            return

        self.fade_escape_bgm_fade_frame = min(
            self.fade_escape_bgm_fade_frame + 1,
            FADE_ESCAPE_BGM_FADE_FRAME_COUNT,
        )
        bgm_rate = 1.0 - (
            self.fade_escape_bgm_fade_frame / FADE_ESCAPE_BGM_FADE_FRAME_COUNT
        )
        self.bgm.set_fade_rate(bgm_rate)
        if self.fade_escape_bgm_fade_frame >= FADE_ESCAPE_BGM_FADE_FRAME_COUNT:
            self._begin_escape_result()

    def _update_healing_popups(self) -> None:
        """Advance recovery numbers independently from the battle phase."""

        popups = getattr(self, "healing_popups", None)
        if not popups:
            return
        for popup in popups:
            popup.update()
        self.healing_popups = [popup for popup in popups if not popup.completed]

    def _update_spell_damage_popups(self) -> None:
        """Advance spell-damage numbers independently from the battle phase."""

        popups = getattr(self, "spell_damage_popups", None)
        if not popups:
            return
        for popup in popups:
            popup.update()
        self.spell_damage_popups = [popup for popup in popups if not popup.completed]

    def _update_affinity_popups(self) -> None:
        """Advance WEAK/RESIST markers independently from the battle phase."""

        popups = getattr(self, "affinity_popups", None)
        if not popups:
            return
        for popup in popups:
            popup.update()
        self.affinity_popups = [popup for popup in popups if not popup.completed]

    def _begin_action_motion(
        self, *, use_cast_pose: bool, jump: bool = False, stationary: bool = False,
        party_index: int | None = None,
    ) -> None:
        """Set the actor's walk, jump, or in-place action motion."""

        if party_index is None:
            party_index = self.active_party_index
        if party_index is None:
            return
        self.action_party_index = party_index
        self.action_stationary = stationary
        self.action_returning = False
        self.action_uses_cast_pose = use_cast_pose
        self.action_forward_jump = jump
        self.action_return_jump = False
        self.action_return_frame = 0
        self.action_return_start_offset = 0
        self.action_landing_guard_frames_remaining = 0

    def _action_forward_jump_in_progress(self) -> bool:
        return (
            getattr(self, "action_forward_jump", False)
            and not self.action_returning
            and self.action_offset_x < ACTION_MOVE_DISTANCE
        )

    def _begin_action_return(
        self,
        *,
        complete_turn: bool = False,
        jump: bool = False,
    ) -> None:
        """Send the party actor back before optionally advancing."""

        if getattr(self, "action_stationary", False):
            self._clear_action_motion_state()
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

        if getattr(self, "action_party_index", None) is None or getattr(
            self, "action_stationary", False
        ):
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
        self.action_stationary = False
        self.action_offset_x = 0
        self.action_motion_frame = 0
        self.action_returning = False
        self.action_uses_cast_pose = False
        self.action_forward_jump = False
        self.action_return_jump = False
        self.action_return_frame = 0
        self.action_return_start_offset = 0
        self.action_landing_guard_frames_remaining = 0

    def _commit_item_use(self, candidate: BattleItemCandidate) -> bool:
        """Spend a confirmed item and remember what to restore on defeat."""

        item = candidate.item
        if not item.breaks_on_use:
            return True
        slot = candidate.equipment_slot
        if slot is None:
            if not self.inventory_system.remove(item):
                return False
            self._consumed_items[item.key] += 1
            return True
        index = self.active_party_index
        if index is None:
            return False
        member = self.party[index]
        if member.equipment.item_at(slot) != item:
            return False
        member.equipment = member.equipment.replaced({slot: None})
        result_index = getattr(self, "result_party", self.party).index(member)
        self._broken_equipment[result_index, slot] = item
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
        if getattr(self, "party_status_shows_mp", False):
            self.party_status_shows_mp = False
            self._refresh_all_party_hp_texts()
        self.target_cursor.active = False
        if self.party_target_cursor is not None:
            self.party_target_cursor.active = False
        self.party_target_cursor = None
        self.all_target_cursors = ()
        self._refresh_monster_name_colors()

    def _begin_identify_target_selection(self) -> bool:
        """Select any living monster, regardless of formation or weapon reach."""

        if self.active_party_index is None or not self.party[
            self.active_party_index
        ].has_skill("Identify"):
            return False
        selectable = tuple(
            index for index, monster in enumerate(self.monsters) if monster.is_alive
        )
        if not selectable:
            return False
        self.selected_command = BattleCommand.IDENTIFY
        self.selectable_target_indexes = selectable
        self.selected_target_index = selectable[-1]
        self.phase = BattlePhase.TARGET
        self._begin_action_motion(use_cast_pose=True)
        self.command_cursor.active = False
        self.target_cursor.active = True
        self.target_cursor.select_key(self.selected_target_index)
        self._refresh_monster_name_colors()
        return True

    def _begin_attack_target_selection(
        self,
        *,
        command: BattleCommand = BattleCommand.ATTACK,
    ) -> bool:
        if command not in (
            BattleCommand.ATTACK,
            BattleCommand.AMBUSH,
            BattleCommand.AIM,
            BattleCommand.IAI,
            BattleCommand.FOCUS,
            BattleCommand.BREATH,
        ):
            raise ValueError("attack target selection requires an attack command")
        selectable = self._active_member_attack_targets(command=command)
        if not selectable:
            return False

        self.selected_command = command
        self.selectable_target_indexes = selectable
        all_enemies = command in ALL_ENEMY_TARGET_COMMANDS
        # DA2 starts enemy selection at the last selectable monster.
        self.selected_target_index = None if all_enemies else selectable[-1]
        self.phase = BattlePhase.TARGET
        if command is not BattleCommand.FOCUS:
            self._begin_action_motion(
                use_cast_pose=False,
                jump=getattr(self, "auto_battle_active", False),
            )
        self.command_cursor.active = False
        self.target_cursor.active = not all_enemies
        if self.selected_target_index is not None:
            self.target_cursor.select_key(self.selected_target_index)
        if all_enemies:
            target_positions = tuple(
                target
                for target in self.target_cursor.targets
                if target.key in selectable
            )
            self.all_target_cursors = self._make_all_target_cursors(
                self.target_window, target_positions
            )
        self._refresh_monster_name_colors()
        return True

    def _update_target_selection(self, input_state: InputState) -> None:
        if getattr(self, "auto_battle_active", False):
            if self.selected_command is BattleCommand.FOCUS:
                self._begin_focus_presentation()
                return
            if self.action_offset_x < ACTION_MOVE_DISTANCE:
                return
            if self.selected_command is BattleCommand.IDENTIFY:
                self._begin_identify_presentation()
            elif self.selected_command is BattleCommand.BREATH:
                self._begin_member_breath()
            else:
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
            self.all_target_cursors = ()
            return

        if input_state.confirm.triggered:
            if self.selected_command is BattleCommand.FOCUS:
                self._begin_focus_presentation()
            elif self.selected_command is BattleCommand.IDENTIFY:
                self._begin_identify_presentation()
            elif self.selected_command is BattleCommand.BREATH:
                self._begin_member_breath()
            else:
                self._begin_attack_presentation()
            return

        if self.selected_command in ALL_ENEMY_TARGET_COMMANDS:
            for cursor in self.all_target_cursors:
                cursor.update()
        else:
            navigation = input_state.navigation
            if navigation is not None:
                self._move_target(navigation)
            self.target_cursor.update()

    def _begin_identify_presentation(self) -> bool:
        """Start DA2's twelve-frame Identify effect at ZERO's frame rate."""

        target_index = self.selected_target_index
        if (
            self.active_party_index is None
            or target_index is None
            or target_index not in self.selectable_target_indexes
        ):
            return False
        self.identify_target_index = target_index
        self.identify_effect_elapsed_frame = 0
        self.phase = BattlePhase.IDENTIFY_PRESENTATION
        self.target_cursor.active = False
        getattr(self, "hidden_party_indexes", set()).discard(self.active_party_index)
        self._refresh_monster_name_colors()
        play_se(BATTLE_IDENTIFY_SE_ID)
        return True

    def _update_identify_presentation(self) -> None:
        """Reveal the record and open DA2's battle detail after the effect."""

        self.identify_effect_elapsed_frame += 1
        if self.identify_effect_elapsed_frame < IDENTIFY_EFFECT_FRAME_COUNT:
            return
        target_index = self.identify_target_index
        if target_index is None:
            raise RuntimeError("identify presentation requires a target")
        monster = self.monsters[target_index]
        self.monster_record_system.reveal_all_identify_fields(monster.key)
        self.identified_monster_indexes.add(target_index)
        definition = self.monster_definitions_by_key[monster.key]
        if self.identify_text_factory is None:
            self.identify_text_factory = LocalizedWindowTextFactory.from_language(
                self.fonts,
                self.settings.language,
            )
        detail_texts = identify_detail_texts(
            number=self.monster_book_number_by_key[monster.key],
            definition=definition,
            revealed_fields=self.save_data.monster_records[monster.key],
            items=self.item_catalog,
            texts=self.texts,
            localizer=self.localizer,
            text_factory=self.identify_text_factory,
        )
        window_grid, _image_x = identify_detail_layout(
            monster,
            len(detail_texts),
        )
        self.identify_detail_window = self.window_factory.create(
            *window_grid,
            detail_texts,
        )
        self.identify_detail_window.open_immediately()
        self.phase = BattlePhase.IDENTIFY_RESULT

    def _update_identify_result(self, input_state: InputState) -> None:
        """Close the inspected detail and finish the acting member's turn."""

        if input_state.confirm.triggered or input_state.cancel.triggered:
            self._finish_identify_result()

    def _finish_identify_result(self) -> None:
        if self.identify_detail_window is not None:
            self.identify_detail_window.close_immediately()
        self.identify_detail_window = None
        self.identify_target_index = None
        self.identify_effect_elapsed_frame = 0
        self._begin_action_return(complete_turn=True)

    def _throwing_projectile_frame_count(
        self,
        actor_index: int,
        target_side: str,
        target_index: int,
        projectile_sprites: tuple[AttackWeaponSprite, ...],
        *,
        move_distance: int = ACTION_MOVE_DISTANCE,
    ) -> int:
        """Measure a throw from the actor's launch position to target center."""

        if not projectile_sprites:
            return 0
        first_sprite = projectile_sprites[0]
        start = (
            self._party_sprite_x(actor_index)
            - move_distance
            + first_sprite.position_x,
            PARTY_SPRITE_Y[actor_index] + first_sprite.position_y,
        )
        target_x, target_y = self._spell_effect_anchor(target_side, target_index)
        end = (
            target_x - ATTACK_WEAPON_SPRITE_SIZE // 2,
            target_y - ATTACK_WEAPON_SPRITE_SIZE // 2,
        )
        return throwing_projectile_frame_count(start, end)

    def _begin_attack_presentation(self) -> bool:
        """Resolve each equipped hand and start its authored attack sequence."""

        if self.selected_command is BattleCommand.IAI:
            return self._begin_iai_presentation()

        party_index = self.active_party_index
        index = self.selected_target_index
        if (
            party_index is None
            or index is None
            or index not in self.selectable_target_indexes
        ):
            return False
        return self._start_member_attack(party_index, index)

    def _start_member_attack(
        self, party_index: int, index: int, *, is_counter: bool = False,
    ) -> bool:
        """Resolve the weapon strikes against a confirmed enemy target."""

        monster = self.monsters[index]
        if not monster.is_alive:
            return False
        member = self.party[party_index]
        right_weapon = member.equipment.weapon_at(EquipmentSlot.RIGHT)
        if right_weapon is None:
            return False
        is_aimed = not is_counter and self.selected_command == BattleCommand.AIM
        is_focused = not is_counter and self.selected_command == BattleCommand.FOCUS
        attacker_hidden = party_index in getattr(
            self,
            "hidden_party_indexes",
            set(),
        )
        member_stats = member.battle_stats
        monster_stats = monster.combat_stats
        target_incapacitated = bool(monster.state.sleeping or monster.state.confused)
        attacker_has_power_hit = member.has_skill("Power Hit")
        left_weapon = member.equipment.weapon_at(EquipmentSlot.LEFT)
        equipped_attacks: list[tuple[Item, int, int, tuple[str, str]]] = [
            (
                right_weapon,
                member_stats.attack_right,
                member_stats.hit_right.total,
                ("1", "2"),
            )
        ]
        if (
            left_weapon is not None
            and member.has_skill("Dual-Wield")
            and member_stats.attack_left is not None
            and member_stats.hit_left is not None
        ):
            equipped_attacks.append(
                (
                    left_weapon,
                    member_stats.attack_left,
                    member_stats.hit_left.total,
                    ("4", "5") if left_weapon.subtype == "THROWING" else ("3", "4"),
                )
            )

        strikes: list[BattleAttackStrike] = []
        records = getattr(self, "monster_record_system", None)
        motion_start_frame = AIM_RETICLE_END_FRAME if is_aimed else 0
        for weapon, weapon_attack, weapon_hit, pose_branches in equipped_attacks:
            pose_change_frame = (
                AIM_ATTACK_HIT_START_FRAME
                if not strikes and is_aimed
                else motion_start_frame + ATTACK_POSE_RAISE_FRAME_COUNT
            )
            projectile_sprites = (
                throwing_projectile_sequence(
                    getattr(self, "attack_poses", {}),
                    weapon.weapon_img,
                    race=member.definition.race,
                    branches=("5", "6") if pose_branches == ("4", "5") else ("2", "3"),
                )
                if weapon.subtype == "THROWING"
                else ()
            )
            projectile_frame_count = self._throwing_projectile_frame_count(
                party_index,
                "enemy",
                index,
                projectile_sprites,
            )
            hit_start_frame = (
                pose_change_frame
                if not projectile_sprites
                else pose_change_frame
                + ATTACK_POSE_SWING_FRAME_COUNT
                + projectile_frame_count
                - 1
            )
            attack = self._member_weapon_attack(member, weapon, weapon_attack)
            if is_focused:
                attack *= FOCUS_ATTACK_MULTIPLIER
            weapon_has_power_hit = weapon.special is ItemSpecial.POWER_HIT
            weapon_attribute = WEAPON_ATTRIBUTE_RESISTANCE.get(weapon.attack_attribute)
            weapon_effective = physical_weapon_is_effective(
                effective_tribe=weapon.effective_tribe,
                target_tribe=getattr(monster, "tribe", None),
                attribute=weapon_attribute,
                target_weaknesses=monster.weaknesses,
                target_resistances=monster.resistances,
            )
            result = resolve_physical_attack(
                attack=attack,
                hit=weapon_hit,
                target_defense=monster.effective_defense,
                target_evasion=monster_stats.evasion,
                target_defending=getattr(monster.state, "is_defending", False),
                hit_roll=random.randint(0, 99),
                target_incapacitated=target_incapacitated,
                attacker_hidden=attacker_hidden,
                hit_value_bonus=AIM_HIT_VALUE_BONUS if is_aimed else 0,
                attacker_has_power_hit=attacker_has_power_hit,
                weapon_has_power_hit=weapon_has_power_hit,
                weapon_effective=weapon_effective,
                critical_rate_scale=(
                    1.5 if member.uses_two_handed_weapon(weapon) else 1.0
                ),
                critical_roll=(
                    random.randint(0, 99)
                    if (
                        target_incapacitated
                        or attacker_hidden
                        or attacker_has_power_hit
                        or weapon_has_power_hit
                        or weapon_effective
                    )
                    else None
                ),
            )
            strikes.append(
                BattleAttackStrike(
                    damage=result.damage,
                    poses=attack_sequence(
                        getattr(self, "attack_poses", {}),
                        weapon.weapon_img,
                        branches=pose_branches,
                    ),
                    effect_row=ATTACK_EFFECT_ROW_BY_SUBTYPE.get(weapon.subtype),
                    motion_start_frame=motion_start_frame,
                    hit_start_frame=hit_start_frame,
                    pose_change_frame=(
                        pose_change_frame if projectile_sprites else None
                    ),
                    projectile_sprites=projectile_sprites,
                    projectile_frame_count=projectile_frame_count,
                    effect_flip_x=bool(strikes),
                    is_hit=result.hit,
                    is_critical=getattr(result, "critical", False),
                    is_weak=weapon_effective,
                    drains_hp=weapon_can_drain(weapon.additional_effect, monster.resistances),
                    additional_effects=(
                        self._resolve_member_attack_additional_effects(
                            member,
                            weapon,
                            monster,
                            result,
                            attacker_hidden=attacker_hidden,
                            weapon_effective=weapon_effective,
                        )
                    ),
                    sound_effect_id=ATTACK_SE_ID_BY_SUBTYPE.get(
                        weapon.subtype,
                        ATTACK_SLASH_SE_ID,
                    ),
                )
            )
            motion_start_frame = (
                strikes[-1].motion_end_frame + DUAL_WIELD_ATTACK_INTERVAL_FRAME_COUNT
            )
            if records is not None and weapon_attribute is not None:
                records.reveal_affinity(monster.key, weapon_attribute)

        self.attack_presentation = BattleAttackPresentation(
            target_index=index,
            strikes=tuple(strikes),
            is_aimed=is_aimed,
            is_focused=is_focused,
            is_counter=is_counter,
        )
        if records is not None:
            records.reveal_profile(monster.key)
        self.phase = BattlePhase.ATTACK_PRESENTATION
        if not is_counter:
            self.action_gauge_adjustment = AIM_GAUGE_ADJUSTMENT if is_aimed else 0.0
        if is_aimed:
            self._show_battle_popup(
                self._command_label(BattleCommand.AIM),
                BATTLE_POPUP_FRAME_COUNT,
            )
        self.target_cursor.active = False
        self.command_window.close_immediately()
        if attacker_hidden:
            self.hidden_party_indexes.discard(party_index)
        self._refresh_monster_name_colors()
        return True

    def _begin_iai_presentation(self) -> bool:
        """Strike every living monster with the right-hand katana at once."""

        party_index = self.active_party_index
        if party_index is None:
            return False
        member = self.party[party_index]
        if not member_can_iai(
            member, attacker_is_front_row=self._party_member_is_front_row(party_index)
        ):
            return False
        targets = tuple(
            index
            for index in self.selectable_target_indexes
            if self.monsters[index].is_alive
        )
        if not targets:
            return False
        weapon = member.equipment.weapon_at(EquipmentSlot.RIGHT)
        stats = member.battle_stats
        attack = self._member_weapon_attack(member, weapon, stats.attack_right * 60 // 100)
        hidden = party_index in getattr(self, "hidden_party_indexes", set())
        power_hit = member.has_skill("Power Hit")
        weapon_power_hit = weapon.special is ItemSpecial.POWER_HIT
        attribute = WEAPON_ATTRIBUTE_RESISTANCE.get(weapon.attack_attribute)
        strikes: list[BattleAttackStrike] = []
        records = getattr(self, "monster_record_system", None)
        final_hit_start_frame = (
            ATTACK_POSE_RAISE_FRAME_COUNT
            + (len(targets) - 1) * IAI_TARGET_STAGGER_FRAME_COUNT
        )
        for target_order, index in enumerate(targets):
            monster = self.monsters[index]
            target_incapacitated = bool(monster.state.sleeping or monster.state.confused)
            effective = physical_weapon_is_effective(
                effective_tribe=weapon.effective_tribe,
                target_tribe=getattr(monster, "tribe", None),
                attribute=attribute,
                target_weaknesses=monster.weaknesses,
                target_resistances=monster.resistances,
            )
            result = resolve_physical_attack(
                attack=attack,
                hit=stats.hit_right.total,
                target_defense=monster.effective_defense,
                target_evasion=monster.combat_stats.evasion,
                target_defending=getattr(monster.state, "is_defending", False),
                hit_roll=random.randint(0, 99),
                target_incapacitated=target_incapacitated,
                attacker_hidden=hidden,
                attacker_has_power_hit=power_hit,
                weapon_has_power_hit=weapon_power_hit,
                weapon_effective=effective,
                critical_rate_scale=(
                    1.5 if member.uses_two_handed_weapon(weapon) else 1.0
                ),
                critical_roll=(
                    random.randint(0, 99)
                    if (
                        target_incapacitated
                        or hidden
                        or power_hit
                        or weapon_power_hit
                        or effective
                    )
                    else None
                ),
            )
            strikes.append(
                BattleAttackStrike(
                    damage=result.damage,
                    poses=attack_sequence(
                        getattr(self, "attack_poses", {}),
                        weapon.weapon_img,
                        branches=("5", "6"),
                    ),
                    effect_row=ATTACK_EFFECT_ROW_BY_SUBTYPE.get(weapon.subtype),
                    motion_start_frame=0,
                    hit_start_frame=(
                        ATTACK_POSE_RAISE_FRAME_COUNT
                        + target_order * IAI_TARGET_STAGGER_FRAME_COUNT
                    ),
                    pose_change_frame=final_hit_start_frame,
                    is_hit=result.hit,
                    is_critical=getattr(result, "critical", False),
                    is_weak=effective,
                    drains_hp=weapon_can_drain(weapon.additional_effect, monster.resistances),
                    additional_effects=self._resolve_member_attack_additional_effects(
                        member,
                        weapon,
                        monster,
                        result,
                        attacker_hidden=hidden,
                        weapon_effective=effective,
                    ),
                    sound_effect_id=ATTACK_SE_ID_BY_SUBTYPE.get(
                        weapon.subtype, ATTACK_SLASH_SE_ID
                    ),
                    target_index=index,
                )
            )
            if records is not None:
                records.reveal_profile(monster.key)
                if attribute is not None:
                    records.reveal_affinity(monster.key, attribute)
        self.attack_presentation = BattleAttackPresentation(
            target_index=targets[0],
            strikes=tuple(strikes),
            is_iai=True,
        )
        self.phase = BattlePhase.ATTACK_PRESENTATION
        self.action_gauge_adjustment = IAI_GAUGE_ADJUSTMENT
        self.target_cursor.active = False
        self.all_target_cursors = ()
        self.command_window.close_immediately()
        if hidden:
            self.hidden_party_indexes.discard(party_index)
        self._refresh_monster_name_colors()
        return True

    @staticmethod
    def _effect_candidates_for_member_attack(
        member: Member,
        weapon: Item,
    ) -> tuple[tuple[AdditionalEffect, bool], ...]:
        """Return weapon/Lethal effects, merging duplicate instant death."""

        weapon_effect = weapon.additional_effect
        if weapon_effect not in PHYSICAL_STATUS_EFFECTS:
            weapon_effect = None
        has_lethal = member.has_skill("Lethal")
        if weapon_effect is AdditionalEffect.DEATH and has_lethal:
            return ((AdditionalEffect.DEATH, True),)
        effects: list[tuple[AdditionalEffect, bool]] = []
        if weapon_effect is not None:
            effects.append((weapon_effect, False))
        if has_lethal:
            effects.append((AdditionalEffect.DEATH, False))
        return tuple(effects)

    def _resolve_member_attack_additional_effects(
        self,
        member: Member,
        weapon: Item,
        monster: BattleMonster,
        result: PhysicalAttackResult,
        *,
        attacker_hidden: bool = False,
        weapon_effective: bool = False,
    ) -> tuple[AdditionalEffect, ...]:
        """Resolve all DA2-style effects carried by one successful strike."""

        candidates = self._effect_candidates_for_member_attack(member, weapon)
        if not result.hit or not candidates:
            return ()
        effect_roll = random.randint(0, 99)
        successful: list[AdditionalEffect] = []
        for effect, stacked_death in candidates:
            resistance = PHYSICAL_EFFECT_RESISTANCE[effect]
            resolution = resolve_physical_additional_effect(
                effect=effect,
                adjusted_hit=result.adjusted_hit,
                effect_roll=effect_roll,
                target_is_member=False,
                target_has_boss_resistance=ResistanceType.DEATH in monster.resistances,
                target_is_weak=(
                    resistance is not None and resistance in monster.weaknesses
                ),
                target_is_resistant=(
                    resistance is not None and resistance in monster.resistances
                ),
                target_defending=getattr(getattr(monster, "state", None), "is_defending", False),
                critical=result.critical,
                attacker_hidden=attacker_hidden,
                weapon_effective=weapon_effective,
                stacked_death=stacked_death,
            )
            if resolution.success:
                successful.append(effect)
        return tuple(successful)

    def _apply_additional_effects_to_monster(
        self,
        target_index: int,
        effects: tuple[AdditionalEffect, ...],
    ) -> tuple[AdditionalEffect, ...]:
        """Apply successful effects after damage while the target still lives."""

        monster = self.monsters[target_index]
        if not monster.is_alive:
            return ()
        applied: list[AdditionalEffect] = []
        for effect in effects:
            changed = False
            if effect is AdditionalEffect.DEATH:
                monster.state.defeat()
                changed = True
            elif effect is AdditionalEffect.SLEEP:
                monster.state.apply_sleep(
                    random.randint(SLEEP_MIN_TURNS, SLEEP_MAX_TURNS)
                )
                changed = True
            elif effect is AdditionalEffect.CONFUSE:
                changed = monster.state.apply_confusion(
                    random.randint(CONFUSE_MIN_TURNS, CONFUSE_MAX_TURNS)
                )
            elif effect is AdditionalEffect.POISON:
                changed = monster.state.apply_poison()
            elif effect is AdditionalEffect.SILENCE and monster.spell_keys:
                changed = monster.state.apply_silence(
                    random.randint(*debuff_turn_range(monster.resistances))
                )
            elif effect is AdditionalEffect.STUN:
                changed = monster.state.apply_stun()
            elif effect is AdditionalEffect.DEFENSE_DOWN:
                changed = monster.state.apply_defense_down(
                    random.randint(*debuff_turn_range(monster.resistances))
                )
            if changed:
                applied.append(effect)
        if applied:
            promote_rear_monsters_if_front_empty(self.monsters)
        return tuple(applied)

    def _update_attack_presentation(self) -> None:
        """Apply each hand's hit, show its result, and start the return."""

        presentation = getattr(self, "attack_presentation", None)
        if presentation is None:
            self._complete_current_turn()
            return
        if self._action_forward_jump_in_progress():
            return
        presentation.elapsed_frame += 1
        if (
            presentation.is_iai
            and not presentation.sound_played
            and presentation.elapsed_frame >= presentation.strikes[-1].hit_start_frame
        ):
            play_se(presentation.strikes[-1].sound_effect_id)
            presentation.sound_played = True
        targets_enemy = presentation.target_side == "enemy"
        monster = self.monsters[presentation.target_index] if targets_enemy else None
        member = self.party[presentation.target_index] if not targets_enemy else None
        party_index = getattr(self, "action_party_index", None)
        for strike in presentation.strikes:
            strike_target_index = (
                presentation.target_index
                if strike.target_index is None
                else strike.target_index
            )
            if targets_enemy:
                monster = self.monsters[strike_target_index]
            provokes_counter = targets_enemy and not presentation.is_counter and (
                presentation.is_iai or strike is presentation.strikes[0]
            )
            if (
                not strike.damage_applied
                and strike.hit_elapsed_frame(presentation.elapsed_frame) >= 0
            ):
                if strike.is_hit:
                    applied_effects = ()
                    hit_target = False
                    if targets_enemy and monster is not None and monster.is_alive:
                        monster.state.take_damage(strike.damage)
                        hit_target = True
                        if provokes_counter:
                            self._queue_monster_counter(strike_target_index)
                        applied_effects = self._apply_additional_effects_to_monster(
                            strike_target_index,
                            strike.additional_effects,
                        )
                        promote_rear_monsters_if_front_empty(self.monsters)
                    elif member is not None and not self._member_is_dead(member):
                        member.take_damage(strike.damage)
                        hit_target = True
                        applied_effects = self._apply_additional_effects_to_member(
                            presentation.target_index,
                            strike.additional_effects,
                        )
                        self._refresh_party_hp_text(presentation.target_index)
                    if hit_target and strike.drains_hp and party_index is not None:
                        self._apply_party_drain(party_index, strike.damage)
                    strike.additional_effects = applied_effects
                    if not presentation.is_iai:
                        if AdditionalEffect.DEATH in applied_effects:
                            self._show_instant_death_message(actor_is_enemy=False)
                        play_se(strike.sound_effect_id)
                elif provokes_counter:
                    self._queue_monster_counter(strike_target_index)
                strike.damage_applied = True
            if (
                strike.is_hit
                and strike.is_weak
                and targets_enemy
                and monster is not None
                and not strike.affinity_popup_started
                and strike.damage_popup_elapsed_frame(presentation.elapsed_frame) >= 0
            ):
                _base_x, base_y = self._monster_base_position(strike_target_index)
                center_x = (
                    self._monster_draw_x(strike_target_index) + monster.width // 2
                )
                affinity_popups = getattr(self, "affinity_popups", None)
                if affinity_popups is None:
                    affinity_popups = []
                    self.affinity_popups = affinity_popups
                affinity_popups.append(
                    BattleAffinityPopup(
                        center_x - AFFINITY_ICON_WIDTH // 2,
                        base_y + 20,
                        SpellAffinity.WEAK,
                    )
                )
                strike.affinity_popup_started = True
        if not presentation.progression_recorded and all(
            strike.damage_applied for strike in presentation.strikes
        ):
            if party_index is not None and monster is not None:
                target_indexes = tuple(
                    dict.fromkeys(
                        (
                            presentation.target_index
                            if strike.target_index is None
                            else strike.target_index
                        )
                        for strike in presentation.strikes
                    )
                )
                self._record_equipped_weapon_action(
                    party_index,
                    tuple(
                        getattr(self.monsters[index], "level", 1)
                        for index in target_indexes
                    ),
                    defeated_enemy_keys=tuple(
                        self.monsters[index].key
                        for index in target_indexes
                        if not self.monsters[index].is_alive
                    ),
                    critical=any(strike.is_critical for strike in presentation.strikes),
                    **({"right_hand_only": True} if presentation.is_iai else {}),
                )
            presentation.progression_recorded = True
        return_wait_frames = (
            0
            if presentation.is_iai
            else (
                FOCUSED_ATTACK_RETURN_WAIT_FRAME_COUNT
                if presentation.is_focused
                else (
                    JUMP_ATTACK_RETURN_WAIT_FRAME_COUNT
                    if getattr(self, "action_forward_jump", False)
                    else 0
                )
            )
        )
        all_strikes_missed = not any(strike.is_hit for strike in presentation.strikes)
        if all_strikes_missed:
            return_wait_frames += MISSED_ACTION_RETURN_WAIT_FRAME_COUNT
        if (
            not presentation.return_started
            and presentation.elapsed_frame
            >= presentation.motion_frame_count + return_wait_frames
        ):
            presentation.return_started = True
            self._begin_action_return(
                jump=presentation.is_iai
                or not getattr(self, "action_forward_jump", False),
            )
        if (
            not presentation.return_started
            or not presentation.result_complete
            or (
                (all_strikes_missed or presentation.is_counter)
                and getattr(self, "action_party_index", None) is not None
            )
        ):
            return
        if presentation.is_iai:
            defeated = tuple(
                index
                for index in dict.fromkeys(
                    strike.target_index for strike in presentation.strikes
                )
                if index is not None and not self.monsters[index].is_alive
            )
            self.attack_presentation = None
            if defeated:
                self._begin_monster_deaths(defeated)
            else:
                self._complete_current_turn()
            return
        target_index = presentation.target_index
        target_is_alive = (
            self.monsters[target_index].is_alive
            if targets_enemy
            else not self._party_member_is_dead(target_index)
        )
        self.attack_presentation = None
        if not target_is_alive and targets_enemy:
            if presentation.is_counter:
                self._begin_monster_death(target_index, from_timeline_head=True)
            else:
                self._begin_monster_death(target_index)
            return
        if not target_is_alive:
            self._remove_defeated_party_from_timeline()
        self._complete_current_turn()

    def _begin_monster_death(
        self,
        index: int | None = None,
        *,
        from_timeline_head: bool = False,
    ) -> bool:
        """Start the defeat effect for a target whose HP reached zero."""

        if index is None:
            index = self.selected_target_index
        if index is None:
            return False
        return self._begin_monster_deaths(
            (index,),
            from_timeline_head=from_timeline_head,
        )

    def _begin_monster_deaths(
        self,
        indexes: Iterable[int],
        *,
        from_timeline_head: bool = False,
    ) -> bool:
        """Start one synchronized defeat effect for one or more targets."""

        dying_indexes = tuple(dict.fromkeys(indexes))
        if not dying_indexes:
            return False
        if from_timeline_head and len(dying_indexes) != 1:
            raise ValueError("timeline-head death must have exactly one target")
        if hasattr(self, "progression"):
            if len(dying_indexes) == 1:
                self.progression.record_enemy_defeat(dying_indexes[0])
            else:
                self.progression.record_simultaneous_enemy_defeats(dying_indexes)
        for index in dying_indexes:
            monster = self.monsters[index]
            if monster.is_alive:
                monster.state.defeat()
        promote_rear_monsters_if_front_empty(self.monsters)
        self.phase = BattlePhase.MONSTER_DEATH
        self.dying_monster_indexes = dying_indexes
        self.monster_death_from_timeline_head = from_timeline_head
        self.monster_death_animation = MonsterDeathAnimation()
        self.monster_death_delay_frames_remaining = (
            BOSS_MONSTER_DEATH_DELAY_FRAME_COUNT
            if any(self.monsters[index].is_boss for index in dying_indexes)
            else 0
        )
        self.target_cursor.active = False
        self.command_window.close_immediately()
        if not self.monster_death_delay_frames_remaining:
            self._start_monster_death_effect()
        return True

    def _start_monster_death_effect(self) -> None:
        """Apply the initial death tint and play its sound once."""

        self._sync_monster_death_palette()
        play_se(BATTLE_MONSTER_DEATH_SE_ID)

    def _update_monster_death_animation(self) -> None:
        """Advance the death effect, remove its actor, and finish the turn."""

        animation = self.monster_death_animation
        if animation is None:
            raise RuntimeError("monster death phase requires an animation")
        if getattr(self, "monster_death_delay_frames_remaining", 0):
            self.monster_death_delay_frames_remaining -= 1
            if not self.monster_death_delay_frames_remaining:
                self._start_monster_death_effect()
            return
        animation.update()
        if not animation.is_finished:
            self._sync_monster_death_palette()
            return

        dying_indexes = self.dying_monster_indexes
        if not dying_indexes:
            raise RuntimeError("monster death phase requires at least one target")
        from_timeline_head = getattr(
            self,
            "monster_death_from_timeline_head",
            False,
        )
        if not from_timeline_head:
            self._remove_timeline_actors(
                tuple(self.monsters[index] for index in dying_indexes)
            )
        self.monster_death_animation = None
        self.monster_death_delay_frames_remaining = 0
        self.dying_monster_indexes = ()
        self.monster_death_from_timeline_head = False
        self._release_palette_variant(MONSTER_DEATH_PALETTE)
        if self._monsters_are_defeated():
            self._begin_victory_summary()
            return
        if from_timeline_head:
            self._start_timeline_removal_animation()
            return
        if getattr(self, "action_party_index", None) is not None:
            self.phase = BattlePhase.ACTION_RETURN
            return
        self._complete_current_turn()

    def _monsters_are_defeated(self) -> bool:
        """Return whether every monster in this encounter has died."""

        return bool(self.monsters) and all(
            not monster.is_alive for monster in self.monsters
        )

    def _begin_victory_summary(self) -> None:
        """Settle rewards and show DA1's victory message over the battlefield."""

        self.auto_battle_active = False
        self.auto_battle_planner = None

        self._remove_timeline_actors(self.monsters)
        self.timeline_animation_phase = None
        self.timeline_animation_frame = 0
        self.timeline_advance = None
        self._begin_hidden_party_victory_return()
        self._clear_damage_popups_for_victory()
        if not all(
            hasattr(self, name)
            for name in ("party", "result_party", "progression", "save_data")
        ):
            self.result = BattleResult.VICTORY
            return
        for member in self.result_party:
            member.sleeping = 0
        hp_growth_ineligible = {
            member.definition.key
            for index, member in enumerate(self.party)
            if index in self.escaped_party_indexes or member.is_dead
        }
        growth = self.progression.settle(
            self.save_data,
            self.result_party,
            ineligible_member_keys=(
                {member.definition.key for member in self.result_party}
                - self.knockout_participant_keys
                if getattr(self, "knockout_battle", False)
                else ()
            ),
            hp_growth_ineligible_member_keys=hp_growth_ineligible,
            inventory_system=self.inventory_system,
            monster_record_system=self.monster_record_system,
            proficiency_level_limit=self.proficiency_level_limit,
            experience_limit=self.experience_limit,
            character_states=self.character_states,
        )
        self.growth_result = growth
        self.result_outcome = BattleResult.VICTORY
        message = self.texts.formatted_text(
            "battle.victory.reward",
            self.localizer,
            {
                "EXP": self._victory_number(growth.experience_gained),
                "GOLD": self._victory_number(growth.gold_gained),
            },
        )
        localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )
        placements = self._victory_summary_placements(
            message,
            growth,
            localized_texts,
        )
        treasure_drop = growth.treasure_drop
        self.victory_summary_window = WindowFactory(
            self.fonts.font_for(Language.JAPANESE)
        ).create(
            0,
            0,
            64,
            10 if treasure_drop is not None else 7,
            placements,
        )
        self.victory_motion_frame = 0
        self.phase = BattlePhase.VICTORY_SUMMARY
        self.active_party_index = None
        self._play_victory_jingle(BATTLE_WIN_BGM_ID)

    def _begin_escape_result(self) -> None:
        """Settle escape growth and reveal its result screen from black."""

        self.bgm.stop()
        self.bgm.set_fade_rate(1.0)
        growth = self.progression.settle_escape(
            self.save_data,
            self.result_party,
            proficiency_level_limit=self.proficiency_level_limit,
        )
        self.growth_result = growth
        self.result_outcome = BattleResult.ESCAPED
        if not growth.has_result_growth:
            self.result = BattleResult.ESCAPED
            return
        if self.return_bgm_id is not None:
            self.bgm.transition_to(
                self.return_bgm_id,
                start_sec=self.return_bgm_start_sec,
            )
        self.result_overlay = BattleResultOverlay(
            party=self.result_party,
            growth=growth,
            settings=self.settings,
            fonts=self.fonts,
            character_sprites=self.character_sprites,
            palette_shifter=self.palette_shifter,
            spells=tuple(self.spells.values()),
            texts=self.texts,
        )
        self.escape_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.result_transition_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.result_transition_fade.start_fade_in()
        self.result_transition_covered = True
        self.phase = BattlePhase.RESULT_TRANSITION

    def _victory_summary_placements(
        self,
        reward_message: str,
        growth: BattleGrowthResult,
        localized_texts: LocalizedWindowTextFactory,
    ) -> tuple[WindowText, ...]:
        """Build the reward line and its optional colored treasure line."""

        placements = [localized_texts.create(reward_message, 2, 2)]
        treasure_drop = growth.treasure_drop
        if treasure_drop is None:
            return tuple(placements)
        item = self.item_catalog[treasure_drop.item_key]
        treasure_message = self.texts.formatted_text(
            "battle.victory.treasure",
            self.localizer,
            {"ITEM": item.localized_name(self.localizer)},
        )
        placements.append(localized_texts.create(treasure_message, 2, 5))
        return tuple(placements)

    def _begin_hidden_party_victory_return(self) -> None:
        """Bring DA2's hidden survivors back from beyond the right edge."""

        hidden = getattr(self, "hidden_party_indexes", None)
        if hidden is None:
            hidden = set()
            self.hidden_party_indexes = hidden
        active = set(self._active_party_indexes())
        self.victory_returning_party_indexes = hidden.intersection(active)
        self.victory_return_frame = 0
        hidden.clear()

    def _update_hidden_party_victory_return(self) -> bool:
        """Advance hidden survivors leftward at twice DA2's converted run speed."""

        returning = getattr(self, "victory_returning_party_indexes", None)
        if not returning:
            return False
        self.victory_return_frame += 1
        returning.intersection_update(
            index
            for index in returning
            if VICTORY_RETURN_START_X - self.victory_return_frame * VICTORY_RETURN_SPEED
            >= self._party_sprite_x(index)
        )
        return bool(returning)

    def _victory_return_x(self, index: int) -> int:
        """Return one formerly hidden member's current victory-entry X."""

        return max(
            self._party_sprite_x(index),
            VICTORY_RETURN_START_X - self.victory_return_frame * VICTORY_RETURN_SPEED,
        )

    def _clear_damage_popups_for_victory(self) -> None:
        """Keep completed-battle damage numbers out of the victory screen."""

        popups = getattr(self, "spell_damage_popups", None)
        if popups is not None:
            popups.clear()

    def _victory_number(self, value: int) -> str:
        if self.settings.language is Language.JAPANESE:
            return format_number(value)
        return str(value)

    def _play_victory_jingle(self, bgm_id: str) -> None:
        if self.next_knockout_bgm_id is not None:
            self.bgm.play_once_then(bgm_id, self.next_knockout_bgm_id)
        elif self.return_bgm_id is None:
            self.bgm.play(bgm_id, loop=False)
        else:
            self.bgm.play_once_then(
                bgm_id,
                self.return_bgm_id,
                next_start_sec=self.return_bgm_start_sec,
            )

    def _update_victory_summary(self, input_state: InputState) -> None:
        self.victory_motion_frame = min(
            self.victory_motion_frame + 1,
            VICTORY_MOTION_LIMIT,
        )
        if self._finish_pending_victory():
            return
        if self._update_hidden_party_victory_return():
            return
        if not input_state.confirm.triggered:
            return
        growth = getattr(self, "growth_result", None)
        if growth is None:
            raise RuntimeError("victory result requires settled growth")
        if not growth.has_result_growth and not getattr(self, "knockout_battle", False):
            self._request_victory_completion()
            return
        self.result_overlay = BattleResultOverlay(
            party=self.result_party,
            growth=growth,
            settings=self.settings,
            fonts=self.fonts,
            character_sprites=self.character_sprites,
            palette_shifter=self.palette_shifter,
            spells=tuple(self.spells.values()),
            texts=self.texts,
            growth_member_keys=getattr(self, "knockout_participant_keys", None),
        )
        self.result_transition_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        self.result_transition_fade.start()
        self.result_transition_covered = False
        self.phase = BattlePhase.RESULT_TRANSITION

    def _update_result_transition(self) -> None:
        event = self.result_transition_fade.update()
        self.palette_shifter.set_global_mix(
            base_rate=self.result_transition_fade.visible_rate,
            target_color=self.palette_shifter.base_colors[0],
        )
        if event is FadeEvent.COVERED:
            self.result_transition_covered = True
        elif event is FadeEvent.FINISHED:
            self.phase = BattlePhase.RESULT

    def _update_result(self, input_state: InputState) -> None:
        if (
            self.result_outcome is BattleResult.VICTORY
            and self._finish_pending_victory()
        ):
            return
        overlay = self.result_overlay
        if overlay is None:
            raise RuntimeError("result phase requires a result overlay")
        was_complete = overlay.animation_complete
        completed = overlay.update(input_state)
        if (
            not was_complete
            and overlay.animation_complete
            and self.growth_result.has_level_up_growth
        ):
            self._play_victory_jingle(BATTLE_LEVEL_UP_BGM_ID)
            self.growth_jingle_played = True
        if completed:
            if self.result_outcome is BattleResult.ESCAPED:
                self.result = BattleResult.ESCAPED
            else:
                self._request_victory_completion()

    def _request_victory_completion(self) -> None:
        """Leave results after the victory jingle, unless another track replaced it."""

        if getattr(getattr(self, "bgm", None), "current_id", None) == BATTLE_WIN_BGM_ID:
            self.victory_exit_pending = True
            return
        self.result = BattleResult.VICTORY

    def _finish_pending_victory(self) -> bool:
        if not getattr(self, "victory_exit_pending", False):
            return False
        if getattr(getattr(self, "bgm", None), "current_id", None) == BATTLE_WIN_BGM_ID:
            return True
        self.victory_exit_pending = False
        self.result = BattleResult.VICTORY
        return True

    def _release_transient_action_palettes(self) -> None:
        """Release mutually exclusive effect blocks before restarting the scene."""

        self.sync_action_screen_flash(suspended=True)
        self._stop_inner_steel_palette()
        self._release_palette_variant(SPELL_EFFECT_FLASH_PALETTE)
        self._release_palette_variant(MONSTER_DEATH_PALETTE)
        self._release_palette_variant(UNSELECTABLE_TARGET_PALETTE)

    def clear_temporary_member_conditions(self) -> None:
        """Clear DA2's battle-only member ailments before leaving the scene."""

        for member in self.result_party:
            member.clear_temporary_battle_conditions()

    def release_palette_variants(self) -> None:
        """Release this battle's palette blocks before the shared shifter is reused."""

        self.sync_action_screen_flash(suspended=True)
        self._stop_inner_steel_palette()
        for name in (
            SPELL_EFFECT_FLASH_PALETTE,
            MONSTER_DEATH_PALETTE,
            UNSELECTABLE_TARGET_PALETTE,
        ):
            self._release_palette_variant(name)

    def _release_palette_variant(self, name: str) -> None:
        palette_shifter = getattr(self, "palette_shifter", None)
        if palette_shifter is not None:
            palette_shifter.remove_variant(name)

    def _sync_unselectable_target_palette(self) -> None:
        """Reserve the palette used to mark enemies outside weapon reach."""

        palette_shifter = getattr(self, "palette_shifter", None)
        if palette_shifter is None:
            return
        base_colors = getattr(palette_shifter, "base_colors", ())
        if not isinstance(base_colors, tuple) or len(base_colors) <= DISABLED_COLOR:
            return
        if palette_shifter.has_variant(UNSELECTABLE_TARGET_PALETTE) or not (
            palette_shifter.can_define_variant(UNSELECTABLE_TARGET_PALETTE)
        ):
            return
        palette_shifter.define_mix(
            UNSELECTABLE_TARGET_PALETTE,
            base_rate=UNSELECTABLE_TARGET_PALETTE_BASE_RATE,
            target_color=base_colors[DISABLED_COLOR],
        )

    def _sync_monster_death_palette(self) -> None:
        animation = self.monster_death_animation
        if animation is None:
            return
        self._stop_inner_steel_palette()
        self._release_palette_variant(UNSELECTABLE_TARGET_PALETTE)
        self.palette_shifter.define_mix(
            MONSTER_DEATH_PALETTE,
            base_rate=MONSTER_DEATH_PALETTE_BASE_RATE,
            target_color=animation.palette_target_color,
        )

    def _move_target(self, direction: Direction) -> bool:
        """Move among selectable enemies according to their visible columns."""

        selected = self.selected_target_index
        if selected is None:
            return False
        try:
            current_x, current_y = self._monster_base_position(selected)
            selectable_positions = tuple(
                (index, *self._monster_base_position(index))
                for index in self.selectable_target_indexes
            )
        except (IndexError, TypeError):
            return False

        if direction in (Direction.UP, Direction.DOWN):
            column = sorted(
                ((index, y) for index, x, y in selectable_positions if x == current_x),
                key=lambda candidate: candidate[1],
            )
            if len(column) <= 1:
                return False
            indexes = tuple(index for index, _y in column)
            try:
                current_position = indexes.index(selected)
            except ValueError:
                return False
            distance = -1 if direction is Direction.UP else 1
            candidate = indexes[(current_position + distance) % len(indexes)]
        elif direction in (Direction.LEFT, Direction.RIGHT):
            opposite_column = sorted(
                ((index, y) for index, x, y in selectable_positions if x != current_x),
                key=lambda candidate: candidate[1],
            )
            if not opposite_column:
                return False
            if direction is Direction.RIGHT:
                candidate = next(
                    (index for index, y in opposite_column if y >= current_y),
                    opposite_column[0][0],
                )
            else:
                candidate = next(
                    (index for index, y in reversed(opposite_column) if y <= current_y),
                    opposite_column[-1][0],
                )
        else:
            return False

        self.selected_target_index = candidate
        self.target_cursor.select_key(candidate)
        return True

    def _complete_current_turn(self) -> None:
        if self._begin_pending_monster_counter():
            return
        self._clear_turn_state()
        timeline = getattr(self, "timeline", ())
        head = timeline[0] if timeline else None
        if getattr(self, "counter_defeated_turn_actor", False) or (
            isinstance(head, BattleCharacter) and self._member_is_dead(head.member)
        ):
            self.counter_defeated_turn_actor = False
            self._start_timeline_removal_animation()
        else:
            self._start_timeline_animation()

    def _clear_turn_state(self) -> None:
        """Release command and presentation state tied to the last action."""

        self.inner_steel_recovery_index = None
        self.selected_command = None
        self.selectable_target_indexes = ()
        self.selected_target_index = None
        self.selectable_party_target_indexes = ()
        self.selected_party_target_index = None
        self.action_targets_enemy = False
        self.action_targets_all = False
        self.pending_item_candidate = None
        self.pending_spell = None
        if getattr(self, "party_status_shows_mp", False):
            self.party_status_shows_mp = False
            self._refresh_all_party_hp_texts()
        self.action_progression_weapon = None
        self.action_progression_enemy_levels = ()
        self.pending_action_effect_spell = None
        self.sync_action_screen_flash(suspended=True)
        self.action_presentation = None
        self.monster_action = None
        self.attack_presentation = None
        self.focus_presentation_elapsed_frame = 0
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

    def _start_timeline_animation(self) -> None:
        self.inner_steel_recovery_index = None
        actor = self._timeline_order.entries[0].actor
        if isinstance(actor, BattleCharacter) and isinstance(actor.member, Member):
            actor.member.elapse_silence_turn()
            actor.member.elapse_debuff_turn()
        elif isinstance(actor, BattleMonster):
            actor.state.elapse_debuff_turn()
        self.timeline_advance = complete_timeline_action(
            self._timeline_order,
            current_agility=self._actor_agility(actor),
            visible_count=TIMELINE_VISIBLE_ENTRY_COUNT,
            gauge_adjustment=getattr(self, "action_gauge_adjustment", 0.0),
        )
        self.action_gauge_adjustment = 0.0
        self.phase = BattlePhase.TIMELINE
        self.active_party_index = None
        if hasattr(self, "active_party_cursor_frame"):
            self.active_party_cursor_frame = 0
            self._sync_active_party_cursor_palette()
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self.timeline_animation_phase = TimelineAnimationPhase.DROP
        self.timeline_animation_frame = 0
        self._refresh_party_text_colors()

    @staticmethod
    def _actor_agility(actor: BattleCharacter | BattleMonster) -> int:
        """Read effective agility while retaining lightweight test actors."""

        return getattr(actor, "effective_agility", actor.agility)

    def _remove_timeline_actors(
        self,
        actors: Sequence[BattleCharacter | BattleMonster],
    ) -> None:
        """Exclude actors immediately, retaining only their departing visuals."""

        before = getattr(self, "timeline", ())
        removed = tuple(
            entry for entry in before if any(entry is actor for actor in actors)
        )
        if not removed:
            return
        order = getattr(self, "_timeline_order", None)
        if order is not None:
            for actor in removed:
                order = remove_timeline_actor(order, actor)
            self._timeline_order = order
            self.timeline = order.actors
        else:
            self.timeline = tuple(
                entry
                for entry in before
                if all(entry is not actor for actor in removed)
            )
        animation = getattr(self, "timeline_removal_animation", None)
        if animation is not None:
            animation.after = self.timeline
        elif any(
            entry is actor
            for entry in before[:TIMELINE_VISIBLE_ENTRY_COUNT]
            for actor in removed
        ):
            self.timeline_removal_animation = TimelineRemovalAnimation(
                before, self.timeline
            )

    def _update_timeline_removal_animation(self) -> bool:
        """Finish departing icons before accepting input or moving the next turn."""

        animation = getattr(self, "timeline_removal_animation", None)
        if animation is None:
            return False
        animation.elapsed_frame += 1
        if animation.elapsed_frame >= (
            TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT + TIMELINE_INTERRUPT_SLIDE_FRAME_COUNT
        ):
            self.timeline_removal_animation = None
        return True

    def _start_timeline_removal_animation(self) -> None:
        """Slide the timeline after an escaping actor leaves permanently."""

        self.inner_steel_recovery_index = None
        self.timeline_advance = remove_timeline_head(self._timeline_order)
        self.phase = BattlePhase.TIMELINE
        self.active_party_index = None
        if hasattr(self, "active_party_cursor_frame"):
            self.active_party_cursor_frame = 0
            self._sync_active_party_cursor_palette()
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self.timeline_animation_phase = TimelineAnimationPhase.DROP
        self.timeline_animation_frame = 0
        self._refresh_party_text_colors()

    def _active_party_cursor_is_visible(self) -> bool:
        """Return whether manual command input is pending for the current actor."""

        return (
            not getattr(self, "auto_battle_active", False)
            and self.phase
            in (
                BattlePhase.COMMAND,
                BattlePhase.ITEM,
                BattlePhase.SPELL,
                BattlePhase.TARGET,
                BattlePhase.COVER_TARGET,
                BattlePhase.ESCAPE_CONFIRMATION,
            )
            and getattr(self, "active_party_index", None) is not None
        )

    def _update_active_party_cursor(self) -> None:
        """Advance the cursor's continuous whiteward palette pulse."""

        if self._active_party_cursor_is_visible():
            self.active_party_cursor_frame = (
                self.active_party_cursor_frame + 1
            ) % ACTIVE_PARTY_CURSOR_CYCLE_FRAME_COUNT
        else:
            self.active_party_cursor_frame = 0
        self._sync_active_party_cursor_palette()

    def _sync_active_party_cursor_palette(self) -> None:
        """Use the former actor pulse's timing and white mix for the cursor."""

        half_cycle = ACTIVE_PARTY_CURSOR_HALF_CYCLE_FRAME_COUNT
        distance_from_peak = abs(half_cycle - self.active_party_cursor_frame)
        progress_to_normal = distance_from_peak / half_cycle
        base_rate = ACTIVE_PARTY_CURSOR_MIN_BASE_RATE + (
            (1.0 - ACTIVE_PARTY_CURSOR_MIN_BASE_RATE) * progress_to_normal
        )
        self.palette_shifter.define_mix(
            ACTIVE_PARTY_CURSOR_PALETTE,
            base_rate=base_rate,
            target_color=ACTIVE_PARTY_CURSOR_TARGET_COLOR,
        )

    def _update_inner_steel_palette(self) -> None:
        if (
            getattr(self, "phase", None) not in (BattlePhase.COMMAND, BattlePhase.GLOBAL_COMMAND)
            or getattr(self, "auto_battle_active", False)
            or getattr(self, "auto_battle_screen", None) is not None
            or getattr(self, "escape_start_frame_by_party_index", {})
        ):
            self._stop_inner_steel_palette()
            return

        recovery_index = getattr(self, "inner_steel_recovery_index", None)
        flashing_indexes = tuple(
            index for index, member in enumerate(getattr(self, "party", ()))
            if isinstance(member, Member) and member.is_alive
            and (member.inner_steel_active or index == recovery_index)
        )
        if not flashing_indexes or not self.is_party_command_ready:
            self._stop_inner_steel_palette()
            return
        if not self.palette_shifter.can_define_variant(INNER_STEEL_PALETTE):
            self._stop_inner_steel_palette()
            return

        previous = getattr(self, "inner_steel_frame", None)
        frame = 0 if previous is None else (previous + 1) % INNER_STEEL_CYCLE_FRAMES
        if previous is None or frame * DA2_REFERENCE_FPS // FPS != previous * DA2_REFERENCE_FPS // FPS:
            reference_frame = min(frame * DA2_REFERENCE_FPS // FPS, DA2_INNER_STEEL_TINT_FRAMES - 1)
            angle = reference_frame * 2 * pi / DA2_INNER_STEEL_TINT_FRAMES
            self.palette_shifter.define_mix(
                INNER_STEEL_PALETTE,
                base_rate=0.8 + cos(angle) * 0.2,
                target_color=INNER_STEEL_TINT_COLOR,
            )
        self.inner_steel_frame = frame
        self.inner_steel_flashing_indexes = flashing_indexes
        if frame == INNER_STEEL_CYCLE_FRAMES - 1:
            self.inner_steel_recovery_index = None

    def _stop_inner_steel_palette(self) -> None:
        if getattr(self, "inner_steel_frame", None) is not None:
            self._release_palette_variant(INNER_STEEL_PALETTE)
            self.inner_steel_frame = None
            self.inner_steel_flashing_indexes = ()

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
            if (
                getattr(self, "escape_requested", False)
                and not self._active_party_indexes()
            ):
                self._begin_escape_animation()
            else:
                self._begin_defeat_message()
            return
        if self._prune_surprise_pending_party(
            FormationAnimationCompletion.ACTIVATE_TIMELINE_HEAD
        ):
            return
        if self._begin_front_promotion_if_needed(
            FormationAnimationCompletion.ACTIVATE_TIMELINE_HEAD
        ):
            return
        actor = self.timeline[0]
        if isinstance(actor, BattleCharacter):
            self.active_party_index = next(
                index
                for index, visual in enumerate(self.party_visuals)
                if visual is actor
            )
            if isinstance(actor.member, Member) and actor.member.recover_with_inner_steel():
                self.inner_steel_recovery_index = self.active_party_index
            if getattr(self, "surprise_active", False):
                self.surprise_turned_party_indexes.add(self.active_party_index)
            elif (
                self.active_party_index in getattr(self, "surprise_original_front_rows", {})
                and not self._member_focus_is_interrupted(
                    actor.member, after_confusion_tick=True,
                )
            ):
                # Restore before turn-start effects so resuming the same head
                # cannot apply poison, recovery, or status timers twice.
                self._restore_surprise_formation(
                    FormationAnimationCompletion.ACTIVATE_TIMELINE_HEAD,
                    party_indexes=(self.active_party_index,),
                )
                return
            self.blinking_monster_index = None
            self.monster_blink_frames_remaining = 0
            self.defending_party_indexes.discard(self.active_party_index)
            getattr(self, "cover_target_by_party_index", {}).pop(
                self.active_party_index,
                None,
            )
            if self._apply_turn_start_hp_change(actor):
                return
            status_skips_turn = False
            if getattr(actor.member, "stunned", False):
                if isinstance(actor.member, Member):
                    actor.member.consume_stun()
                else:
                    actor.member.stunned = False
                getattr(self, "focused_target_by_party_index", {}).pop(
                    self.active_party_index,
                    None,
                )
                status_skips_turn = True
            elif getattr(actor.member, "paralyzed", False):
                getattr(self, "focused_target_by_party_index", {}).pop(
                    self.active_party_index,
                    None,
                )
                status_skips_turn = True
            elif getattr(actor.member, "sleeping", 0):
                if isinstance(actor.member, Member):
                    actor.member.elapse_sleep_turn()
                else:
                    actor.member.sleeping -= 1
                getattr(self, "focused_target_by_party_index", {}).pop(
                    self.active_party_index,
                    None,
                )
                status_skips_turn = True
            if self._skip_surprised_party_turn(
                self.active_party_index, status_skips_turn=status_skips_turn,
            ):
                return
            if status_skips_turn:
                self._start_timeline_animation()
                return
            if getattr(actor.member, "confused", 0):
                if isinstance(actor.member, Member):
                    remains_confused = actor.member.elapse_confusion_turn()
                else:
                    actor.member.confused = max(actor.member.confused - 1, 0)
                    remains_confused = actor.member.confused > 0
                getattr(self, "focused_target_by_party_index", {}).pop(
                    self.active_party_index,
                    None,
                )
                if remains_confused:
                    if not self._begin_confused_party_action(self.active_party_index):
                        self._start_timeline_animation()
                    return
            if getattr(self, "escape_requested", False):
                self._begin_party_member_escape(self.active_party_index)
                return
            if self._begin_focused_attack():
                self._refresh_party_text_colors()
                return
            if getattr(self, "auto_battle_active", False):
                self._begin_auto_action()
                self._refresh_party_text_colors()
                return
            if getattr(self, "_defer_first_party_command", False):
                self._defer_first_party_command = False
                self._pending_first_party_command = True
                self.phase = BattlePhase.INITIAL
                self._refresh_party_text_colors()
                return
            if getattr(self, "initial_global_command_pending", False):
                self.initial_global_command_pending = False
                self._open_global_command_menu()
            else:
                self.phase = BattlePhase.COMMAND
                self.command_cursor.active = True
                self._hide_command_guide()
                self._refresh_command_options()
                self._select_initial_member_command()
                self.command_window.open()
                self._refresh_input_guide()
        else:
            actor.state.defending = False
            self.active_party_index = None
            self.command_cursor.active = False
            self.command_window.close_immediately()
            self.monster_attack_target_index = None
            self.monster_attack_damage = None
            self.monster_attack_critical = False
            self.monster_attack_additional_effects = ()
            self.monster_attack_animation_frame = 0
            self.monster_attack_damage_applied = False
            self.monster_action = None
            self.monster_confused_action_pending = False
            self.monster_charge_presentation = None
            self.monster_escape_actor_index = None
            self.monster_escape_animation_frame = 0
            if self._apply_turn_start_hp_change(actor):
                return
            if actor.state.consume_stun():
                actor.state.elapse_silence_turn()
                self.blinking_monster_index = None
                self.monster_blink_frames_remaining = 0
                self._start_timeline_animation()
                return
            if actor.state.elapse_sleep_turn():
                actor.state.elapse_silence_turn()
                self.blinking_monster_index = None
                self.monster_blink_frames_remaining = 0
                self._start_timeline_animation()
                return
            confusion_turns = getattr(actor.state, "confused", 0)
            if (
                isinstance(confusion_turns, int)
                and not isinstance(confusion_turns, bool)
                and confusion_turns > 0
                and actor.state.elapse_confusion_turn()
            ):
                actor.state.elapse_silence_turn()
                self.phase = BattlePhase.MONSTER_ACTION
                self.blinking_monster_index = self._monster_index(actor)
                self.monster_blink_frames_remaining = MONSTER_BLINK_FRAME_COUNT
                self.monster_confused_action_pending = True
                return
            if not self._monster_can_attempt_action(actor):
                self.blinking_monster_index = None
                self.monster_blink_frames_remaining = 0
                self._start_timeline_animation()
                return
            self.phase = BattlePhase.MONSTER_ACTION
            if self._attempt_monster_reinforcement(actor):
                self._reinforcement_waiting_actor = actor
                self._reinforcement_post_entrance_wait_frames = 0
                self.blinking_monster_index = None
                self.monster_blink_frames_remaining = 0
            else:
                self.blinking_monster_index = self._monster_index(actor)
                self.monster_blink_frames_remaining = MONSTER_BLINK_FRAME_COUNT
        self._refresh_party_text_colors()

    def _begin_confused_party_action(self, actor_index: int) -> bool:
        """Force DA2's confused member attack against an ally when possible."""

        actor = self.party[actor_index]
        ally_indexes = tuple(
            index
            for index in self._active_party_indexes()
            if index != actor_index
            and index not in getattr(self, "hidden_party_indexes", set())
            and not getattr(self.party[index], "paralyzed", False)
            and not getattr(self.party[index], "sleeping", 0)
            and not getattr(self.party[index], "confused", 0)
        )
        if not ally_indexes:
            targets = self._active_member_attack_targets(
                command=BattleCommand.ATTACK,
            )
            if not targets:
                return False
            self.selected_command = BattleCommand.ATTACK
            self.selectable_target_indexes = targets
            self.selected_target_index = random.choice(targets)
            self._begin_action_motion(use_cast_pose=False)
            return self._begin_attack_presentation()

        target_index = random.choice(ally_indexes)
        return self._begin_confused_member_friendly_attack(
            actor_index,
            target_index,
        )

    def _begin_confused_member_friendly_attack(
        self,
        actor_index: int,
        target_index: int,
    ) -> bool:
        """Start the normal weapon motion against one other party member."""

        actor = self.party[actor_index]
        target = self.party[target_index]
        right_weapon = actor.equipment.weapon_at(EquipmentSlot.RIGHT)
        if right_weapon is None:
            return False
        actor_stats = actor.battle_stats
        target_stats = target.battle_stats
        equipped_attacks: list[tuple[Item, int, int, tuple[str, str]]] = [
            (
                right_weapon,
                actor_stats.attack_right,
                actor_stats.hit_right.total,
                ("1", "2"),
            )
        ]
        left_weapon = actor.equipment.weapon_at(EquipmentSlot.LEFT)
        if (
            left_weapon is not None
            and actor.has_skill("Dual-Wield")
            and actor_stats.attack_left is not None
            and actor_stats.hit_left is not None
        ):
            equipped_attacks.append(
                (
                    left_weapon,
                    actor_stats.attack_left,
                    actor_stats.hit_left.total,
                    ("4", "5") if left_weapon.subtype == "THROWING" else ("3", "4"),
                )
            )

        strikes: list[BattleAttackStrike] = []
        motion_start_frame = 0
        target_defending = target_index in self.defending_party_indexes
        target_incapacitated = bool(
            getattr(target, "sleeping", 0) or getattr(target, "confused", 0)
        )
        for weapon, weapon_attack, weapon_hit, pose_branches in equipped_attacks:
            attack = self._member_weapon_attack(actor, weapon, weapon_attack)
            result = resolve_physical_attack(
                attack=attack,
                hit=weapon_hit,
                target_defense=target_stats.defense,
                target_evasion=target_stats.evasion,
                hit_roll=random.randint(0, 99),
                target_defending=target_defending,
                target_incapacitated=target_incapacitated,
                critical_roll=(random.randint(0, 99) if target_incapacitated else None),
            )
            pose_change_frame = motion_start_frame + ATTACK_POSE_RAISE_FRAME_COUNT
            projectile_sprites = (
                throwing_projectile_sequence(
                    getattr(self, "attack_poses", {}),
                    weapon.weapon_img,
                    race=self.party[actor_index].definition.race,
                    branches=("5", "6") if pose_branches == ("4", "5") else ("2", "3"),
                )
                if weapon.subtype == "THROWING"
                else ()
            )
            projectile_frame_count = self._throwing_projectile_frame_count(
                actor_index,
                "ally",
                target_index,
                projectile_sprites,
                move_distance=0,
            )
            hit_start_frame = (
                pose_change_frame
                if not projectile_sprites
                else pose_change_frame
                + ATTACK_POSE_SWING_FRAME_COUNT
                + projectile_frame_count
                - 1
            )
            strikes.append(
                BattleAttackStrike(
                    damage=result.damage,
                    poses=attack_sequence(
                        getattr(self, "attack_poses", {}),
                        weapon.weapon_img,
                        branches=pose_branches,
                    ),
                    effect_row=ATTACK_EFFECT_ROW_BY_SUBTYPE.get(weapon.subtype),
                    motion_start_frame=motion_start_frame,
                    hit_start_frame=hit_start_frame,
                    pose_change_frame=(
                        pose_change_frame if projectile_sprites else None
                    ),
                    projectile_sprites=projectile_sprites,
                    projectile_frame_count=projectile_frame_count,
                    effect_flip_x=bool(strikes),
                    is_hit=result.hit,
                    is_critical=result.critical,
                    drains_hp=weapon_can_drain(weapon.additional_effect, target.resistances),
                    additional_effects=(
                        self._resolve_member_attack_effects_against_member(
                            actor,
                            weapon,
                            target,
                            result,
                            target_defending=target_defending,
                        )
                    ),
                    sound_effect_id=ATTACK_SE_ID_BY_SUBTYPE.get(
                        weapon.subtype,
                        ATTACK_SLASH_SE_ID,
                    ),
                )
            )
            motion_start_frame = (
                strikes[-1].motion_end_frame + DUAL_WIELD_ATTACK_INTERVAL_FRAME_COUNT
            )

        self._begin_action_motion(use_cast_pose=False, stationary=True)
        getattr(self, "hidden_party_indexes", set()).discard(actor_index)
        self.command_cursor.active = False
        self.command_window.close_immediately()
        self.attack_presentation = BattleAttackPresentation(
            target_index=target_index,
            strikes=tuple(strikes),
            target_side="ally",
        )
        self.phase = BattlePhase.ATTACK_PRESENTATION
        return True

    def _resolve_member_attack_effects_against_member(
        self,
        actor: Member,
        weapon: Item,
        target: Member,
        result: PhysicalAttackResult,
        *,
        target_defending: bool,
    ) -> tuple[AdditionalEffect, ...]:
        """Resolve a confused member's weapon effects against an ally."""

        candidates = self._effect_candidates_for_member_attack(actor, weapon)
        if not candidates:
            return ()
        hit_reached_guard = target_defending and result.hit_value >= 0
        if not result.hit and not hit_reached_guard:
            return ()
        effect_roll = random.randint(0, 99)
        target_resistances = target.resistances
        successful: list[AdditionalEffect] = []
        for effect, stacked_death in candidates:
            resistance = PHYSICAL_EFFECT_RESISTANCE[effect]
            resolution = resolve_physical_additional_effect(
                effect=effect,
                adjusted_hit=result.adjusted_hit,
                effect_roll=effect_roll,
                target_is_member=True,
                target_has_boss_resistance=ResistanceType.DEATH in target_resistances,
                target_is_resistant=(
                    resistance is not None and resistance in target_resistances
                ),
                target_defending=target_defending,
                critical=result.critical,
                stacked_death=stacked_death,
            )
            if resolution.success:
                successful.append(effect)
        return tuple(successful)

    def _begin_confused_monster_action(self, actor: BattleMonster) -> bool:
        """Force a confused monster to attack another monster when available."""

        actor_index = self._monster_index(actor)
        ally_indexes = tuple(
            index
            for index, monster in enumerate(self.monsters)
            if index != actor_index and monster.is_alive
        )
        if not ally_indexes:
            targets = self._monster_attack_target_indexes(actor)
            if not targets:
                return False
            self._begin_standard_monster_attack(actor)
            return True

        target_index = random.choice(ally_indexes)
        target = self.monsters[target_index]
        target_incapacitated = bool(target.state.sleeping or target.state.confused)
        power_hit = MonsterSpecialAction.POWER_HIT in actor.special_actions
        result = resolve_physical_attack(
            attack=actor.combat_stats.attack,
            hit=actor.combat_stats.hit,
            target_defense=target.effective_defense,
            target_evasion=target.combat_stats.evasion,
            target_defending=target.state.is_defending,
            hit_roll=random.randint(0, 99),
            target_incapacitated=target_incapacitated,
            attacker_is_monster=True,
            attacker_has_power_hit=power_hit,
            critical_roll=(
                random.randint(0, 99)
                if power_hit or target_incapacitated
                else None
            ),
        )
        effects = resolve_monster_attack_effects(
            actor.additional_effects,
            result,
            roll_effect=lambda: random.randint(0, 99),
            target_is_member=False,
            target_resistances=target.resistances,
            target_weaknesses=target.weaknesses,
            target_defending=target.state.is_defending,
        )
        _base_x, base_y = self._monster_base_position(target_index)
        center_x = self._monster_draw_x(target_index) + target.width // 2
        self.action_presentation = BattleActionPresentation(
            (),
            confused_attack_results=(
                BattleConfusedAttackResult(
                    target_side="enemy",
                    target_index=target_index,
                    damage=result.damage,
                    is_hit=result.hit,
                    popup_x=center_x,
                    popup_y=base_y + target.height - 8,
                    effect_row=CONFUSED_MONSTER_ATTACK_EFFECT_ROW,
                    additional_effects=effects,
                    drain_actor_index=(
                        actor_index if AdditionalEffect.DRAIN in actor.additional_effects
                        and result.damage > 0 else None
                    ),
                    is_critical=result.critical,
                ),
            ),
            result_start_frame=1,
            post_effect_wait_frame_count=ATTACK_HIT_FRAME_COUNT + 1,
        )
        self.phase = BattlePhase.ACTION_PRESENTATION
        return True

    def _apply_turn_start_hp_change(
        self,
        actor: BattleCharacter | BattleMonster,
    ) -> bool:
        """Apply poison and automatic recovery before the actor's turn."""

        damage_popups = getattr(self, "spell_damage_popups", None)
        if damage_popups is None:
            damage_popups = []
            self.spell_damage_popups = damage_popups

        if isinstance(actor, BattleCharacter):
            member = actor.member
            poisoned = getattr(member, "poisoned", False)
            healing_level = getattr(member, "battle_healing", 0)
            if not poisoned and healing_level == 0:
                return False
            poison_damage = poison_tick_damage(max_hp=member.max_hp) if poisoned else 0
            healing = battle_healing_amount(
                max_hp=member.max_hp,
                healing=healing_level,
            )
            hp_change = healing - poison_damage
            if hp_change == 0:
                return False
            party_index = next(
                index
                for index, visual in enumerate(self.party_visuals)
                if visual is actor
            )
            position = self._party_draw_position(party_index)
            if hp_change > 0:
                member.apply_healing(hp_change)
                if position is not None:
                    x, y = position
                    healing_popups = getattr(self, "healing_popups", None)
                    if healing_popups is None:
                        healing_popups = []
                        self.healing_popups = healing_popups
                    healing_popups.append(BattleHealingPopup(x + 6, y + 16, hp_change))
            else:
                damage = -hp_change
                member.take_poison_damage(damage)
                if position is not None:
                    x, y = position
                    damage_popups.append(BattleSpellDamagePopup(x + 6, y + 16, damage))
            self._refresh_party_hp_text(party_index)
            if member.is_dead:
                getattr(self, "focused_target_by_party_index", {}).pop(
                    party_index,
                    None,
                )
                getattr(self, "hidden_party_indexes", set()).discard(party_index)
                self._reveal_hidden_party_if_all_unavailable()
                surprise_pending = getattr(
                    self,
                    "surprise_pending_party_indexes",
                    None,
                )
                if surprise_pending is not None:
                    surprise_pending.discard(party_index)
                if getattr(self, "surprise_active", False) and not surprise_pending:
                    self._restore_surprise_formation(
                        FormationAnimationCompletion.START_TIMELINE_REMOVAL
                    )
                    return True
                self._start_timeline_removal_animation()
                return True
            return False

        if not actor.is_alive:
            return False
        poison_damage = (
            poison_tick_damage(
                max_hp=actor.state.max_hp,
                weak_to_poison=ResistanceType.POISON in actor.weaknesses,
            )
            if actor.state.poisoned
            else 0
        )
        hp_change = (
            battle_healing_amount(
                max_hp=actor.state.max_hp,
                healing=actor.combat_stats.healing,
                is_boss=actor.is_boss,
            )
            - poison_damage
        )
        if hp_change == 0:
            return False
        monster_index = next(
            index for index, monster in enumerate(self.monsters) if monster is actor
        )
        _base_x, y = self._monster_base_position(monster_index)
        popup_x = self._monster_draw_x(monster_index) + actor.width // 2
        popup_y = y + actor.height - 8
        if hp_change > 0:
            actor.state.apply_healing(hp_change)
            healing_popups = getattr(self, "healing_popups", None)
            if healing_popups is None:
                healing_popups = []
                self.healing_popups = healing_popups
            healing_popups.append(BattleHealingPopup(popup_x, popup_y, hp_change))
        else:
            damage = -hp_change
            actor.state.take_poison_damage(damage)
            damage_popups.append(BattleSpellDamagePopup(popup_x, popup_y, damage))
        if not actor.is_alive:
            self.blinking_monster_index = None
            self.monster_blink_frames_remaining = 0
            self._begin_monster_death(
                monster_index,
                from_timeline_head=True,
            )
            return True
        return False

    def _monster_attack_target_indexes(
        self,
        actor: BattleMonster,
    ) -> tuple[int, ...]:
        hidden = getattr(self, "hidden_party_indexes", set())
        return monster_attack_targets(
            (index for index in self._active_party_indexes() if index not in hidden),
            special_actions=actor.special_actions,
            is_front_row=actor.is_front_row,
            target_is_front_row=self._party_member_is_front_row,
        )

    def _monster_charge_target_indexes(self) -> tuple[int, ...]:
        """Return every living member because charge has ranged reach."""

        hidden = getattr(self, "hidden_party_indexes", set())
        return tuple(
            index for index in self._active_party_indexes() if index not in hidden
        )

    def _temptation_target_indexes(self) -> tuple[int, ...]:
        return tuple(
            index for index in self._active_party_indexes()
            if self.party[index].definition.gender is Gender.MALE
        )

    def _black_wind_target_indexes(self) -> tuple[int, ...]:
        return tuple(
            index for index, monster in enumerate(self.monsters)
            if monster.state.can_recover_with_black_wind
        )

    def _monster_can_attempt_action(self, actor: BattleMonster) -> bool:
        """Return whether a monster has any action worth evaluating."""

        if not actor.is_front_row or MonsterSpecialAction.MIRROR in actor.special_actions:
            return True
        if MonsterSpecialAction.EARTHQUAKE in actor.special_actions and self._active_party_indexes():
            return True
        if MonsterSpecialAction.TEMPTATION in actor.special_actions and self._temptation_target_indexes():
            return True
        if MonsterSpecialAction.BLACK_WIND in actor.special_actions and (
            actor.intelligence <= 0 or self._black_wind_target_indexes()
        ):
            return True
        if self._monster_attack_target_indexes(actor):
            return True
        if actor.intelligence in (2, 3) and MonsterSpecialAction.CALL in actor.special_actions:
            slot = self._monster_ally_slot(actor)
            if slot is not None and slot <= 1:
                return True
        if any(
            self._monster_spell_target_indexes(self.spells[key])
            for key in actor.spell_keys
        ):
            return True
        if any(action in actor.special_actions for action in (
            MonsterSpecialAction.CHARGE, MonsterSpecialAction.POISON_BREATH,
            MonsterSpecialAction.FIRE_BREATH,
        )):
            return bool(self._monster_charge_target_indexes())
        return MonsterSpecialAction.ESCAPE in actor.special_actions and bool(
            self._active_party_indexes()
        )

    def _active_member_attack_targets(
        self,
        *,
        command: BattleCommand = BattleCommand.ATTACK,
    ) -> tuple[int, ...]:
        if self.active_party_index is None:
            return ()
        actor = self.party[self.active_party_index]
        if command is BattleCommand.BREATH:
            return tuple(index for index, monster in enumerate(self.monsters) if monster.is_alive)
        if command is BattleCommand.IAI:
            if not member_can_iai(
                actor,
                attacker_is_front_row=self._party_member_is_front_row(
                    self.active_party_index
                ),
            ):
                return ()
            return tuple(
                index for index, monster in enumerate(self.monsters) if monster.is_alive
            )
        if not member_can_attack(actor):
            return ()
        return selectable_attack_target_indexes(
            attacker_is_front_row=self._party_member_is_front_row(
                self.active_party_index
            ),
            weapon_reach=member_attack_reach(actor),
            monsters=self.monsters,
            unrestricted_range=command is BattleCommand.AMBUSH,
        )

    def _active_member_command_options(self) -> tuple[BattleCommandOption, ...]:
        """Ask the Pyxel-independent rules for this actor's command state."""

        if self.active_party_index is None:
            return ()
        active_indexes = self._active_party_indexes()
        active_party = tuple(self.party[index] for index in active_indexes)
        return resolve_battle_commands(
            self.party[self.active_party_index],
            active_party,
            self.monsters,
            context=BattleCommandContext(
                silenced=bool(
                    getattr(self.party[self.active_party_index], "silenced", 0)
                ),
                item_available=bool(self._active_member_item_candidates()),
                actor_hidden=(
                    self.active_party_index
                    in getattr(self, "hidden_party_indexes", set())
                ),
            ),
            party_front_rows=tuple(
                self._party_member_is_front_row(index) for index in active_indexes
            ),
        )

    def _refresh_command_options(self) -> None:
        options = self._active_member_command_options()
        self._command_options = options
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
                )
                for option, _, _, _, cursor_x, cursor_y in placements
            )
        )
        return options

    @property
    def _command_memory_enabled(self) -> bool:
        return getattr(
            getattr(self, "settings", None), "remember_battle_commands", True
        )

    def _restore_command_memory(self) -> None:
        self.initial_global_command_pending = False
        memory = getattr(self, "command_memory", None)
        if memory is None:
            return
        self.last_global_command = None
        if not self._command_memory_enabled:
            memory.clear()
            return
        if memory.global_command is not None:
            self.last_global_command = BattleGlobalCommand(memory.global_command)
            self.initial_global_command_pending = (
                self.last_global_command is BattleGlobalCommand.AUTO
                or (
                    self.last_global_command is BattleGlobalCommand.ESCAPE
                    and self.encounter.escape_command_enabled
                )
            )
        for index, member in enumerate(self.party):
            key = member.definition.key
            for source, target in (
                (memory.commands, self.last_command_by_party_index),
                (memory.spells, self.last_spell_key_by_party_index),
                (memory.items, self.last_item_selection_by_party_index),
            ):
                if key in source:
                    target[index] = source[key]

    def _sync_command_memory(self) -> None:
        memory = getattr(self, "command_memory", None)
        if memory is None or not self._command_memory_enabled:
            return
        command = getattr(self, "last_global_command", None)
        memory.global_command = command.value if command is not None else None
        for index, member in enumerate(self.party):
            key = member.definition.key
            for source, target in (
                (self.last_command_by_party_index, memory.commands),
                (self.last_spell_key_by_party_index, memory.spells),
                (self.last_item_selection_by_party_index, memory.items),
            ):
                if index in source:
                    target[key] = source[index]
                else:
                    target.pop(key, None)

    def _select_initial_member_command(self) -> None:
        """Restore one member's last command, or use the normal initial choice."""

        if not hasattr(self, "party"):
            return
        options = self._active_member_command_options()
        active_index = getattr(self, "active_party_index", None)
        remembered_command = (
            getattr(self, "last_command_by_party_index", {}).get(active_index)
            if self._command_memory_enabled
            else None
        )
        if remembered_command is not None and any(
            option.command == remembered_command and option.enabled
            for option in options
        ):
            try:
                self.command_cursor.select_key(remembered_command)
            except ValueError:
                # A remembered command can become unavailable after an item is
                # consumed or a temporary battle condition changes.
                pass
            else:
                return
        attack = next(
            (
                option
                for option in options
                if option.command in (BattleCommand.ATTACK, BattleCommand.AMBUSH)
            ),
            None,
        )
        if attack is not None and not attack.enabled:
            self.command_cursor.select_key(BattleCommand.DEFEND)

    def _remember_active_command(self, command: BattleCommand) -> None:
        """Keep a confirmed command for its member, except formation movement."""

        active_index = getattr(self, "active_party_index", None)
        if active_index is None or not self._command_memory_enabled:
            return
        commands = getattr(self, "last_command_by_party_index", None)
        if commands is None:
            commands = {}
            self.last_command_by_party_index = commands
        if command is BattleCommand.FORMATION:
            # Retreat and advance must open at the normal initial position on
            # the member's next turn, rather than restoring an older command.
            commands.pop(active_index, None)
            self._sync_command_memory()
            return
        commands[active_index] = (
            BattleCommand.HIDE if command is BattleCommand.AMBUSH else command
        )
        self._sync_command_memory()

    def _command_label(self, command: BattleCommand) -> str:
        """Resolve one command's localized display label from the text catalog."""

        return self.texts.text(self._command_text_key(command), self.localizer)

    def _command_text_key(self, command: BattleCommand) -> str:
        """Resolve the context-sensitive text key for one visible command."""

        if command is BattleCommand.FORMATION and self.active_party_index is not None:
            return FORMATION_COMMAND_TEXT_KEYS[
                self._party_member_is_front_row(self.active_party_index)
            ]
        return COMMAND_TEXT_KEYS[command]

    def _command_guide_lines(self, command: BattleCommand) -> tuple[str, ...]:
        """Return the command's authored guide text."""

        if command is BattleCommand.FORMATION and self.active_party_index is not None:
            key = FORMATION_COMMAND_GUIDE_TEXT_KEYS[
                self._party_member_is_front_row(self.active_party_index)
            ]
        else:
            key = COMMAND_GUIDE_TEXT_KEYS[command]
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
        if getattr(self, "monster_counter_actor_index", None) is not None:
            self._update_monster_counter()
            return
        if getattr(self, "monster_charge_presentation", None) is not None:
            self._update_monster_charge()
            return
        if getattr(self, "monster_escape_actor_index", None) is not None:
            self._update_monster_escape()
            return
        if self.monster_attack_target_index is not None:
            if getattr(self, "formation_actor_indexes", ()):
                self._update_formation_animation()
            self.monster_attack_animation_frame += 1
            frame_count = self._monster_attack_animation_frame_count()
            if self._monster_double_attack_pending() and not getattr(
                self, "monster_attack_damage_applied", False
            ):
                frame_count = MONSTER_DOUBLE_ATTACK_HIT_INTERVAL
            if self.monster_attack_animation_frame >= frame_count:
                self._finish_monster_attack()
            return
        actor = self.timeline[0]
        waiting_actor = getattr(self, "_reinforcement_waiting_actor", None)
        if waiting_actor is not None and waiting_actor is actor:
            if self.reinforcement_entrance_frames:
                return
            if (
                self._reinforcement_post_entrance_wait_frames
                < REINFORCEMENT_POST_ENTRANCE_WAIT_FRAME_COUNT
            ):
                self._reinforcement_post_entrance_wait_frames += 1
                return
            self._reinforcement_waiting_actor = None
            self._reinforcement_post_entrance_wait_frames = 0
            self.blinking_monster_index = self._monster_index(actor)
            self.monster_blink_frames_remaining = MONSTER_BLINK_FRAME_COUNT
            return
        if getattr(self, "_monster_call_pending", False):
            if self.reinforcement_entrance_frames:
                return
            if (
                self._reinforcement_post_entrance_wait_frames
                < REINFORCEMENT_POST_ENTRANCE_WAIT_FRAME_COUNT
            ):
                self._reinforcement_post_entrance_wait_frames += 1
                return
            self._monster_call_pending = False
            self._reinforcement_post_entrance_wait_frames = 0
            self._start_timeline_animation()
            return
        if self.monster_blink_frames_remaining > 0:
            self.monster_blink_frames_remaining -= 1
        if self.monster_blink_frames_remaining > 0:
            return
        if not isinstance(actor, BattleMonster):
            self._start_timeline_animation()
            return
        if getattr(self, "monster_confused_action_pending", False):
            self.monster_confused_action_pending = False
            self.blinking_monster_index = None
            if hasattr(self, "progression"):
                self.progression.record_enemy_action(self._monster_index(actor))
            if not self._begin_confused_monster_action(actor):
                self._start_timeline_animation()
            return
        action = self._select_monster_action(actor)
        # Black Wind cures the caster's silence at impact, even on its last turn.
        turn_was_silenced = (
            action is not MonsterAction.BLACK_WIND and actor.state.elapse_silence_turn()
        )
        if action is None:
            self._start_timeline_animation()
            return
        self.monster_action = action
        self.blinking_monster_index = None
        if action is MonsterAction.IDLE:
            self.monster_action = None
            self._start_timeline_animation()
            return
        if hasattr(self, "progression"):
            self.progression.record_enemy_action(self._monster_index(actor))
        if action is MonsterAction.DEFEND:
            actor.state.defending = True
            self._show_monster_action_message("battle.command.defend")
            self.action_presentation = BattleActionPresentation(
                (), post_effect_wait_frame_count=MONSTER_DEFEND_WAIT_FRAME_COUNT,
            )
            self.phase = BattlePhase.ACTION_PRESENTATION
            return
        if action is MonsterAction.ESCAPE:
            self._begin_monster_escape(actor)
            return
        if action is MonsterAction.CALL:
            self._show_monster_action_message("battle.monster.call")
            self._add_monster_ally(actor, same_monster=True)
            self._monster_call_pending = True
            self._reinforcement_post_entrance_wait_frames = 0
            return
        if action is MonsterAction.CHARGE:
            self._begin_monster_charge(actor)
            return
        if action is MonsterAction.CONSTRICTION:
            self._show_monster_action_message("battle.monster.constriction")
            self._begin_standard_monster_attack(actor, constricting=True)
            return
        if action is MonsterAction.POISON_BREATH:
            if not self._begin_monster_poison_breath(actor):
                self._start_timeline_animation()
            return
        if action is MonsterAction.FIRE_BREATH:
            if not self._begin_monster_fire_breath(actor):
                self._start_timeline_animation()
            return
        if action is MonsterAction.EARTHQUAKE:
            if not self._begin_monster_earthquake(actor):
                self._start_timeline_animation()
            return
        if action is MonsterAction.TEMPTATION:
            if not self._begin_monster_temptation(actor):
                self._start_timeline_animation()
            return
        if action is MonsterAction.BLACK_WIND:
            self._begin_monster_black_wind(actor)
            return
        if isinstance(action, MonsterSpellAction):
            spell = self.spells[action.spell_key]
            if not self._begin_monster_spell(
                actor,
                spell,
                silenced=turn_was_silenced,
            ):
                self._start_timeline_animation()
            return
        self._begin_standard_monster_attack(actor)

    def _attempt_monster_reinforcement(self, actor: BattleMonster) -> bool:
        """Add one ally before the actor's ordinary action without a message."""

        if MonsterSpecialAction.REINFORCE not in actor.special_actions:
            return False
        living_count = sum(monster.is_alive for monster in self.monsters)
        if not reinforcement_arrives(living_count):
            return False
        return self._add_monster_ally(actor, same_monster=False)

    def _monster_ally_slot(self, target: BattleMonster | None = None) -> int | None:
        """Find the first unoccupied display slot, including defeated slots."""

        placement = self._monster_ally_placement(self.monsters[0] if target is None else target)
        return None if placement is None else placement[0]

    def _monster_ally_placement(
        self, target: object,
    ) -> tuple[int, tuple[int, int]] | None:
        """Fit a new image without moving or overlapping surviving enemies."""

        occupied = tuple(
            self._monster_placement(index)
            for index, monster in enumerate(self.monsters)
            if monster.is_alive
        )
        placement = find_monster_placement(target, occupied)
        return None if placement is None else (placement.slot, (placement.x, placement.y))

    def _add_monster_ally(self, actor: BattleMonster, *, same_monster: bool) -> bool:
        """Register a new ally with independent timeline and reward identity."""

        caller = self.monster_definitions_by_key[actor.key]
        target = (
            caller
            if same_monster
            else reinforcement_target(
                caller,
                tuple(self.monster_definitions_by_key.values()),
            )
        )
        placement = self._monster_ally_placement(target)
        if placement is None:
            return False
        slot, position = placement
        record = self.monster_records_by_key[target.key]
        monster = BattleMonster.from_record(
            record,
            is_front_row=slot >= 2,
        )
        index = len(self.monsters)
        self.monsters += (monster,)
        self.monster_slot_indexes += (slot,)
        self._refresh_monster_rows_from_slots()
        self.reinforcement_entrance_frames[index] = 0
        self.monster_positions += (position,)
        self.monster_images[target.key] = self.monster_image_resources.image(
            target.image_resource_id
        )
        name_x, name_y = self._monster_name_window_grid_position(monster, *position)
        window = self.monster_window_factory.create(
            name_x, name_y, 20, 4, transparent=True
        )
        name_text = window.add_text(
            monster.display_name(self.localizer),
            0,
            0,
            color=RESERVE_MEMBER_TEXT_COLOR,
        )
        self.monster_name_windows.append(window)
        self.monster_name_texts.append(name_text)
        self.monster_record_system.register_encounter((target.key,))
        progression_index = self.progression.register_enemy(
            EnemyProgressionData(
                monster.level,
                monster.early_appear,
                monster.max_occurrence,
                monster.gold,
                monster.key,
                monster.treasure_item_key,
                monster.treasure_rate,
            )
        )
        if progression_index != index:
            raise RuntimeError("reinforcement progression index is out of sync")
        agility = self._actor_agility(monster)
        self._timeline_order = insert_timeline_actor(
            self._timeline_order,
            monster,
            agility=agility,
            gauge=min(float(agility), GAUGE_READY_VALUE),
        )
        self.timeline = self._timeline_order.actors
        self._refresh_monster_target_cursor()
        return True

    def _refresh_monster_rows_from_slots(self) -> None:
        """Restore slot rows when reinforcements refill an empty front line."""

        front_slot_occupied = any(
            existing.is_alive and existing_slot >= 2
            for existing, existing_slot in zip(self.monsters, self.monster_slot_indexes)
        )
        for existing, existing_slot in zip(self.monsters, self.monster_slot_indexes):
            if existing.is_alive:
                existing.is_front_row = (
                    existing_slot >= 2 if front_slot_occupied else True
                )

    def _update_reinforcement_entrances(self) -> None:
        """Advance each arriving monster's slide in update, never in draw."""

        frames = getattr(self, "reinforcement_entrance_frames", None)
        if not frames:
            return
        for index, elapsed in tuple(frames.items()):
            duration = MONSTER_ENTRANCE_FRAME_COUNTS[self._monster_slot_index(index)]
            if elapsed + 1 >= duration:
                del frames[index]
            else:
                frames[index] = elapsed + 1

    def _refresh_monster_target_cursor(self) -> None:
        """Keep cursor identities unique when a dead display slot is reused."""

        self.target_cursor = self.target_window.set_cursor(
            tuple(
                CursorTarget(
                    (x + 8) // 4,
                    (y + 16) // 4,
                    key=index,
                )
                for index, (monster, (x, y)) in enumerate(
                    zip(self.monsters, self.monster_positions)
                )
                if monster.is_alive
            ),
            active=False,
        )

    def _monster_index(self, actor: BattleMonster) -> int:
        """Distinguish equal-valued monsters by their encounter identity."""

        for index, monster in enumerate(self.monsters):
            if monster is actor:
                return index
        raise ValueError("monster actor is not in this encounter")

    def _select_monster_action(
        self,
        actor: BattleMonster,
    ) -> MonsterActionChoice | None:
        """Evaluate spells and specials before choosing one action."""

        party_attacks: tuple[int, ...] = ()
        if actor.intelligence != 3 and MonsterSpecialAction.ESCAPE in actor.special_actions:
            party_attacks = tuple(
                self._member_actual_physical_attack(self.party[index])
                for index in self._active_party_indexes()
            )
        spell_keys = self._targetable_monster_spell_keys(actor)
        priority_spell_key = next(
            (key for key in spell_keys if self._monster_spell_candidates[key].priority),
            None,
        )
        return select_monster_action(
            special_actions=actor.special_actions,
            is_front_row=actor.is_front_row,
            can_attack=bool(self._monster_attack_target_indexes(actor)),
            can_charge=bool(self._monster_charge_target_indexes()),
            can_breathe=bool(self._monster_charge_target_indexes()),
            can_earthquake=bool(self._active_party_indexes()),
            can_tempt=(
                MonsterSpecialAction.TEMPTATION in actor.special_actions
                and bool(self._temptation_target_indexes())
            ),
            black_wind_has_targets=(
                MonsterSpecialAction.BLACK_WIND in actor.special_actions
                and bool(self._black_wind_target_indexes())
            ),
            fire_breath_effective=actor.intelligence != 7 or (
                MonsterSpecialAction.FIRE_BREATH not in actor.special_actions
            ) or any(
                ResistanceType.FIRE not in self.party[index].spell_resistances
                for index in self._monster_charge_target_indexes()
            ),
            party_actual_attacks=party_attacks,
            monster_attack=actor.combat_stats.attack,
            spell_keys=spell_keys,
            priority_spell_key=priority_spell_key,
            call_slot=(
                self._monster_ally_slot(actor if actor.intelligence in (2, 3) else None)
                if MonsterSpecialAction.CALL in actor.special_actions
                else None
            ),
            intelligence=actor.intelligence,
            rotation_state=actor.state,
            learned_spell_keys=actor.spell_keys,
        )

    def _targetable_monster_spell_keys(
        self,
        actor: BattleMonster,
    ) -> tuple[str, ...]:
        """Evaluate learned spells and retain their planned targets."""

        self._monster_spell_candidates: dict[str, MonsterSpellCandidate] = {}
        spells = tuple(self.spells[key] for key in actor.spell_keys)
        for spell in monster_spell_evaluation_order(spells, actor.intelligence):
            candidate = self._evaluate_monster_spell(actor, spell)
            if candidate.targets:
                self._monster_spell_candidates[spell.key] = candidate
                if candidate.priority:
                    break
        return tuple(self._monster_spell_candidates)

    def _member_can_cast_spells(self, member: Member) -> bool:
        return any(
            spell.type is not SpellType.ITEM
            and spell.on_battle
            and spell.is_learned_by(member)
            for spell in self.spells.values()
        )

    def _evaluate_monster_spell(
        self, actor: BattleMonster, spell: Spell,
    ) -> MonsterSpellCandidate:
        indexes = self._monster_spell_target_indexes(spell)
        if actor.intelligence <= 0:
            return MonsterSpellCandidate(indexes)
        if actor.state.silenced or actor.state.mp < spell.mp:
            return MonsterSpellCandidate(())
        if not spell.to_enemy:
            return evaluate_monster_support_spell(spell, indexes, intelligence=actor.intelligence)
        targets = tuple(
            MonsterSpellTarget(
                index=index,
                front=self.party[index].formation_row is FormationRow.FRONT,
                actionable=not (
                    self.party[index].sleeping
                    or self.party[index].paralyzed
                    or self.party[index].confused
                ),
                can_cast=(
                    spell.action is SpellAction.SILENCE
                    and self._member_can_cast_spells(self.party[index])
                ),
                silenced=self.party[index].silenced,
                speed=self.party[index].speed_modifier,
                protection=self.party[index].protection_level,
                resistances=self.party[index].spell_resistances,
                magic_shield=self.party[index].magic_shield,
            )
            for index in indexes
        )
        return evaluate_monster_spell(
            spell,
            targets,
            intelligence=actor.intelligence,
            choose=random.choice,
        )

    def _preferred_monster_party_targets(
        self, actor: BattleMonster, indexes: tuple[int, ...],
    ) -> tuple[int, ...]:
        def is_incapacitated(index: int) -> bool:
            member = self.party[index]
            return not member.confused and bool(member.sleeping or member.paralyzed)

        return prefer_monster_targets(
            indexes, intelligence=actor.intelligence, is_incapacitated=is_incapacitated,
        )

    def _monster_spell_target_indexes(self, spell: Spell) -> tuple[int, ...]:
        """Resolve spell targets from the monster caster's perspective."""

        if spell.to_enemy:
            hidden = getattr(self, "hidden_party_indexes", set())
            return tuple(
                index for index in self._active_party_indexes() if index not in hidden
            )
        if spell.action is SpellAction.REVIVE:
            return self._monster_revival_target_indexes()
        living = tuple(index for index, monster in enumerate(self.monsters) if monster.is_alive)
        if spell.action is SpellAction.MAGIC_SHIELD:
            return tuple(i for i in living if not self.monsters[i].state.magic_shield)
        if spell.action is SpellAction.HASTE:
            return tuple(i for i in living if self.monsters[i].state.speed_modifier < MAX_SPEED_MODIFIER)
        if spell.action is SpellAction.PROTECTION:
            return tuple(i for i in living if self.monsters[i].state.defense_modifier < MAX_PROTECTION_LEVEL)
        if spell.action is SpellAction.HEAL:
            return tuple(i for i in living if self.monsters[i].state.hp < self.monsters[i].state.max_hp)
        return living

    def _monster_placement(self, index: int) -> MonsterPlacement:
        monster = self.monsters[index]
        return MonsterPlacement(
            self._monster_slot_index(index), *self._monster_base_position(index),
            monster.width, monster.height,
        )

    def _monster_revival_target_indexes(self) -> tuple[int, ...]:
        escaped = getattr(self, "escaped_monster_indexes", ())
        defeated = tuple(
            index for index, monster in enumerate(self.monsters)
            if not monster.is_alive and index not in escaped
        )
        if not defeated:
            return ()
        occupied = tuple(
            self._monster_placement(index)
            for index, monster in enumerate(self.monsters) if monster.is_alive
        )
        return tuple(
            index for index in defeated
            if monster_revival_placement_available(self._monster_placement(index), occupied)
        )

    @property
    def screen_shake_offset(self) -> tuple[int, int]:
        presentation = getattr(self, "action_presentation", None)
        if presentation is not None and presentation.earthquake:
            return presentation.shake_offset
        return (0, 0)

    def _begin_monster_earthquake(self, actor: BattleMonster) -> bool:
        indexes = self._active_party_indexes()
        if not indexes:
            return False
        damages = []
        stuns = []
        for index in indexes:
            member = self.party[index]
            resistances = member.resistances
            defending = index in self.defending_party_indexes
            result = resolve_earthquake_attack(
                attack=actor.combat_stats.attack, hit=actor.combat_stats.hit,
                target_defense=member.battle_stats.defense,
                target_defending=defending, hit_roll=random.randint(0, 99),
                target_floating=self._party_member_is_fairy(index),
                target_resists_tribe=member.equipment.resists_tribe(actor.tribe),
            )
            stun_success = result.hit and resolve_physical_additional_effect(
                effect=AdditionalEffect.STUN, adjusted_hit=result.adjusted_hit,
                effect_roll=random.randint(0, 99), target_is_member=True,
                target_has_boss_resistance=ResistanceType.DEATH in resistances,
                target_is_resistant=result.tribe_resisted or ResistanceType.STUN in resistances,
                target_defending=defending,
            ).success
            x, y = self._party_draw_position(index) or (self._party_sprite_x(index), PARTY_SPRITE_Y[index])
            damages.append(BattleSpellDamageResult(
                index, result.damage,
                SpellAffinity.RESIST if result.tribe_resisted else SpellAffinity.NORMAL,
                x + 6, y + 16, x + 8 - AFFINITY_ICON_WIDTH // 2, y - 8,
                is_miss=not result.hit,
            ))
            stuns.append(BattlePartyStunResult(index, stun_success))
        self.action_presentation = BattleActionPresentation(
            (), party_damage_results=tuple(damages), party_stun_results=tuple(stuns),
            earthquake=True, result_start_frame=EARTHQUAKE_SHAKE_FRAME_COUNT,
            post_effect_wait_frame_count=EARTHQUAKE_SHAKE_FRAME_COUNT + DAMAGE_POPUP_FRAME_COUNT,
        )
        self.phase = BattlePhase.ACTION_PRESENTATION
        self._queue_spell_affinity_popups(
            damages, dict.fromkeys(indexes, EARTHQUAKE_SHAKE_FRAME_COUNT),
        )
        self._show_monster_action_message("battle.monster.earthquake")
        play_se(BATTLE_EARTHQUAKE_SE_ID)
        return True

    def _begin_monster_temptation(self, actor: BattleMonster) -> bool:
        indexes = self._temptation_target_indexes()
        if not indexes:
            return False
        results = self._resolve_monster_confuse_results(
            actor.magic, indexes, rate=TEMPTATION_RATE, attribute=ResistanceType.CONFUSE,
        )
        effects = self._build_target_spell_effects(
            "CONFUSION", "ally", tuple(result.target_index for result in results if result.success),
            caster=("enemy", self._monster_index(actor)),
        )
        effect_frame_count = max(
            (effect.player.definition.total_frames for effect in effects),
            default=0,
        )
        settings = getattr(self, "settings", None)
        result_frame = max(effect_frame_count - SPELL_RESULT_OVERLAP_FRAME_COUNT, 0)
        screen_flash = (
            SpellScreenFlash(TEMPTATION_FLASH_COLOR, result_frame)
            if settings is None or settings.screen_flash_enabled else None
        )
        self.action_presentation = BattleActionPresentation(
            effects,
            party_confuse_results=results,
            screen_flash=screen_flash,
            result_start_frame=screen_flash.release_frame if screen_flash else result_frame,
        )
        self.phase = BattlePhase.ACTION_PRESENTATION
        self._show_monster_action_message("battle.monster.temptation")
        self._start_target_spell_effects(effects)
        return True

    def _begin_monster_black_wind(self, actor: BattleMonster) -> None:
        targets = self._black_wind_target_indexes()
        effects = self._build_target_spell_effects(
            BLACK_WIND_EFFECT_KEY, "enemy", targets,
            caster=("enemy", self._monster_index(actor)),
            target_start_frames=dict.fromkeys(targets, BLACK_WIND_EFFECT_DELAY),
        )
        self.action_presentation = BattleActionPresentation(
            effects,
            black_wind_targets=targets,
            background_tint_color=BLACK_WIND_TINT_COLOR,
            result_start_frame=BLACK_WIND_RESULT_FRAME,
            post_effect_wait_frame_count=0,
        )
        self.phase = BattlePhase.ACTION_PRESENTATION
        self._sync_action_background(self.action_presentation)
        self._start_target_spell_effects(effects)
        if getattr(self, "action_popup_window", None) is not None and getattr(
            self, "battle_popup", None,
        ) is not None:
            self._show_battle_popup(
                self.texts.formatted_text(
                    "battle.monster.black_wind", self.localizer,
                    {"MONSTER": actor.display_name(self.localizer)},
                ),
                BLACK_WIND_RESULT_FRAME,
                align_left=True,
            )

    def _begin_monster_poison_breath(self, actor: BattleMonster) -> bool:
        return self._begin_monster_breath(actor, poisonous=True)

    def _begin_monster_fire_breath(self, actor: BattleMonster) -> bool:
        return self._begin_monster_breath(actor, poisonous=False)

    def _begin_monster_breath(self, actor: BattleMonster, *, poisonous: bool) -> bool:
        """Start DA2's simultaneous all-party damage and background tint."""

        indexes = self._monster_charge_target_indexes()
        if not indexes:
            return False
        damages = []
        poisons = []
        for index in indexes:
            member = self.party[index]
            arguments = dict(
                attack=actor.combat_stats.attack,
                hp=actor.state.hp,
                max_hp=actor.state.max_hp,
                target_spell_defense=member.battle_stats.spell_resistance,
                random_factor=random.random(),
            )
            if poisonous:
                result = resolve_poison_breath(
                    **arguments,
                    poison_resistant=ResistanceType.POISON in member.resistances,
                    poison_roll=random.randint(0, 9),
                )
            else:
                result = resolve_fire_breath(
                    **arguments,
                    fire_resistant=ResistanceType.FIRE in member.spell_resistances,
                )
            position = self._party_draw_position(index)
            if position is None:
                continue
            x, y = position
            affinity = SpellAffinity.RESIST if result.resisted else SpellAffinity.NORMAL
            damages.append(BattleSpellDamageResult(
                index, result.damage, affinity, x + 6, y + 16,
                x + 8 - AFFINITY_ICON_WIDTH // 2, y - 8,
            ))
            if poisonous:
                poisons.append(BattlePoisonResult(index, result.poisoned))
        presentation = BattleActionPresentation(
            (),
            party_damage_results=tuple(damages),
            party_poison_results=tuple(poisons),
            background_tint_color=(
                POISON_BREATH_TINT_COLOR if poisonous else FIRE_BREATH_TINT_COLOR
            ),
            result_start_frame=DAMAGE_POPUP_FRAME_COUNT,
            post_effect_wait_frame_count=0,
        )
        self.action_presentation = presentation
        self.phase = BattlePhase.ACTION_PRESENTATION
        self.spell_damage_popups.extend(
            BattleSpellDamagePopup(result.popup_x, result.popup_y, result.damage)
            for result in damages
        )
        self.affinity_popups.extend(
            BattleAffinityPopup(result.affinity_x, result.affinity_y, result.affinity)
            for result in damages if result.affinity is SpellAffinity.RESIST
        )
        self._sync_action_background(presentation)
        self._show_monster_action_message(
            "battle.monster.poison_breath" if poisonous else "battle.monster.fire_breath"
        )
        play_se(BATTLE_POISON_BREATH_SE_ID if poisonous else BATTLE_FIRE_BREATH_SE_ID)
        return True

    def _sync_action_background(
        self, presentation: BattleActionPresentation,
    ) -> None:
        """Update only the background palette; draw never advances the tint."""

        # Breaths and Black Wind use the palette block without a target flash.
        self._stop_inner_steel_palette()
        self._release_palette_variant(UNSELECTABLE_TARGET_PALETTE)
        self.palette_shifter.define_mix(
            SPELL_EFFECT_FLASH_PALETTE,
            base_rate=0.7 + cos(presentation.background_tint_progress * pi) * 0.3,
            target_color=presentation.background_tint_color,
        )

    def _begin_monster_spell(
        self,
        actor: BattleMonster,
        spell: Spell,
        *,
        silenced: bool | None = None,
    ) -> bool:
        """Attempt one basic-AI spell, applying DA2's shared MP check."""

        candidates = self._monster_spell_target_indexes(spell)
        if not candidates:
            return False
        if silenced is None:
            silenced = actor.state.silenced > 0
        if silenced:
            self.action_presentation = BattleActionPresentation(
                (),
                post_effect_wait_frame_count=MONSTER_SPELL_FAILURE_FRAME_COUNT,
            )
            self.phase = BattlePhase.ACTION_PRESENTATION
            self._show_monster_spell_sealed_message()
            return True
        if not actor.state.spend_mp(spell.mp):
            self.action_presentation = BattleActionPresentation(
                (),
                post_effect_wait_frame_count=MONSTER_SPELL_FAILURE_FRAME_COUNT,
            )
            self.phase = BattlePhase.ACTION_PRESENTATION
            self._show_monster_spell_mp_lack_message(actor)
            return True

        planned = getattr(self, "_monster_spell_candidates", {}).pop(
            spell.key, None
        )
        if actor.intelligence > 0 and planned is not None:
            candidates = planned.targets
        if spell.to_enemy and not spell.to_all:
            candidates = self._preferred_monster_party_targets(actor, candidates)
        indexes = (
            candidates
            if spell.to_all or len(candidates) == 1
            else (random.choice(candidates),)
        )
        self._prepare_spell_presentation(spell, indexes, ("enemy", self._monster_index(actor)))
        self.phase = BattlePhase.ACTION_PRESENTATION
        self._show_spell_cast_message(spell, actor_is_enemy=True)
        self._start_target_spell_effects(self.action_presentation.spell_effects)
        return True

    def _resolve_monster_spell_damage_results(
        self,
        modifier: int,
        spell: Spell,
        indexes: tuple[int, ...],
    ) -> tuple[BattleSpellDamageResult, ...]:
        """Resolve enemy DAMAGE with the same rule as player offensive magic."""

        if spell.action not in (SpellAction.DAMAGE, SpellAction.BLOOD_SUCK) or not spell.to_enemy:
            return ()
        results: list[BattleSpellDamageResult] = []
        for index in indexes:
            member = self.party[index]
            resolution = resolve_spell_damage(
                intensity=spell.intensity,
                spell_modifier=modifier,
                target_spell_defense=member.battle_stats.spell_resistance,
                attribute=spell.attribute,
                target_weaknesses=frozenset(),
                target_resistances=member.spell_resistances,
                dark_resistance_causes_miss=spell.action is SpellAction.BLOOD_SUCK,
                random_factor=random.random(),
            )
            position = self._party_draw_position(index)
            if position is None:
                continue
            x, y = position
            results.append(
                BattleSpellDamageResult(
                    target_index=index,
                    damage=resolution.damage,
                    affinity=resolution.affinity,
                    popup_x=x + 6,
                    popup_y=y + 16,
                    affinity_x=x + 8 - AFFINITY_ICON_WIDTH // 2,
                    affinity_y=y - 8,
                    is_miss=resolution.is_miss,
                )
            )
        return tuple(results)

    def _resolve_monster_poison_results(
        self,
        modifier: int,
        spell: Spell,
        indexes: tuple[int, ...],
    ) -> tuple[BattlePoisonResult, ...]:
        if not spell.to_enemy or spell.attribute is not ResistanceType.POISON:
            return ()

        results: list[BattlePoisonResult] = []
        for index in indexes:
            member = self.party[index]
            resistances = member.resistances
            resolution = resolve_status_spell(
                spell_modifier=modifier,
                rate=spell.rate,
                target_spell_defense=member.battle_stats.spell_resistance,
                attribute=spell.attribute,
                target_weaknesses=frozenset(),
                target_resistances=resistances,
                success_roll=0 if spell.attribute in resistances else random.randint(0, 19),
            )
            results.append(BattlePoisonResult(index, resolution.success))
        return tuple(results)

    def _resolve_monster_silence_results(self, modifier, spell, indexes):
        if spell.action is not SpellAction.SILENCE or not spell.to_enemy:
            return ()
        results = []
        for index in indexes:
            member = self.party[index]
            success = False
            if self._member_can_cast_spells(member):
                success = resolve_status_spell(
                    spell_modifier=modifier,
                    rate=spell.rate,
                    target_spell_defense=member.battle_stats.spell_resistance,
                    attribute=spell.attribute,
                    target_weaknesses=frozenset(),
                    target_resistances=member.spell_resistances,
                    success_roll=random.randint(0, 19),
                ).success
            position = self._party_draw_position(index)
            if position is not None:
                x, y = position
                results.append(
                    BattlePartySilenceResult(
                        index,
                        success,
                        (
                            random.randint(*debuff_turn_range(member.resistances))
                            if success
                            else 0
                        ),
                        x + 6,
                        y + 16,
                    )
                )
        return tuple(results)

    def _resolve_monster_sleep_results(
        self,
        modifier: int,
        spell: Spell,
        indexes: tuple[int, ...],
    ) -> tuple[BattlePartySleepResult, ...]:
        """Resolve a monster's SLEEP spell against party battle stats."""

        if spell.action is not SpellAction.SLEEP or not spell.to_enemy:
            return ()
        results: list[BattlePartySleepResult] = []
        for index in indexes:
            member = self.party[index]
            resolution = resolve_status_spell(
                spell_modifier=modifier,
                rate=spell.rate,
                target_spell_defense=member.battle_stats.spell_resistance,
                attribute=spell.attribute,
                target_weaknesses=frozenset(),
                target_resistances=member.spell_resistances,
                success_roll=random.randint(0, 19),
            )
            position = self._party_draw_position(index)
            if position is None:
                continue
            x, y = position
            results.append(
                BattlePartySleepResult(
                    target_index=index,
                    success=resolution.success,
                    turns=(
                        random.randint(SLEEP_MIN_TURNS, SLEEP_MAX_TURNS)
                        if resolution.success
                        else 0
                    ),
                    popup_x=x + 6,
                    popup_y=y + 16,
                )
            )
        return tuple(results)

    def _resolve_monster_confuse_results(
        self,
        modifier: int,
        indexes: tuple[int, ...],
        *,
        rate: int,
        attribute: ResistanceType | None,
    ) -> tuple[BattlePartyConfuseResult, ...]:
        """Roll enemy-inflicted confusion against party battle stats."""

        results: list[BattlePartyConfuseResult] = []
        for index in indexes:
            member = self.party[index]
            resolution = resolve_status_spell(
                spell_modifier=modifier,
                rate=rate,
                target_spell_defense=member.battle_stats.spell_resistance,
                attribute=attribute,
                target_weaknesses=frozenset(),
                target_resistances=member.spell_resistances,
                success_roll=random.randint(0, 19),
            )
            x, y = self._party_effect_position(index)
            results.append(
                BattlePartyConfuseResult(
                    target_index=index,
                    success=resolution.success,
                    turns=(
                        random.randint(CONFUSE_MIN_TURNS, CONFUSE_MAX_TURNS)
                        if resolution.success
                        else 0
                    ),
                    popup_x=x + 6,
                    popup_y=y + 16,
                )
            )
        return tuple(results)

    def _resolve_monster_slow_results(
        self,
        modifier: int,
        spell: Spell,
        indexes: tuple[int, ...],
    ) -> tuple[BattlePartySlowResult, ...]:
        """Resolve a monster's SLOW spell against party battle stats."""

        if spell.action is not SpellAction.SLOW or not spell.to_enemy:
            return ()
        results: list[BattlePartySlowResult] = []
        for index in indexes:
            member = self.party[index]
            success = False
            if member.speed_modifier > MIN_SPEED_MODIFIER:
                success = resolve_status_spell(
                    spell_modifier=modifier,
                    rate=spell.rate,
                    target_spell_defense=member.battle_stats.spell_resistance,
                    attribute=spell.attribute,
                    target_weaknesses=frozenset(),
                    target_resistances=member.spell_resistances,
                    success_roll=random.randint(0, 19),
                ).success
            position = self._party_draw_position(index)
            if position is None:
                continue
            x, y = position
            results.append(
                BattlePartySlowResult(
                    target_index=index,
                    success=success,
                    popup_x=x + 6,
                    popup_y=y + 16,
                )
            )
        return tuple(results)

    def _resolve_monster_break_results(
        self,
        modifier: int,
        spell: Spell,
        indexes: tuple[int, ...],
    ) -> tuple[BattlePartyBreakResult, ...]:
        """Resolve a monster's BREAK spell against party battle stats."""

        if spell.action is not SpellAction.BREAK or not spell.to_enemy:
            return ()
        results: list[BattlePartyBreakResult] = []
        for index in indexes:
            member = self.party[index]
            success = False
            if member.protection_level >= 0 and member.battle_stats.defense > 0:
                success = resolve_status_spell(
                    spell_modifier=modifier,
                    rate=spell.rate,
                    target_spell_defense=member.battle_stats.spell_resistance,
                    attribute=spell.attribute,
                    target_weaknesses=frozenset(),
                    target_resistances=member.spell_resistances,
                    success_roll=random.randint(0, 19),
                ).success
            position = self._party_draw_position(index)
            if position is None:
                continue
            x, y = position
            results.append(
                BattlePartyBreakResult(
                    target_index=index,
                    success=success,
                    popup_x=x + 6,
                    popup_y=y + 16,
                )
            )
        return tuple(results)

    @staticmethod
    def _member_actual_physical_attack(member: object) -> int:
        """Return the same total attack used by an actual member strike."""

        if not isinstance(member, Member):
            return max(0, int(getattr(member, "actual_attack", 0)))
        weapon = member.equipment.weapon_at(EquipmentSlot.RIGHT)
        if weapon is None:
            return 0
        return BattleScene._member_weapon_attack(member, weapon, member.battle_stats.attack_right)

    @staticmethod
    def _member_weapon_attack(member: Member, weapon: Item, weapon_attack: int) -> int:
        attack = member_physical_attack(
            weapon_attack=weapon_attack,
            strength=member.adjusted_abilities.strength,
            weapon_level=member.weapon_level(weapon),
            internal_level=member.internal_level,
        )
        if member.has_skill(INNER_STEEL_SKILL_KEY):
            attack = inner_steel_attack(attack, member.hp, member.max_hp)
        return attack

    def _party_member_can_cover(self, index: int) -> bool:
        """Return DA2's actionable condition for a potential coverer."""

        if index not in self._active_party_indexes():
            return False
        member = self.party[index]
        return not (
            getattr(member, "paralyzed", False)
            or getattr(member, "sleeping", 0)
            or getattr(member, "confused", 0)
        )

    def _covering_member_index(self, protected_index: int) -> int:
        """Resolve manual Cover first, then DA2's automatic rescue rule."""

        active_indexes = self._active_party_indexes()
        manual_targets = getattr(self, "cover_target_by_party_index", {})
        for index in active_indexes:
            if (
                index != protected_index
                and manual_targets.get(index) == protected_index
                and self._party_member_can_cover(index)
            ):
                return index

        protected = self.party[protected_index]
        protected_hp = getattr(protected, "hp", 0)
        protected_max_hp = getattr(protected, "max_hp", protected_hp)
        needs_cover = (
            protected_hp <= protected_max_hp // 4
            or bool(getattr(protected, "sleeping", 0))
            or bool(getattr(protected, "paralyzed", False))
        )
        if not needs_cover:
            return protected_index
        for index in active_indexes:
            member = self.party[index]
            has_cover = getattr(member, "has_skill", None)
            if (
                index != protected_index
                and callable(has_cover)
                and has_cover("Cover")
                and self._party_member_can_cover(index)
                and member.hp > member.max_hp // 4
            ):
                return index
        return protected_index

    def _resolve_monster_attack(
        self,
        actor: BattleMonster,
        target_indexes: tuple[int, ...],
        *,
        attack: int,
        constricting: bool = False,
    ) -> tuple[int, PhysicalAttackResult]:
        """Resolve one monster physical attack without starting presentation."""

        protected_index = random.choice(
            self._preferred_monster_party_targets(actor, target_indexes)
        )
        target_index = self._covering_member_index(protected_index)
        self.protected_party_index = (
            protected_index if target_index != protected_index else None
        )
        self.covering_party_index = (
            target_index if target_index != protected_index else None
        )
        if target_index != protected_index:
            getattr(self, "hidden_party_indexes", set()).discard(target_index)
        target = self.party[target_index]
        target_stats = target.battle_stats
        target_incapacitated = bool(
            getattr(target, "sleeping", 0) or getattr(target, "confused", 0)
        )
        power_hit = MonsterSpecialAction.POWER_HIT in actor.special_actions
        roll_count = CONSTRICTION_HIT_ROLL_COUNT if constricting else PHYSICAL_HIT_ROLL_COUNT
        result = resolve_physical_attack(
            attack=attack,
            hit=actor.combat_stats.hit,
            target_defense=target_stats.defense,
            target_evasion=target_stats.evasion,
            hit_roll=random.randint(0, roll_count - 1),
            constricting=constricting,
            target_defending=(target_index in self.defending_party_indexes),
            target_unable_to_evade=(
                target_index in getattr(self, "focused_target_by_party_index", {})
            ),
            target_incapacitated=target_incapacitated,
            attacker_is_monster=True,
            attacker_has_power_hit=power_hit,
            target_resists_tribe=(
                isinstance(target, Member)
                and target.equipment.resists_tribe(getattr(actor, "tribe", None))
            ),
            critical_roll=(
                random.randint(0, 99) if power_hit or target_incapacitated else None
            ),
        )
        return target_index, result

    def _resolve_monster_attack_additional_effects(
        self,
        actor: BattleMonster,
        target_index: int,
        result: PhysicalAttackResult,
        *,
        constricting: bool = False,
    ) -> tuple[AdditionalEffect, ...]:
        """Resolve the monster's effects against the party member taking the hit."""

        if not actor.additional_effects and not constricting:
            return ()
        target = self.party[target_index]
        return resolve_monster_attack_effects(
            actor.additional_effects,
            result,
            roll_effect=lambda: random.randint(0, 99),
            target_is_member=True,
            target_resistances=getattr(target, "resistances", ()),
            target_defending=target_index in self.defending_party_indexes,
            constricting=constricting,
        )

    def _queue_monster_counter(self, monster_index: int) -> None:
        actor = self.monsters[monster_index]
        if not isinstance(actor, BattleMonster) or MonsterSpecialAction.COUNTER not in actor.special_actions:
            return
        party_index = getattr(self, "active_party_index", None)
        if party_index is None:
            return
        member = self.party[party_index]
        if counter_attack_succeeds(
            attacker_agility=member.effective_agility,
            defender_agility=actor.effective_agility,
            attacker_front=self._party_member_is_front_row(party_index),
            defender_front=actor.is_front_row,
            defender_actionable=self._monster_can_counter(actor),
            roll=random.randint(0, 19),
        ):
            pending = getattr(self, "pending_monster_counters", None)
            if pending is None:
                pending = self.pending_monster_counters = []
            pending.append((monster_index, party_index))

    def _queue_party_counter(self, party_index: int) -> None:
        """Test the actual recipient of the enemy's first normal strike."""

        if getattr(self, "surprise_active", False):
            return
        member = self.party[party_index]
        if not isinstance(member, Member) or not member.has_skill("Retaliate"):
            return
        if not self._member_can_counter(member):
            return
        attacker = self.timeline[0]
        if counter_attack_succeeds(
            attacker_agility=attacker.effective_agility,
            defender_agility=member.effective_agility,
            attacker_front=attacker.is_front_row,
            defender_front=self._party_member_is_front_row(party_index),
            defender_actionable=True,
            defender_reach=member_attack_reach(member),
            roll=random.randint(0, 19),
        ):
            self.pending_party_counter_index = party_index

    @staticmethod
    def _member_can_counter(member: Member) -> bool:
        return member.is_alive and member_can_attack(member) and not (
            member.sleeping or member.paralyzed or member.confused or member.stunned
        )

    def _begin_pending_party_counter(self) -> bool:
        party_index = getattr(self, "pending_party_counter_index", None)
        if party_index is None:
            return False
        self.pending_party_counter_index = None
        if not self._member_can_counter(self.party[party_index]):
            return False
        attacker_index = self._monster_index(self.timeline[0])
        if not self._start_member_attack(party_index, attacker_index, is_counter=True):
            return False
        self._begin_action_motion(use_cast_pose=False, jump=True, party_index=party_index)
        self._show_battle_popup(
            self.texts.text("battle.monster.counter", self.localizer),
            BATTLE_POPUP_FRAME_COUNT,
        )
        return True

    @staticmethod
    def _monster_can_counter(actor: BattleMonster) -> bool:
        return actor.is_alive and not (
            actor.state.sleeping or actor.state.confused or actor.state.stunned
        )

    def _begin_pending_monster_counter(self) -> bool:
        pending = getattr(self, "pending_monster_counters", [])
        while pending:
            actor_index, party_index = pending.pop(0)
            if not self._monster_can_counter(self.monsters[actor_index]):
                continue
            if self._member_is_dead(self.party[party_index]):
                continue
            self.monster_counter_actor_index = actor_index
            self.monster_counter_target_index = party_index
            self.monster_attack_target_index = None
            self.monster_blink_frames_remaining = MONSTER_BLINK_FRAME_COUNT
            self.blinking_monster_index = actor_index
            self.phase = BattlePhase.MONSTER_ACTION
            return True
        return False

    def _update_monster_counter(self) -> None:
        if self.monster_attack_target_index is not None:
            self.monster_attack_animation_frame += 1
            if self.monster_attack_animation_frame >= self._monster_attack_animation_frame_count():
                self._finish_monster_attack()
            return
        self.monster_blink_frames_remaining = max(0, self.monster_blink_frames_remaining - 1)
        if self.monster_blink_frames_remaining:
            return
        self.blinking_monster_index = None
        actor = self.monsters[self.monster_counter_actor_index]
        self._show_monster_action_message("battle.monster.counter")
        if hasattr(self, "progression"):
            self.progression.record_enemy_action(self.monster_counter_actor_index)
        self._begin_standard_monster_attack(
            actor, target_indexes=(self.monster_counter_target_index,),
        )

    def _begin_standard_monster_attack(
        self, actor: BattleMonster, *, target_indexes: tuple[int, ...] | None = None,
        constricting: bool = False,
    ) -> None:
        target_index, result = self._resolve_monster_attack(
            actor,
            self._monster_attack_target_indexes(actor) if target_indexes is None else target_indexes,
            attack=actor.combat_stats.attack,
            constricting=constricting,
        )
        self.monster_attack_target_index = target_index
        self.monster_attack_damage = result.damage
        # Guard can turn a critical roll into a miss; only show landed damage.
        self.monster_attack_critical = bool(getattr(result, "critical", False) and result.damage > 0)
        self.monster_attack_additional_effects = (
            self._resolve_monster_attack_additional_effects(
                actor,
                target_index,
                result,
                constricting=constricting,
            )
        )
        self.monster_attack_animation_frame = 0
        self.monster_attack_damage_applied = False
        tribe_resisted = getattr(result, "tribe_resisted", False)
        if tribe_resisted:
            self._show_monster_tribe_resist(target_index)
        if result.hit and result.damage > 0:
            hit_se = BATTLE_HIT_SE_ID
            if (
                not constricting and not tribe_resisted
                and AdditionalEffect.DRAIN in actor.additional_effects
            ):
                position = self._party_draw_position(target_index)
                if position is not None and self._begin_monster_drain(
                    actor, result.damage, position[0] + 14, position[1] + 16
                ):
                    hit_se = BATTLE_DRAIN_SE_ID
            play_se(hit_se)

    def _show_monster_tribe_resist(self, target_index: int) -> None:
        position = self._party_draw_position(target_index)
        if position is not None:
            x, y = position
            self.affinity_popups.append(BattleAffinityPopup(
                x + 8 - AFFINITY_ICON_WIDTH // 2, y - 8, SpellAffinity.RESIST,
            ))

    def _begin_monster_charge(self, actor: BattleMonster) -> None:
        """Start a ranged 1.5x charge toward one living party member."""

        actor_index = self._monster_index(actor)
        target_index, result = self._resolve_monster_attack(
            actor,
            self._monster_charge_target_indexes(),
            attack=(
                actor.combat_stats.attack
                * MONSTER_CHARGE_ATTACK_MULTIPLIER_NUMERATOR
                // MONSTER_CHARGE_ATTACK_MULTIPLIER_DENOMINATOR
            ),
        )
        start_x, start_y = self._monster_base_position(actor_index)
        target_x, target_y = self._monster_charge_destination(actor, target_index)
        distance = hypot(target_x - start_x, target_y - start_y)
        approach_frames = monster_charge_approach_frame_count(distance)
        return_frames = max(1, ceil(distance / MONSTER_CHARGE_RETURN_SPEED))
        reference_frames = self._monster_charge_reference_frame_count(actor)
        jump_height = max(
            1,
            MONSTER_CHARGE_MAX_JUMP_HEIGHT * approach_frames // reference_frames,
        )
        tribe_resisted = getattr(result, "tribe_resisted", False)
        self.monster_charge_presentation = BattleMonsterChargePresentation(
            actor_index=actor_index,
            target_index=target_index,
            damage=result.damage,
            is_critical=bool(getattr(result, "critical", False) and result.damage > 0),
            start_x=start_x,
            start_y=start_y,
            target_x=target_x,
            target_y=target_y,
            travel_distance=distance,
            approach_frame_count=approach_frames,
            return_frame_count=return_frames,
            jump_height=min(MONSTER_CHARGE_MAX_JUMP_HEIGHT, jump_height),
            additional_effects=self._resolve_monster_attack_additional_effects(
                actor,
                target_index,
                result,
            ),
            draining=(
                AdditionalEffect.DRAIN in actor.additional_effects
                and not tribe_resisted
            ),
            tribe_resisted=tribe_resisted,
        )
        self.action_gauge_adjustment = AIM_GAUGE_ADJUSTMENT
        self._show_monster_action_message("battle.monster.charge")

    def _monster_charge_destination(
        self,
        actor: BattleMonster,
        target_index: int,
    ) -> tuple[int, int]:
        position = self._party_draw_position(target_index)
        if position is None:
            raise RuntimeError("charge target must be visible")
        party_x, party_y = position
        return (
            party_x
            + PARTY_SPRITE_WIDTH // 2
            + MONSTER_CHARGE_TARGET_CENTER_OFFSET_X
            - actor.width,
            party_y + 16 - actor.height // 2,
        )

    @staticmethod
    def _monster_charge_reference_frame_count(actor: BattleMonster) -> int:
        """Return the longest layout-supported approach for this image size."""

        maximum_distance = 0.0
        for start_x, start_y in MONSTER_POSITIONS:
            for party_index, party_y in enumerate(PARTY_SPRITE_Y):
                for is_back_row in (False, True):
                    party_x = 156 + party_index * 4 + (16 if is_back_row else 0)
                    target_x = (
                        party_x
                        + PARTY_SPRITE_WIDTH // 2
                        + MONSTER_CHARGE_TARGET_CENTER_OFFSET_X
                        - actor.width
                    )
                    target_y = party_y + 16 - actor.height // 2
                    maximum_distance = max(
                        maximum_distance,
                        hypot(target_x - start_x, target_y - start_y),
                    )
        return monster_charge_approach_frame_count(maximum_distance)

    def _update_monster_charge(self) -> None:
        presentation = self.monster_charge_presentation
        if presentation is None:
            raise RuntimeError("charge action requires a presentation")
        presentation.elapsed_frame += 1
        if presentation.impact_reached and not presentation.damage_applied:
            self.monster_attack_target_index = presentation.target_index
            self.monster_attack_damage = presentation.damage
            self.monster_attack_critical = presentation.is_critical
            self.monster_attack_additional_effects = presentation.additional_effects
            self.monster_attack_animation_frame = 0
            self.monster_attack_damage_applied = True
            presentation.damage_applied = True
            self._apply_monster_attack_damage(
                presentation.target_index,
                presentation.damage,
            )
            self._apply_additional_effects_to_member(
                presentation.target_index,
                presentation.additional_effects,
            )
            if presentation.tribe_resisted:
                self._show_monster_tribe_resist(presentation.target_index)
            if presentation.damage > 0:
                hit_se = BATTLE_HIT_SE_ID
                if presentation.draining:
                    actor = self.monsters[presentation.actor_index]
                    position = self._party_draw_position(presentation.target_index)
                    if position is not None and self._begin_monster_drain(
                        actor, presentation.damage, position[0] + 14, position[1] + 16
                    ):
                        self._apply_monster_drain_healing()
                        hit_se = BATTLE_DRAIN_SE_ID
                play_se(hit_se)
        elif presentation.damage_applied:
            self.monster_attack_animation_frame += 1
        if presentation.completed:
            self._finish_monster_attack()

    def _begin_monster_escape(self, actor: BattleMonster) -> None:
        """Start DA2's leftward enemy escape without death presentation."""

        actor_index = self._monster_index(actor)
        self.monster_escape_actor_index = actor_index
        self.monster_escape_animation_frame = 0
        self.escaped_monster_indexes.add(actor_index)
        actor.state.defeat()
        promote_rear_monsters_if_front_empty(self.monsters)
        if hasattr(self, "progression"):
            self.progression.record_enemy_escape(actor_index)
        self._show_monster_action_message("battle.monster.escape")
        play_se(BATTLE_MONSTER_ESCAPE_SE_ID)

    def _update_monster_escape(self) -> None:
        actor_index = self.monster_escape_actor_index
        if actor_index is None:
            raise RuntimeError("monster escape requires an actor")
        self.monster_escape_animation_frame += 1
        monster = self.monsters[actor_index]
        if self._monster_escape_x(actor_index) + monster.width > 0:
            return
        self.monster_escape_actor_index = None
        self.monster_escape_animation_frame = 0
        self.monster_action = None
        if self._monsters_are_defeated():
            self._begin_victory_summary()
            return
        self._start_timeline_removal_animation()

    def _monster_escape_x(self, actor_index: int) -> int:
        elapsed = max(
            0,
            self.monster_escape_animation_frame
            - MONSTER_ESCAPE_START_DELAY_FRAME_COUNT,
        )
        return (
            self._monster_base_position(actor_index)[0] - elapsed * MONSTER_ESCAPE_SPEED
        )

    def _monster_attack_animation_frame_count(self) -> int:
        return (
            MONSTER_MISS_FRAME_COUNT
            if self.monster_attack_damage == 0
            else MONSTER_DAMAGE_FRAME_COUNT
        )

    def _monster_double_attack_pending(self) -> bool:
        return (
            getattr(self, "monster_action", None) is MonsterAction.ATTACK
            and MonsterSpecialAction.DOUBLE_ATTACK in self.timeline[0].special_actions
        )

    def _finish_monster_attack(self) -> None:
        target_index = self.monster_attack_target_index
        damage = self.monster_attack_damage
        if target_index is None or damage is None:
            raise RuntimeError("monster attack requires a target and result")
        double_attack_pending = self._monster_double_attack_pending()
        is_normal_attack = (
            getattr(self, "monster_counter_actor_index", None) is None
            and getattr(self, "monster_charge_presentation", None) is None
        )
        if not getattr(self, "monster_attack_damage_applied", False):
            member = self.party[target_index]
            was_sleeping_or_confused = isinstance(member, Member) and (
                member.sleeping or member.confused
            )
            self._apply_monster_attack_damage(target_index, damage)
            if (
                is_normal_attack
                and getattr(self, "monster_action", None) is MonsterAction.ATTACK
                and not was_sleeping_or_confused
            ):
                self._queue_party_counter(target_index)
            applied_effects = self._apply_additional_effects_to_member(
                target_index,
                getattr(self, "monster_attack_additional_effects", ()),
            )
            self.monster_attack_additional_effects = applied_effects
            if is_normal_attack and AdditionalEffect.DEATH in applied_effects:
                self._show_instant_death_message(actor_is_enemy=True)
        self._apply_monster_drain_healing()
        popup = getattr(self, "battle_popup", None)
        # The defeat message uses the same screen edge as the attack popup.
        if (
            is_normal_attack
            and popup is not None
            and popup.visible
            and AdditionalEffect.DEATH in self.monster_attack_additional_effects
            and self._party_is_defeated()
        ):
            self.monster_attack_damage_applied = True
            return
        self.monster_previous_attack_popup = None
        if double_attack_pending:
            if self._party_is_defeated():
                if (
                    self.monster_attack_animation_frame
                    < self._monster_attack_animation_frame_count()
                ):
                    self.monster_attack_damage_applied = True
                    return
            elif (position := self._party_draw_position(target_index)) is not None:
                self.monster_previous_attack_popup = BattleMonsterAttackPopup(
                    target_index, damage, self.monster_attack_critical,
                    position, self.monster_attack_animation_frame,
                )
        self.monster_attack_target_index = None
        self.monster_attack_damage = None
        self.monster_attack_critical = False
        self.monster_attack_additional_effects = ()
        self.monster_attack_animation_frame = 0
        self.monster_attack_damage_applied = False
        self.monster_charge_presentation = None
        completion = (
            FormationAnimationCompletion.CONTINUE_MONSTER_ATTACK
            if double_attack_pending else FormationAnimationCompletion.START_TIMELINE
        )
        self.monster_action = None
        self.protected_party_index = None
        self.covering_party_index = None
        self._reveal_hidden_party_if_all_unavailable()
        if getattr(self, "monster_counter_actor_index", None) is not None:
            self.monster_counter_actor_index = None
            self.monster_counter_target_index = None
            self.monster_drain_presentation = None
            head = self.timeline[0]
            if isinstance(head, BattleCharacter) and self._member_is_dead(head.member):
                self.counter_defeated_turn_actor = True
            else:
                self._remove_defeated_party_from_timeline()
            if self._party_is_defeated():
                self.pending_monster_counters = []
                self._begin_defeat_message()
            else:
                self._complete_current_turn()
            return
        if self._member_is_dead(self.party[target_index]):
            self.defending_party_indexes.discard(target_index)
            getattr(self, "cover_target_by_party_index", {}).pop(
                target_index,
                None,
            )
            self._remove_defeated_party_from_timeline()
            if self._party_is_defeated():
                if getattr(self, "escape_requested", False):
                    self._begin_escape_animation()
                else:
                    self._begin_defeat_message()
                return
            if self._prune_surprise_pending_party(
                completion
            ) or self._begin_front_promotion_if_needed(completion):
                # The new rows already apply to targeting. They can animate during the second hit.
                if double_attack_pending and self.phase is BattlePhase.FORMATION:
                    self._continue_after_formation(completion)
                return
        elif self._party_is_defeated():
            self._begin_defeat_message()
            return
        self._continue_after_formation(completion)

    def _apply_party_drain(self, index: int, damage: int) -> None:
        member = self.party[index]
        amount = drain_healing_amount(damage=damage, hp=member.hp, max_hp=member.max_hp)
        if not amount:
            return
        member.apply_healing(amount)
        self._refresh_party_hp_text(index)
        position = self._party_draw_position(index)
        if position is not None:
            x, y = position
            self.healing_popups.append(BattleHealingPopup(x + 6, y + 16, amount))

    def _begin_monster_drain(
        self, actor: BattleMonster, damage: int, source_x: int, source_y: int,
    ) -> bool:
        """Start the drain presentation when there is HP to restore."""

        amount = drain_healing_amount(
            damage=damage, hp=actor.state.hp, max_hp=actor.state.max_hp
        )
        if amount == 0:
            return False
        actor_index = self._monster_index(actor)
        x, y = self._monster_base_position(actor_index)
        self.monster_drain_presentation = BattleMonsterDrainPresentation(
            actor_index, amount, source_x, source_y,
            x + actor.width // 2, y + actor.height - 24,
        )
        return True

    def _apply_monster_drain_healing(self) -> None:
        presentation = getattr(self, "monster_drain_presentation", None)
        if presentation is None or presentation.healing_applied:
            return
        presentation.healing_applied = True
        self.monsters[presentation.actor_index].state.apply_healing(
            presentation.amount
        )

    def _update_monster_drain(self) -> None:
        presentation = getattr(self, "monster_drain_presentation", None)
        if presentation is None:
            return
        presentation.elapsed_frame += 1
        if (
            presentation.elapsed_frame >= MONSTER_DRAIN_HEAL_DELAY
            and not presentation.popup_started
        ):
            presentation.popup_started = True
            self.healing_popups.append(BattleHealingPopup(
                presentation.end_x, presentation.end_y + 16, presentation.amount
            ))
        if presentation.elapsed_frame >= DRAIN_FLIGHT_FRAME_COUNT and presentation.healing_applied:
            self.monster_drain_presentation = None

    def _draw_monster_drain(self) -> None:
        presentation = getattr(self, "monster_drain_presentation", None)
        if presentation is None:
            return
        draw_drain_flight(
            (presentation.start_x, presentation.start_y),
            (presentation.end_x, presentation.end_y), presentation.elapsed_frame,
        )

    def _apply_monster_attack_damage(self, target_index: int, damage: int) -> int:
        """Apply a resolved enemy hit at its presentation's impact frame."""

        if damage <= 0:
            return 0
        member = self.party[target_index]
        previous_hp = member.hp
        if isinstance(member, Member):
            member.take_damage(damage)
        else:
            member.hp = max(0, member.hp - damage)
            if hasattr(member, "sleeping"):
                member.sleeping = 0
            if hasattr(member, "confused"):
                member.confused = 0
        self._refresh_party_hp_text(target_index)
        if self._member_focus_is_interrupted(member):
            getattr(self, "focused_target_by_party_index", {}).pop(
                target_index,
                None,
            )
        return previous_hp - member.hp

    def _apply_additional_effects_to_member(
        self,
        target_index: int,
        effects: tuple[AdditionalEffect, ...],
    ) -> tuple[AdditionalEffect, ...]:
        """Apply resolved enemy-hit effects after damage to a living member."""

        member = self.party[target_index]
        if self._member_is_dead(member):
            return ()
        applied: list[AdditionalEffect] = []
        for effect in effects:
            changed = False
            if effect is AdditionalEffect.DEATH:
                if isinstance(member, Member):
                    member.defeat()
                else:
                    member.hp = 0
                changed = True
            elif effect is AdditionalEffect.SLEEP:
                if isinstance(member, Member):
                    member.apply_sleep(random.randint(SLEEP_MIN_TURNS, SLEEP_MAX_TURNS))
                else:
                    member.sleeping = max(
                        getattr(member, "sleeping", 0),
                        random.randint(SLEEP_MIN_TURNS, SLEEP_MAX_TURNS),
                    )
                    member.confused = 0
                changed = True
            elif effect is AdditionalEffect.CONFUSE:
                if isinstance(member, Member):
                    changed = member.apply_confusion(
                        random.randint(CONFUSE_MIN_TURNS, CONFUSE_MAX_TURNS)
                    )
                else:
                    member.confused = max(
                        getattr(member, "confused", 0),
                        random.randint(CONFUSE_MIN_TURNS, CONFUSE_MAX_TURNS),
                    )
                    member.sleeping = 0
                    changed = True
            elif effect is AdditionalEffect.POISON:
                if isinstance(member, Member):
                    changed = member.apply_poison()
                elif not getattr(member, "poisoned", False):
                    member.poisoned = True
                    changed = True
            elif effect is AdditionalEffect.PARALIZE:
                if not getattr(member, "paralyzed", False):
                    member.paralyzed = True
                    changed = True
            elif effect is AdditionalEffect.STUN:
                if isinstance(member, Member):
                    changed = member.apply_stun()
                elif not getattr(member, "stunned", False):
                    member.stunned = True
                    changed = True
            elif effect is AdditionalEffect.DEFENSE_DOWN:
                if isinstance(member, Member):
                    changed = member.apply_defense_down(
                        random.randint(*debuff_turn_range(member.resistances))
                    )
            if changed:
                applied.append(effect)
        if applied:
            self._refresh_party_hp_text(target_index)
            if self._member_focus_is_interrupted(member):
                getattr(self, "focused_target_by_party_index", {}).pop(
                    target_index,
                    None,
                )
        return tuple(applied)

    def _party_is_defeated(self) -> bool:
        """Return whether no on-field member can recover the battle."""

        active = self._active_party_indexes()
        party = getattr(self, "party", None)
        if party is None:
            party = tuple(visual.member for visual in self.party_visuals)
        return not active or all(
            bool(getattr(party[index], "paralyzed", False)) for index in active
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
        hidden = getattr(self, "hidden_party_indexes", None)
        if hidden is not None:
            hidden.difference_update(
                index
                for index in range(len(self.party_visuals))
                if self._party_member_is_dead(index)
            )
        self._remove_timeline_actors(defeated)

    def _reveal_hidden_party_if_all_unavailable(self) -> bool:
        """Match DA2 by revealing everyone when no living member is targetable."""

        hidden = getattr(self, "hidden_party_indexes", None)
        if not hidden:
            return False
        active = self._active_party_indexes()
        party = getattr(self, "party", ())
        visuals = getattr(self, "party_visuals", ())

        def can_act(index: int) -> bool:
            member = visuals[index].member if visuals else party[index]
            return not (
                bool(getattr(member, "paralyzed", False))
                or bool(getattr(member, "sleeping", 0))
                or bool(getattr(member, "confused", 0))
            )

        if not active or any(
            index not in hidden and can_act(index) for index in active
        ):
            return False
        hidden.difference_update(active)
        return True

    def _refresh_all_party_hp_texts(self) -> None:
        if not hasattr(self, "party_status_texts"):
            return
        for index in range(len(self.party_status_texts)):
            self._refresh_party_hp_text(index)

    def _refresh_party_hp_text(self, index: int) -> None:
        window = self.party_status_windows[index]
        name_text, hp_text = self.party_status_texts[index]
        member = self.party[index]
        show_mp = getattr(self, "party_status_shows_mp", False)
        current = member.mp if show_mp else member.hp
        maximum = member.max_mp if show_mp else member.max_hp
        window.remove_text(hp_text)
        hp_text = window.add_text(
            ascii_to_fullwidth(f"{current:3d}/{maximum:3d}"),
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

        if (
            getattr(self, "phase", None) is BattlePhase.FADE_ESCAPE
            and getattr(self, "fade_escape_snapshot", None) is not None
        ):
            self._draw_fade_escape_mosaic()
            return
        if (
            getattr(self, "phase", None) is BattlePhase.RESULT_TRANSITION
            and self.result_transition_covered
        ):
            if self.result_overlay is None:
                raise RuntimeError("result transition requires a result overlay")
            self.result_overlay.draw()
            return
        if getattr(self, "phase", None) is BattlePhase.RESULT:
            if self.result_overlay is None:
                raise RuntimeError("result phase requires a result overlay")
            self.result_overlay.draw()
            return
        if self._critical_flash_visible():
            pyxel.cls(CRITICAL_FLASH_COLOR)
        else:
            self._draw_background()
        self._draw_party()
        self._draw_monsters()
        self._draw_party_attack_projectile()
        self._draw_aim_reticle()
        self._draw_party_attack_effect()
        self._draw_confused_monster_attack_effect()
        self._draw_spell_effects()
        self._draw_identify_effect()
        self._draw_sleeping_icons()
        self._draw_confusion_icons()
        self._draw_silence_icons()
        self._draw_poison_icons()
        self._draw_paralyze_icons()
        self._draw_stun_icons()
        self._draw_speed_modifier_icons()
        self._draw_magic_shield_icons()
        self._draw_target_affinity_indicators()
        self._draw_affinity_popups()
        self._draw_spell_damage_popups()
        self._draw_healing_popups()
        self._draw_party_attack_damage()
        self._draw_monster_attack_result()
        self._draw_monster_drain()
        self._draw_additional_effect_markers()
        self._draw_critical_markers()
        self._draw_timeline()
        self._draw_windows()
        self._draw_protection_icons()
        self._draw_target_cursor()
        self._draw_identify_result()
        auto_battle_screen = getattr(self, "auto_battle_screen", None)
        if auto_battle_screen is not None:
            auto_battle_screen.draw()
        if (
            getattr(self, "phase", None) is BattlePhase.FADE_ESCAPE
            and getattr(self, "fade_escape_snapshot", None) is None
        ):
            self._capture_fade_escape_snapshot()

    def _capture_fade_escape_snapshot(self) -> None:
        snapshot = pyxel.Image(SCREEN_WIDTH, SCREEN_HEIGHT)
        snapshot.blt(
            0,
            0,
            pyxel.screen,
            0,
            0,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
        )
        self.fade_escape_snapshot = snapshot

    def _draw_fade_escape_mosaic(self) -> None:
        transition = getattr(self, "fade_escape_transition", None)
        snapshot = getattr(self, "fade_escape_snapshot", None)
        if transition is None or snapshot is None:
            raise RuntimeError("FADE escape mosaic has incomplete state")
        pyxel.camera()
        block_size = transition.block_size
        for y in range(0, SCREEN_HEIGHT, block_size):
            for x in range(0, SCREEN_WIDTH, block_size):
                color = snapshot.pget(
                    min(x + block_size // 2, SCREEN_WIDTH - 1),
                    min(y + block_size // 2, SCREEN_HEIGHT - 1),
                )
                pyxel.rect(
                    x,
                    y,
                    min(block_size, SCREEN_WIDTH - x),
                    min(block_size, SCREEN_HEIGHT - y),
                    color,
                )

    def _draw_identify_effect(self) -> None:
        """Draw DA2's five-tile Identify pattern from bank 0 at Y=144."""

        if (
            getattr(self, "phase", None) is not BattlePhase.IDENTIFY_PRESENTATION
            or getattr(self, "identify_target_index", None) is None
        ):
            return
        target_index = self.identify_target_index
        monster = self.monsters[target_index]
        target_x, target_y = self._monster_draw_position(target_index)
        anchor_x = target_x + monster.width // 2
        anchor_y = target_y + monster.height // 2
        reference_frame = min(
            self.identify_effect_elapsed_frame * DA2_REFERENCE_FPS // FPS,
            DA2_IDENTIFY_EFFECT_FRAME_COUNT - 1,
        )
        pattern = ((reference_frame - 1) // 2) % 3
        if pattern == 0:
            pyxel.blt(
                anchor_x - IDENTIFY_EFFECT_TILE_SIZE // 2,
                anchor_y - IDENTIFY_EFFECT_TILE_SIZE // 2,
                0,
                IDENTIFY_EFFECT_CENTER_SOURCE_X,
                IDENTIFY_EFFECT_SOURCE_Y,
                IDENTIFY_EFFECT_TILE_SIZE,
                IDENTIFY_EFFECT_TILE_SIZE,
                IDENTIFY_EFFECT_TRANSPARENT_INDEX,
            )
            return

        inset = (2 - pattern) * 8
        left = anchor_x - 24 + inset
        right = anchor_x + 8 - inset
        top = anchor_y - 24 + inset
        bottom = anchor_y + 8 - inset
        for x, y, source_x in (
            (left, top, 0),
            (right, top, 16),
            (left, bottom, 32),
            (right, bottom, 48),
        ):
            pyxel.blt(
                x,
                y,
                0,
                source_x,
                IDENTIFY_EFFECT_SOURCE_Y,
                IDENTIFY_EFFECT_TILE_SIZE,
                IDENTIFY_EFFECT_TILE_SIZE,
                IDENTIFY_EFFECT_TRANSPARENT_INDEX,
            )

    def _draw_identify_result(self) -> None:
        """Draw the identified monster in DA2's battle detail window."""

        if (
            getattr(self, "phase", None) is not BattlePhase.IDENTIFY_RESULT
            or getattr(self, "identify_detail_window", None) is None
            or getattr(self, "identify_target_index", None) is None
        ):
            return
        window = self.identify_detail_window
        target = self.monsters[self.identify_target_index]
        definition = self.monster_definitions_by_key[target.key]
        _window_grid, image_x = identify_detail_layout(
            target,
            len(window.texts),
        )
        window.draw()
        pyxel.blt(
            window.content_x + image_x,
            window.content_y + IDENTIFY_DETAIL_IMAGE_Y,
            self.monster_images[target.key],
            0,
            0,
            definition.width,
            definition.height,
            TRANSPARENT_INDEX,
        )

    def _draw_background(self) -> None:
        presentation = getattr(self, "action_presentation", None)
        if presentation is not None and presentation.background_tint_color is not None:
            with self.palette_shifter.shifted(SPELL_EFFECT_FLASH_PALETTE):
                self._draw_background_image()
        else:
            self._draw_background_image()

    def _draw_background_image(self) -> None:
        pyxel.blt(
            0,
            0,
            self.background,
            0,
            0,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
        )

    def _critical_flash_visible(self) -> bool:
        """Return whether this frame uses DA2's critical background flash."""

        settings = getattr(self, "settings", None)
        if settings is not None and not settings.screen_flash_enabled:
            return False
        presentation = getattr(self, "attack_presentation", None)
        if (
            getattr(self, "phase", None) is BattlePhase.ATTACK_PRESENTATION
            and presentation is not None
            and any(
                strike.is_hit
                and strike.is_critical
                and strike.damage_applied
                and 0
                <= strike.hit_elapsed_frame(presentation.elapsed_frame)
                < CRITICAL_FLASH_FRAME_COUNT
                for strike in presentation.strikes
            )
        ):
            return True
        return (
            getattr(self, "phase", None) is BattlePhase.MONSTER_ACTION
            and getattr(self, "monster_attack_target_index", None) is not None
            and bool(getattr(self, "monster_attack_critical", False))
            and bool(getattr(self, "monster_attack_damage", 0))
            and 0
            <= getattr(self, "monster_attack_animation_frame", -1)
            < CRITICAL_FLASH_FRAME_COUNT
        )

    def _draw_critical_markers(self) -> None:
        """Draw DA2's SMASH marker when screen flashes are reduced."""

        settings = getattr(self, "settings", None)
        if settings is None or settings.screen_flash_enabled:
            return
        presentation = getattr(self, "attack_presentation", None)
        if (
            presentation is not None
            and presentation.is_iai
            and self.phase is BattlePhase.ATTACK_PRESENTATION
        ):
            for strike in presentation.visible_result_strikes():
                if not (strike.is_hit and strike.is_critical and not strike.is_weak):
                    continue
                index = strike.target_index
                monster = self.monsters[index]
                _target_x, target_y = self._monster_base_position(index)
                self._draw_critical_marker(
                    self._monster_draw_x(index)
                    + monster.width // 2
                    - CRITICAL_MARKER_WIDTH // 2,
                    target_y + 20,
                )
        elif self._party_attack_smash_marker_visible(presentation):
            if getattr(presentation, "target_side", "enemy") == "ally":
                position = self._party_draw_position(presentation.target_index)
                if position is not None:
                    self._draw_critical_marker(*position)
            else:
                monster = self.monsters[presentation.target_index]
                _target_x, target_y = self._monster_base_position(
                    presentation.target_index
                )
                self._draw_critical_marker(
                    self._monster_draw_x(presentation.target_index)
                    + monster.width // 2
                    - CRITICAL_MARKER_WIDTH // 2,
                    target_y + 20,
                )
        target_index = getattr(self, "monster_attack_target_index", None)
        animation_frame = getattr(self, "monster_attack_animation_frame", -1)
        previous = self._visible_previous_monster_attack_popup()
        if (
            previous is not None
            and previous.is_critical
            and previous.elapsed_frame + animation_frame < CRITICAL_MARKER_FRAME_COUNT
        ):
            self._draw_critical_marker(*previous.position)
        if (
            getattr(self, "phase", None) is BattlePhase.MONSTER_ACTION
            and target_index is not None
            and bool(getattr(self, "monster_attack_critical", False))
            and bool(getattr(self, "monster_attack_damage", 0))
            and 0 <= animation_frame < CRITICAL_MARKER_FRAME_COUNT
        ):
            position = self._party_draw_position(target_index)
            if position is not None:
                self._draw_critical_marker(*position)

    def _party_attack_smash_marker_visible(
        self,
        presentation: BattleAttackPresentation | None,
    ) -> bool:
        """Return whether SMASH currently occupies the result-marker slot."""

        settings = getattr(self, "settings", None)
        strike = (
            presentation.latest_result_strike() if presentation is not None else None
        )
        return bool(
            settings is not None
            and not settings.screen_flash_enabled
            and getattr(self, "phase", None) is BattlePhase.ATTACK_PRESENTATION
            and presentation is not None
            and strike is not None
            and strike.is_hit
            and strike.is_critical
            and not strike.is_weak
        )

    def _draw_additional_effect_markers(self) -> None:
        """Draw STUN or defense-down text over the affected monster."""

        presentation = getattr(self, "attack_presentation", None)
        if (
            presentation is not None
            and presentation.is_iai
            and self.phase is BattlePhase.ATTACK_PRESENTATION
        ):
            for result in presentation.visible_result_strikes():
                if not result.is_hit or result.is_weak:
                    continue
                if not self.settings.screen_flash_enabled and result.is_critical:
                    continue
                index = result.target_index
                monster = self.monsters[index]
                if not monster.is_alive:
                    continue
                effect = next(
                    (
                        candidate
                        for candidate in (
                            AdditionalEffect.STUN,
                            AdditionalEffect.DEFENSE_DOWN,
                        )
                        if candidate in result.additional_effects
                        and (
                            (
                                candidate is AdditionalEffect.STUN
                                and monster.state.stunned
                            )
                            or (
                                candidate is AdditionalEffect.DEFENSE_DOWN
                                and monster.state.defense_modifier < 0
                            )
                        )
                    ),
                    None,
                )
                if effect is None:
                    continue
                _target_x, target_y = self._monster_base_position(index)
                source_x, source_y = ADDITIONAL_EFFECT_MARKER_SOURCE[effect]
                pyxel.blt(
                    self._monster_draw_x(index)
                    + monster.width // 2
                    - CRITICAL_MARKER_WIDTH // 2,
                    target_y + 20,
                    0,
                    source_x,
                    source_y,
                    ADDITIONAL_EFFECT_MARKER_WIDTH,
                    ADDITIONAL_EFFECT_MARKER_HEIGHT,
                    TRANSPARENT_INDEX,
                )
            return
        strike = (
            presentation.latest_result_strike() if presentation is not None else None
        )
        if (
            getattr(self, "phase", None) is not BattlePhase.ATTACK_PRESENTATION
            or presentation is None
            or strike is None
            or not strike.is_hit
            or strike.is_weak
            or self._party_attack_smash_marker_visible(presentation)
        ):
            return
        if getattr(presentation, "target_side", "enemy") == "ally":
            member = self.party[presentation.target_index]
            if self._member_is_dead(member):
                return
            effect = next(
                (
                    candidate
                    for candidate in (
                        AdditionalEffect.STUN,
                        AdditionalEffect.DEFENSE_DOWN,
                    )
                    if candidate in strike.additional_effects
                ),
                None,
            )
            position = self._party_draw_position(presentation.target_index)
            if effect is None or position is None:
                return
            source_x, source_y = ADDITIONAL_EFFECT_MARKER_SOURCE[effect]
            pyxel.blt(
                position[0],
                position[1],
                0,
                source_x,
                source_y,
                ADDITIONAL_EFFECT_MARKER_WIDTH,
                ADDITIONAL_EFFECT_MARKER_HEIGHT,
                TRANSPARENT_INDEX,
            )
            return
        monster = self.monsters[presentation.target_index]
        if not monster.is_alive:
            return
        effect = next(
            (
                candidate
                for candidate in (
                    AdditionalEffect.STUN,
                    AdditionalEffect.DEFENSE_DOWN,
                )
                if candidate in strike.additional_effects
                and (
                    (candidate is AdditionalEffect.STUN and monster.state.stunned)
                    or (
                        candidate is AdditionalEffect.DEFENSE_DOWN
                        and monster.state.defense_modifier < 0
                    )
                )
            ),
            None,
        )
        if effect is None:
            return
        _target_x, target_y = self._monster_base_position(presentation.target_index)
        source_x, source_y = ADDITIONAL_EFFECT_MARKER_SOURCE[effect]
        pyxel.blt(
            self._monster_draw_x(presentation.target_index)
            + monster.width // 2
            - CRITICAL_MARKER_WIDTH // 2,
            target_y + 20,
            0,
            source_x,
            source_y,
            ADDITIONAL_EFFECT_MARKER_WIDTH,
            ADDITIONAL_EFFECT_MARKER_HEIGHT,
            TRANSPARENT_INDEX,
        )

    @staticmethod
    def _draw_critical_marker(x: int, y: int) -> None:
        pyxel.blt(
            x,
            y,
            0,
            CRITICAL_MARKER_SOURCE_X,
            CRITICAL_MARKER_SOURCE_Y,
            CRITICAL_MARKER_WIDTH,
            CRITICAL_MARKER_HEIGHT,
            TRANSPARENT_INDEX,
        )

    def _party_attack_pose(self, index: int) -> AttackPoseDefinition | None:
        presentation = getattr(self, "attack_presentation", None)
        if (
            self._party_member_is_dead(index)
            or self.phase is not BattlePhase.ATTACK_PRESENTATION
            or index != getattr(self, "action_party_index", None)
            or presentation is None
            or self._action_forward_jump_in_progress()
        ):
            return None
        if (
            getattr(presentation, "is_iai", False)
            and (
                (self.action_returning and self.action_offset_x > 0)
                or (
                    not presentation.return_started
                    and presentation.elapsed_frame >= presentation.motion_frame_count
                )
            )
        ):
            poses = presentation.strikes[-1].poses
            return poses[-1] if poses else None
        return presentation.pose

    def _draw_party(self) -> None:
        if self.phase is BattlePhase.KNOCKOUT_HANDOFF:
            self._draw_knockout_fighter()
            return
        for index, visual in enumerate(self.party_visuals):
            if index in getattr(self, "escaped_party_indexes", ()):
                continue
            is_hide_motion = (
                self.phase is BattlePhase.HIDE_PRESENTATION
                and index == self.active_party_index
            )
            if (
                index in getattr(self, "hidden_party_indexes", ())
                and not is_hide_motion
            ):
                continue
            position = self._party_draw_position(index)
            if position is None:
                continue
            x, y = position
            action_presentation = getattr(self, "action_presentation", None)
            if (
                self.phase is BattlePhase.ACTION_PRESENTATION
                and action_presentation is not None
                and (action_presentation.background_tint_color is not None or action_presentation.earthquake)
                and action_presentation.party_damage_motion_visible(index)
            ):
                shake_index = (
                    action_presentation.elapsed_frame * DA2_REFERENCE_FPS // FPS
                ) % len(MONSTER_DAMAGE_SHAKE_X)
                x += MONSTER_DAMAGE_SHAKE_X[shake_index]
            attack_presentation = getattr(self, "attack_presentation", None)
            friendly_strike = (
                attack_presentation.latest_result_strike()
                if (
                    self.phase is BattlePhase.ATTACK_PRESENTATION
                    and attack_presentation is not None
                    and getattr(attack_presentation, "target_side", "enemy") == "ally"
                    and index == attack_presentation.target_index
                )
                else None
            )
            if (
                friendly_strike is not None
                and friendly_strike.is_hit
                and friendly_strike.damage > 0
            ):
                shake_index = (
                    attack_presentation.elapsed_frame * DA2_REFERENCE_FPS // FPS
                ) % len(MONSTER_DAMAGE_SHAKE_X)
                x += MONSTER_DAMAGE_SHAKE_X[shake_index]
            if is_hide_motion:
                reference_frame = min(
                    self.hide_presentation_elapsed_frame * DA2_REFERENCE_FPS // FPS,
                    len(HIDE_REFERENCE_OFFSETS) - 1,
                )
                opacity = max(0.0, 1.0 - max(reference_frame - 1, 0) / 5)
                pyxel.dither(opacity)
                try:
                    if self._party_shadow_is_visible(FORMATION_SPRITE_STEP_X):
                        self._draw_party_shadow(x, y, PARTY_SPRITE_WIDTH)
                    y -= self._party_floating_offset(
                        index,
                        FORMATION_SPRITE_STEP_X,
                    )
                    self._draw_party_body(index, x, y, FORMATION_SPRITE_STEP_X, PARTY_SPRITE_WIDTH)
                finally:
                    pyxel.dither(1.0)
                continue
            if (
                self.phase is BattlePhase.MONSTER_ACTION
                and index == getattr(self, "monster_attack_target_index", None)
                and getattr(self, "monster_attack_damage", None)
                and not self._party_member_is_dead(index)
            ):
                shake_index = (
                    self.monster_attack_animation_frame * DA2_REFERENCE_FPS // FPS
                ) % len(MONSTER_DAMAGE_SHAKE_X)
                x += MONSTER_DAMAGE_SHAKE_X[shake_index]
            is_escaping = self._party_member_is_escaping(index)
            width = self._party_sprite_width(index, is_escaping=is_escaping)
            attack_pose = self._party_attack_pose(index)
            sprite_source_x = (
                attack_pose.character_pose * PARTY_SPRITE_WIDTH
                if attack_pose is not None
                else self._party_sprite_source_x(index)
            )
            if self._party_shadow_is_visible(sprite_source_x):
                self._draw_party_shadow(x, y, width)
            y -= self._party_floating_offset(index, sprite_source_x)
            focus_wait_y = y
            if self._party_floating_is_enabled(index, sprite_source_x):
                focus_wait_y -= FOCUS_WAIT_EFFECT_FLOATING_OFFSET_Y
            self._draw_focus_effect(index, x, focus_wait_y, foreground=False)
            if attack_pose is not None:
                self._draw_attack_composite(index, x, y, attack_pose)
                continue
            self._draw_party_body(index, x, y, sprite_source_x, width)
            if self.phase is not BattlePhase.ACTION_PRESENTATION:
                self._draw_focus_effect(index, x, y, foreground=True)
        self._draw_active_party_cursor()

    def _draw_party_body(self, index: int, x: int, y: int, source_x: int, width: int) -> None:
        visual = self.party_visuals[index]

        def draw_body() -> None:
            pyxel.blt(
                x, y, self.character_sprites, source_x, visual.battle_sprite * 32,
                width, 32, TRANSPARENT_INDEX,
            )

        phase = getattr(self, "phase", None)
        if phase is BattlePhase.ACTION_PRESENTATION:
            self._draw_spell_effect_target("ally", index, draw_body)
        elif phase in (BattlePhase.COMMAND, BattlePhase.GLOBAL_COMMAND) and index in getattr(
            self, "inner_steel_flashing_indexes", ()
        ):
            with self.palette_shifter.shifted(INNER_STEEL_PALETTE):
                draw_body()
        else:
            draw_body()

    def _draw_active_party_cursor(self) -> None:
        """Frame the acting member at its position before floating is applied."""

        if (
            not self._active_party_cursor_is_visible()
            or self.active_party_index in getattr(self, "hidden_party_indexes", ())
        ):
            return
        position = self._party_draw_position(self.active_party_index)
        if position is None:
            return
        x, y = position
        with self.palette_shifter.shifted(ACTIVE_PARTY_CURSOR_PALETTE):
            for (source_x, source_y, _, _), (offset_x, offset_y) in zip(
                AIM_RETICLE_CORNER_SOURCES,
                ACTIVE_PARTY_CURSOR_OFFSETS,
            ):
                pyxel.blt(
                    x + offset_x,
                    y + offset_y,
                    0,
                    source_x,
                    source_y,
                    AIM_RETICLE_CORNER_SIZE,
                    AIM_RETICLE_CORNER_SIZE,
                    TRANSPARENT_INDEX,
                )

    def _draw_focus_effect(
        self,
        index: int,
        x: int,
        y: int,
        *,
        foreground: bool,
    ) -> None:
        """Draw the activation in front, then the sustained aura behind the member."""

        if self.phase in (
            BattlePhase.VICTORY_SUMMARY,
            BattlePhase.RESULT_TRANSITION,
            BattlePhase.ESCAPE_MESSAGE,
            BattlePhase.ESCAPE,
        ):
            return
        if index not in getattr(self, "focused_target_by_party_index", {}):
            return
        activation_elapsed = getattr(self, "focus_presentation_elapsed_frame", 0)
        activation_frame_count = (
            FOCUS_ACTIVATION_EFFECT_PATTERN_COUNT
            * FOCUS_ACTIVATION_EFFECT_PATTERN_FRAME_COUNT
        )
        is_activating = (
            self.phase is BattlePhase.FOCUS_PRESENTATION
            and index == self.active_party_index
        )
        if (
            is_activating
            and activation_frame_count
            <= activation_elapsed
            < activation_frame_count + FOCUS_WAIT_EFFECT_DELAY_FRAME_COUNT
        ):
            return
        activation_visible = (
            is_activating and activation_elapsed < activation_frame_count
        )
        if foreground != activation_visible:
            return
        if activation_visible:
            pattern = activation_elapsed // FOCUS_ACTIVATION_EFFECT_PATTERN_FRAME_COUNT
            source_y = FOCUS_ACTIVATION_EFFECT_SOURCE_Y
            effect_width = FOCUS_EFFECT_WIDTH
        else:
            pattern = (
                getattr(self, "focus_wait_animation_frame", 0)
                // FOCUS_WAIT_EFFECT_PATTERN_FRAME_COUNT
            ) % FOCUS_WAIT_EFFECT_PATTERN_COUNT
            source_y = FOCUS_WAIT_EFFECT_SOURCE_Y
            effect_width = FOCUS_WAIT_EFFECT_WIDTH
        pyxel.blt(
            x + (PARTY_SPRITE_WIDTH - effect_width) // 2,
            y,
            0,
            pattern * effect_width,
            source_y,
            effect_width,
            FOCUS_EFFECT_HEIGHT,
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

        race = self.party_visuals[index].member.definition.race
        weapon_y_offset = pose.weapon_y_offset(race)

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
                y + weapon.position_y + weapon_y_offset,
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
        self._draw_party_body(index, x, y, pose.character_pose * 16, 16)
        for weapon in pose.weapons:
            if weapon.layer == "front":
                draw_weapon(weapon)

    def _draw_knockout_fighter(self) -> None:
        frame = self.knockout_handoff_frame
        x = self._party_sprite_x(0)
        if frame < KNOCKOUT_HANDOFF_HALF_FRAMES:
            source_x = self._party_sprite_source_x(0)
            opacity = 1.0 - frame / KNOCKOUT_HANDOFF_HALF_FRAMES
        else:
            elapsed = frame - KNOCKOUT_HANDOFF_HALF_FRAMES
            x = SCREEN_WIDTH - (SCREEN_WIDTH - x) * elapsed // KNOCKOUT_HANDOFF_HALF_FRAMES
            source_x = (elapsed // FORMATION_WALK_PATTERN_FRAME_COUNT % 2) * FORMATION_SPRITE_STEP_X
            opacity = 1.0
        y = PARTY_SPRITE_Y[0]
        width = self._party_sprite_width(0, is_escaping=False)
        pyxel.dither(opacity)
        try:
            if self._party_shadow_is_visible(source_x):
                self._draw_party_shadow(x, y, width)
            self._draw_party_body(
                0, x, y - self._party_floating_offset(0, source_x), source_x, width
            )
        finally:
            pyxel.dither(1.0)

    def _party_draw_position(self, index: int) -> tuple[int, int] | None:
        if getattr(self, "phase", None) is BattlePhase.KNOCKOUT_HANDOFF:
            return None
        if index in getattr(self, "escaped_party_indexes", ()):
            return None
        target_x = self._party_sprite_x(index)
        target_y = PARTY_SPRITE_Y[index]
        if self.phase is BattlePhase.HIDE_PRESENTATION and index == getattr(
            self, "active_party_index", None
        ):
            reference_frame = min(
                self.hide_presentation_elapsed_frame * DA2_REFERENCE_FPS // FPS,
                len(HIDE_REFERENCE_OFFSETS) - 1,
            )
            offset_x, offset_y = HIDE_REFERENCE_OFFSETS[reference_frame]
            return target_x + offset_x, target_y + offset_y
        if index in getattr(self, "hidden_party_indexes", ()):
            return None
        if (
            self.phase is BattlePhase.MONSTER_ACTION
            and index == getattr(self, "covering_party_index", None)
            and getattr(self, "protected_party_index", None) is not None
        ):
            protected_position = self._party_draw_position(self.protected_party_index)
            if protected_position is not None:
                protected_x, protected_y = protected_position
                return protected_x - COVER_POSITION_OFFSET_X, protected_y
        if self.phase is BattlePhase.VICTORY_SUMMARY and index in getattr(
            self, "victory_returning_party_indexes", ()
        ):
            return self._victory_return_x(index), target_y
        if self._party_member_is_escaping(index):
            return self._escape_party_x(index), target_y
        if index in getattr(self, "formation_actor_indexes", ()):
            start_x = self.formation_start_x_by_index[index]
            destination_x = self.formation_destination_x_by_index[index]
            x = start_x + (
                (destination_x - start_x)
                * self.formation_animation_frame
                // FORMATION_MOVE_FRAME_COUNT
            )
            return x, target_y
        if self.phase is not BattlePhase.ENTRANCE:
            if index == getattr(self, "action_party_index", None):
                target_x -= self.action_offset_x
                if not self.action_returning and getattr(
                    self, "action_forward_jump", False
                ):
                    target_y -= (
                        4
                        * ATTACK_FORWARD_JUMP_HEIGHT
                        * self.action_offset_x
                        * (ACTION_MOVE_DISTANCE - self.action_offset_x)
                        // (ACTION_MOVE_DISTANCE**2)
                    )
                elif self.action_returning and getattr(
                    self, "action_return_jump", False
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
            self.escape_start_x[index]
            + (
                self.escape_animation_frame
                - self.escape_start_frame_by_party_index[index]
            ) * ESCAPE_RUN_SPEED,
            ESCAPE_RUN_DESTINATION_X,
        )

    def _party_sprite_x(self, index: int) -> int:
        x = 156 + index * 4
        if not self._party_member_is_front_row(index):
            x += 16
        return x

    @staticmethod
    def _draw_party_shadow(x: int, y: int, sprite_width: int) -> None:
        """Draw a centered shadow below one visible party sprite."""

        shadow_x = x + (abs(sprite_width) - PARTY_SPRITE_WIDTH) // 2
        draw_character_shadow(pyxel, shadow_x, y + PARTY_SPRITE_WIDTH)

    @staticmethod
    def _party_shadow_is_visible(sprite_source_x: int) -> bool:
        """Hide the shadow only for the seventh and tenth collapsed poses."""

        return sprite_source_x not in (
            NEAR_DEATH_SPRITE_SOURCE_X,
            DEAD_SPRITE_SOURCE_X,
        )

    def _party_floating_is_enabled(self, index: int, sprite_source_x: int) -> bool:
        """Return whether the member is a fairy in a floating battle state."""

        if not self._party_member_is_fairy(index):
            return False
        return self._party_shadow_is_visible(sprite_source_x)

    def _party_member_is_fairy(self, index: int) -> bool:
        member = self.party_visuals[index].member
        definition = getattr(member, "definition", None)
        return getattr(definition, "race", None) is Race.FAIRY

    def _party_floating_offset(self, index: int, sprite_source_x: int) -> int:
        """Return the current offset for a fairy in a floating battle state."""

        if not self._party_floating_is_enabled(index, sprite_source_x):
            return 0
        definition = self.party_visuals[index].member.definition
        return floating_offset(
            pyxel.frame_count,
            phase_offset=floating_phase_offset(f"pc:{definition.key}"),
        )

    def _party_member_is_dead(self, index: int) -> bool:
        visuals = getattr(self, "party_visuals", ())
        member = getattr(visuals[index], "member", None) if visuals else None
        if member is None:
            party = getattr(self, "party", ())
            member = party[index] if index < len(party) else None
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
        width = (
            DEAD_SPRITE_WIDTH
            if self._party_member_is_dead(index)
            else PARTY_SPRITE_WIDTH
        )
        faces_backward = is_escaping or (
            getattr(self, "surprise_active", False)
            and index not in getattr(self, "surprise_turned_party_indexes", ())
        )
        return -width if faces_backward else width

    def _party_sprite_source_x(self, index: int) -> int:
        if self._party_member_is_dead(index):
            return DEAD_SPRITE_SOURCE_X
        if self.phase is BattlePhase.VICTORY_SUMMARY and index in getattr(
            self, "victory_returning_party_indexes", ()
        ):
            pattern = (
                self.victory_return_frame // FORMATION_WALK_PATTERN_FRAME_COUNT
            ) % 2
            return pattern * FORMATION_SPRITE_STEP_X
        if self.phase in (
            BattlePhase.VICTORY_SUMMARY,
            BattlePhase.RESULT_TRANSITION,
        ):
            if getattr(self.party_visuals[index].member, "paralyzed", False):
                return NEAR_DEATH_SPRITE_SOURCE_X
            return victory_sprite_source_x(self.victory_motion_frame)
        if self._party_member_is_escaping(index):
            elapsed = (
                self.escape_animation_frame
                - self.escape_start_frame_by_party_index[index]
            )
            pattern = (elapsed // ESCAPE_RUN_PATTERN_FRAME_COUNT) % 2
            return pattern * FORMATION_SPRITE_STEP_X
        if self.phase is BattlePhase.FOCUS_PRESENTATION and index == getattr(
            self, "active_party_index", None
        ):
            return DEFEND_SPRITE_SOURCE_X
        presentation = getattr(self, "action_presentation", None)
        if (
            self.phase is BattlePhase.ACTION_PRESENTATION
            and presentation is not None
            and presentation.party_damage_motion_visible(index)
        ):
            return MONSTER_DAMAGE_SPRITE_SOURCE_X
        if (
            self.phase is BattlePhase.MONSTER_ACTION
            and index == getattr(self, "monster_attack_target_index", None)
            and getattr(self, "monster_attack_damage", None)
        ):
            return MONSTER_DAMAGE_SPRITE_SOURCE_X
        if self.phase is BattlePhase.MONSTER_ACTION and index == getattr(
            self, "covering_party_index", None
        ):
            return DEFEND_SPRITE_SOURCE_X
        if index in getattr(self, "formation_actor_indexes", ()):
            pattern = (
                self.formation_animation_frame // FORMATION_WALK_PATTERN_FRAME_COUNT
            ) % 2
            return pattern * FORMATION_SPRITE_STEP_X
        attack_presentation = getattr(self, "attack_presentation", None)
        if (
            self.phase is BattlePhase.ATTACK_PRESENTATION
            and attack_presentation is not None
            and getattr(attack_presentation, "target_side", "enemy") == "ally"
            and index == attack_presentation.target_index
        ):
            strike = attack_presentation.latest_result_strike()
            if strike is not None and strike.is_hit and strike.damage > 0:
                return MONSTER_DAMAGE_SPRITE_SOURCE_X
        if index == getattr(self, "action_party_index", None) and not getattr(
            self, "action_stationary", False
        ):
            if (
                self.phase is BattlePhase.ATTACK_PRESENTATION
                and attack_presentation is not None
                and attack_presentation.aim_guard_pose_visible
            ):
                return DEFEND_SPRITE_SOURCE_X
            if getattr(self, "action_landing_guard_frames_remaining", 0):
                return DEFEND_SPRITE_SOURCE_X
            if not self.action_returning and getattr(
                self, "action_forward_jump", False
            ):
                return 0
            if self.action_returning and getattr(self, "action_return_jump", False):
                return 0
            if self.action_offset_x != ACTION_MOVE_DISTANCE or self.action_returning:
                pattern = (
                    self.action_motion_frame // FORMATION_WALK_PATTERN_FRAME_COUNT
                ) % 2
                return pattern * FORMATION_SPRITE_STEP_X
            return SPELL_CAST_SPRITE_SOURCE_X if self.action_uses_cast_pose else 0
        member = self.party_visuals[index].member
        if getattr(member, "sleeping", 0) or getattr(member, "paralyzed", False):
            return NEAR_DEATH_SPRITE_SOURCE_X
        if index in getattr(self, "defending_party_indexes", ()):
            return DEFEND_SPRITE_SOURCE_X
        if self._party_member_is_dying(index):
            return NEAR_DEATH_SPRITE_SOURCE_X
        return 0

    def _visible_previous_monster_attack_popup(self) -> BattleMonsterAttackPopup | None:
        previous = getattr(self, "monster_previous_attack_popup", None)
        if (
            previous is None
            or self.phase is not BattlePhase.MONSTER_ACTION
            or previous.target_index == self.monster_attack_target_index
        ):
            return None
        return previous

    def _draw_monster_attack_result(self) -> None:
        target_index = getattr(self, "monster_attack_target_index", None)
        damage = getattr(self, "monster_attack_damage", None)
        if (
            getattr(self, "phase", None) is not BattlePhase.MONSTER_ACTION
            or target_index is None
            or damage is None
        ):
            return
        popup_elapsed_frame = self.monster_attack_animation_frame
        previous = self._visible_previous_monster_attack_popup()
        if previous is not None:
            previous_frame = previous.elapsed_frame + popup_elapsed_frame
            previous_frame_count = (
                MONSTER_MISS_FRAME_COUNT if previous.damage == 0 else MONSTER_DAMAGE_FRAME_COUNT
            )
            if previous_frame < previous_frame_count:
                self._draw_monster_attack_popup(
                    previous.position, previous.damage, previous_frame,
                )
        position = self._party_draw_position(target_index)
        if position is not None:
            self._draw_monster_attack_popup(position, damage, popup_elapsed_frame)

    @staticmethod
    def _draw_monster_attack_popup(
        position: tuple[int, int], damage: int, popup_elapsed_frame: int,
    ) -> None:
        offsets = (
            DA2_MISS_VERTICAL_OFFSETS if damage == 0 else DA2_DAMAGE_VERTICAL_OFFSETS
        )
        reference_frame = min(
            popup_elapsed_frame * DA2_REFERENCE_FPS // FPS,
            len(offsets) - 1,
        )
        vertical_offset = offsets[reference_frame]
        if vertical_offset < 0:
            return
        target_x, target_y = position
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
                DAMAGE_NUMBER_SPRITE_X + int(digit) * DAMAGE_NUMBER_SPRITE_SIZE,
                DAMAGE_NUMBER_SPRITE_Y,
                DAMAGE_NUMBER_SPRITE_SIZE,
                DAMAGE_NUMBER_SPRITE_SIZE,
                TRANSPARENT_INDEX,
            )
            x += DAMAGE_NUMBER_SPRITE_SIZE

    def _draw_party_attack_effect(self) -> None:
        """Draw active weapon-impact rows for the independently timed strikes."""

        presentation = getattr(self, "attack_presentation", None)
        if (
            getattr(self, "phase", None) is not BattlePhase.ATTACK_PRESENTATION
            or presentation is None
        ):
            return
        for strike in presentation.strikes:
            anchor_x, anchor_y = self._spell_effect_anchor(
                getattr(presentation, "target_side", "enemy"),
                (
                    presentation.target_index
                    if strike.target_index is None
                    else strike.target_index
                ),
            )
            hit_elapsed_frame = strike.hit_elapsed_frame(presentation.elapsed_frame)
            if (
                not strike.is_hit
                or strike.effect_row is None
                or not 0 <= hit_elapsed_frame < ATTACK_HIT_FRAME_COUNT
            ):
                continue
            pattern = hit_elapsed_frame // ATTACK_HIT_PATTERN_FRAME_COUNT
            pyxel.blt(
                anchor_x - ATTACK_EFFECT_CELL_SIZE // 2,
                anchor_y - ATTACK_EFFECT_CELL_SIZE // 2 + 8,
                self.attack_effect_image,
                pattern * ATTACK_EFFECT_CELL_SIZE,
                strike.effect_row * ATTACK_EFFECT_CELL_SIZE,
                (
                    -ATTACK_EFFECT_CELL_SIZE
                    if strike.effect_flip_x
                    else ATTACK_EFFECT_CELL_SIZE
                ),
                ATTACK_EFFECT_CELL_SIZE,
                TRANSPARENT_INDEX,
            )

    def _draw_party_attack_projectile(self) -> None:
        """Draw a kunai or shuriken travelling from its wielder to the target."""

        presentation = getattr(self, "attack_presentation", None)
        actor_index = getattr(self, "action_party_index", None)
        if (
            getattr(self, "phase", None) is not BattlePhase.ATTACK_PRESENTATION
            or presentation is None
            or actor_index is None
        ):
            return
        actor_position = self._party_draw_position(actor_index)
        if actor_position is None:
            return
        target_x, target_y = self._spell_effect_anchor(
            presentation.target_side,
            presentation.target_index,
        )
        for strike in presentation.strikes:
            sprite = strike.projectile_at(presentation.elapsed_frame)
            start_frame = strike.projectile_start_frame
            if sprite is None or start_frame is None:
                continue
            first_sprite = strike.projectile_sprites[0]
            start_x = actor_position[0] + first_sprite.position_x
            start_y = actor_position[1] + first_sprite.position_y
            end_x = target_x - ATTACK_WEAPON_SPRITE_SIZE // 2
            end_y = target_y - ATTACK_WEAPON_SPRITE_SIZE // 2
            step = presentation.elapsed_frame - start_frame
            x, y = throwing_projectile_position(
                (start_x, start_y),
                (end_x, end_y),
                step,
            )
            pyxel.blt(
                x,
                y,
                0,
                sprite.image * ATTACK_WEAPON_SPRITE_SIZE,
                ATTACK_WEAPON_SPRITE_Y,
                (
                    -ATTACK_WEAPON_SPRITE_SIZE
                    if sprite.flip_x
                    else ATTACK_WEAPON_SPRITE_SIZE
                ),
                (
                    -ATTACK_WEAPON_SPRITE_SIZE
                    if sprite.flip_y
                    else ATTACK_WEAPON_SPRITE_SIZE
                ),
                TRANSPARENT_INDEX,
            )

    def _draw_confused_monster_attack_effect(self) -> None:
        """Draw the rod/wand impact when a confused monster attacks another."""

        presentation = getattr(self, "action_presentation", None)
        if (
            getattr(self, "phase", None) is not BattlePhase.ACTION_PRESENTATION
            or presentation is None
        ):
            return
        effect_elapsed_frame = (
            presentation.elapsed_frame - presentation.result_start_frame
        )
        if not 0 <= effect_elapsed_frame < ATTACK_HIT_FRAME_COUNT:
            return
        pattern = effect_elapsed_frame // ATTACK_HIT_PATTERN_FRAME_COUNT
        for result in presentation.confused_attack_results:
            if not result.is_hit or result.effect_row is None:
                continue
            anchor_x, anchor_y = self._spell_effect_anchor(
                result.target_side,
                result.target_index,
            )
            pyxel.blt(
                anchor_x - ATTACK_EFFECT_CELL_SIZE // 2,
                anchor_y - ATTACK_EFFECT_CELL_SIZE // 2 + 8,
                self.attack_effect_image,
                pattern * ATTACK_EFFECT_CELL_SIZE,
                result.effect_row * ATTACK_EFFECT_CELL_SIZE,
                ATTACK_EFFECT_CELL_SIZE,
                ATTACK_EFFECT_CELL_SIZE,
                TRANSPARENT_INDEX,
            )

    def _draw_aim_reticle(self) -> None:
        """Draw the four converging corners and timed center marker for Aim."""

        presentation = getattr(self, "attack_presentation", None)
        if (
            getattr(self, "phase", None) is not BattlePhase.ATTACK_PRESENTATION
            or presentation is None
            or presentation.aim_reticle_distance is None
        ):
            return
        center_x, center_y = self._spell_effect_anchor(
            getattr(presentation, "target_side", "enemy"),
            presentation.target_index,
        )
        distance = presentation.aim_reticle_distance
        for source_x, source_y, direction_x, direction_y in AIM_RETICLE_CORNER_SOURCES:
            pyxel.blt(
                center_x + direction_x * distance - AIM_RETICLE_CORNER_SIZE // 2,
                center_y + direction_y * distance - AIM_RETICLE_CORNER_SIZE // 2,
                0,
                source_x,
                source_y,
                AIM_RETICLE_CORNER_SIZE,
                AIM_RETICLE_CORNER_SIZE,
                TRANSPARENT_INDEX,
            )
        if not presentation.aim_reticle_center_visible:
            return
        source_x, source_y = AIM_RETICLE_CENTER_SOURCE
        pyxel.blt(
            center_x - AIM_RETICLE_CENTER_SIZE // 2,
            center_y - AIM_RETICLE_CENTER_SIZE // 2,
            0,
            source_x,
            source_y,
            AIM_RETICLE_CENTER_SIZE,
            AIM_RETICLE_CENTER_SIZE,
            TRANSPARENT_INDEX,
        )

    def _draw_party_attack_damage(self) -> None:
        """Draw each resolved damage or miss result over the attack target."""

        presentation = getattr(self, "attack_presentation", None)
        if (
            getattr(self, "phase", None) is not BattlePhase.ATTACK_PRESENTATION
            or presentation is None
        ):
            return
        for strike in presentation.strikes:
            target_index = (
                presentation.target_index
                if strike.target_index is None
                else strike.target_index
            )
            if getattr(presentation, "target_side", "enemy") == "ally":
                position = self._party_draw_position(target_index)
                if position is None:
                    continue
                target_x, target_y = position
                anchor_x = target_x + 14
                result_y = target_y + 16
            else:
                monster = self.monsters[target_index]
                _target_x, target_y = self._monster_base_position(target_index)
                anchor_x = self._monster_draw_x(target_index) + monster.width // 2
                result_y = target_y + monster.height - 8
            if not strike.damage_applied:
                continue
            offsets = (
                DA2_DAMAGE_VERTICAL_OFFSETS
                if strike.is_hit
                else DA2_MISS_VERTICAL_OFFSETS
            )
            frame_count = (
                ATTACK_DAMAGE_FRAME_COUNT if strike.is_hit else MONSTER_MISS_FRAME_COUNT
            )
            popup_elapsed_frame = strike.damage_popup_elapsed_frame(
                presentation.elapsed_frame
            )
            if not 0 <= popup_elapsed_frame < frame_count:
                continue
            reference_frame = min(
                popup_elapsed_frame * DA2_REFERENCE_FPS // FPS,
                len(offsets) - 1,
            )
            vertical_offset = offsets[reference_frame]
            if vertical_offset < 0:
                continue
            y = result_y - vertical_offset
            if not strike.is_hit:
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
                continue
            digits = str(strike.damage)
            x = anchor_x - len(digits) * DAMAGE_NUMBER_SPRITE_SIZE // 2
            for digit in digits:
                pyxel.blt(
                    x,
                    y,
                    0,
                    DAMAGE_NUMBER_SPRITE_X + int(digit) * DAMAGE_NUMBER_SPRITE_SIZE,
                    DAMAGE_NUMBER_SPRITE_Y,
                    DAMAGE_NUMBER_SPRITE_SIZE,
                    DAMAGE_NUMBER_SPRITE_SIZE,
                    TRANSPARENT_INDEX,
                )
                x += DAMAGE_NUMBER_SPRITE_SIZE

    def _draw_monsters(self) -> None:
        action_presentation = getattr(self, "action_presentation", None)
        wave_strength = (
            action_presentation.background_tint_progress
            if self.phase is BattlePhase.ACTION_PRESENTATION
            and action_presentation is not None
            and action_presentation.wave_enemy_sprites else 0.0
        )
        for index, monster in enumerate(self.monsters):
            is_dying = (
                self.phase is BattlePhase.MONSTER_DEATH
                and index in self.dying_monster_indexes
            )
            attack_presentation = getattr(self, "attack_presentation", None)
            is_attack_target = (
                self.phase is BattlePhase.ATTACK_PRESENTATION
                and attack_presentation is not None
                and getattr(attack_presentation, "target_side", "enemy") == "enemy"
                and (
                    index == attack_presentation.target_index
                    or any(
                        strike.target_index == index
                        for strike in attack_presentation.strikes
                    )
                )
            )
            is_spell_damage_target = (
                self.phase is BattlePhase.ACTION_PRESENTATION
                and action_presentation is not None
                and any(
                    result.target_index == index
                    for result in action_presentation.damage_results
                )
            )
            is_escaping = self.phase is BattlePhase.MONSTER_ACTION and index == getattr(
                self, "monster_escape_actor_index", None
            )
            if (
                not monster.is_alive
                and not is_dying
                and not is_attack_target
                and not is_spell_damage_target
                and not is_escaping
            ):
                continue
            if (
                index == self.blinking_monster_index
                and self.monster_blink_frames_remaining
                and self.monster_blink_frames_remaining % MONSTER_BLINK_PERIOD
                >= MONSTER_BLINK_VISIBLE_FRAMES
            ):
                continue
            x, y = self._monster_draw_position(index)
            if self.phase is BattlePhase.ACTION_PRESENTATION and action_presentation is not None:
                opacity = action_presentation.monster_revival_opacity(index)
                if opacity == 0:
                    continue
                if opacity < 1:
                    pyxel.dither(opacity)
                    try:
                        self._draw_monster_shadow(monster, x, y)
                        self._draw_monster_image(monster, x, y)
                    finally:
                        pyxel.dither(1.0)
                    continue
            if not is_dying or getattr(self, "monster_death_delay_frames_remaining", 0):
                self._draw_monster_shadow(monster, x, y)
                if self.phase is BattlePhase.ACTION_PRESENTATION:
                    if is_spell_damage_target and wave_strength:
                        self._draw_monster_image(
                            monster, x, y, wave_strength=wave_strength,
                            wave_frame=action_presentation.elapsed_frame,
                        )
                    else:
                        self._draw_spell_effect_target(
                            "enemy", index, lambda: self._draw_monster_image(monster, x, y),
                        )
                    self._draw_identified_monster_hp(index, monster, x, y)
                    continue
                is_unselectable_rear_target = (
                    self.phase is BattlePhase.TARGET
                    and not monster.is_front_row
                    and index not in self.selectable_target_indexes
                )
                if not is_unselectable_rear_target:
                    self._draw_monster_image(
                        monster,
                        x,
                        y,
                        flip_x=is_escaping,
                    )
                    self._draw_identified_monster_hp(index, monster, x, y)
                    continue
                palette = (
                    UNSELECTABLE_TARGET_PALETTE
                    if self.palette_shifter.has_variant(UNSELECTABLE_TARGET_PALETTE)
                    else MONOCHROME_PALETTE
                )
                with self.palette_shifter.shifted(palette):
                    self._draw_monster_image(monster, x, y)
                self._draw_identified_monster_hp(index, monster, x, y)
                continue
            animation = self.monster_death_animation
            if animation is None:
                raise RuntimeError("dying monster requires an animation")
            pyxel.dither(animation.opacity)
            try:
                self._draw_monster_shadow(monster, x, y)
                with self.palette_shifter.shifted(MONSTER_DEATH_PALETTE):
                    self._draw_monster_image(monster, x, y)
            finally:
                pyxel.dither(1.0)

    def _draw_identified_monster_hp(
        self,
        index: int,
        monster: BattleMonster,
        x: int,
        y: int,
    ) -> None:
        """Keep DA2's current-HP label below a monster identified this battle."""

        if index not in getattr(self, "identified_monster_indexes", ()):
            return
        baseline_y = y + monster.height + IDENTIFIED_MONSTER_HP_OFFSET_Y
        self._draw_small_text_with_edge(
            x + IDENTIFIED_MONSTER_HP_LABEL_OFFSET_X,
            baseline_y,
            "HP",
            DEFAULT_TEXT_COLOR,
        )
        self._draw_small_text_with_edge(
            x + IDENTIFIED_MONSTER_HP_VALUE_OFFSET_X,
            baseline_y,
            str(monster.state.hp),
            DEFAULT_TEXT_COLOR,
        )

    @staticmethod
    def _draw_small_text_with_edge(
        x: int,
        y: int,
        text: str,
        color: int,
    ) -> None:
        """Draw legible built-in-font text with DA2's one-pixel outline."""

        for offset_y in (-1, 0, 1):
            for offset_x in (-1, 0, 1):
                if offset_x or offset_y:
                    pyxel.text(
                        x + offset_x,
                        y + offset_y,
                        text,
                        IDENTIFIED_MONSTER_HP_EDGE_COLOR,
                    )
        pyxel.text(x, y, text, color)

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
                and effect.start_frame <= presentation.elapsed_frame
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
            if effect.start_frame <= presentation.elapsed_frame:
                self.spell_effect_renderer.draw_effect(effect.player)

    def _draw_sleeping_icons(self) -> None:
        """Draw DA2's four-pattern sleep marker for every sleeping combatant."""

        pattern = (
            pyxel.frame_count // SLEEP_ICON_PATTERN_FRAME_COUNT
        ) % SLEEP_ICON_PATTERN_COUNT
        source_x = SLEEP_ICON_SOURCE_X + pattern * SLEEP_ICON_SIZE
        for index, visual in enumerate(getattr(self, "party_visuals", ())):
            if not getattr(visual.member, "sleeping", 0):
                continue
            position = self._party_condition_icon_position(index, "sleeping")
            if position is None:
                continue
            x, y = position
            pyxel.blt(
                x,
                y,
                0,
                source_x,
                SLEEP_ICON_SOURCE_Y,
                SLEEP_ICON_SIZE,
                SLEEP_ICON_SIZE,
                TRANSPARENT_INDEX,
            )
        for index, monster in enumerate(getattr(self, "monsters", ())):
            if not monster.is_alive or not monster.state.sleeping:
                continue
            x, y = self._monster_condition_icon_position(index, "sleeping")
            pyxel.blt(
                x,
                y,
                0,
                source_x,
                SLEEP_ICON_SOURCE_Y,
                SLEEP_ICON_SIZE,
                SLEEP_ICON_SIZE,
                TRANSPARENT_INDEX,
            )

    def _draw_confusion_icons(self) -> None:
        """Draw ZERO's four-pattern confusion icon for every combatant."""

        pattern = (
            pyxel.frame_count // CONFUSE_ICON_PATTERN_FRAME_COUNT
        ) % CONFUSE_ICON_PATTERN_COUNT
        source_x = CONFUSE_ICON_SOURCE_X + pattern * CONFUSE_ICON_SIZE

        for index, visual in enumerate(getattr(self, "party_visuals", ())):
            if not getattr(visual.member, "confused", 0):
                continue
            position = self._party_condition_icon_position(index, "confused")
            if position is None:
                continue
            x, y = position
            pyxel.blt(
                x,
                y,
                0,
                source_x,
                CONFUSE_ICON_SOURCE_Y,
                CONFUSE_ICON_SIZE,
                CONFUSE_ICON_SIZE,
                TRANSPARENT_INDEX,
            )
        for index, monster in enumerate(getattr(self, "monsters", ())):
            if not monster.is_alive or not monster.state.confused:
                continue
            x, y = self._monster_condition_icon_position(index, "confused")
            pyxel.blt(
                x,
                y,
                0,
                source_x,
                CONFUSE_ICON_SOURCE_Y,
                CONFUSE_ICON_SIZE,
                CONFUSE_ICON_SIZE,
                TRANSPARENT_INDEX,
            )

    def _draw_speed_modifier_icons(self) -> None:
        """Draw DA2's animated defense and speed modifier markers."""

        for index, visual in enumerate(getattr(self, "party_visuals", ())):
            member = visual.member
            modifier = getattr(member, "speed_modifier", 0)
            defense_down = getattr(member, "protection_level", 0) < 0
            if not getattr(member, "is_alive", True) or (
                modifier == 0 and not defense_down
            ):
                continue
            position = self._party_draw_position(index)
            if position is None:
                continue
            x, y = position
            if defense_down:
                defense_pattern = (
                    pyxel.frame_count // DEFENSE_DOWN_ICON_PATTERN_FRAME_COUNT
                ) % PROTECTION_ICON_PATTERN_COUNT
                pyxel.blt(
                    x + 22,
                    y + 24,
                    0,
                    PROTECTION_ICON_SOURCE_X + defense_pattern * PROTECTION_ICON_SIZE,
                    DEFENSE_DOWN_ICON_SOURCE_Y,
                    PROTECTION_ICON_SIZE,
                    PROTECTION_ICON_SIZE,
                    TRANSPARENT_INDEX,
                )
            if modifier == 0:
                continue
            frame_count = (
                SLOW_ICON_PATTERN_FRAME_COUNT
                if modifier < 0
                else HASTE_ICON_PATTERN_FRAME_COUNTS[modifier - 1]
            )
            pattern = (pyxel.frame_count // frame_count) % SPEED_ICON_PATTERN_COUNT
            source_y = (
                SPEED_ICON_NEGATIVE_SOURCE_Y
                if modifier < 0
                else SPEED_ICON_POSITIVE_SOURCE_Y
            )
            pyxel.blt(
                x + 22,
                y + (15 if defense_down else 24),
                0,
                SPEED_ICON_SOURCE_X + pattern * SPEED_ICON_SIZE,
                source_y,
                SPEED_ICON_SIZE,
                SPEED_ICON_SIZE,
                SPEED_ICON_TRANSPARENT_INDEX,
            )
        for index, monster in enumerate(getattr(self, "monsters", ())):
            modifier = monster.state.speed_modifier
            defense_modifier = monster.state.defense_modifier
            if not monster.is_alive or (modifier == 0 and defense_modifier == 0):
                continue
            if self._monster_draw_position(index) != self._monster_base_position(index):
                continue
            if defense_modifier:
                x, y = self._monster_condition_icon_position(index, "defense_modifier")
                defense_interval = (
                    DEFENSE_DOWN_ICON_PATTERN_FRAME_COUNT
                    if defense_modifier < 0
                    else PROTECTION_ICON_PATTERN_FRAME_COUNTS[defense_modifier - 1]
                )
                defense_pattern = (
                    pyxel.frame_count // defense_interval
                ) % PROTECTION_ICON_PATTERN_COUNT
                pyxel.blt(
                    x,
                    y,
                    0,
                    PROTECTION_ICON_SOURCE_X + defense_pattern * PROTECTION_ICON_SIZE,
                    (
                        DEFENSE_DOWN_ICON_SOURCE_Y
                        if defense_modifier < 0
                        else PROTECTION_ICON_SOURCE_Y
                    ),
                    PROTECTION_ICON_SIZE,
                    PROTECTION_ICON_SIZE,
                    TRANSPARENT_INDEX,
                )
            if modifier == 0:
                continue
            x, y = self._monster_condition_icon_position(index, "speed_modifier")
            frame_count = (
                SLOW_ICON_PATTERN_FRAME_COUNT
                if modifier < 0
                else HASTE_ICON_PATTERN_FRAME_COUNTS[modifier - 1]
            )
            pattern = (pyxel.frame_count // frame_count) % SPEED_ICON_PATTERN_COUNT
            source_y = (
                SPEED_ICON_NEGATIVE_SOURCE_Y
                if modifier < 0
                else SPEED_ICON_POSITIVE_SOURCE_Y
            )
            pyxel.blt(
                x,
                y,
                0,
                SPEED_ICON_SOURCE_X + pattern * SPEED_ICON_SIZE,
                source_y,
                SPEED_ICON_SIZE,
                SPEED_ICON_SIZE,
                SPEED_ICON_TRANSPARENT_INDEX,
            )

    def _draw_silence_icons(self) -> None:
        """Draw DA2's silence marker beside silenced monsters."""

        for index, visual in enumerate(getattr(self, "party_visuals", ())):
            if not getattr(visual.member, "silenced", 0):
                continue
            position = self._party_condition_icon_position(index, "silenced")
            if position is not None:
                x, y = position
                pyxel.blt(
                    x,
                    y,
                    0,
                    SILENCE_ICON_SOURCE_X,
                    SILENCE_ICON_SOURCE_Y,
                    SILENCE_ICON_SIZE,
                    SILENCE_ICON_SIZE,
                    TRANSPARENT_INDEX,
                )
        for index, monster in enumerate(getattr(self, "monsters", ())):
            if not monster.is_alive or not monster.state.silenced:
                continue
            x, y = self._monster_condition_icon_position(index, "silenced")
            pyxel.blt(
                x,
                y,
                0,
                SILENCE_ICON_SOURCE_X,
                SILENCE_ICON_SOURCE_Y,
                SILENCE_ICON_SIZE,
                SILENCE_ICON_SIZE,
                TRANSPARENT_INDEX,
            )

    def _draw_poison_icons(self) -> None:
        """Draw the animated poison icon beside poisoned combatants."""

        party_positions: list[tuple[int, int]] = []
        for index, visual in enumerate(getattr(self, "party_visuals", ())):
            if not getattr(visual.member, "poisoned", False):
                continue
            position = self._party_condition_icon_position(index, "poisoned")
            if position is not None:
                party_positions.append(position)

        poisoned = tuple(
            (index, monster)
            for index, monster in enumerate(getattr(self, "monsters", ()))
            if monster.is_alive and monster.state.poisoned
        )
        if not party_positions and not poisoned:
            return
        pattern = (pyxel.frame_count // POISON_ICON_PATTERN_FRAME_COUNT) % len(
            POISON_ICON_DITHER_RATES
        )
        dither_rate = POISON_ICON_DITHER_RATES[pattern]
        if dither_rate <= 0:
            return
        pyxel.dither(dither_rate)
        try:
            for x, y in party_positions:
                pyxel.blt(
                    x,
                    y,
                    0,
                    POISON_ICON_SOURCE_X,
                    POISON_ICON_SOURCE_Y,
                    POISON_ICON_SIZE,
                    POISON_ICON_SIZE,
                    TRANSPARENT_INDEX,
                )
            for index, monster in poisoned:
                x, y = self._monster_condition_icon_position(index, "poisoned")
                pyxel.blt(
                    x,
                    y,
                    0,
                    POISON_ICON_SOURCE_X,
                    POISON_ICON_SOURCE_Y,
                    POISON_ICON_SIZE,
                    POISON_ICON_SIZE,
                    TRANSPARENT_INDEX,
                )
        finally:
            pyxel.dither(1.0)

    def _draw_paralyze_icons(self) -> None:
        """Draw the bank-zero paralysis icon beside paralyzed party members."""

        for index, visual in enumerate(getattr(self, "party_visuals", ())):
            if not getattr(visual.member, "paralyzed", False):
                continue
            position = self._party_condition_icon_position(index, "paralyzed")
            if position is None:
                continue
            x, y = position
            pyxel.blt(
                x,
                y,
                0,
                PARALYZE_ICON_SOURCE_X,
                PARALYZE_ICON_SOURCE_Y,
                PARALYZE_ICON_SIZE,
                PARALYZE_ICON_SIZE,
                TRANSPARENT_INDEX,
            )

    def _draw_stun_icons(self) -> None:
        """Draw the authored persistent stun icon beside stunned combatants."""

        for index, visual in enumerate(getattr(self, "party_visuals", ())):
            if not getattr(visual.member, "stunned", False):
                continue
            position = self._party_condition_icon_position(index, "stunned")
            if position is None:
                continue
            x, y = position
            pyxel.blt(
                x,
                y,
                0,
                STUN_ICON_SOURCE_X,
                STUN_ICON_SOURCE_Y,
                STUN_ICON_SIZE,
                STUN_ICON_SIZE,
                TRANSPARENT_INDEX,
            )

        for index, monster in enumerate(getattr(self, "monsters", ())):
            if not monster.is_alive or not monster.state.stunned:
                continue
            x, y = self._monster_condition_icon_position(index, "stunned")
            pyxel.blt(
                x,
                y,
                0,
                STUN_ICON_SOURCE_X,
                STUN_ICON_SOURCE_Y,
                STUN_ICON_SIZE,
                STUN_ICON_SIZE,
                TRANSPARENT_INDEX,
            )

    def _draw_magic_shield_icons(self) -> None:
        """Show the active elemental barrier in the combatant's condition row."""

        pattern = (
            pyxel.frame_count // MAGIC_SHIELD_ICON_PATTERN_FRAME_COUNT
        ) % MAGIC_SHIELD_ICON_PATTERN_COUNT
        positions = []
        for index, visual in enumerate(getattr(self, "party_visuals", ())):
            if getattr(visual.member, "magic_shield", False):
                position = self._party_condition_icon_position(index, "magic_shield")
                if position is not None:
                    positions.append(position)
        for index, monster in enumerate(getattr(self, "monsters", ())):
            if monster.is_alive and getattr(monster.state, "magic_shield", False):
                positions.append(self._monster_condition_icon_position(index, "magic_shield"))
        for x, y in positions:
            pyxel.blt(
                x, y, 0,
                MAGIC_SHIELD_ICON_SOURCE_X + pattern * SLEEP_ICON_SIZE,
                MAGIC_SHIELD_ICON_SOURCE_Y,
                SLEEP_ICON_SIZE, SLEEP_ICON_SIZE, TRANSPARENT_INDEX,
            )

    def _monster_condition_icon_position(
        self,
        index: int,
        condition: str,
    ) -> tuple[int, int]:
        """Place an active monster marker in the shared row at its image top."""

        monster = self.monsters[index]
        active_fields = tuple(
            field for field in MONSTER_CONDITION_ICON_FIELDS
            if getattr(monster.state, field, 0)
        )
        # Count blinking poison even while invisible so the other icons stay put.
        row_width = len(active_fields) * SLEEP_ICON_SIZE
        offset_x = min(
            MONSTER_CONDITION_ICON_OFFSET_X, max(0, monster.width - row_width)
        )
        _base_x, y = self._monster_base_position(index)
        return (
            self._monster_draw_x(index)
            + offset_x
            + active_fields.index(condition) * SLEEP_ICON_SIZE,
            y,
        )

    def _party_condition_icon_position(
        self,
        index: int,
        condition: str,
    ) -> tuple[int, int] | None:
        """Place active party condition icons in one compact upper-right row."""

        visual = self.party_visuals[index]
        member = visual.member
        if not getattr(member, "is_alive", True):
            return None
        position = self._party_draw_position(index)
        if position is None:
            return None
        preceding_count = sum(
            bool(getattr(member, field, False))
            for field in PARTY_CONDITION_ICON_FIELDS[
                : PARTY_CONDITION_ICON_FIELDS.index(condition)
            ]
        )
        x, y = position
        return (
            x + PARTY_CONDITION_ICON_OFFSET_X + preceding_count * SLEEP_ICON_SIZE,
            y,
        )

    def _draw_protection_icons(self) -> None:
        """Animate each defense stage immediately left of its party name."""

        phase = getattr(self, "phase", None)
        if phase in (
            BattlePhase.VICTORY_SUMMARY,
            BattlePhase.RESULT_TRANSITION,
            BattlePhase.ESCAPE_MESSAGE,
            BattlePhase.ESCAPE,
        ):
            return
        if phase is BattlePhase.ENTRANCE and getattr(
            self, "entrance_animation_frame", 0
        ) < getattr(
            self,
            "party_entrance_complete_frame",
            PARTY_ENTRANCE_COMPLETE_FRAME,
        ):
            return

        hidden_indexes = set(getattr(self, "escaped_party_indexes", set()))
        hidden_indexes.update(getattr(self, "escape_start_frame_by_party_index", {}))

        for index, (member, window) in enumerate(
            zip(
                getattr(self, "party", ()),
                getattr(self, "party_status_windows", ()),
            )
        ):
            level = member.protection_level
            if index in hidden_indexes or level <= 0:
                continue
            interval = PROTECTION_ICON_PATTERN_FRAME_COUNTS[level - 1]
            pattern = (pyxel.frame_count // interval) % PROTECTION_ICON_PATTERN_COUNT
            pyxel.blt(
                window.pixel_x + PROTECTION_ICON_NAME_OFFSET_X,
                window.pixel_y,
                0,
                PROTECTION_ICON_SOURCE_X + pattern * PROTECTION_ICON_SIZE,
                PROTECTION_ICON_SOURCE_Y,
                PROTECTION_ICON_SIZE,
                PROTECTION_ICON_SIZE,
                TRANSPARENT_INDEX,
            )

    def _draw_healing_popups(self) -> None:
        """Draw HEAL numbers from the sprite row below damage digits."""

        for popup in getattr(self, "healing_popups", ()):
            reference_frame = min(
                popup.elapsed_frame * DA2_REFERENCE_FPS // FPS,
                len(DA2_DAMAGE_VERTICAL_OFFSETS) - 1,
            )
            vertical_offset = DA2_DAMAGE_VERTICAL_OFFSETS[reference_frame]
            digits = str(popup.amount)
            x = popup.x - len(digits) * DAMAGE_NUMBER_SPRITE_SIZE // 2
            y = popup.y - vertical_offset
            for digit in digits:
                pyxel.blt(
                    x,
                    y,
                    0,
                    DAMAGE_NUMBER_SPRITE_X + int(digit) * DAMAGE_NUMBER_SPRITE_SIZE,
                    HEALING_NUMBER_SPRITE_Y,
                    DAMAGE_NUMBER_SPRITE_SIZE,
                    DAMAGE_NUMBER_SPRITE_SIZE,
                    TRANSPARENT_INDEX,
                )
                x += DAMAGE_NUMBER_SPRITE_SIZE

    def _draw_spell_damage_popups(self) -> None:
        """Draw spell damage or a DA2-style miss marker."""

        for popup in getattr(self, "spell_damage_popups", ()):
            offsets = (
                DA2_MISS_VERTICAL_OFFSETS
                if popup.is_miss
                else DA2_DAMAGE_VERTICAL_OFFSETS
            )
            reference_frame = min(
                popup.elapsed_frame * DA2_REFERENCE_FPS // FPS,
                len(offsets) - 1,
            )
            vertical_offset = offsets[reference_frame]
            if vertical_offset < 0:
                continue
            y = popup.y - vertical_offset
            if popup.is_miss:
                pyxel.blt(
                    popup.x - MISS_SPRITE_WIDTH // 2,
                    y,
                    0,
                    MISS_SPRITE_SOURCE_X,
                    DAMAGE_NUMBER_SPRITE_Y,
                    MISS_SPRITE_WIDTH,
                    DAMAGE_NUMBER_SPRITE_SIZE,
                    TRANSPARENT_INDEX,
                )
                continue
            digits = str(popup.damage)
            x = popup.x - len(digits) * DAMAGE_NUMBER_SPRITE_SIZE // 2
            for digit in digits:
                pyxel.blt(
                    x,
                    y,
                    0,
                    DAMAGE_NUMBER_SPRITE_X + int(digit) * DAMAGE_NUMBER_SPRITE_SIZE,
                    DAMAGE_NUMBER_SPRITE_Y,
                    DAMAGE_NUMBER_SPRITE_SIZE,
                    DAMAGE_NUMBER_SPRITE_SIZE,
                    TRANSPARENT_INDEX,
                )
                x += DAMAGE_NUMBER_SPRITE_SIZE

    def _draw_affinity_popups(self) -> None:
        """Draw static DA2-style WEAK/RESIST markers from image bank zero."""

        for popup in getattr(self, "affinity_popups", ()):
            source_y = (
                WEAK_ICON_SOURCE_Y
                if popup.affinity is SpellAffinity.WEAK
                else RESIST_ICON_SOURCE_Y
            )
            pyxel.blt(
                popup.x,
                popup.y,
                0,
                AFFINITY_ICON_SOURCE_X,
                source_y,
                AFFINITY_ICON_WIDTH,
                AFFINITY_ICON_HEIGHT,
                TRANSPARENT_INDEX,
            )

    def _draw_target_affinity_indicators(self) -> None:
        """Blink VOID or learned WEAK/RESIST markers during enemy selection."""

        if getattr(self, "auto_battle_active", False):
            return
        phase = getattr(self, "phase", None)
        if (
            phase not in (BattlePhase.TARGET, BattlePhase.ACTION_TARGET)
            or (
                phase is BattlePhase.ACTION_TARGET
                and not getattr(self, "action_targets_enemy", False)
            )
            or pyxel.frame_count % TARGET_AFFINITY_BLINK_FRAME_COUNT
            >= TARGET_AFFINITY_VISIBLE_FRAME_COUNT
        ):
            return
        spell = None
        if phase is BattlePhase.ACTION_TARGET:
            spell = self.pending_spell
            if spell is None and self.pending_item_candidate is not None:
                spell = self.spells.get(self.pending_item_candidate.item.use_spell_key)
        for index in self.selectable_target_indexes:
            if spell is not None and self._enemy_spell_is_void(spell, index):
                source_x, source_y = VOID_ICON_SOURCE_X, VOID_ICON_SOURCE_Y
            else:
                affinities = self._target_affinities(index)
                if not affinities:
                    continue
                visible_frame = pyxel.frame_count % TARGET_AFFINITY_BLINK_FRAME_COUNT
                affinity_index = min(
                    visible_frame
                    * len(affinities)
                    // TARGET_AFFINITY_VISIBLE_FRAME_COUNT,
                    len(affinities) - 1,
                )
                affinity = affinities[affinity_index]
                source_x = AFFINITY_ICON_SOURCE_X
                source_y = (
                    WEAK_ICON_SOURCE_Y
                    if affinity is SpellAffinity.WEAK
                    else RESIST_ICON_SOURCE_Y
                )
            monster = self.monsters[index]
            _base_x, base_y = self._monster_base_position(index)
            pyxel.blt(
                self._monster_draw_x(index)
                + monster.width // 2
                - AFFINITY_ICON_WIDTH // 2,
                base_y + 20,
                0,
                source_x,
                source_y,
                AFFINITY_ICON_WIDTH,
                AFFINITY_ICON_HEIGHT,
                TRANSPARENT_INDEX,
            )

    def _draw_monster_shadow(
        self,
        monster: BattleMonster,
        x: int,
        y: int,
    ) -> None:
        """Keep the ground shadow fixed while the monster sprite floats."""

        if monster.shadow != 1:
            return
        pyxel.blt(
            x + (monster.width - MONSTER_SHADOW_WIDTH) // 2,
            y + monster.height + MONSTER_SHADOW_OFFSET_Y,
            self.monster_shadow,
            0,
            0,
            MONSTER_SHADOW_WIDTH,
            MONSTER_SHADOW_HEIGHT,
            TRANSPARENT_INDEX,
        )

    def _draw_monster_image(
        self,
        monster: BattleMonster,
        x: int,
        y: int,
        *,
        flip_x: bool = False,
        wave_strength: float = 0.0,
        wave_frame: int = 0,
    ) -> None:
        if monster.shadow == 1:
            pattern = (
                pyxel.frame_count // MONSTER_FLOATING_PATTERN_FRAME_COUNT
            ) % len(MONSTER_FLOATING_OFFSETS)
            y += MONSTER_FLOATING_OFFSETS[pattern]
        image = self.monster_images[monster.key]
        width = -monster.width if flip_x else monster.width
        if wave_strength:
            wave_step = wave_frame // BREATH_WAVE_FRAMES_PER_STEP
            for row in range(0, monster.height, BREATH_WAVE_STRIP_HEIGHT):
                phase = (row // BREATH_WAVE_STRIP_HEIGHT - wave_step) % len(BREATH_WAVE_OFFSETS)
                offset = round(BREATH_WAVE_OFFSETS[phase] * wave_strength)
                height = min(BREATH_WAVE_STRIP_HEIGHT, monster.height - row)
                pyxel.blt(x + offset, y + row, image, 0, row, width, height, TRANSPARENT_INDEX)
            return
        pyxel.blt(
            x,
            y,
            image,
            0,
            0,
            width,
            monster.height,
            TRANSPARENT_INDEX,
        )

    def _monster_draw_x(self, index: int) -> int:
        return self._monster_draw_position(index)[0]

    def _monster_slot_index(self, index: int) -> int:
        slots = getattr(self, "monster_slot_indexes", None)
        if slots is None:
            monsters = getattr(self, "monsters", ())
            if not monsters:
                return index
            slots = monster_slot_indexes(monsters)
        return slots[index]

    def _monster_base_position(self, index: int) -> tuple[int, int]:
        positions = getattr(self, "monster_positions", None)
        if positions is None:
            monsters = getattr(self, "monsters", ())
            if not monsters:
                return MONSTER_POSITIONS[index]
            positions = monster_layout(monsters).positions
        return positions[index]

    @staticmethod
    def _monster_name_window_grid_position(
        monster: BattleMonster,
        x: int,
        y: int,
    ) -> tuple[int, int]:
        """Place the name at the same distance from every image's bottom."""

        return x // 4 + 2, (y + monster.height - 12) // 4

    def _monster_draw_position(self, index: int) -> tuple[int, int]:
        target_x, target_y = self._monster_base_position(index)
        phase = getattr(self, "phase", None)
        presentation = getattr(self, "monster_charge_presentation", None)
        if (
            phase is BattlePhase.MONSTER_ACTION
            and presentation is not None
            and index == presentation.actor_index
        ):
            return presentation.position()
        if phase is BattlePhase.MONSTER_ACTION and index == getattr(
            self, "monster_escape_actor_index", None
        ):
            return self._monster_escape_x(index), target_y
        slot_index = self._monster_slot_index(index)
        reinforcement_frame = getattr(self, "reinforcement_entrance_frames", {}).get(
            index
        )
        if reinforcement_frame is not None:
            elapsed = reinforcement_frame
        elif phase is BattlePhase.ENTRANCE:
            elapsed = self.entrance_animation_frame
        else:
            return target_x, target_y
        duration = MONSTER_ENTRANCE_FRAME_COUNTS[slot_index]
        elapsed = min(elapsed, duration)
        remaining = duration - elapsed
        initial_offset = (
            DA2_MONSTER_ENTRANCE_SLIDE_STEPS[slot_index]
            * DA2_MONSTER_ENTRANCE_STEP_DISTANCE
        )
        return target_x - initial_offset * remaining // duration, target_y

    def _draw_target_cursor(self) -> None:
        if getattr(self, "auto_battle_active", False):
            return
        if self.phase is BattlePhase.TARGET:
            if getattr(self, "selected_command", None) in ALL_ENEMY_TARGET_COMMANDS:
                if pyxel.frame_count % 2 == 0:
                    for cursor in self.all_target_cursors:
                        cursor.draw()
            else:
                self.target_cursor.draw()
            return
        if self.phase is BattlePhase.COVER_TARGET:
            if self.party_target_cursor is not None:
                self.party_target_cursor.draw()
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
        animation = getattr(self, "timeline_removal_animation", None)
        if animation is not None:
            self._draw_timeline_removal(animation)
            return
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
            elif advance.interrupt_index is None and advance.reinsert_completed_actor:
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
        if self.phase in (
            BattlePhase.VICTORY_SUMMARY,
            BattlePhase.RESULT_TRANSITION,
        ):
            return
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

    def _draw_timeline_removal(self, animation: TimelineRemovalAnimation) -> None:
        """Reverse the interrupt's rise, then slide survivors into the gaps."""

        fall_frame = min(animation.elapsed_frame, TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT)
        drop = (
            TIMELINE_DROP_DISTANCE * fall_frame // TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT
        )
        slide_frame = max(
            0, animation.elapsed_frame - TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT
        )
        for index, entry in enumerate(animation.before[:TIMELINE_VISIBLE_ENTRY_COUNT]):
            if all(entry is not actor for actor in animation.after):
                self._draw_timeline_entry(
                    entry,
                    TIMELINE_BASE_X + index * TIMELINE_SLOT_SPACING,
                    TIMELINE_BASE_Y + drop,
                )
        for index, entry in enumerate(animation.after[:TIMELINE_VISIBLE_ENTRY_COUNT]):
            previous_index = next(
                old_index
                for old_index, actor in enumerate(animation.before)
                if entry is actor
            )
            start_x = (
                TIMELINE_BASE_X + previous_index * TIMELINE_SLOT_SPACING
                if previous_index < TIMELINE_VISIBLE_ENTRY_COUNT
                else TIMELINE_INCOMING_START_X
                + (previous_index - TIMELINE_VISIBLE_ENTRY_COUNT) * TIMELINE_SLOT_SPACING
            )
            destination_x = TIMELINE_BASE_X + index * TIMELINE_SLOT_SPACING
            x = start_x + (
                (destination_x - start_x)
                * slide_frame
                // TIMELINE_INTERRUPT_SLIDE_FRAME_COUNT
            )
            self._draw_timeline_entry(entry, x, TIMELINE_BASE_Y)

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
        if self.phase in (
            BattlePhase.VICTORY_SUMMARY,
            BattlePhase.RESULT_TRANSITION,
        ):
            if self.victory_summary_window is not None:
                self.victory_summary_window.draw()
            return
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
        hidden_party_status_indexes = set(getattr(self, "escaped_party_indexes", set()))
        hidden_party_status_indexes.update(
            getattr(self, "escape_start_frame_by_party_index", {})
        )
        for window in self.windows:
            if hide_party_status and any(
                window is status_window for status_window in self.party_status_windows
            ):
                continue
            if any(
                index in hidden_party_status_indexes and window is status_window
                for index, status_window in enumerate(self.party_status_windows)
            ):
                continue
            window.draw()
        global_command_window = getattr(self, "global_command_window", None)
        show_monster_names = (
            self.phase in (BattlePhase.BOSS_INTRO, BattlePhase.TARGET)
            or (self.phase is BattlePhase.ACTION_TARGET and self.action_targets_enemy)
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
        elif self.phase is BattlePhase.SURPRISE_PREVENTED:
            self.battle_popup_window.draw()
        elif battle_popup is not None and battle_popup.visible:
            self.action_popup_window.draw()
        if (
            getattr(self, "auto_battle_active", False)
            or self.phase is BattlePhase.COMMAND
        ):
            input_guide_window = getattr(self, "input_guide_window", None)
            if input_guide_window is not None:
                input_guide_window.draw()
