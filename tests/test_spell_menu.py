from __future__ import annotations

from dataclasses import replace
from contextlib import nullcontext
import unittest
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT as _APP_ROOT

from app.input import Direction, InputButton, InputState
from app.resources import TRANSPARENT_INDEX
from app.spell import SpellAction, SpellType
from member import ProficiencyKind
from rendering import DIMMED_PALETTE, MONOCHROME_PALETTE
from ui import DEFAULT_TEXT_COLOR
from ui.teleport_menu import TeleportTarget
from ui.spell_menu import (
    FACE_SIZE,
    GUIDE_WINDOW_GRID,
    MEMBER_CURSOR_X,
    MEMBER_FACE_X,
    MEMBER_FACE_Y,
    MEMBER_NAME_Y,
    MEMBER_MP_LABEL_Y,
    MEMBER_MP_VALUE_Y,
    MEMBER_TEXT_X,
    MEMBER_WINDOW_GRID,
    PARTY_COLUMN_WIDTH,
    PARTY_FACE_X,
    PARTY_FACE_Y,
    PARTY_HP_Y,
    PARTY_MAX_HP_Y,
    PARTY_TEXT_X,
    PARTY_WINDOW_GRID,
    SPELL_CURSOR_X,
    SPELL_DISPLAY_LEVELS,
    SPELL_FIRST_Y,
    SPELL_ROW_HEIGHT,
    SPELL_TEXT_X,
    SPELL_TYPE_ORDER,
    SPELL_WINDOW_GRID,
    PROFICIENCY_ANIMATION_FRAME_COUNT,
    PROFICIENCY_TEXT_X,
    PROFICIENCY_TEXT_Y,
    PROFICIENCY_WINDOW_GRID,
    SpellMenuDataError,
    SpellSelectionPhase,
)
from tests.ui_test_support import SpellMenuHarness, load_test_spells


