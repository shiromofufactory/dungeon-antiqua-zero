# Dungeon Antiqua ZERO プログラム構造

## この文書の位置付け

この文書は、Dungeon Antiqua ZERO（以下、ZERO）の実装を開始・拡張するときのプログラム構造の基準を定める。

ゲーム内容、世界設定、シナリオ、主要なゲームルールは [`content/docs/da0.md`](../content/docs/da0.md)、機能ごとの詳細な振る舞いとUIは [`features/`](./features/README.md) を正本とする。本書はそれらを実装するための責務分割、依存関係、状態管理、画面遷移の方針を扱う。共有データの運用は [`content-workflow.md`](./content-workflow.md) に定める。

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

2026年9月時点では、実装用ディレクトリは `packages` から `app` に改名されている。スタッフ共有コンテンツは独立したprivateリポジトリへ履歴付きで分離し、`content` 自体をGit submoduleとして配置する。

```text
app/
├── main.py                   # Pyxel初期化、共通資産読込、Game生成、pyxel.run
├── game.py                   # タイトル・ロード画面・フィールド間の調停とPyxelコールバック
├── scenes/
│   ├── title.py              # 仮タイトルの決定入力と中央の文言描画
│   └── battle.py             # 本編と単独テストで共有する戦闘Scene
├── game_data.py              # マスターデータ索引と初期パーティ生成
├── battle_commands.py        # 戦闘コマンドの表示・選択可否と攻撃範囲のルール
├── battle_surprise.py        # 平均素早さ差による不意打ち抽選の純粋ルール
├── battle_physical.py        # DA2準拠の通常攻撃力、命中、物理ダメージ計算
├── auto_battle.py            # 固定回復の優先と短期予測による1行動の判断
├── auto_battle_model.py      # 判断用スナップショット、方針、観測履歴、評価結果
├── auto_battle_simulation.py # 本体と切り離した戦闘予測と味方の継続方針
├── attack_pose.py             # 通常攻撃コンポジット定義の検証と武器別ポーズ解決
├── monster.py                # モンスター種族、基本戦闘能力、戦闘ごとのHP、敵隊列ルール
├── input.py                  # Pyxel入力を論理InputStateへ変換
├── field.py                  # タイル単位のフィールド移動状態と通行判定
├── world_sites.py            # ワールド拠点のセル検索と訪問済み候補の抽出
├── state.py                  # LaunchMode、Settings、SaveData
├── localization.py           # 多言語フィールドの選択とフォールバック
├── item_detail.py            # メニュー・店・戦闘で共有するアイテム詳細表現
├── systems/
│   ├── debug.py              # デバッグ時だけ使うパーティ状態の再生成
│   ├── encounter.py          # 歩行加算、発生判定、全滅時の親ダンジョンと出口解決
│   ├── inventory.py          # 所持数、破棄、装備交換を含むアイテム操作
│   ├── battle_progression.py # 戦闘実績、報酬、熟練度、HP・MP成長の確定
│   ├── spell_progression.py  # メニュー呪文使用時の熟練度・最大MP成長
│   ├── auto_recovery.py      # オート回復の1手選択と反復実行（予定）
│   ├── save.py               # セーブv2とv1移行の変換、検証、スロット永続化
│   ├── settings.py           # 端末設定の読込と原子的な永続化
│   └── travel.py             # 拠点への入場、テレポート候補と到着地点参照
├── ui/
│   ├── battle_result.py      # 6人リザルト、待機、数値補間、増加SE
│   ├── input_icons.py        # 論理操作と入力種別から表示タグを選択
│   ├── start_menu.py         # タイトル後のロード・削除Overlay
│   ├── control_guide.py      # タイトル後の操作説明・入力リリース・入力種別変更
│   ├── save_menu.py          # プレイ中の手動セーブOverlay
│   ├── item_menu.py          # アイテムメニューOverlay
│   ├── equipment_menu.py     # 装備メニューOverlay
│   ├── status_menu.py        # ステータスメニューOverlay
│   ├── information_menu.py   # 情報サブメニューとモンスター図鑑Overlay
│   ├── spell_menu.py         # 呪文メニューOverlay
│   ├── spell_proficiency.py  # 呪文熟練度の小Window用表示・補間規則
│   ├── teleport_menu.py      # 本編TELEPORTとデバッグ移動で共有する行き先選択Overlay
│   ├── debug_menu.py         # 現在の開発用デバッグOverlay
│   ├── debug_text.py         # 翻訳対象外のデバッグ専用日本語テキスト
│   ├── party_status.py       # 子メニュー共通の下部パーティ表示
│   ├── shop.py               # ショップOverlay
│   ├── shop_party.py         # 購入時の6人顔・装備比較表示
│   ├── tagged_text.py        # タグ付きテキストとアイコン描画
│   ├── text_format.py        # 数値やプレイ時間の共通表示形式
│   ├── text_layout.py        # 右寄せなどの小さな配置計算
│   └── window.py             # 枠、文字、カーソル、標準フォント付き生成
├── resources/
│   ├── audio.py              # 外部BGMの読込、音量、再生状態
│   ├── data.py               # 生成済みJSON配列の読込と構造検証
│   ├── event_messages.py     # イベント専用メッセージの読込と多言語解決
│   ├── fonts.py              # 言語別フォントの読込とキャッシュ
│   ├── images.py             # 生成済み画像bundleの本番用loader
│   └── maps.py               # 生成済みマップとatlasの本番用loader
├── rendering/
│   ├── field.py              # マップ、カメラ、フィールドキャラクターの描画
│   └── monster_death.py      # モンスター撃破演出の段階・色・描画率
├── data/
│   ├── characters.json
│   ├── items.json
│   ├── monsters.json
│   ├── shops.json
│   ├── skills.json
│   ├── spells.json
│   └── texts.json            # 安定キーを持つ共通表示語彙
├── images/                    # content/imagesから生成する実行時画像データ
├── maps/                      # content/mapsから生成する実行時マップデータ
├── audio/                     # WAVから生成する実行時OGG
└── fonts/
    ├── fusion-pixel-12px-monospaced-zh_hans.bdf
    ├── k6x8_gothic.bdf
    ├── k8x12S.bdf
    └── umplus_j12r.bdf

content/                    # 共有コンテンツsubmodule
├── data/                   # JSONの正本
├── events/                 # イベント定義とイベント専用メッセージの正本
├── images/                 # PNG/GIF画像の正本
├── docs/da0.md             # 制作スタッフ向けの企画ベースドキュメント
├── portal/                 # スタッフポータルの生成処理・表示資産
└── scripts/                # JSON検証とGoogle Sheets同期

docs/
├── content-workflow.md
├── features/
│   ├── README.md
│   ├── field.md
│   ├── save-data.md
│   ├── start-load.md
│   ├── world-sites.md
│   └── shop.md
└── program-architecture.md

scripts/
├── sync-content.mjs        # submoduleからapp/dataを生成
├── build-images.py         # PNGをパレット番号へ変換してapp/imagesを生成
└── build-audio.py          # WAVをPyxel向けOGGへ変換してapp/audioを生成

tools/
├── README.md               # 開発用プログラムの配置基準と操作方法
├── audio_wav/              # 現段階のBGM変換元WAV
├── image_viewer.py         # 本番用画像をPyxelで確認するviewer
└── screen_mocks/
    ├── _runtime.py         # Pyxel初期化、共通資産、戦闘テスト入力
    ├── _runner.py          # 例外表示とCLI終了コード
    ├── _fixtures.py        # 疑似パーティなど戦闘テスト専用状態
    └── battle.py           # BattleSceneへfixtureを注入する単独起動口
```

`content/data` は共有JSONの正本である。`app/data` は `npm run sync` で作るGit管理対象外の実行時コピーであり、直接編集しない。ゲームコードは外部リポジトリやGoogle Sheetsを知らず、従来どおり `app/data` を読む。

`content/images` はゲームとスタッフポータルで共有するPNG/GIF画像の正本である。`app/images` は `npm run images:build` で作るGit管理対象外の実行時データであり、直接編集しない。画像のパレット変換はビルド時に行い、実行時は生成済みの1ピクセル1バイトのパレット番号を読み込む。

現段階のBGM変換元WAVは `tools/audio_wav` に置き、`npm run audio:build` で
`app/audio` の同名OGGと `output/mp3` の視聴用MP3へ変換する。変換状態はGit管理外の
`output/.audio-cache` に置き、変換元と設定が変わらない出力を再生成しない。
ゲームと再生確認ツールはWAVを直接読まず、生成済みOGGを
`app.resources.audio.BgmPlayer` から読む。スタッフ共有や納品用マスターの運用が必要になった
時点で `content/audio` への移管と同期手順を別途定める。

Google Sheetsとの双方向同期とポータル生成は共有コンテンツsubmoduleの責務とし、ゲーム本体の `scripts/` へ混在させない。`app/fonts` は引き続きゲーム本体の既存資産として扱う。

## 目標ディレクトリ構成

初期の目安を次に示す。未実装の機能に対応する空ファイルや空ディレクトリを先に作る必要はない。

```text
app/
├── main.py                  # Pyxel初期化、リソース読込、Game生成、px.run
├── game.py                  # Pyxelコールバックとアプリケーション全体の調停
├── input.py                 # 1フレーム分の入力をInputStateへ変換
├── world_sites.py           # ワールド拠点の不変カタログとセル索引
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
│   ├── menu.py              # 共通メインメニューOverlay
│   ├── item_menu.py         # アイテムメニューOverlay
│   ├── equipment_menu.py    # 装備メニューOverlay
│   ├── status_menu.py       # ステータスメニューOverlay
│   ├── information_menu.py  # 情報サブメニューとモンスター図鑑Overlay
│   ├── spell_menu.py        # 呪文メニューOverlay
│   ├── auto_recovery.py     # オート回復設定・実行Overlay（予定）
│   └── shop.py              # ショップOverlay
│
├── systems/
│   ├── events.py            # イベント検索・条件評価・コマンド実行
│   ├── progression.py       # 戦闘回数、魔力減衰、世界変化
│   ├── inventory.py         # 所持、使用、装備にまたがる操作
│   ├── travel.py            # 拠点への入場、テレポート候補と到着地点参照
│   ├── settings.py          # Settingsの端末別永続化
│   └── save.py              # SaveDataと保存形式の変換・入出力
│
├── resources/
│   ├── audio.py             # 外部BGMの読込、音量、再生状態
│   ├── events.py            # 生成済みイベントの読込、形式検証、ID索引
│   ├── event_messages.py    # 生成済みイベントメッセージの読込
│   └── images.py            # manifestと画像bundleの読込・検証
├── rendering/
│   ├── encounter.py         # PC中心の回転・拡大と暗転タイミング
│   ├── palette.py           # 一時パレットシフトと色変換
│   └── monster_death.py     # モンスター撃破演出の段階・描画パラメータ
│
├── data/                    # content/dataから生成するJSON
├── events/                  # content/eventsから生成する実行時イベント
├── audio/                   # 22.05kHz・モノラルの実行時OGG
├── images/                  # content/imagesから生成するmanifestと画像バイナリ
├── fonts/                   # フォント資産
├── battle_physical.py       # DA2準拠の通常攻撃力、命中、物理ダメージ計算
├── member.py
├── monster.py               # モンスター種族、基本戦闘能力、戦闘ごとのHP、敵隊列ルール
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

`InputBindings` は論理操作ごとに複数のPyxelボタンを保持する。初期設定は矢印キーとゲームパッドの方向、Z・EnterとゲームパッドAの決定、X・BackspaceとゲームパッドBのキャンセル、S・TabとゲームパッドX・Yのフィールドメニューとする。EscapeとゲームパッドStart・Guideは独立した `interruption` に割り当てる。ページやメンバーの前後切り替えには `previous_page` / `next_page` を使い、ゲームパッドの左・右ショルダーを割り当てる。キーボードのShiftキーには割り当てない。キー設定やAB反転を実装するときは、`Settings`から `InputBindings` を生成し、Reader内部やモジュールグローバルを書き換えない。

`InputState.navigation` はカーソル向けの単発およびリピート込み方向、`held_direction` はフィールド移動など押下中の毎フレーム処理に使う方向を表す。方向は上下左右のいずれか1つとし、新しい方向が押された場合は保持中の以前の方向より優先する。新しい方向が離された後も別の方向が保持されていれば、その方向へ切り替える。

方向リピートの状態、アナログスティックのデッドゾーン、直前フレームの押下状態は `PyxelInputReader` インスタンスが所有する。60fpsでDA2と同じ時間感覚にするため、既定の方向リピートは20フレーム後から4フレーム間隔とする。決定、キャンセル、メニュー、割り込み、前後ページは標準ではリピートさせず、初回押下だけを `triggered=True` とする。押したままかどうかは別の `held` で表し、Scene遷移時の入力リリース待ちなどに利用する。

`InputState.device` は、その時点で操作案内に使う入力種別を
`InputDevice.KEYBOARD` / `InputDevice.GAMEPAD` で表す。Readerの初期値はキーボードとし、
どちらか一方の入力だけを検出したフレームでその種別へ切り替え、入力がない間と両方を
同時に検出した間は直前の種別を維持する。アナログスティックはゲームパッド入力として
扱う。現段階ではDA2のWASDモードは設けない。

操作案内ではSceneやOverlayが論理操作の `InputAction` と
`InputState.device` を `ui.input_icons.input_icon_tag()` へ渡し、対応するテキスト内アイコン
タグを得る。これにより、画面ごとにキーボード／ゲームパッドの座標対応を持たない。
戦闘テストで入力種別を固定する場合も `InputDevice` を明示して同じ変換を使う。

開始時の操作説明は `ui/control_guide.py` が表示、入力リリース、表示中の入力種別変更と
キャンセル時の閉じるアニメーションを所有する。Gameはタイトル決定時の `InputState.device` と
`Settings.control_guide_device`、起動モードから表示要否を判定し、確認済みの入力種別を
`SettingsRepository` へ保存して次画面へ遷移する。設定値はPyxel非依存の安定文字列とし、
旧設定では未確認として扱う。表示条件と画面詳細は [タイトル・スタート・ロード](./features/start-load.md#開始時の操作説明) を参照する。

本番では `Game.update()` がフレームごとに一度だけ `poll()` し、SceneManagerを通して最上位Overlayまたは現在のSceneへ渡す。戦闘テストは独立したComposition RootとしてReaderを1つ生成し、同じ `InputState` とWindow部品を直接利用する。テスト固有のQ終了は、Qをキャンセルへ追加したBindingsをReaderへ渡して表現する。

```python
input_state = input_reader.poll()
command_window.update(input_state.navigation)

