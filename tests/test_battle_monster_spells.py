from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

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
from monster_ai import MonsterSpellAction
from battle_magic import resolve_spell_damage, SpellAffinity
from member import Member
from resistance import ResistanceType


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
    mock._refresh_party_hp_text = Mock()
    mock._show_spell_cast_message = Mock()
    mock._show_monster_spell_mp_lack_message = Mock()
    mock._show_monster_spell_sealed_message = Mock()
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

    def test_second_slow_on_same_member_shows_miss(self) -> None:
        actor = spellcaster(magic=7, spell_key="SLOW")
        mock = spell_scene(actor)
        spell = mock.spells["SLOW"]
        target = mock.party[1]

        with (
            patch("scenes.battle.random.choice", return_value=1),
            patch("scenes.battle.random.randint", return_value=0) as randint,
        ):
            self.assertTrue(mock._begin_monster_spell(actor, spell))
            assert mock.action_presentation is not None
            mock._apply_action_results(mock.action_presentation)
            self.assertEqual(target.speed_modifier, -1)

            self.assertTrue(mock._begin_monster_spell(actor, spell))
            presentation = mock.action_presentation
            assert presentation is not None
            self.assertFalse(presentation.party_slow_results[0].success)
            self.assertEqual(presentation.spell_effects, ())
            mock._apply_action_results(presentation)
            randint.assert_called_once_with(0, 19)

        self.assertEqual(target.speed_modifier, -1)
        self.assertEqual([popup.is_miss for popup in mock.spell_damage_popups], [True])
        self.assertEqual(actor.state.mp, 8)

    def test_break_cancels_all_protection_then_applies_defense_down(self) -> None:
        actor = spellcaster(magic=7, spell_key="ARMOR BREAK")
        mock = spell_scene(actor)
        spell = mock.spells["ARMOR BREAK"]
        target = mock.party[0]
        target.protection_level = 2
        self.assertGreater(target.battle_stats.defense, 0)

        with (
            patch("scenes.battle.random.choice", return_value=0),
            patch("scenes.battle.random.randint", return_value=0),
        ):
            self.assertTrue(mock._begin_monster_spell(actor, spell))
        assert mock.action_presentation is not None
        mock._apply_action_results(mock.action_presentation)
        self.assertEqual(target.protection_level, 0)

        with (
            patch("scenes.battle.random.choice", return_value=0),
            patch("scenes.battle.random.randint", return_value=0),
        ):
            self.assertTrue(mock._begin_monster_spell(actor, spell))
        assert mock.action_presentation is not None
        mock._apply_action_results(mock.action_presentation)

        self.assertEqual(target.protection_level, -1)
        self.assertEqual(actor.state.mp, 6)

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

    def test_confuse_replaces_sleep_on_the_selected_member(self) -> None:
        actor = spellcaster(magic=15, spell_key="CONFUSION")
        mock = spell_scene(actor)
        spell = mock.spells["CONFUSION"]
        mock.party[1].apply_sleep(2)

        with (
            patch("scenes.battle.random.choice", return_value=1),
            patch("scenes.battle.random.randint", side_effect=(0, 3)),
        ):
            self.assertTrue(mock._begin_monster_spell(actor, spell))

        presentation = mock.action_presentation
        assert presentation is not None
        self.assertEqual(
            tuple(
                (result.target_index, result.turns)
                for result in presentation.party_confuse_results
            ),
            ((1, 3),),
        )
        mock._apply_action_results(presentation)
        self.assertEqual(mock.party[1].sleeping, 0)
        self.assertEqual(mock.party[1].confused, 3)
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

    def test_silenced_monster_spell_fails_without_spending_mp(self) -> None:
        actor = spellcaster(magic=15, spell_key="SLEEP")
        actor.state.apply_silence(4)
        mock = spell_scene(actor)
        mock.command_window = Mock()
        mock.timeline = (actor,)
        mock.monster_charge_presentation = None
        mock.monster_escape_actor_index = None
        mock.monster_attack_target_index = None
        mock.monster_blink_frames_remaining = 1
        mock.blinking_monster_index = 0
        mock.progression = Mock()
        mock._select_monster_action = Mock(
            return_value=MonsterSpellAction("SLEEP")
        )
        mock._start_timeline_animation = Mock()

        mock._update_monster_action()

        self.assertEqual(actor.state.mp, 12)
        self.assertEqual(actor.state.silenced, 3)
        presentation = mock.action_presentation
        assert presentation is not None
        self.assertEqual(presentation.party_sleep_results, ())
        self.assertEqual(presentation.post_effect_wait_frame_count, 24)
        mock._show_monster_spell_sealed_message.assert_called_once_with()
        mock._show_monster_spell_mp_lack_message.assert_not_called()
        mock.progression.record_enemy_action.assert_called_once_with(0)

    def test_rear_spellcaster_can_attempt_action_without_physical_target(
        self,
    ) -> None:
        actor = spellcaster(magic=0, spell_key="SLOW")
        mock = spell_scene(actor)
        mock._monster_attack_target_indexes = Mock(return_value=())

        self.assertTrue(mock._monster_can_attempt_action(actor))


