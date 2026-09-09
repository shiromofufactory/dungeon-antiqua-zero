from __future__ import annotations

import unittest
from inspect import signature
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT

from game import Game
from input import InputState
from scenes import BattleEncounter, BattleResult, BattleScene


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
        encounter = BattleEncounter(("Coyote",))

        with patch("game.BattleScene.create", return_value=Mock()) as create:
            scene = game._build_battle_scene(encounter)

        self.assertIs(scene, create.return_value)
        self.assertEqual(len(create.call_args.kwargs["party"]), 5)
        self.assertIs(create.call_args.kwargs["encounter"], encounter)


if __name__ == "__main__":
    unittest.main()
