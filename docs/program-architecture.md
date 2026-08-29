# Dungeon Antiqua ZERO プログラム構造

## この文書の位置付け

この文書は、Dungeon Antiqua ZERO（以下、ZERO）の実装を開始・拡張するときのプログラム構造の基準を定める。

ゲーム内容、世界設定、シナリオ、システム仕様のベースドキュメントは [`content/docs/da0.md`](../content/docs/da0.md) とする。本書はそれらを実装するための責務分割、依存関係、状態管理、画面遷移の方針を扱う。共有データの運用は [`content-workflow.md`](./content-workflow.md) に定める。

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

2026年8月時点では、実装用ディレクトリは `packages` から `app` に改名されている。スタッフ共有コンテンツは独立したprivateリポジトリへ履歴付きで分離し、`content` 自体をGit submoduleとして配置する。

```text
app/
├── input.py                  # Pyxel入力を論理InputStateへ変換
├── state.py                  # 言語を含む端末・プレイヤー設定
├── localization.py           # 多言語フィールドの選択とフォールバック
├── ui/
│   ├── tagged_text.py        # タグ付きテキストとアイコン描画
│   └── window.py             # 枠、文字、カーソル、標準フォント付き生成
├── resources/
│   ├── fonts.py              # 言語別フォントの読込とキャッシュ
│   └── images.py             # 生成済み画像bundleの本番用loader
├── data/
│   ├── characters.json
│   ├── items.json
│   ├── monsters.json
│   ├── shops.json
│   ├── skills.json
│   ├── spells.json
│   └── texts.json            # 安定キーを持つ共通表示語彙
├── images/                    # content/imagesから生成する実行時画像データ
└── fonts/
    ├── fusion-pixel-12px-monospaced-zh_hans.bdf
    ├── k6x8_gothic.bdf
    └── k8x12S.bdf

content/                    # 共有コンテンツsubmodule
├── data/                   # JSONの正本
├── images/                 # PNG/GIF画像の正本
├── docs/da0.md             # 企画・仕様のベースドキュメント
├── portal/                 # スタッフポータルの生成処理・表示資産
└── scripts/                # JSON検証とGoogle Sheets同期

docs/
├── content-workflow.md
└── program-architecture.md

scripts/
├── sync-content.mjs        # submoduleからapp/dataを生成
└── build-images.py         # PNGをパレット番号へ変換してapp/imagesを生成

tools/
├── README.md               # 開発用プログラムの配置基準と操作方法
├── image_viewer.py         # 本番用画像をPyxelで確認するviewer
└── screen_mocks/
    ├── battle.py           # 本番用部品を使う戦闘画面モック
    ├── status.py           # ステータス画面モック
    └── menu.py             # メニュー画面モック
```

`content/data` は共有JSONの正本である。`app/data` は `npm run content:sync` で作るGit管理対象外の実行時コピーであり、直接編集しない。ゲームコードは外部リポジトリやGoogle Sheetsを知らず、従来どおり `app/data` を読む。

`content/images` はゲームとスタッフポータルで共有するPNG/GIF画像の正本である。`app/images` は `npm run images:build` で作るGit管理対象外の実行時データであり、直接編集しない。画像のパレット変換はビルド時に行い、実行時は生成済みの1ピクセル1バイトのパレット番号を読み込む。

Google Sheetsとの双方向同期とポータル生成は共有コンテンツsubmoduleの責務とし、ゲーム本体の `scripts/` へ混在させない。`app/fonts` は引き続きゲーム本体の既存資産として扱う。

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
├── resources/
│   └── images.py            # manifestと画像bundleの読込・検証
│
├── data/                    # content/dataから生成するJSON
├── images/                  # content/imagesから生成するmanifestと画像バイナリ
├── fonts/                   # フォント資産
├── member.py
├── monster.py
├── item.py
└── spell.py
```

## 入力の責務

物理入力の取得と画面内での意味付けを分離する。`app/input.py` の `PyxelInputReader` はキーボード、ゲームパッド、アナログスティックを `InputState` へ変換するが、戦闘コマンド、画面遷移、カーソル対象などのゲーム上の意味を知らない。`InputState` は1フレーム分の不変なスナップショットとし、受け取ったScene、Overlay、Windowが内容を書き換えない。

```text
Pyxelの物理入力
  → PyxelInputReader
  → InputState
  → 最上位のSceneまたはOverlay
  → WindowCursorやScene固有処理
