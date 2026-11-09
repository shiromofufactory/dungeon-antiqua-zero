from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from debug_dungeon import (
    DEFAULT_ENCOUNTER, DebugDungeonDataError, DungeonCheckpoint, DungeonProgress, parse_dungeons as parse_dungeon_document, reset_treasures,
)
from game import Game, GameScreenChange
from input import Direction, InputButton, InputState
from resources import FontResources
from scenes import BattleEncounter, BattlePhase, BattleResult
from scenes.debug_dungeon import DebugDungeonScene
from state import Language, LaunchMode, SaveData, Settings
from systems import InventorySystem, TreasureSystem, create_save_document, restore_save_document
from text_catalog import TextCatalog
from tools.debug_dungeon_editor.server import DebugDungeonEditorApplication
from tools.screen_mocks._fixtures import load_mock_character_records, load_mock_items, load_mock_party, load_mock_skills
from ui import LocalizedWindowTextFactory, WindowFactory
from ui.debug_dungeon import DebugDungeonOverlay
from ui.debug_text import DEBUG_TEXT


def parse_dungeons(document, **catalogs):
    return parse_dungeon_document(document, battle_ids={"shrine_guard"}, **catalogs)


def source():
    return {"format_version": 1, "dungeons": [{
        "id": "trial", "name": "調整用ダンジョン", "bgm_id": "da3-dungeon1", "steps": [
            {"id": "random_1", "type": "random_encounter", "count": 2, "encounter": dict(DEFAULT_ENCOUNTER)},
            {"id": "chest_1", "type": "treasure", "contents": {"type": "gold", "amount": 100}},
            {"id": "boss_1", "type": "event_battle", "battle_id": "shrine_guard"},
        ],
    }]}


