"""Run the production battle scene with standalone fixture data."""

from __future__ import annotations

import pyxel

from tools._bootstrap import APP_ROOT
from tools.screen_mocks._fixtures import (
    load_mock_character_records,
    load_mock_items,
    load_mock_party,
    load_mock_skills,
    load_mock_spells,
)
from tools.screen_mocks._runner import run_screen_mock
from tools.screen_mocks._runtime import (
    create_mock_input_reader,
    initialize_screen_mock,
)

from scenes.battle import *  # noqa: F403 - preserve the standalone mock API
from scenes.battle import (
    BattleCharacter,
    BattleDataError,
    BattleEncounter,
    BattleMonster,
    BattlePhase,
    BattleResult,
    BattleScene,
)
from attack_pose import load_attack_poses
from member import FormationRow
from monster import MonsterDataError
from rendering import SpellEffectRenderer
from resources import (
    AudioResourceError,
    BgmPlayer,
    FontResourceError,
    FontResources,
    ImageResourceError,
    ImageResources,
    load_record_array,
)
from spell_effect import (
    SpellEffectDataError,
    load_spell_effects,
)
from state import Language, Settings
from systems import InventorySystem
from text_catalog import TextCatalog, TextCatalogError
from ui import WindowFactory

BATTLE_MOCK_PARTY_CHARACTER_KEYS = ("Fiora", "Cerion", "Alvan")
BATTLE_MOCK_MONSTER_KEYS = (
    "Giant Spider",
    "Giant Spider",
    "Giant Spider",
    "Coyote",
    "Coyote",
)
BATTLE_MOCK_FRONT_MONSTER_INDEXES = frozenset((2, 3, 4))
BATTLE_MOCK_FRONT_CHARACTER_KEYS = frozenset(("Cerion",))

# Compatibility names used by existing focused tests and external mock callers.
BattleMockDataError = BattleDataError
BattleMockPhase = BattlePhase
BattleMockCharacter = BattleCharacter
BattleMockMonster = BattleMonster


class BattleScreenMock(BattleScene):
    """Small composition root for exercising a configured battle in isolation."""

    def __init__(self) -> None:
        palette_shifter = initialize_screen_mock(
            "Dungeon Antiqua ZERO Battle Screen Mock"
        )
        self.input_reader = create_mock_input_reader()
        bgm = BgmPlayer()
        resources = ImageResources()
        settings = Settings()
        fonts = FontResources()
        windows = WindowFactory(fonts.font_for(settings.language))
        items = load_mock_items()
        party = load_mock_party(
            items,
            load_mock_skills(),
            character_keys=BATTLE_MOCK_PARTY_CHARACTER_KEYS,
        )
        for member in party:
            if member.definition.key in BATTLE_MOCK_FRONT_CHARACTER_KEYS:
                member.formation_row = FormationRow.FRONT

        super().__init__(
            settings=settings,
            palette_shifter=palette_shifter,
            bgm=bgm,
            resources=resources,
            windows=windows,
            font_6x8=fonts.font_for(Language.ENGLISH),
            texts=TextCatalog.from_json(APP_ROOT / "data" / "texts.json"),
            item_catalog=items,
            spells=load_mock_spells(),
            inventory_system=InventorySystem.with_one_each(items),
            character_records=load_mock_character_records(),
            party=party,
            monster_records=tuple(
                load_record_array("monsters.json", APP_ROOT / "data")
            ),
            encounter=BattleEncounter(
                BATTLE_MOCK_MONSTER_KEYS,
                BATTLE_MOCK_FRONT_MONSTER_INDEXES,
            ),
            attack_poses=load_attack_poses(
                APP_ROOT / "effects" / "attack_poses.json"
            ),
            spell_effect_renderer=SpellEffectRenderer(
                resources,
                palette_shifter,
            ),
            spell_effects=load_spell_effects(
                APP_ROOT / "effects" / "spells.json"
            ),
            restart_enabled=True,
            reset_party_on_restart=True,
            reset_inventory_on_restart=True,
        )
        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        """Poll standalone input and delegate one frame to the production scene."""

        super().update(self.input_reader.poll())

    def _restart_battle(self) -> None:
        self._restart_battle_mock()

    def _restart_battle_mock(self) -> None:
        super()._restart_battle()

    def _update_escape_animation(self) -> None:
        super()._update_escape_animation()
        if getattr(self, "result", None) is BattleResult.ESCAPED:
            pyxel.quit()


def main() -> int:
    return run_screen_mock(
        BattleScreenMock,
        expected_errors=(
            AudioResourceError,
            BattleDataError,
            FontResourceError,
            ImageResourceError,
            MonsterDataError,
            SpellEffectDataError,
            TextCatalogError,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
