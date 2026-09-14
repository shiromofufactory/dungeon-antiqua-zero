from __future__ import annotations

import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from tools.screen_mocks.battle import (
    ATTACK_DAMAGE_FRAME_COUNT,
    ATTACK_EFFECT_CELL_SIZE,
    ATTACK_HIT_FRAME_COUNT,
    ATTACK_HIT_PATTERN_FRAME_COUNT,
    ATTACK_HIT_START_FRAME,
    ATTACK_MOTION_FRAME_COUNT,
    ATTACK_POSE_RAISE_FRAME_COUNT,
    ATTACK_POSE_SWING_FRAME_COUNT,
    ATTACK_LANDING_GUARD_FRAME_COUNT,
    ATTACK_RETURN_JUMP_FRAME_COUNT,
    ATTACK_BLUNT_SE_ID,
    ATTACK_SE_ID_BY_SUBTYPE,
    ATTACK_SLASH_SE_ID,
    AIM_ATTACK_HIT_START_FRAME,
    AIM_GAUGE_ADJUSTMENT,
    AIM_GUARD_WAIT_FRAME_COUNT,
    AIM_HIT_VALUE_BONUS,
    AIM_RETICLE_CENTER_SOURCE,
    AIM_RETICLE_END_DISTANCE,
    AIM_RETICLE_HOLD_FRAME_COUNT,
    AIM_RETICLE_MOVE_FRAME_COUNT,
    AIM_RETICLE_START_FRAME,
    AIM_RETICLE_START_DISTANCE,
    BATTLE_ENTRANCE_FRAME_COUNT,
    BATTLE_BGM_ID,
    BATTLE_ESCAPE_SE_ID,
    BATTLE_FOCUS_SE_ID,
    BATTLE_HIDE_SE_ID,
    BATTLE_HIT_SE_ID,
    BATTLE_IDENTIFY_SE_ID,
    BATTLE_MONSTER_DEATH_SE_ID,
    BATTLE_MOCK_MONSTER_KEYS,
    BATTLE_MOCK_PARTY_CHARACTER_KEYS,
    BATTLE_TEST_PARTY,
    ACTIVE_PARTY_PULSE_CYCLE_FRAME_COUNT,
    ACTIVE_PARTY_PULSE_MIN_BASE_RATE,
    ACTIVE_PARTY_PULSE_PALETTE,
    ACTIVE_PARTY_PULSE_TARGET_COLOR,
    COMMAND_GUIDE_DELAY_FRAME_COUNT,
    COMMAND_GUIDE_FIRST_Y,
    COMMAND_GUIDE_LINE_SPACING,
    COMMAND_GUIDE_TEXT_KEYS,
    COMMAND_GUIDE_TEXT_X,
    COMMAND_GUIDE_WINDOW_GRID,
    COMMAND_TEXT_KEYS,
    ADDITIONAL_EFFECT_MARKER_FRAME_COUNT,
    ADDITIONAL_EFFECT_MARKER_HEIGHT,
    ADDITIONAL_EFFECT_MARKER_WIDTH,
    CRITICAL_FLASH_COLOR,
    CRITICAL_FLASH_FRAME_COUNT,
    CRITICAL_MARKER_FRAME_COUNT,
    CRITICAL_MARKER_HEIGHT,
    CRITICAL_MARKER_SOURCE_X,
    CRITICAL_MARKER_SOURCE_Y,
    CRITICAL_MARKER_WIDTH,
    DEFENSE_DOWN_MARKER_SOURCE_X,
    DEFENSE_DOWN_MARKER_SOURCE_Y,
    FORMATION_COMMAND_GUIDE_TEXT_KEYS,
    ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT,
    DAMAGE_POPUP_LAST_FRAME_HOLD_COUNT,
    DAMAGE_NUMBER_SPRITE_X,
    DAMAGE_NUMBER_SPRITE_Y,
    DAMAGE_NUMBER_SPRITE_SIZE,
    AFFINITY_ICON_SOURCE_X,
    WEAK_ICON_SOURCE_Y,
    RESIST_ICON_SOURCE_Y,
    HEALING_NUMBER_SPRITE_Y,
    DA2_MONSTER_ENTRANCE_SLIDE_STEPS,
    DA2_MONSTER_ENTRANCE_STEP_DISTANCE,
    DEAD_SPRITE_SOURCE_X,
    DEAD_SPRITE_WIDTH,
    DEFEND_SPRITE_SOURCE_X,
    ESCAPE_RUN_DESTINATION_X,
    ESCAPE_MESSAGE_TEXT_POSITION,
    ESCAPE_RUN_PATTERN_FRAME_COUNT,
    ESCAPE_RUN_SPEED,
    FORMATION_MOVE_FRAME_COUNT,
    FORMATION_SPRITE_STEP_X,
    FORMATION_WALK_PATTERN_FRAME_COUNT,
    FOCUS_ATTACK_MULTIPLIER,
    FOCUS_PRESENTATION_FRAME_COUNT,
    HIDE_PRESENTATION_FRAME_COUNT,
    IDENTIFY_EFFECT_CENTER_SOURCE_X,
    IDENTIFY_EFFECT_FRAME_COUNT,
    IDENTIFY_EFFECT_SOURCE_Y,
    IDENTIFY_EFFECT_TILE_SIZE,
    IDENTIFY_EFFECT_TRANSPARENT_INDEX,
    IDENTIFY_DETAIL_IMAGE_Y,
    IDENTIFY_DETAIL_SMALL_IMAGE_X,
    IDENTIFY_DETAIL_SMALL_WINDOW_GRID,
    IDENTIFIED_MONSTER_HP_LABEL_OFFSET_X,
    IDENTIFIED_MONSTER_HP_OFFSET_Y,
    IDENTIFIED_MONSTER_HP_VALUE_OFFSET_X,
    VICTORY_RETURN_SPEED,
    VICTORY_RETURN_START_X,
    GLOBAL_COMMAND_WINDOW_GRID,
    ITEM_WINDOW_GRID,
    ITEM_GUIDE_WINDOW_GRID,
    MONSTER_BLINK_FRAME_COUNT,
    MONSTER_DAMAGE_FRAME_COUNT,
    MONSTER_DAMAGE_SPRITE_SOURCE_X,
    MONSTER_ENTRANCE_FRAME_COUNTS,
    MONSTER_MISS_FRAME_COUNT,
    MONSTER_POSITIONS,
    NEAR_DEATH_SPRITE_SOURCE_X,
    MISS_SPRITE_SOURCE_X,
    MISS_SPRITE_WIDTH,
    PARTY_ENTRANCE_COMPLETE_FRAME,
    PARTY_ENTRANCE_FRAME_COUNT,
    PARTY_ENTRANCE_OFFSET_Y,
    PARTY_SPRITE_Y,
    PARTY_ENTRANCE_START_X,
    PARTY_ENTRANCE_STAGGER_FRAME_COUNT,
    PARTY_CONDITION_ICON_OFFSET_X,
    PARALYZE_ICON_SIZE,
    PARALYZE_ICON_SOURCE_X,
    PARALYZE_ICON_SOURCE_Y,
    POISON_ICON_SIZE,
    POISON_ICON_SOURCE_X,
    POISON_ICON_SOURCE_Y,
    POISON_ICON_PATTERN_FRAME_COUNT,
    POISON_MONSTER_OFFSET_X,
    STUN_ICON_SIZE,
    STUN_ICON_SOURCE_X,
    STUN_ICON_SOURCE_Y,
    STUN_MARKER_SOURCE_X,
    STUN_MARKER_SOURCE_Y,
    STUN_MONSTER_OFFSET_X,
    BATTLE_POPUP_FRAME_COUNT,
    ACTION_MOVE_DISTANCE,
    ACTION_MOVE_SPEED,
    SPELL_CAST_SPRITE_SOURCE_X,
    SLEEP_ICON_PATTERN_FRAME_COUNT,
    SLEEP_ICON_SIZE,
    SLEEP_ICON_SOURCE_X,
    SLEEP_ICON_SOURCE_Y,
    SLEEP_MAX_TURNS,
    SLEEP_MIN_TURNS,
    SLOW_ICON_PATTERN_FRAME_COUNT,
    SPEED_ICON_NEGATIVE_SOURCE_Y,
    SPEED_ICON_SIZE,
    SPEED_ICON_SOURCE_X,
    SPEED_ICON_TRANSPARENT_INDEX,
    PROTECTION_ICON_NAME_OFFSET_X,
    PROTECTION_ICON_PATTERN_FRAME_COUNTS,
    PROTECTION_ICON_SIZE,
    PROTECTION_ICON_SOURCE_X,
    PROTECTION_ICON_SOURCE_Y,
    SPELL_POST_EFFECT_WAIT_FRAME_COUNT,
    SPELL_RESULT_OVERLAP_FRAME_COUNT,
    BattleActionPresentation,
    BattleAttackPresentation,
    BattleHealingPopup,
    BattleAffinityPopup,
    BattleSpellDamagePopup,
    BattleMockCharacter,
    BattleGlobalCommand,
    BattleItemCandidate,
    BattleMockMonster,
    BattleMockPhase,
    BattleResult,
    BattleScene,
    BattleScreenMock,
    BattleTargetSpellEffect,
    BattleTimedPopup,
    FormationAnimationCompletion,
    FormationRow,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SPELL_GUIDE_WINDOW_GRID,
    SPELL_MP_WINDOW_GRID,
    SPELL_WINDOW_GRID,
    TIMELINE_ANIMATION_FRAME_COUNT,
    TIMELINE_ENTRANCE_COMPLETE_FRAME,
    TIMELINE_ENTRANCE_FRAME_COUNT,
    TIMELINE_ENTRANCE_STAGGER_FRAME_COUNT,
    TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT,
    TIMELINE_INTERRUPT_OVERFLOW_FRAME_COUNT,
    TIMELINE_INTERRUPT_SLIDE_FRAME_COUNT,
    TIMELINE_VISIBLE_ENTRY_COUNT,
    UNSELECTABLE_TARGET_PALETTE,
    UNSELECTABLE_TARGET_PALETTE_BASE_RATE,
    WEAPON_ATTRIBUTE_RESISTANCE,
    TimelineAnimationPhase,
    WindowText,
    ascii_to_fullwidth,
    identify_detail_texts,
    member_attack_reach,
    selectable_attack_target_indexes,
)
from battle_commands import BattleCommand, BattleCommandOption
from attack_pose import AttackPoseDefinition, AttackWeaponSprite
from battle_timeline import (
    TimelineEntry,
    TimelineOrder,
    complete_timeline_action,
)
from localization import Localizer
from member import (
    EquipmentSlot,
    MAX_INTERNAL_LEVEL,
    MIN_INTERNAL_LEVEL,
    ProficiencyKind,
)
from battle_magic import SpellAffinity, member_spell_ability, member_spell_modifier
from item import AdditionalEffect, AttackAttribute
from resistance import ResistanceType
from state import Language, SaveData, Settings
from systems import (
    MONSTER_IDENTIFY_FIELD_KEYS,
    MonsterRecordSystem,
)
from spell_effect import SpellEffectDefinition, SpellEffectPlayer
from text_catalog import TextCatalog
from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_character_records,
    load_mock_items,
    load_mock_party,
    load_mock_skills,
    load_mock_spells,
)
from tools.screen_mocks._runtime import FPS
from input import Direction, InputButton, InputDevice, InputState
from monster import MonsterBattleState, MonsterCombatStats, MonsterDefinition
from rendering import (
    DEFAULT_FADE_FRAME_COUNT,
    DIMMED_PALETTE,
    MONSTER_DEATH_BRIGHTEN_FRAME_COUNT,
    MONSTER_DEATH_DISSOLVE_FRAME_COUNT,
    MONSTER_DEATH_PALETTE,
    MONSTER_DEATH_TINT_FRAME_COUNT,
    MONOCHROME_PALETTE,
    PaletteShifter,
    SPELL_EFFECT_FLASH_PALETTE,
    FadeThroughBlack,
    MonsterDeathAnimation,
)
from resources import load_record_array
from ui import CursorTarget, Window, WindowCursor
from ui import DEFAULT_TEXT_COLOR


_JAPANESE_COMMAND_LABELS = {
    BattleCommand.ATTACK: "こうげき",
    BattleCommand.AMBUSH: "きしゅう",
    BattleCommand.SPELL: "じゅもん",
    BattleCommand.AIM: "ねらう",
    BattleCommand.HIDE: "かくれる",
    BattleCommand.DEFEND: "ぼうぎょ",
    BattleCommand.ESCAPE: "にげる",
    BattleCommand.ITEM: "アイテム",
    BattleCommand.FORMATION: "こうたい",
}


def _damage_test_monster(
    index: int = 0,
    *,
    hp: int = 10_000,
    spell_resistance: int = 0,
    weaknesses: frozenset[ResistanceType] = frozenset(),
    resistances: frozenset[ResistanceType] = frozenset(),
) -> BattleMockMonster:
    return BattleMockMonster(
        key=f"damage-monster-{index}",
        names={},
        image_id=str(index),
        width=64,
        height=64,
        icon_x=0,
        icon_y=0,
        is_front_row=True,
        state=MonsterBattleState(max_hp=hp),
        agility=1,
        combat_stats=MonsterCombatStats(0, 0, 0, 0, spell_resistance),
        weaknesses=weaknesses,
        resistances=resistances,
    )


