from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.audio_catalog import SoundEffectDefinition
from app.spell_effect import SpellEffectDefinition
from app.resources import AudioResourceError
from tools.spell_effect_editor.app import SoundRegistrationDraft, SpellEffectEditor
from tools.spell_effect_editor.model import EditorSpell


class SpellEffectEditorUiTest(unittest.TestCase):
    def sound_editor(self, *, se_id: str | None = "spell_fire1") -> SpellEffectEditor:
        editor = SpellEffectEditor.__new__(SpellEffectEditor)
        definitions = {
            "FIRE1": SpellEffectDefinition.from_record(
                "FIRE1",
                {
                    "kind": "target_sprite",
                    "image_id": "effects/spells32",
                    "row": 0,
                    "frame_count": 1,
                    "frames_per_pattern": 4,
                    "offset": {"ally": [0, 0], "enemy": [0, 0]},
                    "flash_color": None,
                    "se_id": se_id,
                },
            ),
        }
        sounds = {
            "spell_fire1": SoundEffectDefinition.from_record("spell_fire1", {"wav": "fire1.wav"}),
            "spell_healing1": SoundEffectDefinition.from_record("spell_healing1", {"sound": 31}),
        }

        def save_sound(key: str, **record: object) -> None:
            sounds[key] = SoundEffectDefinition.from_record(key, record)

        editor.store = SimpleNamespace(
            spells=(EditorSpell("FIRE1", "ファイア", "mystic", True),),
            preview_definition=lambda key: definitions[key],
            definition=lambda key: definitions.get(key),
            set_definition=lambda definition: definitions.__setitem__(definition.spell_key, definition),
            sound_effects=sounds,
            sound_effect=lambda key: sounds[key],
            available_wavs=("Healing1.wav", "fire1.wav"),
            update_sound_effect=Mock(side_effect=save_sound),
            register_sound_effect=Mock(side_effect=save_sound),
            dirty=False,
        )
        editor.filter_index = 0
        editor.selected_spell_index = 0
        editor.target_side = "enemy"
        editor.debug_visible = False
        editor.playing = False
        editor.paused = False
        editor.looping = False
        editor.exit_confirmation = False
        editor.flash_picker_open = False
        editor.sound_registration = None
        editor.se_player = Mock()
        editor._refresh_player = Mock()
        editor._set_status = Mock()
        return editor

    def test_clicking_sound_name_opens_current_source_without_obsolete_buttons(self) -> None:
        editor = self.sound_editor()
        buttons = {button.id: button for button in editor._buttons()}
        self.assertTrue({"se_prev", "se_next", "test_se", "new_se"}.isdisjoint(buttons))
        button = buttons["se_select"]
        self.assertEqual(button.label, "spell_fire1")
        with patch("tools.spell_effect_editor.app.pyxel", SimpleNamespace(
            mouse_wheel=0, mouse_x=button.x + 2, mouse_y=button.y + 2,
            MOUSE_BUTTON_LEFT=1, btnp=lambda key: True, quit=Mock(),
        )):
            editor._handle_mouse()

        self.assertEqual(editor.sound_registration.se_id, "spell_fire1")
        self.assertEqual(editor.sound_registration.original_se_id, "spell_fire1")
        self.assertTrue(editor.sound_registration.use_wav)
        self.assertEqual(editor.sound_registration.wav_index, 1)
        editor._activate("sound_preview")
        self.assertEqual(editor.se_player.play.call_args.args[0].wav, "fire1.wav")

    def test_applies_new_source_to_current_key_and_can_reopen_it(self) -> None:
        editor = self.sound_editor()
        editor._activate("se_select")
        editor._change_sound_registration_source()
        editor.sound_registration.sound = 17
        editor._activate("sound_register")

        editor.store.update_sound_effect.assert_called_once_with("spell_fire1", sound=17)
        editor.store.register_sound_effect.assert_not_called()
        self.assertIsNone(editor.sound_registration)
        self.assertEqual(editor.definition.se_id, "spell_fire1")
        editor._activate("se_select")
        self.assertFalse(editor.sound_registration.use_wav)
        self.assertEqual(editor.sound_registration.sound, 17)

    def test_clicking_none_registers_new_key_and_none_clears_only_spell_reference(self) -> None:
        editor = self.sound_editor(se_id=None)
        button = next(button for button in editor._buttons() if button.id == "se_select")
        self.assertEqual(button.label, "NONE")
        editor._activate("se_select")
        self.assertEqual(editor.sound_registration.se_id, "spell_fire1_2")
        self.assertIsNone(editor.sound_registration.original_se_id)
        editor.sound_registration.sound = 17
        editor._activate("sound_register")
        editor.store.register_sound_effect.assert_called_once_with("spell_fire1_2", sound=17)
        self.assertEqual(editor.definition.se_id, "spell_fire1_2")
        editor._activate("se_select")
        editor._activate("sound_none")
        self.assertIsNone(editor.definition.se_id)
        self.assertIsNone(editor.sound_registration)
        self.assertIn("spell_fire1_2", editor.store.sound_effects)

    def test_cancel_discards_sound_draft_and_modal_prevents_spell_wheel_selection(self) -> None:
        editor = self.sound_editor()
        editor._activate("se_select")
        editor.sound_registration.wav_index = 0
        editor._select_spell = Mock()
        with patch("tools.spell_effect_editor.app.pyxel", SimpleNamespace(
            mouse_wheel=1, mouse_x=300, mouse_y=50,
            MOUSE_BUTTON_LEFT=1, btnp=lambda key: False,
        )):
            editor._handle_mouse()
        editor._select_spell.assert_not_called()
        editor._activate("sound_cancel")
        self.assertIsNone(editor.sound_registration)
        self.assertEqual(editor.store.sound_effect("spell_fire1").wav, "fire1.wav")
        editor.store.update_sound_effect.assert_not_called()

    def test_save_reports_decode_errors_before_writing(self) -> None:
        editor = SpellEffectEditor.__new__(SpellEffectEditor)
        editor.store = Mock()
        editor.se_player = Mock()
        editor.se_player.preload.side_effect = AudioResourceError("invalid WAV")
        editor._set_status = Mock()

        self.assertFalse(editor._save())

        editor.store.save.assert_not_called()
        self.assertEqual(editor._set_status.call_args.args[0], "invalid WAV")

    def test_registration_switches_sources_selects_wav_and_uses_shared_player(self) -> None:
        editor = SpellEffectEditor.__new__(SpellEffectEditor)
        editor.store = SimpleNamespace(available_wavs=("Healing1.wav", "fire1.wav"))
        editor.se_player = Mock()
        editor.sound_registration = SoundRegistrationDraft("spell_fire1", sound=31)

        editor._preview_sound_registration()
        self.assertEqual(editor.se_player.play.call_args.args[0].sound, 31)
        editor._change_sound_registration_source()
        editor._change_sound_registration_number(1)
        editor._preview_sound_registration()
        self.assertEqual(editor.se_player.play.call_args.args[0].wav, "fire1.wav")
        editor._change_sound_registration_source()
        editor._preview_sound_registration()
        self.assertEqual(editor.se_player.play.call_args.args[0].sound, 31)

    def test_flash_picker_groups_dark_to_bright_colors_in_rows(self) -> None:
        editor = SpellEffectEditor.__new__(SpellEffectEditor)
        editor.store = SimpleNamespace(
            catalogs=SimpleNamespace(
                palette_color_count=62,
                transparent_index=1,
            )
        )

        swatches = {swatch.color: swatch for swatch in editor._flash_color_swatches()}

        self.assertEqual(set(swatches), {0, *range(2, 62)})
        self.assertNotIn(1, swatches)
        self.assertEqual((swatches[0].x, swatches[0].y), (142, 76))
        self.assertEqual(swatches[2].y, swatches[5].y)
        self.assertEqual(swatches[5].x - swatches[2].x, 36)
        self.assertEqual(swatches[6].y - swatches[2].y, 14)
        self.assertEqual(swatches[34].x - swatches[2].x, 158)
        self.assertEqual(swatches[34].y, swatches[2].y)

    def test_offset_buttons_change_only_the_selected_target_side(self) -> None:
        editor = SpellEffectEditor.__new__(SpellEffectEditor)
        current = SpellEffectDefinition.from_record(
            "FIRE1",
            {
                "kind": "target_sprite",
                "image_id": "effects/spells32",
                "row": 0,
                "frame_count": 1,
                "frames_per_pattern": 4,
                "offset": {"ally": [2, -3], "enemy": [8, 9]},
                "flash_color": None,
                "se_id": None,
            },
        )
        definitions = {"FIRE1": current}
        editor.store = SimpleNamespace(
            spells=(EditorSpell("FIRE1", "ファイア", "mystic", True),),
            preview_definition=lambda key: definitions[key],
            definition=lambda key: definitions.get(key),
            set_definition=lambda definition: definitions.__setitem__(
                definition.spell_key, definition
            ),
        )
        editor.filter_index = 0
        editor.selected_spell_index = 0
        editor.target_side = "ally"
        editor._refresh_player = lambda **kwargs: None

        editor._change_offset("x", 1)
        editor._change_offset("y", -1)

        self.assertEqual(definitions["FIRE1"].offset_for("ally"), (3, -4))
        self.assertEqual(definitions["FIRE1"].offset_for("enemy"), (8, 9))


if __name__ == "__main__":
    unittest.main()
