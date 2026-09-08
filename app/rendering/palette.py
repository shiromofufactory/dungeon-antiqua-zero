"""Scoped palette-number shifts for reusable drawing effects."""

from __future__ import annotations

from collections.abc import Callable, Iterator, MutableSequence, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

import pyxel


MIN_COLOR = 0x000000
MAX_COLOR = 0xFFFFFF
MAX_PALETTE_COLOR_COUNT = 256
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
    colors: tuple[int, ...]


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
        if len(self._base_colors) > MAX_PALETTE_COLOR_COUNT:
            raise ValueError(
                f"palette cannot contain more than {MAX_PALETTE_COLOR_COUNT} colors"
            )
        for index, color in enumerate(self._base_colors):
            _validate_color(color, f"colors[{index}]")
        self._variants: dict[str, _PaletteVariant] = {}
        self._global_base_rate = 1.0
        self._global_target_color = MIN_COLOR

    @property
    def base_colors(self) -> tuple[int, ...]:
        return self._base_colors

    @property
    def global_base_rate(self) -> float:
        return self._global_base_rate

    def _globally_mixed(self, colors: Sequence[int]) -> tuple[int, ...]:
        if self._global_base_rate == 1.0:
            return tuple(colors)
        return tuple(
            mix_color(
                color,
                self._global_base_rate,
                self._global_target_color,
            )
            for color in colors
        )

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
            if len(self._colors) + len(variant_colors) > MAX_PALETTE_COLOR_COUNT:
                raise ValueError(
                    "palette variants exceed Pyxel's 0-255 color-number range"
                )
            variant = _PaletteVariant(
                offset=len(self._colors),
                colors=variant_colors,
            )
            self._variants[name] = variant
            self._colors[:] = [
                *self._colors,
                *self._globally_mixed(variant_colors),
            ]
            return
        variant = _PaletteVariant(
            offset=variant.offset,
            colors=variant_colors,
        )
        self._variants[name] = variant
        start = variant.offset
        end = start + len(self._base_colors)
        self._colors[start:end] = list(self._globally_mixed(variant_colors))

    def remove_variant(self, name: str) -> bool:
        """Release one named destination block and compact later blocks.

        Temporary scene effects should release variants after their presentation
        so another mutually exclusive effect can reuse Pyxel's finite 0-255
        color-number range.
        """

        if not isinstance(name, str) or not name:
            raise ValueError("palette variant name must be a non-empty string")
        variant = self._variants.pop(name, None)
        if variant is None:
            return False
        start = variant.offset
        end = start + len(self._base_colors)
        self._colors[:] = [*self._colors[:start], *self._colors[end:]]
        for other_name, other in tuple(self._variants.items()):
            if other.offset > start:
                self._variants[other_name] = _PaletteVariant(
                    offset=other.offset - len(self._base_colors),
                    colors=other.colors,
                )
        return True

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

    def set_global_mix(
        self,
        *,
        base_rate: float,
        target_color: int,
    ) -> None:
        """Mix every registered palette block for a whole-screen effect.

        Unlike ``shifted()``, this does not change color-number remapping. It
        therefore composes with scoped variants such as a dimmed character.
        The immutable source colors are always used, so repeated calls do not
        accumulate rounding errors.
        """

        if isinstance(base_rate, bool) or not isinstance(
            base_rate,
            (int, float),
        ):
            raise TypeError("base_rate must be a number")
        if not 0.0 <= base_rate <= 1.0:
            raise ValueError("base_rate must be from 0.0 to 1.0")
        target_color = _validate_color(target_color, "target_color")
        self._global_base_rate = float(base_rate)
        self._global_target_color = target_color

        base_count = len(self._base_colors)
        self._colors[:base_count] = list(self._globally_mixed(self._base_colors))
        for variant in self._variants.values():
            start = variant.offset
            end = start + base_count
            self._colors[start:end] = list(self._globally_mixed(variant.colors))

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
