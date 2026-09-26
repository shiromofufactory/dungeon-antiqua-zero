from __future__ import annotations

import unittest

from app.input import Direction
from app.item import Item
from app.member import (
    EquipmentSlot,
    Member,
    ProficiencyKind,
    required_experience_for_level,
)
from app.resources.events import EventCatalog, EventResourceError
from app.state import SaveData
from app.systems import (
    EventContext,
    EventRunner,
    EventRuntimeError,
    InventorySystem,
    MessageEffect,
    MovePartyEffect,
    OpenShopEffect,
    PartySystem,
    StartBattleEffect,
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
    def test_start_battle_waits_and_then_continues(self) -> None:
        runner = self.runner([
            {"command": "start_battle", "battle_id": "guard", "monster_keys": ["SLIME"]},
            {"command": "set_flag", "flag_id": "sample.done"},
        ])

        effect = runner.advance()
        self.assertEqual(effect, StartBattleEffect("guard", ("SLIME",)))
        self.assertNotIn("sample.done", self.save_data.event_flags)
        runner.complete_effect(effect)
        self.assertIsNone(runner.advance())
        self.assertIn("sample.done", self.save_data.event_flags)

    def test_battle_start_trigger_resolves_event(self) -> None:
        document = runtime_document([])
        document["battle_start_events"] = {"guard": "sample.run"}

        catalog = EventCatalog.from_document(document)

        self.assertEqual(catalog.battle_start_event("guard"), "sample.run")
        self.assertIsNone(catalog.battle_start_event("other"))

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
                {"command": "message", "message_id": "sample.greeting"},
                {"command": "move_party", "direction": "right", "steps": 2},
                {"command": "set_flag", "flag_id": "sample.done"},
            ]
        )

        message = runner.advance()
        self.assertEqual(message, MessageEffect("sample.greeting"))
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

    def test_end_event_inside_branch_skips_all_remaining_commands(self) -> None:
        runner = self.runner(
            [
                {
                    "command": "branch",
                    "condition": {"type": "flag_set", "flag_id": "sample.done"},
                    "then": [
                        {"command": "set_flag", "flag_id": "sample.reached"},
                        {"command": "end_event"},
                        {"command": "set_flag", "flag_id": "sample.branch_after"},
                    ],
                    "else": [],
                },
                {"command": "set_flag", "flag_id": "sample.root_after"},
            ]
        )
        self.save_data.event_flags.add("sample.done")

        self.assertIsNone(runner.advance())

        self.assertTrue(runner.is_complete)
        self.assertIn("sample.reached", self.save_data.event_flags)
        self.assertNotIn("sample.branch_after", self.save_data.event_flags)
        self.assertNotIn("sample.root_after", self.save_data.event_flags)

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

    def test_join_event_anchors_level_difference_to_shared_experience(self) -> None:
        self.records[1]["lv_diff"] = 17
        self.save_data.experience = 10
        runner = self.runner(
            [{"command": "join_party", "character_key": "Alvan"}]
        )

        self.assertIsNone(runner.advance())

        alvan = self.party.active_party[-1]
        self.assertEqual(alvan.internal_level, 18)
        self.assertEqual(
            alvan.experience_offset,
            required_experience_for_level(18) - 10,
        )

    def test_recover_party_restores_hp_mp_and_all_conditions(self) -> None:
        self.party.join("Alvan")
        for member in self.party.active_party:
            member.hp = 0
            member.mp = 0
            member.poisoned = True
            member.paralyzed = True
            member.sleeping = 3
            member.confused = 2
        runner = self.runner([{"command": "recover_party"}])

        self.assertIsNone(runner.advance())

        for member in self.party.active_party:
            self.assertEqual(member.hp, member.max_hp)
            self.assertEqual(member.mp, member.max_mp)
            self.assertFalse(member.poisoned)
            self.assertFalse(member.paralyzed)
            self.assertEqual(member.sleeping, 0)
            self.assertEqual(member.confused, 0)

    def test_open_shop_waits_for_field_effect_completion(self) -> None:
        runner = self.runner([
            {"command": "open_shop", "shop_key": "FAIRY_HAMLET_ITEMS"},
            {"command": "set_flag", "flag_id": "sample.done"},
        ])

        effect = runner.advance()

        self.assertEqual(effect, OpenShopEffect("FAIRY_HAMLET_ITEMS"))
        self.assertNotIn("sample.done", self.save_data.event_flags)
        runner.complete_effect(effect)
        self.assertIsNone(runner.advance())
        self.assertIn("sample.done", self.save_data.event_flags)

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

    def test_runtime_catalog_rejects_invalid_message_id(self) -> None:
        document = runtime_document(
            [{"command": "message", "message_id": "Invalid"}]
        )

        with self.assertRaises(EventResourceError):
            EventCatalog.from_document(document)

    def test_runtime_catalog_rejects_portrait_on_message_command(self) -> None:
        document = runtime_document(
            [{
                "command": "message",
                "message_id": "sample.greeting",
                "portrait_character_key": "Alvan",
            }]
        )

        with self.assertRaises(EventResourceError):
            EventCatalog.from_document(document)

    def test_runtime_catalog_accepts_unprefixed_global_flag(self) -> None:
        document = runtime_document([])
        document["flags"] = ["game_started"]

        catalog = EventCatalog.from_document(document)

        self.assertEqual(catalog.flag_ids, frozenset({"game_started"}))


if __name__ == "__main__":
    unittest.main()
