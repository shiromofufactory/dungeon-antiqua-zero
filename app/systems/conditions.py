"""Evaluate shared event and mission conditions against explicit domain state."""

from __future__ import annotations

from typing import Mapping

if __package__ == "systems":
    from state import SaveData
else:
    from ..state import SaveData

from .inventory import InventorySystem
from .party import PartySystem


def evaluate_condition(
    condition: Mapping[str, object], *, save_data: SaveData,
    party: PartySystem, inventory: InventorySystem,
) -> bool:
    if not isinstance(condition, Mapping):
        raise TypeError("condition must be a mapping")
    condition_type = condition["type"]
    if condition_type == "flag_set":
        return condition["flag_id"] in save_data.event_flags
    if condition_type == "member_in_party":
        return party.contains(str(condition["character_key"]))
    if condition_type == "item_at_least":
        return inventory.quantity(str(condition["item_key"])) >= int(condition["quantity"])
    if condition_type in ("all", "any"):
        results = (
            evaluate_condition(child, save_data=save_data, party=party, inventory=inventory)
            for child in condition["conditions"]
        )
        return all(results) if condition_type == "all" else any(results)
    if condition_type == "not":
        return not evaluate_condition(
            condition["condition"], save_data=save_data, party=party, inventory=inventory
        )
    raise ValueError(f"unsupported condition: {condition_type}")