if input_state.confirm.triggered and command_window.is_open:
    command = command_cursor.selected_key
```

## ゲームデータリソースの責務

`app/resources/data.py` の `load_record_array()` は、`app/data` の生成済みJSONを
UTF-8で読み込み、ルートがオブジェクト配列であることまでを検証する。本編と戦闘テストは
同じ入口を使い、ファイル不在、JSON構文、ルート構造の処理を
複製しない。ファイル名は `app/data` 直下の名前だけを受け付け、任意のパス探索には
使用しない。

各レコードの意味的な検証は `Item.from_record()`、
`CharacterDefinition.from_record()` などのDomain Modelが担当する。安定キーによる索引、
重複判定、レコード間参照の解決は、必要なマスターデータ単位のloaderまたは
Composition Rootで行う。戦闘テスト用の加入済みパーティは本編のマスターデータではないため、
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

## マップリソースの責務

マップチップ画像、タイルセットメタデータ、制作用マップ、ゲーム用生成物を同じものとして
扱わない。タイルセット形式は
[`features/map-chip-metadata-tool.md`](./features/map-chip-metadata-tool.md)、マップ制作と生成形式は
[`features/map-editor.md`](./features/map-editor.md)を参照する。

- `content/images/mapchips`: 編集元となるマップチップ画像
- `content/maps/tilesets`: 地面、境界、表示候補、オブジェクト、通行設定の正本
- `content/maps/sources`: マップエディタが編集する論理的な地面とオブジェクト配置の正本
- `app/maps`: 保存時のコンパイルで生成する描画・通行特化データ

1つのタイルセットは複数マップから参照でき、複数タイルセットが同じ元画像を参照してもよい。
タイルセットは `world`、`town`、`dungeon` のprofileを1つだけ持ち、参照するマップのprofileと
一致させる。同じ元画像を異なるprofileで使う場合は、元画像を共有する別タイルセットを作る。
タイルセット先頭の地面を変更不能なベース地面とし、全マップの外周と寸法拡張領域へ使用する。
`world` のベース地面は `sea` とする。タイルセットの元画像は作成後に変更せず、マップが使用する
マップチップを変える場合は、同じprofileの別タイルセットへ参照を変更してマップ内容を初期化する。
削除時は参照元を確認し、参照中のマップまたはタイルセットを削除しない。
タイルセットの保存済みオブジェクト定義IDを変更する場合は、マップチップメタデータツールの
Applicationが同じタイルセットを参照する全制作用マップの定義参照を同一保存操作で更新する。
保存済み定義を削除する場合は、その定義を参照する配置済みオブジェクト実体を全制作用マップから
同一保存操作で削除する。途中の書き込み失敗時は更新済みマップを変更前へ戻す。
保存済み地面定義を削除する場合も、参照する全制作用マップの該当セルを先頭のベース地面へ
同一保存操作で置き換え、途中の書き込み失敗時は変更前へ戻す。
メタデータの検証エラーは問題一覧へ残したまま保存できるものとし、編集途中の不整合によって
修正操作が行き詰まらないようにする。

マップ保存時に地面レイヤー、8方向境界、重み付き表示候補、オブジェクト構成、通行可否を
解決し、オブジェクト越しの決定操作を許可するセルグリッドと、マップエディタで選択した
`bgm_id` もゲーム用JSONへ収録する。ゲーム実行時のMap Rendererは解決済みのタイルマップ、アニメーション差し替え情報、
オブジェクト描画面だけを扱い、境界判定、乱数抽選、透過合成を行わない。通行確認も生成済みの
セルグリッドを参照し、表示画像やオブジェクト定義から毎回再計算しない。
Rendererは背面の `object`、通常の `object_y_sorted` とキャラクターと前面の `object_foreground`
の共通Y整列、最前面の `object_overlay` の順に描画する。共通Y整列ではキャラクターの足元Yと
オブジェクト実体の下端Yを比較し、同じYでは「通常 → キャラクター → 前面」の順に描画する。
通行グリッドの生成順はレイヤー順のまま維持し、共通Y整列の描画順とは分離する。
タイルセット保存時は、そのタイルセットを参照するマップのゲーム用データも再生成し、
レイヤーなどの定義変更と実行時データを同期する。

制作用データの検証とコンパイルはPyxel非依存にし、対話ツール、マップエディタ、CIから同じ
処理を呼ぶ。ゲーム本体は `content/maps` や元PNGを直接参照せず、`app/resources/maps.py` の
`MapResources`を通して `app/maps` の形式、参照範囲、atlasのハッシュを検証する。

## 音声リソースの責務

外部BGMは編集用WAVとゲーム用OGGを同じものとして扱わない。

- `tools/audio_wav`: 現段階の変換元WAV
- `app/audio`: `npm run audio:build` で生成するゲーム用Ogg Vorbis
- `output/mp3`: 同じコマンドで生成する視聴用MP3
- `output/.audio-cache`: 形式別の変換状態（Git管理対象外）
- `app/se`: ゲームと制作ツールが直接読むSE用WAV
- `app/audio/catalog.json`: 安定したSE IDとWAVまたはPyxel Soundの対応
- `app/audio_catalog.py`: Pyxel非依存のSE定義解析・WAV参照検証
- `app/resources/audio.py`: BGM IDの解決、PCM読込、音量、再生状態、共通SE再生
- Pyxelチャンネル2: BGM専用チャンネル

`SoundEffectPlayer` はゲームと制作ツールで共通の再生処理を所有する。登録済みWAVは
初期化時に独立したSoundへ読み込み、キャッシュして再利用する。ゲーム側は `play_se()`
へ安定IDを渡し、エディタは未保存の定義も同じPlayerへ渡す。定義の解析は
イベントと呪文エフェクトの生成処理からも共有し、Pyxelを初期化せず検証できる。
ゲームは設定のSE音量を同Playerへ通知し、Playerが音源種別に応じた利得を適用する。
ゲーム音量を指定しない制作ツールでは、試聴用チャンネルの利得を維持する。
SE定義・共通チャンネル・割り込み・制作操作は
[`features/sound-effects.md`](./features/sound-effects.md) を正本とする。

`scripts/build-audio.py` は変換元の相対パスを維持し、22,050Hz・モノラル・Vorbis quality 4
へ変換する。拡張子を除いた `app/audio` からの相対パスを安定したBGM IDとして使い、
`da3-welcome.ogg` は `da3-welcome`、`da3-field.ogg` は `da3-field`、
`dungeon/floor1.ogg` は `dungeon/floor1` とする。

`BgmPlayer` はPyxel初期化と `assets.pyxres` 読込の後にComposition Rootが生成し、
SceneManagerへ明示的に渡す。BGMには `pyxel.Sound()` の独立インスタンスを使い、
`assets.pyxres` 内の効果音Sound番号を上書きしない。同じBGM IDが継続するScene遷移では
再読込・再スタートせず、異なるIDへの切り替えと停止だけをチャンネル2へ適用する。
`Sound.pcm()` は同期デコードのため `draw()` から呼ばず、起動時またはScene遷移時に呼ぶ。
フィールド開始時と、異なるBGMへのマップ遷移の完全暗転時には、遷移先の生成済みマップが持つ
`bgm_id` を `BgmPlayer` へ渡す。マップエディタと非対話検証は、選択したIDに対応する `app/audio` の
OGGが存在することを保存・生成前に確認する。
フィールド開始と異なるBGMへのマップ遷移では、画面フェードの `visible_rate` をBGMの設定音量へ
乗算してフェードアウトで0まで下げる。完全暗転時にBGMを選んで設定音量へ即時復帰し、音量の
フェードインは行わない。同じBGMへのマップ遷移ではゲインも曲位置も変更せず再生を続ける。
非ループのジングルから
次のループBGMへ戻す場合は、次曲を `BgmPlayer` 内で予約する。ジングル開始時に次曲が再生中なら
`pyxel.play_pos()` の秒位置を退避し、ジングル終了後に `pyxel.play(..., sec=退避位置)` で再開する。
Scene切り替え時も同じ次曲が予約済みならジングルを中断しない。別のジングルを明示的に再生した場合は
現在のジングルへ割り込み、新しい予約へ置き換える。
戦闘への遷移開始時はGameが `BgmPlayer.playback_position_sec` を取得し、生成するBattleSceneへ
復帰用BGM IDと開始秒位置を渡す。BattleSceneはその戦闘の復帰位置を所有し、勝利ジングルの
`play_once_then(..., next_start_sec=位置)` と逃走後の `transition_to(..., start_sec=位置)` に使う。
同じ次曲へ予約済みのジングルを切り替える場合は、BgmPlayerが予約位置も引き継ぐ。
`transition_to()` は次曲が再開済みなら位置を巻き戻さず継続する。具体的な復帰規則は
[`features/encounters.md`](./features/encounters.md) を正本とする。秒位置はセーブへ保存しない。
イベントのBGM停止は `BgmPlayer.fade_out_and_stop()` が音量補間と停止までのフレーム進行を
所有する。Gameは停止要求を渡し、`is_fading_out` が偽になるまでEventRunnerを待機させる。
停止要求は予約された次曲を解除し、新しい再生要求は進行中の停止フェードを解除する。
具体的な時間と待機規則は [`features/events.md`](./features/events.md) を正本とする。

現段階ではデスクトップ版のPyxel音声経路だけを対象とする。DA2のAndroid用HTML Audio、
画面非表示からのモバイル復帰、曲長JSONは導入しない。現在位置はPyxelから曲内の秒数として取得
できるため、直前まで流れていたBGMの再開には曲長データを必要としない。イントロ付きループや
異なる再生基盤を導入し、再生位置の正規化が必要になった時点で曲長カタログを追加する。

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
Pyxelの色番号は0〜255に限られるため、基準パレットと全派生パレットの合計を256色以内にする。
呪文フラッシュや死亡演出のように同時使用しない一時派生色は、演出完了時に`remove_variant()`で
解放して後続演出へ領域を再利用する。上限超過は不正な色番号を`pyxel.pal()`へ渡す前に拒否する。
戦闘Sceneを破棄するときは、演出途中であってもSceneが確保した派生色を解放する。
画面全体へ時間変化する色調を適用する場合は、外側を `shifted()` で囲まない。
内側の局所効果が `pyxel.pal()` を解除すると外側の割り当ても失われるため、基準色と
全派生色へ同じ変換を合成する `set_global_mix()` を使用する。

## 開発用中間プログラム

画像viewer、マップ制作、戦闘テストなど、人が対話操作する開発用プログラムはリポジトリ直下の
`tools/` に置く。自動生成や非対話の検証を行う `scripts/`、配布対象の `app/` と責務を分ける。

開発用プログラムのために画像やJSONを複製しない。表示確認ツールは `app/data`、`app/images`、
`app/assets.pyxres`、`app/assets.pyxpal` を本番と同じ入口から読む。制作ツールは正本である
`content/maps` と `content/images/mapchips` を直接扱ってよいが、`app/maps` を編集しない。
manifestや保存形式など、本番と共有すべき解釈処理は `app/resources` や該当Systemが所有し、
`tools/` は画面、入力、選択中の対象といったツール固有状態だけを所有する。これによりviewerだけが
成功し、ゲーム本体では読めないという形式差異を防ぐ。

ツール同士を巨大な共通Appへ統合しない。単独で確認するツールは `python3 -m tools.<module>` で独立起動できる小さなComposition Rootとする。複数ツールで本当に同じ起動処理が生じた場合だけ `tools/` 内の小さな共通モジュールへ抽出する。戦闘テストでは、Pyxelと共通資産の初期化を `_runtime.py`、想定内例外と終了コードの変換を `_runner.py`、疑似パーティを `_fixtures.py` が担当する。Settingsと画像は起点が生成し、BattleSceneへ必要な依存だけを明示的に渡す。`tools/` は `pyxel package app ...` の配布対象に含めない。

マップチップメタデータ設定ツール、マップエディタ、イベントエディタは `tools/editor` を共通の
Composition Rootとし、単一のローカルHTTPサーバーと認証セッションから `/tileset/`、`/map/`、
`/event/` へ振り分ける。統合するのは起動、静的ファイル配信、ナビゲーションだけとし、各画面の
Application、編集中状態、保存、検証処理はそれぞれのモジュールに保持する。

ミッションはイベントエディタの派生タブとして同じApplicationから保存する。
正本の検証・生成は `scripts/event_pipeline/missions.py`、実行時の不変定義は
`resources/events.py` の `EventCatalog` が所有する。イベントとミッションの条件評価は
`systems/conditions.py` へ集約し、SaveData、PartySystem、InventorySystemだけを渡す。
情報メニューの本文とスクロール状態は `ui/information_menu.py` が所有し、Gameは画面を開く時に
表示対象のメッセージIDを渡す。制作形式は [`features/events.md`](./features/events.md)、
表示操作は [`features/information-menu.md`](./features/information-menu.md) を参照する。

マップチップメタデータ設定ツールとマップエディタは対話UIだけを `tools/` に置き、JSON Schema、
検証、地面合成、ゲーム用データ生成は `scripts/map_pipeline/` 相当のPyxel非依存処理へ置く。
両ツールで境界ルールや保存形式を別々に実装しない。

配置オブジェクトの条件付きセルの通行効果はマップ生成処理が展開し、actorの表示条件は
不変な `MapActor` に保持する。両者のフラグ条件は `resources/maps.py` の
`MapVisibilityCondition` に統一し、不変な `CompiledMap` が現在のイベントフラグを
明示的に受け取って評価する。FieldActorsは全actorの一時状態を保持し、表示中のactorだけを
描画・衝突・トリガー座標・自律更新へ渡す。画像リソースは非表示actorの分も初期化時に読み込む。
GameはSaveDataのフラグ集合をFieldMovementとFieldActorsへ注入し、描画とトリガー判定にも
同じ集合を渡す。マップリソースへSaveDataやGameの逆参照、可視状態の複製は持たせない。
具体的な制作操作と適用範囲は [`features/map-editor.md`](./features/map-editor.md) を参照する。

戦闘の単独確認起点は `tools/screen_mocks/battle.py` に置く。仕様が確定して本編でも使う入力、状態、描画は `app/` のScene、Field、Renderer、Overlayまたは表示部品へ置き、テスト起点から本番部品へリソースと疑似状態を注入して確認する。戦闘は `app/scenes/battle.py` の `BattleScene` が処理を所有し、`tools/screen_mocks/battle.py` はPyxel初期化、疑似パーティ・敵編成の構築、入力ポーリング、単独終了だけを担当する。本編の `Game` は現在の `InputState` とセッション状態を渡して同じSceneを利用し、ゲーム本体から `tools/` を参照しない。敵行動数と武器・呪文使用実績の集約、共有経験値・Gold・熟練度・最大HP/MPの成長対象確定はPyxel非依存の `systems/battle_progression.py` が所有する。逃走とフェードの確定では同Systemが経験値、Gold、お宝、最大HPを除外し、熟練度と最大MPだけを反映する。最大HP/MPの理論値と1回の成長上限は、戦闘とメニュー呪文使用で同じ規則を使うため `Member` が所有する。`BattleScene` はその記録契機、勝利・逃走演出、戦闘画面からリザルトへのフェードを調停する。6人リザルトのWindow、色、12フレームの待機、30フレーム補間、表示数値が変化したフレームのSE再生は `ui/battle_result.py` が所有する。リザルトと本編に接続済みのメニュー画面には単独モックを置かず、ゲーム内動線と `app/ui/` を直接対象にした回帰テストで確認する。

武器使用実績は同Systemがキャラクター・武器種ごとに対象敵LV、撃破したモンスターの識別キー集合、
会心の有無を保持し、戦闘終了時に熟練度の加算値を計算する。`BattleScene` は物理攻撃と装備武器使用の
結果から実績だけを渡す。計算式と記録対象の詳細は [`features/battle.md`](./features/battle.md#勝利報酬と成長記録)
を参照する。

遭遇済みモンスター、開示済み属性、お宝取得済みの更新と照会は、Pyxel非依存の
`systems/monster_records.py` が `SaveData.monster_records` に対して行う。BattleSceneは遭遇、
行動確定、ターゲット表示の契機だけを調停し、マスターデータの弱点・耐性そのものをSaveDataへ
複製しない。ターゲット表示はSystemが返す開示状態とBattleMonsterの不変な弱点・耐性を照合する。
属性武器による通常攻撃も、`AttackAttribute` を対応する `ResistanceType` へ変換して開示対象とする。
通常攻撃系のターゲット選択中は、右手武器の変換後属性が開示済みの場合だけ既存の
`WEAK` / `RESIST` ターゲット表示へ反映する。
物理攻撃計算は属性特効の命中値加算・確定会心を `battle_physical.py` で解決し、BattleSceneは
武器属性と対象の弱点・耐性の照合、追加効果への特効情報の伝達、`WEAK` 表示を担当する。

呪文エフェクト設定ツールはブラウザエディタへ統合せず、60fps、PyxelのSound、本番パレットを
そのまま確認できる独立したPyxelプログラムとして`tools/spell_effect_editor/`へ置く。
制作設定の正本はGoogle Sheets同期外の`content/effects/spells.json`、ゲーム用生成物は
`app/effects/spells.json`とし、呪文マスターの`content/data/spells.json`へ描画設定を混在させない。
未登録Soundへ安定した`se_id`を付ける操作は同ツールに持たせ、ゲーム本体も参照する
`app/audio/catalog.json`へ追加する。SE用WAVの登録と試聴も共通Playerを使用する。
Sound自体の編集責務はPyxel Editorに残す。
形式検証とゲーム用索引の生成はPyxel非依存にし、ツール保存と非対話ビルドから同じ処理を使う。
経過フレームと画像パターンの計算は`app/spell_effect.py`、Pyxel画像と対象パレットの描画は
`app/rendering/spell_effect.py`相当が所有し、将来のBattleSceneと設定ツールで共有する。
`SpellEffectPlayer`は対象が味方か敵かを明示的に受け取り、定義に保存された対象側のOFFSETを選ぶ。
画面構成、保存形式、通常エフェクトと特殊エフェクトの境界は
[`features/spell-effect-editor.md`](./features/spell-effect-editor.md)を参照する。

通常攻撃コンポジットも同様に、制作設定の正本を `content/battle/attack_poses.json`、ゲーム用
生成物を `app/effects/attack_poses.json` とする。形式検証と `weapon_img` ごとの枝番解決は
`app/attack_pose.py` に置き、戦闘モックは生成済みデータとアイテムモデルだけを参照する。

呪文マスターの文字列enum、習得レベル、表示名・説明の解釈は `app/spell.py` が所有する。
レベル1から9の呪文はMemberの対応する元素・神聖・暗黒熟練度以下を習得済みとし、
レベル0は通常成長から除外してイベント習得キーがある場合だけ習得済みとする。呪文メニューOverlayは
この判定結果を描画するだけとし、イベント習得状態や呪文効果を画面固有状態へ埋め込まない。
メニューから発動したFADEとTELEPORT以外の呪文の熟練度は、Pyxel非依存の `systems/spell_progression.py` が
`floor(√実消費MP) + 使用種別の適性 + 他の呪文種別の最高LV - 使用種別のLV` を0以上へ丸めて
確定し、レベル上昇時は `Member` の共通成長規則で最大MPを1段分だけ理論値へ近づける。`ui/spell_proficiency.py` は
呪文メニューとオート回復で使う小Windowの文言・補間規則を共有し、各Overlayが配置と表示期間を所有する。
補間時間は [フィールド](./features/field.md) を参照する。呪文自体のSEとの競合を避けるため、
このメニュー経路の数字変化SEは再生しない。
キュアーが対象とする状態の判定と解除は `Member.has_curable_ailment` / `cure_ailments()` が所有し、
呪文メニューOverlayは対象選択、MP消費、熟練度成長の契機だけを調停する。
オート回復は [`features/auto-recovery.md`](./features/auto-recovery.md) を正本とする。
`systems/auto_recovery.py` が回復の1手選択と反復実行を所有し、`ui/auto_recovery.py` は
設定、実行入力、結果表示を所有する。設定値はセーブごとの状態へ置く。
顔と状態異常アイコンの描画規則は `ui/party_status.py` と共有し、同部品の5人固定配置を
オート回復画面へそのまま使わず、6人・2段表示を指定できるようにする。
戦闘中の呪文効果計算はPyxel非依存の `app/battle_magic.py` が所有し、`BattleScene` は対象の確定、
結果をMemberまたはMonsterへ反映するタイミング、エフェクトおよび数字・属性相性ポップアップの
進行だけを扱う。キャラクターごとの術補正値は同モジュールの独立関数とし、攻撃呪文と今後の
状態異常呪文で共有する。毒の手番開始ダメージ量も同モジュールで求め、毒状態そのものと睡眠を
解除しない毒ダメージ反映は `Member` または `MonsterBattleState` が所有する。
速度補正から実効素早さを求める共通ルールはPyxel非依存の `app/battle_speed.py` が所有する。
味方の速度補正は `Member`、敵の速度補正は `MonsterBattleState` が戦闘中だけ保持し、
`BattleScene` は現在の実効素早さをタイムライン再挿入と物理攻撃へ渡す。
待機中の個体に対するゲージ補正と安定した並べ替えはPyxel非依存の `app/battle_timeline.py` が
所有する。`BattleScene` はスロウの適用契機に対象個体のゲージを補正し、表示順を同期する。
オートバトル予測も同じ素早さ・ゲージ補正処理を利用する。効果量と相殺の規則は
[`features/battle.md`](./features/battle.md) を参照する。
通常ランダムエンカウントの不意打ち抽選値は、Pyxel非依存の `app/battle_surprise.py` が
味方・敵それぞれの素早さ列から浮動小数を使わず算出する。遭遇元による抽選可否、乱数の取得、
「けいかい」保有者の選択、反転隊列、未到達メンバー、および隊列復帰アニメーションは
1戦闘限りの状態として `BattleScene` が所有し、`Member.formation_row` へ保存しない。

アイテムメニューOverlayはカテゴリ選択、一覧選択、対象選択、破棄確認の一時状態を所有する。
重要アイテムも通常のアイテムとして `InventorySystem` で所持数と取得記録を管理し、
Overlayに専用所持一覧を持たせない。カテゴリと情報欄の表示・操作は
[`features/field.md`](./features/field.md) を正本とする。メニュー回帰テストの疑似所持品は
`items.json` の全レコードを1個ずつとし、現在のゲームの初期所持品は空とする。
情報欄は選択中の名前、種別、装備条件、0以外の攻撃・命中・防御・回避・術防御、
能力補正、フィールド回復、射程を表示する。破棄して所持数が減っても記録済み状態は維持する。
装備品の取得記録も `InventorySystem.record_equipment()` が所有し、Gameの初期パーティ生成直後と
EventRunnerの加入成功時に登録する。装備状態と未装備の所持数は変更しない。
一覧の商品個数は1桁時の表示位置を右端の基準とし、2桁でも同じ右端へ揃える。
能力補正は1能力につき1行とし、正負の符号を表示する。フィールド回復は数値を出さず、
DA2と同じ「HP じどうかいふく」または「HP じょじょにげんしょう」とする。破棄は
DA2と同じ確認文とはい／いいえの選択を表示し、はいの場合だけ `InventorySystem` が
所持数を1減らす。破棄確認中も、直前の商品位置へ非アクティブカーソルを残す。
`price=0` は破棄不可を表し、確認画面を開かずDA2と同じエラー演出を
返す。下部の顔とHP表示は呪文画面と
`app/ui/party_status.py` の同じ部品を使う。一覧は選択行が上下端を越えると表示開始位置を1件ずつ
追従させ、左右および前後ページ入力では表示行数ぶん移動する。一覧Windowは従来より
8px右へ広げ、情報欄のテキストは追加インデントを置かず枠内側から開始することで、
情報欄テキストの画面上の絶対位置は維持する。一覧が表示行数を超える場合は、右枠の
上端と下端へ共通の縦スクロールインジケーターを表示する。
装備品へカーソルを合わせている間は、装備できないMemberの顔だけを共通の
`PaletteShifter` で暗く描画する。カテゴリ選択中と道具選択中は顔色を変更しない。
毒・麻痺アイコンの状態判定と顔右上脇への描画も `PartyStatusPanel` が所有し、アイテム画面と
呪文画面が個別に座標や描画順を持たないようにする。
フィールドでの回復アイテム使用、対象選択、消費規則は
[`features/field.md`](./features/field.md) を正本とする。

所持品はアイテムキーから個数への辞書として `InventorySystem` が保持する。同一品の上限は
`type1=ITEM` が99、装備品が9で、所持品全体の合計上限は設けない。装備品の上限判定では
所持品と全Memberの装備中個数を合算するが、合計値を重複して保存せず装備状態から都度算出する。
購入、取得、装備着脱、セーブ復元後の検証は同じ上限規則を通す。

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

アイテム詳細の組み立ては画面Overlayではなく `app/item_detail.py` が所有し、
`ItemDetailContext` の `MENU`、`SHOP`、`BATTLE` を受け取る。メニューと店では全詳細を、
戦闘では使用効果だけを返す。価格と入手元は汎用説明行へ混ぜず、`SHOP` の
`ItemDetailView` だけが店画面用メタデータとして公開する。
表示コンテキストによる見出し・区切りの省略も共通の詳細生成が所有し、戦闘Sceneで完成した行を
文字列判定して削らない。戦闘時の説明範囲は [戦闘仕様](./features/battle.md#アイテム使用) を参照する。

ショップの詳細なゲームルール、操作、レイアウト、メッセージ状態は
[`features/shop.md`](./features/shop.md) を正本とする。

ショップマスターの解釈は `app/shop.py` の `Shop` が所有し、`shops.json` のデータ順と
各店の商品順を維持する。価格、最大取引数、Goldと所持数の同時更新、全店舗の固定商品集合に
基づくレア売却判定はPyxel非依存の `systems/shop.py` が担当する。

ショップOverlayは `app/ui/shop.py` が画面内のPhase、モード、カーソル、一時的な取引個数を
所有する。購入時の顔と装備比較は `app/ui/shop_party.py` に分けるが、Domain ModelへPyxel描画を
逆参照させない。現在のゲームはデバッグメニューが全ショップの選択を所有し、選択結果だけを
コールバックで `Game` へ返す。`Game` は選択されたShop、パーティ、共有状態を本番の
ショップOverlayへ渡し、終了時はデバッグメニューのショップ一覧へ戻す。表示文言は
`TextCatalog` の安定キーで参照する。

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
左手へ `RIGHT` 武器を置けるのは「にとうりゅう」を習得しているか、現在装備に
`special=DUAL_WIELD` があるときだけとし、両手武器と
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
すでに黒い画面から表示を開始する演出では `start_fade_in()` を使い、画面固有のフェード計算を
追加しない。
画面やOverlayの差し替えは `COVERED` を受け取ったSceneManagerが1回だけ適用し、
フェード自身へコールバックや遷移先を保持させない。フェード中は通常入力をSceneやOverlayへ
渡さない。単独戦闘テストでは、そのComposition RootがSceneManagerと同じ調停を担当する。
イベント演出など標準よりゆっくり暗転させる場合は、生成時の `frame_count` に6より大きい
正の整数を渡す。時間を指定しないメニューや通常のScene遷移は6フレームを既定値として使い、
SceneやOverlayごとに独自のフェード速度計算を持たせない。

画面全体の色変化は `PaletteShifter.set_global_mix()` を `update()` から更新する。
基準パレットだけでなく `dimmed` など登録済みの派生パレットも不変の通常色から同じ割合で
黒へ混合し、局所的な `pyxel.pal()` と画面全体フェードを合成できるようにする。
フェードの進行やパレット更新を `draw()` で行わず、完了時は通常色へ厳密に復元する。
イベントの全画面フラッシュは `rendering.screen_flash.ScreenFlash` がフレーム進行を持ち、
`Game` が `PaletteShifter.set_global_mix()` へ指定色を適用する。イベントRunnerは効果の完了まで
待機し、色名の検証はイベント生成処理と本番loaderで行う。
イベントの明るさ変更と横揺れは `rendering.screen_effects` の `ScreenBrightness` と
`ScreenShake` が補間値とフレーム進行を所有し、GameがEventEffectの完了をRunnerへ返す。
明るさは `PaletteShifter.set_brightness()` で通常色からの変換へ合成し、
`set_global_mix()` による一時的なフェードやフラッシュが終了しても維持する。
横揺れはGameの描画カメラへ加算してSceneとOverlayへ適用し、Domain Modelの位置を変更しない。
具体的な値、待機、初期化規則は [`features/events.md`](./features/events.md) を正本とする。

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
- Overlayを開いても直下のWindowが表示されたままなら、直前の選択カーソルを消さず、入力を受けない非アクティブ表示で残す。元のWindowを閉じるか置き換える場合だけ、そのカーソルも消す。
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

中央寄せなどで4px未満の端数が必要な場合は `WindowText.pixel_offset_x` を使い、
グリッド座標から水平位置だけをピクセル単位で補正する。既定値は0で既存の配置は変えない。
文言の実描画幅を測って配置を決める責務は各Overlayに残す。

`Window.draw(text_offset_y=...)` は本文だけをピクセル単位で上下へずらし、内容領域で切り抜く。
本文や配置は書き換えず、枠やカーソルは移動しない。メッセージのページ送りではOverlayが
スクロール位置と完了後の文字表示を `update()` で管理し、Windowは指定位置を描画するだけとする。
ページ送りの詳細は [`features/events.md`](./features/events.md) を参照する。

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
window.add_text("ＩＴＥＭ", x=2, y=2)
window.add_text("１０", x=42, y=2, shadow_color=0)
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
`%GAMEPAD_A%`・`%GAMEPAD_B%`・`%GAMEPAD_X%` を標準表示とする。メニュー入力は
`%GAMEPAD_Y%` も受け付ける。
`%KEY_TAB%` と `%GAMEPAD_Y%` も明示的な案内が必要な文章から直接利用できる。

指定上は `(16, 16)` と `(144, 24)` の両方が `%DARK%` だったが、同じタグから2つの座標を一意に選べない。既存の呪文説明が使う闇属性アイコンを `%DARK%` `(16, 16)` とし、暗黒呪文系の後者は `%NETHER%` `(144, 24)` として区別する。元素、神聖、暗黒の呪文系アイコン名は、現実装に合わせて `%MYSTIC%`、`%SACRED%`、`%NETHER%` とする。

## 状態管理

状態は寿命と所有者で分ける。

### 起動モード

`state.LaunchMode` はプロセス単位の起動条件を表す。`main.py` が起動オプションを解析し、
`Game` へ注入する。Gameは起動中のモードを保持し、再初期化時も同じ値を引き継ぐ。
Settings／SaveDataへ含めず、ロード対象のデータからモードを変更しない。

試遊版の日本語固定はGameが実行用Settingsへ適用する。端末から復元した言語の選択を別に保持し、
設定保存と再初期化用の受け渡しではその選択を戻す。SettingsRepositoryと設定JSONの形式へ
起動モードの制約を持ち込まず、ほかのモードの言語選択を保つ。
表示と操作の制約は [起動モード仕様](./features/launch-modes.md#言語) を参照する。

初期パーティ生成は `game_data.create_party()` へフィオラの開始LVを明示して依頼する。
GameはDomain Modelの必要経験値計算を使って初期共有経験値を設定し、各Memberの
`set_joining_experience_offset()` で開始LVをその共有経験値へ対応付ける。
初期HP・MPもDomain Modelの計算から生成し、戦闘側に起動モード判定を
分散させない。Gameはメニュー項目の表示と、手動セーブ・デバッグ画面の開始可否も判断する。

起動モード別の成長上限は `LaunchMode` が数値として提供し、GameがBattleSceneと
呪文・自動回復Overlayへ渡す。Scene／Overlayは上限値だけを成長Systemへ渡し、Systemや
Domain ModelにGameや起動モードへの参照を持たせない。`Proficiency.add_progress()` は
適性と実行時の上限を併用し、既存値を引き下げずに追加分を制限する。BattleProgressionは
共有経験値の追加分も制限し、実際の獲得値を結果へ返す。Gameは同じ上限値をメインメニューの
経験値到達色の判定にも使う。上限はSettings／SaveDataに保存しない。

イベントRunnerと共通条件評価器はGameへの逆参照を持たず、`LaunchMode` の値だけを受け取る。
フィールド・戦闘イベントとミッション条件のすべてへ同じ起動モードを渡す。
具体的なモードと操作・受け入れ条件は [起動モード仕様](./features/launch-modes.md) を参照する。

### Settings

端末やプレイヤー設定。BGM、SE、言語、表示倍率、表示方式、画面フラッシュ、キー配置などを持つ。
ゲーム進行とは別に `~/.config/.pyxel/dungeon-antiqua-zero/settings.json` へ保存する。
設定変更時は一時ファイルからの置換で即時保存し、起動時に読み込む。設定ファイルがない場合や
内容を安全に復元できない場合は初期値を使う。現段階の`Settings`は言語、BGM音量0〜4、SE音量0〜4、
画面倍率1〜5、`DisplayMode.PIXEL` / `DisplayMode.SMOOTH`、画面フラッシュとゲーム内ヒントの有無、
`SpellMode` で表すオートの呪文使用方針、コマンド記憶の有無、操作説明を確認した入力種別を保持し、
BGM・SE・画面倍率はDA2と同じ初期値3・3・3、表示方式はピクセル表示、画面フラッシュとゲーム内ヒントは有効を使う。

呪文使用方針とコマンド記憶の設定・互換性は [フィールド](./features/field.md) を参照する。
選択したコマンドの記憶はSettingsへ含めず、Gameが `BattleCommandMemory` を
所有し、BattleSceneへ明示的に渡す。`systems/save.py` が独立した保存対象として
JSONへ変換し、検証済みの `LoadedGameState` に含めてゲーム状態と同時に復元する。キャラクターの安定キーで
保持する記憶と、Sceneのカーソル・パーティ番号による一時状態を分ける。
記憶する範囲と復元規則は [戦闘](./features/battle.md) を参照する。
保存形式と旧セーブ互換は [セーブデータ](./features/save-data.md) を参照する。

ゲーム内ヒントのWindow、入力解放待ち、開閉状態は `ui/hint.py` の `HintOverlay` が所有する。
Gameはロード成立時にOverlayを生成し、最上位のゲームメニュー・画面遷移に続いて入力を渡す。
表示中はフィールド更新へ進まず、終了後にOverlayを破棄する。表示仕様は
[ゲーム内ヒント](./features/game-hints.md) を参照する。

言語は `Language` で表し、保存値と共有JSONの接尾辞には `ja`、`en`、`zhcn` を使う。初期値は `ja` とする。フォントファイル名に含まれる `zh_hans` はアセット名であり、保存値やデータキーには使用しない。

言語別・表示用途別のフォントは `FontResources` が所有する。画面側はファイル名ではなく
`FontRole.STANDARD`、`FontRole.LARGE` のような意味上の用途を指定する。フォントを変更する
場合は用途と言語に対応する `FontDefinition`（ファイル名、ベースライン補正、行高）を差し替え、
個々のSceneやOverlayへフォントファイル名や高さを持たせない。フォントは必要になった用途から
読み込み、複数の用途や言語が同じファイルを使う場合も生成済みの `pyxel.Font` を再利用する。

| 用途 | 言語 | フォント | ベースライン補正 | 行高 |
|---|---|---|---:|---:|
| 標準 | `ja` | `k8x12S.bdf` | 0px | 12px |
| 標準 | `en` | `k6x8_gothic.bdf` | +3px | 8px |
| 標準 | `zhcn` | `fusion-pixel-12px-monospaced-zh_hans.bdf` | 0px | 12px |
| 大きい表示文字 | `ja` | `umplus_j12r.bdf` | 0px | 13px |
| 大きい表示文字 | `en` | `k6x8_gothic.bdf` | +3px | 8px |
| 大きい表示文字 | `zhcn` | `fusion-pixel-12px-monospaced-zh_hans.bdf` | 0px | 12px |

フォント間のアセント差は `FontResources` のベースライン補正値として管理し、
`WindowText` の文字グリフの描画Y座標へ加算する。英語フォントは日本語・簡体字
中国語フォントより3px下げ、同じ行に置いた文字のベースラインを揃える。タグで
埋め込んだアイコンにはフォントのベースライン補正を適用せず、行本来のY座標を
基準に配置する。

タグ付きテキストのアイコンはフォントの文字幅によらず常に8px幅として扱う。
アイコン描画後の文字送りにも `ICON_SIZE` の8pxを使用する。

翻訳済み文字列をWindowへ配置するときは、`LocalizedWindowTextFactory` が選択言語と
表示用途に対応するフォントとベースライン補正を束ねて `WindowText` を生成する。このファクトリは
翻訳キーを解決せず、各SceneやOverlayが `TextCatalog`、Domain Modelから取得した
表示文字列を渡す。キーの選択、複数の表示値の連結、座標は画面側の責務とする。
簡体字中国語の英数字・記号と漢字の混在は、このファクトリが `TextFontSpan` として解決する。
実描画幅もファクトリの `text_width()` で求め、描画と幅計算で同じフォント切替を使う。
戦闘のようにWindowへ逐次文言を追加する画面では、ファクトリの `apply()` を
`WindowFactory` の `text_style` として渡す。Windowは渡された表示スタイルを登録時に適用し、
言語や翻訳カタログを所有しない。明示的なフォント指定はこのスタイル適用より優先する。

固定幅の表示文字列は `ui.text_format` の `pad()`（右寄せ）と `spacing()`（左寄せ）で
整形する。両関数はPyxelや現在言語に依存せず、ASCII文字と余白を全角へ変換したうえで
指定文字数へ揃える。数値欄などの上限幅は画面側が指定し、Domain Modelの整数値には
余白や全角変換を持ち込まない。
アイテム名などの固有の多言語名は固定幅として扱わず、一覧でも画面側が
文字数や表示幅で切り詰めない。アイテム画面と装備候補一覧は、選択言語の
名称を末尾までそのまま表示する。

選択中言語のフォントがない場合は、別言語のフォントへ暗黙に置き換えずリソースエラーとする。簡体字を日本語フォントへ置き換えても表示を保証できず、配布物の欠損を隠すためである。

多言語フィールドの選択は `Localizer` が担当し、フォント読込とは分離する。フォールバック順は日本語が `ja → en`、英語が `en → ja`、簡体字中国語が `zhcn → en → ja` とする。任意の先頭フィールドを選ぶような非決定的なフォールバックは行わない。

日本語・英語・簡体字中国語モードの表示文字列はDA2と同様、原則として表示時にASCII文字と半角スペースを全角へ変換する。日本語モードでは原文がASCIIかUnicode全角かを問わず、英数字を含む全文を日本語標準フォント `k8x12S.bdf` の8px幅で表示する。英語用6×8ドットフォントへ部分的に切り替えない。JSONの原文は原則として意図する表示幅のまま保持し、`Localizer.value()` は変換前の値、`Localizer.text()` は表示用に正規化した値を返す。画面側で翻訳済み文字列へ英数字を連結する場合も、`LocalizedWindowTextFactory` が配置時に同じ正規化を適用する。これにより識別子、保存値、計算値へ全角変換が波及しない。`%FIRE%` のような表示制御タグ自体は変換・フォント判定の対象にしない。
戦闘画面右端の味方HP表示とセーブ・ロードの日時表示はレイアウト上の明示的な例外とし、全角化した数値と区切りを英語用6×8ドットフォントで描画する。設定Windowの日本語言語ガイドに併記する`Language switching (JP / EN / CN)`もDA2準拠の例外として同じ英語用フォントで描画する。これらの例外は各画面の該当`WindowText`だけに閉じ、共通ローカライズ処理へ持ち込まない。

英語原文へUnicodeの全角文字を明示的に登録した場合は、通常のASCII原文から表示時に
全角化された文字と区別する。`Localizer.text()` が返す `LocalizedText` はこの原文由来の
情報を保持し、英語モードの `LocalizedWindowTextFactory` は前者を日本語フォントの8px幅、後者を
英語フォントの6px幅で表示する。フォント判定は表示用変換より前の原文に対して行い、
表示制御タグ内の文字は判定対象にしない。これはフォント欠損時の代替ではなく、
原文で明示された表示スタイルとして扱う。

キャラクター名など各レコード固有の表示値は `name_ja`、`name_en`、`name_zhcn` のような接尾辞付きフィールドに置く。種族名、性別名、画面項目名など複数レコードや画面から参照する表示語彙は `texts.json` に置き、安定した `text_key` で参照する。`TextCatalog` はキーからレコードを引き、実際の言語選択とフォールバックを `Localizer` に委譲する。Domain Modelとセーブデータには翻訳後の文字列ではなく、`FAIRY`、`FEMALE` などの安定キーを保持する。

`texts.json` の各言語フィールドは1行の文字列または複数行の文字列配列を許可する。
表示文の行数だけを理由に `text_key` を分割せず、意味上1つの文言は1キーにまとめる。
`TextCatalog.text()` は1行の値、`TextCatalog.lines()` は文字列・文字列配列の両方を
1行以上のタプルとして解決する。配列内の空文字は意図した空行として保持する。

DA2準拠の画面語彙を追加するときは、英語・簡体字中国語についてDA2の辞書の対応訳を
優先する。通常は対応訳がない言語を空文字とし、表示時の代替言語は `Localizer` が決める。
ユーザーから暫定翻訳を依頼された場合は、日本語から未登録の訳を補い、専門担当者のレビュー対象とする。
翻訳データの扱いは [コンテンツ運用](./content-workflow.md#google-sheetsとの同期)、
中国語の混在描画は [機能仕様の共通基準](./features/README.md#記載基準) を参照する。

メニュー画面のコマンド、Gold、経験値、難易度、プレイ時間、閉じる案内も
`menu.*` の安定キーで `texts.json` に登録する。操作アイコンを含む文言は
`%CANCEL%` のような論理操作プレースホルダーを翻訳文へ置き、画面構築時に
`input_icon_tag()` が返す入力種別ごとの表示タグへ置換する。翻訳データへ
`%KEY_X%` や `%GAMEPAD_B%` を直接固定しない。

メニューのメンバー欄では現在のパーティを上から順に表示し、各行は名前、名前右側の状態、
現在HP／最大HP、現在MP／最大MPで構成する。状態値は `NEGATIVE_COLOR` を使用し、死亡には
既存の `%DEATH%` アイコンを付ける。現在のゲームの初期パーティは
フィオラ、セリオンの2名とする。
HP・MPラベルも `menu.member.*` の安定キーを使う。顔は32×32pxで、前列をx=20px、
後列をx=32pxへ配置して隊列を表す。現在のゲームではフィオラとセリオンを前列とし、
メニュー回帰テスト用のfixtureではセリオンとエリカを後列にする。この隊列は初期状態であり、
キャラクターの不変なマスターデータには含めない。
メインコマンドには独立した「スキル」を置かず、スキルの確認はステータス画面から行う。
右上のコマンドWindowは8項目分の高さ27、右下の情報Windowはy=27から高さ27とし、
画面右下の「とじる」透明Windowは `(48, 57, 16, 4)` のまま維持する。

`Member` は現在言語やフォントを保持しない。名前、種族、性別の表示値が必要な場合は、Composition RootまたはSceneから現在の `Localizer` と `TextCatalog` を明示的に渡して表示用の不変スナップショットを生成する。固定幅化、余白、座標などは画面側の責務とし、DA2の `name_disp` のようなレイアウト処理をDomain Modelへ含めない。

用語上、`characters.json` と `CharacterDefinition` は加入可能キャラクターの変更されない
マスターデータ、`Member` は加入後の可変なゲーム状態を指す。離脱中のキャラクターまで
「現在のメンバー」と誤認しないよう、この二つは `members` へ統一しない。

町・ダンジョンのプレイヤー歩行画像を浮遊させるかは、既存の
`CharacterDefinition.race` が `Race.FAIRY` かどうかから自動判定する。フィールド描画専用の
キャラクターフラグは追加せず、`Member` やSaveDataにも複製しない。一方、マップ上の人物actorは
場面ごとに姿勢が異なるため、制作マップの `floating` を `MapActor`、実行時の `FieldActor` へ
渡す。PC用歩行画像を参照するactorの待機パターンは、画像が表すPCの種族ではなく配置側の
明示値を優先する。影だけは、Composition Rootが妖精の `battle_sprite` を抽出して描画層へ渡し、
妖精PC画像かつ `floating=false` の配置を判別する。

カーソルのY方向の浮遊とフィールドキャラクターの待機パターンは、`app/rendering` 配下の
小さな共通描画規則へ、それぞれの定数と純粋関数を置く。`ui/window.py` と
`rendering/field.py` がその規則を参照し、互いを参照しない。カーソルは従来どおり自身の
入力待ちタイマー、フィールドは描画時に渡された実行フレーム番号を入力とする。
フィールドキャラクターは安定した開始位相を加える。PCは `pc:{character_key}`、actorは
`actor:{map_id}:{actor_id}` を入力としてCRC32を計算する。
Pythonの実行ごとに変わる組み込み `hash()` や実行時乱数は使わず、セーブデータにも位相を保存しない。
マップエディタも同じCRC32計算を実装し、actorのプレビューを本編と一致させる。
フィールドで停止中の浮遊キャラクターは、共通規則から右足、立ち、左足、立ちを
20フレーム間隔、80フレーム周期、個体別位相で選ぶ。描画Y座標は変更しない。移動中は
`FieldMovement.walking_frame_count` による従来の歩行フレームを優先する。戦闘画像の横方向は
行動ポーズを表すため、この待機パターン切り替えを適用しない。
`FieldMovement.update_animation()` は移動を止めたまま歩行描画状態と画像パターン用の時間を
更新する。Gameはフィールドイベント中にPCのアニメーション更新と `FieldActors.update_roaming()` を
呼び、表示中のNPCの自律移動を継続する。FieldActorsはpartyの現在セル・移動先セルとほかのactorの
占有セルを衝突判定へ渡す。Gameは通常の自律更新とイベント制御移動のいずれでもpartyの現在セル・
移動先セルをFieldActorsへ渡す。占有セルはFieldMovementの現在位置と歩行状態から求め、
予約用の別状態を持たない。イベント指定の移動対象は自律更新から除外し、コマンド側の移動更新へ
任せて二重更新を避ける。
Gameは会話の起動元actor IDをイベントの一時状態として保持し、FieldActorsの自律更新から除外する。
フィールドイベントの終了・中断時に解除し、戦闘でイベントを一時中断している間は保持する。
メッセージ・待機中の詳しい継続規則は [`features/field.md`](./features/field.md) を参照する。
キャラクター用の共通影は `rendering/character_shadow.py` が、イメージバンク0の
`(80, 144)` から16×16pxを描く規則として所有する。`FieldRenderer` は町・ダンジョンのPCおよび
人物actorを描く直前に、この影を16×32px本体の下半分と同じ座標へ描く。影は個別の深度要素にせず、
対象キャラクターと同じ足元Yの描画処理内で本体より先に描く。prop、宝箱、ワールドマップ用
16×16px PCには適用しない。PC歩行画像を使う人物actorでは、Composition Rootが
`CharacterDefinition.race` から妖精に対応する画像番号を渡し、その画像かつ `floating=false` の
配置だけ影を描かない。妖精以外のPC画像やNPC画像のactorでは、従来どおり影を描く。

戦闘中のPCは `CharacterDefinition.race == Race.FAIRY` の判定と、カーソルと共通のY方向浮遊関数、
`pc:{character_key}` の位相を使う。`BattleScene` は最終的に選択した戦闘ポーズの描画元Xを
浮遊可否の入力とし、左から7番目の瀕死・睡眠ポーズと左から10番目の死亡ポーズでだけ
オフセットを0にする。状態異常そのものは浮遊可否の入力にしない。
攻撃ポーズではキャラクターと武器の合成全体へ同じオフセットを適用する。フィールド用の
待機パターン切り替えは適用しない。`BattleScene` は表示中の味方へフィールドと同じ共通影を
本体より先に描き、隊列移動、被ダメージの揺れ、逃走などの基準位置へ追従させる。妖精のY方向の
浮遊オフセットは影へ適用せず、種族や状態異常にかかわらず7番目と10番目のポーズには影を描かない。
本体が非表示の味方にも影を描かない。

顔グラフィックは共有画像 `faces/faces.png` の32×32px領域を使用する。
各レコードの左上座標を `characters.json` の `face_x`、`face_y` に保持し、
`CharacterDefinition.face_position` へ読み込む。画面はキャラクター名による座標分岐や
固定座標を持たず、現在の `Member.face_position` を参照して描画する。

戦闘表示も同じくマスターデータから解決する。タイムライン用の16×16pxアイコンは
`characters.json` と `monsters.json` の `icon_x`、`icon_y` を使い、イメージバンク1から
切り出す。キャラクターの戦闘スプライトは `characters.json` の `battle_sprite` を縦方向の
32px単位インデックスとして `characters/ch_battle` から解決する。モンスターの戦闘画像は
`monsters.json` の `image_id`、`width`、`height` から解決する。BattleSceneまたはその専用の
Rendererがこれらの描画用値を読む責務を持ち、名前・モンスター種別・固定座標で分岐しない。
`Member` や戦闘ルールは画像リソースを保持しない。

モンスターの不変な物理戦闘能力は、`monsters.json` の `attack`、`hit`、`defense`、
`evasion` から `MonsterCombatStats` へ読み込む。戦闘ルールはこの値を命中・ダメージ計算の
入力とし、回避率を `agi` から再計算しない。現在HPや一時的な能力変化は戦闘ごとの可変状態が
所有し、マスターデータと `MonsterCombatStats` は変更しない。

モンスターの行動定義は `monsters.json` の `mmp`、`mag`、`int`、`special`、`extra`、`spells` から
読込境界で構造化する。`special` は日本語1文字ごとの特殊行動キー列、`spells` は改行区切りの
呪文安定キー列へ変換し、`extra` はアイテムと共通の追加効果型へ変換する。最大MP、術補正値、知恵、
行動候補は不変な定義として保持し、現在MPと沈黙残り行動数は戦闘ごとの可変状態が所有する。BattleSceneや
Rendererは生の連結文字列・改行区切り文字列を再解釈せず、敵AIの行動選択結果を利用する。
基本AIは残MPと沈黙状態を候補選択へ使わず、選択後の共通発動処理が戦闘ごとの沈黙状態と
現在MPをこの順に検査し、発動時だけMPを消費する。

モンスターのお宝定義は `treasure_item` をアイテム安定キー、`treasure_rate` を0から16の
16分率として読込境界で検証する。戦闘終了後のドロップ判定と報酬確定は
`BattleProgression` 相当のPyxel非依存Systemが所有し、BattleSceneは判定結果の表示だけを
調停する。候補は最後に撃破した敵1体とし、1戦闘で1回だけ判定する。アイテム付与と所有上限の
判定は既存の `InventorySystem` を経由し、付与に成功した場合だけ `MonsterRecordSystem` へ
取得済みを記録する。

通常攻撃の総合攻撃力、命中判定、物理ダメージは、PyxelやSceneに依存しない
`battle_physical.py` が計算する。BattleSceneと単独戦闘テストは、`Member` の装備・能力・熟練度、
または `MonsterCombatStats` から入力値を組み立て、0～99の命中乱数を明示的に渡す。
演出側は計算結果の命中可否とダメージだけを受け取り、同じ式を重複実装しない。

情報サブメニュー、会話ログ、モンスター図鑑は `ui/information_menu.py` のOverlayが入力、
一覧カーソル、開示段階、Window構成、モンスター画像描画を所有する。会話ログは
`SaveData.logs` の安定キーと引数を現在言語で解決し、日本語本文にはイベントメッセージと同じ
`FontRole.LARGE` を使う。図鑑一覧用の不変データは
`MonsterDefinition` として `monsters.json` から読み込み、遭遇順ではなくマスター順で
`SaveData.monster_records` のキーと照合する。Overlayはセーブ状態を更新せず、戦闘側の
`MonsterRecordSystem` が記録した項目だけを表示する。詳細な操作と開示規則は
[`features/information-menu.md`](./features/information-menu.md) を正本とする。

ステータスメニューOverlayは左右方向または前後ページ入力で表示中のMemberを切り替え、
両端では循環する。切り替え時は名前だけでなく、顔、装備、能力値、熟練度を含むWindow全体を
現在のMemberから再構築する。メニュー回帰テストでは疑似パーティを構築し、実行時には
現在のパーティを、メニューの「ステータス」決定時に同じSettings、
TextCatalog、フォント、顔画像、パレット変換器とともに渡す。
ステータスWindowはアニメーションなしで即時表示する。
メニュー側は最後に表示したメンバー位置を保持し、次回のステータス表示を同じ位置から始める。
通常表示中のキャンセル時はPyxelを終了せずメニューへ戻る。

表示中のMemberが1つ以上のスキルを持つ場合は、右上に `%CONFIRM%：スキル` の
透明ガイドを表示する。通常表示中に決定するとスキル欄の実データ行へカーソルを移し、
左右方向と前後ページによるMember切り替えを停止する。画面に表示するスキルは従来どおり
先頭2件とし、空行はカーソル対象にしない。選択中はDA2のスキルガイドと同様に、
選択スキルの正本で指定された最大2行の説明を画面下部のWindowへ表示する。
上下入力でスキルを循環し、キャンセルで通常表示へ戻る。スキルを持たないMemberでは
ガイドを表示せず、決定しても状態を変更しない。この判定はキャラクター名ではなく
現在の `Member.skills` を使うため、イベント習得後は同じMemberでも自動的に有効になる。

`Skill` は `skills.json` の `description_*` を文字列配列として検証・保持し、
`localized_description()` が行ごとに `Localizer` のフォールバック規則を適用する。
画面側は自動改行せず、正本の改行と色タグをそのまま使用する。

装備メニューOverlayはDA2と同じく、左のメイン欄、右上の候補一覧、右下のアイテム詳細で
構成する。左上は顔の右へ名前、前衛／後衛、装備可能な武器9種と盾のアイコン、各武器の
現在レベルを表示する。レベル成長のない盾には半角ハイフンを表示する。レベルはアイコン直下へ
Pyxel標準の実寸3x5テキストで置き、各8pxアイコンの右端へ揃える。アイコン間は2px空ける。
このアイコン列は4pxグリッドの例外として、0.5グリッド単位のピクセル座標で直接描画する。
続けて右手、左手、体、
頭、腕、オート装備を並べ、戦闘性能はステータス画面と
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
アクティブなカーソルを表示する。交換確定後は左欄へ戻り、交換元の部位にカーソルを残す。
装備画面の攻撃・命中・防御・回避・術防御は、変更前と変更後のどちらも
3桁右寄せで表示する。二刀流の攻撃値はDA2と同様、装備画面では装備比較用に
右手と左手を合計した3桁の値を表示する。ステータス画面では左右を3桁右寄せにし、
`xxx－xxx` のように区切りの前後へ空白を置かない。
装備部位の見出しは、装備画面の日本語・英語でだけ `%RIGHT%` などのアイコンを使う。
装備画面の簡体字中国語と、ステータス画面の全3言語はテキストの部位名を表示する。
ZEROには素手攻撃がないため、武器を外した手の装備名は空欄とし、「すで」相当の文言は
表示しない。

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

装備中の `special=DUAL_WIELD` は「にとうりゅう」、`special=TWO_HANDED` は
「りょうてもち」の習得と同等に扱う。この装備由来判定は `Member.has_skill()` に集約し、
装備画面、オート装備、戦闘処理が個別に `Item.special` を調べない。

装備品の `atk`、`hit`、`dfc`、`rst` は `Item` が非負整数として保持する。現在装備、
調整後能力値、武器・呪文熟練度から導出される攻撃・命中・防御・回避・術防御は、
保存値として重複保持せず `Member.battle_stats` が不変な `BattleStats` として計算する。
二刀流の攻撃・命中は右手と左手を別々に保持し、画面だけが左手攻撃の併記や命中の
平均表示を行う。小数点以下の切り捨てもDomain Model側で行い、画面側は全角数字への
変換だけを担当する。命中補正は装備中の武器レベル補正と他武器の到達補正を内部では
分けて保持し、画面の括弧内では両者の合計を表示する。「りょうてもち」の1.5倍は、
スキルを習得しているか `special=TWO_HANDED` の装備を持ち、対象武器を右手に装備し、
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
ステータスメニューOverlayでは適性0（使用不可）の武器・呪文のレベルと熟練度を `DISABLED_COLOR` で表示する。
ステータスメニューOverlayでは適性2（得意）の武器・呪文に限り、種別アイコンの開始位置から8px左の同じ高さへ
得意マーカー（共通画像バンクの `(152, 24)` から8×8px）を表示する。

共有経験値は `SaveData.experience` が1つだけ所有し、各 `Member.experience_offset` を加えた値から
DA2の累計必要経験値式で内部LVを導出する。`Member.internal_level` は現在値のキャッシュであり、
戦闘報酬確定、加入・再加入、ロード時に再計算する。セーブv2は補正値を保存し、v1からは
保存済み内部LVの必要経験値と共有経験値の差を補正値として移行する。

キャラクター正本の `base_str`、`base_agi`、`base_mag` は、変更されない
`CharacterDefinition.base_abilities` として保持する。画面やゲームルールは基礎値を
直接使わず、`Member.adjusted_abilities` を参照する。調整後能力値は現在装備している全品の
`str`、`agi`、`mag` をそれぞれ基礎値へ合算し、上限を32とする。装備による負の補正も
そのまま合算する。将来追加するアイテムによる永続上昇も後者の計算へ追加し、正本由来の
基礎値とは混在させない。

現在HP、最大HP、現在MP、最大MPは可変な `Member` 状態とする。能力値やHP・MPを
Python上で保持するときは整数のままとし、画面へ渡す時点で共通の
`format_number()` により、選択言語にかかわらず全角数字へ変換する。

前列・後列は加入後に並び替えられるため、`CharacterDefinition` ではなく `Member` の
`FormationRow.FRONT` / `FormationRow.BACK` として保持する。画面はこの安定値を参照して
表示位置を決め、キャラクター名による前後列判定を持たない。メニューの「ならびかえ」は
入れ替え元と入れ替え先を順に選択し、異なるMemberなら表示順を交換、同じMemberなら
前列・後列を切り替える。戦闘参加中の生存かつ麻痺していない最後の前列Memberを後列へ
移す操作と、控えとの交換によって同条件の前列が不在になる操作は受け付けない。
メンバー選択カーソルは顔の左へ置き、入れ替え元の決定後は少し右へずらした
非アクティブ色のカーソルを残す。入れ替え元の決定後、現在のカーソルも入れ替え元にある
場合に限り、現在の前後列から移動できる方向を顔の横の点滅矢印で示す。矢印画像は
30フレームごとに切り替える。最後の生存かつ麻痺していない前列Memberには後列方向の矢印を
表示せず、実際に無効な変更を行おうとした場合はDA2相当の効果音と短い横揺れでエラーを
通知する。入れ替え元の選択前に右入力するとメインメニューへ戻り、選択後の右入力は無視する。
アラートの残り時間は`update()`で進め、`draw()`から状態を変更しない。

装備品のフィールド回復力は `items.json` の符号付き整数 `healing` を `Item` が保持する。
正数は回復、負数はダメージ、0は増減なしを表す。
`Member.healing` は現在装備の値を合計し、`heal_and_poison_amount` はそこから毒の1HPを
差し引いた次回増減量を返す。死亡中はどちらも0とする。実際のHP変更は
`apply_heal_and_poison()` が0〜最大HPへ収めて行い、画面はこの状態変更を行わず、
正常時のHP欄へ正なら `（＋n）`、負なら `（－n）` を表示する。状態異常表示がある場合は
DA2同様に増減表示より状態名を優先する。`Game` はダンジョンの通常歩行が1セル完了し、
イベントやマップ移動が発生しないことを確認した後、ランダムエンカウント判定より先に全Memberへ
`apply_heal_and_poison()` を呼ぶ。world／town profileやイベント移動では適用しない。
この増減でHPが0になったMemberは状態異常と戦闘中補正を解除する。`Game` は変化前後のHPから
新たな死亡者を検出して標準メッセージOverlayへ通知し、生存かつ麻痺していない戦闘参加者の
前列が不在なら、並び順で最初の該当者の `formation_row` を `FRONT` へ変更する。控えはこの
繰り上げ判定に含めず、戦闘からフィールドへ戻す完全暗転時にも同じ補正を行う。
町・ダンジョンの歩行画像もDA2と同様にパーティ順で最初の生存かつ
麻痺していないMemberを参照し、該当者がいない場合だけ先頭Memberへフォールバックする。

毒と麻痺は戦闘後も続く真偽値、眠りと混乱は戦闘中の残り行動数として `Member` が保持する。
敵側は `MonsterBattleState` が同じ残り行動数を保持し、`BattleScene` がタイムライン先頭で
混乱を1減らして、同陣営を優先する強制通常攻撃へ置き換える。睡眠と混乱の相互解除、および
正の通常ダメージによる解除は各状態モデルが所有する。
町・ダンジョンなどからワールドマップへ切り替える際は `Game` が全Memberへワールドマップ復帰を
通知し、死亡状態を維持したまま、生存者のHPと全員のMPを最大まで回復し、それ以外の
状態異常と戦闘中補正を解除する。
状態表示の優先順位は死亡、麻痺、眠り、混乱、毒とする。
戦闘またはダンジョン歩行による全滅では、共通の全滅帰還フェードで完全暗転した後に
復帰メッセージOverlayを表示する。最終ページの確認時に全Memberへ `fully_recover()` を呼び、
HP・MP、状態異常、戦闘中補正を全回復してから入口直前へ戻す。
`Member.status()` は状態異常または死亡を返し、画面用途に応じて正常時の「OK」か空文字を
選べるようにする。最大HPの整形は状態表示と分離し、各画面がHP欄で行う。死亡表示には
`%DEATH%` を付ける。メインメニューとステータス画面は異常値を `NEGATIVE_COLOR` で描画し、
詳細画面ではタグを含む描画幅を測って正常時の「OK」と右端をそろえる。
死亡中の顔は `PaletteShifter` の常設グレースケールvariantを一時適用して描画する。
同じvariantをメンバーごとに再利用するため、死亡人数によってパレット領域は増えない。
手動セーブと起動時ロードのスロット一覧も、保存サマリーがHPから導出した死亡メンバーキーに
基づいて同じvariantを適用する。

`Item` と `Skill` も現在言語やフォントを保持せず、共有JSONのレコードから生の検索キーと多言語名だけを初期化する。表示時に `Localizer` を明示的に渡し、英語の全角化を含む表示名を取得する。現在の共有JSONでは `name_en` がキャラクターや店からの検索キーを兼ねているため、全角化後の英語名やほかの言語の表示名を検索・保存に使用しない。将来、表示名と独立したキーをデータへ追加する場合も、Modelの呼び出し側は同じ生のキーを参照する。

設定画面で言語を変更した場合は `Settings.with_language()` で新しい設定スナップショットを作って保存し、新しい `Localizer` と標準フォントで表示中のWindowを再構築する。既存Windowがグローバルな言語変更を監視したり、フォントだけを後から差し替えたりしない。翻訳後の文字幅が言語ごとに異なるため、必要なレイアウト変更もWindow再構築時に反映する。

メニューの設定OverlayではDA2と同じ順序で、左右入力により言語、BGM音量、SE音量、
画面倍率、表示方式を循環変更する。その他の設定項目と左右操作の詳細は
[フィールド](./features/field.md) を参照する。
設定項目、アクション、ガイドは4pxグリッド上で3単位、すなわち通常の12px行間へ揃え、
項目群の区切りだけ空行を1行置く。
メニューで初めて表示するメイン、設定、確認の各Windowは閉じた状態で生成し、既存の
`Window.open()`により中央から上下へ開く。設定画面で言語を切り替えた際に再構築する
メインWindowは開いた状態で生成し、アニメーションを繰り返さない。いずれかのWindowが開閉中は入力を受け付けず、
パーティの顔画像とカーソルも所属Windowが完全に開いてから表示する。
フィールドと接続済み画面の詳細は [`features/field.md`](./features/field.md) を正本とする。
起動直後は `scenes/title.py` の `TitleScene` を表示する。Sceneは文言の描画と決定入力を所有し、
`Game` は決定後の要求を `GameScreenChange` と標準フェードで調停する。初回と入力種別変更時は
`ui/control_guide.py` の操作説明Overlayを挟み、試遊版は毎回表示する。確認後、試遊版は既存の
ニューゲーム開始処理へ直接接続し、ほかのモードは完全暗転時に `ui/start_menu.py` の
ロードOverlayを生成する。セーブ一覧の読込はロードOverlayの生成時に限定する。ニューゲームでは
初期状態を、ロードでは `systems/save.py` が完全に検証・再構築した `LoadedGameState` と
`MapResources` が解決した保存地点をフェード開始前に準備する。完全暗転時にだけ
`Game` が状態一式を反映し、`FieldMovement` と `FieldRenderer` を使うフィールドへ切り替える。
ロード用の `FieldMovement` はマップ内の保存座標であれば通行不能セルも開始地点として許可する。
ニューゲーム、マップ到着地点、NPC配置では従来どおり開始セルの通行可否を検証する。
タイトルとロード画面のレイアウトと入力は [`features/start-load.md`](./features/start-load.md) を正本とする。
メインメニューで
キャンセルした場合もプロセスを終了せず、現在位置を維持してワールドマップへ戻る。
メニューからワールドマップ、ワールドマップからメニューの
どちらも標準フェードを使い、完全暗転時に表示対象を切り替える。ワールドマップでは論理
`menu`入力でメニューを再表示し、メニューのWindowとカーソル位置は往復時に破棄しない。
ワールドマップからメニューを開く場合だけ、完全暗転時に既存Windowの表示高を0へ戻して
中央からの開放を再開する。Window開放は8フレーム、フェードインは6フレームであるため、
暗転中にWindowを2フレーム分進め、残り6フレームをフェードインと並行して両方を同時に
完了させる。Windowのテキスト、カーソル対象、現在の選択位置は再生成しない。
ワールドマップ上の決定とキャンセルには、現時点では操作を割り当てない。モック確認用だった
決定によるショップ選択と、キャンセルによるプロセス終了は本編接続から撤廃する。
タイトル、操作説明、スタート・ロード画面では `BgmPlayer` により `da3-welcome` をループ再生する。
フィールドへの切り替え成立時に現在マップの `bgm_id` へ切り替え、メニューと
フィールドの往復、および同じBGM IDを持つマップ間の移動では再スタートしない。
BGM音量変更は再生中のチャンネル2へ即時反映する。
SE音量変更時はチャンネル利得を更新して確認音を鳴らし、表示方式は`pyxel.screen_mode()`へ
即時反映する。画面倍率はDA2同様に次回のタイトル復帰時へ反映し、倍率5をフルスクリーンとする。
「タイトルがめんへ もどる」と「ゲームを しゅうりょうする」は、翻訳済みの確認文と
「はい／いいえ」を持つ確認Overlayを経由する。タイトル復帰は端末設定を環境変数へ退避する。
確認で「はい」を決定した後は、表示中のメイン、設定、確認Windowを標準の8フレームで閉じる。
閉じ終えるまでは入力を遮断し、閉じた後も決定、キャンセル、メニュー、前後ページの入力が
すべて離されるまで待ってからGame所有状態を再生成する。これにより、再生成された
`PyxelInputReader` が復帰を決定した押下をタイトル画面の新規入力として検出しない。
適用済みの画面倍率から変更がなければ、現在のPyxelウィンドウと `PaletteShifter` を維持したまま
Game所有状態を再生成して仮タイトルへ戻る。起動モードは再生成時にも保持する。倍率が変わった場合だけPyxelの
ウィンドウ状態を破棄して `pyxel.reset()` を実行し、再起動後の
`pyxel.init(display_scale=...)` へ倍率を渡す。倍率5ではフルスクリーンを有効化する。

イベントの `reset_game` は `ResetGameEffect` を返し、Gameが同じタイトル復帰経路へ接続する。
Runnerはbranchを含む残りのコマンド列を破棄する。復帰待ちはイベント・戦闘更新より優先し、
入力リリース後に実行中のRunnerや中断した戦闘ごとGameのプレイ状態を再生成する。
再生成前に全画面パレットの合成を通常状態へ戻し、明るさ変更などをタイトルへ持ち越さない。
操作とコマンド形式は [イベント仕様](./features/events.md#ゲームをリセット) を参照する。

ワールドマップ拠点の詳細は [`features/world-sites.md`](./features/world-sites.md) を正本とする。
`resources.maps` は生成済みの拠点、遷移先参照、到着地点を不変の値として読み込む。拠点は
移動元として入口と参照だけを持ち、移動先の座標・向きは到着地点だけが所有する。
`WorldSiteCatalog` は入口セルと拠点IDの索引、近隣拠点、訪問済み候補の抽出だけを担当し、
SaveDataやUIを所有しない。`TravelSystem` は拠点への入場成立時の記録と、訪問済み拠点IDに
紐づく `teleport_enabled` の到着地点解決を担当する。施設出口などの移動イベントも同じ
`MapDestination` 参照形式を使う。
Field Sceneは移動完了を受けて遷移を要求し、実際の
Scene切り替えはTransitionとして調停する。拠点名Windowやフェードの状態をCatalogやSystemへ
持たせない。

本編の起動モードはComposition Rootが起動オプションから生成し、`Game` が保持する実行時依存とする。
プレイヤー設定やゲーム進行ではないため、`Settings`、`SaveData`、設定ファイル、セーブデータへ
保存しない。現在は通常モードだけ設定Overlayへデバッグ入口を生成し、画面開始時にもモードを
確認する。最終的には通常モードでも非表示にする。詳細は
[`features/launch-modes.md`](./features/launch-modes.md) を正本とする。

デバッグメニュー固有の入力、数値入力バッファ、候補一覧は
`app/ui/debug_menu.py` が所有する。ただしTELEPORTの行き先候補一覧は本編と共通の
`app/ui/teleport_menu.py` が所有し、デバッグメニューは同じOverlayを呼び出す。`Game` はデバッグ画面の生成、終了、更新後の
パーティ参照だけを担当し、デバッグ項目ごとの分岐を `game.py` へ増やさない。数値入力はDA2の
セーブコード入力と同じ0〜9の2段パッド、削除、決定で構成し、パーティLVは1〜99、Goldは
0〜999999へ制限する。メンバー候補20人は10行×2列に配置し、スクロールなしで1画面に表示する。
メイン項目および一覧の標準行送りは12pxとし、各画面で広い空行を個別に設けない。
「メンバー状態」は現在のパーティから対象を選ぶ一覧と、対象のHP、MP、毒、麻痺を編集する
詳細画面に分ける。HPとMPは同じ数値入力を再利用し、それぞれ0〜現在の最大値に制限する。
詳細画面の「スキル」からは、読み込み済みの全スキルをデータ順の10行×2列で表示し、
現在のMemberが持つものへ選択済み印を付ける。決定入力では選択スキルを自由に追加・解除する。
各Memberが同時に持てるスキルは最大2つとし、2つ選択済みの状態で未選択スキルを決定しても
構成を変更せず、デバッグ画面のエラー通知を行う。
スキル名は本編データと現在言語から解決し、安定キーや表示名を編集状態として複製しない。
デバッグアイテム画面にはComposition Rootから既存の `InventorySystem` を注入する。
画面は `InventorySystem.catalog_items` を無限在庫の候補、`InventorySystem.items` を現在の所持品として
左右に表示し、候補の選択状態と列ごとのスクロール位置だけを所有する。右列の決定入力は
`InventorySystem.add(..., members=party)` へ1個の取得を依頼し、通常取得と同じ所持上限および
装備中個数の判定を再利用する。候補一覧自体は減らさず、左列は読み取り専用とする。
アイテム名は本編データと現在言語から解決し、デバッグ画面へItemカタログや所持数の複製を持たせない。
デバッグ画面だけに登場する日本語文言は `app/ui/debug_text.py` に置き、翻訳対象の
`content/data/texts.json` やGoogle Sheetsへ含めない。デバッグ画面では言語設定にかかわらず
日本語フォントで表示する。キャラクター名は本編でも使うため、通常どおりキャラクターデータと
現在の言語設定から解決する。

デバッグテレポートの候補はField側が `TravelSystem.teleport_destinations()` で抽出し、現在言語の
拠点名と安定した拠点IDだけをデバッグ画面へ渡す。候補表示、スクロール、決定入力はデバッグ画面が
所有し、移動要求は注入されたコールバックでFieldへ返す。Fieldは
`TravelSystem.teleport_destination()` で選択先を再検証し、通常のマップ遷移と同じ到着地点適用処理を
使う。デバッグ画面は `MapResources`、`FieldMovement`、Scene遷移を直接参照しない。

デバッグショップの候補は `Game` が読み込み済みのShopからデータ順に安定キーだけを抽出し、
デバッグ画面へ渡す。候補表示と選択はデバッグ画面が所有し、選択結果をコールバックで `Game` へ
返す。`Game` はデバッグ編集済みパーティを反映してから、通常と同じ標準フェードと
`ShopOverlay` で店を開く。ショップ終了時はデバッグ画面を破棄せず、選択中だったショップ一覧へ
戻す。フィールドSceneはこの開発用ショップ選択を知らない。

デバッグエンカウントは `ui/debug_encounter.py` が設定画面と `DebugEncounterState` を所有する。
Gameは起動中の状態を保持してOverlayへ注入し、開始要求を受けて通常の `EncounterSystem` と
遭遇Transitionへ接続する。設定はSaveData／Settingsへ含めない。詳細は
[エンカウント仕様](./features/encounters.md#デバッグエンカウント)を参照する。

パーティをまたぐデバッグ操作はPyxel非依存の `systems.debug.DebugPartyEditor` が担当する。
フィオラを必須とし、フィオラを含むパーティ総数を1〜6名に制限する。
指定したパーティLVをフィオラの内部LVとし、
ほかのキャラクターは `lv_diff` を加えた値を1〜99へ収める。LV変更時は選択中Memberを
マスターデータから再生成し、武器・呪文熟練度、最大HP・MP、現在HP・MPを指定LV相当に戻す。
通常加入時のフィオラLV1固定規則は変更せず、明示LVでの再生成には
`Member.from_record_at_internal_level()` を使う。
現在HP・MPの境界検証と毒・麻痺の付与・解除も `DebugPartyEditor` が担当する。
毒・麻痺はHPとは独立して自由に切り替えられるデバッグ状態とし、HPを0にする操作では
自動解除しない。パーティLVの変更では従来どおりMemberを再生成するため、個別編集値も初期化する。
`DebugPartyEditor` は読み込み済みのSkillカタログも候補として公開し、安定したスキルキーを
受け取って現在の `Member.skills` へ重複なく追加、または解除する。キャラクター固有の
習得条件は適用しないが、現在スキル数は最大2つに制限する。

### SaveData

セーブ対象となる進行状態。JSON上のフィールド、型、境界値、移行規則は
[`features/save-data.md`](./features/save-data.md)を正本とする。具体的には次のような情報を持つ。

- 離脱中を含むキャラクター、現在パーティ、装備、成長状態
- 所持品、所持金、アイテム図鑑
- イベントフラグ、訪問済み地点、取得済み宝箱
- マップID、セル座標、向き
- 戦闘回数、モンスター図鑑、ログ

SaveDataは「保存可能な現在のゲーム世界」を表す。ウィンドウ、描画用タイマー、選択中カーソル、Pyxelオブジェクトなどを入れない。

魔力減衰率、敵強化段階、設備停止状態などの世界進行結果は、イベントフラグと戦闘回数から
`WorldProgression` が導出するためSaveDataへ複製しない。オートマッピングの踏破状態と
重要アイテム専用の所持一覧も保存しない。

所持金 `gold`、パーティ全体で共有する経験値 `experience`、難易度
`difficulty`、プレイ時間 `play_time_frames` は、個々のMemberではなく
SaveDataが所有する。難易度の保存値には表示文言から独立した
`Difficulty.NORMAL` / `Difficulty.HARD` を使う。プレイ時間はフレーム数のまま保存し、
プレイ中の `Game.update()` から加算する。表示文字列への変換は複数画面で共有する
`ui.text_format.format_play_time()` が担当し、SaveDataや `draw()` は表示形式を持たない。
一度入場した拠点は `visited_site_ids` に安定IDだけを集合として保存する。拠点名、入口、到着地点、
遷移先はマップデータの責務であり、SaveDataへ複製しない。

### Scene固有状態

フィールド待機時のメニュー操作ナビは `ui/field_menu_guide.py` の `FieldMenuGuide` が
待機タイマーと非対話Windowを所有する。現在のComposition RootではGameが通常フィールドの
操作可否を渡し、入力・移動・Modal・遷移で表示と待機時間をリセットする。ナビからGameや
Fieldを逆参照しない。表示条件は [フィールド仕様](./features/field.md) を参照する。

フィールドガイドのタイマーは `FieldScene`、戦闘コマンド選択は `BattleScene`、店のカーソルはShop Overlayが所有する。Scene固有状態を巨大な共有RuntimeStateへ集めない。

ワールドマップの鳥は `field_birds.py` の `WorldMapBirds` が出現待ち、飛行座標、速度、
羽ばたきのフレームと描画を所有する。現在は `Game` が現在マップに応じて生成し、
フィールド表示時の更新と `FieldRenderer` の後の描画を接続する。PC座標とカメラ座標だけを
明示的に渡し、鳥からGameや移動状態を参照しない。演出専用の乱数を使い、セーブや
衝突判定には含めない。詳細は [`features/field.md`](./features/field.md) を参照する。

### SystemとDomain Model

オートバトルの判断仕様は [features/auto-battle.md](./features/auto-battle.md) を参照する。
`auto_battle.py` と `auto_battle_simulation.py` はPyxelの更新・描画に依存しない戦闘ルールであり、
`auto_battle_model.py` の読み取り専用の戦闘状態、
開示済み情報と観測履歴、使用方針、対応済み効果の計算を明示的に受け取る。
Scene、Game、Windowへ逆参照せず、候補評価中に本体状態・本体乱数・成長記録を変更しない。
固定回復の選択規則は予測中の味方継続方針と共用し、必要な回復をケース評価に依存させない。
BattleSceneは計算の開始・中断と結果の実行を所有し、実際の効果・消費・遷移には
手動操作と共通の戦闘ルールを使う。判断履歴と計算途中の位置はSceneの一時状態として所有する。

Member、Item、Spellなど、データとそのデータに密接なルールはDomain Modelへ置く。複数のModelやSaveDataをまたぐ操作はSystemへ置く。

宝箱はマップactorの `kind=treasure` として配置する。`TreasureSystem` は `SaveData` と
`InventorySystem` だけに依存し、所有上限の確認、報酬付与、開封済み記録を一体として扱う。
Field側は表示コマと演出タイマー、Gameまたは将来のFieldSceneは入力とメッセージOverlayの接続を
所有する。宝箱を通常イベントへ変換せず、RendererやDomain ModelからGameを逆参照しない。

Systemへ単一の巨大なContextやAppを渡すと、再び暗黙の依存が増える。必要なデータとサービスを明示的に渡す。Sceneだけは調停役としてSaveDataや複数サービスをまとめて受け取ってよい。

## ZEROのイベント構造

ZEROはフリーシナリオ、戦闘回数による敵の強化、魔力設備の停止、種族ごとの魔力減衰などを予定している。これらを1本の `start_event()` やイベントIDの巨大な `if` / `elif` へ追加し続けない。

通常イベントは型付きのJSONコマンド列として定義する。詳細なsource形式、条件、初期コマンド、
マップトリガー、イベントエディタ、実行時エラーは
[`features/events.md`](./features/events.md) を正本とする。

イベント会話は通常UI語彙の `content/data/texts.json` と分離し、
`content/events/messages.json` から `app/events/messages.json` を生成する。イベント定義は
`message_id` だけを保持し、顔グラフィックのキャラクターキーはメッセージ定義が所有する。
Overlayがメッセージ定義から現在言語と顔を解決する。イベントnamespaceはID整理の単位であり、
マップIDとは対応付けない。

イベントフラグ宣言は各イベントnamespaceへ持たせず、`content/events/flags.json` でグローバルに
管理する。`flag_id` は全イベントから同じ値を参照し、任意のドット区切り接頭辞は分類目的だけに
使用する。生成時に宣言済みIDを `app/events/events.json` へ収録する。

Sceneはトリガー検出、EventRunnerは条件評価とコマンド進行、既存のDomain Model／Systemは
状態変更、Overlayはメッセージなどの入力待ちを担当する。RunnerはUIや具体的Sceneを直接参照せず、
メッセージ、音声、画面演出、時間待ち、移動、向き変更、ショップ、ID付き戦闘開始をEventEffectとして呼び出し元へ返す。ショップは
既存のShopOverlayを開き、退出後にRunnerへ完了を返して後続コマンドを再開する。複雑なカットシーンや
固有ギミックだけをPythonの個別ハンドラーにし、汎用コマンドで無理にすべてを表現することも、
すべてをPythonの巨大な条件分岐に戻すことも避ける。

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
| エンカウント加算、発生判定、モンスター候補抽出・編成、全滅時の出口解決 | `EncounterSystem` |
| エンカウント画面の回転・拡大パラメータ | `rendering/encounter.py` |
| フィールドの描画 | `FieldScene` またはField専用Renderer |
| 拠点のセル検索、近隣名表示候補 | `WorldSiteCatalog` |
| 拠点入場、テレポート到着先参照 | `TravelSystem` |
| 拠点名Window、マップ遷移要求 | `FieldScene` |
| 戦闘コマンドの入力 | `BattleScene` |
| ダメージ、命中、行動順の計算 | 戦闘ルール用Model/System |
| 毒や回復によるMember自身の変化 | `Member` |
| 店で何を選んだか | Shop Overlay |
| 価格、所持、装備可否 | `Item` / `Member` / `InventorySystem` |
| 宝箱の報酬付与と開封済み記録 | `TreasureSystem` |
| 宝箱の表示コマと一時的な開閉演出 | `FieldActors` |
| 一時パレットシフトと変換色 | `rendering/palette.py` |
| 戦闘終了後の世界変化 | `WorldProgression` |
| ウィンドウ枠、文字、カーソル描画 | `ui/window.py` |
| 確認結果を受けた後の処理 | ダイアログを開いたSceneまたはOverlay |
| SettingsとJSONの変換・永続化 | `systems/settings.py` |
| SaveDataとJSONの変換 | `systems/save.py` |
| 起動時のスロット選択と削除確認 | `ui/start_menu.py` |
| 強制割り込みの選択Windowとカーソル | `ui/game_menu.py` |
| ロードJSONからの状態再構築と検証 | `systems/save.py` |
| Scene切り替え、フェード、BGM調停 | `SceneManager` |

現在のComposition Rootでは `Game` が `EncounterSystem` の結果を受け、フィールド画面の保存、
`BattleScene` の生成、`BattleResult` に応じたフィールド復帰を調停する。同一マップ内だけ有効な
FADE状態と遭遇ボーダー補正、およびPC暗色点滅のRenderer入力も `Game` が所有する。エンカウント変数は
`SaveData`、戦闘内の一時状態は `BattleScene`、回転・拡大のフレーム状態は
`EncounterTransition` がそれぞれ所有する。ワールドマップへ切り替える時点でのHP・MP回復と
死亡以外の状態異常・戦闘中補正の解除は、`Game` が
`Member.recover_world_map_entry_ailments()` を呼んで行う。

配置に迷った場合は「どの状態を変更するか」「その状態の所有者は誰か」を先に決める。複数箇所から呼ばれるという理由だけで `util.py` へ移動しない。

ゲームメニューの割り込み入力は `InputState.interruption` とし、通常のキャンセル・
フィールドメニュー入力から分離する。`Game` が入力を最初に調停し、割り込み中は元画面の
更新・描画を呼ばない。Windowと選択状態は `GameMenuOverlay`、停止したBGMの再生位置と
予約曲は `BgmPlayer` が所有する。`BattleScene.is_transitioning` は割り込みを禁止する遷移の
有無だけを公開し、Gameが戦闘内部のタイマーを横断しない。
詳細な入力・復帰条件は [ゲームメニュー仕様](./features/game-menu.md) を参照する。

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
