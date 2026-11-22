from __future__ import annotations

import unittest
from unittest.mock import call, patch

from tools._bootstrap import APP_ROOT  # noqa: F401 - add app to sys.path

from monster import (
    MonsterBattleState,
    MonsterDataError,
    MonsterDefinition,
    MonsterSpecialAction,
    monster_spell_keys_from_record,
    monster_special_actions_from_record,
)
from monster_ai import (
    MonsterAction,
    MonsterSpellAction,
    reinforcement_arrives,
    reinforcement_target,
    select_monster_action,
)
from resources import load_record_array


class MonsterSpecialActionDataTest(unittest.TestCase):
    def test_parses_each_one_character_action_at_the_data_boundary(self) -> None:
        self.assertEqual(
            monster_special_actions_from_record({"special": "逃突援呼会毒炎遠"}),
            (
                MonsterSpecialAction.ESCAPE,
                MonsterSpecialAction.CHARGE,
                MonsterSpecialAction.REINFORCE,
                MonsterSpecialAction.CALL,
                MonsterSpecialAction.POWER_HIT,
                MonsterSpecialAction.POISON_BREATH,
                MonsterSpecialAction.FIRE_BREATH,
                MonsterSpecialAction.RANGED_ATTACK,
            ),
        )

    def test_rejects_unknown_duplicate_or_multiline_actions(self) -> None:
        for special in ("未", "突突", "会会", "逃\n突", None):
            with self.subTest(special=special):
                with self.assertRaises(MonsterDataError):
                    monster_special_actions_from_record({"special": special})

    def test_parses_newline_delimited_spell_keys_once_at_data_boundary(self) -> None:
        self.assertEqual(
            monster_spell_keys_from_record({"spells": "SLOW\nSLEEP"}),
            ("SLOW", "SLEEP"),
        )
        self.assertEqual(
            monster_spell_keys_from_record({"spells": "SLOW\r\nSLEEP"}),
            ("SLOW", "SLEEP"),
        )
        self.assertEqual(monster_spell_keys_from_record({"spells": ""}), ())

    def test_rejects_empty_duplicate_or_non_string_spell_keys(self) -> None:
        for spells in ("SLOW\n", "SLOW\nSLOW", "SLOW\rSLEEP", None):
            with self.subTest(spells=spells):
                with self.assertRaises(MonsterDataError):
                    monster_spell_keys_from_record({"spells": spells})


class MonsterReinforcementRuleTest(unittest.TestCase):
    def test_frau_calls_poltergeist_from_the_master_data(self) -> None:
        records = load_record_array("monsters.json")
        frau_record = next(record for record in records if record["name_en"] == "Frau")
        definitions = tuple(MonsterDefinition.from_record(record) for record in records)
        frau = MonsterDefinition.from_record(frau_record)

        self.assertIn(MonsterSpecialAction.REINFORCE, monster_special_actions_from_record(frau_record))
        self.assertEqual(reinforcement_target(frau, definitions).key, "Poltergeist")

    def test_treant_calls_highest_lower_level_animated_monster(self) -> None:
        definitions = tuple(
            MonsterDefinition.from_record(record)
            for record in load_record_array("monsters.json")
        )
        treant = next(monster for monster in definitions if monster.key == "Treant")

        self.assertEqual(reinforcement_target(treant, definitions).key, "Spirit")

    def test_falls_back_to_caller_without_lower_level_same_tribe(self) -> None:
        definitions = tuple(
            MonsterDefinition.from_record(record)
            for record in load_record_array("monsters.json")
        )
        spirit = next(monster for monster in definitions if monster.key == "Spirit")

        self.assertIs(reinforcement_target(spirit, definitions), spirit)

    def test_arrival_roll_uses_living_monster_count(self) -> None:
        for living_count, roll, expected in (
            (1, 0, True),
            (1, 1, True),
            (1, 2, False),
            (2, 0, True),
            (2, 1, False),
            (3, 0, False),
        ):
            with self.subTest(living_count=living_count, roll=roll):
                with patch("monster_ai.random.randint", return_value=roll) as rng:
                    self.assertIs(reinforcement_arrives(living_count), expected)
                if living_count < 3:
                    rng.assert_called_once_with(0, 2)
                else:
                    rng.assert_not_called()


