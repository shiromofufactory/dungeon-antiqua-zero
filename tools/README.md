# Dungeon Antiqua ZERO 開発用ツール

`tools/` には、Pyxelウィンドウを開いてデータやリソースを手動確認する開発用プログラムを置く。自動生成・同期・CI向けの処理は `scripts/`、配布するゲーム本体は `app/` が所有する。

開発用ツールは次の方針に従う。

- 画像、パレット、JSONなどを `tools/` へ複製しない。
- `app/data`、`app/images`、`app/assets.pyxpal` など本番用生成物をそのまま読む。
- リソース形式の解釈は `app/resources` の本番用loaderへ置き、ツール固有の状態と操作だけを `tools/` へ置く。
- ゲームのSceneやSaveDataをグローバルに変更せず、必要な対象を引数で明示する。
- カレントディレクトリへ依存させず、リポジトリルートから `python3 -m tools.<name>` で起動する。
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

## Window Viewer

`background/bg_nector` を256×240の画面背景として描き、その上に `app/assets.pyxres` の枠画像、設定済みパレット色のグラデーション、複数フォントでの自由なテキスト配置を表示する。

```sh
npm run tools:window-viewer
```

`Q`または`Esc`で終了する。PNGへ保存して終了する場合:

```sh
npm run tools:window-viewer -- --screenshot tmp/window-viewer.png
```
