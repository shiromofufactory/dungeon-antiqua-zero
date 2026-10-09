from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
import unittest

from app.spell_effect import SpellEffectDefinition
from scripts.spell_effect_pipeline import (
    ImageCatalogEntry,
    SpellCatalogEntry,
    SpellEffectCatalogs,
    SpellEffectSourceError,
)
from tools.spell_effect_editor.model import SpellEffectEditorStore


class SpellEffectEditorStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.content_root = self.root / "content"
        (self.content_root / "data").mkdir(parents=True)
        (self.content_root / "effects").mkdir()
        (self.root / "app" / "audio").mkdir(parents=True)
        self.audio_path = self.root / "app" / "audio" / "catalog.json"
        self.audio_path.write_text(
            json.dumps(
                {
                    "format_version": 2,
                    "sound_effects": {
                        "confirm": {"sound": 9},
                    },
                }
            ),
            encoding="utf-8",
        )
        (self.content_root / "data" / "spells.json").write_text(
            json.dumps(
                [
                    {
                        "name_en": "FIRE1",
                        "name_ja": "ファイア",
                        "type": "mystic",
                        "on_battle": 1,
                    }
                ]
            ),
            encoding="utf-8",
        )
        (self.content_root / "effects" / "spells.json").write_text(
            '{"format_version": 1, "effects": []}\n', encoding="utf-8"
        )
        pixels = bytes([2] + [1] * (32 * 32 - 1))
        self.catalogs = SpellEffectCatalogs(
            spells=(SpellCatalogEntry("FIRE1", True),),
            images=MappingProxyType(
                {
                    "effects/spells32": ImageCatalogEntry(
                        "effects/spells32", 32, 32, 0, len(pixels)
                    )
                }
            ),
            palette_color_count=16,
            transparent_index=1,
            se_ids=frozenset(("confirm",)),
            image_bundle=pixels,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def definition() -> SpellEffectDefinition:
        return SpellEffectDefinition.from_record(
            "FIRE1",
            {
                "kind": "target_sprite",
                "image_id": "effects/spells32",
                "row": 0,
                "frame_count": 1,
                "frames_per_pattern": 7,
                "offset": {"ally": [3, -2], "enemy": [-4, 5]},
                "flash_color": 10,
                "se_id": "confirm",
            },
        )

    def test_saves_source_and_compiled_runtime_data(self) -> None:
        store = SpellEffectEditorStore(
            self.root, content_root=self.content_root, catalogs=self.catalogs
        )

        store.set_definition(self.definition())
        self.assertTrue(store.dirty)
        store.save()

        source = json.loads(store.source_path.read_text(encoding="utf-8"))
        runtime = json.loads(store.runtime_path.read_text(encoding="utf-8"))
        self.assertEqual(source["effects"][0]["spell_key"], "FIRE1")
        self.assertEqual(source["format_version"], 2)
        self.assertEqual(
            source["effects"][0]["offset"],
            {"ally": [3, -2], "enemy": [-4, 5]},
        )
        self.assertEqual(runtime["effects"]["FIRE1"]["frames_per_pattern"], 7)
        self.assertFalse(store.dirty)

    def test_refuses_to_overwrite_external_source_change(self) -> None:
        store = SpellEffectEditorStore(
            self.root, content_root=self.content_root, catalogs=self.catalogs
        )
        store.set_definition(self.definition())
        store.source_path.write_text(
            '{"format_version": 1, "effects": [], "external": true}\n',
            encoding="utf-8",
        )

        with self.assertRaises(SpellEffectSourceError):
            store.save()

    def test_registers_sound_and_saves_it_for_runtime_use(self) -> None:
        store = SpellEffectEditorStore(
            self.root, content_root=self.content_root, catalogs=self.catalogs
        )

        store.register_sound_effect("spell_fire1", sound=17)
        self.assertIn("spell_fire1", store.catalogs.se_ids)
        definition = self.definition()
        store.set_definition(
            SpellEffectDefinition.from_record(
                definition.spell_key,
                {**definition.to_runtime_record(), "se_id": "spell_fire1"},
            )
        )
        store.save()

        audio = json.loads(self.audio_path.read_text(encoding="utf-8"))
        self.assertEqual(
            audio["sound_effects"]["spell_fire1"],
            {"sound": 17},
        )
        runtime = json.loads(store.runtime_path.read_text(encoding="utf-8"))
        self.assertEqual(runtime["effects"]["FIRE1"]["se_id"], "spell_fire1")

    def test_rejects_duplicate_or_invalid_sound_ids(self) -> None:
        store = SpellEffectEditorStore(
            self.root, content_root=self.content_root, catalogs=self.catalogs
        )

        with self.assertRaises(ValueError):
            store.register_sound_effect("confirm", sound=9)
        with self.assertRaises(ValueError):
            store.register_sound_effect("BAD ID", sound=9)

    def test_updates_existing_sound_source_without_changing_references(self) -> None:
        se_dir = self.root / "app" / "se"
        se_dir.mkdir()
        (se_dir / "fire1.wav").touch()
        store = SpellEffectEditorStore(
            self.root, content_root=self.content_root, catalogs=self.catalogs
        )
        store.set_definition(self.definition())
        store.save()

        store.update_sound_effect("confirm", sound=9)
        self.assertFalse(store.dirty)
        store.update_sound_effect("confirm", wav="fire1.wav")
        self.assertTrue(store.dirty)
        store.save()

        reopened = SpellEffectEditorStore(
            self.root, content_root=self.content_root, catalogs=self.catalogs
        )
        self.assertEqual(reopened.definition("FIRE1").se_id, "confirm")
        self.assertEqual(reopened.sound_effect("confirm").wav, "fire1.wav")
        self.assertIsNone(reopened.sound_effect("confirm").sound)
        self.assertEqual(set(reopened.sound_effects), {"confirm"})
        reopened.update_sound_effect("confirm", sound=17)
        reopened.save()
        audio = json.loads(self.audio_path.read_text())
        self.assertEqual(audio["sound_effects"], {"confirm": {"sound": 17}})
        with self.assertRaises(ValueError):
            reopened.update_sound_effect("missing", sound=9)
        with self.assertRaises(ValueError):
            reopened.update_sound_effect("confirm", wav="missing.wav")
        self.assertEqual(reopened.sound_effect("confirm").sound, 17)

    def test_registers_wav_and_preserves_both_sources_when_saved_and_reopened(self) -> None:
        se_dir = self.root / "app" / "se"
        se_dir.mkdir()
        (se_dir / "fire1.wav").touch()
        store = SpellEffectEditorStore(
            self.root, content_root=self.content_root, catalogs=self.catalogs
        )

        self.assertEqual(store.available_wavs, ("fire1.wav",))
        store.register_sound_effect("spell_fire1", wav="fire1.wav")
        store.set_definition(SpellEffectDefinition.from_record(
            "FIRE1", {**self.definition().to_runtime_record(), "se_id": "spell_fire1"},
        ))
        store.save()

        audio = json.loads(self.audio_path.read_text())
        self.assertEqual(audio["format_version"], 2)
        self.assertEqual(audio["sound_effects"]["confirm"], {"sound": 9})
        self.assertEqual(audio["sound_effects"]["spell_fire1"], {"wav": "fire1.wav"})
        reopened = SpellEffectEditorStore(
            self.root, content_root=self.content_root, catalogs=store.catalogs
        )
        self.assertEqual(reopened.sound_effect("spell_fire1").wav, "fire1.wav")
        self.assertEqual(reopened.definition("FIRE1").se_id, "spell_fire1")
        with self.assertRaises(ValueError):
            reopened.register_sound_effect("missing", wav="missing.wav")
        (se_dir / "fire1.wav").unlink()
        with self.assertRaises(SpellEffectSourceError):
            reopened.save()
        self.assertEqual(json.loads(self.audio_path.read_text()), audio)

    def test_refuses_to_overwrite_external_audio_catalog_change(self) -> None:
        store = SpellEffectEditorStore(
            self.root, content_root=self.content_root, catalogs=self.catalogs
        )
        store.register_sound_effect("spell_fire1", sound=17)
        self.audio_path.write_text(
            '{"format_version": 2, "sound_effects": {}}\n',
            encoding="utf-8",
        )

        with self.assertRaises(SpellEffectSourceError):
            store.save()


if __name__ == "__main__":
    unittest.main()