class BattleScreenMockTest(unittest.TestCase):
    def _mock_command_labels(self, mock: BattleScreenMock) -> None:
        mock._command_label = Mock(side_effect=_JAPANESE_COMMAND_LABELS.__getitem__)

    def test_mock_uses_sixty_fps(self) -> None:
        self.assertEqual(FPS, 60)

    def test_all_weapon_attack_attributes_map_to_monster_weaknesses(self) -> None:
        self.assertEqual(
            WEAPON_ATTRIBUTE_RESISTANCE,
            {
                AttackAttribute.FIRE: ResistanceType.FIRE,
                AttackAttribute.FREEZE: ResistanceType.FREEZE,
                AttackAttribute.DARK: ResistanceType.DARK,
            },
        )

    def test_draw_uses_explicit_back_to_front_order(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock._draw_background = Mock()
        mock._draw_party = Mock()
        mock._draw_monsters = Mock()
        mock._draw_party_attack_effect = Mock()
        mock._draw_spell_effects = Mock()
        mock._draw_sleeping_icons = Mock()
        mock._draw_poison_icons = Mock()
        mock._draw_paralyze_icons = Mock()
        mock._draw_stun_icons = Mock()
        mock._draw_speed_modifier_icons = Mock()
        mock._draw_party_attack_damage = Mock()
        mock._draw_monster_attack_result = Mock()
        mock._draw_target_cursor = Mock()
        mock._draw_timeline = Mock()
        mock._draw_windows = Mock()
        mock._draw_protection_icons = Mock()

        manager = Mock()
        manager.attach_mock(mock._draw_background, "background")
        manager.attach_mock(mock._draw_party, "party")
        manager.attach_mock(mock._draw_monsters, "monsters")
        manager.attach_mock(mock._draw_party_attack_effect, "party_attack_effect")
        manager.attach_mock(mock._draw_spell_effects, "spell_effects")
        manager.attach_mock(mock._draw_sleeping_icons, "sleeping_icons")
        manager.attach_mock(mock._draw_poison_icons, "poison_icons")
        manager.attach_mock(mock._draw_paralyze_icons, "paralyze_icons")
        manager.attach_mock(mock._draw_stun_icons, "stun_icons")
        manager.attach_mock(mock._draw_speed_modifier_icons, "speed_modifier_icons")
        manager.attach_mock(mock._draw_party_attack_damage, "party_attack_damage")
        manager.attach_mock(mock._draw_monster_attack_result, "monster_attack")
        manager.attach_mock(mock._draw_target_cursor, "target")
        manager.attach_mock(mock._draw_timeline, "timeline")
        manager.attach_mock(mock._draw_windows, "windows")
        manager.attach_mock(mock._draw_protection_icons, "protection_icons")

        mock.draw()

        self.assertEqual(
            manager.mock_calls,
            [
                call.background(),
                call.party(),
                call.monsters(),
                call.party_attack_effect(),
                call.spell_effects(),
                call.sleeping_icons(),
                call.poison_icons(),
                call.paralyze_icons(),
                call.stun_icons(),
                call.speed_modifier_icons(),
                call.party_attack_damage(),
                call.monster_attack(),
                call.timeline(),
                call.windows(),
                call.protection_icons(),
                call.target(),
            ],
        )

    def test_draw_background_is_opaque(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.background = object()

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_background()

        blt.assert_called_once_with(
            0,
            0,
            mock.background,
            0,
            0,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
        )

    def test_critical_hit_flashes_the_background_for_two_impact_frames(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.settings = Settings(screen_flash_enabled=True)
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.attack_presentation = BattleAttackPresentation(
            target_index=0,
            damage=10,
            poses=(),
            effect_row=2,
            is_critical=True,
            elapsed_frame=ATTACK_HIT_START_FRAME,
            damage_applied=True,
        )

        self.assertTrue(mock._critical_flash_visible())
        mock.attack_presentation.elapsed_frame += 1
        self.assertTrue(mock._critical_flash_visible())
        mock.attack_presentation.elapsed_frame += 1
        self.assertFalse(mock._critical_flash_visible())
        self.assertEqual(CRITICAL_FLASH_FRAME_COUNT, 2)

    def test_reduced_flashing_draws_da2_smash_marker_over_monster(self) -> None:
        monster = _damage_test_monster()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.settings = Settings(screen_flash_enabled=False)
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.monsters = (monster,)
        mock.attack_presentation = BattleAttackPresentation(
            target_index=0,
            damage=10,
            poses=(),
            effect_row=2,
            is_critical=True,
            elapsed_frame=(
                ATTACK_HIT_START_FRAME + ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT
            ),
            damage_applied=True,
        )
        mock.monster_attack_target_index = None
        mock.monster_attack_animation_frame = -1
        mock._monster_draw_x = Mock(return_value=4)

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_critical_markers()

        blt.assert_called_once_with(
            22,
            MONSTER_POSITIONS[0][1] + 20,
            0,
            CRITICAL_MARKER_SOURCE_X,
            CRITICAL_MARKER_SOURCE_Y,
            CRITICAL_MARKER_WIDTH,
            CRITICAL_MARKER_HEIGHT,
            1,
        )
        self.assertEqual(CRITICAL_MARKER_WIDTH, 28)
        self.assertEqual(CRITICAL_MARKER_FRAME_COUNT, MONSTER_MISS_FRAME_COUNT)

    def test_reduced_flashing_draws_da2_smash_marker_over_party_target(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.settings = Settings(screen_flash_enabled=False)
        mock.phase = BattleMockPhase.MONSTER_ACTION
        mock.attack_presentation = None
        mock.monster_attack_target_index = 0
        mock.monster_attack_critical = True
        mock.monster_attack_animation_frame = 0
        mock.party_visuals = (
            SimpleNamespace(member=SimpleNamespace(formation_row=FormationRow.FRONT)),
        )

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_critical_markers()

        blt.assert_called_once_with(
            156,
            64,
            0,
            CRITICAL_MARKER_SOURCE_X,
            CRITICAL_MARKER_SOURCE_Y,
            CRITICAL_MARKER_WIDTH,
            CRITICAL_MARKER_HEIGHT,
            1,
        )
        self.assertFalse(mock._critical_flash_visible())
        self.assertEqual(CRITICAL_FLASH_COLOR, 33)

    def test_stun_marker_uses_authored_text_at_the_smash_position(self) -> None:
        monster = _damage_test_monster()
        monster.state.stunned = True
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.settings = Settings(screen_flash_enabled=True)
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.monsters = (monster,)
        mock.attack_presentation = BattleAttackPresentation(
            target_index=0,
            damage=10,
            poses=(),
            effect_row=2,
            additional_effects=(AdditionalEffect.STUN,),
            elapsed_frame=(
                ATTACK_HIT_START_FRAME + ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT
            ),
            damage_applied=True,
        )
        mock._monster_draw_x = Mock(return_value=4)

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_additional_effect_markers()

        blt.assert_called_once_with(
            22,
            MONSTER_POSITIONS[0][1] + 20,
            0,
            STUN_MARKER_SOURCE_X,
            STUN_MARKER_SOURCE_Y,
            ADDITIONAL_EFFECT_MARKER_WIDTH,
            ADDITIONAL_EFFECT_MARKER_HEIGHT,
            1,
        )
        self.assertEqual((STUN_MARKER_SOURCE_X, STUN_MARKER_SOURCE_Y), (208, 8))
        self.assertEqual(ADDITIONAL_EFFECT_MARKER_FRAME_COUNT, 26)

    def test_defense_down_marker_uses_authored_text(self) -> None:
        monster = _damage_test_monster()
        monster.state.defense_modifier = -1
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.settings = Settings(screen_flash_enabled=True)
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.monsters = (monster,)
        mock.attack_presentation = BattleAttackPresentation(
            target_index=0,
            damage=10,
            poses=(),
            effect_row=2,
            additional_effects=(AdditionalEffect.DEFENSE_DOWN,),
            elapsed_frame=(
                ATTACK_HIT_START_FRAME + ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT
            ),
            damage_applied=True,
        )
        mock._monster_draw_x = Mock(return_value=4)

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_additional_effect_markers()

        self.assertEqual(blt.call_args.args[3], DEFENSE_DOWN_MARKER_SOURCE_X)
        self.assertEqual(blt.call_args.args[4], DEFENSE_DOWN_MARKER_SOURCE_Y)
        self.assertEqual(
            (DEFENSE_DOWN_MARKER_SOURCE_X, DEFENSE_DOWN_MARKER_SOURCE_Y),
            (224, 8),
        )

    def test_smash_suppresses_an_overlapping_stun_marker(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.settings = Settings(screen_flash_enabled=False)
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.attack_presentation = BattleAttackPresentation(
            target_index=0,
            damage=10,
            poses=(),
            effect_row=2,
            is_critical=True,
            additional_effects=(AdditionalEffect.STUN,),
            elapsed_frame=(
                ATTACK_HIT_START_FRAME + ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT
            ),
            damage_applied=True,
        )

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_additional_effect_markers()

        blt.assert_not_called()

    def test_weak_marker_suppresses_overlapping_smash_and_status_markers(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.settings = Settings(screen_flash_enabled=False)
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.attack_presentation = BattleAttackPresentation(
            target_index=0,
            damage=10,
            poses=(),
            effect_row=2,
            is_critical=True,
            is_weak=True,
            additional_effects=(AdditionalEffect.STUN,),
            elapsed_frame=(
                ATTACK_HIT_START_FRAME + ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT
            ),
            damage_applied=True,
        )
        mock.monster_attack_target_index = None
        mock.monster_attack_animation_frame = -1

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_critical_markers()
            mock._draw_additional_effect_markers()

        blt.assert_not_called()

    def test_elemental_weak_critical_keeps_the_normal_flash(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.settings = Settings(screen_flash_enabled=True)
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.attack_presentation = BattleAttackPresentation(
            target_index=0,
            damage=10,
            poses=(),
            effect_row=2,
            is_critical=True,
            is_weak=True,
            elapsed_frame=ATTACK_HIT_START_FRAME,
            damage_applied=True,
        )

        self.assertTrue(mock._critical_flash_visible())

    def test_battle_fixture_uses_configured_members_at_level_ninety_nine(self) -> None:
        self.assertEqual(
            BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            tuple(state.character_key for state in BATTLE_TEST_PARTY),
        )
        party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )

        self.assertEqual(
            tuple(member.definition.key for member in party),
            BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        self.assertEqual(len(party), len(BATTLE_TEST_PARTY))
        self.assertTrue(
            all(member.internal_level == MAX_INTERNAL_LEVEL for member in party)
        )

    def test_mock_initializes_display_data_from_generated_records(self) -> None:
        with (
            patch("tools.screen_mocks.battle.initialize_screen_mock") as initialize,
            patch("tools.screen_mocks.battle.create_mock_input_reader"),
            patch("tools.screen_mocks.battle.BgmPlayer"),
            patch("tools.screen_mocks.battle.ImageResources") as images,
            patch("tools.screen_mocks.battle.SpellEffectRenderer"),
            patch("tools.screen_mocks.battle.load_spell_effects", return_value={}),
            patch("tools.screen_mocks.battle.FontResources") as fonts,
            patch("tools.screen_mocks.battle.WindowFactory") as windows,
            patch(
                "battle_timeline.random.uniform",
                side_effect=(
                    *(2.0 for _state in BATTLE_TEST_PARTY),
                    *(1.0 for _monster_key in BATTLE_MOCK_MONSTER_KEYS),
                ),
            ),
            patch("tools.screen_mocks.battle.pyxel.run"),
        ):
            images.return_value.entry.return_value = SimpleNamespace(
                width=SCREEN_WIDTH,
                height=SCREEN_HEIGHT,
            )
            palette_shifter = Mock(
                base_colors=(0x000000, 0xFF0080, 0x4C4C4C, 0x858585),
            )
            initialize.return_value = palette_shifter
            images.return_value.image.return_value = object()
            fonts.return_value.font_for.return_value = object()
            windows.return_value.create.return_value = Mock()
            command_cursor = Mock()
            target_cursor = Mock()
            escape_cursor = Mock()
            restarted_command_cursor = Mock()
            windows.return_value.create.return_value.set_cursor.side_effect = (
                command_cursor,
                target_cursor,
                escape_cursor,
                restarted_command_cursor,
            )

            mock = BattleScreenMock()

        guide_window_call = windows.return_value.create.call_args_list[0]
        self.assertEqual(
            guide_window_call.args[:4],
            COMMAND_GUIDE_WINDOW_GRID,
        )
        self.assertFalse(guide_window_call.kwargs["opened"])
        global_command_window_call = windows.return_value.create.call_args_list[2]
        self.assertEqual(
            global_command_window_call.args[:4],
            GLOBAL_COMMAND_WINDOW_GRID,
        )
        self.assertEqual(GLOBAL_COMMAND_WINDOW_GRID[2], 15)
        self.assertFalse(global_command_window_call.kwargs["opened"])
        item_guide_window_call = windows.return_value.create.call_args_list[3]
        self.assertEqual(
            item_guide_window_call.args[:4],
            ITEM_GUIDE_WINDOW_GRID,
        )
        self.assertFalse(item_guide_window_call.kwargs["opened"])
        self.assertEqual(
            windows.return_value.create.call_args_list[5].args[:4],
            SPELL_WINDOW_GRID,
        )
        self.assertEqual(
            windows.return_value.create.call_args_list[6].args[:4],
            SPELL_GUIDE_WINDOW_GRID,
        )
        self.assertEqual(
            windows.return_value.create.call_args_list[7].args[:4],
            SPELL_MP_WINDOW_GRID,
        )
        action_popup_window_call = windows.return_value.create.call_args_list[15]
        self.assertTrue(action_popup_window_call.kwargs["thin_frame"])

        self.assertEqual(
            tuple(member.definition.key for member in mock.party),
            BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        self.assertTrue(
            all(
                member.internal_level
                == member.definition.joining_internal_level(MIN_INTERNAL_LEVEL)
                for member in mock.party
            )
        )
        character_records = {
            record["name_en"]: record
            for record in load_mock_character_records()
        }
        expected_party_records = tuple(
            character_records[key]
            for key in BATTLE_MOCK_PARTY_CHARACTER_KEYS
        )
        self.assertEqual(
            [visual.battle_sprite for visual in mock.party_visuals],
            [record["battle_sprite"] for record in expected_party_records],
        )
        self.assertEqual(
            [(entry.icon_x, entry.icon_y) for entry in mock.timeline],
            [
                (record["icon_x"], record["icon_y"])
                for record in expected_party_records
            ]
            + [
                (128, 16),
                (128, 16),
                (128, 16),
                (224, 16),
                (224, 16),
            ],
        )
        self.assertEqual(
            tuple(monster.key for monster in mock.monsters),
            BATTLE_MOCK_MONSTER_KEYS,
        )
        self.assertEqual(
            [monster.state.hp for monster in mock.monsters],
            [25, 25, 25, 20, 20],
        )
        self.assertEqual(
            [monster.agility for monster in mock.monsters],
            [15, 15, 15, 12, 12],
        )
        self.assertEqual(
            mock.monsters[0].combat_stats,
            MonsterCombatStats(
                attack=8,
                hit=95,
                defense=0,
                evasion=0,
                spell_resistance=5,
            ),
        )
        self.assertEqual(
            mock.monsters[-1].combat_stats,
            MonsterCombatStats(attack=15, hit=85, defense=0, evasion=0),
        )
        self.assertEqual(mock.timeline, mock.party_visuals + mock.monsters)
        initial_gauges = sorted(
            (
                *(visual.agility * 2.0 for visual in mock.party_visuals),
                *(monster.agility * 1.0 for monster in mock.monsters),
            ),
            reverse=True,
        )
        gauge_offset = 64.0 - initial_gauges[0]
        self.assertEqual(
            tuple(entry.gauge for entry in mock._timeline_order.entries),
            tuple(gauge + gauge_offset for gauge in initial_gauges),
        )
        self.assertEqual(
            mock.inventory_system.catalog_count,
            len(load_mock_items()),
        )
        self.assertTrue(
            all(
                mock.inventory_system.quantity(item) == 1
                for item in load_mock_items().values()
            )
        )
        self.assertIs(mock.phase, BattleMockPhase.ENTRANCE)
        self.assertEqual(mock.entrance_animation_frame, 0)
        self.assertTrue(mock.entrance_fade.is_active)
        self.assertFalse(mock.command_cursor.active)
        palette_shifter.set_global_mix.assert_called_with(
            base_rate=0.0,
            target_color=0x000000,
        )
        self.assertEqual(
            palette_shifter.define_mix.call_args_list,
            [
                call(
                    UNSELECTABLE_TARGET_PALETTE,
                    base_rate=UNSELECTABLE_TARGET_PALETTE_BASE_RATE,
                    target_color=0x858585,
                ),
                call(
                    UNSELECTABLE_TARGET_PALETTE,
                    base_rate=UNSELECTABLE_TARGET_PALETTE_BASE_RATE,
                    target_color=0x858585,
                ),
                call(
                    ACTIVE_PARTY_PULSE_PALETTE,
                    base_rate=1.0,
                    target_color=ACTIVE_PARTY_PULSE_TARGET_COLOR,
                ),
            ],
        )
        self.assertIs(mock.party[1].formation_row, FormationRow.FRONT)
        self.assertEqual(
            [monster.is_front_row for monster in mock.monsters],
            [False, False, True, True, True],
        )
        self.assertEqual(member_attack_reach(mock.party[0]), 1)
        self.assertIsNone(mock.active_party_index)
        mock.active_party_index = 0
        self.assertEqual(mock._active_member_attack_targets(), (2, 3, 4))
        mock.active_party_index = 1
        self.assertEqual(mock._active_member_attack_targets(), (0, 1, 2, 3, 4))
        mock.active_party_index = 0
        target_definitions = (
            windows.return_value.create.return_value.set_cursor.call_args_list[1]
            .args[0]
        )
        self.assertEqual(
            [(target.x, target.y, target.key) for target in target_definitions],
            [
                ((x + 8) // 4, (y + 16) // 4, index)
                for index, (x, y) in enumerate(MONSTER_POSITIONS)
            ],
        )
        self.assertFalse(mock.target_cursor.active)
        self.assertFalse(mock.escape_cursor.active)
        self.assertEqual(mock.escape_animation_frame, 0)
        self.assertEqual(mock.escape_start_x, ())
        self.assertFalse(mock.escape_requested)
        self.assertIsNone(mock.escape_actor_index)
        self.assertEqual(mock.escaped_party_indexes, set())
        self.assertEqual(mock.temporary_front_party_indexes, set())
        first_member = mock.party[0]
        self.assertIn(
            ascii_to_fullwidth(
                f"{first_member.hp:3d}/{first_member.max_hp:3d}"
            ),
            [
                call.args[0]
                for call in windows.return_value.create.return_value.add_text.call_args_list
            ],
        )
        created_texts = [
            placement.text
            for create_call in windows.return_value.create.call_args_list
            for placement in (
                create_call.args[4]
                if len(create_call.args) >= 5
                else ()
            )
        ]
        self.assertIn("ほんとうに　にげて　いいですか？", created_texts)
        self.assertIn(ascii_to_fullwidth("にげだした..."), created_texts)
        self.assertIn("はい", created_texts)
        self.assertIn("いいえ", created_texts)

    def test_entrance_blocks_input_until_all_animations_finish(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ENTRANCE
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock._update_entrance_animation = Mock()
        mock.command_window = Mock()

        mock.update()

        mock._update_entrance_animation.assert_called_once_with()
        mock.command_window.open.assert_not_called()

    def test_entrance_fades_in_then_activates_first_timeline_actor(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ENTRANCE
        mock.entrance_animation_frame = 0
        mock.entrance_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        mock.entrance_fade.start_fade_in()
        mock.palette_shifter = Mock(base_colors=(0x000000,))
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock._activate_timeline_head = Mock()

        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_entrance_animation()

        self.assertIs(mock.phase, BattleMockPhase.ENTRANCE)
        self.assertFalse(mock.entrance_fade.is_active)
        mock.palette_shifter.set_global_mix.assert_called_with(
            base_rate=1.0,
            target_color=0x000000,
        )

        for _frame in range(
            BATTLE_ENTRANCE_FRAME_COUNT - DEFAULT_FADE_FRAME_COUNT
        ):
            mock._update_entrance_animation()

        self.assertEqual(
            mock.entrance_animation_frame,
            BATTLE_ENTRANCE_FRAME_COUNT,
        )
        mock._activate_timeline_head.assert_called_once_with()

    def test_entrance_waits_before_activating_timeline_when_surprise_is_prevented(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.entrance_animation_frame = BATTLE_ENTRANCE_FRAME_COUNT - 1
        mock.entrance_fade = Mock(is_active=False)
        mock.palette_shifter = Mock()
        mock._show_surprise_notice = Mock(return_value=True)
        mock._activate_timeline_head = Mock()

        mock._update_entrance_animation()

        self.assertEqual(
            mock.entrance_animation_frame,
            BATTLE_ENTRANCE_FRAME_COUNT,
        )
        mock._show_surprise_notice.assert_called_once_with()
        mock._activate_timeline_head.assert_not_called()

    def test_surprise_prevention_notice_waits_for_acknowledgement(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ENTRANCE
        mock.surprise_prevented_by_index = 0
        definition = Mock()
        definition.localized_name.return_value = "クレス"
        mock.party = (SimpleNamespace(definition=definition),)
        mock.texts = Mock()
        mock.texts.formatted_text.return_value = "クレスが ふいうちを ふせいだ！"
        mock.localizer = Mock()
        mock._show_battle_popup = Mock()
        mock.battle_popup = BattleTimedPopup(frames_remaining=1)
        mock.battle_popup_window = Mock()

        waiting = mock._show_surprise_notice()

        self.assertTrue(waiting)
        self.assertIs(mock.phase, BattleMockPhase.SURPRISE_PREVENTED)
        self.assertFalse(mock.battle_popup.visible)
        mock.battle_popup_window.clear_texts.assert_called_once_with()
        mock.battle_popup_window.add_text.assert_called_once_with(
            "クレスが ふいうちを ふせいだ！",
            *ESCAPE_MESSAGE_TEXT_POSITION,
        )
        mock._show_battle_popup.assert_not_called()

        mock._activate_timeline_head = Mock()
        mock._update_surprise_prevented(InputState())
        mock._activate_timeline_head.assert_not_called()

        mock._update_surprise_prevented(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertFalse(mock.battle_popup.visible)
        mock._activate_timeline_head.assert_called_once_with()

    def test_party_sprites_use_formation_and_defense_source_images(self) -> None:
        self.assertEqual(DEFEND_SPRITE_SOURCE_X, 16 * 7)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.character_sprites = object()
        mock.party_visuals = (
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT),
                battle_sprite=2,
            ),
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.BACK),
                battle_sprite=4,
            ),
        )
        mock.phase = BattleMockPhase.COMMAND
        mock.defending_party_indexes = {1}

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party()

        self.assertEqual(
            blt.call_args_list,
            [
                call(156, 64, mock.character_sprites, 0, 64, 16, 32, 1),
                call(
                    176,
                    92,
                    mock.character_sprites,
                    DEFEND_SPRITE_SOURCE_X,
                    128,
                    16,
                    32,
                    1,
                ),
            ],
        )

    def test_surprised_party_sprites_face_backward(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.character_sprites = object()
        mock.party_visuals = (
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT),
                battle_sprite=2,
            ),
        )
        mock.phase = BattleMockPhase.COMMAND
        mock.surprise_active = True
        mock.defending_party_indexes = set()

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party()

        blt.assert_called_once_with(
            156,
            64,
            mock.character_sprites,
            0,
            64,
            -16,
            32,
            1,
        )

    def test_party_uses_near_death_and_wide_dead_poses(self) -> None:
        self.assertEqual(NEAR_DEATH_SPRITE_SOURCE_X, 16 * 6)
        self.assertEqual(DEAD_SPRITE_SOURCE_X, 16 * 9)
        self.assertEqual(DEAD_SPRITE_WIDTH, 24)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.character_sprites = object()
        mock.party_visuals = (
            SimpleNamespace(
                member=SimpleNamespace(
                    formation_row=FormationRow.FRONT,
                    is_dead=False,
                    is_dying=True,
                ),
                battle_sprite=2,
            ),
            SimpleNamespace(
                member=SimpleNamespace(
                    formation_row=FormationRow.FRONT,
                    is_dead=True,
                    is_dying=True,
                ),
                battle_sprite=4,
            ),
        )
        mock.phase = BattleMockPhase.COMMAND
        mock.active_party_index = None
        mock.defending_party_indexes = {1}

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party()

        self.assertEqual(
            blt.call_args_list,
            [
                call(
                    156,
                    64,
                    mock.character_sprites,
                    NEAR_DEATH_SPRITE_SOURCE_X,
                    64,
                    16,
                    32,
                    1,
                ),
                call(
                    160,
                    92,
                    mock.character_sprites,
                    DEAD_SPRITE_SOURCE_X,
                    128,
                    DEAD_SPRITE_WIDTH,
                    32,
                    1,
                ),
            ],
        )

    def test_spell_caster_advances_at_da2_speed_and_uses_defense_pose(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 0
        mock.party_visuals = (
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT)
            ),
        )
        mock.phase = BattleMockPhase.SPELL
        mock.action_party_index = None
        mock.action_offset_x = 0
        mock.action_motion_frame = 0
        mock.action_returning = False
        mock.action_uses_cast_pose = False

        mock._begin_action_motion(use_cast_pose=True)
        for _frame in range(ACTION_MOVE_DISTANCE // ACTION_MOVE_SPEED):
            mock._update_action_motion()

        self.assertEqual(ACTION_MOVE_SPEED, 2)
        self.assertEqual(mock._party_draw_position(0), (140, 64))
        self.assertEqual(SPELL_CAST_SPRITE_SOURCE_X, DEFEND_SPRITE_SOURCE_X)
        self.assertEqual(
            mock._party_sprite_source_x(0),
            SPELL_CAST_SPRITE_SOURCE_X,
        )

    def test_attack_timing_uses_adjusted_sixty_fps_frames(self) -> None:
        self.assertEqual(ATTACK_POSE_RAISE_FRAME_COUNT, 3)
        self.assertEqual(ATTACK_POSE_SWING_FRAME_COUNT, 8)
        self.assertEqual(ATTACK_MOTION_FRAME_COUNT, 11)
        self.assertEqual(ATTACK_HIT_PATTERN_FRAME_COUNT, 5)
        self.assertEqual(ATTACK_HIT_FRAME_COUNT, 15)
        self.assertEqual(DAMAGE_POPUP_LAST_FRAME_HOLD_COUNT, 3)
        self.assertEqual(ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT, 10)
        self.assertEqual(ATTACK_DAMAGE_FRAME_COUNT, 35)

        first = Mock(spec=AttackPoseDefinition)
        second = Mock(spec=AttackPoseDefinition)
        presentation = BattleAttackPresentation(0, 10, (first, second), 1)
        self.assertIs(presentation.pose, first)
        presentation.elapsed_frame = ATTACK_POSE_RAISE_FRAME_COUNT
        self.assertIs(presentation.pose, second)
        presentation.elapsed_frame = ATTACK_MOTION_FRAME_COUNT
        self.assertIsNone(presentation.pose)

    def test_aim_holds_the_first_pose_until_the_reticle_finishes(self) -> None:
        first = Mock(spec=AttackPoseDefinition)
        second = Mock(spec=AttackPoseDefinition)
        presentation = BattleAttackPresentation(
            0,
            10,
            (first, second),
            1,
            is_aimed=True,
        )

        self.assertEqual(AIM_RETICLE_MOVE_FRAME_COUNT, 4)
        self.assertEqual(AIM_RETICLE_HOLD_FRAME_COUNT, 6)
        self.assertEqual(AIM_GUARD_WAIT_FRAME_COUNT, 12)
        self.assertEqual(AIM_ATTACK_HIT_START_FRAME, 22)
        self.assertIsNone(presentation.aim_reticle_distance)
        self.assertFalse(presentation.aim_reticle_moving)
        self.assertTrue(presentation.aim_guard_pose_visible)
        self.assertIsNone(presentation.pose)

        presentation.elapsed_frame = AIM_RETICLE_START_FRAME
        self.assertEqual(presentation.aim_reticle_distance, 32)
        self.assertTrue(presentation.aim_reticle_moving)
        self.assertTrue(presentation.aim_guard_pose_visible)
        self.assertIsNone(presentation.pose)

        presentation.elapsed_frame = (
            AIM_RETICLE_START_FRAME + AIM_RETICLE_MOVE_FRAME_COUNT
        )
        self.assertEqual(presentation.aim_reticle_distance, 8)
        self.assertFalse(presentation.aim_reticle_moving)
        self.assertFalse(presentation.aim_guard_pose_visible)
        self.assertTrue(presentation.aim_reticle_center_visible)
        self.assertIs(presentation.pose, first)

        presentation.elapsed_frame = AIM_ATTACK_HIT_START_FRAME - 1
        self.assertTrue(presentation.aim_reticle_center_visible)
        presentation.elapsed_frame = AIM_ATTACK_HIT_START_FRAME
        self.assertIsNone(presentation.aim_reticle_distance)
        self.assertFalse(presentation.aim_reticle_center_visible)
        self.assertIs(presentation.pose, second)

    def test_aim_uses_defense_pose_before_and_while_the_reticle_moves(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.action_party_index = 0
        mock.action_offset_x = ACTION_MOVE_DISTANCE
        mock.action_returning = False
        mock.action_landing_guard_frames_remaining = 0
        mock.attack_presentation = BattleAttackPresentation(
            0,
            10,
            (),
            1,
            is_aimed=True,
            elapsed_frame=AIM_GUARD_WAIT_FRAME_COUNT - 1,
        )
        mock.party_visuals = (
            SimpleNamespace(member=SimpleNamespace(hp=10, is_dying=False)),
        )

        self.assertEqual(mock._party_sprite_source_x(0), DEFEND_SPRITE_SOURCE_X)

    def test_aim_reticle_converges_around_the_monster_center(self) -> None:
        monster = BattleMockMonster(
            key="monster",
            names={},
            image_id="0",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=20),
            agility=12,
        )
        presentation = BattleAttackPresentation(
            0,
            10,
            (),
            1,
            is_aimed=True,
            elapsed_frame=AIM_GUARD_WAIT_FRAME_COUNT - 1,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.attack_presentation = presentation
        mock.monsters = (monster,)

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_aim_reticle()
        blt.assert_not_called()

        presentation.elapsed_frame = (
            AIM_RETICLE_START_FRAME + AIM_RETICLE_MOVE_FRAME_COUNT
        )
        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_aim_reticle()

        center_x = MONSTER_POSITIONS[0][0] + monster.width // 2
        center_y = MONSTER_POSITIONS[0][1] + monster.height // 2
        self.assertEqual(AIM_RETICLE_START_DISTANCE, 32)
        self.assertEqual(AIM_RETICLE_END_DISTANCE, 8)
        self.assertEqual(
            blt.call_args_list,
            [
                call(center_x - 12, center_y - 12, 0, 0, 128, 8, 8, 1),
                call(center_x + 4, center_y - 12, 0, 8, 128, 8, 8, 1),
                call(center_x - 12, center_y + 4, 0, 0, 136, 8, 8, 1),
                call(center_x + 4, center_y + 4, 0, 8, 136, 8, 8, 1),
                call(
                    center_x - 8,
                    center_y - 8,
                    0,
                    *AIM_RETICLE_CENTER_SOURCE,
                    16,
                    16,
                    1,
                ),
            ],
        )

    def test_attack_sound_matches_da2_weapon_categories(self) -> None:
        for subtype in ("SWORD", "KATANA", "KNIFE", "AXE", "SPEAR"):
            with self.subTest(subtype=subtype):
                self.assertEqual(
                    ATTACK_SE_ID_BY_SUBTYPE[subtype],
                    ATTACK_SLASH_SE_ID,
                )
        for subtype in ("HAMMER", "WAND", "ROD"):
            with self.subTest(subtype=subtype):
                self.assertEqual(
                    ATTACK_SE_ID_BY_SUBTYPE[subtype],
                    ATTACK_BLUNT_SE_ID,
                )

    def test_attack_composite_draws_back_weapon_character_and_front_weapon(self) -> None:
        pose = AttackPoseDefinition(
            "SPEAR-1_2",
            "SPEAR-1",
            "2",
            2,
            (
                AttackWeaponSprite(10, -12, 7, "back", False, False),
                AttackWeaponSprite(11, -11, 6, "front", True, True),
            ),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.character_sprites = object()
        mock.party_visuals = (SimpleNamespace(battle_sprite=1),)

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_attack_composite(0, 140, 64, pose)

        self.assertEqual(
            blt.call_args_list,
            [
                call(128, 71, 0, 160, 32, 16, 16, 1),
                call(140, 64, mock.character_sprites, 32, 32, 16, 32, 1),
                call(129, 70, 0, 176, 32, -16, -16, 1),
            ],
        )

    def test_attack_return_uses_an_eight_frame_backward_jump(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = (
            SimpleNamespace(member=SimpleNamespace(formation_row=FormationRow.FRONT)),
        )
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.action_party_index = 0
        mock.action_offset_x = ACTION_MOVE_DISTANCE
        mock.action_motion_frame = 0
        mock.action_returning = False
        mock.action_uses_cast_pose = False
        mock.action_landing_guard_frames_remaining = 0

        mock._begin_action_return(jump=True)
        self.assertEqual(mock.action_return_frame, 1)
        self.assertEqual(mock._party_draw_position(0), (142, 61))
        for _frame in range(ATTACK_RETURN_JUMP_FRAME_COUNT // 2 - 1):
            mock._update_action_motion()

        self.assertEqual(mock._party_draw_position(0), (148, 56))
        for _frame in range(ATTACK_RETURN_JUMP_FRAME_COUNT // 2):
            mock._update_action_motion()
        self.assertEqual(mock._party_draw_position(0), (156, 64))
        self.assertEqual(
            mock.action_landing_guard_frames_remaining,
            ATTACK_LANDING_GUARD_FRAME_COUNT,
        )
        self.assertEqual(mock._party_sprite_source_x(0), DEFEND_SPRITE_SOURCE_X)
        for _frame in range(ATTACK_LANDING_GUARD_FRAME_COUNT - 1):
            mock._update_action_motion()
            self.assertEqual(
                mock._party_sprite_source_x(0),
                DEFEND_SPRITE_SOURCE_X,
            )
        mock._update_action_motion()
        self.assertIsNone(mock.action_party_index)
        self.assertEqual(mock._party_draw_position(0), (156, 64))

    def test_attack_damage_popup_starts_ten_frames_after_hit_effect(self) -> None:
        monster = BattleMockMonster(
            key="monster",
            names={},
            image_id="0",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=20),
            agility=12,
        )
        presentation = BattleAttackPresentation(
            0,
            12,
            (),
            2,
            elapsed_frame=ATTACK_HIT_START_FRAME,
            damage_applied=True,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.attack_presentation = presentation
        mock.attack_effect_image = object()
        mock.monsters = (monster,)

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party_attack_effect()
            mock._draw_party_attack_damage()

        self.assertEqual(
            blt.call_args_list,
            [
                call(
                    MONSTER_POSITIONS[0][0],
                    MONSTER_POSITIONS[0][1] + 8,
                    mock.attack_effect_image,
                    0,
                    128,
                    64,
                    64,
                    1,
                ),
            ],
        )

        presentation.elapsed_frame += ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT
        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party_attack_damage()

        self.assertEqual(
            blt.call_args_list,
            [
                call(
                    28,
                    MONSTER_POSITIONS[0][1] + monster.height - 10,
                    0,
                    DAMAGE_NUMBER_SPRITE_X + 8,
                    DAMAGE_NUMBER_SPRITE_Y,
                    8,
                    8,
                    1,
                ),
                call(
                    36,
                    MONSTER_POSITIONS[0][1] + monster.height - 10,
                    0,
                    DAMAGE_NUMBER_SPRITE_X + 16,
                    DAMAGE_NUMBER_SPRITE_Y,
                    8,
                    8,
                    1,
                ),
            ],
        )

    def test_party_attack_miss_keeps_hp_and_does_not_play_hit_effect(self) -> None:
        monster = BattleMockMonster(
            key="monster",
            names={},
            image_id="0",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=20),
            agility=12,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.monsters = (monster,)
        mock.attack_effect_image = object()
        mock.attack_presentation = BattleAttackPresentation(
            target_index=0,
            damage=0,
            poses=(),
            effect_row=2,
            is_hit=False,
            elapsed_frame=ATTACK_HIT_START_FRAME - 1,
        )

        with (
            patch("scenes.battle.play_se") as play_se,
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
        ):
            mock._update_attack_presentation()
            mock.attack_presentation.elapsed_frame += 2
            mock._draw_party_attack_effect()
            mock._draw_party_attack_damage()

        self.assertEqual(monster.state.hp, 20)
        self.assertTrue(mock.attack_presentation.damage_applied)
        play_se.assert_not_called()
        blt.assert_called_once_with(
            28,
            MONSTER_POSITIONS[0][1] + monster.height - 8,
            0,
            MISS_SPRITE_SOURCE_X,
            DAMAGE_NUMBER_SPRITE_Y,
            MISS_SPRITE_WIDTH,
            8,
            1,
        )

    def test_attack_records_weapon_before_return_clears_the_actor(self) -> None:
        monster = BattleMockMonster(
            key="monster",
            names={},
            image_id="0",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=10),
            agility=12,
            level=1,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (monster,)
        mock.action_party_index = 0
        mock.attack_presentation = BattleAttackPresentation(
            target_index=0,
            damage=10,
            poses=(),
            effect_row=2,
            elapsed_frame=ATTACK_HIT_START_FRAME - 1,
        )
        mock._record_equipped_weapon_action = Mock()

        with patch("scenes.battle.play_se"):
            mock._update_attack_presentation()

        mock._record_equipped_weapon_action.assert_called_once_with(
            0,
            (1,),
            defeated_enemy=True,
            critical=False,
        )

        # The actor is cleared well before the damage popup finishes. The
        # proficiency fact must already be retained and must not be recorded twice.
        mock.action_party_index = None
        mock.attack_presentation.elapsed_frame = (
            ATTACK_HIT_START_FRAME
            + ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT
            + ATTACK_DAMAGE_FRAME_COUNT
            - 1
        )
        mock._begin_monster_death = Mock()
        mock._update_attack_presentation()

        mock._record_equipped_weapon_action.assert_called_once()

    def test_critical_attack_records_weapon_progression_bonus(self) -> None:
        monster = _damage_test_monster(hp=10)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (monster,)
        mock.action_party_index = 0
        mock.attack_presentation = BattleAttackPresentation(
            target_index=0,
            damage=10,
            poses=(),
            effect_row=2,
            is_critical=True,
            elapsed_frame=ATTACK_HIT_START_FRAME - 1,
        )
        mock._record_equipped_weapon_action = Mock()

        with patch("scenes.battle.play_se"):
            mock._update_attack_presentation()

        mock._record_equipped_weapon_action.assert_called_once_with(
            0,
            (1,),
            defeated_enemy=True,
            critical=True,
        )

    def test_missed_attack_still_records_weapon_proficiency(self) -> None:
        monster = BattleMockMonster(
            key="monster",
            names={},
            image_id="0",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=10),
            agility=12,
            level=1,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (monster,)
        mock.action_party_index = 0
        mock.attack_presentation = BattleAttackPresentation(
            target_index=0,
            damage=0,
            poses=(),
            effect_row=2,
            is_hit=False,
            elapsed_frame=ATTACK_HIT_START_FRAME - 1,
        )
        mock._record_equipped_weapon_action = Mock()

        mock._update_attack_presentation()

        mock._record_equipped_weapon_action.assert_called_once_with(
            0,
            (1,),
            defeated_enemy=False,
            critical=False,
        )

    def test_cancelled_spell_caster_walks_back_to_the_original_position(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 0
        mock.party_visuals = (
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT)
            ),
        )
        mock.phase = BattleMockPhase.SPELL
        mock.action_party_index = 0
        mock.action_offset_x = ACTION_MOVE_DISTANCE
        mock.action_motion_frame = 0
        mock.action_returning = False
        mock.action_uses_cast_pose = True

        mock._begin_action_return()
        for _frame in range(ACTION_MOVE_DISTANCE // ACTION_MOVE_SPEED):
            mock._update_action_motion()

        self.assertIsNone(mock.action_party_index)
        self.assertEqual(mock._party_draw_position(0), (156, 64))
        self.assertEqual(mock._party_sprite_source_x(0), 0)

    def test_item_user_advances_without_using_the_spell_cast_pose(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 0
        mock.party_visuals = (
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT)
            ),
        )
        mock.phase = BattleMockPhase.ITEM
        mock.action_party_index = None
        mock.action_offset_x = 0
        mock.action_motion_frame = 0
        mock.action_returning = False
        mock.action_uses_cast_pose = False

        mock._begin_action_motion(use_cast_pose=False)
        for _frame in range(ACTION_MOVE_DISTANCE // ACTION_MOVE_SPEED):
            mock._update_action_motion()

        self.assertEqual(mock._party_draw_position(0), (140, 64))
        self.assertEqual(mock._party_sprite_source_x(0), 0)

    def test_cancelled_item_selection_starts_the_return_movement(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ITEM
        mock.selected_command = BattleCommand.ITEM
        mock.item_candidates = (Mock(),)
        mock.selected_item_index = 0
        mock.item_scroll_offset = 0
        mock.item_cursor = Mock()
        mock.action_party_index = 0
        mock.action_offset_x = ACTION_MOVE_DISTANCE
        mock.action_motion_frame = 0
        mock.action_returning = False
        mock.action_uses_cast_pose = False
        mock.item_window = Mock()
        mock.item_guide_window = Mock()
        mock._refresh_command_options = Mock()
        mock.command_cursor = Mock()
        mock.command_window = Mock()

        mock._cancel_item_selection()

        self.assertIs(mock.phase, BattleMockPhase.COMMAND)
        self.assertTrue(mock.action_returning)
        self.assertFalse(mock.action_uses_cast_pose)

    def test_party_entrance_jumps_quickly_with_two_frame_stagger(
        self,
    ) -> None:
        self.assertEqual(PARTY_ENTRANCE_START_X, SCREEN_WIDTH)
        self.assertEqual(PARTY_ENTRANCE_FRAME_COUNT, 10)
        self.assertEqual(PARTY_ENTRANCE_STAGGER_FRAME_COUNT, 2)
        self.assertEqual(PARTY_ENTRANCE_COMPLETE_FRAME, 14)
        self.assertEqual(BATTLE_ENTRANCE_FRAME_COUNT, 20)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ENTRANCE
        mock.party_visuals = tuple(
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT)
            )
            for _index in range(3)
        )

        mock.entrance_animation_frame = 0
        self.assertEqual(
            mock._party_draw_position(0),
            (PARTY_ENTRANCE_START_X, 64 + PARTY_ENTRANCE_OFFSET_Y),
        )
        self.assertIsNone(mock._party_draw_position(1))

        mock.entrance_animation_frame = PARTY_ENTRANCE_STAGGER_FRAME_COUNT
        self.assertEqual(
            mock._party_draw_position(1),
            (PARTY_ENTRANCE_START_X, 92 + PARTY_ENTRANCE_OFFSET_Y),
        )

        mock.entrance_animation_frame = PARTY_ENTRANCE_FRAME_COUNT // 2
        midpoint = mock._party_draw_position(0)
        self.assertIsNotNone(midpoint)
        assert midpoint is not None
        self.assertGreater(midpoint[0], 156)
        self.assertLess(midpoint[0], PARTY_ENTRANCE_START_X)
        self.assertLess(midpoint[1], 64 + PARTY_ENTRANCE_OFFSET_Y)

        for index in range(3):
            mock.entrance_animation_frame = (
                PARTY_ENTRANCE_FRAME_COUNT
                + index * PARTY_ENTRANCE_STAGGER_FRAME_COUNT
            )
            self.assertEqual(
                mock._party_draw_position(index),
                (156 + index * 4, (64, 92, 120)[index]),
            )

    def test_monster_images_and_timeline_icons_use_display_data(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        image = object()
        mock.monsters = (
            SimpleNamespace(key="Coyote", width=96, height=64, is_alive=True),
        )
        mock.monster_images = {"Coyote": image}
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock.phase = BattleMockPhase.COMMAND
        mock.timeline = (
            SimpleNamespace(icon_x=224, icon_y=16),
        )
        mock.timeline_animation_phase = None

        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_monsters()
            mock._draw_timeline()

        self.assertEqual(
            blt.call_args_list,
            [
                call(*MONSTER_POSITIONS[0], image, 0, 0, 96, 64, 1),
                call(70, 220, 1, 224, 16, 16, 16, 1),
                call(74, 216, 0, 88, 16, 8, 8, 1),
            ],
        )

    def test_monster_entrance_matches_da2_slide_timing_at_sixty_fps(self) -> None:
        self.assertEqual(MONSTER_ENTRANCE_FRAME_COUNTS, (16, 16, 14, 14, 12))
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ENTRANCE
        mock.entrance_animation_frame = 0

        for index, ((target_x, _target_y), slide_steps) in enumerate(
            zip(MONSTER_POSITIONS, DA2_MONSTER_ENTRANCE_SLIDE_STEPS)
        ):
            self.assertEqual(
                mock._monster_draw_x(index),
                target_x - slide_steps * DA2_MONSTER_ENTRANCE_STEP_DISTANCE,
            )

        for index, duration in enumerate(MONSTER_ENTRANCE_FRAME_COUNTS):
            mock.entrance_animation_frame = duration
            self.assertEqual(mock._monster_draw_x(index), MONSTER_POSITIONS[index][0])

    def test_attack_reach_and_rows_determine_selectable_targets(self) -> None:
        monsters = tuple(
            SimpleNamespace(is_front_row=is_front_row, is_alive=True)
            for is_front_row in (False, False, False, True, True)
        )
        expected = {
            (True, 1): (3, 4),
            (False, 1): (),
            (True, 2): (0, 1, 2, 3, 4),
            (False, 2): (3, 4),
            (True, 3): (0, 1, 2, 3, 4),
            (False, 3): (0, 1, 2, 3, 4),
        }

        for (is_front_row, reach), target_indexes in expected.items():
            with self.subTest(is_front_row=is_front_row, reach=reach):
                self.assertEqual(
                    selectable_attack_target_indexes(
                        attacker_is_front_row=is_front_row,
                        weapon_reach=reach,
                        monsters=monsters,
                    ),
                    target_indexes,
                )

    def test_attack_starts_at_last_selectable_target_and_keeps_command_open(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (SimpleNamespace(is_front_row=True),)
        mock.active_party_index = 0
        mock.monsters = tuple(
            SimpleNamespace(is_front_row=is_front_row, is_alive=True)
            for is_front_row in (False, False, False, True, True)
        )
        mock.command_cursor = SimpleNamespace(active=True)
        mock.target_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.phase = BattleMockPhase.COMMAND
        mock.selected_command = None
        mock.selectable_target_indexes = ()
        mock.selected_target_index = None
        mock._refresh_monster_name_colors = Mock()

        with (
            patch("scenes.battle.member_can_attack", return_value=True),
            patch("scenes.battle.member_attack_reach", return_value=1),
        ):
            self.assertTrue(mock._begin_attack_target_selection())

        self.assertEqual(mock.selectable_target_indexes, (3, 4))
        self.assertEqual(mock.selected_target_index, 4)
        self.assertEqual(mock.selected_command, "attack")
        self.assertIs(mock.phase, BattleMockPhase.TARGET)
        self.assertFalse(mock.command_cursor.active)
        self.assertTrue(mock.target_cursor.active)
        self.assertEqual(mock.action_party_index, 0)
        self.assertFalse(mock.action_returning)
        mock.target_cursor.select_key.assert_called_once_with(4)
        mock._refresh_monster_name_colors.assert_called_once_with()
        mock.command_window.close_immediately.assert_not_called()

    def test_reach_one_back_row_member_cannot_start_target_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (SimpleNamespace(is_front_row=False),)
        mock.active_party_index = 0
        mock.monsters = tuple(
            SimpleNamespace(is_front_row=is_front_row, is_alive=True)
            for is_front_row in (False, False, False, True, True)
        )
        mock.command_cursor = SimpleNamespace(active=True)
        mock.target_cursor = Mock(active=False)
        mock.phase = BattleMockPhase.COMMAND
        mock.selected_command = None
        mock.selectable_target_indexes = ()
        mock.selected_target_index = None

        with (
            patch("scenes.battle.member_can_attack", return_value=True),
            patch("scenes.battle.member_attack_reach", return_value=1),
        ):
            self.assertFalse(mock._begin_attack_target_selection())

        self.assertIs(mock.phase, BattleMockPhase.COMMAND)
        self.assertTrue(mock.command_cursor.active)
        self.assertIsNone(mock.selected_target_index)

    def test_ambush_ignores_weapon_reach_and_targets_every_monster_row(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (SimpleNamespace(is_front_row=False),)
        mock.active_party_index = 0
        mock.monsters = tuple(
            SimpleNamespace(is_front_row=is_front_row, is_alive=True)
            for is_front_row in (False, False, False, True, True)
        )
        mock.command_cursor = SimpleNamespace(active=True)
        mock.target_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.phase = BattleMockPhase.COMMAND
        mock.selected_command = None
        mock.selectable_target_indexes = ()
        mock.selected_target_index = None
        mock._refresh_monster_name_colors = Mock()

        with (
            patch("scenes.battle.member_can_attack", return_value=True),
            patch("scenes.battle.member_attack_reach", return_value=1),
        ):
            self.assertTrue(
                mock._begin_attack_target_selection(command=BattleCommand.AMBUSH)
            )

        self.assertEqual(mock.selectable_target_indexes, (0, 1, 2, 3, 4))
        self.assertEqual(mock.selected_target_index, 4)

    def test_target_navigation_uses_da2_order_and_skips_unreachable_enemies(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.selectable_target_indexes = (3, 4)
        mock.selected_target_index = 4
        mock.target_cursor = Mock()

        self.assertTrue(mock._move_target(Direction.LEFT))
        self.assertEqual(mock.selected_target_index, 3)
        self.assertTrue(mock._move_target(Direction.RIGHT))
        self.assertEqual(mock.selected_target_index, 4)

    def test_requested_direction_mapping_matches_numbered_monster_layout(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.selectable_target_indexes = (0, 1, 2, 3, 4)
        mock.target_cursor = Mock()

        expected_from_four = {
            Direction.UP: 2,
            Direction.DOWN: 4,
            Direction.RIGHT: 1,
            Direction.LEFT: 0,
        }
        for direction, expected_index in expected_from_four.items():
            with self.subTest(origin=4, direction=direction):
                mock.selected_target_index = 3
                self.assertTrue(mock._move_target(direction))
                self.assertEqual(mock.selected_target_index, expected_index)

        expected_from_two = {
            Direction.UP: 0,
            Direction.DOWN: 0,
            Direction.RIGHT: 4,
            Direction.LEFT: 3,
        }
        for direction, expected_index in expected_from_two.items():
            with self.subTest(origin=2, direction=direction):
                mock.selected_target_index = 1
                self.assertTrue(mock._move_target(direction))
                self.assertEqual(mock.selected_target_index, expected_index)

        mock.selected_target_index = 4
        self.assertTrue(mock._move_target(Direction.LEFT))
        self.assertEqual(mock.selected_target_index, 1)

    def test_horizontal_target_navigation_cycles_in_both_directions(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.selectable_target_indexes = (0, 1, 2, 3, 4)
        mock.target_cursor = Mock()

        # Display numbers 1 -> 4 -> 2 -> 5 -> 3 -> 1.
        right_cycle = (0, 3, 1, 4, 2, 0)
        mock.selected_target_index = right_cycle[0]
        for expected_index in right_cycle[1:]:
            self.assertTrue(mock._move_target(Direction.RIGHT))
            self.assertEqual(mock.selected_target_index, expected_index)

        # LEFT follows the exact reverse path.
        left_cycle = tuple(reversed(right_cycle))
        for expected_index in left_cycle[1:]:
            self.assertTrue(mock._move_target(Direction.LEFT))
            self.assertEqual(mock.selected_target_index, expected_index)

    def test_fiora_right_skips_monster_two_and_moves_from_four_to_five(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.selectable_target_indexes = (3, 4)
        mock.selected_target_index = 3
        mock.target_cursor = Mock()

        self.assertTrue(mock._move_target(Direction.RIGHT))

        self.assertEqual(mock.selected_target_index, 4)
        mock.target_cursor.select_key.assert_called_once_with(4)

    def test_target_cancel_returns_to_command_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_cursor = SimpleNamespace(active=False)
        mock.target_cursor = SimpleNamespace(active=True)
        mock.phase = BattleMockPhase.TARGET
        mock.selected_command = "attack"
        mock.selectable_target_indexes = (2, 3, 4)
        mock.selected_target_index = 4
        mock.action_party_index = 0
        mock.action_offset_x = ACTION_MOVE_DISTANCE
        mock.action_returning = False

        mock._update_target_selection(
            InputState(cancel=InputButton(triggered=True, held=True))
        )

        self.assertIs(mock.phase, BattleMockPhase.COMMAND)
        self.assertTrue(mock.command_cursor.active)
        self.assertFalse(mock.target_cursor.active)
        self.assertIsNone(mock.selected_command)
        self.assertIsNone(mock.selected_target_index)
        self.assertTrue(mock.action_returning)
        self.assertFalse(mock.action_return_jump)

    def test_target_confirm_starts_attack_and_nonlethal_damage_keeps_enemy(self) -> None:
        monsters = tuple(
            BattleMockMonster(
                key=f"monster-{index}",
                names={},
                image_id=str(index),
                width=64,
                height=64,
                icon_x=index * 16,
                icon_y=16,
                is_front_row=True,
                state=MonsterBattleState(max_hp=100),
                agility=12,
                combat_stats=MonsterCombatStats(
                    attack=0,
                    hit=0,
                    defense=10,
                    evasion=20,
                ),
            )
            for index in range(5)
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.command_cursor = SimpleNamespace(active=False)
        mock.target_cursor = SimpleNamespace(active=True)
        mock.command_window = Mock()
        mock.palette_shifter = Mock()
        mock.monsters = monsters
        mock.attack_poses = {}
        mock.phase = BattleMockPhase.TARGET
        mock.selected_command = "attack"
        mock.selectable_target_indexes = (2, 3, 4)
        mock.selected_target_index = 4
        mock.action_party_index = 0
        mock.action_offset_x = ACTION_MOVE_DISTANCE
        mock.action_motion_frame = 0
        mock.action_returning = False
        mock.action_uses_cast_pose = False
        mock.action_return_jump = False
        mock.action_return_frame = 0
        mock.action_return_start_offset = 0
        mock._refresh_monster_name_colors = Mock()
        mock._complete_current_turn = Mock()

        with (
            patch("tools.screen_mocks.battle.random.randint", return_value=8),
            patch("scenes.battle.play_se") as play_se,
        ):
            mock._update_target_selection(
                InputState(confirm=InputButton(triggered=True, held=True))
            )

            self.assertIs(mock.phase, BattleMockPhase.ATTACK_PRESENTATION)
            self.assertEqual(mock.attack_presentation.effect_row, 2)
            self.assertTrue(mock.attack_presentation.is_hit)
            self.assertEqual(mock.attack_presentation.damage, 43)
            self.assertEqual(monsters[4].state.hp, 100)
            for _frame in range(ATTACK_HIT_START_FRAME):
                mock._update_attack_presentation()
            self.assertEqual(monsters[4].state.hp, 57)
            play_se.assert_called_once_with(ATTACK_SLASH_SE_ID)
            for _frame in range(
                ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT + ATTACK_DAMAGE_FRAME_COUNT
            ):
                mock._update_attack_presentation()

        self.assertFalse(mock.target_cursor.active)
        self.assertTrue(monsters[4].is_alive)
        mock.command_window.close_immediately.assert_called_once_with()
        self.assertIsNone(mock.attack_presentation)
        mock._complete_current_turn.assert_called_once_with()

    def test_aim_attack_applies_bonus_popup_and_delayed_gauge(self) -> None:
        monster = BattleMockMonster(
            key="monster",
            names={},
            image_id="0",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=100),
            agility=12,
            combat_stats=MonsterCombatStats(0, 0, 10, 20),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=(BATTLE_MOCK_PARTY_CHARACTER_KEYS[0],),
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.monsters = (monster,)
        mock.attack_poses = {}
        mock.selected_command = BattleCommand.AIM
        mock.selectable_target_indexes = (0,)
        mock.selected_target_index = 0
        mock.target_cursor = Mock(active=True)
        mock.command_window = Mock()
        mock._refresh_monster_name_colors = Mock()
        mock._show_battle_popup = Mock()
        mock._command_label = Mock(return_value="ねらう")
        result = SimpleNamespace(hit=True, damage=12)

        with patch(
            "scenes.battle.resolve_physical_attack",
            return_value=result,
        ) as resolve:
            self.assertTrue(mock._begin_attack_presentation())

        self.assertIs(mock.phase, BattleMockPhase.ATTACK_PRESENTATION)
        self.assertTrue(mock.attack_presentation.is_aimed)
        self.assertEqual(mock.action_gauge_adjustment, AIM_GAUGE_ADJUSTMENT)
        self.assertEqual(
            resolve.call_args.kwargs["hit_value_bonus"],
            AIM_HIT_VALUE_BONUS,
        )
        mock._show_battle_popup.assert_called_once_with(
            "ねらう",
            BATTLE_POPUP_FRAME_COUNT,
        )

    def test_ambush_uses_hidden_attack_rules_then_reveals_member(self) -> None:
        member = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=(BATTLE_MOCK_PARTY_CHARACTER_KEYS[0],),
            internal_level=MAX_INTERNAL_LEVEL,
        )[0]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (member,)
        mock.active_party_index = 0
        mock.hidden_party_indexes = {0}
        mock.monsters = (_damage_test_monster(),)
        mock.attack_poses = {}
        mock.selected_command = BattleCommand.AMBUSH
        mock.selectable_target_indexes = (0,)
        mock.selected_target_index = 0
        mock.target_cursor = Mock(active=True)
        mock.command_window = Mock()
        mock._refresh_monster_name_colors = Mock()
        mock._resolve_member_attack_additional_effects = Mock(return_value=())
        result = SimpleNamespace(hit=True, damage=20, critical=False)

        with (
            patch("scenes.battle.random.randint", side_effect=(99, 99)),
            patch(
                "scenes.battle.resolve_physical_attack",
                return_value=result,
            ) as resolve,
        ):
            self.assertTrue(mock._begin_attack_presentation())

        self.assertTrue(resolve.call_args.kwargs["attacker_hidden"])
        self.assertEqual(resolve.call_args.kwargs["critical_roll"], 99)
        self.assertEqual(mock.hidden_party_indexes, set())
        self.assertIs(mock.phase, BattleMockPhase.ATTACK_PRESENTATION)

    def test_power_hit_and_sleep_are_passed_to_critical_resolution(self) -> None:
        items = load_mock_items()
        skills = load_mock_skills()
        member = load_mock_party(
            items,
            skills,
            character_keys=(BATTLE_MOCK_PARTY_CHARACTER_KEYS[0],),
            internal_level=MAX_INTERNAL_LEVEL,
        )[0]
        member.skills.append(skills["Power Hit"])
        member.equipment = member.equipment.replaced(
            {EquipmentSlot.RIGHT: items["HANZO KUNAI"]}
        )
        monster = _damage_test_monster()
        monster.state.apply_sleep(2)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (member,)
        mock.active_party_index = 0
        mock.monsters = (monster,)
        mock.attack_poses = {}
        mock.selected_command = BattleCommand.ATTACK
        mock.selectable_target_indexes = (0,)
        mock.selected_target_index = 0
        mock.target_cursor = Mock(active=True)
        mock.command_window = Mock()
        mock._refresh_monster_name_colors = Mock()
        result = SimpleNamespace(hit=True, damage=20, critical=True)

        with (
            patch("scenes.battle.random.randint", side_effect=(40, 9)) as randint,
            patch(
                "scenes.battle.resolve_physical_attack",
                return_value=result,
            ) as resolve,
        ):
            self.assertTrue(mock._begin_attack_presentation())

        self.assertTrue(resolve.call_args.kwargs["target_incapacitated"])
        self.assertTrue(resolve.call_args.kwargs["attacker_has_power_hit"])
        self.assertTrue(resolve.call_args.kwargs["weapon_has_power_hit"])
        self.assertEqual(resolve.call_args.kwargs["critical_roll"], 9)
        self.assertTrue(mock.attack_presentation.is_critical)
        self.assertEqual(randint.call_args_list, [call(0, 99), call(0, 99)])

    def test_elemental_weapon_weakness_uses_effective_attack_and_is_recorded(
        self,
    ) -> None:
        items = load_mock_items()
        member = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=(BATTLE_MOCK_PARTY_CHARACTER_KEYS[0],),
            internal_level=MAX_INTERNAL_LEVEL,
        )[0]
        member.equipment = member.equipment.replaced(
            {EquipmentSlot.RIGHT: items["FIRE SPEAR"]}
        )
        monster = _damage_test_monster(
            weaknesses=frozenset((ResistanceType.FIRE,)),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (member,)
        mock.active_party_index = 0
        mock.monsters = (monster,)
        mock.attack_poses = {}
        mock.selected_command = BattleCommand.ATTACK
        mock.selectable_target_indexes = (0,)
        mock.selected_target_index = 0
        mock.target_cursor = Mock(active=True)
        mock.command_window = Mock()
        mock._refresh_monster_name_colors = Mock()
        mock._resolve_member_attack_additional_effects = Mock(return_value=())
        mock.monster_record_system = Mock()
        result = SimpleNamespace(hit=True, damage=20, critical=True)

        with (
            patch("scenes.battle.random.randint", side_effect=(40, 99)),
            patch(
                "scenes.battle.resolve_physical_attack",
                return_value=result,
            ) as resolve,
        ):
            self.assertTrue(mock._begin_attack_presentation())

        self.assertTrue(resolve.call_args.kwargs["weapon_effective"])
        self.assertEqual(resolve.call_args.kwargs["critical_roll"], 99)
        self.assertTrue(mock.attack_presentation.is_weak)
        self.assertTrue(mock.attack_presentation.is_critical)
        mock._resolve_member_attack_additional_effects.assert_called_once_with(
            member,
            items["FIRE SPEAR"],
            monster,
            result,
            attacker_hidden=False,
            weapon_effective=True,
        )
        mock.monster_record_system.reveal_profile.assert_called_once_with(
            monster.key
        )
        mock.monster_record_system.reveal_affinity.assert_called_once_with(
            monster.key,
            ResistanceType.FIRE,
        )

    def test_physical_weak_popup_starts_with_the_damage_result_only_once(
        self,
    ) -> None:
        monster = _damage_test_monster()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (monster,)
        mock.action_party_index = None
        mock.affinity_popups = []
        mock._monster_draw_x = Mock(return_value=4)
        mock.attack_presentation = BattleAttackPresentation(
            target_index=0,
            damage=10,
            poses=(),
            effect_row=2,
            is_critical=True,
            is_weak=True,
            elapsed_frame=(
                ATTACK_HIT_START_FRAME
                + ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT
                - 1
            ),
            damage_applied=True,
            return_started=True,
        )

        mock._update_attack_presentation()
        mock._update_attack_presentation()

        self.assertEqual(len(mock.affinity_popups), 1)
        popup = mock.affinity_popups[0]
        self.assertEqual(
            (popup.affinity, popup.x, popup.y),
            (
                SpellAffinity.WEAK,
                24,
                MONSTER_POSITIONS[0][1] + 20,
            ),
        )

    def test_aim_gauge_is_consumed_by_timeline_reinsertion(self) -> None:
        actor = SimpleNamespace(agility=50)
        other = SimpleNamespace(agility=10)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock._timeline_order = TimelineOrder(
            (
                TimelineEntry(actor, 50, 64.0),
                TimelineEntry(other, 10, 40.0),
            )
        )
        mock.action_gauge_adjustment = AIM_GAUGE_ADJUSTMENT
        mock.command_cursor = SimpleNamespace(active=True)
        mock.command_window = Mock()
        mock._refresh_party_text_colors = Mock()

        mock._start_timeline_animation()

        self.assertEqual(mock.timeline_advance.after.actors, (other, actor))
        self.assertEqual(
            mock.timeline_advance.after.entries[1].gauge,
            50 + AIM_GAUGE_ADJUSTMENT,
        )
        self.assertEqual(mock.action_gauge_adjustment, 0.0)

    def test_focus_records_target_and_holds_guard_pose_for_36_frames(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (SimpleNamespace(hp=30),)
        mock.party_visuals = ()
        mock.monsters = (_damage_test_monster(),)
        mock.active_party_index = 0
        mock.selected_command = BattleCommand.FOCUS
        mock.selectable_target_indexes = (0,)
        mock.selected_target_index = 0
        mock.focused_target_by_party_index = {}
        mock.focus_presentation_elapsed_frame = 0
        mock.command_cursor = SimpleNamespace(active=True)
        mock.target_cursor = SimpleNamespace(active=True)
        mock.command_window = Mock()
        mock._show_battle_popup = Mock()
        mock._command_label = Mock(return_value="ためる")
        mock._refresh_monster_name_colors = Mock()
        mock._complete_current_turn = Mock()

        with patch("scenes.battle.play_se") as play_se:
            self.assertTrue(mock._begin_focus_presentation())

        self.assertEqual(mock.focused_target_by_party_index, {0: 0})
        self.assertIs(mock.phase, BattleMockPhase.FOCUS_PRESENTATION)
        self.assertFalse(mock.command_cursor.active)
        self.assertFalse(mock.target_cursor.active)
        self.assertEqual(mock._party_sprite_source_x(0), DEFEND_SPRITE_SOURCE_X)
        mock._show_battle_popup.assert_called_once_with(
            "ためる",
            FOCUS_PRESENTATION_FRAME_COUNT,
        )
        play_se.assert_called_once_with(BATTLE_FOCUS_SE_ID)

        for _frame in range(FOCUS_PRESENTATION_FRAME_COUNT - 1):
            mock._update_focus_presentation()
        mock._complete_current_turn.assert_not_called()
        mock._update_focus_presentation()
        mock._complete_current_turn.assert_called_once_with()

    def test_focus_target_selection_does_not_begin_attack_movement(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.selected_command = None
        mock.selectable_target_indexes = ()
        mock.selected_target_index = None
        mock.phase = BattleMockPhase.COMMAND
        mock.command_cursor = SimpleNamespace(active=True)
        mock.target_cursor = Mock(active=False)
        mock._active_member_attack_targets = Mock(return_value=(1, 3))
        mock._begin_action_motion = Mock()
        mock._refresh_monster_name_colors = Mock()

        self.assertTrue(
            mock._begin_attack_target_selection(command=BattleCommand.FOCUS)
        )

        self.assertIs(mock.selected_command, BattleCommand.FOCUS)
        self.assertEqual(mock.selected_target_index, 3)
        self.assertIs(mock.phase, BattleMockPhase.TARGET)
        mock._begin_action_motion.assert_not_called()

    def test_focused_attack_doubles_power_and_retargets_first_living_enemy(
        self,
    ) -> None:
        dead_target = _damage_test_monster(1, hp=1)
        dead_target.state.take_damage(1)
        monsters = (_damage_test_monster(0), dead_target)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=(BATTLE_MOCK_PARTY_CHARACTER_KEYS[0],),
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.monsters = monsters
        mock.attack_poses = {}
        mock.focused_target_by_party_index = {0: 1}
        mock.target_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock._refresh_monster_name_colors = Mock()
        mock._begin_action_motion = Mock()
        mock._active_member_attack_targets = Mock(return_value=(0,))
        result = SimpleNamespace(hit=True, damage=12)

        with (
            patch("scenes.battle.member_physical_attack", return_value=21),
            patch(
                "scenes.battle.resolve_physical_attack",
                return_value=result,
            ) as resolve,
        ):
            self.assertTrue(mock._begin_focused_attack())

        self.assertEqual(mock.focused_target_by_party_index, {})
        self.assertEqual(mock.selected_target_index, 0)
        self.assertIs(mock.selected_command, BattleCommand.FOCUS)
        self.assertIs(mock.phase, BattleMockPhase.ATTACK_PRESENTATION)
        self.assertTrue(mock.attack_presentation.is_focused)
        self.assertEqual(
            resolve.call_args.kwargs["attack"],
            21 * FOCUS_ATTACK_MULTIPLIER,
        )

    def test_incapacitation_cancels_focus_state(self) -> None:
        for field, value in (
            ("paralyzed", True),
            ("sleeping", 1),
            ("confused", 1),
            ("stunned", True),
        ):
            with self.subTest(field=field):
                member = SimpleNamespace(
                    hp=30,
                    paralyzed=False,
                    sleeping=0,
                    confused=0,
                    stunned=False,
                )
                setattr(member, field, value)
                mock = BattleScreenMock.__new__(BattleScreenMock)
                mock.party = (member,)
                mock.focused_target_by_party_index = {0: 2}

                mock._clear_interrupted_focus_states()

                self.assertEqual(mock.focused_target_by_party_index, {})

    def test_focused_member_attacks_before_the_command_window_opens(self) -> None:
        member = SimpleNamespace(
            hp=30,
            formation_row=FormationRow.FRONT,
            is_front_row=True,
        )
        visual = BattleMockCharacter(member, 0, 0, 0)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (member,)
        mock.party_visuals = (visual,)
        mock.timeline = (visual,)
        mock.active_party_index = None
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock.escape_requested = False
        mock.escaped_party_indexes = set()
        mock.temporary_front_party_indexes = set()
        mock.defending_party_indexes = set()
        mock.auto_battle_active = False
        mock.command_cursor = Mock()
        mock.command_window = Mock()
        mock._begin_focused_attack = Mock(return_value=True)
        mock._hide_command_guide = Mock()
        mock._refresh_command_options = Mock()
        mock._select_initial_member_command = Mock()
        mock._refresh_input_guide = Mock()
        mock._refresh_party_text_colors = Mock()

        mock._activate_timeline_head()

        self.assertEqual(mock.active_party_index, 0)
        mock._begin_focused_attack.assert_called_once_with()
        mock.command_window.open.assert_not_called()

    def test_sleeping_member_loses_one_turn_without_opening_commands(self) -> None:
        member = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=(BATTLE_MOCK_PARTY_CHARACTER_KEYS[0],),
        )[0]
        member.apply_sleep(2)
        visual = BattleMockCharacter(member, 0, 0, 0)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (member,)
        mock.party_visuals = (visual,)
        mock.timeline = (visual,)
        mock.escape_requested = False
        mock.escaped_party_indexes = set()
        mock.temporary_front_party_indexes = set()
        mock.defending_party_indexes = {0}
        mock.focused_target_by_party_index = {0: 1}
        mock.command_cursor = Mock()
        mock.command_window = Mock()
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock._start_timeline_animation = Mock()

        mock._activate_timeline_head()

        self.assertEqual(member.sleeping, 1)
        self.assertEqual(mock.defending_party_indexes, set())
        self.assertEqual(mock.focused_target_by_party_index, {})
        mock._start_timeline_animation.assert_called_once_with()
        mock.command_window.open.assert_not_called()

    def test_poison_damage_precedes_a_sleeping_members_skipped_turn(self) -> None:
        member = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=(BATTLE_MOCK_PARTY_CHARACTER_KEYS[0],),
        )[0]
        member.poisoned = True
        member.apply_sleep(2)
        starting_hp = member.hp
        visual = BattleMockCharacter(member, 0, 0, 0)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (member,)
        mock.party_visuals = (visual,)
        mock.timeline = (visual,)
        mock.escape_requested = False
        mock.escaped_party_indexes = set()
        mock.temporary_front_party_indexes = set()
        mock.defending_party_indexes = set()
        mock.focused_target_by_party_index = {}
        mock.command_cursor = Mock()
        mock.command_window = Mock()
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock.spell_damage_popups = []
        mock._party_draw_position = Mock(return_value=(172, 64))
        mock._refresh_party_hp_text = Mock()
        mock._start_timeline_animation = Mock()

        mock._activate_timeline_head()

        expected_damage = (member.max_hp + 15) // 16
        self.assertEqual(member.hp, starting_hp - expected_damage)
        self.assertEqual(member.sleeping, 1)
        self.assertEqual(mock.spell_damage_popups[0].damage, expected_damage)
        mock._start_timeline_animation.assert_called_once_with()

    def test_regenerate_recovers_one_sixteenth_at_turn_start(self) -> None:
        skills = load_mock_skills()
        member = load_mock_party(
            load_mock_items(),
            skills,
            character_keys=(BATTLE_MOCK_PARTY_CHARACTER_KEYS[0],),
        )[0]
        member.skills.append(skills["Regenerate"])
        member.hp = 1
        visual = BattleMockCharacter(member, 0, 0, 0)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (member,)
        mock.party_visuals = (visual,)
        mock.spell_damage_popups = []
        mock.healing_popups = []
        mock._party_draw_position = Mock(return_value=(172, 64))
        mock._refresh_party_hp_text = Mock()

        self.assertFalse(mock._apply_turn_start_hp_change(visual))

        expected_healing = (member.max_hp + 15) // 16
        self.assertEqual(member.hp, 1 + expected_healing)
        self.assertEqual(mock.healing_popups[0].amount, expected_healing)
        self.assertEqual(mock.spell_damage_popups, [])
        mock._refresh_party_hp_text.assert_called_once_with(0)

    def test_regenerate_cancels_normal_poison_at_turn_start(self) -> None:
        skills = load_mock_skills()
        member = load_mock_party(
            load_mock_items(),
            skills,
            character_keys=(BATTLE_MOCK_PARTY_CHARACTER_KEYS[0],),
        )[0]
        member.skills.append(skills["Regenerate"])
        member.poisoned = True
        starting_hp = member.hp
        visual = BattleMockCharacter(member, 0, 0, 0)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (member,)
        mock.party_visuals = (visual,)
        mock.spell_damage_popups = []
        mock.healing_popups = []

        self.assertFalse(mock._apply_turn_start_hp_change(visual))

        self.assertEqual(member.hp, starting_hp)
        self.assertEqual(mock.healing_popups, [])
        self.assertEqual(mock.spell_damage_popups, [])

    def test_lethal_attack_starts_death_then_removes_enemy(self) -> None:
        monster = BattleMockMonster(
            key="monster",
            names={},
            image_id="0",
            width=64,
            height=64,
            icon_x=0,
            icon_y=16,
            is_front_row=True,
            state=MonsterBattleState(max_hp=10),
            agility=12,
        )
        actor = object()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (monster,)
        mock.timeline = (actor, monster)
        mock._timeline_order = TimelineOrder(
            (TimelineEntry(actor, 10, 64.0), TimelineEntry(monster, 10, 50.0))
        )
        mock.phase = BattleMockPhase.ATTACK_PRESENTATION
        mock.attack_presentation = BattleAttackPresentation(0, 10, (), 1)
        mock.action_party_index = 0
        mock.action_offset_x = ACTION_MOVE_DISTANCE
        mock.action_motion_frame = 0
        mock.action_returning = False
        mock.action_uses_cast_pose = False
        mock.action_return_jump = False
        mock.action_return_frame = 0
        mock.action_return_start_offset = 0
        mock.selected_target_index = 0
        mock.selectable_target_indexes = (0,)
        mock.target_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.palette_shifter = Mock()
        mock._complete_current_turn = Mock()
        mock.result = None

        with patch("scenes.battle.play_se") as play_se:
            for _frame in range(
                ATTACK_HIT_START_FRAME
                + ATTACK_DAMAGE_POPUP_DELAY_FRAME_COUNT
                + ATTACK_DAMAGE_FRAME_COUNT
            ):
                mock._update_attack_presentation()

        self.assertEqual(monster.state.hp, 0)
        self.assertEqual(
            play_se.call_args_list,
            [
                call(ATTACK_SLASH_SE_ID),
                call(BATTLE_MONSTER_DEATH_SE_ID),
            ],
        )
        self.assertIs(mock.phase, BattleMockPhase.MONSTER_DEATH)
        self.assertEqual(mock.dying_monster_index, 0)
        self.assertIsInstance(mock.monster_death_animation, MonsterDeathAnimation)

        frame_count = (
            MONSTER_DEATH_TINT_FRAME_COUNT
            + MONSTER_DEATH_BRIGHTEN_FRAME_COUNT
            + MONSTER_DEATH_DISSOLVE_FRAME_COUNT
        )
        for _frame in range(frame_count):
            mock._update_monster_death_animation()

        self.assertNotIn(monster, mock.timeline)
        self.assertEqual(mock.timeline[0], actor)
        self.assertIsNone(mock.dying_monster_index)
        self.assertIsNone(mock.monster_death_animation)
        self.assertEqual(
            mock.palette_shifter.remove_variant.call_args_list[0],
            call(UNSELECTABLE_TARGET_PALETTE),
        )
        self.assertEqual(
            mock.palette_shifter.remove_variant.call_args_list[-1],
            call(MONSTER_DEATH_PALETTE),
        )
        self.assertIs(mock.result, BattleResult.VICTORY)
        mock._complete_current_turn.assert_not_called()

    def test_monster_death_reuses_unselectable_palette_slot(self) -> None:
        colors = list(range(62))
        palette_shifter = PaletteShifter(colors, Mock())
        base_variant = tuple(colors)
        palette_shifter.define_variant(DIMMED_PALETTE, base_variant)
        palette_shifter.define_variant(MONOCHROME_PALETTE, base_variant)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.palette_shifter = palette_shifter
        mock.monster_death_animation = MonsterDeathAnimation()

        mock._sync_unselectable_target_palette()
        self.assertEqual(len(colors), 248)

        mock._sync_monster_death_palette()

        self.assertEqual(len(colors), 248)
        with palette_shifter.shifted(MONSTER_DEATH_PALETTE):
            pass
        with self.assertRaisesRegex(KeyError, UNSELECTABLE_TARGET_PALETTE):
            with palette_shifter.shifted(UNSELECTABLE_TARGET_PALETTE):
                pass

        mock._release_palette_variant(MONSTER_DEATH_PALETTE)
        mock._sync_unselectable_target_palette()
        with palette_shifter.shifted(UNSELECTABLE_TARGET_PALETTE):
            pass

    def test_poison_death_of_timeline_head_removes_head_after_death_effect(self) -> None:
        dying = _damage_test_monster(0, hp=1)
        dying.state.poisoned = True
        dying.state.take_poison_damage(1)
        living = _damage_test_monster(1, hp=10)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (dying, living)
        mock._timeline_order = TimelineOrder(
            (
                TimelineEntry(dying, 1, 64.0),
                TimelineEntry(living, 1, 50.0),
            )
        )
        mock.timeline = mock._timeline_order.actors
        mock.monster_death_animation = MonsterDeathAnimation()
        mock.dying_monster_index = 0
        mock.monster_death_from_timeline_head = True
        mock.pending_monster_death_indexes = []
        mock.action_party_index = None
        mock._sync_monster_death_palette = Mock()
        mock._release_palette_variant = Mock()
        mock._start_timeline_removal_animation = Mock()

        frame_count = (
            MONSTER_DEATH_TINT_FRAME_COUNT
            + MONSTER_DEATH_BRIGHTEN_FRAME_COUNT
            + MONSTER_DEATH_DISSOLVE_FRAME_COUNT
        )
        for _frame in range(frame_count):
            mock._update_monster_death_animation()

        self.assertIs(mock.timeline[0], dying)
        mock._start_timeline_removal_animation.assert_called_once_with()
        self.assertFalse(mock.monster_death_from_timeline_head)

    def test_victory_clears_remaining_damage_popups(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.spell_damage_popups = [BattleSpellDamagePopup(10, 20, 3)]

        mock._clear_damage_popups_for_victory()

        self.assertEqual(mock.spell_damage_popups, [])

    def test_simultaneous_spell_defeats_play_each_monster_death_in_order(self) -> None:
        monsters = (_damage_test_monster(0, hp=1), _damage_test_monster(1, hp=1))
        for monster in monsters:
            monster.state.defeat()
        actor = object()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = monsters
        mock._timeline_order = TimelineOrder(
            (
                TimelineEntry(actor, 10, 64.0),
                TimelineEntry(monsters[0], 10, 50.0),
                TimelineEntry(monsters[1], 10, 40.0),
            )
        )
        mock.timeline = mock._timeline_order.actors
        mock.phase = BattleMockPhase.MONSTER_DEATH
        mock.dying_monster_index = 0
        mock.monster_death_animation = MonsterDeathAnimation()
        mock.pending_monster_death_indexes = [1]
        mock.action_party_index = None
        mock.target_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.palette_shifter = Mock()
        mock._complete_current_turn = Mock()
        mock.result = None
        frame_count = (
            MONSTER_DEATH_TINT_FRAME_COUNT
            + MONSTER_DEATH_BRIGHTEN_FRAME_COUNT
            + MONSTER_DEATH_DISSOLVE_FRAME_COUNT
        )

        with patch("scenes.battle.play_se") as play_se:
            for _frame in range(frame_count):
                mock._update_monster_death_animation()

            self.assertEqual(mock.dying_monster_index, 1)
            self.assertNotIn(monsters[0], mock.timeline)
            self.assertIn(monsters[1], mock.timeline)
            self.assertEqual(mock.pending_monster_death_indexes, [])

            for _frame in range(frame_count):
                mock._update_monster_death_animation()

        play_se.assert_called_once_with(BATTLE_MONSTER_DEATH_SE_ID)
        self.assertNotIn(monsters[1], mock.timeline)
        self.assertIs(mock.result, BattleResult.VICTORY)
        mock._complete_current_turn.assert_not_called()

    def test_monster_death_draw_uses_shifted_palette_and_dither(self) -> None:
        monster = BattleMockMonster(
            key="Coyote",
            names={},
            image_id="3",
            width=64,
            height=64,
            icon_x=224,
            icon_y=16,
            is_front_row=True,
            state=MonsterBattleState(max_hp=2),
            agility=12,
        )
        monster.state.defeat()
        animation = MonsterDeathAnimation()
        for _frame in range(
            MONSTER_DEATH_TINT_FRAME_COUNT
            + MONSTER_DEATH_BRIGHTEN_FRAME_COUNT
            + MONSTER_DEATH_DISSOLVE_FRAME_COUNT // 2
        ):
            animation.update()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (monster,)
        mock.monster_images = {"Coyote": object()}
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock.phase = BattleMockPhase.MONSTER_DEATH
        mock.dying_monster_index = 0
        mock.monster_death_animation = animation
        mock.palette_shifter = Mock()
        mock.palette_shifter.shifted.return_value = nullcontext()

        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.dither") as dither,
        ):
            mock._draw_monsters()

        mock.palette_shifter.shifted.assert_called_once_with(
            MONSTER_DEATH_PALETTE
        )
        self.assertEqual(dither.call_args_list, [call(0.5), call(1.0)])
        blt.assert_called_once_with(
            *MONSTER_POSITIONS[0],
            mock.monster_images["Coyote"],
            0,
            0,
            64,
            64,
            1,
        )

    def test_defeating_last_front_monster_promotes_living_rear_monsters(
        self,
    ) -> None:
        rear_monster = BattleMockMonster(
            key="rear",
            names={},
            image_id="1",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=False,
            state=MonsterBattleState(max_hp=2),
            agility=12,
        )
        front_monster = BattleMockMonster(
            key="front",
            names={},
            image_id="2",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=2),
            agility=12,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (rear_monster, front_monster)
        mock.selectable_target_indexes = (1,)
        mock.selected_target_index = 1
        mock.target_cursor = SimpleNamespace(active=True)
        mock.command_window = Mock()
        mock.palette_shifter = Mock()

        with patch("scenes.battle.play_se") as play_se:
            self.assertTrue(mock._begin_monster_death())

        self.assertFalse(front_monster.is_alive)
        self.assertTrue(rear_monster.is_front_row)
        play_se.assert_called_once_with(BATTLE_MONSTER_DEATH_SE_ID)

        rear_monster.restore()
        self.assertTrue(rear_monster.is_alive)
        self.assertFalse(rear_monster.is_front_row)

    def test_unselectable_rear_monster_uses_gray_palette_during_target_selection(
        self,
    ) -> None:
        monsters = (
            BattleMockMonster(
                key="rear",
                names={},
                image_id="1",
                width=64,
                height=64,
                icon_x=0,
                icon_y=0,
                is_front_row=False,
                state=MonsterBattleState(max_hp=2),
                agility=12,
            ),
            BattleMockMonster(
                key="front",
                names={},
                image_id="2",
                width=64,
                height=64,
                icon_x=0,
                icon_y=0,
                is_front_row=True,
                state=MonsterBattleState(max_hp=2),
                agility=12,
            ),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = monsters
        mock.monster_images = {"rear": object(), "front": object()}
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock.phase = BattleMockPhase.TARGET
        mock.selectable_target_indexes = (1,)
        mock.dying_monster_index = None
        mock.palette_shifter = Mock()
        mock.palette_shifter.shifted.return_value = nullcontext()

        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.dither") as dither,
        ):
            mock._draw_monsters()

        mock.palette_shifter.shifted.assert_called_once_with(
            UNSELECTABLE_TARGET_PALETTE,
        )
        dither.assert_not_called()
        self.assertEqual(blt.call_count, 2)

    def test_identify_command_opens_enemy_target_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock()
        mock.command_cursor.selected_key = BattleCommand.IDENTIFY
        mock.command_window = Mock()
        mock.command_window.is_closed = False
        mock.command_window.is_open = True
        mock.selected_command = None
        mock.active_party_index = 1
        mock.last_command_by_party_index = {}
        mock._begin_identify_target_selection = Mock(return_value=True)
        mock._complete_current_turn = Mock()

        mock.update()

        self.assertEqual(
            mock.last_command_by_party_index,
            {1: BattleCommand.IDENTIFY},
        )
        mock._begin_identify_target_selection.assert_called_once_with()
        mock._complete_current_turn.assert_not_called()

    def test_identify_can_target_any_living_monster_and_uses_cast_motion(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 0
        mock.party = (
            SimpleNamespace(has_skill=lambda key: key == "Identify"),
        )
        mock.monsters = (
            SimpleNamespace(is_alive=True),
            SimpleNamespace(is_alive=False),
            SimpleNamespace(is_alive=True),
        )
        mock.command_cursor = Mock(active=True)
        mock.target_cursor = Mock(active=False)
        mock._begin_action_motion = Mock()
        mock._refresh_monster_name_colors = Mock()

        self.assertTrue(mock._begin_identify_target_selection())

        self.assertIs(mock.selected_command, BattleCommand.IDENTIFY)
        self.assertEqual(mock.selectable_target_indexes, (0, 2))
        self.assertEqual(mock.selected_target_index, 2)
        self.assertIs(mock.phase, BattleMockPhase.TARGET)
        mock._begin_action_motion.assert_called_once_with(use_cast_pose=True)
        mock.target_cursor.select_key.assert_called_once_with(2)

    def test_identify_effect_uses_the_authored_bank_zero_tiles(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.IDENTIFY_PRESENTATION
        mock.identify_target_index = 0
        mock.monsters = (SimpleNamespace(width=64, height=64),)
        mock._monster_draw_position = Mock(return_value=(4, 56))

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock.identify_effect_elapsed_frame = 0
            mock._draw_identify_effect()

            self.assertEqual(
                blt.call_args_list,
                [
                    call(12, 64, 0, 0, 144, 16, 16, 1),
                    call(44, 64, 0, 16, 144, 16, 16, 1),
                    call(12, 96, 0, 32, 144, 16, 16, 1),
                    call(44, 96, 0, 48, 144, 16, 16, 1),
                ],
            )
            self.assertEqual(IDENTIFY_EFFECT_TRANSPARENT_INDEX, 1)

            blt.reset_mock()
            mock.identify_effect_elapsed_frame = 2
            mock._draw_identify_effect()

        blt.assert_called_once_with(
            28,
            80,
            0,
            IDENTIFY_EFFECT_CENTER_SOURCE_X,
            IDENTIFY_EFFECT_SOURCE_Y,
            IDENTIFY_EFFECT_TILE_SIZE,
            IDENTIFY_EFFECT_TILE_SIZE,
            IDENTIFY_EFFECT_TRANSPARENT_INDEX,
        )

    def test_identify_confirmation_starts_the_effect_and_da2_sound(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 0
        mock.selected_target_index = 2
        mock.selectable_target_indexes = (0, 2)
        mock.target_cursor = Mock(active=True)
        mock.hidden_party_indexes = {0}
        mock._refresh_monster_name_colors = Mock()

        with patch("scenes.battle.play_se") as play_se:
            self.assertTrue(mock._begin_identify_presentation())

        self.assertIs(mock.phase, BattleMockPhase.IDENTIFY_PRESENTATION)
        self.assertEqual(mock.identify_target_index, 2)
        self.assertEqual(mock.identify_effect_elapsed_frame, 0)
        self.assertFalse(mock.target_cursor.active)
        self.assertEqual(mock.hidden_party_indexes, set())
        play_se.assert_called_once_with(BATTLE_IDENTIFY_SE_ID)

    def test_identify_reveals_the_record_after_its_effect_and_opens_da2_detail(
        self,
    ) -> None:
        save_data = SaveData()
        records = MonsterRecordSystem(save_data)
        records.register_encounter(("Giant Spider",))
        monster = SimpleNamespace(key="Giant Spider", width=64, height=64)
        definition = object()
        detail_window = Mock()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.identify_target_index = 0
        mock.identify_effect_elapsed_frame = IDENTIFY_EFFECT_FRAME_COUNT - 1
        mock.monsters = (monster,)
        mock.monster_record_system = records
        mock.monster_definitions_by_key = {monster.key: definition}
        mock.monster_book_number_by_key = {monster.key: 1}
        mock.save_data = save_data
        mock.item_catalog = {}
        mock.texts = object()
        mock.localizer = object()
        mock.identify_text_factory = object()
        mock.identified_monster_indexes = set()
        mock.window_factory = Mock()
        mock.window_factory.create.return_value = detail_window

        with patch(
            "scenes.battle.identify_detail_texts",
            return_value=(WindowText("detail", 2, 2),),
        ) as detail_texts:
            mock._update_identify_presentation()

        self.assertEqual(
            save_data.monster_records[monster.key],
            set(MONSTER_IDENTIFY_FIELD_KEYS),
        )
        self.assertEqual(mock.identified_monster_indexes, {0})
        self.assertIs(mock.phase, BattleMockPhase.IDENTIFY_RESULT)
        detail_texts.assert_called_once()
        self.assertIs(detail_texts.call_args.kwargs["definition"], definition)
        self.assertEqual(
            detail_texts.call_args.kwargs["revealed_fields"],
            set(MONSTER_IDENTIFY_FIELD_KEYS),
        )
        self.assertEqual(
            mock.window_factory.create.call_args.args[:4],
            (*IDENTIFY_DETAIL_SMALL_WINDOW_GRID, 18),
        )
        detail_window.open_immediately.assert_called_once_with()

    def test_identify_detail_shows_boss_hp_and_omits_stun_affinity(self) -> None:
        records = load_record_array("monsters.json")
        record = dict(next(record for record in records if record["is_boss"] == 1))
        record["tolerance"] = "炎止"
        definition = MonsterDefinition.from_record(record)
        text_factory = Mock()
        text_factory.create.side_effect = (
            lambda text, x, y, **kwargs: WindowText(text, x, y, **kwargs)
        )

        detail = identify_detail_texts(
            number=1,
            definition=definition,
            revealed_fields=set(MONSTER_IDENTIFY_FIELD_KEYS),
            items=load_mock_items(),
            texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
            localizer=Localizer(Language.JAPANESE),
            text_factory=text_factory,
        )
        lines = [text.text for text in detail]

        hp_line = next(text for text in lines if text.startswith("ＨＰ"))
        self.assertIn(ascii_to_fullwidth(str(definition.max_hp)), hp_line)
        self.assertNotIn("？？？？", hp_line)
        self.assertTrue(any(text.startswith("おたから：") for text in lines))
        self.assertFalse(any(text == "おたから：？？？？" for text in lines))
        self.assertTrue(any("%FIRE%" in text for text in lines))
        self.assertFalse(any("スタン" in text or "止" in text for text in lines))

    def test_identify_result_uses_da2_monster_image_position(self) -> None:
        record = load_record_array("monsters.json")[0]
        monster = BattleMockMonster.from_record(record, is_front_row=True)
        definition = MonsterDefinition.from_record(record)
        window = SimpleNamespace(
            content_x=48,
            content_y=8,
            texts=tuple(WindowText("", 0, index * 3) for index in range(11)),
            draw=Mock(),
        )
        image = object()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.IDENTIFY_RESULT
        mock.identify_detail_window = window
        mock.identify_target_index = 0
        mock.monsters = (monster,)
        mock.monster_definitions_by_key = {monster.key: definition}
        mock.monster_images = {monster.key: image}

        with patch("scenes.battle.pyxel.blt") as blt:
            mock._draw_identify_result()

        window.draw.assert_called_once_with()
        blt.assert_called_once_with(
            window.content_x + IDENTIFY_DETAIL_SMALL_IMAGE_X,
            window.content_y + IDENTIFY_DETAIL_IMAGE_Y,
            image,
            0,
            0,
            definition.width,
            definition.height,
            1,
        )

    def test_identified_monster_keeps_showing_current_hp_below_image(self) -> None:
        monster = _damage_test_monster(hp=25)
        monster.state.hp = 17
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.identified_monster_indexes = {0}
        mock._draw_small_text_with_edge = Mock()

        mock._draw_identified_monster_hp(0, monster, 4, 56)

        baseline_y = 56 + monster.height + IDENTIFIED_MONSTER_HP_OFFSET_Y
        self.assertEqual(
            mock._draw_small_text_with_edge.call_args_list,
            [
                call(
                    4 + IDENTIFIED_MONSTER_HP_LABEL_OFFSET_X,
                    baseline_y,
                    "HP",
                    DEFAULT_TEXT_COLOR,
                ),
                call(
                    4 + IDENTIFIED_MONSTER_HP_VALUE_OFFSET_X,
                    baseline_y,
                    "17",
                    DEFAULT_TEXT_COLOR,
                ),
            ],
        )

    def test_identify_result_closes_on_confirm_and_returns_the_actor(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.identify_detail_window = Mock()
        mock.identify_target_index = 2
        mock.identify_effect_elapsed_frame = IDENTIFY_EFFECT_FRAME_COUNT
        mock._begin_action_return = Mock()

        mock._update_identify_result(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertIsNone(mock.identify_detail_window)
        self.assertIsNone(mock.identify_target_index)
        self.assertEqual(mock.identify_effect_elapsed_frame, 0)
        mock._begin_action_return.assert_called_once_with(complete_turn=True)

    def test_hide_starts_da2_motion_and_marks_member_hidden(self) -> None:
        member = SimpleNamespace(has_skill=Mock(return_value=True))
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (member,)
        mock.active_party_index = 0
        mock.hidden_party_indexes = set()
        mock.hide_presentation_elapsed_frame = 99
        mock.command_cursor = Mock(active=True)
        mock.command_window = Mock()
        mock._refresh_party_text_colors = Mock()

        with patch("scenes.battle.play_se") as play_se:
            self.assertTrue(mock._begin_hide())

        self.assertEqual(mock.hidden_party_indexes, {0})
        self.assertEqual(mock.hide_presentation_elapsed_frame, 0)
        self.assertIs(mock.phase, BattleMockPhase.HIDE_PRESENTATION)
        self.assertIs(mock.selected_command, BattleCommand.HIDE)
        self.assertFalse(mock.command_cursor.active)
        mock.command_window.close_immediately.assert_called_once_with()
        play_se.assert_called_once_with(BATTLE_HIDE_SE_ID)

    def test_hide_finishes_after_da2_timing_and_advances_turn(self) -> None:
        visual = SimpleNamespace(display_name=Mock(return_value="シルファ"))
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 0
        mock.party_visuals = (visual,)
        mock.hide_presentation_elapsed_frame = HIDE_PRESENTATION_FRAME_COUNT - 1
        mock.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        mock.localizer = Localizer(Language.JAPANESE)
        mock._show_battle_popup = Mock()
        mock._reveal_hidden_party_if_all_unavailable = Mock()
        mock._complete_current_turn = Mock()

        mock._update_hide_presentation()

        mock._show_battle_popup.assert_called_once()
        self.assertEqual(
            mock._show_battle_popup.call_args.args[0],
            "かくれる",
        )
        mock._reveal_hidden_party_if_all_unavailable.assert_called_once_with()
        mock._complete_current_turn.assert_called_once_with()

    def test_all_hidden_living_members_are_forcibly_revealed(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.hidden_party_indexes = {0, 1}
        mock.party = tuple(
            SimpleNamespace(paralyzed=False, sleeping=0, confused=0)
            for _index in range(2)
        )
        mock._active_party_indexes = Mock(return_value=(0, 1))

        self.assertTrue(mock._reveal_hidden_party_if_all_unavailable())

        self.assertEqual(mock.hidden_party_indexes, set())

    def test_hidden_member_reappears_when_only_visible_member_cannot_act(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.hidden_party_indexes = {0}
        mock.party = (
            SimpleNamespace(paralyzed=False, sleeping=0, confused=0),
            SimpleNamespace(paralyzed=True, sleeping=0, confused=0),
        )
        mock._active_party_indexes = Mock(return_value=(0, 1))

        self.assertTrue(mock._reveal_hidden_party_if_all_unavailable())

        self.assertEqual(mock.hidden_party_indexes, set())

    def test_hidden_member_sprite_is_not_drawn(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.active_party_index = None
        mock.party_visuals = (SimpleNamespace(),)
        mock.escaped_party_indexes = set()
        mock.hidden_party_indexes = {0}

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party()

        blt.assert_not_called()

    def test_hidden_survivor_runs_in_from_screen_right_for_victory(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = (
            SimpleNamespace(
                member=SimpleNamespace(
                    formation_row=FormationRow.FRONT,
                    is_dead=False,
                ),
                battle_sprite=0,
            ),
            SimpleNamespace(
                member=SimpleNamespace(
                    formation_row=FormationRow.BACK,
                    is_dead=False,
                ),
                battle_sprite=1,
            ),
        )
        mock.escaped_party_indexes = {1}
        mock.hidden_party_indexes = {0, 1}

        mock._begin_hidden_party_victory_return()

        self.assertEqual(mock.hidden_party_indexes, set())
        self.assertEqual(mock.victory_returning_party_indexes, {0})
        self.assertEqual(mock.victory_return_frame, 0)

        mock.phase = BattleMockPhase.VICTORY_SUMMARY
        self.assertEqual(
            mock._party_draw_position(0),
            (VICTORY_RETURN_START_X, PARTY_SPRITE_Y[0]),
        )
        self.assertTrue(mock._update_hidden_party_victory_return())
        self.assertEqual(
            mock._party_draw_position(0),
            (VICTORY_RETURN_START_X - VICTORY_RETURN_SPEED, PARTY_SPRITE_Y[0]),
        )
        self.assertTrue(mock._update_hidden_party_victory_return())
        self.assertEqual(
            mock._party_sprite_source_x(0),
            FORMATION_SPRITE_STEP_X,
        )

        while mock._update_hidden_party_victory_return():
            pass

        self.assertEqual(mock.victory_returning_party_indexes, set())
        self.assertEqual(
            mock._party_draw_position(0),
            (mock._party_sprite_x(0), PARTY_SPRITE_Y[0]),
        )

    def test_hidden_members_are_excluded_from_monster_targets(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.hidden_party_indexes = {1}
        mock._active_party_indexes = Mock(return_value=(0, 1, 2))
        mock._party_member_is_front_row = Mock(return_value=True)
        actor = SimpleNamespace(is_front_row=True)

        self.assertEqual(mock._monster_attack_target_indexes(actor), (0, 2))
        self.assertEqual(mock._monster_charge_target_indexes(), (0, 2))

    def test_hidden_front_member_does_not_block_visible_rear_promotion(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.hidden_party_indexes = {0}
        mock._active_party_indexes = Mock(return_value=(0, 1))
        mock._party_member_is_front_row = Mock(
            side_effect=lambda index: index == 0
        )
        mock._party_sprite_x = Mock(side_effect=lambda index: 156 + index * 16)
        mock.temporary_front_party_indexes = set()
        mock.command_cursor = Mock()
        mock.command_window = Mock()
        mock._refresh_party_text_colors = Mock()

        self.assertTrue(
            mock._begin_front_promotion_if_needed(
                FormationAnimationCompletion.START_TIMELINE
            )
        )

        self.assertEqual(mock.formation_actor_indexes, (0, 1))
        self.assertEqual(mock.temporary_front_party_indexes, {0, 1})

    def test_ally_actions_skip_hidden_members_except_the_caster(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 0
        mock.hidden_party_indexes = {0, 1}
        mock._active_party_indexes = Mock(return_value=(0, 1, 2))
        mock.party = tuple(
            SimpleNamespace(protection_level=0) for _index in range(3)
        )

        single = SimpleNamespace(to_all=False, action=None)
        all_targets = SimpleNamespace(to_all=True, action=None)

        self.assertEqual(
            mock._selectable_party_indexes_for_spell(single),
            (0, 2),
        )
        self.assertEqual(
            mock._selectable_party_indexes_for_spell(all_targets),
            (2,),
        )

    def test_item_command_opens_item_selection_instead_of_completing_turn(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock(selected_key=BattleCommand.ITEM)
        mock.command_window = Mock(is_closed=False, is_open=True)
        mock._begin_item_selection = Mock(return_value=True)
        mock._complete_current_turn = Mock()

        mock.update()

        mock._begin_item_selection.assert_called_once_with()
        mock._complete_current_turn.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)

    def test_item_candidates_use_equipment_then_owned_consumables(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        member = mock.party[0]
        member.equipment = member.equipment.replaced(
            {EquipmentSlot.ARM: items["TELEPORT RING"]}
        )
        mock.active_party_index = 0
        from systems import InventorySystem

        mock.inventory_system = InventorySystem.with_one_each(items)
        mock.spells = load_mock_spells()

        candidates = mock._active_member_item_candidates()

        self.assertEqual(
            tuple(candidate.item.key for candidate in candidates[:7]),
            (
                "DAGGER",
                "TELEPORT RING",
                "POTION",
                "REMEDY",
                "MANA DROP",
                "PANACEA",
                "DIVINE TEAR",
            ),
        )
        self.assertTrue(candidates[0].is_equipped)
        self.assertTrue(candidates[1].is_equipped)
        self.assertTrue(all(not candidate.is_equipped for candidate in candidates[2:]))
        candidate_keys = {candidate.item.key for candidate in candidates}
        self.assertIn("MAGNIFIER", candidate_keys)
        self.assertNotIn("FRUIT of STR", candidate_keys)
        self.assertNotIn("FRUIT of AGI", candidate_keys)
        self.assertNotIn("FRUIT of MAG", candidate_keys)
        self.assertNotIn("NECTOR", candidate_keys)

    def test_item_list_uses_its_own_wider_window_with_three_candidates(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.item_candidates = tuple(
            BattleItemCandidate(items[key])
            for key in ("POTION", "REMEDY", "MANA DROP", "PANACEA")
        )
        mock.selected_item_index = 0
        mock.item_scroll_offset = 0
        from systems import InventorySystem

        mock.inventory_system = InventorySystem.with_one_each(items)
        mock.localizer = Localizer(Language.JAPANESE)
        mock.item_window = Mock()
        mock.item_window.set_cursor.return_value = Mock()
        mock._refresh_item_guide = Mock()

        mock._refresh_item_options()

        self.assertEqual(ITEM_WINDOW_GRID, (32, 0, 32, 13))
        self.assertEqual(mock.item_window.add_text.call_count, 6)
        self.assertTrue(mock.item_window.vertical_navigation)
        targets = mock.item_window.set_cursor.call_args.args[0]
        self.assertEqual(len(targets), 3)
        self.assertEqual(tuple(target.key for target in targets), (0, 1, 2))
        mock._refresh_item_guide.assert_called_once_with()

    def test_item_guide_stays_open_while_item_selection_is_active(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ITEM
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState()
        mock.item_guide_window = Mock()
        mock._update_item_selection = Mock()

        mock.update()

        mock.item_guide_window.close_immediately.assert_not_called()
        mock._update_item_selection.assert_called_once_with(
            mock.input_reader.poll.return_value
        )

    def test_item_guide_opens_immediately_in_its_own_window(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.item_candidates = (BattleItemCandidate(items["POTION"]),)
        mock.selected_item_index = 0
        mock.spells = load_mock_spells()
        mock.localizer = Localizer(Language.JAPANESE)
        mock.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        mock.item_guide_window = Mock()
        mock.command_guide_window = Mock()

        mock._refresh_item_guide()

        self.assertEqual(ITEM_GUIDE_WINDOW_GRID, (0, 0, 32, 13))
        mock.item_guide_window.open_immediately.assert_called_once_with()
        self.assertGreater(mock.item_guide_window.add_text.call_count, 0)
        mock.command_guide_window.open_immediately.assert_not_called()

    def test_spell_candidates_are_learned_battle_spells_only(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.spells = load_mock_spells()

        candidates = mock._active_member_spell_candidates()

        self.assertTrue(candidates)
        self.assertTrue(all(spell.on_battle for spell in candidates))
        self.assertTrue(
            all(spell.is_learned_by(mock.party[0]) for spell in candidates)
        )
        self.assertTrue(all(spell.type != "item" for spell in candidates))

    def test_spell_list_uses_the_item_window_width_for_one_school(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.spell_candidates = tuple(
            load_mock_spells()[key] for key in ("FIRE1", "HEALING1", "POISON1")
        )
        mock.localizer = Localizer(Language.JAPANESE)
        mock.spell_window = Mock()
        mock.spell_window.set_cursor.return_value = Mock()
        mock.spell_cursor = None
        mock.spell_scroll_offset = 0
        mock.spell_type = mock.spell_candidates[0].type
        mock._refresh_spell_guide = Mock()

        mock._refresh_spell_options(preferred_key="FIRE1")

        self.assertEqual(SPELL_WINDOW_GRID, (36, 0, 28, 16))
        self.assertEqual(mock.spell_window.add_text.call_count, 1)
        targets = mock.spell_window.set_cursor.call_args.args[0]
        self.assertEqual(
            [(target.x, target.y, target.key) for target in targets],
            [(2, 2, "FIRE1")],
        )
        mock.spell_window.set_cursor.return_value.select_key.assert_called_once_with(
            "FIRE1"
        )

    def test_left_and_right_switch_the_displayed_spell_school(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        spells = load_mock_spells()
        mock.spell_candidates = tuple(
            spells[key]
            for key in (
                "FIRE1",
                "SLOW",
                "SPARK",
                "FREEZE1",
                "HEALING1",
                "PROTECTION",
                "CURE",
                "SILENCE",
                "POISON1",
                "SLEEP",
                "ARMOR BREAK",
                "FADE",
            )
        )
        mock.spell_scroll_offset = 0
        mock.spell_cursor = None
        mock.spell_type = spells["FIRE1"].type
        mock.localizer = Localizer(Language.JAPANESE)
        mock.spell_window = Window(*SPELL_WINDOW_GRID)
        mock._refresh_spell_guide = Mock()

        mock._refresh_spell_options()
        self.assertTrue(mock._move_spell(Direction.RIGHT))

        self.assertIs(mock.spell_type, spells["HEALING1"].type)
        self.assertEqual(
            [target.key for target in mock.spell_cursor.targets],
            ["HEALING1", "PROTECTION", "CURE", "SILENCE"],
        )

    def test_spell_mp_window_overlays_the_guide_bottom_right(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.spell_candidates = (load_mock_spells()["FIRE1"],)
        mock.spell_cursor = Mock(selected_key="FIRE1")
        mock.localizer = Localizer(Language.JAPANESE)
        mock.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        mock.spell_guide_window = Mock()
        mock.spell_mp_window = Mock()

        mock._refresh_spell_guide()

        self.assertEqual(SPELL_GUIDE_WINDOW_GRID, (0, 0, 36, 16))
        self.assertEqual(SPELL_MP_WINDOW_GRID, (20, 9, 16, 7))
        mock.spell_guide_window.open_immediately.assert_called_once_with()
        mock.spell_mp_window.open_immediately.assert_called_once_with()
        self.assertEqual(mock.spell_guide_window.add_text.call_count, 3)
        self.assertEqual(mock.spell_guide_window.add_text.call_args_list[2].args[2], 11)
        self.assertEqual(
            mock.spell_mp_window.add_text.call_args.args[0],
            ascii_to_fullwidth(f"ＭＰ {mock.party[0].mp:3d}"),
        )

    def test_spell_mp_window_uses_spaces_instead_of_leading_zeroes(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.party[0].mp = 12
        mock.active_party_index = 0
        mock.spell_candidates = (load_mock_spells()["FIRE1"],)
        mock.spell_cursor = Mock(selected_key="FIRE1")
        mock.localizer = Localizer(Language.JAPANESE)
        mock.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        mock.spell_guide_window = Mock()
        mock.spell_mp_window = Mock()

        mock._refresh_spell_guide()

        self.assertEqual(
            mock.spell_mp_window.add_text.call_args.args[0],
            "ＭＰ　　１２",
        )

    def test_using_a_spell_starts_target_selection_without_spending_mp(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        spell = load_mock_spells()["FIRE1"]
        mock.spell_candidates = (spell,)
        mock.spell_cursor = Mock(selected_key=spell.key)
        mock.last_spell_key_by_party_index = {}
        mock._begin_action_target_selection = Mock(return_value=True)
        before_mp = mock.party[0].mp

        self.assertTrue(mock._use_selected_spell())
        self.assertEqual(mock.party[0].mp, before_mp)
        self.assertEqual(mock.last_spell_key_by_party_index, {0: spell.key})
        mock._begin_action_target_selection.assert_called_once_with(spell)

    def test_using_a_breaking_consumable_starts_target_selection_before_removal(self) -> None:
        items = load_mock_items()
        potion = items["POTION"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.item_candidates = (BattleItemCandidate(potion),)
        mock.selected_item_index = 0
        mock.active_party_index = 0
        mock.spells = load_mock_spells()
        from systems import InventorySystem

        mock.inventory_system = InventorySystem.with_one_each(items)
        mock.last_item_selection_by_party_index = {}
        mock._begin_action_target_selection = Mock(return_value=True)

        self.assertTrue(mock._use_selected_item())
        self.assertEqual(mock.inventory_system.quantity(potion), 1)
        self.assertEqual(
            mock.last_item_selection_by_party_index,
            {0: (potion.key, None)},
        )
        mock._begin_action_target_selection.assert_called_once_with(
            mock.spells[potion.use_spell_key],
            item_candidate=mock.item_candidates[0],
        )

    def test_spell_mp_is_spent_only_after_target_confirmation(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.pending_item_candidate = None
        mock.pending_spell = load_mock_spells()["FIRE1"]
        mock._begin_action_presentation = Mock(return_value=True)
        mock._complete_current_turn = Mock()
        before_mp = mock.party[0].mp

        self.assertTrue(mock._confirm_action_target_selection())
        self.assertEqual(mock.party[0].mp, before_mp - mock.pending_spell.mp)
        mock._begin_action_presentation.assert_called_once_with(
            mock.pending_spell,
        )
        mock._complete_current_turn.assert_not_called()

    def test_registered_spell_effect_plays_before_the_turn_completes(self) -> None:
        items = load_mock_items()
        spell = load_mock_spells()["FIRE1"]
        definition = SpellEffectDefinition.from_record(
            spell.key,
            {
                "kind": "target_sprite",
                "image_id": "effects/spells32",
                "row": 0,
                "frame_count": 2,
                "frames_per_pattern": 2,
                "offset": {"ally": [-5, -6], "enemy": [3, 4]},
                "flash_color": 10,
                "se_id": "spell_fire1",
            },
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.pending_item_candidate = None
        mock.pending_spell = spell
        mock.spell_effects = {spell.key: definition}
        mock.spell_effect_renderer = Mock()
        mock.palette_shifter = Mock()
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.action_targets_enemy = True
        mock.action_targets_all = False
        mock.selectable_target_indexes = (0,)
        mock.selected_target_index = 0
        mock.selectable_party_target_indexes = ()
        mock.selected_party_target_index = None
        mock.monsters = (_damage_test_monster(),)
        mock.target_cursor = SimpleNamespace(active=True)
        mock.party_target_cursor = None
        mock.all_target_cursors = ()
        mock._refresh_monster_name_colors = Mock()
        mock._complete_current_turn = Mock()
        mock.spell_damage_popups = []
        mock.affinity_popups = []
        before_mp = mock.party[0].mp

        with patch("scenes.battle.play_se") as play_se:
            self.assertTrue(mock._confirm_action_target_selection())

        self.assertEqual(mock.party[0].mp, before_mp - spell.mp)
        self.assertIs(mock.phase, BattleMockPhase.ACTION_PRESENTATION)
        mock._complete_current_turn.assert_not_called()
        assert mock.action_presentation is not None
        target_effect = mock.action_presentation.spell_effects[0]
        self.assertEqual((target_effect.target_side, target_effect.target_index), ("enemy", 0))
        self.assertEqual(
            target_effect.player.center,
            (
                39,
                MONSTER_POSITIONS[0][1] + mock.monsters[0].height // 2 + 4,
            ),
        )
        play_se.assert_called_once_with("spell_fire1")

        for _frame in range(definition.total_frames - 1):
            mock._update_action_presentation()
        mock._complete_current_turn.assert_not_called()
        mock._update_action_presentation()
        mock._complete_current_turn.assert_not_called()
        for _frame in range(SPELL_POST_EFFECT_WAIT_FRAME_COUNT - 1):
            mock._update_action_presentation()
            mock._complete_current_turn.assert_not_called()
        mock._update_action_presentation()
        mock._complete_current_turn.assert_called_once_with()
        self.assertEqual(
            mock.palette_shifter.remove_variant.call_args_list[0],
            call(UNSELECTABLE_TARGET_PALETTE),
        )
        self.assertEqual(
            mock.palette_shifter.remove_variant.call_args_list[-1],
            call(SPELL_EFFECT_FLASH_PALETTE),
        )

    def test_heal_applies_at_da2_overlap_and_popup_does_not_delay_return(self) -> None:
        items = load_mock_items()
        spell = load_mock_spells()["HEALING1"]
        definition = SpellEffectDefinition.from_record(
            spell.key,
            {
                "kind": "target_sprite",
                "image_id": "effects/spells32",
                "row": 0,
                "frame_count": 5,
                "frames_per_pattern": 4,
                "offset": {"ally": [0, -4], "enemy": [0, -4]},
                "flash_color": 5,
                "se_id": "spell_healing1",
            },
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.party_visuals = tuple(
            SimpleNamespace(member=member) for member in mock.party
        )
        mock.party[0].hp = 1
        mock.active_party_index = 1
        mock.action_party_index = 1
        mock.action_offset_x = ACTION_MOVE_DISTANCE
        mock.action_returning = False
        mock.action_return_jump = False
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.action_targets_enemy = False
        mock.action_targets_all = False
        mock.selectable_party_target_indexes = (0, 1)
        mock.selected_party_target_index = 0
        mock.spell_effects = {spell.key: definition}
        mock.spell_effect_renderer = Mock()
        mock.palette_shifter = Mock()
        mock.target_cursor = SimpleNamespace(active=False)
        mock.party_target_cursor = SimpleNamespace(active=True)
        mock.all_target_cursors = ()
        mock.healing_popups = []
        mock._refresh_monster_name_colors = Mock()
        mock._refresh_party_hp_text = Mock()
        mock._begin_action_return = Mock()

        with (
            patch("scenes.battle.random.random", return_value=0.5),
            patch("scenes.battle.play_se"),
        ):
            self.assertTrue(mock._begin_action_presentation(spell))

        expected_ability = member_spell_ability(
            magic=mock.party[1].adjusted_abilities.magic,
            internal_level=mock.party[1].internal_level,
        )
        expected_amount = int(spell.intensity * expected_ability / 10 + 1)
        result_frame = definition.total_frames - SPELL_RESULT_OVERLAP_FRAME_COUNT
        for _frame in range(result_frame - 1):
            mock._update_action_presentation()
        self.assertEqual(mock.party[0].hp, 1)

        mock._update_action_presentation()

        self.assertEqual(
            mock.party[0].hp,
            min(mock.party[0].max_hp, 1 + expected_amount),
        )
        self.assertEqual(mock.healing_popups[0].amount, expected_amount)
        mock._refresh_party_hp_text.assert_called_once_with(0)

        for _frame in range(SPELL_RESULT_OVERLAP_FRAME_COUNT):
            mock._update_action_presentation()

        mock._begin_action_return.assert_not_called()
        for _frame in range(SPELL_POST_EFFECT_WAIT_FRAME_COUNT):
            mock._update_action_presentation()

        mock._begin_action_return.assert_called_once_with(complete_turn=True)
        self.assertEqual(len(mock.healing_popups), 1)

    def test_item_heal_uses_da2_fixed_ability_of_twenty(self) -> None:
        items = load_mock_items()
        spell = load_mock_spells()["POTION"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        mock.party_visuals = tuple(
            SimpleNamespace(member=member) for member in mock.party
        )
        mock.party[0].hp = 1
        mock.active_party_index = 1
        mock.action_party_index = 1
        mock.action_offset_x = ACTION_MOVE_DISTANCE
        mock.action_returning = False
        mock.action_return_jump = False
        mock.phase = BattleMockPhase.ACTION_TARGET

        with patch("scenes.battle.random.random", return_value=0.5):
            result = mock._resolve_healing_results(spell, (0,))[0]

        self.assertEqual(result.amount, 61)

    def test_unregistered_heal_effect_still_recovers_then_returns(self) -> None:
        items = load_mock_items()
        spell = load_mock_spells()["HEALING2"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        mock.party_visuals = tuple(
            SimpleNamespace(member=member) for member in mock.party
        )
        target = mock.party[0]
        target.hp = 1
        mock.active_party_index = 1
        mock.action_party_index = 1
        mock.action_offset_x = ACTION_MOVE_DISTANCE
        mock.action_returning = False
        mock.action_return_jump = False
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.action_targets_enemy = False
        mock.action_targets_all = False
        mock.selectable_party_target_indexes = (0, 1)
        mock.selected_party_target_index = 0
        mock.spell_effects = {}
        mock.target_cursor = SimpleNamespace(active=False)
        mock.party_target_cursor = SimpleNamespace(active=True)
        mock.all_target_cursors = ()
        mock.healing_popups = []
        mock._refresh_monster_name_colors = Mock()
        mock._refresh_party_hp_text = Mock()
        mock._begin_action_return = Mock()

        with patch("scenes.battle.random.random", return_value=0.5):
            self.assertTrue(mock._begin_action_presentation(spell))
        mock._update_action_presentation()

        self.assertGreater(target.hp, 1)
        mock._begin_action_return.assert_not_called()
        for _frame in range(SPELL_POST_EFFECT_WAIT_FRAME_COUNT - 1):
            mock._update_action_presentation()
        mock._begin_action_return.assert_called_once_with(complete_turn=True)
        self.assertEqual(len(mock.healing_popups), 1)

    def test_zero_intensity_heal_restores_hp_and_cures_all_ailments(self) -> None:
        items = load_mock_items()
        spell = load_mock_spells()["PANACEA"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        target = mock.party[0]
        target.hp = 1
        target.poisoned = True
        target.paralyzed = True
        target.sleeping = 2
        target.confused = 2
        mock.party_visuals = tuple(
            SimpleNamespace(member=member) for member in mock.party
        )
        mock.active_party_index = 1
        mock.action_party_index = 1
        mock.action_offset_x = ACTION_MOVE_DISTANCE
        mock.action_returning = False
        mock.action_return_jump = False
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.healing_popups = []
        mock._refresh_party_hp_text = Mock()

        result = mock._resolve_healing_results(spell, (0,))
        presentation = BattleActionPresentation((), healing_results=result)
        mock._apply_action_results(presentation)

        self.assertEqual(target.hp, target.max_hp)
        self.assertFalse(target.poisoned)
        self.assertFalse(target.paralyzed)
        self.assertEqual(target.sleeping, 0)
        self.assertEqual(target.confused, 0)

    def test_heal_popup_uses_sprite_row_eight_pixels_below_damage(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.healing_popups = [BattleHealingPopup(100, 80, 12)]

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_healing_popups()

        self.assertEqual(HEALING_NUMBER_SPRITE_Y, DAMAGE_NUMBER_SPRITE_Y + 8)
        self.assertEqual(
            blt.call_args_list,
            [
                call(92, 78, 0, DAMAGE_NUMBER_SPRITE_X + 8, 8, 8, 8, 1),
                call(100, 78, 0, DAMAGE_NUMBER_SPRITE_X + 16, 8, 8, 8, 1),
            ],
        )

    def test_fire_damage_uses_member_modifier_and_da2_weakness(self) -> None:
        spell = load_mock_spells()["FIRE1"]
        definition = SpellEffectDefinition.from_record(
            spell.key,
            {
                "kind": "target_sprite",
                "image_id": "effects/spells32",
                "row": 0,
                "frame_count": 2,
                "frames_per_pattern": 2,
                "offset": {"ally": [0, 0], "enemy": [0, 0]},
                "flash_color": None,
                "se_id": None,
            },
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.action_party_index = 0
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.action_targets_enemy = True
        mock.action_targets_all = False
        mock.selectable_target_indexes = (0,)
        mock.selected_target_index = 0
        mock.monsters = (
            _damage_test_monster(
                weaknesses=frozenset((ResistanceType.FIRE,)),
            ),
        )
        mock.spell_effects = {spell.key: definition}
        mock.spell_effect_renderer = Mock()
        mock.palette_shifter = Mock()
        mock.target_cursor = SimpleNamespace(active=True)
        mock.party_target_cursor = None
        mock.all_target_cursors = ()
        mock.spell_damage_popups = []
        mock.affinity_popups = []
        mock._refresh_monster_name_colors = Mock()
        mock._begin_action_return = Mock()

        with patch("scenes.battle.random.random", return_value=0.0):
            self.assertTrue(mock._begin_action_presentation(spell))

        actor = mock.party[0]
        modifier = member_spell_modifier(
            magic=actor.adjusted_abilities.magic,
            spell_level=actor.proficiency(ProficiencyKind.MYSTIC).level,
            internal_level=actor.internal_level,
        )
        expected_damage = int(spell.intensity * modifier * 0.20 * 4)
        result_frame = definition.total_frames - SPELL_RESULT_OVERLAP_FRAME_COUNT
        updates_until_result = max(1, result_frame)
        for _frame in range(updates_until_result):
            mock._update_action_presentation()

        self.assertEqual(mock.monsters[0].state.hp, 10_000 - expected_damage)
        self.assertEqual(mock.spell_damage_popups[0].damage, expected_damage)
        self.assertEqual(
            (mock.spell_damage_popups[0].x, mock.spell_damage_popups[0].y),
            (36, MONSTER_POSITIONS[0][1] + mock.monsters[0].height - 8),
        )
        self.assertEqual(
            (
                mock.affinity_popups[0].affinity,
                mock.affinity_popups[0].x,
                mock.affinity_popups[0].y,
            ),
            (SpellAffinity.WEAK, 24, MONSTER_POSITIONS[0][1] + 20),
        )

        for _frame in range(definition.total_frames - updates_until_result):
            mock._update_action_presentation()

        mock._begin_action_return.assert_not_called()
        for _frame in range(SPELL_POST_EFFECT_WAIT_FRAME_COUNT):
            mock._update_action_presentation()

        mock._begin_action_return.assert_called_once_with(complete_turn=True)
        self.assertEqual(len(mock.spell_damage_popups), 1)
        self.assertEqual(len(mock.affinity_popups), 1)

    def test_sleep_uses_authored_rate_and_applies_da2_duration(self) -> None:
        spell = load_mock_spells()["SLEEP"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.action_targets_enemy = True
        mock.action_targets_all = False
        mock.selectable_target_indexes = (0,)
        mock.selected_target_index = 0
        mock.monsters = (_damage_test_monster(),)
        mock.spell_effects = {}
        mock.target_cursor = SimpleNamespace(active=True)
        mock.party_target_cursor = None
        mock.all_target_cursors = ()
        mock.spell_damage_popups = []
        mock.affinity_popups = []
        mock._refresh_monster_name_colors = Mock()

        with patch(
            "scenes.battle.random.randint",
            side_effect=(0, SLEEP_MAX_TURNS),
        ) as randint:
            self.assertTrue(mock._begin_action_presentation(spell))

        assert mock.action_presentation is not None
        result = mock.action_presentation.sleep_results[0]
        self.assertTrue(result.success)
        self.assertEqual(result.turns, SLEEP_MAX_TURNS)
        self.assertEqual(spell.rate, 6)
        self.assertEqual(
            randint.call_args_list,
            [call(0, 19), call(SLEEP_MIN_TURNS, SLEEP_MAX_TURNS)],
        )

        mock._apply_action_results(mock.action_presentation)

        self.assertEqual(mock.monsters[0].state.sleeping, SLEEP_MAX_TURNS)
        self.assertEqual(mock.spell_damage_popups, [])

    def test_slow_uses_authored_rate_and_applies_zero_speed_formula(self) -> None:
        spell = load_mock_spells()["SLOW"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.action_targets_enemy = True
        mock.action_targets_all = False
        mock.selectable_target_indexes = (0,)
        mock.selected_target_index = 0
        mock.monsters = (_damage_test_monster(),)
        mock.monsters[0].agility = 20
        mock.spell_effects = {}
        mock.target_cursor = SimpleNamespace(active=True)
        mock.party_target_cursor = None
        mock.all_target_cursors = ()
        mock.spell_damage_popups = []
        mock.affinity_popups = []
        mock._refresh_monster_name_colors = Mock()

        with patch("scenes.battle.random.randint", return_value=0) as randint:
            self.assertTrue(mock._begin_action_presentation(spell))

        assert mock.action_presentation is not None
        result = mock.action_presentation.slow_results[0]
        self.assertTrue(result.success)
        self.assertEqual(spell.rate, 16)
        mock._apply_action_results(mock.action_presentation)

        self.assertEqual(mock.monsters[0].state.speed_modifier, -1)
        self.assertEqual(mock.monsters[0].effective_agility, 15)
        self.assertEqual(mock.spell_damage_popups, [])
        randint.assert_called_once_with(0, 19)

    def test_poison_attribute_uses_status_roll_after_dealing_spell_damage(self) -> None:
        spell = load_mock_spells()["POISON1"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        mock.active_party_index = 0
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.action_targets_enemy = True
        mock.action_targets_all = False
        mock.selectable_target_indexes = (0,)
        mock.selected_target_index = 0
        mock.monsters = (_damage_test_monster(hp=100),)
        mock.spell_effects = {}
        mock.target_cursor = SimpleNamespace(active=True)
        mock.party_target_cursor = None
        mock.all_target_cursors = ()
        mock.spell_damage_popups = []
        mock.affinity_popups = []
        mock._refresh_monster_name_colors = Mock()

        with (
            patch("scenes.battle.random.random", return_value=0.5),
            patch("scenes.battle.random.randint", return_value=0) as randint,
        ):
            self.assertTrue(mock._begin_action_presentation(spell))

        assert mock.action_presentation is not None
        presentation = mock.action_presentation
        self.assertGreater(presentation.damage_results[0].damage, 0)
        self.assertTrue(presentation.poison_results[0].success)
        mock._apply_action_results(presentation)

        self.assertLess(mock.monsters[0].state.hp, 100)
        self.assertTrue(mock.monsters[0].state.poisoned)
        randint.assert_called_once_with(0, 19)

    def test_poison_resistance_blocks_poison_but_not_spell_damage(self) -> None:
        spell = load_mock_spells()["POISON1"]
        monster = _damage_test_monster(
            hp=100,
            resistances=frozenset((ResistanceType.POISON,)),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        mock.active_party_index = 0
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.monsters = (monster,)
        mock._monster_draw_x = Mock(return_value=4)

        with patch("scenes.battle.random.randint") as randint:
            poison_results = mock._resolve_poison_results(spell, (0,))
        presentation = BattleActionPresentation(
            (),
            damage_results=mock._resolve_spell_damage_results(spell, (0,)),
            poison_results=poison_results,
        )
        mock.spell_damage_popups = []

        mock._apply_action_results(presentation)

        self.assertLess(monster.state.hp, 100)
        self.assertFalse(monster.state.poisoned)
        randint.assert_not_called()

    def test_failed_slow_shows_miss_without_applying_the_modifier(self) -> None:
        spell = load_mock_spells()["SLOW"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        mock.active_party_index = 0
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.monsters = (_damage_test_monster(spell_resistance=100),)
        mock.spell_damage_popups = []
        results = ()
        with patch("scenes.battle.random.randint", return_value=19):
            results = mock._resolve_slow_results(spell, (0,))
        presentation = BattleActionPresentation((), slow_results=results)
        mock.healing_popups = []

        mock._apply_action_results(presentation)

        self.assertEqual(mock.monsters[0].state.speed_modifier, 0)
        self.assertEqual(
            [popup.is_miss for popup in mock.spell_damage_popups],
            [True],
        )

    def test_slow_targeting_excludes_already_slowed_monsters(self) -> None:
        spell = load_mock_spells()["SLOW"]
        slowed = _damage_test_monster(0)
        slowed.state.speed_modifier = -1
        normal = _damage_test_monster(1)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (slowed, normal)

        self.assertEqual(
            mock._selectable_enemy_indexes_for_spell(spell),
            (1,),
        )

    def test_sleep_resistance_fails_and_shows_miss_with_resist_marker(self) -> None:
        spell = load_mock_spells()["SLEEP"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.action_targets_enemy = True
        mock.action_targets_all = False
        mock.selectable_target_indexes = (0,)
        mock.selected_target_index = 0
        mock.monsters = (
            _damage_test_monster(
                resistances=frozenset((ResistanceType.SLEEP,)),
            ),
        )
        mock.spell_effects = {}
        mock.target_cursor = SimpleNamespace(active=True)
        mock.party_target_cursor = None
        mock.all_target_cursors = ()
        mock.spell_damage_popups = []
        mock.affinity_popups = []
        mock._refresh_monster_name_colors = Mock()

        with patch("scenes.battle.random.randint", return_value=0) as randint:
            self.assertTrue(mock._begin_action_presentation(spell))

        assert mock.action_presentation is not None
        mock._apply_action_results(mock.action_presentation)

        self.assertEqual(mock.monsters[0].state.sleeping, 0)
        self.assertEqual(
            [popup.is_miss for popup in mock.spell_damage_popups],
            [True],
        )
        self.assertEqual(
            [popup.affinity for popup in mock.affinity_popups],
            [SpellAffinity.RESIST],
        )
        randint.assert_not_called()

    def test_protection_applies_one_guaranteed_stage(self) -> None:
        spell = load_mock_spells()["PROTECTION"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        target = mock.party[1]
        results = mock._resolve_protection_results(spell, (1,))
        presentation = BattleActionPresentation((), protection_results=results)
        mock.healing_popups = []
        mock.spell_damage_popups = []

        mock._apply_action_results(presentation)

        self.assertEqual(target.protection_level, 1)
        self.assertTrue(presentation.results_applied)

    def test_protection_targeting_excludes_members_at_second_stage(self) -> None:
        spell = load_mock_spells()["PROTECTION"]
        party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        party[0].protection_level = 2
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = party
        mock.party_visuals = tuple(
            SimpleNamespace(member=member) for member in party
        )
        mock.escaped_party_indexes = set()

        self.assertEqual(
            mock._selectable_party_indexes_for_spell(spell),
            (1,),
        )

    def test_failed_sleep_popup_uses_da2_miss_sprite_and_timing(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        popup = BattleSpellDamagePopup(100, 80, 0, is_miss=True)
        mock.spell_damage_popups = [popup]

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_spell_damage_popups()
        blt.assert_not_called()

        popup.elapsed_frame = 2
        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_spell_damage_popups()

        blt.assert_called_once_with(
            100 - MISS_SPRITE_WIDTH // 2,
            80,
            0,
            MISS_SPRITE_SOURCE_X,
            DAMAGE_NUMBER_SPRITE_Y,
            MISS_SPRITE_WIDTH,
            DAMAGE_NUMBER_SPRITE_SIZE,
            1,
        )
        popup.elapsed_frame = MONSTER_MISS_FRAME_COUNT - 1
        self.assertFalse(popup.completed)
        popup.update()
        self.assertTrue(popup.completed)

    def test_spell_damage_popup_uses_standard_damage_sprite_row(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.spell_damage_popups = [BattleSpellDamagePopup(100, 80, 12)]

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_spell_damage_popups()

        self.assertEqual(
            blt.call_args_list,
            [
                call(92, 78, 0, DAMAGE_NUMBER_SPRITE_X + 8, 0, 8, 8, 1),
                call(100, 78, 0, DAMAGE_NUMBER_SPRITE_X + 16, 0, 8, 8, 1),
            ],
        )

    def test_weak_and_resist_popups_use_the_registered_bank_zero_sprites(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.affinity_popups = [
            BattleAffinityPopup(10, 20, SpellAffinity.WEAK),
            BattleAffinityPopup(30, 40, SpellAffinity.RESIST),
        ]

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_affinity_popups()

        self.assertEqual(
            blt.call_args_list,
            [
                call(10, 20, 0, AFFINITY_ICON_SOURCE_X, WEAK_ICON_SOURCE_Y, 24, 8, 1),
                call(30, 40, 0, AFFINITY_ICON_SOURCE_X, RESIST_ICON_SOURCE_Y, 24, 8, 1),
            ],
        )

    def test_sleep_icons_use_da2_four_pattern_layout_from_bank_zero(self) -> None:
        monster = _damage_test_monster()
        monster.state.apply_sleep(2)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = (
            SimpleNamespace(member=SimpleNamespace(sleeping=2)),
        )
        mock.monsters = (monster,)
        mock._party_draw_position = Mock(return_value=(156, 64))
        mock._monster_draw_x = Mock(return_value=4)

        with (
            patch(
                "tools.screen_mocks.battle.pyxel.frame_count",
                SLEEP_ICON_PATTERN_FRAME_COUNT,
            ),
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
        ):
            mock._draw_sleeping_icons()

        self.assertEqual(
            blt.call_args_list,
            [
                call(
                    168,
                    64,
                    0,
                    SLEEP_ICON_SOURCE_X + SLEEP_ICON_SIZE,
                    SLEEP_ICON_SOURCE_Y,
                    SLEEP_ICON_SIZE,
                    SLEEP_ICON_SIZE,
                    1,
                ),
                call(
                    52,
                    MONSTER_POSITIONS[0][1],
                    0,
                    SLEEP_ICON_SOURCE_X + SLEEP_ICON_SIZE,
                    SLEEP_ICON_SOURCE_Y,
                    SLEEP_ICON_SIZE,
                    SLEEP_ICON_SIZE,
                    1,
                ),
            ],
        )

    def test_protection_icon_animates_left_of_name_at_stage_speed(self) -> None:
        member = SimpleNamespace(protection_level=2)
        window = Window(52, 16, 7, 5, transparent=True)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.party = (member,)
        mock.party_status_windows = (window,)
        mock.escaped_party_indexes = set()

        with (
            patch(
                "tools.screen_mocks.battle.pyxel.frame_count",
                PROTECTION_ICON_PATTERN_FRAME_COUNTS[1],
            ),
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
        ):
            mock._draw_protection_icons()

        blt.assert_called_once_with(
            window.pixel_x + PROTECTION_ICON_NAME_OFFSET_X,
            window.pixel_y,
            0,
            PROTECTION_ICON_SOURCE_X + PROTECTION_ICON_SIZE,
            PROTECTION_ICON_SOURCE_Y,
            PROTECTION_ICON_SIZE,
            PROTECTION_ICON_SIZE,
            1,
        )

    def test_slow_icon_uses_da2_bank_zero_animation_below_monster(self) -> None:
        self.assertEqual((SPEED_ICON_SOURCE_X, SPEED_ICON_NEGATIVE_SOURCE_Y), (96, 136))
        self.assertEqual(SPEED_ICON_TRANSPARENT_INDEX, 1)

        monster = _damage_test_monster()
        monster.state.speed_modifier = -1
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (monster,)
        mock._monster_draw_x = Mock(return_value=4)

        with (
            patch(
                "tools.screen_mocks.battle.pyxel.frame_count",
                SLOW_ICON_PATTERN_FRAME_COUNT,
            ),
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
        ):
            mock._draw_speed_modifier_icons()

        blt.assert_called_once_with(
            4 + monster.width - 24,
            MONSTER_POSITIONS[0][1] + monster.height,
            0,
            SPEED_ICON_SOURCE_X + SPEED_ICON_SIZE,
            SPEED_ICON_NEGATIVE_SOURCE_Y,
            SPEED_ICON_SIZE,
            SPEED_ICON_SIZE,
            SPEED_ICON_TRANSPARENT_INDEX,
        )

    def test_poison_icon_uses_bank_zero_32_16_beside_monster(self) -> None:
        monster = _damage_test_monster()
        monster.state.poisoned = True
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (monster,)
        mock._monster_draw_x = Mock(return_value=4)

        with (
            patch(
                "tools.screen_mocks.battle.pyxel.frame_count",
                POISON_ICON_PATTERN_FRAME_COUNT,
            ),
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.dither") as dither,
        ):
            mock._draw_poison_icons()

        blt.assert_called_once_with(
            4 + POISON_MONSTER_OFFSET_X,
            MONSTER_POSITIONS[0][1],
            0,
            POISON_ICON_SOURCE_X,
            POISON_ICON_SOURCE_Y,
            POISON_ICON_SIZE,
            POISON_ICON_SIZE,
            1,
        )
        self.assertEqual(dither.call_args_list, [call(0.5), call(1.0)])

    def test_party_condition_icons_line_up_from_the_character_upper_right(
        self,
    ) -> None:
        member = SimpleNamespace(
            is_alive=True,
            poisoned=True,
            sleeping=2,
            paralyzed=True,
            stunned=True,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = (SimpleNamespace(member=member),)
        mock.monsters = ()
        mock._party_draw_position = Mock(return_value=(156, 64))

        with (
            patch(
                "tools.screen_mocks.battle.pyxel.frame_count",
                POISON_ICON_PATTERN_FRAME_COUNT,
            ),
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.dither"),
        ):
            mock._draw_sleeping_icons()
            mock._draw_poison_icons()
            mock._draw_paralyze_icons()
            mock._draw_stun_icons()

        first_x = 156 + PARTY_CONDITION_ICON_OFFSET_X
        self.assertEqual(
            blt.call_args_list,
            [
                call(
                    first_x + SLEEP_ICON_SIZE,
                    64,
                    0,
                    SLEEP_ICON_SOURCE_X + SLEEP_ICON_SIZE,
                    SLEEP_ICON_SOURCE_Y,
                    SLEEP_ICON_SIZE,
                    SLEEP_ICON_SIZE,
                    1,
                ),
                call(
                    first_x,
                    64,
                    0,
                    POISON_ICON_SOURCE_X,
                    POISON_ICON_SOURCE_Y,
                    POISON_ICON_SIZE,
                    POISON_ICON_SIZE,
                    1,
                ),
                call(
                    first_x + PARALYZE_ICON_SIZE * 2,
                    64,
                    0,
                    PARALYZE_ICON_SOURCE_X,
                    PARALYZE_ICON_SOURCE_Y,
                    PARALYZE_ICON_SIZE,
                    PARALYZE_ICON_SIZE,
                    1,
                ),
                call(
                    first_x + STUN_ICON_SIZE * 3,
                    64,
                    0,
                    STUN_ICON_SOURCE_X,
                    STUN_ICON_SOURCE_Y,
                    STUN_ICON_SIZE,
                    STUN_ICON_SIZE,
                    1,
                ),
            ],
        )
        self.assertEqual(
            (PARALYZE_ICON_SOURCE_X, PARALYZE_ICON_SOURCE_Y),
            (40, 16),
        )

    def test_stun_icon_uses_authored_bank_zero_sprite_beside_monster(self) -> None:
        monster = _damage_test_monster()
        monster.state.stunned = True
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (monster,)
        mock._monster_draw_x = Mock(return_value=4)

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_stun_icons()

        blt.assert_called_once_with(
            4 + STUN_MONSTER_OFFSET_X,
            MONSTER_POSITIONS[0][1],
            0,
            STUN_ICON_SOURCE_X,
            STUN_ICON_SOURCE_Y,
            STUN_ICON_SIZE,
            STUN_ICON_SIZE,
            1,
        )
        self.assertEqual((STUN_ICON_SOURCE_X, STUN_ICON_SOURCE_Y), (224, 16))

    def test_spell_cast_popup_shows_icon_and_name_at_minimum_top_right_width(self) -> None:
        spell = load_mock_spells()["FIRE1"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.localizer = Localizer(Language.JAPANESE)
        font = Mock()
        font.text_width.side_effect = lambda text: len(text) * 8
        mock.action_popup_window = Window(60, 0, 4, 7, font=font)
        mock.battle_popup = BattleTimedPopup()

        mock._show_spell_cast_message(spell)

        self.assertEqual(
            mock.action_popup_window.texts,
            (WindowText("%MYSTIC%ファイア１", 2, 2),),
        )
        self.assertEqual(mock.action_popup_window.width, 16)
        self.assertEqual(mock.action_popup_window.x, 48)
        self.assertEqual(
            mock.battle_popup.frames_remaining,
            BATTLE_POPUP_FRAME_COUNT,
        )

    def test_item_use_popup_shows_only_name_at_minimum_top_right_width(self) -> None:
        item = load_mock_items()["POTION"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.localizer = Localizer(Language.JAPANESE)
        font = Mock()
        font.text_width.side_effect = lambda text: len(text) * 8
        mock.action_popup_window = Window(60, 0, 4, 7, font=font)
        mock.battle_popup = BattleTimedPopup()

        mock._show_item_use_message(item)

        self.assertEqual(
            mock.action_popup_window.texts,
            (WindowText("きずぐすり", 2, 2),),
        )
        self.assertEqual(mock.action_popup_window.width, 14)
        self.assertEqual(mock.action_popup_window.x, 50)
        self.assertEqual(
            mock.battle_popup.frames_remaining,
            BATTLE_POPUP_FRAME_COUNT,
        )

    def test_spell_cast_message_disappears_after_da2_popup_duration(self) -> None:
        popup = BattleTimedPopup()
        popup.show(BATTLE_POPUP_FRAME_COUNT)

        for _frame in range(BATTLE_POPUP_FRAME_COUNT - 1):
            popup.update()
            self.assertTrue(popup.visible)
        popup.update()

        self.assertEqual(popup.frames_remaining, 0)
        self.assertFalse(popup.visible)

    def test_spell_turn_waits_for_caster_to_return_after_presentation(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ACTION_PRESENTATION
        mock.action_presentation = BattleActionPresentation(())
        mock.battle_popup = BattleTimedPopup(frames_remaining=30)
        mock.action_party_index = 0
        mock.action_offset_x = ACTION_MOVE_DISTANCE
        mock.action_motion_frame = 0
        mock.action_returning = False
        mock.action_uses_cast_pose = True
        mock.palette_shifter = Mock()
        mock._complete_current_turn = Mock()

        for _frame in range(SPELL_POST_EFFECT_WAIT_FRAME_COUNT - 1):
            mock._update_action_presentation()
            self.assertIs(mock.phase, BattleMockPhase.ACTION_PRESENTATION)
            mock._complete_current_turn.assert_not_called()
        mock._update_action_presentation()

        self.assertIs(mock.phase, BattleMockPhase.ACTION_RETURN)
        self.assertTrue(mock.action_returning)
        self.assertEqual(mock.battle_popup.frames_remaining, 30)
        mock._complete_current_turn.assert_not_called()

        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState()
        mock._refresh_input_guide = Mock()
        for _frame in range(ACTION_MOVE_DISTANCE // ACTION_MOVE_SPEED):
            mock.update()

        self.assertIsNone(mock.action_party_index)
        self.assertEqual(mock.battle_popup.frames_remaining, 22)
        self.assertTrue(mock.battle_popup.visible)
        mock._complete_current_turn.assert_called_once_with()

    def test_all_target_spell_creates_one_effect_per_target_and_one_sound(self) -> None:
        spell = load_mock_spells()["FIRE1"]
        definition = SpellEffectDefinition.from_record(
            spell.key,
            {
                "kind": "target_sprite",
                "image_id": "effects/spells32",
                "row": 0,
                "frame_count": 1,
                "frames_per_pattern": 4,
                "offset": {"ally": [0, 0], "enemy": [0, 0]},
                "flash_color": None,
                "se_id": "spell_fire1",
            },
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        mock.spell_effects = {spell.key: definition}
        mock.spell_effect_renderer = Mock()
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.action_targets_enemy = True
        mock.action_targets_all = True
        mock.selectable_target_indexes = (0, 1)
        mock.selected_target_index = None
        mock.monsters = (_damage_test_monster(0), _damage_test_monster(1))
        mock.target_cursor = SimpleNamespace(active=False)
        mock.party_target_cursor = None
        mock.all_target_cursors = (Mock(), Mock())
        mock.spell_damage_popups = []
        mock.affinity_popups = []
        mock._refresh_monster_name_colors = Mock()

        with patch("scenes.battle.play_se") as play_se:
            self.assertTrue(mock._begin_action_presentation(spell))

        assert mock.action_presentation is not None
        self.assertEqual(
            [effect.target_index for effect in mock.action_presentation.spell_effects],
            [0, 1],
        )
        play_se.assert_called_once_with("spell_fire1")

    def test_action_presentation_composes_target_flash_and_effect_sprite(self) -> None:
        definition = SpellEffectDefinition.from_record(
            "FIRE1",
            {
                "kind": "target_sprite",
                "image_id": "effects/spells32",
                "row": 0,
                "frame_count": 1,
                "frames_per_pattern": 4,
                "offset": {"ally": [0, 0], "enemy": [0, 0]},
                "flash_color": 10,
                "se_id": None,
            },
        )
        player = SpellEffectPlayer(
            definition,
            anchor_x=40,
            anchor_y=50,
            target_side="enemy",
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.action_presentation = BattleActionPresentation(
            (BattleTargetSpellEffect("enemy", 1, player),)
        )
        mock.spell_effect_renderer = Mock()
        draw_target = Mock()

        mock._draw_spell_effect_target("enemy", 1, draw_target)
        mock._draw_spell_effects()

        mock.spell_effect_renderer.draw_target.assert_called_once_with(
            player, draw_target
        )
        mock.spell_effect_renderer.draw_effect.assert_called_once_with(player)

    def test_breaking_item_is_removed_only_after_target_confirmation(self) -> None:
        items = load_mock_items()
        potion = items["POTION"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        from systems import InventorySystem

        mock.inventory_system = InventorySystem.with_one_each(items)
        mock.active_party_index = 0
        mock.pending_item_candidate = BattleItemCandidate(potion)
        mock.pending_spell = None
        mock._complete_current_turn = Mock()

        self.assertTrue(mock._confirm_action_target_selection())
        self.assertEqual(mock.inventory_system.quantity(potion), 0)
        mock._complete_current_turn.assert_called_once_with()

    def test_item_confirmation_starts_effect_and_non_blocking_popup(self) -> None:
        items = load_mock_items()
        potion = items["POTION"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        from systems import InventorySystem

        mock.inventory_system = InventorySystem.with_one_each(items)
        mock.active_party_index = 0
        mock.localizer = Localizer(Language.JAPANESE)
        font = Mock()
        font.text_width.side_effect = lambda text: len(text) * 8
        mock.action_popup_window = Window(60, 0, 4, 7, font=font)
        mock.battle_popup = BattleTimedPopup()
        mock.pending_item_candidate = BattleItemCandidate(potion)
        mock.pending_spell = None
        mock.spells = load_mock_spells()
        mock._begin_action_presentation = Mock(return_value=True)
        mock._complete_current_turn = Mock()

        self.assertTrue(mock._confirm_action_target_selection())

        mock._begin_action_presentation.assert_called_once_with(
            mock.spells[potion.use_spell_key]
        )
        self.assertEqual(
            mock.action_popup_window.texts,
            (WindowText("きずぐすり", 2, 2),),
        )
        self.assertEqual(
            mock.battle_popup.frames_remaining,
            BATTLE_POPUP_FRAME_COUNT,
        )
        mock._complete_current_turn.assert_not_called()

    def test_magnifier_is_consumed_and_starts_the_shared_identify_effect(self) -> None:
        items = load_mock_items()
        magnifier = items["MAGNIFIER"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        from systems import InventorySystem

        mock.inventory_system = InventorySystem.with_one_each(items)
        mock.active_party_index = 0
        mock.pending_item_candidate = BattleItemCandidate(magnifier)
        mock.pending_spell = None
        mock.spells = load_mock_spells()
        mock.hidden_party_indexes = set()
        mock._show_item_use_message = Mock()
        mock._begin_identify_presentation = Mock(return_value=True)
        mock._record_action_target_information = Mock()
        mock._begin_action_presentation = Mock()

        self.assertTrue(mock._confirm_action_target_selection())

        self.assertEqual(mock.inventory_system.quantity(magnifier), 0)
        mock._show_item_use_message.assert_called_once_with(magnifier)
        mock._begin_identify_presentation.assert_called_once_with()
        mock._record_action_target_information.assert_not_called()
        mock._begin_action_presentation.assert_not_called()

    def test_target_cancel_returns_to_the_item_list_without_consuming_it(self) -> None:
        items = load_mock_items()
        potion = items["POTION"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.pending_item_candidate = BattleItemCandidate(potion)
        mock.pending_spell = None
        mock.selectable_target_indexes = (0,)
        mock.selected_target_index = 0
        mock.selectable_party_target_indexes = ()
        mock.selected_party_target_index = None
        mock.action_targets_enemy = False
        mock.action_targets_all = False
        mock.target_cursor = Mock()
        mock.party_target_cursor = None
        mock.all_target_cursors = ()
        mock._refresh_monster_name_colors = Mock()
        mock.item_window = Mock()
        mock._refresh_item_options = Mock()

        mock._cancel_action_target_selection()

        self.assertIs(mock.phase, BattleMockPhase.ITEM)
        self.assertIs(mock.selected_command, BattleCommand.ITEM)
        mock.item_window.open_immediately.assert_called_once_with()
        mock._refresh_item_options.assert_called_once_with()

    def test_item_effect_targeting_uses_its_resolved_spell_target_flags(self) -> None:
        spell = load_mock_spells()["FIRE1"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (SimpleNamespace(is_alive=True), SimpleNamespace(is_alive=True))
        mock.target_window = Window(0, 0, 64, 60, transparent=True)
        mock.target_cursor = WindowCursor(
            mock.target_window,
            tuple(
                CursorTarget((x + 8) // 4, (y + 16) // 4, key=index)
                for index, (x, y) in enumerate(MONSTER_POSITIONS[:2])
            ),
            active=False,
        )
        mock.party_target_window = Window(0, 0, 64, 60, transparent=True)
        mock.item_window = Mock()
        mock.item_guide_window = Mock()
        mock._close_spell_windows = Mock()
        mock._refresh_monster_name_colors = Mock()

        self.assertTrue(mock._begin_action_target_selection(spell))

        self.assertIs(mock.phase, BattleMockPhase.ACTION_TARGET)
        self.assertTrue(mock.action_targets_enemy)
        self.assertFalse(mock.action_targets_all)
        self.assertEqual(mock.selected_target_index, 1)
        self.assertTrue(mock.target_cursor.active)

    def test_magnifier_selects_an_enemy_without_requiring_identify_skill(self) -> None:
        spell = load_mock_spells()["IDENTIFY"]
        magnifier = load_mock_items()["MAGNIFIER"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (
            SimpleNamespace(is_alive=True),
            SimpleNamespace(is_alive=True),
        )
        mock.target_window = Window(0, 0, 64, 60, transparent=True)
        mock.target_cursor = WindowCursor(
            mock.target_window,
            tuple(
                CursorTarget((x + 8) // 4, (y + 16) // 4, key=index)
                for index, (x, y) in enumerate(MONSTER_POSITIONS[:2])
            ),
            active=False,
        )
        mock.party_target_window = Window(0, 0, 64, 60, transparent=True)
        mock.item_window = Mock()
        mock.item_guide_window = Mock()
        mock._close_spell_windows = Mock()
        mock._refresh_monster_name_colors = Mock()

        self.assertTrue(
            mock._begin_action_target_selection(
                spell,
                item_candidate=BattleItemCandidate(magnifier),
            )
        )

        self.assertIs(mock.phase, BattleMockPhase.ACTION_TARGET)
        self.assertIs(mock.selected_command, BattleCommand.ITEM)
        self.assertTrue(mock.action_targets_enemy)
        self.assertFalse(mock.action_targets_all)
        self.assertEqual(mock.selected_target_index, 1)
        self.assertTrue(mock.target_cursor.active)

    def test_allied_all_target_creates_one_cursor_for_each_living_member(self) -> None:
        spell = load_mock_spells()["TELEPORT"]
        items = load_mock_items()
        party_keys = ("Fiora", "Cerion", "Alvan")
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=party_keys,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.target_cursor = Mock(active=False)
        mock.party_target_window = Window(0, 0, 64, 60, transparent=True)
        mock._party_sprite_x = Mock(side_effect=(156, 160, 164))
        mock.item_window = Mock()
        mock.item_guide_window = Mock()
        mock._close_spell_windows = Mock()
        mock._refresh_monster_name_colors = Mock()

        self.assertTrue(mock._begin_action_target_selection(spell))

        self.assertFalse(mock.action_targets_enemy)
        self.assertTrue(mock.action_targets_all)
        self.assertEqual(mock.selectable_party_target_indexes, (0, 1, 2))
        self.assertEqual(len(mock.all_target_cursors), 3)
        self.assertFalse(mock.party_target_cursor.active)

    def test_allied_target_cursor_follows_the_advanced_actor(self) -> None:
        spell = load_mock_spells()["POTION"]
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=("Fiora", "Cerion"),
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.action_party_index = 0
        mock.target_cursor = Mock(active=False)
        mock.party_target_window = Window(0, 0, 64, 60, transparent=True)
        mock.item_window = Mock()
        mock.item_guide_window = Mock()
        mock._close_spell_windows = Mock()
        mock._refresh_monster_name_colors = Mock()

        self.assertTrue(mock._begin_action_target_selection(spell))

        targets = {target.key: target for target in mock.party_target_cursor.targets}
        self.assertEqual(
            targets[0].x * 4,
            mock._party_sprite_x(0) - ACTION_MOVE_DISTANCE - 8,
        )
        self.assertEqual(targets[1].x * 4, mock._party_sprite_x(1) - 8)

    def test_all_target_cursors_blink_on_alternating_frames(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ACTION_TARGET
        mock.action_targets_all = True
        mock.all_target_cursors = (Mock(), Mock())

        with patch("tools.screen_mocks.battle.pyxel.frame_count", 20):
            mock._draw_target_cursor()
        self.assertEqual([cursor.draw.call_count for cursor in mock.all_target_cursors], [1, 1])

        with patch("tools.screen_mocks.battle.pyxel.frame_count", 21):
            mock._draw_target_cursor()
        self.assertEqual([cursor.draw.call_count for cursor in mock.all_target_cursors], [1, 1])

    def test_cover_target_cursor_is_drawn(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COVER_TARGET
        mock.party_target_cursor = Mock()

        mock._draw_target_cursor()

        mock.party_target_cursor.draw.assert_called_once_with()

    def test_equipment_without_a_use_effect_stays_selectable_but_is_not_used(self) -> None:
        items = load_mock_items()
        dagger = items["DAGGER"]
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.item_candidates = (
            BattleItemCandidate(dagger, EquipmentSlot.RIGHT),
        )
        mock.selected_item_index = 0
        mock.active_party_index = 0
        mock.spells = load_mock_spells()
        mock._complete_current_turn = Mock()

        self.assertFalse(mock._use_selected_item())
        mock._complete_current_turn.assert_not_called()

    def test_defense_persists_until_the_member_next_becomes_active(self) -> None:
        visual = BattleMockCharacter(
            SimpleNamespace(definition=SimpleNamespace(key="Fiora")),
            0,
            0,
            0,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 0
        mock.defending_party_indexes = set()
        mock.selected_command = None
        mock._complete_current_turn = Mock()

        self.assertTrue(mock._begin_defense())
        self.assertEqual(mock.defending_party_indexes, {0})
        self.assertIs(mock.selected_command, BattleCommand.DEFEND)
        mock._complete_current_turn.assert_called_once_with()

        mock.timeline = (visual,)
        mock.party_visuals = (visual,)
        mock.cover_target_by_party_index = {0: 1}
        mock.phase = BattleMockPhase.TIMELINE
        mock.command_cursor = Mock()
        mock.command_window = Mock()
        mock._refresh_command_options = Mock()
        mock._refresh_party_text_colors = Mock()

        mock._activate_timeline_head()

        self.assertEqual(mock.defending_party_indexes, set())
        self.assertEqual(mock.cover_target_by_party_index, {})
        self.assertIs(mock.phase, BattleMockPhase.COMMAND)

    def test_cover_command_selects_an_ally_and_starts_guarding_them(self) -> None:
        members = (
            SimpleNamespace(hp=30, has_skill=lambda key: key == "Cover"),
            SimpleNamespace(hp=30),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = members
        mock.active_party_index = 0
        mock.escaped_party_indexes = set()
        mock.hidden_party_indexes = set()
        mock.party_target_window = Window(0, 0, 64, 60, transparent=True)
        mock.command_cursor = Mock(active=True)
        mock._party_target_cursor_x = Mock(side_effect=(148, 152))
        mock.last_cover_target_by_party_index = {0: 1}
        mock.cover_target_by_party_index = {}
        mock.defending_party_indexes = set()
        mock._complete_current_turn = Mock()

        self.assertTrue(mock._begin_cover_target_selection())
        self.assertIs(mock.phase, BattleMockPhase.COVER_TARGET)
        self.assertEqual(mock.selectable_party_target_indexes, (0, 1))
        self.assertEqual(mock.selected_party_target_index, 1)
        self.assertFalse(mock.command_cursor.active)

        self.assertTrue(mock._confirm_cover_target_selection())
        self.assertEqual(mock.cover_target_by_party_index, {0: 1})
        self.assertEqual(mock.defending_party_indexes, {0})
        self.assertIs(mock.selected_command, BattleCommand.COVER)
        mock._complete_current_turn.assert_called_once_with()

    def test_covering_self_uses_defend_instead(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 0
        mock.selected_party_target_index = 0
        mock.selectable_party_target_indexes = (0, 1)
        mock.last_cover_target_by_party_index = {}
        mock._begin_defense = Mock(return_value=True)

        self.assertTrue(mock._confirm_cover_target_selection())

        self.assertEqual(mock.last_cover_target_by_party_index, {0: 0})
        mock._begin_defense.assert_called_once_with()

    def test_spell_command_opens_spell_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock(selected_key="spell")
        mock.command_window = Mock(is_closed=False, is_open=True)
        mock.selected_command = None
        mock._begin_spell_selection = Mock(return_value=True)
        mock._complete_current_turn = Mock()

        mock.update()

        mock._begin_spell_selection.assert_called_once_with()
        mock._complete_current_turn.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)

    def test_menu_input_restarts_the_mock_from_any_phase(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.SPELL
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            menu=InputButton(triggered=True, held=True)
        )
        mock._restart_battle_mock = Mock()

        mock.update()

        mock._restart_battle_mock.assert_called_once_with()

    def test_battle_bgm_restarts_from_the_beginning_for_each_mock_reset(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.bgm = Mock()

        mock._restart_battle_bgm()

        mock.bgm.stop.assert_called_once_with()
        mock.bgm.play.assert_called_once_with(BATTLE_BGM_ID)

    def test_timeline_animation_finishes_interrupt_then_readies_new_head(
        self,
    ) -> None:
        actors = tuple(SimpleNamespace(agility=50) for _ in range(7))
        order = TimelineOrder(
            tuple(
                TimelineEntry(actor, 50, gauge)
                for actor, gauge in zip(actors, (64, 58, 52, 44, 38, 32, 26))
            )
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock._timeline_order = order
        mock.timeline = order.actors
        mock.timeline_advance = complete_timeline_action(
            order,
            current_agility=50,
            visible_count=TIMELINE_VISIBLE_ENTRY_COUNT,
        )
        mock.timeline_animation_phase = TimelineAnimationPhase.DROP
        mock.timeline_animation_frame = 0
        mock.command_window = Mock()
        mock._activate_timeline_head = Mock()

        for _frame in range(TIMELINE_ANIMATION_FRAME_COUNT + 1):
            mock._update_timeline_animation()
        self.assertIs(mock.timeline_animation_phase, TimelineAnimationPhase.SLIDE)

        for _frame in range(TIMELINE_ANIMATION_FRAME_COUNT + 1):
            mock._update_timeline_animation()
        self.assertIs(
            mock.timeline_animation_phase,
            TimelineAnimationPhase.INTERRUPT,
        )

        interrupt_frames = mock._timeline_interrupt_frame_count()
        for _frame in range(interrupt_frames + 1):
            mock._update_timeline_animation()

        self.assertIsNone(mock.timeline_animation_phase)
        self.assertEqual(mock.timeline, (actors[1], actors[2], actors[0], *actors[3:]))
        self.assertEqual(mock._timeline_order.entries[0].gauge, 64.0)
        mock._activate_timeline_head.assert_called_once_with()

    def test_active_member_draws_with_the_whiteward_pulse_palette(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 1
        mock.party_visuals = (
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT),
                battle_sprite=0,
            ),
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT),
                battle_sprite=1,
            ),
        )
        mock.character_sprites = object()
        mock.phase = BattleMockPhase.COMMAND
        mock.palette_shifter = Mock()
        mock.palette_shifter.shifted.return_value = nullcontext()

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party()

        mock.palette_shifter.shifted.assert_called_once_with(ACTIVE_PARTY_PULSE_PALETTE)
        self.assertEqual(blt.call_count, 2)

    def test_active_party_pulse_reaches_its_whiteward_peak_mid_cycle(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_pulse_frame = ACTIVE_PARTY_PULSE_CYCLE_FRAME_COUNT // 2
        mock.palette_shifter = Mock()

        mock._sync_active_party_pulse_palette()

        mock.palette_shifter.define_mix.assert_called_once_with(
            ACTIVE_PARTY_PULSE_PALETTE,
            base_rate=ACTIVE_PARTY_PULSE_MIN_BASE_RATE,
            target_color=ACTIVE_PARTY_PULSE_TARGET_COLOR,
        )

    def test_active_party_pulse_ends_when_command_input_is_complete(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 0

        for phase in (
            BattleMockPhase.COMMAND,
            BattleMockPhase.ITEM,
            BattleMockPhase.SPELL,
            BattleMockPhase.TARGET,
            BattleMockPhase.ESCAPE_CONFIRMATION,
        ):
            mock.phase = phase
            self.assertTrue(mock._active_party_pulse_is_visible())

        for phase in (
            BattleMockPhase.INITIAL,
            BattleMockPhase.ENTRANCE,
            BattleMockPhase.FORMATION,
            BattleMockPhase.MONSTER_DEATH,
            BattleMockPhase.DEFEAT_MESSAGE,
            BattleMockPhase.TIMELINE,
            BattleMockPhase.MONSTER_ACTION,
            BattleMockPhase.ESCAPE_MEMBER,
            BattleMockPhase.ESCAPE_MESSAGE,
            BattleMockPhase.ESCAPE,
        ):
            mock.phase = phase
            self.assertFalse(mock._active_party_pulse_is_visible())

    def test_timeline_displays_six_entries_and_brings_seventh_into_view(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.timeline = tuple(
            SimpleNamespace(icon_x=index * 16, icon_y=0)
            for index in range(8)
        )
        order = TimelineOrder(
            tuple(
                TimelineEntry(entry, 10, 64.0 - index * 4)
                for index, entry in enumerate(mock.timeline)
            )
        )
        mock.timeline_advance = complete_timeline_action(
            order,
            current_agility=10,
            visible_count=TIMELINE_VISIBLE_ENTRY_COUNT,
        )
        mock.timeline_animation_phase = TimelineAnimationPhase.DROP
        mock.timeline_animation_frame = TIMELINE_ANIMATION_FRAME_COUNT // 2

        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()

        icon_calls = blt.call_args_list
        self.assertEqual(len(icon_calls), TIMELINE_VISIBLE_ENTRY_COUNT)
        self.assertEqual(icon_calls[0].args[:2], (70, 225))
        self.assertEqual(icon_calls[1].args[:2], (90, 220))

        mock.timeline_animation_phase = TimelineAnimationPhase.SLIDE
        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()

        self.assertEqual(
            [draw_call.args[:2] for draw_call in blt.call_args_list],
            [
                (80, 220),
                (100, 220),
                (120, 220),
                (140, 220),
                (160, 220),
                (213, 220),
            ],
        )
        self.assertEqual(blt.call_args_list[-1].args[3], 96)

        mock.timeline_animation_phase = None
        mock.timeline = mock.timeline_advance.after.actors
        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()

        self.assertEqual(
            [draw_call.args[:2] for draw_call in blt.call_args_list[:-1]],
            [(70 + index * 20, 220) for index in range(6)],
        )
        self.assertEqual(len(blt.call_args_list), TIMELINE_VISIBLE_ENTRY_COUNT + 1)

    def test_timeline_interrupt_cascades_by_collision_and_drops_overflow(self) -> None:
        actors = tuple(
            SimpleNamespace(icon_x=index * 16, icon_y=0)
            for index in range(7)
        )
        order = TimelineOrder(
            tuple(
                TimelineEntry(actor, 50, gauge)
                for actor, gauge in zip(actors, (64, 58, 52, 44, 38, 32, 26))
            )
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.timeline_advance = complete_timeline_action(
            order,
            current_agility=50,
            visible_count=TIMELINE_VISIBLE_ENTRY_COUNT,
        )
        mock.phase = BattleMockPhase.TIMELINE
        mock.timeline_animation_phase = TimelineAnimationPhase.INTERRUPT

        first_collision_frame = mock._timeline_interrupt_collision_frame(2)
        self.assertEqual(first_collision_frame, 1)
        mock.timeline_animation_frame = first_collision_frame + 1
        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()

        # The first displaced icon has moved far enough for its 16x16 rectangle
        # to overlap the next icon; that neighbor begins moving on the next frame.
        self.assertEqual(blt.call_args_list[2].args[:2], (115, 220))
        self.assertEqual(blt.call_args_list[3].args[:2], (130, 220))

        mock.timeline_animation_frame = mock._timeline_interrupt_frame_count()
        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()

        self.assertEqual(
            [draw_call.args[:2] for draw_call in blt.call_args_list],
            [
                (70, 220),
                (90, 220),
                (130, 220),
                (150, 220),
                (170, 220),
                (SCREEN_WIDTH + 16, SCREEN_HEIGHT + 16),
                (110, 220),
            ],
        )
        self.assertEqual(
            mock._timeline_interrupt_frame_count(),
            first_collision_frame
            + 3
            + TIMELINE_INTERRUPT_OVERFLOW_FRAME_COUNT,
        )
        self.assertEqual(TIMELINE_INTERRUPT_ENTRY_FRAME_COUNT, 4)
        self.assertEqual(TIMELINE_INTERRUPT_SLIDE_FRAME_COUNT, 4)

    def test_timeline_collision_uses_overlapping_sixteen_pixel_rectangles(
        self,
    ) -> None:
        collision = BattleScreenMock._timeline_icons_collide

        self.assertFalse(collision(70, 220, 86, 220))
        self.assertTrue(collision(70, 220, 85, 220))
        self.assertFalse(collision(70, 220, 70, 236))
        self.assertTrue(collision(70, 220, 70, 235))

    def test_timeline_enters_from_right_with_two_frame_stagger(self) -> None:
        self.assertEqual(TIMELINE_ENTRANCE_FRAME_COUNT, 10)
        self.assertEqual(TIMELINE_ENTRANCE_STAGGER_FRAME_COUNT, 2)
        self.assertEqual(TIMELINE_ENTRANCE_COMPLETE_FRAME, 20)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ENTRANCE
        mock.timeline = tuple(
            SimpleNamespace(icon_x=index * 16, icon_y=0)
            for index in range(8)
        )
        mock.timeline_animation_phase = None

        mock.entrance_animation_frame = 0
        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()
        self.assertEqual(
            [entry.args[:2] for entry in blt.call_args_list],
            [(256, 220)],
        )

        mock.entrance_animation_frame = 2
        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()
        self.assertEqual(len(blt.call_args_list), 2)
        self.assertEqual(blt.call_args_list[-1].args[:2], (256, 220))

        mock.entrance_animation_frame = TIMELINE_ENTRANCE_COMPLETE_FRAME
        with (
            patch("tools.screen_mocks.battle.pyxel.blt") as blt,
            patch("tools.screen_mocks.battle.pyxel.rect"),
        ):
            mock._draw_timeline()
        self.assertEqual(
            [entry.args[:2] for entry in blt.call_args_list],
            [(70 + index * 20, 220) for index in range(6)],
        )

    def test_monster_blink_uses_da2_six_frame_visibility_cycle(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        image = object()
        mock.monsters = (
            SimpleNamespace(
                key="Giant Spider",
                width=64,
                height=64,
                is_alive=True,
            ),
        )
        mock.monster_images = {"Giant Spider": image}
        mock.blinking_monster_index = 0
        mock.phase = BattleMockPhase.MONSTER_ACTION

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock.monster_blink_frames_remaining = MONSTER_BLINK_FRAME_COUNT
            mock._draw_monsters()
            blt.assert_not_called()

            mock.monster_blink_frames_remaining = 5
            mock._draw_monsters()
            blt.assert_called_once_with(
                *MONSTER_POSITIONS[0],
                image,
                0,
                0,
                64,
                64,
                1,
            )

    def test_front_monster_attacks_only_a_living_front_party_member(self) -> None:
        actor = BattleMockMonster(
            key="Giant Spider",
            names={"name_en": "Giant Spider"},
            image_id="1",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=2),
            agility=12,
            combat_stats=MonsterCombatStats(
                attack=20,
                hit=100,
                defense=0,
                evasion=0,
            ),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_window = Mock()
        mock.timeline = (actor,)
        mock.party = (
            SimpleNamespace(hp=0, formation_row=FormationRow.FRONT),
            SimpleNamespace(hp=30, formation_row=FormationRow.BACK),
            SimpleNamespace(
                hp=30,
                formation_row=FormationRow.FRONT,
                battle_stats=SimpleNamespace(defense=5, evasion=10),
            ),
        )
        mock.monster_blink_frames_remaining = 1
        mock.monster_attack_target_index = None
        mock.monster_attack_damage = None
        mock.monster_attack_animation_frame = 0
        mock.defending_party_indexes = set()
        mock._start_timeline_animation = Mock()

        with (
            patch("tools.screen_mocks.battle.random.choice", return_value=2) as choice,
            patch("tools.screen_mocks.battle.random.randint", return_value=15) as randint,
            patch("scenes.battle.play_se") as play_se,
        ):
            mock._update_monster_action()

        choice.assert_called_once_with((2,))
        randint.assert_called_once_with(0, 99)
        play_se.assert_called_once_with(BATTLE_HIT_SE_ID)
        self.assertEqual(mock.monster_attack_target_index, 2)
        self.assertEqual(mock.monster_attack_damage, 16)
        self.assertEqual(mock.monster_attack_animation_frame, 0)
        mock._start_timeline_animation.assert_not_called()

        mock.monster_attack_target_index = None
        mock.monster_attack_damage = None
        with (
            patch("tools.screen_mocks.battle.random.choice", return_value=2),
            patch("tools.screen_mocks.battle.random.randint", return_value=99),
            patch("scenes.battle.play_se") as play_se,
        ):
            mock._update_monster_action()

        self.assertEqual(mock.monster_attack_damage, 0)
        play_se.assert_not_called()

    def test_defending_member_gets_da2_guard_effect_against_monster_attack(
        self,
    ) -> None:
        actor = BattleMockMonster(
            key="Giant Spider",
            names={"name_en": "Giant Spider"},
            image_id="1",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=2),
            agility=20,
            combat_stats=MonsterCombatStats(
                attack=100,
                hit=100,
                defense=0,
                evasion=0,
            ),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_window = Mock()
        mock.timeline = (actor,)
        mock.party = (
            SimpleNamespace(
                hp=30,
                formation_row=FormationRow.FRONT,
                battle_stats=SimpleNamespace(defense=0, evasion=0),
            ),
        )
        mock.monster_blink_frames_remaining = 1
        mock.monster_attack_target_index = None
        mock.monster_attack_damage = None
        mock.monster_attack_animation_frame = 0
        mock.defending_party_indexes = {0}
        mock._start_timeline_animation = Mock()

        with (
            patch("tools.screen_mocks.battle.random.choice", return_value=0),
            patch("tools.screen_mocks.battle.random.randint", return_value=75),
            patch("scenes.battle.play_se") as play_se,
        ):
            mock._update_monster_action()

        self.assertEqual(mock.monster_attack_damage, 45)
        play_se.assert_called_once_with(BATTLE_HIT_SE_ID)

    def test_manual_cover_redirects_a_physical_attack_with_guard(self) -> None:
        actor = SimpleNamespace(
            combat_stats=SimpleNamespace(hit=90),
            effective_agility=12,
        )
        coverer = SimpleNamespace(
            hp=100,
            max_hp=100,
            paralyzed=False,
            sleeping=0,
            confused=0,
            battle_stats=SimpleNamespace(defense=17, evasion=8),
        )
        protected = SimpleNamespace(
            hp=100,
            max_hp=100,
            battle_stats=SimpleNamespace(defense=3, evasion=2),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (coverer, protected)
        mock.cover_target_by_party_index = {0: 1}
        mock.defending_party_indexes = {0}
        mock.focused_target_by_party_index = {}
        mock.hidden_party_indexes = set()
        mock._active_party_indexes = Mock(return_value=(0, 1))
        result = SimpleNamespace(hit=True, damage=20)

        with (
            patch("tools.screen_mocks.battle.random.choice", return_value=1),
            patch("tools.screen_mocks.battle.random.randint", return_value=5),
            patch(
                "scenes.battle.resolve_physical_attack",
                return_value=result,
            ) as resolve,
        ):
            target_index, resolved = mock._resolve_monster_attack(
                actor,
                (0, 1),
                attack=50,
            )

        self.assertEqual(target_index, 0)
        self.assertIs(resolved, result)
        self.assertEqual(mock.protected_party_index, 1)
        self.assertEqual(mock.covering_party_index, 0)
        self.assertEqual(resolve.call_args.kwargs["target_defense"], 17)
        self.assertTrue(resolve.call_args.kwargs["target_defending"])

    def test_cover_skill_automatically_protects_an_ally_in_crisis(self) -> None:
        actor = SimpleNamespace(
            combat_stats=SimpleNamespace(hit=90),
            effective_agility=12,
        )
        coverer = SimpleNamespace(
            hp=26,
            max_hp=100,
            paralyzed=False,
            sleeping=0,
            confused=0,
            has_skill=lambda key: key == "Cover",
            battle_stats=SimpleNamespace(defense=17, evasion=8),
        )
        protected = SimpleNamespace(
            hp=25,
            max_hp=100,
            sleeping=0,
            paralyzed=False,
            battle_stats=SimpleNamespace(defense=3, evasion=2),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (coverer, protected)
        mock.cover_target_by_party_index = {}
        mock.defending_party_indexes = set()
        mock.focused_target_by_party_index = {}
        mock.hidden_party_indexes = set()
        mock._active_party_indexes = Mock(return_value=(0, 1))
        result = SimpleNamespace(hit=True, damage=20)

        with (
            patch("tools.screen_mocks.battle.random.choice", return_value=1),
            patch("tools.screen_mocks.battle.random.randint", return_value=5),
            patch(
                "scenes.battle.resolve_physical_attack",
                return_value=result,
            ) as resolve,
        ):
            target_index, _resolved = mock._resolve_monster_attack(
                actor,
                (0, 1),
                attack=50,
            )

        self.assertEqual(target_index, 0)
        self.assertFalse(resolve.call_args.kwargs["target_defending"])

    def test_automatic_cover_requires_a_healthy_actionable_coverer(self) -> None:
        protected = SimpleNamespace(
            hp=25,
            max_hp=100,
            sleeping=0,
            paralyzed=False,
        )
        for field, value in (
            ("hp", 25),
            ("sleeping", 1),
            ("paralyzed", True),
            ("confused", 1),
        ):
            with self.subTest(field=field):
                coverer = SimpleNamespace(
                    hp=100,
                    max_hp=100,
                    sleeping=0,
                    paralyzed=False,
                    confused=0,
                    has_skill=lambda key: key == "Cover",
                )
                setattr(coverer, field, value)
                mock = BattleScreenMock.__new__(BattleScreenMock)
                mock.party = (coverer, protected)
                mock.cover_target_by_party_index = {}
                mock._active_party_indexes = Mock(return_value=(0, 1))

                self.assertEqual(mock._covering_member_index(1), 1)

    def test_coverer_moves_beside_the_protected_member_and_uses_guard_on_miss(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (SimpleNamespace(hp=30), SimpleNamespace(hp=30))
        mock.phase = BattleMockPhase.MONSTER_ACTION
        mock.covering_party_index = 0
        mock.protected_party_index = 1
        mock.monster_attack_target_index = 0
        mock.monster_attack_damage = 0
        mock._party_sprite_x = Mock(side_effect=lambda index: 156 + index * 4)

        self.assertEqual(
            mock._party_draw_position(0),
            (160 - 26, PARTY_SPRITE_Y[1]),
        )
        self.assertEqual(mock._party_sprite_source_x(0), DEFEND_SPRITE_SOURCE_X)

        mock.monster_attack_damage = 10
        self.assertEqual(
            mock._party_sprite_source_x(0),
            MONSTER_DAMAGE_SPRITE_SOURCE_X,
        )

    def test_focusing_member_cannot_evade_monster_attack(self) -> None:
        actor = BattleMockMonster(
            key="Giant Spider",
            names={"name_en": "Giant Spider"},
            image_id="1",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=2),
            agility=20,
            combat_stats=MonsterCombatStats(
                attack=20,
                hit=0,
                defense=0,
                evasion=0,
            ),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_window = Mock()
        mock.timeline = (actor,)
        mock.party = (
            SimpleNamespace(
                hp=30,
                formation_row=FormationRow.FRONT,
                battle_stats=SimpleNamespace(defense=0, evasion=100),
            ),
        )
        mock.monster_blink_frames_remaining = 1
        mock.monster_attack_target_index = None
        mock.monster_attack_damage = None
        mock.monster_attack_animation_frame = 0
        mock.defending_party_indexes = set()
        mock.focused_target_by_party_index = {0: 0}
        mock._start_timeline_animation = Mock()
        result = SimpleNamespace(hit=True, damage=10)

        with (
            patch("tools.screen_mocks.battle.random.choice", return_value=0),
            patch("tools.screen_mocks.battle.random.randint", return_value=99),
            patch(
                "scenes.battle.resolve_physical_attack",
                return_value=result,
            ) as resolve,
            patch("scenes.battle.play_se"),
        ):
            mock._update_monster_action()

        self.assertTrue(resolve.call_args.kwargs["target_unable_to_evade"])

    def test_monster_can_critical_a_sleeping_member(self) -> None:
        actor = BattleMockMonster(
            key="Giant Spider",
            names={"name_en": "Giant Spider"},
            image_id="1",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=2),
            agility=20,
            combat_stats=MonsterCombatStats(20, 100, 0, 0),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_window = Mock()
        mock.timeline = (actor,)
        mock.party = (
            SimpleNamespace(
                hp=30,
                sleeping=2,
                formation_row=FormationRow.FRONT,
                battle_stats=SimpleNamespace(defense=0, evasion=100),
            ),
        )
        mock.monster_blink_frames_remaining = 1
        mock.monster_attack_target_index = None
        mock.monster_attack_damage = None
        mock.monster_attack_animation_frame = 0
        mock.defending_party_indexes = set()
        mock.focused_target_by_party_index = {}
        mock._start_timeline_animation = Mock()
        result = SimpleNamespace(hit=True, damage=40, critical=True)

        with (
            patch("tools.screen_mocks.battle.random.choice", return_value=0),
            patch(
                "tools.screen_mocks.battle.random.randint",
                side_effect=(99, 19),
            ) as randint,
            patch(
                "scenes.battle.resolve_physical_attack",
                return_value=result,
            ) as resolve,
            patch("scenes.battle.play_se"),
        ):
            mock._update_monster_action()

        self.assertTrue(resolve.call_args.kwargs["target_incapacitated"])
        self.assertFalse(resolve.call_args.kwargs["target_unable_to_evade"])
        self.assertEqual(resolve.call_args.kwargs["critical_roll"], 19)
        self.assertTrue(mock.monster_attack_critical)
        self.assertEqual(randint.call_args_list, [call(0, 99), call(0, 99)])

    def test_rear_monster_finishes_without_attacking(self) -> None:
        actor = BattleMockMonster(
            key="Giant Spider",
            names={"name_en": "Giant Spider"},
            image_id="1",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=False,
            state=MonsterBattleState(max_hp=2),
            agility=12,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (actor,)
        mock.command_window = Mock()
        mock.timeline = (actor,)
        mock.party = (
            SimpleNamespace(hp=30, formation_row=FormationRow.FRONT),
        )
        mock.command_cursor = Mock()
        mock._remove_defeated_party_from_timeline = Mock()
        mock._party_is_defeated = Mock(return_value=False)
        mock._refresh_party_text_colors = Mock()
        mock._start_timeline_animation = Mock()

        mock._activate_timeline_head()

        self.assertIsNone(mock.blinking_monster_index)
        self.assertEqual(mock.monster_blink_frames_remaining, 0)
        mock._start_timeline_animation.assert_called_once_with()

    def test_sleeping_monster_loses_one_turn_without_attacking(self) -> None:
        actor = _damage_test_monster()
        actor.state.apply_sleep(2)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (actor,)
        mock.timeline = (actor,)
        mock.party = (
            SimpleNamespace(hp=30, formation_row=FormationRow.FRONT),
        )
        mock.party_visuals = (
            SimpleNamespace(member=mock.party[0]),
        )
        mock.escaped_party_indexes = set()
        mock.temporary_front_party_indexes = set()
        mock.command_cursor = Mock()
        mock.command_window = Mock()
        mock._start_timeline_animation = Mock()

        mock._activate_timeline_head()

        self.assertEqual(actor.state.sleeping, 1)
        self.assertIsNone(mock.blinking_monster_index)
        self.assertEqual(mock.monster_blink_frames_remaining, 0)
        mock._start_timeline_animation.assert_called_once_with()

    def test_poison_damage_precedes_a_sleeping_monsters_skipped_turn(self) -> None:
        actor = _damage_test_monster(
            hp=17,
            weaknesses=frozenset((ResistanceType.POISON,)),
        )
        actor.state.poisoned = True
        actor.state.apply_sleep(2)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (actor,)
        mock.timeline = (actor,)
        mock.party = (
            SimpleNamespace(hp=30, formation_row=FormationRow.FRONT),
        )
        mock.party_visuals = (
            SimpleNamespace(member=mock.party[0]),
        )
        mock.escaped_party_indexes = set()
        mock.temporary_front_party_indexes = set()
        mock.command_cursor = Mock()
        mock.command_window = Mock()
        mock.spell_damage_popups = []
        mock._monster_draw_x = Mock(return_value=4)
        mock._start_timeline_animation = Mock()

        mock._activate_timeline_head()

        self.assertEqual(actor.state.hp, 14)
        self.assertEqual(actor.state.sleeping, 1)
        self.assertEqual(mock.spell_damage_popups[0].damage, 3)
        mock._start_timeline_animation.assert_called_once_with()

    def test_lethal_poison_popup_shows_unclamped_calculated_damage(self) -> None:
        actor = _damage_test_monster(
            hp=17,
            weaknesses=frozenset((ResistanceType.POISON,)),
        )
        actor.state.hp = 1
        actor.state.poisoned = True
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (actor,)
        mock.spell_damage_popups = []
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock._monster_draw_x = Mock(return_value=4)
        mock._begin_monster_death = Mock(return_value=True)

        self.assertTrue(mock._apply_turn_start_hp_change(actor))

        self.assertEqual(actor.state.hp, 0)
        self.assertEqual(mock.spell_damage_popups[0].damage, 3)
        mock._begin_monster_death.assert_called_once_with(
            0,
            from_timeline_head=True,
        )

    def test_last_living_rear_member_is_temporarily_promoted_for_enemy_attack(
        self,
    ) -> None:
        actor = BattleMockMonster(
            key="Giant Spider",
            names={"name_en": "Giant Spider"},
            image_id="1",
            width=64,
            height=64,
            icon_x=0,
            icon_y=0,
            is_front_row=True,
            state=MonsterBattleState(max_hp=2),
            agility=12,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (actor,)
        mock.command_window = Mock()
        mock.command_cursor = Mock()
        mock.timeline = (actor,)
        mock.party = (
            SimpleNamespace(hp=30, formation_row=FormationRow.BACK),
            SimpleNamespace(hp=0, formation_row=FormationRow.FRONT),
        )
        mock._remove_defeated_party_from_timeline = Mock()
        mock._party_is_defeated = Mock(return_value=False)
        mock._refresh_party_text_colors = Mock()
        mock._start_timeline_animation = Mock()

        mock._activate_timeline_head()

        self.assertEqual(mock.temporary_front_party_indexes, {0})
        self.assertIs(mock.party[0].formation_row, FormationRow.BACK)
        self.assertIs(mock.phase, BattleMockPhase.FORMATION)
        self.assertEqual(mock._party_draw_position(0), (172, 64))
        for _frame in range(FORMATION_MOVE_FRAME_COUNT):
            mock._update_formation_animation()
        self.assertEqual(mock.blinking_monster_index, 0)
        self.assertEqual(mock.monster_blink_frames_remaining, MONSTER_BLINK_FRAME_COUNT)
        mock._start_timeline_animation.assert_not_called()

    def test_monster_damage_is_applied_after_da2_length_animation(self) -> None:
        member = SimpleNamespace(hp=20, max_hp=30)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_window = Mock()
        mock.party = (member,)
        mock.monster_attack_target_index = 0
        mock.monster_attack_damage = 15
        mock.monster_attack_animation_frame = MONSTER_DAMAGE_FRAME_COUNT - 1
        mock._refresh_party_hp_text = Mock()
        mock._start_timeline_animation = Mock()

        mock._update_monster_action()

        self.assertEqual(member.hp, 5)
        mock._refresh_party_hp_text.assert_called_once_with(0)
        self.assertIsNone(mock.monster_attack_target_index)
        self.assertIsNone(mock.monster_attack_damage)
        mock._start_timeline_animation.assert_called_once_with()

    def test_dead_party_member_is_removed_before_their_timeline_turn(self) -> None:
        party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=("Fiora", "Cerion"),
            internal_level=MAX_INTERNAL_LEVEL,
        )
        party[0].hp = 0
        visuals = tuple(
            BattleMockCharacter(member, index * 16, 0, index)
            for index, member in enumerate(party)
        )
        monster = BattleMockMonster(
            key="monster",
            names={},
            image_id="0",
            width=64,
            height=64,
            icon_x=0,
            icon_y=16,
            is_front_row=True,
            state=MonsterBattleState(max_hp=10),
            agility=12,
        )
        order = TimelineOrder(
            (
                TimelineEntry(visuals[0], visuals[0].agility, 64.0),
                TimelineEntry(visuals[1], visuals[1].agility, 50.0),
                TimelineEntry(monster, monster.agility, 40.0),
            )
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = visuals
        mock._timeline_order = order
        mock.timeline = order.actors
        mock.active_party_index = None
        mock.blinking_monster_index = None
        mock.monster_blink_frames_remaining = 0
        mock.escape_requested = False
        mock.escaped_party_indexes = set()
        mock.defending_party_indexes = set()
        mock.auto_battle_active = False
        mock.command_cursor = Mock()
        mock.command_window = Mock()
        mock._hide_command_guide = Mock()
        mock._refresh_command_options = Mock()
        mock._select_initial_member_command = Mock()
        mock._refresh_input_guide = Mock()
        mock._refresh_party_text_colors = Mock()
        mock._begin_defeat_message = Mock()

        mock._activate_timeline_head()

        self.assertNotIn(visuals[0], mock.timeline)
        self.assertIs(mock.timeline[0], visuals[1])
        self.assertIs(mock.phase, BattleMockPhase.FORMATION)
        for _frame in range(FORMATION_MOVE_FRAME_COUNT):
            mock._update_formation_animation()
        self.assertEqual(mock.active_party_index, 1)
        self.assertIs(mock.phase, BattleMockPhase.COMMAND)
        mock._begin_defeat_message.assert_not_called()

    def test_lethal_monster_attack_removes_last_member_and_begins_defeat(
        self,
    ) -> None:
        member = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=("Fiora",),
            internal_level=MAX_INTERNAL_LEVEL,
        )[0]
        member.hp = 1
        visual = BattleMockCharacter(member, 0, 0, 0)
        monster = BattleMockMonster(
            key="monster",
            names={},
            image_id="0",
            width=64,
            height=64,
            icon_x=0,
            icon_y=16,
            is_front_row=True,
            state=MonsterBattleState(max_hp=10),
            agility=12,
        )
        order = TimelineOrder(
            (
                TimelineEntry(monster, monster.agility, 64.0),
                TimelineEntry(visual, visual.agility, 50.0),
            )
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (member,)
        mock.party_visuals = (visual,)
        mock._timeline_order = order
        mock.timeline = order.actors
        mock.monster_attack_target_index = 0
        mock.monster_attack_damage = 1
        mock.monster_attack_animation_frame = MONSTER_DAMAGE_FRAME_COUNT
        mock.defending_party_indexes = {0}
        mock.focused_target_by_party_index = {0: 0}
        mock._refresh_party_hp_text = Mock()
        mock._begin_defeat_message = Mock()
        mock._start_timeline_animation = Mock()

        mock._finish_monster_attack()

        self.assertTrue(member.is_dead)
        self.assertNotIn(visual, mock.timeline)
        self.assertEqual(mock.defending_party_indexes, set())
        self.assertEqual(mock.focused_target_by_party_index, {})
        mock._begin_defeat_message.assert_called_once_with()
        mock._start_timeline_animation.assert_not_called()

    def test_lethal_attack_on_last_front_promotes_living_rear_members(self) -> None:
        party = list(
            load_mock_party(
                load_mock_items(),
                load_mock_skills(),
                character_keys=("Fiora", "Cerion"),
                internal_level=MAX_INTERNAL_LEVEL,
            )
        )
        party[0].formation_row = FormationRow.FRONT
        party[1].formation_row = FormationRow.BACK
        party[0].hp = 1
        visuals = tuple(
            BattleMockCharacter(member, 0, 0, index)
            for index, member in enumerate(party)
        )
        monster = BattleMockMonster(
            key="monster",
            names={},
            image_id="0",
            width=64,
            height=64,
            icon_x=0,
            icon_y=16,
            is_front_row=True,
            state=MonsterBattleState(max_hp=10),
            agility=12,
        )
        order = TimelineOrder(
            (
                TimelineEntry(monster, monster.agility, 64.0),
                TimelineEntry(visuals[0], visuals[0].agility, 50.0),
                TimelineEntry(visuals[1], visuals[1].agility, 40.0),
            )
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = tuple(party)
        mock.party_visuals = visuals
        mock._timeline_order = order
        mock.timeline = order.actors
        mock.monster_attack_target_index = 0
        mock.monster_attack_damage = 1
        mock.monster_attack_animation_frame = MONSTER_DAMAGE_FRAME_COUNT
        mock.defending_party_indexes = set()
        mock.escaped_party_indexes = set()
        mock.temporary_front_party_indexes = set()
        mock.command_cursor = Mock()
        mock.command_window = Mock()
        mock._refresh_party_text_colors = Mock()
        mock._refresh_party_hp_text = Mock()
        mock._start_timeline_animation = Mock()

        mock._finish_monster_attack()

        self.assertTrue(party[0].is_dead)
        self.assertEqual(mock.temporary_front_party_indexes, {1})
        self.assertTrue(mock._party_member_is_front_row(1))
        self.assertIs(party[1].formation_row, FormationRow.BACK)
        self.assertIs(mock.phase, BattleMockPhase.FORMATION)
        self.assertEqual(mock._party_draw_position(1), (176, 92))
        mock.formation_animation_frame = FORMATION_MOVE_FRAME_COUNT // 2
        self.assertEqual(mock._party_draw_position(1), (168, 92))
        mock.formation_animation_frame = 0
        for _frame in range(FORMATION_MOVE_FRAME_COUNT):
            mock._update_formation_animation()
        mock._start_timeline_animation.assert_called_once_with()

    def test_defeat_message_uses_da2_text_then_reports_production_result(
        self,
    ) -> None:
        mock = BattleScene.__new__(BattleScene)
        mock.phase = BattleMockPhase.MONSTER_ACTION
        mock.result = None
        mock.active_party_index = 0
        mock.blinking_monster_index = 0
        mock.monster_blink_frames_remaining = 1
        mock.timeline_animation_phase = TimelineAnimationPhase.DROP
        mock.timeline_animation_frame = 2
        mock.timeline_advance = object()
        mock.auto_battle_active = True
        mock.command_cursor = Mock(active=True)
        mock.command_window = Mock()
        mock.global_command_window = Mock()
        mock.target_cursor = Mock(active=True)
        mock.escape_cursor = Mock(active=True)
        mock.item_window = Mock()
        mock._close_spell_windows = Mock()
        mock._hide_command_guide = Mock()
        mock.battle_popup = BattleTimedPopup(frames_remaining=20)
        mock.battle_popup_window = Mock()
        mock.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        mock.localizer = Localizer(Language.JAPANESE)
        mock._refresh_party_text_colors = Mock()

        mock._begin_defeat_message()

        self.assertIs(mock.phase, BattleMockPhase.DEFEAT_MESSAGE)
        self.assertFalse(mock.battle_popup.visible)
        mock.battle_popup_window.add_text.assert_called_once_with(
            "ぜんめつした．．．",
            2,
            2,
        )
        mock._update_defeat_message(InputState())
        self.assertIsNone(mock.result)

        mock._update_defeat_message(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertIs(mock.result, BattleResult.DEFEAT)

    def test_standalone_defeat_acknowledgement_restarts_fixture(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock._restart_battle_mock = Mock()

        mock._complete_defeat()

        mock._restart_battle_mock.assert_called_once_with()

    def test_defeat_message_window_stays_visible_while_waiting(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.DEFEAT_MESSAGE
        mock.windows = []
        mock.party_status_windows = []
        mock.monsters = ()
        mock.monster_name_windows = []
        mock.command_window = Mock(is_closed=True)
        mock.global_command_window = Mock(is_open=False, is_closed=True)
        mock.escape_message_window = Mock()
        mock.escape_started_message_window = Mock()
        mock.escape_choice_window = Mock()
        mock.battle_popup = BattleTimedPopup()
        mock.battle_popup_window = Mock()
        mock.action_popup_window = Mock()

        mock._draw_windows()

        mock.battle_popup_window.draw.assert_called_once_with()

    def test_surprise_prevention_window_stays_visible_while_waiting(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.SURPRISE_PREVENTED
        mock.windows = []
        mock.party_status_windows = []
        mock.monsters = ()
        mock.monster_name_windows = []
        mock.command_window = Mock(is_closed=True)
        mock.global_command_window = Mock(is_open=False, is_closed=True)
        mock.escape_message_window = Mock()
        mock.escape_started_message_window = Mock()
        mock.escape_choice_window = Mock()
        mock.battle_popup = BattleTimedPopup()
        mock.battle_popup_window = Mock()
        mock.action_popup_window = Mock()

        mock._draw_windows()

        mock.battle_popup_window.draw.assert_called_once_with()
        mock.action_popup_window.draw.assert_not_called()

    def test_monster_miss_uses_da2_length_without_reducing_hp(self) -> None:
        member = SimpleNamespace(hp=20, max_hp=30)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_window = Mock()
        mock.party = (member,)
        mock.monster_attack_target_index = 0
        mock.monster_attack_damage = 0
        mock.monster_attack_animation_frame = MONSTER_MISS_FRAME_COUNT - 1
        mock._refresh_party_hp_text = Mock()
        mock._start_timeline_animation = Mock()

        with patch("scenes.battle.play_se") as play_se:
            mock._update_monster_action()

        self.assertEqual(member.hp, 20)
        play_se.assert_not_called()
        mock._refresh_party_hp_text.assert_not_called()
        mock._start_timeline_animation.assert_called_once_with()

    def test_monster_damage_uses_sixth_party_pattern_and_da2_shake(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.character_sprites = object()
        mock.party_visuals = (
            SimpleNamespace(
                member=SimpleNamespace(formation_row=FormationRow.FRONT),
                battle_sprite=2,
            ),
        )
        mock.phase = BattleMockPhase.MONSTER_ACTION
        mock.active_party_index = None
        mock.monster_attack_target_index = 0
        mock.monster_attack_damage = 15
        mock.monster_attack_animation_frame = 0
        mock.defending_party_indexes = {0}

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party()

        self.assertEqual(MONSTER_DAMAGE_SPRITE_SOURCE_X, 16 * 5)
        blt.assert_called_once_with(
            164,
            64,
            mock.character_sprites,
            MONSTER_DAMAGE_SPRITE_SOURCE_X,
            64,
            16,
            32,
            1,
        )

    def test_monster_damage_draws_bank_zero_digit_sprites(self) -> None:
        self.assertEqual(
            (DAMAGE_NUMBER_SPRITE_X, DAMAGE_NUMBER_SPRITE_Y),
            (128, 0),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.MONSTER_ACTION
        mock.party_visuals = (
            SimpleNamespace(member=SimpleNamespace(formation_row=FormationRow.FRONT)),
        )
        mock.monster_attack_target_index = 0
        mock.monster_attack_damage = 15
        mock.monster_attack_animation_frame = 0

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_monster_attack_result()

        self.assertEqual(
            blt.call_args_list,
            [
                call(
                    162,
                    78,
                    0,
                    DAMAGE_NUMBER_SPRITE_X + 8,
                    DAMAGE_NUMBER_SPRITE_Y,
                    8,
                    8,
                    1,
                ),
                call(
                    170,
                    78,
                    0,
                    DAMAGE_NUMBER_SPRITE_X + 40,
                    DAMAGE_NUMBER_SPRITE_Y,
                    8,
                    8,
                    1,
                ),
            ],
        )

    def test_covered_damage_popup_uses_the_coverers_moved_position(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.MONSTER_ACTION
        mock.party_visuals = (
            SimpleNamespace(member=SimpleNamespace(formation_row=FormationRow.FRONT)),
            SimpleNamespace(member=SimpleNamespace(formation_row=FormationRow.FRONT)),
        )
        mock.monster_attack_target_index = 0
        mock.monster_attack_damage = 15
        mock.monster_attack_animation_frame = 0
        mock.covering_party_index = 0
        mock.protected_party_index = 1

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_monster_attack_result()

        cover_x = mock._party_sprite_x(1) - 26
        expected_y = PARTY_SPRITE_Y[1] + 14
        self.assertEqual(
            [entry.args[:2] for entry in blt.call_args_list],
            [
                (cover_x + 6, expected_y),
                (cover_x + 14, expected_y),
            ],
        )

    def test_monster_miss_draws_the_supplied_bank_zero_sprite(self) -> None:
        self.assertEqual(MISS_SPRITE_SOURCE_X, 208)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.MONSTER_ACTION
        mock.party_visuals = (
            SimpleNamespace(member=SimpleNamespace(formation_row=FormationRow.FRONT)),
        )
        mock.monster_attack_target_index = 0
        mock.monster_attack_damage = 0

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock.monster_attack_animation_frame = 0
            mock._draw_monster_attack_result()
            blt.assert_not_called()

            mock.monster_attack_animation_frame = 2
            mock._draw_monster_attack_result()

        blt.assert_called_once_with(
            162,
            80,
            0,
            MISS_SPRITE_SOURCE_X,
            DAMAGE_NUMBER_SPRITE_Y,
            MISS_SPRITE_WIDTH,
            8,
            1,
        )

    def test_unable_to_attack_keeps_attack_disabled_and_defend_on_the_right(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_window = Mock()
        self._mock_command_labels(mock)
        new_cursor = Mock()
        mock.command_window.set_cursor.return_value = new_cursor
        mock._active_member_command_options = Mock(
            return_value=(
                BattleCommandOption(BattleCommand.ATTACK, enabled=False),
                BattleCommandOption(BattleCommand.SPELL),
                BattleCommandOption(BattleCommand.AIM),
                BattleCommandOption(BattleCommand.DEFEND),
                BattleCommandOption(BattleCommand.ITEM),
                BattleCommandOption(BattleCommand.FORMATION),
            )
        )

        mock._refresh_command_options()

        self.assertEqual(
            mock.command_window.add_text.call_args_list,
            [
                call("こうげき", 4, 2, color=3),
                call("じゅもん", 4, 5),
                call("ねらう", 4, 8),
                call("ぼうぎょ", 18, 2),
                call("アイテム", 18, 5),
                call("こうたい", 18, 8),
            ],
        )
        targets = mock.command_window.set_cursor.call_args.args[0]
        self.assertEqual(
            [(target.key, target.x, target.y) for target in targets],
            [
                ("attack", 2, 2),
                ("spell", 2, 5),
                ("aim", 2, 8),
                ("defend", 16, 2),
                ("item", 16, 5),
                ("formation", 16, 8),
            ],
        )
        mock.command_window.clear_texts.assert_called_once_with()
        mock.command_window.clear_cursor.assert_called_once_with()
        self.assertIs(mock.command_cursor, new_cursor)

    def test_single_member_defend_uses_the_first_right_column_slot(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_window = Mock()
        self._mock_command_labels(mock)
        mock.command_window.set_cursor.return_value = Mock()
        mock._active_member_command_options = Mock(
            return_value=(
                BattleCommandOption(BattleCommand.ATTACK),
                BattleCommandOption(BattleCommand.SPELL),
                BattleCommandOption(BattleCommand.AIM),
                BattleCommandOption(BattleCommand.DEFEND),
                BattleCommandOption(BattleCommand.ITEM),
            )
        )

        mock._refresh_command_options()

        self.assertIn(
            call("ぼうぎょ", 18, 2),
            mock.command_window.add_text.call_args_list,
        )

    def test_disabled_formation_is_grey_and_not_selectable(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.command_window = Mock()
        self._mock_command_labels(mock)
        mock.command_window.set_cursor.return_value = Mock()
        mock._active_member_command_options = Mock(
            return_value=(
                BattleCommandOption(BattleCommand.ATTACK),
                BattleCommandOption(BattleCommand.SPELL),
                BattleCommandOption(BattleCommand.AIM),
                BattleCommandOption(BattleCommand.DEFEND),
                BattleCommandOption(BattleCommand.ITEM),
                BattleCommandOption(BattleCommand.FORMATION, enabled=False),
            )
        )

        mock._refresh_command_options()

        self.assertIn(
            call("こうたい", 18, 8, color=3),
            mock.command_window.add_text.call_args_list,
        )
        targets = mock.command_window.set_cursor.call_args.args[0]
        formation = next(
            target for target in targets if target.key is BattleCommand.FORMATION
        )
        self.assertFalse(formation.selectable)

    def test_each_command_uses_a_battle_text_key(self) -> None:
        self.assertEqual(
            set(COMMAND_TEXT_KEYS),
            set(BattleCommand),
        )
        self.assertTrue(
            all(
                key.startswith("battle.command.")
                for key in COMMAND_TEXT_KEYS.values()
            )
        )
        texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        localizer = Localizer(Language.JAPANESE)
        self.assertTrue(
            all(
                texts.text(key, localizer)
                for key in COMMAND_TEXT_KEYS.values()
            )
        )

    def test_each_command_guide_uses_a_registered_battle_text_key(self) -> None:
        self.assertEqual(
            set(COMMAND_GUIDE_TEXT_KEYS),
            set(BattleCommand) - {BattleCommand.FORMATION, BattleCommand.ESCAPE},
        )
        guide_keys = {
            *COMMAND_GUIDE_TEXT_KEYS.values(),
            *FORMATION_COMMAND_GUIDE_TEXT_KEYS.values(),
        }
        records = load_record_array("texts.json", APP_ROOT / "data")
        registered_keys = {record["text_key"] for record in records}

        self.assertTrue(all(key.startswith("battle.guide.") for key in guide_keys))
        self.assertLessEqual(guide_keys, registered_keys)

    def test_formation_label_and_guide_reflect_the_active_member_row(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.texts = Mock()
        mock.texts.text.side_effect = lambda key, _localizer: key
        mock.texts.lines.side_effect = lambda key, _localizer: (key,)
        mock.localizer = Localizer(Language.JAPANESE)
        mock.party = (SimpleNamespace(is_front_row=True),)
        mock.active_party_index = 0

        self.assertEqual(
            mock._command_label(BattleCommand.FORMATION),
            "battle.command.retreat",
        )
        self.assertEqual(
            mock._command_guide_lines(BattleCommand.FORMATION),
            ("battle.guide.retreat",),
        )

        mock.party[0].is_front_row = False

        self.assertEqual(
            mock._command_label(BattleCommand.FORMATION),
            "battle.command.advance",
        )
        self.assertEqual(
            mock._command_guide_lines(BattleCommand.FORMATION),
            ("battle.guide.advance",),
        )

    def test_command_guide_waits_at_the_same_command_then_shows_three_lines(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.command_window = Mock(is_open=True)
        mock.command_cursor = Mock(selected_key=BattleCommand.ATTACK)
        mock.command_guide_window = Mock()
        mock.command_guide_command = None
        mock.command_guide_timer = 0
        mock.command_guide_visible = False
        mock._command_guide_lines = Mock(
            return_value=("line one", "line two", "line three", "line four")
        )

        for _frame in range(COMMAND_GUIDE_DELAY_FRAME_COUNT):
            mock._update_command_guide()

        self.assertEqual(COMMAND_GUIDE_DELAY_FRAME_COUNT, 30)
        self.assertIs(mock.command_guide_command, BattleCommand.ATTACK)
        self.assertTrue(mock.command_guide_visible)
        mock.command_guide_window.add_text.assert_has_calls(
            [
                call("line one", COMMAND_GUIDE_TEXT_X, COMMAND_GUIDE_FIRST_Y),
                call(
                    "line two",
                    COMMAND_GUIDE_TEXT_X,
                    COMMAND_GUIDE_FIRST_Y + COMMAND_GUIDE_LINE_SPACING,
                ),
                call(
                    "line three",
                    COMMAND_GUIDE_TEXT_X,
                    COMMAND_GUIDE_FIRST_Y + COMMAND_GUIDE_LINE_SPACING * 2,
                ),
            ]
        )
        self.assertNotIn(
            call(
                "line four",
                COMMAND_GUIDE_TEXT_X,
                COMMAND_GUIDE_FIRST_Y + COMMAND_GUIDE_LINE_SPACING * 3,
            ),
            mock.command_guide_window.add_text.call_args_list,
        )
        mock.command_guide_window.open_immediately.assert_called_once_with()
        mock.command_guide_window.open.assert_not_called()

        mock.command_cursor.selected_key = BattleCommand.FOCUS
        mock._update_command_guide()

        self.assertIs(mock.command_guide_command, BattleCommand.FOCUS)
        self.assertEqual(mock.command_guide_timer, 1)
        self.assertFalse(mock.command_guide_visible)

    def test_command_guide_uses_its_registered_guide_key(self) -> None:
        self.assertEqual(
            COMMAND_GUIDE_TEXT_KEYS[BattleCommand.DEFEND],
            "battle.guide.defend",
        )
        self.assertEqual(
            COMMAND_GUIDE_TEXT_KEYS[BattleCommand.FOCUS],
            "battle.guide.focus",
        )
        texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        localizer = Localizer(Language.JAPANESE)
        self.assertEqual(
            texts.lines(COMMAND_GUIDE_TEXT_KEYS[BattleCommand.ATTACK], localizer),
            (
                ascii_to_fullwidth("もっている ぶきで"),
                ascii_to_fullwidth("てきを こうげきする"),
            ),
        )

    def test_formation_walk_swaps_row_and_uses_alternate_sprite(self) -> None:
        party = list(
            load_mock_party(
                load_mock_items(),
                load_mock_skills(),
                character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
                internal_level=MAX_INTERNAL_LEVEL,
            )
        )
        for member in party:
            member.formation_row = FormationRow.FRONT
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = tuple(party)
        mock.party_visuals = tuple(
            SimpleNamespace(member=member)
            for member in party
        )
        mock.monsters = tuple(
            SimpleNamespace(is_front_row=True)
            for _index in range(2)
        )
        mock.active_party_index = 0
        mock.phase = BattleMockPhase.COMMAND
        mock.selected_command = None
        mock.command_cursor = Mock(active=True)
        mock.command_window = Mock()
        mock._complete_current_turn = Mock()

        self.assertTrue(mock._begin_formation_change())

        self.assertIs(party[0].formation_row, FormationRow.BACK)
        self.assertIs(mock.phase, BattleMockPhase.FORMATION)
        self.assertEqual(mock.formation_start_x, 156)
        self.assertEqual(mock.formation_destination_x, 172)
        self.assertEqual(mock._party_draw_position(0), (156, 64))
        self.assertEqual(mock._party_sprite_source_x(0), 0)
        mock.formation_animation_frame = FORMATION_WALK_PATTERN_FRAME_COUNT
        self.assertEqual(
            mock._party_sprite_source_x(0),
            FORMATION_SPRITE_STEP_X,
        )
        self.assertEqual(mock._party_draw_position(0), (160, 64))
        mock.formation_animation_frame = 0

        for _frame in range(FORMATION_MOVE_FRAME_COUNT):
            mock._update_formation_animation()

        self.assertIsNone(mock.formation_actor_index)
        mock._complete_current_turn.assert_called_once_with()
        mock.command_window.close_immediately.assert_called_once_with()

    def test_disabled_formation_does_not_start_animation(self) -> None:
        party_keys = ("Fiora", "Cerion", "Alvan")
        party = list(
            load_mock_party(
                load_mock_items(),
                load_mock_skills(),
                character_keys=party_keys,
                internal_level=MAX_INTERNAL_LEVEL,
            )
        )
        party[0].formation_row = FormationRow.BACK
        party[1].formation_row = FormationRow.BACK
        party[2].formation_row = FormationRow.FRONT
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = tuple(party)
        mock.monsters = tuple(
            SimpleNamespace(is_front_row=True)
            for _index in range(2)
        )
        mock.active_party_index = 2
        mock.command_window = Mock()

        self.assertFalse(mock._begin_formation_change())

        self.assertIs(party[2].formation_row, FormationRow.FRONT)
        mock.command_window.close_immediately.assert_not_called()

    def test_hidden_member_cannot_start_formation_animation(self) -> None:
        party = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = party
        mock.active_party_index = 0
        mock.hidden_party_indexes = {0}
        mock.command_window = Mock()

        self.assertFalse(mock._begin_formation_change())

        mock.command_window.close_immediately.assert_not_called()

    def test_target_cursor_uses_window_cursor_rendering(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.TARGET
        mock.target_cursor = Mock()

        mock._draw_target_cursor()

        mock.target_cursor.draw.assert_called_once_with()

    def test_update_passes_logical_navigation_to_open_command_window(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            navigation=Direction.RIGHT,
            held_direction=Direction.RIGHT,
        )
        mock.command_window = Mock()
        mock.command_window.is_closed = False
        mock.command_window.is_open = True
        mock.command_cursor = Mock()
        mock.selected_command = None

        mock.update()

        mock.command_window.update.assert_called_once_with(Direction.RIGHT)

    def test_first_confirm_opens_closed_command_window(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.INITIAL
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock()
        mock.command_cursor.selected_key = "attack"
        mock.command_window = Mock()
        mock.command_window.is_closed = True
        mock.command_window.is_open = False
        mock.selected_command = None

        mock.update()

        mock.command_window.open.assert_called_once_with()
        mock.command_window.close_immediately.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)
        self.assertTrue(mock.command_cursor.active)
        self.assertIsNone(mock.selected_command)

    def test_second_confirm_starts_attack_target_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock()
        mock.command_cursor.selected_key = "attack"
        mock.command_window = Mock()
        mock.command_window.is_closed = False
        mock.command_window.is_open = True
        mock.selected_command = None
        mock._begin_attack_target_selection = Mock(return_value=True)

        mock.update()

        mock._begin_attack_target_selection.assert_called_once_with()
        mock.command_window.close_immediately.assert_not_called()
        mock.command_window.open.assert_not_called()
        mock.command_window.update.assert_called_once_with(None)

    def test_confirming_aim_starts_aim_target_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock(selected_key=BattleCommand.AIM)
        mock.command_window = Mock(is_closed=False, is_open=True)
        mock.selected_command = None
        mock._begin_attack_target_selection = Mock(return_value=True)

        mock.update()

        mock._begin_attack_target_selection.assert_called_once_with(
            command=BattleCommand.AIM
        )

    def test_confirming_focus_starts_focus_target_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.command_cursor = Mock(selected_key=BattleCommand.FOCUS)
        mock.command_window = Mock(is_closed=False, is_open=True)
        mock.selected_command = None
        mock._begin_attack_target_selection = Mock(return_value=True)

        mock.update()

        mock._begin_attack_target_selection.assert_called_once_with(
            command=BattleCommand.FOCUS
        )

    def test_global_escape_command_starts_confirmation(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.GLOBAL_COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            confirm=InputButton(triggered=True, held=True)
        )
        mock.global_command_cursor = Mock(selected_key=BattleGlobalCommand.ESCAPE)
        mock.command_window = Mock(is_closed=True, is_open=False)
        mock.global_command_window = Mock(is_closed=False, is_open=True)
        mock.selected_command = None
        mock._begin_escape_confirmation = Mock()

        mock.update()

        mock._begin_escape_confirmation.assert_called_once_with()

    def test_global_cancel_returns_to_member_command_selection(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.GLOBAL_COMMAND
        mock.global_command_window = Mock()
        mock._open_member_command_menu = Mock()

        mock._update_global_command_selection(
            InputState(cancel=InputButton(triggered=True, held=True))
        )

        mock._open_member_command_menu.assert_called_once_with()
        mock.global_command_window.update.assert_not_called()

    def test_global_command_menu_has_fight_escape_and_auto(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.global_command_window = Mock()
        mock.texts = Mock()
        mock.localizer = object()
        mock.texts.text.side_effect = lambda key, _localizer: key
        new_cursor = Mock()
        mock.global_command_window.set_cursor.return_value = new_cursor

        mock._refresh_global_command_options()

        self.assertEqual(
            mock.global_command_window.add_text.call_args_list,
            [
                call("battle.command.fight", 4, 2),
                call("battle.command.escape", 4, 5),
                call("battle.command.auto", 4, 8),
            ],
        )
        targets = mock.global_command_window.set_cursor.call_args.args[0]
        self.assertEqual(
            [target.key for target in targets],
            [
                BattleGlobalCommand.FIGHT,
                BattleGlobalCommand.ESCAPE,
                BattleGlobalCommand.AUTO,
            ],
        )
        self.assertIs(mock.global_command_cursor, new_cursor)

    def test_auto_battle_selects_attack_or_defend_from_target_availability(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.auto_battle_active = False
        mock.global_command_cursor = Mock()
        mock.global_command_window = Mock()
        mock._active_member_attack_targets = Mock(return_value=(2, 3, 4))
        mock._begin_attack_target_selection = Mock()
        mock._begin_defense = Mock()

        mock._begin_auto_battle()

        self.assertTrue(mock.auto_battle_active)
        mock._begin_attack_target_selection.assert_called_once_with()
        mock._begin_defense.assert_not_called()

        mock._active_member_attack_targets.return_value = ()
        mock._begin_attack_target_selection.reset_mock()
        mock._begin_defense.reset_mock()
        mock._begin_auto_action()

        mock._begin_attack_target_selection.assert_not_called()
        mock._begin_defense.assert_called_once_with()

    def test_auto_battle_uses_unrestricted_ambush_while_hidden(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 0
        mock.hidden_party_indexes = {0}
        mock._active_member_attack_targets = Mock(return_value=(0, 1, 2, 3, 4))
        mock._begin_attack_target_selection = Mock()
        mock._begin_defense = Mock()

        mock._begin_auto_action()

        mock._active_member_attack_targets.assert_called_once_with(
            command=BattleCommand.AMBUSH
        )
        mock._begin_attack_target_selection.assert_called_once_with(
            command=BattleCommand.AMBUSH
        )
        mock._begin_defense.assert_not_called()

    def test_auto_target_selection_confirms_the_default_target(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.auto_battle_active = True
        mock._begin_attack_presentation = Mock()

        mock._update_target_selection(InputState())

        mock._begin_attack_presentation.assert_called_once_with()

    def test_cancel_during_auto_targeting_returns_to_member_commands(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.auto_battle_active = True
        mock.phase = BattleMockPhase.TARGET
        mock.selected_command = BattleCommand.ATTACK
        mock.selectable_target_indexes = (2, 3, 4)
        mock.selected_target_index = 4
        mock.target_cursor = Mock(active=True)
        mock._open_member_command_menu = Mock()

        mock._cancel_auto_battle()

        self.assertFalse(mock.auto_battle_active)
        self.assertIsNone(mock.selected_command)
        self.assertEqual(mock.selectable_target_indexes, ())
        self.assertIsNone(mock.selected_target_index)
        self.assertFalse(mock.target_cursor.active)
        mock._open_member_command_menu.assert_called_once_with()

    def test_contextual_cancel_guides_use_the_active_input_device(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.input_guide_window = Mock()
        mock.phase = BattleMockPhase.COMMAND
        mock.auto_battle_active = False
        mock.input_device = InputDevice.KEYBOARD

        mock._refresh_input_guide()

        mock.input_guide_window.add_text.assert_called_once_with(
            "%KEY_X%：ぜんたい",
            0,
            0,
        )

        mock.input_guide_window.reset_mock()
        mock.auto_battle_active = True
        mock.input_device = InputDevice.GAMEPAD
        mock._refresh_input_guide()

        mock.input_guide_window.add_text.assert_called_once_with(
            "%GAMEPAD_B%：キャンセル",
            0,
            0,
        )

    def test_disabled_attack_initially_selects_defend(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = ()
        mock.command_cursor = Mock()
        mock._active_member_command_options = Mock(
            return_value=(
                BattleCommandOption(BattleCommand.ATTACK, enabled=False),
                BattleCommandOption(BattleCommand.SPELL),
                BattleCommandOption(BattleCommand.DEFEND),
                BattleCommandOption(BattleCommand.ITEM),
            )
        )

        mock._select_initial_member_command()

        mock.command_cursor.select_key.assert_called_once_with(BattleCommand.DEFEND)

    def test_member_command_memory_is_restored_and_formation_clears_it(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (object(), object())
        mock.active_party_index = 1
        mock.command_cursor = Mock()
        mock.last_command_by_party_index = {1: BattleCommand.SPELL}
        mock._active_member_command_options = Mock(
            return_value=(
                BattleCommandOption(BattleCommand.ATTACK),
                BattleCommandOption(BattleCommand.SPELL),
                BattleCommandOption(BattleCommand.DEFEND),
            )
        )

        mock._select_initial_member_command()

        mock.command_cursor.select_key.assert_called_once_with(BattleCommand.SPELL)

        mock.command_cursor.select_key.reset_mock()
        mock._remember_active_command(BattleCommand.FORMATION)
        mock._select_initial_member_command()

        self.assertEqual(mock.last_command_by_party_index, {})
        mock.command_cursor.select_key.assert_not_called()

    def test_item_selection_restores_the_active_members_last_item(self) -> None:
        items = load_mock_items()
        candidates = tuple(
            BattleItemCandidate(items[key])
            for key in ("POTION", "REMEDY", "MANA DROP", "PANACEA")
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.active_party_index = 1
        mock.last_item_selection_by_party_index = {1: ("PANACEA", None)}
        mock._active_member_item_candidates = Mock(return_value=candidates)
        mock.command_cursor = Mock()
        mock.command_window = Mock()
        mock.item_window = Mock()
        mock._hide_command_guide = Mock()
        mock._refresh_item_options = Mock()

        self.assertTrue(mock._begin_item_selection())

        self.assertEqual(mock.selected_item_index, 3)
        self.assertEqual(mock.item_scroll_offset, 1)
        self.assertEqual(mock.action_party_index, 1)
        self.assertFalse(mock.action_returning)
        self.assertFalse(mock.action_uses_cast_pose)

    def test_spell_selection_restores_the_active_members_last_spell(self) -> None:
        items = load_mock_items()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
            internal_level=MAX_INTERNAL_LEVEL,
        )
        mock.active_party_index = 0
        remembered_spell = load_mock_spells()["HEALING1"]
        mock.last_spell_key_by_party_index = {0: remembered_spell.key}
        mock._active_member_spell_candidates = Mock(
            return_value=(load_mock_spells()["FIRE1"], remembered_spell)
        )
        mock.command_cursor = Mock()
        mock.command_window = Mock()
        mock.spell_window = Mock()
        mock._hide_command_guide = Mock()
        mock._refresh_spell_options = Mock()

        self.assertTrue(mock._begin_spell_selection())

        self.assertIs(mock.spell_type, remembered_spell.type)
        self.assertEqual(mock.action_party_index, 0)
        self.assertFalse(mock.action_returning)
        self.assertTrue(mock.action_uses_cast_pose)
        mock._refresh_spell_options.assert_called_once_with(
            preferred_key=remembered_spell.key
        )

    def test_escape_confirmation_closes_command_and_defaults_to_yes(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.selected_command = None
        mock.command_cursor = Mock(active=True)
        mock.command_window = Mock()
        mock.escape_cursor = Mock(active=False)

        mock._begin_escape_confirmation()

        self.assertIs(mock.phase, BattleMockPhase.ESCAPE_CONFIRMATION)
        self.assertEqual(mock.selected_command, "escape")
        self.assertFalse(mock.command_cursor.active)
        self.assertTrue(mock.escape_cursor.active)
        mock.command_window.close_immediately.assert_called_once_with()
        mock.escape_cursor.select_key.assert_called_once_with("yes")

    def test_confirming_escape_yes_marks_the_current_member_without_running(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.escape_cursor = Mock(selected_key="yes")
        mock.command_window = Mock(is_closed=True)
        mock._accept_escape_confirmation = Mock()

        with patch("tools.screen_mocks.battle.pyxel.quit") as quit_game:
            mock._update_escape_confirmation(
                InputState(confirm=InputButton(triggered=True, held=True))
            )

        mock._accept_escape_confirmation.assert_called_once_with()
        quit_game.assert_not_called()

    def test_first_escape_member_starts_running_immediately(self) -> None:
        members = tuple(
            SimpleNamespace(formation_row=FormationRow.FRONT, hp=20)
            for _index in range(3)
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = tuple(
            SimpleNamespace(member=member) for member in members
        )
        mock.active_party_index = 0
        mock.escaped_party_indexes = set()
        mock.defending_party_indexes = {0}
        mock.escape_cursor = Mock(active=True)
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock._refresh_party_text_colors = Mock()

        with patch("scenes.battle.play_se") as play_se:
            mock._accept_escape_confirmation()

        self.assertTrue(mock.escape_requested)
        self.assertIs(mock.phase, BattleMockPhase.ESCAPE_MEMBER)
        self.assertEqual(mock.escape_actor_index, 0)
        self.assertEqual(mock.escape_start_x, (156, 160, 164))
        self.assertEqual(mock.escaped_party_indexes, set())
        self.assertEqual(mock.defending_party_indexes, set())
        self.assertFalse(mock.escape_cursor.active)
        play_se.assert_called_once_with(BATTLE_ESCAPE_SE_ID)

    def test_later_party_turn_starts_that_members_escape_without_a_command(self) -> None:
        members = tuple(
            SimpleNamespace(
                definition=SimpleNamespace(key=str(index)),
                formation_row=FormationRow.FRONT,
                hp=20,
            )
            for index in range(3)
        )
        visuals = tuple(
            BattleMockCharacter(member, 0, 0, index)
            for index, member in enumerate(members)
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.timeline = (visuals[1],)
        mock.party_visuals = visuals
        mock.escape_requested = True
        mock.escaped_party_indexes = {0}
        mock.defending_party_indexes = {1}
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.blinking_monster_index = 0
        mock.monster_blink_frames_remaining = 1
        mock._remove_defeated_party_from_timeline = Mock()
        mock._begin_party_member_escape = Mock()
        mock._refresh_party_text_colors = Mock()

        mock._activate_timeline_head()

        self.assertEqual(mock.active_party_index, 1)
        self.assertIsNone(mock.blinking_monster_index)
        mock._begin_party_member_escape.assert_called_once_with(1)
        mock.command_window.open.assert_not_called()

    def test_later_party_member_escape_plays_escape_sound_again(self) -> None:
        members = tuple(
            SimpleNamespace(formation_row=FormationRow.FRONT, hp=20)
            for _index in range(2)
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = tuple(
            SimpleNamespace(member=member) for member in members
        )
        mock.escaped_party_indexes = {0}
        mock.defending_party_indexes = {1}
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock._refresh_party_text_colors = Mock()

        with patch("scenes.battle.play_se") as play_se:
            mock._begin_party_member_escape(1)

        play_se.assert_called_once_with(BATTLE_ESCAPE_SE_ID)
        self.assertIs(mock.phase, BattleMockPhase.ESCAPE_MEMBER)
        self.assertEqual(mock.escape_actor_index, 1)

    def test_escaped_member_leaves_timeline_and_cannot_be_attacked(self) -> None:
        members = (
            SimpleNamespace(formation_row=FormationRow.FRONT, hp=20),
            SimpleNamespace(formation_row=FormationRow.BACK, hp=20),
        )
        visuals = tuple(
            BattleMockCharacter(member, 0, 0, index)
            for index, member in enumerate(members)
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = members
        mock.party_visuals = visuals
        mock._timeline_order = TimelineOrder(
            (
                TimelineEntry(visuals[0], 20, 64.0),
                TimelineEntry(visuals[1], 10, 40.0),
            )
        )
        mock.timeline = mock._timeline_order.actors
        mock.escape_actor_index = 0
        mock.escape_start_x = (ESCAPE_RUN_DESTINATION_X - ESCAPE_RUN_SPEED, 176)
        mock.escape_animation_frame = 0
        mock.escaped_party_indexes = set()
        mock.temporary_front_party_indexes = set()
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock._refresh_party_text_colors = Mock()

        mock._update_party_member_escape()

        self.assertEqual(mock.escaped_party_indexes, {0})
        self.assertEqual(mock.temporary_front_party_indexes, {1})
        self.assertIs(members[1].formation_row, FormationRow.BACK)
        self.assertIs(mock.phase, BattleMockPhase.FORMATION)
        self.assertEqual(mock._party_draw_position(1), (176, 92))
        for _frame in range(FORMATION_MOVE_FRAME_COUNT):
            mock._update_formation_animation()
        self.assertIs(mock.phase, BattleMockPhase.TIMELINE)
        self.assertEqual(mock.timeline_advance.after.actors, (visuals[1],))
        enemy = SimpleNamespace(is_front_row=True)
        self.assertEqual(mock._monster_attack_target_indexes(enemy), (1,))

    def test_final_living_member_departure_starts_escape_message(self) -> None:
        members = (
            SimpleNamespace(formation_row=FormationRow.FRONT, hp=20),
            SimpleNamespace(formation_row=FormationRow.FRONT, hp=0),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = tuple(
            SimpleNamespace(member=member)
            for member in members
        )
        mock.party = members
        mock._timeline_order = TimelineOrder(
            (TimelineEntry(mock.party_visuals[0], 20, 64.0),)
        )
        mock.escape_actor_index = 0
        mock.escape_start_x = (ESCAPE_RUN_DESTINATION_X - ESCAPE_RUN_SPEED, 160)
        mock.escape_animation_frame = 0
        mock.escaped_party_indexes = set()
        mock.temporary_front_party_indexes = set()
        mock.command_cursor = Mock(active=False)
        mock.command_window = Mock()
        mock.escape_cursor = Mock(active=False)
        mock._refresh_party_text_colors = Mock()
        mock.bgm = Mock()

        mock._update_party_member_escape()

        self.assertEqual(mock.escaped_party_indexes, {0})
        self.assertIs(mock.phase, BattleMockPhase.ESCAPE_MESSAGE)
        self.assertEqual(mock.timeline, ())
        mock.bgm.stop.assert_not_called()

    def test_escape_message_hides_selection_without_stopping_bgm(self) -> None:
        members = (
            SimpleNamespace(formation_row=FormationRow.FRONT),
            SimpleNamespace(formation_row=FormationRow.BACK),
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = tuple(
            SimpleNamespace(member=member)
            for member in members
        )
        mock.phase = BattleMockPhase.ESCAPE_CONFIRMATION
        mock.active_party_index = 0
        mock.command_cursor = Mock(active=False)
        mock.escape_cursor = Mock(active=True)
        mock._refresh_party_text_colors = Mock()
        mock.bgm = Mock()

        mock._begin_escape_animation()

        self.assertIs(mock.phase, BattleMockPhase.ESCAPE_MESSAGE)
        self.assertFalse(mock.escape_fade.is_active)
        self.assertEqual(mock.escape_fade.visible_rate, 1.0)
        self.assertFalse(mock.escape_fade_covered)
        self.assertIsNone(mock.active_party_index)
        self.assertFalse(mock.command_cursor.active)
        self.assertFalse(mock.escape_cursor.active)
        mock._refresh_party_text_colors.assert_called_once_with()
        mock.bgm.stop.assert_not_called()

    def test_escape_message_keeps_running_until_a_button_is_pressed(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ESCAPE_MESSAGE
        mock.escape_animation_frame = 0
        mock.escape_fade = Mock()
        mock.bgm = Mock()

        mock._update_escape_message(InputState())

        self.assertIs(mock.phase, BattleMockPhase.ESCAPE_MESSAGE)
        self.assertEqual(mock.escape_animation_frame, 0)
        mock.escape_fade.start.assert_not_called()
        mock.bgm.stop.assert_not_called()

        mock._update_escape_message(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertIs(mock.phase, BattleMockPhase.ESCAPE)
        self.assertEqual(mock.escape_animation_frame, 0)
        mock.escape_fade.start.assert_called_once_with()
        mock.bgm.stop.assert_called_once_with()

    def test_escape_message_accepts_cancel_button_for_acknowledgement(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ESCAPE_MESSAGE
        mock.escape_animation_frame = 0
        mock.escape_fade = Mock()
        mock.bgm = Mock()

        mock._update_escape_message(
            InputState(cancel=InputButton(triggered=True, held=True))
        )

        self.assertIs(mock.phase, BattleMockPhase.ESCAPE)
        mock.escape_fade.start.assert_called_once_with()
        mock.bgm.stop.assert_called_once_with()

    def test_escape_run_uses_da2_speed_walk_pattern_and_right_facing_sprite(
        self,
    ) -> None:
        member = SimpleNamespace(formation_row=FormationRow.FRONT)
        visual = SimpleNamespace(member=member, battle_sprite=2)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party_visuals = (visual,)
        mock.character_sprites = object()
        mock.phase = BattleMockPhase.ESCAPE_MEMBER
        mock.escape_actor_index = 0
        mock.escaped_party_indexes = set()
        mock.escape_start_x = (156,)
        mock.escape_animation_frame = ESCAPE_RUN_PATTERN_FRAME_COUNT

        self.assertGreater(ESCAPE_RUN_SPEED, 0)
        self.assertEqual(
            mock._party_draw_position(0),
            (
                156 + ESCAPE_RUN_SPEED * ESCAPE_RUN_PATTERN_FRAME_COUNT,
                64,
            ),
        )
        self.assertEqual(mock._party_sprite_source_x(0), 16)

        with patch("tools.screen_mocks.battle.pyxel.blt") as blt:
            mock._draw_party()

        blt.assert_called_once_with(
            156 + ESCAPE_RUN_SPEED * ESCAPE_RUN_PATTERN_FRAME_COUNT,
            64,
            mock.character_sprites,
            16,
            64,
            -16,
            32,
            1,
        )

    def test_escape_finishes_when_fade_reaches_black(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.escape_fade_covered = True
        mock._update_escape_fade = Mock()

        with patch("tools.screen_mocks.battle.pyxel.quit") as quit_game:
            mock._update_escape_animation()

        mock._update_escape_fade.assert_called_once_with()
        quit_game.assert_called_once_with()

    def test_escape_fade_reaches_black_and_does_not_fade_back_in(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.escape_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        mock.escape_fade.start()
        mock.escape_fade_covered = False
        mock.palette_shifter = Mock(base_colors=(0x000000,))

        for _frame in range(DEFAULT_FADE_FRAME_COUNT):
            mock._update_escape_fade()

        self.assertTrue(mock.escape_fade_covered)
        self.assertEqual(mock.escape_fade.visible_rate, 0.0)
        mock.palette_shifter.set_global_mix.assert_called_with(
            base_rate=0.0,
            target_color=0x000000,
        )
        update_count = mock.palette_shifter.set_global_mix.call_count

        mock._update_escape_fade()

        self.assertEqual(
            mock.palette_shifter.set_global_mix.call_count,
            update_count,
        )

    def test_escape_fade_starts_only_after_escape_message_acknowledgement(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.escape_fade = FadeThroughBlack(DEFAULT_FADE_FRAME_COUNT)
        mock.escape_fade_covered = False
        mock.palette_shifter = Mock(base_colors=(0x000000,))

        self.assertFalse(mock.escape_fade.is_active)
        mock.palette_shifter.set_global_mix.assert_not_called()

        mock.escape_fade.start()
        mock._update_escape_fade()

        self.assertTrue(mock.escape_fade.is_active)
        mock.palette_shifter.set_global_mix.assert_called_once()

    def test_escape_no_returns_to_the_menu_that_opened_confirmation(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.ESCAPE_CONFIRMATION
        mock.selected_command = "escape"
        mock.escape_cursor = Mock(selected_key="no", active=True)
        mock.command_window = Mock(is_closed=True)
        mock.escape_return_phase = BattleMockPhase.GLOBAL_COMMAND
        mock._open_global_command_menu = Mock()

        mock._update_escape_confirmation(
            InputState(confirm=InputButton(triggered=True, held=True))
        )

        self.assertIsNone(mock.selected_command)
        self.assertFalse(mock.escape_cursor.active)
        mock._open_global_command_menu.assert_called_once_with()

    def test_monster_names_only_draw_for_targeting_and_button_wait(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        base_window = Mock()
        monster_name = Mock()
        mock.windows = [base_window]
        mock.party_status_windows = []
        mock.monsters = (SimpleNamespace(is_alive=True),)
        mock.monster_name_windows = [monster_name]
        mock.escape_message_window = Mock()
        mock.escape_started_message_window = Mock()
        mock.battle_popup_window = Mock()
        mock.action_popup_window = Mock()
        mock.battle_popup = BattleTimedPopup()
        mock.escape_choice_window = Mock()
        mock.command_window = Mock(is_closed=False)
        mock.global_command_window = Mock(is_closed=True, is_open=False)

        mock.phase = BattleMockPhase.COMMAND
        mock._draw_windows()
        monster_name.draw.assert_not_called()

        mock.phase = BattleMockPhase.TARGET
        mock._draw_windows()
        monster_name.draw.assert_called_once_with()

        monster_name.reset_mock()
        mock.phase = BattleMockPhase.GLOBAL_COMMAND
        mock.global_command_window.is_open = False
        mock._draw_windows()
        monster_name.draw.assert_not_called()

        mock.global_command_window.is_open = True
        mock._draw_windows()
        monster_name.draw.assert_called_once_with()

        monster_name.reset_mock()
        mock.phase = BattleMockPhase.INITIAL
        mock.command_window.is_closed = True
        mock._draw_windows()
        monster_name.draw.assert_called_once_with()

        monster_name.reset_mock()
        mock.phase = BattleMockPhase.ESCAPE_CONFIRMATION
        mock.command_window.is_closed = False
        mock._draw_windows()
        monster_name.draw.assert_not_called()
        mock.escape_message_window.draw.assert_not_called()
        mock.escape_choice_window.draw.assert_not_called()

        mock.command_window.is_closed = True
        mock._draw_windows()
        mock.escape_message_window.draw.assert_called_once_with()
        mock.escape_choice_window.draw.assert_called_once_with()

        mock.phase = BattleMockPhase.ESCAPE_MESSAGE
        mock._draw_windows()
        mock.escape_started_message_window.draw.assert_called_once_with()

        mock.phase = BattleMockPhase.ACTION_PRESENTATION
        mock.action_presentation = BattleActionPresentation(())
        mock.battle_popup.show(1)
        mock._draw_windows()
        mock.action_popup_window.draw.assert_called_once_with()

    def test_monster_name_colors_follow_target_availability_and_button_wait(
        self,
    ) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monster_name_windows = [Mock() for _index in range(3)]
        for window in mock.monster_name_windows:
            window.add_text.side_effect = (
                lambda text, x, y, **kwargs: WindowText(
                    text,
                    x,
                    y,
                    **kwargs,
                )
            )
        mock.monster_name_texts = [
            WindowText(f"monster-{index}", 0, 0, color=4)
            for index in range(3)
        ]
        mock.phase = BattleMockPhase.TARGET
        mock.selectable_target_indexes = (0, 2)

        mock._refresh_monster_name_colors()

        self.assertEqual(
            [placement.color for placement in mock.monster_name_texts],
            [5, 4, 5],
        )

        mock.phase = BattleMockPhase.INITIAL
        mock.selectable_target_indexes = ()
        mock._refresh_monster_name_colors()

        self.assertEqual(
            [placement.color for placement in mock.monster_name_texts],
            [5, 5, 5],
        )

    def test_party_status_appears_after_every_party_member_lands(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        command_window = Mock()
        party_status_windows = [Mock(), Mock(), Mock()]
        mock.windows = [command_window, *party_status_windows]
        mock.party_status_windows = party_status_windows
        mock.monster_name_windows = []
        mock.escape_message_window = Mock()
        mock.escape_started_message_window = Mock()
        mock.escape_choice_window = Mock()
        mock.command_window = command_window
        mock.phase = BattleMockPhase.ENTRANCE

        mock.entrance_animation_frame = PARTY_ENTRANCE_COMPLETE_FRAME - 1
        mock._draw_windows()
        command_window.draw.assert_called_once_with()
        for status_window in party_status_windows:
            status_window.draw.assert_not_called()

        mock.entrance_animation_frame = PARTY_ENTRANCE_COMPLETE_FRAME
        mock._draw_windows()
        for status_window in party_status_windows:
            status_window.draw.assert_called_once_with()

        for status_window in party_status_windows:
            status_window.reset_mock()
        mock.phase = BattleMockPhase.ESCAPE_MESSAGE
        mock._draw_windows()
        for status_window in party_status_windows:
            status_window.draw.assert_not_called()

        mock.phase = BattleMockPhase.ESCAPE
        mock._draw_windows()
        for status_window in party_status_windows:
            status_window.draw.assert_not_called()

    def test_escaping_member_status_is_hidden_when_running_starts(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        command_window = Mock()
        party_status_windows = [Mock(), Mock(), Mock()]
        mock.windows = [command_window, *party_status_windows]
        mock.party_status_windows = party_status_windows
        mock.monsters = ()
        mock.monster_name_windows = []
        mock.command_window = command_window
        mock.phase = BattleMockPhase.ESCAPE_MEMBER
        mock.escape_actor_index = 1
        mock.escaped_party_indexes = {0}

        mock._draw_windows()

        command_window.draw.assert_called_once_with()
        party_status_windows[0].draw.assert_not_called()
        party_status_windows[1].draw.assert_not_called()
        party_status_windows[2].draw.assert_called_once_with()

    def test_cancel_input_opens_the_global_command_menu(self) -> None:
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.phase = BattleMockPhase.COMMAND
        mock.input_reader = Mock()
        mock.input_reader.poll.return_value = InputState(
            cancel=InputButton(triggered=True, held=True)
        )
        mock._open_global_command_menu = Mock()

        with patch("tools.screen_mocks.battle.pyxel.quit") as quit_game:
            mock.update()

        quit_game.assert_not_called()
        mock._open_global_command_menu.assert_called_once_with()

    def test_member_attack_effects_apply_to_a_living_monster(self) -> None:
        for effect, state_field in (
            (AdditionalEffect.POISON, "poisoned"),
            (AdditionalEffect.SLEEP, "sleeping"),
            (AdditionalEffect.STUN, "stunned"),
            (AdditionalEffect.DEFENSE_DOWN, "defense_modifier"),
        ):
            with self.subTest(effect=effect):
                monster = _damage_test_monster()
                mock = BattleScreenMock.__new__(BattleScreenMock)
                mock.monsters = (monster,)
                mock._show_battle_popup = Mock()

                with patch("scenes.battle.random.randint", return_value=2):
                    applied = mock._apply_additional_effects_to_monster(
                        0,
                        (effect,),
                    )

                self.assertEqual(applied, (effect,))
                self.assertTrue(getattr(monster.state, state_field))
                mock._show_battle_popup.assert_not_called()

    def test_instant_death_effect_defeats_a_living_monster(self) -> None:
        monster = _damage_test_monster()
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.monsters = (monster,)
        mock._show_battle_popup = Mock()

        applied = mock._apply_additional_effects_to_monster(
            0,
            (AdditionalEffect.DEATH,),
        )

        self.assertEqual(applied, (AdditionalEffect.DEATH,))
        self.assertFalse(monster.is_alive)
        mock._show_battle_popup.assert_not_called()

    def test_lethal_and_death_weapon_are_merged_into_one_check(self) -> None:
        member = SimpleNamespace(has_skill=Mock(return_value=True))
        weapon = SimpleNamespace(additional_effect=AdditionalEffect.DEATH)

        candidates = BattleScreenMock._effect_candidates_for_member_attack(
            member,
            weapon,
        )

        self.assertEqual(candidates, ((AdditionalEffect.DEATH, True),))

    def test_weapon_effect_and_lethal_share_one_random_roll(self) -> None:
        member = SimpleNamespace(has_skill=Mock(return_value=True))
        weapon = SimpleNamespace(additional_effect=AdditionalEffect.POISON)
        monster = SimpleNamespace(
            is_boss=False,
            weaknesses=frozenset(),
            resistances=frozenset(),
        )
        result = SimpleNamespace(
            hit=True,
            adjusted_hit=100,
            critical=False,
        )
        mock = BattleScreenMock.__new__(BattleScreenMock)

        with patch(
            "scenes.battle.random.randint",
            return_value=0,
        ) as randint:
            effects = mock._resolve_member_attack_additional_effects(
                member,
                weapon,
                monster,
                result,
            )

        self.assertEqual(
            effects,
            (AdditionalEffect.POISON, AdditionalEffect.DEATH),
        )
        randint.assert_called_once_with(0, 99)

    def test_enemy_attack_effects_apply_to_a_living_member(self) -> None:
        for effect, state_field in (
            (AdditionalEffect.POISON, "poisoned"),
            (AdditionalEffect.SLEEP, "sleeping"),
            (AdditionalEffect.PARALIZE, "paralyzed"),
            (AdditionalEffect.STUN, "stunned"),
            (AdditionalEffect.DEFENSE_DOWN, "protection_level"),
        ):
            with self.subTest(effect=effect):
                member = load_mock_party(
                    load_mock_items(),
                    load_mock_skills(),
                    character_keys=(BATTLE_MOCK_PARTY_CHARACTER_KEYS[0],),
                    internal_level=MAX_INTERNAL_LEVEL,
                )[0]
                mock = BattleScreenMock.__new__(BattleScreenMock)
                mock.party = (member,)
                mock.party_visuals = (BattleMockCharacter(member, 0, 0, 0),)
                mock.localizer = Localizer(Language.JAPANESE)
                mock.focused_target_by_party_index = {0: 0}
                mock._refresh_party_hp_text = Mock()
                mock._show_battle_popup = Mock()

                with patch("scenes.battle.random.randint", return_value=2):
                    applied = mock._apply_additional_effects_to_member(
                        0,
                        (effect,),
                    )

                self.assertEqual(applied, (effect,))
                self.assertTrue(getattr(member, state_field))
                self.assertEqual(mock.focused_target_by_party_index, {})
                mock._show_battle_popup.assert_not_called()

    def test_stun_skips_the_next_timeline_head_once(self) -> None:
        member = load_mock_party(
            load_mock_items(),
            load_mock_skills(),
            character_keys=(BATTLE_MOCK_PARTY_CHARACTER_KEYS[0],),
            internal_level=MAX_INTERNAL_LEVEL,
        )[0]
        member.stunned = True
        visual = BattleMockCharacter(member, 0, 0, 0)
        mock = BattleScreenMock.__new__(BattleScreenMock)
        mock.party = (member,)
        mock.party_visuals = (visual,)
        mock.timeline = (visual,)
        mock.defending_party_indexes = set()
        mock.focused_target_by_party_index = {0: 0}
        mock._remove_defeated_party_from_timeline = Mock()
        mock._party_is_defeated = Mock(return_value=False)
        mock._begin_front_promotion_if_needed = Mock(return_value=False)
        mock._apply_turn_start_hp_change = Mock(return_value=False)
        mock._start_timeline_animation = Mock()
        mock._refresh_party_text_colors = Mock()

        mock._activate_timeline_head()

        self.assertFalse(member.stunned)
        self.assertEqual(mock.focused_target_by_party_index, {})
        mock._start_timeline_animation.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
