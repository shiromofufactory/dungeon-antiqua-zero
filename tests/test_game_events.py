from __future__ import annotations

from types import MappingProxyType
import unittest
from unittest.mock import Mock

from tools._bootstrap import APP_ROOT
from game import Game, GameScreenChange
from field import FieldActors, FieldMovement, FieldPosition
from input import Direction, InputButton, InputState
from resources import CompiledMap, MapActor, MapCell, MapEventTrigger
from rendering import FadeThroughBlack
from systems import MovePartyEffect, OpenShopEffect


def compiled_map(
    trigger: MapEventTrigger,
    *,
    actors: tuple[MapActor, ...] = (),
) -> CompiledMap:
    static = {activation: {} for activation in ("step", "touch", "interact")}
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
        event_triggers=(trigger,),
        event_trigger_index=MappingProxyType(
            {key: MappingProxyType(value) for key, value in static.items()}
        ),
        actor_event_triggers=MappingProxyType(
            {} if trigger.actor_id is None else {trigger.actor_id: (trigger,)}
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
