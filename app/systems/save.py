"""Convert active game state to versioned JSON and persist save slots."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path

if __package__ == "systems":
    from battle_command_memory import BattleCommandMemory
    from battle_commands import BattleCommand
    from field import FieldPosition
    from input import Direction
    from member import (
        BATTLE_PARTY_MEMBER_COUNT,
        FIORA_CHARACTER_KEY,
        MAX_PARTY_MEMBER_COUNT,
        EquipmentSet,
        EquipmentSlot,
        FormationRow,
        Member,
        Proficiency,
        ProficiencyKind,
        required_experience_for_level,
    )
    from state import Difficulty, SaveData
    from systems.inventory import InventorySystem
else:
    from ..battle_command_memory import BattleCommandMemory
    from ..battle_commands import BattleCommand
    from ..field import FieldPosition
    from ..input import Direction
    from ..member import (
        BATTLE_PARTY_MEMBER_COUNT,
        FIORA_CHARACTER_KEY,
        MAX_PARTY_MEMBER_COUNT,
        EquipmentSet,
        EquipmentSlot,
        FormationRow,
        Member,
        Proficiency,
        ProficiencyKind,
        required_experience_for_level,
    )
    from ..state import Difficulty, SaveData
    from .inventory import InventorySystem


SAVE_FORMAT_VERSION = 2
SUPPORTED_SAVE_FORMAT_VERSIONS = frozenset((1, SAVE_FORMAT_VERSION))
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
    dead_character_keys: tuple[str, ...] = ()

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
        if not isinstance(self.dead_character_keys, tuple) or not all(
            isinstance(key, str) and key for key in self.dead_character_keys
        ):
            raise TypeError(
                "dead_character_keys must be a tuple of non-empty strings"
            )
        if len(set(self.dead_character_keys)) != len(self.dead_character_keys):
            raise ValueError("dead_character_keys must not contain duplicates")
        if not set(self.dead_character_keys).issubset(self.party_character_keys):
            raise ValueError("dead_character_keys must belong to the active party")
        if not self.occupied and (
            self.saved_at is not None
            or self.party_character_keys
            or self.dead_character_keys
        ):
            raise ValueError("an empty save slot cannot contain preview values")


@dataclass(frozen=True)
class LoadedGameState:
    """Fully validated gameplay state reconstructed from one save document."""

    save_data: SaveData
    active_party: tuple[Member, ...]
    character_states: dict[str, Member]
    inventory: InventorySystem
    map_id: str
    position: FieldPosition
    facing: Direction
    battle_command_memory: BattleCommandMemory = field(
        default_factory=BattleCommandMemory
    )


def restore_save_document(
    document: Mapping[str, object],
    *,
    character_records: Sequence[Mapping[str, object]],
    items: Mapping[str, object],
    skills: Mapping[str, object],
) -> LoadedGameState:
    """Validate and reconstruct a supported save version without mutation."""

    if not isinstance(document, Mapping):
        raise TypeError("save document must be a mapping")
    format_version = document.get("format_version")
    if format_version not in SUPPORTED_SAVE_FORMAT_VERSIONS:
        raise SaveSystemError("save document has an unsupported format version")
    if isinstance(character_records, (str, bytes)) or not isinstance(
        character_records, Sequence
    ):
        raise TypeError("character_records must be a sequence")

    saved_at = _required_string(document, "saved_at", "save")
    try:
        timestamp = datetime.fromisoformat(saved_at)
    except ValueError as error:
        raise SaveSystemError("save document has an invalid timestamp") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise SaveSystemError("save timestamp must include a UTC offset")

    progress = _required_mapping(document, "progress", "save")
    difficulty_value = _required_string(progress, "difficulty", "progress")
    try:
        difficulty = Difficulty(difficulty_value)
    except ValueError as error:
        raise SaveSystemError("save difficulty is unsupported") from error

    save_data = SaveData(
        gold=_non_negative_int(progress, "gold", "progress"),
        experience=_non_negative_int(progress, "experience", "progress"),
        battle_count=_non_negative_int(progress, "battle_count", "progress"),
        encounter_count=_optional_non_negative_int(
            progress,
            "encounter_count",
            "progress",
            default=0,
        ),
        difficulty=difficulty,
        play_time_frames=_non_negative_int(
            progress,
            "play_time_frames",
            "progress",
        ),
        event_flags=_string_set(document.get("event_flags"), "event_flags"),
        visited_site_ids=_string_set(
            document.get("visited_site_ids"),
            "visited_site_ids",
        ),
        opened_treasures=_restore_opened_treasures(
            document.get("opened_treasures")
        ),
        monster_records=_restore_monster_records(
            document.get("monster_records")
        ),
        logs=_restore_logs(document.get("logs")),
    )

    records_by_key: dict[str, Mapping[str, object]] = {}
    for record in character_records:
        if not isinstance(record, Mapping):
            raise TypeError("character_records must contain mappings")
        key = record.get("name_en")
        if not isinstance(key, str) or not key:
            raise SaveSystemError("character data has no stable key")
        if key in records_by_key:
            raise SaveSystemError(f"character data key is duplicated: {key}")
        records_by_key[key] = record

    party_document = _required_mapping(document, "party", "save")
    active_keys = _string_list(
        party_document.get("active_character_keys"),
        "party.active_character_keys",
    )
    if not active_keys:
        raise SaveSystemError("active party must not be empty")
    state_documents = _required_mapping(
        party_document,
        "character_states",
        "party",
    )
    character_states: dict[str, Member] = {}
    for key, state_document in state_documents.items():
        if not isinstance(key, str) or not key:
            raise SaveSystemError("character state keys must be non-empty strings")
        record = records_by_key.get(key)
        if record is None:
            raise SaveSystemError(f"saved character is missing from data: {key}")
        character_states[key] = _restore_member(
            key,
            record,
            state_document,
            items=items,
            skills=skills,
            shared_experience=save_data.experience,
            format_version=format_version,
        )
    try:
        active_party = tuple(character_states[key] for key in active_keys)
    except KeyError as error:
        raise SaveSystemError(
            f"active character has no saved state: {error.args[0]}"
        ) from error

    inventory_document = _required_mapping(document, "inventory", "save")
    quantities = _required_mapping(inventory_document, "quantities", "inventory")
    recorded_keys = _string_list(
        inventory_document.get("recorded_item_keys"),
        "inventory.recorded_item_keys",
    )
    if any(
        isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or quantity <= 0
        for quantity in quantities.values()
    ):
        raise SaveSystemError("inventory quantities must be positive integers")
    inventory = InventorySystem(items, quantities, recorded_keys)
    required_recorded_keys = set(inventory.quantities)
    required_recorded_keys.update(
        item.key
        for member in character_states.values()
        for item in member.equipment.equipped_items()
    )
    missing_recorded_keys = required_recorded_keys - set(recorded_keys)
    if missing_recorded_keys:
        raise SaveSystemError(
            "owned items are missing from recorded_item_keys: "
            f"{sorted(missing_recorded_keys)}"
        )

    location = _required_mapping(document, "location", "save")
    map_id = _required_string(location, "map_id", "location")
    position = FieldPosition(
        _non_negative_int(location, "x", "location"),
        _non_negative_int(location, "y", "location"),
    )
    facing_value = _required_string(location, "facing", "location")
    try:
        facing = Direction[facing_value.upper()]
    except KeyError as error:
        raise SaveSystemError("save facing direction is unsupported") from error

    command_memory = _restore_battle_command_memory(
        document.get("battle_command_memory", {})
    )
    # Reuse the writer's aggregate invariants after every value has been restored.
    create_save_document(
        save_data=save_data,
        active_party=active_party,
        character_states=character_states,
        inventory=inventory,
        map_id=map_id,
        position=position,
        facing=facing,
        saved_at=timestamp,
        battle_command_memory=command_memory,
    )
    return LoadedGameState(
        save_data=save_data,
        active_party=active_party,
        character_states=character_states,
        inventory=inventory,
        map_id=map_id,
        position=position,
        facing=facing,
        battle_command_memory=command_memory,
    )


def _restore_member(
    key: str,
    record: Mapping[str, object],
    value: object,
    *,
    items: Mapping[str, object],
    skills: Mapping[str, object],
    shared_experience: int,
    format_version: int,
) -> Member:
    state = _mapping(value, f"party.character_states.{key}")
    internal_level = _non_negative_int(state, "internal_level", f"member {key}")
    initial = Member.from_record_at_internal_level(
        record,
        internal_level,
        items=items,
        skills=skills,
    )

    skill_keys = _string_list(state.get("skill_keys"), f"member {key}.skill_keys")
    try:
        member_skills = [skills[skill_key] for skill_key in skill_keys]
    except KeyError as error:
        raise SaveSystemError(
            f"saved skill is missing from data: {error.args[0]}"
        ) from error

    equipment_document = _required_mapping(state, "equipment", f"member {key}")
    expected_equipment_keys = {slot.value for slot in EquipmentSlot}
    if set(equipment_document) != expected_equipment_keys:
        raise SaveSystemError(f"member {key} equipment slots are incomplete")
    equipment_keys: dict[EquipmentSlot, str] = {}
    for slot in EquipmentSlot:
        item_key = equipment_document[slot.value]
        if item_key is not None and not isinstance(item_key, str):
            raise SaveSystemError(
                f"member {key} equipment key must be a string or null"
            )
        equipment_keys[slot] = "" if item_key is None else item_key
    equipment = EquipmentSet.from_keys(equipment_keys, items)

    proficiency_document = _required_mapping(
        state,
        "proficiencies",
        f"member {key}",
    )
    if set(proficiency_document) != {kind.value for kind in ProficiencyKind}:
        raise SaveSystemError(f"member {key} proficiencies are incomplete")
    proficiencies: dict[ProficiencyKind, Proficiency] = {}
    for kind in ProficiencyKind:
        current = _mapping(
            proficiency_document[kind.value],
            f"member {key}.proficiencies.{kind.value}",
        )
        proficiencies[kind] = Proficiency(
            initial.definition.proficiency_aptitudes[kind],
            level=_non_negative_int(current, "level", f"member {key} proficiency"),
            progress=_non_negative_int(
                current,
                "progress",
                f"member {key} proficiency",
            ),
        )

    bonuses = _required_mapping(state, "ability_bonuses", f"member {key}")
    if set(bonuses) != {"strength", "agility", "magic"} or any(
        _non_negative_int(bonuses, name, f"member {key} ability bonuses") != 0
        for name in ("strength", "agility", "magic")
    ):
        raise SaveSystemError("non-zero ability bonuses are not supported yet")
    event_spell_keys = _string_list(
        state.get("event_spell_keys"),
        f"member {key}.event_spell_keys",
    )
    if event_spell_keys:
        raise SaveSystemError("event spells are not supported yet")

    formation_value = _required_string(state, "formation_row", f"member {key}")
    try:
        formation_row = FormationRow(formation_value)
    except ValueError as error:
        raise SaveSystemError(f"member {key} formation row is unsupported") from error
    member = Member(
        initial.definition,
        internal_level=internal_level,
        experience_offset=(
            _integer(state, "experience_offset", f"member {key}")
            if format_version >= 2
            else required_experience_for_level(internal_level)
            - shared_experience
        ),
        hp=_non_negative_int(state, "hp", f"member {key}"),
        max_hp=_non_negative_int(state, "max_hp", f"member {key}"),
        mp=_non_negative_int(state, "mp", f"member {key}"),
        max_mp=_non_negative_int(state, "max_mp", f"member {key}"),
        formation_row=formation_row,
        poisoned=_required_bool(state, "poisoned", f"member {key}"),
        paralyzed=_required_bool(state, "paralyzed", f"member {key}"),
        skills=member_skills,
        equipment=equipment,
        proficiencies=proficiencies,
    )
    member.refresh_internal_level(shared_experience)
    return member


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SaveSystemError(f"{label} must be an object")
    return value


def _required_mapping(
    value: Mapping[str, object],
    key: str,
    label: str,
) -> Mapping[str, object]:
    return _mapping(value.get(key), f"{label}.{key}")


def _required_string(value: Mapping[str, object], key: str, label: str) -> str:
    current = value.get(key)
    if not isinstance(current, str) or not current:
        raise SaveSystemError(f"{label}.{key} must be a non-empty string")
    return current


def _required_bool(value: Mapping[str, object], key: str, label: str) -> bool:
    current = value.get(key)
    if not isinstance(current, bool):
        raise SaveSystemError(f"{label}.{key} must be a boolean")
    return current


def _non_negative_int(value: Mapping[str, object], key: str, label: str) -> int:
    current = value.get(key)
    if isinstance(current, bool) or not isinstance(current, int) or current < 0:
        raise SaveSystemError(f"{label}.{key} must be a non-negative integer")
    return current


def _integer(value: Mapping[str, object], key: str, label: str) -> int:
    current = value.get(key)
    if isinstance(current, bool) or not isinstance(current, int):
        raise SaveSystemError(f"{label}.{key} must be an integer")
    return current


def _optional_non_negative_int(
    value: Mapping[str, object],
    key: str,
    label: str,
    *,
    default: int,
) -> int:
    """Restore an additive v1 field while accepting saves written earlier."""

    if key not in value:
        return default
    return _non_negative_int(value, key, label)


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(key, str) and key for key in value
    ):
        raise SaveSystemError(f"{label} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise SaveSystemError(f"{label} must not contain duplicates")
    return value


def _string_set(value: object, label: str) -> set[str]:
    return set(_string_list(value, label))


def _restore_opened_treasures(value: object) -> set[tuple[str, str]]:
    if not isinstance(value, list):
        raise SaveSystemError("opened_treasures must be an array")
    restored: set[tuple[str, str]] = set()
    for index, entry in enumerate(value):
        current = _mapping(entry, f"opened_treasures[{index}]")
        pair = (
            _required_string(current, "map_id", f"opened_treasures[{index}]"),
            _required_string(
                current,
                "treasure_id",
                f"opened_treasures[{index}]",
            ),
        )
        if pair in restored:
            raise SaveSystemError("opened_treasures must not contain duplicates")
        restored.add(pair)
    return restored


def _restore_monster_records(value: object) -> dict[str, set[str]]:
    records = _mapping(value, "monster_records")
    restored: dict[str, set[str]] = {}
    for monster_key, entry in records.items():
        if not isinstance(monster_key, str) or not monster_key:
            raise SaveSystemError("monster record keys must be non-empty strings")
        current = _mapping(entry, f"monster_records.{monster_key}")
        restored[monster_key] = _string_set(
            current.get("revealed_field_keys"),
            f"monster_records.{monster_key}.revealed_field_keys",
        )
    return restored


def _restore_logs(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise SaveSystemError("logs must be an array")
    restored: list[dict[str, object]] = []
    for index, entry in enumerate(value):
        current = _mapping(entry, f"logs[{index}]")
        text_key = current.get("text_key")
        message_id = current.get("message_id")
        if isinstance(message_id, str) and message_id and text_key is None:
            reference = {"message_id": message_id}
        elif isinstance(text_key, str) and text_key and message_id is None:
            reference = {"text_key": text_key}
        else:
            raise SaveSystemError(
                f"logs[{index}] must contain one text_key or message_id"
            )
        arguments = _required_mapping(current, "arguments", f"logs[{index}]")
        if not all(
            isinstance(argument_key, str)
            and argument_key
            and (argument is None or isinstance(argument, (str, int, bool)))
            for argument_key, argument in arguments.items()
        ):
            raise SaveSystemError(f"logs[{index}].arguments contains invalid data")
        restored.append({**reference, "arguments": dict(arguments)})
    return restored


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
    battle_command_memory: BattleCommandMemory | None = None,
) -> dict[str, object]:
    """Create one complete current-version save document from explicit owners."""

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
            "encounter_count": save_data.encounter_count,
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
        "battle_command_memory": _serialize_battle_command_memory(
            BattleCommandMemory()
            if battle_command_memory is None
            else battle_command_memory
        ),
    }


def _restore_battle_command_memory(value: object) -> BattleCommandMemory:
    value = _mapping(value, "battle_command_memory")
    global_command = value.get("global_command")
    if global_command is not None and (
        not isinstance(global_command, str)
        or global_command not in ("fight", "escape", "auto")
    ):
        raise SaveSystemError("battle command memory has an invalid global command")
    choices = {}
    for name in ("commands", "spells", "items"):
        current = _mapping(value.get(name, {}), f"battle_command_memory.{name}")
        if not all(isinstance(key, str) and key for key in current):
            raise SaveSystemError("battle command memory has invalid character keys")
        choices[name] = current
    memory = BattleCommandMemory(global_command=global_command)
    for key, command in choices["commands"].items():
        if not isinstance(command, str):
            raise SaveSystemError("remembered commands must be strings")
        try:
            memory.commands[key] = BattleCommand(command)
        except ValueError as error:
            raise SaveSystemError("remembered command is unsupported") from error
    for key, spell in choices["spells"].items():
        if not isinstance(spell, str) or not spell:
            raise SaveSystemError("remembered spell keys must be non-empty strings")
        memory.spells[key] = spell
    for key, selection in choices["items"].items():
        selection = _mapping(selection, "remembered item")
        item_key = _required_string(selection, "item_key", "remembered item")
        slot = selection.get("equipment_slot")
        if slot is not None:
            if not isinstance(slot, str):
                raise SaveSystemError("remembered equipment slot must be a string")
            try:
                slot = EquipmentSlot(slot)
            except ValueError as error:
                raise SaveSystemError(
                    "remembered equipment slot is unsupported"
                ) from error
        memory.items[key] = (item_key, slot)
    return memory


def _serialize_battle_command_memory(memory: BattleCommandMemory) -> dict[str, object]:
    if not isinstance(memory, BattleCommandMemory):
        raise TypeError("battle_command_memory must be BattleCommandMemory")
    if not isinstance(memory.commands, Mapping) or not all(
        isinstance(command, BattleCommand) for command in memory.commands.values()
    ):
        raise TypeError("remembered commands must be BattleCommand values")
    if not isinstance(memory.spells, Mapping) or not isinstance(memory.items, Mapping):
        raise TypeError("remembered spells and items must be mappings")
    items = {}
    for key, selection in memory.items.items():
        if (
            not isinstance(selection, tuple)
            or len(selection) != 2
            or (
                selection[1] is not None and not isinstance(selection[1], EquipmentSlot)
            )
        ):
            raise TypeError(
                "remembered items must contain an item key and equipment slot"
            )
        item_key, slot = selection
        items[key] = {
            "item_key": item_key,
            "equipment_slot": slot.value if slot is not None else None,
        }
    serialized = {
        "global_command": memory.global_command,
        "commands": {key: command.value for key, command in memory.commands.items()},
        "spells": dict(memory.spells),
        "items": items,
    }
    _restore_battle_command_memory(serialized)
    return serialized


def _serialize_member(member: Member) -> dict[str, object]:
    equipment: dict[str, str | None] = {}
    for slot in EquipmentSlot:
        item = member.equipment.item_at(slot)
        equipment[slot.value] = None if item is None else item.key
    return {
        "internal_level": member.internal_level,
        "experience_offset": member.experience_offset,
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
        message_id = entry.get("message_id")
        arguments = entry.get("arguments")
        if isinstance(message_id, str) and message_id and text_key is None:
            reference = {"message_id": message_id}
        elif isinstance(text_key, str) and text_key and message_id is None:
            reference = {"text_key": text_key}
        else:
            raise TypeError("log must contain one text_key or message_id")
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
            {**reference, "arguments": dict(sorted(arguments.items()))}
        )
    return serialized


class SaveRepository:
    """Persist, read, delete, and preview save-slot documents."""

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

    def load(self, slot: int) -> dict[str, object]:
        """Read one version-supported save document without restoring it."""

        path = self.slot_path(slot)
        if not path.is_file():
            raise SaveSystemError(f"save slot {slot} is empty")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise SaveSystemError(f"failed to read save slot {slot}") from error
        if not isinstance(document, dict):
            raise SaveSystemError(f"save slot {slot} does not contain an object")
        if document.get("format_version") not in SUPPORTED_SAVE_FORMAT_VERSIONS:
            raise SaveSystemError("save document has an unsupported format version")
        return document

    def delete(self, slot: int) -> None:
        """Delete one slot file; deleting an empty slot is harmless."""

        path = self.slot_path(slot)
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise SaveSystemError(f"failed to delete save slot {slot}") from error

    @staticmethod
    def _document_summary(
        slot: int,
        document: object,
    ) -> SaveSlotSummary:
        if (
            not isinstance(document, Mapping)
            or document.get("format_version") not in SUPPORTED_SAVE_FORMAT_VERSIONS
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
        character_states = party.get("character_states")
        dead_keys = tuple(
            key
            for key in active_keys
            if isinstance(character_states, Mapping)
            and isinstance(character_states.get(key), Mapping)
            and character_states[key].get("hp") == 0
        )
        return SaveSlotSummary(
            slot,
            True,
            saved_at,
            tuple(active_keys),
            dead_keys,
        )


def _validate_slot(slot: int) -> None:
    if isinstance(slot, bool) or not isinstance(slot, int):
        raise TypeError("save slot must be an integer")
    if not 1 <= slot <= SAVE_SLOT_COUNT:
        raise ValueError(f"save slot must be from 1 to {SAVE_SLOT_COUNT}")


__all__ = [
    "SAVE_DIRECTORY",
    "SAVE_FORMAT_VERSION",
    "SAVE_SLOT_COUNT",
    "LoadedGameState",
    "SaveRepository",
    "SaveSlotSummary",
    "SaveSystemError",
    "create_save_document",
    "restore_save_document",
]
