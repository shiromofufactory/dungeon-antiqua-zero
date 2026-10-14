from __future__ import annotations

import unittest

from app.localization import Localizer
from app.skill import Skill, SkillDataError
from app.state import Language


class SkillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.skill = Skill.from_record(
            {
                "name_en": "Two-Handed",
                "name_ja": "りょうてもち",
                "command": "",
                "description_ja": [
                    "%COL_BLUE%こうげき%COL_END%を つよくする",
                    "りょうてが あいているときに ゆうこう",
                ],
                "description_en": ["Raise attack"],
            }
        )

    def test_preserves_raw_english_name_as_lookup_key(self) -> None:
        self.assertEqual(self.skill.key, "Two-Handed")

    def test_returns_localized_display_name(self) -> None:
        self.assertEqual(
            self.skill.localized_name(Localizer(Language.JAPANESE)),
            "りょうてもち",
        )
        self.assertEqual(
            self.skill.localized_name(Localizer(Language.ENGLISH)),
            "Ｔｗｏ－Ｈａｎｄｅｄ",
        )
        self.assertEqual(
            self.skill.localized_name(Localizer(Language.SIMPLIFIED_CHINESE)),
            "Ｔｗｏ－Ｈａｎｄｅｄ",
        )

    def test_rejects_missing_lookup_key(self) -> None:
        with self.assertRaises(SkillDataError):
            Skill.from_record({"name_ja": "りょうてもち"})

    def test_returns_localized_description_with_per_line_fallback(self) -> None:
        self.assertEqual(
            self.skill.localized_description(Localizer(Language.JAPANESE)),
            (
                "%COL_BLUE%こうげき%COL_END%を　つよくする",
                "りょうてが　あいているときに　ゆうこう",
            ),
        )
        self.assertEqual(
            self.skill.localized_description(Localizer(Language.ENGLISH)),
            (
                "Ｒａｉｓｅ　ａｔｔａｃｋ",
                "りょうてが　あいているときに　ゆうこう",
            ),
        )

    def test_rejects_non_string_description_lines(self) -> None:
        with self.assertRaisesRegex(
            SkillDataError,
            "description_ja must be an array of strings",
        ):
            Skill.from_record(
                {
                    "name_en": "Broken",
                    "description_ja": ["ok", 1],
                }
            )


if __name__ == "__main__":
    unittest.main()
