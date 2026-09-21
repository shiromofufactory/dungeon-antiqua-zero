"""Player-character identity and member state independent of UI and Pyxel."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Mapping, TypeVar

if __package__ == "":
    from battle_speed import (
        MAX_SPEED_MODIFIER,
        MIN_SPEED_MODIFIER,
        modified_agility,
    )
    from item import Item, ItemEquipType, ItemSpecial
    from localization import Localizer
    from resistance import ResistanceType
    from skill import Skill
    from text_catalog import TextCatalog
else:
    from .battle_speed import (
        MAX_SPEED_MODIFIER,
        MIN_SPEED_MODIFIER,
        modified_agility,
    )
    from .item import Item, ItemEquipType, ItemSpecial
    from .localization import Localizer
    from .resistance import ResistanceType
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


class CharacterType(StrEnum):
    """Stable participation type used by party and equipment rules."""

    MAIN = "MAIN"
    SUB = "SUB"
    NPC = "NPC"


class EquipmentSlot(StrEnum):
    """Named physical slots used by a member's current equipment."""

    RIGHT = "RIGHT"
    LEFT = "LEFT"
    HEAD = "HEAD"
    BODY = "BODY"
    ARM = "ARM"


class FormationRow(StrEnum):
    """A member's mutable front- or back-row party position."""

    FRONT = "FRONT"
    BACK = "BACK"


class ProficiencyKind(StrEnum):
    """Stable weapon and spell proficiency identifiers in character data."""

    SWORD = "eq_sword"
    KNIFE = "eq_knife"
    KATANA = "eq_katana"
    SPEAR = "eq_spear"
    HAMMER = "eq_hammer"
    AXE = "eq_axe"
    THROWING = "eq_throwing"
    ROD = "eq_rod"
    WAND = "eq_wand"
    SHIELD = "eq_shield"
    MYSTIC = "sp_mystic"
    SACRED = "sp_sacred"
    NETHER = "sp_nether"


class ProficiencyAptitude(IntEnum):
    """A character's immutable aptitude and corresponding level cap."""

    DISABLED = 0
    NORMAL = 1
    FAVORED = 2

    @property
    def max_level(self) -> int:
        return {
            ProficiencyAptitude.DISABLED: 0,
            ProficiencyAptitude.NORMAL: 8,
            ProficiencyAptitude.FAVORED: 9,
        }[self]


EnumValue = TypeVar("EnumValue", bound=StrEnum)

FIORA_CHARACTER_KEY = "Fiora"
BATTLE_PARTY_MEMBER_COUNT = 5
MAX_PARTY_MEMBER_COUNT = 6
MIN_INTERNAL_LEVEL = 1
MAX_INTERNAL_LEVEL = 99
MAX_HP = 999
MAX_MP = 255
MAX_ABILITY = 32
MIN_PROTECTION_LEVEL = -1
MAX_PROTECTION_LEVEL = 2
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
WEAPON_PROFICIENCY_KINDS = frozenset(
    (
        ProficiencyKind.SWORD,
        ProficiencyKind.KNIFE,
        ProficiencyKind.KATANA,
        ProficiencyKind.SPEAR,
        ProficiencyKind.HAMMER,
        ProficiencyKind.AXE,
        ProficiencyKind.THROWING,
        ProficiencyKind.ROD,
        ProficiencyKind.WAND,
    )
)
SPELL_PROFICIENCY_KINDS = frozenset(
    (
        ProficiencyKind.MYSTIC,
        ProficiencyKind.SACRED,
        ProficiencyKind.NETHER,
    )
)
_WEAPON_PROFICIENCY_BY_SUBTYPE = MappingProxyType(
    {kind.name: kind for kind in WEAPON_PROFICIENCY_KINDS}
)
_EQUIPMENT_PROFICIENCY_BY_SUBTYPE = MappingProxyType(
    {
        **_WEAPON_PROFICIENCY_BY_SUBTYPE,
        "SHIELD": ProficiencyKind.SHIELD,
    }
)
_TWO_HANDED_SKILL_KEY = "Two-Handed"
_DUAL_WIELD_SKILL_KEY = "Dual-Wield"
_REGENERATE_SKILL_KEY = "Regenerate"
_EQUIPMENT_GRANTED_SKILLS = MappingProxyType(
    {
        _DUAL_WIELD_SKILL_KEY: ItemSpecial.DUAL_WIELD,
        _TWO_HANDED_SKILL_KEY: ItemSpecial.TWO_HANDED,
    }
)
_TWO_HANDED_SKILL_KINDS = frozenset(
    (
        ProficiencyKind.SWORD,
        ProficiencyKind.KATANA,
        ProficiencyKind.HAMMER,
        ProficiencyKind.ROD,
    )
)


def required_experience_for_level(level: int) -> int:
    """Return DA2's cumulative experience threshold for one internal level."""

    if isinstance(level, bool) or not isinstance(level, int):
        raise TypeError("level must be an integer")
    if not MIN_INTERNAL_LEVEL <= level <= MAX_INTERNAL_LEVEL:
        raise ValueError(
            f"level must be from {MIN_INTERNAL_LEVEL} to {MAX_INTERNAL_LEVEL}"
        )
    total = 0
    increment = 0
    for previous_level in range(level - 1):
        if previous_level == 0:
            increment = 11
        else:
            factor = max(1.0, 1.4 - (previous_level - 1) / 100)
            increment = int(increment * factor)
        total += increment
    return total


