from __future__ import annotations

from types import MappingProxyType
import unittest
from unittest.mock import ANY, Mock, patch

from game import Game, GameScreenChange
from field import FieldActors, FieldMovement, FieldPosition
from input import Direction, InputButton, InputState
from resources import (
    CompiledMap,
    MapActor,
    MapCell,
    MapEventTrigger,
    MapTreasureContents,
)
from rendering import FadeThroughBlack
from state import SaveData, Settings
from systems import (
    InventorySystem,
    MessageEffect,
    MovePartyEffect,
    OpenShopEffect,
    TreasureSystem,
)


def compiled_map(
    trigger: MapEventTrigger | None,
    *,
    actors: tuple[MapActor, ...] = (),
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
        width=3,
        height=3,
        atlas=object(),
        atlas_columns=1,
        atlas_tile_count=1,
        ground_tiles=(0,) * 9,
        object_tiles=(),
        collision_rows=("000", "000", "000"),
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
    )


def game_for(
    trigger: MapEventTrigger,
    *,
    actors: tuple[MapActor, ...] = (),
) -> Game:
    game = Game.__new__(Game)
    game.current_map = compiled_map(trigger, actors=actors)
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

    def test_touching_character_actor_also_turns_it_toward_the_party(self) -> None:
        actor = MapActor("elder", MapCell(2, 1), "stationary", 0, "up")
        trigger = MapEventTrigger(
            "elder_touch",
            "sample.talk",
            frozenset(("touch",)),
            actor_id="elder",
            offsets=(MapCell(0, 0),),
        )
        game = game_for(trigger, actors=(actor,))

        game._update_field(InputState(held_direction=Direction.RIGHT))

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
