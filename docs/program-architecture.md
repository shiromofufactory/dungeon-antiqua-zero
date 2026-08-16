# Dungeon Antiqua ZERO プログラム構造

## この文書の位置付け

この文書は、Dungeon Antiqua ZERO（以下、ZERO）の実装を開始・拡張するときのプログラム構造の基準を定める。

ゲーム内容、世界設定、シナリオ、システム仕様のベースドキュメントは [`da0.md`](./da0.md) とする。本書はそれらを実装するための責務分割、依存関係、状態管理、画面遷移の方針を扱う。

設計は最初から全ディレクトリを作ることを要求しない。小さく実装を始め、責務が増えた時点で本書の境界に沿って分割する。

## 結論

ZEROでは、Pyxelのコールバックに合わせた `update.py` / `draw.py` の横分割を採用しない。タイトル、フィールド、街、戦闘、メニューなどの**画面・機能単位で縦に分割し、それぞれの更新と描画を同居させる**。

Pyxelの `update()` と `draw()` はエンジンとの接続口であり、アプリケーション全体の分類軸にはしない。

基本方針は次のとおり。

- `main.py` は起動処理に限定する。
- 現在の画面はSceneオブジェクトとして表現する。
- 各Sceneは、自身の入力処理、フレーム更新、描画、Scene固有状態を所有する。
- メニューや確認ダイアログはOverlayとしてSceneの上に積む。
- セーブ対象の進行状態を `App` やSceneから分離する。
- 画面遷移は直接の文字列代入ではなく、明示的なTransitionとして扱う。
- ゲームルールは可能な範囲でPyxelやUIから独立させる。
- 通常イベントはデータと小さな実行器で表し、特殊イベントだけをPythonで実装する。

## 前作から得た判断材料

### Dungeon Antiqua 1

`app/main.py` に主要処理が集中しているため、関数の探索場所には迷いにくい。一方、`App.update()` が入力、画面、ウィンドウ、イベント、フィールド処理を一括で持ち、機能追加に伴って巨大化した。

「同じクラスにあるので接続は分かりやすい」という利点は残しつつ、Sceneごとに所有者を分ける必要がある。

### Dungeon Antiqua 2

`main.py`、`update.py`、`draw.py` に分割されたが、`update.py` は `App` の状態とメソッドを広範囲に読み書きしている。実態は、1つの巨大な `App` を別ファイルの関数から操作する構造である。

特に、すべてのウィンドウ入力を処理する `win_main()` と、フィールドイベントを処理する `start_event()` / `do_event()` が変更の集中点になった。ファイルは分かれていても状態の所有者が分かれていないため、`main.py` と `update.py` のどちらに処理を置くか判断しにくい。

一方、`Field` と `Battle` がそれぞれ `update()` と `draw()` を持つ構造は、機能の境界が明確でありZEROでも活用できる。

### `draw.py` が比較的問題にならなかった理由

描画処理は基本的にゲーム状態を参照する側であり、更新処理より依存方向を一方向にしやすい。ただしZEROでは、タイマー更新やScene遷移を `draw()` 内で行わない。描画は原則として状態を変更せず、フレーム進行は `update()` が担当する。

共通描画関数を `draw_helpers.py` やRendererに分けることは許容する。その場合も、Sceneから描画側を呼ぶ一方向の依存にする。

## 現在のリポジトリ構成

2026年8月時点では、実装用ディレクトリは `packages` から `app` に改名されている。

```text
app/
├── data/
│   ├── characters.json
│   ├── items.json
│   ├── monsters.json
│   ├── shops.json
│   ├── skills.json
│   └── spells.json
└── fonts/
    ├── fusion-pixel-12px-monospaced-zh_hans.bdf
    ├── k6x8_gothic.bdf
    └── k8x12S.bdf

docs/
├── da0.md
└── program-architecture.md
```

`app/data` と `app/fonts` は既存資産として扱い、構造整備のために内容やキーを無断で変更しない。

データ同期スクリプト `scripts/config.js` は現時点で旧パス `packages/data` を参照している。同期スクリプトを実行する前に `app/data` へ更新する必要がある。パスが更新されるまでは、スクリプトが新しい `app/data` を読み書きするとはみなさない。

## 目標ディレクトリ構成

