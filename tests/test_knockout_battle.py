from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_character_records,
    load_mock_items,
    load_mock_party,
    load_mock_skills,
    load_mock_spells,
)

from battle_timeline import TimelineEntry, TimelineOrder
from debug_dungeon import DungeonStep
from game import Game
from input import Direction, InputButton, InputState
from member import EquipmentSlot, FormationRow, required_experience_for_level
from monster import MonsterSpecialAction
from rendering import PaletteShifter
from resources import BgmPlayer, FontResources, ImageResources
from resources.events import EventCatalog, EventResourceError
from scenes.battle import (
    BATTLE_BGM_ID,
    BATTLE_BOSS_BGM_ID,
    BATTLE_LEVEL_UP_BGM_ID,
    BATTLE_WIN_BGM_ID,
    BattleItemCandidate,
    BattlePhase,
    KNOCKOUT_HANDOFF_HALF_FRAMES,
)
from scripts.event_pipeline import compile_event_sources, validate_event_battles
from state import LaunchMode, SaveData, Settings
from systems import InventorySystem
from systems.party import PartySystem
from text_catalog import TextCatalog


CONFIRM = InputState(confirm=InputButton(triggered=True, held=True))
CANCEL = InputState(cancel=InputButton(triggered=True, held=True))
IDLE = InputState()
ENEMIES = ["Giant Spider", "Treant", "Bigfoot", "Coyote", "Giant Spider"]
REGISTRATION = {
    "battle_id": "tournament",
    "mode": "knockout",
    "monster_keys": ENEMIES,
    "defeat_event_id": "sample.lost",
}
SOURCES = {"events": {"format_version": 1, "events": [
    {"id": "sample.challenge", "commands": [
        {"command": "start_battle", "battle_id": "tournament"},
        {"command": "set_flag", "flag_id": "sample.won"},
    ]},
    {"id": "sample.lost", "commands": [
        {"command": "set_flag", "flag_id": "sample.lost"},
    ]},
]}}


def catalog_document():
    return compile_event_sources(
        SOURCES, battles=[REGISTRATION], monster_keys=set(ENEMIES),
        flag_ids=["sample.won", "sample.lost"],
    )


