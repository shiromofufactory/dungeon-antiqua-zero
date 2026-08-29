# Dungeon Antiqua ZERO 開発用ツール

`tools/` には、Pyxelウィンドウを開いてデータやリソースを手動確認する開発用プログラムを置く。自動生成・同期・CI向けの処理は `scripts/`、配布するゲーム本体は `app/` が所有する。

開発用ツールは次の方針に従う。

- 画像、パレット、JSONなどを `tools/` へ複製しない。
- `app/data`、`app/images`、`app/assets.pyxpal` など本番用生成物をそのまま読む。
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

## Screen Mocks

画面モックは `tools/screen_mocks/` に画面・機能単位で置く。各モックは独立したComposition Rootとし、戦闘、メニュー、ショップなどの仮レイアウトや演出を相互に混在させない。

```text
tools/screen_mocks/
├── battle.py               # 戦闘画面モック
├── status.py               # ステータス画面モック
├── menu.py                 # メニュー画面モック
└── shop.py                 # ショップ画面モック（追加時）
```

複数の画面モックで実際に同じ初期化や操作が必要になった場合だけ、`tools/screen_mocks/` 内の小さな共通モジュールへ抽出する。すべてのモックを管理する巨大な共通Appは作らない。

### Battle Screen Mock

`background/bg_nector`、キャラクター、モンスター、ウィンドウなどの本番用リソースを使って戦闘画面の仮レイアウトを表示する。

```sh
npm run tools:screen-mock:battle
```

起動直後はコマンドウィンドウが閉じている。`Z`または`Enter`を押すと中央から開き、開き切った後は矢印キーでコマンドカーソルを移動できる。もう一度`Z`または`Enter`を押すと現在位置のコマンドキーを取得してウィンドウを閉じる。`Q`または`Esc`で終了する。

### Status Screen Mock

戦闘画面モックを雛形として用意したステータス画面モック。レイアウト内容は `tools/screen_mocks/status.py` で書き換える。

```sh
npm run tools:screen-mock:status
```

`Z`、`Enter`、またはゲームパッドAを押すたびに、名前・種族・性別の表示言語が日本語、英語、簡体字中国語の順で切り替わる。`Q`または`Esc`で終了する。

### Menu Screen Mock

ステータス画面モックと同じ全画面の枠だけを表示するメニュー画面モック。レイアウト内容は `tools/screen_mocks/menu.py` へ追加する。

```sh
npm run tools:screen-mock:menu
```