初期の目安を次に示す。未実装の機能に対応する空ファイルや空ディレクトリを先に作る必要はない。

```text
app/
├── main.py                  # Pyxel初期化、リソース読込、Game生成、px.run
├── game.py                  # Pyxelコールバックとアプリケーション全体の調停
├── input.py                 # 1フレーム分の入力をInputStateへ変換
├── state.py                 # Settings、SaveDataなどの永続状態
├── scene.py                 # Scene、Transition、SceneManager
│
├── scenes/
│   ├── title.py
│   ├── field.py
│   ├── town.py              # 「妖精の里」もtownの1種である
│   └── battle.py
│
├── ui/
│   ├── window.py            # 枠、文字、カーソルなどの表示部品
│   ├── dialog.py            # メッセージ、選択肢、確認
│   └── menu.py              # 共通メニューOverlay
│
├── systems/
│   ├── events.py            # イベント検索・条件評価・コマンド実行
│   ├── progression.py       # 戦闘回数、魔力減衰、世界変化
│   ├── inventory.py         # 所持、使用、装備にまたがる操作
│   └── save.py              # SaveDataと保存形式の変換・入出力
│
├── data/                    # JSONデータ
├── fonts/                   # フォント資産
├── member.py
├── monster.py
├── item.py
└── spell.py
```

例えば `scenes/town.py` が店、寺院、宿など複数の独立した変更理由を持つようになったら、次のようにパッケージへ昇格させる。

```text
app/scenes/town/
├── scene.py
├── shop.py
├── temple.py
└── renderer.py
```

行数だけを理由に分割しない。同じ理由で変更される処理は一緒に置き、異なる理由で変更される処理が混在したときに分ける。

## 実行フロー

`main.py` はPyxelとゲーム本体を接続するComposition Rootとする。

```python
class Game:
    def update(self):
        input_state = self.input_reader.read()
        transition = self.scenes.update(input_state)
        self.scenes.apply(transition)

    def draw(self):
        self.scenes.draw()
```

`Game` は個別の街、イベント、戦闘ルールを知らない。現在のSceneへ処理を渡し、返されたTransitionを適用する。

依存方向の基本は次のとおり。

```text
main.py
  ↓
Game / SceneManager
  ↓
Scene ─────→ UI / Renderer ─────→ Pyxel
  ↓
System / Domain Model
  ↓
SaveData / data/*.json
```

Domain Modelやゲームルールから `Game`、具体的なScene、Windowを参照しない。Sceneは調停役としてUIとルールの両方を利用してよい。

## Sceneの責務

Sceneは「プレイヤーが現在いる大きな操作モード」を表す。

```python
class FieldScene:
    def __init__(self, save_data, field, services):
        self.save_data = save_data
        self.field = field
        self.services = services
        self.guide_timer = 0

    def update(self, input_state):
        collision = self.field.update(input_state)

        if input_state.menu:
            return PushOverlay(MainMenu(self.save_data))

        if collision:
            return self.handle_collision(collision)

        return None

    def draw(self):
        self.field.draw()
        self.draw_guide()
```

Sceneが所有するものは次のとおり。

- そのSceneでの入力の意味
- Scene内の処理順序
- カーソル、演出、ガイド表示などの一時状態
- Scene内で発生した結果をTransitionやSystemへ渡す処理
- Scene本体の描画、または専用Rendererの呼び出し

Sceneへ置かないものは次のとおり。

- セーブ形式との変換
- 複数Sceneから使う純粋なゲームルール
- 他Sceneの内部状態
- PyxelやWindowに依存しない計算を、便宜上まとめただけのヘルパー

## Transitionと画面遷移

各所から `scene = "field"` のように文字列を直接代入しない。Sceneは遷移の意図を戻り値として返す。

代表的なTransitionは次のとおり。

- `ReplaceScene(next_scene)`: タイトルからフィールドなど、現在Sceneを置き換える
- `PushOverlay(overlay)`: メニューやダイアログを上に積む
- `PopOverlay(result=None)`: Overlayを閉じて呼び出し元へ戻る
- `StartBattle(encounter)`: 戦闘開始を要求する
- `ReturnFromBattle(result)`: 戦闘結果を遷移元へ返す
- `QuitGame()`: 終了を要求する

