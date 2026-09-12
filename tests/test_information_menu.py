from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT

from game_data import load_items, load_monsters
from input import Direction, InputButton, InputState
from resistance import ResistanceType
from state import Language, Settings
from systems import (
    MONSTER_COMBAT_FIELD_KEYS,
    MONSTER_TREASURE_ACQUIRED_FIELD_KEY,
)
from text_catalog import TextCatalog
from ui.information_menu import (
    INFORMATION_HEADER_WINDOW_GRID,
    INFORMATION_MAIN_WINDOW_GRID,
    MONSTER_DETAIL_WINDOW_GRID,
    MONSTER_LIST_VISIBLE_COUNT,
    MONSTER_LIST_WINDOW_GRID,
    MONSTER_STUN_MARKER,
    MONSTER_STUN_MARKER_X,
    InformationMenuOverlay,
    InformationPhase,
    monster_affinity_icon_row,
)


def input_state(
    *,
    navigation: Direction | None = None,
    confirm: bool = False,
    cancel: bool = False,
    previous_page: bool = False,
    next_page: bool = False,
) -> InputState:
    return InputState(
        navigation=navigation,
        confirm=InputButton(triggered=confirm, held=confirm),
        cancel=InputButton(triggered=cancel, held=cancel),
        previous_page=InputButton(
            triggered=previous_page,
            held=previous_page,
        ),
        next_page=InputButton(triggered=next_page, held=next_page),
    )


