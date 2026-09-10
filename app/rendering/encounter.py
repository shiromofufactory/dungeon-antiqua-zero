"""Frame-driven zoom and whiteout transition for encounters."""

from __future__ import annotations

from dataclasses import dataclass


ENCOUNTER_TRANSITION_FRAME_COUNT = 40
ENCOUNTER_WHITEOUT_FRAME_COUNT = 32
ENCOUNTER_FADE_FRAME_COUNT = 8
ENCOUNTER_FINAL_SCALE = 4.0
ENCOUNTER_WHITE_COLOR = 0xFFFFFF
ENCOUNTER_BLACK_COLOR = 0x000000


@dataclass(frozen=True)
class EncounterTransform:
    """Pyxel blit parameters for one encounter-transition frame."""

    x: float
    y: float
    scale: float


class EncounterTransition:
    """Accelerate a captured field toward white, then fade it to black."""

    def __init__(self, pivot_x: float, pivot_y: float) -> None:
        for name, value in (("pivot_x", pivot_x), ("pivot_y", pivot_y)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number")
        self.pivot_x = float(pivot_x)
        self.pivot_y = float(pivot_y)
        self.elapsed_frames = 0

    @property
    def is_finished(self) -> bool:
        return self.elapsed_frames >= ENCOUNTER_TRANSITION_FRAME_COUNT

    @property
    def palette_base_rate(self) -> float:
        """Return the source-color rate during the whiteout phase."""

        return max(
            0.0,
            1.0 - self.elapsed_frames / ENCOUNTER_WHITEOUT_FRAME_COUNT,
        )

    @property
    def palette_target_color(self) -> int:
        """Return white during whiteout, then a grayscale fade to black."""

        if self.elapsed_frames <= ENCOUNTER_WHITEOUT_FRAME_COUNT:
            return ENCOUNTER_WHITE_COLOR
        fade_progress = min(
            1.0,
            (self.elapsed_frames - ENCOUNTER_WHITEOUT_FRAME_COUNT)
            / ENCOUNTER_FADE_FRAME_COUNT,
        )
        brightness = round(0xFF * (1.0 - fade_progress))
        return (brightness << 16) | (brightness << 8) | brightness

    def update(self) -> None:
        if not self.is_finished:
            self.elapsed_frames += 1

    def transform(self, width: int, height: int) -> EncounterTransform:
        """Keep the PC pivot fixed while Pyxel transforms around image center."""

        for name, value in (("width", width), ("height", height)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"encounter {name} must be a positive integer")
        zoom_progress = min(
            1.0,
            self.elapsed_frames / ENCOUNTER_WHITEOUT_FRAME_COUNT,
        )
        scale = 1.0 + (ENCOUNTER_FINAL_SCALE - 1.0) * zoom_progress**2
        center_x = width / 2
        center_y = height / 2
        relative_x = center_x - self.pivot_x
        relative_y = center_y - self.pivot_y
        destination_center_x = self.pivot_x + scale * relative_x
        destination_center_y = self.pivot_y + scale * relative_y
        return EncounterTransform(
            x=destination_center_x - center_x,
            y=destination_center_y - center_y,
            scale=scale,
        )


__all__ = [
    "ENCOUNTER_BLACK_COLOR",
    "ENCOUNTER_FADE_FRAME_COUNT",
    "ENCOUNTER_FINAL_SCALE",
    "ENCOUNTER_TRANSITION_FRAME_COUNT",
    "ENCOUNTER_WHITE_COLOR",
    "ENCOUNTER_WHITEOUT_FRAME_COUNT",
    "EncounterTransform",
    "EncounterTransition",
]
