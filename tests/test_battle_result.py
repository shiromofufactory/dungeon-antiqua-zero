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
from game_data import load_spells

from input import InputButton, InputState
from member import EquipmentSlot, ProficiencyKind
from resources import FontResources
from rendering.victory_pose import VICTORY_MOTION_LIMIT, VICTORY_SPRITE_SOURCE_X
from state import SaveData, Settings
from systems import BattleProgression, EnemyProgressionData
from text_catalog import TextCatalog
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

    def test_new_spell_notices_precede_result_completion(self) -> None:
        before = self.overlay.growth.before[0]
        after = self.overlay.growth.after[0]
        old = before.proficiencies[ProficiencyKind.SACRED]
        new = replace(old, level=3, progress=0)
        before_proficiencies = dict(before.proficiencies)
        after_proficiencies = dict(after.proficiencies)
        before_proficiencies[ProficiencyKind.SACRED] = replace(old, level=1)
        after_proficiencies[ProficiencyKind.SACRED] = new
        growth = replace(
            self.overlay.growth,
            before=(replace(before, proficiencies=before_proficiencies),),
            after=(replace(after, proficiencies=after_proficiencies),),
        )
        overlay = BattleResultOverlay(
            party=self.party,
            growth=growth,
            settings=Settings(),
            fonts=FontResources(),
            character_sprites=object(),
            spells=tuple(load_spells().values()),
            texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
        )
        self.assertIsNotNone(overlay.spell_learned_popup)
        self.assertEqual(len(overlay.spell_learned_popup.notices), 2)
        self.assertEqual(
            tuple(spell.key for _, spell in overlay.spell_learned_popup.notices),
            ("PROTECTION", "CURE"),
        )
        for _frame in range(RESULT_WAIT_FRAME_COUNT + RESULT_ANIMATION_FRAME_COUNT):
            self.assertFalse(overlay.update(InputState()))
        confirm = InputState(confirm=InputButton(triggered=True))
        self.assertFalse(overlay.update(confirm))
        self.assertIsNotNone(overlay.spell_learned_popup)
        self.assertFalse(overlay.update(confirm))
        self.assertIsNone(overlay.spell_learned_popup)
        self.assertTrue(overlay.update(confirm))

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

    def test_celebrates_only_members_with_stat_or_level_growth(self) -> None:
        before = self.overlay.growth.before[0]
        proficiency = before.proficiencies[ProficiencyKind.KNIFE]
        for field in ("internal_level", "max_hp", "max_mp", "hp", "mp", "progress", "level", "unchanged"):
            with self.subTest(field=field):
                after = before
                if field in ("progress", "level"):
                    proficiencies = dict(before.proficiencies)
                    proficiencies[ProficiencyKind.KNIFE] = replace(
                        proficiency, **{field: getattr(proficiency, field) + 1}
                    )
                    after = replace(before, proficiencies=proficiencies)
                elif field != "unchanged":
                    after = replace(before, **{field: getattr(before, field) + 1})
                overlay = BattleResultOverlay(
                    party=self.party,
                    growth=replace(self.overlay.growth, before=(before,), after=(after,)),
                    settings=Settings(), fonts=FontResources(), character_sprites=object(),
                )
                self.assertEqual(
                    overlay.celebrating_members,
                    (field in ("internal_level", "max_hp", "max_mp", "level"),),
                )

    def test_growth_pose_starts_after_interpolation_and_stops_after_seventy_frames(self) -> None:
        with patch("ui.battle_result.pyxel.cls"), patch("ui.battle_result.pyxel.blt") as blt, patch.object(type(self.overlay.windows[0]), "draw"):
            self.overlay.draw()
            self.assertEqual(blt.call_args.args[3], 0)
            for _ in range(RESULT_WAIT_FRAME_COUNT + RESULT_ANIMATION_FRAME_COUNT):
                self.overlay.update(InputState())
                self.assertEqual(self.overlay.victory_motion_frame, 0)
            for frame in range(1, VICTORY_MOTION_LIMIT + 1):
                self.overlay.update(InputState())
                self.overlay.draw()
                expected = VICTORY_SPRITE_SOURCE_X if 10 <= frame < 30 or 50 <= frame < 70 else 0
                self.assertEqual(blt.call_args.args[3], expected)
            for _ in range(40):
                self.overlay.update(InputState())
            self.overlay.draw()
            self.assertEqual(self.overlay.victory_motion_frame, 70)
            self.assertEqual(blt.call_args.args[3], 0)

    def test_growth_pose_overrides_ailments_but_keeps_death_pose(self) -> None:
        member = self.party[0]
        member.poisoned = member.paralyzed = True
        self.assertEqual(member_battle_sprite_region(member, victory_frame=10)[0], VICTORY_SPRITE_SOURCE_X)
        member.hp = 0
        self.assertEqual(member_battle_sprite_region(member, victory_frame=10)[0], RESULT_DEAD_SPRITE_SOURCE_X)


if __name__ == "__main__":
    unittest.main()
