"""Coordinate the currently playable field-first game flow."""

from __future__ import annotations

import json
import os
import sys
from enum import Enum, auto
from pathlib import Path

import pyxel

from attack_pose import AttackPoseDataError
from battle_command_memory import BattleCommandMemory
from game_data import (
    GameDataError,
    create_party,
    load_character_records,
    load_items,
    load_monsters,
    load_shops,
    load_skills,
    load_spells,
)
from ui.debug_menu import DebugMenuOverlay, DebugShopTarget
from ui.auto_recovery import AutoRecoveryOverlay
from ui.debug_text import DEBUG_TEXT
from ui.teleport_menu import TeleportTarget
from ui.game_menu import GameMenuAction, GameMenuOverlay
from ui.field_menu_guide import FieldMenuGuide
from ui.hint import HintOverlay
from ui.equipment_menu import (
    EquipmentMenuDataError,
    EquipmentMenuOverlay,
)
from ui.item_menu import (
    ItemMenuDataError,
    ItemMenuOverlay,
)
from ui.information_menu import (
    InformationMenuDataError,
    InformationMenuOverlay,
)
from ui.status_menu import (
    StatusMenuDataError,
    StatusMenuOverlay,
)
from ui.spell_menu import (
    SpellMenuDataError,
    SpellMenuOverlay,
)
from ui.shop import ShopOverlay, ShopUiDataError
from field import FieldActors, FieldMovement, FieldPosition
from field_birds import WorldMapBirds
from input import (
    Direction,
    InputAction,
    InputBindings,
    InputDevice,
    InputState,
    PyxelInputReader,
)
from item import ItemDataError
from localization import Localizer, format_number
from member import (
    BATTLE_PARTY_MEMBER_COUNT,
    CharacterDefinition,
    FacePosition,
    FormationRow,
    Member,
    MemberDataError,
    Race,
)
from systems.auto_recovery import valid_config_for_party
from monster import MonsterDataError
from resources import (
    TRANSPARENT_INDEX,
    AudioResourceError,
    BgmPlayer,
    CompiledMap,
    DataResourceError,
    EventCatalog,
    FontResourceError,
    FontResources,
    FontRole,
    ImageResourceError,
    ImageResources,
    MapDestination,
    MapResourceError,
    MapResources,
    play_se,
)
from systems.conditions import evaluate_condition
from resources.event_messages import (
    EventMessageCatalog,
    EventMessageResourceError,
)
from rendering import (
    DEFAULT_FADE_FRAME_COUNT,
    DIMMED_PALETTE,
    MONOCHROME_PALETTE,
    FadeEvent,
    FadePhase,
    FadeThroughBlack,
    EncounterTransition,
    FIELD_ACTOR_CHARACTER_SET_HEIGHT,
    FIELD_ACTOR_CHARACTER_SET_WIDTH,
    FIELD_CHARACTER_ASSET_ID,
    FIELD_PLAYER_CHARACTER_ASSET_ID,
    FIELD_PLAYER_CHARACTER_SET_HEIGHT,
    FIELD_PLAYER_CHARACTER_SET_WIDTH,
    FIELD_PLAYER_CHARACTER_SETS_PER_ROW,
    FIELD_PROP_ASSET_ID,
    FIELD_TREASURE_ASSET_ID,
    floating_phase_offset,
    FieldRenderer,
    PaletteShifter,
)
from scenes import (
    BattleDataError,
    BattleEncounter,
    BattlePhase,
    BattleResult,
    BattleScene,
)
from skill import SkillDataError
from shop import ShopDataError
from spell import SpellDataError
from spell_effect import SpellEffectDataError
from state import DisplayMode, Difficulty, Language, SaveData, Settings, SpellMode
from systems import (
    AUTO_SAVE_SLOT,
    ChangeBgmEffect,
    DebugPartyEditor,
    DebugPartyError,
    EventContext,
    EventRunner,
    EventRuntimeError,
    ENCOUNTER_THRESHOLD,
    EncounterSystem,
    InventorySystem,
    LoadedGameState,
    MessageEffect,
    MoveActorEffect,
    MovePartyEffect,
    OpenShopEffect,
    PartySystem,
    PlaySeEffect,
    StartBattleEffect,
    SaveRepository,
    SaveSlotSummary,
    SaveSystemError,
    SettingsRepository,
    SettingsSystemError,
    ShopSystem,
    TravelSystem,
    TreasureOpenStatus,
    TreasureSystem,
    create_save_document,
    restore_save_document,
)
from world_sites import WorldSiteCatalog

from text_catalog import TextCatalog, TextCatalogError
from ui import (
    CursorTarget,
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    EventMessageDataError,
    EventMessageOverlay,
    MessageOverlay,
    LocalizedWindowTextFactory,
    NEGATIVE_COLOR,
    POSITIVE_COLOR,
    RESERVE_MEMBER_TEXT_COLOR,
    SaveMenuDataError,
    SaveMenuOverlay,
    StartMenuDataError,
    StartMenuOverlay,
    WindowFactory,
    WindowCursor,
    WindowText,
    WINDOW_ANIMATION_FRAME_COUNT,
    draw_tagged_text,
    format_play_time,
    input_icon_tag,
    pad,
)
from ui.formation_arrow import (
    FORMATION_ARROW_BANK,
    FORMATION_ARROW_COLKEY,
    FORMATION_ARROW_FRAME_DURATION,
    FORMATION_ARROW_HEIGHT,
    FORMATION_ARROW_LEFT_X,
    FORMATION_ARROW_RIGHT_X,
    FORMATION_ARROW_WIDTH,
    FORMATION_ARROW_Y,
)

APP_ROOT = Path(__file__).resolve().parent
SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
FPS = 60

FIELD_FADE_ENCOUNTER_MULTIPLIER = 2
FIELD_FADE_PULSE_PALETTE = DIMMED_PALETTE
FIELD_FADE_PULSE_TARGET_COLOR = 0x000000
FIELD_FADE_PULSE_MIN_BASE_RATE = 0.5
FIELD_FADE_PULSE_CYCLE_FRAME_COUNT = 90
FIELD_FADE_PULSE_HALF_CYCLE_FRAME_COUNT = FIELD_FADE_PULSE_CYCLE_FRAME_COUNT // 2

MENU_COMMANDS = (
    ("heal", "menu.command.heal"),
    ("item", "menu.command.item"),
    ("spell", "menu.command.spell"),
    ("equip", "menu.command.equip"),
    ("status", "menu.command.status"),
    ("sort", "menu.command.sort"),
    ("info", "menu.command.info"),
    ("config", "menu.command.settings"),
    ("save", "menu.command.save"),
)
DIFFICULTY_TEXT_KEYS = {
    Difficulty.NORMAL: "menu.difficulty.normal",
    Difficulty.HARD: "menu.difficulty.hard",
}
MENU_INFO_TEXT_KEYS = (
    "menu.info.gold",
    "menu.info.experience",
    "menu.info.difficulty",
    "menu.info.play_time",
)
MENU_CLOSE_GUIDE_TEXT_KEY = "menu.close_guide"
TREASURE_GOLD_TEXT_KEY = "treasure.found_gold"
TREASURE_ITEM_TEXT_KEY = "treasure.found_item"
TREASURE_CAPACITY_TEXT_KEY = "treasure.capacity_exceeded"
TREASURE_OPEN_SE_ID = "treasure_open"
FIELD_POISON_SE_ID = "field_poison"
FIELD_POISON_SE_CHANNEL = 3
FIELD_MEMBER_DEAD_TEXT_KEY = "field.member.dead"
FIELD_MEMBER_ADVANCED_TEXT_KEY = "field.member.advanced"
FIELD_PARTY_ANNIHILATED_TEXT_KEY = "field.party.annihilated"
DEFEAT_RETURN_MESSAGE_TEXT_KEY = "defeat.return.message"
DEFEAT_RETURN_FACE_POSITION = FacePosition(0, 224)
HINT_SHOWN_FLAG_PREFIX = "hint.shown."
FIRST_BATTLE_HINT_ID = "first_battle"
FIRST_RESULT_HINT_ID = "first_result"
FIRST_DUNGEON_EXIT_HINT_ID = "first_dungeon_exit"
FIRST_DEFEAT_RESTART_HINT_ID = "first_defeat_restart"
MENU_MEMBER_TEXT_KEYS = (
    "menu.member.hp",
    "menu.member.mp",
    "term.formation.reserve",
)
SETTINGS_TEXT_KEYS = (
    "settings.language.label",
    "settings.language.ja",
    "settings.language.en",
    "settings.language.zhcn",
    "settings.bgm.label",
    "settings.se.label",
    "settings.screen_size.label",
    "settings.screen_size.fullscreen",
    "settings.display.label",
    "settings.display.pixel",
    "settings.display.smooth",
    "settings.in_game_hints.label",
    "settings.screen_flash.label",
    "settings.screen_flash.normal",
    "settings.screen_flash.reduced",
    "settings.command_memory.label",
    "settings.auto_spells.label",
    "settings.auto_spells.use",
    "settings.auto_spells.recovery_only",
    "settings.auto_spells.never",
    "settings.return_title",
    "settings.quit",
    "settings.confirm.return_title",
    "settings.confirm.quit",
    "settings.yes",
    "settings.no",
    "settings.on",
    "settings.off",
)
SETTINGS_ROWS = (
    ("language", 2),
    ("bgm", 5),
    ("se", 8),
    ("screen_size", 11),
    ("display", 14),
    ("screen_flash", 17),
    ("in_game_hints", 20),
    ("command_memory", 23),
    ("auto_spells", 26),
    ("debug", 29),
    ("return_title", 32),
    ("quit", 35),
)
SETTINGS_GUIDE_KEYS = {
    "in_game_hints": "settings.guide.in_game_hints",
    "language": "settings.guide.language",
    "bgm": "settings.guide.bgm",
    "se": "settings.guide.se",
    "screen_size": "settings.guide.screen_size",
    "display": "settings.guide.display",
    "screen_flash": "settings.guide.screen_flash",
    "command_memory": "settings.guide.command_memory",
    "auto_spells": "settings.guide.auto_spells",
}
LANGUAGE_SEQUENCE = (
    Language.JAPANESE,
    Language.ENGLISH,
    Language.SIMPLIFIED_CHINESE,
)
DISPLAY_SEQUENCE = (DisplayMode.PIXEL, DisplayMode.SMOOTH)
MOCK_INPUT_DEVICE = InputDevice.KEYBOARD
FACES_IMAGE_ID = "faces/faces"
WORLD_MAP_ID = "worldmap"
WORLD_MAP_START_POSITION = FieldPosition(x=17, y=39)
NEW_GAME_EVENT_ID = "worldmap.prologue"
RUNTIME_TEXTS_PATH = APP_ROOT / "data" / "texts.json"
SITE_MAP_FADE_FRAME_COUNT = 12
SITE_NAME_FONT_ROLE = FontRole.LARGE
SITE_NAME_LABEL_GAP = 1
SITE_FACING_DIRECTIONS = {
    "up": Direction.UP,
    "right": Direction.RIGHT,
    "down": Direction.DOWN,
    "left": Direction.LEFT,
}
PARTY_WINDOW_GRID = (0, 0, 48, 60)
PARTY_MEMBER_ROW_HEIGHT = 9
PARTY_MEMBER_ROW_HEIGHT_WITHOUT_RESERVE = 11
PARTY_FACE_X = {
    True: 20,
    False: 32,
}
PARTY_FACE_Y = 10
PARTY_FACE_SIZE = 32
PARTY_NAME_TEXT_X = 17
PARTY_POINT_TEXT_X = 19
PARTY_STATUS_TEXT_X = 32
PARTY_RECOVERY_TEXT_X = 39
PARTY_CURSOR_X = 3
PARTY_CURSOR_Y = 5
RESERVE_MEMBER_Y_OFFSET_GRID = 2
SORT_SOURCE_CURSOR_X_OFFSET = 1
TELEPORT_SOUND_CHANNEL = 0
TELEPORT_SOUND_ID = 8
ALERT_CHANNEL = 1
ALERT_SOUND_ID = 7
SE_CHANNELS = (
    TELEPORT_SOUND_CHANNEL,
    ALERT_CHANNEL,
    FIELD_POISON_SE_CHANNEL,
)
ALERT_FRAME_COUNT = 3
ALERT_CAMERA_X = (0, 0, 1, -1)
SETTINGS_WINDOW_GRID = (4, 4, 56, 52)
SETTINGS_LABEL_X = 4
SETTINGS_VALUE_X = 30
SETTINGS_CURSOR_X = 2
SETTINGS_GUIDE_X = 4
SETTINGS_GUIDE_Y = 41
SETTINGS_GUIDE_ROW_HEIGHT = 3
CONFIRMATION_WINDOW_GRID = (8, 22, 48, 16)
CONFIRMATION_CURSOR_X = 4
CONFIRMATION_YES_Y = 8
CONFIRMATION_NO_Y = 11
SE_VOLUME_GAINS = (0.0, 0.05, 0.10, 0.15, 0.20)
SE_PREVIEW_SOUND_ID = 9
GAME_SETTINGS_ENV = "DA0_GAME_SETTINGS"
WELCOME_BGM_ID = "da3-welcome"
ENCOUNTER_JINGLE_ID = "da3-encount"
INITIAL_GOLD = 100
INITIAL_PARTY_KEYS = ("Fiora", "Cerion")


class GameScreenChange(Enum):
    """Screen replacement applied only while fully black."""

    SHOW_FIELD = auto()
    SHOW_MENU = auto()
    OPEN_RECOVERY = auto()
    CLOSE_RECOVERY = auto()
    OPEN_ITEM = auto()
    CLOSE_ITEM = auto()
    OPEN_SPELL = auto()
    CLOSE_SPELL = auto()
    OPEN_EQUIPMENT = auto()
    CLOSE_EQUIPMENT = auto()
    OPEN_STATUS = auto()
    CLOSE_STATUS = auto()
    OPEN_INFO = auto()
    CLOSE_INFO = auto()
    OPEN_SAVE = auto()
    CLOSE_SAVE = auto()
    OPEN_SHOP = auto()
    CLOSE_SHOP = auto()
    CHANGE_MAP = auto()
    TELEPORT = auto()
    START_GAME = auto()


class MenuAlertEffect:
    """Reproduce DA2's short error sound and horizontal screen shake."""

    def __init__(self) -> None:
        self.remaining_frames = 0

    @property
    def camera_x(self) -> int:
        return ALERT_CAMERA_X[self.remaining_frames]

    def start(self) -> None:
        pyxel.play(ALERT_CHANNEL, ALERT_SOUND_ID)
        self.remaining_frames = ALERT_FRAME_COUNT

    def update(self) -> None:
        if self.remaining_frames > 0:
            self.remaining_frames -= 1


def localized_menu_texts(
    catalog: TextCatalog,
    language: Language,
) -> dict[str, str]:
    """Resolve every menu term from the shared text catalog."""

    if not isinstance(catalog, TextCatalog):
        raise TypeError("catalog must be a TextCatalog")
    localizer = Localizer(language)
    keys = (
        *(text_key for _command_key, text_key in MENU_COMMANDS),
        *MENU_INFO_TEXT_KEYS,
        *DIFFICULTY_TEXT_KEYS.values(),
        MENU_CLOSE_GUIDE_TEXT_KEY,
        *MENU_MEMBER_TEXT_KEYS,
        *SETTINGS_TEXT_KEYS,
    )
    localized: dict[str, str] = {}
    for key in keys:
        text = catalog.text(key, localizer)
        if not text:
            raise GameDataError(f"ゲーム用テキストが見つかりません: {key}")
        localized[key] = text

    for key in SETTINGS_GUIDE_KEYS.values():
        if not any(catalog.lines(key, localizer)):
            raise GameDataError(f"ゲーム用テキストが見つかりません: {key}")

    close_guide = localized[MENU_CLOSE_GUIDE_TEXT_KEY]
    if close_guide.count("%CANCEL%") != 1:
        raise GameDataError(f"{MENU_CLOSE_GUIDE_TEXT_KEY}には%CANCEL%が1つ必要です")
    return localized


