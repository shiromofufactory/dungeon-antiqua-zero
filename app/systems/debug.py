"""Debug-only party state editing independent of Pyxel and screen layout."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

if __package__ == "systems":
    from item import Item
    from member import (
        FIORA_CHARACTER_KEY,
        MAX_PARTY_MEMBER_COUNT,
        MAX_INTERNAL_LEVEL,
        MIN_INTERNAL_LEVEL,
        CharacterDefinition,
        FormationRow,
        Member,
    )
    from skill import Skill
else:
    from ..item import Item
    from ..member import (
        FIORA_CHARACTER_KEY,
        MAX_PARTY_MEMBER_COUNT,
        MAX_INTERNAL_LEVEL,
        MIN_INTERNAL_LEVEL,
        CharacterDefinition,
        FormationRow,
        Member,
    )
    from ..skill import Skill

MIN_OTHER_MEMBER_COUNT = 0
MAX_OTHER_MEMBER_COUNT = MAX_PARTY_MEMBER_COUNT - 1


class DebugPartyError(ValueError):
    """Raised when a requested debug party state is invalid."""


class DebugPartyEditor:
    """Own an editable debug party and recreate level-dependent state."""

    def __init__(
        self,
        character_records: Sequence[Mapping[str, object]],
        *,
        items: Mapping[str, Item],
        skills: Mapping[str, Skill],
        party: Sequence[Member],
    ) -> None:
        if not isinstance(character_records, Sequence):
            raise TypeError("character_records must be a sequence")
        if not isinstance(items, Mapping):
            raise TypeError("items must be a mapping")
        if not isinstance(skills, Mapping):
            raise TypeError("skills must be a mapping")
        if not isinstance(party, Sequence) or not all(
            isinstance(member, Member) for member in party
        ):
            raise TypeError("party must be a sequence of Member values")

        records_by_key: dict[str, Mapping[str, object]] = {}
        definitions: list[CharacterDefinition] = []
        for record in character_records:
            definition = CharacterDefinition.from_record(record)
            if definition.key in records_by_key:
                raise DebugPartyError(
                    f"character key is duplicated: {definition.key}"
                )
            records_by_key[definition.key] = record
            definitions.append(definition)
        if FIORA_CHARACTER_KEY not in records_by_key:
            raise DebugPartyError("Fiora is missing from character records")

        party_by_key: dict[str, Member] = {}
        party_order: list[str] = []
        for member in party:
            key = member.definition.key
            if key not in records_by_key:
                raise DebugPartyError(
                    f"party member is not in character records: {key}"
                )
            if key in party_by_key:
                raise DebugPartyError(f"party member is duplicated: {key}")
            party_by_key[key] = member
            party_order.append(key)
        if FIORA_CHARACTER_KEY not in party_by_key:
            raise DebugPartyError("Fiora must be in the debug party")
        self._validate_other_member_count(len(party_by_key) - 1)

        self._records_by_key = records_by_key
        self._definitions = tuple(definitions)
        self._items = items
        self._skills = skills
        self._party_by_key = party_by_key
        self._party_order = party_order
        self._baseline_level = party_by_key[FIORA_CHARACTER_KEY].internal_level

    @property
    def baseline_level(self) -> int:
        return self._baseline_level

    @property
    def candidate_definitions(self) -> tuple[CharacterDefinition, ...]:
        return self._definitions

    @property
    def selected_keys(self) -> frozenset[str]:
        return frozenset(self._party_by_key)

    @property
    def other_member_count(self) -> int:
        return len(self._party_by_key) - 1

    @property
    def party(self) -> tuple[Member, ...]:
        return tuple(self._party_by_key[key] for key in self._party_order)

    def effective_internal_level(self, character_key: str) -> int:
        """Return one member's level relative to Fiora's baseline."""

        definition = self._definition(character_key)
        if character_key == FIORA_CHARACTER_KEY:
            return self._baseline_level
        return min(
            max(
                self._baseline_level + definition.level_difference,
                MIN_INTERNAL_LEVEL,
            ),
            MAX_INTERNAL_LEVEL,
        )

    def set_baseline_level(self, level: int) -> None:
        """Recreate all selected members at levels derived from Fiora."""

        if isinstance(level, bool) or not isinstance(level, int):
            raise TypeError("debug party level must be an integer")
        if not MIN_INTERNAL_LEVEL <= level <= MAX_INTERNAL_LEVEL:
            raise DebugPartyError(
                f"debug party level must be from {MIN_INTERNAL_LEVEL} "
                f"to {MAX_INTERNAL_LEVEL}"
            )
        formation_rows = {
            key: member.formation_row for key, member in self._party_by_key.items()
        }
        self._baseline_level = level
        self._party_by_key = {
            key: self._new_member(key, formation_row=formation_rows[key])
            for key in self._party_order
        }

    def toggle_member(self, character_key: str) -> None:
        """Add or remove a member while keeping a 1-to-6-person party."""

        self._definition(character_key)
        if character_key == FIORA_CHARACTER_KEY:
            raise DebugPartyError("Fiora cannot be removed from the debug party")
        if character_key in self._party_by_key:
            self._validate_other_member_count(self.other_member_count - 1)
            del self._party_by_key[character_key]
            self._party_order.remove(character_key)
            return

        self._validate_other_member_count(self.other_member_count + 1)
        self._party_by_key[character_key] = self._new_member(character_key)
        self._party_order.append(character_key)

    def _new_member(
        self,
        character_key: str,
        *,
        formation_row: FormationRow | None = None,
    ) -> Member:
        member = Member.from_record_at_internal_level(
            self._records_by_key[character_key],
            self.effective_internal_level(character_key),
            items=self._items,
            skills=self._skills,
        )
        if formation_row is not None:
            member.formation_row = formation_row
        return member

    def _definition(self, character_key: str) -> CharacterDefinition:
        if not isinstance(character_key, str):
            raise TypeError("character_key must be a string")
        for definition in self._definitions:
            if definition.key == character_key:
                return definition
        raise DebugPartyError(f"unknown character key: {character_key}")

    @staticmethod
    def _validate_other_member_count(count: int) -> None:
        if not MIN_OTHER_MEMBER_COUNT <= count <= MAX_OTHER_MEMBER_COUNT:
            raise DebugPartyError(
                "debug party must contain Fiora and from 1 to "
                f"{MAX_PARTY_MEMBER_COUNT} total members"
            )


__all__ = [
    "DebugPartyEditor",
    "DebugPartyError",
    "MAX_OTHER_MEMBER_COUNT",
    "MIN_OTHER_MEMBER_COUNT",
]
