from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import ANY, Mock, patch

from game import Game, GameScreenChange
from field import FieldActors, FieldMovement, FieldPosition
from input import Direction, InputButton, InputState
from resources import (
    CompiledMap,
    EventCatalog,
    MapActor,
    MapCell,
    MapEventTrigger,
    MapTreasureContents,
)
from rendering import FadeThroughBlack
from scenes.battle import BattleEncounter, BattlePhase, BattleResult
from state import SaveData, Settings
from systems import (
    InventorySystem,
    MessageEffect,
    FlashScreenEffect,
    MovePartyEffect,
    OpenShopEffect,
    StartBattleEffect,
    TreasureSystem,
)


def compiled_map(
    trigger: MapEventTrigger | None,
    *,
    actors: tuple[MapActor, ...] = (),
    width: int = 3,
    interact_through_rows: tuple[str, ...] = (),
) -> CompiledMap:
    static = {activation: {} for activation in ("step", "touch", "interact")}
    if trigger is not None:
        for activation in trigger.activations:
            for cell in trigger.cells:
                static[activation][(cell.x, cell.y)] = trigger
    return CompiledMap(
        map_id="test_map",
        profile="town",
        tileset_id="worldmap",
        tile_size=16,
        width=width,
        height=3,
        atlas=object(),
        atlas_columns=1,
        atlas_tile_count=1,
        ground_tiles=(0,) * (width * 3),
        object_tiles=(),
        collision_rows=("0" * width, "0" * width, "0" * width),
        ground_animations=MappingProxyType({}),
        object_animations=MappingProxyType({}),
        actors=actors,
        event_triggers=() if trigger is None else (trigger,),
        event_trigger_index=MappingProxyType(
            {key: MappingProxyType(value) for key, value in static.items()}
        ),
        actor_event_triggers=MappingProxyType(
            {}
            if trigger is None or trigger.actor_id is None
            else {trigger.actor_id: (trigger,)}
        ),
        interact_through_rows=interact_through_rows,
    )


def game_for(
    trigger: MapEventTrigger,
    *,
    actors: tuple[MapActor, ...] = (),
    width: int = 3,
    interact_through_rows: tuple[str, ...] = (),
) -> Game:
    game = Game.__new__(Game)
    game.current_map = compiled_map(
        trigger,
        actors=actors,
        width=width,
        interact_through_rows=interact_through_rows,
    )
    game.field = FieldMovement(
        game.current_map,
        start=FieldPosition(1, 1),
        speed=16,
        facing=Direction.RIGHT,
    )
    game.field_actors = FieldActors(game.current_map) if actors else None
    game.event_release_direction = None
    game.event_release_confirm = False
    game._start_field_event = Mock(return_value=True)
    game._handle_arrived_site = Mock()
    game._refresh_site_name_label = Mock()
    game._begin_screen_change = Mock()
    return game