class Game:
    """Own the current field-first runtime state and Pyxel callbacks."""

    def __init__(
        self,
        *,
        settings: Settings,
        palette_shifter: PaletteShifter,
        settings_repository: SettingsRepository | None = None,
    ) -> None:
        if not isinstance(settings, Settings):
            raise TypeError("settings must be Settings")
        self.settings = settings
        self.battle_command_memory = BattleCommandMemory()
        self.settings_repository = (
            SettingsRepository() if settings_repository is None else settings_repository
        )
        self.applied_screen_scale = settings.screen_scale
        self.palette_shifter = palette_shifter
        self.input_reader = create_game_input_reader()
        self.alert = MenuAlertEffect()
        self.game_menu: GameMenuOverlay | None = None
        self._game_menu_resume_waiting = False
        self._game_menu_return_waiting = False

        self._apply_se_volume()
        self.bgm = BgmPlayer(volume=self.settings.bgm_volume)
        self.bgm.play(WELCOME_BGM_ID)
        self.save_data = SaveData(gold=INITIAL_GOLD)
        self.items = load_items()
        self.monsters = load_monsters()
        self.inventory_system = InventorySystem(self.items)
        self.skills = load_skills()
        self.spells = load_spells()
        self.party = create_party(
            self.items,
            self.skills,
            character_keys=INITIAL_PARTY_KEYS,
        )
        self.shops = load_shops(self.items)
        self.shop_system = ShopSystem(
            shops=self.shops,
            inventory=self.inventory_system,
            party=self.party,
            save_data=self.save_data,
        )
        self._force_reserve_front()
        self.character_records = load_character_records()
        self.character_states = {member.definition.key: member for member in self.party}
        self.party_system = PartySystem(
            character_records=self.character_records,
            items=self.items,
            skills=self.skills,
            active_party=self.party,
            character_states=self.character_states,
        )
        self.treasure_system = TreasureSystem(
            save_data=self.save_data,
            inventory=self.inventory_system,
        )
        character_definitions = tuple(
            CharacterDefinition.from_record(record) for record in self.character_records
        )
        self.character_face_positions = {
            definition.key: definition.face_position
            for definition in character_definitions
        }
        self.fairy_pc_sprite_indices = frozenset(
            definition.battle_sprite
            for definition in character_definitions
            if definition.race is Race.FAIRY
        )
        self.save_repository = SaveRepository()
        self.current_save_slot: int | None = None
        self.texts = TextCatalog.from_json(RUNTIME_TEXTS_PATH)
        self.fonts = FontResources()
        self.field_menu_guide = FieldMenuGuide(texts=self.texts, fonts=self.fonts)
        self.images = ImageResources()
        self.faces = self.images.image(FACES_IMAGE_ID)
        self.event_catalog = EventCatalog.from_json()
        self.event_messages = EventMessageCatalog.from_json()
        self.map_resources = MapResources()
        self.world_map = self.map_resources.map(WORLD_MAP_ID)
        self.current_map = self.world_map
        self.world_sites = WorldSiteCatalog(self.world_map.sites)
        self.current_sites = WorldSiteCatalog(self.current_map.sites)
        self.travel_system = TravelSystem(self.world_sites, self.map_resources)
        self.field = FieldMovement(
            self.world_map,
            start=WORLD_MAP_START_POSITION,
        )
        self.field_renderer = FieldRenderer(
            self.world_map,
            screen_width=SCREEN_WIDTH,
            screen_height=SCREEN_HEIGHT,
        )
        self.field_actors: FieldActors | None = None
        self.field_prop_image = None
        self.field_actor_character_image = None
        self.field_actor_pc_character_image = None
        self.field_player_character_image = None
        self.field_treasure_image = None
        self._reset_field_actors()
        self.event_runner: EventRunner | None = None
        self.event_effect = None
        self.event_message: EventMessageOverlay | None = None
        self.treasure_message: MessageOverlay | None = None
        self.field_condition_message: MessageOverlay | None = None
        self.field_party_annihilated_pending = False
        self.pending_treasure_close_actor_id: str | None = None
        self.event_move_remaining = 0
        self.event_release_direction: Direction | None = None
        self.event_release_confirm = False
        self.event_resume_after_fade = False
        self.event_stationary_actor_facing_restore: (
            tuple[
                str,
                Direction,
            ]
            | None
        ) = None
        self.last_event_error: str | None = None
        self.settings_window = None
        self.settings_cursor: WindowCursor | None = None
        self.confirmation_window = None
        self.confirmation_cursor: WindowCursor | None = None
        self.pending_settings_action: str | None = None
        self._returning_to_start = False
        self.fade = FadeThroughBlack()
        self.pending_screen_change: GameScreenChange | None = None
        self.auto_save_after_fade = False
        self.fade_bgm = False
        self.animate_main_windows_with_fade = False
        self.showing_field = False
        self.encounter_system = EncounterSystem()
        self.field_fade_active = False
        self.field_fade_pulse_frame = 0
        self.encounter_transition: EncounterTransition | None = None
        self.encounter_snapshot = None
        self.battle_return_fade: FadeThroughBlack | None = None
        self.battle_return_result: BattleResult | None = None
        self.defeat_return_message: MessageOverlay | None = None
        self.defeat_return_sound_waiting = False
        self.defeat_return_bgm_restart_pending = False
        self.item_screen: ItemMenuOverlay | None = None
        self.auto_recovery_screen: AutoRecoveryOverlay | None = None
        self.equipment_screen: EquipmentMenuOverlay | None = None
        self.status_screen: StatusMenuOverlay | None = None
        self.information_screen: InformationMenuOverlay | None = None
        self.hint_overlay: HintOverlay | None = None
        self._load_mission_hint_shown_this_launch = False
        self.pending_hint_after_fade: str | None = None
        self.spell_screen: SpellMenuOverlay | None = None
        self.save_screen: SaveMenuOverlay | None = None
        self.shop_screen: ShopOverlay | None = None
        self.battle_scene: BattleScene | None = None
        self.pending_first_party_turn_hint = False
        self.pending_event_battle_encounter: BattleEncounter | None = None
        self.pending_event_battle_id: str | None = None
        self.suspended_field_event: tuple[EventRunner, StartBattleEffect] | None = None
        self.pending_shop = None
        self.shop_return_to_debug = False
        self.debug_screen: DebugMenuOverlay | None = None
        self.selected_member_index = 0
        self.menu_member_selected = False
        self.site_name_site = None
        self.site_name_text: WindowText | None = None
        self._site_name_cache: tuple[str, Language] | None = None
        self.pending_site = None
        self.pending_target_map = None
        self.pending_target_arrival = None
        self.pending_teleport_source: str | None = None
        self.pending_loaded_state: LoadedGameState | None = None
        self.pending_loaded_map = None
        self.pending_loaded_field: FieldMovement | None = None
        self.pending_loaded_renderer: FieldRenderer | None = None
        self.pending_load_slot: int | None = None
        self._build_main_windows()
        self._refresh_site_name_label()
        self.start_screen: StartMenuOverlay | None = StartMenuOverlay(
            summaries=self.save_repository.summaries(),
            autosave_summary=self.save_repository.summary(AUTO_SAVE_SLOT),
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
            faces=self.faces,
            face_positions=self.character_face_positions,
            palette_shifter=self.palette_shifter,
            on_new_game=self._start_new_game,
            on_load=self._load_from_slot,
            on_delete=self._delete_save_slot,
            on_invalid_action=self.alert.start,
        )

    @staticmethod
    def settings_from_environment(
        repository: SettingsRepository | None = None,
    ) -> Settings:
        """Restore reset settings first, then persisted device settings."""

        repository = SettingsRepository() if repository is None else repository
        serialized = os.environ.get(GAME_SETTINGS_ENV)
        if serialized is not None:
            try:
                data = json.loads(serialized)
                return Settings.from_dict(data)
            except (json.JSONDecodeError, TypeError, ValueError):
                os.environ.pop(GAME_SETTINGS_ENV, None)
        try:
            return repository.load()
        except SettingsSystemError:
            return Settings()

    def _build_battle_scene(self, encounter: BattleEncounter) -> BattleScene:
        """Create a battle from current session state without choosing when it starts."""

        memory = getattr(self, "battle_command_memory", None)
        if memory is None:
            memory = self.battle_command_memory = BattleCommandMemory()
        return BattleScene.create(
            settings=self.settings,
            palette_shifter=self.palette_shifter,
            bgm=self.bgm,
            resources=self.images,
            fonts=self.fonts,
            texts=self.texts,
            item_catalog=self.items,
            spells=self.spells,
            inventory_system=self.inventory_system,
            character_records=self.character_records,
            party=self.party[:BATTLE_PARTY_MEMBER_COUNT],
            result_party=self.party,
            save_data=self.save_data,
            return_bgm_id=self.current_map.bgm_id,
            encounter=encounter,
            command_memory=memory,
        )

    def _advance_random_encounter(self) -> bool:
        """Advance one completed dungeon step and begin battle when due."""

        current_map = getattr(self, "current_map", None)
        if getattr(current_map, "profile", None) != "dungeon":
            return False
        threshold = ENCOUNTER_THRESHOLD * (
            FIELD_FADE_ENCOUNTER_MULTIPLIER
            if getattr(self, "field_fade_active", False)
            else 1
        )
        advanced = self.encounter_system.advance(
            self.save_data.encounter_count,
            threshold=threshold,
        )
        self.save_data.encounter_count = advanced.count
        if not advanced.triggered:
            return False
        self._begin_random_encounter()
        return True

    def _activate_field_fade(self) -> bool:
        """Double the random-encounter threshold until the current floor ends."""

        if getattr(
            getattr(self, "current_map", None), "profile", None
        ) != "dungeon" or getattr(self, "field_fade_active", False):
            return False
        self.field_fade_active = True
        self.field_fade_pulse_frame = 0
        self._sync_field_fade_palette()
        return True

    def _reset_field_fade(self) -> None:
        """End the current-floor FADE effect and restore the shared dim palette."""

        self.field_fade_active = False
        self.field_fade_pulse_frame = 0
        self._restore_dimmed_palette()

    def _restore_dimmed_palette(self) -> None:
        palette_shifter = getattr(self, "palette_shifter", None)
        if palette_shifter is None:
            return
        palette_shifter.define_mix(
            DIMMED_PALETTE,
            base_rate=FIELD_FADE_PULSE_MIN_BASE_RATE,
            target_color=FIELD_FADE_PULSE_TARGET_COLOR,
        )

    def _sync_field_fade_palette(self) -> None:
        palette_shifter = getattr(self, "palette_shifter", None)
        if palette_shifter is None:
            return
        half_cycle = FIELD_FADE_PULSE_HALF_CYCLE_FRAME_COUNT
        distance_from_peak = abs(
            half_cycle - getattr(self, "field_fade_pulse_frame", 0)
        )
        progress_to_normal = distance_from_peak / half_cycle
        base_rate = FIELD_FADE_PULSE_MIN_BASE_RATE + (
            (1.0 - FIELD_FADE_PULSE_MIN_BASE_RATE) * progress_to_normal
        )
        palette_shifter.define_mix(
            FIELD_FADE_PULSE_PALETTE,
            base_rate=base_rate,
            target_color=FIELD_FADE_PULSE_TARGET_COLOR,
        )

    def _update_field_fade_pulse(self) -> None:
        if not getattr(self, "field_fade_active", False):
            return
        self.field_fade_pulse_frame = (
            self.field_fade_pulse_frame + 1
        ) % FIELD_FADE_PULSE_CYCLE_FRAME_COUNT
        self._sync_field_fade_palette()

    def _apply_dungeon_step_health_changes(self) -> None:
        """Apply DA2's step HP change, death notice, and row correction."""

        if self.current_map.profile != "dungeon":
            return
        previous_hp = tuple(member.hp for member in self.party)
        for member in self.party:
            member.apply_heal_and_poison()

        defeated = tuple(
            member
            for member, old_hp in zip(self.party, previous_hp, strict=True)
            if old_hp > 0 and member.hp <= 0
        )
        if not defeated:
            return

        localizer = Localizer(self.settings.language)
        lines = [
            self.texts.formatted_text(
                FIELD_MEMBER_DEAD_TEXT_KEY,
                localizer,
                {"MEMBER": member.definition.localized_name(localizer)},
            )
            for member in defeated
        ]
        promoted = self._promote_first_recoverable_member()
        if promoted is not None:
            lines.append(
                self.texts.formatted_text(
                    FIELD_MEMBER_ADVANCED_TEXT_KEY,
                    localizer,
                    {"MEMBER": promoted.definition.localized_name(localizer)},
                )
            )
        annihilated = not any(
            self._member_is_field_recoverable(member) for member in self.party
        )
        if annihilated:
            lines.append(self.texts.text(FIELD_PARTY_ANNIHILATED_TEXT_KEY, localizer))
        self.field_party_annihilated_pending = annihilated
        self.field_condition_message = MessageOverlay(
            lines=tuple(lines),
            settings=self.settings,
            fonts=self.fonts,
        )

    def _finish_field_condition_message(self) -> None:
        """Close a step-health notice and begin defeat return after a wipe."""

        self.field_condition_message = None
        if not getattr(self, "field_party_annihilated_pending", False):
            return
        self.field_party_annihilated_pending = False
        self._begin_battle_return(BattleResult.DEFEAT)

    @staticmethod
    def _member_is_field_recoverable(member: Member) -> bool:
        """Match DA2's field leader/front-row eligibility."""

        return member.hp > 0 and not member.paralyzed

    def _promote_first_recoverable_member(self) -> Member | None:
        """Keep one recoverable battle participant in the permanent front row."""

        active_party = self.party[:BATTLE_PARTY_MEMBER_COUNT]
        recoverable = tuple(
            member
            for member in active_party
            if self._member_is_field_recoverable(member)
        )
        if not recoverable or any(member.is_front_row for member in recoverable):
            return None
        promoted = recoverable[0]
        promoted.formation_row = FormationRow.FRONT
        return promoted

    def _field_player_member(self) -> Member:
        """Return DA2's first recoverable member, falling back to party leader."""

        return next(
            (
                member
                for member in self.party
                if self._member_is_field_recoverable(member)
            ),
            self.party[0],
        )

    def _play_dungeon_poison_movement_sound(self) -> None:
        """Repeat DA2's poison sound while a poisoned party walks."""

        current_map = getattr(self, "current_map", None)
        if (
            getattr(current_map, "profile", None) != "dungeon"
            or not self.field.is_moving
            or not any(member.poisoned for member in self.party)
            or pyxel.play_pos(FIELD_POISON_SE_CHANNEL) is not None
        ):
            return
        play_se(FIELD_POISON_SE_ID)

    def _begin_random_encounter(self) -> None:
        """Freeze the field and begin the PC-centered encounter transition."""

        camera_x, camera_y = self.field_renderer.camera_position(self.field)
        pivot_x = self.field.world_x - camera_x + self.current_map.tile_size / 2
        pivot_y = self.field.world_y - camera_y
        self.field.stop()
        self.encounter_transition = EncounterTransition(pivot_x, pivot_y)
        self.encounter_snapshot = None
        self.bgm.play(ENCOUNTER_JINGLE_ID, loop=False)

    def _update_encounter_transition(self) -> None:
        """White out the enlarged field, fade it, then create the battle scene."""

        transition = self.encounter_transition
        if transition is None:
            return
        transition.update()
        self.palette_shifter.set_global_mix(
            base_rate=transition.palette_base_rate,
            target_color=transition.palette_target_color,
        )
        if not transition.is_finished:
            return
        self.encounter_transition = None
        self.encounter_snapshot = None
        event_encounter = getattr(self, "pending_event_battle_encounter", None)
        self.pending_event_battle_encounter = None
        self.battle_scene = self._build_battle_scene(
            event_encounter or self._create_random_battle_encounter()
        )
        battle_id = getattr(self, "pending_event_battle_id", None)
        if (
            battle_id is not None
            and self.event_catalog.battle_start_event(battle_id) is not None
        ):
            self.battle_scene.defer_first_party_command()
        self.pending_first_party_turn_hint = True

    def _create_random_battle_encounter(self) -> BattleEncounter:
        """Resolve the map level and convert its generated formation for battle."""

        settings = self.current_map.random_encounter
        if settings is None:
            raise RuntimeError("current dungeon has no random encounter settings")
        monster_level = settings.monster_level
        if monster_level == "dynamic":
            monster_level = self.encounter_system.dynamic_monster_level()
        formation = self.encounter_system.generate_formation(
            self.monsters,
            settings,
            monster_level=monster_level,
        )
        return BattleEncounter(
            formation.monster_keys,
            surprise_enabled=True,
        )

    def _begin_event_battle(self, effect: StartBattleEffect) -> None:
        """Suspend the field event while its named battle runs."""

        runner = self.event_runner
        if runner is None or getattr(self, "suspended_field_event", None) is not None:
            raise RuntimeError("an event battle is already active")
        encounter = BattleEncounter(effect.monster_keys, escape_command_enabled=False)
        self.pending_event_battle_encounter = encounter
        self.pending_event_battle_id = effect.battle_id
        self.suspended_field_event = (runner, effect)
        self.event_runner = None
        self.event_effect = None
        self._begin_random_encounter()

    def _start_battle_event(self, event_id: str) -> None:
        """Run the event at the first playable party command of this battle."""

        try:
            self.party_system.replace(
                self.party, character_states=self.character_states
            )
            self.event_runner = EventRunner.from_catalog(
                self.event_catalog,
                event_id,
                context=EventContext.BATTLE,
                save_data=self.save_data,
                party=self.party_system,
                inventory=self.inventory_system,
            )
            self.last_event_error = None
            self._continue_event()
        except (
            KeyError, EventRuntimeError, EventMessageDataError,
            AudioResourceError, ValueError,
        ) as error:
            self._abort_event(error)

    def _resume_event_after_battle(self, result: BattleResult | None) -> None:
        """Continue the initiating event after the battle return transition."""

        self.pending_event_battle_id = None
        suspended = getattr(self, "suspended_field_event", None)
        self.suspended_field_event = None
        if suspended is None:
            return
        if result is BattleResult.DEFEAT:
            self._restore_event_stationary_actor_facing()
            return
        runner, effect = suspended
        try:
            runner.complete_effect(effect)
            self.event_runner = runner
            self.event_effect = None
            self._continue_event()
        except (
            KeyError, EventRuntimeError, EventMessageDataError,
            AudioResourceError, ValueError,
        ) as error:
            self._abort_event(error)

    def _show_hint_once(self, hint_id: str) -> bool:
        """Open one progression hint once per save after its trigger occurs."""

        if not isinstance(hint_id, str) or not hint_id:
            raise ValueError("hint ID must be a non-empty string")
        shown_flag = f"{HINT_SHOWN_FLAG_PREFIX}{hint_id}"
        if (
            not self.settings.in_game_hints_enabled
            or shown_flag in self.save_data.event_flags
            or getattr(self, "hint_overlay", None) is not None
        ):
            return False
        hint_overlay = HintOverlay(
            text_key=f"hint.{hint_id}",
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
        )
        self.hint_overlay = hint_overlay
        self.save_data.event_flags.add(shown_flag)
        return True

    def _queue_hint_after_fade(self, hint_id: str) -> None:
        """Reserve a field hint until the active fade-in has completed."""

        self.pending_hint_after_fade = hint_id

    def _show_pending_hint_after_fade(self) -> None:
        hint_id = getattr(self, "pending_hint_after_fade", None)
        self.pending_hint_after_fade = None
        if hint_id is not None:
            self._show_hint_once(hint_id)

    def _begin_battle_return(
        self,
        result: BattleResult,
        *,
        screen_already_covered: bool = False,
    ) -> None:
        """Begin the fade from a completed battle screen back to the field."""

        if not isinstance(result, BattleResult):
            raise TypeError("battle return result must be a BattleResult")
        if not isinstance(screen_already_covered, bool):
            raise TypeError("screen_already_covered must be a bool")
        self.battle_return_result = result
        self.defeat_return_message = None
        self.defeat_return_sound_waiting = False
        self.defeat_return_bgm_restart_pending = False
        self.battle_return_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        if screen_already_covered:
            self._apply_battle_return()
            self.battle_return_fade.start_fade_in()
            self.palette_shifter.set_global_mix(
                base_rate=0.0,
                target_color=self.palette_shifter.base_colors[0],
            )
            return
        self.battle_return_fade.start()

    def _update_battle_return(self, input_state: InputState) -> None:
        """Pause defeat at black for its message, then return to the field."""

        fade = self.battle_return_fade
        if fade is None:
            return
        message = getattr(self, "defeat_return_message", None)
        if message is not None:
            if message.update(input_state):
                self.defeat_return_message = None
                self.palette_shifter.set_global_mix(
                    base_rate=0.0,
                    target_color=self.palette_shifter.base_colors[0],
                )
                self._apply_battle_return()
                pyxel.play(TELEPORT_SOUND_CHANNEL, TELEPORT_SOUND_ID)
                self.defeat_return_sound_waiting = True
            return
        if getattr(self, "defeat_return_sound_waiting", False):
            if pyxel.play_pos(TELEPORT_SOUND_CHANNEL) is not None:
                return
            self.defeat_return_sound_waiting = False
            if getattr(self, "defeat_return_bgm_restart_pending", False):
                self.bgm.play(self.current_map.bgm_id)
                self.defeat_return_bgm_restart_pending = False
        event = fade.update()
        self.palette_shifter.set_global_mix(
            base_rate=fade.visible_rate,
            target_color=self.palette_shifter.base_colors[0],
        )
        self.bgm.set_fade_rate(fade.visible_rate)
        if event is FadeEvent.COVERED:
            if self.battle_return_result is BattleResult.DEFEAT:
                self._begin_defeat_return_message()
                self.palette_shifter.set_global_mix(
                    base_rate=1.0,
                    target_color=self.palette_shifter.base_colors[0],
                )
            else:
                self._apply_battle_return()
        if event is FadeEvent.FINISHED:
            finished_result = self.battle_return_result
            self.bgm.set_fade_rate(1.0)
            self.battle_return_fade = None
            self.battle_return_result = None
            self.defeat_return_sound_waiting = False
            self.defeat_return_bgm_restart_pending = False
            if finished_result is BattleResult.DEFEAT:
                self._show_hint_once(FIRST_DEFEAT_RESTART_HINT_ID)
            self._resume_event_after_battle(finished_result)

    def _begin_defeat_return_message(self) -> None:
        """Show the fixed rescue message over the fully black screen."""

        localizer = Localizer(self.settings.language)
        self.defeat_return_message = MessageOverlay(
            lines=self.texts.lines(DEFEAT_RETURN_MESSAGE_TEXT_KEY, localizer),
            settings=self.settings,
            fonts=self.fonts,
            faces=self.faces,
            face_position=DEFEAT_RETURN_FACE_POSITION,
        )

    def _update_battle_scene(self, input_state: InputState) -> bool:
        """Update the active battle and detect Game-owned hint timings."""

        battle_scene = getattr(self, "battle_scene", None)
        if battle_scene is None:
            return False
        if (
            getattr(battle_scene, "is_party_command_pending", False) is True
            and not getattr(self, "pending_first_party_turn_hint", False)
            and getattr(self, "hint_overlay", None) is None
        ):
            battle_scene.open_pending_party_command()
        battle_scene.update(input_state)
        if getattr(self, "pending_first_party_turn_hint", False):
            battle_id = getattr(self, "pending_event_battle_id", None)
            event_id = (
                self.event_catalog.battle_start_event(battle_id)
                if battle_id is not None else None
            )
            if (
                event_id is not None
                and battle_scene.is_party_command_pending is True
            ):
                self.pending_first_party_turn_hint = False
                self.pending_event_battle_id = None
                self._start_battle_event(event_id)
            elif event_id is None and battle_scene.is_party_command_ready:
                self.pending_first_party_turn_hint = False
                self.pending_event_battle_id = None
                self._show_hint_once(FIRST_BATTLE_HINT_ID)
        if battle_scene.phase is BattlePhase.RESULT:
            self._show_hint_once(FIRST_RESULT_HINT_ID)
        result = getattr(battle_scene, "result", None)
        if isinstance(result, BattleResult):
            if (
                result is BattleResult.ESCAPED
                and getattr(battle_scene, "result_overlay", None) is None
            ):
                self._begin_battle_return(
                    result,
                    screen_already_covered=True,
                )
            else:
                self._begin_battle_return(result)
        return True

    def _apply_battle_return(self) -> None:
        """Commit battle result changes while the screen is fully black."""

        result = self.battle_return_result
        if result is None:
            raise RuntimeError("battle return has no result")
        battle_scene = getattr(self, "battle_scene", None)
        field_defeat = result is BattleResult.DEFEAT and battle_scene is None
        if battle_scene is not None:
            battle_scene.clear_temporary_member_conditions()
            battle_scene.release_palette_variants()
        if result is BattleResult.VICTORY:
            self.save_data.battle_count += 1
        elif result is BattleResult.DEFEAT:
            for member in self.party:
                member.fully_recover()
            destination = self.encounter_system.defeat_return(
                self.current_map,
                self.field.position,
            )
            if destination is not None:
                self.field = FieldMovement(
                    self.current_map,
                    start=destination.position,
                    facing=destination.facing,
                )
                self._reset_field_actors()
        if getattr(self, "party", ()):
            self._promote_first_recoverable_member()
        self.battle_scene = None
        if getattr(self, "field_fade_active", False):
            self._sync_field_fade_palette()
        else:
            self._restore_dimmed_palette()
        self.bgm.set_fade_rate(0.0)
        if field_defeat:
            self.bgm.stop()
            self.defeat_return_bgm_restart_pending = True
        else:
            self.bgm.transition_to(self.current_map.bgm_id)

    @staticmethod
    def _select_cursor_key(cursor: WindowCursor, key: object) -> None:
        """Move a newly built vertical cursor to one existing key."""

        if cursor.selected_key == key:
            return
        for _target in cursor.targets:
            cursor.move_down()
            if cursor.selected_key == key:
                return
        raise ValueError(f"cursor key is not registered: {key!r}")

    def _build_main_windows(
        self,
        selected_command: str = "heal",
        *,
        animate: bool = True,
    ) -> None:
        localized = localized_menu_texts(
            self.texts,
            self.settings.language,
        )
        localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )
        self.localized = localized
        self.localized_texts = localized_texts
        self.debug_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            Language.JAPANESE,
        )
        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        self.party_window = windows.create(
            *PARTY_WINDOW_GRID,
            self._party_window_texts(
                self._main_menu_members(),
                localized,
                localized_texts,
            ),
            opened=not animate,
        )
        command_texts = tuple(
            localized_texts.create(
                localized[text_key],
                4,
                2 + index * 3,
            )
            for index, (_command_key, text_key) in enumerate(MENU_COMMANDS)
        )
        self.command_window = windows.create(
            48,
            0,
            16,
            31,
            command_texts,
            opened=not animate,
        )
        self.command_cursor = self.command_window.set_cursor(
            tuple(
                CursorTarget(2, 2 + index * 3, key=key)
                for index, (key, _) in enumerate(MENU_COMMANDS)
            )
        )
        if selected_command != MENU_COMMANDS[0][0]:
            self._select_cursor_key(self.command_cursor, selected_command)
        self.party_cursor: WindowCursor | None = None
        self.sort_source_index: int | None = None
        self.sort_source_cursor: WindowCursor | None = None
        self.info_window = windows.create(
            48,
            31,
            16,
            26,
            self._main_info_window_texts(),
            opened=not animate,
        )
        self.close_guide_window = windows.create(
            48,
            57,
            16,
            4,
            (
                localized_texts.create(
                    localized[MENU_CLOSE_GUIDE_TEXT_KEY].replace(
                        "%CANCEL%",
                        input_icon_tag(
                            InputAction.CANCEL,
                            MOCK_INPUT_DEVICE,
                        ),
                    ),
                    2,
                    0,
                ),
            ),
            transparent=True,
            opened=not animate,
        )
        self.windows = [
            self.party_window,
            self.command_window,
            self.info_window,
            self.close_guide_window,
        ]
        if animate:
            for window in self.windows:
                window.open()
        self._refresh_site_name_label(force=True)

    def _refresh_site_name_label(self, *, force: bool = False) -> None:
        """Rebuild the map-anchored nearby-site label when its contents change."""

        catalog = getattr(self, "world_sites", None)
        field = getattr(self, "field", None)
        if not isinstance(catalog, WorldSiteCatalog) or getattr(
            self, "current_map", None
        ) is not getattr(
            self,
            "world_map",
            None,
        ):
            self.site_name_site = None
            self.site_name_text = None
            self._site_name_cache = None
            return
        position = getattr(field, "position", None)
        if not isinstance(position, FieldPosition):
            self.site_name_site = None
            self.site_name_text = None
            self._site_name_cache = None
            return
        site = catalog.nearby_site(position.x, position.y)
        cache = None if site is None else (site.id, self.settings.language)
        if not force and cache == getattr(self, "_site_name_cache", None):
            return
        self._site_name_cache = cache
        if site is None:
            self.site_name_site = None
            self.site_name_text = None
            return
        name = self.texts.text(
            site.name_text_key,
            Localizer(self.settings.language),
            default=site.id,
        )
        text_factory = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
            role=SITE_NAME_FONT_ROLE,
        )
        self.site_name_site = site
        self.site_name_text = text_factory.create(
            name,
            0,
            0,
        )

    def _reset_field_actors(self) -> None:
        """Recreate transient actors and ambient birds when the active map changes."""

        guide = getattr(self, "field_menu_guide", None)
        if guide is not None:
            guide.reset()
        self.field_birds = (
            WorldMapBirds(SCREEN_WIDTH, SCREEN_HEIGHT)
            if isinstance(getattr(self, "current_map", None), CompiledMap)
            and self.current_map.map_id == WORLD_MAP_ID
            and self.current_map.profile == "world"
            else None
        )
        if not isinstance(getattr(self, "current_map", None), CompiledMap):
            self.field_actors = None
            self.field_prop_image = None
            self.field_actor_character_image = None
            self.field_actor_pc_character_image = None
            self.field_player_character_image = None
            self.field_treasure_image = None
            return
        self.field_actors = FieldActors(
            self.current_map,
            opened_treasure_ids=(
                treasure_id
                for map_id, treasure_id in self.save_data.opened_treasures
                if map_id == self.current_map.map_id
            ),
        )
        actors = self.field_actors.actors
        prop_actors = tuple(actor for actor in actors if actor.kind == "prop")
        npc_character_actors = tuple(
            actor
            for actor in actors
            if actor.kind in ("stationary", "roaming") and actor.sprite_source == "npc"
        )
        pc_character_actors = tuple(
            actor
            for actor in actors
            if actor.kind in ("stationary", "roaming") and actor.sprite_source == "pc"
        )
        treasure_actors = tuple(actor for actor in actors if actor.kind == "treasure")
        self.field_prop_image = None
        if prop_actors:
            entry = self.images.entry(FIELD_PROP_ASSET_ID)
            if entry.width % 16 or entry.height % 16:
                raise ImageResourceError(
                    f"{FIELD_PROP_ASSET_ID}の寸法は16pxの倍数である必要があります。"
                )
            prop_capacity = (entry.width // 16) * (entry.height // 16)
            if max(actor.sprite_index for actor in prop_actors) >= prop_capacity:
                raise ImageResourceError(
                    f"{FIELD_PROP_ASSET_ID}にactorのsprite_indexが参照するチップがありません。"
                )
            self.field_prop_image = self.images.image(FIELD_PROP_ASSET_ID)
        self.field_actor_character_image = None
        if npc_character_actors:
            entry = self.images.entry(FIELD_CHARACTER_ASSET_ID)
            if (
                entry.width % FIELD_ACTOR_CHARACTER_SET_WIDTH
                or entry.height % FIELD_ACTOR_CHARACTER_SET_HEIGHT
            ):
                raise ImageResourceError(
                    f"{FIELD_CHARACTER_ASSET_ID}の寸法は幅"
                    f"{FIELD_ACTOR_CHARACTER_SET_WIDTH}px、高さ"
                    f"{FIELD_ACTOR_CHARACTER_SET_HEIGHT}pxの倍数である必要があります。"
                )
            character_capacity = (entry.width // FIELD_ACTOR_CHARACTER_SET_WIDTH) * (
                entry.height // FIELD_ACTOR_CHARACTER_SET_HEIGHT
            )
            if (
                max(actor.sprite_index for actor in npc_character_actors)
                >= character_capacity
            ):
                raise ImageResourceError(
                    f"{FIELD_CHARACTER_ASSET_ID}にactorのsprite_indexが参照するキャラクターがありません。"
                )
            self.field_actor_character_image = self.images.image(
                FIELD_CHARACTER_ASSET_ID
            )
        self.field_actor_pc_character_image = None
        self.field_player_character_image = None
        uses_player_character_image = self.current_map.profile in (
            "town",
            "dungeon",
        )
        if uses_player_character_image or pc_character_actors:
            entry = self.images.entry(FIELD_PLAYER_CHARACTER_ASSET_ID)
            minimum_width = (
                FIELD_PLAYER_CHARACTER_SET_WIDTH * FIELD_PLAYER_CHARACTER_SETS_PER_ROW
            )
            if (
                entry.width < minimum_width
                or entry.width % FIELD_PLAYER_CHARACTER_SET_WIDTH
                or entry.height % FIELD_PLAYER_CHARACTER_SET_HEIGHT
            ):
                raise ImageResourceError(
                    f"{FIELD_PLAYER_CHARACTER_ASSET_ID}の寸法は幅{minimum_width}px以上の"
                    f"{FIELD_PLAYER_CHARACTER_SET_WIDTH}px単位、高さ"
                    f"{FIELD_PLAYER_CHARACTER_SET_HEIGHT}px単位である必要があります。"
                )
            required_sprite_indices = [
                actor.sprite_index for actor in pc_character_actors
            ]
            if uses_player_character_image:
                required_sprite_indices.append(self.party[0].definition.battle_sprite)
            for sprite_index in required_sprite_indices:
                source_x = (
                    sprite_index % FIELD_PLAYER_CHARACTER_SETS_PER_ROW
                ) * FIELD_PLAYER_CHARACTER_SET_WIDTH
                source_y = (
                    sprite_index // FIELD_PLAYER_CHARACTER_SETS_PER_ROW
                ) * FIELD_PLAYER_CHARACTER_SET_HEIGHT
                if (
                    source_x + FIELD_PLAYER_CHARACTER_SET_WIDTH > entry.width
                    or source_y + FIELD_PLAYER_CHARACTER_SET_HEIGHT > entry.height
                ):
                    raise ImageResourceError(
                        f"{FIELD_PLAYER_CHARACTER_ASSET_ID}にsprite_index "
                        f"{sprite_index}が参照する画像セットがありません。"
                    )
            character_image = self.images.image(FIELD_PLAYER_CHARACTER_ASSET_ID)
            if pc_character_actors:
                self.field_actor_pc_character_image = character_image
            if uses_player_character_image:
                self.field_player_character_image = character_image
        self.field_treasure_image = None
        if treasure_actors:
            entry = self.images.entry(FIELD_TREASURE_ASSET_ID)
            if entry.width != 48 or entry.height != 16:
                raise ImageResourceError(
                    f"{FIELD_TREASURE_ASSET_ID}の寸法は48x16pxである必要があります。"
                )
            self.field_treasure_image = self.images.image(FIELD_TREASURE_ASSET_ID)

    def _draw_site_name(self) -> None:
        """Draw the nearby-site name at a position fixed to the world map."""

        site = getattr(self, "site_name_site", None)
        text = getattr(self, "site_name_text", None)
        if site is None or not isinstance(text, WindowText):
            return
        camera_x, camera_y = self.field_renderer.camera_position(self.field)
        tile_size = self.current_map.tile_size
        min_x = min(cell.x for cell in site.entrance_cells)
        max_x = max(cell.x for cell in site.entrance_cells)
        min_y = min(cell.y for cell in site.entrance_cells)
        max_y = max(cell.y for cell in site.entrance_cells)
        left = min_x * tile_size
        right = (max_x + 1) * tile_size
        text_width = (
            text.font.text_width(text.text)
            if text.font is not None
            else pyxel.FONT_WIDTH * len(text.text)
        )
        x = (left + right - text_width) // 2 - camera_x
        line_height = self.fonts.line_height_for(
            self.settings.language,
            role=SITE_NAME_FONT_ROLE,
        )
        if self.field.position.y < min_y:
            y = (max_y + 1) * tile_size - camera_y + SITE_NAME_LABEL_GAP
        else:
            y = min_y * tile_size - camera_y - line_height - SITE_NAME_LABEL_GAP
        draw_tagged_text(
            x,
            y,
            text.text,
            text.color,
            text.font,
            shadow_color=text.shadow_color,
            text_y_offset=text.baseline_offset,
            font_spans=text.font_spans,
        )

    def _handle_arrived_site(self) -> None:
        """Enter a site only after movement completes on an entrance cell."""

        arrived = getattr(self.field, "arrived_position", None)
        if not isinstance(arrived, FieldPosition):
            return
        site = self.current_sites.entrance_at(arrived.x, arrived.y)
        if site is None:
            return
        if not self._stage_map_destination(site.destination):
            return
        self.pending_site = site
        self._begin_screen_change(GameScreenChange.CHANGE_MAP)

    def _stage_map_destination(self, destination: MapDestination) -> bool:
        """Resolve a map destination before starting a screen transition."""

        if not isinstance(destination, MapDestination):
            raise TypeError("map destination must be a MapDestination")
        try:
            target_map = self.map_resources.map(destination.map_id)
        except MapResourceError:
            return False
        try:
            arrival = target_map.arrival_point(destination.arrival_id)
        except KeyError:
            return False
        self.pending_target_map = target_map
        self.pending_target_arrival = arrival
        return True

    def _apply_pending_map_destination(self) -> None:
        """Replace the field using the destination resolved before fading."""

        target_map = self.pending_target_map
        arrival = self.pending_target_arrival
        if target_map is None or arrival is None:
            raise RuntimeError("map change has incomplete destination data")
        previous_map_id = getattr(
            getattr(self, "current_map", None),
            "map_id",
            None,
        )
        if target_map is getattr(self, "world_map", None):
            for member in self.party:
                member.recover_world_map_entry_ailments()
        self.current_map = target_map
        self.current_sites = WorldSiteCatalog(target_map.sites)
        self.field = FieldMovement(
            target_map,
            start=FieldPosition(arrival.position.x, arrival.position.y),
            facing=SITE_FACING_DIRECTIONS[arrival.facing],
        )
        self.field_renderer = FieldRenderer(
            target_map,
            screen_width=SCREEN_WIDTH,
            screen_height=SCREEN_HEIGHT,
        )
        self._reset_field_actors()
        if target_map.map_id != previous_map_id:
            self._reset_field_fade()
        self.bgm.play(target_map.bgm_id)
        self.pending_target_map = None
        self.pending_target_arrival = None
        self._refresh_site_name_label(force=True)

    def _apply_pending_site_change(self) -> None:
        site = self.pending_site
        if site is None:
            raise RuntimeError("site map change has no entered site")
        leaving_dungeon = (
            getattr(self.current_map, "profile", None) == "dungeon"
            and self.pending_target_map is self.world_map
        )
        if self.current_map is self.world_map:
            self.travel_system.enter_site(self.save_data, site)
        self._apply_pending_map_destination()
        self.pending_site = None
        if leaving_dungeon:
            self._queue_hint_after_fade(FIRST_DUNGEON_EXIT_HINT_ID)

    def _party_window_texts(
        self,
        party: tuple[Member, ...],
        localized: dict[str, str],
        text_factory: LocalizedWindowTextFactory,
    ) -> tuple[WindowText, ...]:
        """Build up to six compact name/HP/MP rows for the main window."""

        localizer = Localizer(self.settings.language)
        texts: list[WindowText] = []
        row_height = self._member_row_height_grid(len(party))
        for index, member in enumerate(party):
            is_reserve = (
                len(party) > BATTLE_PARTY_MEMBER_COUNT and index == len(party) - 1
            )
            row_y = (
                2
                + index * row_height
                + (RESERVE_MEMBER_Y_OFFSET_GRID if is_reserve else 0)
            )
            base_color = RESERVE_MEMBER_TEXT_COLOR if is_reserve else DEFAULT_TEXT_COLOR
            name = member.definition.localized_name(localizer)
            if is_reserve:
                name += localized["term.formation.reserve"]
            texts.extend(
                (
                    text_factory.create(
                        name,
                        PARTY_NAME_TEXT_X,
                        row_y,
                        color=base_color,
                    ),
                    text_factory.create(
                        self._point_text(
                            localized["menu.member.hp"],
                            member.hp,
                            member.max_hp,
                        ),
                        PARTY_POINT_TEXT_X,
                        row_y + 3,
                        color=base_color,
                    ),
                    text_factory.create(
                        self._point_text(
                            localized["menu.member.mp"],
                            member.mp,
                            member.max_mp,
                        ),
                        PARTY_POINT_TEXT_X,
                        row_y + 6,
                        color=(DISABLED_COLOR if member.max_mp == 0 else base_color),
                    ),
                )
            )
            condition = member.status(
                localizer,
                self.texts,
            )
            if condition:
                texts.append(
                    text_factory.create(
                        condition,
                        PARTY_STATUS_TEXT_X,
                        row_y,
                        color=NEGATIVE_COLOR,
                    )
                )
                continue
            amount = member.heal_and_poison_amount
            if amount:
                sign = "＋" if amount > 0 else "－"
                texts.append(
                    text_factory.create(
                        f"（{sign}{format_number(abs(amount))}）",
                        PARTY_RECOVERY_TEXT_X,
                        row_y + 3,
                        color=(POSITIVE_COLOR if amount > 0 else NEGATIVE_COLOR),
                    )
                )
        return tuple(texts)

    def _main_menu_members(self) -> tuple[Member, ...]:
        """Return all members, with the final member acting as reserve."""

        return self.party

    def _is_reserve_index(self, index: int) -> bool:
        return (
            len(self.party) > BATTLE_PARTY_MEMBER_COUNT and index == len(self.party) - 1
        )

    def _member_y_offset_grid(self, index: int) -> int:
        return RESERVE_MEMBER_Y_OFFSET_GRID if self._is_reserve_index(index) else 0

    @staticmethod
    def _member_row_height_grid(member_count: int) -> int:
        return (
            PARTY_MEMBER_ROW_HEIGHT
            if member_count > BATTLE_PARTY_MEMBER_COUNT
            else PARTY_MEMBER_ROW_HEIGHT_WITHOUT_RESERVE
        )

    def _force_reserve_front(self) -> None:
        """Keep the reserve ready to enter an all-back active party safely."""

        if len(self.party) > BATTLE_PARTY_MEMBER_COUNT:
            self.party[-1].formation_row = FormationRow.FRONT

    @staticmethod
    def _point_text(label: str, current: int, maximum: int) -> str:
        return f"{label}　{pad(current, 3)}／{pad(maximum, 3)}"

    def _sort_cursor_targets(self) -> tuple[CursorTarget, ...]:
        row_height = self._member_row_height_grid(len(self.party))
        return tuple(
            CursorTarget(
                PARTY_CURSOR_X,
                PARTY_CURSOR_Y + index * row_height + self._member_y_offset_grid(index),
                key=index,
            )
            for index in range(len(self.party))
        )

    def _sort_source_target(self, index: int) -> CursorTarget:
        target = self._sort_cursor_targets()[index]
        return CursorTarget(
            target.x + SORT_SOURCE_CURSOR_X_OFFSET,
            target.y,
            key=target.key,
        )

    def _start_sort(self) -> None:
        self.command_cursor.active = False
        self.party_cursor = self.party_window.set_cursor(self._sort_cursor_targets())
        selected_member_index = getattr(self, "selected_member_index", 0)
        if selected_member_index != 0:
            self._select_cursor_key(self.party_cursor, selected_member_index)

    def _finish_sort(self) -> None:
        self._clear_sort_source()
        self.party_window.clear_cursor()
        self.party_cursor = None
        self.command_cursor.active = True

    def _clear_sort_source(self) -> None:
        self.sort_source_index = None
        self.sort_source_cursor = None

    def _can_change_formation(self, member: Member) -> bool:
        if self._is_reserve_index(len(self.party) - 1) and self.party[-1] is member:
            return not member.is_front_row
        if not member.is_front_row:
            return True
        return any(
            party_member is not member
            and party_member.is_front_row
            and self._member_is_field_recoverable(party_member)
            for party_member in self.party[:BATTLE_PARTY_MEMBER_COUNT]
        )

    def _party_has_recoverable_front(self, party: tuple[Member, ...]) -> bool:
        return any(
            member.is_front_row and self._member_is_field_recoverable(member)
            for member in party[:BATTLE_PARTY_MEMBER_COUNT]
        )

    def _confirm_sort_member(self) -> None:
        if self.party_cursor is None:
            return
        target_index = self.party_cursor.selected_key
        if not isinstance(target_index, int) or not 0 <= target_index < len(self.party):
            return

        if self.sort_source_index is None:
            self.sort_source_index = target_index
            self.sort_source_cursor = WindowCursor(
                self.party_window,
                (self._sort_source_target(target_index),),
                active=False,
                draw_shadow=False,
            )
            return

        source_index = self.sort_source_index
        if source_index == target_index:
            member = self.party[target_index]
            if not self._can_change_formation(member):
                self.alert.start()
            elif member.is_front_row:
                member.formation_row = FormationRow.BACK
            else:
                member.formation_row = FormationRow.FRONT
        else:
            party = list(self.party)
            party[source_index], party[target_index] = (
                party[target_index],
                party[source_index],
            )
            sorted_party = tuple(party)
            if not self._party_has_recoverable_front(sorted_party):
                self.alert.start()
            else:
                self.party = sorted_party
                self._force_reserve_front()
                self._refresh_party_window_texts()
        self._clear_sort_source()

    def _refresh_party_window_texts(self) -> None:
        self.party_window.clear_texts()
        for placement in self._party_window_texts(
            self._main_menu_members(),
            self.localized,
            self.localized_texts,
        ):
            self.party_window.add_text(
                placement.text,
                placement.x,
                placement.y,
                color=placement.color,
                font=placement.font,
                shadow_color=placement.shadow_color,
                baseline_offset=placement.baseline_offset,
                font_spans=placement.font_spans,
            )

    def _main_info_window_texts(self) -> tuple[WindowText, ...]:
        """Build menu information from the current shared save state."""

        return (
            self.localized_texts.create(self.localized["menu.info.gold"], 2, 1),
            WindowText(pad(self.save_data.gold, 6), 2, 4),
            self.localized_texts.create(
                self.localized["menu.info.experience"],
                2,
                7,
            ),
            WindowText(pad(self.save_data.experience, 6), 2, 10),
            self.localized_texts.create(
                self.localized["menu.info.difficulty"],
                2,
                13,
            ),
            self.localized_texts.create(
                self.localized[DIFFICULTY_TEXT_KEYS[self.save_data.difficulty]],
                4,
                16,
            ),
            self.localized_texts.create(
                self.localized["menu.info.play_time"],
                2,
                19,
            ),
            WindowText(
                "　"
                + format_play_time(
                    self.save_data.play_time_frames,
                    fps=FPS,
                    include_seconds=False,
                ),
                2,
                22,
            ),
        )

    def _refresh_info_window_texts(self) -> None:
        """Refresh values that can change while the field is being shown."""

        self.info_window.clear_texts()
        for placement in self._main_info_window_texts():
            self.info_window.add_text(
                placement.text,
                placement.x,
                placement.y,
                color=placement.color,
                font=placement.font,
                shadow_color=placement.shadow_color,
                baseline_offset=placement.baseline_offset,
                font_spans=placement.font_spans,
            )

    def _settings_value(self, key: str) -> str:
        if key == "language":
            return self.localized[f"settings.language.{self.settings.language.value}"]
        if key == "bgm":
            return format_number(self.settings.bgm_volume)
        if key == "se":
            return format_number(self.settings.se_volume)
        if key == "screen_size":
            if self.settings.screen_scale == 5:
                return self.localized["settings.screen_size.fullscreen"]
            return (
                f"{format_number(self.settings.screen_scale * 256)}"
                f"×{format_number(self.settings.screen_scale * 240)}"
            )
        if key == "display":
            return self.localized[
                f"settings.display.{self.settings.display_mode.value}"
            ]
        if key == "screen_flash":
            value = "normal" if self.settings.screen_flash_enabled else "reduced"
            return self.localized[f"settings.screen_flash.{value}"]
        if key == "in_game_hints":
            value = "on" if self.settings.in_game_hints_enabled else "off"
            return self.localized[f"settings.{value}"]
        if key == "command_memory":
            value = "on" if self.settings.remember_battle_commands else "off"
            return self.localized[f"settings.{value}"]
        if key == "auto_spells":
            mode = self.settings.auto_battle_spell_mode.value
            return self.localized[f"settings.auto_spells.{mode}"]
        raise ValueError(f"settings key has no value: {key}")

    def _settings_window_texts(
        self,
        selected_key: str,
    ) -> tuple[WindowText, ...]:
        texts: list[WindowText] = []
        label_keys = {
            "language": "settings.language.label",
            "bgm": "settings.bgm.label",
            "se": "settings.se.label",
            "screen_size": "settings.screen_size.label",
            "display": "settings.display.label",
            "screen_flash": "settings.screen_flash.label",
            "in_game_hints": "settings.in_game_hints.label",
            "command_memory": "settings.command_memory.label",
            "auto_spells": "settings.auto_spells.label",
        }
        action_keys = {
            "return_title": "settings.return_title",
            "quit": "settings.quit",
        }
        for key, y in SETTINGS_ROWS:
            if key in label_keys:
                texts.extend(
                    (
                        self.localized_texts.create(
                            self.localized[label_keys[key]],
                            SETTINGS_LABEL_X,
                            y,
                        ),
                        self.localized_texts.create("：", 28, y),
                        self.localized_texts.create(
                            self._settings_value(key),
                            SETTINGS_VALUE_X,
                            y,
                        ),
                    )
                )
            else:
                text_factory = (
                    self.debug_texts if key == "debug" else self.localized_texts
                )
                text = (
                    DEBUG_TEXT.settings_menu
                    if key == "debug"
                    else self.localized[action_keys[key]]
                )
                texts.append(
                    text_factory.create(
                        text,
                        SETTINGS_LABEL_X,
                        y,
                        color=(
                            NEGATIVE_COLOR if key == "debug" else DEFAULT_TEXT_COLOR
                        ),
                    )
                )
        guide_key = SETTINGS_GUIDE_KEYS.get(selected_key)
        guide_lines = (
            self.texts.lines(guide_key, Localizer(self.settings.language))
            if guide_key is not None
            else ()
        )
        for index, line in enumerate(guide_lines):
            text_factory = (
                LocalizedWindowTextFactory.from_language(
                    self.fonts,
                    Language.ENGLISH,
                )
                if selected_key == "language" and index == 1
                else self.localized_texts
            )
            texts.append(
                text_factory.create(
                    line,
                    SETTINGS_GUIDE_X,
                    SETTINGS_GUIDE_Y + index * SETTINGS_GUIDE_ROW_HEIGHT,
                )
            )
        return tuple(texts)

    def _build_settings_window(self, selected_key: str = "language") -> None:
        texts = self._settings_window_texts(selected_key)

        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        self.settings_window = windows.create(
            *SETTINGS_WINDOW_GRID,
            texts,
            opened=False,
        )
        self.settings_cursor = self.settings_window.set_cursor(
            tuple(
                CursorTarget(SETTINGS_CURSOR_X, y, key=key) for key, y in SETTINGS_ROWS
            )
        )
        self._select_cursor_key(self.settings_cursor, selected_key)
        self.settings_window.open()

    def _refresh_settings_window(self, selected_key: str) -> None:
        if self.settings_window is None:
            return
        self.settings_window.clear_texts()
        for placement in self._settings_window_texts(selected_key):
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

    def _start_settings(self) -> None:
        self.command_cursor.active = False
        self._build_settings_window()

    def _start_debug_menu(self) -> None:
        if self.settings_cursor is None:
            return
        self.settings_cursor.active = False
        editor = DebugPartyEditor(
            self.character_records,
            items=self.items,
            skills=self.skills,
            party=self.party,
        )
        self.debug_screen = DebugMenuOverlay(
            editor=editor,
            inventory_system=self.inventory_system,
            save_data=self.save_data,
            settings=self.settings,
            fonts=self.fonts,
            alert=self.alert,
            teleport_targets=self._teleport_targets(),
            on_teleport=self._start_debug_teleport,
            shop_targets=self._debug_shop_targets(),
            on_shop=self._start_debug_shop,
        )

    def _teleport_targets(self) -> tuple[TeleportTarget, ...]:
        """Build localized choices accepted by the real teleport rules."""

        localizer = Localizer(self.settings.language)
        return tuple(
            TeleportTarget(
                site.id,
                self.texts.text(
                    site.name_text_key,
                    localizer,
                    default=site.id,
                ),
            )
            for site in self.travel_system.teleport_destinations(self.save_data)
        )

    def _debug_teleport_targets(self) -> tuple[TeleportTarget, ...]:
        """Retain the development-menu entry point for focused harnesses."""

        return self._teleport_targets()

    def _debug_shop_targets(self) -> tuple[DebugShopTarget, ...]:
        """Expose every loaded shop to the development-only selector."""

        return tuple(DebugShopTarget(shop.key, shop.key) for shop in self.shops)

    def _apply_debug_party_changes(self) -> None:
        """Commit editor state before another production overlay uses it."""

        if self.debug_screen is None:
            return
        self.party = self.debug_screen.party
        save_data = getattr(self, "save_data", None)
        if isinstance(save_data, SaveData):
            save_data.auto_recovery = valid_config_for_party(
                save_data.auto_recovery, self.party
            )
        character_states = getattr(self, "character_states", {})
        character_states.update(
            (member.definition.key, member) for member in self.party
        )
        self.character_states = character_states
        party_system = getattr(self, "party_system", None)
        if party_system is not None:
            party_system.replace(
                self.party,
                character_states=self.character_states,
            )
        self._force_reserve_front()
        self.selected_member_index = min(
            self.selected_member_index,
            len(self.party) - 1,
        )

    def _start_debug_shop(self, shop_key: str) -> bool:
        """Stage a debug-selected shop and open the production shop overlay."""

        shop = next((shop for shop in self.shops if shop.key == shop_key), None)
        if shop is None:
            return False
        self._apply_debug_party_changes()
        self.pending_shop = shop
        self.shop_return_to_debug = True
        self._begin_screen_change(GameScreenChange.OPEN_SHOP)
        return True

    def _start_debug_teleport(self, site_id: str) -> bool:
        """Stage one debug-selected destination through the shared travel path."""

        return self._start_teleport(site_id, source="debug")

    def _start_field_teleport(self, site_id: str) -> bool:
        """Stage one TELEPORT destination selected from the field spell menu."""

        return self._start_teleport(site_id, source="spell")

    def _start_item_teleport(self, site_id: str) -> bool:
        """Stage one destination selected with a field teleport item."""

        return self._start_teleport(site_id, source="item")

    def _start_teleport(self, site_id: str, *, source: str) -> bool:
        """Resolve one visited destination and begin the common teleport fade."""

        if source not in ("debug", "spell", "item"):
            raise ValueError(f"unsupported teleport source: {source}")

        try:
            destination = self.travel_system.teleport_destination(
                self.save_data,
                site_id,
            )
        except (MapResourceError, ValueError):
            return False
        if not self._stage_map_destination(destination):
            return False
        self.pending_site = None
        self.pending_teleport_source = source
        self._begin_screen_change(GameScreenChange.TELEPORT)
        pyxel.play(TELEPORT_SOUND_CHANNEL, TELEPORT_SOUND_ID)
        return True

    def _finish_debug_menu(self, *, resume_settings: bool = True) -> None:
        if self.debug_screen is None:
            return
        self._apply_debug_party_changes()
        self.debug_screen = None
        self._build_main_windows(selected_command="config", animate=False)
        self.command_cursor.active = not resume_settings
        if resume_settings:
            if self.settings_cursor is not None:
                self.settings_cursor.active = True
        else:
            self.settings_window = None
            self.settings_cursor = None

    def _apply_pending_teleport(self) -> None:
        """Apply shared debug/spell/item teleport state and return to the field."""

        source = getattr(self, "pending_teleport_source", None)
        if source == "debug":
            self._finish_debug_menu(resume_settings=False)
        elif source == "spell":
            if self.spell_screen is not None:
                self.selected_member_index = self.spell_screen.member_index
            self.spell_screen = None
            self._refresh_party_window_texts()
        elif source == "item":
            self.item_screen = None
        else:
            raise RuntimeError("teleport has no pending source")
        self._apply_pending_map_destination()
        self.showing_field = True
        self.pending_teleport_source = None

    def _start_status(self) -> None:
        self.command_cursor.active = False
        self.status_screen = StatusMenuOverlay(
            party=self.party,
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
            faces=self.faces,
            palette_shifter=self.palette_shifter,
            member_index=self.selected_member_index,
        )
        self.menu_member_selected = True

    def _start_item(self) -> None:
        self.command_cursor.active = False
        inventory_system = getattr(self, "inventory_system", None)
        if inventory_system is None:
            inventory_system = InventorySystem.with_one_each(self.items)
            self.inventory_system = inventory_system
        self.item_screen = ItemMenuOverlay(
            party=self.party,
            items=self.items,
            spells=self.spells,
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
            faces=self.faces,
            palette_shifter=self.palette_shifter,
            inventory_system=inventory_system,
            on_field_fade=self._activate_field_fade,
            teleport_targets=self._teleport_targets(),
            on_field_teleport=self._start_item_teleport,
            on_invalid_action=self.alert.start,
        )

    def _start_auto_recovery(self) -> None:
        self.command_cursor.active = False
        self.save_data.auto_recovery = valid_config_for_party(
            self.save_data.auto_recovery, self.party
        )
        self.auto_recovery_screen = AutoRecoveryOverlay(
            party=self.party,
            spells=self.spells,
            items=self.items,
            inventory=self.inventory_system,
            save_data=self.save_data,
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
            faces=self.faces,
            palette_shifter=self.palette_shifter,
        )

    def _finish_auto_recovery(self) -> None:
        self.auto_recovery_screen = None
        self._refresh_party_window_texts()
        self.command_cursor.active = True

    def _finish_item(self) -> None:
        self.item_screen = None
        self.command_cursor.active = True

    def _start_equipment(self) -> None:
        self.command_cursor.active = False
        self.equipment_screen = EquipmentMenuOverlay(
            party=self.party,
            items=self.items,
            spells=self.spells,
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
            faces=self.faces,
            inventory_system=self.inventory_system,
            member_index=self.selected_member_index,
            on_invalid_action=self.alert.start,
        )
        self.menu_member_selected = True

    def _finish_equipment(self) -> None:
        if self.equipment_screen is None:
            return
        self.selected_member_index = self.equipment_screen.member_index
        self.equipment_screen = None
        self._refresh_party_window_texts()
        self.command_cursor.active = True

    def _finish_status(self) -> None:
        if self.status_screen is None:
            return
        status_settings = self.status_screen.settings
        self.selected_member_index = self.status_screen.member_index
        self.status_screen = None
        if status_settings != self.settings:
            self.settings = status_settings
            self._build_main_windows(
                selected_command="status",
                animate=False,
            )
        else:
            self.command_cursor.active = True

    def _start_information(self) -> None:
        self.command_cursor.active = False
        self.information_screen = InformationMenuOverlay(
            monsters=self.monsters,
            monster_records=self.save_data.monster_records,
            items=self.items,
            logs=self.save_data.logs,
            mission_message_ids=tuple(
                mission.message_id
                for mission in self.event_catalog.missions
                if mission.condition is None
                or evaluate_condition(
                    mission.condition,
                    save_data=self.save_data,
                    party=self.party_system,
                    inventory=self.inventory_system,
                )
            ),
            settings=self.settings,
            texts=self.texts,
            event_messages=self.event_messages,
            fonts=self.fonts,
            images=self.images,
            on_invalid_action=self.alert.start,
        )

    def _finish_information(self) -> None:
        self.information_screen = None
        self.command_cursor.active = True

    def _begin_screen_change(self, change: GameScreenChange) -> None:
        """Reserve one menu-related screen replacement and begin fading out."""

        if not isinstance(change, GameScreenChange):
            raise TypeError("field screen change must be a GameScreenChange")
        if getattr(self, "pending_screen_change", None) is not None:
            raise RuntimeError("field screen change is already pending")
        frame_count = (
            SITE_MAP_FADE_FRAME_COUNT
            if change
            in (
                GameScreenChange.CHANGE_MAP,
                GameScreenChange.TELEPORT,
            )
            else DEFAULT_FADE_FRAME_COUNT
        )
        fade = getattr(self, "fade", None)
        if fade is None or fade.frame_count != frame_count:
            fade = FadeThroughBlack(frame_count)
            self.fade = fade
        self.pending_screen_change = change
        self.fade_bgm = change in (
            GameScreenChange.CHANGE_MAP,
            GameScreenChange.TELEPORT,
            GameScreenChange.START_GAME,
        )
        if change in (
            GameScreenChange.SHOW_FIELD,
            GameScreenChange.OPEN_RECOVERY,
            GameScreenChange.OPEN_ITEM,
            GameScreenChange.OPEN_SPELL,
            GameScreenChange.OPEN_EQUIPMENT,
            GameScreenChange.OPEN_STATUS,
            GameScreenChange.OPEN_INFO,
            GameScreenChange.OPEN_SAVE,
        ):
            self.command_cursor.active = False
        fade.start()

    def _apply_pending_screen_change(self) -> None:
        """Apply the reserved replacement at the fully black midpoint."""

        change = self.pending_screen_change
        if change is None:
            raise RuntimeError("fade midpoint has no pending field screen change")
        if change is GameScreenChange.SHOW_FIELD:
            self.showing_field = True
            if getattr(self, "field_fade_active", False):
                self._sync_field_fade_palette()
            else:
                self._restore_dimmed_palette()
        elif change is GameScreenChange.SHOW_MENU:
            self.showing_field = False
            self._restore_dimmed_palette()
            self.selected_member_index = 0
            self.menu_member_selected = False
            self._refresh_party_window_texts()
            self._refresh_info_window_texts()
            self.command_cursor.active = True
            self._restart_main_windows_for_fade_in()
        elif change is GameScreenChange.OPEN_ITEM:
            self._start_item()
        elif change is GameScreenChange.OPEN_RECOVERY:
            self._start_auto_recovery()
        elif change is GameScreenChange.CLOSE_RECOVERY:
            self._finish_auto_recovery()
        elif change is GameScreenChange.CLOSE_ITEM:
            self._finish_item()
        elif change is GameScreenChange.OPEN_SPELL:
            self._start_spell()
        elif change is GameScreenChange.CLOSE_SPELL:
            self._finish_spell()
        elif change is GameScreenChange.OPEN_EQUIPMENT:
            self._start_equipment()
        elif change is GameScreenChange.CLOSE_EQUIPMENT:
            self._finish_equipment()
        elif change is GameScreenChange.OPEN_STATUS:
            self._start_status()
        elif change is GameScreenChange.CLOSE_STATUS:
            self._finish_status()
        elif change is GameScreenChange.OPEN_INFO:
            self._start_information()
        elif change is GameScreenChange.CLOSE_INFO:
            self._finish_information()
        elif change is GameScreenChange.OPEN_SAVE:
            self._start_save()
        elif change is GameScreenChange.CLOSE_SAVE:
            self._finish_save()
        elif change is GameScreenChange.OPEN_SHOP:
            self.showing_field = False
            self._start_shop()
        elif change is GameScreenChange.CLOSE_SHOP:
            return_to_debug = (
                getattr(self, "shop_return_to_debug", False)
                and self.debug_screen is not None
            )
            self._finish_shop()
            self.shop_return_to_debug = False
            self.showing_field = not return_to_debug
            effect = getattr(self, "event_effect", None)
            runner = getattr(self, "event_runner", None)
            if (
                not return_to_debug
                and isinstance(effect, OpenShopEffect)
                and runner is not None
            ):
                runner.complete_effect(effect)
                self.event_effect = None
                self.event_resume_after_fade = True
        elif change is GameScreenChange.CHANGE_MAP:
            self._apply_pending_site_change()
        elif change is GameScreenChange.TELEPORT:
            self._apply_pending_teleport()
        elif change is GameScreenChange.START_GAME:
            self._apply_start_game()
        else:
            raise RuntimeError(f"unsupported field screen change: {change}")
        self.pending_screen_change = None
        self.auto_save_after_fade = change in (
            GameScreenChange.CHANGE_MAP,
            GameScreenChange.TELEPORT,
        )

    def _restart_main_windows_for_fade_in(self) -> None:
        """Synchronize the eight-frame window opening with fade-in."""

        for window in self.windows:
            window.restart_opening()
        hidden_frames = max(
            0,
            WINDOW_ANIMATION_FRAME_COUNT - self.fade.frame_count,
        )
        for _frame in range(hidden_frames):
            for window in self.windows:
                window.update()
        self.animate_main_windows_with_fade = True

    def _update_fade(self) -> bool:
        """Advance the active fade, update palette colors, and block input."""

        fade = getattr(self, "fade", None)
        if fade is None or not fade.is_active:
            return False
        was_fading_in = fade.phase is FadePhase.FADING_IN
        event = fade.update()
        self.palette_shifter.set_global_mix(
            base_rate=fade.visible_rate,
            target_color=self.palette_shifter.base_colors[0],
        )
        if getattr(self, "fade_bgm", False):
            self.bgm.set_fade_rate(fade.visible_rate)
        if event is FadeEvent.COVERED:
            self._apply_pending_screen_change()
            if getattr(self, "fade_bgm", False):
                self.bgm.set_fade_rate(1.0)
                self.fade_bgm = False
        elif was_fading_in and getattr(
            self,
            "animate_main_windows_with_fade",
            False,
        ):
            self._update_window_animations()
            if event is FadeEvent.FINISHED:
                self.animate_main_windows_with_fade = False
        if event is FadeEvent.FINISHED:
            self.fade_bgm = False
            self._show_pending_hint_after_fade()
            if getattr(self, "auto_save_after_fade", False):
                self.auto_save_after_fade = False
                self._auto_save()
            if getattr(self, "event_resume_after_fade", False):
                self.event_resume_after_fade = False
                try:
                    self._continue_event()
                except (
                    KeyError,
                    EventRuntimeError,
                    EventMessageDataError,
                    AudioResourceError,
                    ValueError,
                ) as error:
                    self._abort_event(error)
        return True

    def _start_spell(self) -> None:
        self.command_cursor.active = False
        member_index = (
            self.selected_member_index
            if getattr(self, "menu_member_selected", True)
            else None
        )
        self.spell_screen = SpellMenuOverlay(
            party=self.party,
            spells=self.spells,
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
            faces=self.faces,
            palette_shifter=self.palette_shifter,
            member_index=member_index,
            on_field_fade=self._activate_field_fade,
            teleport_targets=self._teleport_targets(),
            on_field_teleport=self._start_field_teleport,
            on_invalid_action=self.alert.start,
        )
        if member_index is None:
            self.selected_member_index = self.spell_screen.member_index
        self.menu_member_selected = True

    def _start_save(self) -> None:
        self.command_cursor.active = False
        self.save_screen = SaveMenuOverlay(
            summaries=self.save_repository.summaries(),
            current_slot=self.current_save_slot,
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
            faces=self.faces,
            face_positions=self.character_face_positions,
            palette_shifter=self.palette_shifter,
            on_save=self._save_to_slot,
            on_invalid_action=self.alert.start,
        )

    def _finish_save(self) -> None:
        self.save_screen = None
        self.command_cursor.active = True

    def _save_to_slot(self, slot: int) -> SaveSlotSummary | None:
        try:
            document = create_save_document(
                save_data=self.save_data,
                active_party=self.party,
                character_states=self.character_states,
                inventory=self.inventory_system,
                map_id=self.current_map.map_id,
                position=self.field.position,
                facing=self.field.facing,
                battle_command_memory=getattr(self, "battle_command_memory", None),
            )
            summary = self.save_repository.save(slot, document)
        except (SaveSystemError, TypeError, ValueError):
            return None
        if slot != AUTO_SAVE_SLOT:
            self.current_save_slot = slot
        return summary

    def _auto_save(self) -> None:
        """Persist a completed field arrival without changing the manual slot."""

        self._save_to_slot(AUTO_SAVE_SLOT)

    def _start_new_game(self) -> None:
        """Fade from the opening selector into the initialized new game."""

        self.pending_loaded_state = None
        self.pending_load_slot = None
        self._begin_screen_change(GameScreenChange.START_GAME)

    def _load_from_slot(self, slot: int) -> bool:
        """Validate and stage one slot before starting the screen transition."""

        try:
            document = self.save_repository.load(slot)
            loaded = restore_save_document(
                document,
                character_records=self.character_records,
                items=self.items,
                skills=self.skills,
            )
            target_map = self.map_resources.map(loaded.map_id)
            target_field = FieldMovement(
                target_map,
                start=loaded.position,
                facing=loaded.facing,
                allow_blocked_start=True,
            )
            target_renderer = FieldRenderer(
                target_map,
                screen_width=SCREEN_WIDTH,
                screen_height=SCREEN_HEIGHT,
            )
        except (SaveSystemError, MapResourceError, TypeError, ValueError):
            return False
        self.pending_loaded_state = loaded
        self.pending_loaded_map = target_map
        self.pending_loaded_field = target_field
        self.pending_loaded_renderer = target_renderer
        self.pending_load_slot = slot
        self._begin_screen_change(GameScreenChange.START_GAME)
        return True

    def _delete_save_slot(self, slot: int) -> bool:
        try:
            self.save_repository.delete(slot)
        except (SaveSystemError, TypeError, ValueError):
            return False
        return True

    def _apply_start_game(self) -> None:
        """Commit staged loaded state at the fully black fade midpoint."""

        loaded = self.pending_loaded_state
        is_new_game = loaded is None
        if loaded is not None:
            if (
                self.pending_loaded_map is None
                or self.pending_loaded_field is None
                or self.pending_loaded_renderer is None
                or self.pending_load_slot is None
            ):
                raise RuntimeError("loaded game has incomplete staged field state")
            self.save_data = loaded.save_data
            self.party = loaded.active_party
            self.save_data.auto_recovery = valid_config_for_party(
                self.save_data.auto_recovery, self.party
            )
            self.character_states = loaded.character_states
            self.inventory_system = loaded.inventory
            self.current_map = self.pending_loaded_map
            self.current_sites = WorldSiteCatalog(self.current_map.sites)
            self.field = self.pending_loaded_field
            self.field_renderer = self.pending_loaded_renderer
            self.current_save_slot = (
                self.pending_load_slot
                if self.pending_load_slot != AUTO_SAVE_SLOT
                else None
            )
            self.shop_system = ShopSystem(
                shops=self.shops,
                inventory=self.inventory_system,
                party=self.party,
                save_data=self.save_data,
            )
            if hasattr(self, "character_records"):
                self.party_system = PartySystem(
                    character_records=self.character_records,
                    items=self.items,
                    skills=self.skills,
                    active_party=self.party,
                    character_states=self.character_states,
                )
            self.treasure_system = TreasureSystem(
                save_data=self.save_data,
                inventory=self.inventory_system,
            )
            self._reset_field_actors()
            self.selected_member_index = 0
            self._build_main_windows(animate=False)
        self.battle_command_memory = (
            loaded.battle_command_memory
            if loaded is not None
            else BattleCommandMemory()
        )
        if not self.settings.remember_battle_commands:
            self.battle_command_memory.clear()
        self.pending_loaded_state = None
        self.pending_loaded_map = None
        self.pending_loaded_field = None
        self.pending_loaded_renderer = None
        self.pending_load_slot = None
        self.start_screen = None
        self.showing_field = True
        self._reset_field_fade()
        self._refresh_site_name_label(force=True)
        self.bgm.play(self.current_map.bgm_id)
        if is_new_game:
            self._start_field_event(NEW_GAME_EVENT_ID)
        elif self.settings.in_game_hints_enabled and not getattr(
            self,
            "_load_mission_hint_shown_this_launch",
            False,
        ):
            self.hint_overlay = HintOverlay(
                text_key="hint.load.mission",
                settings=self.settings,
                texts=self.texts,
                fonts=self.fonts,
            )
            self._load_mission_hint_shown_this_launch = True

    def _finish_spell(self) -> None:
        if self.spell_screen is None:
            return
        self.selected_member_index = self.spell_screen.member_index
        self.menu_member_selected = True
        self.spell_screen = None
        self._refresh_party_window_texts()
        self.command_cursor.active = True

    def _start_shop(self) -> None:
        shop = self.pending_shop
        if shop is None:
            raise GameDataError("選択されたショップがありません")
        self.shop_system = ShopSystem(
            shops=self.shops,
            inventory=self.inventory_system,
            party=self.party,
            save_data=self.save_data,
        )
        self.shop_screen = ShopOverlay(
            shop=shop,
            shop_system=self.shop_system,
            party=self.party,
            inventory_system=self.inventory_system,
            save_data=self.save_data,
            spells=self.spells,
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
            faces=self.faces,
            palette_shifter=self.palette_shifter,
            on_invalid_action=self.alert.start,
        )
        self.pending_shop = None

    def _finish_shop(self) -> None:
        self.shop_screen = None
        self.pending_shop = None

    def _finish_settings(self) -> None:
        self.settings_window = None
        self.settings_cursor = None
        self.command_cursor.active = True

    def _change_setting(self, distance: int) -> None:
        if distance not in (-1, 1) or self.settings_cursor is None:
            raise ValueError("settings distance must be -1 or 1")
        key = self.settings_cursor.selected_key
        if key == "language":
            index = LANGUAGE_SEQUENCE.index(self.settings.language)
            language = LANGUAGE_SEQUENCE[(index + 1) % len(LANGUAGE_SEQUENCE)]
            updated_settings = self.settings.with_language(language)
        elif key == "bgm":
            volume = (self.settings.bgm_volume + distance) % 5
            updated_settings = self.settings.with_bgm_volume(volume)
        elif key == "se":
            volume = (self.settings.se_volume + distance) % 5
            updated_settings = self.settings.with_se_volume(volume)
        elif key == "screen_size":
            scale = (self.settings.screen_scale - 1 + distance) % 5 + 1
            updated_settings = self.settings.with_screen_scale(scale)
        elif key == "display":
            index = DISPLAY_SEQUENCE.index(self.settings.display_mode)
            mode = DISPLAY_SEQUENCE[(index + distance) % len(DISPLAY_SEQUENCE)]
            updated_settings = self.settings.with_display_mode(mode)
        elif key == "in_game_hints":
            updated_settings = self.settings.with_in_game_hints_enabled(
                not self.settings.in_game_hints_enabled
            )
        elif key == "screen_flash":
            updated_settings = self.settings.with_screen_flash_enabled(
                not self.settings.screen_flash_enabled
            )
        elif key == "command_memory":
            updated_settings = self.settings.with_remember_battle_commands(
                not self.settings.remember_battle_commands
            )
        elif key == "auto_spells":
            sequence = tuple(SpellMode)
            index = sequence.index(self.settings.auto_battle_spell_mode)
            updated_settings = self.settings.with_auto_battle_spell_mode(
                sequence[(index + distance) % len(sequence)]
            )
        else:
            return

        try:
            self.settings_repository.save(updated_settings)
        except SettingsSystemError:
            self.alert.start()
            return
        self.settings = updated_settings
        if key == "command_memory" and not updated_settings.remember_battle_commands:
            memory = getattr(self, "battle_command_memory", None)
            if memory is not None:
                memory.clear()

        if key == "language":
            self._build_main_windows(
                selected_command="config",
                animate=False,
            )
            self.command_cursor.active = False
        elif key == "bgm":
            self.bgm.set_volume(self.settings.bgm_volume)
        elif key == "se":
            self._apply_se_volume()
            pyxel.play(ALERT_CHANNEL, SE_PREVIEW_SOUND_ID)
        elif key == "display":
            self._apply_display_mode()
        self._refresh_settings_window(selected_key=key)

    def _apply_se_volume(self) -> None:
        gain = SE_VOLUME_GAINS[self.settings.se_volume]
        for channel in SE_CHANNELS:
            if len(pyxel.channels) > channel:
                pyxel.channels[channel].gain = gain

    def _apply_display_mode(self) -> None:
        pyxel.screen_mode(1 if self.settings.display_mode is DisplayMode.SMOOTH else 0)

    def _start_confirmation(self, action: str) -> None:
        if action not in ("return_title", "quit"):
            raise ValueError(f"unsupported settings action: {action}")
        if self.settings_cursor is None:
            return
        self.settings_cursor.active = False
        self.pending_settings_action = action
        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        confirmation_key = f"settings.confirm.{action}"
        confirmation_texts = tuple(
            self.localized_texts.create(
                line,
                4,
                2 + index * 3,
            )
            for index, line in enumerate(self.localized[confirmation_key].splitlines())
        )
        self.confirmation_window = windows.create(
            *CONFIRMATION_WINDOW_GRID,
            (
                *confirmation_texts,
                self.localized_texts.create(
                    self.localized["settings.yes"],
                    6,
                    CONFIRMATION_YES_Y,
                ),
                self.localized_texts.create(
                    self.localized["settings.no"],
                    6,
                    CONFIRMATION_NO_Y,
                ),
            ),
            opened=False,
        )
        self.confirmation_cursor = self.confirmation_window.set_cursor(
            (
                CursorTarget(
                    CONFIRMATION_CURSOR_X,
                    CONFIRMATION_YES_Y,
                    key="yes",
                ),
                CursorTarget(
                    CONFIRMATION_CURSOR_X,
                    CONFIRMATION_NO_Y,
                    key="no",
                ),
            )
        )
        self.confirmation_window.open()

    def _cancel_confirmation(self) -> None:
        self.confirmation_window = None
        self.confirmation_cursor = None
        self.pending_settings_action = None
        if self.settings_cursor is not None:
            self.settings_cursor.active = True

    def _begin_return_to_start(self) -> None:
        """Close the current menu stack before recreating the start screen."""

        self._returning_to_start = True
        for cursor in (self.settings_cursor, self.confirmation_cursor):
            if cursor is not None:
                cursor.active = False
        for window in self._visible_windows():
            window.close()

    @staticmethod
    def _has_held_action_input(input_state: InputState) -> bool:
        """Return whether an action could trigger on a newly created reader."""

        if not isinstance(input_state, InputState):
            raise TypeError("input_state must be an InputState")
        return any(
            button.held
            for button in (
                input_state.confirm,
                input_state.cancel,
                input_state.menu,
                input_state.previous_page,
                input_state.next_page,
                input_state.interruption,
            )
        )

    def _update_return_to_start(self, input_state: InputState) -> None:
        """Advance closing windows, then wait for action-button release."""

        if not isinstance(input_state, InputState):
            raise TypeError("input_state must be an InputState")
        windows = self._visible_windows()
        for window in windows:
            if not window.is_closed:
                window.update()
        if any(not window.is_closed for window in windows):
            return
        if self._has_held_action_input(input_state):
            return
        self._returning_to_start = False
        self._return_to_start_screen()

    def _return_to_start_screen(self) -> None:
        os.environ[GAME_SETTINGS_ENV] = json.dumps(
            self.settings.to_dict(),
            ensure_ascii=True,
        )
        battle_scene = getattr(self, "battle_scene", None)
        if battle_scene is not None:
            battle_scene.release_palette_variants()
        self.bgm.stop()
        if self.applied_screen_scale != self.settings.screen_scale:
            os.environ.pop(pyxel.WINDOW_STATE_ENV, None)
            pyxel.reset()
            return
        self._return_to_start_without_window_restart()

    def _return_to_start_without_window_restart(self) -> None:
        """Recreate game-owned state while preserving the Pyxel window."""

        settings = self.settings
        palette_shifter = self.palette_shifter
        load_mission_hint_shown = getattr(
            self,
            "_load_mission_hint_shown_this_launch",
            False,
        )
        self.__init__(
            settings=settings,
            palette_shifter=palette_shifter,
            settings_repository=self.settings_repository,
        )
        self._load_mission_hint_shown_this_launch = load_mission_hint_shown

    def _visible_windows(self) -> tuple[object, ...]:
        windows = list(getattr(self, "windows", ()))
        for attribute in ("settings_window", "confirmation_window"):
            window = getattr(self, attribute, None)
            if window is not None:
                windows.append(window)
        return tuple(windows)

    def _update_window_animations(self) -> bool:
        animating = tuple(
            window for window in self._visible_windows() if window.is_animating is True
        )
        for window in animating:
            window.update()
        return bool(animating)

    def _actor_positions(self):
        actors = getattr(self, "field_actors", None)
        return {} if actors is None else actors.positions

    def _start_field_event(
        self,
        event_id: str,
        *,
        release_direction: Direction | None = None,
        release_confirm: bool = False,
    ) -> bool:
        """Start one map event and immediately run its synchronous prefix."""

        if getattr(self, "event_runner", None) is not None:
            return False
        try:
            self.party_system.replace(
                self.party,
                character_states=self.character_states,
            )
            self.event_runner = EventRunner.from_catalog(
                self.event_catalog,
                event_id,
                context=EventContext.FIELD,
                save_data=self.save_data,
                party=self.party_system,
                inventory=self.inventory_system,
            )
            self.event_release_direction = release_direction
            self.event_release_confirm = release_confirm
            self.last_event_error = None
            self._continue_event()
            if (
                self.event_runner is None
                and getattr(self, "suspended_field_event", None) is None
            ):
                # An event with no waiting effect (for example an empty
                # branch) must not interrupt a held field movement input.
                self.event_release_direction = None
                self.event_release_confirm = False
                return False
        except (
            KeyError,
            EventRuntimeError,
            EventMessageDataError,
            AudioResourceError,
            ValueError,
        ) as error:
            self._abort_event(error)
        return self.event_runner is not None or self.last_event_error is None

    def _continue_event(self) -> None:
        runner = self.event_runner
        if runner is None:
            return
        while True:
            effect = runner.advance()
            self.party = self.party_system.active_party
            self.character_states = self.party_system.character_states
            save_data = getattr(self, "save_data", None)
            if isinstance(save_data, SaveData):
                save_data.auto_recovery = valid_config_for_party(
                    save_data.auto_recovery, self.party
                )
            if effect is None:
                if runner.is_complete:
                    battle_event_finished = runner.context is EventContext.BATTLE
                    if not battle_event_finished:
                        self._restore_event_stationary_actor_facing()
                    self.event_runner = None
                    self.event_effect = None
                    self.event_message = None
                    self.event_move_remaining = 0
                    self.selected_member_index = min(
                        self.selected_member_index,
                        len(self.party) - 1,
                    )
                    if battle_event_finished:
                        self._show_hint_once(FIRST_BATTLE_HINT_ID)
                return
            self.event_effect = effect
            if isinstance(effect, PlaySeEffect):
                play_se(effect.se_id)
                runner.complete_effect(effect)
                self.event_effect = None
                continue
            if isinstance(effect, ChangeBgmEffect):
                self.bgm.play(effect.bgm_id)
                runner.complete_effect(effect)
                self.event_effect = None
                continue
            if isinstance(effect, StartBattleEffect):
                self._begin_event_battle(effect)
                return
            if isinstance(effect, OpenShopEffect):
                shop = next(
                    (shop for shop in self.shops if shop.key == effect.shop_key),
                    None,
                )
                if shop is None:
                    raise EventRuntimeError(
                        runner.event_id,
                        "effect",
                        f"shop is not available: {effect.shop_key}",
                    )
                self.pending_shop = shop
                self.shop_return_to_debug = False
                self._begin_screen_change(GameScreenChange.OPEN_SHOP)
                return
            if isinstance(effect, MessageEffect):
                self.event_message = EventMessageOverlay(
                    message_id=effect.message_id,
                    settings=self.settings,
                    messages=self.event_messages,
                    fonts=self.fonts,
                    faces=self.faces,
                    face_positions=self.character_face_positions,
                )
                self.save_data.logs.insert(
                    0, {"message_id": effect.message_id, "arguments": {}}
                )
                del self.save_data.logs[20:]
                return
            if isinstance(effect, (MovePartyEffect, MoveActorEffect)):
                self.event_move_remaining = effect.steps
                return
            raise EventRuntimeError(
                runner.event_id, "effect", "unsupported event effect"
            )

    def _update_event(self, input_state: InputState) -> None:
        runner = self.event_runner
        effect = self.event_effect
        if runner is None or effect is None:
            return
        try:
            if isinstance(effect, MessageEffect):
                if self.event_message is not None and self.event_message.update(
                    input_state
                ):
                    runner.complete_effect(effect)
                    self.event_effect = None
                    self.event_message = None
                    self._continue_event()
                return
            if isinstance(effect, MovePartyEffect):
                moved = self.field.update(
                    effect.direction,
                    blocked_positions=(
                        ()
                        if self.field_actors is None
                        else self.field_actors.blocked_positions()
                    ),
                )
                movement = self.field
            elif isinstance(effect, MoveActorEffect):
                if self.field_actors is None:
                    raise EventRuntimeError(
                        runner.event_id,
                        "effect",
                        f"actor is not available: {effect.actor_id}",
                    )
                moved = self.field_actors.update(
                    effect.actor_id,
                    effect.direction,
                    party_position=self.field.position,
                )
                movement = self.field_actors.actor(effect.actor_id).movement
            else:
                raise EventRuntimeError(
                    runner.event_id, "effect", "unsupported waiting effect"
                )
            if not moved and not movement.is_moving:
                raise EventRuntimeError(
                    runner.event_id,
                    "effect",
                    "controlled movement is blocked",
                )
            if movement.arrived_position is not None:
                self.event_move_remaining -= 1
                if self.event_move_remaining == 0:
                    runner.complete_effect(effect)
                    self.event_effect = None
                    self._continue_event()
        except (
            KeyError,
            EventRuntimeError,
            EventMessageDataError,
            AudioResourceError,
            ValueError,
        ) as error:
            self._abort_event(error)

    def _abort_event(self, error: BaseException) -> None:
        self.last_event_error = str(error)
        print(f"イベントを中断しました: {error}", file=sys.stderr)
        self._restore_event_stationary_actor_facing()
        self.event_runner = None
        self.event_effect = None
        self.event_message = None
        self.event_move_remaining = 0
        self.event_resume_after_fade = False
        self.alert.start()

    def _restore_event_stationary_actor_facing(self) -> None:
        restore = getattr(self, "event_stationary_actor_facing_restore", None)
        self.event_stationary_actor_facing_restore = None
        if restore is None:
            return
        actors = getattr(self, "field_actors", None)
        if actors is None:
            return
        actor_id, facing = restore
        actors.restore_stationary_facing(actor_id, facing)

    def _release_latch_blocks_field(self, input_state: InputState) -> bool:
        blocked = False
        if getattr(self, "event_release_direction", None) is not None:
            if input_state.held_direction is None:
                self.event_release_direction = None
            else:
                blocked = True
        if getattr(self, "event_release_confirm", False):
            if not input_state.confirm.held:
                self.event_release_confirm = False
            else:
                blocked = True
        return blocked

    def _try_field_trigger(
        self,
        activation: str,
        x: int,
        y: int,
        *,
        release_direction: Direction | None = None,
        release_confirm: bool = False,
    ) -> bool:
        current_map = getattr(self, "current_map", None)
        if not isinstance(current_map, CompiledMap):
            return False
        trigger = current_map.event_trigger_at(
            activation,
            x,
            y,
            actor_positions=self._actor_positions(),
        )
        if trigger is None:
            return False
        if trigger.actor_id is not None and self.field_actors is not None:
            self.event_stationary_actor_facing_restore = None
            if activation in ("touch", "interact"):
                actor = self.field_actors.actor(trigger.actor_id)
                if actor.kind in ("stationary", "roaming"):
                    dx = actor.movement.position.x - self.field.position.x
                    dy = actor.movement.position.y - self.field.position.y
                    if abs(dx) + abs(dy) == 1:
                        self.field.facing = next(
                            direction
                            for direction in Direction
                            if (direction.dx, direction.dy) == (dx, dy)
                        )
                previous_facing = self.field_actors.face_toward(
                    trigger.actor_id,
                    self.field.position,
                )
                if actor.kind == "stationary" and previous_facing is not None:
                    self.event_stationary_actor_facing_restore = (
                        trigger.actor_id,
                        previous_facing,
                    )
            else:
                self.field_actors.stop(trigger.actor_id)
        return self._start_field_event(
            trigger.event_id,
            release_direction=release_direction,
            release_confirm=release_confirm,
        )

    def _try_open_treasure(
        self,
        x: int,
        y: int,
        *,
        release_direction: Direction | None = None,
        release_confirm: bool = False,
    ) -> bool:
        actors = getattr(self, "field_actors", None)
        current_map = getattr(self, "current_map", None)
        if actors is None or not isinstance(current_map, CompiledMap):
            return False
        runtime_actor = actors.actor_at(x, y)
        if runtime_actor is None or runtime_actor.kind != "treasure":
            return False
        if runtime_actor.treasure_frame == 2 and not runtime_actor.treasure_animation:
            return False
        if runtime_actor.treasure_animation:
            self.event_release_direction = release_direction
            self.event_release_confirm = release_confirm
            return True
        actor = next(item for item in current_map.actors if item.id == runtime_actor.id)
        status = self.treasure_system.open(
            current_map.map_id,
            actor,
            members=self.character_states.values(),
        )
        if status is TreasureOpenStatus.ALREADY_OPENED:
            return False

        self.event_release_direction = release_direction
        self.event_release_confirm = release_confirm
        dx = x - self.field.position.x
        dy = y - self.field.position.y
        if abs(dx) + abs(dy) == 1:
            self.field.facing = next(
                direction
                for direction in Direction
                if (direction.dx, direction.dy) == (dx, dy)
            )

        contents = actor.contents
        if contents is None:
            raise ValueError("treasure contents are missing")
        localizer = Localizer(self.settings.language)
        if contents.type == "gold":
            first_line = self.texts.formatted_text(
                TREASURE_GOLD_TEXT_KEY,
                localizer,
                {"AMOUNT": format_number(contents.amount)},
            )
        else:
            if contents.item_key is None:
                raise ValueError("item treasure key is missing")
            item = self.items[contents.item_key]
            first_line = self.texts.formatted_text(
                TREASURE_ITEM_TEXT_KEY,
                localizer,
                {"ITEM": str(item.localized_name(localizer))},
            )
        opened = status is TreasureOpenStatus.OPENED
        lines = [first_line]
        if not opened:
            lines.append(self.texts.text(TREASURE_CAPACITY_TEXT_KEY, localizer))
        else:
            play_se(TREASURE_OPEN_SE_ID)
        actors.start_treasure_opening(actor.id)
        self.pending_treasure_close_actor_id = None if opened else actor.id
        self.treasure_message = MessageOverlay(
            lines=tuple(lines),
            settings=self.settings,
            fonts=self.fonts,
        )
        return True

    def _finish_treasure_message(self) -> None:
        self.treasure_message = None
        actor_id = getattr(self, "pending_treasure_close_actor_id", None)
        self.pending_treasure_close_actor_id = None
        field_actors = getattr(self, "field_actors", None)
        if actor_id is not None and field_actors is not None:
            field_actors.start_treasure_closing(actor_id)

    def _update_field(self, input_state: InputState) -> None:
        if self._release_latch_blocks_field(input_state):
            self.field.update(None)
            return
        if input_state.menu.triggered:
            self._begin_screen_change(GameScreenChange.SHOW_MENU)
            return
        if not self.field.is_moving and input_state.confirm.triggered:
            x = self.field.position.x + self.field.facing.dx
            y = self.field.position.y + self.field.facing.dy
            if self._try_open_treasure(x, y, release_confirm=True):
                return
            if self._try_field_trigger("interact", x, y, release_confirm=True):
                return
            if self.current_map.allows_interaction_through(x, y):
                x += self.field.facing.dx
                y += self.field.facing.dy
                if self._try_open_treasure(x, y, release_confirm=True):
                    return
                if self._try_field_trigger(
                    "interact",
                    x,
                    y,
                    release_confirm=True,
                ):
                    return
        direction = input_state.held_direction
        if not self.field.is_moving and direction is not None:
            x = self.field.position.x + direction.dx
            y = self.field.position.y + direction.dy
            if self._try_open_treasure(
                x,
                y,
                release_direction=direction,
            ):
                return
            if self._try_field_trigger("touch", x, y, release_direction=direction):
                return
        if getattr(self, "field_actors", None) is None:
            self.field.update(direction)
        else:
            self.field.update(
                direction,
                blocked_positions=self.field_actors.blocked_positions(),
            )
        self._play_dungeon_poison_movement_sound()
        arrived = self.field.arrived_position
        if arrived is not None and self._try_field_trigger(
            "step",
            arrived.x,
            arrived.y,
            release_direction=direction,
        ):
            return
        self._handle_arrived_site()
        if (
            isinstance(arrived, FieldPosition)
            and getattr(self, "pending_screen_change", None) is None
        ):
            self._apply_dungeon_step_health_changes()
            if getattr(self, "field_condition_message", None) is not None:
                return
        if (
            arrived is not None
            and getattr(self, "pending_screen_change", None) is None
            and self._advance_random_encounter()
        ):
            return
        self._refresh_site_name_label()
        field_actors = getattr(self, "field_actors", None)
        if field_actors is not None:
            field_actors.update_roaming(party_position=self.field.position)

    def _field_menu_guide_available(self) -> bool:
        """Limit the idle hint to ordinary field play, excluding modal flows."""

        return (
            getattr(self, "showing_field", False) is True
            and not getattr(getattr(self, "fade", None), "is_active", False)
            and not getattr(self, "_returning_to_start", False)
            and not getattr(self, "_game_menu_resume_waiting", False)
            and all(
                getattr(self, attribute, None) is None
                for attribute in (
                    "start_screen",
                    "shop_screen",
                    "battle_scene",
                    "game_menu",
                    "encounter_transition",
                    "battle_return_fade",
                    "pending_screen_change",
                    "event_runner",
                    "event_message",
                    "treasure_message",
                    "field_condition_message",
                    "hint_overlay",
                )
            )
        )

    def _update_field_menu_guide(self, input_state: InputState) -> None:
        guide = getattr(self, "field_menu_guide", None)
        if guide is None:
            return
        field = getattr(self, "field", None)
        guide.update(
            input_state,
            idle=(
                self._field_menu_guide_available()
                and not getattr(field, "is_moving", False)
                and not getattr(field, "is_walking", False)
            ),
            language=self.settings.language,
        )

    def _update_game_menu(self, input_state: InputState) -> bool:
        """Handle global interruption before any underlying screen advances."""

        if getattr(self, "_game_menu_resume_waiting", False):
            if not self._has_held_action_input(input_state):
                self._game_menu_resume_waiting = False
                self.bgm.resume()
            return True
        menu = getattr(self, "game_menu", None)
        if menu is not None:
            if getattr(self, "_game_menu_return_waiting", False):
                if not self._has_held_action_input(input_state):
                    self._return_to_start_screen()
                return True
            action = menu.update(input_state)
            if action is GameMenuAction.RESUME:
                self.game_menu = None
                self._game_menu_resume_waiting = True
            elif action is GameMenuAction.RETURN_TITLE:
                self._game_menu_return_waiting = True
            elif action is GameMenuAction.QUIT:
                pyxel.quit()
            return True
        if not input_state.interruption.triggered:
            return False
        battle_scene = getattr(self, "battle_scene", None)
        if (
            getattr(self, "encounter_transition", None) is not None
            or getattr(self, "battle_return_fade", None) is not None
            or getattr(self, "_returning_to_start", False)
            or getattr(getattr(self, "fade", None), "is_active", False) is True
            or getattr(battle_scene, "is_transitioning", False) is True
        ):
            return False
        self.game_menu = GameMenuOverlay(
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
        )
        self.bgm.pause()
        return True

    def update(self) -> None:
        input_state = self.input_reader.poll()
        if self._update_game_menu(input_state):
            guide = getattr(self, "field_menu_guide", None)
            if guide is not None:
                guide.reset()
            return
        self._update_field_menu_guide(input_state)
        bgm = getattr(self, "bgm", None)
        if bgm is not None:
            bgm.update()
        self.alert.update()
        if getattr(self, "encounter_transition", None) is not None:
            self._update_encounter_transition()
            return
        hint_overlay = getattr(self, "hint_overlay", None)
        if hint_overlay is not None and not getattr(
            getattr(self, "fade", None), "is_active", False
        ):
            if hint_overlay.update(input_state):
                self.hint_overlay = None
            return
        if getattr(self, "battle_return_fade", None) is not None:
            self._update_battle_return(input_state)
            return
        runner = getattr(self, "event_runner", None)
        if runner is not None and runner.context is EventContext.BATTLE:
            self._update_event(input_state)
            return
        if self._update_battle_scene(input_state):
            return
        if getattr(self, "_returning_to_start", False):
            self._update_return_to_start(input_state)
            return
        if self._update_fade():
            return
        start_screen = getattr(self, "start_screen", None)
        if start_screen is not None:
            start_screen.update(input_state)
            return
        shop_screen = getattr(self, "shop_screen", None)
        if shop_screen is not None:
            if shop_screen.update(input_state):
                self._begin_screen_change(GameScreenChange.CLOSE_SHOP)
            return
        if getattr(self, "showing_field", False):
            self._update_field_fade_pulse()
            field_birds = getattr(self, "field_birds", None)
            if field_birds is not None:
                field_birds.update(
                    camera=self.field_renderer.camera_position(self.field),
                    player=(self.field.world_x, self.field.world_y),
                )
            field_actors = getattr(self, "field_actors", None)
            if field_actors is not None:
                field_actors.update_treasure_animations()
            treasure_message = getattr(self, "treasure_message", None)
            if treasure_message is not None:
                if treasure_message.update(input_state):
                    self._finish_treasure_message()
                return
            field_condition_message = getattr(
                self,
                "field_condition_message",
                None,
            )
            if field_condition_message is not None:
                if field_condition_message.update(input_state):
                    self._finish_field_condition_message()
                return
            if getattr(self, "event_runner", None) is not None:
                self._update_event(input_state)
            else:
                self._update_field(input_state)
            return
        item_screen = getattr(self, "item_screen", None)
        auto_recovery_screen = getattr(self, "auto_recovery_screen", None)
        if auto_recovery_screen is not None:
            if auto_recovery_screen.update(input_state):
                self._begin_screen_change(GameScreenChange.CLOSE_RECOVERY)
            return
        if item_screen is not None:
            if item_screen.update(input_state):
                self._begin_screen_change(GameScreenChange.CLOSE_ITEM)
            return
        spell_screen = getattr(self, "spell_screen", None)
        if spell_screen is not None:
            if spell_screen.update(input_state):
                self._begin_screen_change(GameScreenChange.CLOSE_SPELL)
            return
        equipment_screen = getattr(self, "equipment_screen", None)
        if equipment_screen is not None:
            if equipment_screen.update(input_state):
                self._begin_screen_change(GameScreenChange.CLOSE_EQUIPMENT)
            return
        status_screen = getattr(self, "status_screen", None)
        if status_screen is not None:
            if status_screen.update(input_state):
                self._begin_screen_change(GameScreenChange.CLOSE_STATUS)
            return
        information_screen = getattr(self, "information_screen", None)
        if information_screen is not None:
            if information_screen.update(input_state):
                self._begin_screen_change(GameScreenChange.CLOSE_INFO)
            return
        save_screen = getattr(self, "save_screen", None)
        if save_screen is not None:
            if save_screen.update(input_state):
                self._begin_screen_change(GameScreenChange.CLOSE_SAVE)
            return
        debug_screen = getattr(self, "debug_screen", None)
        if debug_screen is not None:
            if debug_screen.update(input_state):
                self._finish_debug_menu()
            return
        if self._update_window_animations():
            return

        if self.confirmation_cursor is not None:
            if input_state.cancel.triggered:
                self._cancel_confirmation()
                return
            if input_state.confirm.triggered:
                if self.confirmation_cursor.selected_key == "yes":
                    action = self.pending_settings_action
                    if action == "return_title":
                        self._begin_return_to_start()
                    elif action == "quit":
                        pyxel.quit()
                    return
                self._cancel_confirmation()
                return
            self.confirmation_window.update(input_state.navigation)
            return

        if self.settings_cursor is not None:
            if input_state.cancel.triggered:
                self._finish_settings()
                return
            if input_state.navigation in (Direction.LEFT, Direction.RIGHT):
                self._change_setting(
                    -1 if input_state.navigation is Direction.LEFT else 1
                )
                return
            if input_state.confirm.triggered:
                key = self.settings_cursor.selected_key
                if key == "debug":
                    self._start_debug_menu()
                elif key in ("return_title", "quit"):
                    self._start_confirmation(key)
                return
            if self.settings_window.update(input_state.navigation):
                self._refresh_settings_window(
                    selected_key=self.settings_cursor.selected_key
                )
            return

        if self.party_cursor is not None:
            if input_state.cancel.triggered:
                if self.sort_source_index is None:
                    self._finish_sort()
                else:
                    self._clear_sort_source()
                return
            if input_state.confirm.triggered:
                self._confirm_sort_member()
            elif (
                input_state.navigation is Direction.RIGHT
                and self.sort_source_index is None
            ):
                self._finish_sort()
                return
            self.party_window.update(input_state.navigation)
            selected_member_index = self.party_cursor.selected_key
            if isinstance(selected_member_index, int):
                self.selected_member_index = selected_member_index
                self.menu_member_selected = True
            return

        if input_state.cancel.triggered:
            self._begin_screen_change(GameScreenChange.SHOW_FIELD)
            return
        if input_state.confirm.triggered and self.command_cursor.selected_key == "heal":
            self._begin_screen_change(GameScreenChange.OPEN_RECOVERY)
            return
        if input_state.navigation is Direction.LEFT:
            self.command_cursor.select_key("sort")
            self._start_sort()
            return
        if input_state.confirm.triggered and self.command_cursor.selected_key == "item":
            self._begin_screen_change(GameScreenChange.OPEN_ITEM)
            return
        if (
            input_state.confirm.triggered
            and self.command_cursor.selected_key == "spell"
        ):
            self._begin_screen_change(GameScreenChange.OPEN_SPELL)
            return
        if (
            input_state.confirm.triggered
            and self.command_cursor.selected_key == "equip"
        ):
            self._begin_screen_change(GameScreenChange.OPEN_EQUIPMENT)
            return
        if (
            input_state.confirm.triggered
            and self.command_cursor.selected_key == "status"
        ):
            self._begin_screen_change(GameScreenChange.OPEN_STATUS)
            return
        if input_state.confirm.triggered and self.command_cursor.selected_key == "sort":
            self._start_sort()
            return
        if input_state.confirm.triggered and self.command_cursor.selected_key == "info":
            self._begin_screen_change(GameScreenChange.OPEN_INFO)
            return
        if (
            input_state.confirm.triggered
            and self.command_cursor.selected_key == "config"
        ):
            self._start_settings()
            return
        if input_state.confirm.triggered and self.command_cursor.selected_key == "save":
            self._begin_screen_change(GameScreenChange.OPEN_SAVE)
            return
        self.command_window.update(input_state.navigation)

    def draw(self) -> None:
        pyxel.cls(0)
        menu = getattr(self, "game_menu", None)
        if menu is not None:
            pyxel.camera()
            menu.draw()
            return
        pyxel.camera(self.alert.camera_x, 0)
        try:
            if getattr(self, "encounter_transition", None) is not None:
                self._draw_encounter_transition()
                return
            defeat_return_message = getattr(
                self,
                "defeat_return_message",
                None,
            )
            if defeat_return_message is not None:
                defeat_return_message.draw()
                return
            battle_scene = getattr(self, "battle_scene", None)
            if battle_scene is not None:
                battle_scene.draw()
                event_message = getattr(self, "event_message", None)
                if event_message is not None:
                    event_message.draw()
                hint_overlay = getattr(self, "hint_overlay", None)
                if hint_overlay is not None:
                    hint_overlay.draw()
                return
            start_screen = getattr(self, "start_screen", None)
            if start_screen is not None:
                start_screen.draw()
                return
            shop_screen = getattr(self, "shop_screen", None)
            if shop_screen is not None:
                shop_screen.draw()
                return
            if getattr(self, "showing_field", False):
                self._draw_field_screen()
                return
            item_screen = getattr(self, "item_screen", None)
            auto_recovery_screen = getattr(self, "auto_recovery_screen", None)
            if auto_recovery_screen is not None:
                auto_recovery_screen.draw()
                return
            if item_screen is not None:
                item_screen.draw()
                return
            spell_screen = getattr(self, "spell_screen", None)
            if spell_screen is not None:
                spell_screen.draw()
                return
            equipment_screen = getattr(self, "equipment_screen", None)
            if equipment_screen is not None:
                equipment_screen.draw()
                return
            status_screen = getattr(self, "status_screen", None)
            if status_screen is not None:
                status_screen.draw()
                return
            information_screen = getattr(self, "information_screen", None)
            if information_screen is not None:
                information_screen.draw()
                return
            save_screen = getattr(self, "save_screen", None)
            if save_screen is not None:
                save_screen.draw()
                return
            debug_screen = getattr(self, "debug_screen", None)
            if debug_screen is not None:
                debug_screen.draw()
                return
            self.party_window.draw()
            if self.party_window.is_open:
                main_menu_members = self._main_menu_members()
                for index, member in enumerate(main_menu_members):
                    if member.is_dead:
                        with self.palette_shifter.shifted(MONOCHROME_PALETTE):
                            self._draw_party_face(
                                index,
                                member,
                                y_offset=self._member_y_offset_grid(index) * 4,
                            )
                    elif self._is_reserve_index(index):
                        with self.palette_shifter.shifted(DIMMED_PALETTE):
                            self._draw_party_face(
                                index,
                                member,
                                y_offset=self._member_y_offset_grid(index) * 4,
                            )
                    else:
                        self._draw_party_face(index, member)
                if self.party_cursor is not None:
                    if self.sort_source_cursor is not None:
                        self.sort_source_cursor.draw()
                        self._draw_formation_arrow()
                    self.party_cursor.draw()
            for window in self.windows[1:]:
                window.draw()
            if self.settings_window is not None:
                self.settings_window.draw()
            if self.confirmation_window is not None:
                self.confirmation_window.draw()
        finally:
            pyxel.camera()

    def _draw_field_screen(self, *, draw_player: bool = True) -> None:
        """Draw the current field and any field-owned overlays."""

        fade_draw_options = {}
        if getattr(self, "field_fade_active", False):
            fade_draw_options = {
                "player_palette_shifter": self.palette_shifter,
                "player_palette_name": FIELD_FADE_PULSE_PALETTE,
            }

        if isinstance(getattr(self, "field_actors", None), FieldActors):
            player_member = self._field_player_member()
            draw_options = {
                "actors": self.field_actors,
                "prop_image": self.field_prop_image,
                "actor_character_image": self.field_actor_character_image,
                "actor_pc_character_image": self.field_actor_pc_character_image,
                "actor_pc_fairy_sprite_indices": getattr(
                    self,
                    "fairy_pc_sprite_indices",
                    (),
                ),
                "player_character_image": self.field_player_character_image,
                "player_sprite_index": player_member.definition.battle_sprite,
                "player_floating": player_member.definition.race is Race.FAIRY,
                "player_floating_phase": floating_phase_offset(
                    f"pc:{player_member.definition.key}"
                ),
                "treasure_image": self.field_treasure_image,
                **fade_draw_options,
            }
            if not draw_player:
                draw_options["draw_player"] = False
            self.field_renderer.draw(self.field, **draw_options)
        elif draw_player:
            self.field_renderer.draw(self.field, **fade_draw_options)
        else:
            self.field_renderer.draw(
                self.field,
                draw_player=False,
                **fade_draw_options,
            )
        field_birds = getattr(self, "field_birds", None)
        if field_birds is not None:
            field_birds.draw(
                camera=self.field_renderer.camera_position(self.field),
                pyxel_api=pyxel,
            )
        self._draw_site_name()
        guide = getattr(self, "field_menu_guide", None)
        if guide is not None and self._field_menu_guide_available():
            guide.draw()
        event_message = getattr(self, "event_message", None)
        if event_message is not None:
            event_message.draw()
        treasure_message = getattr(self, "treasure_message", None)
        if treasure_message is not None:
            treasure_message.draw()
        field_condition_message = getattr(self, "field_condition_message", None)
        if field_condition_message is not None:
            field_condition_message.draw()
        hint_overlay = getattr(self, "hint_overlay", None)
        if hint_overlay is not None:
            hint_overlay.draw()

    def _draw_encounter_transition(self) -> None:
        """Capture the field once, then transform that immutable framebuffer."""

        transition = self.encounter_transition
        if transition is None:
            return
        snapshot = self.encounter_snapshot
        if snapshot is None:
            self._draw_field_screen(draw_player=False)
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
            self.encounter_snapshot = snapshot
            return
        transform = transition.transform(SCREEN_WIDTH, SCREEN_HEIGHT)
        pyxel.camera()
        pyxel.blt(
            transform.x,
            transform.y,
            snapshot,
            0,
            0,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            rotate=transform.rotate,
            scale=transform.scale,
        )

    def _draw_party_face(
        self,
        index: int,
        member: Member,
        *,
        y_offset: int = 0,
    ) -> None:
        face_position = member.face_position
        row_height = self._member_row_height_grid(len(self.party))
        pyxel.blt(
            PARTY_FACE_X[member.is_front_row],
            PARTY_FACE_Y + index * row_height * 4 + y_offset,
            self.faces,
            face_position.x,
            face_position.y,
            PARTY_FACE_SIZE,
            PARTY_FACE_SIZE,
            TRANSPARENT_INDEX,
        )

    def _draw_formation_arrow(self) -> None:
        if (
            self.sort_source_index is None
            or self.party_cursor is None
            or self.party_cursor.selected_key != self.sort_source_index
        ):
            return
        member = self.party[self.sort_source_index]
        if not self._can_change_formation(member):
            return
        if member.is_front_row:
            x = PARTY_FACE_X[True] + PARTY_FACE_SIZE
            source_x = FORMATION_ARROW_RIGHT_X
        else:
            x = PARTY_FACE_X[False] - FORMATION_ARROW_WIDTH
            source_x = FORMATION_ARROW_LEFT_X
        y = (
            PARTY_FACE_Y
            + self.sort_source_index * self._member_row_height_grid(len(self.party)) * 4
            + self._member_y_offset_grid(self.sort_source_index) * 4
            + (PARTY_FACE_SIZE - FORMATION_ARROW_HEIGHT) // 2
        )
        frame = (pyxel.frame_count // FORMATION_ARROW_FRAME_DURATION) % 2
        pyxel.blt(
            x,
            y,
            FORMATION_ARROW_BANK,
            source_x[frame],
            FORMATION_ARROW_Y,
            FORMATION_ARROW_WIDTH,
            FORMATION_ARROW_HEIGHT,
            FORMATION_ARROW_COLKEY,
        )


GAME_ERRORS = (
    AttackPoseDataError,
    AudioResourceError,
    BattleDataError,
    DataResourceError,
    DebugPartyError,
    EventMessageResourceError,
    EquipmentMenuDataError,
    FontResourceError,
    ImageResourceError,
    MapResourceError,
    ItemDataError,
    ItemMenuDataError,
    InformationMenuDataError,
    MemberDataError,
    MonsterDataError,
    GameDataError,
    SkillDataError,
    SaveMenuDataError,
    StartMenuDataError,
    SpellDataError,
    SpellEffectDataError,
    SpellMenuDataError,
    ShopUiDataError,
    ShopDataError,
    StatusMenuDataError,
    TextCatalogError,
)


def create_game_input_reader() -> PyxelInputReader:
    """Create the normal bindings used by the game runtime."""

    return PyxelInputReader(InputBindings.default())


__all__ = [
    "ENCOUNTER_JINGLE_ID",
    "FPS",
    "GAME_ERRORS",
    "GAME_SETTINGS_ENV",
    "Game",
    "SCREEN_HEIGHT",
    "SCREEN_WIDTH",
    "create_game_input_reader",
    "localized_menu_texts",
]
