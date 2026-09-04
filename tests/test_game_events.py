from __future__ import annotations

from types import MappingProxyType
import unittest
from unittest.mock import Mock

from tools._bootstrap import APP_ROOT
from game import Game
from field import FieldMovement, FieldPosition
from input import Direction, InputButton, InputState
from resources import CompiledMap, MapCell, MapEventTrigger
from systems import MovePartyEffect


def compiled_map(trigger: MapEventTrigger) -> CompiledMap:
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
        event_triggers=(trigger,),
        event_trigger_index=MappingProxyType(
            {key: MappingProxyType(value) for key, value in static.items()}
        ),
    )


def game_for(trigger: MapEventTrigger) -> Game:
    game = Game.__new__(Game)
    game.current_map = compiled_map(trigger)
    game.field = FieldMovement(
        game.current_map,
        start=FieldPosition(1, 1),
        speed=16,
        facing=Direction.RIGHT,
    )
    game.field_actors = None
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


if __name__ == "__main__":
    unittest.main()
