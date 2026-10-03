from __future__ import annotations

import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import wave


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build-audio.py"
HAS_AUDIO_TOOLS = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@unittest.skipUnless(HAS_AUDIO_TOOLS, "ffmpeg and ffprobe are required")
class AudioBuildTest(unittest.TestCase):
    def test_converts_nested_wav_to_pyxel_ready_ogg(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "source"
            output_dir = root / "output"
            mp3_dir = root / "mp3"
            cache_dir = root / "cache"
            source = source_dir / "dungeon" / "floor1.wav"
            source.parent.mkdir(parents=True)
            self._write_stereo_wav(source)

            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_SCRIPT),
                    "--source-dir",
                    str(source_dir),
                    "--output-dir",
                    str(output_dir),
                    "--mp3-output-dir",
                    str(mp3_dir),
                    "--cache-dir",
                    str(cache_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            output = output_dir / "dungeon" / "floor1.ogg"
            self.assertTrue(output.is_file())
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_name,sample_rate,channels",
                    "-of",
                    "json",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            stream = json.loads(probe.stdout)["streams"][0]
            self.assertEqual(stream["codec_name"], "vorbis")
            self.assertEqual(stream["sample_rate"], "22050")
            self.assertEqual(stream["channels"], 1)
            self.assertEqual(len(list(mp3_dir.glob("dungeon/floor1_*.mp3"))), 1)

    def test_preserves_existing_ogg_and_skips_unchanged_sources(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_dir = root / "source"
            output_dir = root / "ogg"
            mp3_dir = root / "mp3"
            cache_dir = root / "cache"
            source_dir.mkdir()
            output_dir.mkdir()
            source = source_dir / "da3-win.wav"
            output = output_dir / "da3-win.ogg"
            self._write_stereo_wav(source, frequency=440)

            # Previously generated OGG files used a random stream serial.
            subprocess.run(
                [
                    "ffmpeg", "-v", "error", "-i", str(source), "-vn",
                    "-ac", "1", "-ar", "22050", "-c:a", "libvorbis",
                    "-q:a", "4", str(output),
                ],
                check=True,
            )
            original_bytes = output.read_bytes()
            original_mtime = output.stat().st_mtime_ns

            def build() -> str:
                result = subprocess.run(
                    [
                        sys.executable, str(BUILD_SCRIPT),
                        "--source-dir", str(source_dir),
                        "--output-dir", str(output_dir),
                        "--mp3-output-dir", str(mp3_dir),
                        "--cache-dir", str(cache_dir),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout

            self.assertIn("OGG 内容同一", build())
            self.assertEqual(output.read_bytes(), original_bytes)
            self.assertEqual(output.stat().st_mtime_ns, original_mtime)
            mp3 = next(mp3_dir.glob("da3-win_*.mp3"))
            mp3_mtime = mp3.stat().st_mtime_ns

            def duration(path: Path) -> float:
                result = subprocess.run(
                    [
                        "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                return float(result.stdout)

            self.assertLess(duration(output), 0.2)
            self.assertGreater(duration(mp3), 0.3)

            # Existing MP3 state files move to the ignored shared cache.
            state = cache_dir / "mp3" / "da3-win.state"
            legacy_state = mp3_dir / ".da3-win.make-loop-mp3.state"
            state.replace(legacy_state)
            second = build()
            self.assertIn("OGG 変更なし", second)
            self.assertIn("[da3-win] 変更なし", second)
            self.assertTrue(state.is_file())
            self.assertFalse(legacy_state.exists())
            self.assertEqual(output.stat().st_mtime_ns, original_mtime)
            self.assertEqual(mp3.stat().st_mtime_ns, mp3_mtime)

            self._write_stereo_wav(source, frequency=880)
            third = build()
            self.assertIn("OGG 生成しました", third)
            self.assertIn("[da3-win] ループなし", third)
            self.assertNotEqual(output.read_bytes(), original_bytes)

            (cache_dir / "ogg" / "da3-win.wav.json").unlink()
            changed_mtime = output.stat().st_mtime_ns
            self.assertIn("OGG 内容同一", build())
            self.assertEqual(output.stat().st_mtime_ns, changed_mtime)

            mp3.unlink()
            fourth = build()
            self.assertIn("OGG 変更なし", fourth)
            self.assertIn("[da3-win] ループなし", fourth)
            self.assertTrue(mp3.is_file())

    @staticmethod
    def _write_stereo_wav(path: Path, frequency: int = 0) -> None:
        frames = 4_410
        values = [
            int(10000 * math.sin(2 * math.pi * frequency * index / 44100))
            for index in range(frames)
        ]
        samples = b"".join(
            struct.pack("<hh", value, value) for value in values
        )
        with wave.open(str(path), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(44_100)
            output.writeframes(samples)


if __name__ == "__main__":
    unittest.main()
