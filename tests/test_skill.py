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
            "Two-Handed",
        )

    def test_rejects_missing_lookup_key(self) -> None:
        with self.assertRaises(SkillDataError):
            Skill.from_record({"name_ja": "りょうてもち"})


if __name__ == "__main__":
    unittest.main()
