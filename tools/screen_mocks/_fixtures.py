"""Reusable game-state fixtures for screen mocks."""

from __future__ import annotations

from tools._bootstrap import APP_ROOT
from item import Item
from member import Member, MemberDataError
from resources import load_record_array
from skill import Skill

MOCK_PARTY_CHARACTER_KEYS = (
    "Fiora",
    "Cerion",
    "Alvan",
    "Elika",
    "Ragna",
)


class MockFixtureError(RuntimeError):
    """Raised when shared mock fixture data is missing or ambiguous."""


def load_mock_items() -> dict[str, Item]:
    """Load and index item models by their stable current data keys."""

    items: dict[str, Item] = {}
    for record in load_record_array("items.json", APP_ROOT / "data"):
        item = Item.from_record(record)
        if item.key in items:
            raise MockFixtureError(f"アイテムキーが重複しています: {item.key}")
        items[item.key] = item
    return items


def load_mock_skills() -> dict[str, Skill]:
    """Load and index skill models by their stable current data keys."""

    skills: dict[str, Skill] = {}
    for record in load_record_array("skills.json", APP_ROOT / "data"):
        skill = Skill.from_record(record)
        if skill.key in skills:
            raise MockFixtureError(f"スキルキーが重複しています: {skill.key}")
        skills[skill.key] = skill
    return skills


def load_mock_party(
    items: dict[str, Item],
    skills: dict[str, Skill],
) -> tuple[Member, ...]:
    """Build the shared ordered party from generated character data."""

    records_by_key = {
        key: record
        for record in load_record_array("characters.json", APP_ROOT / "data")
        if isinstance(key := record.get("name_en"), str)
    }
    party: list[Member] = []
    for key in MOCK_PARTY_CHARACTER_KEYS:
        record = records_by_key.get(key)
        if record is None:
            raise MemberDataError(f"モック用キャラクターが見つかりません: {key}")
        party.append(Member.from_record(record, items=items, skills=skills))
    return tuple(party)


__all__ = [
    "MOCK_PARTY_CHARACTER_KEYS",
    "MockFixtureError",
    "load_mock_items",
    "load_mock_party",
    "load_mock_skills",
]
