from __future__ import annotations

from copy import deepcopy
import unittest

from scripts.event_pipeline import compile_event_sources, validate_event_sources
from app.resources.events import EventCatalog, EventResourceError


CATALOGS = {
    "flag_ids": {"story.met_alvan"},
    "character_keys": {"Fiora", "Alvan"},
    "item_keys": {"POTION"},
    "monster_keys": {"SLIME"},
    "tall_first_monster_keys": {"TREANT"},
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
    def test_death_condition_compiles_and_loads_without_attributes(self) -> None:
        source = sample_source()
        branch = source["events"][0]["commands"][0]
        for condition in (
            {"type": "any_member_dead"},
            {"type": "not", "condition": {"type": "any_member_dead"}},
            {"type": "all", "conditions": [{"type": "any", "conditions": [{"type": "any_member_dead"}]}]},
        ):
            with self.subTest(condition=condition):
                branch["condition"] = condition
                self.assertEqual(validate_event_sources({"sample": source}, **CATALOGS), [])
                compiled = compile_event_sources({"sample": source}, **CATALOGS)
                self.assertEqual(compiled["events"]["sample.greeting"]["commands"][0]["condition"], condition)
                EventCatalog.from_document(compiled)

        branch["condition"] = {"type": "any_member_dead", "character_key": "Fiora"}
        self.assertEqual({item.code for item in validate_event_sources({"sample": source}, **CATALOGS)}, {"unknown_field"})
        compiled["events"]["sample.greeting"]["commands"][0]["condition"] = branch["condition"]
        with self.assertRaises(EventResourceError):
            EventCatalog.from_document(compiled)

    def test_bgm_stop_compiles_in_both_contexts_and_rejects_extra_fields(self) -> None:
        source = sample_source()
        source["events"][0]["commands"] = [{"command": "stop_bgm"}]
        for battle_start_id in (None, "guard"):
            if battle_start_id is not None:
                source["events"][0]["battle_start_id"] = battle_start_id
            self.assertEqual(validate_event_sources({"sample": source}, **CATALOGS), [])
            self.assertEqual(compile_event_sources({"sample": source}, **CATALOGS)["events"]["sample.greeting"]["commands"], [{"command": "stop_bgm"}])
        source["events"][0]["commands"][0]["bgm_id"] = "field/world"
        self.assertEqual({item.code for item in validate_event_sources({"sample": source}, **CATALOGS)}, {"unknown_field"})

    def test_screen_effects_compile_in_both_contexts_and_reject_invalid_values(self) -> None:
        source = sample_source()
        commands = [{"command": "change_brightness", "percent": value} for value in (0, 25, 50, 75, 100)]
        commands += [{"command": "shake_screen", "frames": value} for value in (6, 12, 18)]
        source["events"][0]["commands"] = commands
        for battle_start_id in (None, "guard"):
            if battle_start_id is not None:
                source["events"][0]["battle_start_id"] = battle_start_id
            self.assertEqual(validate_event_sources({"sample": source}, **CATALOGS), [])
            self.assertEqual(compile_event_sources({"sample": source}, **CATALOGS)["events"]["sample.greeting"]["commands"], commands)
        for command_type, field, values, code in (
            ("change_brightness", "percent", (None, True, False, 0.0, 25.0, "50", -25, 26, 125), "invalid_brightness_percent"),
            ("shake_screen", "frames", (None, True, 6.0, "6", 0, -6, 7), "invalid_shake_screen_frames"),
        ):
            for value in values:
                with self.subTest(command=command_type, value=value):
                    source["events"][0]["commands"] = [{"command": command_type, field: value}]
                    self.assertEqual({item.code for item in validate_event_sources({"sample": source}, **CATALOGS)}, {code})

    def test_give_item_compiles_optional_boolean_message_setting(self) -> None:
        source = sample_source()
        for option in ({}, {"show_message": False}, {"show_message": True}):
            with self.subTest(option=option):
                command = {"command": "give_item", "item_key": "POTION", "quantity": 3, **option}
                source["events"][0]["commands"] = [command]
                self.assertEqual(validate_event_sources({"sample": source}, **CATALOGS), [])
                self.assertEqual(compile_event_sources({"sample": source}, **CATALOGS)["events"]["sample.greeting"]["commands"], [command])

    def test_give_item_rejects_nonboolean_message_option_and_take_item_option(self) -> None:
        source = sample_source()
        command = {"command": "give_item", "item_key": "POTION", "quantity": 1}
        source["events"][0]["commands"] = [command]
        for value in (None, 0, 1, "on", "false"):
            with self.subTest(value=value):
                command["show_message"] = value
                self.assertEqual({item.code for item in validate_event_sources({"sample": source}, **CATALOGS)}, {"invalid_show_message"})
        command.update(command="take_item", show_message=True)
        self.assertEqual({item.code for item in validate_event_sources({"sample": source}, **CATALOGS)}, {"unknown_field"})

    def test_wait_compiles_in_six_frame_units_in_field_and_battle_events(self) -> None:
        source = sample_source()
        source["events"][0]["commands"] = [{"command": "wait", "frames": 6}, {"command": "wait", "frames": 12}]
        for battle_start_id in (None, "guard"):
            with self.subTest(battle_start_id=battle_start_id):
                if battle_start_id is not None:
                    source["events"][0]["battle_start_id"] = battle_start_id
                self.assertEqual(validate_event_sources({"sample": source}, **CATALOGS), [])
                compiled = compile_event_sources({"sample": source}, **CATALOGS)
                self.assertEqual(compiled["events"]["sample.greeting"]["commands"], source["events"][0]["commands"])

    def test_wait_rejects_missing_nonpositive_nonmultiple_and_noninteger_frames(self) -> None:
        source = sample_source()
        for frames in (None, 0, -6, 1, 7, 6.0, True, "6"):
            with self.subTest(frames=frames):
                source["events"][0]["commands"] = [{"command": "wait", "frames": frames}]
                diagnostics = validate_event_sources({"sample": source}, **CATALOGS)
                self.assertEqual([(item.code, item.path) for item in diagnostics], [
                    ("invalid_wait_frames", "sample.events[0].commands[0].frames"),
                ])
        source["events"][0]["commands"] = [{"command": "wait"}]
        self.assertIn("invalid_wait_frames", {item.code for item in validate_event_sources({"sample": source}, **CATALOGS)})

    def test_facing_commands_compile_and_validate_field_only_attributes(self) -> None:
        commands = [
            {"command": "face_party", "direction": "right"},
            {"command": "face_actor", "actor_id": "elder", "direction": "up"},
        ]
        source = sample_source()
        source["events"][0]["commands"] = commands
        compiled = compile_event_sources({"sample": source}, **CATALOGS)
        self.assertEqual(compiled["events"]["sample.greeting"]["commands"], commands)
        source["events"][0]["battle_start_id"] = "guard"
        self.assertEqual([
            item.code for item in validate_event_sources({"sample": source}, **CATALOGS)
        ], ["field_only_battle_command"] * 2)

    def test_facing_commands_reject_invalid_direction_actor_and_steps(self) -> None:
        source = sample_source()
        source["events"][0]["commands"] = [
            {"command": "face_party", "direction": "north", "steps": 1},
            {"command": "face_actor", "actor_id": "Bad ID", "direction": "up"},
        ]
        self.assertEqual({
            item.code for item in validate_event_sources({"sample": source}, **CATALOGS)
        }, {"unknown_field", "invalid_direction", "invalid_actor_id"})

    def test_flash_screen_accepts_white_and_rejects_other_colors(self) -> None:
        source = sample_source()
        source["events"][0]["commands"] = [{"command": "flash_screen", "color": "white"}]

        self.assertEqual(validate_event_sources({"sample": source}, **CATALOGS), [])
        self.assertEqual(
            compile_event_sources({"sample": source}, **CATALOGS)["events"]["sample.greeting"]["commands"],
            [{"command": "flash_screen", "color": "white"}],
        )
        source["events"][0]["commands"][0]["color"] = "red"
        self.assertIn("invalid_flash_color", {
            item.code for item in validate_event_sources({"sample": source}, **CATALOGS)
        })

    def test_empty_then_with_commands_in_else_is_not_a_warning(self) -> None:
        source = sample_source()

        diagnostics = validate_event_sources({"sample": source}, **CATALOGS)
        compiled = compile_event_sources({"sample": source}, **CATALOGS)

        self.assertEqual(diagnostics, [])
        self.assertEqual(
            compiled["events"]["sample.greeting"]["commands"][0]["then"],
            [],
        )

    def test_branch_with_both_sides_empty_still_warns(self) -> None:
        source = sample_source()
        source["events"][0]["commands"][0]["else"] = []

        diagnostics = validate_event_sources({"sample": source}, **CATALOGS)

        self.assertEqual(
            [(item.code, item.path) for item in diagnostics],
            [("empty_commands", "sample.events[0].commands[0].then")],
        )

    def test_compiles_event_battle_and_start_trigger(self) -> None:
        source = sample_source()
        source["events"][0]["commands"] = [{
            "command": "start_battle",
            "battle_id": "shrine_guard",
            "monster_keys": ["SLIME", "SLIME"],
        }]
        source["events"].append({
            "id": "guard_opens",
            "battle_start_id": "shrine_guard",
            "commands": [{"command": "set_flag", "flag_id": "story.met_alvan"}],
        })

        compiled = compile_event_sources({"sample": source}, **CATALOGS)

        self.assertEqual(compiled["battle_start_events"], {
            "shrine_guard": "sample.guard_opens"
        })
        self.assertEqual(
            compiled["events"]["sample.greeting"]["commands"][0]["monster_keys"],
            ["SLIME", "SLIME"],
        )

    def test_rejects_duplicate_battle_trigger_and_unknown_monster(self) -> None:
        source = sample_source()
        source["events"][0]["battle_start_id"] = "shrine_guard"
        source["events"][0]["commands"] = [{
            "command": "start_battle",
            "battle_id": "shrine_guard",
            "monster_keys": ["MISSING"],
        }]
        source["events"].append({
            "id": "again", "battle_start_id": "shrine_guard", "commands": []
        })

        codes = {item.code for item in validate_event_sources(
            {"sample": source}, **CATALOGS
        )}

        self.assertIn("duplicate_battle_start_id", codes)
        self.assertIn("unknown_monster", codes)

    def test_rejects_field_command_nested_in_battle_start_event(self) -> None:
        source = sample_source()
        source["events"][0]["battle_start_id"] = "shrine_guard"
        source["events"][0]["commands"] = [{
            "command": "branch",
            "condition": {"type": "flag_set", "flag_id": "story.met_alvan"},
            "then": [{"command": "start_battle", "battle_id": "again", "monster_keys": ["SLIME"]}],
            "else": [],
        }]

        codes = {item.code for item in validate_event_sources(
            {"sample": source}, **CATALOGS
        )}

        self.assertIn("field_only_battle_command", codes)

    def test_rejects_five_monsters_after_tall_first_monster(self) -> None:
        source = sample_source()
        source["events"][0]["commands"] = [{
            "command": "start_battle", "battle_id": "forest_guard",
            "monster_keys": ["TREANT", "SLIME", "SLIME", "SLIME", "SLIME"],
        }]
        catalogs = {**CATALOGS, "monster_keys": {"TREANT", "SLIME"}}

        codes = {item.code for item in validate_event_sources(
            {"sample": source}, **catalogs
        )}

        self.assertIn("oversized_monster_lineup", codes)

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
