from __future__ import annotations

import unittest

from battle_timeline import (
    GAUGE_READY_VALUE,
    TimelineEntry,
    TimelineOrder,
    complete_timeline_action,
    initialize_timeline_order,
    insert_timeline_actor,
    ready_timeline_head,
    remove_timeline_actor,
    remove_timeline_head,
)


class BattleTimelineTest(unittest.TestCase):
    def test_initial_gauges_are_rolled_sorted_and_readied(self) -> None:
        rolls = iter((1.0, 2.0, 1.5))

        order = initialize_timeline_order(
            (("slow", 10), ("fast", 20), ("middle", 15)),
            multiplier=lambda: next(rolls),
        )

        self.assertEqual(order.actors, ("fast", "middle", "slow"))
        self.assertEqual(
            tuple(entry.gauge for entry in order.entries),
            (GAUGE_READY_VALUE, 46.5, 34.0),
        )

    def test_readying_adds_the_same_delta_to_every_gauge(self) -> None:
        order = TimelineOrder(
            (
                TimelineEntry("first", 30, 60.0),
                TimelineEntry("second", 20, 45.0),
                TimelineEntry("third", 10, 30.0),
            )
        )

        readied = ready_timeline_head(order)

        self.assertEqual(
            tuple(entry.gauge for entry in readied.entries),
            (64.0, 49.0, 34.0),
        )

    def test_completed_actor_resets_and_interrupts_visible_order(self) -> None:
        order = TimelineOrder(
            tuple(
                TimelineEntry(actor, agility, gauge)
                for actor, agility, gauge in (
                    ("actor", 50, 64.0),
                    ("b", 40, 58.0),
                    ("c", 30, 52.0),
                    ("d", 20, 44.0),
                    ("e", 10, 38.0),
                    ("f", 10, 32.0),
                    ("g", 10, 26.0),
                )
            )
        )

        advance = complete_timeline_action(
            order,
            current_agility=50,
            visible_count=6,
        )

        self.assertEqual(advance.after.actors, ("b", "c", "actor", "d", "e", "f", "g"))
        self.assertEqual(advance.reinsertion_index, 2)
        self.assertEqual(advance.interrupt_index, 2)
        self.assertEqual(advance.overflow_actor, "g")
        self.assertEqual(advance.after.entries[2].gauge, 50.0)

    def test_completed_actor_below_visible_range_does_not_interrupt(self) -> None:
        order = TimelineOrder(
            tuple(
                TimelineEntry(actor, 10, gauge)
                for actor, gauge in zip("abcdefgh", (64, 60, 55, 50, 45, 40, 35, 30))
            )
        )

        advance = complete_timeline_action(order, current_agility=10, visible_count=6)

        self.assertEqual(advance.after.actors, tuple("bcdefgha"))
        self.assertEqual(advance.reinsertion_index, 7)
        self.assertIsNone(advance.interrupt_index)
        self.assertIsNone(advance.overflow_actor)

    def test_equal_gauge_keeps_the_existing_combatant_first(self) -> None:
        order = TimelineOrder(
            (
                TimelineEntry("actor", 50, 64.0),
                TimelineEntry("existing", 50, 50.0),
                TimelineEntry("lower", 10, 40.0),
            )
        )

        advance = complete_timeline_action(order, current_agility=50, visible_count=6)

        self.assertEqual(advance.after.actors, ("existing", "actor", "lower"))

    def test_action_can_adjust_its_reset_gauge_without_changing_agility(self) -> None:
        order = TimelineOrder(
            (
                TimelineEntry("actor", 50, 64.0),
                TimelineEntry("other", 10, 40.0),
            )
        )

        advance = complete_timeline_action(
            order,
            current_agility=50,
            visible_count=6,
            gauge_adjustment=-32,
        )

        self.assertEqual(advance.after.actors, ("other", "actor"))
        self.assertEqual(advance.after.entries[1].agility, 50)
        self.assertEqual(advance.after.entries[1].gauge, 18.0)

    def test_actor_can_be_removed_by_identity(self) -> None:
        first = object()
        second = object()
        order = TimelineOrder(
            (
                TimelineEntry(first, 20, 64.0),
                TimelineEntry(second, 10, 40.0),
            )
        )

        remaining = remove_timeline_actor(order, first)

        self.assertEqual(remaining.actors, (second,))

    def test_returning_actor_is_stably_inserted_by_gauge(self) -> None:
        order = TimelineOrder(
            (
                TimelineEntry("current", 20, 64.0),
                TimelineEntry("equal", 30, 30.0),
                TimelineEntry("later", 10, 10.0),
            )
        )

        inserted = insert_timeline_actor(
            order,
            "revived",
            agility=30,
            gauge=30.0,
        )

        self.assertEqual(
            inserted.actors,
            ("current", "equal", "revived", "later"),
        )

    def test_timeline_head_can_leave_without_being_reinserted(self) -> None:
        order = TimelineOrder(
            (
                TimelineEntry("escaping", 20, 64.0),
                TimelineEntry("remaining", 10, 40.0),
            )
        )

        advance = remove_timeline_head(order)

        self.assertEqual(advance.before.actors, ("escaping", "remaining"))
        self.assertEqual(advance.remaining.actors, ("remaining",))
        self.assertEqual(advance.after.actors, ("remaining",))
        self.assertEqual(advance.completed_actor, "escaping")
        self.assertFalse(advance.reinsert_completed_actor)


if __name__ == "__main__":
    unittest.main()
