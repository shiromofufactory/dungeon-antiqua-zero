"""Convert active game state to versioned JSON and persist save slots."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

if __package__ == "systems":
    from field import FieldPosition
    from input import Direction
    from member import (
        BATTLE_PARTY_MEMBER_COUNT,
        FIORA_CHARACTER_KEY,
        MAX_PARTY_MEMBER_COUNT,
        EquipmentSlot,
        Member,
        ProficiencyKind,
    )
    from state import SaveData
    from systems.inventory import InventorySystem
else:
    from ..field import FieldPosition
    from ..input import Direction
    from ..member import (
        BATTLE_PARTY_MEMBER_COUNT,
        FIORA_CHARACTER_KEY,
        MAX_PARTY_MEMBER_COUNT,
        EquipmentSlot,
        Member,
        ProficiencyKind,
    )
    from ..state import SaveData
    from .inventory import InventorySystem


SAVE_FORMAT_VERSION = 1
SAVE_SLOT_COUNT = 8
SAVE_DIRECTORY = Path.home() / ".config" / ".pyxel" / "dungeon-antiqua-zero"
MAX_SAVE_GOLD = 999_999


class SaveSystemError(RuntimeError):
    """Raised when a save document cannot be created or persisted safely."""


@dataclass(frozen=True)
class SaveSlotSummary:
    """Small preview read from one slot without restoring gameplay state."""

    slot: int
    occupied: bool
    saved_at: str | None = None
    party_character_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_slot(self.slot)
        if not isinstance(self.occupied, bool):
            raise TypeError("occupied must be a boolean")
        if self.saved_at is not None and (
            not isinstance(self.saved_at, str) or not self.saved_at
        ):
            raise TypeError("saved_at must be a non-empty string or None")
        if not isinstance(self.party_character_keys, tuple) or not all(
            isinstance(key, str) and key for key in self.party_character_keys
        ):
            raise TypeError(
                "party_character_keys must be a tuple of non-empty strings"
            )
        if len(set(self.party_character_keys)) != len(self.party_character_keys):
            raise ValueError("party_character_keys must not contain duplicates")
        if len(self.party_character_keys) > MAX_PARTY_MEMBER_COUNT:
            raise ValueError("party_character_keys exceeds the member limit")
        if not self.occupied and (
            self.saved_at is not None or self.party_character_keys
        ):
            raise ValueError("an empty save slot cannot contain preview values")


def create_save_document(
    *,
    save_data: SaveData,
    active_party: Sequence[Member],
    character_states: Mapping[str, Member],
    inventory: InventorySystem,
    map_id: str,
    position: FieldPosition,
    facing: Direction,
    saved_at: datetime | None = None,
) -> dict[str, object]:
    """Create one complete version-1 save document from explicit state owners."""

    if not isinstance(save_data, SaveData):
        raise TypeError("save_data must be SaveData")
    if isinstance(active_party, (str, bytes)) or not isinstance(
        active_party, Sequence
    ):
        raise TypeError("active_party must be a sequence of Member values")
    if not active_party or not all(
        isinstance(member, Member) for member in active_party
    ):
        raise TypeError("active_party must contain at least one Member")
    if not isinstance(character_states, Mapping):
        raise TypeError("character_states must be a mapping")
    if not isinstance(inventory, InventorySystem):
        raise TypeError("inventory must be an InventorySystem")
    if not isinstance(map_id, str) or not map_id:
        raise ValueError("map_id must be a non-empty string")
    if not isinstance(position, FieldPosition):
        raise TypeError("position must be a FieldPosition")
    if position.x < 0 or position.y < 0:
        raise ValueError("save position must not be negative")
    if not isinstance(facing, Direction):
        raise TypeError("facing must be a Direction")

    active_keys = tuple(member.definition.key for member in active_party)
    if len(active_party) > MAX_PARTY_MEMBER_COUNT:
        raise SaveSystemError("active party exceeds the member limit")
    if len(set(active_keys)) != len(active_keys):
        raise SaveSystemError("active party contains a duplicate character")
    if FIORA_CHARACTER_KEY not in active_keys:
        raise SaveSystemError("active party must contain Fiora")
    battle_party = active_party[:BATTLE_PARTY_MEMBER_COUNT]
    if not any(member.is_front_row for member in battle_party):
        raise SaveSystemError("battle party must contain a front-row member")
    if (
        len(active_party) > BATTLE_PARTY_MEMBER_COUNT
        and not active_party[-1].is_front_row
    ):
        raise SaveSystemError("reserve party member must be in the front row")
    if save_data.gold > MAX_SAVE_GOLD:
        raise SaveSystemError(f"gold must not exceed {MAX_SAVE_GOLD}")
    if not all(
        isinstance(key, str)
        and key
        and isinstance(member, Member)
        and member.definition.key == key
        for key, member in character_states.items()
    ):
        raise TypeError(
            "character_states must map each character key to its matching Member"
        )
    missing_keys = set(active_keys) - set(character_states)
    if missing_keys:
        raise SaveSystemError(
            f"active party characters are missing from saved states: {missing_keys}"
        )
    inventory.validate_total_quantities(character_states.values())

    timestamp = datetime.now().astimezone() if saved_at is None else saved_at
    if not isinstance(timestamp, datetime):
        raise TypeError("saved_at must be a datetime or None")
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("saved_at must include a UTC offset")

    serialized_states = {
        key: _serialize_member(character_states[key])
        for key in sorted(character_states)
    }
    recorded_item_keys = {item.key for item in inventory.recorded_items}
    recorded_item_keys.update(
        item.key
        for member in character_states.values()
        for item in member.equipment.equipped_items()
    )

    return {
        "format_version": SAVE_FORMAT_VERSION,
        "saved_at": timestamp.isoformat(timespec="seconds"),
        "progress": {
            "gold": save_data.gold,
            "experience": save_data.experience,
            "battle_count": save_data.battle_count,
            "difficulty": save_data.difficulty.value,
            "play_time_frames": save_data.play_time_frames,
        },
        "location": {
            "map_id": map_id,
            "x": position.x,
            "y": position.y,
            "facing": facing.name.lower(),
        },
        "party": {
            "active_character_keys": list(active_keys),
            "character_states": serialized_states,
        },
        "inventory": {
            "quantities": {
                key: quantity
                for key, quantity in sorted(inventory.quantities.items())
                if quantity > 0
            },
            "recorded_item_keys": sorted(recorded_item_keys),
        },
        "event_flags": sorted(save_data.event_flags),
        "visited_site_ids": sorted(save_data.visited_site_ids),
        "opened_treasures": _serialize_opened_treasures(
            save_data.opened_treasures
        ),
        "monster_records": _serialize_monster_records(save_data.monster_records),
        "logs": _serialize_logs(save_data.logs),
    }


def _serialize_member(member: Member) -> dict[str, object]:
    equipment: dict[str, str | None] = {}
    for slot in EquipmentSlot:
        item = member.equipment.item_at(slot)
        equipment[slot.value] = None if item is None else item.key
    return {
        "internal_level": member.internal_level,
        "hp": member.hp,
        "max_hp": member.max_hp,
        "mp": member.mp,
        "max_mp": member.max_mp,
        "formation_row": member.formation_row.value,
        "poisoned": member.poisoned,
        "paralyzed": member.paralyzed,
        "ability_bonuses": {"strength": 0, "agility": 0, "magic": 0},
        "skill_keys": sorted(skill.key for skill in member.skills),
        "event_spell_keys": [],
        "equipment": equipment,
        "proficiencies": {
            kind.value: {
                "level": member.proficiency(kind).level,
                "progress": member.proficiency(kind).progress,
            }
            for kind in ProficiencyKind
        },
    }


def _serialize_opened_treasures(
    values: Iterable[tuple[str, str]],
) -> list[dict[str, str]]:
    try:
        normalized = set(values)
    except TypeError as error:
        raise TypeError("opened_treasures must contain hashable pairs") from error
    if not all(
        isinstance(value, tuple)
        and len(value) == 2
        and all(isinstance(part, str) and part for part in value)
        for value in normalized
    ):
        raise TypeError("opened_treasures must contain non-empty string pairs")
    return [
        {"map_id": map_id, "treasure_id": treasure_id}
        for map_id, treasure_id in sorted(normalized)
    ]


def _serialize_monster_records(
    records: Mapping[str, Iterable[str]],
) -> dict[str, dict[str, list[str]]]:
    if not all(isinstance(key, str) and key for key in records):
        raise TypeError("monster record keys must be non-empty strings")
    serialized: dict[str, dict[str, list[str]]] = {}
    for monster_key in sorted(records):
        fields = records[monster_key]
        if isinstance(fields, (str, bytes)):
            raise TypeError("revealed monster fields must be an iterable of strings")
        try:
            field_keys = tuple(fields)
        except TypeError as error:
            raise TypeError(
                "revealed monster fields must be an iterable of strings"
            ) from error
        if not all(isinstance(field, str) and field for field in field_keys):
            raise TypeError("revealed monster fields must be non-empty strings")
        serialized[monster_key] = {"revealed_field_keys": sorted(set(field_keys))}
    return serialized


def _serialize_logs(logs: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    if isinstance(logs, (str, bytes)) or not isinstance(logs, Sequence):
        raise TypeError("logs must be a sequence")
    if len(logs) > 20:
        raise ValueError("logs must contain at most 20 entries")
    serialized: list[dict[str, object]] = []
    for entry in logs:
        if not isinstance(entry, Mapping):
            raise TypeError("each log must be an object")
        text_key = entry.get("text_key")
        arguments = entry.get("arguments")
        if not isinstance(text_key, str) or not text_key:
            raise TypeError("log.text_key must be a non-empty string")
        if not isinstance(arguments, Mapping) or not all(
            isinstance(key, str)
            and key
            and (
                value is None
                or isinstance(value, (str, int, bool))
            )
            for key, value in arguments.items()
        ):
            raise TypeError("log.arguments contains an unsupported value")
        serialized.append(
            {"text_key": text_key, "arguments": dict(sorted(arguments.items()))}
        )
    return serialized


class SaveRepository:
    """Persist save documents and expose preview-only slot summaries."""

    def __init__(self, directory: Path = SAVE_DIRECTORY) -> None:
        if not isinstance(directory, Path):
            raise TypeError("save directory must be a pathlib.Path")
        self.directory = directory

    def slot_path(self, slot: int) -> Path:
        _validate_slot(slot)
        return self.directory / f"save{slot}.json"

    def summaries(self) -> tuple[SaveSlotSummary, ...]:
        return tuple(self.summary(slot) for slot in range(1, SAVE_SLOT_COUNT + 1))

    def summary(self, slot: int) -> SaveSlotSummary:
        path = self.slot_path(slot)
        if not path.is_file():
            return SaveSlotSummary(slot, occupied=False)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            return self._document_summary(slot, document)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return SaveSlotSummary(slot, occupied=True)

    def save(self, slot: int, document: Mapping[str, object]) -> SaveSlotSummary:
        path = self.slot_path(slot)
        if not isinstance(document, Mapping):
            raise TypeError("save document must be a mapping")
        if document.get("format_version") != SAVE_FORMAT_VERSION:
            raise SaveSystemError("save document has an unsupported format version")
        try:
            expected_summary = self._document_summary(slot, document)
        except ValueError as error:
            raise SaveSystemError("save document has no valid slot preview") from error

        try:
            serialized = json.dumps(
                document,
                ensure_ascii=False,
                indent=2,
            ) + "\n"
        except (TypeError, ValueError) as error:
            raise SaveSystemError("save document is not JSON serializable") from error

        temporary_path = path.with_suffix(".json.tmp")
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary_path.write_text(serialized, encoding="utf-8")
            temporary_path.replace(path)
        except OSError as error:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise SaveSystemError(f"failed to write save slot {slot}") from error

        return expected_summary

    @staticmethod
    def _document_summary(
        slot: int,
        document: object,
    ) -> SaveSlotSummary:
        if (
            not isinstance(document, Mapping)
            or document.get("format_version") != SAVE_FORMAT_VERSION
        ):
            raise ValueError("unsupported save preview")
        saved_at = document.get("saved_at")
        party = document.get("party")
        if not isinstance(party, Mapping):
            raise ValueError("invalid save preview")
        active_keys = party.get("active_character_keys")
        if (
            not isinstance(saved_at, str)
            or not saved_at
            or not isinstance(active_keys, list)
            or not active_keys
            or len(active_keys) > MAX_PARTY_MEMBER_COUNT
            or not all(isinstance(key, str) and key for key in active_keys)
            or len(set(active_keys)) != len(active_keys)
        ):
            raise ValueError("invalid save preview")
        try:
            timestamp = datetime.fromisoformat(saved_at)
        except ValueError as error:
            raise ValueError("invalid save timestamp") from error
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("save timestamp must include a UTC offset")
        return SaveSlotSummary(slot, True, saved_at, tuple(active_keys))


def _validate_slot(slot: int) -> None:
    if isinstance(slot, bool) or not isinstance(slot, int):
        raise TypeError("save slot must be an integer")
    if not 1 <= slot <= SAVE_SLOT_COUNT:
        raise ValueError(f"save slot must be from 1 to {SAVE_SLOT_COUNT}")


__all__ = [
    "SAVE_DIRECTORY",
    "SAVE_FORMAT_VERSION",
    "SAVE_SLOT_COUNT",
    "SaveRepository",
    "SaveSlotSummary",
    "SaveSystemError",
    "create_save_document",
]