class DebugDungeonDataTest(unittest.TestCase):
    def test_checkpoint_restores_partial_random_battles_and_fade_by_stable_step_id(self):
        dungeon = parse_dungeons(source())[0]
        progress = DungeonProgress(dungeon)
        progress.complete()
        progress.activate_fade()
        checkpoint = DungeonCheckpoint.from_document(progress.checkpoint().to_document())
        restored = DungeonProgress.from_checkpoint(dungeon, checkpoint)
        self.assertEqual(restored.index, 0)
        self.assertEqual(restored.completed_in_step, 1)
        self.assertTrue(restored.fade_active)
        reordered = source()
        steps = reordered["dungeons"][0]["steps"]
        steps.insert(0, steps.pop(1))
        restored = DungeonProgress.from_checkpoint(parse_dungeons(reordered)[0], checkpoint)
        self.assertEqual(restored.index, 1)
        self.assertEqual(restored.completed_in_step, 1)

    def test_checkpoint_restores_end_and_rejects_missing_steps_and_changed_count(self):
        dungeon = parse_dungeons(source())[0]
        finished = DungeonCheckpoint(dungeon.id, None, 0, True)
        self.assertIsNone(DungeonProgress.from_checkpoint(dungeon, finished).current)
        for checkpoint in (DungeonCheckpoint("missing", "random_1", 0, False),
                           DungeonCheckpoint(dungeon.id, "missing", 0, False),
                           DungeonCheckpoint(dungeon.id, "random_1", 2, False),
                           DungeonCheckpoint(dungeon.id, "chest_1", 1, False)):
            with self.subTest(checkpoint=checkpoint), self.assertRaises(DebugDungeonDataError):
                DungeonProgress.from_checkpoint(dungeon, checkpoint)

    def test_rejects_bad_fields_ids_bounds_duplicates_and_references(self):
        mutations = (
            lambda d: d.update(format_version=True),
            lambda d: d["dungeons"].append(deepcopy(d["dungeons"][0])),
            lambda d: d["dungeons"][0].update(id="../map"),
            lambda d: d["dungeons"][0].update(name=""),
            lambda d: d["dungeons"][0].update(name="長" * 25),
            lambda d: d["dungeons"][0]["steps"][0].update(count=0),
            lambda d: d["dungeons"][0]["steps"][0].update(count=True),
            lambda d: d["dungeons"][0]["steps"][0]["encounter"].update(monster_level=True),
            lambda d: d["dungeons"][0]["steps"][0]["encounter"].update(allow_demons=1),
            lambda d: d["dungeons"][0]["steps"][0]["encounter"].update(enabled=False),
            lambda d: d["dungeons"][0]["steps"][1].update(id="random_1"),
            lambda d: d["dungeons"][0]["steps"][1]["contents"].update(amount=1000000),
            lambda d: d["dungeons"][0]["steps"][1].update(contents={"type":"item","item_key":"missing"}),
            lambda d: d["dungeons"][0]["steps"][2].update(monster_keys=[]),
            lambda d: d["dungeons"][0]["steps"][2].update(monster_keys=["missing"]),
            lambda d: d["dungeons"][0].update(bgm_id="missing"),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                data = source()
                mutation(data)
                with self.assertRaises(DebugDungeonDataError):
                    parse_dungeons(data, item_keys={"POTION"}, bgm_ids={"da3-dungeon1"})

    def test_progress_consumes_exactly_one_battle_and_restarts_on_reentry(self):
        dungeon = parse_dungeons(source())[0]
        p = DungeonProgress(dungeon)
        self.assertEqual(p.remaining_battles, 3)
        p.complete()
        self.assertEqual((p.index, p.completed_in_step, p.remaining_battles), (0, 1, 2))
        p.complete()
        self.assertEqual(p.current.type, "treasure")
        p.complete()
        self.assertEqual(p.current.type, "event_battle")
        p.complete()
        self.assertIsNone(p.current)
        self.assertEqual(p.remaining_battles, 0)
        self.assertEqual(DungeonProgress(dungeon).index, 0)

    def test_fade_draws_once_per_random_battle_and_never_for_treasures_or_bosses(self):
        rng = Mock()
        rng.randrange.side_effect = (0, 1)
        p = DungeonProgress(parse_dungeons(source())[0], random_source=rng)
        self.assertFalse(p.skip_random_battle())
        rng.randrange.assert_not_called()
        self.assertTrue(p.activate_fade())
        self.assertFalse(p.activate_fade())
        self.assertTrue(p.skip_random_battle())
        p.complete()
        self.assertFalse(p.skip_random_battle())
        p.complete()
        self.assertFalse(p.skip_random_battle())
        p.complete()
        self.assertFalse(p.skip_random_battle())
        self.assertEqual(rng.randrange.call_args_list, [((2,),), ((2,),)])


class DebugDungeonSceneTest(unittest.TestCase):
    def setUp(self):
        self.items = load_mock_items()
        self.skills = load_mock_skills()
        self.party = load_mock_party(self.items, self.skills)
        self.save_data = SaveData()
        self.inventory = InventorySystem(self.items)
        self.treasures = TreasureSystem(save_data=self.save_data, inventory=self.inventory)
        self.fonts = FontResources()
        self.settings = Settings()
        self.battle = Mock(return_value=True)
        self.menu = Mock()
        self.exit = Mock()

    def scene(self, data=None):
        return DebugDungeonScene(
            dungeon=parse_dungeons(data or source())[0], party=self.party,
            settings=self.settings, fonts=self.fonts, texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
            items=self.items, treasure_system=self.treasures,
            on_battle=self.battle, on_menu=self.menu, on_exit=self.exit, alert=Mock(),
        )

    def test_starts_one_battle_then_waits_for_the_next_choice(self):
        scene = self.scene()
        scene.update(InputState())
        self.assertTrue(scene.waiting_for_battle)
        self.assertEqual(scene.progress.completed_in_step, 0)
        scene.update(InputState(confirm=InputButton(True, True)))
        self.assertEqual(self.battle.call_count, 1)
        scene.complete_battle()
        scene.update(InputState())
        self.assertEqual(self.battle.call_count, 1)
        scene.update(InputState(confirm=InputButton(True, True)))
        self.assertEqual(self.battle.call_count, 2)

    def test_resume_waits_for_choice_without_replaying_the_saved_step(self):
        scene = self.scene()
        checkpoint = DungeonCheckpoint(scene.dungeon.id, "random_1", 1, True)
        scene.resume(checkpoint)
        scene.update(InputState())
        self.battle.assert_not_called()
        self.assertTrue(scene.started)
        self.assertEqual(scene.progress.completed_in_step, 1)
        self.assertTrue(scene.progress.fade_active)
        scene.resume(DungeonCheckpoint(scene.dungeon.id, None, 0, False))
        scene.update(InputState())
        self.assertIsNone(scene.progress.current)
        self.assertNotIn("next", [target.key for target in scene.cursor.targets])

    def test_first_event_battle_warns_and_allows_preparation_without_starting(self):
        data = source()
        data["dungeons"][0]["steps"] = [data["dungeons"][0]["steps"][2]]
        scene = self.scene(data)
        scene.update(InputState())
        self.battle.assert_not_called()
        self.assertIn(DEBUG_TEXT.dungeon_warning, [text.text for text in scene.window.texts])
        scene.cursor.select_key("menu")
        scene.update(InputState(confirm=InputButton(True, True)))
        self.menu.assert_called_once_with()
        self.assertEqual(scene.progress.index, 0)
        scene.refresh()
        scene.update(InputState(confirm=InputButton(True, True)))
        self.battle.assert_called_once()
        scene.complete_battle()
        self.assertNotIn("next", [target.key for target in scene.cursor.targets])
        self.assertIn(DEBUG_TEXT.dungeon_finished, [text.text for text in scene.window.texts])

    @patch("scenes.debug_dungeon.play_se")
    def test_treasure_is_not_duplicated_after_reentry_or_reordering(self, _play):
        data = source()
        data["dungeons"][0]["steps"] = [data["dungeons"][0]["steps"][1]]
        first = self.scene(data)
        first.update(InputState())
        self.assertEqual(self.save_data.gold, 100)
        self.assertEqual(self.save_data.opened_treasures, {("debug_dungeon.trial", "chest_1")})
        second = self.scene(data)
        second.update(InputState())
        self.assertEqual(self.save_data.gold, 100)
        self.assertIsNone(second.message)
        self.assertIsNone(second.progress.current)

    @patch("scenes.debug_dungeon.play_se")
    def test_capacity_failure_leaves_chest_unopened_and_advances(self, _play):
        data = source()
        data["dungeons"][0]["steps"] = data["dungeons"][0]["steps"][1:]
        self.save_data.gold = 999999
        scene = self.scene(data)
        scene.update(InputState())
        self.assertEqual(self.save_data.gold, 999999)
        self.assertFalse(self.save_data.opened_treasures)
        self.assertEqual(scene.progress.current.type, "event_battle")
        self.assertIsNotNone(scene.message)
        self.battle.assert_not_called()

    def test_skipped_battle_consumes_one_count_without_rewards(self):
        scene = self.scene()
        scene.progress.activate_fade()
        scene.progress.random = Mock(randrange=Mock(return_value=0))
        scene.update(InputState())
        self.assertEqual(scene.progress.completed_in_step, 1)
        self.battle.assert_not_called()
        self.assertEqual(self.save_data.battle_count, 0)
        self.assertEqual(scene.notice, DEBUG_TEXT.dungeon_skipped)

    def test_empty_formation_keeps_position_for_retry(self):
        self.battle.return_value = False
        scene = self.scene()
        scene.update(InputState())
        self.assertEqual(scene.progress.completed_in_step, 0)
        self.assertFalse(scene.waiting_for_battle)
        scene.alert.start.assert_called_once()

    def test_reset_and_save_roundtrip_preserve_other_dungeons_and_game_progress(self):
        dungeon = parse_dungeons(source())[0]
        self.save_data.opened_treasures = {(dungeon.treasure_map_id, "chest_1"),
                                         ("real_map", "chest_1"), ("debug_dungeon.other", "chest_2")}
        from field import FieldPosition
        document = create_save_document(
            save_data=self.save_data, active_party=self.party,
            character_states={m.definition.key:m for m in self.party}, inventory=self.inventory,
            map_id="worldmap", position=FieldPosition(1,1), facing=Direction.DOWN,
        )
        loaded = restore_save_document(document, character_records=load_mock_character_records(),
                                       items=self.items, skills=self.skills)
        self.assertEqual(loaded.save_data.opened_treasures, self.save_data.opened_treasures)
        reset_treasures(dungeon, self.save_data.opened_treasures)
        self.assertEqual(self.save_data.opened_treasures, {("real_map", "chest_1"), ("debug_dungeon.other", "chest_2")})


class DebugDungeonGameTest(unittest.TestCase):
    def game(self):
        game = Game.__new__(Game)
        game.launch_mode = LaunchMode.NORMAL
        game.debug_dungeon_scene = Mock()
        game.save_data = SaveData()
        game.current_map = SimpleNamespace(bgm_id="original", map_id="real_map")
        game.bgm = Mock()
        game.field = Mock()
        game.field_renderer = Mock()
        game.encounter_system = Mock()
        game.event_catalog = Mock()
        game.event_catalog.battle_monster_keys.return_value = ("Giant Spider",)
        game.party = (Mock(),)
        game.battle_scene = Mock(return_bgm_start_sec=12.5)
        game._restore_dimmed_palette = Mock()
        game._promote_first_recoverable_member = Mock()
        game._build_main_windows = Mock()
        return game

    def test_active_simulation_allows_manual_save_but_not_autosave_or_teleport(self):
        game = self.game()
        game.save_repository = Mock()
        self.assertTrue(game._manual_save_enabled())
        game._auto_save()
        game.save_repository.save.assert_not_called()
        self.assertFalse(game._start_teleport("town", source="spell"))
        game.debug_dungeon_scene.progress.activate_fade.return_value = True
        self.assertTrue(game._activate_field_fade())

    def test_manual_save_keeps_trial_results_and_original_field_location(self):
        items = load_mock_items()
        skills = load_mock_skills()
        party = load_mock_party(items, skills)
        game = self.game()
        game.debug_dungeon_scene.progress = DungeonProgress(parse_dungeons(source())[0])
        game.debug_dungeon_scene.progress.complete()
        game.debug_dungeon_scene.progress.activate_fade()
        game.items = items
        game.skills = skills
        game.party = party
        game.character_states = {member.definition.key:member for member in party}
        game.inventory_system = InventorySystem(items)
        game.inventory_system.add("POTION", members=party)
        game.save_data.gold = 345
        game.save_data.battle_count = 7
        game.save_data.opened_treasures.add(("debug_dungeon.trial", "chest_1"))
        game.party[0].hp = 1
        from field import FieldPosition
        game.field.position = FieldPosition(3, 4)
        game.field.facing = Direction.LEFT
        with TemporaryDirectory() as directory:
            from systems import SaveRepository
            game.save_repository = SaveRepository(Path(directory))
            self.assertIsNotNone(game._save_to_slot(2))
            self.assertEqual(game.current_save_slot, 2)
            restored = restore_save_document(game.save_repository.load(2),
                character_records=load_mock_character_records(), items=items, skills=skills)
        self.assertEqual((restored.map_id, restored.position, restored.facing),
                         ("real_map", FieldPosition(3, 4), Direction.LEFT))
        self.assertEqual(restored.debug_dungeon, game.debug_dungeon_scene.progress.checkpoint())
        self.assertEqual(restored.active_party[0].hp, 1)
        self.assertEqual(restored.save_data.gold, 345)
        self.assertEqual(restored.save_data.battle_count, 7)
        self.assertIn(("debug_dungeon.trial", "chest_1"), restored.save_data.opened_treasures)

    def test_exhibition_manual_save_restriction_is_preserved(self):
        game = self.game()
        game.launch_mode = LaunchMode.EXHIBITION
        self.assertFalse(game._manual_save_enabled())

    def test_load_rejects_deleted_dungeon_before_staging_a_transition(self):
        game = self.game()
        game.character_records = ()
        game.items = {}
        game.skills = {}
        game.save_repository = Mock()
        game._load_debug_dungeons = Mock(return_value=())
        game._begin_screen_change = Mock()
        loaded = SimpleNamespace(debug_dungeon=DungeonCheckpoint("missing", "step", 0, False))
        with patch("game.restore_save_document", return_value=loaded):
            self.assertFalse(game._load_from_slot(1))
        game._begin_screen_change.assert_not_called()

    def test_load_rejects_trial_in_non_debug_modes(self):
        game = self.game()
        game.launch_mode = LaunchMode.BETA
        game.character_records = ()
        game.items = {}
        game.skills = {}
        game.save_repository = Mock()
        loaded = SimpleNamespace(debug_dungeon=DungeonCheckpoint("trial", "step", 0, False))
        with patch("game.restore_save_document", return_value=loaded):
            self.assertFalse(game._load_from_slot(1))

    def test_victory_and_escape_return_to_progress_and_preserve_original_map(self):
        for result in (BattleResult.VICTORY, BattleResult.ESCAPED):
            with self.subTest(result=result):
                game = self.game()
                simulation = game.debug_dungeon_scene
                game.battle_return_result = result
                game._apply_battle_return()
                simulation.complete_battle.assert_called_once()
                self.assertEqual(game.save_data.battle_count, int(result is BattleResult.VICTORY))
                game.encounter_system.defeat_return.assert_not_called()
                game.field.update.assert_not_called()
                game.bgm.transition_to.assert_called_once_with(simulation.dungeon.bgm_id, start_sec=12.5)
                self.assertIsNone(game.battle_scene)

    def test_defeat_exits_and_recovers_without_resolving_a_real_dungeon_exit(self):
        game = self.game()
        game.battle_return_result = BattleResult.DEFEAT
        game._apply_battle_return()
        self.assertIsNone(game.debug_dungeon_scene)
        game.party[0].fully_recover.assert_called_once()
        game.encounter_system.defeat_return.assert_not_called()
        self.assertEqual(game.current_map.map_id, "real_map")
        game.bgm.play.assert_called_once_with("original")

    def test_event_battle_stages_id_and_disables_normal_escape(self):
        game = self.game()
        game._begin_random_encounter = Mock()
        step = parse_dungeons(source())[0].steps[2]
        self.assertTrue(game._start_debug_dungeon_battle(step))
        self.assertEqual(game.pending_event_battle_id, "shrine_guard")
        self.assertFalse(game.pending_debug_battle_encounter.escape_command_enabled)
        game._begin_random_encounter.assert_called_once()

    def test_staged_battle_runs_its_registered_start_event_at_the_first_turn(self):
        game = self.game()
        encounter = BattleEncounter(("Giant Spider",), escape_command_enabled=False)
        game.encounter_transition = Mock(is_finished=True)
        game.palette_shifter = Mock()
        game.pending_debug_battle_encounter = encounter
        game.pending_event_battle_id = "shrine_guard"
        game.event_catalog = Mock()
        game.event_catalog.battle_start_event.return_value = "trial.before_guard"
        battle = Mock(is_party_command_pending=True, result=None, phase=BattlePhase.INITIAL)
        game._build_battle_scene = Mock(return_value=battle)
        game._update_encounter_transition()
        game._build_battle_scene.assert_called_once_with(encounter)
        battle.defer_first_party_command.assert_called_once()
        game._start_battle_event = Mock()
        game._update_battle_scene(InputState())
        game._start_battle_event.assert_called_once_with("trial.before_guard")
        battle.open_pending_party_command.assert_not_called()

    def test_menu_spell_and_item_overlays_disable_teleport_and_keep_fade(self):
        game = self.game()
        for name in ("command_cursor", "items", "spells", "settings", "texts", "fonts",
                     "faces", "palette_shifter", "inventory_system", "alert"):
            setattr(game, name, Mock())
        game.selected_member_index = 0
        game.menu_member_selected = True
        game._teleport_targets = Mock(side_effect=AssertionError("simulation must not offer real destinations"))
        for method, overlay in ((game._start_spell, "SpellMenuOverlay"), (game._start_item, "ItemMenuOverlay")):
            with patch(f"game.{overlay}") as factory:
                method()
                options = factory.call_args.kwargs
                self.assertEqual(options["teleport_targets"], ())
                self.assertIsNone(options["on_field_teleport"])
                self.assertEqual(options["on_field_fade"], game._activate_field_fade)

    def test_scene_menu_return_refreshes_party_without_advancing(self):
        game = self.game()
        game.pending_screen_change = GameScreenChange.SHOW_FIELD
        game.settings = Settings()
        game._apply_pending_screen_change()
        game.debug_dungeon_scene.refresh.assert_called_once()
        game.debug_dungeon_scene.complete_battle.assert_not_called()
        self.assertTrue(game.showing_field)


class DebugDungeonSelectorTest(unittest.TestCase):
    def test_reset_requires_confirmation_and_list_scrolls(self):
        fonts = FontResources()
        texts = LocalizedWindowTextFactory.from_language(fonts, Language.JAPANESE)
        d = parse_dungeons(source())[0]
        start, reset = Mock(), Mock()
        overlay = DebugDungeonOverlay(dungeons=(d,) * 12, texts=texts,
            windows=WindowFactory(fonts.font_for(Language.JAPANESE)), guide=texts.create("",4,49),
            on_start=start, on_reset=reset)
        for _ in range(10):
            overlay.update(InputState(navigation=Direction.DOWN))
        self.assertEqual(overlay.index, 10)
        self.assertEqual(len(overlay.cursor.targets), 2)
        confirm = InputState(confirm=InputButton(True,True))
        overlay.update(confirm)
        overlay.cursor.select_key("reset")
        overlay.update(confirm)
        reset.assert_not_called()
        overlay.update(confirm)  # The default choice cancels reset.
        reset.assert_not_called()
        overlay.cursor.select_key("reset")
        overlay.update(confirm)
        overlay.cursor.select_key("yes")
        overlay.update(confirm)
        reset.assert_called_once_with(d)
        start.assert_not_called()


class DebugDungeonEditorTest(unittest.TestCase):
    def test_save_validates_references_and_keeps_previous_file_on_error(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = root / "content" / "data"
            data_root.mkdir(parents=True)
            for name, key in (("items","POTION"),("monsters","Giant Spider")):
                (data_root / f"{name}.json").write_text(json.dumps([{"name_en":key}]))
            audio = root / "app" / "audio"
            audio.mkdir(parents=True)
            (audio / "da3-dungeon1.ogg").touch()
            events = root / "content" / "events"
            events.mkdir()
            (events / "battles.json").write_text(json.dumps([{"battle_id":"shrine_guard", "monster_keys":["Giant Spider"]}]))
            app = DebugDungeonEditorApplication(root / "content", root / "app", token="test")
            self.assertEqual(app.document_payload()["data"]["dungeons"], [])
            self.assertTrue(app.save(source())["saved"])
            before = app.source_path.read_bytes()
            bad = source()
            bad["dungeons"][0]["steps"][2]["battle_id"] = "unknown"
            result = app.save(bad)
            self.assertFalse(result["saved"])
            self.assertTrue(result["diagnostics"])
            self.assertEqual(app.source_path.read_bytes(), before)
            self.assertFalse(list(app.source_path.parent.glob("*.tmp")))
