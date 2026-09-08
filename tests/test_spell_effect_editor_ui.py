from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.spell_effect import SpellEffectDefinition
from tools.spell_effect_editor.app import SpellEffectEditor
from tools.spell_effect_editor.model import EditorSpell


class SpellEffectEditorUiTest(unittest.TestCase):
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
