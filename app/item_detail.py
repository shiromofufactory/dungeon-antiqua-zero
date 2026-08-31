"""Context-aware item-detail presentation independent of Pyxel screens."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

if __package__ == "":
    from item import (
        AdditionalEffect,
        AttackAttribute,
        Item,
        ItemEquipType,
        ItemSpecial,
    )
    from localization import (
        LocalizedText,
        Localizer,
        format_number,
        normalize_ascii_display_text,
    )
    from monster import MonsterTribe
    from resistance import ResistanceType
    from spell import Spell, SpellType
    from state import Language
    from text_catalog import TextCatalog
    from ui import TEXT_ICONS
else:
    from .item import (
        AdditionalEffect,
        AttackAttribute,
        Item,
        ItemEquipType,
        ItemSpecial,
    )
    from .localization import (
        LocalizedText,
        Localizer,
        format_number,
        normalize_ascii_display_text,
    )
    from .monster import MonsterTribe
    from .resistance import ResistanceType
    from .spell import Spell, SpellType
    from .state import Language
    from .text_catalog import TextCatalog
    from .ui import TEXT_ICONS


class ItemDetailError(RuntimeError):
    """Raised when item detail cannot be built from the supplied masters."""


class ItemDetailContext(StrEnum):
    """Screens that consume a shared item-detail presentation."""

    MENU = "menu"
    SHOP = "shop"
    BATTLE = "battle"


@dataclass(frozen=True)
class ItemDetailView:
    """Display lines plus shop-only metadata for one item."""

    lines: tuple[str, ...]
    price: int | None = None
    source: str | None = None


ITEM_TYPE_TEXT_KEYS = {
    ItemEquipType.ITEM: "item.detail.type.ITEM",
    ItemEquipType.RIGHT: "item.detail.type.RIGHT",
    ItemEquipType.LEFT: "item.detail.type.LEFT",
    ItemEquipType.TWO_HANDS: "item.detail.type.TWO_HANDS",
    ItemEquipType.BODY: "item.detail.type.BODY",
    ItemEquipType.HEAD: "item.detail.type.HEAD",
    ItemEquipType.ARM: "item.detail.type.ARM",
}
ITEM_TYPES_WITH_SUBTYPE = frozenset(
    (
        ItemEquipType.RIGHT,
        ItemEquipType.TWO_HANDS,
        ItemEquipType.BODY,
        ItemEquipType.HEAD,
        ItemEquipType.ARM,
    )
)
ITEM_SUBTYPE_TEXT_KEYS = {
    subtype: f"item.detail.subtype.{subtype}"
    for subtype in (
        "ITEM",
        "SWORD",
        "KNIFE",
        "KATANA",
        "SPEAR",
        "HAMMER",
        "AXE",
        "THROWING",
        "ROD",
        "WAND",
        "SHIELD",
        "GENERAL",
        "HEAVY",
        "MAGICAL",
    )
}
ITEM_REQUIREMENT_TEXT_KEYS = {
    requirement: f"item.detail.requirement.{requirement}"
    for requirement in (
        "LV9",
        "NO_DRAGONS",
        "NO_FAIRYS",
        "ONLY_DRAGON",
        "ONLY_FAIRYS",
        "ONLY_FEMALE",
        "ONLY_MALE",
        "ONLY_RAGNA",
        "ONLY_ROBO",
    )
}
ITEM_STAT_ROWS = (
    ("attack", "item.detail.attack"),
    ("hit", "item.detail.hit"),
    ("defense", "item.detail.defense"),
    ("evasion", "item.detail.evasion"),
    ("spell_resistance", "item.detail.spell_resistance"),
)
ITEM_ABILITY_ROWS = (
    ("strength_modifier", "status.strength"),
    ("agility_modifier", "status.agility"),
    ("magic_modifier", "status.magic"),
)
ITEM_ATTACK_ATTRIBUTE_TEXT_KEYS = {
    attribute: f"item.detail.attribute.{attribute.value}"
    for attribute in AttackAttribute
}
ITEM_ADDITIONAL_EFFECT_TEXT_KEYS = {
    effect: f"item.detail.additional_effect.{effect.value}"
    for effect in AdditionalEffect
}
ITEM_SPECIAL_TEXT_KEYS = {
    special: f"item.detail.special.{special.value}" for special in ItemSpecial
}
ITEM_TRIBE_TEXT_KEYS = {
    tribe: f"item.detail.tribe.{tribe.value}"
    for tribe in MonsterTribe
}
ITEM_RESISTANCE_TEXT_KEYS = {
    resistance: f"item.detail.resistance.{resistance.value}"
    for resistance in ResistanceType
}
ITEM_TYPE_ICON_TAGS = {
    ItemEquipType.LEFT: "%SHIELD%",
    ItemEquipType.HEAD: "%HEAD%",
    ItemEquipType.BODY: "%BODY%",
    ItemEquipType.ARM: "%ARM%",
}


def _required_catalog_text(
    texts: TextCatalog,
    key: str,
    localizer: Localizer,
) -> str:
    text = texts.text(key, localizer)
    if not text:
        raise ItemDetailError(f"アイテム詳細用テキストが見つかりません: {key}")
    return text


def _required_catalog_lines(
    texts: TextCatalog,
    key: str,
    localizer: Localizer,
) -> tuple[str, ...]:
    lines = texts.lines(key, localizer)
    if not lines:
        raise ItemDetailError(f"アイテム詳細用テキストが見つかりません: {key}")
    return lines


def _composed_text(localizer: Localizer, *parts: str) -> str:
    text = "".join(str(part) for part in parts)
    if localizer.language is Language.JAPANESE:
        return normalize_ascii_display_text(text)
    narrow_spans: list[tuple[int, int]] = []
    offset = 0
    for part in parts:
        if isinstance(part, LocalizedText):
            narrow_spans.extend(
                (start + offset, end + offset)
                for start, end in part.narrow_spans
            )
        offset += len(part)
    return LocalizedText(
        text,
        prefers_wide_font=any(
            isinstance(part, LocalizedText) and part.prefers_wide_font
            for part in parts
        ),
        narrow_spans=tuple(narrow_spans),
    )


def _item_type_line(
    item: Item,
    localizer: Localizer,
    texts: TextCatalog,
) -> str:
    try:
        type_key = ITEM_TYPE_TEXT_KEYS[item.equip_type]
    except KeyError as error:
        raise ItemDetailError(f"未対応のアイテム種別です: {item.equip_type}") from error
    type_text = _required_catalog_text(texts, type_key, localizer)
    type_icon = ITEM_TYPE_ICON_TAGS.get(item.equip_type, "")
    if type_icon:
        if type_icon not in TEXT_ICONS:
            raise ItemDetailError(f"未対応の種別アイコンです: {type_icon}")
        type_text = _composed_text(localizer, type_icon, type_text)
    if item.equip_type not in ITEM_TYPES_WITH_SUBTYPE:
        return type_text

    try:
        subtype_key = ITEM_SUBTYPE_TEXT_KEYS[item.subtype]
    except KeyError as error:
        raise ItemDetailError(f"未対応のアイテム副種別です: {item.subtype}") from error
    subtype_text = _required_catalog_text(texts, subtype_key, localizer)
    if item.equip_type in (ItemEquipType.RIGHT, ItemEquipType.TWO_HANDS):
        subtype_icon = f"%{item.subtype}%"
        if subtype_icon not in TEXT_ICONS:
            raise ItemDetailError(f"未対応の武器種別アイコンです: {item.subtype}")
        subtype_text = _composed_text(localizer, subtype_icon, subtype_text)
    separator = "/" if localizer.language is Language.ENGLISH else " / "
    return _composed_text(localizer, type_text, separator, subtype_text)


def _item_requirement_line(
    item: Item,
    localizer: Localizer,
    texts: TextCatalog,
) -> str:
    if not item.requirement:
        return ""
    try:
        key = ITEM_REQUIREMENT_TEXT_KEYS[item.requirement]
    except KeyError as error:
        raise ItemDetailError(f"未対応の装備条件です: {item.requirement}") from error
    return _required_catalog_text(texts, key, localizer)


def _signed_modifier(value: int) -> str:
    sign = "＋" if value > 0 else "－"
    return f"{sign}{format_number(abs(value))}"


def _item_use_lines(
    item: Item,
    spells: Mapping[str, Spell],
    localizer: Localizer,
    texts: TextCatalog,
) -> tuple[str, ...]:
    if not item.use_spell_key:
        return ()
    spell = spells.get(item.use_spell_key)
    if spell is None:
        raise ItemDetailError(f"未定義の使用効果です: {item.use_spell_key}")

    lines: list[str] = []
    shows_spell_name = (
        spell.type is not SpellType.ITEM
        and (item.is_equipment or item.is_spell_book)
    )
    if shows_spell_name:
        label = _required_catalog_text(texts, "item.detail.use.spell", localizer)
        lines.append(
            _composed_text(localizer, label, spell.localized_display_name(localizer))
        )
    if item.equip_type is ItemEquipType.ITEM:
        lines.extend(spell.localized_description(localizer))
    if item.breaks_on_use and item.equip_type is not ItemEquipType.ITEM:
        lines.append(_required_catalog_text(texts, "item.detail.breaks_on_use", localizer))
    return tuple(lines)


def build_item_detail(
    item: Item,
    spells: Mapping[str, Spell],
    localizer: Localizer,
    texts: TextCatalog,
    *,
    context: ItemDetailContext = ItemDetailContext.MENU,
) -> ItemDetailView:
    """Build item detail once for menu, shop, or battle consumers."""

    if not isinstance(item, Item):
        raise TypeError("item must be an Item")
    if not isinstance(spells, Mapping) or not all(
        isinstance(key, str) and isinstance(spell, Spell) and key == spell.key
        for key, spell in spells.items()
    ):
        raise TypeError("spells must map each string key to its matching Spell")
    if not isinstance(localizer, Localizer):
        raise TypeError("localizer must be a Localizer")
    if not isinstance(texts, TextCatalog):
        raise TypeError("texts must be a TextCatalog")
    if not isinstance(context, ItemDetailContext):
        raise TypeError("context must be an ItemDetailContext")

    use_lines = _item_use_lines(item, spells, localizer, texts)
    if context is ItemDetailContext.BATTLE:
        return ItemDetailView(lines=use_lines)

    lines = [item.localized_name(localizer), _item_type_line(item, localizer, texts)]
    requirement = _item_requirement_line(item, localizer, texts)
    if requirement:
        lines.append(requirement)

    details: list[str] = []
    for attribute, text_key in ITEM_STAT_ROWS:
        value = getattr(item, attribute)
        if value:
            label = _required_catalog_text(texts, text_key, localizer)
            details.append(_composed_text(localizer, label, "：", format_number(value)))

    if item.attack_attribute is not None:
        label = _required_catalog_text(texts, "item.detail.attribute.label", localizer)
        value = _required_catalog_text(
            texts,
            ITEM_ATTACK_ATTRIBUTE_TEXT_KEYS[item.attack_attribute],
            localizer,
        )
        details.append(_composed_text(localizer, label, value))

    if item.additional_effect is not None:
        label = _required_catalog_text(
            texts,
            "item.detail.additional_effect.label",
            localizer,
        )
        value = _required_catalog_text(
            texts,
            ITEM_ADDITIONAL_EFFECT_TEXT_KEYS[item.additional_effect],
            localizer,
        )
        details.append(_composed_text(localizer, label, value))

    for resistance in ResistanceType:
        if resistance in item.resistances:
            details.append(
                _required_catalog_text(
                    texts,
                    ITEM_RESISTANCE_TEXT_KEYS[resistance],
                    localizer,
                )
            )

    for attribute, text_key in ITEM_ABILITY_ROWS:
        value = getattr(item, attribute)
        if value:
            label = _required_catalog_text(texts, text_key, localizer)
            details.append(_composed_text(localizer, label, " ", _signed_modifier(value)))

    if item.reach == 2:
        details.extend(_required_catalog_lines(texts, "item.detail.reach.2", localizer))
    elif item.reach == 3:
        details.append(_required_catalog_text(texts, "item.detail.reach.3", localizer))
    elif item.reach not in (0, 1):
        raise ItemDetailError(f"未対応の射程です: {item.reach}")

    if item.effective_tribe is not None:
        details.append(
            _required_catalog_text(
                texts,
                ITEM_TRIBE_TEXT_KEYS[item.effective_tribe],
                localizer,
            )
        )

    details.extend(use_lines)

    if item.healing:
        healing_key = (
            "item.detail.healing.positive"
            if item.healing > 0
            else "item.detail.healing.negative"
        )
        details.append(_required_catalog_text(texts, healing_key, localizer))

    if item.special is not None:
        details.extend(
            line
            for line in texts.lines(
                ITEM_SPECIAL_TEXT_KEYS[item.special],
                localizer,
            )
            if line
        )
    if details:
        lines.append("")
        lines.extend(details)

    is_shop = context is ItemDetailContext.SHOP
    return ItemDetailView(
        lines=tuple(lines),
        price=item.price if is_shop else None,
        source=item.source if is_shop else None,
    )


def item_detail_lines(
    item: Item,
    spells: Mapping[str, Spell],
    localizer: Localizer,
    texts: TextCatalog,
    *,
    context: ItemDetailContext = ItemDetailContext.MENU,
) -> tuple[str, ...]:
    """Return only the lines for consumers that do not need shop metadata."""

    return build_item_detail(
        item,
        spells,
        localizer,
        texts,
        context=context,
    ).lines


__all__ = [
    "ItemDetailContext",
    "ItemDetailError",
    "ItemDetailView",
    "build_item_detail",
    "item_detail_lines",
]
