from __future__ import annotations

import json
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

    @staticmethod
    def _write_stereo_wav(path: Path) -> None:
        frames = 4_410
        silence = struct.pack("<hh", 0, 0) * frames
        with wave.open(str(path), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(44_100)
            output.writeframes(silence)


if __name__ == "__main__":
    unittest.main()
