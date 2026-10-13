"""Shared desktop staging, bundle validation, and atomic publication."""

from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil
import zipfile


MODES = ("normal", "exhibition", "demo", "beta")
BUILD_INFO = "_desktop_build.json"
STARTUP = "_desktop_main.py"
PYXEL_STARTUP = ".pyxapp_startup_script"
REQUIRED_RESOURCES = (
    "main.py", "assets.pyxres", "assets.pyxpal",
    "data/characters.json", "data/items.json", "data/monsters.json",
    "data/shops.json", "data/skills.json", "data/spells.json", "data/texts.json",
    "images/manifest.json", "images/graphics.bin", "maps/worldmap.json",
    "events/events.json", "events/messages.json", "effects/spells.json",
    "effects/attack_poses.json", "audio/catalog.json",
)
TEXT_SUFFIXES = {".py", ".json", ".bdf", ".txt", ".md"}


def app_name(mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"未対応のモードです: {mode}")
    return "dungeon-antiqua-zero" + ("" if mode == "normal" else f"-{mode}")


def bootstrap(mode: str) -> str:
    app_name(mode)
    return (
        '# title: Dungeon Antiqua ZERO\n'
        '"""Start the packaged game in the mode selected at build time."""\n\n'
        'from main import main\n\n'
        'if __name__ == "__main__":\n'
        f'    raise SystemExit(main(["--mode", "{mode}"]))\n'
    )


def resource_digest(name: str, data: bytes) -> str:
    # gitのautocrlfによるWindows/Mac間の改行差だけは同一ソースとして扱う。
    if Path(name).suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return sha256(data).hexdigest()


def is_packaged_source(name: str) -> bool:
    path = Path(name)
    return (
        not any(part.startswith(".") or "__pycache__" in part for part in path.parts)
        and path.name not in (BUILD_INFO, STARTUP)
        and path.suffix.lower() not in (".gif", ".zip", ".pyc", ".pyo")
    )


def source_manifest(app_root: Path) -> dict[str, str]:
    return {
        path.relative_to(app_root).as_posix(): resource_digest(path.name, path.read_bytes())
        for path in sorted(app_root.rglob("*"))
        if path.is_file() and is_packaged_source(path.relative_to(app_root).as_posix())
    }


def check_resources(app_root: Path) -> None:
    for name in REQUIRED_RESOURCES:
        path = app_root / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"配布用リソースがありません: {path}（docs/desktop-build.md を参照）")


def write_startup(app_root: Path, mode: str) -> None:
    (app_root / STARTUP).write_text(bootstrap(mode), encoding="utf-8", newline="\n")
    info = {"format_version": 1, "launch_mode": mode, "source_files": source_manifest(app_root)}
    (app_root / BUILD_INFO).write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def stage_app(source: Path, target: Path, mode: str) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", "*.pyo", ".DS_Store", STARTUP, BUILD_INFO,
    ))
    write_startup(target, mode)


def file_digest(path: Path) -> str:
    with path.open("rb") as source:
        digest = sha256()
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_checksum(archive: Path) -> Path:
    checksum = archive.with_suffix(".zip.sha256")
    checksum.write_text(f"{file_digest(archive)}  {archive.name}\n", encoding="ascii")
    return checksum


def check_checksum(archive: Path) -> None:
    fields = archive.with_suffix(".zip.sha256").read_text(encoding="ascii").split()
    if fields != [file_digest(archive), archive.name]:
        raise ValueError(f"チェックサムが一致しません。Dropboxの同期完了を確認してください: {archive}")


def validate_windows_zip(archive: Path, mode: str, app_root: Path) -> None:
    name = app_name(mode)
    with zipfile.ZipFile(archive) as release:
        paths = release.namelist()
        if len({p.casefold() for p in paths}) != len(paths):
            raise ValueError("Windows ZIPに重複したファイルがあります。")
        if any(
            "\\" in p or ".." in p.split("/")
            or not (p == f"{name}.exe" or p.startswith("_internal/"))
            for p in paths
        ):
            raise ValueError("Windows ZIPの構成が不正です。exeと_internalだけを含めてください。")
        damaged = release.testzip()
        if damaged:
            raise ValueError(f"Windows ZIPが破損しています: {damaged}")
        with release.open(f"{name}.exe") as executable:
            if executable.read(2) != b"MZ":
                raise ValueError("Windows実行ファイルのヘッダーが不正です。")
        with zipfile.ZipFile(BytesIO(release.read(f"_internal/{name}.pyxapp"))) as package:
            damaged = package.testzip()
            if damaged:
                raise ValueError(f"ゲームパッケージが破損しています: {damaged}")
            if len(set(package.namelist())) != len(package.namelist()):
                # Pyxelは起動設定を2回登録する版があるため、その重複だけを許可する。
                duplicates = {p for p in package.namelist() if package.namelist().count(p) > 1}
                if duplicates != {f"app/{PYXEL_STARTUP}"}:
                    raise ValueError("ゲームパッケージに重複したファイルがあります。")
            info = json.loads(package.read(f"app/{BUILD_INFO}"))
            if not isinstance(info, dict) or info.get("format_version") != 1 or info.get("launch_mode") != mode:
                raise ValueError("Windows版のビルドモードが指定モードと一致しません。")
            if package.read(f"app/{PYXEL_STARTUP}").decode() != STARTUP:
                raise ValueError("Windows版の起動設定が不正です。")
            if package.read(f"app/{STARTUP}").decode() != bootstrap(mode):
                raise ValueError("Windows版の起動モードが不正です。")
            actual = {
                p.removeprefix("app/"): resource_digest(p, package.read(p))
                for p in package.namelist()
                if p.startswith("app/") and not p.endswith("/")
                and is_packaged_source(p.removeprefix("app/"))
            }
            if not actual or actual != info.get("source_files"):
                raise ValueError("Windows版のゲームデータとビルド記録が一致しません。")
            expected = source_manifest(app_root)
            if actual != expected:
                differences = sorted(k for k in actual.keys() | expected.keys() if actual.get(k) != expected.get(k))
                raise ValueError("Windows版と現在のappが一致しません:\n- " + "\n- ".join(differences[:20]))


def publish_directory(staged: Path, output: Path) -> None:
    previous = staged.parent / "previous"
    if output.exists():
        output.rename(previous)
    try:
        staged.rename(output)
    except BaseException:
        if previous.exists():
            previous.rename(output)
        raise


def default_dropbox_dir() -> Path:
    import os
    return Path(os.environ.get("DA0_DROPBOX_DIR", Path.home() / "Dropbox/public/tmp/dungeon-antiqua-zero"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="配布物の一時コピーへ起動モードとビルド記録を埋め込みます。")
    parser.add_argument("--app-root", type=Path, required=True)
    parser.add_argument("--mode", choices=MODES, required=True)
    arguments = parser.parse_args()
    write_startup(arguments.app_root, arguments.mode)
