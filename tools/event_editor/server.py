"""Serve the local structured event-authoring UI."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import sys
from urllib.parse import parse_qs, urlparse
import webbrowser

from scripts.event_pipeline import (
    compile_event_sources,
    load_event_source,
    load_event_sources,
    reference_catalogs,
    save_compiled_events,
    save_event_source,
    validate_event_sources,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = Path(__file__).resolve().parent / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8768
SESSION_CLIENT_HEADER = "event-editor-ui"
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def _valid_id(value: str) -> bool:
    return re.fullmatch(r"[a-z][a-z0-9_]*", value) is not None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    content_root = Path(
        os.environ.get("DA0_CONTENT_DIR", PROJECT_ROOT / "content")
    ).resolve()
    parser = argparse.ArgumentParser(description="イベント定義を構造化フォームで制作します。")
    parser.add_argument("--namespace", default="common", help="編集するnamespace（既定: common）")
    parser.add_argument("--content-root", type=Path, default=content_root, help=argparse.SUPPRESS)
    parser.add_argument("--runtime", type=Path, default=PROJECT_ROOT / "app" / "events" / "events.json", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args(argv)


class EventEditorApplication:
    def __init__(
        self,
        content_root: Path,
        runtime_path: Path,
        namespace: str,
        *,
        token: str | None = None,
        app_root: Path | None = None,
    ) -> None:
        if not _valid_id(namespace):
            raise ValueError("namespaceはlower_snake_caseで指定してください。")
        self.content_root = content_root.resolve()
        self.runtime_path = runtime_path.resolve()
        self.namespace = namespace
        self.token = token or secrets.token_urlsafe(24)
        self.app_root = (app_root or PROJECT_ROOT / "app").resolve()
        self.source_path = (
            self.content_root / "events" / f"{namespace}.json"
        ).resolve()
        source_root = (self.content_root / "events").resolve()
        if source_root not in self.source_path.parents:
            raise ValueError("イベントパスがcontent/events外です。")

    def load_source(self) -> tuple[dict[str, object], bool]:
        if self.source_path.is_file():
            return load_event_source(self.source_path), False
        return {
            "format_version": 1,
            "namespace": self.namespace,
            "flags": [],
            "events": [],
        }, True

    def sources_with(self, data: object) -> dict[str, dict[str, object]]:
        sources = load_event_sources(self.content_root)
        if isinstance(data, dict):
            sources[self.namespace] = data
        return sources

    def catalogs(self) -> dict[str, set[str]]:
        catalogs = reference_catalogs(self.content_root, app_root=self.app_root)
        maps_root = self.content_root / "maps" / "sources"
        actor_ids: set[str] = set()
        for path in sorted(maps_root.glob("*.json")) if maps_root.is_dir() else ():
            try:
                source = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(source, dict):
                continue
            actor_ids.update(
                actor["id"]
                for actor in source.get("actors", [])
                if isinstance(actor, dict) and isinstance(actor.get("id"), str)
            )
        catalogs["actor_ids"] = actor_ids
        return catalogs

    def validate(self, data: object) -> list[dict[str, str]]:
        if not isinstance(data, dict):
            return [{
                "severity": "error",
                "code": "invalid_root",
                "path": self.namespace,
                "message": "イベントJSONのルートはobjectである必要があります。",
            }]
        return [
            item.as_dict()
            for item in validate_event_sources(
                self.sources_with(data),
                **{
                    key: value
                    for key, value in self.catalogs().items()
                    if key != "actor_ids"
                },
            )
        ]

    def document_payload(self) -> dict[str, object]:
        data, is_new = self.load_source()
        catalogs = self.catalogs()
        sources = self.sources_with(data)
        event_ids = sorted(
            f"{source.get('namespace')}.{event.get('id')}"
            for source in sources.values()
            if isinstance(source.get("namespace"), str)
            for event in source.get("events", [])
            if isinstance(event, dict) and isinstance(event.get("id"), str)
        )
        flag_ids = sorted(
            f"{source.get('namespace')}.{flag.get('id')}"
            for source in sources.values()
            if isinstance(source.get("namespace"), str)
            for flag in source.get("flags", [])
            if isinstance(flag, dict) and isinstance(flag.get("id"), str)
        )
        return {
            "data": data,
            "catalogs": {
                key: sorted(values) for key, values in catalogs.items()
            },
            "event_ids": event_ids,
            "flag_ids": flag_ids,
            "diagnostics": self.validate(data),
            "is_new": is_new,
            "source_path": self._display_path(self.source_path),
            "runtime_path": self._display_path(self.runtime_path),
        }

    def save(self, data: object) -> dict[str, object]:
        diagnostics = self.validate(data)
        if any(item["severity"] == "error" for item in diagnostics) or not isinstance(data, dict):
            return {"saved": False, "diagnostics": diagnostics}
        sources = self.sources_with(data)
        catalogs = self.catalogs()
        compiled = compile_event_sources(
            sources,
            **{key: value for key, value in catalogs.items() if key != "actor_ids"},
        )
        save_event_source(self.source_path, data)
        save_compiled_events(self.runtime_path, compiled)
        return {
            "saved": True,
            "diagnostics": diagnostics,
            "source_sha256": compiled["source_sha256"],
        }

    @staticmethod
    def _display_path(path: Path) -> str:
        return (
            path.relative_to(PROJECT_ROOT).as_posix()
            if PROJECT_ROOT in path.parents
            else path.as_posix()
        )


def make_handler(application: EventEditorApplication) -> type[BaseHTTPRequestHandler]:
    class EventEditorHandler(BaseHTTPRequestHandler):
        server_version = "DA0EventEditor/1"

        def log_message(self, format: str, *args: object) -> None:
            if self.path.startswith("/api/") and args and str(args[1]) >= "400":
                super().log_message(format, *args)

        def _authorized(self, parsed=None) -> bool:
            parsed = parsed or urlparse(self.path)
            query_token = parse_qs(parsed.query).get("token", [None])[0]
            return query_token == application.token or self.headers.get(
                "X-Event-Editor-Token"
            ) == application.token

        def _session_allowed(self) -> bool:
            host = urlparse(f"//{self.headers.get('Host', '')}").hostname
            return host == DEFAULT_HOST and self.headers.get(
                "X-Event-Editor-Client"
            ) == SESSION_CLIENT_HEADER

        def _send_bytes(self, content: bytes, content_type: str, status=HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(content)

        def _send_json(self, value: object, status=HTTPStatus.OK) -> None:
            self._send_bytes(
                (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8"),
                "application/json; charset=utf-8",
                status,
            )

        def _error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/session-token":
                if not self._session_allowed():
                    self._error(HTTPStatus.FORBIDDEN, "セッション更新要求が不正です。")
                    return
                self._send_json({"token": application.token})
                return
            if parsed.path == "/api/document":
                if not self._authorized(parsed):
                    self._error(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                    return
                try:
                    self._send_json(application.document_payload())
                except (OSError, ValueError) as error:
                    self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                return
            relative = "index.html" if parsed.path in ("", "/") else parsed.path.lstrip("/")
            static_path = (STATIC_ROOT / relative).resolve()
            if STATIC_ROOT not in static_path.parents or not static_path.is_file():
                self._error(HTTPStatus.NOT_FOUND, "ページが見つかりません。")
                return
            self._send_bytes(
                static_path.read_bytes(),
                MIME_TYPES.get(static_path.suffix.lower(), "application/octet-stream"),
            )

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path not in ("/api/validate", "/api/save"):
                self._error(HTTPStatus.NOT_FOUND, "APIが見つかりません。")
                return
            if not self._authorized(parsed):
                self._error(HTTPStatus.FORBIDDEN, "認証トークンが不正です。")
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                self._error(HTTPStatus.BAD_REQUEST, "Content-Lengthが不正です。")
                return
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "リクエストサイズが不正です。")
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._error(HTTPStatus.BAD_REQUEST, "JSONを読み込めません。")
                return
            data = payload.get("data") if isinstance(payload, dict) else None
            try:
                response = (
                    application.save(data)
                    if parsed.path == "/api/save"
                    else {"saved": False, "diagnostics": application.validate(data)}
                )
                self._send_json(response)
            except (OSError, ValueError) as error:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    return EventEditorHandler


def create_server(application: EventEditorApplication, port: int) -> ThreadingHTTPServer:
    if not 0 <= port <= 65535:
        raise ValueError("portは0から65535で指定してください。")
    return ThreadingHTTPServer((DEFAULT_HOST, port), make_handler(application))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        application = EventEditorApplication(
            args.content_root, args.runtime, args.namespace
        )
        server = create_server(application, args.port)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    actual_port = server.server_address[1]
    url = f"http://{DEFAULT_HOST}:{actual_port}/?token={application.token}"
    print("Event Editorを起動しました。")
    print(url)
    print("終了するにはこのターミナルでCtrl+Cを押してください。")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n終了します。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