class SpellMenuTest(unittest.TestCase):
    def test_builds_da2_layout_with_three_spell_types_per_level_row(self) -> None:
        mock = SpellMenuHarness()

        self.assertEqual(
            tuple(
                (window.x, window.y, window.width, window.height)
                for window in mock.windows
            ),
            (
                MEMBER_WINDOW_GRID,
                GUIDE_WINDOW_GRID,
                SPELL_WINDOW_GRID,
                PARTY_WINDOW_GRID,
            ),
        )
        self.assertTrue(mock.member_window.horizontal_navigation)
        self.assertEqual(mock.member.definition.key, "Fiora")
        self.assertEqual(
            [(text.text, text.x, text.y) for text in mock.spell_window.texts],
            [
                ("%MYSTIC%ファイア１", SPELL_TEXT_X[0], SPELL_FIRST_Y),
                ("%NETHER%ポイズン１", SPELL_TEXT_X[2], SPELL_FIRST_Y),
            ],
        )
        self.assertEqual(
            [(target.key, target.x, target.y) for target in mock.spell_cursor.targets],
            [
                ("FIRE1", SPELL_CURSOR_X[0], SPELL_FIRST_Y),
                ("POISON1", SPELL_CURSOR_X[2], SPELL_FIRST_Y),
            ],
        )
        self.assertNotIn("Ｌ１", "".join(text.text for text in mock.spell_window.texts))
        self.assertEqual(SPELL_TYPE_ORDER, tuple(SpellType)[:3])
        self.assertEqual(SPELL_DISPLAY_LEVELS, (*range(1, 10), 0))
        member_texts = {(text.x, text.y): text.text for text in mock.member_window.texts}
        self.assertEqual(member_texts[(MEMBER_TEXT_X, MEMBER_MP_LABEL_Y)], "ＭＰ")
        self.assertEqual(
            member_texts[(MEMBER_TEXT_X, MEMBER_MP_VALUE_Y)],
            "　１２／　１２",
        )
        self.assertEqual(mock._point_text(16, 255), "　１６／２５５")
        self.assertIs(mock.phase, SpellSelectionPhase.CASTER)
        self.assertTrue(mock.caster_cursor.active)
        self.assertEqual(
            (
                mock.caster_cursor.selected_key,
                mock.caster_cursor.selected_target.x,
                mock.caster_cursor.selected_target.y,
            ),
            (0, MEMBER_CURSOR_X, MEMBER_NAME_Y),
        )
        self.assertFalse(mock.spell_cursor.active)
        self.assertEqual(mock.guide_window.texts, ())

    def test_bottom_party_uses_five_faces_and_three_digit_hp_fields(self) -> None:
        mock = SpellMenuHarness()
        placements = {(text.x, text.y): text.text for text in mock.party_window.texts}

        self.assertEqual(len(mock.party), 6)
        self.assertEqual(len(mock.party_panel.party), 5)
        self.assertEqual(
            [target.key for target in mock.member_cursor.targets],
            list(range(5)),
        )
        self.assertEqual(placements[(PARTY_TEXT_X, PARTY_HP_Y)], "ＨＰ　４４")
        self.assertEqual(placements[(PARTY_TEXT_X + 12, PARTY_HP_Y)], "ＨＰ　６４")
        self.assertEqual(placements[(PARTY_TEXT_X + 24, PARTY_HP_Y)], "ＨＰ２２０")
        self.assertEqual(placements[(PARTY_TEXT_X + 36, PARTY_HP_Y)], "ＨＰ１１５")
        self.assertEqual(placements[(PARTY_TEXT_X + 48, PARTY_HP_Y)], "ＨＰ１７１")
        self.assertEqual(placements[(PARTY_TEXT_X + 2, PARTY_MAX_HP_Y)], "／　４４")

        mock.windows = tuple(Mock() for _ in mock.windows)
        mock.caster_cursor = Mock()
        mock.spell_cursor = Mock()
        mock.member_cursor = Mock()
        with patch("ui.spell_menu.pyxel.blt") as blt:
            mock.draw()

        expected_faces = [
            call(
                MEMBER_FACE_X,
                MEMBER_FACE_Y,
                mock.faces,
                mock.member.face_position.x,
                mock.member.face_position.y,
                FACE_SIZE,
                FACE_SIZE,
                TRANSPARENT_INDEX,
            )
        ]
        expected_faces.extend(
            call(
                PARTY_FACE_X + index * PARTY_COLUMN_WIDTH * 4,
                PARTY_FACE_Y,
                mock.faces,
                member.face_position.x,
                member.face_position.y,
                FACE_SIZE,
                FACE_SIZE,
                TRANSPARENT_INDEX,
            )
            for index, member in enumerate(mock.party_panel.party)
        )
        self.assertEqual(blt.call_args_list, expected_faces)
        mock.caster_cursor.draw.assert_called_once_with()
        mock.spell_cursor.draw.assert_not_called()
        mock.member_cursor.draw.assert_not_called()

    def test_selects_caster_before_moving_between_spells(self) -> None:
        mock = SpellMenuHarness()

        mock.update(InputState(confirm=InputButton(True, True)))
        mock.update(InputState(navigation=Direction.RIGHT))

        self.assertIs(mock.phase, SpellSelectionPhase.SPELL)
        self.assertFalse(mock.caster_cursor.active)
        self.assertFalse(mock.member_window.active)
        self.assertTrue(mock.spell_cursor.active)
        self.assertEqual(mock.selected_spell.key, "POISON1")
        self.assertEqual(
            [text.text for text in mock.guide_window.texts],
            [
                "てき１たいを%POISON%どくにおかし",
                "ダメージ（ばいりつ：１０）",
                "しょうひＭＰ：　２",
            ],
        )

    def test_left_and_right_select_caster_before_spell_confirmation(self) -> None:
        mock = SpellMenuHarness()

        mock.update(InputState(navigation=Direction.RIGHT))

        self.assertEqual(mock.member.definition.key, "Cerion")
        self.assertIs(mock.phase, SpellSelectionPhase.CASTER)
        self.assertEqual(mock.guide_window.texts, ())

        mock.update(InputState(confirm=InputButton(True, True)))
        self.assertIs(mock.phase, SpellSelectionPhase.SPELL)
        self.assertEqual(mock.selected_spell.key, "HEALING1")

    def test_defaults_to_first_member_with_a_usable_field_spell(self) -> None:
        mock = SpellMenuHarness(member_index=None)

        self.assertEqual(mock.member.definition.key, "Cerion")
        self.assertEqual(mock.member_index, 1)
        self.assertEqual(mock.selected_spell.key, "HEALING1")

    def test_defaults_spell_cursor_to_first_usable_spell(self) -> None:
        mock = SpellMenuHarness(member_index=1)

        self.assertEqual(
            [target.key for target in mock.spell_cursor.targets],
            ["FIRE1", "HEALING1"],
        )
        self.assertEqual(mock.selected_spell.key, "HEALING1")

    def test_first_usable_spell_order_is_top_to_bottom_then_left_to_right(
        self,
    ) -> None:
        spells = load_test_spells()
        spells["FIRE1"] = replace(
            spells["FIRE1"],
            on_camp=True,
            to_enemy=False,
            action=SpellAction.HEAL,
        )

        mock = SpellMenuHarness(member_index=1, spells=spells)

        self.assertEqual(mock.selected_spell.key, "FIRE1")

    def test_cancel_returns_from_spell_to_caster_then_to_menu(self) -> None:
        mock = SpellMenuHarness()

        mock.update(InputState(confirm=InputButton(True, True)))
        self.assertFalse(mock.update(InputState(cancel=InputButton(True, True))))
        self.assertIs(mock.phase, SpellSelectionPhase.CASTER)
        self.assertTrue(mock.caster_cursor.active)
        self.assertTrue(mock.member_window.active)
        self.assertFalse(mock.spell_cursor.active)
        self.assertEqual(mock.guide_window.texts, ())
        self.assertTrue(mock.update(InputState(cancel=InputButton(True, True))))

    def test_page_buttons_switch_member_and_cancel_returns_to_menu(self) -> None:
        mock = SpellMenuHarness()

        self.assertFalse(
            mock.update(InputState(previous_page=InputButton(True, True)))
        )
        self.assertEqual(mock.member_index, 5)
        self.assertEqual(mock.member.definition.key, "Dain")

        self.assertFalse(
            mock.update(InputState(next_page=InputButton(True, True)))
        )
        self.assertEqual(mock.member_index, 0)
        self.assertEqual(mock.member.definition.key, "Fiora")
        self.assertEqual(
            [target.key for target in mock.spell_cursor.targets],
            ["FIRE1", "POISON1"],
        )
        self.assertTrue(
            mock.update(InputState(cancel=InputButton(True, True)))
        )

    @patch("ui.spell_menu.play_se")
    @patch("ui.spell_menu.random.random", return_value=0.5)
    def test_healing_spell_recovers_hp_spends_mp_and_refreshes_values(
        self,
        random_value: Mock,
        play_se: Mock,
    ) -> None:
        mock = SpellMenuHarness(member_index=1)
        target = mock.party[0]
        target.hp = 1
        initial_mp = mock.member.mp

        mock.update(InputState(confirm=InputButton(True, True)))
        self.assertFalse(mock.update(InputState(confirm=InputButton(True, True))))
        self.assertIs(mock.phase, SpellSelectionPhase.TARGET)
        self.assertFalse(mock.update(InputState(confirm=InputButton(True, True))))

        self.assertEqual(target.hp, target.max_hp)
        self.assertEqual(mock.dimmed_member_indexes, frozenset(range(5)))
        self.assertTrue(
            all(text.color == DEFAULT_TEXT_COLOR for text in mock.party_window.texts)
        )
        self.assertEqual(mock.member.mp, initial_mp - mock.spells["HEALING1"].mp)
        self.assertIs(mock.phase, SpellSelectionPhase.TARGET)
        self.assertEqual(mock.selected_spell.key, "HEALING1")
        member_texts = {(text.x, text.y): text.text for text in mock.member_window.texts}
        self.assertEqual(
            member_texts[(MEMBER_TEXT_X, MEMBER_MP_VALUE_Y)],
            "　１３／　１６",
        )
        party_texts = {(text.x, text.y): text.text for text in mock.party_window.texts}
        self.assertEqual(party_texts[(PARTY_TEXT_X, PARTY_HP_Y)], "ＨＰ　４４")
        random_value.assert_called_once_with()
        play_se.assert_called_once_with("spell_healing1")

        for _frame in range(PROFICIENCY_ANIMATION_FRAME_COUNT + 1):
            mock.update(InputState())
        self.assertIs(mock.phase, SpellSelectionPhase.TARGET)
        self.assertEqual(mock.member_cursor.selected_key, 0)
        self.assertIn(mock.proficiency_window, mock.windows)

        mock.update(InputState(cancel=InputButton(True, True)))
        self.assertIs(mock.phase, SpellSelectionPhase.SPELL)

    def test_target_cursor_appears_only_after_usable_spell_is_selected(self) -> None:
        mock = SpellMenuHarness(member_index=1)
        mock.party[0].hp -= 1
        self.assertFalse(mock.member_cursor.active)

        mock.update(InputState(confirm=InputButton(True, True)))
        self.assertIs(mock.phase, SpellSelectionPhase.SPELL)
        self.assertFalse(mock.member_cursor.active)

        mock.spell_cursor.select_key("FIRE1")
        mock.update(InputState(confirm=InputButton(True, True)))
        self.assertIs(mock.phase, SpellSelectionPhase.SPELL)

        mock.spell_cursor.select_key("HEALING1")
        self.assertEqual(mock.selected_spell.key, "HEALING1")
        mock.update(InputState(confirm=InputButton(True, True)))

        self.assertIs(mock.phase, SpellSelectionPhase.TARGET)
        self.assertFalse(mock.spell_cursor.active)
        self.assertTrue(mock.member_cursor.active)
        self.assertEqual(mock.member_cursor.selected_key, 0)
        self.assertEqual(
            (
                mock.proficiency_window.x,
                mock.proficiency_window.y,
                mock.proficiency_window.width,
                mock.proficiency_window.height,
            ),
            PROFICIENCY_WINDOW_GRID,
        )
        sacred = mock.member.proficiency(ProficiencyKind.SACRED)
        self.assertEqual(
            [
                (text.text, text.x, text.y)
                for text in mock.proficiency_window.texts
            ],
            [
                (
                    f"%SACRED%{sacred.level}－{sacred.progress:02d}".translate(
                        str.maketrans("0123456789", "０１２３４５６７８９")
                    ),
                    PROFICIENCY_TEXT_X,
                    PROFICIENCY_TEXT_Y,
                )
            ],
        )
        self.assertIn(mock.proficiency_window, mock.windows)

        mock.update(InputState(navigation=Direction.RIGHT))
        self.assertEqual(mock.member_cursor.selected_key, 1)
        self.assertFalse(mock.update(InputState(cancel=InputButton(True, True))))
        self.assertIs(mock.phase, SpellSelectionPhase.SPELL)
        self.assertTrue(mock.spell_cursor.active)
        self.assertFalse(mock.member_cursor.active)
        self.assertNotIn(mock.proficiency_window, mock.windows)

    @patch("ui.spell_menu.play_se")
    @patch("ui.spell_menu.random.random", return_value=0.5)
    def test_spell_use_animates_applied_proficiency_for_six_frames(
        self,
        _random_value: Mock,
        play_se: Mock,
    ) -> None:
        mock = SpellMenuHarness(member_index=1)
        target = mock.party[0]
        target.hp = 1
        sacred = mock.member.proficiency(ProficiencyKind.SACRED)
        sacred.level = 1
        sacred.progress = 95
        mock.member.proficiency(ProficiencyKind.MYSTIC).level = 5

        mock.update(InputState(confirm=InputButton(True, True)))
        mock.update(InputState(confirm=InputButton(True, True)))
        mock.update(InputState(confirm=InputButton(True, True)))

        self.assertEqual((sacred.level, sacred.progress), (2, 2))
        self.assertEqual(mock.proficiency_window.texts[0].text, "%SACRED%１－９５")
        self.assertIs(mock.phase, SpellSelectionPhase.TARGET)
        play_se.assert_called_once_with("spell_healing1")

        for _frame in range(5):
            mock.update(InputState())

        self.assertNotEqual(mock.proficiency_window.texts[0].text, "%SACRED%２－０２")
        mock.update(InputState())
        self.assertEqual(mock.proficiency_window.texts[0].text, "%SACRED%２－０２")
        play_se.assert_called_once_with("spell_healing1")

        mock.update(InputState())
        self.assertIs(mock.phase, SpellSelectionPhase.TARGET)
        self.assertEqual(mock.member_cursor.selected_key, 0)
        self.assertIn(mock.proficiency_window, mock.windows)

    def test_healing_with_no_valid_target_reports_an_error(self) -> None:
        invalid_action = Mock()
        mock = SpellMenuHarness(member_index=1)
        mock.on_invalid_action = invalid_action

        mock.update(InputState(confirm=InputButton(True, True)))
        mock.update(InputState(confirm=InputButton(True, True)))

        self.assertIs(mock.phase, SpellSelectionPhase.SPELL)
        self.assertEqual(mock.member.mp, mock.member.max_mp)
        invalid_action.assert_called_once_with()

    @patch("ui.spell_menu.play_se")
    @patch("ui.spell_menu.random.random")
    def test_cure_clears_da2_ailments_without_healing_or_clearing_stun(
        self,
        random_value: Mock,
        play_se: Mock,
    ) -> None:
        palette_shifter = Mock()
        palette_shifter.shifted.side_effect = lambda _name: nullcontext()
        mock = SpellMenuHarness(member_index=1, palette_shifter=palette_shifter)
        proficiency = mock.member.proficiency(ProficiencyKind.SACRED)
        proficiency.level = 3
        mock._build_windows()
        target = mock.party[0]
        initial_hp = target.hp
        initial_mp = mock.member.mp
        target.poisoned = True
        target.paralyzed = True
        target.sleeping = 2
        target.confused = 3
        target.stunned = True
        mock.party[2].hp = 0
        mock.party[2].poisoned = True

        mock.update(InputState(confirm=InputButton(True, True)))
        mock.spell_cursor.select_key("CURE")
        mock.update(InputState(confirm=InputButton(True, True)))

        self.assertIs(mock.phase, SpellSelectionPhase.TARGET)
        self.assertEqual(mock.member_cursor.selected_key, 0)
        self.assertEqual(mock._usable_target_indexes(mock.spells["CURE"]), (0,))
        self.assertEqual(mock.dimmed_member_indexes, frozenset((1, 2, 3, 4)))
        self.assertEqual(
            [text.color for text in mock.party_window.texts],
            [DEFAULT_TEXT_COLOR] * 10,
        )
        with patch("ui.party_status.pyxel.blt"):
            mock.party_panel.draw_faces(mock.dimmed_member_indexes)
        self.assertEqual(
            palette_shifter.shifted.call_args_list,
            [
                call(DIMMED_PALETTE),
                call(MONOCHROME_PALETTE),
                call(DIMMED_PALETTE),
                call(DIMMED_PALETTE),
            ],
        )

        mock.update(InputState(confirm=InputButton(True, True)))

        self.assertEqual(target.hp, initial_hp)
        self.assertFalse(target.poisoned)
        self.assertFalse(target.paralyzed)
        self.assertEqual(target.sleeping, 0)
        self.assertEqual(target.confused, 0)
        self.assertTrue(target.stunned)
        self.assertEqual(mock.member.mp, initial_mp - mock.spells["CURE"].mp)
        self.assertEqual(proficiency.progress, 85)
        random_value.assert_not_called()
        play_se.assert_called_once_with("spell_healing1")

        for _frame in range(PROFICIENCY_ANIMATION_FRAME_COUNT + 1):
            mock.update(InputState())
        self.assertIs(mock.phase, SpellSelectionPhase.TARGET)
        self.assertEqual(mock.member_cursor.selected_key, 0)
        self.assertIn(mock.proficiency_window, mock.windows)

        invalid_action = Mock()
        mock.on_invalid_action = invalid_action
        remaining_mp = mock.member.mp
        self.assertEqual(mock._usable_target_indexes(mock.spells["CURE"]), ())

        mock.update(InputState(confirm=InputButton(True, True)))

        self.assertIs(mock.phase, SpellSelectionPhase.TARGET)
        self.assertEqual(mock.member.mp, remaining_mp)
        self.assertTrue(target.stunned)
        invalid_action.assert_called_once_with()
        self.assertEqual(mock.dimmed_member_indexes, frozenset(range(5)))
        self.assertTrue(
            all(text.color == DEFAULT_TEXT_COLOR for text in mock.party_window.texts)
        )
        mock.update(InputState(cancel=InputButton(True, True)))
        self.assertEqual(mock.dimmed_member_indexes, frozenset())
        self.assertTrue(
            all(text.color == DEFAULT_TEXT_COLOR for text in mock.party_window.texts)
        )

    @patch("ui.spell_menu.play_se")
    def test_fade_activates_without_ally_targeting_and_spends_mp(
        self,
        play_se: Mock,
    ) -> None:
        activate = Mock(return_value=True)
        mock = SpellMenuHarness(member_index=0, on_field_fade=activate)
        proficiency = mock.member.proficiency(ProficiencyKind.NETHER)
        proficiency.level = 4
        mock.member.proficiency(ProficiencyKind.MYSTIC).level = 9
        spell = mock.spells["FADE"]
        mock.member.mp = max(mock.member.mp, spell.mp)
        initial_mp = mock.member.mp
        initial_progress = proficiency.progress
        mock._build_windows()

        mock.update(InputState(confirm=InputButton(True, True)))
        mock.spell_cursor.select_key("FADE")
        mock.update(InputState(confirm=InputButton(True, True)))

        activate.assert_called_once_with()
        self.assertIs(mock.phase, SpellSelectionPhase.SPELL)
        self.assertFalse(mock.member_cursor.active)
        self.assertEqual(mock.member.mp, initial_mp - spell.mp)
        self.assertEqual(proficiency.progress, initial_progress)
        self.assertIsNone(mock._proficiency_animation)
        play_se.assert_called_once_with("spell_healing1")
        self.assertIs(mock.phase, SpellSelectionPhase.SPELL)
        self.assertEqual(mock.spell_cursor.selected_key, "FADE")

    def test_teleport_uses_shared_destination_menu_without_proficiency_growth(
        self,
    ) -> None:
        teleport = Mock(return_value=True)
        target = TeleportTarget("sample_town", "サンプルの町")
        mock = SpellMenuHarness(
            member_index=0,
            event_spell_keys={"TELEPORT"},
            teleport_targets=(target,),
            on_field_teleport=teleport,
        )
        spell = mock.spells["TELEPORT"]
        proficiency = mock.member.proficiency(ProficiencyKind.MYSTIC)
        initial_mp = mock.member.mp
        initial_progress = proficiency.progress

        mock.update(InputState(confirm=InputButton(True, True)))
        mock.spell_cursor.select_key(spell.key)
        mock.update(InputState(confirm=InputButton(True, True)))

        self.assertIsNotNone(mock.teleport_menu)
        assert mock.teleport_menu is not None
        self.assertEqual(mock.teleport_menu.cursor.selected_key, "sample_town")
        mock.update(InputState(confirm=InputButton(True, True)))

        teleport.assert_called_once_with("sample_town")
        self.assertEqual(mock.member.mp, initial_mp - spell.mp)
        self.assertEqual(proficiency.progress, initial_progress)
        self.assertIsNone(mock._proficiency_animation)

    def test_canceling_teleport_destination_returns_to_spell_selection(self) -> None:
        mock = SpellMenuHarness(
            event_spell_keys={"TELEPORT"},
            teleport_targets=(TeleportTarget("sample_town", "サンプルの町"),),
            on_field_teleport=Mock(return_value=True),
        )
        mock.update(InputState(confirm=InputButton(True, True)))
        mock.spell_cursor.select_key("TELEPORT")
        mock.update(InputState(confirm=InputButton(True, True)))

        mock.update(InputState(cancel=InputButton(True, True)))

        self.assertIsNone(mock.teleport_menu)
        self.assertIs(mock.phase, SpellSelectionPhase.SPELL)
        self.assertEqual(mock.spell_cursor.selected_key, "TELEPORT")

    def test_fade_activation_failure_does_not_spend_mp(self) -> None:
        activate = Mock(return_value=False)
        invalid_action = Mock()
        mock = SpellMenuHarness(member_index=0, on_field_fade=activate)
        mock.on_invalid_action = invalid_action
        proficiency = mock.member.proficiency(ProficiencyKind.NETHER)
        proficiency.level = 4
        spell = mock.spells["FADE"]
        mock.member.mp = max(mock.member.mp, spell.mp)
        initial_mp = mock.member.mp
        mock._build_windows()

        mock.update(InputState(confirm=InputButton(True, True)))
        mock.spell_cursor.select_key("FADE")
        mock.update(InputState(confirm=InputButton(True, True)))

        self.assertEqual(mock.member.mp, initial_mp)
        invalid_action.assert_called_once_with()

    @patch("ui.spell_menu.play_se")
    @patch("ui.spell_menu.random.random")
    def test_revive_spells_restore_dead_targets_at_authored_hp_percentages(
        self,
        random_value: Mock,
        play_se: Mock,
    ) -> None:
        cases = (("REVIVE1", 25, ()), ("REVIVE2", 100, {"REVIVE2"}))
        for spell_key, percentage, event_spell_keys in cases:
            with self.subTest(spell_key=spell_key):
                mock = SpellMenuHarness(
                    member_index=1,
                    event_spell_keys=event_spell_keys,
                )
                sacred = mock.member.proficiency(ProficiencyKind.SACRED)
                sacred.level = 5
                mock.member.mp = max(mock.member.mp, mock.spells[spell_key].mp)
                mock._build_windows()
                target = mock.party[0]
                target.hp = 0
                target.stunned = True
                initial_mp = mock.member.mp

                mock.update(InputState(confirm=InputButton(True, True)))
                mock.spell_cursor.select_key(spell_key)
                mock.update(InputState(confirm=InputButton(True, True)))

                self.assertIs(mock.phase, SpellSelectionPhase.TARGET)
                self.assertEqual(
                    mock._usable_target_indexes(mock.spells[spell_key]),
                    (0,),
                )
                mock.update(InputState(confirm=InputButton(True, True)))

                self.assertEqual(
                    target.hp,
                    max(1, target.max_hp * percentage // 100),
                )
                self.assertFalse(target.stunned)
                self.assertEqual(mock.member.mp, initial_mp - mock.spells[spell_key].mp)

        random_value.assert_not_called()
        self.assertEqual(play_se.call_count, len(cases))

    @patch("ui.spell_menu.play_se")
    @patch("ui.spell_menu.random.random", return_value=0.5)
    def test_healing_keeps_target_selection_on_next_injured_member(
        self,
        _random_value: Mock,
        _play_se: Mock,
    ) -> None:
        mock = SpellMenuHarness(member_index=1)
        mock.party[0].hp = 1
        mock.party[1].hp = 1

        mock.update(InputState(confirm=InputButton(True, True)))
        mock.update(InputState(confirm=InputButton(True, True)))
        mock.update(InputState(confirm=InputButton(True, True)))

        for _frame in range(PROFICIENCY_ANIMATION_FRAME_COUNT + 1):
            mock.update(InputState())

        self.assertIs(mock.phase, SpellSelectionPhase.TARGET)
        self.assertEqual(mock.selected_spell.key, "HEALING1")
        self.assertEqual(mock.member_cursor.selected_key, 1)
        self.assertEqual(mock.dimmed_member_indexes, frozenset((0, 2, 3, 4)))

    def test_spell_cursor_draws_only_after_caster_confirmation(self) -> None:
        mock = SpellMenuHarness()
        mock.windows = tuple(Mock() for _ in mock.windows)
        mock.caster_cursor = Mock(active=True)
        mock.spell_cursor = Mock(selected_key="FIRE1", active=False)
        mock.member_cursor = Mock(active=False)

        with patch("ui.spell_menu.pyxel.blt"):
            mock.draw()
        mock.caster_cursor.draw.assert_called_once_with()
        mock.spell_cursor.draw.assert_not_called()

        mock.phase = SpellSelectionPhase.SPELL
        with patch("ui.spell_menu.pyxel.blt"):
            mock.draw()
        self.assertEqual(mock.caster_cursor.draw.call_count, 2)
        mock.spell_cursor.draw.assert_called_once_with()
        mock.member_cursor.draw.assert_not_called()

        mock.phase = SpellSelectionPhase.TARGET
        with patch("ui.spell_menu.pyxel.blt"):
            mock.draw()
        self.assertEqual(mock.caster_cursor.draw.call_count, 3)
        self.assertEqual(mock.spell_cursor.draw.call_count, 2)
        mock.member_cursor.draw.assert_called_once_with()

    def test_level_zero_spell_appears_only_when_event_key_is_supplied(self) -> None:
        without_event = SpellMenuHarness()
        with_event = SpellMenuHarness(event_spell_keys={"TELEPORT"})
        level_zero_y = SPELL_FIRST_Y + 9 * SPELL_ROW_HEIGHT

        self.assertNotIn(
            "TELEPORT",
            [target.key for target in without_event.spell_cursor.targets],
        )
        teleport = next(
            target
            for target in with_event.spell_cursor.targets
            if target.key == "TELEPORT"
        )
        self.assertEqual((teleport.x, teleport.y), (SPELL_CURSOR_X[0], level_zero_y))

    def test_member_without_spell_aptitude_has_no_cursor_selection(self) -> None:
        mock = SpellMenuHarness(member_index=4)

        self.assertEqual(mock.member.definition.key, "Ragna")
        self.assertEqual(mock.spell_window.texts, ())
        self.assertIsNone(mock.selected_spell)
        self.assertEqual(mock.guide_window.texts, ())

        mock.update(InputState(confirm=InputButton(True, True)))
        self.assertIs(mock.phase, SpellSelectionPhase.CASTER)

    def test_duplicate_type_and_level_is_rejected(self) -> None:
        mock = SpellMenuHarness()
        fire = mock.spells["FIRE1"]
        spells = dict(mock.spells)
        spells["DUPLICATE"] = replace(fire, key="DUPLICATE")

        with self.assertRaisesRegex(SpellMenuDataError, "重複"):
            SpellMenuHarness(spells=spells)


if __name__ == "__main__":
    unittest.main()
