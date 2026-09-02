"""ZERO shop view used by the connected menu-screen mock."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from enum import Enum, StrEnum

import pyxel

from tools._bootstrap import APP_ROOT
from input import InputAction, InputDevice, InputState
from item import Item
from item_detail import ItemDetailContext, build_item_detail
from localization import Localizer, format_number
from member import Member
from resources import FontResources
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
SHOP_LIST_VISIBLE_COUNT = 12
SHOP_ITEM_TEXT_X = 4
SHOP_ITEM_COUNT_X = 27
SHOP_ITEM_CURSOR_X = 2
SHOP_ITEM_FIRST_Y = 2
SHOP_ITEM_ROW_HEIGHT = 3
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
MOCK_INPUT_DEVICE = InputDevice.KEYBOARD
RARE_WINDOW_GRID = (4, 13, 56, 22)
RARE_TEXT_X = 4
RARE_TEXT_Y = 3
RARE_CHOICE_X = 40
RARE_CURSOR_X = 38
RARE_YES_Y = 11
RARE_NO_Y = 15


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


class ShopMockDataError(RuntimeError):
    """Raised when shop data or required localized text is unavailable."""


class ShopScreenMock:
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
        on_invalid_action: Callable[[], None] | None = None,
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

        self.shop = shop
        self.shop_system = shop_system
        self.party = party
        self.inventory_system = inventory_system
        self.save_data = save_data
        self.spells = dict(spells)
        self.settings = settings
        self.texts = texts
        self.fonts = fonts
        self.on_invalid_action = on_invalid_action
        self.phase = ShopPhase.COMMAND
        self.mode = ShopMode.BUY
        self.selected_item_index = 0
        self.scroll_offset = 0
        self.trade_quantity = 1
        self.trade_max_quantity = 0
        self.quantity_window = None
        self.quantity_value_text: WindowText | None = None
        self.purchase_message_window = None
        self.sell_price_window = None
        self.rare_window = None
        self.rare_cursor: WindowCursor | None = None
        self._build_windows()

    def _required_text(self, key: str) -> str:
        value = self.texts.text(key, self.localizer)
        if not value:
            raise ShopMockDataError(f"ショップモック用テキストが見つかりません: {key}")
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
        self._build_trade_windows()

    def _build_shopkeeper_message_window(self, text_key: str) -> Window:
        lines = self.texts.lines(text_key, self.localizer)
        if not lines:
            raise ShopMockDataError(f"{text_key}が見つかりません")
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
            raise ShopMockDataError("shop.gold_displayが見つかりません")
        return (
            self.localized_texts.create(
                gold_text,
                SHOP_GOLD_X,
                SHOP_GOLD_Y,
            ),
        )

    def _build_sell_price_window(self) -> Window | None:
        if self.phase is ShopPhase.COMMAND or self.mode is not ShopMode.SELL:
            return None
        if self.selected_item is None:
            return None
        sale_price_text = self.texts.formatted_text(
            "shop.sale_price_display",
            self.localizer,
            {"PRICE": pad(self.unit_price, 6)},
        )
        if not sale_price_text:
            raise ShopMockDataError("shop.sale_price_displayが見つかりません")
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
                self.scroll_offset : self.scroll_offset + SHOP_LIST_VISIBLE_COUNT
            ]
        )
        list_texts: list[WindowText] = []
        targets: list[CursorTarget] = []
        for row, item in enumerate(visible):
            y = SHOP_ITEM_FIRST_Y + row * SHOP_ITEM_ROW_HEIGHT
            list_texts.extend(
                (
                    self.localized_texts.create(
                        str(item.localized_name(self.localizer)),
                        SHOP_ITEM_TEXT_X,
                        y,
                    ),
                    self.localized_texts.create(
                        format_number(
                            self.inventory_system.total_quantity(
                                item,
                                self.party,
                            )
                        ),
                        SHOP_ITEM_COUNT_X,
                        y,
                    ),
                )
            )
            targets.append(CursorTarget(SHOP_ITEM_CURSOR_X, y, key=item.key))

        selected = (
            None if self.phase is ShopPhase.COMMAND else self.selected_item
        )
        scrollable = len(items) > SHOP_LIST_VISIBLE_COUNT
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
            self.purchase_message_window
            if self.purchase_message_window is not None
            else self.greeting_window
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
            raise ShopMockDataError(
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
            raise ShopMockDataError("ショップコマンドが選択されていません")
        self.mode = ShopMode(command.value)
        self.selected_item_index = 0
        self.scroll_offset = 0
        self.purchase_message_window = None
        if not self.available_items:
            self._invalid_action()
            return
        self.phase = ShopPhase.ITEM
        self._refresh_trade_windows()

    def _return_to_commands(self) -> None:
        self.phase = ShopPhase.COMMAND
        self.quantity_window = None
        self.quantity_value_text = None
        self.purchase_message_window = None
        self.rare_window = None
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
            self.scroll_offset = max(0, len(items) - SHOP_LIST_VISIBLE_COUNT)
        elif self.selected_item_index < self.scroll_offset:
            self.scroll_offset = self.selected_item_index
        elif self.selected_item_index >= self.scroll_offset + SHOP_LIST_VISIBLE_COUNT:
            self.scroll_offset = self.selected_item_index - SHOP_LIST_VISIBLE_COUNT + 1
        self.purchase_message_window = None
        self._refresh_trade_windows()

    def _move_page(self, distance: int) -> None:
        items = self.available_items
        if not items:
            return
        next_index = self.selected_item_index + distance * SHOP_LIST_VISIBLE_COUNT
        if next_index < 0:
            next_index = len(items) - 1
        elif next_index >= len(items):
            next_index = 0
        self.selected_item_index = next_index
        self.scroll_offset = min(
            (next_index // SHOP_LIST_VISIBLE_COUNT) * SHOP_LIST_VISIBLE_COUNT,
            max(0, len(items) - SHOP_LIST_VISIBLE_COUNT),
        )
        self.purchase_message_window = None
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
        self.purchase_message_window = None
        self._refresh_trade_windows()
        self._build_quantity_window()

    def _build_quantity_window(self) -> None:
        total_text = self.texts.formatted_text(
            "shop.price_display",
            self.localizer,
            {"PRICE": pad(self.unit_price * self.trade_quantity, 6)},
        )
        if not total_text:
            raise ShopMockDataError("shop.price_displayが見つかりません")
        quantity = format_number(self.trade_quantity)
        quantity_width = self.localized_texts.font.text_width(quantity)
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
            raise ShopMockDataError(
                "shop.quantity.guideには%CONFIRM%と%CANCEL%が1つずつ必要です"
            )
        guide = guide.replace(
            "%CONFIRM%",
            input_icon_tag(InputAction.CONFIRM, MOCK_INPUT_DEVICE),
        ).replace(
            "%CANCEL%",
            input_icon_tag(InputAction.CANCEL, MOCK_INPUT_DEVICE),
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
        lines = self.texts.lines("shop.rare.confirm", self.localizer)
        yes = self._required_text("settings.yes")
        no = self._required_text("settings.no")
        if not lines:
            raise ShopMockDataError("shop.rare.confirmが見つかりません")
        texts = [
            self.localized_texts.create(
                line,
                RARE_TEXT_X,
                RARE_TEXT_Y + row * SHOP_INFO_ROW_HEIGHT,
            )
            for row, line in enumerate(lines)
        ]
        texts.extend(
            (
                self.localized_texts.create(yes, RARE_CHOICE_X, RARE_YES_Y),
                self.localized_texts.create(no, RARE_CHOICE_X, RARE_NO_Y),
            )
        )
        self.phase = ShopPhase.RARE_CONFIRMATION
        self.quantity_window = None
        self.rare_window = self._window_factory.create(
            *RARE_WINDOW_GRID,
            tuple(texts),
        )
        self.rare_cursor = WindowCursor(
            self.rare_window,
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
            self.purchase_message_window = (
                self._build_shopkeeper_message_window("shop.purchase.complete")
                if self.mode is ShopMode.BUY
                else None
            )
        self.quantity_window = None
        self.quantity_value_text = None
        self.rare_window = None
        self.rare_cursor = None
        items = self.available_items
        if items:
            self.selected_item_index = min(self.selected_item_index, len(items) - 1)
            self.scroll_offset = min(
                self.scroll_offset,
                max(0, len(items) - SHOP_LIST_VISIBLE_COUNT),
            )
        else:
            self._return_to_commands()
            return
        self._refresh_trade_windows()

    def _cancel_rare_confirmation(self) -> None:
        self.phase = ShopPhase.ITEM
        self.rare_window = None
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
                raise ShopMockDataError("レア売却確認カーソルがありません")
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
                    raise ShopMockDataError("ショップコマンドが選択されていません")
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
            if navigation.dy < 0:
                self._move_item(-1)
                self.item_list_window.set_vertical_navigation_pressed(-1)
            elif navigation.dy > 0:
                self._move_item(1)
                self.item_list_window.set_vertical_navigation_pressed(1)
        return False

    def draw(self) -> None:
        for window in self.windows:
            window.draw()
        self.command_cursor.draw()
        if self.phase is ShopPhase.ITEM:
            self.item_cursor.draw()
        if self.quantity_window is not None:
            self.quantity_window.draw()
            self._draw_quantity_arrows()
        if self.rare_window is not None:
            self.rare_window.draw()
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
    "ShopMockDataError",
    "ShopMode",
    "ShopPhase",
    "ShopScreenMock",
]
