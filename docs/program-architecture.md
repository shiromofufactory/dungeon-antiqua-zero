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
├── item_detail.py            # メニュー・店・戦闘で共有するアイテム詳細表現
├── systems/
│   └── inventory.py         # 所持数、破棄、装備交換を含むアイテム操作
├── ui/
│   ├── input_icons.py        # 論理操作と入力種別から表示タグを選択
│   ├── tagged_text.py        # タグ付きテキストとアイコン描画
│   ├── text_format.py        # 数値やプレイ時間の共通表示形式
│   └── window.py             # 枠、文字、カーソル、標準フォント付き生成
├── resources/
│   ├── data.py               # 生成済みJSON配列の読込と構造検証
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
    ├── _runtime.py         # Pyxel初期化、共通資産、モック入力
    ├── _runner.py          # 例外表示とCLI終了コード
    ├── _fixtures.py        # 疑似パーティなどモック専用状態
    ├── _party_status.py    # 子メニュー共通の下部パーティ表示
    ├── battle.py           # 本番用部品を使う戦闘画面モック
    ├── status.py           # メニューから使うステータス画面部品
    ├── spell.py            # メニューから使う呪文画面部品
    ├── item.py             # メニューから使うアイテム画面部品
    ├── equipment.py        # メニューから使う装備画面部品
    └── menu.py             # メニューと各子画面の接続モック
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
├── rendering/
│   └── palette.py           # 一時パレットシフトと色変換
│
├── data/                    # content/dataから生成するJSON
├── images/                  # content/imagesから生成するmanifestと画像バイナリ
├── fonts/                   # フォント資産
├── member.py
├── monster.py
├── item.py
├── skill.py
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

`InputBindings` は論理操作ごとに複数のPyxelボタンを保持する。初期設定は矢印キーとゲームパッドの方向、Z・EnterとゲームパッドAの決定、X・Backspace・EscapeとゲームパッドBのキャンセル、S・TabとゲームパッドXのメニューとする。ページやメンバーの前後切り替えには `previous_page` / `next_page` を使い、ゲームパッドの左・右ショルダーを割り当てる。キーボードのShiftキーには割り当てない。キー設定やAB反転を実装するときは、`Settings`から `InputBindings` を生成し、Reader内部やモジュールグローバルを書き換えない。

`InputState.navigation` はカーソル向けの単発およびリピート込み方向、`held_direction` はフィールド移動など押下中の毎フレーム処理に使う方向を表す。方向は上下左右のいずれか1つとし、新しい方向が押された場合は保持中の以前の方向より優先する。新しい方向が離された後も別の方向が保持されていれば、その方向へ切り替える。

方向リピートの状態、アナログスティックのデッドゾーン、直前フレームの押下状態は `PyxelInputReader` インスタンスが所有する。60fpsでDA2と同じ時間感覚にするため、既定の方向リピートは20フレーム後から4フレーム間隔とする。決定、キャンセル、メニュー、前後ページは標準ではリピートさせず、初回押下だけを `triggered=True` とする。押したままかどうかは別の `held` で表し、Scene遷移時の入力リリース待ちなどに利用する。

`InputState.device` は、その時点で操作案内に使う入力種別を
`InputDevice.KEYBOARD` / `InputDevice.GAMEPAD` で表す。Readerの初期値はキーボードとし、
どちらか一方の入力だけを検出したフレームでその種別へ切り替え、入力がない間と両方を
同時に検出した間は直前の種別を維持する。アナログスティックはゲームパッド入力として
扱う。現段階ではDA2のWASDモードは設けない。

操作案内ではSceneやOverlayが論理操作の `InputAction` と
`InputState.device` を `ui.input_icons.input_icon_tag()` へ渡し、対応するテキスト内アイコン
タグを得る。これにより、画面ごとにキーボード／ゲームパッドの座標対応を持たない。
開発用モックで入力種別を固定する場合も `InputDevice` を明示して同じ変換を使う。

本番では `Game.update()` がフレームごとに一度だけ `poll()` し、SceneManagerを通して最上位Overlayまたは現在のSceneへ渡す。開発用モックは独立したComposition RootとしてReaderを1つ生成し、同じ `InputState` とWindow部品を直接利用する。モック固有のQ終了などは、Qをキャンセルへ追加したBindingsをReaderへ渡して表現する。

```python
input_state = input_reader.poll()
command_window.update(input_state.navigation)

if input_state.confirm.triggered and command_window.is_open:
    command = command_cursor.selected_key
```

## ゲームデータリソースの責務

`app/resources/data.py` の `load_record_array()` は、`app/data` の生成済みJSONを
UTF-8で読み込み、ルートがオブジェクト配列であることまでを検証する。本編と開発用
モックは同じ入口を使い、画面ごとにファイル不在、JSON構文、ルート構造の処理を
複製しない。ファイル名は `app/data` 直下の名前だけを受け付け、任意のパス探索には
使用しない。

各レコードの意味的な検証は `Item.from_record()`、
`CharacterDefinition.from_record()` などのDomain Modelが担当する。安定キーによる索引、
重複判定、レコード間参照の解決は、必要なマスターデータ単位のloaderまたは
Composition Rootで行う。モック用の加入済みパーティは本編のマスターデータではないため、
`tools/screen_mocks/_fixtures.py` が生成し、`app/resources` へ置かない。

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

### 一時パレットシフト

キャラクター単位の暗転、点滅、色付きエフェクトは `rendering/palette.py` の
`PaletteShifter` を使う。Pyxel初期化と本番パレット読込の直後に1つ生成し、基準色を
不変のタプルとして保持する。名前付きの変換後パレットは基準パレットと同じ色数で末尾へ
追加し、描画直前だけ元の色番号を追加領域へ `pyxel.pal()` で割り当てる。対象描画後は
例外発生時も含めて必ず `pyxel.pal()` を引数なしで呼び、後続のWindow、文字、画像へ
色変換を漏らさない。

