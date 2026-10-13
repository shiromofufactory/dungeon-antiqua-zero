"""Receive, optionally extract, and clean up a validated Windows transfer."""

from __future__ import annotations

import argparse
import errno
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
    file_digest, publish_directory, validate_windows_zip, write_checksum,
)


def cleanup_transfer(source: Path, archive: Path, checksum_bytes: bytes) -> None:
    checksum = source.with_suffix(".zip.sha256")
    # DA2のcmpと同じく、受け取り中に更新された原本を削除しない。
    if file_digest(source) != file_digest(archive) or checksum.read_bytes() != checksum_bytes:
        raise ValueError(
            "受け取り中にDropboxの原本が更新されました。原本は削除しません。"
            f"受け取り済みZIPは保持しています: {archive}"
        )
    source.unlink()
    checksum.unlink()
    print(f"受け取り済みファイルを削除しました: {source.name}, {checksum.name}")
    # モード別の空ディレクトリだけを取り除く。他のファイルや共有tmpは触らない。
    if source.parent.name in MODES and source.parent.parent.name == "dungeon-antiqua-zero":
        try:
            source.parent.rmdir()
        except OSError as error:
            if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                raise


def import_windows_build(
    root: Path, source: Path, mode: str, *, extract: bool = False,
    cleanup: bool = False, require_current_source: bool = True,
) -> Path:
    source = source.resolve()
    output = root / "dist/windows" / mode
    # 原本と保存先が同じ場合に、置き換え後の唯一の配布物を削除しない。
    if source.is_relative_to(output.resolve()):
        raise ValueError("保存先dist/windows内のZIPは受け渡し原本として指定できません。")
    check_resources(root / "app")
    subprocess.run(["node", str(root / "scripts/sync-content.mjs"), "--check"], cwd=root, check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".receive-{mode}-", dir=output.parent) as directory:
        stage = Path(directory)
        # Dropboxが同期中に変化しても、検査する対象と保存するZIPは同じコピーに固定する。
        snapshot = stage / source.name
        shutil.copyfile(source, snapshot)
        shutil.copyfile(source.with_suffix(".zip.sha256"), snapshot.with_suffix(".zip.sha256"))
        checksum_bytes = snapshot.with_suffix(".zip.sha256").read_bytes()
        check_checksum(snapshot)
        differences = validate_windows_zip(
            snapshot, mode, root / "app", require_current_source=require_current_source,
        )
        if differences:
            print("Windows版と現在のappに差分があります。Windows版の内容をそのまま保管します:")
            for name in differences:
                print(f"- {name}")
        release = stage / "release"
        release.mkdir()
        archive = release / f"{app_name(mode)}-win.zip"
        snapshot.rename(archive)
        write_checksum(archive)
        if extract:
            # 構成・パス・破損の検証を済ませたZIPだけを、公開前の一時ディレクトリへ展開する。
            with zipfile.ZipFile(archive) as release_zip:
                release_zip.extractall(release)
        publish_directory(release, output)
        archive = output / archive.name
        print(f"Windows版を確認・受け取りました: {archive.name} → {output}")
        if cleanup:
            cleanup_transfer(source, archive, checksum_bytes)
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DropboxのWindows ZIPを検証してdist/windows/<mode>へ受け取ります。")
    parser.add_argument("--mode", choices=MODES, default="normal")
    parser.add_argument("--dropbox-dir", type=Path, default=default_dropbox_dir())
    parser.add_argument("--source", type=Path, help="受け取るZIPを明示指定（GitHub Actions等からの取得にも利用可能）")
    parser.add_argument("--extract", action="store_true", help="保存先へexeと_internalも展開")
    parser.add_argument("--cleanup", action="store_true", help="保存完了後、受け取ったZIPとチェックサムを原本から削除")
    parser.add_argument("--allow-source-differences", action="store_true", help="現在のappとの違いを表示して保管（パッケージ自身の検証は維持）")
    args = parser.parse_args(argv)
    try:
        source = args.source
        if source is None:
            inbox = args.dropbox_dir.expanduser() / args.mode
            candidates = sorted(inbox.glob(f"{app_name(args.mode)}-win-*.zip"), key=lambda p: (p.stat().st_mtime_ns, p.name))
            if not candidates:
                raise ValueError(f"Windows版の受け渡しZIPがありません: {inbox}")
            source = candidates[-1]
        source = source.expanduser().resolve()
        import_windows_build(
            PROJECT_ROOT, source, args.mode, extract=args.extract, cleanup=args.cleanup,
            require_current_source=not args.allow_source_differences,
        )
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile, KeyError) as error:
        print(f"Windows版の受け取りに失敗しました: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
