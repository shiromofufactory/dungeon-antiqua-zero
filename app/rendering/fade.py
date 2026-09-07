"""Frame-driven fade state for transitions through black."""

from __future__ import annotations

from enum import Enum, auto


DEFAULT_FADE_FRAME_COUNT = 6


class FadePhase(Enum):
    """Current phase of one fade-through-black transition."""

    IDLE = auto()
    FADING_OUT = auto()
    FADING_IN = auto()


class FadeEvent(Enum):
    """Milestones reported while advancing a fade transition."""

    NONE = auto()
    COVERED = auto()
    FINISHED = auto()


class FadeThroughBlack:
    """Advance a configurable fade out followed by a matching fade in.

    This object owns only presentation timing. The transition coordinator that
    owns it applies the pending screen change when ``COVERED`` is reported.
    """

    def __init__(self, frame_count: int = DEFAULT_FADE_FRAME_COUNT) -> None:
        if isinstance(frame_count, bool) or not isinstance(frame_count, int):
            raise TypeError("fade frame count must be an integer")
        if frame_count <= 0:
            raise ValueError("fade frame count must be positive")
        self._frame_count = frame_count
        self._phase = FadePhase.IDLE
        self._elapsed_frames = 0

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def phase(self) -> FadePhase:
        return self._phase

    @property
    def elapsed_frames(self) -> int:
        return self._elapsed_frames

    @property
    def is_active(self) -> bool:
        return self._phase is not FadePhase.IDLE

    @property
    def visible_rate(self) -> float:
        """Return 1.0 when visible and 0.0 when fully covered by black."""

        if self._phase is FadePhase.FADING_OUT:
            return 1.0 - self._elapsed_frames / self._frame_count
        if self._phase is FadePhase.FADING_IN:
            return self._elapsed_frames / self._frame_count
        return 1.0

    def start(self) -> None:
        """Start a new transition from the fully visible state."""

        if self.is_active:
            raise RuntimeError("fade transition is already active")
        self._phase = FadePhase.FADING_OUT
        self._elapsed_frames = 0

    def start_fade_in(self) -> None:
        """Start directly from black and fade into the current screen."""

        if self.is_active:
            raise RuntimeError("fade transition is already active")
        self._phase = FadePhase.FADING_IN
        self._elapsed_frames = 0

    def update(self) -> FadeEvent:
        """Advance one frame and report a transition milestone."""

        if self._phase is FadePhase.IDLE:
            return FadeEvent.NONE

        self._elapsed_frames += 1
        if self._elapsed_frames < self._frame_count:
            return FadeEvent.NONE

        if self._phase is FadePhase.FADING_OUT:
            self._phase = FadePhase.FADING_IN
            self._elapsed_frames = 0
            return FadeEvent.COVERED

        self._phase = FadePhase.IDLE
        self._elapsed_frames = 0
        return FadeEvent.FINISHED


__all__ = [
    "DEFAULT_FADE_FRAME_COUNT",
    "FadeEvent",
    "FadePhase",
    "FadeThroughBlack",
]