```

`InputBindings` は論理操作ごとに複数のPyxelボタンを保持する。初期設定は矢印キーとゲームパッドの方向、Z・EnterとゲームパッドAの決定、X・Backspace・EscapeとゲームパッドBのキャンセル、S・TabとゲームパッドXのメニューとする。キー設定やAB反転を実装するときは、`Settings`から `InputBindings` を生成し、Reader内部やモジュールグローバルを書き換えない。

`InputState.navigation` はカーソル向けの単発およびリピート込み方向、`held_direction` はフィールド移動など押下中の毎フレーム処理に使う方向を表す。方向は上下左右のいずれか1つとし、新しい方向が押された場合は保持中の以前の方向より優先する。新しい方向が離された後も別の方向が保持されていれば、その方向へ切り替える。

方向リピートの状態、アナログスティックのデッドゾーン、直前フレームの押下状態は `PyxelInputReader` インスタンスが所有する。60fpsでDA2と同じ時間感覚にするため、既定の方向リピートは20フレーム後から4フレーム間隔とする。決定、キャンセル、メニューは標準ではリピートさせず、初回押下だけを `triggered=True` とする。押したままかどうかは別の `held` で表し、Scene遷移時の入力リリース待ちなどに利用する。

本番では `Game.update()` がフレームごとに一度だけ `poll()` し、SceneManagerを通して最上位Overlayまたは現在のSceneへ渡す。開発用モックは独立したComposition RootとしてReaderを1つ生成し、同じ `InputState` とWindow部品を直接利用する。モック固有のQ終了などは、Qをキャンセルへ追加したBindingsをReaderへ渡して表現する。

```python
input_state = input_reader.poll()
command_window.update(input_state.navigation)

if input_state.confirm.triggered and command_window.is_open:
    command = command_cursor.selected_key
```

## 画像リソースの責務

画像のPNG/GIF原本、ゲーム用生成物、実行時のイメージバンクを同じものとして扱わない。

- `content/images`: 編集、レビュー、ポータル表示に使うPNG/GIFの正本
- `app/images/manifest.json`: 安定した画像ID、寸法、バイナリ内の配置情報
- `app/images/graphics.bin`: Pyxelパレット番号へ変換済みの画素列
- `app/assets.pyxres`: UIや共通タイルなど、常駐させる固定リソース
- Pyxelイメージバンク: 現在のSceneで必要な画像を置く実行時領域

SceneやRendererは表示名や元画像ファイル名を直接組み立てず、manifestの画像IDを使う。元画像の読み込み、色変換、ファイルI/O、イメージバンクへの転送は `draw()` で行わず、起動時またはScene遷移時に画像リソースを所有するサービスが行う。Domain Modelはバンク番号やUV座標を所有しない。

ゲーム起動時にComposition Rootで `ImageResources` を1つ生成し、画像を必要とするSceneやRendererへ明示的に渡す。モジュールグローバルのloaderや汎用 `util.set_image()` は作らない。

```python
image_resources = ImageResources()
field_scene = FieldScene(save_data, images=image_resources)
```

イメージバンクへの転送には `ImageResources.copy_to_bank()` を標準APIとして使う。呼び出し側は生の画素配列ではなく安定した画像IDと転送先を指定する。256×256を超えるシートやアニメーションの一部を転送するときは、転送元矩形を明示する `copy_region_to_bank()` を使う。

```python
images.copy_to_bank("background/bg_nector", bank=1, x=0, y=0)

