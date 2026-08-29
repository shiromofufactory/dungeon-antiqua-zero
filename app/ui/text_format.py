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
