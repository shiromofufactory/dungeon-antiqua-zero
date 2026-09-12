"""Apply proficiency growth caused by using a spell from the field menu."""

from __future__ import annotations

from dataclasses import dataclass
from math import isqrt

if __package__ == "systems":
    from member import Member, ProficiencyKind
else:
    from ..member import Member, ProficiencyKind


SPELL_PROFICIENCY_KINDS = (
    ProficiencyKind.MYSTIC,
    ProficiencyKind.SACRED,
    ProficiencyKind.NETHER,
)


@dataclass(frozen=True)
class MenuSpellProficiencyGrowth:
    """One menu spell's applied before/after proficiency totals."""

    kind: ProficiencyKind
    before_total: int
    after_total: int

    @property
    def applied_amount(self) -> int:
        return self.after_total - self.before_total


def menu_spell_proficiency_gain(
    member: Member,
    kind: ProficiencyKind,
    *,
    mp_spent: int,
) -> int:
    """Return the non-negative proficiency award for one menu spell use."""

    if not isinstance(member, Member):
        raise TypeError("member must be a Member")
    if not isinstance(kind, ProficiencyKind):
        raise TypeError("kind must be a ProficiencyKind")
    if kind not in SPELL_PROFICIENCY_KINDS:
        raise ValueError("kind must identify a spell school")
    if isinstance(mp_spent, bool) or not isinstance(mp_spent, int):
        raise TypeError("mp_spent must be an integer")
    if mp_spent < 0:
        raise ValueError("mp_spent must not be negative")

    proficiency = member.proficiency(kind)
    highest_other_level = max(
        member.proficiency(other_kind).level
        for other_kind in SPELL_PROFICIENCY_KINDS
        if other_kind is not kind
    )
    return max(
        0,
        isqrt(mp_spent)
        + int(proficiency.aptitude)
        + highest_other_level
        - proficiency.level,
    )


def apply_menu_spell_proficiency_growth(
    member: Member,
    kind: ProficiencyKind,
    *,
    mp_spent: int,
) -> MenuSpellProficiencyGrowth:
    """Apply one menu spell's proficiency and any resulting max-MP growth."""

    amount = menu_spell_proficiency_gain(member, kind, mp_spent=mp_spent)
    proficiency = member.proficiency(kind)
    before_total = proficiency.level * 100 + proficiency.progress
    before_level = proficiency.level
    proficiency.add_progress(amount)
    after_total = proficiency.level * 100 + proficiency.progress

    if proficiency.level > before_level:
        member.max_mp = max(member.max_mp, member.calculated_max_mp())

    return MenuSpellProficiencyGrowth(kind, before_total, after_total)


__all__ = [
    "MenuSpellProficiencyGrowth",
    "SPELL_PROFICIENCY_KINDS",
    "apply_menu_spell_proficiency_growth",
    "menu_spell_proficiency_gain",
]
