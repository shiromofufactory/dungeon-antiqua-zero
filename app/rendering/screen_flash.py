"""Frame timing for a whole-screen color flash."""

from __future__ import annotations


FLASH_PHASE_FRAMES = 6


class ScreenFlash:
    """Fade into the target color, then fade back to the original palette."""

    def __init__(self, target_color: int, phase_frames: int = FLASH_PHASE_FRAMES) -> None:
        if (
            isinstance(phase_frames, bool)
            or not isinstance(phase_frames, int)
            or phase_frames < 1
        ):
            raise ValueError("phase_frames must be a positive integer")
        self.target_color = target_color
        self.phase_frames = phase_frames
        self.elapsed_frames = 0

    @property
    def is_active(self) -> bool:
        return self.elapsed_frames < self.phase_frames * 2

    @property
    def visible_rate(self) -> float:
        if self.elapsed_frames <= self.phase_frames:
            return (self.phase_frames - self.elapsed_frames) / self.phase_frames
        return (self.elapsed_frames - self.phase_frames) / self.phase_frames

    def update(self) -> None:
        if self.is_active:
            self.elapsed_frames += 1
