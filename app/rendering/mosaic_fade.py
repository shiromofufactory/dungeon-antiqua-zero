"""Frame-driven mosaic fade-out state for battle escape magic."""

from __future__ import annotations


DEFAULT_MOSAIC_FADE_FRAME_COUNT = 24
DEFAULT_MOSAIC_MAX_BLOCK_SIZE = 16


class MosaicFadeOut:
    """Increase pixel-block size while fading an immutable screen to black."""

    def __init__(
        self,
        frame_count: int = DEFAULT_MOSAIC_FADE_FRAME_COUNT,
        *,
        maximum_block_size: int = DEFAULT_MOSAIC_MAX_BLOCK_SIZE,
    ) -> None:
        for label, value in (
            ("frame count", frame_count),
            ("maximum block size", maximum_block_size),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"mosaic fade {label} must be a positive integer")
        if maximum_block_size < 2:
            raise ValueError("mosaic fade maximum block size must be at least 2")
        self.frame_count = frame_count
        self.maximum_block_size = maximum_block_size
        self.frame = 0

    @property
    def is_finished(self) -> bool:
        return self.frame >= self.frame_count

    @property
    def visible_rate(self) -> float:
        return 1.0 - min(self.frame, self.frame_count) / self.frame_count

    @property
    def block_size(self) -> int:
        if self.frame <= 0:
            return 1
        return max(
            2,
            1
            + (self.maximum_block_size - 1)
            * min(self.frame, self.frame_count)
            // self.frame_count,
        )

    def update(self) -> None:
        if not self.is_finished:
            self.frame += 1


__all__ = [
    "DEFAULT_MOSAIC_FADE_FRAME_COUNT",
    "DEFAULT_MOSAIC_MAX_BLOCK_SIZE",
    "MosaicFadeOut",
]
