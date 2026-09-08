from __future__ import annotations

from types import MappingProxyType
import unittest

from scripts.spell_effect_pipeline import (
    ImageCatalogEntry,
    SpellCatalogEntry,
    SpellEffectCatalogs,
    SpellEffectSourceError,
    compile_document,
    definitions_from_document,
    source_document_from_definitions,
    validate_document,
)


def catalogs() -> SpellEffectCatalogs:
    width = 96
    height = 64
    pixels = bytearray([1] * (width * height))
    pixels[0] = 2
    return SpellEffectCatalogs(
        spells=(
            SpellCatalogEntry("FIRE1", True),
            SpellCatalogEntry("TELEPORT", True),
            SpellCatalogEntry("CAMP", False),
        ),
        images=MappingProxyType(
            {
                "effects/spells32": ImageCatalogEntry(
                    "effects/spells32", width, height, 0, width * height
                )
            }
        ),
        palette_color_count=16,
        transparent_index=1,
        se_ids=frozenset(("spell_fire1",)),
        image_bundle=bytes(pixels),
    )


def source_record(**changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "spell_key": "FIRE1",
        "kind": "target_sprite",
        "image_id": "effects/spells32",
        "row": 0,
        "frame_count": 1,
        "frames_per_pattern": 4,
        "offset": {"ally": [0, 0], "enemy": [0, 0]},
        "flash_color": 10,
        "se_id": "spell_fire1",
    }
    record.update(changes)
    return record


class SpellEffectPipelineTest(unittest.TestCase):
    def test_compiles_source_array_to_runtime_index_in_master_order(self) -> None:
        document = {
            "format_version": 2,
            "effects": [
                source_record(spell_key="CAMP", flash_color=None, se_id=None),
                source_record(),
            ],
        }

        compiled = compile_document(document, catalogs())

        self.assertEqual(tuple(compiled["effects"]), ("FIRE1", "CAMP"))
        self.assertNotIn("spell_key", compiled["effects"]["FIRE1"])
        self.assertEqual(compiled["effects"]["FIRE1"]["frames_per_pattern"], 4)
        self.assertEqual(compiled["format_version"], 2)

    def test_warns_for_missing_battle_effect_and_nonbattle_setting(self) -> None:
        document = {
            "format_version": 2,
            "effects": [source_record(spell_key="CAMP", flash_color=None, se_id=None)],
        }

        diagnostics = validate_document(document, catalogs())
        codes = {(item.spell_key, item.code) for item in diagnostics}

        self.assertIn(("CAMP", "not_battle_spell"), codes)
        self.assertIn(("FIRE1", "missing_effect"), codes)
        self.assertIn(("TELEPORT", "missing_effect"), codes)

    def test_rejects_bounds_palette_sound_and_duplicate_errors(self) -> None:
        bad = source_record(frame_count=4, flash_color=1, se_id="missing")
        document = {"format_version": 2, "effects": [bad, dict(bad)]}

        diagnostics = validate_document(document, catalogs())
        codes = {item.code for item in diagnostics if item.severity == "error"}

        self.assertEqual(
            codes,
            {
                "duplicate_spell_key",
                "frames_out_of_bounds",
                "invalid_flash_color",
                "unknown_se_id",
            },
        )
        with self.assertRaises(SpellEffectSourceError):
            compile_document(document, catalogs())

    def test_warns_when_selected_pattern_is_fully_transparent(self) -> None:
        document = {
            "format_version": 2,
            "effects": [source_record(frame_count=2)],
        }

        diagnostics = validate_document(document, catalogs())

        empty = next(item for item in diagnostics if item.code == "empty_frames")
        self.assertEqual(empty.spell_key, "FIRE1")
        self.assertIn("1", empty.message)

    def test_serializes_authoring_records_in_spell_order(self) -> None:
        document = {
            "format_version": 2,
            "effects": [
                source_record(spell_key="CAMP", flash_color=None, se_id=None),
                source_record(),
            ],
        }
        definitions = definitions_from_document(document, catalogs())

        serialized = source_document_from_definitions(
            definitions, ("FIRE1", "TELEPORT", "CAMP")
        )

        self.assertEqual(
            [record["spell_key"] for record in serialized["effects"]],
            ["FIRE1", "CAMP"],
        )
        self.assertEqual(serialized["format_version"], 2)

    def test_compiles_legacy_single_offset_into_both_target_sides(self) -> None:
        document = {
            "format_version": 1,
            "effects": [source_record(offset=[3, -2])],
        }

        diagnostics = validate_document(document, catalogs())
        compiled = compile_document(document, catalogs())

        self.assertIn("legacy_format_version", {item.code for item in diagnostics})
        self.assertEqual(compiled["format_version"], 2)
        self.assertEqual(
            compiled["effects"]["FIRE1"]["offset"],
            {"ally": [3, -2], "enemy": [3, -2]},
        )


if __name__ == "__main__":
    unittest.main()
