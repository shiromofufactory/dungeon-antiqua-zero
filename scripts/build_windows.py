"""Build and sign a Windows bundle, then hand its ZIP to Dropbox."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import uuid
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.desktop_build import (
    MODES, STARTUP, app_name, check_resources, default_dropbox_dir, file_digest,
    publish_directory, stage_app, validate_windows_zip, write_checksum,
)


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def prepare_resources(root: Path, *, allow_palette_mismatch: bool = False) -> None:
    """共有コンテンツの同期と、Git管理外の実行時リソースの生成を行う。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(root), env.get("PYTHONPATH")]))
    if not any((root / "content").iterdir()):
        raise ValueError("contentが空です。先に git submodule update --init を実行してください。")
    images = [sys.executable, "-B", str(root / "scripts/build-images.py")]
    if allow_palette_mismatch:
        images.append("--allow-palette-mismatch")
    steps = [
        ("共有データの同期", ["node", str(root / "scripts/sync-content.mjs")]),
        ("画像の生成", images),
        ("マップの生成", [sys.executable, "-B", str(root / "scripts/compile-maps.py")]),
        ("イベントの生成", [sys.executable, "-B", str(root / "scripts/compile-events.py")]),
        ("呪文エフェクトの生成", [sys.executable, "-B", str(root / "scripts/compile-spell-effects.py")]),
        ("攻撃ポーズの生成", [sys.executable, "-B", str(root / "scripts/compile-attack-poses.py")]),
    ]
    for label, command in steps:
        print(f"== {label}", flush=True)
        subprocess.run(command, cwd=root, env=env, check=True)


def export_to_dropbox(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = destination / f"{archive.stem}-{timestamp}-{file_digest(archive)[:12]}.zip"
    # 同期中のZIPを配布物として拾わないよう、完成した1ファイルだけを公開する。
    temporary = destination / f".{uuid.uuid4().hex}.partial"
    try:
        shutil.copyfile(archive, temporary)
        if file_digest(temporary) != file_digest(archive):
            raise ValueError("Dropboxへのコピーが一致しません。")
        temporary.rename(target)
        write_checksum(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def build_windows(root: Path, mode: str, *, sign: bool, dropbox_dir: Path | None) -> Path:
    name = app_name(mode)
    check_resources(root / "app")
    run(["node", str(root / "scripts/sync-content.mjs"), "--check"], root)
    output = root / "dist/windows" / mode
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".build-{mode}-", dir=output.parent) as directory:
        stage = Path(directory)
        staged_app = stage / "app"
        stage_app(root / "app", staged_app, mode)
        run([
            sys.executable, "-B", "-c", "from pyxel.cli import cli; cli()",
            "package", str(staged_app), str(staged_app / STARTUP),
        ], stage)
        package = stage / f"{name}.pyxapp"
        (stage / "app.pyxapp").rename(package)

        # Pyxelのapp2exeと同じ起動口・依存解析を使い、アイコンと終了コードを明示する。
        # 同じPythonでPyInstallerを呼ぶため、PATH上の別環境との混在を避けられる。
        from pyxel.utils import list_imported_modules

        launcher = stage / f"{name}.py"
        launcher.write_text(
            "import os\nfrom pyxel.cli import play_pyxel_app\n"
            f"play_pyxel_app(os.path.join(os.path.dirname(__file__), '{name}.pyxapp'))\n",
            encoding="utf-8",
        )
        command = [
            sys.executable, "-m", "PyInstaller", "--windowed", "--onedir", "--noconfirm",
            "--name", name, "--distpath", str(stage / "bundle"),
            "--workpath", str(stage / "work"), "--specpath", str(stage),
            "--add-data", f"{package}{os.pathsep}.",
        ]
        icon = root / "icons/icon.ico"
        if icon.is_file():
            command.extend(["--icon", str(icon)])
        for module in list_imported_modules(str(staged_app / STARTUP))["system"]:
            command.extend(["--hidden-import", module])
        command.append(str(launcher))
        run(command, stage)
        bundle = stage / "bundle" / name
        executable = bundle / f"{name}.exe"
        if not executable.is_file() or not (bundle / "_internal" / package.name).is_file():
            raise ValueError("Windows実行ファイルまたは_internalが生成されませんでした。")
        if sign:
            signtool = os.environ.get("SIGNTOOL", "signtool")
            run([
                signtool, "sign", "/a", "/fd", "SHA256", "/tr",
                "http://timestamp.digicert.com", "/td", "SHA256", str(executable),
            ], stage)
            run([signtool, "verify", "/pa", str(executable)], stage)

        release = stage / "release"
        release.mkdir()
        archive = release / f"{name}-win.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            for path in sorted(bundle.rglob("*")):
                if path.is_file():
                    zipped.write(path, path.relative_to(bundle).as_posix())
        validate_windows_zip(archive, mode, root / "app")
        write_checksum(archive)
        # ローカルで起動確認できるよう、ZIPと同じexe・_internalも保持する。
        for path in bundle.iterdir():
            shutil.move(str(path), release / path.name)
        publish_directory(release, output)
    archive = output / f"{name}-win.zip"
    print(f"生成完了: {output}")
    if dropbox_dir is not None:
        target = export_to_dropbox(archive, dropbox_dir / mode)
        print(f"Dropbox受け渡し用ZIP: {target}")
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Windows版のビルド・署名・ZIP化とDropboxへの受け渡しを行います。")
    parser.add_argument("--mode", choices=MODES, default="normal")
    parser.add_argument("--no-sign", action="store_true", help="ローカル確認用に署名を省略")
    parser.add_argument("--no-dropbox", action="store_true", help="ローカル生成のみ")
    parser.add_argument("--dropbox-dir", type=Path, default=default_dropbox_dir(), help="受け渡し先の基部ディレクトリ")
    parser.add_argument("--skip-prepare", action="store_true", help="リソースの同期・生成を行わず、現在のappをそのままビルド")
    parser.add_argument("--allow-palette-mismatch", action="store_true", help="画像生成でパレット外の色を最近傍色へ変換（確認用）")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("Windows版はWindows上でビルドしてください。", file=sys.stderr)
        return 1
    try:
        if sys.version_info < (3, 11):
            raise ValueError("Python 3.11以上が必要です。")
        for module in ("pyxel", "PyInstaller"):
            if importlib.util.find_spec(module) is None:
                raise ValueError(f"現在のPython環境に{module}をインストールしてください。")
        if shutil.which("node") is None:
            raise ValueError("Node.jsがPATHにありません。")
        if not args.no_sign and shutil.which(os.environ.get("SIGNTOOL", "signtool")) is None:
            raise ValueError("signtoolがPATHにありません。SIGNTOOLへパスを指定するか、確認用に--no-signを指定してください。")
        if not args.skip_prepare:
            prepare_resources(PROJECT_ROOT, allow_palette_mismatch=args.allow_palette_mismatch)
        build_windows(
            PROJECT_ROOT, args.mode, sign=not args.no_sign,
            dropbox_dir=None if args.no_dropbox else args.dropbox_dir.expanduser().resolve(),
        )
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile, KeyError) as error:
        print(f"Windowsビルドに失敗しました: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
