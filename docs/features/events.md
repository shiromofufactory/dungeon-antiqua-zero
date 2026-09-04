# イベント仕様

## 位置付け

本書は、フィールドや戦闘から起動される通常イベントの定義形式、実行順序、マップ上の
トリガー、イベント制作ツール、検証条件を定める。イベントで表示する実際の文言は
`content/data/texts.json`、キャラクターとアイテムは対応する `content/data/*.json` を正本とする。
Scene、Overlay、Systemの依存方向は
[`program-architecture.md`](../program-architecture.md)、セーブ対象は
[`save-data.md`](./save-data.md)、空間上の編集操作は
[`map-editor.md`](./map-editor.md)を参照する。

本書の初期フィールドイベント範囲は実装済みである。イベント実行器、イベントエディタ、
マップエディタのトリガー編集を利用できる。戦闘中のトリガー接続、戦闘開始、選択肢、
フラグ解除、所持金操作などは、必要になった時点で型付きコマンドまたはadapterを追加する。

## 結論

- イベントは人とプログラムの双方が扱えるJSONを正本とする。YAMLとの二重管理はしない。
- 通常の制作入口として、参照先をリストから選べるローカルWeb版イベントエディタを用意する。
  JSONの手編集も許可するが、保存時とCIで同じ検証を必須にする。
- イベント本体は `content/events/*.json`、空間上のトリガーは
  `content/maps/sources/*.json` に分ける。同じイベントを別のトリガーから参照できる。
- イベント本体はコマンド列として表し、条件分岐だけが子コマンド列を持つ。任意の式やPythonを
  JSONへ埋め込まない。
- マップエディタはトリガーの位置、発火方法、イベントIDを編集する。イベント本文は専用
  イベントエディタで編集する。
- Sceneは発火条件の検出、`EventRunner` は条件評価とコマンド進行、既存のDomain Model／Systemは
  実際の状態変更、Overlayはメッセージ入力を担当する。
- 一度に実行するイベントは1件だけとし、イベント中は通常のScene入力と新規トリガー判定を止める。
- イベント実行位置は保存しない。イベント中は手動セーブを開かず、完了後に通常操作へ戻す。

JSONを採用する理由は、既存のマスターデータ、マップ、Python標準ライブラリと揃い、暗黙の
型変換や追加parserを避けられるためである。人向けの入力負担と参照ミスはイベントエディタで
解消する。

## 用語と責務

| 用語 | 内容 |
|---|---|
| イベント定義 | 安定イベントIDと、順番に実行するコマンド列 |
| イベント名前空間 | 1ファイルをまとめる安定ID。ファイル名と一致させる |
| イベントフラグ定義 | 利用可能なフラグIDと制作用メモの宣言 |
| トリガー | いつ、どのイベントIDを起動するかというScene側の設定 |
| イベント呼び出し | トリガーからRunnerへ渡すイベントID、起動元Scene、マップIDなどの値 |
| EventCatalog | 生成済みイベントをIDで検索する不変カタログ |
| EventRunner | 条件評価、コマンド位置、分岐スタック、待機中の効果を所有する実行器 |
| EventEffect | メッセージ、音、移動など、SceneまたはOverlayで完了させる要求 |

トリガーとイベント定義を分けることで、シナリオ本文へ座標を埋め込まず、マップ修正時は
マップ側だけを変更できる。反対に、同じ調査メッセージを接触と決定の両方から起動する場合も、
イベント本文を複製しない。

## ファイル配置と生成

```text
content/events/
├── fairy_village.json        # イベントとフラグの制作用正本
└── common.json

content/maps/sources/
└── fairy_village.json        # actor配置とevent_triggersを含むマップ正本

app/events/
└── events.json               # 全定義を索引化したゲーム用生成物

app/maps/
└── fairy_village.json        # 解決済みトリガーを含むゲーム用生成物
```

`content/events` はシナリオの入れ子構造を持つためGoogle Sheets同期の対象にしない。
`app/events` はGit管理せず、直接編集しない。イベント検証・生成処理はUIから独立した
`scripts/event_pipeline/`、対話UIは `tools/event_editor/`、本番loaderとRunnerは
`app/resources/events.py` と `app/systems/events.py` に置く。

