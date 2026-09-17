from __future__ import annotations

import random
import unittest
from unittest.mock import Mock, call

from app.field_birds import (
    BIRD_FLAP_INTERVAL,
    BIRD_PLAYER_MARGIN,
    BIRD_SIZE,
    FieldBird,
    WorldMapBirds,
)


class WorldMapBirdsTest(unittest.TestCase):
    def test_random_flights_avoid_stationary_player_including_map_edges(self) -> None:
        camera = (100, 200)
        for player in ((220, 312), (100, 200), (340, 424), (100, 312), (220, 424)):
            with self.subTest(player=player):
                flock = WorldMapBirds(256, 240, rng=random.Random(7))
                flights = []
                max_visible = 0
                for _frame in range(12000):
                    previous = {id(bird) for bird in flock.birds}
                    flock.update(camera=camera, player=player)
                    max_visible = max(max_visible, len(flock.birds))
                    for bird in flock.birds:
                        if id(bird) not in previous:
                            flights.append((bird.x, bird.velocity_x, bird.velocity_y))
                            self.assertEqual(bird.y, camera[1] + 240)
                        self.assertLess(bird.velocity_y, 0)
                        self.assertGreaterEqual(abs(bird.velocity_x), 0.15)
                        overlaps = (
                            bird.x < player[0] + BIRD_SIZE + BIRD_PLAYER_MARGIN
                            and bird.x + BIRD_SIZE > player[0] - BIRD_PLAYER_MARGIN
                            and bird.y < player[1] + BIRD_SIZE + BIRD_PLAYER_MARGIN
                            and bird.y + BIRD_SIZE > player[1] - BIRD_PLAYER_MARGIN
                        )
                        self.assertFalse(overlaps)
                self.assertGreater(len(flights), 20)
                self.assertGreater(max_visible, 1)
                self.assertTrue(any(vx < 0 for _x, vx, _vy in flights))
                self.assertTrue(any(vx > 0 for _x, vx, _vy in flights))
                self.assertGreater(len({vy for _x, _vx, vy in flights}), 1)

    def test_flaps_slowly_and_draw_does_not_advance_state(self) -> None:
        flock = WorldMapBirds(256, 240, rng=random.Random(1))
        flock._spawn_wait = 1000
        bird = FieldBird(128, 120, 0.15, -0.6)
        flock.birds.append(bird)
        pyxel = Mock()
        for source_y in (64, 80, 96, 80, 64):
            for _frame in range(BIRD_FLAP_INTERVAL):
                before = (bird.x, bird.y, bird.age, flock._spawn_wait)
                flock.draw(camera=(0, 0), pyxel_api=pyxel)
                self.assertEqual(pyxel.blt.call_args.args[2:], (0, 32, source_y, 16, 16, 1))
                self.assertEqual(before, (bird.x, bird.y, bird.age, flock._spawn_wait))
                flock.update(camera=(0, 0), player=(0, 0))

    def test_camera_scroll_changes_draw_position_without_changing_flight(self) -> None:
        flock = WorldMapBirds(256, 240)
        bird = FieldBird(160, 140, 0.25, -1)
        flock.birds.append(bird)
        pyxel = Mock()
        flock.draw(camera=(32, 16), pyxel_api=pyxel)
        flock.draw(camera=(48, 32), pyxel_api=pyxel)
        self.assertEqual(pyxel.blt.call_args_list, [
            call(128, 124, 0, 32, 64, 16, 16, 1),
            call(112, 108, 0, 32, 64, 16, 16, 1),
        ])
        flock.update(camera=(48, 32), player=(160, 140))
        self.assertEqual((bird.x, bird.y), (160.25, 139))

    def test_removes_birds_after_they_leave_the_viewport(self) -> None:
        flock = WorldMapBirds(256, 240)
        flock.birds.extend((
            FieldBird(30, -15.5, 0, -1),
            FieldBird(255.5, 50, 1, -1),
            FieldBird(-15.5, 50, -1, -1),
        ))
        flock.update(camera=(0, 0), player=(120, 112))
        self.assertEqual(flock.birds, [])

    def test_cosmetic_randomness_does_not_consume_gameplay_randomness(self) -> None:
        state = random.getstate()
        flock = WorldMapBirds(256, 240)
        for _frame in range(1000):
            flock.update(camera=(0, 0), player=(120, 112))
        self.assertEqual(random.getstate(), state)


if __name__ == "__main__":
    unittest.main()
