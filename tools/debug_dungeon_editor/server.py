"""Read, validate and atomically save the developer-owned dungeon catalog."""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

from app.debug_dungeon import parse_dungeons


class DebugDungeonEditorApplication:
    def __init__(self, content_root: Path, app_root: Path, *, token: str):
        self.content_root = content_root
        self.app_root = app_root
        self.source_path = app_root / "debug" / "dungeons.json"
        self.token = token
        self.lock = Lock()

    def catalogs(self):
        result = {}
        for name in ("items", "monsters"):
            records = json.loads((self.content_root / "data" / f"{name}.json").read_text(encoding="utf-8"))
            result[name] = [{"key": record["name_en"], "name": record.get("name_ja") or record["name_en"]}
                            for record in records]
        result["bgm_ids"] = sorted(path.stem for path in (self.app_root / "audio").glob("*.ogg"))
        return result

    def validate(self, data):
        catalogs = self.catalogs()
        try:
            parse_dungeons(data, item_keys={item["key"] for item in catalogs["items"]},
                           monster_keys={monster["key"] for monster in catalogs["monsters"]},
                           bgm_ids=catalogs["bgm_ids"])
        except ValueError as error:
            return [{"severity": "error", "message": str(error)}]
        return []

    def document_payload(self):
        data = (json.loads(self.source_path.read_text(encoding="utf-8")) if self.source_path.exists()
                else {"format_version": 1, "dungeons": []})
        return {"data": data, "catalogs": self.catalogs(), "diagnostics": self.validate(data)}

    def save(self, data):
        with self.lock:
            diagnostics = self.validate(data)
            if diagnostics:
                return {"saved": False, "diagnostics": diagnostics}
            self.source_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.source_path.parent,
                                        prefix=".dungeons-", suffix=".tmp", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
                temporary.replace(self.source_path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return {"saved": True, "diagnostics": []}
