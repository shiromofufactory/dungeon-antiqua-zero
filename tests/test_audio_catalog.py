from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.audio_catalog import AudioCatalogError, SoundEffectDefinition, load_sound_effects


class AudioCatalogTest(unittest.TestCase):
    def test_loads_mixed_sources_without_channels(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "audio").mkdir()
            (root / "se").mkdir()
            (root / "se" / "Healing1.wav").touch()
            catalog = root / "audio" / "catalog.json"
            catalog.write_text(json.dumps({
                "format_version": 2,
                "sound_effects": {
                    "equip_complete": {"sound": 6},
                    "spell_healing1": {"wav": "Healing1.wav"},
                },
            }))

            loaded = load_sound_effects(catalog)

            self.assertEqual(loaded["equip_complete"].to_record(), {"sound": 6})
            self.assertEqual(loaded["spell_healing1"].wav_path(root / "se"), root / "se" / "Healing1.wav")
            self.assertEqual(loaded["spell_healing1"].to_record(), {"wav": "Healing1.wav"})

    def test_rejects_ambiguous_or_invalid_sources(self) -> None:
        for record in (
            {}, {"sound": 6, "wav": "hit.wav"}, {"channel": 0, "sound": 6},
            {"sound": True}, {"sound": -1}, {"sound": "6"},
            {"wav": "../hit.wav"}, {"wav": "/hit.wav"}, {"wav": "hit.ogg"},
            {"wav": ""}, {"wav": "folder\\hit.wav"}, {"wav": "./hit.wav"},
        ):
            with self.subTest(record=record), self.assertRaises(AudioCatalogError):
                SoundEffectDefinition.from_record("hit", record)

    def test_rejects_missing_wav_and_symlink_outside_se_directory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            se_dir = root / "se"
            se_dir.mkdir()
            definition = SoundEffectDefinition.from_record("hit", {"wav": "hit.wav"})
            with self.assertRaises(AudioCatalogError):
                definition.wav_path(se_dir)
            (root / "hit.wav").touch()
            (se_dir / "hit.wav").symlink_to(root / "hit.wav")
            with self.assertRaises(AudioCatalogError):
                definition.wav_path(se_dir)


if __name__ == "__main__":
    unittest.main()
