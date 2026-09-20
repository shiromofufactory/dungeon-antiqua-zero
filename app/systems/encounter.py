"""Random encounter progress, formation, and dungeon-defeat return rules."""

from __future__ import annotations

from dataclasses import dataclass
import random

if __package__ == "systems":
    from field import FieldPosition
    from input import Direction
    from monster import MonsterDefinition, MonsterTribe
    from resistance import ResistanceType
    from resources.maps import CompiledMap, MapRandomEncounter
else:
    from ..field import FieldPosition
    from ..input import Direction
    from ..monster import MonsterDefinition, MonsterTribe
    from ..resistance import ResistanceType
    from ..resources.maps import CompiledMap, MapRandomEncounter


ENCOUNTER_STEP_MIN = 1
ENCOUNTER_STEP_MAX = 4
ENCOUNTER_THRESHOLD = 120
LOW_DANGER_MAX_ENCOUNTER_MONSTERS = 4
MAX_ENCOUNTER_MONSTERS = 5


class EncounterGenerationError(RuntimeError):
    """Raised when map settings leave no monster for the first formation group."""


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


@dataclass(frozen=True)
class EncounterFormation:
    """Ordered monster keys produced for one random battle."""

    monster_keys: tuple[str, ...]


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
    def dynamic_monster_level() -> int:
        """Resolve the provisional dynamic map level."""

        return 1

    def generate_formation(
        self,
        monsters: tuple[MonsterDefinition, ...],
        settings: MapRandomEncounter,
        *,
        monster_level: int,
    ) -> EncounterFormation:
        """Build one weighted, at-most-five-monster random formation."""

        if not isinstance(settings, MapRandomEncounter):
            raise TypeError("encounter settings must be a MapRandomEncounter")
        if not monsters or not all(
            isinstance(monster, MonsterDefinition) for monster in monsters
        ):
            raise TypeError("monsters must contain MonsterDefinition values")
        if (
            isinstance(monster_level, bool)
            or not isinstance(monster_level, int)
            or not 1 <= monster_level <= 9
        ):
            raise ValueError("monster level must be from 1 to 9")

        keys: list[str] = []
        current_level = monster_level
        maximum_monsters = (
            MAX_ENCOUNTER_MONSTERS
            if settings.danger == "high"
            else LOW_DANGER_MAX_ENCOUNTER_MONSTERS
        )
        while True:
            weighted_pool = self._weighted_pool(
                monsters,
                settings,
                current_level,
            )
            if not weighted_pool:
                if not keys:
                    raise EncounterGenerationError(
                        "random encounter settings have no eligible monsters"
                    )
                break

            selected = self._weighted_choice(weighted_pool)
            maximum = selected.max_occurrence
            if settings.danger == "low":
                maximum = (maximum + 1) // 2
            occurrence = self._random.randint(1, maximum)
            if len(keys) + occurrence > maximum_monsters:
                break

            keys.extend((selected.key,) * occurrence)

            remaining = maximum_monsters - len(keys)
            if remaining < self._random.randint(1, maximum_monsters):
                break
            if self._random.randrange(2) == 0:
                current_level = max(1, current_level - 1)

        return EncounterFormation(tuple(keys))

    def _weighted_pool(
        self,
        monsters: tuple[MonsterDefinition, ...],
        settings: MapRandomEncounter,
        monster_level: int,
    ) -> tuple[tuple[MonsterDefinition, int], ...]:
        pool: list[tuple[MonsterDefinition, int]] = []
        included_keys: set[str] = set()
        for monster in monsters:
            level_matches = monster.level == monster_level
            early_matches = (
                settings.danger == "high"
                and monster.level == monster_level + 1
                and monster.early_appear
            )
            if not (level_matches or early_matches):
                continue
            if monster.key in included_keys:
                continue
            if not settings.allow_demons and monster.tribe is MonsterTribe.DEMON:
                continue
            if not settings.allow_humans and monster.tribe in (
                MonsterTribe.HUMAN,
                MonsterTribe.MAGE,
            ):
                continue
            if not settings.allow_giants and monster.tribe is MonsterTribe.GIANT:
                continue
            if not settings.allow_large_animals and monster.is_large_animal:
                continue

            has_fire_weakness = ResistanceType.FIRE in monster.weaknesses
            has_freeze_weakness = ResistanceType.FREEZE in monster.weaknesses
            if settings.polarity == "yang" and has_fire_weakness:
                continue
            if settings.polarity == "yin" and has_freeze_weakness:
                continue
            weight = (
                1
                if settings.polarity == "neutral"
                and (has_fire_weakness or has_freeze_weakness)
                else 2
            )
            pool.append((monster, weight))
            included_keys.add(monster.key)
        return tuple(pool)

    def _weighted_choice(
        self,
        pool: tuple[tuple[MonsterDefinition, int], ...],
    ) -> MonsterDefinition:
        target = self._random.randrange(sum(weight for _monster, weight in pool))
        for monster, weight in pool:
            if target < weight:
                return monster
            target -= weight
        raise AssertionError("weighted monster pool selection fell through")

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
    "EncounterFormation",
    "EncounterGenerationError",
    "EncounterSystem",
    "LOW_DANGER_MAX_ENCOUNTER_MONSTERS",
    "MAX_ENCOUNTER_MONSTERS",
]
