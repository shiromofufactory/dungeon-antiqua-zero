from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from game import Game
from resources.events import EventCatalog, EventResourceError
from state import SaveData
from systems.conditions import evaluate_condition
from scripts.event_pipeline import compile_event_sources, validate_missions


CATALOGS = {
    "flag_ids": {"quest.started", "quest.done"},
    "character_keys": {"Fiora"},
    "item_keys": {"POTION"},
    "message_ids": {"mission.first", "mission.second"},
}


def missions() -> list[dict[str, object]]:
    return [
        {"id": "z_first", "note": "制作メモ", "condition": {"type": "all", "conditions": [
            {"type": "flag_set", "flag_id": "quest.started"},
            {"type": "not", "condition": {"type": "flag_set", "flag_id": "quest.done"}},
        ]}, "message_id": "mission.first"},
        {"id": "a_second", "message_id": "mission.second"},
    ]


class MissionTest(unittest.TestCase):
    def test_compilation_retains_order_and_conditions_and_removes_notes(self) -> None:
        compiled = compile_event_sources({}, missions=missions(), **CATALOGS)
        self.assertEqual([value["id"] for value in compiled["missions"]], ["z_first", "a_second"])
        self.assertNotIn("note", compiled["missions"][0])
        catalog = EventCatalog.from_document(compiled)
        self.assertEqual([mission.id for mission in catalog.missions], ["z_first", "a_second"])
        with self.assertRaises(TypeError):
            catalog.missions[0].condition["type"] = "not"
        changed = missions()
        changed.reverse()
        self.assertNotEqual(compiled["source_sha256"], compile_event_sources({}, missions=changed, **CATALOGS)["source_sha256"])

    def test_rejects_duplicates_invalid_groups_and_unknown_references(self) -> None:
        cases = (
            ({"id": "z_first"}, "duplicate_mission_id"),
            ({"id": "Invalid"}, "invalid_mission_id"),
            ({"condition": {"type": "flag_set", "flag_id": "missing"}}, "unknown_flag"),
            ({"condition": {"type": "any", "conditions": []}}, "empty_condition_group"),
            ({"condition": {"type": "item_at_least", "item_key": "POTION", "quantity": 0}}, "invalid_quantity"),
            ({"condition": {"type": "unknown"}}, "unknown_condition"),
            ({"message_id": "mission.missing"}, "unknown_message"),
            ({"commands": []}, "unknown_field"),
        )
        for changes, code in cases:
            values = missions()
            values[1].update(changes)
            self.assertIn(code, {error.code for error in validate_missions(values, **CATALOGS)})
            with self.assertRaises(ValueError):
                compile_event_sources({}, missions=values, **CATALOGS)

    def test_condition_depth_is_bounded_in_source_and_runtime(self) -> None:
        condition = {"type": "flag_set", "flag_id": "quest.started"}
        for _ in range(18):
            condition = {"type": "not", "condition": condition}
        values = missions()
        values[0]["condition"] = condition
        self.assertIn("condition_too_deep", {error.code for error in validate_missions(values, **CATALOGS)})
        compiled = compile_event_sources({}, missions=missions(), **CATALOGS)
        compiled["missions"][0]["condition"] = condition
        with self.assertRaises(EventResourceError):
            EventCatalog.from_document(compiled)

    def test_conditions_use_flags_party_and_inventory_without_mutation(self) -> None:
        save_data = SaveData(event_flags={"quest.started"})
        party = Mock(contains=Mock(return_value=True))
        inventory = Mock(quantity=Mock(return_value=2))
        condition = {"type": "all", "conditions": [
            missions()[0]["condition"],
            {"type": "any", "conditions": [
                {"type": "flag_set", "flag_id": "quest.done"},
                {"type": "member_in_party", "character_key": "Fiora"},
            ]},
            {"type": "item_at_least", "item_key": "POTION", "quantity": 2},
        ]}
        self.assertTrue(evaluate_condition(condition, save_data=save_data, party=party, inventory=inventory))
        self.assertEqual(save_data.event_flags, {"quest.started"})
        save_data.event_flags.add("quest.done")
        self.assertFalse(evaluate_condition(condition, save_data=save_data, party=party, inventory=inventory))

    @patch("game.InformationMenuOverlay")
    def test_game_rechecks_conditions_each_time_information_is_opened(self, overlay: Mock) -> None:
        game = Game.__new__(Game)
        game.event_catalog = EventCatalog.from_document(compile_event_sources({}, missions=missions(), **CATALOGS))
        game.save_data = SaveData()
        for name in ("command_cursor", "monsters", "items", "settings", "texts", "event_messages", "fonts", "images", "alert", "party_system", "inventory_system"):
            setattr(game, name, Mock())
        for flags, expected in ((set(), ("mission.second",)), ({"quest.started"}, ("mission.first", "mission.second")), ({"quest.started", "quest.done"}, ("mission.second",))):
            game.save_data.event_flags = flags
            game._start_information()
            self.assertEqual(overlay.call_args.kwargs["mission_message_ids"], expected)
        self.assertEqual(game.save_data.logs, [])


if __name__ == "__main__":
    unittest.main()
