from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from tools._bootstrap import APP_ROOT  # noqa: F401 - adds app/ to sys.path

from battle_magic import SpellAffinity
from battle_commands import BattleCommand
from item import AttackAttribute
from member import EquipmentSlot
from resistance import ResistanceType
from scenes.battle import (
    AFFINITY_ICON_HEIGHT,
    AFFINITY_ICON_SOURCE_X,
    AFFINITY_ICON_WIDTH,
    MONSTER_POSITIONS,
    RESIST_ICON_SOURCE_Y,
    TARGET_AFFINITY_BLINK_FRAME_COUNT,
    TARGET_AFFINITY_VISIBLE_FRAME_COUNT,
    TRANSPARENT_INDEX,
    WEAK_ICON_SOURCE_Y,
    BattlePhase,
    BattleScene,
)
from state import SaveData
from systems import MONSTER_PROFILE_FIELD_KEY, MonsterRecordSystem


def _monster(
    key: str,
    *,
    weaknesses: frozenset[ResistanceType] = frozenset(),
    resistances: frozenset[ResistanceType] = frozenset(),
) -> SimpleNamespace:
    return SimpleNamespace(
        key=key,
        width=64,
        weaknesses=weaknesses,
        resistances=resistances,
    )


def _spell(attribute: ResistanceType | None) -> SimpleNamespace:
    return SimpleNamespace(attribute=attribute)


