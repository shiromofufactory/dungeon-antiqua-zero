# Dungeon Antiqua ZERO 開発用ツール

`tools/` には、データやリソースを対話操作で制作・確認する開発用プログラムを置く。
自動生成・同期・CI向けの処理は `scripts/`、配布するゲーム本体は `app/` が所有する。

開発用ツールは次の方針に従う。

- 画像、パレット、JSONなどを `tools/` へ複製しない。
- 表示確認ツールは `app/data`、`app/images`、`app/assets.pyxpal` など本番用生成物をそのまま読む。
- マップ制作ツールは `content/maps` と `content/images/mapchips` の正本を扱い、`app/maps` を直接編集しない。
- リソース形式の解釈は `app/resources` の本番用loaderへ置き、ツール固有の状態と操作だけを `tools/` へ置く。
- ゲームのSceneやSaveDataをグローバルに変更せず、必要な対象を引数で明示する。
- カレントディレクトリへ依存させず、リポジトリルートから `python3 -m tools.<module>` で起動する。
- `pyxel package app ...` の対象へ `tools/` を含めない。

## Spell Effect Editor

通常の呪文エフェクトについて、32px／64px画像の行と使用パターン数、1パターンの
ゲームフレーム数、味方・敵それぞれの対象位置補正、フラッシュ色、`se_id`を編集するPyxelツールである。
本番と同じ60fps、画像、パレット、Pyxel Soundを使って、キャラクターまたはモンスターへ
重ねた状態を確認できる。画像ストリップは下部の全幅に表示し、64px画像を8セル同時に比較できる。
未登録Soundはキー、Sound番号、channelを登録・試聴し、ゲーム用SEカタログへ保存できる。詳細仕様は
[`docs/features/spell-effect-editor.md`](../docs/features/spell-effect-editor.md)を参照する。

```sh
npm run spell-effect-editor
```

起動時に本番用画像を再生成する。画面では呪文やプレビュー対象を選び、右側のボタンで値を
変更する。`PLAY`で先頭から再生、`PAUSE`で一時停止、`STEP`で1/60秒送り、`LOOP`で
反復を切り替える。`TEST`は選択SEだけを鳴らす。`NEW SE`ではキーを入力し、上下キーで
Sound番号、左右キーでchannelを変更して、登録前に試聴できる。`SAVE`または`Ctrl+S`で正本、
ゲーム用生成物、追加したSEを保存する。`Q`または`Esc`で終了し、未保存変更があれば確認画面を表示する。
`FLASH`行の`PICK`では、0番の黒と、2〜61番を4色単位の暗色〜明色に並べた一覧から選択する。
`ALLY`／`ENEMY`を切り替えると、OFFSET欄は選択した対象側の値を編集する。

画面を開かずに検証またはゲーム用データを再生成する場合は次を使う。未設定の戦闘用呪文は
警告になるが、特殊エフェクトを本ツールの対象外にできるよう生成は妨げない。

```sh
npm run spell-effects:validate
npm run spell-effects:build
```

## Attack Pose Editor

戦闘用キャラクターの静止ポーズと武器画像を重ね、通常攻撃の振り上げ・振り下ろしを調整する
ローカルWebツールである。詳細仕様は
[`docs/features/attack-pose-editor.md`](../docs/features/attack-pose-editor.md)を参照する。

```sh
npm run attack-pose-editor
npm run attack-poses:validate
npm run attack-poses:build
```

## Image Viewer

生成済み画像を本番パレットで表示する。

```sh
npm run images:build
npm run tools:image-viewer
```

パレット修正前の試作生成物を表示する場合は、先に `npm run images:build:force` を実行する。

画像IDを指定する場合:

```sh
npm run tools:image-viewer -- background/bg_nector
```

画像ID一覧:

```sh
npm run tools:image-viewer -- --list
```

操作は矢印キーでパン、`N`または`Tab`で次の画像、`P`で前の画像、`Q`または`Esc`で終了する。透過色1は市松模様として確認できる。

