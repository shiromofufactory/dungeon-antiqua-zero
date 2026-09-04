"""Game systems coordinating changes across domain models and state."""

from .debug import (
    DebugPartyEditor,
    DebugPartyError,
    MAX_OTHER_MEMBER_COUNT,
    MIN_OTHER_MEMBER_COUNT,
)
from .inventory import InventorySystem
from .events import (
    ChangeBgmEffect,
    EventContext,
    EventRunner,
    EventRuntimeError,
    MessageEffect,
    MoveActorEffect,
    MovePartyEffect,
    PlaySeEffect,
)
from .party import PartySystem, PartySystemError
from .save import (
    SAVE_DIRECTORY,
    SAVE_FORMAT_VERSION,
    SAVE_SLOT_COUNT,
    LoadedGameState,
    SaveRepository,
    SaveSlotSummary,
    SaveSystemError,
    create_save_document,
    restore_save_document,
)
from .shop import MAX_GOLD, ShopSystem
from .travel import TravelSystem


__all__ = [
    "DebugPartyEditor",
    "DebugPartyError",
    "InventorySystem",
    "ChangeBgmEffect",
    "EventContext",
    "EventRunner",
    "EventRuntimeError",
    "MessageEffect",
    "MoveActorEffect",
    "MovePartyEffect",
    "PartySystem",
    "PartySystemError",
    "PlaySeEffect",
    "LoadedGameState",
    "SAVE_DIRECTORY",
    "SAVE_FORMAT_VERSION",
    "SAVE_SLOT_COUNT",
    "MAX_GOLD",
    "MAX_OTHER_MEMBER_COUNT",
    "MIN_OTHER_MEMBER_COUNT",
    "SaveRepository",
    "SaveSlotSummary",
    "SaveSystemError",
    "ShopSystem",
    "TravelSystem",
    "create_save_document",
    "restore_save_document",
]