class GameEventTriggerTest(unittest.TestCase):
    def test_event_flash_restores_palette_before_resuming_commands(self) -> None:
        game = Game.__new__(Game)
        effect = FlashScreenEffect("white")
        game.event_runner = Mock(advance=Mock(return_value=effect))
        game.party_system = Mock(active_party=(), character_states={})
        game.settings = Settings()
        game.palette_shifter = Mock()
        game._continue_event()

        self.assertIs(game.event_effect, effect)
        game.palette_shifter.set_global_mix.assert_called_with(
            base_rate=5 / 6, target_color=0xFFFFFF,
        )
        game._continue_event = Mock()
        for _ in range(5):
            game._update_event(InputState())
            game.event_runner.complete_effect.assert_not_called()
        game.palette_shifter.set_global_mix.assert_called_with(
            base_rate=0.0, target_color=0xFFFFFF,
        )
        for _ in range(5):
            game._update_event(InputState())
            game.event_runner.complete_effect.assert_not_called()
        game._update_event(InputState())

        self.assertIsNone(game.event_screen_flash)
        self.assertIsNone(game.event_effect)
        game.palette_shifter.set_global_mix.assert_called_with(
            base_rate=1.0, target_color=0xFFFFFF,
        )
        game.event_runner.complete_effect.assert_called_once_with(effect)
        game._continue_event.assert_called_once_with()

    def test_reduced_screen_flash_setting_skips_visual_effect(self) -> None:
        game = Game.__new__(Game)
        effect = FlashScreenEffect("white")
        runner = Mock(advance=Mock(side_effect=[effect, None]), is_complete=False)
        game.event_runner = runner
        game.party_system = Mock(active_party=(), character_states={})
        game.settings = Settings(screen_flash_enabled=False)
        game.palette_shifter = Mock()

        game._continue_event()

        self.assertIs(game.event_runner, runner)
        runner.complete_effect.assert_called_once_with(effect)
        game.palette_shifter.set_global_mix.assert_not_called()

    def test_completed_flag_branch_does_not_pause_held_step_movement(self) -> None:
        trigger = MapEventTrigger(
            "floor", "sample.run", frozenset(("step",)),
            cells=(MapCell(2, 1),),
        )
        game = game_for(trigger, width=4)
        game._start_field_event = Game._start_field_event.__get__(game, Game)
        game.event_catalog = EventCatalog.from_document({
            "format_version": 1,
            "source_sha256": "0" * 64,
            "flags": ["sample.done"],
            "events": {"sample.run": {"commands": [{
                "command": "branch",
                "condition": {"type": "flag_set", "flag_id": "sample.done"},
                "then": [],
                "else": [{
                    "command": "start_battle", "battle_id": "guard",
                    "monster_keys": ["SLIME"],
                }],
            }]}},
        })
        game.party = (object(),)
        game.character_states = {}
        game.party_system = Mock(
            active_party=game.party, character_states=game.character_states,
        )
        game.inventory_system = Mock()
        game.save_data = SimpleNamespace(event_flags={"sample.done"})
        game.selected_member_index = 0
        game.event_runner = None
        game._apply_dungeon_step_health_changes = Mock()
        game._advance_random_encounter = Mock(return_value=False)

        game._update_field(InputState(held_direction=Direction.RIGHT))

        self.assertEqual(game.field.position, FieldPosition(2, 1))
        self.assertIsNone(game.event_runner)
        self.assertIsNone(game.event_release_direction)
        game._update_field(InputState(held_direction=Direction.RIGHT))
        self.assertEqual(game.field.position, FieldPosition(3, 1))

        game.field = FieldMovement(
            game.current_map,
            start=FieldPosition(1, 1),
            speed=16,
            facing=Direction.RIGHT,
        )
        game.save_data.event_flags.clear()
        game.suspended_field_event = None
        game._begin_random_encounter = Mock()
        game._update_field(InputState(held_direction=Direction.RIGHT))

        self.assertEqual(game.field.position, FieldPosition(2, 1))
        self.assertEqual(game.pending_event_battle_id, "guard")
        self.assertIs(game.event_release_direction, Direction.RIGHT)
        game._begin_random_encounter.assert_called_once_with()

    def test_registered_battle_event_defers_first_command_menu(self) -> None:
        game = Game.__new__(Game)
        game.encounter_transition = Mock(
            is_finished=True,
            palette_base_rate=0.0,
            palette_target_color=0,
        )
        game.palette_shifter = Mock(base_colors=(0,))
        game.pending_event_battle_encounter = BattleEncounter(("SLIME",))
        game.pending_event_battle_id = "shrine_guard"
        game.event_catalog = Mock()
        game.event_catalog.battle_start_event.return_value = "sample.guard_opens"
        battle = Mock()
        game._build_battle_scene = Mock(return_value=battle)

        game._update_encounter_transition()

        battle.defer_first_party_command.assert_called_once_with()
        self.assertTrue(game.pending_first_party_turn_hint)

    def test_named_battle_suspends_field_event_until_result(self) -> None:
        game = Game.__new__(Game)
        runner = Mock()
        effect = StartBattleEffect("shrine_guard", ("SLIME",))
        game.event_runner = runner
        game.event_effect = effect
        game.suspended_field_event = None
        game._begin_random_encounter = Mock()
        game._continue_event = Mock()

        game._begin_event_battle(effect)

        self.assertEqual(game.pending_event_battle_id, "shrine_guard")
        self.assertEqual(game.pending_event_battle_encounter.monster_keys, ("SLIME",))
        self.assertFalse(game.pending_event_battle_encounter.escape_command_enabled)
        self.assertIsNone(game.event_runner)
        self.assertIsNone(game.event_effect)
        game._begin_random_encounter.assert_called_once_with()

        game._resume_event_after_battle(BattleResult.VICTORY)

        runner.complete_effect.assert_called_once_with(effect)
        self.assertIs(game.event_runner, runner)
        game._continue_event.assert_called_once_with()

    def test_named_battle_event_starts_before_first_command_window_opens(self) -> None:
        game = Game.__new__(Game)
        game.battle_scene = Mock(
            is_party_command_pending=True,
            is_party_command_ready=False,
            result=None,
        )
        game.pending_first_party_turn_hint = True
        game.pending_event_battle_id = "shrine_guard"
        game.event_catalog = Mock()
        game.event_catalog.battle_start_event.return_value = "sample.guard_opens"
        game._start_battle_event = Mock()
        game._show_hint_once = Mock()

        self.assertTrue(game._update_battle_scene(InputState()))

        game.battle_scene.update.assert_called_once_with(InputState())
        game._start_battle_event.assert_called_once_with("sample.guard_opens")
        game._show_hint_once.assert_not_called()
        game.battle_scene.open_pending_party_command.assert_not_called()
        self.assertIsNone(game.pending_event_battle_id)
        self.assertFalse(game.pending_first_party_turn_hint)

    def test_command_window_waits_until_battle_event_and_hint_finish(self) -> None:
        game = Game.__new__(Game)
        game.battle_scene = Mock(
            is_party_command_pending=True,
            is_party_command_ready=False,
            phase=BattlePhase.INITIAL,
            result=None,
        )
        game.pending_first_party_turn_hint = False
        game.hint_overlay = Mock()

        game._update_battle_scene(InputState())
        game.battle_scene.open_pending_party_command.assert_not_called()

        game.hint_overlay = None
        game._update_battle_scene(InputState())
        game.battle_scene.open_pending_party_command.assert_called_once_with()

    @patch("game.MessageOverlay")
    def test_touching_treasure_opens_it_before_normal_movement(
        self,
        message_overlay: Mock,
    ) -> None:
        actor = MapActor(
            "gold_chest",
            MapCell(2, 1),
            "treasure",
            0,
            contents=MapTreasureContents("gold", amount=50),
        )
        game = game_for(None, actors=(actor,))
        game.save_data = SaveData(gold=10)
        game.inventory_system = InventorySystem({})
        game.treasure_system = TreasureSystem(
            save_data=game.save_data,
            inventory=game.inventory_system,
        )
        game.character_states = {}
        game.settings = Settings()
        game.fonts = Mock()
        game.texts = Mock()
        game.texts.formatted_text.return_value = "宝箱には　５０Ｇが入っていた！"
        game.field.facing = Direction.LEFT

        with patch("game.play_se") as play_se:
            game._update_field(InputState(held_direction=Direction.RIGHT))

        self.assertEqual(game.field.position, FieldPosition(1, 1))
        self.assertIs(game.field.facing, Direction.RIGHT)
        self.assertEqual(game.save_data.gold, 60)
        self.assertIn(("test_map", "gold_chest"), game.save_data.opened_treasures)
        self.assertEqual(game.field_actors.actor("gold_chest").treasure_frame, 1)
        message_overlay.assert_called_once_with(
            lines=("宝箱には　５０Ｇが入っていた！",),
            settings=game.settings,
            fonts=game.fonts,
        )
        game.texts.formatted_text.assert_called_once_with(
            "treasure.found_gold",
            ANY,
            {"AMOUNT": "５０"},
        )
        play_se.assert_called_once_with("treasure_open")

    @patch("game.MessageOverlay")
    def test_opened_treasure_has_no_special_reaction(
        self,
        message_overlay: Mock,
    ) -> None:
        actor = MapActor(
            "gold_chest",
            MapCell(2, 1),
            "treasure",
            0,
            contents=MapTreasureContents("gold", amount=50),
        )
        game = game_for(None, actors=(actor,))
        game.save_data = SaveData(
            gold=60,
            opened_treasures={("test_map", "gold_chest")},
        )
        game.inventory_system = InventorySystem({})
        game.treasure_system = TreasureSystem(
            save_data=game.save_data,
            inventory=game.inventory_system,
        )
        game.character_states = {}
        game.field_actors = FieldActors(
            game.current_map,
            opened_treasure_ids=("gold_chest",),
        )

        with patch("game.play_se") as play_se:
            game._update_field(InputState(held_direction=Direction.RIGHT))

        self.assertEqual(game.field.position, FieldPosition(1, 1))
        self.assertEqual(game.save_data.gold, 60)
        self.assertEqual(game.field_actors.actor("gold_chest").treasure_frame, 2)
        self.assertIsNone(game.event_release_direction)
        self.assertFalse(game.event_release_confirm)
        message_overlay.assert_not_called()
        play_se.assert_not_called()

    @patch("game.MessageOverlay")
    def test_capacity_failure_starts_closing_after_the_message_finishes(
        self,
        message_overlay: Mock,
    ) -> None:
        actor = MapActor(
            "gold_chest",
            MapCell(2, 1),
            "treasure",
            0,
            contents=MapTreasureContents("gold", amount=50),
        )
        game = game_for(None, actors=(actor,))
        game.save_data = SaveData(gold=999_980)
        game.inventory_system = InventorySystem({})
        game.treasure_system = TreasureSystem(
            save_data=game.save_data,
            inventory=game.inventory_system,
        )
        game.character_states = {}
        game.settings = Settings()
        game.fonts = Mock()
        game.texts = Mock()
        game.texts.formatted_text.return_value = "宝箱には　５０Ｇが入っていた！"
        game.texts.text.return_value = "しかし、これ以上持つことができない"

        with patch("game.play_se") as play_se:
            game._update_field(InputState(held_direction=Direction.RIGHT))
        treasure = game.field_actors.actor("gold_chest")
        self.assertEqual(game.pending_treasure_close_actor_id, "gold_chest")
        self.assertEqual(treasure.treasure_animation, (2,))

        for _frame in range(100):
            game.field_actors.update_treasure_animations()
        self.assertEqual(treasure.treasure_frame, 2)
        self.assertEqual(treasure.treasure_animation, ())

        game._finish_treasure_message()

        self.assertIsNone(game.treasure_message)
        self.assertIsNone(game.pending_treasure_close_actor_id)
        self.assertEqual(treasure.treasure_frame, 1)
        self.assertEqual(treasure.treasure_animation, (0,))
        self.assertEqual(game.save_data.gold, 999_980)
        self.assertEqual(game.save_data.opened_treasures, set())
        play_se.assert_not_called()

    def test_touch_trigger_precedes_movement(self) -> None:
        trigger = MapEventTrigger(
            "npc_touch",
            "sample.talk",
            frozenset(("touch",)),
            cells=(MapCell(2, 1),),
        )
        game = game_for(trigger)

        game._update_field(InputState(held_direction=Direction.RIGHT))

        self.assertEqual(game.field.position, FieldPosition(1, 1))
        game._start_field_event.assert_called_once_with(
            "sample.talk",
            release_direction=Direction.RIGHT,
            release_confirm=False,
        )

    def test_interact_trigger_uses_the_facing_cell(self) -> None:
        trigger = MapEventTrigger(
            "sign",
            "sample.sign",
            frozenset(("interact",)),
            cells=(MapCell(2, 1),),
        )
        game = game_for(trigger)

        game._update_field(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        game._start_field_event.assert_called_once_with(
            "sample.sign",
            release_direction=None,
            release_confirm=True,
        )

    def test_interact_reaches_actor_one_cell_beyond_enabled_object(self) -> None:
        actor = MapActor("shopkeeper", MapCell(3, 1), "stationary", 0, "up")
        trigger = MapEventTrigger(
            "shopkeeper_talk",
            "sample.shop",
            frozenset(("touch", "interact")),
            actor_id="shopkeeper",
            offsets=(MapCell(0, 0),),
        )
        without_enabled_object = game_for(
            trigger,
            actors=(actor,),
            width=4,
        )
        without_enabled_object._update_field(
            InputState(confirm=InputButton(triggered=True, held=True))
        )
        without_enabled_object._start_field_event.assert_not_called()

        game = game_for(
            trigger,
            actors=(actor,),
            width=4,
            interact_through_rows=("0000", "0010", "0000"),
        )

        game._update_field(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        game._start_field_event.assert_called_once_with(
            "sample.shop",
            release_direction=None,
            release_confirm=True,
        )
        self.assertIs(
            game.field_actors.actor("shopkeeper").movement.facing,
            Direction.LEFT,
        )

    def test_interacting_with_character_actor_turns_it_toward_the_party(self) -> None:
        actor = MapActor("elder", MapCell(2, 1), "stationary", 0, "up")
        trigger = MapEventTrigger(
            "elder_talk",
            "sample.talk",
            frozenset(("interact",)),
            actor_id="elder",
            offsets=(MapCell(0, 0),),
        )
        game = game_for(trigger, actors=(actor,))

        game._update_field(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertIs(
            game.field_actors.actor("elder").movement.facing,
            Direction.LEFT,
        )
        self.assertIs(game.field.facing, Direction.RIGHT)

    def test_stationary_actor_restores_its_facing_when_event_finishes(self) -> None:
        actor = MapActor("elder", MapCell(2, 1), "stationary", 0, "up")
        trigger = MapEventTrigger(
            "elder_talk",
            "sample.talk",
            frozenset(("interact",)),
            actor_id="elder",
            offsets=(MapCell(0, 0),),
        )
        game = game_for(trigger, actors=(actor,))

        game._update_field(
            InputState(confirm=InputButton(triggered=True, held=True))
        )
        self.assertIs(
            game.field_actors.actor("elder").movement.facing,
            Direction.LEFT,
        )

        game.event_runner = Mock(advance=Mock(return_value=None), is_complete=True)
        game.party_system = Mock(active_party=(object(),), character_states={})
        game.party = game.party_system.active_party
        game.selected_member_index = 0
        game._continue_event()

        self.assertIs(
            game.field_actors.actor("elder").movement.facing,
            Direction.UP,
        )
        self.assertIsNone(game.event_stationary_actor_facing_restore)

    def test_roaming_actor_keeps_its_facing_when_event_finishes(self) -> None:
        actor = MapActor("villager", MapCell(2, 1), "roaming", 0, "up")
        trigger = MapEventTrigger(
            "villager_talk",
            "sample.talk",
            frozenset(("interact",)),
            actor_id="villager",
            offsets=(MapCell(0, 0),),
        )
        game = game_for(trigger, actors=(actor,))

        game._update_field(
            InputState(confirm=InputButton(triggered=True, held=True))
        )
        game.event_runner = Mock(advance=Mock(return_value=None), is_complete=True)
        game.party_system = Mock(active_party=(object(),), character_states={})
        game.party = game.party_system.active_party
        game.selected_member_index = 0
        game._continue_event()

        self.assertIs(
            game.field_actors.actor("villager").movement.facing,
            Direction.LEFT,
        )
        self.assertIsNone(game.event_stationary_actor_facing_restore)

    def test_touching_character_actor_turns_both_characters_toward_each_other(
        self,
    ) -> None:
        actor = MapActor("elder", MapCell(2, 1), "stationary", 0, "up")
        trigger = MapEventTrigger(
            "elder_touch",
            "sample.talk",
            frozenset(("touch",)),
            actor_id="elder",
            offsets=(MapCell(0, 0),),
        )
        game = game_for(trigger, actors=(actor,))
        game.field.facing = Direction.UP

        game._update_field(InputState(held_direction=Direction.RIGHT))

        self.assertIs(game.field.facing, Direction.RIGHT)
        self.assertIs(
            game.field_actors.actor("elder").movement.facing,
            Direction.LEFT,
        )

    def test_step_trigger_runs_only_after_arriving(self) -> None:
        trigger = MapEventTrigger(
            "floor",
            "sample.floor",
            frozenset(("step",)),
            cells=(MapCell(2, 1),),
        )
        game = game_for(trigger)

        game._update_field(InputState(held_direction=Direction.RIGHT))

        self.assertEqual(game.field.position, FieldPosition(2, 1))
        game._start_field_event.assert_called_once_with(
            "sample.floor",
            release_direction=Direction.RIGHT,
            release_confirm=False,
        )
        game._handle_arrived_site.assert_not_called()

    def test_event_release_latch_requires_the_initiating_input_to_be_released(self) -> None:
        trigger = MapEventTrigger(
            "floor", "sample.floor", frozenset(("step",)), cells=(MapCell(2, 1),)
        )
        game = game_for(trigger)
        game.event_release_direction = Direction.RIGHT

        game._update_field(InputState(held_direction=Direction.RIGHT))
        self.assertEqual(game.field.position, FieldPosition(1, 1))

        game._update_field(InputState())
        self.assertIsNone(game.event_release_direction)

    def test_event_controlled_party_move_completes_one_step(self) -> None:
        trigger = MapEventTrigger(
            "floor", "sample.floor", frozenset(("step",)), cells=(MapCell(2, 1),)
        )
        game = game_for(trigger)
        runner = Mock()
        effect = MovePartyEffect(Direction.RIGHT, 1)
        game.event_runner = runner
        game.event_effect = effect
        game.event_move_remaining = 1
        game._continue_event = Mock()

        game._update_event(InputState())

        self.assertEqual(game.field.position, FieldPosition(2, 1))
        runner.complete_effect.assert_called_once_with(effect)
        self.assertIsNone(game.event_effect)
        game._continue_event.assert_called_once_with()

    def test_event_shop_effect_stages_the_requested_shop(self) -> None:
        game = Game.__new__(Game)
        selected_shop = Mock(key="FAIRY_HAMLET_ITEMS")
        effect = OpenShopEffect("FAIRY_HAMLET_ITEMS")
        game.event_runner = Mock(advance=Mock(return_value=effect))
        game.party_system = Mock(active_party=(), character_states={})
        game.shops = (selected_shop,)
        game._begin_screen_change = Mock()

        game._continue_event()

        self.assertIs(game.pending_shop, selected_shop)
        self.assertFalse(game.shop_return_to_debug)
        self.assertIs(game.event_effect, effect)
        game._begin_screen_change.assert_called_once_with(
            GameScreenChange.OPEN_SHOP
        )

    @patch("game.EventMessageOverlay")
    def test_event_message_log_is_added_newest_first_and_capped_at_twenty(
        self,
        _event_message_overlay: Mock,
    ) -> None:
        game = Game.__new__(Game)
        effect = MessageEffect("sample.new")
        game.event_runner = Mock(advance=Mock(return_value=effect))
        game.party_system = Mock(active_party=(), character_states={})
        game.settings = Settings()
        game.event_messages = Mock()
        game.fonts = Mock()
        game.faces = Mock()
        game.character_face_positions = {}
        old_logs = [
            {"message_id": f"sample.old{index}", "arguments": {}}
            for index in range(20)
        ]
        game.save_data = SaveData(logs=old_logs)

        game._continue_event()

        self.assertEqual(len(game.save_data.logs), 20)
        self.assertEqual(game.save_data.logs[0]["message_id"], "sample.new")
        self.assertEqual(game.save_data.logs[-1]["message_id"], "sample.old18")

    def test_closing_event_shop_defers_event_resume_until_fade_finishes(self) -> None:
        game = Game.__new__(Game)
        effect = OpenShopEffect("FAIRY_HAMLET_ITEMS")
        game.pending_screen_change = GameScreenChange.CLOSE_SHOP
        game.shop_return_to_debug = False
        game.debug_screen = None
        game.event_effect = effect
        game.event_runner = Mock()
        game.event_resume_after_fade = False
        game.showing_field = False
        game._finish_shop = Mock()

        game._apply_pending_screen_change()

        game.event_runner.complete_effect.assert_called_once_with(effect)
        self.assertIsNone(game.event_effect)
        self.assertTrue(game.event_resume_after_fade)
        self.assertTrue(game.showing_field)
        self.assertIsNone(game.pending_screen_change)

    def test_event_resumes_when_shop_close_fade_finishes(self) -> None:
        game = Game.__new__(Game)
        game.fade = FadeThroughBlack(1)
        game.fade.start()
        game.fade.update()
        game.palette_shifter = Mock(base_colors=((0, 0, 0),))
        game.fade_bgm = False
        game.event_resume_after_fade = True
        game._continue_event = Mock()

        self.assertTrue(game._update_fade())

        self.assertFalse(game.event_resume_after_fade)
        game._continue_event.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
