"""Frame-driven monster defeat presentation independent of Pyxel callbacks."""

from __future__ import annotations

from enum import StrEnum

from .palette import mix_color

MONSTER_DEATH_PALETTE = "monster_death"
MONSTER_DEATH_TINT_COLOR = 0xBD9E8C
# MONSTER_DEATH_BRIGHT_COLOR = 0xF5E8FF
MONSTER_DEATH_BRIGHT_COLOR = 0xBDBDBD
MONSTER_DEATH_PALETTE_BASE_RATE = 0.3
MONSTER_DEATH_TINT_FRAME_COUNT = 6
MONSTER_DEATH_BRIGHTEN_FRAME_COUNT = 8
MONSTER_DEATH_DISSOLVE_FRAME_COUNT = 16


class MonsterDeathPhase(StrEnum):
    """Ordered visual stages for one defeated monster."""

    TINT = "tint"
    BRIGHTEN = "brighten"
    DISSOLVE = "dissolve"
    FINISHED = "finished"


class MonsterDeathAnimation:
    """Own timing and render parameters for a red-purple death dissolve."""

    def __init__(self) -> None:
        self.phase = MonsterDeathPhase.TINT
        self.elapsed_frames = 0

    @property
    def is_finished(self) -> bool:
        return self.phase is MonsterDeathPhase.FINISHED

    @property
    def palette_target_color(self) -> int:
        """Return the tint color for the current animation frame."""

        if self.phase is MonsterDeathPhase.TINT:
            return MONSTER_DEATH_TINT_COLOR
        if self.phase is MonsterDeathPhase.BRIGHTEN:
            progress = (self.elapsed_frames + 1) / MONSTER_DEATH_BRIGHTEN_FRAME_COUNT
            return mix_color(
                MONSTER_DEATH_TINT_COLOR,
                1.0 - progress,
                MONSTER_DEATH_BRIGHT_COLOR,
            )
        return MONSTER_DEATH_BRIGHT_COLOR

    @property
    def opacity(self) -> float:
        """Return ordered-dither coverage during the dissolve stage."""

        if self.phase is MonsterDeathPhase.FINISHED:
            return 0.0
        if self.phase is not MonsterDeathPhase.DISSOLVE:
            return 1.0
        return 1.0 - (self.elapsed_frames / MONSTER_DEATH_DISSOLVE_FRAME_COUNT)

    def update(self) -> None:
        """Advance one frame, moving through tint, brighten, and dissolve."""

        if self.is_finished:
            return
        self.elapsed_frames += 1
        duration = {
            MonsterDeathPhase.TINT: MONSTER_DEATH_TINT_FRAME_COUNT,
            MonsterDeathPhase.BRIGHTEN: MONSTER_DEATH_BRIGHTEN_FRAME_COUNT,
            MonsterDeathPhase.DISSOLVE: MONSTER_DEATH_DISSOLVE_FRAME_COUNT,
        }[self.phase]
        if self.elapsed_frames < duration:
            return
        self.phase = {
            MonsterDeathPhase.TINT: MonsterDeathPhase.BRIGHTEN,
            MonsterDeathPhase.BRIGHTEN: MonsterDeathPhase.DISSOLVE,
            MonsterDeathPhase.DISSOLVE: MonsterDeathPhase.FINISHED,
        }[self.phase]
        self.elapsed_frames = 0


__all__ = [
    "MONSTER_DEATH_BRIGHT_COLOR",
    "MONSTER_DEATH_BRIGHTEN_FRAME_COUNT",
    "MONSTER_DEATH_DISSOLVE_FRAME_COUNT",
    "MONSTER_DEATH_PALETTE",
    "MONSTER_DEATH_PALETTE_BASE_RATE",
    "MONSTER_DEATH_TINT_COLOR",
    "MONSTER_DEATH_TINT_FRAME_COUNT",
    "MonsterDeathAnimation",
    "MonsterDeathPhase",
]
