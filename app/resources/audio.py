"""Load and play external PCM background music through a dedicated channel."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pyxel


BGM_CHANNEL = 2
BGM_VOLUME_GAINS = (0.0, 0.2, 0.4, 0.6, 0.8)
SE_CATALOG_PATH = Path(__file__).resolve().parents[1] / "audio" / "catalog.json"


class AudioResourceError(RuntimeError):
    """Raised when a BGM asset cannot be resolved or decoded."""


def _load_se_catalog(path: Path = SE_CATALOG_PATH) -> MappingProxyType:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AudioResourceError(
            f"SEカタログを読み込めません: {path}: {error}"
        ) from error
    if not isinstance(document, dict) or document.get("format_version") != 1:
        raise AudioResourceError("SEカタログのformat_versionが不正です。")
    records = document.get("sound_effects")
    if not isinstance(records, dict) or not records:
        raise AudioResourceError("SEカタログのsound_effectsが不正です。")
    loaded: dict[str, tuple[int, int]] = {}
    for se_id, record in records.items():
        if not isinstance(se_id, str) or not se_id or not isinstance(record, dict):
            raise AudioResourceError("SEカタログのレコードが不正です。")
        channel = record.get("channel")
        sound = record.get("sound")
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0
            for value in (channel, sound)
        ):
            raise AudioResourceError(
                f"SEカタログのchannelまたはsoundが不正です: {se_id}"
            )
        loaded[se_id] = (channel, sound)
    return MappingProxyType(loaded)


SE_CATALOG = _load_se_catalog()


def list_bgm_ids(audio_dir: Path | None = None) -> tuple[str, ...]:
    app_dir = Path(__file__).resolve().parents[1]
    resolved_dir = (audio_dir or app_dir / "audio").resolve()
    if not resolved_dir.is_dir():
        return ()
    ids = {
        path.relative_to(resolved_dir).with_suffix("").as_posix()
        for path in resolved_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() == ".ogg"
        and not path.name.startswith(".")
    }
    return tuple(sorted(ids))


def list_se_ids() -> tuple[str, ...]:
    return tuple(SE_CATALOG)


def play_se(se_id: str, *, pyxel_api: Any = pyxel) -> None:
    if not isinstance(se_id, str) or se_id not in SE_CATALOG:
        raise AudioResourceError(f"未定義のSE IDです: {se_id}")
    channel, sound = SE_CATALOG[se_id]
    try:
        pyxel_api.play(channel, sound)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as error:
        raise AudioResourceError(f"SEを再生できません: {se_id}: {error}") from error


class BgmPlayer:
    """Own the active decoded BGM and its dedicated Pyxel channel."""

    def __init__(
        self,
        audio_dir: Path | None = None,
        *,
        channel: int = BGM_CHANNEL,
        volume: int = 3,
        pyxel_api: Any | None = None,
    ) -> None:
        if isinstance(channel, bool) or not isinstance(channel, int):
            raise TypeError("channel must be an integer")
        if channel < 0:
            raise ValueError("channel must not be negative")

        app_dir = Path(__file__).resolve().parents[1]
        self.audio_dir = (audio_dir or app_dir / "audio").resolve()
        self.channel = channel
        self._pyxel = pyxel_api or pyxel
        self._active_sound: Any | None = None
        self._current_id: str | None = None
        self._loop = True
        self._volume = 0
        self._fade_rate = 1.0
        self.set_volume(volume)

    @property
    def current_id(self) -> str | None:
        return self._current_id

    @property
    def volume(self) -> int:
        return self._volume

    @property
    def fade_rate(self) -> float:
        return self._fade_rate

    @property
    def is_playing(self) -> bool:
        return self._current_id is not None

    @property
    def available_ids(self) -> tuple[str, ...]:
        return list_bgm_ids(self.audio_dir)

    def set_volume(self, volume: int) -> None:
        if isinstance(volume, bool) or not isinstance(volume, int):
            raise TypeError("volume must be an integer")
        if not 0 <= volume < len(BGM_VOLUME_GAINS):
            raise ValueError("volume must be from 0 to 4")
        if self.channel >= len(self._pyxel.channels):
            raise AudioResourceError(
                f"BGMチャンネルがありません: {self.channel}"
            )

        self._volume = volume
        self._apply_gain()

    def set_fade_rate(self, rate: float) -> None:
        """Scale the configured BGM volume without changing the setting."""

        if isinstance(rate, bool) or not isinstance(rate, (int, float)):
            raise TypeError("BGM fade rate must be a number")
        if not 0.0 <= rate <= 1.0:
            raise ValueError("BGM fade rate must be from 0.0 to 1.0")
        self._fade_rate = float(rate)
        self._apply_gain()

    def _apply_gain(self) -> None:
        self._pyxel.channels[self.channel].gain = (
            BGM_VOLUME_GAINS[self._volume] * self._fade_rate
        )

    def play(
        self,
        bgm_id: str,
        *,
        loop: bool = True,
        start_sec: float = 0.0,
    ) -> bool:
        if not isinstance(loop, bool):
            raise TypeError("loop must be a bool")
        if isinstance(start_sec, bool) or not isinstance(
            start_sec,
            (int, float),
        ):
            raise TypeError("start_sec must be a number")
        if start_sec < 0:
            raise ValueError("start_sec must not be negative")
        if self._current_id == bgm_id and self._loop == loop and start_sec == 0:
            return False

        path = self._path_for(bgm_id)
        sound = self._load_sound(bgm_id, path)
        self._pyxel.stop(self.channel)
        try:
            self._pyxel.play(
                self.channel,
                sound,
                sec=float(start_sec),
                loop=loop,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            self._active_sound = None
            self._current_id = None
            raise AudioResourceError(
                f"BGMを再生できません: {bgm_id}: {error}"
            ) from error

        self._active_sound = sound
        self._current_id = bgm_id
        self._loop = loop
        return True

    def stop(self) -> bool:
        was_playing = self.is_playing
        self._pyxel.stop(self.channel)
        self._active_sound = None
        self._current_id = None
        return was_playing

    def _path_for(self, bgm_id: str) -> Path:
        if not isinstance(bgm_id, str) or not bgm_id:
            raise ValueError("bgm_id must be a non-empty string")

        relative = Path(bgm_id)
        if (
            relative.is_absolute()
            or relative.as_posix() != bgm_id
            or relative.suffix
            or any(part in ("", ".", "..") for part in relative.parts)
        ):
            raise ValueError(f"BGM IDが不正です: {bgm_id}")

        path = self.audio_dir.joinpath(*relative.parts).with_suffix(".ogg")
        if not path.is_file():
            raise AudioResourceError(f"BGMファイルがありません: {path}")
        return path

    def _load_sound(self, bgm_id: str, path: Path) -> Any:
        try:
            sound = self._pyxel.Sound()
            sound.pcm(str(path))
            return sound
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            raise AudioResourceError(
                f"BGMを読み込めません: {bgm_id}: {error}"
            ) from error


__all__ = [
    "BGM_CHANNEL",
    "BGM_VOLUME_GAINS",
    "SE_CATALOG_PATH",
    "AudioResourceError",
    "BgmPlayer",
    "SE_CATALOG",
    "list_bgm_ids",
    "list_se_ids",
    "play_se",
]
