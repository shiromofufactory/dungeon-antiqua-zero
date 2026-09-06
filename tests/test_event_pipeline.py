from __future__ import annotations

from copy import deepcopy
import unittest

from scripts.event_pipeline import compile_event_sources, validate_event_sources


CATALOGS = {
    "flag_ids": {"story.met_alvan"},
    "character_keys": {"Fiora", "Alvan"},
    "item_keys": {"POTION"},
    "shop_keys": {"FAIRY_HAMLET_ITEMS"},
    "message_ids": {"sample.greeting"},
    "bgm_ids": {"field/world"},
    "se_ids": {"confirm"},
}


def sample_source() -> dict[str, object]:
    return {
        "format_version": 1,
        "namespace": "sample",
        "events": [
            {
                "id": "greeting",
                "note": "sample",
                "commands": [
                    {
                        "command": "branch",
                        "condition": {
                            "type": "flag_set",
                            "flag_id": "story.met_alvan",
                        },
                        "then": [],
                        "else": [
                            {
                                "command": "message",
                                "message_id": "sample.greeting",
                            },
                            {"command": "give_item", "item_key": "POTION", "quantity": 1},
                            {"command": "set_flag", "flag_id": "story.met_alvan"},
                        ],
                    }
                ],
            }
        ],
    }


class EventPipelineTest(unittest.TestCase):
    def test_validates_and_compiles_fully_qualified_ids(self) -> None:
        sources = {"sample": sample_source()}

        diagnostics = validate_event_sources(sources, **CATALOGS)
        compiled = compile_event_sources(sources, **CATALOGS)

        self.assertEqual(
            [item for item in diagnostics if item.severity == "error"], []
        )
        self.assertEqual(compiled["flags"], ["story.met_alvan"])
        self.assertEqual(tuple(compiled["events"]), ("sample.greeting",))
        self.assertNotIn("note", compiled["events"]["sample.greeting"])

    def test_rejects_unknown_references_and_namespace_mismatch(self) -> None:
        source = sample_source()
        source["namespace"] = "wrong"
        command = source["events"][0]["commands"][0]["else"][0]
        command["message_id"] = "sample.missing"
        source["events"][0]["commands"][0]["condition"]["flag_id"] = (
            "missing_flag"
        )

        codes = {
            item.code
            for item in validate_event_sources({"sample": source}, **CATALOGS)
            if item.severity == "error"
        }

        self.assertIn("namespace_filename_mismatch", codes)
        self.assertIn("unknown_message", codes)
        self.assertIn("unknown_flag", codes)

    def test_rejects_unknown_fields_and_invalid_movement(self) -> None:
        source = deepcopy(sample_source())
        source["events"][0]["commands"] = [
            {
                "command": "move_party",
                "direction": "north",
                "steps": 0,
                "typo": True,
            }
        ]

        codes = {
            item.code
            for item in validate_event_sources({"sample": source}, **CATALOGS)
        }

        self.assertEqual(
            {"unknown_field", "invalid_direction", "invalid_steps"} - codes,
            set(),
        )

    def test_rejects_portrait_on_message_command(self) -> None:
        source = deepcopy(sample_source())
        command = source["events"][0]["commands"][0]["else"][0]
        command["portrait_character_key"] = "Alvan"

        codes = {
            item.code
            for item in validate_event_sources({"sample": source}, **CATALOGS)
        }

        self.assertIn("unknown_field", codes)

    def test_accepts_attribute_free_end_event_inside_branch(self) -> None:
        source = deepcopy(sample_source())
        source["events"][0]["commands"][0]["then"] = [
            {"command": "end_event"}
        ]

        diagnostics = validate_event_sources({"sample": source}, **CATALOGS)
        compiled = compile_event_sources({"sample": source}, **CATALOGS)

        self.assertEqual(
            [item for item in diagnostics if item.severity == "error"], []
        )
        self.assertEqual(
            compiled["events"]["sample.greeting"]["commands"][0]["then"],
            [{"command": "end_event"}],
        )

    def test_rejects_attributes_on_end_event(self) -> None:
        source = deepcopy(sample_source())
        source["events"][0]["commands"] = [
            {"command": "end_event", "unexpected": True}
        ]

        codes = {
            item.code
            for item in validate_event_sources({"sample": source}, **CATALOGS)
        }

        self.assertIn("unknown_field", codes)

    def test_accepts_party_recovery_and_known_shop(self) -> None:
        source = deepcopy(sample_source())
        source["events"][0]["commands"] = [
            {"command": "recover_party"},
            {"command": "open_shop", "shop_key": "FAIRY_HAMLET_ITEMS"},
        ]

        diagnostics = validate_event_sources({"sample": source}, **CATALOGS)

        self.assertEqual(
            [item for item in diagnostics if item.severity == "error"], []
        )

    def test_rejects_unknown_shop(self) -> None:
        source = deepcopy(sample_source())
        source["events"][0]["commands"] = [
            {"command": "open_shop", "shop_key": "MISSING"}
        ]

        codes = {
            item.code
            for item in validate_event_sources({"sample": source}, **CATALOGS)
        }

        self.assertIn("unknown_shop", codes)


if __name__ == "__main__":
    unittest.main()