## Map Production Editor

マップチップメタデータ、マップ、イベントの3画面は、単一のローカルWebサーバーと認証セッションで
動作する。共通入口ではマップ画面を最初に開き、ヘッダーの「マップチップ」「マップ」「イベント」で
切り替える。各画面の未保存変更は別画面への移動前にブラウザが確認する。

```sh
npm run tools:editor
```

以下の各コマンドは、最初に表示する画面を変える互換入口である。どの入口から起動しても、
ヘッダーから3画面すべてへ移動できる。

## Map Chip Metadata Tool

ワールド、ダンジョン、町で使用する16×16pxマップチップへ、地面の親子関係、8方向境界、
表示差分、アニメーション、複数セルオブジェクト、通行可否を設定するローカルWebツールである。
仕様は
[`docs/features/map-chip-metadata-tool.md`](../docs/features/map-chip-metadata-tool.md) を参照する。

```sh
npm run tools:mapchip-metadata
```

起動後はローカルURLを既定ブラウザで開く。別のブラウザで確認するときは、ターミナルに表示された
token付きURLを開く。自動でブラウザを開かない場合は次を使う。

ツール再起動前の画面が残っている場合、保存・検証時に現在のローカルセッションへ自動で
再接続する。再接続できない場合は、ツールを再起動して新しく開いた画面を使用する。

```sh
npm run tools:mapchip-metadata -- --no-browser
```

既定では `content/maps/tilesets/worldmap.json` と
`content/images/mapchips/worldmap.png` を開く。メタデータJSONは検証成功時だけ原子的に保存する。
画像のパレット不一致は問題一覧へ警告として表示するが、メタデータの保存は妨げない。
ヘッダーから既存タイルセットを切り替えたり、同じ元画像を再利用して新規作成したりできる。
ソース画像は作成後に変更できない。使用中でない通常タイルセットはソース画像欄から削除できる。
保存済みオブジェクト定義IDを変更して保存すると、同じタイルセットを使う全制作用マップの
`definition_id` も追随して更新する。追随先のない定義削除など、マップに未定義参照を残す変更は
保存できない。

対話UIは `tools/mapchip_metadata/`、UIから独立した検証処理は `scripts/map_pipeline/` に置く。
後続のマップエディタも同じ検証処理を利用する。

## Map Editor

タイルセットメタデータを使って地面とオブジェクトを配置し、制作用マップとゲーム用生成物を
同時に保存するローカルWebツールである。仕様は
[`docs/features/map-editor.md`](../docs/features/map-editor.md)を参照する。

```sh
npm run tools:map-editor
```

既定では `worldmap` マップを開く。`content/maps/sources/worldmap.json` がなければ、
32×24セルの海で埋めた新規マップとして開始し、保存するまでファイルは作成しない。
ヘッダーから既存マップを切り替え、マップID、タイルセット、profile、寸法を指定して別マップを
作成できる。マップの最小寸法は16×15セルで、外周と拡張領域はタイルセット先頭のベース地面で埋める。
同じprofileの別タイルセットへ変更すると、寸法を維持してマップ内容を初期化する。未参照の通常マップは
制作用データとゲーム用生成物をまとめて削除できる。

```sh
npm run tools:map-editor -- --map field_01 --tileset dungeon --profile dungeon
```

保存時に `content/maps/sources/<map_id>.json` と、Git管理外の
`app/maps/<map_id>.json`、`app/maps/<map_id>.bin` を生成する。全マップを再生成する場合は
`npm run maps:build` を使う。

「イベント」タブではactorを配置し、cell、object、actorをアンカーにしたイベントトリガーを
編集できる。イベント本文の作成は次のEvent Editorで行う。

## Event Editor

通常イベント、グローバルフラグ、条件分岐、メッセージ、音声、パーティ・actor移動などを構造化入力で
作成するローカルWebツールである。仕様は
[`docs/features/events.md`](../docs/features/events.md)を参照する。

```sh
npm run editor -- --editor event
```

