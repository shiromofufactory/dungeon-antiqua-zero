"""Map-free, interactive dungeon simulation using production treasure rules."""

from __future__ import annotations

from collections.abc import Callable

from debug_dungeon import DebugDungeon, DungeonCheckpoint, DungeonProgress, DungeonStep
from input import InputState
from localization import Localizer, format_number
from resources import play_se
from state import Language
from systems.treasure import TreasureOpenStatus
from ui import CursorTarget, DEFAULT_TEXT_COLOR, DISABLED_COLOR, NEGATIVE_COLOR, LocalizedWindowTextFactory, MessageOverlay, WindowFactory
from ui.debug_text import DEBUG_TEXT


class DebugDungeonScene:
    def __init__(self, *, dungeon: DebugDungeon, party, settings, fonts, texts, items,
                 treasure_system, on_battle: Callable[[DungeonStep], bool],
                 on_menu: Callable[[], None], on_exit: Callable[[], None], alert) -> None:
        self.progress = DungeonProgress(dungeon)
        self.party = party
        self.settings = settings
        self.fonts = fonts
        self.texts = texts
        self.items = items
        self.treasure_system = treasure_system
        self.on_battle = on_battle
        self.on_menu = on_menu
        self.on_exit = on_exit
        self.alert = alert
        self.message: MessageOverlay | None = None
        self.notice = ""
        self.waiting_for_battle = False
        self.started = False
        self.placements = LocalizedWindowTextFactory.from_language(fonts, Language.JAPANESE)
        self.windows = WindowFactory(fonts.font_for(Language.JAPANESE))
        self.refresh()

    @property
    def dungeon(self) -> DebugDungeon:
        return self.progress.dungeon

    def start(self) -> None:
        # Named battles always offer preparation before the first encounter too.
        if self.progress.current is not None and self.progress.current.type != "event_battle":
            self.advance()

    def resume(self, checkpoint: DungeonCheckpoint) -> None:
        self.progress = DungeonProgress.from_checkpoint(self.dungeon, checkpoint)
        self.started = True
        self.refresh()

    def refresh(self) -> None:
        p = self.progress
        step = p.current
        placements = [
            self.placements.create(self.dungeon.name, 4, 3),
            self.placements.create(DEBUG_TEXT.dungeon_progress.format(
                current=min(p.index + 1, len(self.dungeon.steps)), total=len(self.dungeon.steps)), 4, 8),
            self.placements.create(DEBUG_TEXT.dungeon_remaining.format(count=p.remaining_battles), 4, 12),
        ]
        if p.fade_active:
            placements.append(self.placements.create(DEBUG_TEXT.dungeon_fade_active, 30, 12))
        if step is not None and step.type == "event_battle":
            summary = DEBUG_TEXT.dungeon_warning
        elif step is None:
            summary = DEBUG_TEXT.dungeon_finished
        elif step.type == "random_encounter":
            summary = DEBUG_TEXT.dungeon_random.format(current=p.completed_in_step + 1, total=step.count)
        else:
            summary = ""
        placements.extend((self.placements.create(summary, 4, 17,
                               color=NEGATIVE_COLOR if step is not None and step.type == "event_battle" else DEFAULT_TEXT_COLOR),
                           self.placements.create(self.notice, 4, 21)))
        localizer = Localizer(self.settings.language)
        member_texts = LocalizedWindowTextFactory.from_language(self.fonts, self.settings.language)
        placements.extend((self.placements.create("HP", 32, 25), self.placements.create("MP", 47, 25)))
        for index, member in enumerate(self.party):
            name = member.definition.localized_name(localizer)
            y = 28 + index * 3
            placements.extend((member_texts.create(name, 4, y),
                               self.placements.create(str(member.hp), 32, y),
                               self.placements.create(str(member.mp), 47, y)))
        choices = (("next", DEBUG_TEXT.dungeon_next), ("exit", DEBUG_TEXT.dungeon_exit),
                   ("menu", DEBUG_TEXT.dungeon_menu))
        for index, (key, label) in enumerate(choices):
            placements.append(self.placements.create(label, 6, 47 + index * 4,
                color=DISABLED_COLOR if key == "next" and step is None else DEFAULT_TEXT_COLOR))
        self.window = self.windows.create(0, 0, 64, 60, tuple(placements), opened=True)
        self.cursor = self.window.set_cursor(tuple(
            CursorTarget(3, 47 + index * 4, key=key)
            for index, (key, _) in enumerate(choices) if key != "next" or step is not None
        ))

    def advance(self) -> None:
        step = self.progress.current
        if step is None or self.waiting_for_battle:
            return
        if step.type == "treasure":
            self._open_treasure(step)
            self.progress.complete()
            self.refresh()
        elif self.progress.skip_random_battle():
            self.progress.complete()
            self.notice = DEBUG_TEXT.dungeon_skipped
            self.refresh()
        elif self.on_battle(step):
            self.waiting_for_battle = True
        else:
            self.notice = DEBUG_TEXT.dungeon_error
            self.alert.start()
            self.refresh()

    def complete_battle(self) -> None:
        if not self.waiting_for_battle:
            raise RuntimeError("debug dungeon has no active battle")
        self.waiting_for_battle = False
        self.progress.complete()
        self.notice = DEBUG_TEXT.dungeon_battle_finished
        self.refresh()

    def _open_treasure(self, step: DungeonStep) -> None:
        status = self.treasure_system.open(self.dungeon.treasure_map_id, step.treasure_actor(), members=self.party)
        if status is TreasureOpenStatus.ALREADY_OPENED:
            self.notice = DEBUG_TEXT.dungeon_opened
            return
        contents = step.contents
        opened = status is TreasureOpenStatus.OPENED
        localizer = Localizer(self.settings.language)
        if contents.type == "gold":
            key = "treasure.received_gold" if opened else "treasure.found_gold"
            values = {"AMOUNT": format_number(contents.amount)}
        else:
            key = "treasure.received_item" if opened else "treasure.found_item"
            values = {"ITEM": str(self.items[contents.item_key].localized_name(localizer))}
        lines = list(self.texts.formatted_lines(key, localizer, values))
        if opened:
            play_se("treasure_open")
        else:
            lines.append(self.texts.text("treasure.capacity_exceeded", localizer))
        self.notice = ""
        self.message = MessageOverlay(lines=tuple(lines), settings=self.settings, fonts=self.fonts)

    def update(self, input_state: InputState) -> None:
        if not self.started:
            self.started = True
            self.start()
            return
        if self.message is not None:
            if self.message.update(input_state):
                self.message = None
            return
        if self.waiting_for_battle:
            return
        if input_state.menu.triggered:
            self.on_menu()
        elif input_state.confirm.triggered:
            key = self.cursor.selected_key
            if key == "next":
                self.advance()
            elif key == "exit":
                self.on_exit()
            elif key == "menu":
                self.on_menu()
        else:
            self.window.update(input_state.navigation)

    def draw(self) -> None:
        self.window.draw()
        if self.message is not None:
            self.message.draw()
