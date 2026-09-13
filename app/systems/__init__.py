"""Game systems coordinating changes across domain models and state."""

from .debug import (
    DebugPartyEditor,
    DebugPartyError,
    MAX_MEMBER_SKILL_COUNT,
    MAX_OTHER_MEMBER_COUNT,
    MIN_OTHER_MEMBER_COUNT,
)
from .encounter import (
    DungeonExitReturn,
    ENCOUNTER_STEP_MAX,
    ENCOUNTER_STEP_MIN,
    ENCOUNTER_THRESHOLD,
    EncounterAdvance,
    EncounterSystem,
)
from .inventory import InventorySystem
from .monster_records import (
    MONSTER_COMBAT_FIELD_KEYS,
    MONSTER_IDENTIFY_FIELD_KEYS,
    MONSTER_PROFILE_FIELD_KEY,
    MONSTER_TREASURE_ACQUIRED_FIELD_KEY,
    MONSTER_TREASURE_IDENTIFIED_FIELD_KEY,
    MonsterRecordSystem,
)
from .events import (
    ChangeBgmEffect,
    EventContext,
    EventRunner,
    EventRuntimeError,
    MessageEffect,
    MoveActorEffect,
    MovePartyEffect,
    OpenShopEffect,
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
from .settings import (
    SETTINGS_DIRECTORY,
    SETTINGS_PATH,
    SettingsRepository,
    SettingsSystemError,
)
from .shop import MAX_GOLD, ShopSystem
from .spell_progression import (
    MenuSpellProficiencyGrowth,
    apply_menu_spell_proficiency_growth,
    menu_spell_proficiency_gain,
)
from .battle_progression import (
    BattleGrowthResult,
    BattleProgression,
    EnemyProgressionData,
    MemberGrowthSnapshot,
    ProficiencySnapshot,
)
from .travel import TravelSystem
from .treasure import TreasureOpenStatus, TreasureSystem


__all__ = [
    "DebugPartyEditor",
    "DebugPartyError",
    "DungeonExitReturn",
    "ENCOUNTER_STEP_MAX",
    "ENCOUNTER_STEP_MIN",
    "ENCOUNTER_THRESHOLD",
    "EncounterAdvance",
    "EncounterSystem",
    "InventorySystem",
    "MONSTER_COMBAT_FIELD_KEYS",
    "MONSTER_IDENTIFY_FIELD_KEYS",
    "MONSTER_PROFILE_FIELD_KEY",
    "MONSTER_TREASURE_ACQUIRED_FIELD_KEY",
    "MONSTER_TREASURE_IDENTIFIED_FIELD_KEY",
    "MonsterRecordSystem",
    "MenuSpellProficiencyGrowth",
    "ChangeBgmEffect",
    "EventContext",
    "EventRunner",
    "EventRuntimeError",
    "MessageEffect",
    "MoveActorEffect",
    "MovePartyEffect",
    "OpenShopEffect",
    "PartySystem",
    "PartySystemError",
    "PlaySeEffect",
    "LoadedGameState",
    "SAVE_DIRECTORY",
    "SAVE_FORMAT_VERSION",
    "SAVE_SLOT_COUNT",
    "MAX_GOLD",
    "BattleGrowthResult",
    "BattleProgression",
    "EnemyProgressionData",
    "MemberGrowthSnapshot",
    "ProficiencySnapshot",
    "MAX_MEMBER_SKILL_COUNT",
    "MAX_OTHER_MEMBER_COUNT",
    "MIN_OTHER_MEMBER_COUNT",
    "SaveRepository",
    "SaveSlotSummary",
    "SaveSystemError",
    "SETTINGS_DIRECTORY",
    "SETTINGS_PATH",
    "SettingsRepository",
    "SettingsSystemError",
    "ShopSystem",
    "TravelSystem",
    "TreasureOpenStatus",
    "TreasureSystem",
    "create_save_document",
    "apply_menu_spell_proficiency_growth",
    "menu_spell_proficiency_gain",
    "restore_save_document",
]
