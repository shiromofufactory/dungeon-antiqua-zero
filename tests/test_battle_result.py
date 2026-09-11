from __future__ import annotations

import unittest

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
from ui.battle_result import BattleResultOverlay, RESULT_ANIMATION_FRAME_COUNT


class BattleResultOverlayTest(unittest.TestCase):
    def setUp(self) -> None:
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
        for _frame in range(RESULT_ANIMATION_FRAME_COUNT - 1):
            self.assertFalse(self.overlay.update(InputState()))
            self.assertFalse(self.overlay.animation_complete)

        self.assertFalse(self.overlay.update(InputState()))
        self.assertTrue(self.overlay.animation_complete)

    def test_accepts_only_confirm_after_animation(self) -> None:
        early_confirm = InputState(confirm=InputButton(triggered=True))
        self.assertFalse(self.overlay.update(early_confirm))
        for _frame in range(RESULT_ANIMATION_FRAME_COUNT - 1):
            self.overlay.update(InputState())

        self.assertFalse(self.overlay.update(InputState()))
        self.assertTrue(
            self.overlay.update(InputState(confirm=InputButton(triggered=True)))
        )

    def test_marks_level_and_max_hp_growth_with_positive_color(self) -> None:
        for _frame in range(RESULT_ANIMATION_FRAME_COUNT):
            self.overlay.update(InputState())

        texts = [placement.text for placement in self.overlay.windows[0].texts]
        self.assertTrue(any(text.startswith("%COL_POSITIVE%ＨＰ") for text in texts))
        self.assertTrue(
            any("%COL_POSITIVE%%KNIFE%" in text for text in texts)
        )


if __name__ == "__main__":
    unittest.main()
