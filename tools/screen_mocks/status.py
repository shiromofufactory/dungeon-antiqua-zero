"""Display the current status-screen layout mock."""

from __future__ import annotations

import json

import pyxel

from tools._bootstrap import APP_ROOT
from input import InputBindings, PyxelInputReader
from item import Item, ItemDataError
from localization import Localizer, format_number
from member import EquipmentSlot, Member, MemberDataError
from resources import (
    TRANSPARENT_INDEX,
    FontResourceError,
    FontResources,
    ImageResourceError,
    ImageResources,
)
from skill import Skill, SkillDataError
from state import Language, Settings
from text_catalog import TextCatalog, TextCatalogError
from ui import TEXT_ICONS, LocalizedWindowTextFactory, WindowFactory, WindowText

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
FPS = 60
FACES_IMAGE_ID = "faces/faces_pc"
MOCK_CHARACTER_KEY = "Fiora"
STATUS_TEXT_KEYS = {
    "label.condition": "status.condition",
    "label.strength": "status.strength",
    "label.agility": "status.agility",
    "label.magic": "status.magic",
    "label.skill": "status.skill",
    "label.equip.right": "status.equip.right",
    "label.equip.left": "status.equip.left",
    "label.equip.body": "status.equip.body",
    "label.equip.head": "status.equip.head",
    "label.equip.arm": "status.equip.arm",
    "label.attack": "status.attack",
    "label.hit": "status.hit",
    "label.defense": "status.defense",
    "label.evasion": "status.evasion",
    "label.spell_resistance": "status.spell_resistance",
    "label.tolerance": "status.tolerance",
}
LOCALIZED_POSITIONS = {
    (14, 2): "member.name",
    (14, 5): "member.race",
    (14, 8): "member.gender",
    (6, 20): "label.condition",
    (22, 20): "value.condition",
    (6, 26): "label.strength",
    (6, 29): "label.agility",
    (6, 32): "label.magic",
    (6, 38): "label.skill",
    (8, 41): "skill.0",
    (8, 44): "skill.1",
    (30, 8): "equipment.right",
    (30, 11): "equipment.left",
    (30, 14): "equipment.body",
    (30, 17): "equipment.head",
    (30, 20): "equipment.arm",
    (30, 26): "label.attack",
    (30, 29): "label.hit",
    (30, 32): "label.defense",
    (30, 35): "label.evasion",
    (30, 38): "label.spell_resistance",
    (30, 41): "label.tolerance",
}
LANGUAGE_SEQUENCE = (
    Language.JAPANESE,
    Language.ENGLISH,
    Language.SIMPLIFIED_CHINESE,
)


def next_language(language: Language) -> Language:
    """Return the next language used by the status mock."""

    if not isinstance(language, Language):
        raise TypeError("language must be a Language")
    index = LANGUAGE_SEQUENCE.index(language)
    return LANGUAGE_SEQUENCE[(index + 1) % len(LANGUAGE_SEQUENCE)]


class StatusMockDataError(RuntimeError):
    """Raised when generated data required by this mock is unavailable."""


def load_data_records(filename: str) -> list[dict[str, object]]:
    """Load one generated array dataset used by the status mock."""

    path = APP_ROOT / "data" / filename
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise StatusMockDataError(f"ゲームデータがありません: {path}") from error
    except json.JSONDecodeError as error:
        raise StatusMockDataError(
            f"ゲームデータを読み込めません: {path}: {error}"
        ) from error

    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise StatusMockDataError(
            f"{filename}のルートはオブジェクトの配列である必要があります"
        )
    return records


def load_mock_member(
    items: dict[str, Item],
    skills: dict[str, Skill],
) -> Member:
    """Load the character used by this mock from generated game data."""

    records = load_data_records("characters.json")
    record = next(
        (
            candidate
            for candidate in records
            if candidate.get("name_en") == MOCK_CHARACTER_KEY
        ),
        None,
    )
    if record is None:
        raise MemberDataError(
            f"モック用キャラクターが見つかりません: {MOCK_CHARACTER_KEY}"
        )
    return Member.from_record(record, items=items, skills=skills)