ヘッダーから既存のnamespaceを切り替え、新しいnamespaceを入力してイベントファイルを新規作成
できる。namespaceはマップIDと1対1で対応する必要はない。全namespaceから共有するフラグと、
イベント・ミッション共通のメッセージも同じ画面で作成する。「ミッション」タブでは条件と
多言語本文を編集し、一覧のドラッグでゲーム内の表示順を変更できる。

保存時に `content/events/<namespace>.json`、`content/events/flags.json`、
`content/events/messages.json`、`content/events/missions.json` を検証し、成功した
場合だけ原子的に保存して、Git管理外の `app/events/events.json` と
`app/events/messages.json` を再生成する。キャラクター、アイテム、イベントメッセージ、BGM、
SE、宣言済みグローバルフラグは一覧から選択できる。JSONを手編集する場合も
`python3 -B scripts/validate-events.py` と `npm run events-build` が同じ検証処理を使用する。

## Battle Test

戦闘の状態・更新・描画は `app/scenes/battle.py` が所有する。`tools/screen_mocks/battle.py` は
本番Sceneへテスト用パーティ、敵編成、全アイテム1個ずつの所持状態を渡して単独実行する入口である。
本編に接続済みのメニュー画面には単独モックを置かず、ゲーム内の動線と `app/ui/` を直接対象にした
回帰テストで確認する。

```text
tools/screen_mocks/
├── _runtime.py             # 共通初期化、資産、入力設定
├── _runner.py              # 例外表示と終了コード
├── _fixtures.py            # 疑似パーティなどの戦闘fixture
├── battle.py               # 本番BattleSceneをfixtureで単独起動
└── battle_result.py        # 戦闘勝利リザルトの静的モック
```

Pyxel、共通アセット、パレット、Q終了入力は `_runtime.py`、想定内エラーの表示と
終了コードは `_runner.py` へ集約する。ゲームデータJSON自体は本編と同じ
`app.resources.load_record_array()` で読み、戦闘テスト固有の疑似パーティ構築だけを
`_fixtures.py` に置く。

確定済みのフィールド、メインメニュー、接続済み子画面はゲーム本体へ移行した。
起動方法と仕様は [`docs/features/field.md`](../docs/features/field.md) を参照する。

`background/bg_nector`、キャラクター、モンスター、ウィンドウなどの本番用リソースと
本編の `BattleScene` を使い、指定したパーティ状態と敵編成で戦闘を単独実行する。

```sh
npm run test-battle
```

パーティ構成、内部レベル、前後列、開始HP・MPは
`tools/screen_mocks/battle.py` の `BATTLE_TEST_PARTY` で指定する。開始HP・MPを `None` にすると
最大値で開始する。敵の種類は `BATTLE_TEST_MONSTER_KEYS` で指定し、前衛・後衛は本編と同じく
表示スロットから決まる。Sキーによる再開始でも同じ状態へ戻る。
全員が死亡すると「ぜんめつした...」を表示し、決定またはキャンセル入力後に同じ指定状態から
戦闘を再開始する。

起動直後はコマンドウィンドウが閉じている。`Z`または`Enter`を押すと中央から開き、開き切った後は矢印キーでコマンドカーソルを移動できる。もう一度`Z`または`Enter`を押すと現在位置のコマンドキーを取得してウィンドウを閉じる。`Q`または`Esc`で終了する。
起動前に呪文エフェクトのゲーム用データを再生成する。登録済み呪文または使用効果アイテムの
ターゲットを決定すると、対象側のOFFSET、フラッシュ、SEを使ってエフェクトを再生し、完了後に
次の手番へ進む。

## Battle Result Mock

戦闘勝利後のリザルト画面を、フィオラの内部レベル50を基準にした6人パーティで静的表示する。
レイアウトと表示内容の詳細は
[`docs/features/battle.md`](../docs/features/battle.md)を参照する。`Q`または`Esc`で終了する。

```sh
npm run mock-battle-result
```
