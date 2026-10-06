"""Frame-driven screen brightness and horizontal shake presentation."""

from __future__ import annotations


BRIGHTNESS_CHANGE_FRAMES = 30
BRIGHTNESS_PERCENTAGES = (0, 25, 50, 75, 100)
SHAKE_OFFSETS = (0, 1, 2, 0, -2, -1)


class ScreenBrightness:
    """Keep the chosen brightness after interpolating from the current value."""

    def __init__(self) -> None:
        self.rate = 1.0
        self._start_rate = 1.0
        self._target_rate = 1.0
        self.elapsed_frames = BRIGHTNESS_CHANGE_FRAMES

    @property
    def is_active(self) -> bool:
        return self.elapsed_frames < BRIGHTNESS_CHANGE_FRAMES

    def start(self, percent: int) -> None:
        if type(percent) is not int or percent not in BRIGHTNESS_PERCENTAGES:
            raise ValueError("brightness percent must be 0, 25, 50, 75 or 100")
        self._start_rate = self.rate
        self._target_rate = percent / 100
        self.elapsed_frames = 0

    def update(self) -> None:
        if not self.is_active:
            return
        self.elapsed_frames += 1
        if not self.is_active:
            self.rate = self._target_rate
        else:
            progress = self.elapsed_frames / BRIGHTNESS_CHANGE_FRAMES
            self.rate = self._start_rate + (self._target_rate - self._start_rate) * progress

    def stop(self) -> None:
        """Cancel an interrupted change while retaining the current brightness."""

        self.elapsed_frames = BRIGHTNESS_CHANGE_FRAMES


class ScreenShake:
    """Move only the drawing camera, restoring its origin at completion."""

    def __init__(self, frames: int) -> None:
        if type(frames) is not int or frames < 6 or frames % 6:
            raise ValueError("shake frames must be a positive multiple of six")
        self.frames = frames
        self.elapsed_frames = 0

    @property
    def is_active(self) -> bool:
        return self.elapsed_frames < self.frames

    @property
    def camera_x(self) -> int:
        if not self.is_active:
            return 0
        return SHAKE_OFFSETS[self.elapsed_frames % len(SHAKE_OFFSETS)]

    def update(self) -> None:
        if self.is_active:
            self.elapsed_frames += 1