class MonsterActionSelectionTest(unittest.TestCase):
    def test_rear_ranged_attack_uses_the_normal_rotation_slot(self) -> None:
        state = MonsterBattleState(max_hp=20)
        state.action_rotation_index = 1
        arguments = dict(
            special_actions=(MonsterSpecialAction.RANGED_ATTACK,),
            is_front_row=False, can_charge=False, party_actual_attacks=(),
            monster_attack=20, spell_keys=("SLOW",), intelligence=3,
            rotation_state=state, learned_spell_keys=("SLOW",),
        )

        self.assertIs(select_monster_action(**arguments, can_attack=True), MonsterAction.ATTACK)
        self.assertEqual(state.action_rotation_index, 0)
        self.assertEqual(select_monster_action(**arguments, can_attack=True), MonsterSpellAction("SLOW"))
        self.assertEqual(select_monster_action(**arguments, can_attack=False), MonsterSpellAction("SLOW"))

    def test_rotation_includes_eligible_specials_on_their_turn(self):
        state = MonsterBattleState(max_hp=20)
        arguments = dict(
            intelligence=3, rotation_state=state,
            special_actions=(
                MonsterSpecialAction.CHARGE, MonsterSpecialAction.CALL,
                MonsterSpecialAction.REINFORCE, MonsterSpecialAction.DOUBLE_ATTACK,
            ),
            is_front_row=True, can_attack=True, can_charge=True,
            party_actual_attacks=(), monster_attack=0,
        )
        with patch("monster_ai.random.randrange", return_value=0) as choose_start:
            self.assertIs(select_monster_action(**arguments, call_slot=1), MonsterAction.CHARGE)
            self.assertIs(select_monster_action(**arguments, call_slot=1), MonsterAction.CALL)
            self.assertIs(select_monster_action(**arguments, call_slot=1), MonsterAction.ATTACK)
            self.assertIs(select_monster_action(**arguments, call_slot=2), MonsterAction.CHARGE)
            self.assertIs(select_monster_action(**arguments, call_slot=2), MonsterAction.ATTACK)
        choose_start.assert_called_once_with(3)

    def test_rear_idle_eligibility_for_random_action_selection(self):
        for intelligence, spell_keys, can_charge, expected in (
            (1, ("SLOW",), False, (MonsterSpellAction("SLOW"), MonsterAction.IDLE)),
            (2, (), False, (MonsterAction.IDLE,)),
            (2, ("SLOW",), False, (MonsterSpellAction("SLOW"),)),
            (4, (), True, (MonsterAction.CHARGE,)),
            (2, ("SLOW",), True, (MonsterAction.CHARGE, MonsterSpellAction("SLOW"))),
        ):
            with (
                self.subTest(intelligence=intelligence, spells=spell_keys, can_charge=can_charge),
                patch("monster_ai.random.choice", side_effect=lambda candidates: candidates[-1]) as choose,
            ):
                result = select_monster_action(
                    special_actions=(MonsterSpecialAction.CHARGE,),
                    is_front_row=False, can_attack=False, can_charge=can_charge,
                    party_actual_attacks=(), monster_attack=20,
                    spell_keys=spell_keys, intelligence=intelligence,
                )
                self.assertEqual(result, expected[-1])
                if len(expected) > 1:
                    choose.assert_called_once_with(list(expected))
                else:
                    choose.assert_not_called()

    def test_power_hit_is_passive_and_does_not_add_an_action_candidate(self) -> None:
        for front, expected in ((True, MonsterAction.ATTACK), (False, MonsterAction.IDLE)):
            with self.subTest(front=front), patch("monster_ai.random.choice") as choice:
                action = select_monster_action(
                    special_actions=(MonsterSpecialAction.POWER_HIT,),
                    is_front_row=front,
                    can_attack=front,
                    can_charge=True,
                    party_actual_attacks=(),
                    monster_attack=20,
                )
                self.assertIs(action, expected)
                choice.assert_not_called()

    def test_one_spell_and_front_attack_are_two_equal_candidates(self) -> None:
        selected = MonsterSpellAction("SLEEP")
        with patch("monster_ai.random.choice", return_value=selected) as choice:
            action = select_monster_action(
                special_actions=(),
                is_front_row=True,
                can_attack=True,
                can_charge=True,
                party_actual_attacks=(),
                monster_attack=10,
                spell_keys=("SLEEP",),
            )

        self.assertEqual(action, selected)
        choice.assert_called_once_with(
            [MonsterSpellAction("SLEEP"), MonsterAction.ATTACK]
        )

    def test_rear_spell_and_idle_are_two_equal_candidates(self) -> None:
        selected = MonsterSpellAction("SLEEP")
        with patch("monster_ai.random.choice", return_value=selected) as choice:
            action = select_monster_action(
                special_actions=(),
                is_front_row=False,
                can_attack=False,
                can_charge=False,
                party_actual_attacks=(),
                monster_attack=10,
                spell_keys=("SLEEP",),
            )

        self.assertEqual(action, selected)
        choice.assert_called_once_with(
            [MonsterSpellAction("SLEEP"), MonsterAction.IDLE]
        )

    def test_each_learned_spell_is_an_equal_weight_action_candidate(self) -> None:
        selected = MonsterSpellAction("SLEEP")
        with patch("monster_ai.random.choice", return_value=selected) as choice:
            action = select_monster_action(
                special_actions=(MonsterSpecialAction.CHARGE,),
                is_front_row=True,
                can_attack=True,
                can_charge=True,
                party_actual_attacks=(),
                monster_attack=10,
                spell_keys=("SLOW", "SLEEP"),
            )

        self.assertEqual(action, selected)
        choice.assert_called_once_with(
            [
                MonsterAction.CHARGE,
                MonsterSpellAction("SLOW"),
                MonsterSpellAction("SLEEP"),
                MonsterAction.ATTACK,
            ]
        )

    def test_front_charge_and_normal_attack_are_equal_weight_candidates(self) -> None:
        with patch(
            "monster_ai.random.choice",
            return_value=MonsterAction.CHARGE,
        ) as choice:
            action = select_monster_action(
                special_actions=(MonsterSpecialAction.CHARGE,),
                is_front_row=True,
                can_attack=True,
                can_charge=True,
                party_actual_attacks=(),
                monster_attack=10,
            )

        self.assertIs(action, MonsterAction.CHARGE)
        choice.assert_called_once_with(
            [MonsterAction.CHARGE, MonsterAction.ATTACK]
        )

    def test_rear_charge_and_idle_are_equal_weight_candidates(self) -> None:
        with patch(
            "monster_ai.random.choice",
            return_value=MonsterAction.CHARGE,
        ) as choice:
            action = select_monster_action(
                special_actions=(MonsterSpecialAction.CHARGE,),
                is_front_row=False,
                can_attack=False,
                can_charge=True,
                party_actual_attacks=(),
                monster_attack=10,
            )

        self.assertIs(action, MonsterAction.CHARGE)
        choice.assert_called_once_with(
            [MonsterAction.CHARGE, MonsterAction.IDLE]
        )

    def test_rear_monster_with_no_other_action_selects_idle(self) -> None:
        with patch("monster_ai.random.choice") as choice:
            action = select_monster_action(
                special_actions=(),
                is_front_row=False,
                can_attack=False,
                can_charge=False,
                party_actual_attacks=(),
                monster_attack=10,
            )

        self.assertIs(action, MonsterAction.IDLE)
        choice.assert_not_called()

    def test_escape_uses_da2_gate_and_actual_attack_comparison(self) -> None:
        with (
            patch("monster_ai.random.randint", return_value=1),
            patch(
                "monster_ai.random.choice",
                side_effect=(31, MonsterAction.ESCAPE),
            ) as choice,
            patch("monster_ai.random.uniform", return_value=1.5),
        ):
            action = select_monster_action(
                special_actions=(MonsterSpecialAction.ESCAPE,),
                is_front_row=False,
                can_attack=False,
                can_charge=False,
                party_actual_attacks=(12, 31),
                monster_attack=20,
            )

        self.assertIs(action, MonsterAction.ESCAPE)
        self.assertEqual(
            choice.call_args_list,
            [
                call((12, 31)),
                call([MonsterAction.ESCAPE, MonsterAction.IDLE]),
            ],
        )

    def test_escape_is_not_a_candidate_when_gate_or_comparison_fails(self) -> None:
        with patch("monster_ai.random.randint", return_value=0):
            self.assertIs(
                select_monster_action(
                    special_actions=(MonsterSpecialAction.ESCAPE,),
                    is_front_row=False,
                    can_attack=False,
                    can_charge=False,
                    party_actual_attacks=(99,),
                    monster_attack=1,
                ),
                MonsterAction.IDLE,
            )
        with (
            patch("monster_ai.random.randint", return_value=1),
            patch("monster_ai.random.choice", return_value=30),
            patch("monster_ai.random.uniform", return_value=1.5),
        ):
            self.assertIs(
                select_monster_action(
                    special_actions=(MonsterSpecialAction.ESCAPE,),
                    is_front_row=False,
                    can_attack=False,
                    can_charge=False,
                    party_actual_attacks=(30,),
                    monster_attack=20,
                ),
                MonsterAction.IDLE,
            )


