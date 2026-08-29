"""Player-character identity and member state independent of UI and Pyxel."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, TypeVar

if __package__ == "":
    from item import Item, ItemEquipType
    from localization import Localizer, format_number
    from skill import Skill
    from text_catalog import TextCatalog
else:
    from .item import Item, ItemEquipType
    from .localization import Localizer, format_number
    from .skill import Skill
    from .text_catalog import TextCatalog


class MemberDataError(ValueError):
    """Raised when a character record cannot be converted into a member."""


class Race(StrEnum):
    """Stable race identifiers stored in character and save data."""

    FAIRY = "FAIRY"
    HUMAN = "HUMAN"
    DRAGONEWT = "DRAGONEWT"
    ELF = "ELF"
    DWARF = "DWARF"
    ROBOT = "ROBOT"


class Gender(StrEnum):
    """Stable gender identifiers stored in character and save data."""

    MALE = "MALE"
    FEMALE = "FEMALE"
    NONE = "NONE"


class EquipmentSlot(StrEnum):
    """Named physical slots used by a member's current equipment."""

    RIGHT = "RIGHT"
    LEFT = "LEFT"
    HEAD = "HEAD"
    BODY = "BODY"
    ARM = "ARM"


EnumValue = TypeVar("EnumValue", bound=StrEnum)

INITIAL_HP = 999
INITIAL_MAX_HP = 999
INITIAL_MP = 255
INITIAL_MAX_MP = 255
EQUIPMENT_RECORD_FIELDS = MappingProxyType(
    {
        EquipmentSlot.RIGHT: "equip_right",
        EquipmentSlot.LEFT: "equip_left",
        EquipmentSlot.HEAD: "equip_head",
        EquipmentSlot.BODY: "equip_body",
        EquipmentSlot.ARM: "equip_arm",
    }
)
_EQUIPMENT_TYPES_BY_SLOT = MappingProxyType(
    {
        EquipmentSlot.RIGHT: frozenset(
            (ItemEquipType.RIGHT, ItemEquipType.TWO_HANDS)
        ),
        EquipmentSlot.LEFT: frozenset(
            (ItemEquipType.LEFT, ItemEquipType.RIGHT)
        ),
        EquipmentSlot.HEAD: frozenset((ItemEquipType.HEAD,)),
        EquipmentSlot.BODY: frozenset((ItemEquipType.BODY,)),
        EquipmentSlot.ARM: frozenset((ItemEquipType.ARM,)),
    }
)