次の入口を使用する。

```sh
npm run tools:event-editor
npm run events:validate
npm run events:build
```

`content:validate` はイベント、マップ、マスターデータの横断検証を含むようにする。
`events:build` はエラーが1件でもあれば生成物を更新せず、成功時だけ原子的に
`app/events/events.json` を置き換える。マップ生成も存在するイベントIDとの参照整合性を検証する。

## イベント定義形式

### ファイルルート

制作用イベント形式の初期 `format_version` は1とする。

```json
{
  "format_version": 1,
  "namespace": "fairy_village",
  "flags": [
    {
      "id": "alvan_joined",
      "note": "アルヴァンが一度加入した"
    }
  ],
  "events": [
    {
      "id": "meet_alvan",
      "note": "里でアルヴァンと話す",
      "commands": [
        {
          "command": "branch",
          "condition": {
            "type": "flag_set",
            "flag_id": "fairy_village.alvan_joined"
          },
          "then": [
            {
              "command": "message",
              "text_key": "event.fairy_village.meet_alvan.after",
              "portrait_character_key": "Alvan"
            }
          ],
          "else": [
            {
              "command": "message",
              "text_key": "event.fairy_village.meet_alvan.first",
              "portrait_character_key": "Alvan"
            },
            {
              "command": "join_party",
              "character_key": "Alvan"
            },
            {
              "command": "set_flag",
              "flag_id": "fairy_village.alvan_joined"
            }
          ]
        }
      ]
    }
  ]
}
```

名前空間、フラグのローカルID、イベントのローカルIDは `lower_snake_case` とする。
ファイル名は `<namespace>.json` と一致させる。実行時に使う完全IDは
`<namespace>.<local_id>` とし、上の例では `fairy_village.meet_alvan` と
`fairy_village.alvan_joined` になる。

参照フィールドには常に完全IDを保存する。エディタ上では同じ名前空間の接頭辞を省略表示して
よいが、JSONへ省略形を保存しない。`note` は制作者向けでありゲーム用生成物から除外する。

フラグは `flags` で先に宣言する。条件やコマンドに書かれただけの未知フラグを自動作成しない。
これにより手入力の綴り違いを別フラグとして受理しない。フラグIDの削除・変更時は全イベントと
セーブ互換性への影響を確認する。

### 条件

初期条件は次のとおり。

| `type` | 必須属性 | 真になる条件 |
|---|---|---|
| `flag_set` | `flag_id` | `SaveData.event_flags` に完全フラグIDがある |
| `member_in_party` | `character_key` | 現在の活動パーティにキャラクターがいる |
| `item_at_least` | `item_key`, `quantity` | 装備中を除くインベントリに指定数以上ある |
| `all` | `conditions` | 1件以上の全子条件が真 |
| `any` | `conditions` | 1件以上のいずれかの子条件が真 |
| `not` | `condition` | 子条件が偽 |

不在、未所持、未設定は専用の重複conditionを増やさず `not` で表す。

```json
{
  "type": "all",
  "conditions": [
    {
      "type": "not",
      "condition": {
        "type": "member_in_party",
        "character_key": "Cerion"
      }
    },
    {
      "type": "item_at_least",
      "item_key": "POTION",
      "quantity": 2
    }
  ]
}
```

`quantity` は1以上の整数とする。初期仕様のアイテム所持条件は、イベント消費と同じ対象にするため
インベントリだけを数え、自動的に装備品を外して数えない。装備中を含む所有判定が必要になった
場合は、意味の異なるconditionを追加する。

条件評価は状態を変更せず、短絡評価の有無に結果が左右されない。未知のconditionは偽として
続行せず、生成時エラー、本番loaderエラー、開発中の実行エラーとして扱う。

### コマンド

初期コマンドは次のとおり。属性名に表示名や配列位置を使用せず、正本の安定キーを使う。

