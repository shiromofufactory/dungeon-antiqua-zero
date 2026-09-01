#!/usr/bin/env python3
"""Convert development WAV sources into Pyxel-ready Ogg Vorbis files."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


SAMPLE_RATE = 22_050
CHANNELS = 1
VORBIS_QUALITY = 4


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description=(
            "tools/audio_wavのWAVを22.05kHz・モノラルのOGGへ変換します。"
        )
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=project_root / "tools" / "audio_wav",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "app" / "audio",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def find_wav_files(source_dir: Path) -> list[Path]:
    if not source_dir.is_dir():
        raise ValueError(f"WAVディレクトリが見つかりません: {source_dir}")

    wav_files = sorted(
        (
            path
            for path in source_dir.rglob("*")
            if path.is_file() and path.suffix.lower() == ".wav"
        ),
        key=lambda path: path.relative_to(source_dir).as_posix(),
    )
    if not wav_files:
        raise ValueError(f"WAVファイルがありません: {source_dir}")
    return wav_files


def output_path_for(source: Path, source_dir: Path, output_dir: Path) -> Path:
    relative = source.relative_to(source_dir)
    return output_dir / relative.with_suffix(".ogg")


def convert_wav(source: Path, output: Path, ffmpeg: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.tmp.ogg")
    temporary.unlink(missing_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        str(CHANNELS),
        "-ar",
        str(SAMPLE_RATE),
        "-c:a",
        "libvorbis",
        "-q:a",
        str(VORBIS_QUALITY),
        str(temporary),
    ]
    try:
        subprocess.run(command, check=True)
        temporary.replace(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def build_audio(source_dir: Path, output_dir: Path, ffmpeg: str) -> list[Path]:
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    outputs = []
    for source in find_wav_files(source_dir):
        output = output_path_for(source, source_dir, output_dir)
        convert_wav(source, output, ffmpeg)
        outputs.append(output)
    return outputs


def main() -> int:
    args = parse_args()
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        print(
            "ffmpegが見つかりません。ffmpegをインストールしてください。",
            file=sys.stderr,
        )
        return 1

    try:
        outputs = build_audio(args.source_dir, args.output_dir, ffmpeg)
        for output in outputs:
            print(f"生成しました: {output}")
        print(
            f"{len(outputs)}曲を{SAMPLE_RATE}Hz・モノラルOGGへ変換しました。"
        )
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
