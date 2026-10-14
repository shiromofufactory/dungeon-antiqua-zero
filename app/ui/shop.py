"""ZERO shop overlay shared by the game and development harnesses."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import Enum, StrEnum

import pyxel

from input import InputAction, InputDevice, InputState
from item import Item
from item_detail import ItemDetailContext, build_item_detail
from localization import Localizer, format_number
from member import Member
from rendering import PaletteShifter
from resources import FontResources, ImageResources
from shop import Shop
from spell import Spell
from state import Language, SaveData, Settings
from systems import InventorySystem, ShopSystem
from text_catalog import TextCatalog
from ui import (
    CursorTarget,
    LocalizedWindowTextFactory,
    Window,
    WindowCursor,
    WindowFactory,
    WindowText,
    input_icon_tag,
    pad,
)
from ui.shop_party import ShopPartyPanel
from ui.text_layout import right_aligned_grid_x

SHOP_COMMAND_WINDOW_GRID = (0, 0, 44, 7)
SHOP_GOLD_WINDOW_GRID = (44, 0, 20, 7)
SHOP_LIST_WINDOW_GRID = (0, 7, 32, 40)
SHOP_INFO_WINDOW_GRID = (31, 7, 33, 40)
SHOP_COMMANDS = (
    ("buy", "shop.command.buy"),
    ("sell", "shop.command.sell"),
    ("leave", "shop.command.leave"),
)
SHOP_COMMAND_TEXT_X = (8, 17, 26)
SHOP_COMMAND_CURSOR_X = tuple(x - 2 for x in SHOP_COMMAND_TEXT_X)
SHOP_COMMAND_Y = 2
SHOP_GOLD_X = 4
SHOP_GOLD_Y = 2
SHOP_BUY_LIST_VISIBLE_COUNT = 8
SHOP_LIST_VISIBLE_COUNT = 12
SHOP_ITEM_TEXT_X = 4
SHOP_ITEM_COUNT_X = 27
SHOP_ITEM_CURSOR_X = 2
SHOP_ITEM_FIRST_Y = 2
SHOP_ITEM_ROW_HEIGHT = 3
SHOP_BUY_PRICE_X = 4
SHOP_BUY_PRICE_Y = 29
SHOP_BUY_OWNED_X = 4
SHOP_BUY_OWNED_Y = 32
SHOP_INFO_X = 2
SHOP_INFO_Y = 2
SHOP_INFO_ROW_HEIGHT = 3
SHOP_INFO_MAX_ROWS = 12
SHOP_GREETING_X = 4
SHOP_GREETING_Y = 2
SHOP_GREETING_ROW_HEIGHT = 3
SHOP_MESSAGE_WINDOW_GRID = (0, 47, 64, 13)
SHOP_SELL_PRICE_WINDOW_GRID = (38, 47, 26, 7)
SHOP_SELL_PRICE_TEXT_X = 2
SHOP_SELL_PRICE_TEXT_Y = 2
QUANTITY_WINDOW_GRID = (10, 16, 44, 18)
QUANTITY_TEXT_X = 5
QUANTITY_FIRST_Y = 3
QUANTITY_TOTAL_Y = 6
QUANTITY_TOTAL_VALUE_X = 18
QUANTITY_PRICE_FIELD_WIDTH = 6
QUANTITY_NUMBER_RIGHT_X = (
    QUANTITY_TOTAL_VALUE_X + QUANTITY_PRICE_FIELD_WIDTH * 2
)
QUANTITY_GUIDE_X = 6
QUANTITY_GUIDE_Y = 12
QUANTITY_ARROW_BANK = 0
QUANTITY_ARROW_LEFT_SOURCE = (96, 0)
QUANTITY_ARROW_RIGHT_SOURCE = (104, 0)
QUANTITY_ARROW_WIDTH = 8
QUANTITY_ARROW_HEIGHT = 16
QUANTITY_ARROW_COLKEY = 1
QUANTITY_ARROW_LEFT_X = 22
QUANTITY_ARROW_RIGHT_X = 32
QUANTITY_TEXT_HEIGHT = 12
QUANTITY_ARROW_Y_ADJUSTMENT = 2
RARE_CHOICE_WINDOW_GRID = (50, 47, 14, 10)
RARE_CHOICE_X = 4
RARE_CURSOR_X = 2
RARE_YES_Y = 2
RARE_NO_Y = 5
FACES_IMAGE_ID = "faces/faces"


class ShopMode(StrEnum):
    BUY = "buy"
    SELL = "sell"


class ShopCommand(StrEnum):
    BUY = "buy"
    SELL = "sell"
    LEAVE = "leave"


class ShopPhase(Enum):
    COMMAND = "command"
    ITEM = "item"
    QUANTITY = "quantity"
    RARE_CONFIRMATION = "rare_confirmation"


class ShopUiDataError(RuntimeError):
    """Raised when shop data or required localized text is unavailable."""


class ShopOverlay:
    """Own shop cursors and quantity-selection state without owning game data."""

    def __init__(
        self,
        *,
        shop: Shop,
        shop_system: ShopSystem,
        party: tuple[Member, ...],
        inventory_system: InventorySystem,
        save_data: SaveData,
        spells: Mapping[str, Spell],
        settings: Settings,
        texts: TextCatalog,
        fonts: FontResources,
        faces: object | None = None,
        palette_shifter: PaletteShifter | None = None,
        on_invalid_action: Callable[[], None] | None = None,
        input_device: InputDevice = InputDevice.KEYBOARD,
    ) -> None:
        if not isinstance(shop, Shop):
            raise TypeError("shop must be a Shop")
        if not isinstance(shop_system, ShopSystem):
            raise TypeError("shop_system must be a ShopSystem")
        if shop not in shop_system.shops:
            raise ValueError(f"unknown shop: {shop.key!r}")
        if not party or not all(isinstance(member, Member) for member in party):
            raise TypeError("party must contain at least one Member")
        if not isinstance(inventory_system, InventorySystem):
            raise TypeError("inventory_system must be InventorySystem")
        if not isinstance(save_data, SaveData):
            raise TypeError("save_data must be SaveData")
        if not isinstance(spells, Mapping) or not all(
            isinstance(key, str) and isinstance(spell, Spell) and key == spell.key
            for key, spell in spells.items()
        ):
            raise TypeError("spells must map each string key to its matching Spell")
        if on_invalid_action is not None and not callable(on_invalid_action):
            raise TypeError("on_invalid_action must be callable")
        if not isinstance(input_device, InputDevice):
            raise TypeError("input_device must be an InputDevice")

        self.shop = shop
        self.shop_system = shop_system
        self.party = party
        self.inventory_system = inventory_system
        self.save_data = save_data
        self.spells = dict(spells)
        self.settings = settings
        self.texts = texts
        self.fonts = fonts
        self.faces = (
            faces if faces is not None else ImageResources().image(FACES_IMAGE_ID)
        )
        self.palette_shifter = palette_shifter
        self.on_invalid_action = on_invalid_action
        self.input_device = input_device
        self.phase = ShopPhase.COMMAND
        self.mode = ShopMode.BUY
        self.selected_item_index = 0
        self.scroll_offset = 0
        self.trade_quantity = 1
        self.trade_max_quantity = 0
        self.quantity_window = None
        self.quantity_value_text: WindowText | None = None
        self.completion_message_window = None
        self.sell_price_window = None
        self.rare_window = None
        self.rare_choice_window = None
        self.rare_cursor: WindowCursor | None = None
        self._build_windows()

    def _required_text(self, key: str) -> str:
        value = self.texts.text(key, self.localizer)
        if not value:
            raise ShopUiDataError(f"ショップ用テキストが見つかりません: {key}")
        return value

    @property
    def available_items(self) -> tuple[Item, ...]:
        if self.mode is ShopMode.BUY:
            return self.shop.items
        return tuple(item for item in self.inventory_system.items if item.price > 0)

    @property
    def selected_item(self) -> Item | None:
        items = self.available_items
        if not items:
            return None
        return items[self.selected_item_index]

    @property
    def unit_price(self) -> int:
        item = self.selected_item
        if item is None:
            return 0
        return (
            item.price
            if self.mode is ShopMode.BUY
            else self.shop_system.sale_unit_price(item)
        )

    @property
    def visible_item_count(self) -> int:
        return (
            SHOP_BUY_LIST_VISIBLE_COUNT
            if self.mode is ShopMode.BUY
            else SHOP_LIST_VISIBLE_COUNT
        )

    def _build_windows(self) -> None:
        self.localizer = Localizer(self.settings.language)
        self.localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )
        self._window_factory = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        self.greeting_window = self._build_shopkeeper_message_window(
            "shop.greeting"
        )
        self.sale_start_window = self._build_shopkeeper_message_window(
            "shop.sale.start"
        )
        self.party_panel = ShopPartyPanel(
            party=self.party,
            window_factory=self._window_factory,
            faces=self.faces,
            fonts=self.fonts,
            palette_shifter=self.palette_shifter,
        )
        self.party_window = self.party_panel.window
        self._build_trade_windows()

    def _build_shopkeeper_message_window(self, text_key: str) -> Window:
        lines = self.texts.lines(text_key, self.localizer)
        if not lines:
            raise ShopUiDataError(f"{text_key}が見つかりません")
        return self._window_factory.create(
            *SHOP_MESSAGE_WINDOW_GRID,
            tuple(
                self.localized_texts.create(
                    line,
                    SHOP_GREETING_X,
                    SHOP_GREETING_Y + row * SHOP_GREETING_ROW_HEIGHT,
                )
                for row, line in enumerate(lines)
            ),
        )

    def _build_trade_windows(self) -> None:
        self.command_window = self._window_factory.create(
            *SHOP_COMMAND_WINDOW_GRID,
            self._command_texts(),
        )
        self.gold_window = self._window_factory.create(
            *SHOP_GOLD_WINDOW_GRID,
            self._gold_texts(),
        )
        self.command_cursor = WindowCursor(
            self.command_window,
            tuple(
                CursorTarget(
                    SHOP_COMMAND_CURSOR_X[index],
                    SHOP_COMMAND_Y,
                    key=ShopCommand(key),
                )
                for index, (key, _text_key) in enumerate(SHOP_COMMANDS)
            ),
            active=self.phase is ShopPhase.COMMAND,
        )
        selected_command = ShopCommand(self.mode.value)
        self.command_cursor.select_key(selected_command)
        self._build_item_and_info_windows()

    def _command_texts(self) -> tuple[WindowText, ...]:
        return tuple(
            self.localized_texts.create(
                self._required_text(text_key),
                SHOP_COMMAND_TEXT_X[index],
                SHOP_COMMAND_Y,
            )
            for index, (_key, text_key) in enumerate(SHOP_COMMANDS)
        )

    def _gold_texts(self) -> tuple[WindowText, ...]:
        gold_text = self.texts.formatted_text(
            "shop.gold_display",
            self.localizer,
            {"GOLD": pad(self.save_data.gold, 6)},
        )
        if not gold_text:
            raise ShopUiDataError("shop.gold_displayが見つかりません")
        return (
            self.localized_texts.create(
                gold_text,
                SHOP_GOLD_X,
                SHOP_GOLD_Y,
            ),
        )

    def _build_sell_price_window(self) -> Window | None:
        if (
            self.phase is ShopPhase.COMMAND
            or self.mode is not ShopMode.SELL
            or self.completion_message_window is not None
        ):
            return None
        if self.selected_item is None:
            return None
        sale_price_text = self.texts.formatted_text(
            "shop.sale_price_display",
            self.localizer,
            {"PRICE": pad(self.unit_price, 6)},
        )
        if not sale_price_text:
            raise ShopUiDataError("shop.sale_price_displayが見つかりません")
        return self._window_factory.create(
            *SHOP_SELL_PRICE_WINDOW_GRID,
            (
                self.localized_texts.create(
                    sale_price_text,
                    SHOP_SELL_PRICE_TEXT_X,
                    SHOP_SELL_PRICE_TEXT_Y,
                ),
            ),
        )

    def _build_item_and_info_windows(self) -> None:
        items = self.available_items
        visible = (
            ()
            if self.phase is ShopPhase.COMMAND
            else items[
                self.scroll_offset : self.scroll_offset + self.visible_item_count
            ]
        )
        list_texts: list[WindowText] = []
        targets: list[CursorTarget] = []
        for row, item in enumerate(visible):
            y = SHOP_ITEM_FIRST_Y + row * SHOP_ITEM_ROW_HEIGHT
            list_texts.append(
                self.localized_texts.create(
                    str(item.localized_name(self.localizer)),
                    SHOP_ITEM_TEXT_X,
                    y,
                )
            )
            if self.mode is ShopMode.SELL:
                count_text = format_number(self.inventory_system.quantity(item))
                list_texts.append(
                    self.localized_texts.create(
                        count_text,
                        right_aligned_grid_x(
                            count_text,
                            reference_text=format_number(0),
                            reference_x=SHOP_ITEM_COUNT_X,
                            font=self.localized_texts,
                        ),
                        y,
                    )
                )
            targets.append(CursorTarget(SHOP_ITEM_CURSOR_X, y, key=item.key))

        selected = (
            None if self.phase is ShopPhase.COMMAND else self.selected_item
        )
        if self.mode is ShopMode.BUY and selected is not None:
            list_texts.extend(self._buy_summary_texts(selected))

        scrollable = len(items) > self.visible_item_count
        self.item_list_window = self._window_factory.create(
            *SHOP_LIST_WINDOW_GRID,
            tuple(list_texts),
            horizontal_navigation=scrollable,
            vertical_navigation=scrollable,
            active=self.phase is not ShopPhase.COMMAND,
        )
        self.item_cursor = WindowCursor(
            self.item_list_window,
            tuple(targets),
            active=self.phase is ShopPhase.ITEM,
        )
        if selected is not None and self.item_cursor.targets:
            self.item_cursor.select_key(selected.key)

        self.info_window = self._window_factory.create(
            *SHOP_INFO_WINDOW_GRID,
            self._info_texts(selected),
        )
        message_window = (
            self.completion_message_window
            if self.completion_message_window is not None
            else (
                self.party_window
                if self.mode is ShopMode.BUY
                and self.phase is not ShopPhase.COMMAND
                else (
                    self.sale_start_window
                    if self.mode is ShopMode.SELL
                    and self.phase is not ShopPhase.COMMAND
                    else self.greeting_window
                )
            )
        )
        self.sell_price_window = self._build_sell_price_window()
        windows = (
            self.command_window,
            self.gold_window,
            self.info_window,
            self.item_list_window,
            message_window,
        )
        self.windows = (
            windows
            if self.sell_price_window is None
            else (*windows, self.sell_price_window)
        )

    def _buy_summary_texts(self, item: Item) -> tuple[WindowText, ...]:
        price_text = self.texts.formatted_text(
            "shop.price_display",
            self.localizer,
            {"PRICE": pad(item.price, 6)},
        )
        owned_text = self.texts.formatted_text(
            "shop.owned_display",
            self.localizer,
            {
                "COUNT": format_number(
                    self.inventory_system.total_quantity(item, self.party)
                )
            },
        )
        if not price_text:
            raise ShopUiDataError("shop.price_displayが見つかりません")
        if not owned_text:
            raise ShopUiDataError("shop.owned_displayが見つかりません")
        return (
            self.localized_texts.create(
                price_text,
                SHOP_BUY_PRICE_X,
                SHOP_BUY_PRICE_Y,
            ),
            self.localized_texts.create(
                owned_text,
                SHOP_BUY_OWNED_X,
                SHOP_BUY_OWNED_Y,
            ),
        )

    def _info_texts(self, item: Item | None) -> tuple[WindowText, ...]:
        if item is None or self.phase is ShopPhase.COMMAND:
            return ()
        lines = build_item_detail(
            item,
            self.spells,
            self.localizer,
            self.texts,
            context=ItemDetailContext.SHOP,
        ).lines
        if len(lines) > SHOP_INFO_MAX_ROWS:
            raise ShopUiDataError(
                f"ショップのアイテム詳細が{SHOP_INFO_MAX_ROWS}行を超えています: {item.key}"
            )
        return tuple(
            self.localized_texts.create(
                line,
                SHOP_INFO_X,
                SHOP_INFO_Y + row * SHOP_INFO_ROW_HEIGHT,
            )
            for row, line in enumerate(lines)
            if line
        )

    def _refresh_trade_windows(self) -> None:
        self._build_trade_windows()
        if self.phase is not ShopPhase.COMMAND:
            self.command_cursor.active = False

    def _enter_item_selection(self, command: ShopCommand) -> None:
        if not isinstance(command, ShopCommand) or command is ShopCommand.LEAVE:
            raise ShopUiDataError("ショップコマンドが選択されていません")
        self.mode = ShopMode(command.value)
        self.selected_item_index = 0
        self.scroll_offset = 0
        self.completion_message_window = None
        if not self.available_items:
            self._invalid_action()
            return
        self.phase = ShopPhase.ITEM
        self._refresh_trade_windows()

    def _return_to_commands(self) -> None:
        self.phase = ShopPhase.COMMAND
        self.quantity_window = None
        self.quantity_value_text = None
        self.completion_message_window = None
        self.rare_window = None
        self.rare_choice_window = None
        self.rare_cursor = None
        self._refresh_trade_windows()

    def _move_item(self, distance: int) -> None:
        items = self.available_items
        if not items:
            return
        previous = self.selected_item_index
        self.selected_item_index = (previous + distance) % len(items)
        if self.selected_item_index == 0 and previous == len(items) - 1:
            self.scroll_offset = 0
        elif self.selected_item_index == len(items) - 1 and previous == 0:
            self.scroll_offset = max(0, len(items) - self.visible_item_count)
        elif self.selected_item_index < self.scroll_offset:
            self.scroll_offset = self.selected_item_index
        elif self.selected_item_index >= self.scroll_offset + self.visible_item_count:
            self.scroll_offset = self.selected_item_index - self.visible_item_count + 1
        if self.mode is ShopMode.BUY:
            self.completion_message_window = None
        self._refresh_trade_windows()

    def _move_page(self, distance: int) -> None:
        items = self.available_items
        if not items:
            return
        next_index = self.selected_item_index + distance * self.visible_item_count
        if next_index < 0:
            next_index = len(items) - 1
        elif next_index >= len(items):
            next_index = 0
        self.selected_item_index = next_index
        self.scroll_offset = min(
            (next_index // self.visible_item_count) * self.visible_item_count,
            max(0, len(items) - self.visible_item_count),
        )
        if self.mode is ShopMode.BUY:
            self.completion_message_window = None
        self._refresh_trade_windows()

    def _trade_max(self, item: Item) -> int:
        return (
            self.shop_system.max_buy_quantity(self.shop, item)
            if self.mode is ShopMode.BUY
            else self.shop_system.max_sell_quantity(item)
        )

    def _start_quantity_selection(self) -> None:
        item = self.selected_item
        if item is None:
            return
        maximum = self._trade_max(item)
        if maximum <= 0:
            self._invalid_action()
            return
        self.phase = ShopPhase.QUANTITY
        self.trade_quantity = 1
        self.trade_max_quantity = maximum
        self.completion_message_window = None
        self._refresh_trade_windows()
        self._build_quantity_window()

    def _build_quantity_window(self) -> None:
        total_text = self.texts.formatted_text(
            "shop.price_display",
            self.localizer,
            {"PRICE": pad(self.unit_price * self.trade_quantity, 6)},
        )
        if not total_text:
            raise ShopUiDataError("shop.price_displayが見つかりません")
        quantity = format_number(self.trade_quantity)
        quantity_width = self.localized_texts.text_width(quantity)
        quantity_x = (
            QUANTITY_NUMBER_RIGHT_X * 4 - quantity_width + 2
        ) // 4
        self.quantity_value_text = self.localized_texts.create(
            quantity,
            quantity_x,
            QUANTITY_FIRST_Y,
        )
        guide = self._required_text("shop.quantity.guide")
        if guide.count("%CONFIRM%") != 1 or guide.count("%CANCEL%") != 1:
            raise ShopUiDataError(
                "shop.quantity.guideには%CONFIRM%と%CANCEL%が1つずつ必要です"
            )
        guide = guide.replace(
            "%CONFIRM%",
            input_icon_tag(InputAction.CONFIRM, self.input_device),
        ).replace(
            "%CANCEL%",
            input_icon_tag(InputAction.CANCEL, self.input_device),
        )
        texts = (
            self.localized_texts.create(
                self._required_text("shop.quantity"),
                QUANTITY_TEXT_X,
                QUANTITY_FIRST_Y,
            ),
            self.quantity_value_text,
            self.localized_texts.create(
                self._required_text("shop.total"),
                QUANTITY_TEXT_X,
                QUANTITY_TOTAL_Y,
            ),
            self.localized_texts.create(
                total_text,
                QUANTITY_TOTAL_VALUE_X,
                QUANTITY_TOTAL_Y,
            ),
            self.localized_texts.create(
                guide,
                QUANTITY_GUIDE_X,
                QUANTITY_GUIDE_Y,
            ),
        )
        self.quantity_window = self._window_factory.create(
            *QUANTITY_WINDOW_GRID,
            texts,
        )

    def _change_quantity(self, distance: int) -> None:
        self.trade_quantity = min(
            self.trade_max_quantity,
            max(1, self.trade_quantity + distance),
        )
        self._build_quantity_window()

    def _confirm_quantity(self) -> None:
        item = self.selected_item
        if item is None:
            return
        if self.mode is ShopMode.SELL and self.shop_system.is_rare_sale(item):
            self._start_rare_confirmation()
            return
        self._finish_transaction()

    def _start_rare_confirmation(self) -> None:
        yes = self._required_text("settings.yes")
        no = self._required_text("settings.no")
        self.phase = ShopPhase.RARE_CONFIRMATION
        self.quantity_window = None
        self.rare_window = self._build_shopkeeper_message_window(
            "shop.rare.confirm"
        )
        self.rare_choice_window = self._window_factory.create(
            *RARE_CHOICE_WINDOW_GRID,
            (
                self.localized_texts.create(yes, RARE_CHOICE_X, RARE_YES_Y),
                self.localized_texts.create(no, RARE_CHOICE_X, RARE_NO_Y),
            ),
        )
        self.rare_cursor = WindowCursor(
            self.rare_choice_window,
            (
                CursorTarget(RARE_CURSOR_X, RARE_YES_Y, key="yes"),
                CursorTarget(RARE_CURSOR_X, RARE_NO_Y, key="no"),
            ),
        )

    def _finish_transaction(self) -> None:
        item = self.selected_item
        if item is None:
            return
        changed = (
            self.shop_system.buy(self.shop, item, self.trade_quantity)
            if self.mode is ShopMode.BUY
            else self.shop_system.sell(item, self.trade_quantity)
        )
        if not changed:
            self._invalid_action()
            self.phase = ShopPhase.ITEM
        else:
            self.phase = ShopPhase.ITEM
            completion_key = (
                "shop.purchase.complete"
                if self.mode is ShopMode.BUY
                else "shop.sale.complete"
            )
            self.completion_message_window = (
                self._build_shopkeeper_message_window(completion_key)
            )
        self.quantity_window = None
        self.quantity_value_text = None
        self.rare_window = None
        self.rare_choice_window = None
        self.rare_cursor = None
        items = self.available_items
        if items:
            self.selected_item_index = min(self.selected_item_index, len(items) - 1)
            self.scroll_offset = min(
                self.scroll_offset,
                max(0, len(items) - self.visible_item_count),
            )
        else:
            self._return_to_commands()
            return
        self._refresh_trade_windows()

    def _cancel_rare_confirmation(self) -> None:
        self.phase = ShopPhase.ITEM
        self.rare_window = None
        self.rare_choice_window = None
        self.rare_cursor = None
        self._refresh_trade_windows()

    def _invalid_action(self) -> None:
        if self.on_invalid_action is not None:
            self.on_invalid_action()

    def update(self, input_state: InputState) -> bool:
        """Update shop state and return whether the shop should close."""

        self.item_list_window.set_vertical_navigation_pressed()
        if self.phase is ShopPhase.RARE_CONFIRMATION:
            if self.rare_cursor is None:
                raise ShopUiDataError("レア売却確認カーソルがありません")
            if input_state.cancel.triggered:
                self._cancel_rare_confirmation()
                return False
            if input_state.confirm.triggered:
                if self.rare_cursor.selected_key == "yes":
                    self._finish_transaction()
                else:
                    self._cancel_rare_confirmation()
                return False
            self.rare_cursor.update(input_state.navigation)
            return False

        if self.phase is ShopPhase.QUANTITY:
            if input_state.cancel.triggered:
                self.phase = ShopPhase.ITEM
                self.quantity_window = None
                self.quantity_value_text = None
                self._refresh_trade_windows()
                return False
            if input_state.confirm.triggered:
                self._confirm_quantity()
                return False
            if input_state.navigation is not None and input_state.navigation.dx:
                self._change_quantity(-1 if input_state.navigation.dx < 0 else 1)
            return False

        if self.phase is ShopPhase.COMMAND:
            if input_state.cancel.triggered:
                return True
            if input_state.confirm.triggered:
                command = self.command_cursor.selected_key
                if not isinstance(command, ShopCommand):
                    raise ShopUiDataError("ショップコマンドが選択されていません")
                if command is ShopCommand.LEAVE:
                    return True
                self._enter_item_selection(command)
                return False
            self.command_cursor.update(input_state.navigation)
            command = self.command_cursor.selected_key
            if isinstance(command, ShopCommand) and command is not ShopCommand.LEAVE:
                self.mode = ShopMode(command.value)
            return False

        if input_state.cancel.triggered:
            self._return_to_commands()
            return False
        if input_state.confirm.triggered:
            self._start_quantity_selection()
            return False
        if input_state.previous_page.triggered:
            self._move_page(-1)
            return False
        if input_state.next_page.triggered:
            self._move_page(1)
            return False
        navigation = input_state.navigation
        if navigation is not None:
            if navigation.dx and self.mode is ShopMode.SELL:
                self._move_page(-1 if navigation.dx < 0 else 1)
            elif navigation.dy < 0:
                self._move_item(-1)
                self.item_list_window.set_vertical_navigation_pressed(-1)
            elif navigation.dy > 0:
                self._move_item(1)
                self.item_list_window.set_vertical_navigation_pressed(1)
        return False

    def draw(self) -> None:
        for window in self.windows:
            window.draw()
        if self.party_window in self.windows:
            self.party_panel.draw(self.selected_item)
        self.command_cursor.draw()
        if self.phase is not ShopPhase.COMMAND:
            self.item_cursor.draw()
        if self.quantity_window is not None:
            self.quantity_window.draw()
            self._draw_quantity_arrows()
        if self.rare_window is not None:
            self.rare_window.draw()
        if self.rare_choice_window is not None:
            self.rare_choice_window.draw()
        if self.rare_cursor is not None:
            self.rare_cursor.draw()

    def _draw_quantity_arrows(self) -> None:
        if (
            self.quantity_window is None
            or self.quantity_value_text is None
            or self.trade_max_quantity <= 1
        ):
            return
        _value_x, value_y = self.quantity_window.text_position(
            self.quantity_value_text
        )
        arrow_y = (
            value_y
            - (QUANTITY_ARROW_HEIGHT - QUANTITY_TEXT_HEIGHT) // 2
            + QUANTITY_ARROW_Y_ADJUSTMENT
        )
        pyxel.blt(
            self.quantity_window.pixel_x + QUANTITY_ARROW_LEFT_X * 4,
            arrow_y,
            QUANTITY_ARROW_BANK,
            QUANTITY_ARROW_LEFT_SOURCE[0],
            QUANTITY_ARROW_LEFT_SOURCE[1],
            QUANTITY_ARROW_WIDTH,
            QUANTITY_ARROW_HEIGHT,
            QUANTITY_ARROW_COLKEY,
        )
        pyxel.blt(
            self.quantity_window.pixel_x + QUANTITY_ARROW_RIGHT_X * 4,
            arrow_y,
            QUANTITY_ARROW_BANK,
            QUANTITY_ARROW_RIGHT_SOURCE[0],
            QUANTITY_ARROW_RIGHT_SOURCE[1],
            QUANTITY_ARROW_WIDTH,
            QUANTITY_ARROW_HEIGHT,
            QUANTITY_ARROW_COLKEY,
        )


__all__ = [
    "ShopCommand",
    "ShopMode",
    "ShopOverlay",
    "ShopPhase",
    "ShopUiDataError",
]
