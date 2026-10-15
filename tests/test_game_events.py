from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import ANY, Mock, call, patch

from tools._bootstrap import APP_ROOT as _APP_ROOT
from game import EVENT_ITEM_RECEIVED_TEXT_KEY, Game, GameScreenChange
from field import FieldActors, FieldMovement, FieldPosition
from input import Direction, InputButton, InputState
from resources.maps import MapVisibilityCondition
from resources import (
    CompiledMap,
    EventCatalog,
    MapActor,
    MapCell,
    MapEventTrigger,
    MapDestination,
    MapTreasureContents,
    WorldSite,
)
from rendering import FadeThroughBlack, ScreenBrightness
from rendering.field import FieldRenderer
from scenes.battle import BattleEncounter, BattlePhase, BattleResult
from state import SaveData, Settings
from systems import (
    StopBgmEffect,
    ChangeBrightnessEffect,
    ShakeScreenEffect,
    InventorySystem,
    EventContext,
    MessageEffect,
    ItemReceivedEffect,
    FlashScreenEffect,
    FaceActorEffect,
    FacePartyEffect,
    MoveActorEffect,
    MovePartyEffect,
    OpenShopEffect,
    StartBattleEffect,
    WaitEffect,
    TreasureSystem,
)


def compiled_map(
    trigger: MapEventTrigger | None,
    *,
    actors: tuple[MapActor, ...] = (),
    width: int = 5,
    height: int = 5,
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
        height=height,
        atlas=object(),
        atlas_columns=1,
        atlas_tile_count=1,
        ground_tiles=(0,) * (width * height),
        object_tiles=(),
        collision_rows=("0" * width,) * height,
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
    width: int = 5,
    height: int = 5,
    interact_through_rows: tuple[str, ...] = (),
) -> Game:
    game = Game.__new__(Game)
    game.save_data = SaveData()
    game.current_map = compiled_map(
        trigger,
        actors=actors,
        width=width,
        height=height,
        interact_through_rows=interact_through_rows,
    )
    game.field = FieldMovement(
        game.current_map,
        start=FieldPosition(1, 1),
        speed=16,
        facing=Direction.RIGHT,
        event_flags=game.save_data.event_flags,
    )
    game.field_actors = FieldActors(game.current_map, event_flags=game.save_data.event_flags) if actors else None
    game.event_release_direction = None
    game.event_release_confirm = False
    game.event_conversation_actor_id = None
    game._start_field_event = Mock(return_value=True)
    game._handle_arrived_site = Mock()
    game._refresh_site_name_label = Mock()
    game._begin_screen_change = Mock()
    return game


