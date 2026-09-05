from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.event_pipeline import (
    compile_event_flags,
    event_flag_ids,
    load_event_flags,
    validate_event_flags,
)


class EventFlagPipelineTest(unittest.TestCase):
    def test_accepts_global_ids_with_optional_classification_prefix(self) -> None:
        source = [
            {"flag_id": "game_started", "note": "全体進行"},
            {"flag_id": "quest.alvan_joined", "note": "加入済み"},
        ]

        self.assertEqual(validate_event_flags(source), [])
        self.assertEqual(
            compile_event_flags(source),
            ["game_started", "quest.alvan_joined"],
        )
        self.assertEqual(
            event_flag_ids(source),
            {"game_started", "quest.alvan_joined"},
        )

    def test_rejects_duplicate_invalid_and_unknown_fields(self) -> None:
        source = [
            {"flag_id": "quest.done"},
            {"flag_id": "quest.done"},
            {"flag_id": "Invalid", "extra": True},
        ]

        codes = {item.code for item in validate_event_flags(source)}

        self.assertEqual(
            {"duplicate_flag_id", "invalid_flag_id", "unknown_field"} - codes,
            set(),
        )

    def test_loads_missing_catalog_as_empty_for_initial_setup(self) -> None:
        with TemporaryDirectory() as directory:
            self.assertEqual(load_event_flags(Path(directory)), [])


if __name__ == "__main__":
    unittest.main()