| `command` | 必須属性 | 完了条件・結果 | 使用可能な起動元 |
|---|---|---|---|
| `set_flag` | `flag_id` | フラグを集合へ追加。同じ値は成功扱いのno-op | field / battle |
| `join_party` | `character_key` | キャラクターをパーティ末尾へ加入 | fieldのみ |
| `leave_party` | `character_key` | 活動パーティから外し、成長状態は保持 | fieldのみ |
| `give_item` | `item_key`, `quantity` | 全数量を一括でインベントリへ追加 | field / battle |
| `take_item` | `item_key`, `quantity` | 全数量を一括でインベントリから削除 | field / battle |
| `branch` | `condition`, `then`, `else` | 条件に応じて片方の子コマンド列だけを実行 | field / battle |
| `message` | `text_key` | メッセージOverlayを閉じるまで待機 | field / battle |
| `play_se` | `se_id` | SE再生を要求して同フレームで完了 | field / battle |
| `change_bgm` | `bgm_id` | BGM切替要求が受理された時点で完了 | field / battle |
| `move_party` | `direction`, `steps` | 指定歩数のフィールド移動演出完了まで待機 | fieldのみ |
| `move_actor` | `actor_id`, `direction`, `steps` | 指定actorの移動演出完了まで待機 | fieldのみ |

`branch.else` は空配列を許可するが省略しない。`then` と `else` の各コマンドへも同じ検証を再帰的に
適用し、入れ子の深さは16までとする。空のイベントと空の `then` は警告にする。

#### パーティとアイテム

- `join_party` はすでに活動中なら成功扱いのno-opとする。初加入なら現在の加入レベル規則から
  Memberを作り、過去に離脱して保存済み状態があればその状態を再利用する。
- 活動パーティは1〜6人、戦闘参加は先頭5人という既存規則を変えない。6人時の加入は状態を
  変更せず、イベントを安全に中断する。
- `leave_party` は不在なら成功扱いのno-opとする。フィオラ、最後の1人、または既存の隊列不変条件を
  破る離脱は指定できない。離脱者の成長、HP・MP、装備は `character_states` に保持する。
- `give_item` と `take_item` は数量全体を適用できる場合だけ変更する。所持上限超過または数量不足で
  一部だけ増減しない。
- `take_item` はインベントリだけを対象とし、装備品を暗黙に外さない。
- 動的な上限・不足で実行できない場合は、そのコマンド以降を実行しない。開発時はイベントIDと
  コマンドpathを診断へ出し、本番では対応するシステム文言を表示して通常操作へ戻す。

イベント全体のロールバックは行わない。失敗し得る加入、取得、消費、移動を先に置き、完了フラグは
その後に置く。イベントエディタは、同じ分岐内で失敗し得るコマンドより前に `set_flag` がある場合を
警告する。

#### メッセージ

```json
{
  "command": "message",
  "text_key": "event.fairy_village.meet_alvan.first",
  "portrait_character_key": "Alvan"
}
```

- `text_key` は `content/data/texts.json` の既存キーを参照する。翻訳後文字列をイベント定義へ
  複製しない。
- `portrait_character_key` は任意で、指定時は `characters.json` の `name_en` と顔座標を使う。
  現在パーティにいないキャラクターも表示できる。初期仕様で任意画像座標は指定しない。
- 顔なしでは本文領域をWindow全幅にし、顔ありでは32×32pxの顔領域を確保する。左右配置、話者名、
  自動送りは画面仕様が必要になった時点で追加する。
- イベント中の決定入力は最上位のメッセージOverlayだけが受け取り、閉じた入力を次のコマンドや
  FieldSceneへ持ち越さない。
- 表示したメッセージは既存ログ仕様に従って `text_key` と引数を記録する。演出専用でログへ
  残さない指定が必要になった場合は別属性として追加する。

#### 音声

- `bgm_id` は拡張子なしの安定IDとし、現在の `BgmPlayer` と同じID解決を使う。同じIDへの切替は
  曲頭へ戻さない。
- イベントで切り替えたBGMは、別のBGMコマンドまたはScene遷移まで継続する。再生位置と現在曲は
  セーブしない。
- `se_id` も数値Sound番号ではなく安定IDとする。Pyxel Sound番号との対応は
  `app/audio/catalog.json` へ分離し、イベントエディタと本番コードが同じカタログを読む。
- 音量は `Settings.bgm_volume` / `se_volume` を使い、イベント定義へ音量設定を持たせない。

#### 移動

```json
{
  "command": "move_party",
  "direction": "right",
  "steps": 2
}
```

