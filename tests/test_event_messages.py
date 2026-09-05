from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.localization import Localizer
from app.resources.event_messages import (
    EventMessageCatalog,
    EventMessageResourceError,
)
from app.state import Language
from scripts.event_pipeline import (
    compile_event_messages,
    event_source_paths,
    load_event_messages,
    validate_event_messages,
)


def message_record(
    message_id: str = "sample.greeting",
) -> dict[str, object]:
    return {
        "message_id": message_id,
        "text_ja": ["こんにちは", "ようこそ"],
        "text_en": [],
        "text_zhcn": ["你好", "欢迎"],
    }


class EventMessagePipelineTest(unittest.TestCase):
    def test_compiles_localized_records(self) -> None:
        source = [message_record()]

        diagnostics = validate_event_messages(source)
        compiled = compile_event_messages(source)

        self.assertEqual(diagnostics, [])
        self.assertEqual(compiled[0]["message_id"], "sample.greeting")
        self.assertEqual(compiled, source)

    def test_rejects_removed_note_field(self) -> None:
        source = [{**message_record(), "note": "制作メモ"}]

        diagnostics = validate_event_messages(source)

        self.assertIn("unknown_field", {item.code for item in diagnostics})

    def test_rejects_duplicate_invalid_and_empty_messages(self) -> None:
        source = [
            message_record(),
            message_record(),
            {
                **message_record("Invalid"),
                "text_ja": ["   "],
                "extra": True,
            },
        ]

        codes = {item.code for item in validate_event_messages(source)}

        self.assertEqual(
            {
                "duplicate_message_id",
                "invalid_message_id",
                "invalid_message_text",
                "unknown_field",
            }
            - codes,
            set(),
        )

    def test_loads_missing_catalog_as_empty_for_initial_setup(self) -> None:
        with TemporaryDirectory() as directory:
            self.assertEqual(load_event_messages(Path(directory)), [])

    def test_messages_file_is_not_treated_as_event_namespace(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            events = root / "events"
            events.mkdir()
            (events / "flags.json").write_text("[]", encoding="utf-8")
            (events / "messages.json").write_text("[]", encoding="utf-8")
            (events / "sample.json").write_text("{}", encoding="utf-8")

            self.assertEqual(
                [path.name for path in event_source_paths(root)],
                ["sample.json"],
            )


class EventMessageCatalogTest(unittest.TestCase):
    def test_resolves_selected_language_and_falls_back_to_japanese(self) -> None:
        runtime = [message_record()]
        catalog = EventMessageCatalog.from_records(runtime)

        self.assertEqual(
            catalog.lines(
                "sample.greeting", Localizer(Language.SIMPLIFIED_CHINESE)
            ),
            ("你好", "欢迎"),
        )
        self.assertEqual(
            catalog.lines("sample.greeting", Localizer(Language.ENGLISH)),
            ("こんにちは", "ようこそ"),
        )

    def test_loads_compiled_json_and_rejects_unknown_fields(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "messages.json"
            path.write_text(
                json.dumps(compile_event_messages([message_record()])),
                encoding="utf-8",
            )
            self.assertEqual(EventMessageCatalog.from_json(path).ids, ("sample.greeting",))

        with self.assertRaises(EventMessageResourceError):
            EventMessageCatalog.from_records(
                [{**message_record(), "note": "未対応の属性"}]
            )


if __name__ == "__main__":
    unittest.main()