標準の `dimmed` は全基準色を黒へ50%混合したパレットとする。変換済み画像を複製せず、
顔、フィールドキャラクター、戦闘キャラクターなど同じ仕組みを必要とするRendererへ
`PaletteShifter` を明示的に渡す。SceneやOverlayは対象と効果名だけを決め、Member、Item、
SaveDataなどのDomain ModelはPyxelの色番号や `PaletteShifter` を保持しない。時間変化する
効果は名前付き変換先を `define_mix()` で更新し、タイマー自体は所有元のSceneが進める。
画面全体へ時間変化する色調を適用する場合は、外側を `shifted()` で囲まない。
内側の局所効果が `pyxel.pal()` を解除すると外側の割り当ても失われるため、基準色と
全派生色へ同じ変換を合成する `set_global_mix()` を使用する。

## 開発用中間プログラム

画像viewer、マップ確認、戦闘テストなど、Pyxelを起動して本番データを確認するプログラムはリポジトリ直下の `tools/` に置く。自動生成や非対話の検証を行う `scripts/`、配布対象の `app/` と責務を分ける。

開発用プログラムのために画像やJSONを複製しない。`app/data`、`app/images`、`app/assets.pyxres`、`app/assets.pyxpal` を本番と同じ入口から読む。manifestや保存形式など、本番と共有すべき解釈処理は `app/resources` や該当Systemが所有し、`tools/` は画面、入力、選択中の対象といったツール固有状態だけを所有する。これによりviewerだけが成功し、ゲーム本体では読めないという形式差異を防ぐ。

ツール同士を巨大な共通Appへ統合しない。単独で確認するツールは `python3 -m tools.<module>` で独立起動できる小さなComposition Rootとし、画面遷移を確認する場合は起点となるモックだけをComposition Rootにする。複数ツールで本当に同じ起動処理が生じた場合だけ `tools/` 内の小さな共通モジュールへ抽出する。画面モックでは、Pyxelと共通資産の初期化を `_runtime.py`、想定内例外と終了コードの変換を `_runner.py`、疑似パーティを `_fixtures.py` が担当する。Settings、SaveData、画面固有画像は起点が生成し、子画面へ必要な依存だけを明示的に渡す。すべてを格納する汎用Contextは作らない。`tools/` は `pyxel package app ...` の配布対象に含めない。

戦闘、メニュー、ショップなどの画面レイアウトを試作するプログラムは `tools/screen_mocks/` に画面単位で置く。`battle.py`、`menu.py`、`shop.py` のように起点を独立させ、無関係な画面の仮状態や描画分岐を1つのviewerへ集めない。メニュー配下のステータス画面や呪文画面のように実際の遷移関係がある場合は、子画面を別モジュールの部品として保ち、起点側から状態と資産を明示的に渡す。画面モック間の共通基盤は先に作らず、複数のモックで実際に重複が生じた時点で小さく抽出する。

呪文マスターの文字列enum、習得レベル、表示名・説明の解釈は `app/spell.py` が所有する。
レベル1から9の呪文はMemberの対応する元素・神聖・暗黒熟練度以下を習得済みとし、
レベル0は通常成長から除外してイベント習得キーがある場合だけ習得済みとする。呪文画面モックは
この判定結果を描画するだけとし、イベント習得状態や呪文効果を画面固有状態へ埋め込まない。

アイテム画面モックはDA2準拠の「つかう／すてる／いちらん／だいじなもの」の
4カテゴリ、左の一覧、右の情報欄を持つ。現段階の疑似所持品は `items.json` の全レコードを
1個ずつとし、だいじなものは未定義のため空とする。情報欄は選択中の名前、種別、装備条件、
0以外の攻撃・命中・防御・回避・術防御、能力補正、フィールド回復、射程を表示する。
カテゴリカーソルが「つかう」「すてる」「いちらん」にある間は、情報欄をDA2と同じ
所持数（上限255）と記録済み種類数へ切り替える。「だいじなもの」のカテゴリカーソル中は
空欄とする。破棄して所持数が減っても記録済み状態は維持する。
能力補正は1能力につき1行とし、正負の符号を表示する。フィールド回復は数値を出さず、
DA2と同じ「HP じどうかいふく」または「HP じょじょにげんしょう」とする。破棄は
DA2と同じ確認文とはい／いいえの選択を表示し、はいの場合だけ `InventorySystem` が
所持数を1減らす。`price=0` は破棄不可を表し、確認画面を開かずDA2と同じエラー演出を
返す。下部の顔とHP表示は呪文画面と
`_party_status.py` の同じ部品を使う。一覧は選択行が上下端を越えると表示開始位置を1件ずつ
追従させ、左右および前後ページ入力では表示行数ぶん移動する。一覧Windowは従来より
8px右へ広げ、情報欄のテキストは追加インデントを置かず枠内側から開始することで、
情報欄テキストの画面上の絶対位置は維持する。一覧が表示行数を超える場合は、右枠の
上端と下端へ共通の縦スクロールインジケーターを表示する。
装備品へカーソルを合わせている間は、装備できないMemberの顔だけを共通の
`PaletteShifter` で暗く描画する。カテゴリ選択中と道具選択中は顔色を変更しない。

種別の `RIGHT` は「かたてぶき」、`TWO_HANDS` は「りょうてぶき」とし、武器種を併記する。
防具分類の `GENERAL` は「だれでも」、`HEAVY` は「おもいぼうぐ」、`MAGICAL` は
「まほうぼうぐ」とする。装備条件の `LV9` は該当武器種の武器レベル9を表す。
武器は武器種名の直前へ `%SWORD%` など副種別と同名のアイコンタグを置き、頭・体・腕は
部位名の直前へそれぞれ `%HEAD%`、`%BODY%`、`%ARM%` を置く。
射程2は「こうれつから こうげきかのう」、射程3は
「えんきょりこうげき かのう」と表示する。射程2の武器は後列から攻撃できるが、
実際の威力補正は画面ではなく戦闘ルールが担当する。射程2は表示行数によらず
`item.detail.reach.2` 1キーで保持し、1行なら文字列、複数行なら文字列配列を使う。