def load_mock_items() -> dict[str, Item]:
    """Load and index item models by their current data keys."""

    items: dict[str, Item] = {}
    for record in load_data_records("items.json"):
        item = Item.from_record(record)
        if item.key in items:
            raise StatusMockDataError(f"アイテムキーが重複しています: {item.key}")
        items[item.key] = item
    return items


def load_mock_skills() -> dict[str, Skill]:
    """Load and index skill models by their current data keys."""

    skills: dict[str, Skill] = {}
    for record in load_data_records("skills.json"):
        skill = Skill.from_record(record)
        if skill.key in skills:
            raise StatusMockDataError(f"スキルキーが重複しています: {skill.key}")
        skills[skill.key] = skill
    return skills


class StatusScreenMock:
    def __init__(self) -> None:
        pyxel.init(
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            title="Dungeon Antiqua ZERO Status Screen Mock",
            fps=FPS,
        )
        pyxel.load(str(APP_ROOT / "assets.pyxres"))
        pyxel.load_pal(str(APP_ROOT / "assets.pyxpal"))
        self.input_reader = PyxelInputReader(
            InputBindings.default().with_cancel(pyxel.KEY_Q)
        )

        resources = ImageResources()
        self.faces = resources.image(FACES_IMAGE_ID)

        self.settings = Settings()
        self.texts = TextCatalog.from_json(APP_ROOT / "data" / "texts.json")
        self.items = load_mock_items()
        self.skills = load_mock_skills()
        self.member = load_mock_member(self.items, self.skills)
        self.fonts = FontResources()
        localizer = Localizer(self.settings.language)
        localized = self._localized_texts(localizer)
        abilities = self.member.adjusted_abilities
        localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )

        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        self.windows = [
            windows.create(
                0,
                0,
                64,
                60,
                (
                    localized_texts.create(localized["member.name"], 14, 2),
                    localized_texts.create(localized["member.race"], 14, 5),
                    localized_texts.create(localized["member.gender"], 14, 8),
                    WindowText(
                        f"ＨＰ　{format_number(self.member.hp)}"
                        f"／{format_number(self.member.max_hp)}",
                        6,
                        14,
                    ),
                    WindowText(
                        f"ＭＰ　{format_number(self.member.mp)}"
                        f"／{format_number(self.member.max_mp)}",
                        6,
                        17,
                    ),
                    localized_texts.create(localized["label.condition"], 6, 20),
                    localized_texts.create(localized["value.condition"], 22, 20),
                    localized_texts.create(localized["label.strength"], 6, 26),
                    WindowText(format_number(abilities.strength), 20, 26),
                    localized_texts.create(localized["label.agility"], 6, 29),
                    WindowText(format_number(abilities.agility), 20, 29),
                    localized_texts.create(localized["label.magic"], 6, 32),
                    WindowText(format_number(abilities.magic), 20, 32),
                    localized_texts.create(localized["label.skill"], 6, 38),
                    localized_texts.create(localized["skill.0"], 8, 41),
                    localized_texts.create(localized["skill.1"], 8, 44),
                    localized_texts.create(localized["equipment.right"], 30, 8),
                    localized_texts.create(localized["equipment.left"], 30, 11),
                    localized_texts.create(localized["equipment.body"], 30, 14),
                    localized_texts.create(localized["equipment.head"], 30, 17),
                    localized_texts.create(localized["equipment.arm"], 30, 20),
                    localized_texts.create(localized["label.attack"], 30, 26),
                    WindowText("９６", 46, 26),
                    localized_texts.create(localized["label.hit"], 30, 29),
                    WindowText("１１６（＋１６）", 44, 29),
                    localized_texts.create(localized["label.defense"], 30, 32),
                    WindowText("２０", 46, 32),
                    localized_texts.create(localized["label.evasion"], 30, 35),
                    WindowText("１５", 46, 35),
                    localized_texts.create(localized["label.spell_resistance"], 30, 38),
                    WindowText("４０", 46, 38),
                    localized_texts.create(localized["label.tolerance"], 30, 41),
                    WindowText("%FIRE%", 32, 44),
                    WindowText("%FREEZE%", 34, 44),
                    WindowText("%DARK%", 36, 44),
                    WindowText("%SLEEP%", 38, 44),
                    WindowText("%POISON%", 40, 44),
                    WindowText("%PARALIZE%", 42, 44),
                    WindowText("%CONFUSE%", 44, 44),
                    WindowText("%SILENCE%", 46, 44),
                    WindowText("%DEATH%", 48, 44),
                    WindowText("%SWORD%：９－９９", 6, 49),
                    WindowText("%KATANA%：９－９９", 20, 49),
                    WindowText("%SPEAR%：９－９９", 34, 49),
                    WindowText("%KNIFE%：９－９９", 48, 49),
                    WindowText("%AXE%：９－９９", 6, 52),
                    WindowText("%HAMMER%：９－９９", 20, 52),
                    WindowText("%THROWING%：９－９９", 34, 52),
                    WindowText("%ROD%：９－９９", 48, 52),
                    WindowText("%WAND%：９－９９", 6, 55),
                    WindowText("%MYSTIC%：９－９９", 20, 55),
                    WindowText("%SACRED%：９－９９", 34, 55),
                    WindowText("%NETHER%：９－９９", 48, 55),
                ),
            ),
        ]
        pyxel.run(self.update, self.draw)

    def _localized_texts(self, localizer: Localizer) -> dict[str, str]:
        """Resolve all names and labels currently switched by this mock."""

        identity = self.member.display_identity(localizer, self.texts)
        localized = {
            "member.name": identity.name,
            "member.race": identity.race,
            "member.gender": identity.gender,
        }
        for index in range(2):
            localized[f"skill.{index}"] = (
                self.member.skills[index].localized_name(localizer)
                if index < len(self.member.skills)
                else ""
            )

        for display_key, text_key in STATUS_TEXT_KEYS.items():
            text = self.texts.text(text_key, localizer)
            if not text:
                raise StatusMockDataError(
                    f"モック用テキストが見つかりません: {text_key}"
                )
            localized[display_key] = text
        localized["value.condition"] = self.member.status(
            localizer,
            self.texts,
            show_ok=True,
        )
        for slot in EquipmentSlot:
            slot_name = slot.value.lower()
            item = self.member.equipment.item_at(slot)
            icon = ""
            if item is not None:
                candidate = f"%{item.subtype}%"
                if candidate in TEXT_ICONS:
                    icon = candidate
            localized[f"equipment.{slot_name}"] = (
                localized[f"label.equip.{slot_name}"]
                + icon
                + (item.localized_name(localizer) if item is not None else "")
            )
        return localized

    def _rebuild_localized_window(self) -> None:
        """Rebuild the window with names in the selected language."""

        current_window = self.windows[0]
        localizer = Localizer(self.settings.language)
        localized = self._localized_texts(localizer)
        localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )
        texts = tuple(
            (
                localized_texts.create(
                    localized[LOCALIZED_POSITIONS[(text.x, text.y)]],
                    text.x,
                    text.y,
                    color=text.color,
                    shadow_color=text.shadow_color,
                )
                if (text.x, text.y) in LOCALIZED_POSITIONS
                else text
            )
            for text in current_window.texts
        )
        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        self.windows = [windows.create(0, 0, 64, 60, texts)]

    def update(self) -> None:
        input_state = self.input_reader.poll()
        if input_state.cancel.triggered:
            pyxel.quit()
            return

        if input_state.confirm.triggered:
            language = next_language(self.settings.language)
            self.settings = self.settings.with_language(language)
            self._rebuild_localized_window()

    def draw(self) -> None:
        # ウィンドウ
        for window in self.windows:
            window.draw()
        # 顔
        pyxel.blt(
            16,
            8,
            self.faces,
            0,
            0,
            32,
            32,
            TRANSPARENT_INDEX,
        )


def main() -> int:
    try:
        StatusScreenMock()
        return 0
    except (
        FontResourceError,
        ImageResourceError,
        ItemDataError,
        MemberDataError,
        SkillDataError,
        StatusMockDataError,
        TextCatalogError,
    ) as error:
        print(error)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
