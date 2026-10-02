"""Run the production battle scene with standalone fixture data."""

from __future__ import annotations

from dataclasses import dataclass

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
from game import MenuAlertEffect
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
from state import Language, SaveData, Settings
from systems import InventorySystem
from text_catalog import TextCatalog, TextCatalogError
from ui import WindowFactory


@dataclass(frozen=True)
class BattleTestMember:
    """Editable initial state for one member in the standalone battle test."""

    character_key: str
    internal_level: int | None = None
    formation_row: FormationRow = FormationRow.FRONT
    hp: int | None = None
    mp: int | None = None


# Edit these fixtures to choose the standalone battle's initial state.
BATTLE_TEST_PARTY = (
    BattleTestMember("Fiora"),
    BattleTestMember("Cerion"),
    # BattleTestMember("Alvan"),
)
BATTLE_TEST_MONSTER_KEYS = (
    "Giant Spider",
    "Giant Spider",
    "Giant Spider",
    "Coyote",
    "Coyote",
)

# Compatibility names retained for the existing focused regression tests.
BATTLE_MOCK_PARTY_CHARACTER_KEYS = tuple(
    member.character_key for member in BATTLE_TEST_PARTY
)
BATTLE_MOCK_MONSTER_KEYS = BATTLE_TEST_MONSTER_KEYS
BATTLE_MOCK_FRONT_CHARACTER_KEYS = frozenset(
    member.character_key
    for member in BATTLE_TEST_PARTY
    if member.formation_row is FormationRow.FRONT
)

# Compatibility type names used by the existing focused regression tests.
BattleMockDataError = BattleDataError
BattleMockPhase = BattlePhase
BattleMockCharacter = BattleCharacter
BattleMockMonster = BattleMonster


class BattleTestApp(BattleScene):
    """Small composition root for exercising a configured battle in isolation."""

    def __init__(self) -> None:
        palette_shifter = initialize_screen_mock("Dungeon Antiqua ZERO Battle Test")
        self.alert = MenuAlertEffect()
        self.input_reader = create_mock_input_reader()
        bgm = BgmPlayer()
        resources = ImageResources()
        settings = Settings()
        fonts = FontResources()
        windows = WindowFactory(fonts.font_for(settings.language))
        items = load_mock_items()
        skills = load_mock_skills()
        party = tuple(
            load_mock_party(
                items,
                skills,
                character_keys=(state.character_key,),
                internal_level=state.internal_level,
            )[0]
            for state in BATTLE_TEST_PARTY
        )

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
            encounter=BattleEncounter(BATTLE_TEST_MONSTER_KEYS),
            attack_poses=load_attack_poses(APP_ROOT / "effects" / "attack_poses.json"),
            spell_effect_renderer=SpellEffectRenderer(
                resources,
                palette_shifter,
            ),
            spell_effects=load_spell_effects(APP_ROOT / "effects" / "spells.json"),
            restart_enabled=True,
            reset_party_on_restart=True,
            reset_inventory_on_restart=True,
            save_data=SaveData(),
            result_party=party,
            return_bgm_id="da3-field",
            fonts=fonts,
            on_invalid_action=self.alert.start,
        )
        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        """Poll standalone input and delegate one frame to the production scene."""

        bgm = getattr(self, "bgm", None)
        if bgm is not None:
            bgm.update()
        alert = getattr(self, "alert", None)
        if alert is not None:
            alert.update()
        super().update(self.input_reader.poll())
        if getattr(self, "result", None) in (
            BattleResult.VICTORY,
            BattleResult.ESCAPED,
        ):
            pyxel.quit()

    def draw(self) -> None:
        alert = getattr(self, "alert", None)
        if alert is None:
            super().draw()
            return
        pyxel.camera(alert.camera_x, 0)
        try:
            super().draw()
        finally:
            pyxel.camera()

    def _restart_battle(self) -> None:
        self._restart_battle_mock()

    def _restart_battle_mock(self) -> None:
        super()._restart_battle()

    def _prepare_party_for_restart(self) -> None:
        """Apply the configured state before the production timeline is built."""

        self._apply_test_party_state(self.party)

    def _complete_defeat(self) -> None:
        """Restart the standalone fixture after acknowledging a wipeout."""

        self._restart_battle_mock()

    @staticmethod
    def _apply_test_party_state(party) -> None:
        states = {state.character_key: state for state in BATTLE_TEST_PARTY}
        for member in party:
            state = states[member.definition.key]
            member.formation_row = state.formation_row
            hp = member.max_hp if state.hp is None else state.hp
            mp = member.max_mp if state.mp is None else state.mp
            if not 0 <= hp <= member.max_hp:
                raise ValueError(
                    f"battle test HP must be from 0 to {member.max_hp}: "
                    f"{member.definition.key}"
                )
            if not 0 <= mp <= member.max_mp:
                raise ValueError(
                    f"battle test MP must be from 0 to {member.max_mp}: "
                    f"{member.definition.key}"
                )
            member.hp = hp
            member.mp = mp

def main() -> int:
    return run_screen_mock(
        BattleTestApp,
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


BattleScreenMock = BattleTestApp


if __name__ == "__main__":
    raise SystemExit(main())
