"""Coordinate world-site visits and destination references."""

from __future__ import annotations

if __package__ == "systems":
    from resources.maps import MapDestination, MapResources, WorldSite
    from state import SaveData
    from world_sites import WorldSiteCatalog
else:
    from ..resources.maps import MapDestination, MapResources, WorldSite
    from ..state import SaveData
    from ..world_sites import WorldSiteCatalog


class TravelSystem:
    """Resolve site entry and teleport references from stable site IDs."""

    def __init__(
        self,
        sites: WorldSiteCatalog,
        map_resources: MapResources,
    ) -> None:
        if not isinstance(sites, WorldSiteCatalog):
            raise TypeError("travel sites must be a WorldSiteCatalog")
        if not all(
            callable(getattr(map_resources, name, None))
            for name in ("map", "teleport_destination")
        ):
            raise TypeError("travel map resources must be MapResources")
        self.sites = sites
        self.map_resources = map_resources

    def enter_site(self, save_data: SaveData, site: WorldSite) -> MapDestination:
        self._validate_save(save_data)
        if not isinstance(site, WorldSite):
            raise TypeError("entered site must be a WorldSite")
        registered = self.sites.site(site.id)
        if registered is not site and registered != site:
            raise ValueError("entered site does not belong to this world catalog")
        save_data.remember_site(site.id)
        return site.destination

    def teleport_destinations(self, save_data: SaveData) -> tuple[WorldSite, ...]:
        self._validate_save(save_data)
        return tuple(
            site
            for site in self.sites.visited_sites(save_data.visited_site_ids)
            if self._has_teleport_destination(site.id)
        )

    def teleport_destination(
        self,
        save_data: SaveData,
        site_id: str,
    ) -> MapDestination:
        """Return the arrival reference for one visited teleport target."""

        self._validate_save(save_data)
        if site_id not in save_data.visited_site_ids:
            raise ValueError(f"world site has not been visited: {site_id}")
        self.sites.site(site_id)
        try:
            return self.map_resources.teleport_destination(site_id)
        except KeyError as error:
            raise ValueError(
                f"world site is not a teleport destination: {site_id}"
            ) from error

    def _has_teleport_destination(self, site_id: str) -> bool:
        try:
            self.map_resources.teleport_destination(site_id)
        except KeyError:
            return False
        return True

    @staticmethod
    def _validate_save(save_data: SaveData) -> None:
        if not isinstance(save_data, SaveData):
            raise TypeError("travel save data must be SaveData")


__all__ = ["TravelSystem"]