class KnockoutBattleTest(unittest.TestCase):
    def setUp(self):
        for target in ("scenes.battle.play_se", "ui.battle_result.play_se"):
            sound = patch(target)
            sound.start()
            self.addCleanup(sound.stop)
        game = self.game = Game.__new__(Game)
        game.items = load_mock_items()
        skills = load_mock_skills()
        game.spells = load_mock_spells()
        game.character_records = load_mock_character_records()
        game.party = load_mock_party(game.items, skills)
        game.party_system = PartySystem(
            active_party=game.party, character_records=game.character_records,
            items=game.items, skills=skills,
        )
        game.character_states = game.party_system.character_states
        game.inventory_system = InventorySystem(game.items, {"POTION": 2})
        game.settings = Settings()
        game.fonts = FontResources()
        game.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        game.event_catalog = EventCatalog.from_document(catalog_document())
        game.save_data = SaveData()
        game.launch_mode = LaunchMode.NORMAL
        game.selected_member_index = 0
        game.alert = Mock()
        game.bgm = Mock(current_id=None)
        game.images = Mock(spec=ImageResources)
        game.images.entry.return_value = SimpleNamespace(width=256, height=240)
        game.palette_shifter = Mock(spec=PaletteShifter, base_colors=tuple(range(16)))
        game.current_map = SimpleNamespace(bgm_id="da3-field")
        game.map_resources = Mock()
        game.field = Mock()
        game.encounter_system = Mock()
        game.encounter_system.defeat_return.return_value = None
        game._begin_random_encounter = Mock()
        game._restore_dimmed_palette = Mock()
        game._show_hint_once = Mock()

    def _start_challenge(self):
        game = self.game
        self.assertTrue(game._start_field_event("sample.challenge"))
        order = game.knockout_order
        game._update_knockout_order(InputState(navigation=Direction.DOWN))
        for _ in order.candidates:
            game._update_knockout_order(CONFIRM)
        game._update_knockout_order(CONFIRM)
        game.encounter_transition = Mock(
            is_finished=True, palette_base_rate=0.0, palette_target_color=0,
        )
        game._update_encounter_transition()
        return game.battle_scene

    def _show_current_round_result(self):
        game = self.game
        scene = game.battle_scene
        scene.monsters[0].state.defeat()
        scene.progression.record_enemy_defeat(0)
        with patch("systems.battle_progression.random.randrange", return_value=15):
            scene._begin_victory_summary()
        for _ in range(45):
            game._update_battle_scene(IDLE)
        self.assertIs(scene.phase, BattlePhase.VICTORY_SUMMARY)
        game._update_battle_scene(CONFIRM)
        for _ in range(80):
            game._update_battle_scene(IDLE)
        self.assertIs(scene.phase, BattlePhase.RESULT)

    def _close_current_round_result(self):
        game = self.game
        game._update_battle_scene(CONFIRM)
        self.assertIsNotNone(game.battle_return_fade)
        for _ in range(30):
            if game.battle_return_fade is None:
                break
            game._update_battle_return(IDLE)

    def _win_current_round(self):
        self._show_current_round_result()
        self._close_current_round_result()

    def test_catalog_round_trip_preserves_order_and_requires_five_enemies(self):
        document = catalog_document()
        catalog = EventCatalog.from_document(document)
        self.assertTrue(catalog.is_knockout_battle("tournament"))
        self.assertEqual(catalog.battle_monster_keys("tournament"), tuple(ENEMIES))
        self.assertEqual(catalog.battle_defeat_event("tournament"), "sample.lost")
        for mode, lineup, code in (
            ("knockout", ENEMIES[:4], "invalid_monster_lineup"),
            ("sequence", ENEMIES, "invalid_battle_mode"),
        ):
            issues = validate_event_battles(
                [{**REGISTRATION, "mode": mode, "monster_keys": lineup}],
                monster_keys=ENEMIES, field_event_ids=["sample.lost"],
            )
            self.assertEqual([issue.code for issue in issues], [code])
        with self.assertRaises(EventResourceError):
            EventCatalog.from_document({**document, "knockout_battles": ["missing"]})
        del document["knockout_battles"]
        self.assertFalse(EventCatalog.from_document(document).is_knockout_battle("tournament"))

    def test_order_selects_only_available_non_reserves_and_supports_cancellation(self):
        game = self.game
        party = game.party
        party[1].hp = 0
        party[3].paralyzed = True
        game._start_field_event("sample.challenge")
        order = game.knockout_order
        self.assertEqual(order.candidates, (party[0], party[2], party[4]))
        game._update_knockout_order(CONFIRM)
        game._update_knockout_order(CANCEL)
        self.assertEqual(order.order, [])
        game._update_knockout_order(CANCEL)
        self.assertIsNone(game.event_runner)
        self.assertEqual(game.save_data.event_flags, set())
        game._begin_random_encounter.assert_not_called()
        for member in party[:5]:
            member.hp = 0
        self.assertTrue(game._start_field_event("sample.challenge"))
        self.assertFalse(game.knockout_order.candidates)
        game._update_knockout_order(CONFIRM)
        self.assertIsNone(game.event_runner)
        game._begin_random_encounter.assert_not_called()

    def test_five_victories_keep_the_fighter_and_resume_once_after_the_final_result(self):
        game = self.game
        scene = self._start_challenge()
        fighter = game.party[1]
        fighter.hp -= 5
        fighter.mp = 1
        fighter.silenced = 2
        self.assertIs(fighter.formation_row, FormationRow.BACK)
        self.assertTrue(scene._party_member_is_front_row(0))
        expected_hp = fighter.hp
        for index, key in enumerate(ENEMIES, start=1):
            with self.subTest(round=index):
                self.assertEqual(game.battle_scene.party, (fighter,))
                self.assertEqual(tuple(m.key for m in game.battle_scene.monsters), (key,))
                actions = game.battle_scene.monsters[0].special_actions
                self.assertNotIn(MonsterSpecialAction.CALL, actions)
                self.assertNotIn(MonsterSpecialAction.REINFORCE, actions)
                self._win_current_round()
                self.assertEqual(game.save_data.battle_count, index)
                self.assertEqual((fighter.hp, fighter.mp, fighter.silenced), (expected_hp, 1, 0))
                self.assertEqual(game.save_data.event_flags, {"sample.won"} if index == 5 else set())
        self.assertIsNone(game.battle_scene)
        self.assertIsNone(game.event_battle_id)
        self.assertIs(fighter.formation_row, FormationRow.BACK)

    def test_debug_trial_uses_the_same_order_and_can_return_to_preparation(self):
        game = self.game
        simulation = game.debug_dungeon_scene = Mock()
        challenge = DungeonStep(id="challenge", type="event_battle", battle_id="tournament")
        self.assertTrue(game._start_debug_dungeon_battle(challenge))
        self.assertEqual(game.knockout_order.candidates, game.party[:5])
        game._update_knockout_order(CANCEL)
        simulation.cancel_battle.assert_called_once_with()
        game._begin_random_encounter.assert_not_called()
        self.assertIsNone(game.event_battle_id)

        self.assertTrue(game._start_debug_dungeon_battle(challenge))
        for _ in range(6):
            game._update_knockout_order(CONFIRM)
        self.assertEqual(game.pending_debug_battle_encounter.monster_keys, (ENEMIES[0],))
        self.assertEqual(game.knockout_enemy_keys, tuple(ENEMIES[1:]))
        self.assertEqual(game.knockout_party, game.party[:5])
        game._begin_random_encounter.assert_called_once_with()

    def test_result_growth_excludes_waiting_members_and_the_reserve(self):
        game = self.game
        game.save_data.experience = required_experience_for_level(2) - 1
        scene = self._start_challenge()
        fighter, = scene.party
        self.assertEqual(fighter.definition.key, "Cerion")
        for member in game.party:
            member.hp = member.max_hp = 1
            self.assertGreater(member.calculated_max_hp(), 1)

        self._show_current_round_result()

        self.assertGreater(fighter.max_hp, 1)
        self.assertGreaterEqual(game.save_data.experience, required_experience_for_level(2))
        self.assertGreater(
            scene.growth_result.after[0].internal_level,
            scene.growth_result.before[0].internal_level,
        )
        for index, (member, before, after) in enumerate(zip(
            game.party, scene.growth_result.before, scene.growth_result.after,
        )):
            self.assertEqual(member.hp, 1)
            if member is not fighter:
                self.assertEqual(after.max_hp, before.max_hp)
                self.assertEqual(after.max_mp, before.max_mp)
                self.assertEqual(after.proficiencies, before.proficiencies)
            self.assertEqual(scene.result_overlay.celebrating_members[index], member is fighter)

    def test_growth_uses_the_fighters_for_each_opponent_after_an_ally_handoff(self):
        game = self.game
        scene = self._start_challenge()
        first_fighter, = scene.party
        for member in game.party:
            member.max_hp = 999
        first_fighter.hp = first_fighter.max_hp = 1
        first_fighter.paralyzed = True
        scene._activate_timeline_head()
        self.assertIs(scene.phase, BattlePhase.KNOCKOUT_HANDOFF)
        for _ in range(2 * KNOCKOUT_HANDOFF_HALF_FRAMES):
            scene.update(IDLE)
        self.assertEqual(scene.party, (game.party[0],))

        self._win_current_round()
        self.assertGreater(first_fighter.max_hp, 1)

        first_fighter.max_hp = 1
        self._show_current_round_result()
        self.assertEqual(first_fighter.max_hp, 1)

    def test_result_plays_next_battle_or_field_bgm_and_keeps_playback_on_transition(self):
        from tests.test_audio_resources import FakePyxel

        game = self.game
        px = FakePyxel()
        game.bgm = BgmPlayer(APP_ROOT / "audio", pyxel_api=px)
        game.pending_battle_bgm_start_sec = 12.5
        scene = self._start_challenge()
        self.assertEqual(game.bgm.current_id, BATTLE_BGM_ID)
        fighter, = scene.party
        fighter.hp = fighter.max_hp = 1
        successors = (
            BATTLE_BOSS_BGM_ID, BATTLE_BGM_ID, BATTLE_BGM_ID, BATTLE_BGM_ID, "da3-field",
        )
        for index, successor in enumerate(successors):
            self._show_current_round_result()
            jingle = BATTLE_LEVEL_UP_BGM_ID if index == 0 else BATTLE_WIN_BGM_ID
            self.assertEqual(game.bgm.current_id, jingle)
            px.play_position = None
            self.assertTrue(game.bgm.update())
            self.assertEqual(game.bgm.current_id, successor)
            expected_start = 12.5 if successor == "da3-field" else 0.0
            self.assertEqual(px.play_calls[-1][2:], (expected_start, True))
            play_count = len(px.play_calls)
            stop_count = len(px.stop_calls)
            self._close_current_round_result()
            self.assertEqual(game.bgm.current_id, successor)
            self.assertEqual(len(px.play_calls), play_count)
            self.assertEqual(len(px.stop_calls), stop_count)
            fighter.max_hp = 999

    def test_death_and_paralysis_swap_in_place_then_team_defeat_refunds_since_last_win(self):
        game = self.game
        for member in game.party[3:5]:
            member.paralyzed = True
        scene = self._start_challenge()
        potion = BattleItemCandidate(game.items["POTION"])
        scene.active_party_index = 0
        self.assertTrue(scene._commit_item_use(potion))
        self._win_current_round()
        first_reward = game.save_data.gold
        self.assertGreater(first_reward, 0)

        scene = game.battle_scene
        scene.active_party_index = 0
        self.assertTrue(scene._commit_item_use(potion))
        ring = game.items["TELEPORT RING"]
        fighter = scene.party[0]
        fighter.equipment = fighter.equipment.replaced({EquipmentSlot.ARM: ring})
        self.assertFalse(scene._item_is_usable_in_battle(ring))
        self.assertTrue(scene._commit_item_use(BattleItemCandidate(ring, EquipmentSlot.ARM)))
        monster = scene.monsters[0]
        monster.state.hp = 7
        monster.state.mp = 3
        monster.state.poisoned = True
        monster.state.action_rotation_index = 1

        def party_first(combatants):
            return TimelineOrder(tuple(
                TimelineEntry(actor, agility, 64.0 - index)
                for index, (actor, agility) in enumerate(combatants)
            ))

        for defeated, entrant in ((game.party[1], game.party[0]), (game.party[0], game.party[2])):
            if defeated is game.party[1]:
                scene.monster_attack_target_index = 0
                scene.monster_attack_damage = defeated.hp
                scene._finish_monster_attack()
                self.assertTrue(defeated.is_dead)
            else:
                defeated.paralyzed = True
                scene._activate_timeline_head()
            self.assertIs(scene.phase, BattlePhase.KNOCKOUT_HANDOFF)
            self.assertEqual(scene.party, (defeated,))
            with patch("scenes.battle.initialize_timeline_order", side_effect=party_first):
                for _ in range(2 * KNOCKOUT_HANDOFF_HALF_FRAMES):
                    scene.update(IDLE)
            self.assertIs(game.battle_scene, scene)
            self.assertEqual(scene.party, (entrant,))
            self.assertIs(scene.monsters[0], monster)
            self.assertEqual((monster.state.hp, monster.state.mp), (7, 3))
            self.assertTrue(monster.state.poisoned)
            self.assertEqual(monster.state.action_rotation_index, 1)
            self.assertEqual(game.inventory_system.quantity("POTION"), 0)
            self.assertIsNone(fighter.equipment.item_at(EquipmentSlot.ARM))
            self.assertEqual(game.save_data.event_flags, set())

        game.party[2].hp = 0
        scene._begin_defeat_message()
        self.assertIs(scene.phase, BattlePhase.DEFEAT_MESSAGE)
        game._update_battle_scene(CONFIRM)
        with patch("game.play_se"), patch("game.pyxel.play_pos", return_value=None):
            for _ in range(30):
                if game.battle_return_fade is None:
                    break
                game._update_battle_return(IDLE)
        self.assertEqual(game.save_data.event_flags, {"sample.lost"})
        self.assertEqual(game.save_data.gold, first_reward)
        self.assertEqual(game.save_data.battle_count, 1)
        self.assertEqual(game.inventory_system.quantity("POTION"), 1)
        self.assertEqual(fighter.equipment.item_at(EquipmentSlot.ARM), ring)
        self.assertIsNone(game.battle_scene)