images.copy_region_to_bank(
    "effects/spells",
    bank=2,
    source_x=0,
    source_y=64,
    width=128,
    height=64,
    x=0,
    y=0,
)
```

いずれも転送元または転送先が範囲外ならエラーとし、暗黙のクリッピングは行わない。転送はScene開始、敵出現、装備変更など画像が変わったタイミングで行い、`draw()` ではバンクからの描画だけを行う。バンク番号と配置座標はSceneやRenderer側の一時的な表示設計であり、Domain Modelや画像manifestへ保存しない。

パレット番号1の `#FF0080` は、ZERO全体で画像の透過色として予約する。画像ビルドではPNGの完全透明ピクセル、GIFの論理背景色と完全透明ピクセルを番号1へ変換し、半透明ピクセルはエラーとする。透過付き画像を描画するRendererは `blt()` / `bltm()` の `colkey` に1を指定する。番号1を通常の表示色として使わず、透過番号をSceneや個別画像ごとに変更しない。GIFは静止画だけを扱い、アニメーションGIFは専用の実行時仕様を定めるまで変換しない。

## 開発用中間プログラム

画像viewer、マップ確認、戦闘テストなど、Pyxelを起動して本番データを確認するプログラムはリポジトリ直下の `tools/` に置く。自動生成や非対話の検証を行う `scripts/`、配布対象の `app/` と責務を分ける。

開発用プログラムのために画像やJSONを複製しない。`app/data`、`app/images`、`app/assets.pyxres`、`app/assets.pyxpal` を本番と同じ入口から読む。manifestや保存形式など、本番と共有すべき解釈処理は `app/resources` や該当Systemが所有し、`tools/` は画面、入力、選択中の対象といったツール固有状態だけを所有する。これによりviewerだけが成功し、ゲーム本体では読めないという形式差異を防ぐ。

ツール同士を巨大な共通Appへ統合しない。各ツールを `python3 -m tools.<module>` で独立起動できる小さなComposition Rootとし、複数ツールで本当に同じ起動処理が生じた場合だけ `tools/` 内の小さな共通モジュールへ抽出する。`tools/` は `pyxel package app ...` の配布対象に含めない。

戦闘、メニュー、ショップなどの画面レイアウトを試作するプログラムは `tools/screen_mocks/` に画面単位で置く。`battle.py`、`menu.py`、`shop.py` のように独立させ、別画面の仮状態や描画分岐を1つのviewerへ集めない。画面モック間の共通基盤は先に作らず、複数のモックで実際に重複が生じた時点で小さく抽出する。

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

### Windowの座標と描画

共通ウィンドウは `app/ui/window.py` の `Window` を使う。ウィンドウの外接矩形はテキストと同じグリッド単位の `x`, `y`, `width`, `height` で指定する。横・縦とも1単位は4pxとし、描画時に内部でピクセルへ変換する。幅と高さの最小値は4単位で、どちらも8×8の四隅を配置できる16pxに相当する。

通常枠は `assets.pyxres` のイメージバンク0、`(16, 0)` から `(31, 15)` にある四隅と、そこから切り出した4px幅または4px高の辺を反復して描く。`thin_frame=True` を指定した場合は、同じ構成の細い枠 `(32, 0)` から `(47, 15)` へ四隅と辺の転送元を切り替える。枠内は `GRADIENT_COLORS` の2色を使い、第2色で下地を塗った上へ第1色を重ねる。第1色のdither率を上から `1.0`, `0.75`, `0.5`, `0.25`, `0.0` と変化させ、5段階のグラデーションにする。全段階の高さは均等に分割し、割り切れない余りの1pxは先頭と末尾が同じ高さになるよう中央対称に配分する。グラデーション領域は外接矩形の各辺から4px内側まで広げて先に塗り、その後に枠を重ねる。これにより枠の内側の丸みを保つ。描画後は後続描画へ影響させないようditherを1.0へ戻す。