攻撃属性は `AttackAttribute`、追加効果は `AdditionalEffect`、種族特効は
`MonsterTribe` の安定キーへ変換して `Item` が保持する。攻撃属性は属性アイコン付きの
「ぞくせい：🔥ほのお」形式とし、闇属性は「ぞくせい：🌙やみ」と表示する。追加効果
`吸` は属性とは別に「ついかこうか：きゅうしゅう」と表示する。
追加効果 `止` は次の行動を封じる「スタン」、`破` は「ぼうぎょダウン」とする。
属性、状態、種族など複数画面で使う語は `term.attribute.*`、`term.condition.*`、
`term.effect.*`、`term.monster_tribe.*` の共通キーで保持する。アイコンがある属性・状態は
共通語自体へアイコンタグを含める。アイテム画面は `item.detail.attribute`、
`item.detail.additional_effect`、`item.detail.resistance`、
`item.detail.effective_tribe` の `$ATTRIBUTE$`、`$EFFECT$`、`$RESISTANCE$`、`$TRIBE$`
へ共通語を代入し、属性・状態・種族ごとの完成文を個別キーとして重複保持しない。
装備条件の「専用」「除外」も
`item.detail.requirement.only` / `item.detail.requirement.excludes` の `$TARGET$` へ
`race.*` または `gender.*` の共通語を代入する。Memberの状態表示も同じ
`term.condition.*` を参照する。
種族特効は `ANIMAL`、`UNDEAD`、`GOBLIN`、`HUMAN`、`MAGE`、`GIANT`、
`DRAGON`、`ANIMATED`、`DEMON` の9種とし、旧スペル `DEAMON` は受理しない。
耐性は `ResistanceType` の定義順で1耐性につき1行を表示する。対応アイコンがない
スタン耐性はテキストだけで表示する。
説明欄は基本性能、攻撃属性、追加効果、耐性、能力補正・射程・種族特効などその他の特性、
使用効果の順で構成し、HP回復・減少と `special` は末尾に置く。盾は種別名「たて」の
直前へ `%SHIELD%` アイコンを置く。
基本性能の表示名はステータス画面のキーを流用せず、`item.detail.attack`、
`item.detail.hit`、`item.detail.defense`、`item.detail.evasion`、
`item.detail.spell_resistance` のアイテム画面専用キーを使う。
`special` は `ItemSpecial` の10種の安定キーへ変換して `Item` が保持し、
`item.detail.special.<special>` の辞書行をその他の特性として表示する。未入力で
`pending: true` の辞書行は表示しない。`%COL_BLUE%` は `ui/colors.py` の
`BLUE_TEXT_COLOR`（色13）へ変更し、
`%COL_END%` は白（色5）へ戻すゼロ幅タグとして共通のタグ描画処理が解釈する。

アイテム詳細の組み立ては画面モックではなく `app/item_detail.py` が所有し、
`ItemDetailContext` の `MENU`、`SHOP`、`BATTLE` を受け取る。メニューと店では全詳細を、
戦闘では使用効果だけを返す。価格と入手元は汎用説明行へ混ぜず、`SHOP` の
`ItemDetailView` だけが店画面用メタデータとして公開する。

`use` は `spells.json` の安定キーとして解決する。呪文名の標準表現は
`Spell.localized_display_name()` が所有し、元素・神聖・暗黒の種別アイコンを名前の直前へ
付ける。呪文画面とアイテム詳細はこの同じ表現を使う。通常呪文を発動する `type2=BOOK` の
本は「つかうと アイコン＋呪文名」に続けて参照先Spellのdescriptionを表示する。それ以外の
消耗品は参照先が通常呪文でも呪文名を出さず、descriptionだけを表示する。装備品は
「つかうと アイコン＋呪文名」だけを表示し、descriptionは表示しない。
呪文descriptionの直前には空行を1行置く。画面側はdescriptionを表示幅で自動改行せず、
`spells.json` の配列で指定された行境界をそのまま使う。この方針は他の表示テキストにも
共通とし、必要な改行は正本データで明示する。
`break=1` でも `type1=ITEM` の消耗品には
破損・消費表記を出さない。装備品の `break=1` は「（こわれる）」を表示し、現行データで
該当するのは「てんいのゆびわ」だけである。

装備可否のうち、Member自身の適性、種族、性別、固有条件は `Member.can_equip()` が
純粋なルールとして判定する。武器と盾は対応する武器適性が0なら装備不可、`GENERAL`
防具は全員装備可能、`HEAVY` 防具は盾適性が1以上、`MAGICAL` 防具はいずれかの呪文適性が
1以上なら装備可能とする。`LV9` はその武器種の現在レベル9、`ONLY_RAGNA`、種族条件、
性別条件は安定キーで判定する。所持数の交換、装備枠の競合、NPCの固定装備といった
操作時の条件は `InventorySystem` が担当し、この純粋な可否判定へ混在させない。
左手へ `RIGHT` 武器を置けるのは「にとうりゅう」を所持するときだけとし、両手武器と
左手装備の競合時は、交換可能なMemberでは競合装備を所持品へ戻す。NPCは
初期装備だけを固定し、空き枠へ追加した装備は取り外しや交換を許可する。
両手武器との競合もこの固定判定に従い、オート装備も同じ交換規則を通す。

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

### フェード遷移

標準の画面切り替えフェードは、黒へのフェードアウト6フレームと黒からの
フェードイン6フレームで構成する。`rendering.fade.FadeThroughBlack` は
`IDLE`、`FADING_OUT`、`FADING_IN` の段階と経過フレームだけを保持し、
フェードアウト完了時に `COVERED`、フェードイン完了時に `FINISHED` を返す。
画面やOverlayの差し替えは `COVERED` を受け取ったSceneManagerが1回だけ適用し、
フェード自身へコールバックや遷移先を保持させない。フェード中は通常入力をSceneやOverlayへ
渡さない。開発用画面モックでは、そのComposition RootがSceneManagerと同じ調停を担当する。
イベント演出など標準よりゆっくり暗転させる場合は、生成時の `frame_count` に6より大きい
正の整数を渡す。時間を指定しないメニューや通常のScene遷移は6フレームを既定値として使い、
SceneやOverlayごとに独自のフェード速度計算を持たせない。

画面全体の色変化は `PaletteShifter.set_global_mix()` を `update()` から更新する。
基準パレットだけでなく `dimmed` など登録済みの派生パレットも不変の通常色から同じ割合で
黒へ混合し、局所的な `pyxel.pal()` と画面全体フェードを合成できるようにする。
フェードの進行やパレット更新を `draw()` で行わず、完了時は通常色へ厳密に復元する。

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

