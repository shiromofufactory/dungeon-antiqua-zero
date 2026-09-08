from __future__ import annotations

from unittest.mock import Mock, call
import unittest

from app.rendering.palette import PaletteShifter
from app.rendering.spell_effect import (
    SPELL_EFFECT_FLASH_PALETTE,
    SpellEffectRenderer,
)
from app.resources.images import ImageResources
from app.spell_effect import SpellEffectDefinition, SpellEffectPlayer


class SpellEffectRendererTest(unittest.TestCase):
    def setUp(self) -> None:
        record = {
            "kind": "target_sprite",
            "image_id": "effects/spells32",
            "row": 2,
            "frame_count": 2,
            "frames_per_pattern": 4,
            "offset": {"ally": [2, -3], "enemy": [2, -3]},
            "flash_color": 2,
            "se_id": None,
        }
        self.player = SpellEffectPlayer(
            SpellEffectDefinition.from_record("FIRE1", record),
            anchor_x=100,
            anchor_y=80,
        )
        self.remap = Mock()
        self.shifter = PaletteShifter(
            [0x000000, 0xFF0080, 0xFFFFFF], self.remap
        )
        self.images = ImageResources.__new__(ImageResources)
        self.effect_image = object()
        self.images.image = Mock(return_value=self.effect_image)  # type: ignore[method-assign]
        self.pyxel = Mock()
        self.renderer = SpellEffectRenderer(
            self.images, self.shifter, pyxel_api=self.pyxel
        )

    def test_prepares_scoped_flash_and_draws_only_target_through_it(self) -> None:
        draw_target = Mock()

        self.renderer.prepare(self.player)
        self.renderer.draw_target(self.player, draw_target)

        draw_target.assert_called_once_with()
        self.assertEqual(
            self.remap.call_args_list,
            [call(0, 3), call(1, 4), call(2, 5), call()],
        )
        self.assertIn(SPELL_EFFECT_FLASH_PALETTE, self.shifter._variants)

    def test_draws_current_source_pattern_centered_on_adjusted_anchor(self) -> None:
        for _ in range(4):
            self.player.update()

        self.renderer.draw_effect(self.player)

        self.pyxel.blt.assert_called_once_with(
            86,
            61,
            self.effect_image,
            32,
            64,
            32,
            32,
            1,
        )

    def test_completed_effect_draws_target_normally_and_no_sprite(self) -> None:
        for _ in range(self.player.definition.total_frames):
            self.player.update()
        draw_target = Mock()

        self.renderer.prepare(self.player)
        self.renderer.draw_target(self.player, draw_target)
        self.renderer.draw_effect(self.player)

        draw_target.assert_called_once_with()
        self.remap.assert_not_called()
        self.pyxel.blt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
