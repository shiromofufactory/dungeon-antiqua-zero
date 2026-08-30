from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.resources.data import DataResourceError, load_record_array


class DataResourcesTest(unittest.TestCase):
    def test_loads_an_array_of_objects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            (data_dir / "records.json").write_text(
                '[{"key": "one"}, {"key": "two"}]',
                encoding="utf-8",
            )

            records = load_record_array("records.json", data_dir)

        self.assertEqual(records, [{"key": "one"}, {"key": "two"}])

    def test_reports_missing_and_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with self.assertRaises(DataResourceError):
                load_record_array("missing.json", data_dir)

            (data_dir / "invalid.json").write_text("[", encoding="utf-8")
            with self.assertRaises(DataResourceError):
                load_record_array("invalid.json", data_dir)

    def test_rejects_non_record_array_roots(self) -> None:
        invalid_values = ("{}", "[1]", '[[{"key": "nested"}]]')
        for value in invalid_values:
            with self.subTest(value=value):
                with tempfile.TemporaryDirectory() as directory:
                    data_dir = Path(directory)
                    (data_dir / "records.json").write_text(
                        value,
                        encoding="utf-8",
                    )
                    with self.assertRaises(DataResourceError):
                        load_record_array("records.json", data_dir)

    def test_rejects_paths_and_invalid_data_directories(self) -> None:
        with self.assertRaises(ValueError):
            load_record_array("../records.json")
        with self.assertRaises(TypeError):
            load_record_array("records.json", "data")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
