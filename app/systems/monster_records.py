"""Record monster discoveries without copying master data into save data."""

from __future__ import annotations

from collections.abc import Iterable

if __package__ == "systems":
    from resistance import ResistanceType
    from state import SaveData
else:
    from ..resistance import ResistanceType
    from ..state import SaveData


MONSTER_PROFILE_FIELD_KEY = "profile"
MONSTER_TREASURE_ACQUIRED_FIELD_KEY = "treasure_acquired"
MONSTER_TREASURE_IDENTIFIED_FIELD_KEY = "treasure_identified"
MONSTER_COMBAT_FIELD_KEYS = frozenset(
    (
        MONSTER_PROFILE_FIELD_KEY,
        *(resistance.value for resistance in ResistanceType),
    )
)
MONSTER_IDENTIFY_FIELD_KEYS = frozenset(
    (*MONSTER_COMBAT_FIELD_KEYS, MONSTER_TREASURE_IDENTIFIED_FIELD_KEY)
)


class MonsterRecordSystem:
    """Own DA2-style encounter, affinity, identify, and treasure records."""

    def __init__(self, save_data: SaveData) -> None:
        if not isinstance(save_data, SaveData):
            raise TypeError("save_data must be SaveData")
        self.save_data = save_data

    def register_encounter(self, monster_keys: Iterable[str]) -> None:
        """Add encountered monster types while leaving their details unknown."""

        for monster_key in self._monster_keys(monster_keys):
            self.save_data.monster_records.setdefault(monster_key, set())

    def reveal_affinity(
        self,
        monster_key: str,
        resistance: ResistanceType,
    ) -> None:
        """Remember the profile and one attribute tested against this monster."""

        if not isinstance(resistance, ResistanceType):
            raise TypeError("resistance must be ResistanceType")
        fields = self._fields(monster_key)
        fields.add(MONSTER_PROFILE_FIELD_KEY)
        fields.add(resistance.value)

    def reveal_profile(self, monster_key: str) -> None:
        """Remember the basic information exposed by one attempted action."""

        self._fields(monster_key).add(MONSTER_PROFILE_FIELD_KEY)

    def reveal_all_combat_fields(self, monster_key: str) -> None:
        """Reveal the profile and every battle affinity."""

        self._fields(monster_key).update(MONSTER_COMBAT_FIELD_KEYS)

    def reveal_all_identify_fields(self, monster_key: str) -> None:
        """Reveal every field discovered by ZERO's Identify skill."""

        self._fields(monster_key).update(MONSTER_IDENTIFY_FIELD_KEYS)

    def record_treasure_acquired(self, monster_key: str) -> None:
        """Remember that this monster has successfully yielded its treasure."""

        self._fields(monster_key).add(MONSTER_TREASURE_ACQUIRED_FIELD_KEY)

    def affinity_is_revealed(
        self,
        monster_key: str,
        resistance: ResistanceType,
    ) -> bool:
        """Return whether target selection may expose this affinity."""

        if not isinstance(resistance, ResistanceType):
            raise TypeError("resistance must be ResistanceType")
        self._validate_monster_key(monster_key)
        return resistance.value in self.save_data.monster_records.get(
            monster_key,
            (),
        )

    def treasure_was_acquired(self, monster_key: str) -> bool:
        """Return the persisted per-monster treasure-acquisition flag."""

        self._validate_monster_key(monster_key)
        return MONSTER_TREASURE_ACQUIRED_FIELD_KEY in (
            self.save_data.monster_records.get(monster_key, ())
        )

    def _fields(self, monster_key: str) -> set[str]:
        self._validate_monster_key(monster_key)
        return self.save_data.monster_records.setdefault(monster_key, set())

    @classmethod
    def _monster_keys(cls, values: Iterable[str]) -> tuple[str, ...]:
        if isinstance(values, (str, bytes)):
            raise TypeError("monster_keys must be an iterable of strings")
        try:
            monster_keys = tuple(values)
        except TypeError as error:
            raise TypeError("monster_keys must be an iterable of strings") from error
        for monster_key in monster_keys:
            cls._validate_monster_key(monster_key)
        return monster_keys

    @staticmethod
    def _validate_monster_key(monster_key: str) -> None:
        if not isinstance(monster_key, str) or not monster_key:
            raise ValueError("monster_key must be a non-empty string")


__all__ = [
    "MONSTER_COMBAT_FIELD_KEYS",
    "MONSTER_IDENTIFY_FIELD_KEYS",
    "MONSTER_PROFILE_FIELD_KEY",
    "MONSTER_TREASURE_ACQUIRED_FIELD_KEY",
    "MONSTER_TREASURE_IDENTIFIED_FIELD_KEY",
    "MonsterRecordSystem",
]
