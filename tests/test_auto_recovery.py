from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import Mock, patch

from tools._bootstrap import APP_ROOT
from field import FieldPosition
from game_data import load_spells
from input import Direction, InputButton, InputState
from member import ProficiencyKind
from resources import FontResources
from spell import SpellType
from state import AutoRecoveryConfig, AutoRecoveryMethod, Language, SaveData, Settings
from systems.auto_recovery import (
    RecoveryResult,
    eligible_healer_keys,
    execute_auto_recovery,
    next_recovery_step,
    valid_config_for_party,
)
from systems.inventory import InventorySystem
from systems.spell_progression import MenuSpellProficiencyGrowth
from systems.save import (
    SaveSystemError,
    create_save_document,
    restore_save_document,
)
from text_catalog import TextCatalog
from tools.screen_mocks._fixtures import (
    load_mock_character_records,
    load_mock_items,
    load_mock_party,
    load_mock_skills,
)
from ui.auto_recovery import AutoRecoveryOverlay
from ui.spell_proficiency import (
    PROFICIENCY_ANIMATION_FRAME_COUNT,
    spell_proficiency_text,
)


class AutoRecoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.items = load_mock_items()
        cls.skills = load_mock_skills()
        cls.spells = load_spells()
        cls.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")

    def setUp(self) -> None:
        self.party = load_mock_party(self.items, self.skills)

    def test_threshold_is_strict_and_includes_reserve(self) -> None:
        reserve = self.party[5]
        reserve.hp = (reserve.max_hp * 60 + 99) // 100
        inventory = InventorySystem(self.items, {"POTION": 3})
        config = AutoRecoveryConfig(60, AutoRecoveryMethod.ITEMS_SPELLS)
        self.assertIsNone(next_recovery_step(self.party, self.spells, inventory, config))
        reserve.hp -= 1
        step = next_recovery_step(self.party, self.spells, inventory, config)
        self.assertIsNotNone(step)
        self.assertEqual(step.target_index, 5)

    def test_item_first_cures_and_heals_reserve_and_reports_consumption(self) -> None:
        reserve = self.party[5]
        reserve.hp = 20
        reserve.poisoned = True
        inventory = InventorySystem(self.items, {"POTION": 3, "REMEDY": 1})
        result = execute_auto_recovery(
            self.party,
            self.spells,
            inventory,
            AutoRecoveryConfig(80, AutoRecoveryMethod.ITEMS_SPELLS),
            random_factor=lambda: 0.5,
        )
        self.assertFalse(reserve.poisoned)
        self.assertGreaterEqual(reserve.hp * 100, reserve.max_hp * 80)
        self.assertEqual(result.items_used["REMEDY"], 1)
        self.assertGreater(result.items_used["POTION"], 0)
        self.assertEqual(inventory.quantity("REMEDY"), 0)
        self.assertIn(5, result.hp_recovered)
        self.assertEqual(result.mp_spent, set())

    def test_selected_healer_casts_first_and_grows_proficiency(self) -> None:
        self.party[5].hp = 20
        healer = self.party[1]
        proficiency = healer.proficiency(ProficiencyKind.SACRED)
        before = proficiency.progress
        before_total = proficiency.level * 100 + before
        inventory = InventorySystem(self.items, {"POTION": 3})
        config = AutoRecoveryConfig(60, AutoRecoveryMethod.SPELLS, healer.definition.key)
        step = next_recovery_step(self.party, self.spells, inventory, config)
        self.assertEqual(step.caster_index, 1)
        result = execute_auto_recovery(
            self.party, self.spells, inventory, config, random_factor=lambda: 0.5
        )
        self.assertGreater(result.actions, 0)
        self.assertEqual(result.items_used, {})
        self.assertEqual(inventory.quantity("POTION"), 3)
        self.assertGreater(healer.proficiency(ProficiencyKind.SACRED).progress, before)
        self.assertIn(5, result.hp_recovered)
        self.assertIn(1, result.mp_spent)
        self.assertEqual(result.proficiency_growths[1].before_total, before_total)
        self.assertEqual(
            result.proficiency_growths[1].after_total,
            proficiency.level * 100 + proficiency.progress,
        )

    def test_multiple_casts_aggregate_proficiency_growth_per_caster(self) -> None:
        self.party[5].hp = 20
        healer = self.party[1]
        proficiency = healer.proficiency(ProficiencyKind.SACRED)
        before_total = proficiency.level * 100 + proficiency.progress
        result = execute_auto_recovery(
            self.party,
            self.spells,
            InventorySystem(self.items),
            AutoRecoveryConfig(100, AutoRecoveryMethod.SPELLS, healer.definition.key),
            random_factor=lambda: 0.5,
        )
        self.assertGreater(result.actions, 1)
        self.assertEqual(tuple(result.proficiency_growths), (1,))
        growth = result.proficiency_growths[1]
        self.assertEqual(growth.before_total, before_total)
        self.assertEqual(
            growth.after_total,
            proficiency.level * 100 + proficiency.progress,
        )

    def test_cure_without_hp_gain_does_not_mark_hp_as_recovered(self) -> None:
        self.party[0].poisoned = True
        result = execute_auto_recovery(
            self.party,
            self.spells,
            InventorySystem(self.items, {"REMEDY": 1}),
            AutoRecoveryConfig(60, AutoRecoveryMethod.ITEMS_SPELLS),
        )
        self.assertEqual(result.actions, 1)
        self.assertEqual(result.hp_recovered, set())
        self.assertEqual(result.mp_spent, set())

    def test_unusable_selected_healer_falls_back_and_departure_resets_choice(self) -> None:
        self.party[5].hp = 20
        self.party[1].mp = 0
        config = AutoRecoveryConfig(60, AutoRecoveryMethod.SPELLS, "Cerion")
        step = next_recovery_step(
            self.party, self.spells, InventorySystem(self.items), config
        )
        self.assertIsNotNone(step)
        self.assertNotEqual(step.caster_index, 1)
        self.assertEqual(
            eligible_healer_keys(self.party), ("Cerion", "Alvan", "Dain")
        )
        self.assertIsNone(
            valid_config_for_party(config, self.party[2:]).healer_key
        )

    def test_save_roundtrip_and_old_save_default(self) -> None:
        config = AutoRecoveryConfig(90, AutoRecoveryMethod.ITEMS_SPELLS, "Cerion")
        save_data = SaveData(auto_recovery=config)
        document = create_save_document(
            save_data=save_data,
            active_party=self.party[:2],
            character_states={member.definition.key: member for member in self.party[:2]},
            inventory=InventorySystem(self.items),
            map_id="worldmap",
            position=FieldPosition(17, 39),
            facing=Direction.DOWN,
            saved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        restored = restore_save_document(
            document,
            character_records=load_mock_character_records(),
            items=self.items,
            skills=self.skills,
        )
        self.assertEqual(restored.save_data.auto_recovery, config)
        document.pop("auto_recovery")
        legacy = restore_save_document(
            document,
            character_records=load_mock_character_records(),
            items=self.items,
            skills=self.skills,
        )
        self.assertEqual(legacy.save_data.auto_recovery, AutoRecoveryConfig())
        document["auto_recovery"] = {
            "threshold": 90,
            "method": "items_spells",
            "healer_key": "Fiora",
        }
        ineligible = restore_save_document(
            document,
            character_records=load_mock_character_records(),
            items=self.items,
            skills=self.skills,
        )
        self.assertIsNone(ineligible.save_data.auto_recovery.healer_key)
        document["auto_recovery"] = {"threshold": 65, "method": "spells", "healer_key": None}
        with self.assertRaises(SaveSystemError):
            restore_save_document(
                document,
                character_records=load_mock_character_records(),
                items=self.items,
                skills=self.skills,
            )

    def test_overlay_has_six_faces_without_member_names(self) -> None:
        fonts = Mock()
        fonts.baseline_offset_for.return_value = 0
        overlay = AutoRecoveryOverlay(
            party=self.party,
            spells=self.spells,
            items=self.items,
            inventory=InventorySystem(self.items),
            save_data=SaveData(),
            settings=Settings(),
            texts=self.texts,
            fonts=fonts,
            faces=Mock(),
        )
        self.assertEqual(len(overlay.party_window.texts), 16)
        self.assertEqual(overlay.cursor.selected_key, "execute")
        self.assertEqual(
            [(text.x, text.y) for text in overlay.settings_window.texts if text.text == "："],
            [(30, 2), (30, 5), (30, 8)],
        )
        self.assertEqual(
            [text.x for text in overlay.party_window.texts if "／" in text.text],
            [10, 10, 27, 27, 44, 44, 10, 10, 27, 27, 44, 44],
        )
        self.assertEqual(
            [text.x for text in overlay.party_window.texts if text.text in ("ＨＰ", "ＭＰ")],
            [4, 4, 4, 4],
        )
        self.assertEqual(
            sum(text.text == "ＨＰ" for text in overlay.party_window.texts), 2
        )
        self.assertEqual(
            sum(text.text == "ＭＰ" for text in overlay.party_window.texts), 2
        )
        self.assertEqual(
            (overlay.settings_window.x, overlay.settings_window.y,
             overlay.settings_window.width, overlay.settings_window.height),
            (0, 0, 64, 16),
        )
        self.assertEqual(
            (overlay.guide_window.x, overlay.guide_window.y,
             overlay.guide_window.width, overlay.guide_window.height),
            (0, 16, 64, 10),
        )
        self.assertEqual(
            (overlay.party_window.x, overlay.party_window.y,
             overlay.party_window.width, overlay.party_window.height),
            (0, 26, 64, 34),
        )
        with patch.object(overlay.settings_window, "draw"), patch.object(overlay.guide_window, "draw"), patch.object(overlay.party_window, "draw"):
            with patch("ui.auto_recovery.draw_member_face_at") as draw_face:
                overlay.draw()
        self.assertEqual(
            [(call.kwargs["x"], call.kwargs["y"]) for call in draw_face.call_args_list],
            [(52, 112), (120, 112), (188, 112),
             (52, 176), (120, 176), (188, 176)],
        )

    def test_confirm_on_setting_selects_execute_without_changing_value(self) -> None:
        fonts = Mock()
        fonts.baseline_offset_for.return_value = 0
        save_data = SaveData()
        overlay = AutoRecoveryOverlay(
            party=self.party,
            spells=self.spells,
            items=self.items,
            inventory=InventorySystem(self.items),
            save_data=save_data,
            settings=Settings(),
            texts=self.texts,
            fonts=fonts,
            faces=Mock(),
        )
        original = save_data.auto_recovery
        for key in ("threshold", "method", "healer"):
            with self.subTest(key=key):
                overlay.cursor.select_key(key)
                overlay.update(InputState(confirm=InputButton(True, True)))
                self.assertEqual(overlay.cursor.selected_key, "execute")
                self.assertEqual(save_data.auto_recovery, original)
                self.assertIn("せっていないように", overlay.guide_window.texts[0].text)

        overlay.cursor.select_key("threshold")
        overlay.update(InputState(navigation=Direction.RIGHT))
        self.assertEqual(save_data.auto_recovery.threshold, 70)

    def test_result_shows_only_items_actually_used(self) -> None:
        fonts = Mock()
        fonts.baseline_offset_for.return_value = 0
        overlay = AutoRecoveryOverlay(
            party=self.party[:2],
            spells=self.spells,
            items=self.items,
            inventory=InventorySystem(self.items, {"POTION": 2}),
            save_data=SaveData(),
            settings=Settings(),
            texts=self.texts,
            fonts=fonts,
            faces=Mock(),
        )
        overlay.result = RecoveryResult(actions=1)
        overlay._refresh()
        self.assertEqual(overlay.guide_window.texts, ())
        overlay.result = RecoveryResult(actions=1, items_used={"POTION": 1})
        overlay._refresh()
        self.assertEqual(len(overlay.guide_window.texts), 1)
        self.assertIn("きずぐすり", overlay.guide_window.texts[0].text)
        overlay._start_proficiency_animation()
        self.assertEqual(overlay.proficiency_windows, {})

    def test_item_usage_message_matches_da2_in_all_languages(self) -> None:
        expected = {
            Language.JAPANESE: "きずぐすりを　１こ　つかった（のこり　２こ）",
            Language.ENGLISH: "１　ＰＯＴＩＯＮｓ　ｕｓｅｄ（２　ｌｅｆｔ）",
            Language.SIMPLIFIED_CHINESE: "使用了1个POTION（剩余2个）",
        }
        for language, message in expected.items():
            with self.subTest(language=language):
                fonts = Mock()
                fonts.baseline_offset_for.return_value = 0
                overlay = AutoRecoveryOverlay(
                    party=self.party[:2],
                    spells=self.spells,
                    items=self.items,
                    inventory=InventorySystem(self.items, {"POTION": 2}),
                    save_data=SaveData(),
                    settings=Settings(language=language),
                    texts=self.texts,
                    fonts=fonts,
                    faces=Mock(),
                )
                overlay.result = RecoveryResult(actions=1, items_used={"POTION": 1})
                overlay._refresh()
                self.assertEqual(overlay.guide_window.texts[0].text, message)

    def test_overlay_omits_empty_second_row_labels(self) -> None:
        fonts = Mock()
        fonts.baseline_offset_for.return_value = 0
        overlay = AutoRecoveryOverlay(
            party=self.party[:2],
            spells=self.spells,
            items=self.items,
            inventory=InventorySystem(self.items),
            save_data=SaveData(),
            settings=Settings(),
            texts=self.texts,
            fonts=fonts,
            faces=Mock(),
        )
        self.assertEqual(len(overlay.party_window.texts), 6)
        self.assertEqual(
            [text.text for text in overlay.party_window.texts[:2]], ["ＨＰ", "ＭＰ"]
        )
        self.assertEqual(
            [text.x for text in overlay.party_window.texts if text.text in ("ＨＰ", "ＭＰ")],
            [12, 12],
        )
        self.assertEqual(
            [text.x for text in overlay.party_window.texts if "／" in text.text],
            [18, 18, 35, 35],
        )
        with patch.object(overlay.settings_window, "draw"), patch.object(overlay.guide_window, "draw"), patch.object(overlay.party_window, "draw"):
            with patch("ui.auto_recovery.draw_member_face_at") as draw_face:
                overlay.draw()
        self.assertEqual(
            [(call.kwargs["x"], call.kwargs["y"]) for call in draw_face.call_args_list],
            [(84, 112), (152, 112)],
        )

    def test_overlay_colors_only_changed_current_hp_and_mp(self) -> None:
        fonts = Mock()
        fonts.baseline_offset_for.return_value = 0
        overlay = AutoRecoveryOverlay(
            party=self.party[:2],
            spells=self.spells,
            items=self.items,
            inventory=InventorySystem(self.items),
            save_data=SaveData(),
            settings=Settings(),
            texts=self.texts,
            fonts=fonts,
            faces=Mock(),
        )
        overlay.result = RecoveryResult(actions=1, hp_recovered={0}, mp_spent={1})
        overlay._refresh()
        values = [text.text for text in overlay.party_window.texts if "／" in text.text]
        self.assertIn("%COL_POSITIVE%", values[0])
        self.assertIn("%COL_BLUE%", values[3])
        self.assertTrue(values[0].split("／")[0].endswith("%COL_END%"))
        self.assertTrue(values[3].split("／")[0].endswith("%COL_END%"))
        self.assertNotIn("%COL_", values[1] + values[2])
        overlay.result = None
        overlay._refresh()
        self.assertFalse(any("%COL_" in text.text for text in overlay.party_window.texts))

    @patch("ui.auto_recovery.play_se")
    def test_spell_recovery_animates_proficiency_above_caster_hp(
        self, play_se: Mock
    ) -> None:
        self.party[0].hp = 1
        healer = self.party[1]
        fonts = Mock()
        fonts.baseline_offset_for.return_value = 0
        overlay = AutoRecoveryOverlay(
            party=self.party[:2],
            spells=self.spells,
            items=self.items,
            inventory=InventorySystem(self.items),
            save_data=SaveData(
                auto_recovery=AutoRecoveryConfig(
                    100, AutoRecoveryMethod.SPELLS, healer.definition.key
                )
            ),
            settings=Settings(),
            texts=self.texts,
            fonts=fonts,
            faces=Mock(),
        )
        overlay.settings_window.open_immediately()
        overlay.update(InputState(confirm=InputButton(True, True)))
        self.assertIsNotNone(overlay.result)
        growth = overlay.result.proficiency_growths[1]
        window = overlay.proficiency_windows[1]
        self.assertEqual((window.x, window.y, window.width, window.height), (35, 29, 14, 7))
        self.assertEqual(
            window.texts[0].text,
            spell_proficiency_text(SpellType.SACRED, growth.before_total),
        )
        self.assertFalse(overlay.update(InputState(cancel=InputButton(True, True))))
        for _frame in range(PROFICIENCY_ANIMATION_FRAME_COUNT - 1):
            overlay.update(InputState())
        self.assertEqual(
            window.texts[0].text,
            spell_proficiency_text(SpellType.SACRED, growth.after_total),
        )
        overlay.update(InputState())
        self.assertIn(1, overlay.proficiency_windows)
        overlay.update(InputState(navigation=Direction.UP))
        self.assertEqual(overlay.proficiency_windows, {})
        self.assertIsNone(overlay.result)
        play_se.assert_called_once_with("spell_healing1")

    def test_proficiency_windows_follow_casters_in_both_rows(self) -> None:
        fonts = Mock()
        fonts.baseline_offset_for.return_value = 0
        overlay = AutoRecoveryOverlay(
            party=self.party,
            spells=self.spells,
            items=self.items,
            inventory=InventorySystem(self.items),
            save_data=SaveData(),
            settings=Settings(),
            texts=self.texts,
            fonts=fonts,
            faces=Mock(),
        )
        overlay.result = RecoveryResult(
            actions=2,
            proficiency_growths={
                1: MenuSpellProficiencyGrowth(ProficiencyKind.SACRED, 184, 187),
                5: MenuSpellProficiencyGrowth(ProficiencyKind.SACRED, 196, 201),
            },
        )
        overlay._start_proficiency_animation()
        self.assertEqual(
            [(window.x, window.y) for window in overlay.proficiency_windows.values()],
            [(27, 29), (44, 45)],
        )
        self.assertEqual(
            [window.texts[0].text for window in overlay.proficiency_windows.values()],
            ["%SACRED%１－８４", "%SACRED%１－９６"],
        )

    def test_level_growth_stays_green_and_announces_new_spell(self) -> None:
        level_up_jingle = Mock()
        overlay = AutoRecoveryOverlay(
            party=self.party,
            spells=self.spells,
            items=self.items,
            inventory=InventorySystem(self.items),
            save_data=SaveData(),
            settings=Settings(),
            texts=self.texts,
            fonts=FontResources(),
            faces=Mock(),
            on_spell_level_up=level_up_jingle,
        )
        overlay.result = RecoveryResult(
            actions=1,
            proficiency_growths={
                1: MenuSpellProficiencyGrowth(ProficiencyKind.SACRED, 196, 201)
            },
        )
        overlay._start_proficiency_animation()
        for _frame in range(PROFICIENCY_ANIMATION_FRAME_COUNT + 1):
            overlay.update(InputState())
        self.assertIn(
            "%COL_POSITIVE%２%COL_END%",
            overlay.proficiency_windows[1].texts[0].text,
        )
        self.assertIsNotNone(overlay.spell_learned_popup)
        self.assertEqual(overlay.spell_learned_popup.window.y, 18)
        level_up_jingle.assert_called_once_with()
        confirm = InputState(confirm=InputButton(True, True))
        self.assertFalse(overlay.update(confirm))
        self.assertIsNone(overlay.spell_learned_popup)
        self.assertIn(1, overlay.proficiency_windows)
        level_up_jingle.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
