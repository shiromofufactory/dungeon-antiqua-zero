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
from resistance import ResistanceType
from spell import Spell, SpellAction, SpellDataError, SpellType
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
        self.assertIs(spell.action, SpellAction.DAMAGE)
        self.assertIs(spell.attribute, ResistanceType.FIRE)
        self.assertEqual(spell.rate, 0)
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

    def test_identify_item_effect_targets_one_enemy_only_in_battle(self) -> None:
        identify = self.spells["IDENTIFY"]

        self.assertIs(identify.type, SpellType.ITEM)
        self.assertIs(identify.action, SpellAction.IDENTIFY)
        self.assertFalse(identify.on_camp)
        self.assertTrue(identify.on_battle)
        self.assertTrue(identify.to_enemy)
        self.assertFalse(identify.to_all)
        self.assertFalse(identify.is_learned_by(self.party[0]))

    def test_loads_every_current_heal_effect_by_its_stable_action(self) -> None:
        self.assertEqual(
            {
                spell.key
                for spell in self.spells.values()
                if spell.action is SpellAction.HEAL
            },
            {"HEALING1", "HEALING2", "POTION", "PANACEA"},
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

    def test_sleep_loads_its_authored_success_rate(self) -> None:
        self.assertEqual(self.spells["SLEEP"].rate, 6)

    def test_rejects_legacy_numeric_spell_type(self) -> None:
        record = dict(load_record_array("spells.json")[0])
        record["type"] = 1

        with self.assertRaisesRegex(SpellDataError, "type must be a string"):
            Spell.from_record(record)

    def test_empty_attribute_is_normalized_to_none(self) -> None:
        self.assertIsNone(self.spells["SPARK"].attribute)

    def test_rejects_unknown_attribute_code(self) -> None:
        record = dict(load_record_array("spells.json")[0])
        record["attr"] = "雷"

        with self.assertRaisesRegex(SpellDataError, "unsupported spell.attr"):
            Spell.from_record(record)

    def test_rejects_negative_status_rate(self) -> None:
        record = dict(load_record_array("spells.json")[0])
        record["rate"] = -1

        with self.assertRaisesRegex(SpellDataError, "rate must be at least 0"):
            Spell.from_record(record)


if __name__ == "__main__":
    unittest.main()
