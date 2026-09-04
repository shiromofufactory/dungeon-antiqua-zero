"""Coordinate active-party membership without losing character state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

if __package__ == "systems":
    from item import Item
    from member import FIORA_CHARACTER_KEY, MAX_PARTY_MEMBER_COUNT, Member
    from skill import Skill
else:
    from ..item import Item
    from ..member import FIORA_CHARACTER_KEY, MAX_PARTY_MEMBER_COUNT, Member
    from ..skill import Skill


class PartySystemError(ValueError):
    """Raised when an event requests an invalid membership change."""


class PartySystem:
    def __init__(
        self,
        *,
        character_records: Sequence[Mapping[str, object]],
        items: Mapping[str, Item],
        skills: Mapping[str, Skill],
        active_party: Sequence[Member],
        character_states: Mapping[str, Member] | None = None,
    ) -> None:
        self._records = {
            record.get("name_en"): record
            for record in character_records
            if isinstance(record.get("name_en"), str)
        }
        self._items = dict(items)
        self._skills = dict(skills)
        self.replace(active_party, character_states=character_states)

    @property
    def active_party(self) -> tuple[Member, ...]:
        return self._active_party

    @property
    def character_states(self) -> dict[str, Member]:
        return self._character_states

    def contains(self, character_key: str) -> bool:
        return any(
            member.definition.key == character_key for member in self._active_party
        )

    def replace(
        self,
        active_party: Sequence[Member],
        *,
        character_states: Mapping[str, Member] | None = None,
    ) -> None:
        party = tuple(active_party)
        if not party or len(party) > MAX_PARTY_MEMBER_COUNT:
            raise PartySystemError("party must contain from 1 to 6 members")
        keys = tuple(member.definition.key for member in party)
        if len(keys) != len(set(keys)):
            raise PartySystemError("party contains duplicate characters")
        if FIORA_CHARACTER_KEY not in keys:
            raise PartySystemError("party must contain Fiora")
        if character_states is None:
            states = {member.definition.key: member for member in party}
        else:
            states = dict(character_states)
            states.update((member.definition.key, member) for member in party)
        self._active_party = party
        self._character_states = states

    def join(self, character_key: str) -> bool:
        self._require_character(character_key)
        if self.contains(character_key):
            return False
        if len(self._active_party) >= MAX_PARTY_MEMBER_COUNT:
            raise PartySystemError("party is full")
        member = self._character_states.get(character_key)
        if member is None:
            fiora = next(
                member
                for member in self._active_party
                if member.definition.key == FIORA_CHARACTER_KEY
            )
            member = Member.from_record(
                self._records[character_key],
                items=self._items,
                skills=self._skills,
                fiora_internal_level=fiora.internal_level,
            )
            self._character_states[character_key] = member
        self._active_party = (*self._active_party, member)
        return True

    def leave(self, character_key: str) -> bool:
        self._require_character(character_key)
        if character_key == FIORA_CHARACTER_KEY:
            raise PartySystemError("Fiora cannot leave the party")
        if not self.contains(character_key):
            return False
        remaining = tuple(
            member
            for member in self._active_party
            if member.definition.key != character_key
        )
        if not remaining:
            raise PartySystemError("party must not be empty")
        self._active_party = remaining
        return True

    def _require_character(self, character_key: str) -> None:
        if not isinstance(character_key, str):
            raise TypeError("character_key must be a string")
        if character_key not in self._records:
            raise PartySystemError(f"unknown character: {character_key}")


__all__ = ["PartySystem", "PartySystemError"]
