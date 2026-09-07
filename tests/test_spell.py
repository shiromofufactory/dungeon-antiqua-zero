from __future__ import annotations

import unittest

from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
    load_mock_spells,
)
from localization import Localizer
from resources import load_record_array
from spell import Spell, SpellDataError, SpellType
from state import Language


class SpellTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spells = load_mock_spells()
        self.party = load_mock_party(load_mock_items(), load_mock_skills())

    def test_parses_enum_type_and_localized_display_data(self) -> None:
        spell = self.spells["FIRE1"]

        self.assertEqual(spell.type, SpellType.MYSTIC)
        self.assertEqual(spell.level, 1)
        self.assertEqual(spell.mp, 2)
        self.assertFalse(spell.on_camp)
        self.assertTrue(spell.to_enemy)
        self.assertFalse(spell.to_all)
        self.assertEqual(
            spell.localized_name(Localizer(Language.JAPANESE)),
            "ファイア１",
        )
        self.assertEqual(
            spell.localized_display_name(Localizer(Language.JAPANESE)),
            "%MYSTIC%ファイア１",
        )
        self.assertEqual(
            spell.localized_description(Localizer(Language.JAPANESE)),
            (
                "てき１たいに%FIRE%ほのおぞくせいの",
                "ダメージ（ばいりつ：１５）",
            ),
        )

    def test_learning_uses_each_members_spell_proficiency_level(self) -> None:
        fiora, cerion, alvan, _elika, ragna, _dain = self.party

        self.assertTrue(self.spells["FIRE1"].is_learned_by(fiora))
        self.assertTrue(self.spells["POISON1"].is_learned_by(fiora))
        self.assertFalse(self.spells["HEALING1"].is_learned_by(fiora))
        self.assertTrue(self.spells["HEALING1"].is_learned_by(cerion))
        self.assertTrue(self.spells["SLOW"].is_learned_by(alvan))
        self.assertFalse(self.spells["FIRE1"].is_learned_by(ragna))

    def test_level_zero_requires_explicit_event_acquisition(self) -> None:
        fiora = self.party[0]
        teleport = self.spells["TELEPORT"]

        self.assertFalse(teleport.is_learned_by(fiora))
        self.assertTrue(teleport.is_learned_by(fiora, {"TELEPORT"}))

    def test_item_effect_records_are_not_member_spells(self) -> None:
        self.assertFalse(self.spells["POTION"].is_learned_by(self.party[0]))
        self.assertEqual(
            self.spells["POTION"].localized_display_name(
                Localizer(Language.JAPANESE)
            ),
            "－",
        )

    def test_standard_display_name_uses_each_spell_school_icon(self) -> None:
        localizer = Localizer(Language.JAPANESE)
        expected = {
            "FIRE1": "%MYSTIC%ファイア１",
            "HEALING1": "%SACRED%ヒーリング１",
            "SLEEP": "%NETHER%スリープ",
        }

        for key, display_name in expected.items():
            with self.subTest(spell=key):
                self.assertEqual(
                    self.spells[key].localized_display_name(localizer),
                    display_name,
                )

    def test_rejects_legacy_numeric_spell_type(self) -> None:
        record = dict(load_record_array("spells.json")[0])
        record["type"] = 1

        with self.assertRaisesRegex(SpellDataError, "type must be a string"):
            Spell.from_record(record)


if __name__ == "__main__":
    unittest.main()
