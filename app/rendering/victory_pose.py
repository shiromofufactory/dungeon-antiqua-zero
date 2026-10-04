"""Shared victory pose timing for the battlefield and growth results."""

VICTORY_SPRITE_SOURCE_X = 16 * 8
VICTORY_MOTION_LIMIT = 70
VICTORY_MOTION_PERIOD = 40
VICTORY_MOTION_VISIBLE_FRAMES = 20


def victory_sprite_source_x(frame: int) -> int:
    motion_visible = (
        min(frame, VICTORY_MOTION_LIMIT) + VICTORY_MOTION_VISIBLE_FRAMES + 10
    ) % VICTORY_MOTION_PERIOD < VICTORY_MOTION_VISIBLE_FRAMES
    return VICTORY_SPRITE_SOURCE_X if motion_visible else 0
