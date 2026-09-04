"""Coordinate the currently playable field-first game flow."""

from __future__ import annotations

import json
import os
from enum import Enum, auto
from pathlib import Path

import pyxel

from game_data import (
    GameDataError,
    create_party,
    load_character_records,
    load_items,
    load_shops,
    load_skills,
    load_spells,
)
from ui.debug_menu import DebugMenuOverlay, DebugTeleportTarget
from ui.debug_text import DEBUG_TEXT
from ui.equipment_menu import (
    EquipmentMenuDataError,
    EquipmentMenuOverlay,
)
from ui.item_menu import (
    ItemMenuDataError,
    ItemMenuOverlay,
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
from field import FieldMovement, FieldPosition
from input import (
    Direction,
    InputAction,
    InputBindings,
    InputDevice,
    PyxelInputReader,
)
from item import ItemDataError
from localization import Localizer, format_number
from member import (
    BATTLE_PARTY_MEMBER_COUNT,
    CharacterDefinition,
    FormationRow,
    Member,
    MemberDataError,
)
from resources import (
    TRANSPARENT_INDEX,
    AudioResourceError,
    BgmPlayer,
    DataResourceError,
    FontResourceError,
    FontResources,
    FontRole,
    ImageResourceError,
    ImageResources,
    MapDestination,
    MapResourceError,
    MapResources,
)
from rendering import (
    DEFAULT_FADE_FRAME_COUNT,
    DIMMED_PALETTE,
    FadeEvent,
    FadePhase,
    FadeThroughBlack,
    FieldRenderer,
    PaletteShifter,
)
from skill import SkillDataError
from shop import ShopDataError
from spell import SpellDataError
from state import DisplayMode, Difficulty, Language, SaveData, Settings
from systems import (
    DebugPartyEditor,
    DebugPartyError,
    InventorySystem,
    SaveRepository,
    SaveSlotSummary,
    SaveSystemError,
    ShopSystem,
    TravelSystem,
    create_save_document,
)
from world_sites import WorldSiteCatalog

from text_catalog import TextCatalog, TextCatalogError
from ui import (
    CursorTarget,
    DEFAULT_TEXT_COLOR,
    DISABLED_COLOR,
    LocalizedWindowTextFactory,
    NEGATIVE_COLOR,
    POSITIVE_COLOR,
    RESERVE_MEMBER_TEXT_COLOR,
    SaveMenuDataError,
    SaveMenuOverlay,
    WindowFactory,
    WindowCursor,
    WindowText,
    WINDOW_ANIMATION_FRAME_COUNT,
    draw_tagged_text,
    format_play_time,
    input_icon_tag,
    pad,
)

APP_ROOT = Path(__file__).resolve().parent
SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
FPS = 60

MENU_COMMANDS = (
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
    "settings.return_title",
    "settings.quit",
    "settings.guide.language.0",
    "settings.guide.language.1",
    "settings.guide.bgm.0",
    "settings.guide.bgm.1",
    "settings.guide.se.0",
    "settings.guide.se.1",
    "settings.guide.screen_size.0",
    "settings.guide.screen_size.1",
    "settings.guide.display.0",
    "settings.guide.display.1",
    "settings.confirm.return_title",
    "settings.confirm.quit",
    "settings.yes",
    "settings.no",
)
SETTINGS_ROWS = (
    ("language", 2),
    ("bgm", 5),
    ("se", 8),
    ("screen_size", 11),
    ("display", 14),
    ("debug", 17),
    ("return_title", 20),
    ("quit", 23),
)
SETTINGS_GUIDE_KEYS = {
    "language": (
        "settings.guide.language.0",
        "settings.guide.language.1",
    ),
    "bgm": ("settings.guide.bgm.0", "settings.guide.bgm.1"),
    "se": ("settings.guide.se.0", "settings.guide.se.1"),
    "screen_size": (
        "settings.guide.screen_size.0",
        "settings.guide.screen_size.1",
    ),
    "display": ("settings.guide.display.0", "settings.guide.display.1"),
}
LANGUAGE_SEQUENCE = (
    Language.JAPANESE,
    Language.ENGLISH,
    Language.SIMPLIFIED_CHINESE,
)
DISPLAY_SEQUENCE = (DisplayMode.PIXEL, DisplayMode.SMOOTH)
MOCK_INPUT_DEVICE = InputDevice.KEYBOARD
FACES_IMAGE_ID = "faces/faces_pc"
WORLD_MAP_ID = "worldmap"
WORLD_MAP_START_POSITION = FieldPosition(x=17, y=39)
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
PARTY_RECOVERY_TEXT_X = 39
PARTY_CURSOR_X = 3
PARTY_CURSOR_Y = 5
RESERVE_MEMBER_Y_OFFSET_GRID = 2
SORT_SOURCE_CURSOR_X_OFFSET = 1
FORMATION_ARROW_BANK = 0
FORMATION_ARROW_LEFT_X = (96, 112)
FORMATION_ARROW_RIGHT_X = (104, 120)
FORMATION_ARROW_Y = 0
FORMATION_ARROW_WIDTH = 8
FORMATION_ARROW_HEIGHT = 16
FORMATION_ARROW_COLKEY = 1
FORMATION_ARROW_FRAME_DURATION = 30
TELEPORT_SOUND_CHANNEL = 0
TELEPORT_SOUND_ID = 8
ALERT_CHANNEL = 1
ALERT_SOUND_ID = 7
SE_CHANNELS = (TELEPORT_SOUND_CHANNEL, ALERT_CHANNEL)
ALERT_FRAME_COUNT = 3
ALERT_CAMERA_X = (0, 0, 1, -1)
SETTINGS_WINDOW_GRID = (4, 12, 56, 36)
SETTINGS_LABEL_X = 4
SETTINGS_VALUE_X = 30
SETTINGS_CURSOR_X = 2
SETTINGS_GUIDE_X = 4
SETTINGS_GUIDE_Y = 29
SETTINGS_GUIDE_ROW_HEIGHT = 3
CONFIRMATION_WINDOW_GRID = (8, 22, 48, 16)
CONFIRMATION_CURSOR_X = 4
CONFIRMATION_YES_Y = 8
CONFIRMATION_NO_Y = 11
SE_VOLUME_GAINS = (0.0, 0.05, 0.10, 0.15, 0.20)
SE_PREVIEW_SOUND_ID = 9
GAME_SETTINGS_ENV = "DA0_GAME_SETTINGS"
FIELD_BGM_ID = "da3-field"
INITIAL_GOLD = 100
INITIAL_PARTY_KEYS = ("Fiora", "Cerion")
SHOP_SELECTOR_WINDOW_GRID = (4, 7, 56, 46)
SHOP_SELECTOR_TEXT_X = 4
SHOP_SELECTOR_CURSOR_X = 2
SHOP_SELECTOR_FIRST_Y = 2
SHOP_SELECTOR_ROW_HEIGHT = 3


class GameScreenChange(Enum):
    """Screen replacement applied only while fully black."""

    SHOW_FIELD = auto()
    SHOW_MENU = auto()
    OPEN_ITEM = auto()
    CLOSE_ITEM = auto()
    OPEN_SPELL = auto()
    CLOSE_SPELL = auto()
    OPEN_EQUIPMENT = auto()
    CLOSE_EQUIPMENT = auto()
    OPEN_STATUS = auto()
    CLOSE_STATUS = auto()
    OPEN_SAVE = auto()
    CLOSE_SAVE = auto()
    OPEN_SHOP = auto()
    CLOSE_SHOP = auto()
    CHANGE_MAP = auto()
    TELEPORT = auto()


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
    ) -> None:
        if not isinstance(settings, Settings):
            raise TypeError("settings must be Settings")
        self.settings = settings
        self.palette_shifter = palette_shifter
        self.input_reader = create_game_input_reader()
        self.alert = MenuAlertEffect()

        self._apply_se_volume()
        self.bgm = BgmPlayer(volume=self.settings.bgm_volume)
        self.bgm.play(FIELD_BGM_ID)
        self.save_data = SaveData(gold=INITIAL_GOLD)
        self.items = load_items()
        self.inventory_system = InventorySystem(self.items)
        self.skills = load_skills()
        self.spells = load_spells()
        self.party = create_party(
            self.items,
            self.skills,
            character_keys=INITIAL_PARTY_KEYS,
            back_row_character_keys=("Cerion",),
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
        self.character_states = {
            member.definition.key: member for member in self.party
        }
        character_definitions = tuple(
            CharacterDefinition.from_record(record)
            for record in self.character_records
        )
        self.character_face_positions = {
            definition.key: definition.face_position
            for definition in character_definitions
        }
        self.save_repository = SaveRepository()
        self.current_save_slot: int | None = None
        self.texts = TextCatalog.from_json(RUNTIME_TEXTS_PATH)
        self.fonts = FontResources()
        images = ImageResources()
        self.faces = images.image(FACES_IMAGE_ID)
        self.map_resources = MapResources()
        self.world_map = self.map_resources.map(WORLD_MAP_ID)
        self.current_map = self.world_map
        self.world_sites = WorldSiteCatalog(self.world_map.sites)
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
        self.settings_window = None
        self.settings_cursor: WindowCursor | None = None
        self.confirmation_window = None
        self.confirmation_cursor: WindowCursor | None = None
        self.pending_settings_action: str | None = None
        self.fade = FadeThroughBlack()
        self.pending_screen_change: GameScreenChange | None = None
        self.animate_main_windows_with_fade = False
        self.showing_field = True
        self.item_screen: ItemMenuOverlay | None = None
        self.equipment_screen: EquipmentMenuOverlay | None = None
        self.status_screen: StatusMenuOverlay | None = None
        self.spell_screen: SpellMenuOverlay | None = None
        self.save_screen: SaveMenuOverlay | None = None
        self.shop_screen: ShopOverlay | None = None
        self.shop_selector_window = None
        self.shop_selector_cursor: WindowCursor | None = None
        self.pending_shop = None
        self.debug_screen: DebugMenuOverlay | None = None
        self.selected_member_index = 0
        self.site_name_site = None
        self.site_name_text: WindowText | None = None
        self._site_name_cache: tuple[str, Language] | None = None
        self.pending_site = None
        self.pending_target_map = None
        self.pending_target_arrival = None
        self._build_main_windows()
        self._refresh_site_name_label()

    @staticmethod
    def settings_from_environment() -> Settings:
        serialized = os.environ.get(GAME_SETTINGS_ENV)
        if serialized is None:
            return Settings()
        try:
            data = json.loads(serialized)
            return Settings.from_dict(data)
        except (json.JSONDecodeError, TypeError, ValueError):
            os.environ.pop(GAME_SETTINGS_ENV, None)
            return Settings()

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
        selected_command: str = "item",
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
            27,
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
            27,
            16,
            27,
            (
                localized_texts.create(localized["menu.info.gold"], 2, 2),
                WindowText(pad(self.save_data.gold, 6), 2, 5),
                localized_texts.create(
                    localized["menu.info.experience"],
                    2,
                    8,
                ),
                WindowText(pad(self.save_data.experience, 6), 2, 11),
                localized_texts.create(
                    localized["menu.info.difficulty"],
                    2,
                    14,
                ),
                localized_texts.create(
                    localized[DIFFICULTY_TEXT_KEYS[self.save_data.difficulty]],
                    4,
                    17,
                ),
                localized_texts.create(
                    localized["menu.info.play_time"],
                    2,
                    20,
                ),
                WindowText(
                    "　"
                    + format_play_time(
                        self.save_data.play_time_frames,
                        fps=FPS,
                        include_seconds=False,
                    ),
                    2,
                    23,
                ),
            ),
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
        if (
            not isinstance(catalog, WorldSiteCatalog)
            or getattr(self, "current_map", None) is not getattr(
                self,
                "world_map",
                None,
            )
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
        if not isinstance(arrived, FieldPosition) or self.current_map is not self.world_map:
            return
        site = self.world_sites.entrance_at(arrived.x, arrived.y)
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
        self.current_map = target_map
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
        self.pending_target_map = None
        self.pending_target_arrival = None
        self._refresh_site_name_label(force=True)

    def _apply_pending_site_change(self) -> None:
        site = self.pending_site
        if site is None:
            raise RuntimeError("site map change has no entered site")
        self.travel_system.enter_site(self.save_data, site)
        self._apply_pending_map_destination()
        self.pending_site = None

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
                len(party) > BATTLE_PARTY_MEMBER_COUNT
                and index == len(party) - 1
            )
            row_y = (
                2
                + index * row_height
                + (RESERVE_MEMBER_Y_OFFSET_GRID if is_reserve else 0)
            )
            base_color = (
                RESERVE_MEMBER_TEXT_COLOR if is_reserve else DEFAULT_TEXT_COLOR
            )
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
                        color=(
                            DISABLED_COLOR if member.max_mp == 0 else base_color
                        ),
                    ),
                )
            )
            condition = member.status(
                localizer,
                self.texts,
                show_mhp=False,
            )
            if condition:
                texts.append(
                    text_factory.create(
                        condition,
                        PARTY_RECOVERY_TEXT_X,
                        row_y + 3,
                        color=base_color,
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
            len(self.party) > BATTLE_PARTY_MEMBER_COUNT
            and index == len(self.party) - 1
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
                PARTY_CURSOR_Y
                + index * row_height
                + self._member_y_offset_grid(index),
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
        if (
            self._is_reserve_index(len(self.party) - 1)
            and self.party[-1] is member
        ):
            return not member.is_front_row
        return (
            not member.is_front_row
            or sum(
                party_member.is_front_row
                for party_member in self.party[:BATTLE_PARTY_MEMBER_COUNT]
            )
            > 1
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
            self.party = tuple(party)
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
        guide_keys = SETTINGS_GUIDE_KEYS.get(selected_key, ())
        if selected_key == "language" and self.settings.language is Language.ENGLISH:
            guide_keys = guide_keys[:1]
        for index, text_key in enumerate(guide_keys):
            texts.append(
                self.localized_texts.create(
                    self.localized[text_key],
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
            save_data=self.save_data,
            settings=self.settings,
            fonts=self.fonts,
            alert=self.alert,
            teleport_targets=self._debug_teleport_targets(),
            on_teleport=self._start_debug_teleport,
        )

    def _debug_teleport_targets(self) -> tuple[DebugTeleportTarget, ...]:
        """Build localized choices accepted by the real teleport rules."""

        localizer = Localizer(self.settings.language)
        return tuple(
            DebugTeleportTarget(
                site.id,
                self.texts.text(
                    site.name_text_key,
                    localizer,
                    default=site.id,
                ),
            )
            for site in self.travel_system.teleport_destinations(self.save_data)
        )

    def _start_debug_teleport(self, site_id: str) -> bool:
        """Stage one visited teleport destination and begin fading out."""

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
        self._begin_screen_change(GameScreenChange.TELEPORT)
        pyxel.play(TELEPORT_SOUND_CHANNEL, TELEPORT_SOUND_ID)
        return True

    def _finish_debug_menu(self, *, resume_settings: bool = True) -> None:
        if self.debug_screen is None:
            return
        self.party = self.debug_screen.party
        character_states = getattr(self, "character_states", {})
        character_states.update(
            (member.definition.key, member) for member in self.party
        )
        self.character_states = character_states
        self._force_reserve_front()
        self.debug_screen = None
        self.selected_member_index = min(
            self.selected_member_index,
            len(self.party) - 1,
        )
        self._build_main_windows(selected_command="config", animate=False)
        self.command_cursor.active = not resume_settings
        if resume_settings:
            if self.settings_cursor is not None:
                self.settings_cursor.active = True
        else:
            self.settings_window = None
            self.settings_cursor = None

    def _apply_pending_debug_teleport(self) -> None:
        """Apply a debug teleport and return directly to the field."""

        self._apply_pending_map_destination()
        self._finish_debug_menu(resume_settings=False)
        self.showing_field = True

    def _start_status(self) -> None:
        self.command_cursor.active = False
        self.status_screen = StatusMenuOverlay(
            party=self.party,
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
            faces=self.faces,
            member_index=self.selected_member_index,
        )

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
            on_invalid_action=self.alert.start,
        )

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

    def _begin_screen_change(self, change: GameScreenChange) -> None:
        """Reserve one menu-related screen replacement and begin fading out."""

        if not isinstance(change, GameScreenChange):
            raise TypeError("field screen change must be a GameScreenChange")
        if getattr(self, "pending_screen_change", None) is not None:
            raise RuntimeError("field screen change is already pending")
        frame_count = (
            SITE_MAP_FADE_FRAME_COUNT
            if change in (
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
        if change in (
            GameScreenChange.SHOW_FIELD,
            GameScreenChange.OPEN_ITEM,
            GameScreenChange.OPEN_SPELL,
            GameScreenChange.OPEN_EQUIPMENT,
            GameScreenChange.OPEN_STATUS,
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
        elif change is GameScreenChange.SHOW_MENU:
            self.showing_field = False
            self.command_cursor.active = True
            self._restart_main_windows_for_fade_in()
        elif change is GameScreenChange.OPEN_ITEM:
            self._start_item()
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
        elif change is GameScreenChange.OPEN_SAVE:
            self._start_save()
        elif change is GameScreenChange.CLOSE_SAVE:
            self._finish_save()
        elif change is GameScreenChange.OPEN_SHOP:
            self.showing_field = False
            self._start_shop()
        elif change is GameScreenChange.CLOSE_SHOP:
            self._finish_shop()
            self.showing_field = True
        elif change is GameScreenChange.CHANGE_MAP:
            self._apply_pending_site_change()
        elif change is GameScreenChange.TELEPORT:
            self._apply_pending_debug_teleport()
        else:
            raise RuntimeError(f"unsupported field screen change: {change}")
        self.pending_screen_change = None

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
        if event is FadeEvent.COVERED:
            self._apply_pending_screen_change()
        elif was_fading_in and getattr(
            self,
            "animate_main_windows_with_fade",
            False,
        ):
            self._update_window_animations()
            if event is FadeEvent.FINISHED:
                self.animate_main_windows_with_fade = False
        return True

    def _start_spell(self) -> None:
        self.command_cursor.active = False
        self.spell_screen = SpellMenuOverlay(
            party=self.party,
            spells=self.spells,
            settings=self.settings,
            texts=self.texts,
            fonts=self.fonts,
            faces=self.faces,
            member_index=self.selected_member_index,
        )

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
            )
            summary = self.save_repository.save(slot, document)
        except (SaveSystemError, TypeError, ValueError):
            return None
        self.current_save_slot = slot
        return summary

    def _finish_spell(self) -> None:
        if self.spell_screen is None:
            return
        self.selected_member_index = self.spell_screen.member_index
        self.spell_screen = None
        self.command_cursor.active = True

    def _start_shop_selector(self) -> None:
        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        self.shop_selector_window = windows.create(
            *SHOP_SELECTOR_WINDOW_GRID,
            tuple(
                self.localized_texts.create(
                    shop.key,
                    SHOP_SELECTOR_TEXT_X,
                    SHOP_SELECTOR_FIRST_Y + index * SHOP_SELECTOR_ROW_HEIGHT,
                )
                for index, shop in enumerate(self.shops)
            ),
        )
        self.shop_selector_cursor = WindowCursor(
            self.shop_selector_window,
            tuple(
                CursorTarget(
                    SHOP_SELECTOR_CURSOR_X,
                    SHOP_SELECTOR_FIRST_Y + index * SHOP_SELECTOR_ROW_HEIGHT,
                    key=shop.key,
                )
                for index, shop in enumerate(self.shops)
            ),
        )

    def _close_shop_selector(self) -> None:
        self.shop_selector_window = None
        self.shop_selector_cursor = None
        self.pending_shop = None

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
        self._close_shop_selector()

    def _finish_shop(self) -> None:
        self.shop_screen = None
        self.pending_shop = None
        self._close_shop_selector()

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
            self.settings = self.settings.with_language(language)
            self._build_main_windows(
                selected_command="config",
                animate=False,
            )
            self.command_cursor.active = False
        elif key == "bgm":
            volume = (self.settings.bgm_volume + distance) % 5
            self.settings = self.settings.with_bgm_volume(volume)
            self.bgm.set_volume(volume)
        elif key == "se":
            volume = (self.settings.se_volume + distance) % 5
            self.settings = self.settings.with_se_volume(volume)
            self._apply_se_volume()
            pyxel.play(ALERT_CHANNEL, SE_PREVIEW_SOUND_ID)
        elif key == "screen_size":
            scale = (self.settings.screen_scale - 1 + distance) % 5 + 1
            self.settings = self.settings.with_screen_scale(scale)
        elif key == "display":
            index = DISPLAY_SEQUENCE.index(self.settings.display_mode)
            mode = DISPLAY_SEQUENCE[(index + distance) % len(DISPLAY_SEQUENCE)]
            self.settings = self.settings.with_display_mode(mode)
            self._apply_display_mode()
        else:
            return
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

    def _restart_game(self) -> None:
        os.environ[GAME_SETTINGS_ENV] = json.dumps(
            self.settings.to_dict(),
            ensure_ascii=True,
        )
        os.environ.pop(pyxel.WINDOW_STATE_ENV, None)
        pyxel.reset()

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

    def update(self) -> None:
        self.alert.update()
        input_state = self.input_reader.poll()
        if self._update_fade():
            return
        shop_screen = getattr(self, "shop_screen", None)
        if shop_screen is not None:
            if shop_screen.update(input_state):
                self._begin_screen_change(GameScreenChange.CLOSE_SHOP)
            return
        if getattr(self, "showing_field", False):
            shop_selector_cursor = getattr(self, "shop_selector_cursor", None)
            if shop_selector_cursor is not None:
                if input_state.cancel.triggered:
                    self._close_shop_selector()
                    return
                if input_state.confirm.triggered:
                    selected_key = shop_selector_cursor.selected_key
                    self.pending_shop = next(
                        (shop for shop in self.shops if shop.key == selected_key),
                        None,
                    )
                    if self.pending_shop is None:
                        raise GameDataError(
                            f"選択されたショップが見つかりません: {selected_key!r}"
                        )
                    self._begin_screen_change(GameScreenChange.OPEN_SHOP)
                    return
                shop_selector_cursor.update(input_state.navigation)
            elif input_state.confirm.triggered:
                self._start_shop_selector()
            elif input_state.menu.triggered:
                self._begin_screen_change(GameScreenChange.SHOW_MENU)
            elif input_state.cancel.triggered:
                pyxel.quit()
            else:
                self.field.update(input_state.held_direction)
                self._handle_arrived_site()
                self._refresh_site_name_label()
            return
        item_screen = getattr(self, "item_screen", None)
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
                        self._restart_game()
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
            self.party_window.update(input_state.navigation)
            selected_member_index = self.party_cursor.selected_key
            if isinstance(selected_member_index, int):
                self.selected_member_index = selected_member_index
            return

        if input_state.cancel.triggered:
            self._begin_screen_change(GameScreenChange.SHOW_FIELD)
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
        pyxel.camera(self.alert.camera_x, 0)
        try:
            shop_screen = getattr(self, "shop_screen", None)
            if shop_screen is not None:
                shop_screen.draw()
                return
            if getattr(self, "showing_field", False):
                self.field_renderer.draw(self.field)
                self._draw_site_name()
                shop_selector_window = getattr(self, "shop_selector_window", None)
                if shop_selector_window is not None:
                    shop_selector_window.draw()
                shop_selector_cursor = getattr(self, "shop_selector_cursor", None)
                if shop_selector_cursor is not None:
                    shop_selector_cursor.draw()
                return
            item_screen = getattr(self, "item_screen", None)
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
                    if self._is_reserve_index(index):
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
            + self.sort_source_index
            * self._member_row_height_grid(len(self.party))
            * 4
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
    AudioResourceError,
    DataResourceError,
    DebugPartyError,
    EquipmentMenuDataError,
    FontResourceError,
    ImageResourceError,
    MapResourceError,
    ItemDataError,
    ItemMenuDataError,
    MemberDataError,
    GameDataError,
    SkillDataError,
    SaveMenuDataError,
    SpellDataError,
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
    "FPS",
    "GAME_ERRORS",
    "GAME_SETTINGS_ENV",
    "Game",
    "SCREEN_HEIGHT",
    "SCREEN_WIDTH",
    "create_game_input_reader",
    "localized_menu_texts",
]
