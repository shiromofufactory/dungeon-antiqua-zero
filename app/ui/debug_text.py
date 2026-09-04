"""Japanese-only text owned by the development debug overlay."""

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
    teleport: str = "テレポート"
    teleport_destination: str = "テレポートさき"
    teleport_count_template: str = "{count}かしょ"
    no_teleport_destinations: str = "いどうさきが　ありません"
    shop: str = "ショップ"
    shop_selection: str = "ショップせんたく"
    shop_count_template: str = "{count}けん"
    no_shops: str = "ショップが　ありません"
    member_count_template: str = "フィオラ＋{count}にん"
    numeric_delete: str = "けす"
    numeric_confirm: str = "けってい"
    close_guide: str = "%CANCEL%：もどる"

    def member_count(self, count: int) -> str:
        """Format the number of selected members other than Fiora."""

        return self._format_count(count, self.member_count_template)

    def teleport_count(self, count: int) -> str:
        """Format the number of currently available teleport destinations."""

        return self._format_count(count, self.teleport_count_template)

    def shop_count(self, count: int) -> str:
        """Format the number of selectable debug shops."""

        return self._format_count(count, self.shop_count_template)

    @staticmethod
    def _format_count(count: int, template: str) -> str:
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError("debug count must be an integer")
        if count < 0:
            raise ValueError("debug count must not be negative")
        count_text = str(count).translate(_FULLWIDTH_DIGITS)
        return template.format(count=count_text)


DEBUG_TEXT = DebugText()


__all__ = ["DEBUG_TEXT", "DebugText"]