テキスト座標はウィンドウ枠の左上を原点とし、横・縦とも4pxの相対グリッドで指定する。`(0, 0)` は枠と重なる位置であり、枠から左右8pxずつ内側に入った従来の内容領域左上は `(2, 2)` となる。行の配列として保持せず、各 `WindowText` が文字列、x、y、色、任意のフォントを所有する。同じウィンドウ内で左右の列や異なる高さへ個別に配置できる。ウィンドウまたは個々のテキストへ `pyxel.Font` を渡し、フォント幅を位置決めの単位にしない。

通常のSceneとOverlayは、現在言語の標準フォントで初期化した `WindowFactory` からWindowを生成する。`WindowText.font=None` はWindowの標準フォントを継承し、個別のフォント指定がある場合だけそちらを優先する。解決順は「WindowText個別フォント → Window標準フォント」とし、言語状態やモジュールグローバルをWindowから参照しない。これにより通常のテキストごとに同じフォントを繰り返し指定せず、数値など例外的な表示だけを個別指定できる。

テキストは既定で本体より1px下へパレット0の同じ文字を先に描き、影を付ける。`shadow_color` で影色を変更でき、`None` を指定すると影を描かない。

`transparent=True` を指定したWindowは、グラデーションと枠を描かずテキストだけを描画する。この場合もWindow左上をテキスト座標の原点とし、通常Windowと同じ4×4pxグリッドと領域を使う。背景上へ座標を揃えて文字だけを重ねる用途に使い、透明かどうかによってテキスト座標を変えない。

### Windowの開閉アニメーション

開閉状態は各 `Window` が `WindowState.CLOSED`、`OPENING`、`OPEN`、`CLOSING` のいずれかとして所有する。通常は従来と同じ `OPEN` で生成し、初期状態を閉じたい場合だけ `opened=False` を指定する。所有元のSceneまたはOverlayは `open()` / `close()` で開始を指示し、毎フレーム `Window.update()` を呼ぶ。

アニメーションはウィンドウ本来の座標、サイズ、テキスト、カーソル位置を変更せず、中央を基準にした描画クリップの高さだけを変える。60fpsで上下の端を1フレームにつき4pxずつ動かし、見える全高は1フレームにつき8px増減する。端数がある最終フレームだけ本来の高さまたは0へ揃える。開閉途中に逆の操作を受けた場合は、現在の表示高から反転する。

`update()` が表示高と状態を進め、`draw()` は現在の表示高でクリップして描くだけとする。通常Windowは開閉中も現在の上下端へ枠を描き、背景と枠だけの小さなWindowが中央から伸縮して見えるようにする。文字とカーソルは開き切ってから描画する。透明Windowには枠がないため、開閉中は文字とカーソルを現在の表示高でクリップする。閉じたWindowは何も描画せず、開き切ったWindowはクリップを使わず通常描画する。

開閉中はカーソル移動と浮遊タイマーを進めず、`OPEN` の間だけ `Window.update(input_state.navigation)` がカーソルへ入力を渡す。決定入力を開閉やゲーム進行のどちらとして扱うかは、WindowではなくSceneまたはOverlayが判断する。

### Windowのカーソル

選択肢を持つWindowには `Window.set_cursor()` で `CursorTarget` を登録する。ターゲットの `x`, `y` はテキストと同じWindow相対の4×4pxグリッドで指定し、`key` にはSceneまたはOverlayが確定時に受け取る任意の識別子を設定できる。キーを必要としないカーソル位置では `key=None` のまま登録してよい。

ターゲットの存在、選択可否、キーの有無は別の概念として扱う。空きマスにはターゲットを登録せず、表示はするがカーソルを合わせない項目は `selectable=False` とする。`key=None` を選択不可の印として使わない。全ターゲットが選択不可の場合は選択位置を持たず、カーソルを描画しない。

上下移動は現在位置と同じ `x`、左右移動は同じ `y` のターゲットを座標順に循環する。空きマスと `selectable=False` のターゲットはWindow側で自動的にスキップし、同じ行または列に別の選択可能なターゲットがなければ現在位置に留まる。1列だけを登録した標準的なメニューは、この規則により上下移動だけが有効になる。

