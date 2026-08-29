from __future__ import annotations

import unittest

from app.localization import Localizer
from app.member import Gender, Member, MemberDataError, Race
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
            ]
        )

    def test_normalizes_stable_race_and_gender_values(self) -> None:
        self.assertEqual(self.member.definition.race, Race.FAIRY)
        self.assertEqual(self.member.definition.gender, Gender.FEMALE)

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
                }
            )


if __name__ == "__main__":
    unittest.main()
