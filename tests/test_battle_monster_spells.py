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
    BattleMockCharacter,
    BattleMockPhase,
    BattleScreenMock,
)
from monster import MonsterBattleState, MonsterCombatStats
from monster_ai import MonsterAction, MonsterSpellAction
from battle_magic import resolve_healing, resolve_spell_damage, SpellAffinity
from member import EquipmentSlot, Member, FormationRow
from battle_timeline import TimelineEntry, TimelineOrder
from resources import load_record_array
from resistance import ResistanceType
from scenes.battle import BattleMonster
from spell_effect import load_spell_effects


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
    def test_screen_flash_from_spell_catalog_runs_once_for_all_targets(self):
        actor = spellcaster(magic=40, spell_key="SLEEP")
        scene = spell_scene(actor)
        definition = load_spell_effects(APP_ROOT / "effects" / "spells.json")["SLEEP"]
        scene.spell_effects = {
            "SLEEP": replace(definition, flash_scope="screen", flash_color=57, se_id=None)
        }
        scene.spell_effect_renderer = Mock()
        with patch("scenes.battle.random.randint", return_value=2):
            self.assertTrue(scene._begin_monster_spell(actor, scene.spells["SLEEP"]))
        presentation = scene.action_presentation
        self.assertEqual([effect.target_index for effect in presentation.spell_effects], [0, 1])
        self.assertEqual(presentation.screen_flash.color_index, 57)
        scene._update_action_presentation()
        scene.spell_effect_renderer.prepare_screen_flash.assert_called_once_with(
            presentation.screen_flash, 1
        )

    def test_priest_protection_cancels_defense_down_and_gives_effective_defense(self):
        record = next(r for r in load_record_array("monsters.json") if r["name_en"] == "Priest")
        actor = BattleMonster.from_record(record, is_front_row=True)
        actor.state.apply_defense_down(5)
        scene = spell_scene(actor)
        spell = scene.spells["PROTECTION"]
        for old_stage, expected_defense in ((-1, 8), (0, 16), (1, 27)):
            self.assertIn(spell.key, actor.spell_keys)
            self.assertEqual(scene._evaluate_monster_spell(actor, spell, is_solo=True).targets, (0,))
            self.assertTrue(scene._begin_monster_spell(actor, spell))
            self.assertEqual(actor.state.defense_modifier, old_stage)
            scene._update_action_presentation()
            self.assertEqual(actor.state.defense_modifier, old_stage + 1)
            self.assertEqual(actor.state.defense_down_turns, 0)
            self.assertEqual(actor.effective_defense, expected_defense)
        self.assertEqual(actor.state.mp, 1)
        self.assertEqual(scene._monster_spell_target_indexes(spell), ())
        self.assertTrue(actor.state.apply_defense_down(5, armor_break=True))
        self.assertEqual((actor.state.defense_modifier, actor.state.defense_down_turns), (0, 0))

    def test_monster_heal_uses_magic_and_observes_actual_hp_recovered(self):
        actor = spellcaster(magic=14, spell_key="HEALING1")
        target = spellcaster(magic=0, spell_key="HASTE")
        target.state.take_damage(3)
        target.state.apply_poison()
        defeated = spellcaster(magic=0, spell_key="HASTE")
        defeated.state.defeat()
        scene = spell_scene(actor)
        scene.monsters = (actor, target, defeated)
        scene.auto_battle_observations = Mock()
        spell = scene.spells["HEALING1"]
        expected = resolve_healing(
            intensity=spell.intensity, ability=14, current_hp=17, max_hp=20,
            random_factor=0.5,
        ).amount
        self.assertEqual(scene._monster_spell_target_indexes(spell), (1,))
        with patch("scenes.battle.random.random", return_value=0.5):
            self.assertTrue(scene._begin_monster_spell(actor, spell))
        self.assertEqual(target.state.hp, 17)
        self.assertEqual(actor.state.mp, 12 - spell.mp)
        presentation = scene.action_presentation
        scene._update_action_presentation()
        scene._apply_action_results(presentation)
        self.assertEqual(target.state.hp, 20)
        self.assertTrue(target.state.poisoned)
        self.assertEqual(scene.healing_popups[0].amount, expected)
        scene.auto_battle_observations.damage.assert_called_once_with(1, -3)
        self.assertFalse(scene._begin_monster_spell(actor, spell))

    def test_poltergeist_haste_uses_speed_stages_without_moving_waiting_target(self):
        record = next(r for r in load_record_array("monsters.json") if r["name_en"] == "Poltergeist")
        actor = BattleMonster.from_record(record, is_front_row=True)
        target = spellcaster(magic=0, spell_key="HASTE")
        target.state.apply_slow()
        actor.state.speed_modifier = 2
        scene = spell_scene(actor)
        scene.monsters = (actor, target)
        order = TimelineOrder((
            TimelineEntry(actor, actor.agility, 64),
            TimelineEntry(target, target.agility, 50),
        ))
        scene._timeline_order = order
        spell = scene.spells["HASTE"]
        for expected in (0, 1, 2):
            self.assertEqual(scene._monster_spell_target_indexes(spell), (1,))
            self.assertTrue(scene._begin_monster_spell(actor, spell))
            self.assertEqual(target.state.speed_modifier, expected - 1)
            scene._update_action_presentation()
            self.assertEqual(target.state.speed_modifier, expected)
            self.assertEqual(target.state.slow_turns, 0)
            self.assertEqual(target.effective_agility, target.agility + expected * 8)
            self.assertIs(scene._timeline_order, order)
            self.assertEqual(actor.state.mp, 0)
            actor.state.mp = actor.state.max_mp
        self.assertFalse(scene._begin_monster_spell(actor, spell))
        self.assertEqual(actor.state.mp, 4)

    def test_single_target_slow_uses_random_living_member_and_monster_magic(
        self,
    ) -> None:
        actor = spellcaster(magic=7, spell_key="SLOW")
        mock = spell_scene(actor)
        spell = mock.spells["SLOW"]
        visuals = tuple(BattleMockCharacter(member, 0, 0, index) for index, member in enumerate(mock.party))
        mock._timeline_order = TimelineOrder((
            TimelineEntry(actor, actor.agility, 64),
            TimelineEntry(visuals[1], visuals[1].agility, 60),
            TimelineEntry(visuals[0], visuals[0].agility, 56),
        ))
        mock.timeline = mock._timeline_order.actors

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
        self.assertEqual(mock.party[1].effective_agility, max(1, mock.party[1].adjusted_abilities.agility - 8))
        self.assertEqual(mock.timeline, (actor, visuals[0], visuals[1]))
        self.assertEqual(tuple(entry.gauge for entry in mock._timeline_order.entries), (64, 56, 52))
        mock._apply_action_results(presentation)
        self.assertEqual(mock._timeline_order.entries[-1].gauge, 52)
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
            patch("scenes.battle.random.randint", side_effect=lambda low, high: low) as randint,
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
        self.assertEqual(randint.call_args_list, [((0, 19),), ((4, 5),)])

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