class GameEventTriggerTest(unittest.TestCase):
    def test_normal_pc_and_npc_movement_cannot_share_a_destination(self) -> None:
        for first_mover in ("party", "actor"):
            with self.subTest(first_mover=first_mover):
                game = game_for(None, actors=(
                    MapActor("walker", MapCell(2, 0), "roaming", 0, "down"),
                ), width=4, height=3)
                game.field = FieldMovement(game.current_map, start=FieldPosition(1, 1))
                game.field_actors._random = Mock(randint=Mock(return_value=30),
                                                 choice=Mock(return_value=Direction.DOWN))
                walker = game.field_actors.actor("walker")
                walker.roam_wait_frames = 0
                if first_mover == "actor":
                    game.field_actors.update("walker", Direction.DOWN, party_position=game.field.position)
                game._update_field(InputState(held_direction=Direction.RIGHT))
                winner, loser = ((game.field, walker.movement) if first_mover == "party"
                                 else (walker.movement, game.field))
                self.assertEqual(winner.destination_position, FieldPosition(2, 1))
                self.assertFalse(loser.is_moving)
                for _ in range(8):
                    game._update_field(InputState())
                self.assertEqual(winner.position, FieldPosition(2, 1))
                self.assertNotEqual(winner.position, loser.position)

    def test_hidden_actor_cannot_start_a_conversation_or_change_facing(self) -> None:
        actor = MapActor("elder", MapCell(2, 1), "stationary", 0, "up", visibility_condition=MapVisibilityCondition("story.visible", True))
        trigger = MapEventTrigger("talk", "sample.talk", frozenset(("touch", "interact")), actor_id="elder", offsets=(MapCell(0, 0),))
        game = game_for(trigger, actors=(actor,))
        for activation in ("touch", "interact"):
            self.assertFalse(game._try_field_trigger(activation, 2, 1))
        game._start_field_event.assert_not_called()
        self.assertIs(game.field_actors.actor("elder").movement.facing, Direction.UP)
        game.save_data.event_flags.add("story.visible")
        self.assertTrue(game._try_field_trigger("interact", 2, 1))
        game._start_field_event.assert_called_once()
        self.assertIs(game.field_actors.actor("elder").movement.facing, Direction.LEFT)

    def test_hidden_treasure_has_no_reward_or_opening_side_effects(self) -> None:
        actor = MapActor("chest", MapCell(2, 1), "treasure", 0, contents=MapTreasureContents("gold", amount=50), visibility_condition=MapVisibilityCondition("story.visible", True))
        game = game_for(None, actors=(actor,))
        game.treasure_system = Mock()
        self.assertFalse(game._try_open_treasure(2, 1))
        game.treasure_system.open.assert_not_called()
        self.assertEqual(game.save_data.gold, 0)
        self.assertEqual(game.save_data.opened_treasures, set())
        self.assertEqual(game.field_actors.actor("chest").treasure_frame, 0)

    def test_bgm_stop_waits_thirty_updates_in_field_and_battle_without_input_skip(self) -> None:
        from resources.audio import BgmPlayer
        from tests.test_audio_resources import FakePyxel

        for context in EventContext:
            with self.subTest(context=context), TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "da3-field.ogg").touch()
                px = FakePyxel()
                game = Game.__new__(Game)
                game.bgm = BgmPlayer(root, pyxel_api=px)
                game.bgm.play("da3-field")
                game.event_runner = Mock(context=context, advance=Mock(return_value=StopBgmEffect()))
                game.party_system = Mock(active_party=(), character_states={})
                game.input_reader = Mock(poll=Mock(return_value=InputState(confirm=InputButton(triggered=True, held=True))))
                game.alert = Mock()
                game.showing_field = context is EventContext.FIELD
                game.field = Mock()
                game.field_actors = Mock()
                game.battle_scene = Mock() if context is EventContext.BATTLE else None
                game._update_game_menu = Mock(return_value=False)
                game._update_fade = Mock(return_value=False)
                game._continue_event()
                effect = game.event_effect
                game._continue_event = Mock()
                for _ in range(29):
                    game.update()
                    game.event_runner.complete_effect.assert_not_called()
                    self.assertTrue(game.bgm.is_playing)
                game.update()
                self.assertFalse(game.bgm.is_playing)
                self.assertIsNone(game.event_effect)
                game.event_runner.complete_effect.assert_called_once_with(effect)
                game._continue_event.assert_called_once_with()
                game.field.update.assert_not_called()
                if context is EventContext.FIELD:
                    self.assertEqual(game.field_actors.update_roaming.call_count, 30)
                else:
                    game.field_actors.update_roaming.assert_not_called()
                if game.battle_scene is not None:
                    game.battle_scene.update.assert_not_called()

    def test_bgm_stop_while_silent_continues_without_an_extra_wait(self) -> None:
        game = Game.__new__(Game)
        effect = StopBgmEffect()
        game.event_runner = Mock(advance=Mock(side_effect=(effect, WaitEffect(6))))
        game.party_system = Mock(active_party=(), character_states={})
        game.bgm = Mock(fade_out_and_stop=Mock(return_value=False))
        game._continue_event()
        game.event_runner.complete_effect.assert_called_once_with(effect)
        self.assertEqual(game.event_effect, WaitEffect(6))
        self.assertEqual(game.event_wait_remaining, 6)

    def test_brightness_and_shake_wait_exact_frames_then_continue_in_order(self) -> None:
        game = Game.__new__(Game)
        effects = (ChangeBrightnessEffect(25), ShakeScreenEffect(18), WaitEffect(6))
        runner = Mock(advance=Mock(side_effect=(*effects, None)), context=EventContext.FIELD)
        game.event_runner = runner
        game.party_system = Mock(active_party=(object(),), character_states={})
        game.selected_member_index = 0
        game.screen_brightness = ScreenBrightness()
        game.palette_shifter = Mock()
        game._continue_event()
        self.assertEqual(game.screen_brightness.rate, 1.0)
        pressed = InputState(confirm=InputButton(triggered=True, held=True), cancel=InputButton(triggered=True, held=True))
        for frame in range(1, 30):
            game._update_event(pressed)
            game.event_runner.complete_effect.assert_not_called()
            self.assertAlmostEqual(game.screen_brightness.rate, 1 - 0.75 * frame / 30)
        game._update_event(pressed)
        self.assertIs(game.event_effect, effects[1])
        game.palette_shifter.set_brightness.assert_called_with(0.25)
        for _ in range(17):
            game._update_event(pressed)
            self.assertIs(game.event_effect, effects[1])
        game._update_event(pressed)
        self.assertIs(game.event_effect, effects[2])
        self.assertIsNone(game.event_screen_shake)
        self.assertEqual(game.screen_brightness.rate, 0.25)
        self.assertEqual(game.event_runner.complete_effect.call_args_list, [call(effects[0]), call(effects[1])])
        for _ in range(6):
            game._update_event(pressed)
        self.assertIsNone(game.event_runner)
        self.assertEqual(game.screen_brightness.rate, 0.25)
        runner.complete_effect.assert_called_with(effects[2])

    @patch("game.pyxel")
    def test_shake_draw_applies_only_horizontal_camera_and_always_restores_it(self, px: Mock) -> None:
        game = Game.__new__(Game)
        game.event_runner = Mock(advance=Mock(return_value=ShakeScreenEffect(18)))
        game.party_system = Mock(active_party=(), character_states={})
        game.alert = Mock(camera_x=0)
        game.showing_field = True
        game._draw_field_screen = Mock()
        game._continue_event()
        game._update_event(InputState())
        game.draw()
        self.assertEqual(px.camera.call_args_list, [call(1, 0), call()])
        self.assertEqual(game.event_screen_shake.elapsed_frames, 1)
        px.camera.reset_mock()
        game._draw_field_screen.side_effect = RuntimeError("draw failed")
        with self.assertRaises(RuntimeError):
            game.draw()
        px.camera.assert_called_with()

    def test_aborted_screen_effect_restores_shake_and_stops_brightness(self) -> None:
        game = Game.__new__(Game)
        game.screen_brightness = ScreenBrightness()
        game.screen_brightness.start(25)
        game.screen_brightness.update()
        current = game.screen_brightness.rate
        game.event_screen_shake = Mock()
        game.alert = Mock()
        game._abort_event(ValueError("preview"))
        self.assertIsNone(game.event_screen_shake)
        self.assertFalse(game.screen_brightness.is_active)
        self.assertEqual(game.screen_brightness.rate, current)

    @patch("game.MessageOverlay")
    def test_item_received_message_formats_name_only_and_waits_until_closed(self, overlay: Mock) -> None:
        game = Game.__new__(Game)
        effect = ItemReceivedEffect("POTION")
        game.event_runner = Mock(advance=Mock(return_value=effect))
        game.party_system = Mock(active_party=(), character_states={})
        game.settings = Settings()
        game.fonts = Mock()
        game.items = {"POTION": Mock(localized_name=Mock(return_value="ポーション"))}
        game.texts = Mock(formatted_text=Mock(return_value="ポーションを　手に入れた！"))
        game.save_data = SaveData()

        game._continue_event()

        game.texts.formatted_text.assert_called_once_with(EVENT_ITEM_RECEIVED_TEXT_KEY, ANY, {"ITEM": "ポーション"})
        overlay.assert_called_once_with(lines=("ポーションを　手に入れた！",), settings=game.settings, fonts=game.fonts)
        self.assertIs(game.event_message, overlay.return_value)
        self.assertEqual(game.save_data.logs, [])
        game._continue_event = Mock()
        overlay.return_value.update.return_value = False
        game._update_event(InputState())
        game.event_runner.complete_effect.assert_not_called()
        game._continue_event.assert_not_called()
        overlay.return_value.update.return_value = True
        game._update_event(InputState(confirm=InputButton(triggered=True, held=True)))
        game.event_runner.complete_effect.assert_called_once_with(effect)
        self.assertIsNone(game.event_effect)
        self.assertIsNone(game.event_message)
        game._continue_event.assert_called_once_with()

    def test_wait_resumes_exactly_on_its_final_frame_without_input_skip(self) -> None:
        for frames in (6, 12, 18):
            with self.subTest(frames=frames):
                game = Game.__new__(Game)
                effect = WaitEffect(frames)
                game.event_runner = Mock(advance=Mock(return_value=effect))
                game.party_system = Mock(active_party=(), character_states={})
                game._continue_event()
                self.assertEqual(game.event_wait_remaining, frames)
                game._continue_event = Mock()
                input_state = InputState(
                    confirm=InputButton(triggered=True, held=True),
                    cancel=InputButton(triggered=True, held=True),
                    held_direction=Direction.RIGHT,
                )
                for remaining in range(frames - 1, 0, -1):
                    game._update_event(input_state)
                    self.assertEqual(game.event_wait_remaining, remaining)
                    game.event_runner.complete_effect.assert_not_called()
                    game._continue_event.assert_not_called()
                game._update_event(input_state)
                self.assertEqual(game.event_wait_remaining, 0)
                self.assertIsNone(game.event_effect)
                game.event_runner.complete_effect.assert_called_once_with(effect)
                game._continue_event.assert_called_once_with()

    def test_consecutive_waits_have_no_extra_frame_between_them(self) -> None:
        game = Game.__new__(Game)
        effects = (WaitEffect(6), WaitEffect(12), MovePartyEffect(Direction.DOWN, 1))
        game.event_runner = Mock(advance=Mock(side_effect=effects))
        game.party_system = Mock(active_party=(), character_states={})
        game._continue_event()
        for _ in range(6):
            game._update_event(InputState())
        self.assertIs(game.event_effect, effects[1])
        self.assertEqual(game.event_wait_remaining, 12)
        for _ in range(12):
            game._update_event(InputState())
        self.assertIs(game.event_effect, effects[2])
        self.assertEqual(game.event_wait_remaining, 0)
        self.assertEqual(game.event_runner.complete_effect.call_args_list, [call(effects[0]), call(effects[1])])

    def test_active_event_ignores_actor_trigger_without_stopping_controlled_movement(self) -> None:
        trigger = MapEventTrigger(
            "elder", "sample.meeting", frozenset(("touch", "interact")),
            actor_id="elder", offsets=(MapCell(0, 0),),
        )
        game = game_for(trigger, actors=(MapActor("elder", MapCell(2, 2), "stationary", 0, "up"),))
        game.event_runner = Mock()
        game.field_actors.update("elder", Direction.UP, party_position=game.field.position)
        movement = game.field_actors.actor("elder").movement
        for activation in ("touch", "interact"):
            self.assertFalse(game._try_field_trigger(activation, 2, 2))
        self.assertTrue(movement.is_moving)
        self.assertEqual(movement.offset_y, -2)
        self.assertIs(movement.facing, Direction.UP)
        game._start_field_event.assert_not_called()

    def test_active_event_ignores_party_arrival_on_an_exit(self) -> None:
        game = game_for(MapEventTrigger("floor", "sample.floor", frozenset(("step",)), cells=(MapCell(2, 1),)))
        game.field.update(Direction.RIGHT)
        game.event_runner = Mock()
        game.current_sites = Mock()
        game._stage_map_destination = Mock(return_value=True)

        Game._handle_arrived_site(game)

        game.current_sites.entrance_at.assert_not_called()
        game._stage_map_destination.assert_not_called()
        game._begin_screen_change.assert_not_called()

    def test_actor_moves_thirteen_steps_across_an_exit_and_event_cell(self) -> None:
        trigger = MapEventTrigger(
            "flowers", "sample.flowers", frozenset(("step",)),
            cells=(MapCell(17, 23),),
        )
        game = game_for(trigger, width=20, height=40, actors=(
            MapActor("alvan", MapCell(17, 35), "stationary", 2, "up"),
        ))
        object.__setattr__(game.current_map, "sites", (
            WorldSite("exit", "location.exit", (MapCell(17, 26),), MapDestination("next_map", "entrance")),
        ))
        game.field = FieldMovement(game.current_map, start=FieldPosition(17, 20))
        runner = Mock()
        effect = MoveActorEffect("alvan", Direction.UP, 13)
        game.event_runner = runner
        game.event_effect = effect
        game.event_move_remaining = 13
        game._continue_event = Mock()
        game.input_reader = Mock(poll=Mock(return_value=InputState()))
        game.alert = Mock()
        game.showing_field = True
        game._update_game_menu = Mock(return_value=False)
        game._update_field_menu_guide = Mock()
        game._update_battle_scene = Mock(return_value=False)
        game._update_fade = Mock(return_value=False)
        game._update_field_fade_pulse = Mock()
        game._try_field_trigger = Mock(return_value=False)
        game._advance_random_encounter = Mock()

        for _ in range(13 * 8):
            game.update()

        self.assertEqual(game.field_actors.actor("alvan").movement.position, FieldPosition(17, 22))
        self.assertEqual(game.event_move_remaining, 0)
        self.assertFalse(game.field_actors.actor("alvan").movement.is_moving)
        runner.complete_effect.assert_called_once_with(effect)
        game._continue_event.assert_called_once_with()
        game._handle_arrived_site.assert_not_called()
        game._try_field_trigger.assert_not_called()
        game._advance_random_encounter.assert_not_called()
        game.alert.start.assert_not_called()

    def test_facing_commands_apply_in_one_frame_and_keep_explicit_actor_facing(self) -> None:
        trigger = MapEventTrigger("meeting", "sample.meeting", frozenset(("interact",)), cells=(MapCell(2, 1),))
        game = game_for(trigger, actors=(MapActor("elder", MapCell(2, 1), "stationary", 0, "up"),))
        party_effect = FacePartyEffect(Direction.DOWN)
        actor_effect = FaceActorEffect("elder", Direction.LEFT)
        runner = Mock(advance=Mock(side_effect=[party_effect, actor_effect, None]), is_complete=True)
        game.event_runner = runner
        game.party_system = Mock(active_party=(object(),), character_states={})
        game.selected_member_index = 0
        game.event_stationary_actor_facing_restore = ("elder", Direction.UP)

        game._continue_event()

        self.assertIs(game.field.facing, Direction.DOWN)
        self.assertEqual(game.field.position, FieldPosition(1, 1))
        self.assertIs(game.field_actors.actor("elder").movement.facing, Direction.LEFT)
        self.assertEqual(game.field_actors.actor("elder").movement.position, FieldPosition(2, 1))
        self.assertIsNone(game.event_stationary_actor_facing_restore)
        self.assertIsNone(game.event_runner)
        self.assertEqual(runner.complete_effect.call_args_list, [
            call(party_effect), call(actor_effect),
        ])

    def test_hidden_object_trigger_stops_firing_when_its_flag_changes(self) -> None:
        trigger = MapEventTrigger(
            "rock_touch", "sample.rock", frozenset(("touch",)),
            cells=(MapCell(2, 1),), object_id="rock",
        )
        game = game_for(trigger)
        object.__setattr__(game.current_map, "object_conditions", MappingProxyType({
            "rock": MapVisibilityCondition("story.open", False),
        }))
        self.assertTrue(game._try_field_trigger("touch", 2, 1))
        game._start_field_event.reset_mock()
        game.save_data.event_flags.add("story.open")
        self.assertFalse(game._try_field_trigger("touch", 2, 1))
        game._start_field_event.assert_not_called()

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
        game = game_for(trigger, width=5)
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
        game.event_conversation_actor_id = "villager"
        game.suspended_field_event = None
        game._begin_random_encounter = Mock()
        game._continue_event = Mock()

        game._begin_event_battle(effect)

        self.assertEqual(game.pending_event_battle_id, "shrine_guard")
        self.assertEqual(game.pending_event_battle_encounter.monster_keys, ("SLIME",))
        self.assertFalse(game.pending_event_battle_encounter.escape_command_enabled)
        self.assertIsNone(game.event_runner)
        self.assertIsNone(game.event_effect)
        self.assertEqual(game.event_conversation_actor_id, "villager")
        game._begin_random_encounter.assert_called_once_with()

        game._resume_event_after_battle(BattleResult.VICTORY)

        runner.complete_effect.assert_called_once_with(effect)
        self.assertIs(game.event_runner, runner)
        self.assertEqual(game.event_conversation_actor_id, "villager")
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
        game.texts.formatted_lines.return_value = ("宝箱から", "５０Ｇを　手に入れた！")
        game.field.facing = Direction.LEFT

        with patch("game.play_se") as play_se:
            game._update_field(InputState(held_direction=Direction.RIGHT))

        self.assertEqual(game.field.position, FieldPosition(1, 1))
        self.assertIs(game.field.facing, Direction.RIGHT)
        self.assertEqual(game.save_data.gold, 60)
        self.assertIn(("test_map", "gold_chest"), game.save_data.opened_treasures)
        self.assertEqual(game.field_actors.actor("gold_chest").treasure_frame, 1)
        message_overlay.assert_called_once_with(
            lines=("宝箱から", "５０Ｇを　手に入れた！"),
            settings=game.settings,
            fonts=game.fonts,
        )
        game.texts.formatted_lines.assert_called_once_with(
            "treasure.received_gold",
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
        game.texts.formatted_lines.return_value = ("宝箱には　５０Ｇが入っていた！",)
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

    def test_blocked_cell_touch_turns_party_before_starting_event(self) -> None:
        for direction in Direction:
            with self.subTest(direction=direction):
                target = MapCell(1 + direction.dx, 1 + direction.dy)
                trigger = MapEventTrigger(
                    "blocked_touch", "sample.talk", frozenset(("touch",)),
                    cells=(target,),
                )
                game = game_for(trigger)
                rows = [list(row) for row in game.current_map.collision_rows]
                rows[target.y][target.x] = "1"
                game.current_map = replace(
                    game.current_map, collision_rows=tuple("".join(row) for row in rows),
                )
                game.field = FieldMovement(
                    game.current_map, start=FieldPosition(1, 1),
                    facing=Direction.DOWN if direction is not Direction.DOWN else Direction.UP,
                )

                def start_event(*args, **kwargs):
                    self.assertIs(game.field.facing, direction)
                    self.assertEqual(game.field.position, FieldPosition(1, 1))
                    self.assertFalse(game.field.is_moving)
                    return True

                game._start_field_event.side_effect = start_event
                game._update_field(InputState(held_direction=direction))

                self.assertIs(game.field.facing, direction)
                self.assertEqual(game.field.position, FieldPosition(1, 1))
                self.assertFalse(game.field.is_walking)
                game._start_field_event.assert_called_once_with(
                    "sample.talk", release_direction=direction, release_confirm=False,
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

    @patch("game.EventMessageOverlay")
    def test_repeated_message_moves_to_front_without_evicting_other_logs(
        self, _event_message_overlay: Mock,
    ) -> None:
        game = Game.__new__(Game)
        effect = MessageEffect("sample.old5")
        game.event_runner = Mock(advance=Mock(return_value=effect))
        game.party_system = Mock(active_party=(), character_states={})
        game.settings = Settings()
        game.event_messages = Mock()
        game.fonts = Mock()
        game.faces = Mock()
        game.character_face_positions = {}
        logs = [
            {"message_id": f"sample.old{index}", "arguments": {}}
            for index in range(20)
        ]
        game.save_data = SaveData(logs=list(logs))
        game._continue_event()
        self.assertEqual(game.save_data.logs, [logs[5]] + logs[:5] + logs[6:])
        game._continue_event()
        self.assertEqual(len(game.save_data.logs), 20)
        self.assertEqual(game.save_data.logs[-1], logs[-1])

        # Remove all old duplicates, while preserving different arguments.
        game.save_data.logs = [logs[5], logs[0], logs[5], {
            "message_id": "sample.old5", "arguments": {"VALUE": 1},
        }]
        game._continue_event()
        self.assertEqual(game.save_data.logs, [logs[5], logs[0], {
            "message_id": "sample.old5", "arguments": {"VALUE": 1},
        }])

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


class GameEventAnimationTest(unittest.TestCase):
    def game(self) -> Game:
        game = game_for(None, width=6, height=6, actors=(
            MapActor("hover", MapCell(1, 1), "stationary", 0, "down", floating=True),
            MapActor("walker", MapCell(0, 3), "roaming", 1, "right"),
            MapActor("hidden", MapCell(3, 3), "roaming", 2, "right",
                     visibility_condition=MapVisibilityCondition("visible", True)),
        ))
        # Start with completed PC/NPC steps and another NPC mid-step.
        game.field.update(Direction.RIGHT)
        hover = game.field_actors.actor("hover").movement
        for _ in range(8):
            hover.update(Direction.DOWN)
        for actor_id in ("walker", "hidden"):
            game.field_actors.actor(actor_id).movement.update(Direction.RIGHT)
        game.field_actors._random = Mock(
            randint=Mock(return_value=30), choice=Mock(return_value=Direction.RIGHT),
        )
        game.input_reader = Mock(poll=Mock(return_value=InputState(
            held_direction=Direction.RIGHT, menu=InputButton(triggered=True),
        )))
        game.alert = Mock()
        game.showing_field = True
        game._update_game_menu = Mock(return_value=False)
        game._update_field_menu_guide = Mock()
        game._update_field_fade_pulse = Mock()
        game._update_battle_scene = Mock(return_value=False)
        game._update_fade = Mock(return_value=False)
        game._update_field = Mock()
        game.event_runner = Mock(context=EventContext.FIELD)
        game._continue_event = Mock()
        return game

    def test_message_and_wait_continue_npc_movement_without_field_input_or_new_events(self) -> None:
        for effect in (MessageEffect("sample.talk"), WaitEffect(180)):
            with self.subTest(effect=effect):
                game = self.game()
                game.event_effect = effect
                game.event_wait_remaining = 180
                game.event_message = Mock(update=Mock(return_value=False))
                walker = game.field_actors.actor("walker")
                hidden = game.field_actors.actor("hidden")
                walker_position = (walker.movement.world_x, walker.movement.world_y)
                hidden_position = (hidden.movement.world_x, hidden.movement.world_y)
                hidden_wait = hidden.roam_wait_frames
                walking_image = Mock(width=384, height=384)
                actor_image = Mock(width=192, height=128)
                px = Mock(frame_count=0)
                renderer = FieldRenderer(game.current_map, screen_width=80,
                                         screen_height=80, pyxel_api=px)
                frames = {"player": set(), "hover": set(), "walker": set()}
                for frame in range(80):
                    game.update()
                    px.blt.reset_mock()
                    renderer.draw(game.field, actors=game.field_actors,
                                  player_character_image=walking_image, player_floating=True,
                                  actor_character_image=actor_image, frame_count=frame)
                    for draw in px.blt.call_args_list:
                        if draw.args[2] is walking_image:
                            frames["player"].add(draw.args[3])
                        elif draw.args[2] is actor_image:
                            kind = "hover" if draw.args[3] < 48 else "walker"
                            frames[kind].add(draw.args[3])
                self.assertEqual(frames["player"], {0, 16, 32})
                self.assertEqual(frames["hover"], {0, 16, 32})
                self.assertGreaterEqual(len(frames["walker"]), 2)
                self.assertTrue(frames["walker"].issubset({48, 64, 80}))
                self.assertEqual(game.field.position, FieldPosition(2, 1))
                self.assertFalse(game.field.is_walking)
                self.assertIsNone(game.field.arrived_position)
                self.assertEqual(game.field_actors.actor("hover").movement.position,
                                 FieldPosition(1, 2))
                self.assertFalse(game.field_actors.actor("hover").movement.is_walking)
                self.assertNotEqual((walker.movement.world_x, walker.movement.world_y), walker_position)
                self.assertIs(walker.movement.facing, Direction.RIGHT)
                game.field_actors._random.choice.assert_called()
                self.assertEqual((hidden.movement.world_x, hidden.movement.world_y), hidden_position)
                self.assertEqual(hidden.roam_wait_frames, hidden_wait)
                self.assertEqual(hidden.movement.walking_frame_count, 1)
                game._update_field.assert_not_called()
                game._start_field_event.assert_not_called()
                game._handle_arrived_site.assert_not_called()
                game.event_runner.complete_effect.assert_not_called()
                if isinstance(effect, WaitEffect):
                    self.assertEqual(game.event_wait_remaining, 100)
                else:
                    self.assertEqual(game.event_message.update.call_count, 80)

    def test_roaming_wait_expires_and_starts_a_new_step_during_a_message(self) -> None:
        game = self.game()
        game.event_effect = MessageEffect("sample.talk")
        game.event_message = Mock(update=Mock(return_value=False))
        walker = game.field_actors.actor("walker")
        walker.movement.stop()
        walker.roam_wait_frames = 2
        game.update()
        self.assertEqual(walker.roam_wait_frames, 1)
        game.update()
        self.assertEqual(walker.roam_wait_frames, 0)
        self.assertFalse(walker.movement.is_moving)
        game.update()
        self.assertTrue(walker.movement.is_moving)
        self.assertEqual(walker.movement.world_x, walker.movement.speed)
        game.event_runner.complete_effect.assert_not_called()

    def test_only_the_conversation_partner_pauses_until_the_event_finishes(self) -> None:
        for activation in ("touch", "interact"):
            for effect in (MessageEffect("sample.talk"), WaitEffect(180)):
                with self.subTest(activation=activation, effect=effect):
                    game = self.game()
                    trigger = MapEventTrigger("talk", "sample.talk", frozenset((activation,)),
                                              actor_id="walker", offsets=(MapCell(0, 0),))
                    game.current_map = replace(game.current_map,
                        actors=(*game.current_map.actors,
                                MapActor("bystander", MapCell(4, 4), "roaming", 3, "left")),
                        actor_event_triggers=MappingProxyType({"walker": (trigger,)}))
                    game.field_actors = FieldActors(game.current_map, random_source=Mock(
                        randint=Mock(return_value=30), choice=Mock(return_value=Direction.LEFT),
                    ))
                    game.field = FieldMovement(game.current_map, start=FieldPosition(1, 3))
                    game.event_runner = None
                    self.assertTrue(game._try_field_trigger(activation, 0, 3))
                    self.assertEqual(game.event_conversation_actor_id, "walker")
                    game.event_runner = Mock(context=EventContext.FIELD)
                    game.event_effect = effect
                    game.event_wait_remaining = 180
                    game.event_message = Mock(update=Mock(return_value=False))
                    walker = game.field_actors.actor("walker")
                    bystander = game.field_actors.actor("bystander")
                    walker.roam_wait_frames = 0
                    bystander.roam_wait_frames = 0
                    for _ in range(10):
                        game.update()
                    self.assertEqual(walker.movement.position, FieldPosition(0, 3))
                    self.assertIs(walker.movement.facing, Direction.RIGHT)
                    self.assertFalse(walker.movement.is_moving)
                    self.assertEqual(walker.roam_wait_frames, 0)
                    self.assertEqual(bystander.movement.position, FieldPosition(3, 4))
                    game.event_runner.complete_effect.assert_not_called()
                    game.event_runner = Mock(context=EventContext.FIELD,
                                             advance=Mock(return_value=None), is_complete=True)
                    game.party_system = Mock(active_party=(), character_states={})
                    game.selected_member_index = 0
                    Game._continue_event(game)
                    self.assertIsNone(game.event_conversation_actor_id)
                    game.event_runner = Mock(context=EventContext.FIELD)
                    game.event_effect = WaitEffect(180)
                    game.event_wait_remaining = 180
                    walker.roam_wait_frames = 0
                    game.field_actors._random.choice.return_value = Direction.RIGHT
                    game.field = FieldMovement(game.current_map, start=FieldPosition(2, 2))
                    game.update()
                    self.assertTrue(walker.movement.is_moving)

    def test_aborting_an_event_releases_the_conversation_partner(self) -> None:
        game = self.game()
        game.event_conversation_actor_id = "walker"
        game._abort_event(ValueError("preview conversation"))
        self.assertIsNone(game.event_conversation_actor_id)

    def test_conversation_partner_keeps_its_roaming_wait_time(self) -> None:
        game = self.game()
        game.event_conversation_actor_id = "walker"
        game.event_effect = MessageEffect("sample.talk")
        game.event_message = Mock(update=Mock(return_value=False))
        walker = game.field_actors.actor("walker")
        walker.movement.stop()
        walker.roam_wait_frames = 40
        for _ in range(5):
            game.update()
        self.assertEqual(walker.roam_wait_frames, 40)
        self.assertIs(walker.movement.facing, Direction.RIGHT)

    def test_roaming_npc_does_not_enter_the_partys_controlled_destination(self) -> None:
        game = self.game()
        game.current_map = replace(game.current_map, actors=(
            MapActor("walker", MapCell(3, 2), "roaming", 1, "left"),
        ))
        game.field = FieldMovement(game.current_map, start=FieldPosition(2, 1))
        game.field.update(Direction.DOWN)
        game.field_actors = FieldActors(game.current_map, random_source=Mock(
            randint=Mock(return_value=30), choice=Mock(return_value=Direction.LEFT),
        ))
        walker = game.field_actors.actor("walker")
        walker.roam_wait_frames = 0
        game.event_effect = MovePartyEffect(Direction.DOWN, 1)
        game.event_move_remaining = 1
        game.update()
        self.assertEqual(walker.movement.position, FieldPosition(3, 2))
        self.assertFalse(walker.movement.is_moving)
        self.assertGreater(game.field.world_y, 16)

    def test_controlled_party_moves_cannot_enter_hidden_border(self) -> None:
        game = self.game()
        game.field = FieldMovement(game.current_map, start=FieldPosition(2, 1))
        walker = game.field_actors.actor("walker").movement
        walker.position = FieldPosition(3, 1)
        walker.stop()
        game.event_effect = MovePartyEffect(Direction.UP, 1)
        game.event_move_remaining = 1
        game._abort_event = Mock()

        game.update()

        game._abort_event.assert_called_once()
        self.assertIn("controlled movement is blocked", str(game._abort_event.call_args.args[0]))
        self.assertEqual(game.field.position, FieldPosition(2, 1))
        self.assertEqual(walker.position, FieldPosition(3, 1))
        self.assertFalse(game.field.is_moving)
        self.assertFalse(walker.is_moving)

    def test_controlled_actor_enters_from_below_map_and_completes_all_five_steps(self) -> None:
        game = self.game()
        game.current_map = compiled_map(None, width=36, height=28, actors=(
            MapActor("walker", MapCell(17, 28), "stationary", 0, "up"),
        ))
        game.field = FieldMovement(game.current_map, start=FieldPosition(17, 20))
        game.field_actors = FieldActors(game.current_map)
        effect = MoveActorEffect("walker", Direction.UP, 5)
        game.event_effect = effect
        game.event_move_remaining = 5
        game._abort_event = Mock()

        for _ in range(40):
            game.update()

        game._abort_event.assert_not_called()
        walker = game.field_actors.actor("walker").movement
        self.assertEqual(walker.position, FieldPosition(17, 23))
        self.assertFalse(walker.is_moving)
        game.event_runner.complete_effect.assert_called_once_with(effect)
        game._continue_event.assert_called_once_with()

    def test_controlled_actor_still_stops_at_blocked_border_or_outside_destination(self) -> None:
        for position in (FieldPosition(3, 1), FieldPosition(3, 0)):
            with self.subTest(position=position):
                game = self.game()
                game.current_map = replace(game.current_map, collision_rows=("000100",) + ("000000",) * 5)
                game.field = FieldMovement(game.current_map, start=FieldPosition(2, 1))
                game.field_actors = FieldActors(game.current_map)
                walker = game.field_actors.actor("walker").movement
                walker.position = position
                walker.stop()
                game.event_effect = MoveActorEffect("walker", Direction.UP, 1)
                game.event_move_remaining = 1
                game._abort_event = Mock()

                game.update()

                game._abort_event.assert_called_once()
                self.assertIn("controlled movement is blocked", str(game._abort_event.call_args.args[0]))
                self.assertEqual(walker.position, position)
                self.assertFalse(walker.is_moving)

    def test_controlled_moves_cannot_enter_another_characters_destination(self) -> None:
        for first_mover in ("party", "actor"):
            with self.subTest(first_mover=first_mover):
                game = self.game()
                game.current_map = replace(game.current_map, actors=(
                    MapActor("walker", MapCell(2, 0), "roaming", 1, "down"),
                ))
                game.field = FieldMovement(game.current_map, start=FieldPosition(1, 1))
                game.field_actors = FieldActors(game.current_map)
                walker = game.field_actors.actor("walker")
                if first_mover == "party":
                    game.field.update(Direction.RIGHT)
                    game.event_effect = MoveActorEffect("walker", Direction.DOWN, 1)
                    candidate = walker.movement
                else:
                    game.field_actors.update("walker", Direction.DOWN, party_position=game.field.position)
                    game.event_effect = MovePartyEffect(Direction.RIGHT, 1)
                    candidate = game.field
                game.event_move_remaining = 1
                game._abort_event = Mock()
                game.update()
                self.assertFalse(candidate.is_moving)
                game._abort_event.assert_called_once()
                self.assertIn("controlled movement is blocked", str(game._abort_event.call_args.args[0]))

    def test_controlled_movement_advances_animation_only_once_per_frame(self) -> None:
        for effect in (MovePartyEffect(Direction.DOWN, 1), MoveActorEffect("walker", Direction.RIGHT, 1)):
            with self.subTest(effect=effect):
                game = self.game()
                game.field = FieldMovement(game.current_map, start=FieldPosition(2, 1))
                game.event_effect = effect
                game.event_move_remaining = 1
                if isinstance(effect, MoveActorEffect):
                    game.event_conversation_actor_id = "walker"
                movement = (game.field if isinstance(effect, MovePartyEffect)
                            else game.field_actors.actor("walker").movement)
                walker = game.field_actors.actor("walker")
                walker_wait = walker.roam_wait_frames
                initial_frame = movement.walking_frame_count
                initial_position = (movement.world_x, movement.world_y)
                for frame in range(1, 5):
                    game.update()
                    self.assertEqual(movement.walking_frame_count, initial_frame + frame)
                    self.assertEqual((movement.world_x, movement.world_y), (
                        initial_position[0] + effect.direction.dx * movement.speed * frame,
                        initial_position[1] + effect.direction.dy * movement.speed * frame,
                    ))
                    if isinstance(effect, MoveActorEffect):
                        self.assertEqual(walker.roam_wait_frames, walker_wait)
                if isinstance(effect, MovePartyEffect):
                    self.assertGreater(walker.movement.world_x, walker.movement.speed)
                game.event_runner.complete_effect.assert_not_called()

    def test_conversation_partner_stays_paused_while_another_actor_is_controlled(self) -> None:
        game = self.game()
        game.current_map = replace(game.current_map, actors=(
            MapActor("walker", MapCell(0, 3), "roaming", 1, "right"),
            MapActor("bystander", MapCell(4, 3), "roaming", 2, "up"),
        ))
        game.field_actors = FieldActors(game.current_map, random_source=Mock(
            randint=Mock(return_value=30), choice=Mock(return_value=Direction.LEFT),
        ))
        game.event_conversation_actor_id = "walker"
        game.event_effect = MoveActorEffect("bystander", Direction.UP, 1)
        game.event_move_remaining = 1
        walker = game.field_actors.actor("walker")
        bystander = game.field_actors.actor("bystander")
        walker.roam_wait_frames = bystander.roam_wait_frames = 0
        for _ in range(4):
            game.update()
        self.assertFalse(walker.movement.is_moving)
        self.assertEqual(walker.movement.position, FieldPosition(0, 3))
        self.assertEqual(bystander.movement.walking_frame_count, 4)
        self.assertEqual(bystander.movement.world_y, 3 * 16 - 4 * bystander.movement.speed)

    def test_controlled_actor_resumes_roaming_while_other_npcs_keep_moving(self) -> None:
        game = self.game()
        game.current_map = replace(game.current_map, actors=(
            MapActor("walker", MapCell(0, 3), "roaming", 1, "right"),
            MapActor("bystander", MapCell(4, 3), "roaming", 2, "left"),
        ))
        game.field_actors = FieldActors(game.current_map, random_source=Mock(
            randint=Mock(return_value=30), choice=Mock(return_value=Direction.LEFT),
        ))
        walker = game.field_actors.actor("walker")
        bystander = game.field_actors.actor("bystander")
        walker.roam_wait_frames = bystander.roam_wait_frames = 0
        effect = MoveActorEffect("walker", Direction.RIGHT, 1)
        game.event_effect = effect
        game.event_move_remaining = 1
        for _ in range(8):
            game.update()
        self.assertEqual(walker.movement.position, FieldPosition(1, 3))
        self.assertEqual(bystander.movement.position, FieldPosition(3, 3))
        self.assertEqual(walker.roam_wait_frames, 0)
        game.event_runner.complete_effect.assert_called_once_with(effect)
        game.event_effect = WaitEffect(180)
        game.event_wait_remaining = 180
        game.field_actors._random.choice.return_value = Direction.RIGHT
        game.update()
        self.assertIs(walker.movement.facing, Direction.RIGHT)
        self.assertEqual(walker.movement.world_x, 16 + walker.movement.speed)


if __name__ == "__main__":
    unittest.main()
