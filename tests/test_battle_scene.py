from __future__ import annotations

import unittest
from inspect import signature
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import load_mock_items

from field import FieldPosition
from game import (
    ENCOUNTER_JINGLE_ID,
    RANDOM_BATTLE_ENCOUNTER,
    TELEPORT_SOUND_CHANNEL,
    TELEPORT_SOUND_ID,
    Game,
)
from input import Direction, InputButton, InputState
from localization import Localizer
from member import FormationRow
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
    MONSTER_POSITIONS,
    BattleCharacter,
    BattlePhase,
    FormationAnimationCompletion,
    monster_slot_indexes,
)
from state import Language, SaveData, Settings
from systems import DungeonExitReturn, EncounterAdvance
from text_catalog import TextCatalog
from ui import LocalizedWindowTextFactory, POSITIVE_COLOR
from ui.tagged_text import TextColor, split_tagged_text


class BattleEncounterTest(unittest.TestCase):
    def test_encounter_keeps_order_and_front_row_indexes(self) -> None:
        encounter = BattleEncounter(
            ("Giant Spider", "Coyote"),
            frozenset((1,)),
        )

        self.assertEqual(encounter.monster_keys, ("Giant Spider", "Coyote"))
        self.assertEqual(encounter.front_monster_indexes, frozenset((1,)))
        self.assertFalse(encounter.surprise_enabled)

    def test_encounter_rejects_an_index_outside_its_lineup(self) -> None:
        with self.assertRaisesRegex(ValueError, "front monster indexes"):
            BattleEncounter(("Coyote",), frozenset((1,)))

    def test_random_encounter_enables_surprise(self) -> None:
        self.assertTrue(RANDOM_BATTLE_ENCOUNTER.surprise_enabled)

    def test_standard_first_monster_keeps_all_five_slots(self) -> None:
        monsters = tuple(
            SimpleNamespace(width=64, height=64) for _ in range(5)
        )

        self.assertEqual(monster_slot_indexes(monsters), (0, 1, 2, 3, 4))

    def test_64_by_96_first_monster_skips_the_second_rear_slot(self) -> None:
        monsters = (
            SimpleNamespace(width=64, height=96),
            SimpleNamespace(width=64, height=64),
            SimpleNamespace(width=64, height=64),
            SimpleNamespace(width=64, height=64),
        )
        slots = monster_slot_indexes(monsters)

        self.assertEqual(slots, (0, 2, 3, 4))
        self.assertEqual(
            tuple(MONSTER_POSITIONS[index] for index in slots),
            ((4, 48), (68, 16), (68, 80), (68, 144)),
        )

    def test_64_by_96_first_monster_rejects_a_fifth_monster(self) -> None:
        monsters = tuple(
            SimpleNamespace(width=64, height=96 if index == 0 else 64)
            for index in range(5)
        )

        with self.assertRaisesRegex(ValueError, "supports at most 4 monsters"):
            monster_slot_indexes(monsters)


