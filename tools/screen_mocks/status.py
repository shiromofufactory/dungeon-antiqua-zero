"""Display the current status-screen layout mock."""

from __future__ import annotations

import json

import pyxel

from tools._bootstrap import APP_ROOT
from input import Direction, InputBindings, PyxelInputReader
from item import Item, ItemDataError
from localization import Localizer
from member import (
    BattleStats,
    EquipmentSlot,
    Member,
    MemberDataError,
    ProficiencyAptitude,
    ProficiencyKind,
)
from resistance import ResistanceType
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
from ui import (
    TEXT_ICONS,
    LocalizedWindowTextFactory,
    Window,
    WindowFactory,
    WindowText,
    pad,
)

SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
FPS = 60
FACES_IMAGE_ID = "faces/faces_pc"
MOCK_PARTY_CHARACTER_KEYS = (
    "Fiora",
    "Cerion",
    "Alvan",
    "Elika",
    "Ragna",
)
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
PROFICIENCY_POSITIONS = (
    (ProficiencyKind.SWORD, "%SWORD%", 6, 49),
    (ProficiencyKind.KATANA, "%KATANA%", 20, 49),
    (ProficiencyKind.SPEAR, "%SPEAR%", 34, 49),
    (ProficiencyKind.KNIFE, "%KNIFE%", 48, 49),
    (ProficiencyKind.AXE, "%AXE%", 6, 52),
    (ProficiencyKind.HAMMER, "%HAMMER%", 20, 52),
    (ProficiencyKind.THROWING, "%THROWING%", 34, 52),
    (ProficiencyKind.ROD, "%ROD%", 48, 52),
    (ProficiencyKind.WAND, "%WAND%", 6, 55),
    (ProficiencyKind.MYSTIC, "%MYSTIC%", 20, 55),
    (ProficiencyKind.SACRED, "%SACRED%", 34, 55),
    (ProficiencyKind.NETHER, "%NETHER%", 48, 55),
)
RESISTANCE_POSITIONS = tuple(
    (resistance, 32 + index * 2, 44)
    for index, resistance in enumerate(
        (
            ResistanceType.FIRE,
            ResistanceType.FREEZE,
            ResistanceType.DARK,
            ResistanceType.SLEEP,
            ResistanceType.POISON,
            ResistanceType.PARALIZE,
            ResistanceType.CONFUSE,
            ResistanceType.SILENCE,
            ResistanceType.DEATH,
        )
    )
)


def next_language(language: Language) -> Language:
    """Return the next language used by the status mock."""

    if not isinstance(language, Language):
        raise TypeError("language must be a Language")
    index = LANGUAGE_SEQUENCE.index(language)
    return LANGUAGE_SEQUENCE[(index + 1) % len(LANGUAGE_SEQUENCE)]


def proficiency_display(member: Member, kind: ProficiencyKind) -> str:
    """Format one member proficiency with fullwidth fixed-width numbers."""

    proficiency = member.proficiency(kind)
    level = pad(proficiency.level, 1, fill="0")
    progress = pad(proficiency.progress, 2, fill="0")
    return f"{level}－{progress}"


def attack_display(stats: BattleStats) -> str:
    """Format one- or two-weapon attack values for the status screen."""

    right = pad(stats.attack_right, 2)
    if stats.attack_left is None:
        return right
    return f"{right}　－　{pad(stats.attack_left, 2)}"


def hit_display(stats: BattleStats) -> str:
    """Format hit and its equipped-weapon level bonus."""

    bonus = stats.hit_bonus
    sign = "＋" if bonus >= 0 else "－"
    return f"{pad(stats.hit, 3)}" f"（{sign}{pad(abs(bonus), 2)}）"


def resistance_icon_tag(
    member: Member,
    resistance: ResistanceType,
) -> str:
    """Return the enabled or disabled icon tag for one resistance."""

    if resistance in member.resistances:
        return f"%{resistance.value}%"
    return f"%{resistance.value}_DISABLED%"


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


