"""Execute small, typed event commands independently of Pyxel and UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

if __package__ == "systems":
    from input import Direction
    from resources.events import EventCatalog, EventDefinition
    from state import LaunchMode, SaveData
else:
    from ..input import Direction
    from ..resources.events import EventCatalog, EventDefinition
    from ..state import LaunchMode, SaveData

from .conditions import evaluate_condition
from .inventory import InventorySystem
from .party import PartySystem, PartySystemError


class EventContext(StrEnum):
    FIELD = "field"
    BATTLE = "battle"


class EventRuntimeError(RuntimeError):
    """Raised when a validated event cannot complete against current state."""

    def __init__(self, event_id: str, command_path: str, message: str) -> None:
        self.event_id = event_id
        self.command_path = command_path
        super().__init__(f"{event_id} {command_path}: {message}")


@dataclass(frozen=True)
class MessageEffect:
    message_id: str


@dataclass(frozen=True)
class ItemReceivedEffect:
    item_key: str


@dataclass(frozen=True)
class PlaySeEffect:
    se_id: str


@dataclass(frozen=True)
class ChangeBgmEffect:
    bgm_id: str


@dataclass(frozen=True)
class StopBgmEffect:
    pass


@dataclass(frozen=True)
class ResetGameEffect:
    pass


@dataclass(frozen=True)
class FlashScreenEffect:
    color: str


@dataclass(frozen=True)
class WaitEffect:
    frames: int


@dataclass(frozen=True)
class ChangeBrightnessEffect:
    percent: int


@dataclass(frozen=True)
class ShakeScreenEffect:
    frames: int


@dataclass(frozen=True)
class OpenShopEffect:
    shop_key: str


@dataclass(frozen=True)
class StartBattleEffect:
    battle_id: str
    monster_keys: tuple[str, ...]


@dataclass(frozen=True)
class FacePartyEffect:
    direction: Direction


@dataclass(frozen=True)
class FaceActorEffect:
    actor_id: str
    direction: Direction


@dataclass(frozen=True)
class MovePartyEffect:
    direction: Direction
    steps: int


@dataclass(frozen=True)
class MoveActorEffect:
    actor_id: str
    direction: Direction
    steps: int


EventEffect = (
    MessageEffect
    | ItemReceivedEffect
    | PlaySeEffect
    | ChangeBgmEffect
    | StopBgmEffect
    | ResetGameEffect
    | FlashScreenEffect
    | WaitEffect
    | ChangeBrightnessEffect
    | ShakeScreenEffect
    | OpenShopEffect
    | StartBattleEffect
    | FacePartyEffect
    | FaceActorEffect
    | MovePartyEffect
    | MoveActorEffect
)


@dataclass
class _Frame:
    commands: tuple[Mapping[str, object], ...]
    path: str
    index: int = 0


class EventRunner:
    """Advance one event until it completes or waits for an external effect."""

    def __init__(
        self,
        definition: EventDefinition,
        *,
        context: EventContext,
        save_data: SaveData,
        party: PartySystem,
        inventory: InventorySystem,
        launch_mode: LaunchMode = LaunchMode.NORMAL,
    ) -> None:
        if not isinstance(definition, EventDefinition):
            raise TypeError("definition must be an EventDefinition")
        if not isinstance(context, EventContext):
            raise TypeError("context must be an EventContext")
        if not isinstance(launch_mode, LaunchMode):
            raise TypeError("launch_mode must be a LaunchMode")
        self.definition = definition
        self.context = context
        self.save_data = save_data
        self.party = party
        self.inventory = inventory
        self.launch_mode = launch_mode
        self._stack = [_Frame(definition.commands, "commands")]
        self._waiting_effect: EventEffect | None = None
        self._complete = False

    @classmethod
    def from_catalog(
        cls,
        catalog: EventCatalog,
        event_id: str,
        **dependencies: object,
    ) -> EventRunner:
        return cls(catalog.event(event_id), **dependencies)

    @property
    def event_id(self) -> str:
        return self.definition.id

    @property
    def is_waiting(self) -> bool:
        return self._waiting_effect is not None

    @property
    def is_complete(self) -> bool:
        return self._complete

    def advance(self) -> EventEffect | None:
        if self._complete:
            return None
        if self._waiting_effect is not None:
            return self._waiting_effect
        while self._stack:
            frame = self._stack[-1]
            if frame.index >= len(frame.commands):
                self._stack.pop()
                continue
            index = frame.index
            frame.index += 1
            command = frame.commands[index]
            path = f"{frame.path}[{index}]"
            effect = self._execute(command, path)
            if effect is not None:
                self._waiting_effect = effect
                return effect
        self._complete = True
        return None

    def complete_effect(self, effect: EventEffect, *, succeeded: bool = True) -> None:
        if self._waiting_effect is None or effect is not self._waiting_effect:
            raise ValueError("effect is not the active event effect")
        if not succeeded:
            raise EventRuntimeError(self.event_id, "effect", "event effect failed")
        self._waiting_effect = None

    def _execute(
        self,
        command: Mapping[str, object],
        path: str,
    ) -> EventEffect | None:
        command_type = command["command"]
        try:
            if command_type == "set_flag":
                self.save_data.event_flags.add(str(command["flag_id"]))
                return None
            if command_type == "join_party":
                self._require_field(command_type)
                self.party.join(
                    str(command["character_key"]),
                    shared_experience=self.save_data.experience,
                )
                return None
            if command_type == "leave_party":
                self._require_field(command_type)
                self.party.leave(str(command["character_key"]))
                return None
            if command_type == "give_item":
                if not self.inventory.add(
                    str(command["item_key"]),
                    int(command["quantity"]),
                    members=self.party.character_states.values(),
                ):
                    raise EventRuntimeError(self.event_id, path, "item capacity exceeded")
                if command.get("show_message", False):
                    return ItemReceivedEffect(str(command["item_key"]))
                return None
            if command_type == "take_item":
                if not self.inventory.remove(
                    str(command["item_key"]), int(command["quantity"])
                ):
                    raise EventRuntimeError(self.event_id, path, "not enough items")
                return None
            if command_type == "branch":
                branch = "then" if self._condition(command["condition"]) else "else"
                commands = command[branch]
                if not isinstance(commands, tuple):
                    raise TypeError("compiled branch commands must be a tuple")
                self._stack.append(_Frame(commands, f"{path}.{branch}"))
                return None
            if command_type == "end_event":
                self._stack.clear()
                return None
            if command_type == "reset_game":
                self._stack.clear()
                return ResetGameEffect()
            if command_type == "message":
                return MessageEffect(str(command["message_id"]))
            if command_type == "play_se":
                return PlaySeEffect(str(command["se_id"]))
            if command_type == "change_bgm":
                return ChangeBgmEffect(str(command["bgm_id"]))
            if command_type == "stop_bgm":
                return StopBgmEffect()
            if command_type == "flash_screen":
                return FlashScreenEffect(str(command["color"]))
            if command_type == "wait":
                return WaitEffect(int(command["frames"]))
            if command_type == "change_brightness":
                return ChangeBrightnessEffect(int(command["percent"]))
            if command_type == "shake_screen":
                return ShakeScreenEffect(int(command["frames"]))
            if command_type == "recover_party":
                self.party.recover_all()
                return None
            if command_type == "open_shop":
                self._require_field(command_type)
                return OpenShopEffect(str(command["shop_key"]))
            if command_type == "start_battle":
                self._require_field(command_type)
                return StartBattleEffect(
                    str(command["battle_id"]), tuple(command["monster_keys"])
                )
            if command_type == "face_party":
                self._require_field(command_type)
                return FacePartyEffect(self._direction(command["direction"]))
            if command_type == "face_actor":
                self._require_field(command_type)
                return FaceActorEffect(str(command["actor_id"]), self._direction(command["direction"]))
            if command_type == "move_party":
                self._require_field(command_type)
                return MovePartyEffect(self._direction(command["direction"]), int(command["steps"]))
            if command_type == "move_actor":
                self._require_field(command_type)
                return MoveActorEffect(str(command["actor_id"]), self._direction(command["direction"]), int(command["steps"]))
        except EventRuntimeError:
            raise
        except (KeyError, TypeError, ValueError, PartySystemError) as error:
            raise EventRuntimeError(self.event_id, path, str(error)) from error
        raise EventRuntimeError(self.event_id, path, f"unsupported command: {command_type}")

    def _condition(self, condition: object) -> bool:
        return evaluate_condition(
            condition, save_data=self.save_data,
            party=self.party, inventory=self.inventory,
            launch_mode=self.launch_mode,
        )

    def _require_field(self, command_type: object) -> None:
        if self.context is not EventContext.FIELD:
            raise ValueError(f"{command_type} is only available in field events")

    @staticmethod
    def _direction(value: object) -> Direction:
        try:
            return Direction[str(value).upper()]
        except KeyError as error:
            raise ValueError(f"unsupported direction: {value}") from error


__all__ = [
    "ChangeBgmEffect",
    "StopBgmEffect",
    "ResetGameEffect",
    "ChangeBrightnessEffect",
    "ShakeScreenEffect",
    "EventContext",
    "EventEffect",
    "EventRunner",
    "EventRuntimeError",
    "FaceActorEffect",
    "FacePartyEffect",
    "FlashScreenEffect",
    "MessageEffect",
    "ItemReceivedEffect",
    "MoveActorEffect",
    "MovePartyEffect",
    "OpenShopEffect",
    "PlaySeEffect",
    "StartBattleEffect",
    "WaitEffect",
]
