"""Reusable game-state fixtures for screen mocks."""

from __future__ import annotations

from tools._bootstrap import APP_ROOT
from item import Item
from member import FormationRow, Member, MemberDataError
from resources import load_record_array
from skill import Skill
from shop import Shop
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


class MockFixtureError(RuntimeError):
    """Raised when shared mock fixture data is missing or ambiguous."""


def load_mock_character_records() -> tuple[dict[str, object], ...]:
    """Load character records in their stable shared-data order."""

    return tuple(load_record_array("characters.json", APP_ROOT / "data"))


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


def load_mock_spells() -> dict[str, Spell]:
    """Load and index spell models by their stable current data keys."""

    spells: dict[str, Spell] = {}
    for record in load_record_array("spells.json", APP_ROOT / "data"):
        spell = Spell.from_record(record)
        if spell.key in spells:
            raise MockFixtureError(f"呪文キーが重複しています: {spell.key}")
        spells[spell.key] = spell
    return spells


def load_mock_shops(items: dict[str, Item]) -> tuple[Shop, ...]:
    """Load shops in shared-data order and resolve their fixed products."""

    shops: list[Shop] = []
    seen: set[str] = set()
    for record in load_record_array("shops.json", APP_ROOT / "data"):
        shop = Shop.from_record(record, items)
        if shop.key in seen:
            raise MockFixtureError(f"ショップキーが重複しています: {shop.key}")
        seen.add(shop.key)
        shops.append(shop)
    if not shops:
        raise MockFixtureError("ショップデータがありません")
    return tuple(shops)


def load_mock_party(
    items: dict[str, Item],
    skills: dict[str, Skill],
) -> tuple[Member, ...]:
    """Build the shared ordered party from generated character data."""

    records_by_key = {
        key: record
        for record in load_mock_character_records()
        if isinstance(key := record.get("name_en"), str)
    }
    party: list[Member] = []
    for key in MOCK_PARTY_CHARACTER_KEYS:
        record = records_by_key.get(key)
        if record is None:
            raise MemberDataError(f"モック用キャラクターが見つかりません: {key}")
        member = Member.from_record(record, items=items, skills=skills)
        if key in MOCK_BACK_ROW_CHARACTER_KEYS:
            member.formation_row = FormationRow.BACK
        party.append(member)
    return tuple(party)


__all__ = [
    "MOCK_PARTY_CHARACTER_KEYS",
    "MOCK_BACK_ROW_CHARACTER_KEYS",
    "MockFixtureError",
    "load_mock_character_records",
    "load_mock_items",
    "load_mock_party",
    "load_mock_skills",
    "load_mock_shops",
    "load_mock_spells",
]
