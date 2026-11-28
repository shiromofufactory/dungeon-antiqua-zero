"""Stable event flags owned by the game's progression rules."""

from collections.abc import Collection
from types import MappingProxyType


FIORA_AWAKENED = "progress.fiora_awakened"
TELEPORT_UNSEALED = "progress.teleport_unsealed"
REVIVE2_UNSEALED = "progress.revive2_unsealed"
ABYSS_NOVA_UNSEALED = "progress.abyss_nova_unsealed"

RESERVED_EVENT_FLAGS = MappingProxyType({
    FIORA_AWAKENED: "孤児院襲撃後にフィオラが覚醒し、通常適性が得意になる",
    TELEPORT_UNSEALED: "峠の道で理術の封印を解き、テレポートを解放",
    REVIVE2_UNSEALED: "大雪原で聖術の封印を解き、リヴァイヴ2を解放",
    ABYSS_NOVA_UNSEALED: "漆黒の森で冥術の封印を解き、アビスノヴァを解放",
})

_SPELL_KEY_BY_FLAG = {
    TELEPORT_UNSEALED: "TELEPORT",
    REVIVE2_UNSEALED: "REVIVE2",
    ABYSS_NOVA_UNSEALED: "ABYSS NOVA",
}


def unlocked_event_spell_keys(event_flags: Collection[str]) -> frozenset[str]:
    """Return the party-wide spell unlocks from the current save flags."""

    return frozenset(
        key for flag_id, key in _SPELL_KEY_BY_FLAG.items() if flag_id in event_flags
    )
