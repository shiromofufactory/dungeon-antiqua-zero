from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.resources.fonts import FONT_FILENAMES, FontResourceError, FontResources
from app.state import Language


class FontResourcesTest(unittest.TestCase):
    def test_expected_font_file_is_loaded_once_per_language(self) -> None:
        with TemporaryDirectory() as directory:
            fonts_dir = Path(directory)
            font_path = fonts_dir / FONT_FILENAMES[Language.ENGLISH]
            font_path.touch()
            loaded_paths: list[str] = []
            font = object()

            def load(path: str) -> object:
                loaded_paths.append(path)
                return font

            resources = FontResources(fonts_dir, loader=load)

            self.assertIs(resources.font_for(Language.ENGLISH), font)
            self.assertIs(resources.font_for(Language.ENGLISH), font)
            self.assertEqual(loaded_paths, [str(font_path.resolve())])
            self.assertEqual(resources.loaded_languages, (Language.ENGLISH,))

    def test_all_configured_font_files_exist_in_default_directory(self) -> None:
        resources = FontResources(loader=lambda path: object())

        for filename in FONT_FILENAMES.values():
            self.assertTrue((resources.fonts_dir / filename).is_file())

    def test_missing_language_font_is_reported_without_fallback(self) -> None:
        with TemporaryDirectory() as directory:
            resources = FontResources(Path(directory), loader=lambda path: object())

            with self.assertRaisesRegex(FontResourceError, "言語フォントがありません"):
                resources.font_for(Language.SIMPLIFIED_CHINESE)

    def test_language_must_be_an_enum_value(self) -> None:
        resources = FontResources(loader=lambda path: object())

        with self.assertRaises(TypeError):
            resources.font_for("ja")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