```json
{
  "command": "move_actor",
  "actor_id": "village_elder",
  "direction": "left",
  "steps": 2
}
```

- `direction` は `up`、`right`、`down`、`left`、`steps` は1〜255の整数とする。
- 1セルずつ通常の歩行速度と向き変更を使い、全歩数の演出が終わってから次のコマンドへ進む。
- イベント制御移動中はプレイヤー入力、ランダムエンカウント、step/touch/interactトリガーを
  発火させない。
- マップ外や通行不可セルへ進む命令は状態を半セルに残さず、現在セルで停止してイベントを中断する。
- `move_actor.actor_id` は現在マップの安定したactor実体IDを参照する。actorの初期位置、見た目、
  通行設定はマップ側が所有し、イベント定義へ複製しない。
- 静的地形に対する経路は横断検証する。ほかのactorやパーティとの動的な衝突規則は、actor機能の
  実装時に確定する。初期コマンドへ座標テレポートや衝突無視の隠し属性を設けない。

## マップ上のトリガー

### 制作用形式

イベントトリガー追加時に制作用マップの `format_version` を3へ上げ、version 2からは
`actors: []` と `event_triggers: []` を追加する明示的な移行を行う。既存の
`sites` と `arrival_points` はそのまま維持する。

```json
{
  "format_version": 3,
  "actors": [
    {
      "id": "village_elder",
      "position": [12, 8],
      "facing": "down",
      "appearance_id": "village_elder"
    }
  ],
  "event_triggers": [
    {
      "id": "meet_elder",
      "event_id": "fairy_village.meet_alvan",
      "activations": ["touch", "interact"],
      "anchor": {
        "kind": "actor",
        "actor_id": "village_elder"
      },
      "offsets": [[0, 0]]
    },
    {
      "id": "entrance_notice",
      "event_id": "fairy_village.entrance_notice",
      "activations": ["step"],
      "anchor": {
        "kind": "cell",
        "position": [4, 10]
      },
      "offsets": [[0, 0], [1, 0]]
    }
  ]
}
```

actorの描画用 `appearance_id` の正本と衝突規則は、フィールドactor配置機能で別途定める。
イベント機能はマップ内で一意な `actor.id`、現在位置、向き、移動完了通知だけに依存する。
初期実装では `appearance_id` と一致する生成済み画像があればそれを使い、未登録時はフィールドの
標準キャラクターチップを代替表示する。専用actor素材のカタログ化は素材形式の決定後に行う。

トリガーのアンカーは次の3種類とする。

| `anchor.kind` | 内容 |
|---|---|
| `cell` | `position` を基準とする。マップ上の見た目と独立した場所 |
| `object` | `object_id` の起点を基準とし、エディタでオブジェクトを動かすと追従する |
| `actor` | `actor_id` の現在位置を基準とし、ゲーム中のactor移動にも追従する |

`offsets` はアンカーからトリガー対象セルへの相対座標で、1件以上を指定する。cellアンカーの
通常の単一セルは `[[0, 0]]` とする。オブジェクトの表示範囲すべてへ自動展開せず、どのセルへ
触れる／決定するかを明示する。

初期activationは次の3種類とする。

| activation | 発火タイミング |
|---|---|
| `step` | プレイヤー操作による1セル歩行が完了し、対象の通行可能セルへ入った直後 |
| `touch` | プレイヤーが対象セルへ進もうとし、接触が成立した時。対象は通行不可でもよい |
| `interact` | パーティが停止中に対象セルを向き、決定操作がtriggeredになった時 |

1トリガーは複数activationを持てる。たとえばNPCは `touch` と `interact` のどちらでも同じ
会話を起動できる。起動条件の違う複数シナリオを同じセルへ重ねず、1イベント内の `branch` で
表す。同じマップ、activation、解決後セルが複数トリガーで重複する状態は生成エラーにする。

初期配置、ロード、到着地点への配置、イベント制御移動、押したままの入力復帰では発火しない。
`step` はセルへ入ったエッジで1回だけ、`touch` は1回の移動試行で1回だけ、`interact` は決定の
初回押下で1回だけ発火する。イベント終了後は起動に使った方向または決定入力が離されるまで
通常入力へ戻さない。

