from __future__ import annotations

import unittest

from app.resistance import ResistanceType, resistances_from_tolerance


class ResistanceTest(unittest.TestCase):
    def test_maps_all_supported_tolerance_characters(self) -> None:
        self.assertEqual(
            resistances_from_tolerance("炎冷闇眠毒麻乱黙死止"),
            frozenset(ResistanceType),
        )

    def test_ignores_unknown_characters_and_collapses_duplicates(self) -> None:
        self.assertEqual(
            resistances_from_tolerance("炎炎？"),
            frozenset((ResistanceType.FIRE,)),
        )

    def test_requires_string_tolerance(self) -> None:
        with self.assertRaises(TypeError):
            resistances_from_tolerance(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