class MonsterCallRuleTest(unittest.TestCase):
    def choose(self, *, slot=0, intelligence=0):
        return select_monster_action(
            special_actions=(MonsterSpecialAction.CALL,),
            is_front_row=True, can_attack=True, can_charge=False,
            party_actual_attacks=(), monster_attack=10,
            call_slot=slot, intelligence=intelligence,
        )

    def test_low_intelligence_uses_three_of_four_gate_then_equal_candidates(self):
        for roll in range(4):
            with (
                self.subTest(roll=roll),
                patch("monster_ai.random.randint", return_value=roll) as rng,
                patch("monster_ai.random.choice", return_value=MonsterAction.CALL) as choice,
            ):
                action = self.choose()
                rng.assert_called_once_with(0, 3)
                if roll:
                    self.assertIs(action, MonsterAction.CALL)
                    choice.assert_called_once_with([MonsterAction.CALL, MonsterAction.ATTACK])
                else:
                    self.assertIs(action, MonsterAction.ATTACK)
                    choice.assert_not_called()

    def test_full_formation_never_rolls_or_calls(self):
        with patch("monster_ai.random.randint") as rng:
            self.assertIs(self.choose(slot=None), MonsterAction.ATTACK)
            rng.assert_not_called()

    def test_da2_high_intelligence_prioritizes_first_two_empty_slots(self):
        for slot in range(5):
            with self.subTest(slot=slot), patch("monster_ai.random.randint") as rng:
                expected = MonsterAction.CALL if slot <= 1 else MonsterAction.ATTACK
                self.assertIs(self.choose(slot=slot, intelligence=2), expected)
                rng.assert_not_called()

    def test_call_data_key_is_supported(self):
        self.assertEqual(monster_special_actions_from_record({"special": "呼"}),
                         (MonsterSpecialAction.CALL,))


if __name__ == "__main__":
    unittest.main()
