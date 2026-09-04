from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from tools._bootstrap import APP_ROOT
from field import FieldPosition
from input import Direction
from state import Difficulty, SaveData
from systems import (
    SAVE_FORMAT_VERSION,
    SAVE_SLOT_COUNT,
    InventorySystem,
    SaveRepository,
    SaveSystemError,
    create_save_document,
)
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)


class SaveSystemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.items = load_mock_items()
        cls.skills = load_mock_skills()
        cls.all_members = load_mock_party(cls.items, cls.skills)

    def save_document(self) -> dict[str, object]:
        inventory = InventorySystem(self.items)
        party = self.all_members[:2]
        character_states = {
            member.definition.key: member for member in self.all_members[:3]
        }
        return create_save_document(
            save_data=SaveData(
                gold=123,
                experience=456,
                battle_count=7,
                difficulty=Difficulty.HARD,
                play_time_frames=890,
                event_flags={"prologue_complete", "fairy_saved"},
                visited_site_ids={"sample_town"},
                opened_treasures={
                    ("nectar_forest", "entrance_potion"),
                },
                monster_records={
                    "Giant Spider": {"FIRE", "profile"},
                },
                logs=[
                    {
                        "text_key": "shop.greeting",
                        "arguments": {"COUNT": 2},
                    },
                ],
            ),
            active_party=party,
            character_states=character_states,
            inventory=inventory,
            map_id="worldmap",
            position=FieldPosition(17, 39),
            facing=Direction.LEFT,
            saved_at=datetime(
                2026,
                9,
                4,
                12,
                34,
                56,
                tzinfo=timezone(timedelta(hours=9)),
            ),
        )

    def test_creates_complete_version_one_document(self) -> None:
        document = self.save_document()

        self.assertEqual(document["format_version"], SAVE_FORMAT_VERSION)
        self.assertEqual(document["saved_at"], "2026-09-04T12:34:56+09:00")
        self.assertEqual(
            document["progress"],
            {
                "gold": 123,
                "experience": 456,
                "battle_count": 7,
                "difficulty": "hard",
                "play_time_frames": 890,
            },
        )
        self.assertEqual(
            document["location"],
            {"map_id": "worldmap", "x": 17, "y": 39, "facing": "left"},
        )
        party = document["party"]
        self.assertEqual(
            party["active_character_keys"],
            ["Fiora", "Cerion"],
        )
        self.assertEqual(set(party["character_states"]), {"Fiora", "Cerion", "Alvan"})
        fiora = party["character_states"]["Fiora"]
        self.assertEqual(
            set(fiora["equipment"]),
            {"RIGHT", "LEFT", "HEAD", "BODY", "ARM"},
        )
        self.assertEqual(len(fiora["proficiencies"]), 13)
        self.assertEqual(
            fiora["ability_bonuses"],
            {"strength": 0, "agility": 0, "magic": 0},
        )
        self.assertEqual(fiora["event_spell_keys"], [])
        self.assertEqual(document["event_flags"], ["fairy_saved", "prologue_complete"])
        self.assertEqual(document["visited_site_ids"], ["sample_town"])
        self.assertEqual(
            document["opened_treasures"],
            [{"map_id": "nectar_forest", "treasure_id": "entrance_potion"}],
        )
        self.assertEqual(
            document["monster_records"],
            {"Giant Spider": {"revealed_field_keys": ["FIRE", "profile"]}},
        )
        self.assertEqual(
            document["logs"],
            [{"text_key": "shop.greeting", "arguments": {"COUNT": 2}}],
        )
        self.assertNotIn("automapping", document)
        self.assertNotIn("important_items", document)
        self.assertNotIn("world_progression", document)

    def test_repository_writes_all_manual_slots_and_reads_preview_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SaveRepository(Path(directory))
            document = self.save_document()

            summary = repository.save(SAVE_SLOT_COUNT, document)

            self.assertEqual(summary.slot, SAVE_SLOT_COUNT)
            self.assertTrue(summary.occupied)
            self.assertEqual(summary.saved_at, "2026-09-04T12:34:56+09:00")
            self.assertEqual(
                summary.party_character_keys,
                ("Fiora", "Cerion"),
            )
            self.assertEqual(
                json.loads(repository.slot_path(SAVE_SLOT_COUNT).read_text()),
                document,
            )
            self.assertFalse(
                repository.slot_path(SAVE_SLOT_COUNT).with_suffix(".json.tmp").exists()
            )
            summaries = repository.summaries()
            self.assertEqual(len(summaries), SAVE_SLOT_COUNT)
            self.assertFalse(summaries[0].occupied)
            self.assertEqual(summaries[-1], summary)

    def test_corrupt_slot_remains_occupied_without_preview_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SaveRepository(Path(directory))
            repository.slot_path(2).write_text("not-json", encoding="utf-8")

            summary = repository.summary(2)

            self.assertTrue(summary.occupied)
            self.assertIsNone(summary.saved_at)
            self.assertEqual(summary.party_character_keys, ())

    def test_repository_rejects_non_v1_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SaveRepository(Path(directory))
            with self.assertRaises(SaveSystemError):
                repository.save(1, {"format_version": 2})
            with self.assertRaises(SaveSystemError):
                repository.save(1, {"format_version": 1})
            self.assertFalse(repository.slot_path(1).exists())


if __name__ == "__main__":
    unittest.main()
