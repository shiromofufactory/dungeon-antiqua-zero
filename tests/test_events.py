from __future__ import annotations

import unittest

from app.input import Direction
from app.item import Item
from app.member import EquipmentSlot, Member, ProficiencyKind
from app.resources.events import EventCatalog, EventResourceError
from app.state import SaveData
from app.systems import (
    EventContext,
    EventRunner,
    EventRuntimeError,
    InventorySystem,
    MessageEffect,
    MovePartyEffect,
    PartySystem,
)


def item_record(key: str) -> Item:
    return Item.from_record(
        {
            "name_en": key,
            "name_ja": key,
            "type1": "ITEM",
            "type2": "GENERAL",
            "price": 10,
            "atk": 0,
            "hit": 0,
            "dfc": 0,
            "eva": 0,
            "rst": 0,
            "tolerance": "",
        }
    )


def character_record(key: str, character_type: str) -> dict[str, object]:
    record: dict[str, object] = {
        "name_en": key,
        "name_ja": key,
        "type": character_type,
        "race": "FAIRY" if key == "Fiora" else "HUMAN",
        "gender": "FEMALE" if key == "Fiora" else "MALE",
        "skills": [],
        "lv_diff": 0,
        "base_hp": 40,
        "base_mp": 10,
        "base_str": 20,
        "base_agi": 20,
        "base_mag": 20,
        "face_x": 0,
        "face_y": 0,
        **{kind.value: 1 for kind in ProficiencyKind},
    }
    for slot in EquipmentSlot:
        record[f"equip_{slot.value.lower()}"] = ""
    return record


def runtime_document(commands: list[dict[str, object]]) -> dict[str, object]:
    return {
        "format_version": 1,
        "source_sha256": "0" * 64,
        "flags": ["sample.done"],
        "events": {"sample.run": {"commands": commands}},
    }


class EventRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.records = (
            character_record("Fiora", "MAIN"),
            character_record("Alvan", "SUB"),
        )
        self.items = {"POTION": item_record("POTION")}
        fiora = Member.from_record(self.records[0], items=self.items, skills={})
        self.party = PartySystem(
            character_records=self.records,
            items=self.items,
            skills={},
            active_party=(fiora,),
        )
        self.inventory = InventorySystem(self.items)
        self.save_data = SaveData()

    def runner(self, commands: list[dict[str, object]]) -> EventRunner:
        catalog = EventCatalog.from_document(runtime_document(commands))
        return EventRunner.from_catalog(
            catalog,
            "sample.run",
            context=EventContext.FIELD,
            save_data=self.save_data,
            party=self.party,
            inventory=self.inventory,
        )

    def test_mutates_state_and_waits_for_external_effects_in_order(self) -> None:
        runner = self.runner(
            [
                {"command": "join_party", "character_key": "Alvan"},
                {"command": "give_item", "item_key": "POTION", "quantity": 2},
                {"command": "message", "text_key": "event.sample.greeting"},
                {"command": "move_party", "direction": "right", "steps": 2},
                {"command": "set_flag", "flag_id": "sample.done"},
            ]
        )

        message = runner.advance()
        self.assertEqual(message, MessageEffect("event.sample.greeting"))
        self.assertTrue(self.party.contains("Alvan"))
        self.assertEqual(self.inventory.quantity("POTION"), 2)
        self.assertIs(runner.advance(), message)

        runner.complete_effect(message)
        movement = runner.advance()
        self.assertEqual(movement, MovePartyEffect(Direction.RIGHT, 2))
        runner.complete_effect(movement)
        self.assertIsNone(runner.advance())
        self.assertTrue(runner.is_complete)
        self.assertIn("sample.done", self.save_data.event_flags)

    def test_branch_uses_current_flag_member_and_item_state(self) -> None:
        self.save_data.event_flags.add("sample.done")
        self.inventory.add("POTION", 1)
        runner = self.runner(
            [
                {
                    "command": "branch",
                    "condition": {
                        "type": "all",
                        "conditions": [
                            {"type": "flag_set", "flag_id": "sample.done"},
                            {"type": "member_in_party", "character_key": "Fiora"},
                            {"type": "item_at_least", "item_key": "POTION", "quantity": 1},
                        ],
                    },
                    "then": [{"command": "take_item", "item_key": "POTION", "quantity": 1}],
                    "else": [],
                }
            ]
        )

        self.assertIsNone(runner.advance())
        self.assertTrue(runner.is_complete)
        self.assertEqual(self.inventory.quantity("POTION"), 0)

    def test_failing_atomic_item_change_stops_the_event(self) -> None:
        runner = self.runner(
            [{"command": "take_item", "item_key": "POTION", "quantity": 1}]
        )

        with self.assertRaises(EventRuntimeError):
            runner.advance()

    def test_party_leave_preserves_state_for_rejoin(self) -> None:
        self.party.join("Alvan")
        alvan = self.party.active_party[-1]
        alvan.hp = 1

        self.party.leave("Alvan")
        self.party.join("Alvan")

        self.assertIs(self.party.active_party[-1], alvan)
        self.assertEqual(self.party.active_party[-1].hp, 1)

    def test_runtime_catalog_rejects_unknown_nested_command(self) -> None:
        document = runtime_document(
            [
                {
                    "command": "branch",
                    "condition": {"type": "flag_set", "flag_id": "sample.done"},
                    "then": [{"command": "unknown"}],
                    "else": [],
                }
            ]
        )

        with self.assertRaises(EventResourceError):
            EventCatalog.from_document(document)


if __name__ == "__main__":
    unittest.main()
