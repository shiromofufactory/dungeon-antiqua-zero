"""Fixed-width display-text formatting independent of Pyxel."""

from __future__ import annotations

if __package__ == "ui":
    from localization import ascii_to_fullwidth
else:
    from ..localization import ascii_to_fullwidth


def _validate_width(width: int) -> None:
    if isinstance(width, bool) or not isinstance(width, int):
        raise TypeError("width must be an integer")
    if width < 0:
        raise ValueError("width must not be negative")


def _validate_fill(fill: str) -> None:
    if not isinstance(fill, str) or len(fill) != 1:
        raise ValueError("fill must be one character")


def spacing(value: object, width: int, *, fill: str = " ") -> str:
    """Left-align a value to a fixed fullwidth-character width.

    Values longer than ``width`` keep their rightmost characters, matching
    the fixed-field behavior used by the previous Dungeon Antiqua games.
    """

    _validate_width(width)
    _validate_fill(fill)
    if width == 0:
        return ""
    text = str(value).ljust(width, fill)[-width:]
    return ascii_to_fullwidth(text)


def pad(value: object, width: int, *, fill: str = " ") -> str:
    """Right-align a value to a fixed fullwidth-character width.

    Values longer than ``width`` keep their rightmost characters, matching
    the fixed-field behavior used by the previous Dungeon Antiqua games.
    """

    _validate_width(width)
    _validate_fill(fill)
    if width == 0:
        return ""
    text = str(value).rjust(width, fill)[-width:]
    return ascii_to_fullwidth(text)


def format_play_time(
    frames: int,
    *,
    fps: int = 60,
    include_seconds: bool = True,
) -> str:
    """Format a saved frame count as a fullwidth play-time display."""

    if isinstance(frames, bool) or not isinstance(frames, int):
        raise TypeError("frames must be an integer")
    if frames < 0:
        raise ValueError("frames must not be negative")
    if isinstance(fps, bool) or not isinstance(fps, int):
        raise TypeError("fps must be an integer")
    if fps <= 0:
        raise ValueError("fps must be positive")
    if not isinstance(include_seconds, bool):
        raise TypeError("include_seconds must be a boolean")

    total_seconds = frames // fps
    hours = min(total_seconds // 3600, 99)
    minutes = (total_seconds // 60) % 60
    seconds = total_seconds % 60
    formatted = f"{hours:02d}:{minutes:02d}"
    if include_seconds:
        formatted += f":{seconds:02d}"
    return ascii_to_fullwidth(formatted)
