"""Gauge-based battle turn ordering independent of Pyxel presentation."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Generic, TypeVar


Actor = TypeVar("Actor")
GAUGE_READY_VALUE = 64.0
INITIAL_GAUGE_MULTIPLIER_MIN = 1.0
INITIAL_GAUGE_MULTIPLIER_MAX = 2.0


@dataclass(frozen=True)
class TimelineEntry(Generic[Actor]):
    """One combatant's current agility and gauge value."""

    actor: Actor
    agility: int
    gauge: float

    def __post_init__(self) -> None:
        if isinstance(self.agility, bool) or not isinstance(self.agility, int):
            raise TypeError("timeline agility must be an integer")
        if self.agility < 0:
            raise ValueError("timeline agility must not be negative")
        if isinstance(self.gauge, bool) or not isinstance(self.gauge, Real):
            raise TypeError("timeline gauge must be numeric")


@dataclass(frozen=True)
class TimelineOrder(Generic[Actor]):
    """Combatants sorted from the next actor to the last actor."""

    entries: tuple[TimelineEntry[Actor], ...]

    @property
    def actors(self) -> tuple[Actor, ...]:
        return tuple(entry.actor for entry in self.entries)


@dataclass(frozen=True)
class TimelineAdvance(Generic[Actor]):
    """One completed action and the ordering needed by its presentation."""

    before: TimelineOrder[Actor]
    remaining: TimelineOrder[Actor]
    after: TimelineOrder[Actor]
    completed_actor: Actor
    reinsertion_index: int
    interrupt_index: int | None
    overflow_actor: Actor | None
    reinsert_completed_actor: bool = True


def initialize_timeline_order(
    combatants: Sequence[tuple[Actor, int]],
    *,
    multiplier: Callable[[], float] | None = None,
) -> TimelineOrder[Actor]:
    """Roll initial gauges, sort descending, and ready the first actor."""

    roll = multiplier or random.uniform
    entries: list[TimelineEntry[Actor]] = []
    for actor, agility in combatants:
        if multiplier is None:
            value = roll(
                INITIAL_GAUGE_MULTIPLIER_MIN,
                INITIAL_GAUGE_MULTIPLIER_MAX,
            )
        else:
            value = roll()
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError("timeline multiplier must be numeric")
        value = float(value)
        if not INITIAL_GAUGE_MULTIPLIER_MIN <= value <= INITIAL_GAUGE_MULTIPLIER_MAX:
            raise ValueError("timeline multiplier must be from 1.0 to 2.0")
        entries.append(TimelineEntry(actor, agility, agility * value))

    # Python's stable sort keeps encounter order for exact gauge ties.
    rolled = TimelineOrder(
        tuple(sorted(entries, key=lambda entry: entry.gauge, reverse=True))
    )
    return ready_timeline_head(rolled)


def ready_timeline_head(
    order: TimelineOrder[Actor],
    *,
    ready_value: float = GAUGE_READY_VALUE,
) -> TimelineOrder[Actor]:
    """Add one shared delta so the leading combatant's gauge equals 64."""

    if not order.entries:
        return order
    delta = ready_value - order.entries[0].gauge
    return TimelineOrder(
        tuple(
            TimelineEntry(entry.actor, entry.agility, entry.gauge + delta)
            for entry in order.entries
        )
    )


def complete_timeline_action(
    order: TimelineOrder[Actor],
    *,
    current_agility: int,
    visible_count: int,
    gauge_adjustment: Real = 0,
) -> TimelineAdvance[Actor]:
    """Reset the current actor's gauge and stably reinsert it by gauge."""

    if not order.entries:
        raise ValueError("cannot complete an action on an empty timeline")
    if isinstance(visible_count, bool) or not isinstance(visible_count, int):
        raise TypeError("visible_count must be an integer")
    if visible_count <= 0:
        raise ValueError("visible_count must be positive")

    completed = order.entries[0]
    remaining = TimelineOrder(order.entries[1:])
    if isinstance(gauge_adjustment, bool) or not isinstance(
        gauge_adjustment,
        Real,
    ):
        raise TypeError("gauge_adjustment must be numeric")
    gauge = current_agility + gauge_adjustment
    reset = TimelineEntry(completed.actor, current_agility, float(gauge))
    entries = list(remaining.entries)
    reinsertion_index = len(entries)
    for index, entry in enumerate(entries):
        if reset.gauge > entry.gauge:
            reinsertion_index = index
            break
    entries.insert(reinsertion_index, reset)
    after = TimelineOrder(tuple(entries))

    interrupt_index = (
        reinsertion_index
        if reinsertion_index < visible_count
        and any(entry.gauge < reset.gauge for entry in remaining.entries)
        else None
    )
    overflow_actor = (
        remaining.entries[visible_count - 1].actor
        if interrupt_index is not None and len(remaining.entries) >= visible_count
        else None
    )
    return TimelineAdvance(
        before=order,
        remaining=remaining,
        after=after,
        completed_actor=completed.actor,
        reinsertion_index=reinsertion_index,
        interrupt_index=interrupt_index,
        overflow_actor=overflow_actor,
    )


def remove_timeline_head(
    order: TimelineOrder[Actor],
) -> TimelineAdvance[Actor]:
    """Remove the current actor without reinserting it after the slide."""

    if not order.entries:
        raise ValueError("cannot remove an actor from an empty timeline")
    completed = order.entries[0]
    remaining = TimelineOrder(order.entries[1:])
    return TimelineAdvance(
        before=order,
        remaining=remaining,
        after=remaining,
        completed_actor=completed.actor,
        reinsertion_index=len(remaining.entries),
        interrupt_index=None,
        overflow_actor=None,
        reinsert_completed_actor=False,
    )


def remove_timeline_actor(
    order: TimelineOrder[Actor],
    actor: Actor,
) -> TimelineOrder[Actor]:
    """Remove one combatant by identity without disturbing the others."""

    return TimelineOrder(
        tuple(entry for entry in order.entries if entry.actor is not actor)
    )


def insert_timeline_actor(
    order: TimelineOrder[Actor],
    actor: Actor,
    *,
    agility: int,
    gauge: Real,
) -> TimelineOrder[Actor]:
    """Stably insert a returning combatant without disturbing equal gauges."""

    entry = TimelineEntry(actor, agility, gauge)
    entries = list(order.entries)
    insertion_index = len(entries)
    for index, current in enumerate(entries):
        if entry.gauge > current.gauge:
            insertion_index = index
            break
    entries.insert(insertion_index, entry)
    return TimelineOrder(tuple(entries))


__all__ = [
    "GAUGE_READY_VALUE",
    "INITIAL_GAUGE_MULTIPLIER_MAX",
    "INITIAL_GAUGE_MULTIPLIER_MIN",
    "TimelineAdvance",
    "TimelineEntry",
    "TimelineOrder",
    "complete_timeline_action",
    "initialize_timeline_order",
    "insert_timeline_actor",
    "ready_timeline_head",
    "remove_timeline_actor",
    "remove_timeline_head",
]
