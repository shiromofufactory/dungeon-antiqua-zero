"""Actor sprite footprints shared by map authoring and runtime loading."""


def actor_overlaps_map(kind: str, x: int, y: int, width: int, height: int) -> bool:
    """Characters occupy the foot cell and one cell above it."""
    sprite_height = 2 if kind in ("stationary", "roaming") else 1
    return 0 <= x < width and y >= 0 and y - sprite_height + 1 < height