フェード、BGM切り替え、入力リリース待ちなど、Sceneをまたぐ共通処理はSceneManagerがTransition適用時に扱う。遷移先Sceneが、遷移元のWindow名や文字列キーを調べて復帰先を推測しない構造にする。

## OverlayとUI

メニュー、メッセージ、選択肢、確認画面などはOverlayとしてSceneの上に積む。

```text
FieldScene
  └── MainMenuOverlay
        └── ItemMenuOverlay
              └── ConfirmDialog
```

基本動作は次のとおり。

- 描画は下のSceneから順に行う。
- 入力は最上位のOverlayだけが受け取る。
- Overlayを閉じると、結果を直下の所有者へ返す。
- 全Windowを1つの巨大な条件分岐で処理しない。
- Windowは表示と基本操作の部品に留め、ゲーム進行を変更しない。
- `Window.app` のようなアプリケーション全体への逆参照を持たせない。

例えば捨てる確認は `ConfirmDialog` が `yes` / `no` を返し、アイテム画面が実際の破棄を `InventorySystem` へ依頼する。

## 状態管理

状態は寿命と所有者で分ける。

### Settings

端末やプレイヤー設定。BGM、SE、言語、表示倍率、キー配置などを持つ。ゲーム進行とは別に保存する。

### SaveData

セーブ対象となる進行状態。具体的には次のような情報を持つ。

- メンバー、装備、成長状態
- 所持品、所持金
- フラグ、訪問済み地点、取得済み宝箱
- 現在位置
- 戦闘回数などの世界進行値
- 魔力減衰や設備停止の判定に必要な値

SaveDataは「保存可能な現在のゲーム世界」を表す。ウィンドウ、描画用タイマー、選択中カーソル、Pyxelオブジェクトなどを入れない。

### Scene固有状態

フィールドガイドのタイマーは `FieldScene`、戦闘コマンド選択は `BattleScene`、店のカーソルはShop Overlayが所有する。Scene固有状態を巨大な共有RuntimeStateへ集めない。

### SystemとDomain Model

Member、Item、Spellなど、データとそのデータに密接なルールはDomain Modelへ置く。複数のModelやSaveDataをまたぐ操作はSystemへ置く。

Systemへ単一の巨大なContextやAppを渡すと、再び暗黙の依存が増える。必要なデータとサービスを明示的に渡す。Sceneだけは調停役としてSaveDataや複数サービスをまとめて受け取ってよい。

## ZEROのイベント構造

ZEROはフリーシナリオ、戦闘回数による敵の強化、魔力設備の停止、種族ごとの魔力減衰などを予定している。これらを1本の `start_event()` やイベントIDの巨大な `if` / `elif` へ追加し続けない。

通常イベントは、可能な範囲でデータとして定義する。

```json
{
  "id": "nectar_forest_entrance",
  "conditions": [
    ["flag_absent", "forest_opened"]
  ],
  "commands": [
    ["message", "forest_entrance_1"],
    ["set_flag", "forest_opened"],
    ["start_battle", "forest_guardian"]
  ]
}
```

EventRunnerは、次のような小さな汎用コマンドを順に実行する。

- メッセージ表示、選択肢
- フラグの追加・削除
- 仲間の加入・離脱
- アイテムや所持金の増減
- 戦闘開始
- 場所移動
- NPC移動
- BGM、効果音、フェード

複雑なカットシーンや固有ギミックだけをPythonの個別ハンドラーにする。汎用コマンドで無理にすべてを表現することも、すべてをPythonの条件分岐に戻すことも避ける。

## 世界進行と魔力減衰

戦闘回数や物語進行による世界変化は `WorldProgression` 相当のSystemへ集約する。

```python
progression.on_battle_finished(save_data)
facility_state = progression.facility_state(save_data, "lorewick_port")
spell_rate = progression.magic_power_rate(save_data, member)
```

Sceneやイベントは、設備停止や魔法倍率の細かい計算を独自に持たない。仕様調整時に1か所を変更すれば済む状態を保つ。

EventRunnerは必要に応じてWorldProgressionの判定結果を条件として利用するが、WorldProgressionがEventRunnerやUIを参照してはならない。

## 処理の配置基準

