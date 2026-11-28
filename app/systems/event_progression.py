"""Apply permanent gameplay changes when an event flag is set."""

from collections.abc import Iterable

if __package__ == "systems":
    from event_flags import FIORA_AWAKENED
    from member import FIORA_CHARACTER_KEY, Member
else:
    from ..event_flags import FIORA_AWAKENED
    from ..member import FIORA_CHARACTER_KEY, Member


def set_event_flag(
    flag_id: str, event_flags: set[str], members: Iterable[Member],
) -> None:
    if flag_id == FIORA_AWAKENED:
        for member in members:
            if member.definition.key == FIORA_CHARACTER_KEY:
                member.awaken()
                break
    event_flags.add(flag_id)