方向入力では、移動先セルの `touch` を通行判定より先に調べる。該当時は移動を開始せずイベントを
起動し、`step` は評価しない。`touch` がなければ通常の通行判定と歩行を行い、歩行完了後に
`step` を調べる。決定入力では `interact` だけを調べる。この順序により、1回の操作から複数の
イベントを起動しない。

### ゲーム用形式

object/cellアンカーは生成時に絶対セルへ解決する。移動するactorアンカーだけはactor IDと
offsetを残す。

```json
{
  "event_triggers": [
    {
      "id": "entrance_notice",
      "event_id": "fairy_village.entrance_notice",
      "activations": ["step"],
      "target": {
        "kind": "cells",
        "cells": [[4, 10], [5, 10]]
      }
    },
    {
      "id": "meet_elder",
      "event_id": "fairy_village.meet_alvan",
      "activations": ["touch", "interact"],
      "target": {
        "kind": "actor",
        "actor_id": "village_elder",
        "offsets": [[0, 0]]
      }
    }
  ]
}
```

本番ではactivationごとのセル索引をマップ読込時に作り、毎フレーム全イベントを走査しない。

## 戦闘からの起動

BattleSceneもFieldSceneと同じ `EventInvocation` を作るが、トリガー定義はマップへ置かない。
敵グループ、ボス戦定義、または戦闘シナリオの正本へイベントIDと戦闘条件を置く。具体的な
戦闘条件は戦闘仕様とともに追加する。

BattleSceneはラウンド開始、行動完了、HP変化、勝敗確定などの安全な境界でだけ条件を評価し、
演出やダメージ計算の途中でRunnerを割り込ませない。イベント中は戦闘入力を止め、メッセージ
Overlayなどが完了した後に同じ戦闘phaseへ戻る。同じ境界で同じトリガーを繰り返さないため、
戦闘中だけ有効な発火済みtrigger ID集合をBattleSceneが持つ。この集合はセーブしない。

field専用の加入、離脱、移動コマンドを含むイベントがbattleトリガーから参照された場合は
横断検証エラーにする。戦闘中の参加者変更はBattleSceneの行動順や勝敗条件へ影響するため、
必要になった時点で専用の安全なphaseと結果を別途設計する。
将来の `start_battle` はScene遷移と戦闘結果を待つEventEffectとして追加し、Runnerや定義形式を
作り直さない。

## 実行モデル

```text
FieldScene / BattleScene
        │  EventInvocation(event_id, source)
        ▼
EventCoordinator
        │  定義と明示的なサービスだけを渡す
        ▼
EventRunner ──→ 条件評価／SaveData・PartySystem・InventorySystem
        │
        ├──→ MessageEffect ──→ MessageOverlay ──→ 完了通知
        ├──→ AudioEffect ────→ BGM／SEサービス ─→ 完了通知
        └──→ MovementEffect ─→ FieldScene ──────→ 完了通知
```

1. Sceneが通常更新の安全な境界でトリガーを検出する。
2. EventCoordinatorは別イベント実行中でないことを確認し、EventCatalogから完全IDを解決する。
3. EventRunnerはコマンド位置とbranchのスタックを作る。
4. 同期コマンドは既存Systemへ委譲して結果を受け、直ちに次へ進む。
5. メッセージや移動はEventEffectを1件返して待機する。SceneManagerまたはSceneがOverlay／演出を
   開き、完了結果をRunnerへ返す。
6. 全コマンド完了後、CoordinatorがRunnerを破棄し、入力リリース待ちを経てScene操作へ戻す。

Runner自身はPyxel、Window、具体的Scene、ファイルI/Oを参照しない。巨大なGame Contextも
受け取らず、条件参照と状態変更に必要な `SaveData`、PartySystem、InventorySystemなどを
明示的に渡す。Sceneをまたぐ効果はTransitionまたはEventEffectとして返し、Runnerから
`Game.scene` を直接変更しない。

Runnerの状態は実行中だけ有効であり、SaveDataへコマンドindexやbranchスタックを保存しない。
メニュー、セーブ、別イベントの起動も許可しない。アプリ終了やロード後はイベント開始前の
保存地点から再開し、フラグなど完了済みの永続状態によって通常の分岐を選び直す。