def internal_level_for_experience(experience: int) -> int:
    """Resolve the highest internal level whose DA2 threshold is reached."""

    if isinstance(experience, bool) or not isinstance(experience, int):
        raise TypeError("experience must be an integer")
    if experience < 0:
        return MIN_INTERNAL_LEVEL
    for level in range(MAX_INTERNAL_LEVEL, MIN_INTERNAL_LEVEL, -1):
        if experience >= required_experience_for_level(level):
            return level
    return MIN_INTERNAL_LEVEL


def _validate_ability_value(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MemberDataError(f"character.{name} must be an integer")
    if value < 0:
        raise MemberDataError(f"character.{name} must not be negative")
    return value


def _validate_integer_value(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MemberDataError(f"character.{name} must be an integer")
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


def _proficiency_aptitudes(
    record: Mapping[str, object],
) -> Mapping[ProficiencyKind, ProficiencyAptitude]:
    aptitudes: dict[ProficiencyKind, ProficiencyAptitude] = {}
    for kind in ProficiencyKind:
        value = record.get(kind.value)
        if isinstance(value, bool) or not isinstance(value, int):
            raise MemberDataError(
                f"character.{kind.value} must be an integer from 0 to 2"
            )
        try:
            aptitudes[kind] = ProficiencyAptitude(value)
        except ValueError as error:
            raise MemberDataError(
                f"character.{kind.value} must be an integer from 0 to 2"
            ) from error
    return MappingProxyType(aptitudes)


@dataclass
class Proficiency:
    """A member's current level and progress for one weapon or spell kind."""

    aptitude: ProficiencyAptitude
    level: int = 0
    progress: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.aptitude, ProficiencyAptitude):
            raise TypeError("aptitude must be a ProficiencyAptitude")
        for name in ("level", "progress"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if not 0 <= self.level <= self.max_level:
            raise ValueError(f"level must be from 0 to {self.max_level}")
        if not 0 <= self.progress <= 99:
            raise ValueError("progress must be from 0 to 99")
        if self.aptitude is ProficiencyAptitude.DISABLED and self.progress != 0:
            raise ValueError("disabled proficiency progress must be 0")

    @property
    def max_level(self) -> int:
        return self.aptitude.max_level

    @classmethod
    def at_limit(cls, aptitude: ProficiencyAptitude) -> Proficiency:
        """Create a proficiency at the highest attainable value."""

        if not isinstance(aptitude, ProficiencyAptitude):
            raise TypeError("aptitude must be a ProficiencyAptitude")
        if aptitude is ProficiencyAptitude.DISABLED:
            return cls(aptitude, level=0, progress=0)
        return cls(aptitude, level=aptitude.max_level, progress=99)

    @classmethod
    def for_joining_member(
        cls,
        aptitude: ProficiencyAptitude,
        internal_level: int,
        *,
        is_fiora: bool = False,
    ) -> Proficiency:
        """Create the proficiency held when a character first joins."""

        if not isinstance(aptitude, ProficiencyAptitude):
            raise TypeError("aptitude must be a ProficiencyAptitude")
        if (
            isinstance(internal_level, bool)
            or not isinstance(internal_level, int)
        ):
            raise TypeError("internal_level must be an integer")
        if not MIN_INTERNAL_LEVEL <= internal_level <= MAX_INTERNAL_LEVEL:
            raise ValueError(
                f"internal_level must be from {MIN_INTERNAL_LEVEL} "
                f"to {MAX_INTERNAL_LEVEL}"
            )
        if not isinstance(is_fiora, bool):
            raise TypeError("is_fiora must be a boolean")
        if aptitude is ProficiencyAptitude.DISABLED:
            return cls(aptitude, level=0, progress=0)
        if is_fiora:
            return cls(aptitude, level=1, progress=0)

        if aptitude is ProficiencyAptitude.FAVORED:
            total = 160 + internal_level * 8
        else:
            total = 93 + internal_level * 7
        total = min(total, aptitude.max_level * 100 + 99)
        level, progress = divmod(total, 100)
        return cls(aptitude, level=level, progress=progress)

    def add_progress(self, amount: int) -> None:
        """Add progress, carrying each 100 points into one level."""

        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TypeError("amount must be an integer")
        if amount < 0:
            raise ValueError("amount must not be negative")
        if self.aptitude is ProficiencyAptitude.DISABLED or amount == 0:
            return
        current = self.level * 100 + self.progress
        limit = self.max_level * 100 + 99
        self.level, self.progress = divmod(min(current + amount, limit), 100)


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

    def replaced(
        self,
        replacements: Mapping[EquipmentSlot, Item | None],
    ) -> EquipmentSet:
        """Return a validated copy with explicit slot replacements."""

        if not isinstance(replacements, Mapping):
            raise TypeError("replacements must be a mapping")
        if not all(isinstance(slot, EquipmentSlot) for slot in replacements):
            raise TypeError("replacement keys must be EquipmentSlot values")
        copied = dict(self._items)
        copied.update(replacements)
        return EquipmentSet(copied)

    def equipped_items(self) -> tuple[Item, ...]:
        """Return equipped items in the stable screen and save-data order."""

        return tuple(
            item
            for slot in EquipmentSlot
            if (item := self._items[slot]) is not None
        )

    def weapon_at(self, slot: EquipmentSlot) -> Item | None:
        """Return the weapon in one hand, excluding a left-hand shield."""

        if not isinstance(slot, EquipmentSlot):
            raise TypeError("slot must be an EquipmentSlot")
        if slot not in (EquipmentSlot.RIGHT, EquipmentSlot.LEFT):
            raise ValueError("weapon slot must be RIGHT or LEFT")
        item = self.item_at(slot)
        return item if item is not None and item.is_weapon else None

    def armor_items(self) -> tuple[Item, ...]:
        """Return equipped shields and armor contributing defense values."""

        return tuple(item for item in self.equipped_items() if item.is_armor)

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
class HandHit:
    """One hand's final hit value and separated hit bonuses."""

    total: int
    weapon_level_bonus: int
    cross_weapon_bonus: int

    @property
    def bonus(self) -> int:
        """Return all bonuses included in this hand's final hit value."""

        return self.weapon_level_bonus + self.cross_weapon_bonus


@dataclass(frozen=True)
class BattleStats:
    """Battle status values derived from current member state."""

    attack_right: int
    attack_left: int | None
    hit_right: HandHit
    hit_left: HandHit | None
    defense: int
    evasion: int
    spell_resistance: int

    @property
    def hit(self) -> int:
        """Return the displayed hit value, averaging two weapons if present."""

        if self.hit_left is None:
            return self.hit_right.total
        return (self.hit_right.total + self.hit_left.total) // 2

    @property
    def hit_bonus(self) -> int:
        """Return the displayed total hit bonus."""

        if self.hit_left is None:
            return self.hit_right.bonus
        return (self.hit_right.bonus + self.hit_left.bonus) // 2


@dataclass(frozen=True)
class FacePosition:
    """Top-left pixel position of one face in the player face sheet."""

    x: int
    y: int

    def __post_init__(self) -> None:
        for name in ("x", "y"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise MemberDataError(
                    f"character.face_{name} must be an integer"
                )
            if value < 0 or value % 32 != 0:
                raise MemberDataError(
                    f"character.face_{name} must be a non-negative "
                    "multiple of 32"
                )


@dataclass(frozen=True)
class CharacterDefinition:
    """Immutable master data loaded from one ``characters.json`` record."""

    key: str
    names: Mapping[str, object]
    character_type: CharacterType
    race: Race
    gender: Gender
    face_position: FacePosition
    battle_sprite: int
    level_difference: int
    base_hp: int
    base_mp: int
    base_abilities: BaseAbilities
    initial_skill_keys: tuple[str, ...]
    initial_equipment_keys: Mapping[EquipmentSlot, str]
    proficiency_aptitudes: Mapping[
        ProficiencyKind,
        ProficiencyAptitude,
    ]

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
        key = names.get("name_en")
        if not key:
            raise MemberDataError("character.name_en must be a non-empty string")

        character_type = cls._enum_value(record, "type", CharacterType)
        race = cls._enum_value(record, "race", Race)
        gender = cls._enum_value(record, "gender", Gender)
        level_difference = _validate_integer_value(
            "lv_diff",
            record.get("lv_diff"),
        )
        base_hp = _validate_ability_value("base_hp", record.get("base_hp"))
        base_mp = _validate_ability_value("base_mp", record.get("base_mp"))
        base_abilities = BaseAbilities(
            strength=_validate_ability_value("base_str", record.get("base_str")),
            agility=_validate_ability_value("base_agi", record.get("base_agi")),
            magic=_validate_ability_value("base_mag", record.get("base_mag")),
        )
        face_position = FacePosition(
            x=record.get("face_x"),
            y=record.get("face_y"),
        )
        battle_sprite = _validate_integer_value(
            "battle_sprite",
            record.get("battle_sprite", 0),
        )
        if battle_sprite < 0:
            raise MemberDataError("character.battle_sprite must not be negative")
        initial_skill_keys = _string_keys(record, "skills")
        initial_equipment_keys: dict[EquipmentSlot, str] = {}
        for slot, field_name in EQUIPMENT_RECORD_FIELDS.items():
            value = record.get(field_name, "")
            if not isinstance(value, str):
                raise MemberDataError(f"character.{field_name} must be a string")
            initial_equipment_keys[slot] = value
        return cls(
            key,
            MappingProxyType(names),
            character_type,
            race,
            gender,
            face_position,
            battle_sprite,
            level_difference,
            base_hp,
            base_mp,
            base_abilities,
            initial_skill_keys,
            MappingProxyType(initial_equipment_keys),
            _proficiency_aptitudes(record),
        )

    def joining_internal_level(self, fiora_internal_level: int) -> int:
        """Return this character's internal level at first recruitment."""

        if (
            isinstance(fiora_internal_level, bool)
            or not isinstance(fiora_internal_level, int)
        ):
            raise TypeError("fiora_internal_level must be an integer")
        if not MIN_INTERNAL_LEVEL <= fiora_internal_level <= MAX_INTERNAL_LEVEL:
            raise ValueError(
                f"fiora_internal_level must be from {MIN_INTERNAL_LEVEL} "
                f"to {MAX_INTERNAL_LEVEL}"
            )
        if self.key == FIORA_CHARACTER_KEY:
            return MIN_INTERNAL_LEVEL
        return min(
            max(
                fiora_internal_level + self.level_difference,
                MIN_INTERNAL_LEVEL,
            ),
            MAX_INTERNAL_LEVEL,
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
    internal_level: int = MIN_INTERNAL_LEVEL
    experience_offset: int = 0
    hp: int | None = None
    max_hp: int | None = None
    mp: int | None = None
    max_mp: int | None = None
    formation_row: FormationRow = FormationRow.FRONT
    poisoned: bool = False
    paralyzed: bool = False
    sleeping: int = 0
    confused: int = 0
    stunned: bool = False
    protection_level: int = 0
    speed_modifier: int = 0
    skills: list[Skill] = field(default_factory=list)
    equipment: EquipmentSet = field(default_factory=EquipmentSet)
    proficiencies: dict[ProficiencyKind, Proficiency] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.definition, CharacterDefinition):
            raise TypeError("definition must be a CharacterDefinition")
        if (
            isinstance(self.internal_level, bool)
            or not isinstance(self.internal_level, int)
        ):
            raise TypeError("internal_level must be an integer")
        if not MIN_INTERNAL_LEVEL <= self.internal_level <= MAX_INTERNAL_LEVEL:
            raise ValueError(
                f"internal_level must be from {MIN_INTERNAL_LEVEL} "
                f"to {MAX_INTERNAL_LEVEL}"
            )
        if isinstance(self.experience_offset, bool) or not isinstance(
            self.experience_offset, int
        ):
            raise TypeError("experience_offset must be an integer")
        if not isinstance(self.proficiencies, dict):
            raise TypeError("proficiencies must be a dictionary")
        if not self.proficiencies:
            is_fiora = self.definition.key == FIORA_CHARACTER_KEY
            self.proficiencies = {
                kind: Proficiency.for_joining_member(
                    aptitude,
                    self.internal_level,
                    is_fiora=is_fiora,
                )
                for kind, aptitude in self.definition.proficiency_aptitudes.items()
            }
        if set(self.proficiencies) != set(ProficiencyKind):
            raise ValueError("proficiencies must contain every ProficiencyKind")
        for kind, proficiency in self.proficiencies.items():
            if not isinstance(kind, ProficiencyKind):
                raise TypeError("proficiency keys must be ProficiencyKind values")
            if not isinstance(proficiency, Proficiency):
                raise TypeError("proficiencies must contain Proficiency values")
            expected = self.definition.proficiency_aptitudes[kind]
            if proficiency.aptitude is not expected:
                raise MemberDataError(
                    "proficiency aptitude differs from character data: "
                    f"{kind.value}"
                )

        calculated_max_hp = min(
            self.definition.base_hp * (4 + self.internal_level) // 5,
            MAX_HP,
        )
        maximum_spell_level = max(
            self.proficiency(kind).level for kind in SPELL_PROFICIENCY_KINDS
        )
        calculated_max_mp = min(
            self.definition.base_mp
            * (11 + self.internal_level)
            * (7 + maximum_spell_level)
            // 200,
            MAX_MP,
        )
        if self.max_hp is None:
            self.max_hp = calculated_max_hp
        if self.hp is None:
            self.hp = self.max_hp
        if self.max_mp is None:
            self.max_mp = calculated_max_mp
        if self.mp is None:
            self.mp = self.max_mp
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
        if not isinstance(self.formation_row, FormationRow):
            raise TypeError("formation_row must be a FormationRow")
        for name in ("poisoned", "paralyzed", "stunned"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean")
        for name in ("sleeping", "confused"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        if (
            isinstance(self.protection_level, bool)
            or not isinstance(self.protection_level, int)
        ):
            raise TypeError("protection_level must be an integer")
        if not (
            MIN_PROTECTION_LEVEL
            <= self.protection_level
            <= MAX_PROTECTION_LEVEL
        ):
            raise ValueError(
                "protection_level must be from "
                f"{MIN_PROTECTION_LEVEL} to {MAX_PROTECTION_LEVEL}"
            )
        if (
            isinstance(self.speed_modifier, bool)
            or not isinstance(self.speed_modifier, int)
        ):
            raise TypeError("speed_modifier must be an integer")
        if not MIN_SPEED_MODIFIER <= self.speed_modifier <= MAX_SPEED_MODIFIER:
            raise ValueError(
                f"speed_modifier must be from {MIN_SPEED_MODIFIER} "
                f"to {MAX_SPEED_MODIFIER}"
            )
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
        fiora_internal_level: int = MIN_INTERNAL_LEVEL,
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
            internal_level=definition.joining_internal_level(
                fiora_internal_level
            ),
            experience_offset=required_experience_for_level(
                definition.joining_internal_level(fiora_internal_level)
            ),
            skills=current_skills,
            equipment=equipment,
        )

    @classmethod
    def from_record_at_internal_level(
        cls,
        record: Mapping[str, object],
        internal_level: int,
        *,
        items: Mapping[str, Item] | None = None,
        skills: Mapping[str, Skill] | None = None,
    ) -> Member:
        """Recreate initial member state at one explicit internal level.

        This is intentionally separate from :meth:`from_record`: normal
        recruitment derives a member's level from Fiora and always starts
        Fiora at level 1.  Restore, migration, and debug tooling sometimes
        need to construct the same master-data-backed state at a known level.
        """

        if (
            isinstance(internal_level, bool)
            or not isinstance(internal_level, int)
        ):
            raise TypeError("internal_level must be an integer")
        if not MIN_INTERNAL_LEVEL <= internal_level <= MAX_INTERNAL_LEVEL:
            raise ValueError(
                f"internal_level must be from {MIN_INTERNAL_LEVEL} "
                f"to {MAX_INTERNAL_LEVEL}"
            )

        member = cls.from_record(record, items=items, skills=skills)
        is_fiora_start = (
            member.definition.key == FIORA_CHARACTER_KEY
            and internal_level == MIN_INTERNAL_LEVEL
        )
        proficiencies = {
            kind: Proficiency.for_joining_member(
                aptitude,
                internal_level,
                is_fiora=is_fiora_start,
            )
            for kind, aptitude in member.definition.proficiency_aptitudes.items()
        }
        return cls(
            member.definition,
            internal_level=internal_level,
            experience_offset=required_experience_for_level(internal_level),
            skills=member.skills,
            equipment=member.equipment,
            proficiencies=proficiencies,
        )

    def set_joining_experience_offset(self, shared_experience: int) -> None:
        """Anchor this member's joining level against current shared experience."""

        if isinstance(shared_experience, bool) or not isinstance(
            shared_experience, int
        ):
            raise TypeError("shared_experience must be an integer")
        if shared_experience < 0:
            raise ValueError("shared_experience must not be negative")
        self.experience_offset = (
            required_experience_for_level(self.internal_level) - shared_experience
        )

    def refresh_internal_level(self, shared_experience: int) -> int:
        """Recalculate and store internal level from shared experience plus offset."""

        if isinstance(shared_experience, bool) or not isinstance(
            shared_experience, int
        ):
            raise TypeError("shared_experience must be an integer")
        if shared_experience < 0:
            raise ValueError("shared_experience must not be negative")
        self.internal_level = internal_level_for_experience(
            shared_experience + self.experience_offset
        )
        return self.internal_level

    def calculated_max_hp(self) -> int:
        """Return the current internal-level HP ceiling without mutating state."""

        return min(self._uncapped_max_hp(self.internal_level), MAX_HP)

    def apply_max_hp_growth(self) -> int:
        """Move max HP toward its ceiling by at most one internal-level step."""

        target = self.calculated_max_hp()
        if target <= self.max_hp:
            return 0
        step = max(
            1,
            self._uncapped_max_hp(self.internal_level)
            - self._uncapped_max_hp(self.internal_level - 1),
        )
        amount = min(target - self.max_hp, step)
        self.max_hp += amount
        return amount

    def maximum_spell_level(self) -> int:
        """Return the highest current level among the three spell schools."""

        return max(
            self.proficiency(kind).level for kind in SPELL_PROFICIENCY_KINDS
        )

    def calculated_max_mp(self) -> int:
        """Return the current level/proficiency MP ceiling without mutating state."""

        return min(
            self._uncapped_max_mp(
                self.internal_level,
                self.maximum_spell_level(),
            ),
            MAX_MP,
        )

    def apply_max_mp_growth(
        self,
        *,
        maximum_spell_level_increased: bool,
    ) -> int:
        """Move max MP toward its ceiling by one relevant level step."""

        if not isinstance(maximum_spell_level_increased, bool):
            raise TypeError("maximum_spell_level_increased must be a boolean")
        target = self.calculated_max_mp()
        if target <= self.max_mp:
            return 0
        maximum_spell_level = self.maximum_spell_level()
        current_raw = self._uncapped_max_mp(
            self.internal_level,
            maximum_spell_level,
        )
        if maximum_spell_level_increased:
            previous_raw = self._uncapped_max_mp(
                self.internal_level,
                maximum_spell_level - 1,
            )
        else:
            previous_raw = self._uncapped_max_mp(
                self.internal_level - 1,
                maximum_spell_level,
            )
        amount = min(target - self.max_mp, max(1, current_raw - previous_raw))
        self.max_mp += amount
        return amount

    def _uncapped_max_hp(self, internal_level: int) -> int:
        return self.definition.base_hp * (4 + internal_level) // 5

    def _uncapped_max_mp(
        self,
        internal_level: int,
        maximum_spell_level: int,
    ) -> int:
        return (
            self.definition.base_mp
            * (11 + internal_level)
            * (7 + maximum_spell_level)
            // 200
        )

    @property
    def adjusted_abilities(self) -> AdjustedAbilities:
        """Return current abilities without mutating their master-data base."""

        base = self.definition.base_abilities
        equipment = self.equipment.equipped_items()
        return AdjustedAbilities(
            strength=min(
                MAX_ABILITY,
                base.strength
                + sum(item.strength_modifier for item in equipment),
            ),
            agility=min(
                MAX_ABILITY,
                base.agility
                + sum(item.agility_modifier for item in equipment),
            ),
            magic=min(
                MAX_ABILITY,
                base.magic
                + sum(item.magic_modifier for item in equipment),
            ),
        )

    @property
    def face_position(self) -> FacePosition:
        """Return this member's immutable face-sheet position."""

        return self.definition.face_position

    @property
    def is_front_row(self) -> bool:
        """Return whether the member currently occupies the front row."""

        return self.formation_row is FormationRow.FRONT

    @property
    def is_alive(self) -> bool:
        """Return whether the member has at least one HP."""

        return self.hp > 0

    @property
    def is_dead(self) -> bool:
        """Return whether the member has no HP remaining."""

        return not self.is_alive

    @property
    def is_dying(self) -> bool:
        """Return DA2's near-death state, including poison at any HP."""

        return self.poisoned or (
            self.is_alive and self.hp <= self.max_hp // 4
        )

    @property
    def has_curable_ailment(self) -> bool:
        """Return whether DA2's CURE spell can clear a current ailment."""

        return bool(
            self.poisoned
            or self.paralyzed
            or self.sleeping
            or self.confused
        )

    @property
    def is_npc(self) -> bool:
        """Return whether this member uses the NPC equipment rules."""

        return self.definition.character_type is CharacterType.NPC

    def is_equipment_fixed(self, slot: EquipmentSlot) -> bool:
        """Return whether the NPC's initial item still occupies ``slot``."""

        if not isinstance(slot, EquipmentSlot):
            raise TypeError("slot must be an EquipmentSlot")
        current = self.equipment.item_at(slot)
        return (
            self.is_npc
            and current is not None
            and current.key == self.definition.initial_equipment_keys[slot]
        )

    @property
    def healing(self) -> int:
        """Return field HP recovery supplied by currently equipped items."""

        if self.hp <= 0:
            return 0
        return sum(item.healing for item in self.equipment.equipped_items())

    @property
    def battle_healing(self) -> int:
        """Return battle recovery levels from equipment and Regenerate."""

        if self.hp <= 0:
            return 0
        return self.healing + int(self.has_skill(_REGENERATE_SKILL_KEY))

    @property
    def heal_and_poison_amount(self) -> int:
        """Return the next net field HP change without mutating the member."""

        if self.hp <= 0:
            return 0
        return self.healing - int(self.poisoned)

    def apply_heal_and_poison(self) -> int:
        """Apply one field recovery/poison tick and return the actual HP delta."""

        old_hp = self.hp
        self.hp = min(
            self.max_hp,
            max(0, self.hp + self.heal_and_poison_amount),
        )
        if old_hp > 0 and self.hp <= 0:
            self._clear_conditions_on_death()
        return self.hp - old_hp

    def _clear_conditions_on_death(self) -> None:
        """Clear persistent and temporary conditions when HP reaches zero."""

        self.poisoned = False
        self.paralyzed = False
        self.sleeping = 0
        self.confused = 0
        self.stunned = False
        self.protection_level = 0
        self.speed_modifier = 0

    def apply_healing(self, amount: int, *, cure_ailments: bool = False) -> int:
        """Apply a non-negative recovery and optionally clear all ailments."""

        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TypeError("amount must be an integer")
        if amount < 0:
            raise ValueError("amount must not be negative")
        if not isinstance(cure_ailments, bool):
            raise TypeError("cure_ailments must be a boolean")
        old_hp = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        if cure_ailments:
            self.poisoned = False
            self.paralyzed = False
            self.sleeping = 0
            self.confused = 0
            self.stunned = False
        return self.hp - old_hp

    def cure_ailments(self) -> bool:
        """Clear the four ailments removed by DA2's CURE spell."""

        cured = self.has_curable_ailment
        self.poisoned = False
        self.paralyzed = False
        self.sleeping = 0
        self.confused = 0
        return cured

    def take_damage(self, damage: int) -> int:
        """Apply battle damage, waking from sleep or confusion like DA2."""

        if isinstance(damage, bool) or not isinstance(damage, int):
            raise TypeError("damage must be an integer")
        if damage < 0:
            raise ValueError("damage must not be negative")
        old_hp = self.hp
        self.hp = max(0, self.hp - damage)
        if damage > 0:
            self.sleeping = 0
            self.confused = 0
        if self.hp <= 0:
            self._clear_conditions_on_death()
        return old_hp - self.hp

    def take_poison_damage(self, damage: int) -> int:
        """Apply poison damage without clearing sleep or confusion."""

        if isinstance(damage, bool) or not isinstance(damage, int):
            raise TypeError("damage must be an integer")
        if damage < 0:
            raise ValueError("damage must not be negative")
        old_hp = self.hp
        self.hp = max(0, self.hp - damage)
        if self.hp <= 0:
            self._clear_conditions_on_death()
        return old_hp - self.hp

    def apply_poison(self) -> bool:
        """Apply persistent poison and report whether the state changed."""

        if self.poisoned or not self.is_alive:
            return False
        self.poisoned = True
        return True

    def apply_sleep(self, turns: int) -> None:
        """Apply DA2's non-shortening sleep duration and clear confusion."""

        if isinstance(turns, bool) or not isinstance(turns, int):
            raise TypeError("turns must be an integer")
        if turns <= 0:
            raise ValueError("turns must be positive")
        self.sleeping = max(self.sleeping, turns)
        self.confused = 0

    def elapse_sleep_turn(self) -> bool:
        """Consume one sleeping action and report whether it was skipped."""

        if self.sleeping <= 0:
            return False
        self.sleeping -= 1
        return True

    def apply_stun(self) -> bool:
        """Mark the next timeline action to be skipped once."""

        if self.stunned or not self.is_alive:
            return False
        self.stunned = True
        return True

    def consume_stun(self) -> bool:
        """Clear one pending stun and report that this action must be skipped."""

        if not self.stunned:
            return False
        self.stunned = False
        return True

    def apply_protection(self) -> bool:
        """Raise DA2's defense buff by one stage, up to its second stage."""

        if self.protection_level >= MAX_PROTECTION_LEVEL:
            return False
        self.protection_level += 1
        return True

    def apply_defense_down(self) -> bool:
        """Lower DA2's defense stage once, cancelling protection first."""

        if self.protection_level <= MIN_PROTECTION_LEVEL or not self.is_alive:
            return False
        self.protection_level -= 1
        return True

    def apply_slow(self) -> bool:
        """Apply DA2's SLOW state or cancel any positive HASTE state."""

        if self.speed_modifier <= MIN_SPEED_MODIFIER:
            return False
        self.speed_modifier = 0 if self.speed_modifier > 0 else MIN_SPEED_MODIFIER
        return True

    def apply_haste(self) -> bool:
        """Raise DA2's battle speed by one stage, up to the second stage."""

        if self.speed_modifier >= MAX_SPEED_MODIFIER or not self.is_alive:
            return False
        self.speed_modifier += 1
        return True

    def defeat(self) -> None:
        """Set HP to zero and clear battle modifiers after instant death."""

        self.hp = 0
        self._clear_conditions_on_death()

    @property
    def effective_agility(self) -> int:
        """Return equipment-adjusted agility with the battle modifier."""

        return modified_agility(
            self.adjusted_abilities.agility,
            self.speed_modifier,
        )

    def clear_temporary_battle_conditions(self) -> None:
        """Discard ailments that DA2 keeps only for the current battle."""

        self.sleeping = 0
        self.confused = 0
        self.stunned = False
        self.protection_level = 0
        self.speed_modifier = 0

    def recover_world_map_entry_ailments(self) -> None:
        """Restore points and clear non-death conditions on world-map entry."""

        if self.is_alive:
            self.hp = self.max_hp
        self.mp = self.max_mp
        self.poisoned = False
        self.paralyzed = False
        self.sleeping = 0
        self.confused = 0
        self.stunned = False
        self.protection_level = 0
        self.speed_modifier = 0

    def fully_recover(self) -> None:
        """Restore HP and MP and clear every current abnormal condition."""

        self.hp = self.max_hp
        self.mp = self.max_mp
        self.poisoned = False
        self.paralyzed = False
        self.sleeping = 0
        self.confused = 0
        self.stunned = False
        self.protection_level = 0
        self.speed_modifier = 0

    def proficiency(self, kind: ProficiencyKind) -> Proficiency:
        """Return the current proficiency for one stable kind."""

        if not isinstance(kind, ProficiencyKind):
            raise TypeError("kind must be a ProficiencyKind")
        return self.proficiencies[kind]

    def weapon_level(self, weapon: Item) -> int:
        """Return the current proficiency level for one weapon."""

        if not isinstance(weapon, Item):
            raise TypeError("weapon must be an Item")
        if not weapon.is_weapon:
            raise ValueError("weapon must be a weapon item")
        return self.proficiency(self._weapon_proficiency_kind(weapon)).level

    @property
    def resistances(self) -> frozenset[ResistanceType]:
        """Return the union of resistances on all currently equipped items."""

        return frozenset(
            resistance
            for item in self.equipment.equipped_items()
            for resistance in item.resistances
        )

    def has_skill(
        self,
        key: str,
        *,
        equipment: EquipmentSet | None = None,
    ) -> bool:
        """Return whether a learned skill or the supplied equipment grants ``key``."""

        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        if equipment is not None and not isinstance(equipment, EquipmentSet):
            raise TypeError("equipment must be an EquipmentSet or None")
        if any(skill.key == key for skill in self.skills):
            return True
        item_special = _EQUIPMENT_GRANTED_SKILLS.get(key)
        active_equipment = self.equipment if equipment is None else equipment
        return item_special is not None and any(
            item.special is item_special for item in active_equipment.equipped_items()
        )

    def can_equip(self, item: Item) -> bool:
        """Return intrinsic eligibility for one equipment item.

        Slot conflicts and inventory exchange are intentionally outside this
        check. This method covers aptitude, equipment class, and the stable
        requirements currently present in ``items.json``.
        """

        if not isinstance(item, Item):
            raise TypeError("item must be an Item")
        if not item.is_equipment:
            return False

        proficiency_kind = _EQUIPMENT_PROFICIENCY_BY_SUBTYPE.get(item.subtype)
        if proficiency_kind is not None:
            if (
                self.proficiency(proficiency_kind).aptitude
                is ProficiencyAptitude.DISABLED
            ):
                return False
        elif item.subtype == "GENERAL":
            pass
        elif item.subtype == "HEAVY":
            if (
                self.proficiency(ProficiencyKind.SHIELD).aptitude
                is ProficiencyAptitude.DISABLED
            ):
                return False
        elif item.subtype == "MAGICAL":
            if not any(
                self.proficiency(kind).aptitude
                is not ProficiencyAptitude.DISABLED
                for kind in SPELL_PROFICIENCY_KINDS
            ):
                return False
        else:
            raise MemberDataError(
                f"unsupported equipment subtype: {item.subtype}"
            )

        requirement = item.requirement
        if not requirement:
            return True
        if requirement == "LV9":
            if proficiency_kind is None:
                raise MemberDataError(
                    f"LV9 requires a proficiency subtype: {item.subtype}"
                )
            return self.proficiency(proficiency_kind).level >= 9
        if requirement == "ONLY_RAGNA":
            return self.definition.key == "Ragna"
        if requirement == "NO_FAIRYS":
            return self.definition.race is not Race.FAIRY
        if requirement == "ONLY_FAIRYS":
            return self.definition.race is Race.FAIRY
        if requirement == "NO_DRAGONS":
            return self.definition.race is not Race.DRAGONEWT
        if requirement == "ONLY_DRAGON":
            return self.definition.race is Race.DRAGONEWT
        if requirement == "ONLY_ROBO":
            return self.definition.race is Race.ROBOT
        if requirement == "ONLY_FEMALE":
            return self.definition.gender is Gender.FEMALE
        if requirement == "ONLY_MALE":
            return self.definition.gender is Gender.MALE
        raise MemberDataError(f"unsupported equipment requirement: {requirement}")

    def can_equip_at(self, item: Item, slot: EquipmentSlot) -> bool:
        """Return intrinsic eligibility for an item in one physical slot.

        Inventory availability and conflicts with already occupied slots are
        handled by ``InventorySystem`` because they can return displaced items.
        """

        if not isinstance(item, Item):
            raise TypeError("item must be an Item")
        if not isinstance(slot, EquipmentSlot):
            raise TypeError("slot must be an EquipmentSlot")
        if not self.can_equip(item):
            return False
        if item.equip_type not in _EQUIPMENT_TYPES_BY_SLOT[slot]:
            return False
        if (
            slot is EquipmentSlot.LEFT
            and item.equip_type is ItemEquipType.RIGHT
            and not self.has_skill(_DUAL_WIELD_SKILL_KEY)
        ):
            return False
        return True

    @staticmethod
    def _weapon_proficiency_kind(weapon: Item) -> ProficiencyKind:
        try:
            return _WEAPON_PROFICIENCY_BY_SUBTYPE[weapon.subtype]
        except KeyError as error:
            raise MemberDataError(
                f"unsupported weapon subtype: {weapon.subtype}"
            ) from error

    def _uses_two_handed_skill(self, weapon: Item) -> bool:
        kind = self._weapon_proficiency_kind(weapon)
        return (
            self.has_skill(_TWO_HANDED_SKILL_KEY)
            and self.equipment.item_at(EquipmentSlot.LEFT) is None
            and kind in _TWO_HANDED_SKILL_KINDS
        )

    def uses_two_handed_weapon(self, weapon: Item) -> bool:
        """Return whether one weapon receives the current two-hand bonus."""

        if not isinstance(weapon, Item):
            raise TypeError("weapon must be an Item")
        return self._uses_two_handed_skill(weapon)

    def _cross_weapon_hit_bonus(
        self,
        equipped_kinds: frozenset[ProficiencyKind],
    ) -> int:
        bonus = 0
        for kind in WEAPON_PROFICIENCY_KINDS - equipped_kinds:
            proficiency = self.proficiency(kind)
            if (proficiency.level, proficiency.progress) == (9, 99):
                bonus += 2
            elif (proficiency.level, proficiency.progress) == (8, 99):
                bonus += 1
        return bonus

    def _hand_hit(self, weapon: Item, cross_weapon_bonus: int) -> HandHit:
        level = self.weapon_level(weapon)
        weapon_level_bonus = (level - 1) * 2
        return HandHit(
            total=weapon.hit + weapon_level_bonus + cross_weapon_bonus,
            weapon_level_bonus=weapon_level_bonus,
            cross_weapon_bonus=cross_weapon_bonus,
        )

    @property
    def battle_stats(self) -> BattleStats:
        """Calculate battle status from current equipment and proficiencies."""

        right_weapon = self.equipment.weapon_at(EquipmentSlot.RIGHT)
        left_weapon = self.equipment.weapon_at(EquipmentSlot.LEFT)
        weapons = tuple(
            weapon
            for weapon in (right_weapon, left_weapon)
            if weapon is not None
        )
        equipped_kinds = frozenset(
            self._weapon_proficiency_kind(weapon) for weapon in weapons
        )
        cross_weapon_bonus = self._cross_weapon_hit_bonus(equipped_kinds)

        attack_right = right_weapon.attack if right_weapon is not None else 0
        if right_weapon is not None and self._uses_two_handed_skill(right_weapon):
            attack_right = right_weapon.attack * 15 // 10
        attack_left = (
            left_weapon.attack * 8 // 10
            if left_weapon is not None
            else None
        )

        hit_right = (
            self._hand_hit(right_weapon, cross_weapon_bonus)
            if right_weapon is not None
            else HandHit(
                total=0,
                weapon_level_bonus=0,
                cross_weapon_bonus=0,
            )
        )
        hit_left = (
            self._hand_hit(left_weapon, cross_weapon_bonus)
            if left_weapon is not None
            else None
        )

        armor = self.equipment.armor_items()
        base_defense = sum(item.defense for item in armor)
        defense_level = (
            -2 if self.protection_level < 0 else self.protection_level
        )
        defense = max(
            0,
            int(
                (base_defense + defense_level * 5)
                * (1.0 + defense_level / 4)
            ),
        )
        abilities = self.adjusted_abilities
        agility_bonus = max(0, (self.effective_agility - 20) * 2)
        evasion = max(
            0,
            sum(item.evasion for item in armor) + agility_bonus,
        )
        spell_resistance = (
            sum(item.spell_resistance for item in armor)
            + abilities.magic // 2
        )
        return BattleStats(
            attack_right=attack_right,
            attack_left=attack_left,
            hit_right=hit_right,
            hit_left=hit_left,
            defense=defense,
            evasion=evasion,
            spell_resistance=spell_resistance,
        )

    def status(
        self,
        localizer: Localizer,
        texts: TextCatalog,
        *,
        show_ok: bool = False,
    ) -> str:
        """Return the localized condition, optional healthy text, or nothing."""

        if not isinstance(localizer, Localizer):
            raise TypeError("localizer must be a Localizer")
        if not isinstance(texts, TextCatalog):
            raise TypeError("texts must be a TextCatalog")
        if not isinstance(show_ok, bool):
            raise TypeError("show_ok must be a boolean")

        text_key = None
        icon = ""
        if self.hp <= 0:
            text_key = "status.dead"
            icon = "%DEATH%"
        elif self.paralyzed:
            text_key = "term.condition.PARALIZE"
        elif self.sleeping:
            text_key = "term.condition.SLEEP"
        elif self.confused:
            text_key = "term.condition.CONFUSE"
        elif self.poisoned:
            text_key = "term.condition.POISON"
        elif show_ok:
            text_key = "status.ok"

        if text_key is not None:
            value = texts.text(text_key, localizer)
            if not value:
                raise MemberDataError(
                    f"localized member text is missing: {text_key}"
                )
            return icon + value
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
