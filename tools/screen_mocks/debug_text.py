"""Japanese-only text owned by the development debug screens."""

from __future__ import annotations

from dataclasses import dataclass

_FULLWIDTH_DIGITS = str.maketrans("0123456789", "０１２３４５６７８９")


@dataclass(frozen=True)
class DebugText:
    """Fixed text that is intentionally excluded from game localization."""

    settings_menu: str = "デバッグメニュー"
    title: str = "デバッグメニュー"
    party_level: str = "パーティＬＶ"
    gold: str = "Ｇｏｌｄ"
    members: str = "メンバー"
    member_count_template: str = "フィオラ＋{count}にん"
    numeric_delete: str = "けす"
    numeric_confirm: str = "けってい"
    close_guide: str = "%CANCEL%：もどる"

    def member_count(self, count: int) -> str:
        """Format the number of selected members other than Fiora."""

        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError("debug member count must be an integer")
        if count < 0:
            raise ValueError("debug member count must not be negative")
        count_text = str(count).translate(_FULLWIDTH_DIGITS)
        return self.member_count_template.format(count=count_text)


DEBUG_TEXT = DebugText()


__all__ = ["DEBUG_TEXT", "DebugText"]
