from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from scripts import build_windows as builder
from scripts import import_windows_build as receiver
from scripts.desktop_build import (
    BUILD_INFO, MODES, PYXEL_STARTUP, REQUIRED_RESOURCES, STARTUP, app_name, check_checksum,
    source_manifest, validate_windows_zip, write_checksum,
    publish_directory,
)


class WindowsBuildTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory(prefix="windows build test ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = self.root / "app"
        for name in REQUIRED_RESOURCES:
            path = self.app / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("resource\n", encoding="utf-8", newline="\n")
        (self.app / "main.py").write_text("def main(argv):\n    return 0\n")
        (self.root / "icons").mkdir()
        (self.root / "icons/icon.ico").write_bytes(b"icon")
        self.commands: list[list[str]] = []
        self.failure: str | None = None
        self.inbox = self.root / "Dropbox"

    def fake_run(self, command: list[str], cwd: Path) -> None:
        self.commands.append(command)
        if command[0] == "node":
            if self.failure == "sync":
                raise subprocess.CalledProcessError(1, command)
        elif "package" in command:
            app = cwd / "app"
            with zipfile.ZipFile(cwd / "app.pyxapp", "w") as package:
                package.writestr(f"app/{PYXEL_STARTUP}", STARTUP)
                for path in app.rglob("*"):
                    if path.is_file():
                        package.write(path, path.relative_to(cwd).as_posix())
        elif "PyInstaller" in command:
            if self.failure == "pyinstaller":
                raise subprocess.CalledProcessError(1, command)
            if self.failure == "missing-exe":
                return
            name = command[command.index("--name") + 1]
            bundle = cwd / "bundle" / name
            (bundle / "_internal").mkdir(parents=True)
            (bundle / f"{name}.exe").write_bytes(b"MZ" + b"test executable")
            package = cwd / f"{name}.pyxapp"
            (bundle / "_internal" / package.name).write_bytes(package.read_bytes())
            (bundle / "_internal/library.dll").write_bytes(b"library")
            self.assertEqual(command[command.index("--icon") + 1], str(self.root / "icons/icon.ico"))
        elif "sign" in command:
            executable = Path(command[-1])
            executable.write_bytes(executable.read_bytes() + b"signed")
            if self.failure == "sign":
                raise subprocess.CalledProcessError(1, command)
        elif "verify" in command and self.failure == "verify":
            raise subprocess.CalledProcessError(1, command)

    def build(self, mode: str = "demo", *, sign: bool = True) -> Path:
        with patch.object(builder, "run", side_effect=self.fake_run):
            return builder.build_windows(self.root, mode, sign=sign, dropbox_dir=self.inbox)

    def receive(self, source: Path, mode: str = "demo") -> Path:
        with patch.object(receiver.subprocess, "run"):
            return receiver.import_windows_build(self.root, source, mode)

    def test_all_modes_build_signed_zip_and_receive_without_loose_pyxapp(self) -> None:
        for mode in MODES:
            with self.subTest(mode=mode):
                archive = self.build(mode)
                check_checksum(archive)
                name = app_name(mode)
                with zipfile.ZipFile(archive) as release:
                    self.assertEqual(set(release.namelist()), {
                        f"{name}.exe", f"_internal/{name}.pyxapp", "_internal/library.dll",
                    })
                    self.assertTrue(release.read(f"{name}.exe").endswith(b"signed"))
                    with zipfile.ZipFile(BytesIO(release.read(f"_internal/{name}.pyxapp"))) as package:
                        info = json.loads(package.read(f"app/{BUILD_INFO}"))
                        self.assertEqual(info["launch_mode"], mode)
                        self.assertEqual(info["source_files"], source_manifest(self.app))
                exported, = (self.inbox / mode).glob("*.zip")
                check_checksum(exported)
                self.assertEqual(exported.read_bytes(), archive.read_bytes())
                received = self.receive(exported, mode)
                self.assertEqual(received.read_bytes(), exported.read_bytes())
                self.assertTrue(exported.exists())
                self.assertEqual(
                    {p.name for p in received.parent.iterdir()},
                    {f"{name}-win.zip", f"{name}-win.zip.sha256"},
                )
                self.assertFalse((self.app / STARTUP).exists())
                self.assertFalse((self.app / BUILD_INFO).exists())
                self.assertEqual(list((self.root / "dist/windows").glob(".*-*")), [])
        signs = [c for c in self.commands if "sign" in c]
        verifies = [c for c in self.commands if "verify" in c]
        self.assertEqual(len(signs), len(MODES))
        self.assertEqual(len(verifies), len(MODES))

    def test_unsigned_build_and_no_dropbox(self) -> None:
        with patch.object(builder, "run", side_effect=self.fake_run):
            archive = builder.build_windows(self.root, "normal", sign=False, dropbox_dir=None)
        self.assertTrue(archive.exists())
        self.assertFalse(any("sign" in c for c in self.commands))
        self.assertFalse(self.inbox.exists())

    def test_failed_build_preserves_previous_release_and_does_not_export(self) -> None:
        output = self.root / "dist/windows/demo"
        output.mkdir(parents=True)
        previous = output / "previous.zip"
        previous.write_bytes(b"previous")
        for failure in ("sync", "pyinstaller", "missing-exe", "sign", "verify"):
            with self.subTest(failure=failure):
                self.failure = failure
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    self.build()
                self.assertEqual(list(output.iterdir()), [previous])
                self.assertEqual(previous.read_bytes(), b"previous")
                self.assertFalse(self.inbox.exists())
                self.assertEqual(list(output.parent.glob(".build-*")), [])

    def test_unique_dropbox_names_preserve_previous_transfers(self) -> None:
        self.build()
        first, = (self.inbox / "demo").glob("*.zip")
        self.build()
        archives = list((self.inbox / "demo").glob("*.zip"))
        self.assertEqual(len(archives), 2)
        self.assertIn(first, archives)
        for archive in archives:
            check_checksum(archive)

    def test_receive_rejects_incomplete_sync_and_preserves_previous_release(self) -> None:
        self.build()
        source, = (self.inbox / "demo").glob("*.zip")
        output = self.root / "dist/windows/demo"
        previous = (output / "dungeon-antiqua-zero-demo-win.zip").read_bytes()
        checksum = source.with_suffix(".zip.sha256")
        saved = checksum.read_bytes()
        checksum.unlink()
        with self.assertRaises(OSError):
            self.receive(source)
        checksum.write_bytes(saved)
        source.write_bytes(source.read_bytes() + b"incomplete sync")
        with self.assertRaisesRegex(ValueError, "チェックサム"):
            self.receive(source)
        self.assertEqual((output / "dungeon-antiqua-zero-demo-win.zip").read_bytes(), previous)
        self.assertEqual(list(output.parent.glob(".receive-*")), [])

    def test_receive_rejects_wrong_mode_or_changed_source_and_resources(self) -> None:
        self.build()
        source, = (self.inbox / "demo").glob("*.zip")
        with self.assertRaises((KeyError, ValueError)):
            self.receive(source, "exhibition")
        for name in ("main.py", "data/texts.json", "images/graphics.bin", "audio/catalog.json"):
            with self.subTest(name=name):
                path = self.app / name
                saved = path.read_bytes()
                path.write_bytes(saved + b"changed")
                with self.assertRaisesRegex(ValueError, "現在のapp"):
                    self.receive(source)
                path.write_bytes(saved)

    def test_receive_accepts_windows_crlf_but_rejects_changed_package_content(self) -> None:
        (self.app / "main.py").write_bytes(b"def main(argv):\r\n    return 0\r\n")
        self.build()
        source, = (self.inbox / "demo").glob("*.zip")
        (self.app / "main.py").write_bytes(b"def main(argv):\n    return 0\n")
        self.receive(source)
        with zipfile.ZipFile(source) as release:
            files = {p: release.read(p) for p in release.namelist()}
        package_name = "_internal/dungeon-antiqua-zero-demo.pyxapp"
        with zipfile.ZipFile(BytesIO(files[package_name])) as package:
            package_files = {p: package.read(p) for p in package.namelist()}
        package_files["app/main.py"] += b"changed"
        result = BytesIO()
        with zipfile.ZipFile(result, "w") as package:
            for name, data in package_files.items():
                package.writestr(name, data)
        files[package_name] = result.getvalue()
        with zipfile.ZipFile(source, "w") as release:
            for name, data in files.items():
                release.writestr(name, data)
        write_checksum(source)
        with self.assertRaisesRegex(ValueError, "ビルド記録"):
            self.receive(source)

    def test_zip_rejects_extra_loose_pyxapp_or_unsafe_paths(self) -> None:
        self.build()
        source, = (self.inbox / "demo").glob("*.zip")
        for name in ("game.pyxapp", "_internal/../../unexpected", "_internal\\library.dll"):
            with self.subTest(name=name):
                modified = self.root / "modified.zip"
                modified.write_bytes(source.read_bytes())
                with zipfile.ZipFile(modified, "a") as release:
                    release.writestr(name, b"extra")
                with self.assertRaisesRegex(ValueError, "構成"):
                    validate_windows_zip(modified, "demo", self.app)

    def test_platform_guard_and_help_on_mac(self) -> None:
        with patch.object(builder.sys, "platform", "darwin"):
            self.assertEqual(builder.main(["--mode", "demo"]), 1)
        with self.assertRaises(SystemExit) as error:
            builder.main(["--help"])
        self.assertEqual(error.exception.code, 0)

    def test_actual_pyxel_package_is_compatible_with_receiver(self) -> None:
        from scripts.desktop_build import stage_app
        stage = self.root / "actual pyxel"
        stage.mkdir()
        stage_app(self.app, stage / "app", "beta")
        subprocess.run([
            sys.executable, "-B", "-c", "from pyxel.cli import cli; cli()",
            "package", str(stage / "app"), str(stage / "app" / STARTUP),
        ], cwd=stage, check=True, capture_output=True)
        name = app_name("beta")
        archive = stage / "windows.zip"
        with zipfile.ZipFile(archive, "w") as release:
            release.writestr(f"{name}.exe", b"MZtest")
            release.write(stage / "app.pyxapp", f"_internal/{name}.pyxapp")
        validate_windows_zip(archive, "beta", self.app)

    def test_publication_failure_restores_previous_directory(self) -> None:
        stage = self.root / "stage"
        release = stage / "release"
        release.mkdir(parents=True)
        (release / "new.zip").write_bytes(b"new")
        output = self.root / "output"
        output.mkdir()
        (output / "previous.zip").write_bytes(b"previous")
        original_rename = Path.rename

        def failing_rename(path: Path, target: Path) -> Path:
            if path == release:
                raise OSError("publication failure")
            return original_rename(path, target)

        with patch.object(Path, "rename", failing_rename):
            with self.assertRaisesRegex(OSError, "publication"):
                publish_directory(release, output)
        self.assertEqual((output / "previous.zip").read_bytes(), b"previous")
        self.assertFalse((stage / "previous").exists())

    def test_dropbox_copy_failure_preserves_local_and_previous_transfers(self) -> None:
        archive = self.build()
        saved = archive.read_bytes()
        previous = set((self.inbox / "demo").iterdir())
        with patch.object(builder.shutil, "copyfile", side_effect=OSError("copy failure")):
            with self.assertRaisesRegex(OSError, "copy failure"):
                builder.export_to_dropbox(archive, self.inbox / "demo")
        self.assertEqual(archive.read_bytes(), saved)
        self.assertEqual(set((self.inbox / "demo").iterdir()), previous)


if __name__ == "__main__":
    unittest.main()