## エラーと中断

- ビルドで発見できる不正参照、未知属性、使用context違反は実行時へ持ち込まず生成を失敗させる。
- 実行時に動的理由でコマンドを完了できない場合、そのコマンドは状態を変更せずイベントを中断する。
- 中断時は開いているイベントOverlayとイベント制御移動を閉じ、セル途中へ状態を残さない。
- 開発起動ではイベントID、JSON path、理由を画面と標準エラーへ出す。本番では内部IDを見せず、
  持ち物上限など利用者が対処可能な場合だけ対応文言を表示する。
- イベント定義の欠落・破損はセーブデータを初期化する理由にしない。該当イベントを起動せず、
  セーブ状態を保持したまま診断する。
- 前の同期コマンドまでの変更はロールバックしない。このため完了フラグを最後に置く規則を
  エディタ警告とレビューで守る。

## イベントエディタ

### 役割

イベントエディタはJSONを隠す独自データベースではなく、同じJSONを安全に作る入力支援ツールと
する。手編集、ツール編集、非対話ビルドのすべてが `scripts/event_pipeline` の同じparserと
validatorを使う。

マップは空間編集、イベントはコマンド木編集で操作が異なるため、イベント本文をマップエディタへ
埋め込まない。マップエディタの「イベント」タブはトリガーを配置し、既存イベントを選択し、
選択したイベントをイベントエディタで開くところまでを担当する。

### 画面

画面は次の3列を基本とする。

1. 左: 編集中名前空間のイベントとフラグの一覧・入力欄
2. 中央: イベント属性、コマンド列、branchの入れ子、参照先選択。追加、削除、上下移動
3. 右: validatorの問題一覧

イベント／フラグのIDと制作用 `note` は自由入力できる。参照値は原則としてリストまたは検索付き
セレクターから選ぶ。

| 入力 | 選択元 |
|---|---|
| `flag_id` | 全 `content/events/*.json` の宣言済みフラグ |
| `character_key` / 顔 | `content/data/characters.json` |
| `item_key` | `content/data/items.json` |
| `text_key` | `content/data/texts.json` |
| `bgm_id` | 本番BGMカタログ／生成元 |
| `se_id` | 安定SEカタログ |
| `actor_id` | 全マップのactor一覧。参照元マップとの一致は保存・生成時に横断検証する |

初期版のmessage編集は、既存の `text_key` を一覧から選ぶ。文言そのものの追加・翻訳は
`content/data/texts.json` 側で行う。将来、エディタから文言を新規作成するときは
`event.<namespace>.<event_id>.<message_id>` を既定値とし、並べ替えで変化しない安定IDを使う。

### 操作と安全策

- 起動時に全イベント、フラグ、マスターデータ、文言、音声を読み、参照索引を作る。
- コマンドを選ぶと、その種類に必要な属性だけを表示する。未使用属性はJSONへ残さない。
- conditionは「すべて／いずれか／否定／フラグ／メンバー／アイテム」の部品で組み立てる。
- ID変更・削除後は同じvalidatorで全参照を検証し、問題一覧へ不整合を表示する。参照先の
  一括変更とセーブ済みフラグIDの移行は初期版では自動化しない。
- Undo/Redoは1回のコマンド追加、削除、並べ替え、属性変更を単位とする。
- 未保存変更がある状態でページを閉じる場合は確認する。名前空間は起動引数で1件を指定する。
- エラーがある間は保存しない。警告は内容を表示したうえで保存できる。
- 保存は無関係なJSONを再整形せず、変更対象のイベントファイルだけを更新する。
- 保存成功後にゲーム用イベントを生成する。マップ側の未保存変更はイベント保存に含めない。

初期版では任意JSON入力欄、Python式、変数、ラベル／goto、並列実行、タイムライン編集、イベントの
途中再開を提供しない。必要な機能は型付きconditionまたはcommandとして追加する。

## マップエディタのイベント操作

- 「イベント」タブでcell、object、actorのいずれかをアンカーにしてトリガーを追加する。
- キャンバスではトリガー対象セルを半透明の枠、actorを丸印と向きで表示する。選択中の対象は
  ピンクで強調し、activationは左のトリガー一覧と右の編集欄に表示する。
