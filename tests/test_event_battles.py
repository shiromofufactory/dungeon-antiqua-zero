from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from tools._bootstrap import APP_ROOT
from debug_dungeon import parse_dungeons
from game import Game
from resources.events import EventCatalog, EventResourceError
from scripts.event_pipeline import compile_event_sources, validate_event_sources
from scripts.event_pipeline.battles import validate_event_battles
from systems.events import StartBattleEffect
from tools.event_editor.server import EventEditorApplication


BATTLES = [{"battle_id": "guard", "note": "共通の門番", "monster_keys": ["SLIME", "SLIME"]}]
SOURCE = {"events": {"format_version": 1, "events": [
    {"id": "sample.first", "commands": [{"command": "start_battle", "battle_id": "guard"}]},
    {"id": "sample.second", "commands": [{"command": "start_battle", "battle_id": "guard"}]},
]}}


class EventBattleTest(unittest.TestCase):
    def test_one_registration_is_resolved_by_both_events_and_trial(self):
        for lineup in (["SLIME", "SLIME"], ["BAT"]):
            battles = [{**BATTLES[0], "monster_keys": lineup}]
            compiled = compile_event_sources(SOURCE, battles=battles, monster_keys={"SLIME", "BAT"})
            catalog = EventCatalog.from_document(compiled)
            self.assertEqual(catalog.battle_ids, ("guard",))
            self.assertEqual(compiled["battles"], {"guard": lineup})
            for event in compiled["events"].values():
                self.assertEqual(event["commands"], [{"command":"start_battle", "battle_id":"guard"}])
            dungeon = parse_dungeons({"format_version":1,"dungeons":[{
                "id":"trial", "name":"調整用", "bgm_id":"field", "steps":[{
                    "id":"boss", "type":"event_battle", "battle_id":"guard",
                }],
            }]}, battle_ids=catalog.battle_ids)[0]
            game = Game.__new__(Game)
            game.event_catalog = catalog
            game._begin_random_encounter = Mock()
            game.event_runner = Mock()
            game.suspended_field_event = None
            game._begin_event_battle(StartBattleEffect("guard"))
            self.assertEqual(game.pending_event_battle_encounter.monster_keys, tuple(lineup))
            game._start_debug_dungeon_battle(dungeon.steps[0])
            self.assertEqual(game.pending_debug_battle_encounter.monster_keys, tuple(lineup))
            self.assertFalse(game.pending_debug_battle_encounter.escape_command_enabled)

    def test_duplicate_empty_unknown_and_oversized_registrations_are_rejected(self):
        cases = [
            (BATTLES * 2, "duplicate_battle_id"),
            ([{**BATTLES[0], "monster_keys": []}], "invalid_monster_lineup"),
            ([{**BATTLES[0], "monster_keys": ["unknown"]}], "unknown_monster"),
            ([{**BATTLES[0], "monster_keys": ["TREANT"] * 5}], "oversized_monster_lineup"),
        ]
        for battles, code in cases:
            with self.subTest(code=code):
                issues = validate_event_battles(battles, monster_keys={"SLIME", "TREANT"}, tall_first_monster_keys={"TREANT"})
                self.assertIn(code, {issue.code for issue in issues})

    def test_unknown_reference_and_inline_lineup_are_rejected(self):
        self.assertIn("unknown_battle", {issue.code for issue in validate_event_sources(SOURCE)})
        source = deepcopy(SOURCE)
        source["events"]["events"][0]["commands"][0]["monster_keys"] = ["SLIME"]
        self.assertIn("unknown_field", {issue.code for issue in validate_event_sources(source, battles=BATTLES, monster_keys={"SLIME"})})
        compiled = compile_event_sources(SOURCE, battles=BATTLES, monster_keys={"SLIME"})
        del compiled["battles"]["guard"]
        with self.assertRaises(EventResourceError):
            EventCatalog.from_document(compiled)

    def test_changing_only_the_lineup_changes_the_generated_hash(self):
        first = compile_event_sources(SOURCE, battles=BATTLES, monster_keys={"SLIME"})
        second = compile_event_sources(SOURCE, battles=[{**BATTLES[0],"monster_keys":["SLIME"]}], monster_keys={"SLIME"})
        self.assertNotEqual(first["source_sha256"], second["source_sha256"])

    def test_trial_reference_prevents_deleting_a_used_registration(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "content" / "data"
            data.mkdir(parents=True)
            for name in ("characters", "items", "monsters", "shops"):
                (data / f"{name}.json").write_text("[]")
            audio = root / "app" / "audio"
            audio.mkdir(parents=True)
            (audio / "catalog.json").write_text('{"format_version":2,"sound_effects":{"confirm":{"sound":9}}}')
            debug = root / "app" / "debug"
            debug.mkdir()
            (debug / "dungeons.json").write_text(json.dumps({"dungeons":[{"id":"trial","steps":[{
                "id":"boss", "type":"event_battle", "battle_id":"guard",
            }]}]}))
            app = EventEditorApplication(root / "content", root / "app" / "events" / "events.json", app_root=root / "app")
            issues = app.validate({"format_version":1,"events":[]}, [], [], [], [])
            self.assertIn("referenced_debug_battle", {issue["code"] for issue in issues})
            self.assertFalse(app.save({"format_version":1,"events":[]}, [], [], [], [])["saved"])
            self.assertFalse(app.source_path.exists())