| 処理 | 所有者・配置先 |
|---|---|
| フィールドで入力を受けた結果 | `FieldScene` |
| フィールドや迷宮の移動ルール | `Field` または探索用System |
| フィールドの描画 | `FieldScene` またはField専用Renderer |
| 戦闘コマンドの入力 | `BattleScene` |
| ダメージ、命中、行動順の計算 | 戦闘ルール用Model/System |
| 毒や回復によるMember自身の変化 | `Member` |
| 店で何を選んだか | Shop Overlay |
| 価格、所持、装備可否 | `Item` / `InventorySystem` |
| 戦闘終了後の世界変化 | `WorldProgression` |
| ウィンドウ枠、文字、カーソル描画 | `ui/window.py` |
| 確認結果を受けた後の処理 | ダイアログを開いたSceneまたはOverlay |
| SaveDataとJSONの変換 | `systems/save.py` |
| Scene切り替え、フェード、BGM調停 | `SceneManager` |

配置に迷った場合は「どの状態を変更するか」「その状態の所有者は誰か」を先に決める。複数箇所から呼ばれるという理由だけで `util.py` へ移動しない。

## 実装上のルール

- `main.py` にゲーム内容を追加しない。
- ゲーム全体を扱う `update.py` は作らない。
- `draw()` でゲーム状態やタイマーを進めない。
- 画面遷移を文字列の直接代入で行わない。
- あるSceneから別Sceneの内部メソッドを直接呼ばない。
- WindowやDomain ModelからGame全体へ逆参照しない。
- mutableなデフォルト引数を使わない。
- `util.py` を機能の置き場所が決まらない処理の集積所にしない。
- JSONの識別子は表示名と分離し、可能な限り安定したキーを使用する。
- ゲームルールの計算は、可能な範囲でPyxelを起動せずテストできる形にする。

## 分割の判断

次の兆候が出たら、Sceneや機能をさらに分割する。

- 1つのファイルに、互いに関係しない複数画面の入力処理がある。
- 大きな `if` / `elif` がWindow名やイベントIDを横断している。
- ある機能の修正で、離れた複数ファイルを必ず同時に変更する。
- クラスがGame全体の状態へ広範囲にアクセスしている。
- `self.app` や汎用Context経由で、必要な依存が分からない。
- 描画だけを変更したいのにルールやセーブ処理へ影響する。

反対に、短いクラスを作ること自体を目的にしない。戦闘の更新と描画が同じ理由で変更されるなら、同じBattle機能の中に置いてよい。

## テスト方針

実装開始後は、リスクに応じて次の順に検証できる構造を目指す。

1. ダメージ、装備可否、魔力減衰などの純粋なルールテスト
2. SaveDataの保存・復元と旧バージョン移行テスト
3. EventRunnerの条件評価とコマンド列テスト
4. 仮のInputStateを使ったScene遷移テスト
5. Pyxelを起動したタイトル、フィールド、戦闘のスモークテスト

描画の細部すべてを単体テストする必要はない。ゲーム進行を壊しやすいルール、保存、イベント、遷移を優先する。

## 導入順序

1. `Game`、`SceneManager`、`SaveData`、`InputState` の最小構成を作る。
2. `TitleScene → FieldScene → BattleScene → FieldScene` の縦方向の流れを通す。
3. Overlay方式でメニューと確認ダイアログを追加する。
4. 小さなイベントをEventRunnerで実行する。
5. 戦闘回数と魔力減衰をWorldProgressionへ実装する。
6. 各Sceneが複数の変更理由を持ち始めた時点で、サブ機能やRendererへ分割する。

最初から完全な汎用フレームワーク、ECS、汎用イベントバスを導入しない。ZEROに実際に必要な機能を縦に完成させながら境界を育てる。

## リファレンスプロジェクト

同階層に過去作がある。

- `../dungeon-antiqua`: Dungeon Antiqua 1
- `../dungeon-antiqua2`: Dungeon Antiqua 2

過去作は、ゲームルール、Pyxel固有処理、データ形式、ビルド処理、演出を調査するための参照元とする。ただし、巨大な `App.update()`、ゲーム全体の `update.py`、全Windowを処理する単一ディスパッチャはZEROへそのまま移植しない。

既存実装を移植するときも、まずZEROでの状態の所有者を決め、Scene、System、Domain Modelのいずれかへ配置する。
