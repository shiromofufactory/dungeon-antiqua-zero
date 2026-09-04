from __future__ import annotations

import unittest
from unittest.mock import Mock

from app.resources.maps import (
    MapCell,
    MapDestination,
    MapResources,
    WorldSite,
)
from app.state import SaveData
from app.systems.travel import TravelSystem
from app.world_sites import WorldSiteCatalog


def site(
    site_id: str,
    entrances: tuple[MapCell, ...],
) -> WorldSite:
    return WorldSite(
        id=site_id,
        name_text_key=f"location.{site_id}",
        entrance_cells=entrances,
        destination=MapDestination(site_id, "from_world"),
    )


class WorldSiteCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.village = site(
            "sample_village",
            (MapCell(2, 2), MapCell(3, 2), MapCell(2, 3), MapCell(3, 3)),
        )
        self.cave = site("sample_cave", (MapCell(8, 8),))
        self.catalog = WorldSiteCatalog((self.village, self.cave))

    def test_finds_entrance_and_nearest_site_name(self) -> None:
        self.assertIs(self.catalog.entrance_at(3, 3), self.village)
        self.assertIsNone(self.catalog.entrance_at(4, 4))
        self.assertIs(self.catalog.nearby_site(4, 3), self.village)
        self.assertIsNone(self.catalog.nearby_site(5, 3))

    def test_filters_teleport_candidates_in_catalog_order(self) -> None:
        self.assertEqual(
            self.catalog.visited_sites({"sample_cave", "unknown"}),
            (self.cave,),
        )


class TravelSystemTest(unittest.TestCase):
    def test_remembers_entry_and_resolves_teleport_destination(self) -> None:
        village = site("sample_village", (MapCell(2, 2),))
        catalog = WorldSiteCatalog((village,))
        map_resources = Mock(spec=MapResources)
        map_resources.teleport_destination.return_value = MapDestination(
            "worldmap",
            "sample_village_world",
        )
        travel = TravelSystem(catalog, map_resources)
        save_data = SaveData()

        destination = travel.enter_site(save_data, village)

        self.assertEqual(destination, MapDestination("sample_village", "from_world"))
        self.assertEqual(save_data.visited_site_ids, {"sample_village"})
        self.assertEqual(travel.teleport_destinations(save_data), (village,))
        self.assertEqual(
            travel.teleport_destination(save_data, "sample_village"),
            MapDestination("worldmap", "sample_village_world"),
        )

        map_resources.teleport_destination.side_effect = KeyError(
            "sample_village"
        )
        self.assertEqual(travel.teleport_destinations(save_data), ())
        with self.assertRaisesRegex(ValueError, "not a teleport destination"):
            travel.teleport_destination(save_data, "sample_village")


if __name__ == "__main__":
    unittest.main()
