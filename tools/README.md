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
別マップを作る場合は、マップID、タイルセット、profileを指定する。

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
npm run tools:event-editor
```

ヘッダーから既存のnamespaceを切り替え、新しいnamespaceを入力してイベントファイルを新規作成
できる。namespaceはマップIDと1対1で対応する必要はない。全namespaceから共有するフラグと、
イベント専用メッセージも同じ画面で作成する。

保存時に `content/events/<namespace>.json`、`content/events/flags.json`、
`content/events/messages.json` を検証し、成功した
場合だけ原子的に保存して、Git管理外の `app/events/events.json` と
`app/events/messages.json` を再生成する。キャラクター、アイテム、イベントメッセージ、BGM、
SE、宣言済みグローバルフラグは一覧から選択できる。JSONを手編集する場合も
`npm run events:validate` と `npm run events:build` が同じ検証処理を使用する。

## Screen Mocks

画面モックの起動処理と疑似状態は `tools/screen_mocks/` に置く。仕様が確定して本編でも使う画面は `app/ui/` のOverlay／表示部品とし、モックから同じ実装へ疑似状態を渡す。

```text
tools/screen_mocks/
├── _runtime.py             # 共通初期化、資産、入力設定
├── _runner.py              # 例外表示と終了コード
├── _fixtures.py            # 疑似パーティなどの共有fixture
├── battle.py               # 戦闘画面モック
├── status.py               # 本番Overlayへ疑似状態を渡す互換アダプター
├── spell.py                # 本番Overlayへ疑似状態を渡す互換アダプター
├── item.py                 # 本番Overlayへ疑似状態を渡す互換アダプター
├── equipment.py            # 本番Overlayへ疑似状態を渡す互換アダプター
└── shop.py                 # 本番ショップOverlayの互換アダプター
```

Pyxel、共通アセット、パレット、Q終了入力は `_runtime.py`、想定内エラーの表示と
終了コードは `_runner.py` へ集約する。ゲームデータJSON自体は本編と同じ
`app.resources.load_record_array()` で読み、モック固有の疑似パーティ構築だけを
`_fixtures.py` に置く。Settings、SaveData、画面固有画像は起点となるComposition Rootが所有し、
`app/ui/item_menu.py`、`equipment_menu.py`、`status_menu.py`、`spell_menu.py`、`shop.py` へ
必要なものだけを明示的に渡す。すべてのモックを管理する巨大な共通Appは作らない。

確定済みのフィールド、メインメニュー、接続済み子画面はゲーム本体へ移行した。
起動方法と仕様は [`docs/features/field.md`](../docs/features/field.md) を参照する。

### Battle Screen Mock

`background/bg_nector`、キャラクター、モンスター、ウィンドウなどの本番用リソースを使って戦闘画面の仮レイアウトを表示する。

```sh
npm run tools:screen-mock:battle
```

起動直後はコマンドウィンドウが閉じている。`Z`または`Enter`を押すと中央から開き、開き切った後は矢印キーでコマンドカーソルを移動できる。もう一度`Z`または`Enter`を押すと現在位置のコマンドキーを取得してウィンドウを閉じる。`Q`または`Esc`で終了する。
