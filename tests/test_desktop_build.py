from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# PyInstallerを走らせずに、シェルの処理と配布物の起動口を端から端まで確認する。
FAKE_TOOL = '''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
import zipfile

tool = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["BUILD_TEST_LOG"], "a") as log:
    log.write(json.dumps([tool, args]) + "\\n")
if tool == "uname":
    print("Darwin")
elif tool == "node":
    if os.environ.get("BUILD_TEST_FAIL") == "sync":
        sys.exit(1)
elif tool == "pyxel":
    if args[0] == "package":
        with zipfile.ZipFile("app.pyxapp", "w") as package:
            package.writestr("app/.pyxapp_startup_script", Path(args[2]).name)
            for source in Path(args[1]).rglob("*"):
                if source.is_file():
                    package.write(source, source.as_posix())
    elif os.environ.get("BUILD_TEST_FAIL") != "app2exe":
        name = Path(args[1]).stem
        app = Path(name + ".app") / "Contents"
        (app / "MacOS").mkdir(parents=True)
        (app / "Resources").mkdir()
        binary = app / "MacOS" / name
        binary.write_text("#!/bin/sh\\nexit 0\\n")
        binary.chmod(0o755)
        (app / "Resources" / Path(args[1]).name).write_bytes(Path(args[1]).read_bytes())
elif tool == "codesign":
    if "--sign" in args:
        assert (Path(args[-1]) / "Contents/Resources/icon-windowed.icns").read_bytes() == b"icon"
    if os.environ.get("BUILD_TEST_FAIL") == "codesign":
        sys.exit(1)
elif tool == "ditto":
    if os.environ.get("BUILD_TEST_FAIL") == "ditto":
        sys.exit(1)
    root = Path(args[-2])
    with zipfile.ZipFile(args[-1], "w") as archive:
        for source in root.rglob("*"):
            if source.is_file():
                archive.write(source, source.relative_to(root))
'''


class DesktopBuildTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory(prefix="desktop build test ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copyfile(PROJECT_ROOT / "build.sh", self.root / "build.sh")
        (self.root / "scripts").mkdir()
        shutil.copyfile(PROJECT_ROOT / "scripts/desktop_build.py", self.root / "scripts/desktop_build.py")
        self.app = self.root / "app"
        for resource in (
            "assets.pyxres", "assets.pyxpal", "data/characters.json",
            "data/items.json", "data/monsters.json", "data/shops.json",
            "data/skills.json", "data/spells.json", "data/texts.json",
            "images/manifest.json", "images/graphics.bin", "maps/worldmap.json",
            "events/events.json", "events/messages.json", "effects/spells.json",
            "effects/attack_poses.json", "audio/catalog.json", "__pycache__/main.pyc",
            ".DS_Store",
        ):
            path = self.app / resource
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("resource")
        # 実際の起動引数がPyxel側のargvから混入しないことも検証する。
        (self.app / "main.py").write_text(
            "import json\ndef main(argv):\n    print(json.dumps(argv))\n    return 0\n"
        )
        (self.root / "icons").mkdir()
        (self.root / "icons/icon.icns").write_bytes(b"icon")
        commands = self.root / "commands"
        commands.mkdir()
        for name in ("uname", "node", "pyxel", "pyinstaller", "codesign", "ditto"):
            path = commands / name
            path.write_text(FAKE_TOOL)
            path.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{commands}{os.pathsep}{os.environ['PATH']}")
        self.log = self.root / "commands.jsonl"
        self.env["BUILD_TEST_LOG"] = str(self.log)
        self.env.pop("PYXEL", None)
        self.env.pop("CODESIGN_IDENTITY", None)

    def build(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.root / "build.sh"), *args],
            cwd=self.root.parent,
            env=self.env,
            capture_output=True,
            text=True,
        )

    def test_builds_each_mode_with_only_app_in_distribution(self) -> None:
        for mode in ("normal", "exhibition", "demo", "beta"):
            with self.subTest(mode=mode):
                args = () if mode == "normal" else ("--mode", mode)
                result = self.build(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                name = "dungeon-antiqua-zero" + ("" if mode == "normal" else f"-{mode}")
                output = self.root / "dist/mac" / mode
                self.assertEqual(
                    {p.name for p in output.iterdir()},
                    {f"{name}.app", f"{name}-mac.zip"},
                )
                with zipfile.ZipFile(output / f"{name}-mac.zip") as archive:
                    self.assertTrue(archive.namelist())
                    self.assertTrue(all(p.startswith(f"{name}.app/") for p in archive.namelist()))
                package_path = output / f"{name}.app/Contents/Resources/{name}.pyxapp"
                with zipfile.ZipFile(package_path) as package:
                    self.assertNotIn("app/__pycache__/main.pyc", package.namelist())
                    self.assertNotIn("app/.DS_Store", package.namelist())
                    startup = package.read("app/.pyxapp_startup_script").decode()
                    with TemporaryDirectory() as extracted:
                        package.extractall(extracted)
                        run = subprocess.run(
                            [sys.executable, "-B", "-c",
                             "import runpy, sys; sys.path.insert(0, sys.argv[1]); "
                             "sys.argv = ['pyxel', 'play', 'game.pyxapp']; "
                             f"runpy.run_path(sys.path[0] + '/{startup}', run_name='__main__')",
                             str(Path(extracted) / "app")],
                            capture_output=True, text=True,
                        )
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(json.loads(run.stdout), ["--mode", mode])
                self.assertFalse((self.app / "_desktop_main.py").exists())
                self.assertTrue((self.app / "__pycache__/main.pyc").exists())
                self.assertEqual(list((self.root / "dist/mac").glob(".build-*")), [])
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        signing = [args for tool, args in calls if tool == "codesign"]
        self.assertEqual(len(signing), 8)
        self.assertTrue(all(args[args.index("--sign") + 1] == "-" for args in signing[::2]))

    def test_rejects_invalid_arguments_before_running_tools(self) -> None:
        for args in (("--mode", "unknown"), ("--mode",), ("--windows",)):
            with self.subTest(args=args):
                result = self.build(*args)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.log.exists())
                self.assertFalse((self.root / "dist").exists())
        self.assertEqual(self.build("--help").returncode, 0)
        self.assertFalse(self.log.exists())

    def test_failure_preserves_previous_release_and_cleans_stage(self) -> None:
        output = self.root / "dist/mac/demo"
        output.mkdir(parents=True)
        previous = output / "previous.zip"
        previous.write_bytes(b"previous release")
        for failure in ("sync", "app2exe", "codesign", "ditto"):
            with self.subTest(failure=failure):
                self.env["BUILD_TEST_FAIL"] = failure
                result = self.build("--mode=demo")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(previous.read_bytes(), b"previous release")
                self.assertEqual(list(output.iterdir()), [previous])
                self.assertEqual(list(output.parent.glob(".build-*")), [])
        self.env.pop("BUILD_TEST_FAIL")
        self.env["CODESIGN_IDENTITY"] = "test identity"
        self.env["PYXEL"] = "commands/pyxel"
        result = self.build("--mode=demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(previous.exists())
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertTrue(any("test identity" in args for tool, args in calls if tool == "codesign"))

    def test_missing_resource_stops_before_packaging(self) -> None:
        (self.app / "images/graphics.bin").unlink()
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("app/images/graphics.bin", result.stderr)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertFalse(any(tool == "pyxel" for tool, _ in calls))


if __name__ == "__main__":
    unittest.main()
