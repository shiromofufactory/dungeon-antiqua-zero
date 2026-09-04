"""Query immutable world-site definitions by cell and visit state."""

from __future__ import annotations

from types import MappingProxyType
from typing import Iterable, Mapping

if __package__:
    from .resources.maps import WorldSite
else:
    from resources.maps import WorldSite


SITE_NAME_DISTANCE = 2


class WorldSiteCatalog:
    """Index one world map's sites without owning save or UI state."""

    def __init__(self, sites: Iterable[WorldSite]) -> None:
        if isinstance(sites, (str, bytes, Mapping)):
            raise TypeError("world sites must be an iterable of WorldSite values")
        by_id: dict[str, WorldSite] = {}
        by_entrance: dict[tuple[int, int], WorldSite] = {}
        ordered = []
        for site in sites:
            if not isinstance(site, WorldSite):
                raise TypeError("world sites must contain WorldSite values")
            if site.id in by_id:
                raise ValueError(f"duplicate world site ID: {site.id}")
            by_id[site.id] = site
            ordered.append(site)
            for cell in site.entrance_cells:
                point = (cell.x, cell.y)
                if point in by_entrance:
                    raise ValueError(f"duplicate world site entrance: {point}")
                by_entrance[point] = site
        self.sites = tuple(ordered)
        self._by_id = MappingProxyType(by_id)
        self._by_entrance = MappingProxyType(by_entrance)

    def site(self, site_id: str) -> WorldSite:
        if not isinstance(site_id, str) or not site_id:
            raise ValueError("world site ID must be a non-empty string")
        try:
            return self._by_id[site_id]
        except KeyError as error:
            raise KeyError(f"unknown world site: {site_id}") from error

    def entrance_at(self, x: int, y: int) -> WorldSite | None:
        self._validate_cell(x, y)
        return self._by_entrance.get((x, y))

    def nearby_site(
        self,
        x: int,
        y: int,
        *,
        maximum_distance: int = SITE_NAME_DISTANCE,
    ) -> WorldSite | None:
        self._validate_cell(x, y)
        if (
            isinstance(maximum_distance, bool)
            or not isinstance(maximum_distance, int)
            or maximum_distance < 0
        ):
            raise ValueError("site distance must be a non-negative integer")
        candidates = (
            (
                min(
                    abs(x - cell.x) + abs(y - cell.y)
                    for cell in site.entrance_cells
                ),
                site.id,
                site,
            )
            for site in self.sites
        )
        return next(
            (
                site
                for distance, _site_id, site in sorted(candidates)
                if distance <= maximum_distance
            ),
            None,
        )

    def visited_sites(self, site_ids: Iterable[str]) -> tuple[WorldSite, ...]:
        if isinstance(site_ids, (str, bytes, Mapping)):
            raise TypeError("visited site IDs must be an iterable of strings")
        visited = set(site_ids)
        if not all(isinstance(site_id, str) for site_id in visited):
            raise TypeError("visited site IDs must contain strings")
        return tuple(site for site in self.sites if site.id in visited)

    @staticmethod
    def _validate_cell(x: int, y: int) -> None:
        if (
            isinstance(x, bool)
            or not isinstance(x, int)
            or isinstance(y, bool)
            or not isinstance(y, int)
        ):
            raise TypeError("world site cell coordinates must be integers")


__all__ = ["SITE_NAME_DISTANCE", "WorldSiteCatalog"]
