from __future__ import annotations

import unittest

from app.localization import Localizer, language_candidates
from app.state import Language


class LocalizationTest(unittest.TestCase):
    def test_language_candidates_are_deterministic(self) -> None:
        self.assertEqual(
            language_candidates(Language.SIMPLIFIED_CHINESE),
            (
                Language.SIMPLIFIED_CHINESE,
                Language.ENGLISH,
                Language.JAPANESE,
            ),
        )

    def test_selected_language_is_preferred(self) -> None:
        localizer = Localizer(Language.SIMPLIFIED_CHINESE)

        self.assertEqual(
            localizer.value(
                {"name_ja": "剣", "name_en": "Sword", "name_zhcn": "剑"},
                "name",
            ),
            "剑",
        )

    def test_empty_translation_uses_fallback_language(self) -> None:
        localizer = Localizer(Language.SIMPLIFIED_CHINESE)

        self.assertEqual(
            localizer.value(
                {"name_ja": "剣", "name_en": "Sword", "name_zhcn": ""},
                "name",
            ),
            "Sword",
        )

    def test_missing_translation_returns_explicit_default(self) -> None:
        localizer = Localizer(Language.ENGLISH)

        self.assertEqual(localizer.value({}, "name", default="?"), "?")


if __name__ == "__main__":
    unittest.main()
