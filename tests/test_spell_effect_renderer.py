from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock, call
import unittest

from app.rendering.palette import PaletteShifter, mix_color
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
        self.colors = [0x000000, 0xFF0080, 0xFFFFFF]
        self.shifter = PaletteShifter(self.colors, self.remap)
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

    def test_blood_suck_draws_flight_during_target_flash_without_sheet(self) -> None:
        player = SpellEffectPlayer(
            SpellEffectDefinition.from_record("BLOOD SUCK", {
                "kind": "blood_suck", "flash_color": 2, "se_id": "spell_blood_suck",
            }),
            anchor_x=100, anchor_y=80, caster_anchor=(150, 100),
        )
        self.renderer.draw_effect(player)
        self.pyxel.blt.assert_called_once_with(88, 72, 0, 0, 48, 24, 16, 1)
        for _ in range(6):
            player.update()
        self.renderer.prepare(player)
        draw_target = Mock()
        self.renderer.draw_target(player, draw_target)
        self.renderer.draw_effect(player)

        self.assertLess(player.flash_base_rate, 1.0)
        draw_target.assert_called_once_with()
        self.assertEqual(self.remap.call_args_list, [call(0, 3), call(1, 4), call(2, 5), call()])
        self.pyxel.blt.assert_called_with(118, 84, 0, 48, 48, 24, 16, 1)
        self.images.image.assert_not_called()

        for _ in range(6):
            player.update()
        self.renderer.draw_effect(player)
        self.assertEqual(self.pyxel.blt.call_count, 2)

    def test_screen_flash_composes_with_fade_and_local_variants_then_restores(self) -> None:
        player = SpellEffectPlayer(
            replace(self.player.definition, flash_scope="screen"), anchor_x=100, anchor_y=80
        )
        self.shifter.define_variant("dimmed", [0, 0x7F0040, 0x7F7F7F])
        self.shifter.set_global_mix(base_rate=0.5, target_color=0)
        self.shifter.set_brightness(0.5)
        original = self.colors.copy()
        self.renderer.prepare_screen_flash(player.screen_flash, 8)
        tinted = mix_color(0, 0.7, 0xFFFFFF)
        self.assertEqual(self.colors[0], mix_color(mix_color(tinted, 0.5, 0), 0.5, 0))
        self.assertEqual(self.colors[3], self.colors[0])
        self.assertNotEqual(self.colors, original)
        self.renderer.prepare_screen_flash(player.screen_flash, player.playback_frames)
        self.assertEqual(self.colors, original)
        self.remap.assert_not_called()

    def test_screen_preview_scopes_palette_to_preview_without_local_target_remap(self) -> None:
        player = SpellEffectPlayer(
            replace(self.player.definition, flash_scope="screen"), anchor_x=100, anchor_y=80
        )
        for _ in range(8):
            player.update()
        target = Mock()
        self.renderer.prepare(player, preview=True)
        self.renderer.draw_preview(lambda: self.renderer.draw_target(player, target))
        target.assert_called_once_with()
        self.assertEqual(
            self.remap.call_args_list, [call(0, 3), call(1, 4), call(2, 5), call()]
        )
        self.assertEqual(self.colors[:3], [0x000000, 0xFF0080, 0xFFFFFF])


if __name__ == "__main__":
    unittest.main()
