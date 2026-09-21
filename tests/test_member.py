from __future__ import annotations

import unittest

from app.item import Item
from app.localization import Localizer
from app.member import (
    AdjustedAbilities,
    BaseAbilities,
    CharacterType,
    EquipmentSet,
    EquipmentSlot,
    FacePosition,
    FormationRow,
    Gender,
    Member,
    MemberDataError,
    Proficiency,
    ProficiencyAptitude,
    ProficiencyKind,
    Race,
)
from app.resistance import ResistanceType
from app.skill import Skill
from app.state import Language
from app.text_catalog import TextCatalog


PROFICIENCY_FIELDS = {kind.value: 0 for kind in ProficiencyKind}
FACE_FIELDS = {"face_x": 0, "face_y": 0}
GROWTH_FIELDS = {
    "type": "SUB",
    "lv_diff": 0,
    "base_hp": 44,
    "base_mp": 27,
}


class MemberTest(unittest.TestCase):
    def setUp(self) -> None:
        self.member = Member.from_record(
            {
                "name_ja": "フィオラ",
                "name_en": "Fiora",
                "race": "FAIRY",
                "gender": "FEMALE",
                "base_str": 17,
                "base_agi": 25,
                "base_mag": 24,
                **GROWTH_FIELDS,
                **FACE_FIELDS,
                **PROFICIENCY_FIELDS,
                "sp_mystic": 1,
            }
        )
        self.texts = TextCatalog.from_records(
            [
                {
                    "text_key": "race.FAIRY",
                    "text_ja": "ようせい",
                    "text_en": "Fairy",
                    "text_zhcn": "妖精",
                },
                {
                    "text_key": "gender.FEMALE",
                    "text_ja": "おんな",
                    "text_en": "Female",
                    "text_zhcn": "女性",
                },
                {
                    "text_key": "status.ok",
                    "text_ja": "ＯＫ",
                    "text_en": "OK",
                    "text_zhcn": "ＯＫ",
                },
                {
                    "text_key": "status.dead",
                    "text_ja": "しぼう",
                    "text_en": "Dead",
                    "text_zhcn": "死亡",
                },
                {
                    "text_key": "term.condition.PARALIZE",
                    "text_ja": "%PARALIZE%まひ",
                    "text_en": "%PARALIZE%Paralyze",
                    "text_zhcn": "麻痹",
                },
                {
                    "text_key": "term.condition.SLEEP",
                    "text_ja": "%SLEEP%ねむり",
                    "text_en": "%SLEEP%Sleep",
                    "text_zhcn": "睡眠",
                },
                {
                    "text_key": "term.condition.CONFUSE",
                    "text_ja": "%CONFUSE%こんらん",
                    "text_en": "%CONFUSE%Confuse",
                    "text_zhcn": "混乱",
                },
                {
                    "text_key": "term.condition.POISON",
                    "text_ja": "%POISON%どく",
                    "text_en": "%POISON%Poison",
                    "text_zhcn": "中毒",
                },
            ]
        )

    @staticmethod
    def item(
        key: str,
        equip_type: str,
        subtype: str = "GENERAL",
        *,
        attack: int = 0,
        hit: int = 0,
        defense: int = 0,
        evasion: int = 0,
        spell_resistance: int = 0,
        strength_modifier: int = 0,
        agility_modifier: int = 0,
        magic_modifier: int = 0,
        healing: int = 0,
        tolerance: str = "",
        requirements: str = "",
        special: str = "",
    ) -> Item:
        return Item.from_record(
            {
                "name_en": key,
                "name_ja": key,
                "type1": equip_type,
                "type2": subtype,
                "atk": attack,
                "hit": hit,
                "dfc": defense,
                "eva": evasion,
                "rst": spell_resistance,
                "str": strength_modifier,
                "agi": agility_modifier,
                "mag": magic_modifier,
                "healing": healing,
                "tolerance": tolerance,
                "requirements": requirements,
                "special": special,
            }
        )

    @staticmethod
    def build_member(
        key: str,
        *,
        race: str = "HUMAN",
        gender: str = "MALE",
        **aptitudes: int,
    ) -> Member:
        return Member.from_record(
            {
                "name_en": key,
                "name_ja": key,
                "race": race,
                "gender": gender,
                "base_str": 20,
                "base_agi": 20,
                "base_mag": 20,
                **GROWTH_FIELDS,
                **FACE_FIELDS,
                **PROFICIENCY_FIELDS,
                **aptitudes,
            }
        )

    @staticmethod
    def skill(key: str) -> Skill:
        return Skill.from_record({"name_en": key, "name_ja": key})

    def test_normalizes_stable_race_and_gender_values(self) -> None:
        self.assertEqual(self.member.definition.character_type, CharacterType.SUB)
        self.assertEqual(self.member.definition.race, Race.FAIRY)
        self.assertEqual(self.member.definition.gender, Gender.FEMALE)

    def test_keeps_face_sheet_position_on_member(self) -> None:
        self.assertEqual(self.member.face_position, FacePosition(0, 0))

    def test_formation_defaults_to_front_and_can_be_changed_to_back(self) -> None:
        self.assertEqual(self.member.formation_row, FormationRow.FRONT)
        self.assertTrue(self.member.is_front_row)

        self.member.formation_row = FormationRow.BACK

        self.assertFalse(self.member.is_front_row)

    def test_alive_dead_and_dying_conditions_match_da2(self) -> None:
        self.assertTrue(self.member.is_alive)
        self.assertFalse(self.member.is_dead)

        self.member.hp = self.member.max_hp // 4 + 1
        self.assertFalse(self.member.is_dying)

        self.member.hp = self.member.max_hp // 4
        self.assertTrue(self.member.is_dying)

        self.member.hp = self.member.max_hp
        self.member.poisoned = True
        self.assertTrue(self.member.is_dying)

        self.member.poisoned = False
        self.member.hp = 0
        self.assertFalse(self.member.is_alive)
        self.assertTrue(self.member.is_dead)
        self.assertFalse(self.member.is_dying)

        # DA2's status predicate still reports poison at zero HP. Rendering
        # resolves the overlap by giving the death pose priority.
        self.member.poisoned = True
        self.assertTrue(self.member.is_dying)

    def test_equipment_eligibility_uses_aptitude_and_armor_class(self) -> None:
        fighter = self.build_member("Fighter", eq_sword=2, eq_shield=1)
        mage = self.build_member("Mage", gender="FEMALE", sp_mystic=1)
        sword = self.item("SWORD", "RIGHT", "SWORD")
        wand = self.item("WAND", "RIGHT", "WAND")
        general = self.item("LEATHER", "BODY", "GENERAL")
        heavy = self.item("PLATE", "BODY", "HEAVY")
        magical = self.item("ROBE", "BODY", "MAGICAL")
        consumable = self.item("HERB", "ITEM", "ITEM")

        self.assertTrue(fighter.can_equip(sword))
        self.assertFalse(mage.can_equip(sword))
        self.assertFalse(fighter.can_equip(wand))
        self.assertTrue(fighter.can_equip(general))
        self.assertTrue(mage.can_equip(general))
        self.assertTrue(fighter.can_equip(heavy))
        self.assertFalse(mage.can_equip(heavy))
        self.assertFalse(fighter.can_equip(magical))
        self.assertTrue(mage.can_equip(magical))
        self.assertFalse(fighter.can_equip(consumable))

    def test_equipment_eligibility_applies_every_current_requirement(self) -> None:
        ragna = self.build_member("Ragna", eq_sword=2)
        fairy = self.build_member(
            "Fairy",
            race="FAIRY",
            gender="FEMALE",
            eq_sword=2,
        )
        dragon = self.build_member("Dragon", race="DRAGONEWT", eq_sword=2)
        robot = self.build_member(
            "Robot",
            race="ROBOT",
            gender="NONE",
            eq_sword=2,
        )
        woman = self.build_member("Woman", gender="FEMALE", eq_sword=2)
        def sword(requirement: str) -> Item:
            return self.item(
                requirement,
                "RIGHT",
                "SWORD",
                requirements=requirement,
            )

        self.assertTrue(ragna.can_equip(sword("ONLY_RAGNA")))
        self.assertFalse(woman.can_equip(sword("ONLY_RAGNA")))
        self.assertTrue(fairy.can_equip(sword("ONLY_FAIRYS")))
        self.assertFalse(ragna.can_equip(sword("ONLY_FAIRYS")))
        self.assertFalse(fairy.can_equip(sword("NO_FAIRYS")))
        self.assertTrue(ragna.can_equip(sword("NO_FAIRYS")))
        self.assertFalse(dragon.can_equip(sword("NO_DRAGONS")))
        self.assertTrue(ragna.can_equip(sword("NO_DRAGONS")))
        self.assertTrue(dragon.can_equip(sword("ONLY_DRAGON")))
        self.assertFalse(ragna.can_equip(sword("ONLY_DRAGON")))
        self.assertTrue(robot.can_equip(sword("ONLY_ROBO")))
        self.assertFalse(ragna.can_equip(sword("ONLY_ROBO")))
        self.assertTrue(woman.can_equip(sword("ONLY_FEMALE")))
        self.assertFalse(ragna.can_equip(sword("ONLY_FEMALE")))
        self.assertTrue(ragna.can_equip(sword("ONLY_MALE")))
        self.assertFalse(woman.can_equip(sword("ONLY_MALE")))

    def test_lv9_requirement_uses_the_selected_weapon_proficiency(self) -> None:
        member = self.build_member("Master", eq_sword=2, eq_knife=2)
        member.proficiencies[ProficiencyKind.SWORD] = Proficiency(
            ProficiencyAptitude.FAVORED,
            level=9,
        )
        sword = self.item(
            "ULTIMATE SWORD",
            "RIGHT",
            "SWORD",
            requirements="LV9",
        )
        knife = self.item(
            "ULTIMATE KNIFE",
            "RIGHT",
            "KNIFE",
            requirements="LV9",
        )

        self.assertTrue(member.can_equip(sword))
        self.assertFalse(member.can_equip(knife))

    def test_rejects_unstable_formation_value(self) -> None:
        with self.assertRaisesRegex(TypeError, "formation_row"):
            Member(self.member.definition, formation_row="BACK")

    def test_equipment_healing_and_poison_are_owned_by_member(self) -> None:
        wand = self.item("WAND", "RIGHT", "WAND", healing=1)
        ring = self.item("RING", "ARM", healing=1)
        self.member.equipment = EquipmentSet(
            {
                EquipmentSlot.RIGHT: wand,
                EquipmentSlot.ARM: ring,
            }
        )
        self.member.hp = 40

        self.assertEqual(self.member.healing, 2)
        self.assertEqual(self.member.heal_and_poison_amount, 2)
        self.assertEqual(self.member.apply_heal_and_poison(), 2)
        self.assertEqual(self.member.hp, 42)

        self.member.poisoned = True
        self.assertEqual(self.member.heal_and_poison_amount, 1)
        self.assertEqual(self.member.apply_heal_and_poison(), 1)
        self.assertEqual(self.member.hp, 43)

    def test_regenerate_adds_one_battle_healing_level_only_in_battle(self) -> None:
        self.member.skills.append(self.skill("Regenerate"))
        self.member.hp = 40

        self.assertEqual(self.member.healing, 0)
        self.assertEqual(self.member.battle_healing, 1)

        ring = self.item("RING", "ARM", healing=1)
        self.member.equipment = EquipmentSet({EquipmentSlot.ARM: ring})

        self.assertEqual(self.member.healing, 1)
        self.assertEqual(self.member.battle_healing, 2)

    def test_poison_tick_cannot_reduce_hp_below_zero(self) -> None:
        self.member.hp = 1
        self.member.poisoned = True

        self.assertEqual(self.member.heal_and_poison_amount, -1)
        self.assertEqual(self.member.apply_heal_and_poison(), -1)
        self.assertEqual(self.member.hp, 0)
        self.assertFalse(self.member.poisoned)
        self.assertEqual(self.member.heal_and_poison_amount, 0)

    def test_battle_healing_caps_hp_and_can_clear_all_ailments(self) -> None:
        self.member.hp = 1
        self.member.poisoned = True
        self.member.paralyzed = True
        self.member.sleeping = 2
        self.member.confused = 3
        self.member.stunned = True

        recovered = self.member.apply_healing(999, cure_ailments=True)

        self.assertEqual(recovered, self.member.max_hp - 1)
        self.assertEqual(self.member.hp, self.member.max_hp)
        self.assertFalse(self.member.poisoned)
        self.assertFalse(self.member.paralyzed)
        self.assertEqual(self.member.sleeping, 0)
        self.assertEqual(self.member.confused, 0)
        self.assertFalse(self.member.stunned)

    def test_cure_clears_da2_ailments_but_not_stun(self) -> None:
        self.member.poisoned = True
        self.member.paralyzed = True
        self.member.sleeping = 2
        self.member.confused = 3
        self.member.stunned = True

        self.assertTrue(self.member.has_curable_ailment)
        self.assertTrue(self.member.cure_ailments())

        self.assertFalse(self.member.poisoned)
        self.assertFalse(self.member.paralyzed)
        self.assertEqual(self.member.sleeping, 0)
        self.assertEqual(self.member.confused, 0)
        self.assertTrue(self.member.stunned)
        self.assertFalse(self.member.has_curable_ailment)
        self.assertFalse(self.member.cure_ailments())

    def test_sleep_skips_actions_and_positive_damage_wakes_the_member(self) -> None:
        self.member.confused = 3
        self.member.apply_sleep(2)

        self.assertEqual(self.member.sleeping, 2)
        self.assertEqual(self.member.confused, 0)
        self.assertTrue(self.member.elapse_sleep_turn())
        self.assertEqual(self.member.sleeping, 1)
        self.member.take_damage(1)

        self.assertEqual(self.member.sleeping, 0)
        self.assertFalse(self.member.elapse_sleep_turn())

    def test_poison_damage_does_not_wake_the_member(self) -> None:
        self.member.poisoned = True
        self.member.apply_sleep(2)

        self.assertEqual(self.member.take_poison_damage(1), 1)
        self.assertEqual(self.member.sleeping, 2)

    def test_stun_skips_exactly_one_future_action(self) -> None:
        self.assertTrue(self.member.apply_stun())
        self.assertFalse(self.member.apply_stun())
        self.assertTrue(self.member.consume_stun())
        self.assertFalse(self.member.consume_stun())

    def test_temporary_battle_ailments_are_cleared_after_battle(self) -> None:
        self.member.sleeping = 2
        self.member.confused = 3
        self.member.stunned = True
        self.member.protection_level = 2
        self.member.speed_modifier = -1
        self.member.poisoned = True
        self.member.paralyzed = True

        self.member.clear_temporary_battle_conditions()

        self.assertEqual(self.member.sleeping, 0)
        self.assertEqual(self.member.confused, 0)
        self.assertFalse(self.member.stunned)
        self.assertEqual(self.member.protection_level, 0)
        self.assertEqual(self.member.speed_modifier, 0)
        self.assertTrue(self.member.poisoned)
        self.assertTrue(self.member.paralyzed)

    def test_world_map_entry_restores_points_and_cures_every_condition(
        self,
    ) -> None:
        self.member.hp = 1
        self.member.mp = 2
        self.member.poisoned = True
        self.member.paralyzed = True
        self.member.sleeping = 2
        self.member.confused = 3
        self.member.stunned = True
        self.member.protection_level = 2
        self.member.speed_modifier = -1

        self.member.recover_world_map_entry_ailments()

        self.assertFalse(self.member.poisoned)
        self.assertFalse(self.member.paralyzed)
        self.assertEqual(self.member.sleeping, 0)
        self.assertEqual(self.member.confused, 0)
        self.assertFalse(self.member.stunned)
        self.assertEqual(self.member.protection_level, 0)
        self.assertEqual(self.member.speed_modifier, 0)
        self.assertEqual(self.member.hp, self.member.max_hp)
        self.assertEqual(self.member.mp, self.member.max_mp)

    def test_world_map_entry_does_not_revive_a_dead_member(self) -> None:
        self.member.hp = 0
        self.member.mp = 2

        self.member.recover_world_map_entry_ailments()

        self.assertEqual(self.member.hp, 0)
        self.assertEqual(self.member.mp, self.member.max_mp)

    def test_full_recovery_restores_points_and_all_conditions(self) -> None:
        self.member.hp = 1
        self.member.mp = 2
        self.member.poisoned = True
        self.member.paralyzed = True
        self.member.sleeping = 2
        self.member.confused = 2
        self.member.stunned = True
        self.member.protection_level = -1
        self.member.speed_modifier = -1

        self.member.fully_recover()

        self.assertEqual(self.member.hp, self.member.max_hp)
        self.assertEqual(self.member.mp, self.member.max_mp)
        self.assertFalse(self.member.poisoned)
        self.assertFalse(self.member.paralyzed)
        self.assertEqual(self.member.sleeping, 0)
        self.assertEqual(self.member.confused, 0)
        self.assertFalse(self.member.stunned)
        self.assertEqual(self.member.protection_level, 0)
        self.assertEqual(self.member.speed_modifier, 0)

    def test_protection_raises_defense_twice_using_da2_formula(self) -> None:
        armor = self.item("ARMOR", "BODY", defense=10)
        self.member.equipment = EquipmentSet({EquipmentSlot.BODY: armor})

        self.assertEqual(self.member.battle_stats.defense, 10)
        self.assertTrue(self.member.apply_protection())
        self.assertEqual(self.member.battle_stats.defense, 18)
        self.assertTrue(self.member.apply_protection())
        self.assertEqual(self.member.battle_stats.defense, 30)
        self.assertFalse(self.member.apply_protection())
        self.assertEqual(self.member.protection_level, 2)

    def test_defense_down_cancels_protection_then_uses_da2_formula(self) -> None:
        armor = self.item("ARMOR", "BODY", defense=20)
        self.member.equipment = EquipmentSet({EquipmentSlot.BODY: armor})
        self.member.protection_level = 1

        self.assertTrue(self.member.apply_defense_down())
        self.assertEqual(self.member.protection_level, 0)
        self.assertEqual(self.member.battle_stats.defense, 20)
        self.assertTrue(self.member.apply_defense_down())
        self.assertEqual(self.member.protection_level, -1)
        self.assertEqual(self.member.battle_stats.defense, 5)
        self.assertFalse(self.member.apply_defense_down())

    def test_death_clears_battle_modifiers(self) -> None:
        self.member.poisoned = True
        self.member.paralyzed = True
        self.member.sleeping = 2
        self.member.confused = 2
        self.member.stunned = True
        self.member.protection_level = 2
        self.member.speed_modifier = -1

        self.member.take_damage(self.member.hp)

        self.assertFalse(self.member.poisoned)
        self.assertFalse(self.member.paralyzed)
        self.assertEqual(self.member.sleeping, 0)
        self.assertEqual(self.member.confused, 0)
        self.assertFalse(self.member.stunned)
        self.assertEqual(self.member.protection_level, 0)
        self.assertEqual(self.member.speed_modifier, 0)

    def test_effective_agility_uses_speed_modifier_and_slow_cancels_haste(self) -> None:
        self.assertEqual(self.member.adjusted_abilities.agility, 25)
        self.assertEqual(self.member.effective_agility, 25)

        self.member.speed_modifier = -1
        self.assertTrue(self.member.apply_haste())
        self.assertEqual(self.member.speed_modifier, 0)
        self.assertTrue(self.member.apply_haste())
        self.assertTrue(self.member.apply_haste())
        self.assertFalse(self.member.apply_haste())
        self.assertEqual(self.member.speed_modifier, 2)
        self.assertEqual(self.member.effective_agility, 37)
        self.assertTrue(self.member.apply_slow())
        self.assertEqual(self.member.speed_modifier, 0)
        self.assertTrue(self.member.apply_slow())
        self.assertEqual(self.member.speed_modifier, -1)
        self.assertEqual(self.member.effective_agility, 18)
        self.assertEqual(self.member.battle_stats.evasion, 0)
        self.assertFalse(self.member.apply_slow())

    def test_negative_equipment_healing_reduces_hp(self) -> None:
        cursed_ring = self.item("CURSED RING", "ARM", healing=-2)
        self.member.equipment = EquipmentSet(
            {EquipmentSlot.ARM: cursed_ring}
        )
        self.member.hp = 40

        self.assertEqual(self.member.healing, -2)
        self.assertEqual(self.member.heal_and_poison_amount, -2)
        self.assertEqual(self.member.apply_heal_and_poison(), -2)
        self.assertEqual(self.member.hp, 38)

    def test_poison_and_negative_equipment_healing_stack_per_step(self) -> None:
        cursed_ring = self.item("CURSED RING", "ARM", healing=-2)
        self.member.equipment = EquipmentSet(
            {EquipmentSlot.ARM: cursed_ring}
        )
        self.member.poisoned = True
        self.member.hp = 40

        self.assertEqual(self.member.heal_and_poison_amount, -3)
        self.assertEqual(self.member.apply_heal_and_poison(), -3)
        self.assertEqual(self.member.hp, 37)

    def test_keeps_base_and_adjusted_ability_layers_separate(self) -> None:
        self.assertEqual(
            self.member.definition.base_abilities,
            BaseAbilities(strength=17, agility=25, magic=24),
        )
        self.assertEqual(
            self.member.adjusted_abilities,
            AdjustedAbilities(strength=17, agility=25, magic=24),
        )

    def test_adjusted_abilities_include_equipment_modifiers_and_cap_at_32(
        self,
    ) -> None:
        flower_crown = self.item(
            "FLOWER CROWN",
            "HEAD",
            strength_modifier=1,
            agility_modifier=1,
            magic_modifier=1,
        )
        magic_ring = self.item(
            "MAGIC RING",
            "ARM",
            strength_modifier=20,
            magic_modifier=-2,
        )
        self.member.equipment = EquipmentSet(
            {
                EquipmentSlot.HEAD: flower_crown,
                EquipmentSlot.ARM: magic_ring,
            }
        )

        self.assertEqual(
            self.member.adjusted_abilities,
            AdjustedAbilities(strength=32, agility=26, magic=23),
        )
        self.assertEqual(
            self.member.definition.base_abilities,
            BaseAbilities(strength=17, agility=25, magic=24),
        )

    def test_fiora_initial_growth_state_uses_level_one_formulas(self) -> None:
        self.assertEqual(self.member.internal_level, 1)
        self.assertEqual(self.member.hp, 44)
        self.assertEqual(self.member.max_hp, 44)
        self.assertEqual(self.member.mp, 12)
        self.assertEqual(self.member.max_mp, 12)

    def test_maximum_points_remain_stored_when_internal_level_changes(self) -> None:
        self.member.internal_level = 2

        self.assertEqual((self.member.hp, self.member.max_hp), (44, 44))
        self.assertEqual((self.member.mp, self.member.max_mp), (12, 12))

    def test_max_hp_growth_is_limited_to_one_internal_level_step(self) -> None:
        self.member.internal_level = 5

        amount = self.member.apply_max_hp_growth()

        self.assertEqual(amount, 9)
        self.assertEqual(self.member.max_hp, 53)
        self.assertEqual(self.member.hp, 44)
        self.assertEqual(self.member.calculated_max_hp(), 79)

    def test_max_mp_growth_uses_one_internal_level_step_without_spell_level_up(
        self,
    ) -> None:
        self.member.internal_level = 5

        amount = self.member.apply_max_mp_growth(
            maximum_spell_level_increased=False
        )

        self.assertEqual(amount, 1)
        self.assertEqual(self.member.max_mp, 13)
        self.assertEqual(self.member.mp, 12)
        self.assertEqual(self.member.calculated_max_mp(), 17)

    def test_max_mp_growth_uses_one_spell_level_step_after_spell_level_up(
        self,
    ) -> None:
        self.member.internal_level = 5
        self.member.proficiency(ProficiencyKind.MYSTIC).level = 2

        amount = self.member.apply_max_mp_growth(
            maximum_spell_level_increased=True
        )

        self.assertEqual(amount, 2)
        self.assertEqual(self.member.max_mp, 14)
        self.assertEqual(self.member.mp, 12)
        self.assertEqual(self.member.calculated_max_mp(), 19)

    def test_growth_steps_use_uncapped_values_near_point_limits(self) -> None:
        member = Member.from_record_at_internal_level(
            {
                "name_en": "Limit",
                "name_ja": "Limit",
                "race": "HUMAN",
                "gender": "NONE",
                "base_str": 1,
                "base_agi": 1,
                "base_mag": 1,
                **GROWTH_FIELDS,
                "base_hp": 60,
                "base_mp": 32,
                **FACE_FIELDS,
                **PROFICIENCY_FIELDS,
                "sp_mystic": 2,
            },
            99,
        )
        member.hp = member.max_hp = 980
        member.mp = member.max_mp = 240

        hp_amount = member.apply_max_hp_growth()
        mp_amount = member.apply_max_mp_growth(
            maximum_spell_level_increased=True
        )

        self.assertEqual((hp_amount, member.max_hp), (12, 992))
        self.assertEqual((mp_amount, member.max_mp), (15, 255))

    def test_initial_skills_and_equipment_are_copied_to_member_state(self) -> None:
        dagger = self.item("DAGGER", "RIGHT", "KNIFE")
        robe = self.item("ROBE", "BODY")
        focus = self.skill("Focus")
        member = Member.from_record(
            {
                "name_en": "Fiora",
                "race": "FAIRY",
                "gender": "FEMALE",
                "base_str": 17,
                "base_agi": 25,
                "base_mag": 24,
                **GROWTH_FIELDS,
                "skills": ["Focus"],
                "equip_right": "DAGGER",
                "equip_left": "",
                "equip_head": "",
                "equip_body": "ROBE",
                "equip_arm": "",
                **FACE_FIELDS,
                **PROFICIENCY_FIELDS,
            },
            items={"DAGGER": dagger, "ROBE": robe},
            skills={"Focus": focus},
        )

        self.assertEqual(member.definition.initial_skill_keys, ("Focus",))
        self.assertEqual(member.skills, [focus])
        self.assertIs(
            member.equipment.item_at(EquipmentSlot.RIGHT),
            dagger,
        )
        self.assertIs(
            member.equipment.item_at(EquipmentSlot.BODY),
            robe,
        )
        self.assertEqual(member.equipment.equipped_items(), (dagger, robe))

    def test_equipment_set_supports_explicit_left_hand_weapon(self) -> None:
        sword = self.item("SWORD", "RIGHT", "SWORD")
        dagger = self.item("DAGGER", "RIGHT", "KNIFE")

        equipment = EquipmentSet(
            {
                EquipmentSlot.RIGHT: sword,
                EquipmentSlot.LEFT: dagger,
            }
        )

        self.assertIs(equipment.item_at(EquipmentSlot.LEFT), dagger)

    def test_fiora_starts_enabled_proficiencies_at_level_one(self) -> None:
        record = {
            "name_en": "Fiora",
            "race": "FAIRY",
            "gender": "FEMALE",
            "base_str": 17,
            "base_agi": 25,
            "base_mag": 24,
            **GROWTH_FIELDS,
            **FACE_FIELDS,
            **PROFICIENCY_FIELDS,
            "eq_sword": 2,
            "eq_knife": 1,
        }

        member = Member.from_record(record)

        self.assertEqual(
            member.definition.proficiency_aptitudes[ProficiencyKind.SWORD],
            ProficiencyAptitude.FAVORED,
        )
        self.assertEqual(
            (
                member.proficiency(ProficiencyKind.SWORD).level,
                member.proficiency(ProficiencyKind.SWORD).progress,
            ),
            (1, 0),
        )
        self.assertEqual(
            (
                member.proficiency(ProficiencyKind.KNIFE).level,
                member.proficiency(ProficiencyKind.KNIFE).progress,
            ),
            (1, 0),
        )
        self.assertEqual(
            (
                member.proficiency(ProficiencyKind.KATANA).level,
                member.proficiency(ProficiencyKind.KATANA).progress,
            ),
            (0, 0),
        )

    def test_other_member_joining_state_uses_fiora_level_and_difference(self) -> None:
        record = {
            "name_en": "Cerion",
            "type": "SUB",
            "race": "FAIRY",
            "gender": "MALE",
            "lv_diff": 2,
            "base_hp": 46,
            "base_mp": 30,
            "base_str": 18,
            "base_agi": 22,
            "base_mag": 21,
            **FACE_FIELDS,
            **PROFICIENCY_FIELDS,
            "eq_knife": 1,
            "eq_spear": 2,
            "sp_mystic": 1,
            "sp_sacred": 2,
        }

        member = Member.from_record(record, fiora_internal_level=1)

        self.assertEqual(member.internal_level, 3)
        self.assertEqual((member.hp, member.max_hp), (64, 64))
        self.assertEqual((member.mp, member.max_mp), (16, 16))
        self.assertEqual(
            (
                member.proficiency(ProficiencyKind.SPEAR).level,
                member.proficiency(ProficiencyKind.SPEAR).progress,
            ),
            (1, 84),
        )
        self.assertEqual(
            (
                member.proficiency(ProficiencyKind.KNIFE).level,
                member.proficiency(ProficiencyKind.KNIFE).progress,
            ),
            (1, 14),
        )

    def test_recreates_fiora_at_explicit_internal_level(self) -> None:
        record = {
            "name_en": "Fiora",
            "race": "FAIRY",
            "gender": "FEMALE",
            "base_str": 17,
            "base_agi": 25,
            "base_mag": 24,
            **GROWTH_FIELDS,
            **FACE_FIELDS,
            **PROFICIENCY_FIELDS,
            "eq_sword": 2,
            "eq_knife": 1,
        }

        member = Member.from_record_at_internal_level(record, 50)

        self.assertEqual(member.internal_level, 50)
        self.assertEqual((member.hp, member.max_hp), (475, 475))
        self.assertEqual(
            (
                member.proficiency(ProficiencyKind.SWORD).level,
                member.proficiency(ProficiencyKind.SWORD).progress,
            ),
            (5, 60),
        )
        self.assertEqual(
            (
                member.proficiency(ProficiencyKind.KNIFE).level,
                member.proficiency(ProficiencyKind.KNIFE).progress,
            ),
            (4, 43),
        )

    def test_explicit_level_one_keeps_fiora_starting_proficiencies(self) -> None:
        record = {
            "name_en": "Fiora",
            "race": "FAIRY",
            "gender": "FEMALE",
            "base_str": 17,
            "base_agi": 25,
            "base_mag": 24,
            **GROWTH_FIELDS,
            **FACE_FIELDS,
            **PROFICIENCY_FIELDS,
            "eq_sword": 2,
        }

        member = Member.from_record_at_internal_level(record, 1)

        self.assertEqual(
            (
                member.proficiency(ProficiencyKind.SWORD).level,
                member.proficiency(ProficiencyKind.SWORD).progress,
            ),
            (1, 0),
        )

    def test_joining_internal_level_is_capped_at_99(self) -> None:
        record = {
            "name_en": "Cerion",
            "type": "SUB",
            "race": "FAIRY",
            "gender": "MALE",
            "lv_diff": 2,
            "base_hp": 46,
            "base_mp": 30,
            "base_str": 18,
            "base_agi": 22,
            "base_mag": 21,
            **FACE_FIELDS,
            **PROFICIENCY_FIELDS,
            "eq_knife": 1,
            "eq_spear": 2,
        }

        member = Member.from_record(record, fiora_internal_level=98)

        self.assertEqual(member.internal_level, 99)
        self.assertEqual(
            (
                member.proficiency(ProficiencyKind.SPEAR).level,
                member.proficiency(ProficiencyKind.SPEAR).progress,
            ),
            (9, 52),
        )
        self.assertEqual(
            (
                member.proficiency(ProficiencyKind.KNIFE).level,
                member.proficiency(ProficiencyKind.KNIFE).progress,
            ),
            (7, 86),
        )

    def test_proficiency_progress_carries_at_100_and_respects_cap(self) -> None:
        proficiency = Proficiency(
            ProficiencyAptitude.NORMAL,
            level=7,
            progress=99,
        )

        proficiency.add_progress(1)
        self.assertEqual((proficiency.level, proficiency.progress), (8, 0))

        proficiency.add_progress(200)
        self.assertEqual((proficiency.level, proficiency.progress), (8, 99))

    def test_disabled_proficiency_cannot_gain_progress(self) -> None:
        proficiency = Proficiency(ProficiencyAptitude.DISABLED)

        proficiency.add_progress(100)

        self.assertEqual((proficiency.level, proficiency.progress), (0, 0))

    def test_rejects_proficiency_aptitude_outside_zero_to_two(self) -> None:
        record = {
            "name_en": "Fiora",
            "race": "FAIRY",
            "gender": "FEMALE",
            "base_str": 17,
            "base_agi": 25,
            "base_mag": 24,
            **GROWTH_FIELDS,
            **FACE_FIELDS,
            **PROFICIENCY_FIELDS,
            "eq_sword": 3,
        }

        with self.assertRaisesRegex(MemberDataError, "eq_sword"):
            Member.from_record(record)

    def test_calculates_single_weapon_and_defensive_battle_stats(self) -> None:
        dagger = self.item(
            "DAGGER",
            "RIGHT",
            "KNIFE",
            attack=8,
            hit=105,
            defense=99,
            spell_resistance=99,
        )
        robe = self.item(
            "ROBE",
            "BODY",
            defense=3,
            evasion=-12,
        )
        record = {
            "name_en": "Fiora",
            "race": "FAIRY",
            "gender": "FEMALE",
            "base_str": 17,
            "base_agi": 25,
            "base_mag": 24,
            **GROWTH_FIELDS,
            "equip_right": "DAGGER",
            "equip_body": "ROBE",
            **FACE_FIELDS,
            **PROFICIENCY_FIELDS,
            "eq_knife": 1,
            "eq_throwing": 1,
            "eq_wand": 1,
            "eq_shield": 2,
            "sp_mystic": 2,
        }
        member = Member.from_record(
            record,
            items={"DAGGER": dagger, "ROBE": robe},
        )
        for kind, level in (
            (ProficiencyKind.KNIFE, 8),
            (ProficiencyKind.THROWING, 8),
            (ProficiencyKind.WAND, 8),
            (ProficiencyKind.MYSTIC, 9),
        ):
            proficiency = member.proficiency(kind)
            proficiency.level = level
            proficiency.progress = 99

        stats = member.battle_stats

        self.assertEqual(stats.attack_right, 8)
        self.assertIsNone(stats.attack_left)
        self.assertEqual(stats.hit_right.total, 121)
        self.assertEqual(stats.hit_right.weapon_level_bonus, 14)
        self.assertEqual(stats.hit_right.cross_weapon_bonus, 2)
        self.assertEqual(stats.hit_right.bonus, 16)
        self.assertIsNone(stats.hit_left)
        self.assertEqual(stats.hit, 121)
        self.assertEqual(stats.hit_bonus, 16)
        self.assertEqual(stats.defense, 3)
        self.assertEqual(stats.evasion, 0)
        self.assertEqual(stats.spell_resistance, 12)

    def test_dual_wield_uses_left_attack_factor_and_average_hit(self) -> None:
        sword = self.item(
            "SWORD",
            "RIGHT",
            "SWORD",
            attack=41,
            hit=100,
        )
        dagger = self.item(
            "DAGGER",
            "RIGHT",
            "KNIFE",
            attack=41,
            hit=90,
        )
        record = {
            "name_en": "Elika",
            "race": "HUMAN",
            "gender": "FEMALE",
            "base_str": 20,
            "base_agi": 20,
            "base_mag": 20,
            **GROWTH_FIELDS,
            "equip_right": "SWORD",
            "equip_left": "DAGGER",
            **FACE_FIELDS,
            **PROFICIENCY_FIELDS,
            "eq_sword": 2,
            "eq_knife": 1,
            "eq_katana": 2,
        }
        member = Member.from_record(
            record,
            items={"SWORD": sword, "DAGGER": dagger},
        )
        for kind, level in (
            (ProficiencyKind.SWORD, 9),
            (ProficiencyKind.KNIFE, 8),
            (ProficiencyKind.KATANA, 9),
        ):
            proficiency = member.proficiency(kind)
            proficiency.level = level
            proficiency.progress = 99

        stats = member.battle_stats

        self.assertEqual((stats.attack_right, stats.attack_left), (41, 32))
        self.assertEqual(stats.hit_right.total, 118)
        self.assertEqual(stats.hit_left.total, 106)
        self.assertEqual(stats.hit, 112)
        self.assertEqual(stats.hit_bonus, 17)
        self.assertEqual(stats.evasion, 0)

    def test_two_handed_skill_increases_compatible_weapon_attack(self) -> None:
        sword = self.item(
            "SWORD",
            "RIGHT",
            "SWORD",
            attack=41,
            hit=100,
        )
        two_handed = self.skill("Two-Handed")
        record = {
            "name_en": "Ragna",
            "race": "HUMAN",
            "gender": "MALE",
            "base_str": 20,
            "base_agi": 20,
            "base_mag": 20,
            **GROWTH_FIELDS,
            "skills": ["Two-Handed"],
            "equip_right": "SWORD",
            **FACE_FIELDS,
            **PROFICIENCY_FIELDS,
            "eq_sword": 2,
        }
        member = Member.from_record(
            record,
            items={"SWORD": sword},
            skills={"Two-Handed": two_handed},
        )

        self.assertEqual(member.battle_stats.attack_right, 61)
        self.assertTrue(member.uses_two_handed_weapon(sword))

    def test_equipment_specials_grant_dual_wield_and_two_handed_skills(self) -> None:
        sword = self.item(
            "SWORD",
            "RIGHT",
            "SWORD",
            attack=40,
            hit=100,
        )
        dagger = self.item(
            "DAGGER",
            "RIGHT",
            "KNIFE",
            attack=20,
            hit=100,
        )
        dual_gloves = self.item(
            "DUAL GLOVES",
            "ARM",
            "HEAVY",
            special="DUAL_WIELD",
        )
        two_handed_gloves = self.item(
            "TWO HANDED GLOVES",
            "ARM",
            "HEAVY",
            special="TWO_HANDED",
        )
        record = {
            "name_en": "Equipment Skills",
            "race": "HUMAN",
            "gender": "MALE",
            "base_str": 20,
            "base_agi": 20,
            "base_mag": 20,
            **GROWTH_FIELDS,
            **FACE_FIELDS,
            **PROFICIENCY_FIELDS,
            "eq_sword": 2,
            "eq_knife": 2,
            "eq_shield": 2,
            "equip_right": "SWORD",
            "equip_arm": "DUAL GLOVES",
        }
        items = {
            item.key: item
            for item in (sword, dagger, dual_gloves, two_handed_gloves)
        }
        member = Member.from_record(record, items=items)

        self.assertTrue(member.has_skill("Dual-Wield"))
        self.assertTrue(member.can_equip_at(dagger, EquipmentSlot.LEFT))
        self.assertFalse(member.has_skill("Two-Handed"))

        member.equipment = member.equipment.replaced(
            {EquipmentSlot.ARM: two_handed_gloves}
        )

        self.assertFalse(member.has_skill("Dual-Wield"))
        self.assertTrue(member.has_skill("Two-Handed"))
        self.assertTrue(member.uses_two_handed_weapon(sword))
        self.assertEqual(member.battle_stats.attack_right, 60)

    def test_resistances_are_union_of_all_equipped_items(self) -> None:
        sword = self.item(
            "SWORD",
            "RIGHT",
            "SWORD",
            tolerance="炎冷",
        )
        robe = self.item(
            "ROBE",
            "BODY",
            tolerance="冷闇",
        )
        record = {
            "name_en": "Fiora",
            "race": "FAIRY",
            "gender": "FEMALE",
            "base_str": 17,
            "base_agi": 25,
            "base_mag": 24,
            **GROWTH_FIELDS,
            "equip_right": "SWORD",
            "equip_body": "ROBE",
            **FACE_FIELDS,
            **PROFICIENCY_FIELDS,
        }
        member = Member.from_record(
            record,
            items={"SWORD": sword, "ROBE": robe},
        )

        self.assertEqual(
            member.resistances,
            frozenset(
                (
                    ResistanceType.FIRE,
                    ResistanceType.FREEZE,
                    ResistanceType.DARK,
                )
            ),
        )

    def test_two_handed_equipment_reserves_the_left_hand(self) -> None:
        spear = self.item("SPEAR", "TWO_HANDS", "SPEAR")
        shield = self.item("SHIELD", "LEFT", "SHIELD")

        equipment = EquipmentSet({EquipmentSlot.RIGHT: spear})

        self.assertTrue(equipment.uses_both_hands)
        with self.assertRaisesRegex(MemberDataError, "left equipment"):
            EquipmentSet(
                {
                    EquipmentSlot.RIGHT: spear,
                    EquipmentSlot.LEFT: shield,
                }
            )

    def test_rejects_item_in_wrong_equipment_slot(self) -> None:
        robe = self.item("ROBE", "BODY")

        with self.assertRaisesRegex(MemberDataError, "cannot be equipped"):
            EquipmentSet({EquipmentSlot.HEAD: robe})

    def test_healthy_status_can_show_ok_or_nothing(self) -> None:
        localizer = Localizer(Language.JAPANESE)

        self.assertEqual(self.member.status(localizer, self.texts), "")
        self.assertEqual(
            self.member.status(localizer, self.texts, show_ok=True),
            "ＯＫ",
        )

    def test_status_uses_da2_condition_priority(self) -> None:
        localizer = Localizer(Language.ENGLISH)
        self.member.poisoned = True
        self.member.confused = 2
        self.member.sleeping = 3
        self.member.paralyzed = True

        self.assertEqual(
            self.member.status(localizer, self.texts, show_ok=True),
            "%PARALIZE%Ｐａｒａｌｙｚｅ",
        )

        self.member.hp = 0
        self.assertEqual(
            self.member.status(localizer, self.texts, show_ok=True),
            "%DEATH%Ｄｅａｄ",
        )

    def test_each_condition_uses_shared_condition_term(self) -> None:
        localizer = Localizer(Language.JAPANESE)
        cases = (
            ({"paralyzed": True}, "%PARALIZE%まひ"),
            ({"sleeping": 2}, "%SLEEP%ねむり"),
            ({"confused": 2}, "%CONFUSE%こんらん"),
            ({"poisoned": True}, "%POISON%どく"),
        )

        for values, expected in cases:
            with self.subTest(values=values):
                member = Member(self.member.definition, **values)
                self.assertEqual(member.status(localizer, self.texts), expected)

    def test_condition_state_types_are_validated(self) -> None:
        with self.assertRaisesRegex(TypeError, "paralyzed"):
            Member(self.member.definition, paralyzed=1)
        with self.assertRaisesRegex(TypeError, "sleeping"):
            Member(self.member.definition, sleeping=True)
        with self.assertRaisesRegex(ValueError, "confused"):
            Member(self.member.definition, confused=-1)
        with self.assertRaisesRegex(TypeError, "protection_level"):
            Member(self.member.definition, protection_level=True)
        with self.assertRaisesRegex(ValueError, "protection_level"):
            Member(self.member.definition, protection_level=3)
        with self.assertRaisesRegex(ValueError, "protection_level"):
            Member(self.member.definition, protection_level=-2)
        with self.assertRaisesRegex(TypeError, "speed_modifier"):
            Member(self.member.definition, speed_modifier=True)
        with self.assertRaisesRegex(ValueError, "speed_modifier"):
            Member(self.member.definition, speed_modifier=-2)

    def test_rejects_missing_base_ability(self) -> None:
        with self.assertRaisesRegex(MemberDataError, "base_mag"):
            Member.from_record(
                {
                    "name_en": "Fiora",
                    "race": "FAIRY",
                    "gender": "FEMALE",
                    "base_str": 17,
                    "base_agi": 25,
                    **GROWTH_FIELDS,
                }
            )

    def test_rejects_missing_or_unaligned_face_coordinate(self) -> None:
        record = {
            "name_en": "Fiora",
            "race": "FAIRY",
            "gender": "FEMALE",
            "base_str": 17,
            "base_agi": 25,
            "base_mag": 24,
            **GROWTH_FIELDS,
            **PROFICIENCY_FIELDS,
        }

        with self.assertRaisesRegex(MemberDataError, "face_x"):
            Member.from_record(record)

        record.update(face_x=16, face_y=0)
        with self.assertRaisesRegex(MemberDataError, "face_x"):
            Member.from_record(record)

    def test_returns_japanese_display_identity(self) -> None:
        identity = self.member.display_identity(
            Localizer(Language.JAPANESE),
            self.texts,
        )

        self.assertEqual(identity.name, "フィオラ")
        self.assertEqual(identity.race, "ようせい")
        self.assertEqual(identity.gender, "おんな")

    def test_chinese_name_uses_existing_english_fallback(self) -> None:
        identity = self.member.display_identity(
            Localizer(Language.SIMPLIFIED_CHINESE),
            self.texts,
        )

        self.assertEqual(identity.name, "Fiora")
        self.assertEqual(identity.race, "妖精")
        self.assertEqual(identity.gender, "女性")

    def test_english_display_identity_is_fullwidth(self) -> None:
        identity = self.member.display_identity(
            Localizer(Language.ENGLISH),
            self.texts,
        )

        self.assertEqual(identity.name, "Ｆｉｏｒａ")
        self.assertEqual(identity.race, "Ｆａｉｒｙ")
        self.assertEqual(identity.gender, "Ｆｅｍａｌｅ")

    def test_rejects_unknown_race(self) -> None:
        with self.assertRaises(MemberDataError):
            Member.from_record(
                {
                    "name_en": "Fiora",
                    "race": "UNKNOWN",
                    "gender": "FEMALE",
                    "base_str": 17,
                    "base_agi": 25,
                    "base_mag": 24,
                }
            )


if __name__ == "__main__":
    unittest.main()
