from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.member import BattleStats, HandHit
from app.resistance import ResistanceType
from app.resources import load_record_array
from app.ui import DEFAULT_TEXT_COLOR, DISABLED_COLOR
from tools.screen_mocks._fixtures import MOCK_PARTY_CHARACTER_KEYS
from tools.screen_mocks.status import (
    LOCALIZED_POSITIONS,
    RESISTANCE_POSITIONS,
    Direction,
    EquipmentSlot,
    Language,
    Localizer,
    TRANSPARENT_INDEX,
    Settings,
    StatusScreenMock,
    attack_display,
    hit_display,
    next_language,
    pad,
    resistance_icon_tag,
)


def input_state(
    *,
    navigation: Direction | None = None,
    confirm: bool = False,
    cancel: bool = False,
    previous_page: bool = False,
    next_page: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        navigation=navigation,
        confirm=SimpleNamespace(triggered=confirm),
        cancel=SimpleNamespace(triggered=cancel),
        previous_page=SimpleNamespace(triggered=previous_page),
        next_page=SimpleNamespace(triggered=next_page),
    )


class StatusScreenMockTest(unittest.TestCase):
    def test_character_face_coordinates_match_faces_pc_sheet(self) -> None:
        expected = {
            "フィオラ": (0, 0),
            "セリオン": (32, 0),
            "アルヴァン": (64, 0),
            "ラグナ": (0, 32),
            "エリカ": (32, 32),
            "クレス": (64, 32),
            "バルトロメ": (96, 32),
            "アルファード": (0, 64),
            "ダイン": (32, 64),
            "イリス": (0, 96),
            "ミリア": (32, 96),
            "オルウェン": (64, 96),
            "TKG-48": (96, 96),
            "カスミ": (0, 128),
            "グリム": (32, 128),
            "シルファ": (64, 128),
            "カゲトラ": (0, 160),
            "ライザ": (32, 160),
            "リゼル": (64, 160),
            "ヴァルド": (96, 160),
        }
        actual = {
            record["name_ja"]: (record["face_x"], record["face_y"])
            for record in load_record_array("characters.json")
        }

        self.assertEqual(actual, expected)

    def test_language_sequence_wraps_after_simplified_chinese(self) -> None:
        self.assertEqual(next_language(Language.JAPANESE), Language.ENGLISH)
        self.assertEqual(
            next_language(Language.ENGLISH),
            Language.SIMPLIFIED_CHINESE,
        )
        self.assertEqual(
            next_language(Language.SIMPLIFIED_CHINESE),
            Language.JAPANESE,
        )

    def test_first_three_lines_use_localized_member_identity(self) -> None:
        with (
            patch("tools.screen_mocks.status.ImageResources") as images,
            patch("tools.screen_mocks.status.FontResources") as fonts,
            patch("tools.screen_mocks.status.WindowFactory") as factory,
        ):
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = object()
            fonts.return_value.baseline_offset_for.return_value = 0

            mock = StatusScreenMock()

        self.assertEqual(
            tuple(member.definition.names["name_en"] for member in mock.party),
            MOCK_PARTY_CHARACTER_KEYS,
        )
        self.assertEqual(
            [
                (member.internal_level, member.hp, member.mp)
                for member in mock.party
            ],
            [
                (1, 44, 12),
                (3, 64, 16),
                (18, 220, 30),
                (8, 115, 15),
                (11, 171, 0),
            ],
        )
        self.assertEqual(
            [member.battle_stats.evasion for member in mock.party],
            [10, 4, 12, 0, 0],
        )
        self.assertEqual(mock.member_index, 0)
        self.assertNotIn("opened", factory.return_value.create.call_args.kwargs)
        self.assertTrue(
            factory.return_value.create.call_args.kwargs[
                "horizontal_navigation"
            ]
        )

        texts = tuple(factory.return_value.create.call_args.args[4])
        self.assertEqual(
            [item.text for item in texts[:3]],
            ["フィオラ", "ようせい", "おんな"],
        )
        placed = {(item.x, item.y): item.text for item in texts}
        placements = {(item.x, item.y): item for item in texts}
        self.assertEqual(placed[(6, 14)], "ＨＰ　　４４／　４４")
        self.assertEqual(placed[(6, 17)], "ＭＰ　　１２／　１２")
        self.assertEqual(placements[(6, 17)].color, DEFAULT_TEXT_COLOR)
        self.assertEqual(placed[(22, 20)], "ＯＫ")
        self.assertEqual(placed[(6, 26)], "ちから")
        self.assertEqual(placed[(20, 26)], "１７")
        self.assertEqual(placed[(20, 29)], "２５")
        self.assertEqual(placed[(20, 32)], "２４")
        self.assertEqual(placed[(8, 41)], "")
        self.assertEqual(placed[(8, 44)], "")
        self.assertEqual(placed[(30, 8)], "みぎて　：%KNIFE%ダガー")
        self.assertEqual(placed[(30, 11)], "ひだりて：")
        self.assertEqual(placed[(30, 14)], "からだ　：ローブ")
        self.assertEqual(placed[(30, 17)], "あたま　：")
        arm = mock.member.equipment.item_at(EquipmentSlot.ARM)
        self.assertEqual(
            placed[(30, 20)],
            "うで　　："
            + (
                arm.localized_name(Localizer(Language.JAPANESE))
                if arm is not None
                else ""
            ),
        )
        self.assertEqual(placed[(46, 26)], "　８")
        self.assertEqual(placed[(44, 29)], "１０５（＋　０）")
        self.assertEqual(placed[(46, 32)], "　３")
        self.assertEqual(placed[(46, 35)], "１０")
        self.assertEqual(
            placed[(46, 38)],
            pad(mock.member.battle_stats.spell_resistance, 2),
        )
        self.assertEqual(placed[(30, 38)], "じゅつぼうぎょ")
        for resistance, x, y in RESISTANCE_POSITIONS:
            self.assertEqual(
                placed[(x, y)],
                resistance_icon_tag(mock.member, resistance),
            )
        self.assertEqual(placed[(6, 49)], "%SWORD%：０－００")
        self.assertEqual(placed[(20, 49)], "%KATANA%：０－００")
        self.assertEqual(placed[(34, 49)], "%SPEAR%：０－００")
        self.assertEqual(placed[(48, 49)], "%KNIFE%：１－００")
        self.assertEqual(placed[(6, 52)], "%AXE%：０－００")
        self.assertEqual(placed[(20, 52)], "%HAMMER%：０－００")
        self.assertEqual(placed[(34, 52)], "%THROWING%：１－００")
        self.assertEqual(placed[(48, 52)], "%ROD%：０－００")
        self.assertEqual(placed[(6, 55)], "%WAND%：１－００")
        self.assertEqual(placed[(20, 55)], "%MYSTIC%：１－００")
        self.assertEqual(placed[(34, 55)], "%SACRED%：０－００")
        self.assertEqual(placed[(48, 55)], "%NETHER%：１－００")
        for position in (
            (6, 49),
            (20, 49),
            (34, 49),
            (6, 52),
            (20, 52),
            (48, 52),
            (34, 55),
        ):
            self.assertEqual(placements[position].color, DISABLED_COLOR)
        for position in (
            (48, 49),
            (34, 52),
            (6, 55),
            (20, 55),
            (48, 55),
        ):
            self.assertEqual(placements[position].color, DEFAULT_TEXT_COLOR)
        self.assertNotIn("%FAVORED%", (item.text for item in texts))

    def test_starts_from_supplied_member_without_opening_animation(self) -> None:
        with (
            patch("tools.screen_mocks.status.ImageResources") as images,
            patch("tools.screen_mocks.status.FontResources") as fonts,
            patch("tools.screen_mocks.status.WindowFactory") as factory,
        ):
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = object()
            fonts.return_value.baseline_offset_for.return_value = 0

            mock = StatusScreenMock(member_index=2)

        self.assertEqual(mock.member_index, 2)
        self.assertEqual(mock.member.definition.key, "Alvan")
        self.assertNotIn("opened", factory.return_value.create.call_args.kwargs)
        factory.return_value.create.return_value.open.assert_not_called()

    def test_member_without_mp_uses_shared_disabled_color(self) -> None:
        with (
            patch("tools.screen_mocks.status.ImageResources") as images,
            patch("tools.screen_mocks.status.FontResources") as fonts,
        ):
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = object()
            fonts.return_value.baseline_offset_for.return_value = 0
            mock = StatusScreenMock()

        mock.member_index = 4
        window = mock._build_window()
        mp_text = next(
            text for text in window.texts if (text.x, text.y) == (6, 17)
        )

        self.assertEqual(mock.member.definition.key, "Ragna")
        self.assertEqual(mock.member.max_mp, 0)
        self.assertEqual(mp_text.color, DISABLED_COLOR)

    def test_favored_marker_is_eight_pixels_left_of_icon(self) -> None:
        with (
            patch("tools.screen_mocks.status.ImageResources") as images,
            patch("tools.screen_mocks.status.FontResources") as fonts,
        ):
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = object()
            fonts.return_value.baseline_offset_for.return_value = 0
            mock = StatusScreenMock()

        mock.member_index = 1
        mock._rebuild_window()

        favored_positions = {
            (item.x, item.y)
            for item in mock.windows[0].texts
            if item.text == "%FAVORED%"
        }
        self.assertEqual(favored_positions, {(32, 49), (32, 55)})

    def test_formats_dual_wield_attack_and_average_hit(self) -> None:
        stats = BattleStats(
            attack_right=40,
            attack_left=32,
            hit_right=HandHit(
                total=109,
                weapon_level_bonus=16,
                cross_weapon_bonus=2,
            ),
            hit_left=HandHit(
                total=108,
                weapon_level_bonus=14,
                cross_weapon_bonus=2,
            ),
            defense=0,
            evasion=0,
            spell_resistance=0,
        )

        self.assertEqual(attack_display(stats), "４０　－　３２")
        self.assertEqual(hit_display(stats), "１０８（＋１７）")

        narrow_stats = BattleStats(
            attack_right=8,
            attack_left=None,
            hit_right=HandHit(
                total=8,
                weapon_level_bonus=0,
                cross_weapon_bonus=1,
            ),
            hit_left=None,
            defense=0,
            evasion=0,
            spell_resistance=0,
        )
        self.assertEqual(attack_display(narrow_stats), "　８")
        self.assertEqual(hit_display(narrow_stats), "　　８（＋　１）")

    def test_resistance_icon_uses_enabled_and_disabled_variants(self) -> None:
        member = Mock(
            resistances=frozenset(
                (ResistanceType.FIRE, ResistanceType.DEATH)
            )
        )

        self.assertEqual(
            resistance_icon_tag(member, ResistanceType.FIRE),
            "%FIRE%",
        )
        self.assertEqual(
            resistance_icon_tag(member, ResistanceType.FREEZE),
            "%FREEZE_DISABLED%",
        )

    def test_confirm_cycles_language_and_rebuilds_localized_window(self) -> None:
        mock = StatusScreenMock.__new__(StatusScreenMock)
        mock.settings = Settings()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = input_state(confirm=True)
        mock._rebuild_window = Mock()

        returned = mock.update(mock.input_reader.poll.return_value)

        self.assertEqual(mock.settings.language, Language.ENGLISH)
        mock._rebuild_window.assert_called_once_with()
        self.assertFalse(returned)

    def test_right_navigation_wraps_from_ragna_to_fiora(self) -> None:
        mock = StatusScreenMock.__new__(StatusScreenMock)
        mock.party = tuple(Mock() for _ in MOCK_PARTY_CHARACTER_KEYS)
        mock.member_index = 4
        mock.settings = Settings()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = input_state(
            navigation=Direction.RIGHT
        )
        mock._rebuild_window = Mock()

        returned = mock.update(mock.input_reader.poll.return_value)

        self.assertEqual(mock.member_index, 0)
        self.assertIs(mock.member, mock.party[0])
        mock._rebuild_window.assert_called_once_with()
        self.assertFalse(returned)

    def test_left_navigation_wraps_from_fiora_to_ragna(self) -> None:
        mock = StatusScreenMock.__new__(StatusScreenMock)
        mock.party = tuple(Mock() for _ in MOCK_PARTY_CHARACTER_KEYS)
        mock.member_index = 0
        mock.settings = Settings()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = input_state(
            navigation=Direction.LEFT
        )
        mock._rebuild_window = Mock()

        returned = mock.update(mock.input_reader.poll.return_value)

        self.assertEqual(mock.member_index, 4)
        self.assertIs(mock.member, mock.party[4])
        self.assertFalse(returned)

    def test_lr_page_buttons_switch_party_members(self) -> None:
        cases = (
            ("previous_page", 2, 1),
            ("next_page", 2, 3),
        )
        for button_name, start, expected in cases:
            with self.subTest(button_name=button_name):
                mock = StatusScreenMock.__new__(StatusScreenMock)
                mock.party = tuple(Mock() for _ in MOCK_PARTY_CHARACTER_KEYS)
                mock.member_index = start
                mock.settings = Settings()
                mock.input_reader = Mock()
                mock.input_reader.poll.return_value = input_state(
                    **{button_name: True},
                )
                mock._rebuild_window = Mock()

                returned = mock.update(mock.input_reader.poll.return_value)

                self.assertEqual(mock.member_index, expected)
                mock._rebuild_window.assert_called_once_with()
                self.assertFalse(returned)

    def test_english_localized_text_is_rebuilt_as_fullwidth(self) -> None:
        japanese_font = object()
        english_font = object()
        with (
            patch("tools.screen_mocks.status.ImageResources") as images,
            patch("tools.screen_mocks.status.FontResources") as fonts,
        ):
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.side_effect = (
                lambda language: english_font
                if language is Language.ENGLISH
                else japanese_font
            )
            fonts.return_value.baseline_offset_for.side_effect = (
                lambda language: 3
                if language is Language.ENGLISH
                else 0
            )
            mock = StatusScreenMock()

        mock.settings = mock.settings.with_language(Language.ENGLISH)
        mock._rebuild_window()

        texts = {
            (item.x, item.y): item.text for item in mock.windows[0].texts
        }
        self.assertEqual(texts[(14, 2)], "Ｆｉｏｒａ")
        self.assertEqual(texts[(14, 5)], "Ｆａｉｒｙ")
        self.assertEqual(texts[(14, 8)], "Ｆｅｍａｌｅ")
        self.assertEqual(texts[(8, 41)], "")
        self.assertEqual(texts[(8, 44)], "")
        self.assertEqual(texts[(6, 20)], "Ｓｔａｔｕｓ")
        self.assertEqual(texts[(22, 20)], "ＯＫ")
        self.assertEqual(texts[(6, 26)], "ＳＴＲ")
        self.assertEqual(texts[(6, 29)], "ＡＧＩ")
        self.assertEqual(texts[(6, 32)], "ＭＡＧ")
        self.assertEqual(texts[(6, 38)], "Ｓｋｉｌｌ：")
        self.assertEqual(
            texts[(30, 8)],
            "%RIGHT%：%KNIFE%ＤＡＧＧＥＲ",
        )
        self.assertEqual(texts[(30, 11)], "%LEFT%：")
        self.assertEqual(texts[(30, 14)], "%BODY%：ＲＯＢＥ")
        self.assertEqual(texts[(30, 17)], "%HEAD%：")
        arm = mock.member.equipment.item_at(EquipmentSlot.ARM)
        self.assertEqual(
            texts[(30, 20)],
            "%ARM%："
            + (
                arm.localized_name(Localizer(Language.ENGLISH))
                if arm is not None
                else ""
            ),
        )
        self.assertEqual(texts[(30, 26)], "Ａｔｔａｃｋ")
        self.assertEqual(texts[(30, 29)], "Ｈｉｔ")
        self.assertEqual(texts[(30, 32)], "Ｄｅｆｅｎｃｅ")
        self.assertEqual(texts[(30, 35)], "Ｅｖａｓｉｏｎ")
        self.assertEqual(texts[(30, 38)], "Ｓｐｅｌｌ　ｒｅｓ")
        self.assertEqual(texts[(30, 41)], "Ｔｏｌｅｒａｎｃｅ")
        self.assertEqual(
            {
                item.baseline_offset
                for item in mock.windows[0].texts
                if (item.x, item.y) in LOCALIZED_POSITIONS
            },
            {0, 3},
        )
        placements = {
            (item.x, item.y): item for item in mock.windows[0].texts
        }
        for position in ((6, 26), (6, 29), (6, 32)):
            self.assertIs(placements[position].font, japanese_font)
            self.assertEqual(placements[position].baseline_offset, 0)
        self.assertIs(placements[(6, 20)].font, english_font)
        self.assertEqual(placements[(6, 20)].baseline_offset, 3)

    def test_chinese_fixed_labels_are_rebuilt_from_text_catalog(self) -> None:
        with (
            patch("tools.screen_mocks.status.ImageResources") as images,
            patch("tools.screen_mocks.status.FontResources") as fonts,
        ):
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = object()
            fonts.return_value.baseline_offset_for.return_value = 0
            mock = StatusScreenMock()

        mock.settings = mock.settings.with_language(
            Language.SIMPLIFIED_CHINESE
        )
        mock._rebuild_window()

        texts = {
            (item.x, item.y): item.text for item in mock.windows[0].texts
        }
        self.assertEqual(texts[(6, 20)], "状态")
        self.assertEqual(texts[(22, 20)], "ＯＫ")
        self.assertEqual(texts[(6, 26)], "力量")
        self.assertEqual(texts[(6, 29)], "敏捷")
        self.assertEqual(texts[(6, 32)], "魔力")
        self.assertEqual(texts[(6, 38)], "技能：")
        self.assertEqual(texts[(8, 41)], "")
        self.assertEqual(texts[(8, 44)], "")
        self.assertEqual(texts[(30, 8)], "右手：%KNIFE%DAGGER")
        self.assertEqual(texts[(30, 11)], "左手：")
        self.assertEqual(texts[(30, 14)], "身体：ROBE")
        self.assertEqual(texts[(30, 17)], "头部：")
        arm = mock.member.equipment.item_at(EquipmentSlot.ARM)
        self.assertEqual(
            texts[(30, 20)],
            "手臂："
            + (
                arm.localized_name(Localizer(Language.SIMPLIFIED_CHINESE))
                if arm is not None
                else ""
            ),
        )
        self.assertEqual(texts[(30, 26)], "攻击")
        self.assertEqual(texts[(30, 29)], "命中")
        self.assertEqual(texts[(30, 32)], "防御")
        self.assertEqual(texts[(30, 35)], "闪避")
        self.assertEqual(texts[(30, 38)], "抗性")
        self.assertEqual(texts[(30, 41)], "耐性")

    def test_cancel_returns_to_menu_without_changing_language(self) -> None:
        mock = StatusScreenMock.__new__(StatusScreenMock)
        mock.settings = Settings()
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = input_state(cancel=True)
        mock._rebuild_window = Mock()

        returned = mock.update(mock.input_reader.poll.return_value)

        self.assertTrue(returned)
        self.assertEqual(mock.settings.language, Language.JAPANESE)
        mock._rebuild_window.assert_not_called()

    def test_draws_all_windows_before_face(self) -> None:
        mock = StatusScreenMock.__new__(StatusScreenMock)
        mock.faces = object()
        mock.party = (Mock(face_position=Mock(x=64, y=96)),)
        mock.member_index = 0
        first_window = Mock(is_open=True)
        second_window = Mock()
        mock.windows = (first_window, second_window)
        draw_order: list[str] = []

        first_window.draw.side_effect = lambda: draw_order.append("first_window")
        second_window.draw.side_effect = lambda: draw_order.append("second_window")

        with patch(
            "tools.screen_mocks.status.pyxel.blt",
            side_effect=lambda *args: draw_order.append("face"),
        ) as blt:
            mock.draw()

        self.assertEqual(draw_order, ["first_window", "second_window", "face"])
        blt.assert_called_once_with(
            16,
            10,
            mock.faces,
            64,
            96,
            32,
            32,
            TRANSPARENT_INDEX,
        )

if __name__ == "__main__":
    unittest.main()
