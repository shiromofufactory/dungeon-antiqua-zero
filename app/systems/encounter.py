"""Random encounter progress and dungeon-defeat return rules."""

from __future__ import annotations

from dataclasses import dataclass
import random

if __package__ == "systems":
    from field import FieldPosition
    from input import Direction
    from resources.maps import CompiledMap
else:
    from ..field import FieldPosition
    from ..input import Direction
    from ..resources.maps import CompiledMap


ENCOUNTER_STEP_MIN = 1
ENCOUNTER_STEP_MAX = 4
ENCOUNTER_THRESHOLD = 120


@dataclass(frozen=True)
class EncounterAdvance:
    """Result of advancing the persisted encounter gauge by one step."""

    count: int
    triggered: bool


@dataclass(frozen=True)
class DungeonExitReturn:
    """A safe cell immediately inside the selected dungeon exit."""

    position: FieldPosition
    facing: Direction


class EncounterSystem:
    """Apply DA1's random step increment with ZERO's fixed threshold."""

    def __init__(self, *, random_source: random.Random | None = None) -> None:
        self._random = random_source or random.Random()

    def advance(self, count: int) -> EncounterAdvance:
        """Advance one completed dungeon step and reset when battle starts."""

        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError("encounter count must be an integer")
        if count < 0:
            raise ValueError("encounter count must not be negative")
        advanced = count + self._random.randint(
            ENCOUNTER_STEP_MIN,
            ENCOUNTER_STEP_MAX,
        )
        if advanced >= ENCOUNTER_THRESHOLD:
            return EncounterAdvance(count=0, triggered=True)
        return EncounterAdvance(count=advanced, triggered=False)

    @staticmethod
    def defeat_return(
        map_data: CompiledMap,
        origin: FieldPosition,
    ) -> DungeonExitReturn | None:
        """Resolve the nearest outward site and a non-trigger cell beside it."""

        if not isinstance(map_data, CompiledMap):
            raise TypeError("defeat return requires a CompiledMap")
        if not isinstance(origin, FieldPosition):
            raise TypeError("defeat return origin must be a FieldPosition")
        exit_cells = {
            (cell.x, cell.y)
            for site in map_data.sites
            if site.destination.map_id != map_data.map_id
            for cell in site.entrance_cells
        }
        candidates: list[tuple[int, int, str, int, int, int, DungeonExitReturn]] = []
        for site in map_data.sites:
            if site.destination.map_id == map_data.map_id:
                continue
            for exit_cell in site.entrance_cells:
                exit_distance = abs(exit_cell.x - origin.x) + abs(
                    exit_cell.y - origin.y
                )
                for direction_index, direction in enumerate(Direction):
                    landing = FieldPosition(
                        exit_cell.x - direction.dx,
                        exit_cell.y - direction.dy,
                    )
                    if (landing.x, landing.y) in exit_cells or map_data.is_blocked(
                        landing.x, landing.y
                    ):
                        continue
                    landing_distance = abs(landing.x - origin.x) + abs(
                        landing.y - origin.y
                    )
                    candidates.append(
                        (
                            exit_distance,
                            landing_distance,
                            site.id,
                            exit_cell.y,
                            exit_cell.x,
                            direction_index,
                            DungeonExitReturn(landing, direction),
                        )
                    )
        if not candidates:
            return None
        return min(candidates, key=lambda candidate: candidate[:-1])[-1]


__all__ = [
    "DungeonExitReturn",
    "ENCOUNTER_STEP_MAX",
    "ENCOUNTER_STEP_MIN",
    "ENCOUNTER_THRESHOLD",
    "EncounterAdvance",
    "EncounterSystem",
]
