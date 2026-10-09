"""Interactive Pyxel UI for editing ordinary spell effects."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Callable

import pyxel

from app.rendering import SpellEffectRenderer, create_default_palette_shifter
from app.audio_catalog import SoundEffectDefinition
from app.resources import (
    AudioResourceError,
    SoundEffectPlayer,
    FontResources,
    ImageResourceError,
    ImageResources,
    TRANSPARENT_INDEX,
    reload_se_catalog,
)
from app.spell_effect import (
    MAX_EFFECT_OFFSET,
    MIN_EFFECT_OFFSET,
    SpellEffectDefinition,
    SpellEffectPlayer,
)
from app.state import Language
from scripts.spell_effect_pipeline import SpellEffectSourceError
from tools.spell_effect_editor.model import EditorSpell, SpellEffectEditorStore


SCREEN_WIDTH = 512
SCREEN_HEIGHT = 320
TOP_PANEL_HEIGHT = 240
PREVIEW_WIDTH = 256
SPELL_LIST_X = 256
SPELL_LIST_WIDTH = 104
SETTINGS_X = 360
SETTINGS_WIDTH = 152
FPS = 60
DISPLAY_SCALE = 2
WINDOW_TITLE = "Dungeon Antiqua ZERO Spell Effect Editor"
BACKGROUND_IMAGE_ID = "background/bg_nector"
CHARACTER_IMAGE_ID = "characters/ch_battle"
VISIBLE_SPELL_COUNT = 17
SPELL_ROW_HEIGHT = 12
SPELL_LIST_Y = 28
STRIP_HEADER_Y = 240
STRIP_Y = 256
STRIP_WIDTH = SCREEN_WIDTH
MAX_SE_ID_LENGTH = 28
FLASH_DIALOG_X = 96
FLASH_DIALOG_Y = 42
FLASH_DIALOG_WIDTH = 320
FLASH_DIALOG_HEIGHT = 204
FLASH_SWATCH_SIZE = 12
FLASH_GROUP_ROW_HEIGHT = 14
FLASH_GROUPS_PER_COLUMN = 8
STATUS_FRAME_COUNT = 240
BUTTON_TEXT_COLOR = 5
BUTTON_FRAME_COLOR = 3
BUTTON_ACTIVE_COLOR = 13
PANEL_COLOR = 0
PANEL_BORDER_COLOR = 2
WARNING_COLOR = 33
ERROR_COLOR = 14
SUCCESS_COLOR = 21
FILTER_ORDER = (None, "mystic", "sacred", "nether", "item")
FILTER_LABELS = {
    None: "ALL",
    "mystic": "MYS",
    "sacred": "SAC",
    "nether": "NET",
    "item": "ITEM",
}


@dataclass(frozen=True)
class Button:
    id: str
    x: int
    y: int
    width: int
    height: int
    label: str
    active: bool = False

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height


@dataclass(frozen=True)
class ColorSwatch:
    color: int
    x: int
    y: int
    size: int = FLASH_SWATCH_SIZE

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.size and self.y <= y < self.y + self.size


@dataclass(frozen=True)
class PreviewTarget:
    key: str
    name: str
    image_id: str
    source_x: int
    source_y: int
    width: int
    height: int
    side: str


@dataclass
class SoundRegistrationDraft:
    se_id: str
    sound: int = 0
    use_wav: bool = False
    wav_index: int = 0
    original_se_id: str | None = None


class SpellEffectEditor:
    """Own editor-only selection, preview, and input state."""

    def __init__(self, project_root: Path, *, content_root: Path | None = None) -> None:
        self.project_root = project_root.resolve()
        self.content_root = (content_root or self.project_root / "content").resolve()
        pyxel.init(
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            title=WINDOW_TITLE,
            fps=FPS,
            quit_key=pyxel.KEY_NONE,
            display_scale=DISPLAY_SCALE,
        )
        pyxel.load(str(self.project_root / "app" / "assets.pyxres"))
        pyxel.load_pal(str(self.project_root / "app" / "assets.pyxpal"))
        pyxel.mouse(True)

        self.palette_shifter = create_default_palette_shifter()
        self.images = ImageResources(self.project_root / "app" / "images")
        self.renderer = SpellEffectRenderer(self.images, self.palette_shifter)
        self.store = SpellEffectEditorStore(
            self.project_root,
            content_root=self.content_root,
        )
        self.se_player = SoundEffectPlayer(self.store.se_dir)
        self.se_player.preload(self.store.sound_effects)
        self.japanese_font = FontResources(
            self.project_root / "app" / "fonts"
        ).font_for(Language.JAPANESE)
        self.background = self.images.image(BACKGROUND_IMAGE_ID)
        self.targets = self._load_targets()
        if not self.targets["ally"] or not self.targets["enemy"]:
            raise ImageResourceError(
                "プレビュー用のキャラクターまたはモンスター画像がありません。"
            )

        self.filter_index = 0
        self.selected_spell_index = 0
        self.spell_scroll = 0
        self.target_side = "enemy"
        self.target_indexes = {"ally": 0, "enemy": 0}
        self.strip_scroll = 0
        self.playing = False
        self.paused = False
        self.looping = True
        self.debug_visible = True
        self.exit_confirmation = False
        self.flash_picker_open = False
        self.sound_registration: SoundRegistrationDraft | None = None
        self.status_message = ""
        self.status_color = BUTTON_TEXT_COLOR
        self.status_frames = 0
        self._hold_start_frame = False
        self._player = self._new_player()
        self.renderer.prepare(self._player)

    @property
    def filtered_spells(self) -> tuple[EditorSpell, ...]:
        selected_type = FILTER_ORDER[self.filter_index]
        return tuple(
            spell
            for spell in self.store.spells
            if spell.on_battle and (selected_type is None or spell.type == selected_type)
        )

    @property
    def selected_spell(self) -> EditorSpell:
        spells = self.filtered_spells
        if not spells:
            raise SpellEffectSourceError("選択中の分類に戦闘用呪文がありません。")
        index = max(0, min(self.selected_spell_index, len(spells) - 1))
        return spells[index]

    @property
    def definition(self) -> SpellEffectDefinition:
        return self.store.preview_definition(self.selected_spell.key)

    @property
    def target(self) -> PreviewTarget:
        options = self.targets[self.target_side]
        index = self.target_indexes[self.target_side] % len(options)
        return options[index]

    def _load_json_array(self, filename: str) -> list[dict[str, object]]:
        path = self.content_root / "data" / filename
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SpellEffectSourceError(f"プレビュー用データを読めません: {path}: {error}") from error
        if not isinstance(document, list) or not all(isinstance(item, dict) for item in document):
            raise SpellEffectSourceError(f"プレビュー用データはobject配列が必要です: {path}")
        return document

    @staticmethod
    def _display_name(record: dict[str, object]) -> str:
        japanese = record.get("name_ja")
        english = record.get("name_en")
        if isinstance(japanese, str) and japanese and japanese != "-":
            return japanese
        return english if isinstance(english, str) else "?"

    def _load_targets(self) -> dict[str, tuple[PreviewTarget, ...]]:
        available = set(self.images.ids)
        character_entry = self.images.entry(CHARACTER_IMAGE_ID)
        allies: list[PreviewTarget] = []
        for record in self._load_json_array("characters.json"):
            key = record.get("name_en")
            sprite = record.get("battle_sprite")
            if (
                not isinstance(key, str)
                or isinstance(sprite, bool)
                or not isinstance(sprite, int)
                or sprite < 0
                or (sprite + 1) * 32 > character_entry.height
            ):
                continue
            allies.append(
                PreviewTarget(
                    key,
                    self._display_name(record),
                    CHARACTER_IMAGE_ID,
                    0,
                    sprite * 32,
                    16,
                    32,
                    "ally",
                )
            )

        enemies: list[PreviewTarget] = []
        for record in self._load_json_array("monsters.json"):
            key = record.get("name_en")
            image_value = record.get("image_id")
            width = record.get("width")
            height = record.get("height")
            if (
                not isinstance(key, str)
                or isinstance(image_value, bool)
                or not isinstance(image_value, (str, int))
                or isinstance(width, bool)
                or not isinstance(width, int)
                or isinstance(height, bool)
                or not isinstance(height, int)
            ):
                continue
            image_id = f"monsters/{image_value}"
            if image_id not in available:
                continue
            entry = self.images.entry(image_id)
            if width <= 0 or height <= 0 or width > entry.width or height > entry.height:
                continue
            enemies.append(
                PreviewTarget(
                    key,
                    self._display_name(record),
                    image_id,
                    0,
                    0,
                    width,
                    height,
                    "enemy",
                )
            )
        return {"ally": tuple(allies), "enemy": tuple(enemies)}

    def _target_rect(self) -> tuple[int, int, int, int]:
        target = self.target
        center_x = 184 if target.side == "ally" else 92
        center_y = 118
        return (
            center_x - target.width // 2,
            center_y - target.height // 2,
            target.width,
            target.height,
        )

    def _new_player(self, *, elapsed_frame: int = 0) -> SpellEffectPlayer:
        x, y, width, height = self._target_rect()
        player = SpellEffectPlayer(
            self.definition,
            anchor_x=x + width // 2,
            anchor_y=y + height // 2,
            target_side=self.target_side,
        )
        for _ in range(min(elapsed_frame, player.definition.total_frames)):
            player.update()
        return player

    def _refresh_player(self, *, restart_if_playing: bool = True) -> None:
        elapsed = 0 if self.playing and restart_if_playing else self._player.elapsed_frame
        self._player = self._new_player(elapsed_frame=elapsed)
        self._hold_start_frame = bool(self.playing and restart_if_playing)
        self.renderer.prepare(self._player)

    def _set_status(self, message: str, color: int = BUTTON_TEXT_COLOR) -> None:
        self.status_message = message
        self.status_color = color
        self.status_frames = STATUS_FRAME_COUNT

    def _play_start_sound(self) -> None:
        se_id = self._player.take_start_sound()
        if se_id is None:
            return
        try:
            self._play_registered_sound(se_id)
        except (AudioResourceError, ValueError) as error:
            self._set_status(str(error), ERROR_COLOR)

    def _play_registered_sound(self, se_id: str) -> None:
        self.se_player.play(self.store.sound_effect(se_id))

    def _open_sound_registration(self) -> None:
        self.status_frames = 0
        se_id = self.definition.se_id
        if se_id is not None:
            entry = self.store.sound_effect(se_id)
            self.sound_registration = SoundRegistrationDraft(
                se_id,
                sound=entry.sound if entry.sound is not None else 0,
                use_wav=entry.wav is not None,
                wav_index=(
                    self.store.available_wavs.index(entry.wav)
                    if entry.wav is not None else 0
                ),
                original_se_id=se_id,
            )
            return
        suggested = "spell_" + "_".join(self.selected_spell.key.lower().split())
        suffix = 2
        candidate = suggested
        while candidate in self.store.sound_effects:
            candidate = f"{suggested}_{suffix}"
            suffix += 1
        self.sound_registration = SoundRegistrationDraft(candidate[:MAX_SE_ID_LENGTH])

    def _change_sound_registration_number(self, direction: int) -> None:
        draft = self.sound_registration
        if draft is None:
            return
        if draft.use_wav:
            wavs = self.store.available_wavs
            if wavs:
                draft.wav_index = (draft.wav_index + direction) % len(wavs)
            return
        maximum = max(0, len(pyxel.sounds) - 1)
        draft.sound = max(0, min(draft.sound + direction, maximum))

    def _change_sound_registration_source(self) -> None:
        draft = self.sound_registration
        if draft is None:
            return
        if not draft.use_wav and not self.store.available_wavs:
            raise ValueError("app/seに登録できるWAVがありません。")
        draft.use_wav = not draft.use_wav

    def _registration_definition(self) -> SoundEffectDefinition:
        draft = self.sound_registration
        if draft is None:
            raise ValueError("SE登録画面が開いていません。")
        if draft.use_wav:
            wavs = self.store.available_wavs
            if not wavs:
                raise ValueError("app/seに登録できるWAVがありません。")
            record = {"wav": wavs[draft.wav_index % len(wavs)]}
        else:
            record = {"sound": draft.sound}
        # Preview remains available while the ID field is being edited.
        return SoundEffectDefinition.from_record("preview", record)

    def _preview_sound_registration(self) -> None:
        draft = self.sound_registration
        if draft is None:
            return
        self.se_player.play(self._registration_definition())

    def _register_sound(self) -> None:
        draft = self.sound_registration
        if draft is None:
            return
        save_sound = (
            self.store.update_sound_effect
            if draft.se_id == draft.original_se_id
            else self.store.register_sound_effect
        )
        save_sound(
            draft.se_id, **self._registration_definition().to_record(),
        )
        self.sound_registration = None
        if self.definition.se_id != draft.se_id:
            self._change_definition(se_id=draft.se_id)
        self._set_status(f"SE {draft.se_id}を設定しました", SUCCESS_COLOR)

    def _clear_sound(self) -> None:
        self.sound_registration = None
        self._change_definition(se_id=None)

    def _start_playback(self) -> None:
        self.playing = True
        self.paused = False
        self._player = self._new_player()
        self._hold_start_frame = True
        self.renderer.prepare(self._player)
        self._play_start_sound()

    def _step_playback(self) -> None:
        self.playing = False
        self.paused = True
        if self._player.completed:
            self._player.restart()
        else:
            self._player.update()
        self.renderer.prepare(self._player)

    def _reset_preview(self) -> None:
        self.playing = False
        self.paused = False
        self._player = self._new_player()
        self._hold_start_frame = False
        self.renderer.prepare(self._player)

    def _update_playback(self) -> None:
        if not self.playing or self.paused:
            return
        if self._hold_start_frame:
            self._hold_start_frame = False
            return
        self._player.update()
        if self._player.completed and self.looping:
            self._player.restart()
            self._hold_start_frame = False
            self._play_start_sound()
        elif self._player.completed:
            self.playing = False
        self.renderer.prepare(self._player)

    def _select_spell(self, index: int) -> None:
        spells = self.filtered_spells
        if not spells:
            return
        new_index = max(0, min(index, len(spells) - 1))
        if new_index == self.selected_spell_index:
            return
        self.selected_spell_index = new_index
        self.strip_scroll = 0
        self._keep_spell_visible()
        self._refresh_player()

    def _keep_spell_visible(self) -> None:
        if self.selected_spell_index < self.spell_scroll:
            self.spell_scroll = self.selected_spell_index
        if self.selected_spell_index >= self.spell_scroll + VISIBLE_SPELL_COUNT:
            self.spell_scroll = self.selected_spell_index - VISIBLE_SPELL_COUNT + 1

    def _cycle_filter(self, direction: int = 1) -> None:
        current_key = self.selected_spell.key
        self.filter_index = (self.filter_index + direction) % len(FILTER_ORDER)
        spells = self.filtered_spells
        self.selected_spell_index = next(
            (index for index, spell in enumerate(spells) if spell.key == current_key),
            0,
        )
        self.spell_scroll = 0
        self.strip_scroll = 0
        self._refresh_player()

    def _ensure_definition(self) -> SpellEffectDefinition:
        definition = self.definition
        if self.store.definition(definition.spell_key) is None:
            self.store.set_definition(definition)
        return definition

    def _change_definition(self, **changes: object) -> None:
        definition = self._ensure_definition()
        updated = replace(definition, **changes)
        self.store.set_definition(updated)
        self._refresh_player()

    def _cycle_image(self, direction: int) -> None:
        image_ids = tuple(self.store.catalogs.images)
        image_ids = tuple(
            image
            for image in ("effects/spells32", "effects/spells64")
            if image in image_ids
        )
        current = self.definition.image_id
        index = (image_ids.index(current) + direction) % len(image_ids)
        image_id = image_ids[index]
        entry = self.store.catalogs.images[image_id]
        size = 32 if image_id.endswith("32") else 64
        self.strip_scroll = 0
        self._change_definition(
            image_id=image_id,
            row=min(self.definition.row, entry.height // size - 1),
            frame_count=min(self.definition.frame_count, entry.width // size),
        )

    def _change_row(self, direction: int) -> None:
        definition = self.definition
        entry = self.store.catalogs.images[definition.image_id]
        maximum = entry.height // definition.cell_size - 1
        self._change_definition(row=max(0, min(definition.row + direction, maximum)))

    def _change_frame_count(self, direction: int) -> None:
        definition = self.definition
        entry = self.store.catalogs.images[definition.image_id]
        maximum = entry.width // definition.cell_size
        self._change_definition(
            frame_count=max(1, min(definition.frame_count + direction, maximum))
        )

    def _change_speed(self, direction: int) -> None:
        definition = self.definition
        self._change_definition(
            frames_per_pattern=max(1, min(definition.frames_per_pattern + direction, 60))
        )

    def _change_offset(self, axis: str, direction: int) -> None:
        definition = self.definition
        offset_x, offset_y = definition.offset_for(self.target_side)
        field = f"{self.target_side}_offset_{axis}"
        current = offset_x if axis == "x" else offset_y
        self._change_definition(
            **{
                field: max(
                    MIN_EFFECT_OFFSET,
                    min(MAX_EFFECT_OFFSET, current + direction),
                )
            }
        )

    def _cycle_flash(self, direction: int) -> None:
        choices: tuple[int | None, ...] = (
            None,
            *(
                index
                for index in range(self.store.catalogs.palette_color_count)
                if index != self.store.catalogs.transparent_index
            ),
        )
        current = self.definition.flash_color
        index = (choices.index(current) + direction) % len(choices)
        self._change_definition(flash_color=choices[index])

    def _flash_color_swatches(self) -> tuple[ColorSwatch, ...]:
        color_count = self.store.catalogs.palette_color_count
        swatches = [ColorSwatch(0, 142, 76)] if color_count > 0 else []
        grouped_colors = tuple(
            color
            for color in range(2, color_count)
            if color != self.store.catalogs.transparent_index
        )
        for group_index, start in enumerate(range(0, len(grouped_colors), 4)):
            column = group_index // FLASH_GROUPS_PER_COLUMN
            row = group_index % FLASH_GROUPS_PER_COLUMN
            base_x = 142 + column * 158
            y = 96 + row * FLASH_GROUP_ROW_HEIGHT
            for shade, color in enumerate(grouped_colors[start : start + 4]):
                swatches.append(
                    ColorSwatch(color, base_x + shade * FLASH_SWATCH_SIZE, y)
                )
        return tuple(swatches)

    def _select_flash_color(self, color: int | None) -> None:
        self._change_definition(flash_color=color)
        self.flash_picker_open = False

    def _cycle_target(self, direction: int) -> None:
        options = self.targets[self.target_side]
        self.target_indexes[self.target_side] = (
            self.target_indexes[self.target_side] + direction
        ) % len(options)
        self._refresh_player()

    def _toggle_target_side(self) -> None:
        self.target_side = "ally" if self.target_side == "enemy" else "enemy"
        self._refresh_player()

    def _change_strip_scroll(self, direction: int) -> None:
        definition = self.definition
        entry = self.store.catalogs.images[definition.image_id]
        maximum = entry.width // definition.cell_size
        visible_count = max(1, STRIP_WIDTH // definition.cell_size)
        maximum_scroll = max(0, maximum - visible_count)
        self.strip_scroll = max(
            0,
            min(self.strip_scroll + direction, maximum_scroll),
        )

    def _save(self) -> bool:
        try:
            self.se_player.preload(self.store.sound_effects)
            self.store.save()
            reload_se_catalog(self.store.audio_catalog_path)
        except (
            OSError,
            AudioResourceError,
            SpellEffectSourceError,
            ValueError,
        ) as error:
            self._set_status(str(error), ERROR_COLOR)
            return False
        self._set_status("保存しました", SUCCESS_COLOR)
        return True

    def _request_exit(self) -> None:
        if self.store.dirty:
            self.exit_confirmation = True
        else:
            pyxel.quit()

    def _buttons(self) -> tuple[Button, ...]:
        definition = self.definition
        configured = self.store.definition(self.selected_spell.key) is not None
        buttons = [
            Button("filter", 258, 14, 40, 11, FILTER_LABELS[FILTER_ORDER[self.filter_index]]),
            Button("target_side", 2, 2, 36, 11, self.target_side.upper()),
            Button("target_prev", 40, 2, 12, 11, "<"),
            Button("target_next", 54, 2, 12, 11, ">"),
            Button("debug", 68, 2, 30, 11, "GUIDE", self.debug_visible),
            Button("play", 2, 224, 30, 12, "PLAY", self.playing and not self.paused),
            Button("pause", 34, 224, 34, 12, "PAUSE", self.paused),
            Button("loop", 70, 224, 30, 12, "LOOP", self.looping),
            Button("step", 102, 224, 30, 12, "STEP"),
            Button("reset", 134, 224, 34, 12, "RESET"),
            Button("sheet_prev", 440, 20, 12, 11, "<"),
            Button("sheet_next", 498, 20, 12, 11, ">"),
            Button("row_prev", 440, 34, 12, 11, "-"),
            Button("row_next", 498, 34, 12, 11, "+"),
            Button("count_prev", 440, 48, 12, 11, "-"),
            Button("count_next", 498, 48, 12, 11, "+"),
            Button("speed_prev", 440, 62, 12, 11, "-"),
            Button("speed_next", 498, 62, 12, 11, "+"),
            Button("x_prev", 440, 76, 12, 11, "-"),
            Button("x_next", 498, 76, 12, 11, "+"),
            Button("y_prev", 440, 90, 12, 11, "-"),
            Button("y_next", 498, 90, 12, 11, "+"),
            Button("flash_prev", 440, 104, 12, 11, "<"),
            Button("flash_picker", 454, 104, 42, 11, "PICK"),
            Button("flash_next", 498, 104, 12, 11, ">"),
            Button(
                "se_select", 390, 116, 120, 11,
                definition.se_id[:MAX_SE_ID_LENGTH] if definition.se_id else "NONE",
            ),
            Button("set", 362, 142, 40, 12, "UNSET" if configured else "SET"),
            Button("save", 440, 142, 38, 12, "SAVE", self.store.dirty),
            Button("strip_prev", 480, 242, 14, 12, "<"),
            Button("strip_next", 496, 242, 14, 12, ">"),
        ]
        if self.sound_registration is not None:
            buttons.extend(
                (
                    Button("sound_source_prev", 260, 130, 16, 12, "<"),
                    Button("sound_source_next", 330, 130, 16, 12, ">"),
                    Button("sound_number_prev", 260, 146, 16, 12, "-"),
                    Button("sound_number_next", 330, 146, 16, 12, "+"),
                    Button("sound_key_clear", 346, 108, 42, 12, "CLEAR"),
                    Button("sound_preview", 128, 174, 64, 14, "PREVIEW"),
                    Button("sound_register", 198, 174, 52, 14, "APPLY"),
                    Button("sound_none", 256, 174, 48, 14, "NONE"),
                    Button("sound_cancel", 310, 174, 64, 14, "CANCEL"),
                )
            )
        if self.flash_picker_open:
            buttons.extend(
                (
                    Button(
                        "flash_dialog_none",
                        244,
                        218,
                        52,
                        14,
                        "NONE",
                        self.definition.flash_color is None,
                    ),
                    Button("flash_dialog_cancel", 302, 218, 62, 14, "CANCEL"),
                )
            )
        if self.exit_confirmation:
            buttons.extend(
                (
                    Button("exit_save", 170, 122, 52, 14, "SAVE"),
                    Button("exit_discard", 226, 122, 60, 14, "DISCARD"),
                    Button("exit_cancel", 290, 122, 52, 14, "CANCEL"),
                )
            )
        return tuple(buttons)

    def _activate(self, button_id: str) -> None:
        actions: dict[str, Callable[[], None]] = {
            "filter": self._cycle_filter,
            "target_side": self._toggle_target_side,
            "target_prev": lambda: self._cycle_target(-1),
            "target_next": lambda: self._cycle_target(1),
            "debug": lambda: setattr(self, "debug_visible", not self.debug_visible),
            "play": self._start_playback,
            "pause": lambda: setattr(self, "paused", not self.paused),
            "loop": lambda: setattr(self, "looping", not self.looping),
            "step": self._step_playback,
            "reset": self._reset_preview,
            "sheet_prev": lambda: self._cycle_image(-1),
            "sheet_next": lambda: self._cycle_image(1),
            "row_prev": lambda: self._change_row(-1),
            "row_next": lambda: self._change_row(1),
            "count_prev": lambda: self._change_frame_count(-1),
            "count_next": lambda: self._change_frame_count(1),
            "speed_prev": lambda: self._change_speed(-1),
            "speed_next": lambda: self._change_speed(1),
            "x_prev": lambda: self._change_offset("x", -1),
            "x_next": lambda: self._change_offset("x", 1),
            "y_prev": lambda: self._change_offset("y", -1),
            "y_next": lambda: self._change_offset("y", 1),
            "flash_prev": lambda: self._cycle_flash(-1),
            "flash_picker": lambda: setattr(self, "flash_picker_open", True),
            "flash_next": lambda: self._cycle_flash(1),
            "se_select": self._open_sound_registration,
            "set": lambda: (
                self.store.remove_definition(self.selected_spell.key)
                if self.store.definition(self.selected_spell.key) is not None
                else self.store.set_definition(self.definition)
            ),
            "save": self._save,
            "strip_prev": lambda: self._change_strip_scroll(-1),
            "strip_next": lambda: self._change_strip_scroll(1),
            "sound_number_prev": lambda: self._change_sound_registration_number(-1),
            "sound_number_next": lambda: self._change_sound_registration_number(1),
            "sound_source_prev": self._change_sound_registration_source,
            "sound_source_next": self._change_sound_registration_source,
            "sound_key_clear": lambda: setattr(
                self.sound_registration, "se_id", ""
            ),
            "sound_preview": self._preview_sound_registration,
            "sound_register": self._register_sound,
            "sound_none": self._clear_sound,
            "sound_cancel": lambda: setattr(self, "sound_registration", None),
            "flash_dialog_none": lambda: self._select_flash_color(None),
            "flash_dialog_cancel": lambda: setattr(self, "flash_picker_open", False),
            "exit_save": lambda: pyxel.quit() if self._save() else None,
            "exit_discard": pyxel.quit,
            "exit_cancel": lambda: setattr(self, "exit_confirmation", False),
        }
        action = actions.get(button_id)
        if action is not None:
            try:
                action()
            except (AudioResourceError, ValueError) as error:
                self._set_status(str(error), ERROR_COLOR)
            if button_id == "set":
                self._refresh_player()

    def _handle_mouse(self) -> None:
        wheel = getattr(pyxel, "mouse_wheel", 0)
        if (
            wheel
            and not (self.exit_confirmation or self.flash_picker_open or self.sound_registration is not None)
            and SPELL_LIST_X <= pyxel.mouse_x < SETTINGS_X
        ):
            self._select_spell(self.selected_spell_index - int(wheel))
        if not pyxel.btnp(pyxel.MOUSE_BUTTON_LEFT):
            return
        if self.exit_confirmation:
            for button in self._buttons():
                if button.id.startswith("exit_") and button.contains(pyxel.mouse_x, pyxel.mouse_y):
                    self._activate(button.id)
                    return
            return
        if self.flash_picker_open:
            for swatch in self._flash_color_swatches():
                if swatch.contains(pyxel.mouse_x, pyxel.mouse_y):
                    self._select_flash_color(swatch.color)
                    return
            for button in self._buttons():
                if button.id.startswith("flash_dialog_") and button.contains(
                    pyxel.mouse_x, pyxel.mouse_y
                ):
                    self._activate(button.id)
                    return
            return
        if self.sound_registration is not None:
            for button in self._buttons():
                if button.id.startswith("sound_") and button.contains(
                    pyxel.mouse_x, pyxel.mouse_y
                ):
                    self._activate(button.id)
                    return
            return
        if (
            SPELL_LIST_X <= pyxel.mouse_x < SETTINGS_X
            and pyxel.mouse_y >= SPELL_LIST_Y
        ):
            row = (pyxel.mouse_y - SPELL_LIST_Y) // SPELL_ROW_HEIGHT
            index = self.spell_scroll + row
            if index < len(self.filtered_spells):
                self._select_spell(index)
                return
        for button in self._buttons():
            if button.contains(pyxel.mouse_x, pyxel.mouse_y):
                self._activate(button.id)
                return
        self._handle_strip_click()

    def _handle_strip_click(self) -> None:
        definition = self.definition
        size = definition.cell_size
        if not (
            0 <= pyxel.mouse_x < STRIP_WIDTH
            and STRIP_Y <= pyxel.mouse_y < STRIP_Y + size
        ):
            return
        column = self.strip_scroll + pyxel.mouse_x // size
        entry = self.store.catalogs.images[definition.image_id]
        if column < entry.width // size:
            self._change_definition(frame_count=column + 1)

    def _handle_keyboard(self) -> None:
        if self.sound_registration is not None:
            draft = self.sound_registration
            typed = getattr(pyxel, "input_text", "")
            for character in typed:
                if (
                    len(draft.se_id) < MAX_SE_ID_LENGTH
                    and character.isascii()
                    and (
                        character.islower()
                        or character.isdigit()
                        or character == "_"
                    )
                ):
                    draft.se_id += character
            if pyxel.btnp(pyxel.KEY_BACKSPACE) and draft.se_id:
                draft.se_id = draft.se_id[:-1]
            if pyxel.btnp(pyxel.KEY_UP, hold=20, repeat=4):
                self._change_sound_registration_number(1)
            if pyxel.btnp(pyxel.KEY_DOWN, hold=20, repeat=4):
                self._change_sound_registration_number(-1)
            if pyxel.btnp(pyxel.KEY_LEFT):
                self._activate("sound_source_prev")
            if pyxel.btnp(pyxel.KEY_RIGHT):
                self._activate("sound_source_next")
            if pyxel.btnp(pyxel.KEY_RETURN):
                self._activate("sound_register")
            elif pyxel.btnp(pyxel.KEY_ESCAPE):
                self._activate("sound_cancel")
            return
        if self.flash_picker_open:
            if pyxel.btnp(pyxel.KEY_N):
                self._activate("flash_dialog_none")
            elif pyxel.btnp(pyxel.KEY_ESCAPE):
                self._activate("flash_dialog_cancel")
            return
        if self.exit_confirmation:
            if pyxel.btnp(pyxel.KEY_S):
                self._activate("exit_save")
            elif pyxel.btnp(pyxel.KEY_D):
                self._activate("exit_discard")
            elif pyxel.btnp(pyxel.KEY_X) or pyxel.btnp(pyxel.KEY_ESCAPE):
                self._activate("exit_cancel")
            return
        if pyxel.btnp(pyxel.KEY_UP, hold=20, repeat=4):
            self._select_spell(self.selected_spell_index - 1)
        if pyxel.btnp(pyxel.KEY_DOWN, hold=20, repeat=4):
            self._select_spell(self.selected_spell_index + 1)
        if pyxel.btnp(pyxel.KEY_Z) or pyxel.btnp(pyxel.KEY_RETURN):
            self._start_playback()
        if pyxel.btnp(pyxel.KEY_SPACE):
            self.paused = not self.paused
        if pyxel.btnp(pyxel.KEY_L):
            self.looping = not self.looping
        if pyxel.btnp(pyxel.KEY_T):
            self._toggle_target_side()
        if pyxel.btnp(pyxel.KEY_COMMA):
            self._cycle_target(-1)
        if pyxel.btnp(pyxel.KEY_PERIOD):
            self._cycle_target(1)
        if pyxel.btnp(pyxel.KEY_G):
            self.debug_visible = not self.debug_visible
        control = pyxel.btn(pyxel.KEY_LCTRL) or pyxel.btn(pyxel.KEY_RCTRL)
        if control and pyxel.btnp(pyxel.KEY_S):
            self._save()
        if pyxel.btnp(pyxel.KEY_Q) or pyxel.btnp(pyxel.KEY_ESCAPE):
            self._request_exit()

    def update(self) -> None:
        if self.status_frames > 0:
            self.status_frames -= 1
        self._handle_keyboard()
        self._handle_mouse()
        self._update_playback()

    def _draw_button(self, button: Button) -> None:
        fill = 7 if button.active else PANEL_COLOR
        frame = BUTTON_ACTIVE_COLOR if button.active else BUTTON_FRAME_COLOR
        pyxel.rect(button.x, button.y, button.width, button.height, fill)
        pyxel.rectb(button.x, button.y, button.width, button.height, frame)
        text_width = len(button.label) * 4
        pyxel.text(
            button.x + max(2, (button.width - text_width) // 2),
            button.y + max(2, (button.height - 6) // 2),
            button.label,
            BUTTON_TEXT_COLOR,
        )

    def _draw_target(self) -> None:
        x, y, width, height = self._target_rect()
        target = self.target
        pyxel.blt(
            x,
            y,
            self.images.image(target.image_id),
            target.source_x,
            target.source_y,
            width,
            height,
            TRANSPARENT_INDEX,
        )

    def _draw_preview(self) -> None:
        pyxel.blt(0, 0, self.background, 0, 0, PREVIEW_WIDTH, TOP_PANEL_HEIGHT)
        self.renderer.draw_target(self._player, self._draw_target)
        self.renderer.draw_effect(self._player)
        pyxel.rect(0, 16, PREVIEW_WIDTH, 12, PANEL_COLOR)
        label = f"{self.target_side.upper()} {self.target.key[:22]}"
        pyxel.text(4, 19, label, BUTTON_TEXT_COLOR)
        if self.debug_visible:
            x, y, width, height = self._target_rect()
            anchor_x = x + width // 2
            anchor_y = y + height // 2
            pyxel.line(anchor_x - 3, anchor_y, anchor_x + 3, anchor_y, WARNING_COLOR)
            pyxel.line(anchor_x, anchor_y - 3, anchor_x, anchor_y + 3, WARNING_COLOR)
            destination = self.renderer.destination_rect(self._player)
            if destination is not None:
                dx, dy, dw, dh = destination
                pyxel.rectb(dx, dy, dw, dh, BUTTON_ACTIVE_COLOR)
            pattern = self._player.pattern_index
            info = (
                f"F {self._player.elapsed_frame:03d}/{self.definition.total_frames:03d} "
                f"PAT {pattern if pattern is not None else '-'}"
            )
            pyxel.rect(0, 208, PREVIEW_WIDTH, 12, PANEL_COLOR)
            pyxel.text(4, 211, info, BUTTON_TEXT_COLOR)

    def _draw_spell_list(self) -> None:
        pyxel.rect(SPELL_LIST_X, 0, SPELL_LIST_WIDTH, TOP_PANEL_HEIGHT, PANEL_COLOR)
        pyxel.line(
            SETTINGS_X - 1,
            0,
            SETTINGS_X - 1,
            TOP_PANEL_HEIGHT,
            PANEL_BORDER_COLOR,
        )
        pyxel.text(300, 17, f"{len(self.filtered_spells):02d}", 4)
        visible = self.filtered_spells[
            self.spell_scroll : self.spell_scroll + VISIBLE_SPELL_COUNT
        ]
        for row, spell in enumerate(visible):
            index = self.spell_scroll + row
            y = SPELL_LIST_Y + row * SPELL_ROW_HEIGHT
            configured = self.store.definition(spell.key) is not None
            diagnostics = self.store.diagnostics_for(spell.key)
            if any(item.severity == "error" for item in diagnostics):
                color = ERROR_COLOR
            elif diagnostics:
                color = WARNING_COLOR
            elif configured:
                color = SUCCESS_COLOR
            else:
                color = 4
            if index == self.selected_spell_index:
                pyxel.rect(SPELL_LIST_X + 1, y, SPELL_LIST_WIDTH - 2, 11, 7)
                color = BUTTON_TEXT_COLOR
            prefix = "+" if configured else "-"
            pyxel.text(SPELL_LIST_X + 3, y + 2, f"{prefix}{spell.key[:14]}", color)

    def _draw_value_line(self, label: str, value: str, y: int) -> None:
        pyxel.text(363, y + 2, label, 4)
        pyxel.text(455, y + 2, value[:10], BUTTON_TEXT_COLOR)

    def _draw_settings(self) -> None:
        pyxel.rect(SETTINGS_X, 0, SETTINGS_WIDTH, TOP_PANEL_HEIGHT, PANEL_COLOR)
        spell = self.selected_spell
        pyxel.text(363, 2, spell.key[:23], BUTTON_TEXT_COLOR)
        pyxel.text(363, 10, spell.name[:9], 5, self.japanese_font)
        definition = self.definition
        self._draw_value_line("SHEET", "32" if definition.cell_size == 32 else "64", 18)
        self._draw_value_line("ROW", str(definition.row), 32)
        self._draw_value_line("COUNT", str(definition.frame_count), 46)
        self._draw_value_line("SPEED", str(definition.frames_per_pattern), 60)
        offset_x, offset_y = definition.offset_for(self.target_side)
        side_label = self.target_side.upper()
        self._draw_value_line(f"{side_label} X", str(offset_x), 74)
        self._draw_value_line(f"{side_label} Y", str(offset_y), 88)
        flash_text = "NONE" if definition.flash_color is None else str(definition.flash_color)
        pyxel.text(363, 104, "FLASH", 4)
        pyxel.text(410, 104, flash_text[:4], BUTTON_TEXT_COLOR)
        if definition.flash_color is not None:
            pyxel.rect(426, 104, 10, 9, definition.flash_color)
            pyxel.rectb(426, 104, 10, 9, 5)
        if definition.se_id is None:
            se_detail = "SE NONE"
        else:
            entry = self.store.sound_effect(definition.se_id)
            se_detail = (
                f"WAV {entry.wav}" if entry.wav is not None else f"PYXEL S{entry.sound}"
            )
        pyxel.text(363, 118, "SE", 4)
        pyxel.text(363, 128, se_detail[:36], 4)
        duration = definition.total_frames / FPS
        pyxel.text(363, 135, f"{definition.total_frames}F  {duration:.3f}s", 4)

        diagnostics = self.store.diagnostics_for(spell.key)
        errors = sum(item.severity == "error" for item in diagnostics)
        warnings = sum(item.severity == "warning" for item in diagnostics)
        pyxel.text(480, 145, f"E{errors} W{warnings}", ERROR_COLOR if errors else 4)
        pyxel.text(363, 161, f"{len(self.store.sound_effects)} IDS", 4)
        ally_x, ally_y = definition.offset_for("ally")
        enemy_x, enemy_y = definition.offset_for("enemy")
        pyxel.text(363, 177, f"ALLY  {ally_x:+4d},{ally_y:+4d}", 4)
        pyxel.text(363, 185, f"ENEMY {enemy_x:+4d},{enemy_y:+4d}", 4)

    def _draw_strip(self) -> None:
        definition = self.definition
        entry = self.store.catalogs.images[definition.image_id]
        size = definition.cell_size
        maximum = entry.width // size
        visible_count = max(1, STRIP_WIDTH // size)
        maximum_scroll = max(0, maximum - visible_count)
        scroll = max(0, min(self.strip_scroll, maximum_scroll))
        pyxel.rect(0, STRIP_HEADER_Y, SCREEN_WIDTH, 16, PANEL_COLOR)
        pyxel.line(0, STRIP_HEADER_Y, SCREEN_WIDTH, STRIP_HEADER_Y, PANEL_BORDER_COLOR)
        last_visible = min(maximum - 1, scroll + visible_count - 1)
        pyxel.text(
            3,
            STRIP_HEADER_Y + 5,
            f"ROW {definition.row}  PATTERNS {scroll}-{last_visible}  CLICK=COUNT",
            4,
        )
        pyxel.rect(0, STRIP_Y, STRIP_WIDTH, size, 6)
        source_image = self.images.image(definition.image_id)
        for visible_index in range(visible_count):
            column = scroll + visible_index
            if column >= maximum:
                break
            x = visible_index * size
            pyxel.blt(
                x,
                STRIP_Y,
                source_image,
                column * size,
                definition.row * size,
                size,
                size,
                TRANSPARENT_INDEX,
            )
            selected = column < definition.frame_count
            pyxel.rectb(
                x,
                STRIP_Y,
                size,
                size,
                SUCCESS_COLOR if selected else 3,
            )
            pyxel.text(x + 2, STRIP_Y + 2, str(column), BUTTON_TEXT_COLOR)

    def _draw_status(self) -> None:
        if self.status_message and self.status_frames > 0:
            message = self.status_message
            color = self.status_color
        else:
            diagnostics = self.store.diagnostics_for(self.selected_spell.key)
            if not diagnostics:
                return
            message = diagnostics[0].message
            color = ERROR_COLOR if diagnostics[0].severity == "error" else WARNING_COLOR
        if not message:
            return
        pyxel.rect(0, 196, PREVIEW_WIDTH, 12, PANEL_COLOR)
        pyxel.text(4, 198, message[:28], color, self.japanese_font)

    def _draw_exit_confirmation(self) -> None:
        pyxel.dither(0.5)
        pyxel.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, 0)
        pyxel.dither(1.0)
        pyxel.rect(154, 88, 204, 58, 0)
        pyxel.rectb(154, 88, 204, 58, 5)
        pyxel.text(178, 100, "UNSAVED CHANGES. EXIT?", 5)
        pyxel.text(170, 111, "S:SAVE  D:DISCARD  X:CANCEL", 4)

    def _draw_sound_registration(self) -> None:
        draft = self.sound_registration
        if draft is None:
            return
        pyxel.dither(0.5)
        pyxel.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, 0)
        pyxel.dither(1.0)
        pyxel.rect(106, 76, 296, 136, PANEL_COLOR)
        pyxel.rectb(106, 76, 296, 136, BUTTON_TEXT_COLOR)
        pyxel.text(122, 86, "SELECT SE", BUTTON_TEXT_COLOR)
        pyxel.text(122, 102, "SE ID", 4)
        pyxel.rect(168, 100, 174, 16, 6)
        pyxel.rectb(168, 100, 174, 16, BUTTON_ACTIVE_COLOR)
        pyxel.text(172, 105, draft.se_id[:MAX_SE_ID_LENGTH], BUTTON_TEXT_COLOR)
        if pyxel.frame_count % 60 < 30:
            cursor_x = 172 + min(len(draft.se_id), MAX_SE_ID_LENGTH) * 4
            pyxel.line(cursor_x, 104, cursor_x, 111, WARNING_COLOR)
        pyxel.text(122, 133, "TYPE", 4)
        pyxel.text(284, 133, "WAV" if draft.use_wav else "PYXEL", BUTTON_TEXT_COLOR)
        pyxel.text(122, 149, "FILE" if draft.use_wav else "SOUND", 4)
        wavs = self.store.available_wavs
        value = f"{draft.sound:02d}"
        if draft.use_wav:
            value = wavs[draft.wav_index % len(wavs)] if wavs else "NONE"
        pyxel.text(172, 149, value[:20], BUTTON_TEXT_COLOR)
        if self.status_message and self.status_frames > 0:
            pyxel.text(
                122,
                192,
                self.status_message[:28],
                ERROR_COLOR,
                self.japanese_font,
            )
        else:
            pyxel.text(122, 193, "Up/Down=File/Sound  Left/Right=Type", 3)
            pyxel.text(122, 201, "Type key / Enter=apply / Esc=cancel", 3)

    def _draw_flash_picker(self) -> None:
        pyxel.dither(0.5)
        pyxel.rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, 0)
        pyxel.dither(1.0)
        pyxel.rect(
            FLASH_DIALOG_X,
            FLASH_DIALOG_Y,
            FLASH_DIALOG_WIDTH,
            FLASH_DIALOG_HEIGHT,
            PANEL_COLOR,
        )
        pyxel.rectb(
            FLASH_DIALOG_X,
            FLASH_DIALOG_Y,
            FLASH_DIALOG_WIDTH,
            FLASH_DIALOG_HEIGHT,
            BUTTON_TEXT_COLOR,
        )
        selected = self.definition.flash_color
        selected_text = "NONE" if selected is None else str(selected)
        pyxel.text(112, 54, "FLASH COLOR PICKER", BUTTON_TEXT_COLOR)
        pyxel.text(300, 54, f"SELECTED {selected_text}", 4)
        pyxel.text(112, 78, "BLACK 00", 4)

        grouped_color_count = max(
            0,
            self.store.catalogs.palette_color_count - 2,
        )
        group_count = (grouped_color_count + 3) // 4
        for group_index in range(group_count):
            column = group_index // FLASH_GROUPS_PER_COLUMN
            row = group_index % FLASH_GROUPS_PER_COLUMN
            first = 2 + group_index * 4
            last = min(first + 3, self.store.catalogs.palette_color_count - 1)
            pyxel.text(
                112 + column * 158,
                99 + row * FLASH_GROUP_ROW_HEIGHT,
                f"{first:02d}-{last:02d}",
                4,
            )

        for swatch in self._flash_color_swatches():
            pyxel.rect(swatch.x, swatch.y, swatch.size, swatch.size, swatch.color)
            pyxel.rectb(swatch.x, swatch.y, swatch.size, swatch.size, 3)
            if swatch.color == selected:
                pyxel.rectb(
                    swatch.x - 1,
                    swatch.y - 1,
                    swatch.size + 2,
                    swatch.size + 2,
                    WARNING_COLOR,
                )
        pyxel.text(112, 224, "Each row: dark > bright", 3)

    def draw(self) -> None:
        self._draw_preview()
        self._draw_spell_list()
        self._draw_settings()
        self._draw_status()
        self._draw_strip()
        for button in self._buttons():
            if not button.id.startswith(("exit_", "sound_", "flash_dialog_")):
                self._draw_button(button)
        if self.sound_registration is not None:
            self._draw_sound_registration()
            for button in self._buttons():
                if button.id.startswith("sound_"):
                    self._draw_button(button)
        elif self.flash_picker_open:
            self._draw_flash_picker()
            for button in self._buttons():
                if button.id.startswith("flash_dialog_"):
                    self._draw_button(button)
        elif self.exit_confirmation:
            self._draw_exit_confirmation()
            for button in self._buttons():
                if button.id.startswith("exit_"):
                    self._draw_button(button)


__all__ = [
    "DISPLAY_SCALE",
    "FPS",
    "PREVIEW_WIDTH",
    "SCREEN_HEIGHT",
    "SCREEN_WIDTH",
    "SpellEffectEditor",
]
