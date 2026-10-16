from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from tools._bootstrap import APP_ROOT
from battle_command_memory import BattleCommandMemory
from battle_commands import BattleCommand
from field import FieldPosition
from input import Direction
from state import Difficulty, SaveData
from member import EquipmentSlot, internal_level_for_experience, required_experience_for_level
from systems import (
    AUTO_SAVE_SLOT,
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

    def save_document(self, memory=None) -> dict[str, object]:
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
            battle_command_memory=memory,
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

    def test_battle_memory_round_trip_uses_keys_and_preserves_independent_choices(self):
        for command in ("fight", "escape", "auto"):
            with self.subTest(command=command):
                memory = BattleCommandMemory(
                    global_command=command,
                    commands={
                        "Fiora": BattleCommand.SPELL,
                        "Alvan": BattleCommand.HIDE,
                    },
                    spells={"Fiora": "HEALING1", "Alvan": "FIRE1"},
                    items={
                        "Fiora": ("POTION", None),
                        "Cerion": ("MIRACLE RING", EquipmentSlot.ARM),
                        "Alvan": ("SHORT SWORD", EquipmentSlot.RIGHT),
                    },
                )
                document = json.loads(json.dumps(self.save_document(memory)))
                restored = restore_save_document(
                    document,
                    character_records=load_mock_character_records(),
                    items=self.items,
                    skills=self.skills,
                )
                self.assertEqual(restored.battle_command_memory, memory)
                serialized = document["battle_command_memory"]
                self.assertEqual(serialized["global_command"], command)
                self.assertEqual(serialized["commands"]["Fiora"], "spell")
                self.assertEqual(serialized["items"]["Cerion"]["equipment_slot"], "ARM")
                self.assertIsNone(serialized["items"]["Fiora"]["equipment_slot"])
                self.assertEqual(
                    set(serialized), {"global_command", "commands", "spells", "items"}
                )
                self.assertIsNot(restored.battle_command_memory, memory)
                restored.battle_command_memory.clear()
                self.assertEqual(memory.global_command, command)
                self.assertEqual(document["battle_command_memory"], serialized)

    def test_legacy_saves_without_battle_memory_restore_empty_choices(self):
        for version in (1, 2, SAVE_FORMAT_VERSION):
            with self.subTest(version=version):
                document = self.save_document()
                document["format_version"] = version
                del document["battle_command_memory"]
                if version == 1:
                    for state in document["party"]["character_states"].values():
                        del state["experience_offset"]
                restored = restore_save_document(
                    document,
                    character_records=load_mock_character_records(),
                    items=self.items,
                    skills=self.skills,
                )
                self.assertEqual(restored.battle_command_memory, BattleCommandMemory())

    def test_invalid_battle_memory_is_rejected_before_restoration(self):
        for value in (
            None,
            [],
            {"global_command": "unknown"},
            {"global_command": True},
            {"commands": []},
            {"commands": {"": "attack"}},
            {"commands": {"Fiora": "unknown"}},
            {"commands": {"Fiora": 1}},
            {"spells": {"Fiora": ""}},
            {"spells": {"Fiora": False}},
            {"items": {"Fiora": []}},
            {"items": {"Fiora": {"item_key": "POTION", "equipment_slot": "FOOT"}}},
            {"items": {"Fiora": {"item_key": "POTION", "equipment_slot": 0}}},
            {"items": {"Fiora": {"item_key": ""}}},
        ):
            with self.subTest(value=value):
                document = self.save_document()
                document["battle_command_memory"] = value
                with self.assertRaises(SaveSystemError):
                    restore_save_document(
                        document,
                        character_records=load_mock_character_records(),
                        items=self.items,
                        skills=self.skills,
                    )

    def test_battle_memory_keeps_history_of_currently_unavailable_spells_and_items(
        self,
    ):
        memory = BattleCommandMemory(
            spells={"Fiora": "missing_spell"},
            items={"Fiora": ("missing_item", EquipmentSlot.ARM)},
        )
        restored = restore_save_document(
            self.save_document(memory),
            character_records=load_mock_character_records(),
            items=self.items,
            skills=self.skills,
        )
        self.assertEqual(restored.battle_command_memory, memory)

    def test_repository_persists_battle_memory_in_each_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = SaveRepository(Path(directory))
            for slot, command in enumerate(("fight", "escape", "auto"), start=1):
                repository.save(
                    slot,
                    self.save_document(BattleCommandMemory(global_command=command)),
                )
            for slot, command in enumerate(("fight", "escape", "auto"), start=1):
                restored = restore_save_document(
                    repository.load(slot),
                    character_records=load_mock_character_records(),
                    items=self.items,
                    skills=self.skills,
                )
                self.assertEqual(restored.battle_command_memory.global_command, command)

    def test_migrates_legacy_village_ids_without_changing_source_or_unknown_keys(self) -> None:
        for version in (1, 2):
            for include_corrected_ids in (False, True):
                with self.subTest(version=version, include_corrected_ids=include_corrected_ids):
                    document = self.save_document()
                    document["format_version"] = version
                    document["location"]["map_id"] = "faily_village"
                    document["event_flags"] = ["faily_village.event_1", "faily_village.event_2", "faily_village.unknown", "quest.unregistered"]
                    document["opened_treasures"] = [
                        {"map_id": "faily_village", "treasure_id": "chest_1"},
                        {"map_id": "forest_nector", "treasure_id": "chest_2"},
                    ]
                    document["logs"] = [
                        {"message_id": "faily_village.opening_1", "arguments": {"TEXT": "faily_village"}},
                        {"message_id": "forest_nector.message_0_1", "arguments": {}},
                        {"text_key": "faily_village.ui_text", "arguments": {}},
                    ]
                    if include_corrected_ids:
                        document["event_flags"].append("fairy_village.event_1")
                        document["opened_treasures"].append({"map_id": "fairy_village", "treasure_id": "chest_1"})
                    original = json.dumps(document, sort_keys=True)
                    restored = restore_save_document(
                        document, character_records=load_mock_character_records(),
                        items=self.items, skills=self.skills,
                    )
                    self.assertEqual(restored.map_id, "fairy_village")
                    self.assertEqual(restored.save_data.event_flags, {
                        "fairy_village.event_1", "fairy_village.event_2", "faily_village.unknown", "quest.unregistered",
                    })
                    self.assertEqual(restored.save_data.opened_treasures, {
                        ("fairy_village", "chest_1"), ("forest_nector", "chest_2"),
                    })
                    self.assertEqual(restored.save_data.logs, [
                        {"message_id": "fairy_village.opening_1", "arguments": {"TEXT": "faily_village"}},
                        document["logs"][1], document["logs"][2],
                    ])
                    self.assertEqual(json.dumps(document, sort_keys=True), original)
                    resaved = create_save_document(
                        save_data=restored.save_data, active_party=restored.active_party,
                        character_states=restored.character_states, inventory=restored.inventory,
                        map_id=restored.map_id, position=restored.position, facing=restored.facing,
                        battle_command_memory=restored.battle_command_memory,
                    )
                    self.assertEqual(resaved["format_version"], 3)
                    self.assertEqual(resaved["location"]["map_id"], "fairy_village")
                    self.assertEqual(resaved["logs"][0]["message_id"], "fairy_village.opening_1")
                    self.assertNotIn("faily_village.event_1", resaved["event_flags"])

    def test_legacy_village_slot_preview_uses_corrected_map_without_rewriting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SaveRepository(Path(directory))
            for version in (1, 2):
                document = self.save_document()
                document["format_version"] = version
                document["location"]["map_id"] = "faily_village"
                original = json.dumps(document)
                repository.slot_path(1).write_text(original)
                self.assertEqual(repository.summary(1).map_id, "fairy_village")
                self.assertEqual(repository.load(1), document)
                self.assertEqual(repository.slot_path(1).read_text(), original)

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
            self.assertEqual(summary.map_id, "worldmap")
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

    def test_preview_reads_legacy_locations_and_tolerates_invalid_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SaveRepository(Path(directory))
            for version in (1, 2, SAVE_FORMAT_VERSION):
                document = self.save_document()
                document["format_version"] = version
                for location in (
                    {"map_id": "forest_nector"},
                    None, {}, {"map_id": ""}, {"map_id": 123},
                ):
                    with self.subTest(version=version, location=location):
                        document["location"] = location
                        repository.slot_path(1).write_text(json.dumps(document))
                        summary = repository.summary(1)
                        self.assertTrue(summary.occupied)
                        self.assertEqual(summary.party_character_keys, ("Fiora", "Cerion"))
                        self.assertEqual(
                            summary.map_id,
                            "forest_nector" if location == {"map_id": "forest_nector"} else None,
                        )

    def test_autosave_uses_slot_zero_and_cannot_be_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SaveRepository(Path(directory))
            document = self.save_document()

            summary = repository.save(AUTO_SAVE_SLOT, document)

            self.assertEqual(summary.slot, AUTO_SAVE_SLOT)
            self.assertEqual(repository.load(AUTO_SAVE_SLOT), document)
            self.assertEqual(repository.summary(AUTO_SAVE_SLOT), summary)
            self.assertEqual(len(repository.summaries()), SAVE_SLOT_COUNT)
            self.assertTrue(repository.slot_path(AUTO_SAVE_SLOT).exists())
            with self.assertRaises(ValueError):
                repository.delete(AUTO_SAVE_SLOT)
            self.assertTrue(repository.slot_path(AUTO_SAVE_SLOT).exists())

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
        self.assertEqual(restored.save_data.play_time_frames, 890)
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
        self.assertEqual(round_tripped["progress"]["play_time_frames"], 890)
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