- object/actor選択情報から「イベントトリガーを追加」を実行できる。初期offsetは `[[0, 0]]` とする。
- cellアンカーとoffsetはキャンバスで移動・複数選択できる。object/actorアンカーは対象の移動へ
  追従し、トリガーだけの絶対座標を保持しない。
- イベントIDはイベントカタログから選ぶ。未作成イベントIDを文字列で仮入力する機能は設けない。
- イベント本文の新規作成と編集は `npm run tools:event-editor -- --namespace <namespace>` で行い、
  保存後にマップエディタを再読込してイベント一覧を更新する。
- 問題一覧は不正なトリガー、イベント定義、参照先actorのJSON pathと理由を表示する。
- マップ保存はイベント参照を検証し、成功時だけ制作用マップとゲーム用マップを更新する。

## 検証

### イベント単体

次をエラーにする。

- 不正なformat version、名前空間、ローカルID、またはファイル名との不一致
- 名前空間、完全イベントID、完全フラグIDの重複
- 未知のフィールド、condition、command、または必須属性の欠落
- 宣言されていないフラグ、存在しないキャラクター、アイテム、文言、BGM、SEの参照
- 0以下または上限外の数量・歩数、空のcondition集合、branchの深さ超過
- フィオラを対象にした `leave_party`
- 数量や歩数など、単体で静的に判定できる不正値

### マップとの横断検証

次をエラーにする。

- 存在しないイベントID、object ID、actor IDの参照
- 不正、空、重複、範囲外のトリガーoffsetまたは解決後セル
- `step` の対象が通行不可である状態
- 同じactivationと解決後セルを複数トリガーが占有する状態
- actorを参照するイベントが、そのイベントを起動するマップに存在しない `actor_id` を移動する状態

別マップのactorを動かすことはできない。1イベントが複数マップから参照される場合、
`move_actor` の各IDが全参照元マップに存在しなければエラーにする。マップ固有のactorを動かす
イベントはマップ固有の名前空間へ置く。

空のイベントまたはbranchの空のthen側は警告にする。空のelse側は正常な定義として扱う。
未参照イベント、未使用フラグ、
連続する同値設定、完了フラグの配置は、シナリオデータが増えた段階で静的解析を追加する。
警告は生成を妨げない。

## 実装状況と拡張順序

1. source parser、全体索引、validator、compiler、`EventCatalog` は実装済み。
2. condition、同期コマンド、PartySystem、待機型Runner、メッセージ／音声／移動効果は実装済み。
3. map format 3、actor、step/touch/interactトリガーとフィールド接続は実装済み。
4. 同じvalidatorを使うイベントエディタと、トリガーを扱うマップエディタは実装済み。
5. BattleScene実装時に戦闘トリガーadapterと戦闘用conditionを追加する。
6. 将来の `start_battle` などを新しい型付きコマンドとして追加する。

最初の縦方向の確認には、「NPCの前で決定 → 顔付きメッセージ → アイテム取得 → フラグ設定 →
再度決定すると別メッセージ」の1イベントを使う。その後、イベント制御移動と加入・離脱を追加し、
Runnerとマップトリガーを一度に作り込みすぎない。

## 受け入れ条件

- JSONを手編集してもイベントエディタで編集しても、同じ検証とゲーム用生成結果になる。
- イベント、フラグ、キャラクター、アイテム、文言、音声、actorの不正参照をゲーム起動前に検出できる。
- step、touch、interactが定めた入力エッジで1回だけ発火し、初期配置やイベント移動では発火しない。
- フラグ、パーティ、インベントリへの操作が既存の上限・隊列・セーブ規則を迂回しない。
- flag、メンバー、アイテムとall/any/notを組み合わせ、then/elseの片方だけを実行できる。
- 顔あり／なしのメッセージを表示し、決定入力が下のSceneへ漏れない。
- BGMとSEが安定IDから再生され、Settingsの音量に従う。
- パーティとactorが指定方向へ指定歩数だけ順次移動し、移動中に別トリガーを起動しない。
- イベント中に別イベントや手動セーブを開かず、完了または安全な中断後にScene操作へ戻れる。
- 将来の戦闘開始や選択肢を、既存イベントファイルの意味を変えず新commandとして追加できる。