def load_mock_party(
    items: dict[str, Item],
    skills: dict[str, Skill],
) -> tuple[Member, ...]:
    """Load the ordered party used by this mock from generated game data."""

    records = load_data_records("characters.json")
    records_by_key = {
        key: record
        for record in records
        if isinstance(key := record.get("name_en"), str)
    }
    party: list[Member] = []
    for key in MOCK_PARTY_CHARACTER_KEYS:
        record = records_by_key.get(key)
        if record is None:
            raise MemberDataError(f"モック用キャラクターが見つかりません: {key}")
        party.append(Member.from_record(record, items=items, skills=skills))
    return tuple(party)


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
        self.party = load_mock_party(self.items, self.skills)
        self.member_index = 0
        self.fonts = FontResources()
        self.windows = [self._build_window()]
        pyxel.run(self.update, self.draw)

    @property
    def member(self) -> Member:
        """Return the party member currently shown by the status mock."""

        return self.party[self.member_index]

    def _build_window(self) -> Window:
        """Build the complete status window for the current member."""

        localizer = Localizer(self.settings.language)
        localized = self._localized_texts(localizer)
        abilities = self.member.adjusted_abilities
        battle_stats = self.member.battle_stats
        localized_texts = LocalizedWindowTextFactory.from_language(
            self.fonts,
            self.settings.language,
        )

        windows = WindowFactory(self.fonts.font_for(Language.JAPANESE))
        return windows.create(
            0,
            0,
            64,
            60,
            (
                localized_texts.create(localized["member.name"], 14, 2),
                localized_texts.create(localized["member.race"], 14, 5),
                localized_texts.create(localized["member.gender"], 14, 8),
                WindowText(
                    f"ＨＰ　{pad(self.member.hp, 3)}" f"／{pad(self.member.max_hp, 3)}",
                    6,
                    14,
                ),
                WindowText(
                    f"ＭＰ　{pad(self.member.mp, 3)}" f"／{pad(self.member.max_mp, 3)}",
                    6,
                    17,
                ),
                localized_texts.create(localized["label.condition"], 6, 20),
                localized_texts.create(localized["value.condition"], 22, 20),
                localized_texts.create(localized["label.strength"], 6, 26),
                WindowText(pad(abilities.strength, 2), 20, 26),
                localized_texts.create(localized["label.agility"], 6, 29),
                WindowText(pad(abilities.agility, 2), 20, 29),
                localized_texts.create(localized["label.magic"], 6, 32),
                WindowText(pad(abilities.magic, 2), 20, 32),
                localized_texts.create(localized["label.skill"], 6, 38),
                localized_texts.create(localized["skill.0"], 8, 41),
                localized_texts.create(localized["skill.1"], 8, 44),
                localized_texts.create(localized["equipment.right"], 30, 8),
                localized_texts.create(localized["equipment.left"], 30, 11),
                localized_texts.create(localized["equipment.body"], 30, 14),
                localized_texts.create(localized["equipment.head"], 30, 17),
                localized_texts.create(localized["equipment.arm"], 30, 20),
                localized_texts.create(localized["label.attack"], 30, 26),
                WindowText(attack_display(battle_stats), 46, 26),
                localized_texts.create(localized["label.hit"], 30, 29),
                WindowText(hit_display(battle_stats), 44, 29),
                localized_texts.create(localized["label.defense"], 30, 32),
                WindowText(pad(battle_stats.defense, 2), 46, 32),
                localized_texts.create(localized["label.evasion"], 30, 35),
                WindowText(pad(battle_stats.evasion, 2), 46, 35),
                localized_texts.create(localized["label.spell_resistance"], 30, 38),
                WindowText(
                    pad(battle_stats.spell_resistance, 2),
                    46,
                    38,
                ),
                localized_texts.create(localized["label.tolerance"], 30, 41),
                *(
                    WindowText(
                        resistance_icon_tag(self.member, resistance),
                        x,
                        y,
                    )
                    for resistance, x, y in RESISTANCE_POSITIONS
                ),
                *(
                    WindowText(
                        f"{icon}：{proficiency_display(self.member, kind)}",
                        x,
                        y,
                    )
                    for kind, icon, x, y in PROFICIENCY_POSITIONS
                ),
                *(
                    WindowText("%FAVORED%", x - 2, y)
                    for kind, _icon, x, y in PROFICIENCY_POSITIONS
                    if self.member.proficiency(kind).aptitude
                    is ProficiencyAptitude.FAVORED
                ),
            ),
            horizontal_navigation=len(self.party) > 1,
        )

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

    def _rebuild_window(self) -> None:
        """Rebuild all values for the current member and language."""

        self.windows = [self._build_window()]

    def _switch_member(self, distance: int) -> None:
        """Move through the mock party, wrapping at both ends."""

        if distance not in (-1, 1):
            raise ValueError("member switch distance must be -1 or 1")
        self.member_index = (self.member_index + distance) % len(self.party)
        self._rebuild_window()

    def update(self) -> None:
        input_state = self.input_reader.poll()
        if input_state.cancel.triggered:
            pyxel.quit()
            return

        if (
            input_state.navigation is Direction.LEFT
            or input_state.previous_page.triggered
        ):
            self._switch_member(-1)
        elif (
            input_state.navigation is Direction.RIGHT or input_state.next_page.triggered
        ):
            self._switch_member(1)
        elif input_state.confirm.triggered:
            language = next_language(self.settings.language)
            self.settings = self.settings.with_language(language)
            self._rebuild_window()

    def draw(self) -> None:
        # ウィンドウ
        for window in self.windows:
            window.draw()
        # 顔
        face_position = self.member.face_position
        pyxel.blt(
            16,
            10,
            self.faces,
            face_position.x,
            face_position.y,
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