class MonsterDamageSpellTest(unittest.TestCase):
    def test_fire_and_freeze_use_shared_damage_rule_and_apply_once_at_result_time(self):
        for key in ("FIRE1", "FREEZE1"):
            with self.subTest(spell=key):
                actor = spellcaster(magic=2, spell_key=key)
                scene = spell_scene(actor)
                spell = scene.spells[key]
                target = scene.party[1]
                hp = target.hp
                target.apply_sleep(2)
                expected = resolve_spell_damage(
                    intensity=spell.intensity, spell_modifier=actor.magic,
                    target_spell_defense=target.battle_stats.spell_resistance,
                    attribute=spell.attribute, target_weaknesses=frozenset(),
                    target_resistances=target.resistances, random_factor=0.5,
                )
                with (
                    patch("scenes.battle.random.choice", return_value=1),
                    patch("scenes.battle.random.random", return_value=0.5),
                ):
                    scene._begin_monster_spell(actor, spell)
                presentation = scene.action_presentation
                self.assertEqual(target.hp, hp)
                self.assertEqual(presentation.party_damage_results[0].damage, expected.damage)
                self.assertEqual(actor.state.mp, actor.state.max_mp - spell.mp)
                scene._update_action_presentation()
                self.assertEqual(target.hp, max(0, hp - expected.damage))
                self.assertEqual(target.sleeping, 0)
                scene._refresh_party_hp_text.assert_called_once_with(1)
                self.assertEqual(scene.spell_damage_popups[0].damage, expected.damage)
                scene._apply_action_results(presentation)
                self.assertEqual(len(scene.spell_damage_popups), 1)
                self.assertEqual(target.hp, max(0, hp - expected.damage))

    def test_damage_waits_for_presentation_result_frame(self):
        actor = spellcaster(magic=3, spell_key="FIRE1")
        scene = spell_scene(actor)
        with patch("scenes.battle.random.choice", return_value=0):
            scene._begin_monster_spell(actor, scene.spells["FIRE1"])
        scene.action_presentation.result_start_frame = 3
        hp = scene.party[0].hp
        for _ in range(2):
            scene._update_action_presentation()
            self.assertEqual(scene.party[0].hp, hp)
            self.assertEqual(scene.spell_damage_popups, [])
        scene._update_action_presentation()
        self.assertLess(scene.party[0].hp, hp)
        self.assertEqual(len(scene.spell_damage_popups), 1)

    def test_all_targets_exclude_dead_hidden_and_escaped_members(self):
        actor = spellcaster(magic=3, spell_key="FIRE1")
        for excluded in ("dead", "hidden", "escaped", None):
            with self.subTest(excluded=excluded):
                scene = spell_scene(actor)
                if excluded == "dead":
                    scene.party[1].hp = 0
                elif excluded == "hidden":
                    scene.hidden_party_indexes.add(1)
                elif excluded == "escaped":
                    scene.escaped_party_indexes.add(1)
                with patch("scenes.battle.random.random", return_value=0.5) as roll:
                    scene._begin_monster_spell(actor, replace(scene.spells["FIRE1"], to_all=True))
                results = scene.action_presentation.party_damage_results
                self.assertEqual(tuple(r.target_index for r in results), (0, 1) if excluded is None else (0,))
                self.assertEqual(roll.call_count, len(results))

    def test_elemental_resistance_reduces_damage_and_displays_affinity(self):
        actor = spellcaster(magic=8, spell_key="FREEZE1")
        scene = spell_scene(actor)
        with (
            patch.object(Member, "resistances", new_callable=PropertyMock,
                         return_value=frozenset({ResistanceType.FREEZE})),
            patch("scenes.battle.random.choice", return_value=0),
            patch("scenes.battle.random.random", return_value=0.5),
        ):
            scene._begin_monster_spell(actor, scene.spells["FREEZE1"])
        result = scene.action_presentation.party_damage_results[0]
        self.assertIs(result.affinity, SpellAffinity.RESIST)
        self.assertEqual(len(scene.affinity_popups), 1)
        self.assertIs(scene.affinity_popups[0].affinity, SpellAffinity.RESIST)
        normal = resolve_spell_damage(
            intensity=40, spell_modifier=8,
            target_spell_defense=scene.party[0].battle_stats.spell_resistance,
            attribute=ResistanceType.FREEZE, target_weaknesses=frozenset(),
            target_resistances=frozenset(), random_factor=0.5,
        )
        self.assertLess(result.damage, normal.damage)

    def test_lethal_damage_clears_conditions_and_interrupts_focus(self):
        actor = spellcaster(magic=99, spell_key="FREEZE1")
        scene = spell_scene(actor)
        target = scene.party[0]
        target.apply_confusion(3)
        scene.focused_target_by_party_index = {0: 0}
        with patch("scenes.battle.random.choice", return_value=0):
            scene._begin_monster_spell(actor, scene.spells["FREEZE1"])
        scene._apply_action_results(scene.action_presentation)
        self.assertEqual(target.hp, 0)
        self.assertEqual(target.confused, 0)
        self.assertNotIn(0, scene.focused_target_by_party_index)

    def test_zero_damage_keeps_conditions_and_hp(self):
        actor = spellcaster(magic=0, spell_key="FIRE1")
        scene = spell_scene(actor)
        target = scene.party[0]
        target.apply_sleep(2)
        hp = target.hp
        with patch("scenes.battle.random.choice", return_value=0):
            scene._begin_monster_spell(actor, scene.spells["FIRE1"])
        scene._apply_action_results(scene.action_presentation)
        self.assertEqual((target.hp, target.sleeping), (hp, 2))
        self.assertEqual(scene.spell_damage_popups[0].damage, 0)

    def test_mp_shortage_and_silence_prevent_damage_and_mp_consumption(self):
        for silenced in (False, True):
            with self.subTest(silenced=silenced):
                actor = spellcaster(magic=99, spell_key="FREEZE1", max_mp=2)
                scene = spell_scene(actor)
                hp = tuple(m.hp for m in scene.party)
                scene._begin_monster_spell(actor, scene.spells["FREEZE1"], silenced=silenced)
                scene._apply_action_results(scene.action_presentation)
                self.assertEqual(tuple(m.hp for m in scene.party), hp)
                self.assertEqual(actor.state.mp, 2)
                self.assertEqual(scene.action_presentation.party_damage_results, ())


if __name__ == "__main__":
    unittest.main()
