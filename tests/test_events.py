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
from app.state import LaunchMode, SaveData
from app.systems import (
    ChangeBrightnessEffect,
    StopBgmEffect,
    ResetGameEffect,
    ShakeScreenEffect,
    EventContext,
    EventRunner,
    EventRuntimeError,
    FaceActorEffect,
    FacePartyEffect,
    FlashScreenEffect,
    InventorySystem,
    MessageEffect,
    ItemReceivedEffect,
    MovePartyEffect,
    OpenShopEffect,
    PartySystem,
    StartBattleEffect,
    WaitEffect,
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
    def test_reset_waits_after_message_and_discards_all_branch_continuations(self) -> None:
        for context in EventContext:
            with self.subTest(context=context):
                self.save_data.event_flags.clear()
                runner = self.runner([
                    {"command": "message", "message_id": "sample.end"},
                    {"command": "branch", "condition": {
                        "type": "not", "condition": {"type": "flag_set", "flag_id": "sample.done"},
                    }, "then": [
                        {"command": "reset_game"},
                        {"command": "set_flag", "flag_id": "sample.done"},
                    ], "else": []},
                    {"command": "set_flag", "flag_id": "sample.done"},
                ])
                runner.context = context
                message = runner.advance()
                self.assertEqual(message, MessageEffect("sample.end"))
                self.assertIs(runner.advance(), message)
                runner.complete_effect(message)
                reset = runner.advance()
                self.assertEqual(reset, ResetGameEffect())
                self.assertIs(runner.advance(), reset)
                runner.complete_effect(reset)
                self.assertIsNone(runner.advance())
                self.assertTrue(runner.is_complete)
                self.assertNotIn("sample.done", self.save_data.event_flags)

    def test_launch_mode_branches_in_field_and_battle_with_nested_conditions(self) -> None:
        for context in EventContext:
            for mode in LaunchMode:
                for target in LaunchMode:
                    with self.subTest(context=context, mode=mode, target=target):
                        condition = {"type": "all", "conditions": [
                            {"type": "any", "conditions": [{"type": "launch_mode", "mode": target.value}]},
                            {"type": "not", "condition": {"type": "flag_set", "flag_id": "sample.done"}},
                        ]}
                        catalog = EventCatalog.from_document(runtime_document([{
                            "command": "branch", "condition": condition,
                            "then": [{"command": "message", "message_id": "sample.matches"}],
                            "else": [{"command": "message", "message_id": "sample.other"}],
                        }]))
                        runner = EventRunner.from_catalog(
                            catalog, "sample.run", context=context,
                            save_data=self.save_data, party=self.party,
                            inventory=self.inventory, launch_mode=mode,
                        )
                        expected = "sample.matches" if mode is target else "sample.other"
                        self.assertEqual(runner.advance(), MessageEffect(expected))

    def test_bgm_stop_waits_for_audio_completion_before_following_commands(self) -> None:
        for context in EventContext:
            with self.subTest(context=context):
                self.save_data.event_flags.clear()
                runner = self.runner([
                    {"command": "stop_bgm"},
                    {"command": "set_flag", "flag_id": "sample.done"},
                ])
                runner.context = context
                effect = runner.advance()
                self.assertEqual(effect, StopBgmEffect())
                self.assertIs(runner.advance(), effect)
                self.assertNotIn("sample.done", self.save_data.event_flags)
                runner.complete_effect(effect)
                self.assertIsNone(runner.advance())
                self.assertIn("sample.done", self.save_data.event_flags)
        with self.assertRaises(EventResourceError):
            EventCatalog.from_document(runtime_document([{"command": "stop_bgm", "bgm_id": "da3-field"}]))

    def test_screen_effects_wait_for_completion_in_field_and_battle_events(self) -> None:
        for context in EventContext:
            with self.subTest(context=context):
                self.save_data.event_flags.clear()
                runner = self.runner([
                    {"command": "change_brightness", "percent": 0},
                    {"command": "shake_screen", "frames": 18},
                    {"command": "set_flag", "flag_id": "sample.done"},
                ])
                runner.context = context
                for expected in (ChangeBrightnessEffect(0), ShakeScreenEffect(18)):
                    effect = runner.advance()
                    self.assertEqual(effect, expected)
                    self.assertIs(runner.advance(), effect)
                    self.assertNotIn("sample.done", self.save_data.event_flags)
                    runner.complete_effect(effect)
                self.assertIsNone(runner.advance())
                self.assertIn("sample.done", self.save_data.event_flags)

    def test_screen_effect_loader_rejects_invalid_fields_and_values(self) -> None:
        for command in (
            *({"command": "change_brightness", "percent": value} for value in (None, True, False, 0.0, 25.0, "50", -25, 26, 125)),
            *({"command": "shake_screen", "frames": value} for value in (None, True, 6.0, "6", 0, -6, 7)),
            {"command": "change_brightness"}, {"command": "shake_screen"},
            {"command": "change_brightness", "percent": 50, "frames": 6},
            {"command": "shake_screen", "frames": 6, "direction": "up"},
        ):
            with self.subTest(command=command), self.assertRaises(EventResourceError):
                EventCatalog.from_document(runtime_document([command]))

    def test_give_item_adds_all_items_once_before_waiting_for_notification(self) -> None:
        for context in EventContext:
            with self.subTest(context=context):
                self.inventory = InventorySystem(self.items)
                self.save_data.event_flags.clear()
                runner = self.runner([
                    {"command": "give_item", "item_key": "POTION", "quantity": 3, "show_message": True},
                    {"command": "set_flag", "flag_id": "sample.done"},
                ])
                runner.context = context
                effect = runner.advance()
                self.assertEqual(effect, ItemReceivedEffect("POTION"))
                self.assertEqual(self.inventory.quantity("POTION"), 3)
                self.assertIs(runner.advance(), effect)
                self.assertEqual(self.inventory.quantity("POTION"), 3)
                self.assertNotIn("sample.done", self.save_data.event_flags)
                runner.complete_effect(effect)
                self.assertIsNone(runner.advance())
                self.assertEqual(self.inventory.quantity("POTION"), 3)
                self.assertIn("sample.done", self.save_data.event_flags)

    def test_give_item_without_notification_finishes_immediately(self) -> None:
        for option in ({}, {"show_message": False}):
            with self.subTest(option=option):
                runner = self.runner([{"command": "give_item", "item_key": "POTION", "quantity": 2, **option}])
                self.assertIsNone(runner.advance())
                self.assertTrue(runner.is_complete)

    def test_give_item_over_capacity_never_emits_a_success_notification(self) -> None:
        self.inventory.add("POTION", 98)
        runner = self.runner([
            {"command": "give_item", "item_key": "POTION", "quantity": 2, "show_message": True},
            {"command": "set_flag", "flag_id": "sample.done"},
        ])
        with self.assertRaisesRegex(EventRuntimeError, "item capacity exceeded"):
            runner.advance()
        self.assertEqual(self.inventory.quantity("POTION"), 98)
        self.assertNotIn("sample.done", self.save_data.event_flags)

    def test_runtime_loader_requires_boolean_give_item_message_option(self) -> None:
        for value in (None, 0, 1, "on", "false"):
            with self.subTest(value=value), self.assertRaises(EventResourceError):
                EventCatalog.from_document(runtime_document([{
                    "command": "give_item", "item_key": "POTION", "quantity": 1, "show_message": value,
                }]))
        with self.assertRaises(EventResourceError):
            EventCatalog.from_document(runtime_document([{
                "command": "take_item", "item_key": "POTION", "quantity": 1, "show_message": True,
            }]))

    def test_wait_delays_following_command_in_field_and_battle_events(self) -> None:
        for context in EventContext:
            with self.subTest(context=context):
                self.save_data.event_flags.clear()
                runner = self.runner([
                    {"command": "wait", "frames": 12},
                    {"command": "set_flag", "flag_id": "sample.done"},
                ])
                runner.context = context
                effect = runner.advance()
                self.assertEqual(effect, WaitEffect(12))
                self.assertIs(runner.advance(), effect)
                self.assertNotIn("sample.done", self.save_data.event_flags)
                runner.complete_effect(effect)
                self.assertIsNone(runner.advance())
                self.assertIn("sample.done", self.save_data.event_flags)

    def test_runtime_loader_rejects_invalid_wait_frames(self) -> None:
        for frames in (None, 0, -6, 1, 7, 6.0, True, "6"):
            with self.subTest(frames=frames), self.assertRaises(EventResourceError):
                EventCatalog.from_document(runtime_document([{"command": "wait", "frames": frames}]))
        for command in ({"command": "wait"}, {"command": "wait", "frames": 6, "steps": 1}):
            with self.subTest(command=command), self.assertRaises(EventResourceError):
                EventCatalog.from_document(runtime_document([command]))

    def test_facing_effects_run_in_order_before_the_following_command(self) -> None:
        runner = self.runner([
            {"command": "face_party", "direction": "right"},
            {"command": "face_actor", "actor_id": "elder", "direction": "up"},
            {"command": "set_flag", "flag_id": "sample.done"},
        ])
        for expected in (FacePartyEffect(Direction.RIGHT), FaceActorEffect("elder", Direction.UP)):
            effect = runner.advance()
            self.assertEqual(effect, expected)
            self.assertIs(runner.advance(), effect)
            self.assertNotIn("sample.done", self.save_data.event_flags)
            runner.complete_effect(effect)
        self.assertIsNone(runner.advance())
        self.assertIn("sample.done", self.save_data.event_flags)

    def test_facing_commands_reject_battle_context(self) -> None:
        for command in (
            {"command": "face_party", "direction": "left"},
            {"command": "face_actor", "actor_id": "elder", "direction": "down"},
        ):
            with self.subTest(command=command):
                runner = self.runner([command])
                runner.context = EventContext.BATTLE
                with self.assertRaisesRegex(EventRuntimeError, "only available in field"):
                    runner.advance()

    def test_runtime_loader_rejects_invalid_facing_commands(self) -> None:
        for command in (
            {"command": "face_party", "direction": "north"},
            {"command": "face_party", "direction": "up", "steps": 1},
            {"command": "face_actor", "direction": "up"},
            {"command": "face_actor", "actor_id": "Bad ID", "direction": "up"},
        ):
            with self.subTest(command=command), self.assertRaises(EventResourceError):
                EventCatalog.from_document(runtime_document([command]))

    def test_flash_screen_waits_before_following_command(self) -> None:
        runner = self.runner([
            {"command": "flash_screen", "color": "white"},
            {"command": "set_flag", "flag_id": "sample.done"},
        ])

        effect = runner.advance()
        self.assertEqual(effect, FlashScreenEffect("white"))
        self.assertIs(runner.advance(), effect)
        self.assertNotIn("sample.done", self.save_data.event_flags)
        runner.complete_effect(effect)
        self.assertIsNone(runner.advance())
        self.assertIn("sample.done", self.save_data.event_flags)

    def test_runtime_loader_rejects_unknown_flash_color(self) -> None:
        document = runtime_document([{"command": "flash_screen", "color": "red"}])
        with self.assertRaises(EventResourceError):
            EventCatalog.from_document(document)

    def test_empty_then_runs_else_only_while_flag_is_off(self) -> None:
        commands = [{
            "command": "branch",
            "condition": {"type": "flag_set", "flag_id": "sample.done"},
            "then": [],
            "else": [
                {"command": "start_battle", "battle_id": "guard", "monster_keys": ["SLIME"]},
                {"command": "set_flag", "flag_id": "sample.done"},
            ],
        }]
        runner = self.runner(commands)

        effect = runner.advance()
        self.assertEqual(effect, StartBattleEffect("guard", ("SLIME",)))
        runner.complete_effect(effect)
        self.assertIsNone(runner.advance())
        self.assertIn("sample.done", self.save_data.event_flags)

        next_runner = self.runner(commands)
        self.assertIsNone(next_runner.advance())
        self.assertTrue(next_runner.is_complete)

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

    def test_branch_detects_dead_active_members_in_field_and_battle(self) -> None:
        self.party.join("Alvan")
        fiora, alvan = self.party.active_party
        commands = [{
            "command": "branch",
            "condition": {"type": "any_member_dead"},
            "then": [{"command": "message", "message_id": "sample.dead"}],
            "else": [{"command": "message", "message_id": "sample.alive"}],
        }]
        alvan.poisoned = True
        for context in EventContext:
            for health in ((1, 1), (0, 1), (1, 0), (0, 0)):
                with self.subTest(context=context, health=health):
                    fiora.hp, alvan.hp = health
                    runner = self.runner(commands)
                    runner.context = context
                    expected = "sample.dead" if 0 in health else "sample.alive"
                    self.assertEqual(runner.advance(), MessageEffect(expected))
                    self.assertEqual((fiora.hp, alvan.hp), health)
                    self.assertTrue(alvan.poisoned)

        fiora.hp, alvan.hp = 1, 0
        self.party.leave("Alvan")
        self.assertIs(self.party.character_states["Alvan"], alvan)
        self.assertEqual(self.runner(commands).advance(), MessageEffect("sample.alive"))

    def test_death_condition_rechecks_health_after_event_recovery(self) -> None:
        self.party.join("Alvan")
        self.party.active_party[1].hp = 0
        runner = self.runner([
            {
                "command": "branch",
                "condition": {"type": "any_member_dead"},
                "then": [{"command": "recover_party"}],
                "else": [{"command": "end_event"}],
            },
            {
                "command": "branch",
                "condition": {"type": "not", "condition": {"type": "any_member_dead"}},
                "then": [{"command": "message", "message_id": "sample.recovered"}],
                "else": [],
            },
        ])

        self.assertEqual(runner.advance(), MessageEffect("sample.recovered"))
        self.assertTrue(all(member.is_alive for member in self.party.active_party))

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