枠と左右インジケーターは、指定した外接矩形から描画時だけ1px下へずらす。
グラデーションは枠画像の内側へ重ねて隙間を埋めるため、開始座標を維持したまま
下方向へ1px延長する。
テキストとカーソルも従来のグリッド座標を維持し、透明Windowは枠を持たないため
オフセットしない。開閉中のクリップ領域は枠と同じ位置へずらす。

テキスト座標はウィンドウ枠の左上を原点とし、横・縦とも4pxの相対グリッドで指定する。`(0, 0)` は枠と重なる位置であり、枠から左右8pxずつ内側に入った従来の内容領域左上は `(2, 2)` となる。行の配列として保持せず、各 `WindowText` が文字列、x、y、色、任意のフォントを所有する。同じウィンドウ内で左右の列や異なる高さへ個別に配置できる。ウィンドウまたは個々のテキストへ `pyxel.Font` を渡し、フォント幅を位置決めの単位にしない。

通常のSceneとOverlayは、現在言語の標準フォントで初期化した `WindowFactory` からWindowを生成する。`WindowText.font=None` はWindowの標準フォントを継承し、個別のフォント指定がある場合だけそちらを優先する。解決順は「WindowText個別フォント → Window標準フォント」とし、言語状態やモジュールグローバルをWindowから参照しない。これにより通常のテキストごとに同じフォントを繰り返し指定せず、数値など例外的な表示だけを個別指定できる。

テキストは既定で本体より1px下へパレット0の同じ文字を先に描き、影を付ける。`shadow_color` で影色を変更でき、`None` を指定すると影を描かない。

画面をまたいで同じ意味に使う色は `ui.colors` の意味名から参照し、各画面で色番号を
再定義しない。現時点では使用不可を `DISABLED_COLOR = 3`、正の増減を
`POSITIVE_COLOR = 29`、負の増減を `NEGATIVE_COLOR = 45` とする。MPを持たない
Member（最大MPが0）のMP欄は、メニュー画面とステータス画面のどちらも
`DISABLED_COLOR` で表示する。

`transparent=True` を指定したWindowは、グラデーションと枠を描かずテキストだけを描画する。この場合もWindow左上をテキスト座標の原点とし、通常Windowと同じ4×4pxグリッドと領域を使う。背景上へ座標を揃えて文字だけを重ねる用途に使い、透明かどうかによってテキスト座標を変えない。

左右キーや前後ページ操作で表示対象を切り替えられるWindowは
`horizontal_navigation=True` とする。左右移動可能であることを示すインジケーターは、
イメージバンク0の `(96, 0)` から16×16pxの画像を左右8×16pxに分けて使う。
DA2と同じくWindowの高さ中央へ置き、左側は外接矩形の左端から1px外側、右側は
右端から1px外側へはみ出す位置に描画する。Windowは切り替え先を知らず、実際の対象変更は
所有元のSceneまたはOverlayが `InputState` を解釈して行う。左右インジケーターは
入力を受け付けるアクティブなWindowにだけ表示し、非アクティブなWindowでは表示しない。
所有元はWindow生成時または状態遷移時に `active` を現在の入力対象と一致させる。

表示行数を超える内容を上下スクロールできるWindowは `vertical_navigation=True` とする。
縦スクロールインジケーターはイメージバンク0の `(192, 16)` から、左から順に上・下の
通常表示、上・下の押下表示となる4×8pxの4パターンを使い、DA2と同じくWindow右枠の
右上と右下へ重ねて描画する。所有元は上下入力のフレームに
`set_vertical_navigation_pressed(-1)` または `(1)` を設定し、入力のないフレームは
`(0)` へ戻す。Windowはスクロール位置や表示内容を変更せず、表示条件と入力反映は
所有元のSceneまたはOverlayが管理する。

### Windowの開閉アニメーション

開閉状態は各 `Window` が `WindowState.CLOSED`、`OPENING`、`OPEN`、`CLOSING` のいずれかとして所有する。通常は従来と同じ `OPEN` で生成し、初期状態を閉じたい場合だけ `opened=False` を指定する。所有元のSceneまたはOverlayは `open()` / `close()` で開始を指示し、毎フレーム `Window.update()` を呼ぶ。

アニメーションはウィンドウ本来の座標、サイズ、テキスト、カーソル位置を変更せず、中央を基準にした描画クリップの高さだけを変える。確認ダイアログの従来速度を基準に開閉時間を8フレームへ統一し、1フレームあたりの表示高増減量はWindow自身の高さを8で割って切り上げた値とする。このため大きいWindowほど1フレームの移動量が大きく、どのサイズも同じ時間で開閉する。端数がある最終フレームだけ本来の高さまたは0へ揃える。開閉途中に逆の操作を受けた場合は、現在の表示高から反転する。

`update()` が表示高と状態を進め、`draw()` は現在の表示高でクリップして描くだけとする。通常Windowは開閉中も現在の上下端へ枠を描き、背景と枠だけの小さなWindowが中央から伸縮して見えるようにする。文字とカーソルは開き切ってから描画する。透明Windowには枠がないため、開閉中は文字とカーソルを現在の表示高でクリップする。閉じたWindowは何も描画せず、開き切ったWindowはクリップを使わず通常描画する。

開閉中はカーソル移動と浮遊タイマーを進めず、`OPEN` の間だけ `Window.update(input_state.navigation)` がカーソルへ入力を渡す。決定入力を開閉やゲーム進行のどちらとして扱うかは、WindowではなくSceneまたはOverlayが判断する。

### Windowのカーソル

選択肢を持つWindowには `Window.set_cursor()` で `CursorTarget` を登録する。ターゲットの `x`, `y` はテキストと同じWindow相対の4×4pxグリッドで指定し、`key` にはSceneまたはOverlayが確定時に受け取る任意の識別子を設定できる。キーを必要としないカーソル位置では `key=None` のまま登録してよい。

ターゲットの存在、選択可否、キーの有無は別の概念として扱う。空きマスにはターゲットを登録せず、表示はするがカーソルを合わせない項目は `selectable=False` とする。`key=None` を選択不可の印として使わない。全ターゲットが選択不可の場合は選択位置を持たず、カーソルを描画しない。

上下移動は現在位置と同じ `x`、左右移動は同じ `y` のターゲットを座標順に循環する。空きマスと `selectable=False` のターゲットはWindow側で自動的にスキップし、同じ行または列に別の選択可能なターゲットがなければ現在位置に留まる。1列だけを登録した標準的なメニューは、この規則により上下移動だけが有効になる。