カーソルはイメージバンク0の本体 `(48, 0)` から16×16px、影 `(64, 0)` から16×16pxを使い、透過色は1とする。ターゲットのテキスト原点より8px左を基準位置とし、影は固定、本体だけを上へ0～2px動かす。浮遊パターンは `(0, 0, 0, 1, 2, 2, 2, 1)` とする。

ZEROの実行フレームレートは60fpsとする。DA2の30fps時と同じ1.6秒周期を維持するため、浮遊パターンの各段階は12フレーム継続する。カーソルのアニメーションタイマーは `update()` で進め、`draw()` では変更しない。入力待ちでない場合はタイマーを停止する。方向入力のリピートは `PyxelInputReader` が共通して処理する。

カーソルは入力デバイスを直接読まず、Sceneまたは最上位Overlayから `InputState.navigation` を `WindowCursor.update()` へ渡す。決定入力時は `selected_target` または `selected_key` を取得し、その後のゲーム進行はカーソルやWindowではなく所有元のSceneまたはOverlayが処理する。

```python
window = Window(2, 2, 60, 16, font=font_8x12)  # 8, 8, 240, 64px
window.add_text("ITEM", x=2, y=2)
window.add_text("10", x=42, y=2, font=font_6x8, shadow_color=0)
window.draw()

thin_window = Window(2, 20, 30, 8, thin_frame=True)
thin_window.draw()

guide = Window(2, 2, 60, 8, transparent=True)
guide.add_text("透明ウィンドウ", x=0, y=0)
guide.draw()
```

### テキスト内アイコン

`WindowText.text` と `Window.add_text()` に渡す文字列では、`%FIRE%` のようなタグをイメージバンク0の8×8アイコンとして描画する。タグは半角の `%` で囲んだ大文字英数字とアンダースコアからなり、定義済みのタグだけを変換する。未知のタグ、不完全なタグ、小文字を含むタグ、通常の `%` は消さずにそのまま文字として描画する。

文字列は左から描画し、通常文字は使用中のフォントの `text_width()`、アイコンは8pxだけ描画位置を進める。アイコンは12px高の本文行内で上から3px下げ、透過色1で描画する。連続するタグの間に空白は不要とする。

| タグ | 座標 | タグ | 座標 |
| --- | --- | --- | --- |
| `%FIRE%` | `(0, 16)` | `%FIRE_DISABLED%` | `(0, 24)` |
| `%FREEZE%` | `(8, 16)` | `%FREEZE_DISABLED%` | `(8, 24)` |
| `%DARK%` | `(16, 16)` | `%DARK_DISABLED%` | `(16, 24)` |
| `%SLEEP%` | `(24, 16)` | `%SLEEP_DISABLED%` | `(24, 24)` |
| `%POISON%` | `(32, 16)` | `%POISON_DISABLED%` | `(32, 24)` |
| `%PARALIZE%` | `(40, 16)` | `%PARALIZE_DISABLED%` | `(40, 24)` |
| `%CONFUSE%` | `(48, 16)` | `%CONFUSE_DISABLED%` | `(48, 24)` |
| `%SILENCE%` | `(56, 16)` | `%SILENCE_DISABLED%` | `(56, 24)` |
| `%DEATH%` | `(64, 16)` | `%DEATH_DISABLED%` | `(64, 24)` |
| `%RIGHT%` | `(72, 16)` | `%LEFT%` | `(80, 16)` |
| `%HEAD%` | `(72, 24)` | `%BODY%` | `(80, 24)` |
| `%ARM%` | `(88, 24)` | `%UNDEAD%` | `(96, 16)` |
| `%FLY%` | `(96, 24)` | `%SWORD%` | `(104, 16)` |
| `%KATANA%` | `(112, 16)` | `%KNIFE%` | `(120, 16)` |
| `%SPEAR%` | `(128, 16)` | `%AXE%` | `(136, 16)` |
| `%HAMMER%` | `(144, 16)` | `%THROWING%` | `(152, 16)` |
| `%ROD%` | `(104, 24)` | `%WAND%` | `(112, 24)` |
| `%SHIELD%` | `(120, 24)` | `%MYSTIC%` | `(128, 24)` |
| `%SACRED%` | `(136, 24)` | `%NETHER%` | `(144, 24)` |