class InformationMenuOverlayTest(unittest.TestCase):
    def create_overlay(
        self,
        records: dict[str, set[str]] | None = None,
        *,
        invalid_action: Mock | None = None,
    ) -> InformationMenuOverlay:
        fonts = Mock()
        font = Mock()
        font.text_width.side_effect = lambda text: len(text) * 8
        fonts.font_for.return_value = font
        fonts.baseline_offset_for.return_value = 0
        images = Mock()
        images.image.return_value = object()
        return InformationMenuOverlay(
            monsters=load_monsters(),
            monster_records={} if records is None else records,
            items=load_items(),
            settings=Settings(language=Language.JAPANESE),
            texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
            fonts=fonts,
            images=images,
            on_invalid_action=invalid_action,
        )

    def test_starts_at_information_submenu_with_only_monster_book(self) -> None:
        overlay = self.create_overlay()

        self.assertIs(overlay.phase, InformationPhase.MENU)
        self.assertEqual(overlay.header_cursor.selected_key, "monster_book")
        self.assertEqual(
            (
                overlay.header_window.x,
                overlay.header_window.y,
                overlay.header_window.width,
                overlay.header_window.height,
            ),
            INFORMATION_HEADER_WINDOW_GRID,
        )
        self.assertEqual(
            (
                overlay.main_window.x,
                overlay.main_window.y,
                overlay.main_window.width,
                overlay.main_window.height,
            ),
            INFORMATION_MAIN_WINDOW_GRID,
        )
        self.assertEqual(
            [text.text for text in overlay.header_window.texts],
            ["モンスターずかん"],
        )

    def test_empty_book_alerts_and_stays_in_information_submenu(self) -> None:
        invalid_action = Mock()
        overlay = self.create_overlay(invalid_action=invalid_action)

        self.assertFalse(overlay.update(input_state(confirm=True)))

        invalid_action.assert_called_once_with()
        self.assertIs(overlay.phase, InformationPhase.MENU)
        self.assertIsNone(overlay.monster_list_window)

    def test_registered_monsters_are_listed_in_master_order(self) -> None:
        monsters = load_monsters()
        overlay = self.create_overlay(
            {
                monsters[4].key: set(),
                monsters[0].key: set(),
                "removed_monster": set(),
            }
        )

        self.assertEqual(
            [(number, monster.key) for number, monster in overlay.registered_monsters],
            [(1, monsters[0].key), (5, monsters[4].key)],
        )
        overlay.update(input_state(confirm=True))

        self.assertIs(overlay.phase, InformationPhase.MONSTER_BOOK)
        self.assertFalse(overlay.header_cursor.active)
        self.assertEqual(
            (
                overlay.monster_list_window.x,
                overlay.monster_list_window.y,
                overlay.monster_list_window.width,
                overlay.monster_list_window.height,
            ),
            MONSTER_LIST_WINDOW_GRID,
        )
        self.assertEqual(
            (
                overlay.monster_detail_window.x,
                overlay.monster_detail_window.y,
                overlay.monster_detail_window.width,
                overlay.monster_detail_window.height,
            ),
            MONSTER_DETAIL_WINDOW_GRID,
        )
        self.assertEqual(
            [text.text for text in overlay.monster_list_window.texts],
            [
                monsters[0].localized_name(overlay.localizer),
                monsters[4].localized_name(overlay.localizer),
            ],
        )

    def test_incomplete_record_hides_stats_and_identification_details(self) -> None:
        monster = load_monsters()[0]
        overlay = self.create_overlay({monster.key: {"profile", "FIRE"}})
        overlay.update(input_state(confirm=True))

        detail = [text.text for text in overlay.monster_detail_window.texts]

        self.assertEqual(detail[0], "Ｎｏ：　１")
        self.assertEqual(detail[1], monster.localized_name(overlay.localizer))
        self.assertIn("？？？？", detail[3])
        self.assertIn("？？？？", detail[4])
        self.assertIn("しきべつ　されていません", detail)
        self.assertFalse(any("ＬＶ" in text for text in detail))
        self.assertFalse(any("おたから" in text for text in detail))

    def test_complete_record_shows_level_stats_affinities_and_unknown_treasure(
        self,
    ) -> None:
        monster = load_monsters()[0]
        overlay = self.create_overlay(
            {monster.key: set(MONSTER_COMBAT_FIELD_KEYS)}
        )
        overlay.update(input_state(confirm=True))

        detail = [text.text for text in overlay.monster_detail_window.texts]

        self.assertTrue(
            any(text.startswith("ＨＰ") and text.endswith("２５") for text in detail)
        )
        self.assertTrue(
            any(text.startswith("ＭＰ") and text.endswith("０") for text in detail)
        )
        self.assertTrue(
            any(text.startswith("ＬＶ") and text.endswith("１") for text in detail)
        )
        self.assertIn("おたから：？？？？", detail)
        self.assertIn(monster_affinity_icon_row(monster.resistances), detail)
        self.assertIn(monster_affinity_icon_row(monster.weaknesses), detail)
        stun_markers = [
            text
            for text in overlay.monster_detail_window.texts
            if text.text == MONSTER_STUN_MARKER
        ]
        self.assertEqual(len(stun_markers), 2)
        self.assertTrue(
            all(text.x == MONSTER_STUN_MARKER_X for text in stun_markers)
        )

    def test_treasure_name_requires_the_per_monster_acquired_flag(self) -> None:
        monster = load_monsters()[0]
        fields = set(MONSTER_COMBAT_FIELD_KEYS)
        fields.add(MONSTER_TREASURE_ACQUIRED_FIELD_KEY)
        overlay = self.create_overlay({monster.key: fields})
        overlay.update(input_state(confirm=True))

        detail = [text.text for text in overlay.monster_detail_window.texts]

        self.assertIn("おたから：ちりょうやく", detail)

    def test_boss_hp_remains_hidden_after_complete_identification(self) -> None:
        number, monster = next(
            (number, monster)
            for number, monster in enumerate(load_monsters(), start=1)
            if monster.is_boss
        )
        overlay = self.create_overlay(
            {monster.key: set(MONSTER_COMBAT_FIELD_KEYS)}
        )
        overlay.update(input_state(confirm=True))

        detail = [text.text for text in overlay.monster_detail_window.texts]

        self.assertTrue(detail[0].startswith("Ｎｏ："))
        fullwidth_number = str(number).translate(
            str.maketrans("0123456789", "０１２３４５６７８９")
        )
        self.assertTrue(detail[0].endswith(fullwidth_number))
        self.assertIn("ＨＰ　　　？？？？", detail)
        self.assertTrue(
            any("ＭＰ" in text and "？？？？" not in text for text in detail)
        )

    def test_up_down_and_page_inputs_move_through_all_registered_entries(self) -> None:
        monsters = load_monsters()
        overlay = self.create_overlay({monster.key: set() for monster in monsters})
        overlay.update(input_state(confirm=True))

        overlay.update(input_state(navigation=Direction.UP))
        self.assertEqual(overlay.selected_monster_index, len(monsters) - 1)
        overlay.update(input_state(navigation=Direction.DOWN))
        self.assertEqual(overlay.selected_monster_index, 0)
        overlay.update(input_state(next_page=True))
        self.assertEqual(
            overlay.selected_monster_index,
            MONSTER_LIST_VISIBLE_COUNT,
        )
        overlay.update(input_state(previous_page=True))
        self.assertEqual(overlay.selected_monster_index, 0)

    def test_cancel_returns_to_submenu_before_closing_information(self) -> None:
        monster = load_monsters()[0]
        overlay = self.create_overlay({monster.key: set()})
        overlay.update(input_state(confirm=True))

        self.assertFalse(overlay.update(input_state(cancel=True)))
        self.assertIs(overlay.phase, InformationPhase.MENU)
        self.assertTrue(overlay.header_cursor.active)
        self.assertTrue(overlay.update(input_state(cancel=True)))

    @patch("ui.information_menu.Window.draw")
    @patch("ui.information_menu.pyxel.blt")
    def test_draw_places_selected_monster_in_detail_window(
        self,
        blt: Mock,
        _draw_window: Mock,
    ) -> None:
        monster = load_monsters()[0]
        overlay = self.create_overlay({monster.key: set()})
        overlay.update(input_state(confirm=True))

        overlay.draw()

        image = overlay.images.image.return_value
        blt.assert_called_once_with(
            overlay.monster_detail_window.content_x + 58 - monster.width // 2,
            overlay.monster_detail_window.content_y + 180 - monster.height // 2,
            image,
            0,
            0,
            monster.width,
            monster.height,
            1,
        )
        overlay.images.image.assert_called_once_with(monster.image_resource_id)


class MonsterAffinityIconRowTest(unittest.TestCase):
    def test_uses_enabled_and_disabled_da2_icon_variants(self) -> None:
        row = monster_affinity_icon_row(
            frozenset((ResistanceType.FIRE, ResistanceType.POISON))
        )

        self.assertIn("%FIRE%", row)
        self.assertIn("%POISON%", row)
        self.assertIn("%FREEZE_DISABLED%", row)
        self.assertIn("%DEATH_DISABLED%", row)


if __name__ == "__main__":
    unittest.main()