カーソルはイメージバンク0の本体 `(48, 0)` から16×16px、影 `(64, 0)` から16×16px、
非アクティブ本体 `(80, 0)` から16×16pxを使い、透過色は1とする。ターゲットのテキスト
原点より8px左を基準位置とし、影は固定、本体だけを上へ0～2px動かす。浮遊パターンは
`(0, 0, 0, 1, 2, 2, 2, 1)` とする。選択元を残すマーカーなど影が不要な用途では、
`WindowCursor` の影描画を明示的に無効化する。

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
| `%FAVORED%` | `(152, 24)` | `%GAMEPAD_A%` | `(160, 16)` |
| `%GAMEPAD_B%` | `(168, 16)` | `%GAMEPAD_X%` | `(176, 16)` |
| `%GAMEPAD_Y%` | `(184, 16)` | `%KEY_Z%` | `(160, 24)` |
| `%KEY_X%` | `(168, 24)` | `%KEY_S%` | `(176, 24)` |
| `%KEY_TAB%` | `(184, 24)` |  |  |

入力アイコンもほかのアイコンと同じタグとして扱うため、操作案内専用の項目に限らず
任意の `WindowText.text` 内へ埋め込める。キーボードの決定・キャンセル・メニューは
`%KEY_Z%`・`%KEY_X%`・`%KEY_S%`、ゲームパッドでは
`%GAMEPAD_A%`・`%GAMEPAD_B%`・`%GAMEPAD_X%` を標準表示とする。
`%KEY_TAB%` と `%GAMEPAD_Y%` も明示的な案内が必要な文章から直接利用できる。

指定上は `(16, 16)` と `(144, 24)` の両方が `%DARK%` だったが、同じタグから2つの座標を一意に選べない。既存の呪文説明が使う闇属性アイコンを `%DARK%` `(16, 16)` とし、暗黒呪文系の後者は `%NETHER%` `(144, 24)` として区別する。元素、神聖、暗黒の呪文系アイコン名は、現実装に合わせて `%MYSTIC%`、`%SACRED%`、`%NETHER%` とする。

## 状態管理

状態は寿命と所有者で分ける。

### Settings

端末やプレイヤー設定。BGM、SE、言語、表示倍率、表示方式、キー配置などを持つ。
ゲーム進行とは別に保存する。現段階の`Settings`は言語、SE音量0〜4、画面倍率1〜5、
`DisplayMode.PIXEL` / `DisplayMode.SMOOTH`を保持し、DA2と同じ初期値3・3・ピクセル表示を使う。

言語は `Language` で表し、保存値と共有JSONの接尾辞には `ja`、`en`、`zhcn` を使う。初期値は `ja` とする。フォントファイル名に含まれる `zh_hans` はアセット名であり、保存値やデータキーには使用しない。

言語別の標準フォントは `FontResources` が所有する。フォントは必要になった言語から読み込み、同じ言語では生成済みの `pyxel.Font` を再利用する。

| 言語 | 標準フォント | ベースライン補正 |
|---|---|---:|
| `ja` | `k8x12S.bdf` | 0px |
| `en` | `k6x8_gothic.bdf` | +3px |
| `zhcn` | `fusion-pixel-12px-monospaced-zh_hans.bdf` | 0px |

フォント間のアセント差は `FontResources` のベースライン補正値として管理し、
`WindowText` の文字グリフの描画Y座標へ加算する。英語フォントは日本語・簡体字
中国語フォントより3px下げ、同じ行に置いた文字のベースラインを揃える。タグで
埋め込んだアイコンにはフォントのベースライン補正を適用せず、行本来のY座標を
基準に配置する。

タグ付きテキストのアイコンはフォントの文字幅によらず常に8px幅として扱う。
アイコン描画後の文字送りにも `ICON_SIZE` の8pxを使用する。

翻訳済み文字列をWindowへ配置するときは、`LocalizedWindowTextFactory` が選択言語の
標準フォントとベースライン補正を束ねて `WindowText` を生成する。このファクトリは
翻訳キーを解決せず、各SceneやOverlayが `TextCatalog`、Domain Modelから取得した
表示文字列を渡す。キーの選択、複数の表示値の連結、座標は画面側の責務とする。

固定幅の表示文字列は `ui.text_format` の `pad()`（右寄せ）と `spacing()`（左寄せ）で
整形する。両関数はPyxelや現在言語に依存せず、ASCII文字と余白を全角へ変換したうえで
指定文字数へ揃える。数値欄などの上限幅は画面側が指定し、Domain Modelの整数値には
余白や全角変換を持ち込まない。
アイテム名などの固有の多言語名は固定幅として扱わず、一覧でも画面側が
文字数や表示幅で切り詰めない。アイテム画面と装備候補一覧は、選択言語の
名称を末尾までそのまま表示する。

選択中言語のフォントがない場合は、別言語のフォントへ暗黙に置き換えずリソースエラーとする。簡体字を日本語フォントへ置き換えても表示を保証できず、配布物の欠損を隠すためである。

多言語フィールドの選択は `Localizer` が担当し、フォント読込とは分離する。フォールバック順は日本語が `ja → en`、英語が `en → ja`、簡体字中国語が `zhcn → en → ja` とする。任意の先頭フィールドを選ぶような非決定的なフォールバックは行わない。

日本語・英語モードの表示文字列はDA2と同様、原則として表示時にASCII文字と半角スペースを全角へ変換する。日本語モードでは、原文がUnicode全角なら日本語フォントの8px幅でそのまま表示し、原文がASCIIなら全角文字へ変換したうえで英語用6×8ドットフォントの6px幅で表示する。同じ文字列内に両方が含まれる場合も原文の範囲ごとにフォントを切り替える。JSONの原文は原則として意図する表示幅のまま保持し、`Localizer.value()` は変換前の値、`Localizer.text()` は表示用に正規化した値と原文由来のフォント範囲を返す。画面側で翻訳済み文字列へ英数字を連結する場合も、`LocalizedWindowTextFactory` が配置時に同じ正規化を適用する。これにより識別子、保存値、計算値へ全角変換が波及しない。`%FIRE%` のような表示制御タグ自体は変換・フォント判定の対象にしない。

