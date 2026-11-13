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
    battle_count: str = "しょうりすう"
    gold: str = "Ｇｏｌｄ"
    members: str = "メンバー"
    member_status: str = "メンバー状態"
    items: str = "アイテム"
    item_inventory: str = "もちもの"
    item_warehouse: str = "そうこ"
    item_switch_guide: str = "←→：きりかえ"
    item_count_template: str = "{count}しゅ"
    no_items: str = "なし"
    member_status_selection: str = "メンバーせんたく"
    hp: str = "ＨＰ"
    mp: str = "ＭＰ"
    poisoned: str = "どく"
    paralyzed: str = "まひ"
    skills: str = "スキル"
    skill_selection: str = "スキルいれかえ"
    skill_count_template: str = "{count}／２"
    condition_on: str = "あり"
    condition_off: str = "なし"
    teleport: str = "テレポート"
    teleport_destination: str = "テレポートさき"
    teleport_count_template: str = "{count}かしょ"
    no_teleport_destinations: str = "いどうさきが　ありません"
    shop: str = "ショップ"
    shop_selection: str = "ショップせんたく"
    shop_count_template: str = "{count}けん"
    no_shops: str = "ショップが　ありません"
    encounter: str = "エンカウント"
    dungeon: str = "ダンジョン試行"
    dungeon_empty: str = "エディタでダンジョンを作成してください"
    dungeon_invalid: str = "ダンジョンデータを確認してください"
    dungeon_start: str = "入口から開始"
    dungeon_reset: str = "宝箱の取得記録をリセット"
    dungeon_reset_confirm: str = "このダンジョンの宝箱を未取得に戻す？"
    dungeon_reset_done: str = "宝箱の取得記録をリセットしました"
    dungeon_yes: str = "リセットする"
    dungeon_no: str = "戻る"
    dungeon_next: str = "進む"
    dungeon_exit: str = "ダンジョンを出る"
    dungeon_menu: str = "メニューを開く"
    dungeon_warning: str = "注意：次はイベント戦闘です"
    dungeon_finished: str = "最奥部に到達しました"
    dungeon_skipped: str = "ＦＡＤＥで戦闘を回避しました"
    dungeon_opened: str = "この宝箱は取得済みです"
    dungeon_fade_active: str = "ＦＡＤＥ有効"
    dungeon_progress: str = "ステップ {current}／{total}"
    dungeon_healing_spring: str = "次は回復の泉です"
    dungeon_event_error: str = "イベントを実行できません。設定を確認してください"
    dungeon_battle_finished: str = "戦闘が終了しました"
    dungeon_error: str = "敵編成を生成できません。設定を確認してください"
    encounter_settings: str = "エンカウント設定"
    monster_level: str = "モンスターレベル"
    danger: str = "危険度"
    polarity: str = "傾向"
    allow_demons: str = "悪魔出現"
    allow_humans: str = "人間出現"
    allow_giants: str = "巨人出現"
    allow_large_animals: str = "大型動物出現"
    encounter_start: str = "バトル開始"
    encounter_change_guide: str = "←→／決定：設定変更"
    event_flags: str = "イベントフラグ"
    no_event_flags: str = "フラグが　ありません"
    flag_on: str = "ＯＮ"
    flag_off: str = "ＯＦＦ"
    flag_toggle_guide: str = "%CONFIRM%：ＯＮ／ＯＦＦ"
    flag_page_guide: str = "←→：ページ"
    flag_count_template: str = "{count}こ"
    member_count_template: str = "フィオラ＋{count}にん"
    party_member_count_template: str = "{count}にん"
    numeric_delete: str = "けす"
    numeric_confirm: str = "けってい"
    close_guide: str = "%CANCEL%：もどる"

    def member_count(self, count: int) -> str:
        """Format the number of selected members other than Fiora."""

        return self._format_count(count, self.member_count_template)

    def teleport_count(self, count: int) -> str:
        """Format the number of currently available teleport destinations."""

        return self._format_count(count, self.teleport_count_template)

    def party_member_count(self, count: int) -> str:
        """Format the current total party-member count."""

        return self._format_count(count, self.party_member_count_template)

    def skill_count(self, count: int) -> str:
        """Format the number of skills currently assigned to one member."""

        return self._format_count(count, self.skill_count_template)

    def item_count(self, count: int) -> str:
        """Format the number of currently owned item types."""

        return self._format_count(count, self.item_count_template)

    def shop_count(self, count: int) -> str:
        """Format the number of selectable debug shops."""

        return self._format_count(count, self.shop_count_template)

    def flag_count(self, count: int) -> str:
        """Format the number of registered event flags."""

        return self._format_count(count, self.flag_count_template)

    def flag_page(self, page: int, total: int) -> str:
        """Format the current and total flag pages."""

        return f"{self._validated_count_text(page)}／{self._validated_count_text(total)}"

    @staticmethod
    def _format_count(count: int, template: str) -> str:
        count_text = DebugText._validated_count_text(count)
        return template.format(count=count_text)

    @staticmethod
    def _validated_count_text(count: int) -> str:
        if isinstance(count, bool) or not isinstance(count, int):
            raise TypeError("debug count must be an integer")
        if count < 0:
            raise ValueError("debug count must not be negative")
        return str(count).translate(_FULLWIDTH_DIGITS)


DEBUG_TEXT = DebugText()


__all__ = ["DEBUG_TEXT", "DebugText"]
