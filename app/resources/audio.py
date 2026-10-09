"""Play WAV/Pyxel sound effects and external PCM background music."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import pyxel

if __package__ == "resources":
    from audio_catalog import AudioCatalogError, SoundEffectDefinition, load_sound_effects
else:
    from ..audio_catalog import AudioCatalogError, SoundEffectDefinition, load_sound_effects


SE_CHANNEL = 0
SE_VOLUME_GAINS = (0.0, 0.05, 0.10, 0.15, 0.20)
# ゲーム内のWAV効果音だけに適用する倍率。1.0で補正なし、1.5で50%増。
WAV_SE_VOLUME_MULTIPLIER = 1.5
BGM_CHANNEL = 2
BGM_VOLUME_GAINS = (0.0, 0.2, 0.4, 0.6, 0.8)
BGM_STOP_FADE_FRAMES = 30
SE_CATALOG_PATH = Path(__file__).resolve().parents[1] / "audio" / "catalog.json"


class AudioResourceError(RuntimeError):
    """Raised when an audio asset cannot be resolved, decoded, or played."""


def load_se_catalog(path: Path = SE_CATALOG_PATH) -> MappingProxyType:
    try:
        return load_sound_effects(path)
    except AudioCatalogError as error:
        raise AudioResourceError(str(error)) from error


_SE_CATALOG_DATA = dict(load_se_catalog())
SE_CATALOG = MappingProxyType(_SE_CATALOG_DATA)


def reload_se_catalog(path: Path = SE_CATALOG_PATH) -> MappingProxyType:
    """Reload edited SE mappings without replacing the public mapping object."""

    loaded = load_se_catalog(path)
    _SE_CATALOG_DATA.clear()
    _SE_CATALOG_DATA.update(loaded)
    global _se_player
    _se_player = SoundEffectPlayer(path.parent.parent / "se", volume=_se_player.volume)
    return SE_CATALOG


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


def sound_effect_definition(se_id: str) -> SoundEffectDefinition:
    """Resolve a stable SE ID to its WAV or Pyxel Sound definition."""

    if not isinstance(se_id, str) or se_id not in SE_CATALOG:
        raise AudioResourceError(f"未定義のSE IDです: {se_id}")
    return SE_CATALOG[se_id]


class SoundEffectPlayer:
    """Cache WAVs; an optional game volume enables source-specific gain."""

    def __init__(
        self, se_dir: Path | None = None, *, pyxel_api: Any | None = None,
        volume: int | None = None,
    ) -> None:
        self.se_dir = (se_dir or SE_CATALOG_PATH.parent.parent / "se").resolve()
        self._pyxel = pyxel if pyxel_api is None else pyxel_api
        self._wav_sounds: dict[Path, tuple[int, int, Any]] = {}
        if volume is not None:
            self._validate_volume(volume)
        self._volume = volume
        self._active_wav = False

    @property
    def volume(self) -> int | None:
        return self._volume

    @staticmethod
    def _validate_volume(volume: int) -> None:
        if isinstance(volume, bool) or not isinstance(volume, int):
            raise TypeError("SE volume must be an integer")
        if not 0 <= volume < len(SE_VOLUME_GAINS):
            raise ValueError("SE volume must be from 0 to 4")

    def set_volume(self, volume: int, *, pyxel_api: Any | None = None) -> None:
        self._validate_volume(volume)
        self._volume = volume
        self._apply_gain(pyxel_api=pyxel_api)

    def _apply_gain(self, *, pyxel_api: Any | None = None) -> None:
        # Editors without a game volume keep their existing preview gain.
        if self._volume is None:
            return
        px = self._pyxel if pyxel_api is None else pyxel_api
        if len(px.channels) > SE_CHANNEL:
            multiplier = WAV_SE_VOLUME_MULTIPLIER if self._active_wav else 1.0
            px.channels[SE_CHANNEL].gain = SE_VOLUME_GAINS[self._volume] * multiplier

    def _sound(self, definition: SoundEffectDefinition) -> Any:
        if definition.wav is None:
            return definition.sound
        path = definition.wav_path(self.se_dir)
        stat = path.stat()
        cached = self._wav_sounds.get(path)
        signature = (stat.st_mtime_ns, stat.st_size)
        if cached is not None and cached[:2] == signature:
            return cached[2]
        sound = self._pyxel.Sound()
        sound.pcm(str(path))
        self._wav_sounds[path] = (*signature, sound)
        return sound

    def preload(
        self, definitions: Mapping[str, SoundEffectDefinition] = SE_CATALOG,
    ) -> None:
        """Decode registered WAVs during initialization rather than combat."""

        for definition in definitions.values():
            if definition.wav is not None:
                self._resolve_sound(definition)

    def _resolve_sound(self, definition: SoundEffectDefinition) -> Any:
        try:
            return self._sound(definition)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            raise AudioResourceError(f"SEを読み込めません: {definition.se_id}: {error}") from error

    def play(self, definition: SoundEffectDefinition) -> None:
        sound = self._resolve_sound(definition)
        try:
            self._active_wav = definition.wav is not None
            self._apply_gain()
            self._pyxel.play(SE_CHANNEL, sound)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            raise AudioResourceError(f"SEを再生できません: {definition.se_id}: {error}") from error


_se_player = SoundEffectPlayer()


def preload_se() -> None:
    _se_player.preload()


def set_se_volume(volume: int, *, pyxel_api: Any | None = None) -> None:
    _se_player.set_volume(volume, pyxel_api=pyxel_api)


def play_se(se_id: str, *, pyxel_api: Any | None = None) -> None:
    definition = sound_effect_definition(se_id)
    player = (
        _se_player if pyxel_api is None
        else SoundEffectPlayer(
            _se_player.se_dir, pyxel_api=pyxel_api, volume=_se_player.volume,
        )
    )
    player.play(definition)


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
        self._queued_id: str | None = None
        self._queued_start_sec = 0.0
        self._volume = 0
        self._fade_rate = 1.0
        self._stop_fade_frames = 0
        self._stop_fade_remaining = 0
        self._stop_fade_start_rate = 1.0
        self._paused = False
        self._paused_sec: float | None = None
        self.set_volume(volume)

    @property
    def current_id(self) -> str | None:
        return self._current_id

    @property
    def playback_position_sec(self) -> float | None:
        """Return the current track's position, including while paused."""

        if self._paused:
            return self._paused_sec
        return self._playback_position_sec()

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
    def is_fading_out(self) -> bool:
        return self._stop_fade_remaining > 0

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
            self._cancel_stop_fade()
            self._queued_id = None
            self._queued_start_sec = 0.0
            return False

        path = self._path_for(bgm_id)
        sound = self._load_sound(bgm_id, path)
        self._cancel_stop_fade()
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
        self._queued_id = None
        self._queued_start_sec = 0.0
        self._paused = False
        self._paused_sec = None
        return True

    def play_once_then(
        self,
        bgm_id: str,
        next_bgm_id: str,
        *,
        next_start_sec: float = 0.0,
    ) -> bool:
        """Play one track once and start a looping track immediately afterward."""

        if not isinstance(next_bgm_id, str) or not next_bgm_id:
            raise ValueError("next_bgm_id must be a non-empty string")
        if isinstance(next_start_sec, bool) or not isinstance(next_start_sec, (int, float)):
            raise TypeError("next_start_sec must be a number")
        if next_start_sec < 0:
            raise ValueError("next_start_sec must not be negative")
        self._path_for(next_bgm_id)
        resume_sec = float(next_start_sec)
        if self._current_id == next_bgm_id and self._loop:
            resume_sec = self.playback_position_sec or 0.0
        elif self._queued_id == next_bgm_id:
            resume_sec = self._queued_start_sec
        changed = self.play(bgm_id, loop=False)
        self._queued_id = next_bgm_id
        self._queued_start_sec = resume_sec
        return changed

    def transition_to(self, bgm_id: str, *, start_sec: float = 0.0) -> bool:
        """Respect a matching queued transition, or play the requested BGM now."""

        self._path_for(bgm_id)
        if self._queued_id == bgm_id:
            return False
        if self._current_id == bgm_id and self._loop:
            return self.play(bgm_id)
        return self.play(bgm_id, start_sec=start_sec)

    def update(self) -> bool:
        """Advance a pending fade stop, or resolve a one-shot successor."""

        if self._paused:
            return False
        if self.is_fading_out:
            self._stop_fade_remaining -= 1
            self.set_fade_rate(
                self._stop_fade_start_rate * self._stop_fade_remaining / self._stop_fade_frames
            )
            if self._stop_fade_remaining == 0:
                self.stop()
                return True
            return False
        if self._queued_id is None:
            if self._current_id is None or self._loop:
                return False
            if self._playback_position_sec() is not None:
                return False
            self._active_sound = None
            self._current_id = None
            return True
        if self._playback_position_sec() is not None:
            return False
        next_bgm_id = self._queued_id
        start_sec = self._queued_start_sec
        self._queued_id = None
        self._queued_start_sec = 0.0
        return self.play(next_bgm_id, start_sec=start_sec)

    def pause(self) -> None:
        """Suspend playback without losing the decoded track or queued successor."""

        if self._paused:
            return
        self._paused_sec = self._playback_position_sec()
        self._paused = True
        self._pyxel.stop(self.channel)

    def resume(self) -> None:
        """Continue a suspended track at its saved playback position."""

        if not self._paused:
            return
        if self._active_sound is not None and self._paused_sec is not None:
            try:
                self._pyxel.play(
                    self.channel, self._active_sound,
                    sec=self._paused_sec, loop=self._loop,
                )
            except (KeyboardInterrupt, SystemExit):
                raise
            except BaseException as error:
                raise AudioResourceError(
                    f"BGMを再開できません: {self._current_id}: {error}"
                ) from error
        self._paused = False
        self._paused_sec = None

    def fade_out_and_stop(self, frames: int = BGM_STOP_FADE_FRAMES) -> bool:
        """Fade the current track to silence and discard automatic successors."""

        if type(frames) is not int or frames < 1:
            raise ValueError("BGM stop fade frames must be a positive integer")
        self._queued_id = None
        self._queued_start_sec = 0.0
        if not self.is_playing:
            self.stop()
            return False
        self._stop_fade_frames = frames
        self._stop_fade_remaining = frames
        self._stop_fade_start_rate = self._fade_rate
        return True

    def _cancel_stop_fade(self) -> None:
        if self._stop_fade_frames:
            self._stop_fade_frames = 0
            self._stop_fade_remaining = 0
            self.set_fade_rate(1.0)

    def stop(self) -> bool:
        was_playing = self.is_playing
        self._pyxel.stop(self.channel)
        self._cancel_stop_fade()
        self._active_sound = None
        self._current_id = None
        self._queued_id = None
        self._queued_start_sec = 0.0
        self._paused = False
        self._paused_sec = None
        return was_playing

    def _playback_position_sec(self) -> float | None:
        try:
            position = self._pyxel.play_pos(self.channel)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as error:
            raise AudioResourceError(
                f"BGMの再生位置を取得できません: {error}"
            ) from error
        if position is None:
            return None
        try:
            seconds = float(position[1])
        except (IndexError, TypeError, ValueError) as error:
            raise AudioResourceError("BGMの再生位置が不正です。") from error
        if seconds < 0:
            raise AudioResourceError("BGMの再生位置が不正です。")
        return seconds

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
    "BGM_STOP_FADE_FRAMES",
    "SE_CATALOG_PATH",
    "AudioResourceError",
    "BgmPlayer",
    "SE_CATALOG",
    "list_bgm_ids",
    "load_se_catalog",
    "list_se_ids",
    "play_se",
    "reload_se_catalog",
    "SE_CHANNEL",
    "SE_VOLUME_GAINS",
    "WAV_SE_VOLUME_MULTIPLIER",
    "SoundEffectPlayer",
    "sound_effect_definition",
    "preload_se",
    "set_se_volume",
]