英語原文へUnicodeの全角文字を明示的に登録した場合は、通常のASCII原文から表示時に
全角化された文字と区別する。`Localizer.text()` が返す `LocalizedText` はこの原文由来の
情報を保持し、`LocalizedWindowTextFactory` は前者を日本語フォントの8px幅、後者を
英語フォントの6px幅で表示する。この判定は日本語モードにも共通して適用する。フォント判定は表示用変換より前の原文に対して行い、
表示制御タグ内の文字は判定対象にしない。これはフォント欠損時の代替ではなく、
原文で明示された表示スタイルとして扱う。

キャラクター名など各レコード固有の表示値は `name_ja`、`name_en`、`name_zhcn` のような接尾辞付きフィールドに置く。種族名、性別名、画面項目名など複数レコードや画面から参照する表示語彙は `texts.json` に置き、安定した `text_key` で参照する。`TextCatalog` はキーからレコードを引き、実際の言語選択とフォールバックを `Localizer` に委譲する。Domain Modelとセーブデータには翻訳後の文字列ではなく、`FAIRY`、`FEMALE` などの安定キーを保持する。

`texts.json` の各言語フィールドは1行の文字列または複数行の文字列配列を許可する。
表示文の行数だけを理由に `text_key` を分割せず、意味上1つの文言は1キーにまとめる。
`TextCatalog.text()` は1行の値、`TextCatalog.lines()` は文字列・文字列配列の両方を
1行以上のタプルとして解決する。配列内の空文字は意図した空行として保持する。

DA2準拠の画面語彙を追加するときは、英語・簡体字中国語についてDA2の辞書に対応する
訳語がある場合だけ転記する。対応訳を確認できない文言を実装者が新たに翻訳せず、
`text_en`、`text_zhcn` は空文字のままにする。空文字の表示時フォールバックは、上記の
`Localizer` の規則に従う。

メニュー画面のコマンド、Gold、経験値、難易度、プレイ時間、閉じる案内も
`menu.*` の安定キーで `texts.json` に登録する。操作アイコンを含む文言は
`%CANCEL%` のような論理操作プレースホルダーを翻訳文へ置き、画面構築時に
`input_icon_tag()` が返す入力種別ごとの表示タグへ置換する。翻訳データへ
`%KEY_X%` や `%GAMEPAD_B%` を直接固定しない。

メニューのメンバー欄ではフィオラ、セリオン、アルヴァン、エリカ、ラグナの5人を
上から順に表示し、各行は名前、現在HP／最大HP、現在MP／最大MPだけで構成する。
HP・MPラベルも `menu.member.*` の安定キーを使う。顔は32×32pxで、前列をx=16px、
後列をx=28pxへ配置して隊列を表す。セリオンとエリカを後列とするのはモックfixture
だけの初期状態であり、キャラクターの不変なマスターデータには含めない。

`Member` は現在言語やフォントを保持しない。名前、種族、性別の表示値が必要な場合は、Composition RootまたはSceneから現在の `Localizer` と `TextCatalog` を明示的に渡して表示用の不変スナップショットを生成する。固定幅化、余白、座標などは画面側の責務とし、DA2の `name_disp` のようなレイアウト処理をDomain Modelへ含めない。

用語上、`characters.json` と `CharacterDefinition` は加入可能キャラクターの変更されない
マスターデータ、`Member` は加入後の可変なゲーム状態を指す。離脱中のキャラクターまで
「現在のメンバー」と誤認しないよう、この二つは `members` へ統一しない。

プレイヤーキャラクターの顔は共有画像 `faces/faces_pc.png` の32×32px領域を使用する。
各レコードの左上座標を `characters.json` の `face_x`、`face_y` に保持し、
`CharacterDefinition.face_position` へ読み込む。画面はキャラクター名による座標分岐や
固定座標を持たず、現在の `Member.face_position` を参照して描画する。

ステータス画面モックではフィオラ、セリオン、アルヴァン、エリカ、ラグナの順に
疑似パーティを構築する。左右方向または前後ページ入力で表示中のMemberを切り替え、
両端では循環する。切り替え時は名前だけでなく、顔、装備、能力値、熟練度を含むWindow全体を
現在のMemberから再構築する。ステータス画面は単体起動せず、メニューモックの
「ステータス」決定時に同じSettings、疑似パーティ、TextCatalog、フォント、顔画像を受け取って
表示する。ステータスWindowはアニメーションなしで即時表示する。
メニュー側は最後に表示したメンバー位置を保持し、次回のステータス表示を同じ位置から始める。
キャンセル時はPyxelを終了せずメニューへ戻る。

装備画面モックはDA2と同じく、左のメイン欄、右上の候補一覧、右下のアイテム詳細で
構成する。左上は顔の右へ名前、前衛／後衛、装備可能な武器9種と盾のアイコンを3行で
表示する。続けて右手、左手、体、頭、腕、オート装備を並べ、戦闘性能はステータス画面と
同じ「こうげき」「めいちゅう」「ぼうぎょ」「かいひりつ」「じゅつぼうぎょ」「たいせい」
の語彙と配置順を使う。「じゅつぼうぎょ」と「たいせい」の間に空行は置かず、左欄の
総行数をDA2と同じ18行に保つ。候補選択中は装備後の性能と耐性をプレビューするが、
確定まではMemberと所持数を変更しない。命中を変更前から変更後の順に表示するときは、
両方とも括弧内の熟練度補正を省略し、最終命中値だけを表示する。耐性は現在の
アイコン列を残し、その下に矢印と変化した種別だけを表示する。付与される耐性は
通常アイコン、失われる耐性は無効アイコン、変化しない種別は空欄とする。
右上の候補一覧では、武器名の前に対応する武器種アイコンを表示する。
所持品のうち選択部位に対応する装備品は装備可否にかかわらず列挙し、種族、適性、専用条件、
他の固定装備との競合などで装備できない品は `DISABLED_COLOR` で表示し、装備可能な品の
後ろへ安定ソートする。disabled項目にもカーソルを合わせてアイテム詳細を確認できるが、
性能・耐性のBefore/Afterは表示しない。決定した場合は装備を変更せず、メニュー共通の
エラー音と横振動を発生させる。左手では盾を常に列挙するが、片手武器は二刀流スキルを
持つMemberにだけ列挙する。
候補選択中も交換元の部位には非アクティブ色のカーソルを残し、右上の候補には
アクティブなカーソルを表示する。
装備画面の攻撃・命中・防御・回避・術防御は、変更前と変更後のどちらも
3桁右寄せで表示する。二刀流の攻撃値は装備画面とステータス画面の両方で
左右を3桁右寄せにし、`xxx－xxx` のように区切りの前後へ空白を置かない。
装備部位の見出しは、装備画面の日本語・英語でだけ `%RIGHT%` などのアイコンを使う。
装備画面の簡体字中国語と、ステータス画面の全3言語はテキストの部位名を表示する。

