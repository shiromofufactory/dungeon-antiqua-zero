from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT  # noqa: F401 - add app to sys.path
from tools.screen_mocks._fixtures import (
    load_mock_items,
    load_mock_party,
    load_mock_skills,
    load_mock_spells,
)
from tools.screen_mocks.battle import (
    BattleMockMonster,
    BattleMockPhase,
    BattleScreenMock,
)
from monster import MonsterBattleState, MonsterCombatStats


def spellcaster(
    *,
    magic: int,
    spell_key: str,
    max_mp: int = 12,
) -> BattleMockMonster:
    return BattleMockMonster(
        key="spellcaster",
        names={"name_en": "spellcaster"},
        image_id="1",
        width=64,
        height=64,
        icon_x=0,
        icon_y=0,
        is_front_row=False,
        state=MonsterBattleState(max_hp=20, max_mp=max_mp),
        agility=12,
        magic=magic,
        spell_keys=(spell_key,),
        combat_stats=MonsterCombatStats(attack=0, hit=0, defense=0, evasion=0),
    )


def spell_scene(actor: BattleMockMonster) -> BattleScreenMock:
    items = load_mock_items()
    party = load_mock_party(
        items,
        load_mock_skills(),
        character_keys=("Fiora", "Cerion"),
    )
    mock = BattleScreenMock.__new__(BattleScreenMock)
    mock.party = party
    mock.party_visuals = tuple(SimpleNamespace(member=member) for member in party)
    mock.monsters = (actor,)
    mock.spells = load_mock_spells()
    mock.spell_effects = {}
    mock.hidden_party_indexes = set()
    mock.escaped_party_indexes = set()
    mock.phase = BattleMockPhase.MONSTER_ACTION
    mock.action_presentation = None
    mock.spell_damage_popups = []
    mock._party_draw_position = Mock(
        side_effect=lambda index: (188, 64 + index * 28)
    )
    mock._show_spell_cast_message = Mock()
    mock._show_monster_spell_mp_lack_message = Mock()
    return mock


class MonsterSpellTest(unittest.TestCase):
    def test_single_target_slow_uses_random_living_member_and_monster_magic(
        self,
    ) -> None:
        actor = spellcaster(magic=7, spell_key="SLOW")
        mock = spell_scene(actor)
        spell = mock.spells["SLOW"]

        with (
            patch("scenes.battle.random.choice", return_value=1) as choice,
            patch("scenes.battle.random.randint", return_value=0),
        ):
            self.assertTrue(mock._begin_monster_spell(actor, spell))

        choice.assert_called_once_with((0, 1))
        presentation = mock.action_presentation
        assert presentation is not None
        self.assertEqual(mock.phase, BattleMockPhase.ACTION_PRESENTATION)
        self.assertEqual(
            tuple(result.target_index for result in presentation.party_slow_results),
            (1,),
        )
        mock._apply_action_results(presentation)
        self.assertEqual(mock.party[0].speed_modifier, 0)
        self.assertEqual(mock.party[1].speed_modifier, -1)
        self.assertEqual(actor.state.mp, 10)
        mock._show_spell_cast_message.assert_called_once_with(
            spell,
            actor_is_enemy=True,
        )

    def test_all_target_sleep_applies_to_every_living_member(self) -> None:
        actor = spellcaster(magic=15, spell_key="SLEEP")
        mock = spell_scene(actor)
        spell = mock.spells["SLEEP"]

        with patch(
            "scenes.battle.random.randint",
            side_effect=(0, 2, 0, 3),
        ):
            self.assertTrue(mock._begin_monster_spell(actor, spell))

        presentation = mock.action_presentation
        assert presentation is not None
        self.assertEqual(
            tuple(
                (result.target_index, result.turns)
                for result in presentation.party_sleep_results
            ),
            ((0, 2), (1, 3)),
        )
        mock._apply_action_results(presentation)
        self.assertEqual(tuple(member.sleeping for member in mock.party), (2, 3))
        self.assertEqual(actor.state.mp, 9)

    def test_mp_shortage_is_not_filtered_by_ai_but_spell_fails_at_cast(self) -> None:
        actor = spellcaster(magic=15, spell_key="SLEEP", max_mp=2)
        mock = spell_scene(actor)
        spell = mock.spells["SLEEP"]

        self.assertEqual(mock._targetable_monster_spell_keys(actor), ("SLEEP",))
        self.assertTrue(mock._begin_monster_spell(actor, spell))

        presentation = mock.action_presentation
        assert presentation is not None
        self.assertEqual(actor.state.mp, 2)
        self.assertEqual(presentation.party_sleep_results, ())
        self.assertEqual(
            presentation.post_effect_wait_frame_count,
            24,
        )
        mock._show_monster_spell_mp_lack_message.assert_called_once_with(actor)

    def test_rear_spellcaster_can_attempt_action_without_physical_target(
        self,
    ) -> None:
        actor = spellcaster(magic=0, spell_key="SLOW")
        mock = spell_scene(actor)
        mock._monster_attack_target_indexes = Mock(return_value=())

        self.assertTrue(mock._monster_can_attempt_action(actor))


if __name__ == "__main__":
    unittest.main()
