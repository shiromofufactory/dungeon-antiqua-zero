"""World-map birds: cosmetic flight state and drawing, without collisions."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any


BIRD_SIZE = 16
BIRD_FLAP_INTERVAL = 20
BIRD_FRAMES = (64, 80, 96, 80)
BIRD_SPAWN_WAIT_MIN = 60
BIRD_SPAWN_WAIT_MAX = 180
BIRD_PLAYER_MARGIN = 8


@dataclass
class FieldBird:
    x: float
    y: float
    velocity_x: float
    velocity_y: float
    age: int = 0

    @property
    def source_y(self) -> int:
        return BIRD_FRAMES[(self.age // BIRD_FLAP_INTERVAL) % len(BIRD_FRAMES)]


class WorldMapBirds:
    """Own transient birds in map pixel coordinates, independently of gameplay RNG."""

    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        *,
        rng: random.Random | None = None,
    ) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._rng = random.Random() if rng is None else rng
        self.birds: list[FieldBird] = []
        self._spawn_wait = self._next_wait()

    def _next_wait(self) -> int:
        return self._rng.randint(BIRD_SPAWN_WAIT_MIN, BIRD_SPAWN_WAIT_MAX)

    def update(
        self,
        *,
        camera: tuple[int, int],
        player: tuple[int, int],
    ) -> None:
        camera_x, camera_y = camera
        for bird in self.birds:
            bird.x += bird.velocity_x
            bird.y += bird.velocity_y
            bird.age += 1
        self.birds[:] = [
            bird for bird in self.birds
            if camera_x - BIRD_SIZE < bird.x < camera_x + self.screen_width
            and camera_y - BIRD_SIZE < bird.y <= camera_y + self.screen_height
        ]
        self._spawn_wait -= 1
        if self._spawn_wait <= 0:
            self._spawn(camera, player)
            self._spawn_wait = self._next_wait()

    def _spawn(self, camera: tuple[int, int], player: tuple[int, int]) -> None:
        camera_x, camera_y = camera
        player_x, player_y = player
        bottom_y = camera_y + self.screen_height
        top_y = camera_y - BIRD_SIZE
        for _attempt in range(32):
            bird = FieldBird(
                x=camera_x + self._rng.uniform(0, self.screen_width - BIRD_SIZE),
                y=bottom_y,
                velocity_x=self._rng.choice((-1, 1)) * self._rng.uniform(0.15, 0.45),
                velocity_y=-self._rng.uniform(0.6, 1.2),
            )
            top_x = bird.x + bird.velocity_x * (top_y - bottom_y) / bird.velocity_y
            if not camera_x <= top_x <= camera_x + self.screen_width - BIRD_SIZE:
                continue
            # Test the whole segment while the sprites could overlap vertically.
            # Once chosen, the trajectory stays fixed even when the PC moves.
            band_top = player_y - BIRD_SIZE - BIRD_PLAYER_MARGIN
            band_bottom = player_y + BIRD_SIZE + BIRD_PLAYER_MARGIN
            crossing_x = tuple(
                bird.x + bird.velocity_x * (y - bottom_y) / bird.velocity_y
                for y in (band_top, band_bottom)
            )
            if (
                max(crossing_x) + BIRD_SIZE <= player_x - BIRD_PLAYER_MARGIN
                or min(crossing_x) >= player_x + BIRD_SIZE + BIRD_PLAYER_MARGIN
            ):
                self.birds.append(bird)
                return

    def draw(self, *, camera: tuple[int, int], pyxel_api: Any) -> None:
        camera_x, camera_y = camera
        for bird in self.birds:
            pyxel_api.blt(
                int(bird.x - camera_x), int(bird.y - camera_y),
                0, 32, bird.source_y, BIRD_SIZE, BIRD_SIZE, 1,
            )