左右方向または前後ページ入力でMemberを循環切り替え、メニュー側は最後に表示した
Member位置を保持する。
右手または左手の両手占有、二刀流、装備適性、所持数交換は `InventorySystem` を経由して
確定する。`characters.json` の `type=NPC` は初期装備を固定する判定に使い、固定装備名は
`POSITIVE_COLOR` で表示する。部位見出しと区切りの「：」は通常色のままとする。
NPCの空き枠へ追加した装備は固定せず、取り外しや
交換を許可する。NPCの固定された初期装備を決定して交換しようとした場合は候補一覧へ
移らず、メニュー共通のエラー音と横振動を発生させる。

加入時スキルは `characters.json` の `skills`、加入時装備は `equip_right`、
`equip_left`、`equip_head`、`equip_body`、`equip_arm` を正本とする。
`CharacterDefinition` はこれらを安定キーとして保持し、Member生成時に `Skill` と `Item` へ
解決して現在状態へコピーする。進行中に変更されるのは `Member.skills` と
`Member.equipment` であり、加入時の定義を書き換えない。
`characters.json` の `type` は `MAIN`、`SUB`、`NPC` の安定値として
`CharacterDefinition.character_type` へ読み込み、表示上の分類ではなくNPC初期装備の固定などの
ゲームルール判定に使用する。

現在装備は数値添字の配列ではなく、`EquipmentSlot` をキーとする `EquipmentSet` が
管理する。右手、左手、頭、体、腕を明示し、両手武器は右手に保持したうえで左手を
使用不可とする。二刀流の武器は `Item.type1` が `RIGHT` であっても左手スロットへの
配置を許可する。物理スロットと
二刀流の可否を `Member.can_equip_at()`、所持数交換、両手競合、NPC初期装備の固定、オート装備を
`InventorySystem` が担当する。

装備品の `atk`、`hit`、`dfc`、`rst` は `Item` が非負整数として保持する。現在装備、
調整後能力値、武器・呪文熟練度から導出される攻撃・命中・防御・回避・術防御は、
保存値として重複保持せず `Member.battle_stats` が不変な `BattleStats` として計算する。
二刀流の攻撃・命中は右手と左手を別々に保持し、画面だけが左手攻撃の併記や命中の
平均表示を行う。小数点以下の切り捨てもDomain Model側で行い、画面側は全角数字への
変換だけを担当する。命中補正は装備中の武器レベル補正と他武器の到達補正を内部では
分けて保持し、画面の括弧内では両者の合計を表示する。「りょうてもち」の1.5倍は、
スキルの対象武器を右手に装備し、
左手が空いている場合に適用する。`TWO_HANDS` の槍・斧は装備枠を両手分使用するが、
このスキル補正とは区別する。

耐性種別は `ResistanceType` の安定キーで表し、`Item` は `tolerance` の漢字1文字を
対応する耐性の不変集合へ変換して保持する。`Member.resistances` は武器・盾・防具を含む
全現在装備の耐性の和集合を都度返し、装備変更前の値を重複保持しない。画面は9種を
定義順に配置し、集合に含まれる場合は通常アイコン、含まれない場合は同種の
`*_DISABLED` アイコンを選ぶ。`止` は `STUN` としてDomain Modelに保持するが、対応する
アイコンがないためステータス画面の9種には含めない。現在未定義の文字は別の耐性へ
誤変換せず無視する。

武器・呪文の適性は `characters.json` の `eq_sword` から `eq_shield`、および
`sp_mystic`、`sp_sacred`、`sp_nether` を正本とする。`CharacterDefinition` は0（使用不可）、
1（通常）、2（得意）の不変な適性を保持し、`Member` は各 `ProficiencyKind` の現在レベルと
熟練度を別に保持する。熟練度は0〜99で、100ポイントごとにレベルへ繰り上げる。
レベル上限は使用不可が0、通常が8、得意が9であり、上限到達後の加算は上限レベル・
熟練度99で止める。現段階のステータス画面用初期値は、適性0を0・00、適性1を8・99、
適性2を9・99とする。加入時の実際の成長値やセーブ・復元を導入するときは、この一時的な
初期化を保存済みのMember状態で置き換え、適性の正本とは混在させない。
ステータス画面モックでは適性0（使用不可）の武器・呪文のレベルと熟練度を `DISABLED_COLOR` で表示する。
ステータス画面モックでは適性2（得意）の武器・呪文に限り、種別アイコンの開始位置から8px左の同じ高さへ
得意マーカー（共通画像バンクの `(152, 24)` から8×8px）を表示する。

キャラクター正本の `base_str`、`base_agi`、`base_mag` は、変更されない
`CharacterDefinition.base_abilities` として保持する。画面やゲームルールは基礎値を
直接使わず、`Member.adjusted_abilities` を参照する。現段階では両者は同値だが、
装備補正やアイテムによる永続上昇は後者の計算へ追加し、正本由来の基礎値とは
混在させない。

現在HP、最大HP、現在MP、最大MPは可変な `Member` 状態とする。能力値やHP・MPを
Python上で保持するときは整数のままとし、画面へ渡す時点で共通の
`format_number()` により、選択言語にかかわらず全角数字へ変換する。

