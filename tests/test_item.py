from __future__ import annotations

import unittest

from app.item import Item, ItemDataError
from app.localization import Localizer
from app.state import Language


class ItemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.item = Item.from_record(
            {
                "name_en": "DAYBRINGER",
                "name_ja": "デイブリンガー",
                "type1": "RIGHT",
            }
        )

    def test_preserves_raw_english_name_as_lookup_key(self) -> None:
        self.assertEqual(self.item.key, "DAYBRINGER")

    def test_returns_localized_display_name(self) -> None:
        self.assertEqual(
            self.item.localized_name(Localizer(Language.JAPANESE)),
            "デイブリンガー",
        )
        self.assertEqual(
            self.item.localized_name(Localizer(Language.ENGLISH)),
            "ＤＡＹＢＲＩＮＧＥＲ",
        )
        self.assertEqual(
            self.item.localized_name(Localizer(Language.SIMPLIFIED_CHINESE)),
            "DAYBRINGER",
        )

    def test_rejects_missing_lookup_key(self) -> None:
        with self.assertRaises(ItemDataError):
            Item.from_record({"name_ja": "デイブリンガー"})


if __name__ == "__main__":
    unittest.main()
