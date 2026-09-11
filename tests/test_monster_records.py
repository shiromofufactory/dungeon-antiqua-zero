from __future__ import annotations

import unittest

from tools._bootstrap import APP_ROOT  # noqa: F401 - adds app/ to sys.path

from resistance import ResistanceType
from state import SaveData
from systems import (
    MONSTER_COMBAT_FIELD_KEYS,
    MONSTER_PROFILE_FIELD_KEY,
    MONSTER_TREASURE_ACQUIRED_FIELD_KEY,
    MonsterRecordSystem,
)


class MonsterRecordSystemTest(unittest.TestCase):
    def setUp(self) -> None:
        self.save_data = SaveData()
        self.records = MonsterRecordSystem(self.save_data)

    def test_encounter_registers_each_monster_without_revealing_details(self) -> None:
        self.records.register_encounter(("Giant Spider", "Coyote", "Coyote"))

        self.assertEqual(
            self.save_data.monster_records,
            {"Giant Spider": set(), "Coyote": set()},
        )

    def test_confirmed_attribute_reveals_profile_and_only_that_affinity(self) -> None:
        self.records.reveal_affinity("Coyote", ResistanceType.FIRE)

        self.assertEqual(
            self.save_data.monster_records["Coyote"],
            {MONSTER_PROFILE_FIELD_KEY, ResistanceType.FIRE.value},
        )
        self.assertTrue(
            self.records.affinity_is_revealed("Coyote", ResistanceType.FIRE)
        )
        self.assertFalse(
            self.records.affinity_is_revealed("Coyote", ResistanceType.SLEEP)
        )

    def test_attempted_action_can_reveal_only_the_basic_profile(self) -> None:
        self.records.reveal_profile("Coyote")

        self.assertEqual(
            self.save_data.monster_records["Coyote"],
            {MONSTER_PROFILE_FIELD_KEY},
        )

    def test_identify_reveals_every_combat_field_but_not_treasure(self) -> None:
        self.records.reveal_all_combat_fields("Giant Spider")

        self.assertEqual(
            self.save_data.monster_records["Giant Spider"],
            set(MONSTER_COMBAT_FIELD_KEYS),
        )
        self.assertFalse(self.records.treasure_was_acquired("Giant Spider"))

    def test_treasure_flag_is_per_monster_and_persists_in_revealed_fields(self) -> None:
        self.records.record_treasure_acquired("Giant Spider")

        self.assertTrue(self.records.treasure_was_acquired("Giant Spider"))
        self.assertFalse(self.records.treasure_was_acquired("Coyote"))
        self.assertEqual(
            self.save_data.monster_records["Giant Spider"],
            {MONSTER_TREASURE_ACQUIRED_FIELD_KEY},
        )


if __name__ == "__main__":
    unittest.main()
