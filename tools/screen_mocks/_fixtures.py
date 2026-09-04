"""Reusable game-state fixtures for standalone screen mocks."""

from __future__ import annotations

from game_data import (
    create_party,
    load_character_records,
    load_items,
    load_shops,
    load_skills,
    load_spells,
)
from item import Item
from member import Member
from shop import Shop
from skill import Skill
from spell import Spell

MOCK_PARTY_CHARACTER_KEYS = (
    "Fiora",
    "Cerion",
    "Alvan",
    "Elika",
    "Ragna",
    "Dain",
)
MOCK_BACK_ROW_CHARACTER_KEYS = frozenset(("Cerion", "Elika"))


def load_mock_character_records() -> tuple[dict[str, object], ...]:
    """Load character records in their stable shared-data order."""

    return load_character_records()


def load_mock_items() -> dict[str, Item]:
    """Load and index item models by their stable current data keys."""

    return load_items()


def load_mock_skills() -> dict[str, Skill]:
    """Load and index skill models by their stable current data keys."""

    return load_skills()


def load_mock_spells() -> dict[str, Spell]:
    """Load and index spell models by their stable current data keys."""

    return load_spells()


def load_mock_shops(items: dict[str, Item]) -> tuple[Shop, ...]:
    """Load shops in shared-data order and resolve their fixed products."""

    return load_shops(items)


def load_mock_party(
    items: dict[str, Item],
    skills: dict[str, Skill],
    *,
    character_keys: tuple[str, ...] = MOCK_PARTY_CHARACTER_KEYS,
) -> tuple[Member, ...]:
    """Build the shared ordered party from generated character data."""

    return create_party(
        items,
        skills,
        character_keys=character_keys,
        back_row_character_keys=MOCK_BACK_ROW_CHARACTER_KEYS,
    )


__all__ = [
    "MOCK_PARTY_CHARACTER_KEYS",
    "MOCK_BACK_ROW_CHARACTER_KEYS",
    "load_mock_character_records",
    "load_mock_items",
    "load_mock_party",
    "load_mock_skills",
    "load_mock_shops",
    "load_mock_spells",
]
