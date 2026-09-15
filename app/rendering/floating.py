"""Shared floating offsets, phases, and field-character idle frames."""

from __future__ import annotations

from zlib import crc32


FLOATING_OFFSETS = (0, 0, 0, 1, 2, 2, 2, 1)
FLOATING_PHASE_FRAMES = 12
FLOATING_CYCLE_FRAMES = len(FLOATING_OFFSETS) * FLOATING_PHASE_FRAMES
FLOATING_CHARACTER_FRAMES = (2, 1, 0, 1)
FLOATING_CHARACTER_FRAME_INTERVAL = 20
FLOATING_CHARACTER_CYCLE_FRAMES = (
    len(FLOATING_CHARACTER_FRAMES) * FLOATING_CHARACTER_FRAME_INTERVAL
)


def floating_phase_offset(identity: str) -> int:
    """Derive a stable position within the cycle from an entity identity."""

    if not isinstance(identity, str):
        raise TypeError("floating identity must be a string")
    if not identity:
        raise ValueError("floating identity must not be empty")
    return crc32(identity.encode("utf-8")) % FLOATING_CYCLE_FRAMES


def floating_offset(frame_count: int, *, phase_offset: int = 0) -> int:
    """Return the upward draw offset for one animation frame."""

    if isinstance(frame_count, bool) or not isinstance(frame_count, int):
        raise TypeError("floating frame count must be an integer")
    if frame_count < 0:
        raise ValueError("floating frame count must not be negative")
    if isinstance(phase_offset, bool) or not isinstance(phase_offset, int):
        raise TypeError("floating phase offset must be an integer")
    phase = (
        (frame_count + phase_offset) // FLOATING_PHASE_FRAMES
    ) % len(FLOATING_OFFSETS)
    return FLOATING_OFFSETS[phase]


def floating_character_frame(frame_count: int, *, phase_offset: int = 0) -> int:
    """Return the idle sprite frame for a floating three-frame character."""

    if isinstance(frame_count, bool) or not isinstance(frame_count, int):
        raise TypeError("floating character frame count must be an integer")
    if frame_count < 0:
        raise ValueError("floating character frame count must not be negative")
    if isinstance(phase_offset, bool) or not isinstance(phase_offset, int):
        raise TypeError("floating character phase offset must be an integer")
    phase = (
        (frame_count + phase_offset) // FLOATING_CHARACTER_FRAME_INTERVAL
    ) % len(FLOATING_CHARACTER_FRAMES)
    return FLOATING_CHARACTER_FRAMES[phase]


__all__ = [
    "FLOATING_CHARACTER_CYCLE_FRAMES",
    "FLOATING_CHARACTER_FRAME_INTERVAL",
    "FLOATING_CHARACTER_FRAMES",
    "FLOATING_CYCLE_FRAMES",
    "FLOATING_OFFSETS",
    "FLOATING_PHASE_FRAMES",
    "floating_character_frame",
    "floating_offset",
    "floating_phase_offset",
]
