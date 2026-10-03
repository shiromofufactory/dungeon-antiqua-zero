#!/usr/bin/env python3
"""Build game OGG files and listening MP3 files from development WAV sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


SAMPLE_RATE = 22_050
CHANNELS = 1
VORBIS_QUALITY = 4
OGG_CACHE_VERSION = 1


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="tools/audio_wavのWAVからゲーム用OGGと視聴用MP3を生成します。"
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
    parser.add_argument(
        "--mp3-output-dir",
        type=Path,
        default=project_root / "output" / "mp3",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=project_root / "output" / ".audio-cache",
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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ogg_fingerprint(source: Path) -> str:
    settings = f"ogg:{OGG_CACHE_VERSION}:{SAMPLE_RATE}:{CHANNELS}:{VORBIS_QUALITY}"
    digest = hashlib.sha256()
    digest.update(settings.encode("ascii"))
    digest.update(b"\0")
    digest.update(sha256_file(source).encode("ascii"))
    return digest.hexdigest()


def read_state(path: Path) -> dict[str, str]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def write_state(path: Path, fingerprint: str, output_hash: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as state_file:
            json.dump(
                {"fingerprint": fingerprint, "output_sha256": output_hash},
                state_file,
            )
            state_file.write("\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def ogg_audio_matches(existing: Path, generated: Path, ffmpeg: str, ffprobe: str) -> bool:
    # Old OGG files can have a different container serial even when their audio is identical.
    try:
        probe = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,sample_rate,channels",
                "-of",
                "json",
                str(existing),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        streams = json.loads(probe.stdout).get("streams", [])
        if not streams or streams[0] != {
            "codec_name": "vorbis",
            "sample_rate": str(SAMPLE_RATE),
            "channels": CHANNELS,
        }:
            return False

        def audio_hash(path: Path) -> str:
            result = subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-i",
                    str(path),
                    "-map",
                    "0:a:0",
                    "-c:a",
                    "pcm_s16le",
                    "-f",
                    "hash",
                    "-hash",
                    "SHA256",
                    "-",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()

        return audio_hash(existing) == audio_hash(generated)
    except (OSError, ValueError, subprocess.CalledProcessError):
        return False


def convert_wav(source: Path, output: Path, ffmpeg: str, ffprobe: str) -> tuple[bool, str]:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.stem}.", suffix=".ogg", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
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
        "-fflags",
        "+bitexact",
        str(temporary),
    ]
    try:
        subprocess.run(command, check=True)
        output_hash = sha256_file(temporary)
        if output.is_file():
            existing_hash = sha256_file(output)
            if existing_hash == output_hash or ogg_audio_matches(
                output, temporary, ffmpeg, ffprobe
            ):
                return False, existing_hash
        temporary.replace(output)
        return True, output_hash
    finally:
        temporary.unlink(missing_ok=True)


def build_audio(
    source_dir: Path, output_dir: Path, cache_dir: Path, ffmpeg: str, ffprobe: str
) -> list[tuple[Path, str]]:
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    cache_dir = cache_dir.resolve()
    results = []
    for source in find_wav_files(source_dir):
        relative = source.relative_to(source_dir)
        output = output_path_for(source, source_dir, output_dir)
        state_path = cache_dir / "ogg" / f"{relative.as_posix()}.json"
        fingerprint = ogg_fingerprint(source)
        state = read_state(state_path)
        if (
            state.get("fingerprint") == fingerprint
            and output.is_file()
            and state.get("output_sha256") == sha256_file(output)
        ):
            results.append((output, "skip"))
            continue

        changed, output_hash = convert_wav(source, output, ffmpeg, ffprobe)
        write_state(state_path, fingerprint, output_hash)
        results.append((output, "updated" if changed else "same"))
    return results


def main() -> int:
    args = parse_args()
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg is None or ffprobe is None:
        print("ffmpegとffprobeが必要です。", file=sys.stderr)
        return 1

    try:
        results = build_audio(
            args.source_dir, args.output_dir, args.cache_dir, ffmpeg, ffprobe
        )
        for output, status in results:
            label = {"skip": "変更なし", "same": "内容同一", "updated": "生成しました"}[status]
            print(f"OGG {label}: {output}", flush=True)

        project_root = Path(__file__).resolve().parent.parent
        environment = os.environ.copy()
        environment.update(
            AUDIO_SOURCE_DIR=str(args.source_dir.resolve()),
            AUDIO_MP3_DIR=str(args.mp3_output_dir.resolve()),
            AUDIO_CACHE_DIR=str(args.cache_dir.resolve()),
        )
        subprocess.run(
            ["bash", str(project_root / "tools" / "make-loop-mp3.sh")],
            check=True,
            env=environment,
        )
        print(f"OGG {len(results)}曲、MP3の変換を確認しました。")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