class BattleDebuffRecoveryTest(unittest.TestCase):
    def states(self):
        actor = spellcaster(magic=7, spell_key="SLOW")
        scene = spell_scene(actor)
        return ((scene.party[0], "protection_level"), (actor.state, "defense_modifier"))

    def test_runtime_spells_and_physical_effects_draw_turns_for_target_resistance(self):
        from item import AdditionalEffect
        from scenes.battle import (
            BattleActionPresentation, BattleSlowResult, BattleBreakResult,
            BattlePartySlowResult, BattlePartyBreakResult,
        )

        for resistances, bounds, duration in (
            (frozenset(), (4, 5), 5),
            (frozenset((ResistanceType.DEATH,)), (3, 4), 3),
        ):
            monster = spellcaster(magic=7, spell_key="SLOW")
            monster.resistances = resistances
            scene = spell_scene(monster)
            scene._delay_slow_target = Mock()
            presentation = BattleActionPresentation(
                (), slow_results=(BattleSlowResult(0, True, 0, 0),),
                break_results=(BattleBreakResult(0, True, 0, 0),),
                party_slow_results=(BattlePartySlowResult(0, True, 0, 0),),
                party_break_results=(BattlePartyBreakResult(0, True, 0, 0),),
            )
            with (
                patch.object(Member, "resistances", new_callable=PropertyMock,
                             return_value=resistances),
                patch("scenes.battle.random.randint", return_value=duration) as draw,
            ):
                scene._apply_action_results(presentation)
                for state in (scene.party[0], monster.state):
                    self.assertEqual((state.slow_turns, state.defense_down_turns), (duration, duration))
                scene.party[0].clear_temporary_battle_conditions()
                monster.state.restore()
                scene._apply_additional_effects_to_monster(0, (AdditionalEffect.DEFENSE_DOWN,))
                scene._apply_additional_effects_to_member(0, (AdditionalEffect.DEFENSE_DOWN,))
            self.assertEqual(draw.call_count, 6)
            self.assertTrue(all(args.args == bounds for args in draw.call_args_list))
            self.assertEqual(scene.party[0].defense_down_turns, duration)
            self.assertEqual(monster.state.defense_down_turns, duration)

    def test_debuffs_recover_independently_after_own_turns(self):
        for duration in (3, 4, 5):
            for state, defense in self.states():
                with self.subTest(duration=duration, state=type(state).__name__):
                    state.apply_slow(duration)
                    state.apply_defense_down(5)
                    state.apply_silence(duration)
                    state.take_damage(1)
                    for turn in range(1, 6):
                        state.elapse_debuff_turn()
                        state.elapse_silence_turn()
                        self.assertEqual(state.slow_turns, max(0, duration - turn))
                        self.assertEqual(state.speed_modifier, -1 if turn < duration else 0)
                        self.assertEqual(getattr(state, defense), -1 if turn < 5 else 0)
                        self.assertEqual(state.slow_turns, state.silenced)

    def test_failed_reapplication_preserves_remaining_duration(self):
        for state, _ in self.states():
            state.apply_slow(4)
            state.apply_defense_down(4)
            state.elapse_debuff_turn()
            self.assertFalse(state.apply_slow(6))
            self.assertFalse(state.apply_defense_down(6))
            if isinstance(state, Member):
                self.assertFalse(state.apply_armor_break(6))
            self.assertEqual((state.slow_turns, state.defense_down_turns), (3, 3))

    def test_positive_buffs_survive_turns_and_cancel_pending_debuff_timers(self):
        for state, defense in self.states():
            state.apply_slow(4)
            state.apply_haste()
            state.apply_haste()
            state.apply_haste()
            if isinstance(state, Member):
                state.apply_defense_down(4)
                state.apply_protection()
                state.apply_protection()
                state.apply_protection()
            for _ in range(8):
                state.elapse_debuff_turn()
            self.assertEqual(state.speed_modifier, 2)
            self.assertEqual(getattr(state, defense), 2 if isinstance(state, Member) else 0)
            self.assertEqual((state.slow_turns, state.defense_down_turns), (0, 0))
            state.apply_slow(6)
            self.assertEqual((state.speed_modifier, state.slow_turns), (0, 0))
            if isinstance(state, Member):
                state.apply_armor_break(6)
                self.assertEqual((state.protection_level, state.defense_down_turns), (0, 0))

    def test_death_and_battle_cleanup_discard_debuff_timers(self):
        for cleanup in ("damage", "poison", "defeat", "reset"):
            for state, defense in self.states():
                state.apply_slow(6)
                state.apply_defense_down(6)
                if cleanup == "damage":
                    state.take_damage(state.hp)
                elif cleanup == "poison":
                    state.take_poison_damage(state.hp)
                elif cleanup == "defeat":
                    state.defeat()
                elif isinstance(state, Member):
                    state.clear_temporary_battle_conditions()
                else:
                    state.restore()
                self.assertEqual((state.slow_turns, state.defense_down_turns), (0, 0))
                self.assertEqual((state.speed_modifier, getattr(state, defense)), (0, 0))

    def test_turn_completion_recovers_both_sides_before_timeline_reinsertion(self):
        from scenes.battle import BattleCharacter

        for side in ("ally", "enemy"):
            monster = spellcaster(magic=7, spell_key="SLOW")
            scene = spell_scene(monster)
            member = scene.party[0]
            actor = BattleCharacter(member, 0, 0, 0) if side == "ally" else monster
            state = member if side == "ally" else monster.state
            state.apply_slow(1)
            state.apply_defense_down(1)
            scene._timeline_order = TimelineOrder((TimelineEntry(actor, 12, 64),))
            scene.command_cursor = Mock()
            scene.command_window = Mock()
            scene._refresh_party_text_colors = Mock()
            scene._start_timeline_animation()
            self.assertEqual((state.slow_turns, state.defense_down_turns), (0, 0))
            self.assertEqual(state.speed_modifier, 0)
            self.assertEqual(scene.timeline_advance.after.entries[0].agility,
                             member.effective_agility if side == "ally" else monster.agility)


