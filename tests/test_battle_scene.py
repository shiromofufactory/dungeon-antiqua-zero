from __future__ import annotations

import unittest
from inspect import signature
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT

from field import FieldPosition
from game import (
    ENCOUNTER_JINGLE_ID,
    RANDOM_BATTLE_ENCOUNTER,
    Game,
)
from input import Direction, InputButton, InputState
from rendering import (
    DEFAULT_FADE_FRAME_COUNT,
    ENCOUNTER_TRANSITION_FRAME_COUNT,
    EncounterTransition,
    FadePhase,
    FadeThroughBlack,
)
from scenes import BattleEncounter, BattleResult, BattleScene
from scenes.battle import (
    BATTLE_CONFIRM_REPEAT_DELAY_FRAME_COUNT,
    BATTLE_CONFIRM_REPEAT_INTERVAL_FRAME_COUNT,
    BattlePhase,
)
from state import Language, SaveData, Settings
from systems import DungeonExitReturn, EncounterAdvance


class BattleEncounterTest(unittest.TestCase):
    def test_encounter_keeps_order_and_front_row_indexes(self) -> None:
        encounter = BattleEncounter(
            ("Giant Spider", "Coyote"),
            frozenset((1,)),
        )

        self.assertEqual(encounter.monster_keys, ("Giant Spider", "Coyote"))
        self.assertEqual(encounter.front_monster_indexes, frozenset((1,)))

    def test_encounter_rejects_an_index_outside_its_lineup(self) -> None:
        with self.assertRaisesRegex(ValueError, "front monster indexes"):
            BattleEncounter(("Coyote",), frozenset((1,)))


