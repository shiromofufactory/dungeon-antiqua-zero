"""Shared vertical floating animation used by cursors and field actors."""

from __future__ import annotations


FLOATING_OFFSETS = (0, 0, 0, 1, 2, 2, 2, 1)
FLOATING_PHASE_FRAMES = 12
FLOATING_CYCLE_FRAMES = len(FLOATING_OFFSETS) * FLOATING_PHASE_FRAMES


def floating_offset(frame_count: int) -> int:
    """Return the upward draw offset for one animation frame."""

    if isinstance(frame_count, bool) or not isinstance(frame_count, int):
        raise TypeError("floating frame count must be an integer")
    if frame_count < 0:
        raise ValueError("floating frame count must not be negative")
    phase = (frame_count // FLOATING_PHASE_FRAMES) % len(FLOATING_OFFSETS)
    return FLOATING_OFFSETS[phase]


__all__ = [
    "FLOATING_CYCLE_FRAMES",
    "FLOATING_OFFSETS",
    "FLOATING_PHASE_FRAMES",
    "floating_offset",
]