指定上は `(16, 16)` と `(144, 24)` の両方が `%DARK%` だったが、同じタグから2つの座標を一意に選べない。既存の呪文説明が使う闇属性アイコンを `%DARK%` `(16, 16)` とし、暗黒呪文系の後者は `%NETHER%` `(144, 24)` として区別する。元素、神聖、暗黒の呪文系アイコン名は、現実装に合わせて `%MYSTIC%`、`%SACRED%`、`%NETHER%` とする。

## 状態管理

状態は寿命と所有者で分ける。

### Settings

端末やプレイヤー設定。BGM、SE、言語、表示倍率、キー配置などを持つ。ゲーム進行とは別に保存する。

言語は `Language` で表し、保存値と共有JSONの接尾辞には `ja`、`en`、`zhcn` を使う。初期値は `ja` とする。フォントファイル名に含まれる `zh_hans` はアセット名であり、保存値やデータキーには使用しない。

言語別の標準フォントは `FontResources` が所有する。フォントは必要になった言語から読み込み、同じ言語では生成済みの `pyxel.Font` を再利用する。

| 言語 | 標準フォント |
|---|---|
| `ja` | `k8x12S.bdf` |
| `en` | `k6x8_gothic.bdf` |
| `zhcn` | `fusion-pixel-12px-monospaced-zh_hans.bdf` |

選択中言語のフォントがない場合は、別言語のフォントへ暗黙に置き換えずリソースエラーとする。簡体字を日本語フォントへ置き換えても表示を保証できず、配布物の欠損を隠すためである。

多言語フィールドの選択は `Localizer` が担当し、フォント読込とは分離する。フォールバック順は日本語が `ja → en`、英語が `en → ja`、簡体字中国語が `zhcn → en → ja` とする。任意の先頭フィールドを選ぶような非決定的なフォールバックは行わない。

英語の表示文字列はDA2と同様、原則として表示時にASCII文字と半角スペースを全角へ変換する。JSONの英語原文は半角のまま保持し、`Localizer.value()` は変換前の値、`Localizer.text()` は表示用に正規化した値を返す。これにより識別子、保存値、計算値へ全角変換が波及しない。`%FIRE%` のような表示制御タグ自体は変換せず、半角表示が必要な箇所についても専用タグで明示する。専用タグの構文と描画規則は、具体的な利用箇所を実装するときに定める。

キャラクター名など各レコード固有の表示値は `name_ja`、`name_en`、`name_zhcn` のような接尾辞付きフィールドに置く。種族名、性別名、画面項目名など複数レコードや画面から参照する表示語彙は `texts.json` に置き、安定した `text_key` で参照する。`TextCatalog` はキーからレコードを引き、実際の言語選択とフォールバックを `Localizer` に委譲する。Domain Modelとセーブデータには翻訳後の文字列ではなく、`FAIRY`、`FEMALE` などの安定キーを保持する。

`Member` は現在言語やフォントを保持しない。名前、種族、性別の表示値が必要な場合は、Composition RootまたはSceneから現在の `Localizer` と `TextCatalog` を明示的に渡して表示用の不変スナップショットを生成する。固定幅化、余白、座標などは画面側の責務とし、DA2の `name_disp` のようなレイアウト処理をDomain Modelへ含めない。

設定画面で言語を変更した場合は `Settings.with_language()` で新しい設定スナップショットを作って保存し、新しい `Localizer` と標準フォントで表示中のWindowを再構築する。既存Windowがグローバルな言語変更を監視したり、フォントだけを後から差し替えたりしない。翻訳後の文字幅が言語ごとに異なるため、必要なレイアウト変更もWindow再構築時に反映する。

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