class MonsterDamageSpellTest(unittest.TestCase):
    def test_party_blood_suck_respects_dark_affinity_and_caps_healing(self):
        target = spellcaster(magic=0, spell_key="HASTE")
        target.resistances = frozenset({ResistanceType.DARK})
        scene = spell_scene(target)
        caster = scene.party[0]
        caster.hp = caster.max_hp - 1
        scene.active_party_index = 0
        scene.action_targets_enemy = True
        scene.action_targets_all = False
        scene.selected_target_index = 0
        scene.target_cursor = Mock()
        scene.party_target_cursor = None
        scene._refresh_monster_name_colors = Mock()
        spell = scene.spells["BLOOD SUCK"]

        with (
            patch("scenes.battle.random.random", return_value=0.5),
            patch("scenes.battle.play_se"),
        ):
            self.assertTrue(scene._begin_action_presentation(spell))
            result, = scene.action_presentation.damage_results
            self.assertIs(result.affinity, SpellAffinity.RESIST)
            self.assertGreater(result.damage, 1)
            scene._update_action_presentation()

        self.assertEqual(target.state.hp, max(0, target.state.max_hp - result.damage))
        self.assertEqual(caster.hp, caster.max_hp)
        self.assertEqual(scene.healing_popups[0].amount, 1)

    def test_mage_dwarf_blood_suck_heals_only_actual_hp_lost_once(self):
        record = next(r for r in load_record_array("monsters.json") if r["name_en"] == "メイジドワーフ")
        actor = BattleMonster.from_record(record, is_front_row=True)
        actor.state.take_damage(30)
        actor.state.apply_poison()
        scene = spell_scene(actor)
        target = scene.party[0]
        target.hp = 2
        hp = actor.state.hp
        scene.auto_battle_observations = Mock()

        with (
            patch("scenes.battle.random.choice", return_value=0),
            patch("scenes.battle.random.random", return_value=0.5),
            patch("scenes.battle.play_se") as play_se,
        ):
            self.assertEqual(actor.state.mp, 11)
            self.assertTrue(scene._begin_monster_spell(actor, scene.spells["BLOOD SUCK"]))
            self.assertEqual(actor.state.mp, 6)
            presentation = scene.action_presentation
            self.assertGreater(presentation.party_damage_results[0].damage, 2)
            self.assertEqual((target.hp, actor.state.hp), (2, hp))
            scene._update_action_presentation()
            scene._apply_action_results(presentation)

        self.assertEqual((target.hp, actor.state.hp), (0, hp + 2))
        self.assertTrue(actor.state.poisoned)
        scene.auto_battle_observations.damage.assert_called_once_with(0, -2)
        play_se.assert_called_once_with("battle_drain")

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

    def test_poison_spell_damage_and_poison_are_resolved_separately(self):
        for case, roll, expected_hp, poisoned in (
            ("success", 0, 43, True),
            ("failed roll", 19, 43, False),
            ("resisted", 0, 54, False),
            ("lethal", 0, 0, False),
        ):
            with self.subTest(case=case):
                actor = spellcaster(magic=8, spell_key="POISON1")
                scene = spell_scene(actor)
                target = scene.party[1]
                if case == "resisted":
                    target.equipment = target.equipment.replaced(
                        {EquipmentSlot.HEAD: load_mock_items()["SNAKE CAP"]}
                    )
                if case == "lethal":
                    target.hp = 1
                hp = target.hp
                with (
                    patch("scenes.battle.random.choice", return_value=1),
                    patch("scenes.battle.random.random", return_value=0.5),
                    patch("scenes.battle.random.randint", return_value=roll) as status_roll,
                ):
                    self.assertTrue(scene._begin_monster_spell(actor, scene.spells["POISON1"]))

                self.assertEqual(target.hp, hp)
                self.assertFalse(target.poisoned)
                scene._update_action_presentation()
                self.assertEqual(target.hp, expected_hp)
                self.assertEqual(target.poisoned, poisoned)
                if case == "resisted":
                    status_roll.assert_not_called()
                    self.assertIs(scene.affinity_popups[0].affinity, SpellAffinity.RESIST)
                else:
                    status_roll.assert_called_once_with(0, 19)

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


