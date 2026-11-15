"""Own sound-test selections and reuse production audio playback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.audio_catalog import SoundEffectDefinition, load_sound_effects
from app.resources.audio import AudioResourceError, BgmPlayer, SE_CHANNEL, SoundEffectPlayer
from app.state import Settings


@dataclass(frozen=True)
class SoundOption:
    label: str
    definition: SoundEffectDefinition


def pyxel_sound_options(
    definitions: Mapping[str, SoundEffectDefinition],
) -> tuple[SoundOption, ...]:
    options = []
    for number in range(64):
        names = sorted(key for key, value in definitions.items() if value.sound == number)
        label = str(number) + (f" ({', '.join(names)})" if names else "")
        options.append(SoundOption(
            label, SoundEffectDefinition(f"preview_sound_{number}", sound=number)
        ))
    return tuple(options)


def wav_sound_options(se_dir: Path) -> tuple[SoundOption, ...]:
    root = se_dir.resolve()
    paths = sorted((
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() == ".wav"
        and path.resolve().is_relative_to(root)
        and not any(part.startswith(".") for part in path.relative_to(root).parts)
    ), key=lambda name: (name.casefold(), name))
    return tuple(SoundOption(
        name, SoundEffectDefinition(f"preview_wav_{index}", wav=name)
    ) for index, name in enumerate(paths))


class SoundTestSession:
    """Keep preview state local; never write the catalog or game settings."""

    def __init__(self, app_root: Path, *, pyxel_api: Any) -> None:
        self._pyxel = pyxel_api
        defaults = Settings()
        self.bgm = BgmPlayer(app_root / "audio", volume=defaults.bgm_volume,
                             pyxel_api=pyxel_api)
        self.se = SoundEffectPlayer(app_root / "se", volume=defaults.se_volume,
                                    pyxel_api=pyxel_api)
        catalog = load_sound_effects(app_root / "audio" / "catalog.json")
        self.bgm_ids = self.bgm.available_ids
        self.pyxel_sounds = pyxel_sound_options(catalog)
        self.wav_sounds = wav_sound_options(app_root / "se")
        self.bgm_index = 0
        self.sound_index = 0
        self.wav_index = 0
        self.use_wav = False

    @property
    def se_options(self) -> tuple[SoundOption, ...]:
        return self.wav_sounds if self.use_wav else self.pyxel_sounds

    @property
    def se_index(self) -> int:
        return self.wav_index if self.use_wav else self.sound_index

    def select_bgm(self, index: int) -> None:
        self.bgm_index = max(0, min(index, len(self.bgm_ids) - 1))
        if self.bgm.is_playing:
            self.play_bgm()

    def select_se(self, index: int) -> None:
        index = max(0, min(index, len(self.se_options) - 1))
        if self.use_wav:
            self.wav_index = index
        else:
            self.sound_index = index

    def set_volume(self, *, bgm: bool, volume: int) -> None:
        player = self.bgm if bgm else self.se
        player.set_volume(max(0, min(volume, 4)))

    def play_bgm(self) -> None:
        if not self.bgm_ids:
            raise AudioResourceError("BGMがありません。app/audioへOGGを配置してください。")
        self.bgm.play(self.bgm_ids[self.bgm_index], loop=True)

    def play_se(self) -> None:
        if not self.se_options:
            raise AudioResourceError("WAVがありません。app/seへWAVを配置してください。")
        self.se.play(self.se_options[self.se_index].definition)

    def stop_se(self) -> None:
        self._pyxel.stop(SE_CHANNEL)

    def close(self) -> None:
        self.bgm.stop()
        self.stop_se()
