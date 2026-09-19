from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_character_records,
    load_mock_items,
    load_mock_skills,
)
from tools.screen_mocks.battle_result import build_result_party

from input import InputButton, InputState
from member import EquipmentSlot, ProficiencyKind
from resources import FontResources
from state import SaveData, Settings
from systems import BattleProgression, EnemyProgressionData
from ui.battle_result import (
    RESULT_AILMENT_SPRITE_SOURCE_X,
    RESULT_ANIMATION_FRAME_COUNT,
    RESULT_DEAD_SPRITE_SOURCE_X,
    RESULT_DEAD_SPRITE_WIDTH,
    RESULT_INCREMENT_SE_ID,
    RESULT_WAIT_FRAME_COUNT,
    BattleResultOverlay,
    member_battle_sprite_region,
)


class BattleResultOverlayTest(unittest.TestCase):
    def setUp(self) -> None:
        play_se_patcher = patch("ui.battle_result.play_se")
        self.play_se = play_se_patcher.start()
        self.addCleanup(play_se_patcher.stop)
        self.party = build_result_party(
            load_mock_character_records(),
            load_mock_items(),
            load_mock_skills(),
        )[:1]
        member = self.party[0]
        member.proficiency(ProficiencyKind.KNIFE).level = 0
        member.proficiency(ProficiencyKind.KNIFE).progress = 99
        member.max_hp -= 1
        member.hp = min(member.hp, member.max_hp)
        progression = BattleProgression((EnemyProgressionData(1, 0, 1, 0),))
        weapon = member.equipment.weapon_at(EquipmentSlot.RIGHT)
        progression.record_weapon_action(member, (weapon,), (1,))
        growth = progression.settle(SaveData(), self.party)
        self.overlay = BattleResultOverlay(
            party=self.party,
            growth=growth,
            settings=Settings(),
            fonts=FontResources(),
            character_sprites=object(),
        )

    def test_interpolates_for_exactly_thirty_frames(self) -> None:
        for _frame in range(RESULT_WAIT_FRAME_COUNT):
            self.assertFalse(self.overlay.update(InputState()))
            self.assertEqual(self.overlay.frame, 0)

        for _frame in range(RESULT_ANIMATION_FRAME_COUNT - 1):
            self.assertFalse(self.overlay.update(InputState()))
            self.assertFalse(self.overlay.animation_complete)

        self.assertFalse(self.overlay.update(InputState()))
        self.assertTrue(self.overlay.animation_complete)

    def test_accepts_only_confirm_after_animation(self) -> None:
        early_confirm = InputState(confirm=InputButton(triggered=True))
        self.assertFalse(self.overlay.update(early_confirm))
        for _frame in range(RESULT_WAIT_FRAME_COUNT - 1):
            self.overlay.update(InputState())
        for _frame in range(RESULT_ANIMATION_FRAME_COUNT):
            self.overlay.update(InputState())

        self.assertFalse(self.overlay.update(InputState()))
        self.assertTrue(
            self.overlay.update(InputState(confirm=InputButton(triggered=True)))
        )

    def test_marks_level_and_max_hp_growth_with_positive_color(self) -> None:
        for _frame in range(
            RESULT_WAIT_FRAME_COUNT + RESULT_ANIMATION_FRAME_COUNT
        ):
            self.overlay.update(InputState())

        texts = [placement.text for placement in self.overlay.windows[0].texts]
        hp_text = next(text for text in texts if text.startswith("ＨＰ"))
        self.assertNotIn("%COL_POSITIVE%ＨＰ", hp_text)
        self.assertIn("／%COL_POSITIVE%", hp_text)
        self.assertTrue(hp_text.endswith("%COL_END%"))
        self.assertTrue(
            any("%COL_POSITIVE%%KNIFE%" in text for text in texts)
        )

    def test_plays_se_two_only_when_a_displayed_number_changes(self) -> None:
        for _frame in range(RESULT_WAIT_FRAME_COUNT):
            self.overlay.update(InputState())
        self.play_se.assert_not_called()

        previous = self.overlay._displayed_numbers(0)
        changed_frame_count = 0
        for _frame in range(RESULT_ANIMATION_FRAME_COUNT):
            self.overlay.update(InputState())
            current = self.overlay._displayed_numbers(0)
            if current != previous:
                changed_frame_count += 1
            previous = current

        self.assertGreater(changed_frame_count, 0)
        self.assertEqual(self.play_se.call_count, changed_frame_count)
        self.play_se.assert_called_with(RESULT_INCREMENT_SE_ID)

    def test_marks_only_the_max_mp_number_with_positive_color(self) -> None:
        before = self.overlay.growth.before[0]
        growth = replace(
            self.overlay.growth,
            after=(replace(before, max_mp=before.max_mp + 1),),
        )
        overlay = BattleResultOverlay(
            party=self.party,
            growth=growth,
            settings=Settings(),
            fonts=FontResources(),
            character_sprites=object(),
        )
        for _frame in range(
            RESULT_WAIT_FRAME_COUNT + RESULT_ANIMATION_FRAME_COUNT
        ):
            overlay.update(InputState())

        mp_text = next(
            placement.text
            for placement in overlay.windows[0].texts
            if placement.text.startswith("ＭＰ")
        )
        self.assertNotIn("%COL_POSITIVE%ＭＰ", mp_text)
        self.assertIn("／%COL_POSITIVE%", mp_text)
        self.assertTrue(mp_text.endswith("%COL_END%"))

    def test_marks_max_mp_only_after_the_displayed_value_increases(self) -> None:
        original = self.overlay.growth.before[0]
        before = replace(original, mp=min(original.mp, 16), max_mp=16)
        after = replace(before, max_mp=24)
        overlay = BattleResultOverlay(
            party=self.party,
            growth=replace(self.overlay.growth, before=(before,), after=(after,)),
            settings=Settings(),
            fonts=FontResources(),
            character_sprites=object(),
        )

        def mp_text() -> str:
            return next(
                placement.text
                for placement in overlay.windows[0].texts
                if placement.text.startswith("ＭＰ")
            )

        self.assertEqual(overlay._snapshot(0).max_mp, 16)
        self.assertNotIn("%COL_POSITIVE%", mp_text())
        for _frame in range(RESULT_WAIT_FRAME_COUNT):
            overlay.update(InputState())
        for _frame in range(3):
            overlay.update(InputState())
            self.assertEqual(overlay._snapshot(0).max_mp, 16)
            self.assertNotIn("%COL_POSITIVE%", mp_text())

        overlay.update(InputState())

        self.assertEqual(overlay._snapshot(0).max_mp, 17)
        self.assertIn("／%COL_POSITIVE%", mp_text())

    def test_uses_death_and_ailment_poses_in_the_result(self) -> None:
        member = self.party[0]
        sprite_y = member.definition.battle_sprite * 32

        member.poisoned = True
        self.assertEqual(
            member_battle_sprite_region(member),
            (RESULT_AILMENT_SPRITE_SOURCE_X, sprite_y, 16, 32),
        )

        member.poisoned = False
        member.paralyzed = True
        self.assertEqual(
            member_battle_sprite_region(member),
            (RESULT_AILMENT_SPRITE_SOURCE_X, sprite_y, 16, 32),
        )

        member.hp = 0
        member.poisoned = True
        self.assertEqual(
            member_battle_sprite_region(member),
            (RESULT_DEAD_SPRITE_SOURCE_X, sprite_y, RESULT_DEAD_SPRITE_WIDTH, 32),
        )


if __name__ == "__main__":
    unittest.main()