前列・後列は加入後に並び替えられるため、`CharacterDefinition` ではなく `Member` の
`FormationRow.FRONT` / `FormationRow.BACK` として保持する。画面はこの安定値を参照して
表示位置を決め、キャラクター名による前後列判定を持たない。メニューの「ならびかえ」は
入れ替え元と入れ替え先を順に選択し、異なるMemberなら表示順を交換、同じMemberなら
前列・後列を切り替える。最後の前列Memberを後列へ移す操作は受け付けず、常に1人以上を
前列に残す。メンバー選択カーソルは顔の左へ置き、入れ替え元の決定後は少し右へずらした
非アクティブ色のカーソルを残す。入れ替え元の決定後、現在のカーソルも入れ替え元にある
場合に限り、現在の前後列から移動できる方向を顔の横の点滅矢印で示す。矢印画像は
30フレームごとに切り替える。最後の前列Memberには後列方向の矢印を表示せず、実際に
後列へ移そうとした場合はDA2相当の効果音と短い横揺れでエラーを通知する。アラートの
残り時間は`update()`で進め、`draw()`から状態を変更しない。

装備品のフィールド回復力は `items.json` の符号付き整数 `healing` を `Item` が保持する。
正数は回復、負数はダメージ、0は増減なしを表す。
`Member.healing` は現在装備の値を合計し、`heal_and_poison_amount` はそこから毒の1HPを
差し引いた次回増減量を返す。死亡中はどちらも0とする。実際のHP変更は
`apply_heal_and_poison()` が0〜最大HPへ収めて行い、画面はこの状態変更を行わず、
正常時のHP欄へ正なら `（＋n）`、負なら `（－n）` を表示する。状態異常表示がある場合は
DA2同様に増減表示より状態名を優先する。

毒と麻痺は解除されるまで続く真偽値、眠りと混乱は戦闘中の残りターン数として
`Member` が保持する。状態表示の優先順位は死亡、麻痺、眠り、混乱、毒とする。
`Member.status()` は画面用途に応じて、正常時の「OK」、最大HP、空文字を選べるように
する。表示文言は `TextCatalog` から取得し、最大HPは `format_number()` で全角化する。

`Item` と `Skill` も現在言語やフォントを保持せず、共有JSONのレコードから生の検索キーと多言語名だけを初期化する。表示時に `Localizer` を明示的に渡し、英語の全角化を含む表示名を取得する。現在の共有JSONでは `name_en` がキャラクターや店からの検索キーを兼ねているため、全角化後の英語名やほかの言語の表示名を検索・保存に使用しない。将来、表示名と独立したキーをデータへ追加する場合も、Modelの呼び出し側は同じ生のキーを参照する。

設定画面で言語を変更した場合は `Settings.with_language()` で新しい設定スナップショットを作って保存し、新しい `Localizer` と標準フォントで表示中のWindowを再構築する。既存Windowがグローバルな言語変更を監視したり、フォントだけを後から差し替えたりしない。翻訳後の文字幅が言語ごとに異なるため、必要なレイアウト変更もWindow再構築時に反映する。

メニューの設定Overlayでは左右入力で言語、SE音量、画面倍率、表示方式を循環変更する。
設定項目、アクション、ガイドは4pxグリッド上で3単位、すなわち通常の12px行間へ揃え、
項目群の区切りだけ空行を1行置く。
メニューモックで初めて表示するメイン、設定、確認の各Windowは閉じた状態で生成し、既存の
`Window.open()`により中央から上下へ開く。設定画面で言語を切り替えた際に再構築する
メインWindowは開いた状態で生成し、アニメーションを繰り返さない。いずれかのWindowが開閉中は入力を受け付けず、
パーティの顔画像とカーソルも所属Windowが完全に開いてから表示する。
メインメニューでキャンセルした場合はプロセスを終了せず、`mock/bg_field` の256×240px画像を
仮フィールドとして画面全体へ描画する。メニューから仮フィールド、仮フィールドからメニューの
どちらも標準フェードを使い、完全暗転時に表示対象を切り替える。仮フィールドでは論理
`menu`入力でメニューを再表示し、メニューのWindowとカーソル位置は往復時に破棄しない。
仮フィールドからメニューを開く場合だけ、完全暗転時に既存Windowの表示高を0へ戻して
中央からの開放を再開する。Window開放は8フレーム、フェードインは6フレームであるため、
暗転中にWindowを2フレーム分進め、残り6フレームをフェードインと並行して両方を同時に
完了させる。Windowのテキスト、カーソル対象、現在の選択位置は再生成しない。
開発用の終了操作として、仮フィールドでのキャンセル入力は従来どおりプロセスを終了する。
SE音量変更時はチャンネル利得を更新して確認音を鳴らし、表示方式は`pyxel.screen_mode()`へ
即時反映する。画面倍率はDA2同様に次回リセット時へ反映し、倍率5をフルスクリーンとする。
「タイトルがめんへ もどる」と「ゲームを しゅうりょうする」は、翻訳済みの確認文と
「はい／いいえ」を持つ確認Overlayを経由する。タイトル復帰は端末設定を環境変数へ退避し、
Pyxelのウィンドウ状態を破棄して `pyxel.reset()` でメニューモックのプロセス自体を再起動する。
再起動時は退避した画面倍率を `pyxel.init(display_scale=...)` へ渡し、倍率5ではフルスクリーンを
有効化する。これによりSaveData、疑似パーティ、画面固有の一時状態を初期化しつつ端末設定を維持する。

### SaveData

セーブ対象となる進行状態。具体的には次のような情報を持つ。

- メンバー、装備、成長状態
- 所持品、所持金
- フラグ、訪問済み地点、取得済み宝箱
- 現在位置
- 戦闘回数などの世界進行値
- 魔力減衰や設備停止の判定に必要な値

SaveDataは「保存可能な現在のゲーム世界」を表す。ウィンドウ、描画用タイマー、選択中カーソル、Pyxelオブジェクトなどを入れない。

所持金 `gold`、パーティ全体で共有する経験値 `experience`、難易度
`difficulty`、プレイ時間 `play_time_frames` は、個々のMemberではなく
SaveDataが所有する。難易度の保存値には表示文言から独立した
`Difficulty.NORMAL` / `Difficulty.HARD` を使う。プレイ時間はフレーム数のまま保存し、
プレイ中の `Game.update()` から加算する。表示文字列への変換は複数画面で共有する
`ui.text_format.format_play_time()` が担当し、SaveDataや `draw()` は表示形式を持たない。

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
| 価格、所持、装備可否 | `Item` / `Member` / `InventorySystem` |
| 一時パレットシフトと変換色 | `rendering/palette.py` |
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
