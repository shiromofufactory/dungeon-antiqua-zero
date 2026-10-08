"""Load and connect the generated master data used by a game session."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from item import Item
from member import (
    FIORA_CHARACTER_KEY,
    MIN_INTERNAL_LEVEL,
    FormationRow,
    Member,
    MemberDataError,
    required_experience_for_level,
)
from monster import MonsterDefinition
from resources import load_record_array
from shop import Shop
from skill import Skill
from spell import Spell


class GameDataError(RuntimeError):
    """Raised when generated master data is missing or ambiguous."""


def load_character_records() -> tuple[dict[str, object], ...]:
    """Load character records in their stable shared-data order."""

    return tuple(load_record_array("characters.json"))


def load_monsters() -> tuple[MonsterDefinition, ...]:
    """Load monsters in the stable master order used by the bestiary."""

    monsters: list[MonsterDefinition] = []
    seen: set[str] = set()
    for record in load_record_array("monsters.json"):
        monster = MonsterDefinition.from_record(record)
        if monster.key in seen:
            raise GameDataError(f"モンスターキーが重複しています: {monster.key}")
        seen.add(monster.key)
        monsters.append(monster)
    if not monsters:
        raise GameDataError("モンスターデータがありません")
    return tuple(monsters)


def load_items() -> dict[str, Item]:
    """Load and index item models by their stable current data keys."""

    items: dict[str, Item] = {}
    for record in load_record_array("items.json"):
        item = Item.from_record(record)
        if item.key in items:
            raise GameDataError(f"アイテムキーが重複しています: {item.key}")
        items[item.key] = item
    return items


def load_skills() -> dict[str, Skill]:
    """Load and index skill models by their stable current data keys."""

    skills: dict[str, Skill] = {}
    for record in load_record_array("skills.json"):
        skill = Skill.from_record(record)
        if skill.key in skills:
            raise GameDataError(f"スキルキーが重複しています: {skill.key}")
        skills[skill.key] = skill
    return skills


def load_spells() -> dict[str, Spell]:
    """Load and index spell models by their stable current data keys."""

    spells: dict[str, Spell] = {}
    for record in load_record_array("spells.json"):
        spell = Spell.from_record(record)
        if spell.key in spells:
            raise GameDataError(f"呪文キーが重複しています: {spell.key}")
        spells[spell.key] = spell
    return spells


def load_shops(items: dict[str, Item]) -> tuple[Shop, ...]:
    """Load shops in shared-data order and resolve their fixed products."""

    shops: list[Shop] = []
    seen: set[str] = set()
    for record in load_record_array("shops.json"):
        shop = Shop.from_record(record, items)
        if shop.key in seen:
            raise GameDataError(f"ショップキーが重複しています: {shop.key}")
        seen.add(shop.key)
        shops.append(shop)
    if not shops:
        raise GameDataError("ショップデータがありません")
    return tuple(shops)


def create_party(
    items: dict[str, Item],
    skills: dict[str, Skill],
    *,
    character_keys: Iterable[str],
    back_row_character_keys: Iterable[str] = (),
    internal_level: int | None = None,
    fiora_internal_level: int = MIN_INTERNAL_LEVEL,
) -> tuple[Member, ...]:
    """Create an ordered party from generated character data.

    ``internal_level`` is for explicit-state fixtures, restoration, and debug
    tools.  Normal party creation leaves it as ``None`` and uses each
    character's joining-level rule. ``fiora_internal_level`` selects the new
    game's starting party level while preserving Fiora's initial proficiencies.
    """

    requested_keys = tuple(character_keys)
    if not requested_keys or not all(
        isinstance(key, str) and key for key in requested_keys
    ):
        raise ValueError("character_keys must contain non-empty strings")
    if len(requested_keys) != len(set(requested_keys)):
        raise ValueError("character_keys must be unique")
    back_row_keys = frozenset(back_row_character_keys)
    if not all(isinstance(key, str) and key for key in back_row_keys):
        raise ValueError("back_row_character_keys must contain non-empty strings")

    records_by_key = {
        key: record
        for record in load_character_records()
        if isinstance(key := record.get("name_en"), str)
    }
    party: list[Member] = []
    for key in requested_keys:
        record = records_by_key.get(key)
        if record is None:
            raise MemberDataError(f"キャラクターが見つかりません: {key}")
        if internal_level is None:
            member = Member.from_record(
                record, items=items, skills=skills,
                fiora_internal_level=fiora_internal_level,
            )
            if (
                key == FIORA_CHARACTER_KEY
                and fiora_internal_level != MIN_INTERNAL_LEVEL
            ):
                member = replace(
                    member,
                    internal_level=fiora_internal_level,
                    experience_offset=required_experience_for_level(fiora_internal_level),
                    hp=None,
                    max_hp=None,
                    mp=None,
                    max_mp=None,
                )
        else:
            member = Member.from_record_at_internal_level(
                record,
                internal_level,
                items=items,
                skills=skills,
            )
        if key in back_row_keys:
            member.formation_row = FormationRow.BACK
        party.append(member)
    return tuple(party)


__all__ = [
    "GameDataError",
    "create_party",
    "load_character_records",
    "load_items",
    "load_monsters",
    "load_shops",
    "load_skills",
    "load_spells",
]
