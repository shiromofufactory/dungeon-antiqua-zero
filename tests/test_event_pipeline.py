from __future__ import annotations

from copy import deepcopy
import unittest

from scripts.event_pipeline import compile_event_sources, validate_event_sources


CATALOGS = {
    "character_keys": {"Fiora", "Alvan"},
    "item_keys": {"POTION"},
    "text_keys": {"event.sample.greeting"},
    "bgm_ids": {"field/world"},
    "se_ids": {"confirm"},
}


def sample_source() -> dict[str, object]:
    return {
        "format_version": 1,
        "namespace": "sample",
        "flags": [{"id": "met_alvan", "note": "met"}],
        "events": [
            {
                "id": "greeting",
                "note": "sample",
                "commands": [
                    {
                        "command": "branch",
                        "condition": {
                            "type": "flag_set",
                            "flag_id": "sample.met_alvan",
                        },
                        "then": [],
                        "else": [
                            {
                                "command": "message",
                                "text_key": "event.sample.greeting",
                                "portrait_character_key": "Alvan",
                            },
                            {"command": "give_item", "item_key": "POTION", "quantity": 1},
                            {"command": "set_flag", "flag_id": "sample.met_alvan"},
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
        self.assertEqual(compiled["flags"], ["sample.met_alvan"])
        self.assertEqual(tuple(compiled["events"]), ("sample.greeting",))
        self.assertNotIn("note", compiled["events"]["sample.greeting"])

    def test_rejects_unknown_references_and_namespace_mismatch(self) -> None:
        source = sample_source()
        source["namespace"] = "wrong"
        command = source["events"][0]["commands"][0]["else"][0]
        command["text_key"] = "event.missing"

        codes = {
            item.code
            for item in validate_event_sources({"sample": source}, **CATALOGS)
            if item.severity == "error"
        }

        self.assertIn("namespace_filename_mismatch", codes)
        self.assertIn("unknown_text", codes)
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


if __name__ == "__main__":
    unittest.main()
