"""Battle cursor choices retained across battles and restored from save slots."""

from __future__ import annotations

from dataclasses import dataclass, field

if __package__:
    from .battle_commands import BattleCommand
    from .member import EquipmentSlot
else:
    from battle_commands import BattleCommand
    from member import EquipmentSlot


@dataclass
class BattleCommandMemory:
    """Character keys keep choices attached to members across party reordering."""

    global_command: str | None = None
    commands: dict[str, BattleCommand] = field(default_factory=dict)
    spells: dict[str, str] = field(default_factory=dict)
    items: dict[str, tuple[str, EquipmentSlot | None]] = field(default_factory=dict)

    def clear(self) -> None:
        self.global_command = None
        self.commands.clear()
        self.spells.clear()
        self.items.clear()