class BattleSurpriseIntegrationTest(unittest.TestCase):
    @staticmethod
    def _member(
        agility: int,
        row: FormationRow,
        *,
        vigilant: bool = False,
        alive: bool = True,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            adjusted_abilities=SimpleNamespace(agility=agility),
            formation_row=row,
            is_alive=alive,
            hp=1 if alive else 0,
            has_skill=lambda key: vigilant and key == "Vigilance",
        )

    @staticmethod
    def _scene(
        *members: SimpleNamespace,
        surprise_enabled: bool = True,
    ) -> BattleScene:
        scene = BattleScene.__new__(BattleScene)
        scene.party = members
        scene.party_visuals = tuple(
            SimpleNamespace(member=member) for member in members
        )
        scene.monsters = (SimpleNamespace(agility=12, is_alive=True),)
        scene.encounter = BattleEncounter(
            ("Coyote",),
            surprise_enabled=surprise_enabled,
        )
        scene.temporary_front_party_indexes = set()
        scene.escaped_party_indexes = set()
        return scene

    def test_surprise_inverts_mixed_rows_without_mutating_members(self) -> None:
        front = self._member(10, FormationRow.FRONT)
        rear = self._member(10, FormationRow.BACK)
        scene = self._scene(front, rear)

        with patch("scenes.battle.pyxel.rndi", return_value=0):
            scene._prepare_surprise()

        self.assertTrue(scene.surprise_active)
        self.assertFalse(scene._party_member_is_front_row(0))
        self.assertTrue(scene._party_member_is_front_row(1))
        self.assertIs(front.formation_row, FormationRow.FRONT)
        self.assertIs(rear.formation_row, FormationRow.BACK)
        self.assertEqual(scene.surprise_pending_party_indexes, {0, 1})

    def test_all_front_party_stays_front_during_surprise(self) -> None:
        scene = self._scene(
            self._member(10, FormationRow.FRONT),
            self._member(10, FormationRow.FRONT),
        )

        with patch("scenes.battle.pyxel.rndi", return_value=0):
            scene._prepare_surprise()

        self.assertTrue(scene._party_member_is_front_row(0))
        self.assertTrue(scene._party_member_is_front_row(1))

    def test_living_vigilance_owner_prevents_surprise(self) -> None:
        vigilant = self._member(10, FormationRow.FRONT, vigilant=True)
        scene = self._scene(vigilant)

        with patch("scenes.battle.pyxel.rndi", return_value=0):
            scene._prepare_surprise()

        self.assertFalse(scene.surprise_active)
        self.assertEqual(scene.surprise_prevented_by_index, 0)

        dead_vigilant = self._member(
            10,
            FormationRow.FRONT,
            vigilant=True,
            alive=False,
        )
        living = self._member(10, FormationRow.FRONT)
        scene = self._scene(dead_vigilant, living)
        with patch("scenes.battle.pyxel.rndi", return_value=0):
            scene._prepare_surprise()
        self.assertIsNone(scene.surprise_prevented_by_index)
        self.assertTrue(scene.surprise_active)

    def test_losing_roll_does_not_start_surprise(self) -> None:
        scene = self._scene(self._member(32, FormationRow.FRONT))

        with patch("scenes.battle.pyxel.rndi", return_value=31):
            scene._prepare_surprise()

        self.assertFalse(scene.surprise_roll.triggered)
        self.assertFalse(scene.surprise_active)

    def test_non_random_encounter_does_not_draw(self) -> None:
        scene = self._scene(
            self._member(10, FormationRow.FRONT),
            surprise_enabled=False,
        )

        with patch("scenes.battle.pyxel.rndi") as rndi:
            scene._prepare_surprise()

        rndi.assert_not_called()

    def test_agility_average_includes_dead_battle_participants(self) -> None:
        scene = self._scene(
            self._member(32, FormationRow.FRONT, alive=False),
            self._member(0, FormationRow.FRONT),
        )

        with patch("scenes.battle.pyxel.rndi", return_value=0):
            scene._prepare_surprise()

        self.assertEqual(scene.surprise_roll.threshold, 1)
        self.assertTrue(scene.surprise_active)

    def test_repeated_party_handoffs_skip_until_every_member_was_reached(
        self,
    ) -> None:
        front = self._member(10, FormationRow.FRONT)
        rear = self._member(10, FormationRow.BACK)
        scene = self._scene(front, rear)
        scene.command_cursor = Mock()
        scene.command_window = Mock()
        scene._refresh_party_text_colors = Mock()
        scene._start_timeline_animation = Mock()
        with patch("scenes.battle.pyxel.rndi", return_value=0):
            scene._prepare_surprise()

        self.assertEqual(
            scene._party_sprite_width(0, is_escaping=False),
            -16,
        )
        self.assertTrue(scene._skip_surprised_party_turn(0))
        self.assertEqual(scene.surprise_pending_party_indexes, {1})
        self.assertTrue(scene._skip_surprised_party_turn(0))
        self.assertEqual(scene.surprise_pending_party_indexes, {1})
        self.assertTrue(scene._skip_surprised_party_turn(1))

        self.assertFalse(scene.surprise_active)
        self.assertEqual(
            scene._party_sprite_width(0, is_escaping=False),
            16,
        )
        self.assertIs(scene.phase, BattlePhase.FORMATION)
        self.assertIs(front.formation_row, FormationRow.FRONT)
        self.assertIs(rear.formation_row, FormationRow.BACK)
        self.assertEqual(scene._start_timeline_animation.call_count, 2)

        for _frame in range(8):
            scene._update_formation_animation()
        self.assertEqual(scene._start_timeline_animation.call_count, 3)

    def test_status_is_processed_before_the_single_surprise_skip(self) -> None:
        member = self._member(10, FormationRow.FRONT)
        member.sleeping = 2
        member.poisoned = False
        member.battle_healing = 0
        member.paralyzed = False
        member.stunned = False
        actor = BattleCharacter(member, 0, 0, 0)
        scene = self._scene(member)
        scene.party_visuals = (actor,)
        scene.timeline = (actor,)
        scene.surprise_active = True
        scene.surprise_pending_party_indexes = {0}
        scene.surprise_original_front_rows = {0: True}
        scene.surprise_front_party_indexes = {0}
        scene.surprise_temporary_front_party_indexes = set()
        scene.escape_requested = False
        scene.defending_party_indexes = set()
        scene.focused_target_by_party_index = {}
        scene.blinking_monster_index = None
        scene.monster_blink_frames_remaining = 0
        scene.command_cursor = Mock()
        scene.command_window = Mock()
        scene._refresh_party_text_colors = Mock()
        scene._start_timeline_animation = Mock()

        scene._activate_timeline_head()

        self.assertEqual(member.sleeping, 1)
        self.assertFalse(scene.surprise_active)
        scene._start_timeline_animation.assert_called_once_with()

    def test_restore_keeps_survivors_front_when_original_front_died(self) -> None:
        defeated_front = self._member(10, FormationRow.FRONT, alive=False)
        living_rear = self._member(10, FormationRow.BACK)
        scene = self._scene(defeated_front, living_rear)
        scene.surprise_active = True
        scene.surprise_pending_party_indexes = set()
        scene.surprise_original_front_rows = {0: True, 1: False}
        scene.surprise_front_party_indexes = {1}
        scene.surprise_temporary_front_party_indexes = set()
        scene.command_cursor = Mock()
        scene.command_window = Mock()
        scene._refresh_party_text_colors = Mock()
        scene._start_timeline_animation = Mock()

        scene._restore_surprise_formation(
            FormationAnimationCompletion.START_TIMELINE
        )

        self.assertEqual(scene.temporary_front_party_indexes, {1})
        self.assertTrue(scene._party_member_is_front_row(1))
        self.assertIs(living_rear.formation_row, FormationRow.BACK)
        scene._start_timeline_animation.assert_called_once_with()


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

    def test_victory_confirmation_waits_for_hidden_member_return(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        scene.phase = BattlePhase.VICTORY_SUMMARY
        scene.result = None
        scene.victory_motion_frame = 0
        scene.victory_return_frame = 0
        scene.victory_returning_party_indexes = {0}
        scene.party_visuals = (
            Mock(
                member=Mock(
                    formation_row=FormationRow.FRONT,
                    is_dead=False,
                )
            ),
        )
        scene.growth_result = Mock(has_result_growth=False)

        scene._update_victory_summary(
            InputState(confirm=InputButton(triggered=True))
        )

        self.assertIsNone(scene.result)
        self.assertEqual(scene.victory_return_frame, 1)
        self.assertEqual(scene.victory_returning_party_indexes, {0})

    def test_waits_for_victory_jingle_before_leaving_results(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        scene.phase = BattlePhase.VICTORY_SUMMARY
        scene.result = None
        scene.victory_motion_frame = 0
        scene.victory_exit_pending = False
        scene.growth_result = Mock(has_result_growth=False)
        scene.bgm = Mock(current_id="da3-win")

        scene._update_victory_summary(
            InputState(confirm=InputButton(triggered=True))
        )

        self.assertIsNone(scene.result)
        self.assertTrue(scene.victory_exit_pending)

        scene.bgm.current_id = "da3-field"
        scene._update_victory_summary(InputState())

        self.assertIs(scene.result, BattleResult.VICTORY)
        self.assertFalse(scene.victory_exit_pending)

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

    def test_victory_treasure_is_a_second_line_with_only_item_positive(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        items = load_mock_items()
        item = items["DIVINE TEAR"]
        scene.item_catalog = items
        scene.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        scene.localizer = Localizer(Language.JAPANESE)
        factory = LocalizedWindowTextFactory(Mock(), 0)
        growth = SimpleNamespace(
            treasure_drop=SimpleNamespace(item_key=item.key),
        )

        placements = scene._victory_summary_placements(
            "ほうしゅう",
            growth,
            factory,
        )

        self.assertEqual(tuple(text.y for text in placements), (2, 5))
        parts = split_tagged_text(placements[1].text)
        self.assertIsInstance(parts[0], TextColor)
        self.assertEqual(parts[0].color, POSITIVE_COLOR)
        self.assertEqual(parts[1], item.localized_name(scene.localizer))
        self.assertIsInstance(parts[2], TextColor)
        self.assertEqual(parts[3], "を　てにいれた")

    def test_monster_death_records_the_drop_candidate_order(self) -> None:
        scene = BattleScene.__new__(BattleScene)
        scene.monsters = (
            SimpleNamespace(is_alive=False, is_front_row=True),
        )
        scene.progression = Mock()
        scene.target_cursor = Mock()
        scene.command_window = Mock()
        scene._sync_monster_death_palette = Mock()

        with patch("scenes.battle.play_se"):
            self.assertTrue(scene._begin_monster_death(0))

        scene.progression.record_enemy_defeat.assert_called_once_with(0)

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
        game.current_map = Mock(profile="dungeon")
        game.party = ()
        game.pending_screen_change = None
        game._release_latch_blocks_field = Mock(return_value=False)
        game._try_open_treasure = Mock(return_value=False)
        game._try_field_trigger = Mock(return_value=False)
        game._handle_arrived_site = Mock()
        game._apply_dungeon_step_health_changes = Mock()
        game._advance_random_encounter = Mock(return_value=True)
        game._refresh_site_name_label = Mock()

        game._update_field(InputState())

        game._try_field_trigger.assert_called_once_with(
            "step",
            3,
            4,
            release_direction=None,
        )
        game._apply_dungeon_step_health_changes.assert_called_once_with()
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
                "Treant",
                "Cobra",
                "Cobra",
                "Cobra",
            ),
        )
        self.assertEqual(
            RANDOM_BATTLE_ENCOUNTER.front_monster_indexes,
            frozenset((1, 2, 3)),
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
        members = (
            Mock(hp=10, paralyzed=False, is_front_row=True),
            Mock(hp=10, paralyzed=False, is_front_row=True),
        )
        game.party = members
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
        for member in members:
            member.fully_recover.assert_called_once_with()
        game._reset_field_actors.assert_called_once_with()
        game.bgm.transition_to.assert_called_once_with("da3-forest")

    @patch("game.pyxel.play_pos", return_value=None)
    def test_field_defeat_restarts_bgm_after_teleport_sound(
        self,
        play_pos: Mock,
    ) -> None:
        game = Game.__new__(Game)
        game.battle_return_result = BattleResult.DEFEAT
        game.battle_scene = None
        game.current_map = Mock(bgm_id="da3-forest")
        game.field = Mock(position=FieldPosition(20, 20))
        game.encounter_system = Mock()
        game.encounter_system.defeat_return.return_value = None
        game.party = (
            Mock(hp=10, paralyzed=False, is_front_row=True),
        )
        game.bgm = Mock()

        game._apply_battle_return()

        game.bgm.stop.assert_called_once_with()
        game.bgm.play.assert_not_called()
        game.bgm.transition_to.assert_not_called()
        self.assertTrue(game.defeat_return_bgm_restart_pending)

        game.battle_return_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        game.battle_return_fade.start_fade_in()
        game.defeat_return_message = None
        game.defeat_return_sound_waiting = True
        game.palette_shifter = Mock(base_colors=(0,))

        game._update_battle_return(InputState())

        play_pos.assert_called_once_with(TELEPORT_SOUND_CHANNEL)
        game.bgm.play.assert_called_once_with("da3-forest")
        self.assertFalse(game.defeat_return_bgm_restart_pending)
        self.assertEqual(game.battle_return_fade.elapsed_frames, 1)

    def test_victory_return_counts_the_completed_battle(self) -> None:
        game = Game.__new__(Game)
        game.battle_return_result = BattleResult.VICTORY
        battle_scene = Mock()
        member = Mock(hp=10, paralyzed=False, is_front_row=True)
        game.battle_scene = battle_scene
        game.party = (member,)
        game.save_data = SaveData(battle_count=4)
        game.current_map = Mock(bgm_id="da3-forest")
        game.bgm = Mock()

        game._apply_battle_return()

        self.assertEqual(game.save_data.battle_count, 5)
        battle_scene.clear_temporary_member_conditions.assert_called_once_with()
        member.fully_recover.assert_not_called()
        member.recover_world_map_entry_ailments.assert_not_called()

    def test_battle_return_permanently_advances_first_recoverable_rear(
        self,
    ) -> None:
        game = Game.__new__(Game)
        game.battle_return_result = BattleResult.VICTORY
        defeated_front = Mock(
            hp=0,
            paralyzed=False,
            is_front_row=True,
            formation_row=FormationRow.FRONT,
        )
        rear = Mock(
            hp=10,
            paralyzed=False,
            is_front_row=False,
            formation_row=FormationRow.BACK,
        )
        game.party = (defeated_front, rear)
        game.battle_scene = Mock()
        game.save_data = SaveData()
        game.current_map = Mock(bgm_id="da3-forest")
        game.bgm = Mock()

        game._apply_battle_return()

        self.assertIs(rear.formation_row, FormationRow.FRONT)

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

    @patch("game.pyxel.play_pos")
    @patch("game.pyxel.play")
    @patch("game.MessageOverlay")
    def test_defeat_return_waits_at_black_for_rescue_message(
        self,
        message_overlay: Mock,
        play: Mock,
        play_pos: Mock,
    ) -> None:
        game = Game.__new__(Game)
        game.settings = Settings(language=Language.JAPANESE)
        game.texts = Mock()
        game.texts.lines.return_value = (
            "line 1",
            "line 2",
            "line 3",
            "line 4",
        )
        game.fonts = object()
        game.faces = object()
        game.palette_shifter = Mock(base_colors=(0,))
        game.bgm = Mock()
        game._apply_battle_return = Mock()
        message_overlay.return_value.update.return_value = False

        game._begin_battle_return(BattleResult.DEFEAT)
        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            game._update_battle_return(InputState())

        self.assertIs(
            game.defeat_return_message,
            message_overlay.return_value,
        )
        self.assertIs(game.battle_return_fade.phase, FadePhase.FADING_IN)
        game._apply_battle_return.assert_not_called()
        self.assertEqual(
            message_overlay.call_args.kwargs["lines"],
            game.texts.lines.return_value,
        )
        text_key, localizer = game.texts.lines.call_args.args
        self.assertEqual(text_key, "defeat.return.message")
        self.assertIs(localizer.language, Language.JAPANESE)
        face = message_overlay.call_args.kwargs["face_position"]
        self.assertEqual((face.x, face.y), (0, 224))
        play.assert_not_called()

        message_overlay.return_value.update.return_value = True
        game._update_battle_return(InputState())

        self.assertIsNone(game.defeat_return_message)
        game._apply_battle_return.assert_called_once_with()
        self.assertEqual(
            game.palette_shifter.set_global_mix.call_args.kwargs["base_rate"],
            0.0,
        )
        play.assert_called_once_with(TELEPORT_SOUND_CHANNEL, TELEPORT_SOUND_ID)
        self.assertTrue(game.defeat_return_sound_waiting)
        self.assertEqual(game.battle_return_fade.elapsed_frames, 0)

        play_pos.return_value = (TELEPORT_SOUND_ID, 0)
        game._update_battle_return(InputState())

        play_pos.assert_called_once_with(TELEPORT_SOUND_CHANNEL)
        self.assertTrue(game.defeat_return_sound_waiting)
        self.assertEqual(game.battle_return_fade.elapsed_frames, 0)

        play_pos.return_value = None
        game._update_battle_return(InputState())

        self.assertFalse(game.defeat_return_sound_waiting)
        self.assertEqual(game.battle_return_fade.elapsed_frames, 1)

    @patch("game.pyxel.camera")
    @patch("game.pyxel.cls")
    def test_defeat_return_message_draws_over_black_instead_of_battle(
        self,
        clear: Mock,
        camera: Mock,
    ) -> None:
        game = Game.__new__(Game)
        game.alert = Mock(camera_x=0)
        game.encounter_transition = None
        game.defeat_return_message = Mock()
        game.battle_scene = Mock()

        game.draw()

        clear.assert_called_once_with(0)
        game.defeat_return_message.draw.assert_called_once_with()
        game.battle_scene.draw.assert_not_called()


if __name__ == "__main__":
    unittest.main()
