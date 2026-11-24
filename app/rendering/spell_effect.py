"""Render spell sprites, target flashes, and whole-screen color effects."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pyxel

if __package__ == "rendering":
    from resources.images import TRANSPARENT_INDEX, ImageResources
    from spell_effect import (
        BLOOD_SUCK_EFFECT_KIND, DRAIN_FLIGHT_FRAMES_PER_PATTERN, DRAIN_FLIGHT_PATTERNS,
        FLASH_SCOPE_TARGET, SpellEffectPlayer, SpellScreenFlash,
    )
    from rendering.palette import PaletteShifter
else:
    from ..resources.images import TRANSPARENT_INDEX, ImageResources
    from ..spell_effect import (
        BLOOD_SUCK_EFFECT_KIND, DRAIN_FLIGHT_FRAMES_PER_PATTERN, DRAIN_FLIGHT_PATTERNS,
        FLASH_SCOPE_TARGET, SpellEffectPlayer, SpellScreenFlash,
    )
    from .palette import PaletteShifter


SPELL_EFFECT_FLASH_PALETTE = "spell_effect_flash"


def draw_drain_flight(
    start: tuple[int, int], end: tuple[int, int], elapsed_frame: int, *, pyxel_api: Any = pyxel,
) -> None:
    """Draw the travelling orb shared by physical and spell drains."""

    step = elapsed_frame // DRAIN_FLIGHT_FRAMES_PER_PATTERN
    if step >= len(DRAIN_FLIGHT_PATTERNS):
        return
    rate = step / (len(DRAIN_FLIGHT_PATTERNS) - 1)
    x = start[0] + (end[0] - start[0]) * rate
    y = start[1] + (end[1] - start[1]) * rate
    pyxel_api.blt(x - 12, y - 8, 0, DRAIN_FLIGHT_PATTERNS[step] * 24, 48, 24, 16, TRANSPARENT_INDEX)


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
        self._preview_flash_prepared = False

    def prepare(self, player: SpellEffectPlayer, *, preview: bool = False) -> None:
        """Update the reusable flash palette during the owner's update phase."""

        if not isinstance(player, SpellEffectPlayer):
            raise TypeError("player must be SpellEffectPlayer")
        color_index = player.definition.flash_color
        self._flash_prepared = (
            player.definition.flash_scope == FLASH_SCOPE_TARGET
            and color_index is not None and not player.completed
        )
        screen_flash = player.screen_flash if preview else None
        base_rate = (
            screen_flash.base_rate_at(player.elapsed_frame)
            if screen_flash is not None else player.flash_base_rate
        )
        self._preview_flash_prepared = screen_flash is not None and base_rate < 1.0
        if not (self._flash_prepared or self._preview_flash_prepared):
            return
        self._palette_shifter.define_mix(
            SPELL_EFFECT_FLASH_PALETTE, base_rate=base_rate,
            target_color=self._flash_rgb(color_index),
        )

    def _flash_rgb(self, color_index: int) -> int:
        if not 0 <= color_index < len(self._palette_shifter.base_colors):
            raise ValueError(f"flash color is outside the base palette: {color_index}")
        return self._palette_shifter.base_colors[color_index]

    def prepare_screen_flash(self, flash: SpellScreenFlash | None, elapsed_frame: int) -> None:
        """Update the battle palette, including HUD and all local color variants."""

        if flash is None:
            self._palette_shifter.set_screen_flash()
            return
        self._palette_shifter.set_screen_flash(
            base_rate=flash.base_rate_at(elapsed_frame),
            target_color=self._flash_rgb(flash.color_index),
        )

    def draw_preview(self, draw_preview: Callable[[], None]) -> None:
        """Confine screen tint to the simulated battle in the editor."""

        if self._preview_flash_prepared:
            with self._palette_shifter.shifted(SPELL_EFFECT_FLASH_PALETTE):
                draw_preview()
        else:
            draw_preview()

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

        if player.definition.kind == BLOOD_SUCK_EFFECT_KIND:
            if not player.completed and player.caster_anchor is not None:
                draw_drain_flight(
                    (player.anchor_x, player.anchor_y), player.caster_anchor,
                    player.elapsed_frame, pyxel_api=self._pyxel,
                )
            return
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


__all__ = ["SPELL_EFFECT_FLASH_PALETTE", "SpellEffectRenderer", "draw_drain_flight"]