class BattleSceneIntegrationTest(unittest.TestCase):
    def test_skips_result_when_no_growth_was_recorded(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        scene.phase = BattlePhase.VICTORY_SUMMARY
        scene.result = None
        scene.victory_motion_frame = 0
        scene.growth_result = Mock(has_result_growth=False)

        scene._update_victory_summary(
            InputState(confirm=InputButton(triggered=True))
        )

        self.assertIs(scene.result, BattleResult.VICTORY)

    def test_result_transition_fades_out_and_in_before_result(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        scene.phase = BattlePhase.RESULT_TRANSITION
        scene.result_transition_fade = FadeThroughBlack(
            DEFAULT_FADE_FRAME_COUNT
        )
        scene.result_transition_fade.start()
        scene.result_transition_covered = False
        scene.palette_shifter = Mock(base_colors=(0,))

        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            scene._update_result_transition()

        self.assertTrue(scene.result_transition_covered)
        self.assertIs(scene.phase, BattlePhase.RESULT_TRANSITION)

        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            scene._update_result_transition()

        self.assertIs(scene.phase, BattlePhase.RESULT)
        scene.palette_shifter.set_global_mix.assert_called_with(
            base_rate=1.0,
            target_color=0,
        )

    def test_japanese_victory_numbers_use_fullwidth_glyphs(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        scene.settings = Settings(language=Language.JAPANESE)

        self.assertEqual(scene._victory_number(1234), "１２３４")

    def test_victory_jingle_queues_the_field_bgm(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        scene.bgm = Mock()
        scene.return_bgm_id = "da3-field"

        scene._play_victory_jingle("da3-win")

        scene.bgm.play_once_then.assert_called_once_with(
            "da3-win",
            "da3-field",
        )

    def test_held_confirm_repeats_at_da2_equivalent_timing(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        pressed = InputState(confirm=InputButton(triggered=True, held=True))
        held = InputState(confirm=InputButton(held=True))

        self.assertEqual(BATTLE_CONFIRM_REPEAT_DELAY_FRAME_COUNT, 20)
        self.assertEqual(BATTLE_CONFIRM_REPEAT_INTERVAL_FRAME_COUNT, 4)
        self.assertTrue(scene._apply_confirm_repeat(pressed).confirm.triggered)
        before_repeat = tuple(
            scene._apply_confirm_repeat(held).confirm.triggered
            for _frame in range(BATTLE_CONFIRM_REPEAT_DELAY_FRAME_COUNT - 1)
        )
        first_repeat = scene._apply_confirm_repeat(held)
        before_next_repeat = tuple(
            scene._apply_confirm_repeat(held).confirm.triggered
            for _frame in range(BATTLE_CONFIRM_REPEAT_INTERVAL_FRAME_COUNT - 1)
        )
        next_repeat = scene._apply_confirm_repeat(held)

        self.assertFalse(any(before_repeat))
        self.assertTrue(first_repeat.confirm.triggered)
        self.assertFalse(any(before_next_repeat))
        self.assertTrue(next_repeat.confirm.triggered)

    def test_releasing_confirm_resets_the_battle_repeat_delay(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        held = InputState(confirm=InputButton(held=True))
        released = InputState()

        for _frame in range(BATTLE_CONFIRM_REPEAT_DELAY_FRAME_COUNT - 1):
            scene._apply_confirm_repeat(held)
        scene._apply_confirm_repeat(released)
        after_release = tuple(
            scene._apply_confirm_repeat(held).confirm.triggered
            for _frame in range(BATTLE_CONFIRM_REPEAT_DELAY_FRAME_COUNT - 1)
        )

        self.assertFalse(any(after_release))

    def test_battle_update_passes_repeated_confirm_to_the_active_phase(
        self,
    ) -> None:
        scene = BattleScene.__new__(BattleScene)
        scene.result = None
        scene.restart_enabled = False
        scene.confirm_hold_frame_count = (
            BATTLE_CONFIRM_REPEAT_DELAY_FRAME_COUNT - 1
        )
        scene.phase = BattlePhase.ITEM
        scene._refresh_input_guide = Mock()
        scene._update_action_motion = Mock()
        scene._update_item_selection = Mock()
        held = InputState(confirm=InputButton(held=True))

        scene.update(held)

        repeated = scene._update_item_selection.call_args.args[0]
        self.assertFalse(held.confirm.triggered)
        self.assertTrue(repeated.confirm.triggered)
        self.assertTrue(repeated.confirm.held)

    def test_scene_consumes_input_supplied_by_its_owner(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        scene.result = BattleResult.ESCAPED
        scene._refresh_input_guide = Mock()
        input_state = InputState()

        scene.update(input_state)

        scene._refresh_input_guide.assert_called_once_with()

    def test_production_scene_does_not_depend_on_tools_package(self) -> None:
        source = (APP_ROOT / "scenes" / "battle.py").read_text(encoding="utf-8")

        self.assertNotIn("from tools", source)
        self.assertNotIn("import tools", source)
        self.assertNotIn("pyxel.run(", source)
        self.assertNotIn("pyxel.quit(", source)

    def test_production_restart_options_are_disabled_by_default(self) -> None:
        parameters = signature(BattleScene).parameters

        self.assertFalse(parameters["restart_enabled"].default)
        self.assertFalse(parameters["reset_party_on_restart"].default)
        self.assertFalse(parameters["reset_inventory_on_restart"].default)

    def test_game_routes_update_and_draw_to_an_active_battle(self) -> None:
        game = Game.__new__(Game)
        game.alert = Mock(camera_x=0)
        game.input_reader = Mock()
        input_state = InputState()
        game.input_reader.poll.return_value = input_state
        game.battle_scene = Mock()

        Game.update(game)
        with patch("game.pyxel"):
            Game.draw(game)

        game.battle_scene.update.assert_called_once_with(input_state)
        game.battle_scene.draw.assert_called_once_with()

    def test_game_builds_battle_from_current_session_dependencies(self) -> None:
        game = Game.__new__(Game)
        game.settings = object()
        game.palette_shifter = object()
        game.bgm = object()
        game.images = object()
        game.fonts = object()
        game.texts = object()
        game.items = object()
        game.spells = object()
        game.inventory_system = object()
        game.character_records = object()
        game.party = tuple(object() for _index in range(6))
        game.save_data = SaveData()
        game.current_map = Mock(bgm_id="da3-field")
        encounter = BattleEncounter(("Coyote",))

        with patch("game.BattleScene.create", return_value=Mock()) as create:
            scene = game._build_battle_scene(encounter)

        self.assertIs(scene, create.return_value)
        self.assertEqual(len(create.call_args.kwargs["party"]), 5)
        self.assertEqual(len(create.call_args.kwargs["result_party"]), 6)
        self.assertIs(create.call_args.kwargs["save_data"], game.save_data)
        self.assertEqual(create.call_args.kwargs["return_bgm_id"], "da3-field")
        self.assertIs(create.call_args.kwargs["encounter"], encounter)

    def test_game_advances_encounters_only_on_dungeon_steps(self) -> None:
        game = Game.__new__(Game)
        game.current_map = Mock(profile="dungeon")
        game.save_data = SaveData(encounter_count=158)
        game.encounter_system = Mock()
        game.encounter_system.advance.return_value = EncounterAdvance(0, True)
        game._begin_random_encounter = Mock()

        self.assertTrue(game._advance_random_encounter())

        game.encounter_system.advance.assert_called_once_with(158)
        self.assertEqual(game.save_data.encounter_count, 0)
        game._begin_random_encounter.assert_called_once_with()

        game.current_map.profile = "town"
        game.encounter_system.reset_mock()
        self.assertFalse(game._advance_random_encounter())
        game.encounter_system.advance.assert_not_called()

    def test_completed_ordinary_field_step_checks_for_an_encounter(self) -> None:
        game = Game.__new__(Game)
        arrived = FieldPosition(3, 4)
        game.field = Mock(is_moving=False, arrived_position=arrived)
        game.field_actors = None
        game.pending_screen_change = None
        game._release_latch_blocks_field = Mock(return_value=False)
        game._try_open_treasure = Mock(return_value=False)
        game._try_field_trigger = Mock(return_value=False)
        game._handle_arrived_site = Mock()
        game._advance_random_encounter = Mock(return_value=True)
        game._refresh_site_name_label = Mock()

        game._update_field(InputState())

        game._try_field_trigger.assert_called_once_with(
            "step",
            3,
            4,
            release_direction=None,
        )
        game._advance_random_encounter.assert_called_once_with()
        game._refresh_site_name_label.assert_not_called()

    def test_game_begins_pc_centered_transition_with_encounter_jingle(self) -> None:
        game = Game.__new__(Game)
        game.current_map = Mock(tile_size=16)
        game.field = Mock(world_x=160, world_y=96)
        game.field_renderer = Mock()
        game.field_renderer.camera_position.return_value = (40, 20)
        game.bgm = Mock()

        game._begin_random_encounter()

        self.assertEqual(game.encounter_transition.pivot_x, 128)
        self.assertEqual(game.encounter_transition.pivot_y, 76)
        self.assertIsNone(game.encounter_snapshot)
        game.field.stop.assert_called_once_with()
        game.bgm.play.assert_called_once_with(ENCOUNTER_JINGLE_ID, loop=False)

    def test_encounter_transition_builds_the_fixed_test_lineup_at_black(
        self,
    ) -> None:
        game = Game.__new__(Game)
        game.encounter_transition = EncounterTransition(128, 120)
        game.encounter_snapshot = object()
        game.palette_shifter = Mock(base_colors=(0,))
        battle = Mock()
        game._build_battle_scene = Mock(return_value=battle)

        for _frame in range(ENCOUNTER_TRANSITION_FRAME_COUNT):
            game._update_encounter_transition()

        self.assertIsNone(game.encounter_transition)
        self.assertIsNone(game.encounter_snapshot)
        self.assertIs(game.battle_scene, battle)
        game._build_battle_scene.assert_called_once_with(RANDOM_BATTLE_ENCOUNTER)
        self.assertEqual(
            RANDOM_BATTLE_ENCOUNTER.monster_keys,
            (
                "Giant Spider",
                "Giant Spider",
                "Giant Spider",
                "Coyote",
                "Coyote",
            ),
        )

    @patch("game.pyxel.Image")
    def test_encounter_snapshot_hides_the_player(self, image_type: Mock) -> None:
        game = Game.__new__(Game)
        game.encounter_transition = EncounterTransition(128, 120)
        game.encounter_snapshot = None
        game._draw_field_screen = Mock()

        game._draw_encounter_transition()

        game._draw_field_screen.assert_called_once_with(draw_player=False)
        self.assertIs(game.encounter_snapshot, image_type.return_value)

    def test_defeat_return_moves_to_the_cell_before_nearest_dungeon_exit(
        self,
    ) -> None:
        game = Game.__new__(Game)
        game.battle_return_result = BattleResult.DEFEAT
        game.battle_scene = Mock()
        game.current_map = Mock(bgm_id="da3-forest")
        game.field = Mock(position=FieldPosition(20, 20))
        game.encounter_system = Mock()
        game.encounter_system.defeat_return.return_value = DungeonExitReturn(
            FieldPosition(16, 38),
            Direction.DOWN,
        )
        game._reset_field_actors = Mock()
        game.bgm = Mock()

        with patch("game.FieldMovement", return_value=Mock()) as movement:
            game._apply_battle_return()

        movement.assert_called_once_with(
            game.current_map,
            start=FieldPosition(16, 38),
            facing=Direction.DOWN,
        )
        self.assertIsNone(game.battle_scene)
        game._reset_field_actors.assert_called_once_with()
        game.bgm.play.assert_called_once_with("da3-forest")

    def test_victory_return_counts_the_completed_battle(self) -> None:
        game = Game.__new__(Game)
        game.battle_return_result = BattleResult.VICTORY
        game.battle_scene = Mock()
        game.save_data = SaveData(battle_count=4)
        game.current_map = Mock(bgm_id="da3-forest")
        game.bgm = Mock()

        game._apply_battle_return()

        self.assertEqual(game.save_data.battle_count, 5)

    def test_escape_reuses_battle_blackout_and_starts_with_field_fade_in(
        self,
    ) -> None:
        game = Game.__new__(Game)
        game.palette_shifter = Mock(base_colors=(0,))
        game._apply_battle_return = Mock()

        game._begin_battle_return(BattleResult.ESCAPED)

        game._apply_battle_return.assert_called_once_with()
        self.assertIs(game.battle_return_result, BattleResult.ESCAPED)
        self.assertIs(game.battle_return_fade.phase, FadePhase.FADING_IN)


if __name__ == "__main__":
    unittest.main()