class IntelligentMonsterSpellTest(unittest.TestCase):
    def scene(self, key, *, intelligence=1):
        actor = spellcaster(magic=17, spell_key=key, max_mp=12)
        actor.intelligence = intelligence
        return actor, spell_scene(actor)

    def test_int_one_filters_silence_and_insufficient_mp_but_int_zero_keeps_spells(self):
        for intelligence in (0, 1):
            for condition in ("silence", "mp"):
                with self.subTest(intelligence=intelligence, condition=condition):
                    actor, scene = self.scene("FIRE1", intelligence=intelligence)
                    if condition == "silence":
                        actor.state.apply_silence(1)
                    else:
                        actor.state.mp = 1
                    self.assertEqual(scene._targetable_monster_spell_keys(actor),
                                     ("FIRE1",) if intelligence == 0 else ())

    def test_all_target_debuff_is_kept_if_any_member_is_effective(self):
        for key in ("SLOW", "SLEEP", "SILENCE"):
            actor, scene = self.scene(key)
            scene.spells[key] = replace(scene.spells[key], to_all=True)
            scene._member_can_cast_spells = Mock(return_value=True)
            for member in scene.party:
                member.speed_modifier = -1
                member.sleeping = 2
                member.silenced = 4
            with self.subTest(spell=key):
                self.assertEqual(scene._targetable_monster_spell_keys(actor), ())
                scene.party[1].speed_modifier = 0
                scene.party[1].sleeping = 0
                scene.party[1].silenced = 0
                self.assertEqual(scene._targetable_monster_spell_keys(actor), (key,))
                # DA2 still applies the full spell to everyone, not just the effective member.
                self.assertEqual(scene._monster_spell_candidates[key].targets, (0, 1))

    def test_frau_rotates_from_each_starting_action_and_wraps(self):
        record = next(r for r in load_record_array("monsters.json") if r["name_en"] == "Frau")
        rotation = (
            MonsterSpellAction("FREEZE2"), MonsterSpellAction("CONFUSION"), MonsterAction.ATTACK,
        )
        for start in range(len(rotation)):
            with self.subTest(start=start):
                actor = BattleMonster.from_record(record, is_front_row=True)
                scene = spell_scene(actor)
                with (
                    patch("monster_ai.random.randrange", return_value=start) as choose_start,
                    patch.object(Member, "resistances", return_value=frozenset(), new_callable=PropertyMock),
                ):
                    self.assertEqual(
                        tuple(scene._select_monster_action(actor) for _ in range(4)),
                        tuple(rotation[(start + offset) % 3] for offset in range(4)),
                    )
                choose_start.assert_called_once_with(3)
                actor.restore()
                self.assertIsNone(actor.state.action_rotation_index)

    def test_frau_skips_silenced_unaffordable_and_ineffective_spells(self):
        record = next(r for r in load_record_array("monsters.json") if r["name_en"] == "Frau")
        actor = BattleMonster.from_record(record, is_front_row=True)
        scene = spell_scene(actor)
        actor.state.action_rotation_index = 0
        actor.state.apply_silence(1)
        self.assertIs(scene._select_monster_action(actor), MonsterAction.ATTACK)
        actor.state.elapse_silence_turn()
        actor.state.mp = scene.spells["CONFUSION"].mp
        self.assertLess(actor.state.mp, scene.spells["FREEZE2"].mp)
        with patch.object(Member, "resistances", return_value=frozenset(), new_callable=PropertyMock):
            self.assertEqual(scene._select_monster_action(actor), MonsterSpellAction("CONFUSION"))

        actor.state.action_rotation_index = 1
        actor.state.mp = actor.max_mp
        with patch.object(
            Member, "resistances", new_callable=PropertyMock,
            return_value=frozenset({ResistanceType.CONFUSE}),
        ):
            self.assertIs(scene._select_monster_action(actor), MonsterAction.ATTACK)
        scene.hidden_party_indexes = set(range(len(scene.party)))
        self.assertIsNone(scene._select_monster_action(actor))

    def test_rear_frau_waits_on_attack_turn_even_with_usable_spells(self):
        record = next(r for r in load_record_array("monsters.json") if r["name_en"] == "Frau")
        actor = BattleMonster.from_record(record, is_front_row=False)
        actor.state.action_rotation_index = 2
        scene = spell_scene(actor)
        scene.command_window = Mock()
        scene.timeline = (actor,)
        scene.monster_attack_target_index = None
        scene.monster_blink_frames_remaining = 0
        scene._start_timeline_animation = Mock()

        scene._update_monster_action()

        scene._start_timeline_animation.assert_called_once_with()
        self.assertIsNone(scene.monster_action)
        self.assertEqual(actor.state.defense_modifier, 0)
        self.assertEqual(actor.state.mp, actor.max_mp)
        self.assertEqual(scene._select_monster_action(actor), MonsterSpellAction("FREEZE2"))

    def test_int_two_prioritizes_area_debuff_if_all_applicable_targets_are_effective(self):
        actor, scene = self.scene("SLEEP", intelligence=2)
        actor.spell_keys = ("FIRE1", "SLEEP")
        scene.party[0].sleeping = 2
        self.assertEqual(scene._select_monster_action(actor), MonsterSpellAction("FIRE1"))
        actor.is_front_row = True
        with (
            patch.object(
                Member, "resistances", property(
                    lambda member: frozenset({ResistanceType.SLEEP})
                    if member is scene.party[0] else frozenset()
                ),
            ),
            patch("monster_ai.random.choice") as choose,
        ):
            self.assertEqual(scene._select_monster_action(actor), MonsterSpellAction("SLEEP"))
        choose.assert_not_called()
        self.assertEqual(scene._monster_spell_candidates["SLEEP"].targets, (0, 1))

    def test_int_two_prefers_visible_sleeping_or_paralyzed_targets(self):
        actor, scene = self.scene("FIRE1", intelligence=2)
        spell = scene.spells["FIRE1"]
        for sleeping, paralyzed in ((2, False), (0, True)):
            with self.subTest(sleeping=sleeping, paralyzed=paralyzed):
                scene.party[1].sleeping = sleeping
                scene.party[1].paralyzed = paralyzed
                self.assertEqual(scene._preferred_monster_party_targets(actor, (0, 1)), (1,))
                self.assertTrue(scene._begin_monster_spell(actor, spell))
                self.assertEqual(scene.action_presentation.party_damage_results[0].target_index, 1)
        scene.party[1].confused = 2
        self.assertEqual(scene._preferred_monster_party_targets(actor, (0, 1)), (0, 1))
        scene.hidden_party_indexes = {1}
        self.assertTrue(scene._begin_monster_spell(actor, spell))
        self.assertEqual(scene.action_presentation.party_damage_results[0].target_index, 0)

    def test_silence_excludes_party_without_any_caster(self):
        actor, scene = self.scene("SILENCE")
        scene._member_can_cast_spells = Mock(return_value=False)
        self.assertEqual(scene._targetable_monster_spell_keys(actor), ())

    def test_break_random_target_is_checked_before_candidate_inclusion_and_retained(self):
        actor, scene = self.scene("ARMOR BREAK")
        scene.party[0].formation_row = FormationRow.FRONT
        scene.party[1].formation_row = FormationRow.BACK
        with patch("scenes.battle.random.choice", return_value=1) as choose:
            self.assertEqual(scene._targetable_monster_spell_keys(actor), ())
            choose.assert_called_once_with((0, 1))
        scene.party[0].protection_level = -1
        with patch("scenes.battle.random.choice", return_value=0):
            self.assertEqual(scene._targetable_monster_spell_keys(actor), ())
        scene.party[0].protection_level = 0
        with patch("scenes.battle.random.choice", return_value=0) as choose:
            self.assertEqual(scene._targetable_monster_spell_keys(actor), ("ARMOR BREAK",))
            scene._begin_monster_spell(actor, scene.spells["ARMOR BREAK"])
            choose.assert_called_once_with((0, 1))
        self.assertEqual(scene.action_presentation.party_break_results[0].target_index, 0)

    def test_silence_applies_target_duration_only_to_casters_and_respects_resistance(self):
        actor, scene = self.scene("SILENCE")
        scene._member_can_cast_spells = Mock(side_effect=lambda member: member is scene.party[1])
        with (
            patch.object(Member, "resistances", new_callable=PropertyMock,
                         return_value=frozenset({ResistanceType.DEATH})),
            patch("scenes.battle.random.randint", side_effect=(0, 3)) as draw,
        ):
            scene._begin_monster_spell(actor, scene.spells["SILENCE"])
        self.assertEqual([args.args for args in draw.call_args_list], [(0, 19), (3, 4)])
        scene._apply_action_results(scene.action_presentation)
        self.assertEqual(tuple(m.silenced for m in scene.party), (0, 3))
        self.assertEqual([p.is_miss for p in scene.spell_damage_popups], [True])
        actor, scene = self.scene("SILENCE")
        scene._member_can_cast_spells = Mock(return_value=True)
        with patch.object(Member, "resistances", new_callable=PropertyMock,
                          return_value=frozenset({ResistanceType.SILENCE})):
            scene._begin_monster_spell(actor, scene.spells["SILENCE"])
        scene._apply_action_results(scene.action_presentation)
        self.assertEqual(tuple(m.silenced for m in scene.party), (0, 0))

    def test_member_silence_survives_damage_and_cure_and_clears_on_death_or_battle_exit(self):
        actor, scene = self.scene("SILENCE")
        member = scene.party[0]
        member.apply_silence(6)
        member.apply_silence(4)
        member.take_damage(1)
        member.cure_ailments()
        self.assertEqual(member.silenced, 6)
        for remaining in range(5, -1, -1):
            self.assertTrue(member.elapse_silence_turn())
            self.assertEqual(member.silenced, remaining)
        self.assertFalse(member.elapse_silence_turn())
        member.apply_silence(4)
        member.clear_temporary_battle_conditions()
        self.assertEqual(member.silenced, 0)
        member.apply_silence(4)
        member.take_damage(member.hp)
        self.assertEqual(member.silenced, 0)

    def test_member_silence_decrements_when_turn_returns_to_timeline(self):
        from scenes.battle import BattleCharacter
        from battle_timeline import TimelineEntry, TimelineOrder

        _, scene = self.scene("SILENCE")
        member = scene.party[0]
        visual = BattleCharacter(member, 0, 0, 0)
        scene._timeline_order = TimelineOrder((TimelineEntry(visual, 10, 64),))
        scene.command_cursor = Mock()
        scene.command_window = Mock()
        scene._refresh_party_text_colors = Mock()
        member.apply_silence(1)
        member.apply_sleep(2)
        scene._start_timeline_animation()
        self.assertEqual(member.silenced, 0)

    def test_silenced_member_spell_fails_without_mp_use(self):
        actor, scene = self.scene("SILENCE")
        scene.active_party_index = 1
        member = scene.party[1]
        member.apply_silence(1)
        scene.pending_spell = scene.spells["FIRE1"]
        scene.pending_item_candidate = None
        scene._selected_party_target_can_receive_spell = Mock(return_value=True)
        mp = member.mp
        self.assertTrue(scene._confirm_action_target_selection())
        self.assertEqual(member.mp, mp)
        self.assertEqual(scene.action_presentation.party_damage_results, ())
        scene._show_monster_spell_sealed_message.assert_called_once_with(actor_is_enemy=False)


if __name__ == "__main__":
    unittest.main()
