from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import Mock

from app.field import FieldActors, FieldMovement, FieldPosition
from app.input import Direction
from app.rendering.field import FieldRenderer
from app.resources.maps import MapActor, MapCell, MapTreasureContents, MapVisibilityCondition
from tests.test_field import compiled_map


class ActorVisibilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.flags: set[str] = set()
        self.map_data = replace(
            compiled_map(("0000",) * 4, profile="town"),
            actors=(
                MapActor("on_actor", MapCell(1, 1), "roaming", 0, "down", visibility_condition=MapVisibilityCondition("story.open", True)),
                MapActor("off_actor", MapCell(2, 1), "stationary", 0, "left", visibility_condition=MapVisibilityCondition("story.open", False)),
                MapActor("always", MapCell(3, 1), "prop", 0),
                MapActor("chest", MapCell(1, 2), "treasure", 0, contents=MapTreasureContents("gold", amount=10), visibility_condition=MapVisibilityCondition("story.open", True)),
            ),
        )
        self.actors = FieldActors(self.map_data, event_flags=self.flags)

    def test_visibility_changes_collision_and_lookup_without_recreating_actor_state(self) -> None:
        hidden = self.actors.actor("on_actor")
        self.assertEqual({actor.id for actor in self.actors.actors}, {"on_actor", "off_actor", "always", "chest"})
        self.assertEqual({actor.id for actor in self.actors.visible_actors}, {"off_actor", "always"})
        self.assertEqual(set(self.actors.positions), {"off_actor", "always"})
        self.assertEqual(set(self.actors.blocked_positions()), {FieldPosition(2, 1), FieldPosition(3, 1)})
        self.assertIsNone(self.actors.actor_at(1, 1))
        self.flags.add("story.open")
        self.assertIs(self.actors.actor("on_actor"), hidden)
        self.assertIs(self.actors.actor_at(1, 1), hidden)
        self.assertEqual({actor.id for actor in self.actors.visible_actors}, {"on_actor", "always", "chest"})
        self.assertEqual(set(self.actors.positions), {"on_actor", "always", "chest"})
        self.assertNotIn(FieldPosition(2, 1), self.actors.blocked_positions())
        self.assertNotIn(FieldPosition(1, 1), self.actors.blocked_positions(excluding="on_actor"))

    def test_party_can_enter_hidden_actor_cell_but_visible_actor_blocks_it(self) -> None:
        party = FieldMovement(self.map_data, start=FieldPosition(0, 1), allow_blocked_start=True, event_flags=self.flags)
        self.flags.add("story.open")
        self.assertFalse(party.update(Direction.RIGHT, blocked_positions=self.actors.blocked_positions()))
        self.flags.clear()
        self.assertTrue(party.update(Direction.RIGHT, blocked_positions=self.actors.blocked_positions()))

    def test_hidden_roaming_actor_pauses_and_resumes_its_wait_and_movement(self) -> None:
        actor = self.actors.actor("on_actor")
        actor.roam_wait_frames = 5
        party = FieldPosition(0, 0)
        self.actors.update_roaming(party_position=party)
        self.assertEqual(actor.roam_wait_frames, 5)
        self.flags.add("story.open")
        self.actors.update_roaming(party_position=party)
        self.assertEqual(actor.roam_wait_frames, 4)
        self.actors.update("on_actor", Direction.DOWN, party_position=party)
        # The visible treasure blocks this route; hiding it allows an explicit move.
        self.assertFalse(actor.movement.is_moving)
        self.flags.clear()
        self.actors.update("on_actor", Direction.DOWN, party_position=party)
        self.assertTrue(actor.movement.is_moving)
        world_y = actor.movement.world_y
        self.assertNotIn(FieldPosition(1, 2), self.actors.blocked_positions())
        self.actors.update_roaming(party_position=party)
        self.assertEqual(actor.movement.world_y, world_y)
        self.flags.add("story.open")
        self.assertIn(FieldPosition(1, 2), self.actors.blocked_positions())
        self.actors.update_roaming(party_position=party)
        self.assertGreater(actor.movement.world_y, world_y)

    def test_hidden_actor_can_be_moved_and_faced_by_explicit_event_commands(self) -> None:
        actor = self.actors.actor("on_actor")
        for _ in range(8):
            self.actors.update("on_actor", Direction.DOWN, party_position=FieldPosition(0, 0))
        self.actors.face("on_actor", Direction.UP)
        self.flags.add("story.open")
        self.assertIs(self.actors.actor_at(1, 2), actor)
        self.assertIs(actor.movement.facing, Direction.UP)

    def test_hidden_treasure_keeps_open_state_and_pauses_its_animation(self) -> None:
        actor = self.actors.actor("chest")
        self.actors.start_treasure_opening("chest")
        self.actors.update_treasure_animations()
        self.assertEqual(actor.treasure_animation_elapsed, 0)
        self.assertIsNone(self.actors.actor_at(1, 2))
        self.flags.add("story.open")
        self.actors.update_treasure_animations()
        self.assertEqual(actor.treasure_animation_elapsed, 1)
        opened = FieldActors(self.map_data, event_flags=self.flags, opened_treasure_ids=("chest",))
        self.flags.clear()
        self.assertIsNone(opened.actor_at(1, 2))
        self.flags.add("story.open")
        self.assertEqual(opened.actor_at(1, 2).treasure_frame, 2)

    def test_renderer_omits_hidden_actor_sprites_and_shadows_for_all_kinds(self) -> None:
        for kind in ("prop", "stationary", "roaming", "treasure"):
            with self.subTest(kind=kind):
                actor = next(actor for actor in self.map_data.actors if actor.kind == kind)
                actor = replace(actor, visibility_condition=MapVisibilityCondition("story.visible", True))
                map_data = replace(self.map_data, actors=(actor,))
                flags: set[str] = set()
                actors = FieldActors(map_data, event_flags=flags)
                field = FieldMovement(map_data, start=FieldPosition(0, 0), allow_blocked_start=True, event_flags=flags)
                px = Mock(frame_count=0)
                image = Mock(width=48, height=16 if kind in ("prop", "treasure") else 128)
                renderer = FieldRenderer(map_data, screen_width=64, screen_height=64, pyxel_api=px)
                def draw() -> None:
                    px.blt.reset_mock()
                    renderer.draw(field, actors=actors, prop_image=image, actor_character_image=image, treasure_image=image, draw_player=False)
                draw()
                self.assertFalse(any(call.args[2] is image or call.args[2] == 0 for call in px.blt.call_args_list))
                flags.add("story.visible")
                draw()
                self.assertTrue(any(call.args[2] is image for call in px.blt.call_args_list))
                flags.clear()
                draw()
                self.assertFalse(any(call.args[2] is image or call.args[2] == 0 for call in px.blt.call_args_list))


if __name__ == "__main__":
    unittest.main()
