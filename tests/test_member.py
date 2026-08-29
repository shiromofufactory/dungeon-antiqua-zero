from __future__ import annotations

import unittest

from app.localization import Localizer
from app.member import (
    AdjustedAbilities,
    BaseAbilities,
    Gender,
    Member,
    MemberDataError,
    Race,
)
from app.state import Language
from app.text_catalog import TextCatalog


class MemberTest(unittest.TestCase):
    def setUp(self) -> None:
        self.member = Member.from_record(
            {
                "name_ja": "フィオラ",
                "name_en": "Fiora",
                "race": "FAIRY",
                "gender": "FEMALE",
                "base_str": 17,
                "base_agi": 25,
                "base_mag": 24,
            }
        )
        self.texts = TextCatalog.from_records(
            [
                {
                    "text_key": "race.FAIRY",
                    "text_ja": "ようせい",
                    "text_en": "Fairy",
                    "text_zhcn": "妖精",
                },
                {
                    "text_key": "gender.FEMALE",
                    "text_ja": "おんな",
                    "text_en": "Female",
                    "text_zhcn": "女性",
                },
                {
                    "text_key": "status.ok",
                    "text_ja": "ＯＫ",
                    "text_en": "OK",
                    "text_zhcn": "ＯＫ",
                },
                {
                    "text_key": "status.dead",
                    "text_ja": "しぼう",
                    "text_en": "Dead",
                    "text_zhcn": "死亡",
                },
                {
                    "text_key": "status.paralyzed",
                    "text_ja": "まひ",
                    "text_en": "Paralyze",
                    "text_zhcn": "麻痹",
                },
                {
                    "text_key": "status.sleeping",
                    "text_ja": "ねむり",
                    "text_en": "Asleep",
                    "text_zhcn": "睡眠",
                },
                {
                    "text_key": "status.confused",
                    "text_ja": "らん",
                    "text_en": "Confused",
                    "text_zhcn": "混乱",
                },
                {
                    "text_key": "status.poisoned",
                    "text_ja": "どく",
                    "text_en": "Poisoned",
                    "text_zhcn": "中毒",
                },
            ]
        )

    def test_normalizes_stable_race_and_gender_values(self) -> None:
        self.assertEqual(self.member.definition.race, Race.FAIRY)
        self.assertEqual(self.member.definition.gender, Gender.FEMALE)

    def test_keeps_base_and_adjusted_ability_layers_separate(self) -> None:
        self.assertEqual(
            self.member.definition.base_abilities,
            BaseAbilities(strength=17, agility=25, magic=24),
        )
        self.assertEqual(
            self.member.adjusted_abilities,
            AdjustedAbilities(strength=17, agility=25, magic=24),
        )

    def test_initial_health_and_magic_points_are_fixed_member_state(self) -> None:
        self.assertEqual(self.member.hp, 999)
        self.assertEqual(self.member.max_hp, 999)
        self.assertEqual(self.member.mp, 255)
        self.assertEqual(self.member.max_mp, 255)

    def test_healthy_status_can_show_max_hp_ok_or_nothing(self) -> None:
        localizer = Localizer(Language.JAPANESE)

        self.assertEqual(self.member.status(localizer, self.texts), "９９９")
        self.assertEqual(
            self.member.status(localizer, self.texts, show_ok=True),
            "ＯＫ",
        )
        self.assertEqual(
            self.member.status(localizer, self.texts, show_mhp=False),
            "",
        )

    def test_status_uses_da2_condition_priority(self) -> None:
        localizer = Localizer(Language.ENGLISH)
        self.member.poisoned = True
        self.member.confused = 2
        self.member.sleeping = 3
        self.member.paralyzed = True

        self.assertEqual(
            self.member.status(localizer, self.texts, show_ok=True),
            "Ｐａｒａｌｙｚｅ",
        )

        self.member.hp = 0
        self.assertEqual(
            self.member.status(localizer, self.texts, show_ok=True),
            "Ｄｅａｄ",
        )

    def test_each_condition_has_da2_localized_text(self) -> None:
        localizer = Localizer(Language.JAPANESE)
        cases = (
            ({"paralyzed": True}, "まひ"),
            ({"sleeping": 2}, "ねむり"),
            ({"confused": 2}, "らん"),
            ({"poisoned": True}, "どく"),
        )

        for values, expected in cases:
            with self.subTest(values=values):
                member = Member(self.member.definition, **values)
                self.assertEqual(member.status(localizer, self.texts), expected)

    def test_condition_state_types_are_validated(self) -> None:
        with self.assertRaisesRegex(TypeError, "paralyzed"):
            Member(self.member.definition, paralyzed=1)
        with self.assertRaisesRegex(TypeError, "sleeping"):
            Member(self.member.definition, sleeping=True)
        with self.assertRaisesRegex(ValueError, "confused"):
            Member(self.member.definition, confused=-1)

    def test_rejects_missing_base_ability(self) -> None:
        with self.assertRaisesRegex(MemberDataError, "base_mag"):
            Member.from_record(
                {
                    "name_en": "Fiora",
                    "race": "FAIRY",
                    "gender": "FEMALE",
                    "base_str": 17,
                    "base_agi": 25,
                }
            )

    def test_returns_japanese_display_identity(self) -> None:
        identity = self.member.display_identity(
            Localizer(Language.JAPANESE),
            self.texts,
        )

        self.assertEqual(identity.name, "フィオラ")
        self.assertEqual(identity.race, "ようせい")
        self.assertEqual(identity.gender, "おんな")

    def test_chinese_name_uses_existing_english_fallback(self) -> None:
        identity = self.member.display_identity(
            Localizer(Language.SIMPLIFIED_CHINESE),
            self.texts,
        )

        self.assertEqual(identity.name, "Fiora")
        self.assertEqual(identity.race, "妖精")
        self.assertEqual(identity.gender, "女性")

    def test_english_display_identity_is_fullwidth(self) -> None:
        identity = self.member.display_identity(
            Localizer(Language.ENGLISH),
            self.texts,
        )

        self.assertEqual(identity.name, "Ｆｉｏｒａ")
        self.assertEqual(identity.race, "Ｆａｉｒｙ")
        self.assertEqual(identity.gender, "Ｆｅｍａｌｅ")

    def test_rejects_unknown_race(self) -> None:
        with self.assertRaises(MemberDataError):
            Member.from_record(
                {
                    "name_en": "Fiora",
                    "race": "UNKNOWN",
                    "gender": "FEMALE",
                    "base_str": 17,
                    "base_agi": 25,
                    "base_mag": 24,
                }
            )


if __name__ == "__main__":
    unittest.main()
