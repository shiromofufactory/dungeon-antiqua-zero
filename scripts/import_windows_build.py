"""Receive and validate a Windows ZIP without changing Dropbox originals."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.desktop_build import (
    MODES, app_name, check_checksum, check_resources, default_dropbox_dir,
    publish_directory, validate_windows_zip, write_checksum,
)


def import_windows_build(root: Path, source: Path, mode: str) -> Path:
    check_resources(root / "app")
    subprocess.run(["node", str(root / "scripts/sync-content.mjs"), "--check"], cwd=root, check=True)
    output = root / "dist/windows" / mode
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".receive-{mode}-", dir=output.parent) as directory:
        stage = Path(directory)
        # Dropboxが同期中に変化しても、検査する対象と保存するZIPは同じコピーに固定する。
        snapshot = stage / source.name
        shutil.copyfile(source, snapshot)
        shutil.copyfile(source.with_suffix(".zip.sha256"), snapshot.with_suffix(".zip.sha256"))
        check_checksum(snapshot)
        validate_windows_zip(snapshot, mode, root / "app")
        release = stage / "release"
        release.mkdir()
        archive = release / f"{app_name(mode)}-win.zip"
        snapshot.rename(archive)
        write_checksum(archive)
        publish_directory(release, output)
    print(f"Windows版を確認・受け取りました: {archive.name} → {output}")
    return output / archive.name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DropboxのWindows ZIPを検証してdist/windows/<mode>へ受け取ります。")
    parser.add_argument("--mode", choices=MODES, default="normal")
    parser.add_argument("--dropbox-dir", type=Path, default=default_dropbox_dir())
    parser.add_argument("--source", type=Path, help="受け取るZIPを明示指定（GitHub Actions等からの取得にも利用可能）")
    args = parser.parse_args(argv)
    try:
        source = args.source
        if source is None:
            inbox = args.dropbox_dir.expanduser() / args.mode
            candidates = sorted(inbox.glob(f"{app_name(args.mode)}-win-*.zip"), key=lambda p: (p.stat().st_mtime_ns, p.name))
            if not candidates:
                raise ValueError(f"Windows版の受け渡しZIPがありません: {inbox}")
            source = candidates[-1]
        import_windows_build(PROJECT_ROOT, source.expanduser().resolve(), args.mode)
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile, KeyError) as error:
        print(f"Windows版の受け取りに失敗しました: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