def _validate_ability_value(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MemberDataError(f"character.{name} must be an integer")
    if value < 0:
        raise MemberDataError(f"character.{name} must not be negative")
    return value


def _string_keys(record: Mapping[str, object], field_name: str) -> tuple[str, ...]:
    value = record.get(field_name, [])
    if not isinstance(value, list):
        raise MemberDataError(f"character.{field_name} must be an array")
    if not all(isinstance(key, str) and key for key in value):
        raise MemberDataError(
            f"character.{field_name} must contain non-empty strings"
        )
    return tuple(value)


@dataclass
class EquipmentSet:
    """A member's current equipment indexed by explicit physical slots."""

    _items: dict[EquipmentSlot, Item | None] = field(
        default_factory=lambda: {slot: None for slot in EquipmentSlot}
    )

    def __post_init__(self) -> None:
        if not isinstance(self._items, dict):
            raise TypeError("equipment items must be a dictionary")
        if not all(isinstance(slot, EquipmentSlot) for slot in self._items):
            raise TypeError("equipment keys must be EquipmentSlot values")
        unknown_slots = set(self._items) - set(EquipmentSlot)
        if unknown_slots:
            raise ValueError(f"unsupported equipment slots: {unknown_slots}")
        for slot in EquipmentSlot:
            item = self._items.setdefault(slot, None)
            if item is not None and not isinstance(item, Item):
                raise TypeError(f"equipment at {slot.value} must be an Item or None")
            if item is not None and item.equip_type not in _EQUIPMENT_TYPES_BY_SLOT[slot]:
                raise MemberDataError(
                    f"item cannot be equipped at {slot.value}: {item.key}"
                )
        right = self._items[EquipmentSlot.RIGHT]
        if (
            right is not None
            and right.equip_type is ItemEquipType.TWO_HANDS
            and self._items[EquipmentSlot.LEFT] is not None
        ):
            raise MemberDataError(
                "left equipment must be empty when using a two-handed item"
            )

    @classmethod
    def from_keys(
        cls,
        keys: Mapping[EquipmentSlot, str],
        items: Mapping[str, Item],
    ) -> EquipmentSet:
        """Resolve stable item keys into one current equipment set."""

        if not isinstance(keys, Mapping):
            raise TypeError("equipment keys must be a mapping")
        if not isinstance(items, Mapping):
            raise TypeError("items must be a mapping")
        resolved: dict[EquipmentSlot, Item | None] = {}
        for slot in EquipmentSlot:
            key = keys.get(slot, "")
            if not isinstance(key, str):
                raise MemberDataError(
                    f"initial equipment key must be a string: {slot.value}"
                )
            if not key:
                resolved[slot] = None
                continue
            try:
                item = items[key]
            except KeyError as error:
                raise MemberDataError(
                    f"initial equipment item is missing: {key}"
                ) from error
            if not isinstance(item, Item):
                raise TypeError(f"items[{key!r}] must be an Item")
            resolved[slot] = item
        return cls(resolved)

    def item_at(self, slot: EquipmentSlot) -> Item | None:
        """Return the item occupying ``slot`` without exposing the mapping."""

        if not isinstance(slot, EquipmentSlot):
            raise TypeError("slot must be an EquipmentSlot")
        return self._items[slot]

    def equipped_items(self) -> tuple[Item, ...]:
        """Return equipped items in the stable screen and save-data order."""

        return tuple(
            item
            for slot in EquipmentSlot
            if (item := self._items[slot]) is not None
        )

    @property
    def uses_both_hands(self) -> bool:
        """Return whether the right-hand item reserves both hand slots."""

        right = self._items[EquipmentSlot.RIGHT]
        return (
            right is not None
            and right.equip_type is ItemEquipType.TWO_HANDS
        )


@dataclass(frozen=True)
class BaseAbilities:
    """Immutable ability values read directly from character master data."""

    strength: int
    agility: int
    magic: int


@dataclass(frozen=True)
class AdjustedAbilities:
    """Current ability values after applying runtime adjustments."""

    strength: int
    agility: int
    magic: int


@dataclass(frozen=True)
class CharacterDefinition:
    """Immutable master data loaded from one ``characters.json`` record."""

    names: Mapping[str, object]
    race: Race
    gender: Gender
    base_abilities: BaseAbilities
    initial_skill_keys: tuple[str, ...]
    initial_equipment_keys: Mapping[EquipmentSlot, str]

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> CharacterDefinition:
        """Validate and normalize one character master-data record."""

        if not isinstance(record, Mapping):
            raise MemberDataError("character must be an object")

        names: dict[str, str] = {}
        for key, value in record.items():
            if not key.startswith("name_"):
                continue
            if not isinstance(value, str):
                raise MemberDataError(f"character.{key} must be a string")
            names[key] = value
        if not names:
            raise MemberDataError("character must have at least one localized name")
        if not any(names.values()):
            raise MemberDataError("character must have a non-empty localized name")

        race = cls._enum_value(record, "race", Race)
        gender = cls._enum_value(record, "gender", Gender)
        base_abilities = BaseAbilities(
            strength=_validate_ability_value("base_str", record.get("base_str")),
            agility=_validate_ability_value("base_agi", record.get("base_agi")),
            magic=_validate_ability_value("base_mag", record.get("base_mag")),
        )
        initial_skill_keys = _string_keys(record, "skills")
        initial_equipment_keys: dict[EquipmentSlot, str] = {}
        for slot, field_name in EQUIPMENT_RECORD_FIELDS.items():
            value = record.get(field_name, "")
            if not isinstance(value, str):
                raise MemberDataError(f"character.{field_name} must be a string")
            initial_equipment_keys[slot] = value
        return cls(
            MappingProxyType(names),
            race,
            gender,
            base_abilities,
            initial_skill_keys,
            MappingProxyType(initial_equipment_keys),
        )

    @staticmethod
    def _enum_value(
        record: Mapping[str, object],
        field: str,
        enum_type: type[EnumValue],
    ) -> EnumValue:
        value = record.get(field)
        if not isinstance(value, str):
            raise MemberDataError(f"character.{field} must be a string")
        try:
            return enum_type(value)
        except ValueError as error:
            raise MemberDataError(
                f"unsupported character.{field}: {value}"
            ) from error

    def localized_name(self, localizer: Localizer) -> str:
        """Return the character name for the selected language."""

        try:
            return localizer.text(self.names, "name")
        except TypeError as error:
            raise MemberDataError(
                "localized character name must be a string"
            ) from error


@dataclass(frozen=True)
class MemberDisplayIdentity:
    """Localized identity values ready for presentation by a screen."""

    name: str
    race: str
    gender: str


@dataclass
class Member:
    """Current player-character state backed by an immutable definition."""

    definition: CharacterDefinition
    hp: int = INITIAL_HP
    max_hp: int = INITIAL_MAX_HP
    mp: int = INITIAL_MP
    max_mp: int = INITIAL_MAX_MP
    poisoned: bool = False
    paralyzed: bool = False
    sleeping: int = 0
    confused: int = 0
    skills: list[Skill] = field(default_factory=list)
    equipment: EquipmentSet = field(default_factory=EquipmentSet)

    def __post_init__(self) -> None:
        if not isinstance(self.definition, CharacterDefinition):
            raise TypeError("definition must be a CharacterDefinition")
        for name in ("hp", "max_hp", "mp", "max_mp"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        if self.hp > self.max_hp:
            raise ValueError("hp must not exceed max_hp")
        if self.mp > self.max_mp:
            raise ValueError("mp must not exceed max_mp")
        for name in ("poisoned", "paralyzed"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean")
        for name in ("sleeping", "confused"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        if not isinstance(self.skills, list):
            raise TypeError("skills must be a list")
        if not all(isinstance(skill, Skill) for skill in self.skills):
            raise TypeError("skills must contain only Skill values")
        if not isinstance(self.equipment, EquipmentSet):
            raise TypeError("equipment must be an EquipmentSet")

    @classmethod
    def from_record(
        cls,
        record: Mapping[str, object],
        *,
        items: Mapping[str, Item] | None = None,
        skills: Mapping[str, Skill] | None = None,
    ) -> Member:
        """Create the initial member state from a character data record."""

        definition = CharacterDefinition.from_record(record)
        item_catalog = {} if items is None else items
        skill_catalog = {} if skills is None else skills
        current_skills: list[Skill] = []
        for key in definition.initial_skill_keys:
            try:
                skill = skill_catalog[key]
            except KeyError as error:
                raise MemberDataError(
                    f"initial member skill is missing: {key}"
                ) from error
            if not isinstance(skill, Skill):
                raise TypeError(f"skills[{key!r}] must be a Skill")
            current_skills.append(skill)
        equipment = EquipmentSet.from_keys(
            definition.initial_equipment_keys,
            item_catalog,
        )
        return cls(
            definition,
            skills=current_skills,
            equipment=equipment,
        )

    @property
    def adjusted_abilities(self) -> AdjustedAbilities:
        """Return current abilities without mutating their master-data base."""

        base = self.definition.base_abilities
        return AdjustedAbilities(
            strength=base.strength,
            agility=base.agility,
            magic=base.magic,
        )

    def status(
        self,
        localizer: Localizer,
        texts: TextCatalog,
        *,
        show_ok: bool = False,
        show_mhp: bool = True,
    ) -> str:
        """Return the localized condition or the healthy maximum-HP display."""

        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        if not isinstance(texts, TextCatalog):
            raise TypeError("texts must be a TextCatalog")
        if not isinstance(show_ok, bool):
            raise TypeError("show_ok must be a boolean")
        if not isinstance(show_mhp, bool):
            raise TypeError("show_mhp must be a boolean")

        text_key = None
        if self.hp <= 0:
            text_key = "status.dead"
        elif self.paralyzed:
            text_key = "status.paralyzed"
        elif self.sleeping:
            text_key = "status.sleeping"
        elif self.confused:
            text_key = "status.confused"
        elif self.poisoned:
            text_key = "status.poisoned"
        elif show_ok:
            text_key = "status.ok"

        if text_key is not None:
            value = texts.text(text_key, localizer)
            if not value:
                raise MemberDataError(
                    f"localized member text is missing: {text_key}"
                )
            return value
        if show_mhp:
            return format_number(self.max_hp)
        return ""

    def display_identity(
        self,
        localizer: Localizer,
        texts: TextCatalog,
    ) -> MemberDisplayIdentity:
        """Resolve name, race, and gender without retaining language state."""

        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        if not isinstance(texts, TextCatalog):
            raise TypeError("texts must be a TextCatalog")

        name = self.definition.localized_name(localizer)
        race_key = f"race.{self.definition.race.value}"
        gender_key = f"gender.{self.definition.gender.value}"
        race = texts.text(race_key, localizer)
        gender = texts.text(gender_key, localizer)
        required_text = (
            ("character.name", name),
            (race_key, race),
            (gender_key, gender),
        )
        for key, value in required_text:
            if not value:
                raise MemberDataError(f"localized member text is missing: {key}")

        return MemberDisplayIdentity(name=name, race=race, gender=gender)
