"""Scoped palette-number shifts for reusable drawing effects."""

from __future__ import annotations

from collections.abc import Callable, Iterator, MutableSequence, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

import pyxel


MIN_COLOR = 0x000000
MAX_COLOR = 0xFFFFFF
DIMMED_PALETTE = "dimmed"
DIMMED_BASE_RATE = 0.5
DIMMED_TARGET_COLOR = 0x000000


def _validate_color(color: object, label: str) -> int:
    if isinstance(color, bool) or not isinstance(color, int):
        raise TypeError(f"{label} must be an integer RGB color")
    if not MIN_COLOR <= color <= MAX_COLOR:
        raise ValueError(f"{label} must be from 0x000000 to 0xFFFFFF")
    return color


def mix_color(base_color: int, base_rate: float, target_color: int) -> int:
    """Mix one packed RGB color toward another using the DA2 formula."""

    base_color = _validate_color(base_color, "base_color")
    target_color = _validate_color(target_color, "target_color")
    if isinstance(base_rate, bool) or not isinstance(base_rate, (int, float)):
        raise TypeError("base_rate must be a number")
    if not 0.0 <= base_rate <= 1.0:
        raise ValueError("base_rate must be from 0.0 to 1.0")

    base_red = (base_color >> 16) & 0xFF
    base_green = (base_color >> 8) & 0xFF
    base_blue = base_color & 0xFF
    target_red = (target_color >> 16) & 0xFF
    target_green = (target_color >> 8) & 0xFF
    target_blue = target_color & 0xFF
    red = int(base_red * base_rate + target_red * (1.0 - base_rate))
    green = int(base_green * base_rate + target_green * (1.0 - base_rate))
    blue = int(base_blue * base_rate + target_blue * (1.0 - base_rate))
    return (red << 16) | (green << 8) | blue


@dataclass(frozen=True)
class _PaletteVariant:
    offset: int


class PaletteShifter:
    """Own extra palette blocks and apply them only around target drawing.

    Create one instance after loading the production palette, then inject it
    into renderers that need palette effects. Domain models never retain this
    Pyxel-specific service.
    """

    def __init__(
        self,
        colors: MutableSequence[int] | None = None,
        remap: Callable[..., None] | None = None,
    ) -> None:
        self._colors = pyxel.colors if colors is None else colors
        self._remap = pyxel.pal if remap is None else remap
        self._base_colors = tuple(self._colors)
        if not self._base_colors:
            raise ValueError("palette must contain at least one color")
        for index, color in enumerate(self._base_colors):
            _validate_color(color, f"colors[{index}]")
        self._variants: dict[str, _PaletteVariant] = {}

    @property
    def base_colors(self) -> tuple[int, ...]:
        return self._base_colors

    def define_variant(self, name: str, colors: Sequence[int]) -> None:
        """Add or replace one destination block for a named effect."""

        if not isinstance(name, str) or not name:
            raise ValueError("palette variant name must be a non-empty string")
        variant_colors = tuple(colors)
        if len(variant_colors) != len(self._base_colors):
            raise ValueError("palette variant must match the base palette size")
        for index, color in enumerate(variant_colors):
            _validate_color(color, f"variant colors[{index}]")

        variant = self._variants.get(name)
        if variant is None:
            variant = _PaletteVariant(offset=len(self._colors))
            self._variants[name] = variant
            self._colors[:] = [*self._colors, *variant_colors]
            return
        start = variant.offset
        end = start + len(self._base_colors)
        self._colors[start:end] = list(variant_colors)

    def define_mix(
        self,
        name: str,
        *,
        base_rate: float,
        target_color: int,
    ) -> None:
        """Define a variant by mixing every base color toward one RGB color."""

        self.define_variant(
            name,
            tuple(
                mix_color(color, base_rate, target_color)
                for color in self._base_colors
            ),
        )

    @contextmanager
    def shifted(self, name: str) -> Iterator[None]:
        """Temporarily remap base indices to one destination palette block."""

        try:
            variant = self._variants[name]
        except KeyError as error:
            raise KeyError(f"palette variant is not defined: {name}") from error

        try:
            for source in range(len(self._base_colors)):
                self._remap(source, variant.offset + source)
            yield
        finally:
            self._remap()


def create_default_palette_shifter() -> PaletteShifter:
    """Create the shared production variants from the loaded base palette."""

    shifter = PaletteShifter()
    shifter.define_mix(
        DIMMED_PALETTE,
        base_rate=DIMMED_BASE_RATE,
        target_color=DIMMED_TARGET_COLOR,
    )
    return shifter
