from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_shops,
    load_mock_skills,
    load_mock_spells,
)
from tools.screen_mocks.shop import (
    QUANTITY_ARROW_HEIGHT,
    QUANTITY_ARROW_LEFT_X,
    QUANTITY_ARROW_LEFT_SOURCE,
    QUANTITY_ARROW_RIGHT_X,
    QUANTITY_ARROW_RIGHT_SOURCE,
    QUANTITY_ARROW_WIDTH,
    QUANTITY_ARROW_Y_ADJUSTMENT,
    QUANTITY_GUIDE_Y,
    QUANTITY_NUMBER_RIGHT_X,
    QUANTITY_PRICE_FIELD_WIDTH,
    QUANTITY_TEXT_HEIGHT,
    QUANTITY_TOTAL_VALUE_X,
    QUANTITY_TOTAL_Y,
    SHOP_COMMAND_WINDOW_GRID,
    SHOP_COMMAND_TEXT_X,
    SHOP_GOLD_WINDOW_GRID,
    SHOP_GREETING_ROW_HEIGHT,
    SHOP_GREETING_Y,
    SHOP_INFO_WINDOW_GRID,
    SHOP_INFO_MAX_ROWS,
    SHOP_INFO_Y,
    SHOP_ITEM_COUNT_X,
    SHOP_ITEM_FIRST_Y,
    SHOP_ITEM_ROW_HEIGHT,
    SHOP_LIST_VISIBLE_COUNT,
    SHOP_LIST_WINDOW_GRID,
    SHOP_MESSAGE_WINDOW_GRID,
    SHOP_SELL_PRICE_TEXT_X,
    SHOP_SELL_PRICE_TEXT_Y,
    SHOP_SELL_PRICE_WINDOW_GRID,
    ShopCommand,
    ShopMode,
    ShopPhase,
    ShopScreenMock,
)
from input import Direction, InputButton, InputState
from resources import FontResources
from state import SaveData, Settings
from systems import MAX_GOLD, InventorySystem, ShopSystem
from text_catalog import TextCatalog


class ShopScreenMockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.items = load_mock_items()
        self.party = load_mock_party(self.items, load_mock_skills())
        self.shops = load_mock_shops(self.items)
        self.inventory = InventorySystem.with_one_each(self.items)
        self.save_data = SaveData(gold=MAX_GOLD)
        self.system = ShopSystem(
            shops=self.shops,
            inventory=self.inventory,
            party=self.party,
            save_data=self.save_data,
        )
        self.invalid_action = Mock()
        self.screen = ShopScreenMock(
            shop=self.shops[0],
            shop_system=self.system,
            party=self.party,
            inventory_system=self.inventory,
            save_data=self.save_data,
            spells=load_mock_spells(),
            settings=Settings(),
            texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
            fonts=FontResources(),
            on_invalid_action=self.invalid_action,
        )

    def test_builds_da2_split_layout_without_shopkeeper_portrait(self) -> None:
        self.assertEqual(
            tuple((window.x, window.y, window.width, window.height) for window in self.screen.windows),
            (
                SHOP_COMMAND_WINDOW_GRID,
                SHOP_GOLD_WINDOW_GRID,
                SHOP_INFO_WINDOW_GRID,
                SHOP_LIST_WINDOW_GRID,
                SHOP_MESSAGE_WINDOW_GRID,
            ),
        )
        self.assertIs(self.screen.phase, ShopPhase.COMMAND)
        self.assertIs(self.screen.mode, ShopMode.BUY)
        self.assertEqual(
            [target.key for target in self.screen.command_cursor.targets],
            [ShopCommand.BUY, ShopCommand.SELL, ShopCommand.LEAVE],
        )
        self.assertEqual(
            [text.text for text in self.screen.command_window.texts],
            ["かう", "うる", "みせをでる"],
        )
        self.assertEqual(
            [text.x for text in self.screen.command_window.texts],
            list(SHOP_COMMAND_TEXT_X),
        )
        self.assertEqual(
            [text.text for text in self.screen.gold_window.texts],
            ["９９９９９９Ｇ"],
        )
        self.assertEqual(SHOP_LIST_WINDOW_GRID[1], SHOP_INFO_WINDOW_GRID[1])
        self.assertEqual(SHOP_COMMAND_WINDOW_GRID, (0, 0, 44, 7))
        self.assertEqual(SHOP_GOLD_WINDOW_GRID, (44, 0, 20, 7))
        self.assertEqual(SHOP_LIST_WINDOW_GRID, (0, 7, 32, 40))
        self.assertEqual(SHOP_INFO_WINDOW_GRID, (31, 7, 33, 40))
        self.assertEqual(SHOP_INFO_Y, 2)
        self.assertEqual(SHOP_INFO_MAX_ROWS, 12)
        self.assertIs(self.screen.windows[-1], self.screen.greeting_window)
        self.assertEqual(
            [text.text for text in self.screen.greeting_window.texts],
            ["「いらっしゃい！", "　きょうは　どんな　ようかしら？"],
        )
        self.assertEqual(
            [text.y for text in self.screen.greeting_window.texts],
            [SHOP_GREETING_Y, SHOP_GREETING_Y + SHOP_GREETING_ROW_HEIGHT],
        )
        self.assertEqual(SHOP_GREETING_ROW_HEIGHT * 4, 12)
        self.assertEqual(self.screen.item_list_window.texts, ())
        self.assertEqual(self.screen.info_window.texts, ())
        self.assertFalse(hasattr(self.screen, "party_panel"))
        self.assertFalse(hasattr(self.screen, "party_window"))
        self.assertEqual(SHOP_MESSAGE_WINDOW_GRID, (0, 47, 64, 13))
        self.assertEqual(
            [item.key for item in self.screen.shop.items],
            [
                "POTION",
                "MANA DROP",
                "DAGGER",
                "WAND of POISON",
                "ROBE",
                "LEATHER CAP",
            ],
        )
        self.assertFalse(hasattr(self.screen, "shopkeeper_face"))

    def test_buy_uses_item_then_quantity_then_confirmation_flow(self) -> None:
        before_gold = self.save_data.gold
        before_count = self.inventory.quantity("POTION")

        self.screen.update(InputState(confirm=InputButton(triggered=True)))
        self.assertIs(self.screen.phase, ShopPhase.ITEM)
        self.assertEqual(self.screen.selected_item.key, "POTION")

        self.screen.update(InputState(confirm=InputButton(triggered=True)))
        self.assertIs(self.screen.phase, ShopPhase.QUANTITY)
        self.assertEqual(self.screen.trade_quantity, 1)
        self.screen.update(InputState(navigation=Direction.RIGHT))
        self.screen.update(InputState(navigation=Direction.RIGHT))
        self.assertEqual(self.screen.trade_quantity, 3)

        self.screen.update(InputState(confirm=InputButton(triggered=True)))

        self.assertIs(self.screen.phase, ShopPhase.ITEM)
        self.assertEqual(self.inventory.quantity("POTION"), before_count + 3)
        self.assertEqual(self.save_data.gold, before_gold - 150)
        self.assertIsNotNone(self.screen.purchase_message_window)
        self.assertIs(
            self.screen.windows[-1],
            self.screen.purchase_message_window,
        )
        self.assertEqual(
            [text.text for text in self.screen.purchase_message_window.texts],
            ["「ありがとね！　ほかにもどう？"],
        )

        self.screen.update(InputState(navigation=Direction.DOWN))

        self.assertIsNone(self.screen.purchase_message_window)
        self.assertIs(self.screen.windows[-1], self.screen.greeting_window)

    @patch("tools.screen_mocks.shop.Window.draw")
    def test_selected_command_keeps_an_inactive_cursor(
        self,
        _draw_window: Mock,
    ) -> None:
        self.screen.update(InputState(confirm=InputButton(triggered=True)))
        self.assertIs(self.screen.command_cursor.selected_key, ShopCommand.BUY)
        self.assertFalse(self.screen.command_cursor.active)
        self.screen.command_cursor.draw = Mock()
        self.screen.item_cursor.draw = Mock()

        self.screen.draw()

        self.screen.command_cursor.draw.assert_called_once_with()

    def test_quantity_selection_works_for_non_first_shop_items(self) -> None:
        self.screen.update(InputState(confirm=InputButton(triggered=True)))

        for expected_key in ("MANA DROP", "DAGGER"):
            self.screen.update(InputState(navigation=Direction.DOWN))
            self.assertEqual(self.screen.selected_item.key, expected_key)

            self.screen.update(InputState(confirm=InputButton(triggered=True)))

            self.assertIs(self.screen.phase, ShopPhase.QUANTITY)
            self.assertEqual(self.screen.quantity_value_text.text, "１")
            self.screen.update(InputState(cancel=InputButton(triggered=True)))
            self.assertIs(self.screen.phase, ShopPhase.ITEM)

    @patch("tools.screen_mocks.shop.pyxel.blt")
    def test_quantity_window_shows_current_total_guide_and_inline_arrows(
        self,
        blt: Mock,
    ) -> None:
        self.screen.update(InputState(confirm=InputButton(triggered=True)))
        self.screen.update(InputState(confirm=InputButton(triggered=True)))

        texts = self.screen.quantity_window.texts
        self.assertEqual(
            [(text.text, text.y) for text in texts],
            [
                ("こすう", 4),
                ("１", 4),
                ("ごうけい", QUANTITY_TOTAL_Y),
                ("　　　　５０　Ｇｏｌｄ", QUANTITY_TOTAL_Y),
                (
                    "%KEY_Z%：けってい　%KEY_X%：キャンセル",
                    QUANTITY_GUIDE_Y,
                ),
            ],
        )
        quantity_text = self.screen.quantity_value_text
        total_text = self.screen.quantity_window.texts[3]
        quantity_right = (
            quantity_text.x * 4
            + quantity_text.font.text_width(quantity_text.text)
        )
        total_number_right = (
            total_text.x * 4
            + total_text.font.text_width(
                total_text.text[:QUANTITY_PRICE_FIELD_WIDTH]
            )
        )
        self.assertEqual(quantity_right, total_number_right)
        self.assertEqual(quantity_right, QUANTITY_NUMBER_RIGHT_X * 4)
        self.assertEqual(
            QUANTITY_NUMBER_RIGHT_X,
            QUANTITY_TOTAL_VALUE_X + QUANTITY_PRICE_FIELD_WIDTH * 2,
        )
        self.assertFalse(self.screen.quantity_window.horizontal_navigation)
        self.assertFalse(any("／" in text.text for text in texts))
        self.assertFalse(any("たんか" in text.text for text in texts))

        self.screen._draw_quantity_arrows()

        self.assertEqual(blt.call_count, 2)
        self.assertEqual(
            blt.call_args_list[0].args[3:7],
            (
                QUANTITY_ARROW_LEFT_SOURCE[0],
                QUANTITY_ARROW_LEFT_SOURCE[1],
                QUANTITY_ARROW_WIDTH,
                QUANTITY_ARROW_HEIGHT,
            ),
        )
        self.assertEqual(
            blt.call_args_list[1].args[3:7],
            (
                QUANTITY_ARROW_RIGHT_SOURCE[0],
                QUANTITY_ARROW_RIGHT_SOURCE[1],
                QUANTITY_ARROW_WIDTH,
                QUANTITY_ARROW_HEIGHT,
            ),
        )
        _value_x, value_y = self.screen.quantity_window.text_position(
            self.screen.quantity_value_text
        )
        self.assertEqual(
            blt.call_args_list[0].args[0],
            self.screen.quantity_window.pixel_x + QUANTITY_ARROW_LEFT_X * 4,
        )
        self.assertEqual(
            blt.call_args_list[1].args[0],
            self.screen.quantity_window.pixel_x + QUANTITY_ARROW_RIGHT_X * 4,
        )
        self.assertEqual(
            blt.call_args_list[0].args[1],
            value_y
            - (QUANTITY_ARROW_HEIGHT - QUANTITY_TEXT_HEIGHT) // 2
            + QUANTITY_ARROW_Y_ADJUSTMENT,
        )

        self.screen.trade_quantity = 9
        self.screen._build_quantity_window()
        blt.reset_mock()
        self.screen._draw_quantity_arrows()
        arrow_positions_at_nine = [
            call.args[:2] for call in blt.call_args_list
        ]
        self.screen.update(InputState(navigation=Direction.RIGHT))
        blt.reset_mock()
        self.screen._draw_quantity_arrows()

        self.assertEqual(self.screen.quantity_window.texts[1].text, "１０")
        self.assertEqual(
            self.screen.quantity_window.texts[3].text,
            "　　　５００　Ｇｏｌｄ",
        )
        quantity_text = self.screen.quantity_value_text
        total_text = self.screen.quantity_window.texts[3]
        self.assertEqual(
            quantity_text.x * 4
            + quantity_text.font.text_width(quantity_text.text),
            total_text.x * 4
            + total_text.font.text_width(
                total_text.text[:QUANTITY_PRICE_FIELD_WIDTH]
            ),
        )
        self.assertEqual(
            [call.args[:2] for call in blt.call_args_list],
            arrow_positions_at_nine,
        )

    def test_item_list_uses_all_rows_for_names_and_owned_counts(self) -> None:
        self.screen.update(InputState(confirm=InputButton(triggered=True)))

        self.assertIs(self.screen.windows[-1], self.screen.greeting_window)
        self.assertLess(
            self.screen.windows.index(self.screen.info_window),
            self.screen.windows.index(self.screen.item_list_window),
        )
        list_texts = {
            (text.x, text.y): text.text
            for text in self.screen.item_list_window.texts
        }
        self.assertEqual(
            list_texts[(4, 2)],
            "きずぐすり",
        )
        self.assertEqual(
            list_texts[(SHOP_ITEM_COUNT_X, 2)],
            "１",
        )
        self.assertEqual(
            len(self.screen.item_list_window.texts),
            len(self.screen.shop.items) * 2,
        )
        self.assertFalse(
            any("Ｇｏｌｄ" in text.text for text in self.screen.item_list_window.texts)
        )
        self.assertEqual(SHOP_LIST_VISIBLE_COUNT, 12)

    def test_sell_overlays_unit_price_on_shopkeeper_message(self) -> None:
        self.screen.update(InputState(navigation=Direction.RIGHT))
        self.screen.update(InputState(confirm=InputButton(triggered=True)))

        self.assertIs(self.screen.mode, ShopMode.SELL)
        self.assertTrue(self.screen.item_list_window.horizontal_navigation)
        self.assertEqual(len(self.screen.item_cursor.targets), 12)
        self.assertEqual(
            self.screen.item_cursor.targets[-1].y,
            SHOP_ITEM_FIRST_Y + 11 * SHOP_ITEM_ROW_HEIGHT,
        )
        self.assertIsNotNone(self.screen.sell_price_window)
        self.assertIs(self.screen.windows[-2], self.screen.greeting_window)
        self.assertIs(self.screen.windows[-1], self.screen.sell_price_window)
        self.assertEqual(
            (
                self.screen.sell_price_window.x,
                self.screen.sell_price_window.y,
                self.screen.sell_price_window.width,
                self.screen.sell_price_window.height,
            ),
            SHOP_SELL_PRICE_WINDOW_GRID,
        )
        sale_text = self.screen.sell_price_window.texts[0]
        self.assertEqual((sale_text.x, sale_text.y), (
            SHOP_SELL_PRICE_TEXT_X,
            SHOP_SELL_PRICE_TEXT_Y,
        ))
        self.assertTrue(sale_text.text.startswith("うりね　"))
        self.assertTrue(sale_text.text.endswith("２５Ｇ"))

        self.screen.update(InputState(navigation=Direction.DOWN))

        self.assertEqual(self.screen.selected_item.key, "REMEDY")
        self.assertTrue(
            self.screen.sell_price_window.texts[0].text.endswith("２０Ｇ")
        )

    def test_sell_warns_for_item_not_sold_by_any_shop(self) -> None:
        self.screen.update(InputState(navigation=Direction.RIGHT))
        self.screen.update(InputState(confirm=InputButton(triggered=True)))
        self.assertIs(self.screen.mode, ShopMode.SELL)

        rare_index = next(
            index
            for index, item in enumerate(self.screen.available_items)
            if self.system.is_rare_sale(item)
        )
        self.screen.selected_item_index = rare_index
        self.screen.scroll_offset = rare_index
        self.screen._refresh_trade_windows()
        rare_item = self.screen.selected_item
        before_count = self.inventory.quantity(rare_item)

        self.screen.update(InputState(confirm=InputButton(triggered=True)))
        self.screen.update(InputState(confirm=InputButton(triggered=True)))

        self.assertIs(self.screen.phase, ShopPhase.RARE_CONFIRMATION)
        self.assertIn(
            "「ウチでは　うれない　しなものだけど",
            [text.text for text in self.screen.rare_window.texts],
        )
        self.screen.update(InputState(confirm=InputButton(triggered=True)))
        self.assertIs(self.screen.phase, ShopPhase.ITEM)
        self.assertEqual(self.inventory.quantity(rare_item), before_count - 1)
        self.assertNotIn(rare_item, self.screen.shop.items)

    def test_horizontal_input_does_nothing_in_item_list(self) -> None:
        self.screen.update(InputState(confirm=InputButton(triggered=True)))
        dagger_index = next(
            index
            for index, item in enumerate(self.screen.available_items)
            if item.key == "DAGGER"
        )
        self.screen.selected_item_index = dagger_index
        self.screen.scroll_offset = 0
        self.screen._refresh_trade_windows()

        selected_index = self.screen.selected_item_index
        info_window = self.screen.info_window
        lines = [text.text for text in info_window.texts]

        self.screen.update(InputState(navigation=Direction.RIGHT))
        self.screen.update(InputState(navigation=Direction.LEFT))

        self.assertEqual(self.screen.selected_item_index, selected_index)
        self.assertIs(self.screen.info_window, info_window)
        self.assertEqual(
            [text.text for text in self.screen.info_window.texts],
            lines,
        )

    def test_leave_command_closes_shop(self) -> None:
        self.screen.update(InputState(navigation=Direction.RIGHT))
        self.screen.update(InputState(navigation=Direction.RIGHT))

        self.assertIs(self.screen.command_cursor.selected_key, ShopCommand.LEAVE)
        self.assertTrue(
            self.screen.update(InputState(confirm=InputButton(triggered=True)))
        )

    def test_cancel_returns_one_phase_at_a_time(self) -> None:
        self.screen.update(InputState(confirm=InputButton(triggered=True)))
        self.screen.update(InputState(confirm=InputButton(triggered=True)))
        self.assertIs(self.screen.phase, ShopPhase.QUANTITY)

        self.assertFalse(
            self.screen.update(InputState(cancel=InputButton(triggered=True)))
        )
        self.assertIs(self.screen.phase, ShopPhase.ITEM)
        self.assertFalse(
            self.screen.update(InputState(cancel=InputButton(triggered=True)))
        )
        self.assertIs(self.screen.phase, ShopPhase.COMMAND)
        self.assertTrue(
            self.screen.update(InputState(cancel=InputButton(triggered=True)))
        )

if __name__ == "__main__":
    unittest.main()
