"""Frame-driven zooming and rotating field transition for encounters."""

from __future__ import annotations

from dataclasses import dataclass
import math


ENCOUNTER_TRANSITION_FRAME_COUNT = 40
ENCOUNTER_FADE_START_FRAME = 20
ENCOUNTER_ROTATION_START_FRAME = 12
ENCOUNTER_ROTATION_DEGREES = 360.0
ENCOUNTER_FINAL_SCALE = 4.0
_SCALE_EASING_EXPONENT = 1.5
_COVERAGE_SAFETY_RATE = 1.01


@dataclass(frozen=True)
class EncounterTransform:
    """Pyxel blit parameters for one encounter-transition frame."""

    x: float
    y: float
    rotate: float
    scale: float


class EncounterTransition:
    """Enlarge, then rotate a captured field while keeping the screen covered."""

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
    def progress(self) -> float:
        return min(1.0, self.elapsed_frames / ENCOUNTER_TRANSITION_FRAME_COUNT)

    @property
    def visible_rate(self) -> float:
        if self.elapsed_frames <= ENCOUNTER_FADE_START_FRAME:
            return 1.0
        fade_frames = (
            ENCOUNTER_TRANSITION_FRAME_COUNT - ENCOUNTER_FADE_START_FRAME
        )
        return max(
            0.0,
            1.0
            - (self.elapsed_frames - ENCOUNTER_FADE_START_FRAME)
            / fade_frames,
        )

    def update(self) -> None:
        if not self.is_finished:
            self.elapsed_frames += 1

    def transform(self, width: int, height: int) -> EncounterTransform:
        """Keep the PC pivot fixed while Pyxel transforms around image center."""

        for name, value in (("width", width), ("height", height)):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"encounter {name} must be a positive integer")
        progress = self.progress
        last_visible_frame = ENCOUNTER_TRANSITION_FRAME_COUNT - 1
        rotation_frame_count = (
            last_visible_frame - ENCOUNTER_ROTATION_START_FRAME
        )
        rotation_progress = max(
            0.0,
            min(
                1.0,
                (self.elapsed_frames - ENCOUNTER_ROTATION_START_FRAME)
                / rotation_frame_count,
            ),
        )
        rotate = ENCOUNTER_ROTATION_DEGREES * rotation_progress
        scale = 1.0 + (ENCOUNTER_FINAL_SCALE - 1.0) * (
            progress**_SCALE_EASING_EXPONENT
        )
        radians = math.radians(rotate)
        cosine = math.cos(radians)
        sine = math.sin(radians)
        if rotate != 0.0:
            scale = max(
                scale,
                self._minimum_cover_scale(
                    width,
                    height,
                    cosine=cosine,
                    sine=sine,
                )
                * _COVERAGE_SAFETY_RATE,
            )
        center_x = width / 2
        center_y = height / 2
        relative_x = center_x - self.pivot_x
        relative_y = center_y - self.pivot_y
        destination_center_x = self.pivot_x + scale * (
            relative_x * cosine - relative_y * sine
        )
        destination_center_y = self.pivot_y + scale * (
            relative_x * sine + relative_y * cosine
        )
        return EncounterTransform(
            x=destination_center_x - center_x,
            y=destination_center_y - center_y,
            rotate=rotate,
            scale=scale,
        )

    def _minimum_cover_scale(
        self,
        width: int,
        height: int,
        *,
        cosine: float,
        sine: float,
    ) -> float:
        """Return the scale needed for the rotated image to cover the viewport."""

        left = self.pivot_x
        right = width - self.pivot_x
        top = self.pivot_y
        bottom = height - self.pivot_y
        if min(left, right, top, bottom) <= 0.0:
            return 1.0

        required_scale = 1.0
        for corner_x, corner_y in (
            (0.0, 0.0),
            (float(width), 0.0),
            (0.0, float(height)),
            (float(width), float(height)),
        ):
            relative_x = corner_x - self.pivot_x
            relative_y = corner_y - self.pivot_y
            source_x = cosine * relative_x + sine * relative_y
            source_y = -sine * relative_x + cosine * relative_y
            required_scale = max(
                required_scale,
                source_x / right if source_x >= 0.0 else -source_x / left,
                source_y / bottom if source_y >= 0.0 else -source_y / top,
            )
        return required_scale


__all__ = [
    "ENCOUNTER_FADE_START_FRAME",
    "ENCOUNTER_FINAL_SCALE",
    "ENCOUNTER_ROTATION_DEGREES",
    "ENCOUNTER_ROTATION_START_FRAME",
    "ENCOUNTER_TRANSITION_FRAME_COUNT",
    "EncounterTransform",
    "EncounterTransition",
]