class BattleMonsterRecordTest(unittest.TestCase):
    def _target_scene(self) -> BattleScene:
        scene = BattleScene.__new__(BattleScene)
        scene.phase = BattlePhase.ACTION_TARGET
        scene.action_targets_enemy = True
        scene.action_targets_all = False
        scene.selectable_target_indexes = (0, 1)
        scene.selected_target_index = 0
        scene.pending_item_candidate = None
        scene.pending_spell = _spell(ResistanceType.FIRE)
        scene.monsters = (
            _monster(
                "Fire Weak",
                weaknesses=frozenset((ResistanceType.FIRE,)),
            ),
            _monster(
                "Fire Resist",
                resistances=frozenset((ResistanceType.FIRE,)),
            ),
        )
        scene.monster_record_system = MonsterRecordSystem(SaveData())
        return scene

    def test_confirmed_enemy_spell_records_only_its_actual_single_target(self) -> None:
        scene = self._target_scene()

        scene._record_action_target_information(scene.pending_spell)

        self.assertEqual(
            scene.monster_record_system.save_data.monster_records,
            {
                "Fire Weak": {
                    MONSTER_PROFILE_FIELD_KEY,
                    ResistanceType.FIRE.value,
                }
            },
        )

    def test_all_target_spell_records_every_target(self) -> None:
        scene = self._target_scene()
        scene.action_targets_all = True
        scene.selected_target_index = None

        scene._record_action_target_information(scene.pending_spell)

        self.assertEqual(
            set(scene.monster_record_system.save_data.monster_records),
            {"Fire Weak", "Fire Resist"},
        )

    def test_target_affinity_stays_hidden_until_that_attribute_is_known(self) -> None:
        scene = self._target_scene()

        self.assertIs(scene._target_affinity(0), SpellAffinity.NORMAL)
        scene.monster_record_system.reveal_affinity(
            "Fire Weak",
            ResistanceType.FIRE,
        )

        self.assertIs(scene._target_affinity(0), SpellAffinity.WEAK)

    def test_single_target_selection_exposes_every_known_enemy_affinity(self) -> None:
        scene = self._target_scene()
        scene.monster_record_system.reveal_affinity(
            "Fire Weak",
            ResistanceType.FIRE,
        )
        scene.monster_record_system.reveal_affinity(
            "Fire Resist",
            ResistanceType.FIRE,
        )

        self.assertEqual(
            tuple(scene._target_affinity(index) for index in (0, 1)),
            (SpellAffinity.WEAK, SpellAffinity.RESIST),
        )

    def test_known_resistance_is_shown_for_an_item_spell_too(self) -> None:
        scene = self._target_scene()
        scene.pending_spell = None
        scene.pending_item_candidate = SimpleNamespace(
            item=SimpleNamespace(use_spell_key="FIRE1")
        )
        scene.spells = {"FIRE1": _spell(ResistanceType.FIRE)}
        scene.selected_target_index = 1
        scene.monster_record_system.reveal_affinity(
            "Fire Resist",
            ResistanceType.FIRE,
        )

        self.assertIs(scene._target_affinity(1), SpellAffinity.RESIST)

    def test_physical_target_weakness_uses_known_right_weapon_attribute(
        self,
    ) -> None:
        scene = self._target_scene()
        weapon = SimpleNamespace(attack_attribute=AttackAttribute.FIRE)
        equipment = SimpleNamespace(weapon_at=Mock(return_value=weapon))
        scene.phase = BattlePhase.TARGET
        scene.selected_command = BattleCommand.ATTACK
        scene.active_party_index = 0
        scene.party = (SimpleNamespace(equipment=equipment),)

        self.assertIs(scene._target_affinity(0), SpellAffinity.NORMAL)

        scene.monster_record_system.reveal_affinity(
            "Fire Weak",
            ResistanceType.FIRE,
        )

        self.assertIs(scene._target_affinity(0), SpellAffinity.WEAK)

    def test_physical_target_affinity_keeps_known_resistance_priority(
        self,
    ) -> None:
        scene = self._target_scene()
        weapon = SimpleNamespace(attack_attribute=AttackAttribute.FIRE)
        scene.phase = BattlePhase.TARGET
        scene.selected_command = BattleCommand.AIM
        scene.active_party_index = 0
        scene.party = (
            SimpleNamespace(
                equipment=SimpleNamespace(weapon_at=Mock(return_value=weapon))
            ),
        )
        scene.monsters = (
            _monster(
                "Fire Both",
                weaknesses=frozenset((ResistanceType.FIRE,)),
                resistances=frozenset((ResistanceType.FIRE,)),
            ),
            scene.monsters[1],
        )
        scene.monster_record_system.reveal_affinity(
            "Fire Both",
            ResistanceType.FIRE,
        )

        self.assertIs(scene._target_affinity(0), SpellAffinity.RESIST)

    def test_dual_wield_alternates_known_right_and_left_affinities(self) -> None:
        scene = self._target_scene()
        weapons = {
            EquipmentSlot.RIGHT: SimpleNamespace(
                attack_attribute=AttackAttribute.FIRE
            ),
            EquipmentSlot.LEFT: SimpleNamespace(
                attack_attribute=AttackAttribute.FREEZE
            ),
        }
        scene.phase = BattlePhase.TARGET
        scene.selected_command = BattleCommand.ATTACK
        scene.active_party_index = 0
        scene.party = (
            SimpleNamespace(
                equipment=SimpleNamespace(weapon_at=weapons.get),
                has_skill=lambda key: key == "Dual-Wield",
            ),
        )
        scene.monsters = (
            _monster(
                "Mixed Affinity",
                weaknesses=frozenset((ResistanceType.FIRE,)),
                resistances=frozenset((ResistanceType.FREEZE,)),
            ),
            scene.monsters[1],
        )
        for attribute in (ResistanceType.FIRE, ResistanceType.FREEZE):
            scene.monster_record_system.reveal_affinity(
                "Mixed Affinity",
                attribute,
            )
        scene._monster_draw_x = Mock(return_value=4)

        self.assertEqual(
            scene._target_affinities(0),
            (SpellAffinity.WEAK, SpellAffinity.RESIST),
        )
        source_y_by_frame = {}
        for frame in (0, TARGET_AFFINITY_VISIBLE_FRAME_COUNT // 2):
            with (
                patch("scenes.battle.pyxel.frame_count", frame),
                patch("scenes.battle.pyxel.blt") as blt,
            ):
                scene._draw_target_affinity_indicators()
            source_y_by_frame[frame] = blt.call_args.args[4]

        self.assertEqual(
            source_y_by_frame,
            {
                0: WEAK_ICON_SOURCE_Y,
                TARGET_AFFINITY_VISIBLE_FRAME_COUNT // 2: RESIST_ICON_SOURCE_Y,
            },
        )

    def test_draws_known_physical_weakness_during_target_selection(self) -> None:
        scene = self._target_scene()
        weapon = SimpleNamespace(attack_attribute=AttackAttribute.FIRE)
        scene.phase = BattlePhase.TARGET
        scene.selected_command = BattleCommand.ATTACK
        scene.active_party_index = 0
        scene.party = (
            SimpleNamespace(
                equipment=SimpleNamespace(weapon_at=Mock(return_value=weapon))
            ),
        )
        scene.monster_record_system.reveal_affinity(
            "Fire Weak",
            ResistanceType.FIRE,
        )
        scene._monster_draw_x = Mock(return_value=4)

        with (
            patch("scenes.battle.pyxel.frame_count", 0),
            patch("scenes.battle.pyxel.blt") as blt,
        ):
            scene._draw_target_affinity_indicators()

        blt.assert_called_once_with(
            24,
            MONSTER_POSITIONS[0][1] + 20,
            0,
            AFFINITY_ICON_SOURCE_X,
            WEAK_ICON_SOURCE_Y,
            AFFINITY_ICON_WIDTH,
            AFFINITY_ICON_HEIGHT,
            TRANSPARENT_INDEX,
        )

    def test_draws_known_affinities_for_each_all_target_marker(self) -> None:
        scene = self._target_scene()
        scene.action_targets_all = True
        scene.selected_target_index = None
        scene.monster_record_system.reveal_affinity(
            "Fire Weak",
            ResistanceType.FIRE,
        )

    def test_single_target_cursor_draws_known_affinities_for_all_enemies(self) -> None:
        scene = self._target_scene()
        scene.monster_record_system.reveal_affinity(
            "Fire Weak",
            ResistanceType.FIRE,
        )
        scene.monster_record_system.reveal_affinity(
            "Fire Resist",
            ResistanceType.FIRE,
        )
        scene._monster_draw_x = Mock(side_effect=(4, 68))

        with (
            patch("scenes.battle.pyxel.frame_count", 0),
            patch("scenes.battle.pyxel.blt") as blt,
        ):
            scene._draw_target_affinity_indicators()

        self.assertEqual(len(blt.call_args_list), 2)
        self.assertEqual(
            [draw.args[4] for draw in blt.call_args_list],
            [WEAK_ICON_SOURCE_Y, RESIST_ICON_SOURCE_Y],
        )
        scene.monster_record_system.reveal_affinity(
            "Fire Resist",
            ResistanceType.FIRE,
        )
        scene._monster_draw_x = Mock(side_effect=(4, 68))

        with (
            patch("scenes.battle.pyxel.frame_count", 0),
            patch("scenes.battle.pyxel.blt") as blt,
        ):
            scene._draw_target_affinity_indicators()

        self.assertEqual(
            blt.call_args_list,
            [
                call(
                    24,
                    MONSTER_POSITIONS[0][1] + 20,
                    0,
                    AFFINITY_ICON_SOURCE_X,
                    WEAK_ICON_SOURCE_Y,
                    AFFINITY_ICON_WIDTH,
                    AFFINITY_ICON_HEIGHT,
                    TRANSPARENT_INDEX,
                ),
                call(
                    88,
                    MONSTER_POSITIONS[1][1] + 20,
                    0,
                    AFFINITY_ICON_SOURCE_X,
                    RESIST_ICON_SOURCE_Y,
                    AFFINITY_ICON_WIDTH,
                    AFFINITY_ICON_HEIGHT,
                    TRANSPARENT_INDEX,
                ),
            ],
        )

    def test_auto_battle_hides_target_affinities_but_keeps_hit_popups(self) -> None:
        scene = self._target_scene()
        scene.monster_record_system.reveal_affinity(
            "Fire Weak", ResistanceType.FIRE
        )
        scene.monster_record_system.reveal_affinity(
            "Fire Resist", ResistanceType.FIRE
        )
        scene._monster_draw_x = Mock(side_effect=(4, 68))

        with (
            patch("scenes.battle.pyxel.frame_count", 0),
            patch("scenes.battle.pyxel.blt") as blt,
        ):
            scene.auto_battle_active = True
            scene._draw_target_affinity_indicators()
            blt.assert_not_called()
            scene.affinity_popups = (
                SimpleNamespace(x=10, y=20, affinity=SpellAffinity.WEAK),
            )
            scene._draw_affinity_popups()
            blt.assert_called_once()
            blt.reset_mock()

            scene.auto_battle_active = False
            scene._draw_target_affinity_indicators()

        self.assertEqual(
            [draw.args[4] for draw in blt.call_args_list],
            [WEAK_ICON_SOURCE_Y, RESIST_ICON_SOURCE_Y],
        )

    def test_target_affinity_uses_da2_blink_timing(self) -> None:
        scene = self._target_scene()
        scene.monster_record_system.reveal_affinity(
            "Fire Weak",
            ResistanceType.FIRE,
        )
        scene._monster_draw_x = Mock(return_value=4)

        with (
            patch(
                "scenes.battle.pyxel.frame_count",
                TARGET_AFFINITY_VISIBLE_FRAME_COUNT,
            ),
            patch("scenes.battle.pyxel.blt") as blt,
        ):
            scene._draw_target_affinity_indicators()

        self.assertEqual(TARGET_AFFINITY_BLINK_FRAME_COUNT, 30)
        self.assertEqual(TARGET_AFFINITY_VISIBLE_FRAME_COUNT, 24)
        blt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
