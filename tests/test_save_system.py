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
from member import internal_level_for_experience, required_experience_for_level
from systems import (
    SAVE_FORMAT_VERSION,
    SAVE_SLOT_COUNT,
    InventorySystem,
    SaveRepository,
    SaveSystemError,
    create_save_document,
    restore_save_document,
)
from tools.screen_mocks._fixtures import (
    load_mock_character_records,
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
                encounter_count=83,
                difficulty=Difficulty.HARD,
                play_time_frames=890,
                event_flags={"prologue_complete", "fairy_saved"},
                visited_site_ids={"sample_town"},
                opened_treasures={
                    ("nectar_forest", "entrance_potion"),
                },
                monster_records={
                    "Giant Spider": {
                        "FIRE",
                        "profile",
                        "treasure_acquired",
                    },
                },
                logs=[
                    {
                        "text_key": "shop.greeting",
                        "arguments": {"COUNT": 2},
                    },
                    {
                        "message_id": "sample.greeting",
                        "arguments": {},
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

    def test_creates_complete_current_version_document(self) -> None:
        document = self.save_document()

        self.assertEqual(document["format_version"], SAVE_FORMAT_VERSION)
        self.assertEqual(document["saved_at"], "2026-09-04T12:34:56+09:00")
        self.assertEqual(
            document["progress"],
            {
                "gold": 123,
                "experience": 456,
                "battle_count": 7,
                "encounter_count": 83,
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
            {
                "Giant Spider": {
                    "revealed_field_keys": [
                        "FIRE",
                        "profile",
                        "treasure_acquired",
                    ]
                }
            },
        )
        self.assertEqual(
            document["logs"],
            [
                {"text_key": "shop.greeting", "arguments": {"COUNT": 2}},
                {"message_id": "sample.greeting", "arguments": {}},
            ],
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
            self.assertEqual(summary.dead_character_keys, ())
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

    def test_repository_preview_derives_dead_active_members_from_saved_hp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SaveRepository(Path(directory))
            document = self.save_document()
            states = document["party"]["character_states"]
            states["Fiora"]["hp"] = 0
            states["Cerion"]["hp"] = 0
            states["Alvan"]["hp"] = 0

            summary = repository.save(1, document)

            self.assertEqual(
                summary.dead_character_keys,
                ("Fiora", "Cerion"),
            )

    def test_corrupt_slot_remains_occupied_without_preview_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SaveRepository(Path(directory))
            repository.slot_path(2).write_text("not-json", encoding="utf-8")

            summary = repository.summary(2)

            self.assertTrue(summary.occupied)
            self.assertIsNone(summary.saved_at)
            self.assertEqual(summary.party_character_keys, ())

    def test_repository_rejects_non_current_write_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SaveRepository(Path(directory))
            with self.assertRaises(SaveSystemError):
                repository.save(1, {"format_version": 2})
            with self.assertRaises(SaveSystemError):
                repository.save(1, {"format_version": 1})
            self.assertFalse(repository.slot_path(1).exists())

    def test_restores_complete_state_and_rederives_internal_levels(self) -> None:
        document = self.save_document()

        restored = restore_save_document(
            document,
            character_records=load_mock_character_records(),
            items=self.items,
            skills=self.skills,
        )

        self.assertEqual(restored.save_data.gold, 123)
        self.assertEqual(restored.save_data.encounter_count, 83)
        self.assertEqual(restored.save_data.difficulty, Difficulty.HARD)
        self.assertEqual(
            restored.save_data.monster_records,
            {
                "Giant Spider": {
                    "FIRE",
                    "profile",
                    "treasure_acquired",
                }
            },
        )
        self.assertEqual(
            [member.definition.key for member in restored.active_party],
            ["Fiora", "Cerion"],
        )
        self.assertEqual(set(restored.character_states), {"Fiora", "Cerion", "Alvan"})
        self.assertEqual(restored.map_id, "worldmap")
        self.assertEqual(restored.position, FieldPosition(17, 39))
        self.assertIs(restored.facing, Direction.LEFT)
        round_tripped = create_save_document(
            save_data=restored.save_data,
            active_party=restored.active_party,
            character_states=restored.character_states,
            inventory=restored.inventory,
            map_id=restored.map_id,
            position=restored.position,
            facing=restored.facing,
            saved_at=datetime.fromisoformat(document["saved_at"]),
        )
        for state in round_tripped["party"]["character_states"].values():
            self.assertEqual(
                state["internal_level"],
                internal_level_for_experience(
                    document["progress"]["experience"]
                    + state["experience_offset"]
                ),
            )

    def test_migrates_version_one_member_level_to_an_experience_offset(self) -> None:
        document = self.save_document()
        document["format_version"] = 1
        for state in document["party"]["character_states"].values():
            del state["experience_offset"]

        restored = restore_save_document(
            document,
            character_records=load_mock_character_records(),
            items=self.items,
            skills=self.skills,
        )

        for member in restored.character_states.values():
            saved_level = document["party"]["character_states"][
                member.definition.key
            ]["internal_level"]
            self.assertEqual(member.internal_level, saved_level)
            self.assertEqual(
                member.experience_offset,
                required_experience_for_level(saved_level)
                - document["progress"]["experience"],
            )

    def test_legacy_version_one_save_defaults_missing_encounter_count(self) -> None:
        document = self.save_document()
        del document["progress"]["encounter_count"]

        restored = restore_save_document(
            document,
            character_records=load_mock_character_records(),
            items=self.items,
            skills=self.skills,
        )

        self.assertEqual(restored.save_data.encounter_count, 0)

    def test_repository_loads_and_deletes_slot_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SaveRepository(Path(directory))
            document = self.save_document()
            repository.save(3, document)

            self.assertEqual(repository.load(3), document)
            repository.delete(3)

            self.assertFalse(repository.slot_path(3).exists())
            self.assertFalse(repository.summary(3).occupied)
            with self.assertRaises(SaveSystemError):
                repository.load(3)

    def test_restore_rejects_corrupt_member_before_returning_state(self) -> None:
        document = self.save_document()
        document["party"]["character_states"]["Fiora"]["hp"] = -1

        with self.assertRaises(SaveSystemError):
            restore_save_document(
                document,
                character_records=load_mock_character_records(),
                items=self.items,
                skills=self.skills,
            )


if __name__ == "__main__":
    unittest.main()
