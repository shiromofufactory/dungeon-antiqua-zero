"""Inventory operations shared by item screens and future game scenes."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from copy import copy
from types import MappingProxyType

if __package__ == "systems":
    from battle_commands import member_attack_reach
    from item import Item, ItemEquipType
    from member import EquipmentSet, EquipmentSlot, Member
else:
    from ..battle_commands import member_attack_reach
    from ..item import Item, ItemEquipType
    from ..member import EquipmentSet, EquipmentSlot, Member


class InventorySystem:
    """Own item quantities and enforce rules for changing them."""

    def __init__(
        self,
        items: Mapping[str, Item],
        quantities: Mapping[str, int] | None = None,
        recorded_keys: Iterable[str] | None = None,
    ) -> None:
        if not isinstance(items, Mapping) or not all(
            isinstance(key, str) and isinstance(item, Item) and key == item.key
            for key, item in items.items()
        ):
            raise TypeError("items must map each string key to its matching Item")
        if quantities is None:
            quantities = {}
        if not isinstance(quantities, Mapping):
            raise TypeError("quantities must be a mapping")

        normalized: dict[str, int] = {}
        for key, quantity in quantities.items():
            if not isinstance(key, str) or key not in items:
                raise ValueError(f"unknown inventory item key: {key!r}")
            if isinstance(quantity, bool) or not isinstance(quantity, int):
                raise TypeError("item quantity must be an integer")
            if quantity < 0:
                raise ValueError("item quantity must not be negative")
            limit = self.stack_limit(items[key])
            if quantity > limit:
                raise ValueError(
                    f"item quantity exceeds stack limit {limit}: {key!r}"
                )
            if quantity:
                normalized[key] = quantity

        if recorded_keys is None:
            normalized_recorded_keys = frozenset(normalized)
        else:
            if isinstance(recorded_keys, (str, bytes)):
                raise TypeError("recorded_keys must be an iterable of strings")
            try:
                normalized_recorded_keys = frozenset(recorded_keys)
            except TypeError as error:
                raise TypeError(
                    "recorded_keys must be an iterable of strings"
                ) from error
            if not all(isinstance(key, str) for key in normalized_recorded_keys):
                raise TypeError("recorded item keys must be strings")
            unknown_recorded_keys = normalized_recorded_keys - items.keys()
            if unknown_recorded_keys:
                unknown = sorted(unknown_recorded_keys)[0]
                raise ValueError(f"unknown recorded item key: {unknown!r}")

        self._items = dict(items)
        self._quantities = normalized
        self._recorded_keys = normalized_recorded_keys

    @classmethod
    def with_one_each(cls, items: Mapping[str, Item]) -> InventorySystem:
        """Build a development-test inventory with one of every item."""

        return cls(items, {key: 1 for key in items})

    @property
    def items(self) -> tuple[Item, ...]:
        """Return owned item types in master-data order."""

        return tuple(
            item for key, item in self._items.items() if self.quantity(key) > 0
        )

    @property
    def catalog_items(self) -> tuple[Item, ...]:
        """Return every registered item in master-data order."""

        return tuple(self._items.values())

    @property
    def quantities(self) -> Mapping[str, int]:
        """Expose current quantities without allowing callers to mutate them."""

        return MappingProxyType(self._quantities)

    @property
    def recorded_items(self) -> tuple[Item, ...]:
        """Return discovered item types in master-data order."""

        return tuple(
            item for key, item in self._items.items() if key in self._recorded_keys
        )

    @property
    def recorded_count(self) -> int:
        return len(self._recorded_keys)

    @property
    def catalog_count(self) -> int:
        return len(self._items)

    def record_equipment(self, members: Iterable[Member]) -> None:
        """Reveal equipped item types without adding loose inventory copies."""

        party = tuple(members)
        if not all(isinstance(member, Member) for member in party):
            raise TypeError("members must contain only Member values")
        keys = {
            self._item_key(item)
            for member in party
            for item in member.equipment.equipped_items()
        }
        self._recorded_keys = self._recorded_keys | keys

    def quantity(self, item: Item | str) -> int:
        """Return the owned count for an item model or stable item key."""

        key = self._item_key(item)
        return self._quantities.get(key, 0)

    @staticmethod
    def stack_limit(item: Item) -> int:
        """Return ZERO's per-item ownership limit."""

        if not isinstance(item, Item):
            raise TypeError("item must be an Item")
        return 99 if item.equip_type is ItemEquipType.ITEM else 9

    def equipped_quantity(
        self,
        item: Item | str,
        members: Iterable[Member],
    ) -> int:
        """Count matching copies currently equipped by the supplied party."""

        key = self._item_key(item)
        try:
            party = tuple(members)
        except TypeError as error:
            raise TypeError("members must be an iterable of Member") from error
        if not all(isinstance(member, Member) for member in party):
            raise TypeError("members must contain only Member values")
        return sum(
            equipped.key == key
            for member in party
            for equipped in member.equipment.equipped_items()
        )

    def total_quantity(
        self,
        item: Item | str,
        members: Iterable[Member] = (),
    ) -> int:
        """Return inventory plus equipped copies without duplicating save state."""

        key = self._item_key(item)
        return self.quantity(key) + self.equipped_quantity(key, members)

    def remaining_capacity(
        self,
        item: Item | str,
        members: Iterable[Member] = (),
    ) -> int:
        """Return how many more copies may be acquired."""

        key = self._item_key(item)
        return max(
            0,
            self.stack_limit(self._items[key]) - self.total_quantity(key, members),
        )

    def can_add(
        self,
        item: Item | str,
        quantity: int = 1,
        *,
        members: Iterable[Member] = (),
    ) -> bool:
        """Return whether an acquisition respects the shared ownership limit."""

        self._validate_positive_quantity(quantity)
        return quantity <= self.remaining_capacity(item, members)

    def add(
        self,
        item: Item | str,
        quantity: int = 1,
        *,
        members: Iterable[Member] = (),
    ) -> bool:
        """Add multiple copies atomically when the ownership limit permits it."""

        key = self._item_key(item)
        if not self.can_add(key, quantity, members=members):
            return False
        self._increase(key, quantity)
        return True

    def can_remove(self, item: Item | str, quantity: int = 1) -> bool:
        """Return whether the inventory contains the requested loose copies."""

        self._validate_positive_quantity(quantity)
        return quantity <= self.quantity(item)

    def remove(self, item: Item | str, quantity: int = 1) -> bool:
        """Remove multiple inventory copies atomically."""

        key = self._item_key(item)
        if not self.can_remove(key, quantity):
            return False
        self._decrease(key, quantity)
        return True

    def validate_total_quantities(self, members: Iterable[Member]) -> None:
        """Reject loaded state whose inventory plus equipment exceeds a limit."""

        party = tuple(members)
        for key, item in self._items.items():
            total = self.total_quantity(key, party)
            limit = self.stack_limit(item)
            if total > limit:
                raise ValueError(
                    f"total item quantity exceeds stack limit {limit}: {key!r}"
                )

    def replace_npc_equipment(
        self,
        member: Member,
        slot: EquipmentSlot,
        item_key: str,
        *,
        members: Iterable[Member],
    ) -> bool:
        """Grant fixed equipment by event, returning player equipment to inventory."""

        item = self._items[self._item_key(item_key)]
        if not member.is_npc or not member.has_joined:
            raise ValueError("equipment replacement requires an NPC who has joined")
        replacements = self._equipment_replacements(member, slot, item)
        if replacements[slot] is None:
            raise ValueError("replacement requires Dual-Wield in the resulting equipment")

        next_equipment = member.equipment.replaced(replacements)
        overrides = dict(member.event_equipment_overrides)
        returned: list[Item] = []
        added_copies = 1
        for replaced_slot, replacement in replacements.items():
            previous = member.equipment.item_at(replaced_slot)
            if previous is None:
                continue
            if replacement is not None and previous.key == replacement.key:
                added_copies -= 1
                continue
            if member.is_equipment_fixed(replaced_slot):
                added_copies -= int(previous.key == item.key)
                overrides[replaced_slot] = None
            else:
                returned.append(previous)
        if added_copies > 0 and not self.can_add(item, added_copies, members=members):
            return False

        for previous in returned:
            self._increase(previous.key)
        overrides[slot] = item.key
        member.equipment = next_equipment
        member.event_equipment_overrides = overrides
        self._recorded_keys = self._recorded_keys | {item.key}
        return True

    def can_discard(self, item: Item | str) -> bool:
        """Return whether one owned item may be discarded.

        DA2 treats a zero price as the protected-item marker.
        """

        key = self._item_key(item)
        return self._quantities.get(key, 0) > 0 and self._items[key].price > 0

    def discard(self, item: Item | str) -> bool:
        """Discard one item when allowed, returning whether state changed."""

        key = self._item_key(item)
        if not self.can_discard(key):
            return False
        return self.remove(key)

    def can_equip(
        self,
        member: Member,
        slot: EquipmentSlot,
        item: Item | None,
    ) -> bool:
        """Return whether one inventory-backed equipment change is legal."""

        self._validate_equipment_arguments(member, slot, item)
        current = member.equipment.item_at(slot)
        if member.is_equipment_fixed(slot):
            return False
        if item is None:
            if current is None:
                return False
        elif self.quantity(item) <= 0 or not member.can_equip_at(item, slot):
            return False

        replacements = self._equipment_replacements(member, slot, item)
        for replaced_slot, replacement in replacements.items():
            if replaced_slot is slot:
                continue
            previous = member.equipment.item_at(replaced_slot)
            if previous is not replacement and member.is_equipment_fixed(
                replaced_slot
            ):
                return False
        return True

    def equip(
        self,
        member: Member,
        slot: EquipmentSlot,
        item: Item | None,
    ) -> bool:
        """Exchange one equipped item with inventory, honoring NPC locks."""

        if not self.can_equip(member, slot, item):
            return False

        replacements = self._equipment_replacements(member, slot, item)
        displaced: list[Item] = []
        for replaced_slot, replacement in replacements.items():
            previous = member.equipment.item_at(replaced_slot)
            if previous is not None and previous is not replacement:
                displaced.append(previous)

        next_equipment = member.equipment.replaced(replacements)
        if item is not None:
            self._decrease(item.key)
        for replaced_item in displaced:
            self._increase(replaced_item.key)
        member.equipment = next_equipment
        return True

    def preview_equipment(
        self,
        member: Member,
        slot: EquipmentSlot,
        item: Item | None,
    ) -> EquipmentSet | None:
        """Return the equipment set produced by a legal change without applying it."""

        if not self.can_equip(member, slot, item):
            return None
        return member.equipment.replaced(
            self._equipment_replacements(member, slot, item)
        )

    def auto_equip(self, member: Member) -> bool:
        """Select armor and compare legal hand combinations for one member.

        NPC fixed equipment is never removed or replaced. Equipment added
        later follows the same replacement rules as player-character gear.
        """

        if not isinstance(member, Member):
            raise TypeError("member must be a Member")
        changed = False
        for slot in EquipmentSlot:
            if (
                member.equipment.item_at(slot) is not None
                and not member.is_equipment_fixed(slot)
            ):
                changed = self.equip(member, slot, None) or changed

        # Armor can grant the skills used to evaluate the hands.
        for slot in (
            EquipmentSlot.BODY,
            EquipmentSlot.HEAD,
            EquipmentSlot.ARM,
        ):
            if member.equipment.item_at(slot) is not None:
                continue
            armor = self._best_item(
                member,
                slot,
                score=self._armor_score,
            )
            if armor is not None:
                changed = self.equip(member, slot, armor) or changed

        right, left = self._best_hand_equipment(member)
        for slot, item in ((EquipmentSlot.RIGHT, right), (EquipmentSlot.LEFT, left)):
            if item is not None and item is not member.equipment.item_at(slot):
                changed = self.equip(member, slot, item) or changed
        return changed

    def _best_hand_equipment(self, member: Member) -> tuple[Item | None, Item | None]:
        base = member.equipment
        current_right = base.item_at(EquipmentSlot.RIGHT)
        current_left = base.item_at(EquipmentSlot.LEFT)
        weapons = tuple(item for item in self.items if item.is_weapon)
        right_candidates = (current_right,)
        if current_right is None:
            right_candidates = tuple(
                weapon for weapon in weapons
                if self.can_equip(member, EquipmentSlot.RIGHT, weapon)
            ) or (None,)

        shield = None
        if current_left is None:
            shield = self._best_item(
                member,
                EquipmentSlot.LEFT,
                score=self._armor_score,
                accepted_type=ItemEquipType.LEFT,
            )
        preview = copy(member)
        best_hands = current_right, current_left
        best_score = None
        for right in right_candidates:
            right_equipment = base.replaced({EquipmentSlot.RIGHT: right})
            preview.equipment = right_equipment
            left_candidates = [current_left]
            if current_left is None and not right_equipment.uses_both_hands:
                if shield is not None:
                    left_candidates.append(shield)
                if right is not None and preview.has_skill("Dual-Wield"):
                    left_candidates.extend(
                        weapon for weapon in weapons
                        if preview.can_equip_at(weapon, EquipmentSlot.LEFT)
                        and (
                            current_right is not None or weapon is not right
                            or self.quantity(weapon) >= 2
                        )
                    )

            for left in left_candidates:
                preview.equipment = right_equipment.replaced({EquipmentSlot.LEFT: left})
                stats = preview.battle_stats
                right_score = stats.attack_right * stats.hit_right.total
                left_score = (
                    stats.attack_left * stats.hit_left.total
                    if stats.attack_left is not None and stats.hit_left is not None
                    else 0
                )
                can_reach = member.is_front_row or (
                    right is not None and member_attack_reach(preview) >= 2
                )
                shield_score = (
                    self._armor_score(left)
                    if left is not None and left.is_armor else float("-inf")
                )
                score = can_reach, right_score + left_score, shield_score, right_score
                if best_score is None or score > best_score:
                    best_hands = right, left
                    best_score = score
        return best_hands

    def _best_item(
        self,
        member: Member,
        slot: EquipmentSlot,
        *,
        score: Callable[[Item], float | int],
        accepted_type: ItemEquipType | None = None,
    ) -> Item | None:
        candidates = (
            item
            for item in self.items
            if (accepted_type is None or item.equip_type is accepted_type)
            and self.can_equip(member, slot, item)
        )
        return max(candidates, key=score, default=None)

    @staticmethod
    def _armor_score(item: Item) -> float:
        return (
            0.01
            + item.defense
            + (item.evasion + item.spell_resistance) / 5
            + len(item.resistances) * 1.3
            + item.strength_modifier
            + item.agility_modifier
            + item.magic_modifier
        )

    def _increase(self, key: str, quantity: int = 1) -> None:
        self._quantities[key] = self._quantities.get(key, 0) + quantity
        self._recorded_keys = self._recorded_keys | {key}

    def _decrease(self, key: str, amount: int = 1) -> None:
        quantity = self._quantities.get(key, 0)
        if quantity < amount:
            raise ValueError(f"inventory item is not owned: {key!r}")
        if quantity == amount:
            del self._quantities[key]
        else:
            self._quantities[key] = quantity - amount

    @staticmethod
    def _validate_positive_quantity(quantity: int) -> None:
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise TypeError("quantity must be an integer")
        if quantity <= 0:
            raise ValueError("quantity must be positive")

    def _validate_equipment_arguments(
        self,
        member: Member,
        slot: EquipmentSlot,
        item: Item | None,
    ) -> None:
        if not isinstance(member, Member):
            raise TypeError("member must be a Member")
        if not isinstance(slot, EquipmentSlot):
            raise TypeError("slot must be an EquipmentSlot")
        if item is not None and not isinstance(item, Item):
            raise TypeError("item must be an Item or None")
        if item is not None and item.key not in self._items:
            raise ValueError(f"unknown inventory item key: {item.key!r}")

    def _equipment_replacements(
        self,
        member: Member,
        slot: EquipmentSlot,
        item: Item | None,
    ) -> dict[EquipmentSlot, Item | None]:
        replacements: dict[EquipmentSlot, Item | None] = {slot: item}
        if (
            item is not None
            and slot is EquipmentSlot.RIGHT
            and item.equip_type is ItemEquipType.TWO_HANDS
        ):
            replacements[EquipmentSlot.LEFT] = None
        elif item is not None and slot is EquipmentSlot.LEFT:
            right = member.equipment.item_at(EquipmentSlot.RIGHT)
            if (
                right is not None
                and right.equip_type is ItemEquipType.TWO_HANDS
            ):
                replacements[EquipmentSlot.RIGHT] = None

        proposed = member.equipment.replaced(replacements)
        left = proposed.item_at(EquipmentSlot.LEFT)
        if (
            left is not None
            and left.equip_type is ItemEquipType.RIGHT
            and not member.has_skill("Dual-Wield", equipment=proposed)
        ):
            replacements[EquipmentSlot.LEFT] = None
        return replacements

    def _item_key(self, item: Item | str) -> str:
        if isinstance(item, Item):
            key = item.key
        elif isinstance(item, str):
            key = item
        else:
            raise TypeError("item must be an Item or string key")
        if key not in self._items:
            raise ValueError(f"unknown inventory item key: {key!r}")
        return key


__all__ = ["InventorySystem"]
