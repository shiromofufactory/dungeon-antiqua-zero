from __future__ import annotations

import unittest

from app.item import Item
from app.localization import Localizer
from app.member import (
    AdjustedAbilities,
    BaseAbilities,
    EquipmentSet,
    EquipmentSlot,
    FacePosition,
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
                **FACE_FIELDS,
                **PROFICIENCY_FIELDS,
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
                    "text_key": "status.paralyzed",
                    "text_ja": "まひ",
                    "text_en": "Paralyze",
                    "text_zhcn": "麻痹",
                },
                {
                    "text_key": "status.sleeping",
                    "text_ja": "ねむり",
                    "text_en": "Asleep",
                    "text_zhcn": "睡眠",
                },
                {
                    "text_key": "status.confused",
                    "text_ja": "らん",
                    "text_en": "Confused",
                    "text_zhcn": "混乱",
                },
                {
                    "text_key": "status.poisoned",
                    "text_ja": "どく",
                    "text_en": "Poisoned",
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
        spell_resistance: int = 0,
        tolerance: str = "",
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
                "rst": spell_resistance,
                "tolerance": tolerance,
            }
        )

    @staticmethod
    def skill(key: str) -> Skill:
        return Skill.from_record({"name_en": key, "name_ja": key})

    def test_normalizes_stable_race_and_gender_values(self) -> None:
        self.assertEqual(self.member.definition.race, Race.FAIRY)
        self.assertEqual(self.member.definition.gender, Gender.FEMALE)

    def test_keeps_face_sheet_position_on_member(self) -> None:
        self.assertEqual(self.member.face_position, FacePosition(0, 0))

    def test_keeps_base_and_adjusted_ability_layers_separate(self) -> None:
        self.assertEqual(
            self.member.definition.base_abilities,
            BaseAbilities(strength=17, agility=25, magic=24),
        )
        self.assertEqual(
            self.member.adjusted_abilities,
            AdjustedAbilities(strength=17, agility=25, magic=24),
        )

    def test_initial_health_and_magic_points_are_fixed_member_state(self) -> None:
        self.assertEqual(self.member.hp, 999)
        self.assertEqual(self.member.max_hp, 999)
        self.assertEqual(self.member.mp, 255)
        self.assertEqual(self.member.max_mp, 255)

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

    def test_initial_proficiencies_are_fixed_at_each_aptitude_limit(self) -> None:
        record = {
            "name_en": "Fiora",
            "race": "FAIRY",
            "gender": "FEMALE",
            "base_str": 17,
            "base_agi": 25,
            "base_mag": 24,
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
            (9, 99),
        )
        self.assertEqual(
            (
                member.proficiency(ProficiencyKind.KNIFE).level,
                member.proficiency(ProficiencyKind.KNIFE).progress,
            ),
            (8, 99),
        )
        self.assertEqual(
            (
                member.proficiency(ProficiencyKind.KATANA).level,
                member.proficiency(ProficiencyKind.KATANA).progress,
            ),
            (0, 0),
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
        )
        record = {
            "name_en": "Fiora",
            "race": "FAIRY",
            "gender": "FEMALE",
            "base_str": 17,
            "base_agi": 25,
            "base_mag": 24,
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
        self.assertEqual(stats.evasion, 13)
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

    def test_healthy_status_can_show_max_hp_ok_or_nothing(self) -> None:
        localizer = Localizer(Language.JAPANESE)

        self.assertEqual(self.member.status(localizer, self.texts), "９９９")
        self.assertEqual(
            self.member.status(localizer, self.texts, show_ok=True),
            "ＯＫ",
        )
        self.assertEqual(
            self.member.status(localizer, self.texts, show_mhp=False),
            "",
        )

    def test_status_uses_da2_condition_priority(self) -> None:
        localizer = Localizer(Language.ENGLISH)
        self.member.poisoned = True
        self.member.confused = 2
        self.member.sleeping = 3
        self.member.paralyzed = True

        self.assertEqual(
            self.member.status(localizer, self.texts, show_ok=True),
            "Ｐａｒａｌｙｚｅ",
        )

        self.member.hp = 0
        self.assertEqual(
            self.member.status(localizer, self.texts, show_ok=True),
            "Ｄｅａｄ",
        )

    def test_each_condition_has_da2_localized_text(self) -> None:
        localizer = Localizer(Language.JAPANESE)
        cases = (
            ({"paralyzed": True}, "まひ"),
            ({"sleeping": 2}, "ねむり"),
            ({"confused": 2}, "らん"),
            ({"poisoned": True}, "どく"),
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

    def test_rejects_missing_base_ability(self) -> None:
        with self.assertRaisesRegex(MemberDataError, "base_mag"):
            Member.from_record(
                {
                    "name_en": "Fiora",
                    "race": "FAIRY",
                    "gender": "FEMALE",
                    "base_str": 17,
                    "base_agi": 25,
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
