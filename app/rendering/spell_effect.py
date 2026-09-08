"""Render ordinary target-centered spell effects with scoped palette flashes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pyxel

if __package__ == "rendering":
    from resources.images import TRANSPARENT_INDEX, ImageResources
    from spell_effect import SpellEffectPlayer
    from rendering.palette import PaletteShifter
else:
    from ..resources.images import TRANSPARENT_INDEX, ImageResources
    from ..spell_effect import SpellEffectPlayer
    from .palette import PaletteShifter


SPELL_EFFECT_FLASH_PALETTE = "spell_effect_flash"


class SpellEffectRenderer:
    """Draw one shared playback state using production image resources."""

    def __init__(
        self,
        images: ImageResources,
        palette_shifter: PaletteShifter,
        *,
        pyxel_api: Any = pyxel,
    ) -> None:
        if not isinstance(images, ImageResources):
            raise TypeError("images must be ImageResources")
        if not isinstance(palette_shifter, PaletteShifter):
            raise TypeError("palette_shifter must be PaletteShifter")
        self._images = images
        self._palette_shifter = palette_shifter
        self._pyxel = pyxel_api
        self._flash_prepared = False

    def prepare(self, player: SpellEffectPlayer) -> None:
        """Update the reusable flash palette during the owner's update phase."""

        if not isinstance(player, SpellEffectPlayer):
            raise TypeError("player must be SpellEffectPlayer")
        color_index = player.definition.flash_color
        self._flash_prepared = color_index is not None and not player.completed
        if not self._flash_prepared:
            return
        if color_index < 0 or color_index >= len(self._palette_shifter.base_colors):
            raise ValueError(f"flash color is outside the base palette: {color_index}")
        self._palette_shifter.define_mix(
            SPELL_EFFECT_FLASH_PALETTE,
            base_rate=player.flash_base_rate,
            target_color=self._palette_shifter.base_colors[color_index],
        )

    def draw_target(
        self,
        player: SpellEffectPlayer,
        draw_target: Callable[[], None],
    ) -> None:
        """Draw only the target through the currently prepared flash palette."""

        if not isinstance(player, SpellEffectPlayer):
            raise TypeError("player must be SpellEffectPlayer")
        if not callable(draw_target):
            raise TypeError("draw_target must be callable")
        if not self._flash_prepared or player.completed:
            draw_target()
            return
        with self._palette_shifter.shifted(SPELL_EFFECT_FLASH_PALETTE):
            draw_target()

    def destination_rect(
        self,
        player: SpellEffectPlayer,
    ) -> tuple[int, int, int, int] | None:
        if player.completed or player.source_position is None:
            return None
        size = player.definition.cell_size
        center_x, center_y = player.center
        return center_x - size // 2, center_y - size // 2, size, size

    def draw_effect(self, player: SpellEffectPlayer) -> None:
        """Draw the current pattern over the target without advancing time."""

        source = player.source_position
        destination = self.destination_rect(player)
        if source is None or destination is None:
            return
        source_x, source_y = source
        x, y, width, height = destination
        self._pyxel.blt(
            x,
            y,
            self._images.image(player.definition.image_id),
            source_x,
            source_y,
            width,
            height,
            TRANSPARENT_INDEX,
        )


__all__ = ["SPELL_EFFECT_FLASH_PALETTE", "SpellEffectRenderer"]
