# Dungeon Antiqua ZERO コンテンツ運用

## 目的

ゲームデータと企画文書を開発スタッフと安全に共有し、ゲーム本体、Google Sheets、スタッフ向け情報ポータルへ同じ内容を届けるための運用を定める。

## リポジトリの責務

### ゲーム本体リポジトリ（main）

- Pyxelゲーム本体とプログラム設計文書を管理する。
- `content` 自体を共有コンテンツリポジトリのGit submoduleとして固定する。
- `app/data` はsubmoduleから生成する実行時コピーとし、Git管理しない。
- `app/images` は `content/images` から生成する実行時画像データとし、Git管理しない。
- Google Sheetsやポータルへ直接接続しない。

### 共有コンテンツリポジトリ（sub）

- privateリポジトリ `shiromofufactory/dungeon-antiqua-zero-content` として独立した履歴を持つ。
- `data/*.json` と `docs/da0.md` の正本を管理する。
- ゲームとポータルで共有するPNG/GIF画像の正本を `images/` で管理する。
- JSONの検証、Google Sheetsとの同期、スタッフポータルの生成と配備を担当する。
- このリポジトリ単独でもスタッフが編集・レビューできる。

## 正本とデータの流れ

日常の共同編集では、レビュー済みの共有リポジトリをコード上の正本とする。Google Sheetsはユーザーが管理するマスター表であり、スタッフの変更はレビュー後に明示的に反映する。

```text
スタッフがJSONを編集
        ↓ commit / pull request / review
共有リポジトリ Sheets同期対象JSON（texts.jsonを除く）
        ├──→ put-data.mjs ──→ GAS ──→ Google Sheets
        ├──→ portal:build ──→ スタッフポータル
        └──→ mainのcontent:sync ──→ app/data ──→ Pyxelゲーム

Google Sheets ──→ GAS ──→ get-data.mjs ──→ Sheets同期対象JSON
                                            ↓
                                      diff確認・commit

共有リポジトリ texts.json（Sheets同期対象外）
        ├──→ portal:build ──→ スタッフポータル
        └──→ mainのcontent:sync ──→ app/data ──→ Pyxelゲーム
```

画像はGoogle Sheetsとは同期せず、次の経路で利用する。

```text
共有リポジトリ images/**/*.{png,gif}
        ├──→ portal:build ──→ dist/images ──→ スタッフポータル
        └──→ images:build ──→ app/images ──→ Pyxelゲーム
```

`get-data.mjs` と `put-data.mjs` の双方向性は意図したものである。ただし自動マージや常時同期は行わず、いずれの向きもGit差分を人が確認する。

## 初回セットアップ

ゲーム本体をcloneした後、mainリポジトリのルートで実行する。

```sh
npm run content:init
```

これはprivate submoduleを取得し、検証済みのJSONを `app/data` へ複製する。GitHubへのアクセス権が必要である。

## 日常の更新

共有コンテンツの確定版をゲームへ取り込む。

```sh
npm run content:update
```

このコマンドはsubmoduleの `master` を更新し、続けて `app/data` を再生成する。取り込んだsubmoduleのcommitポインタはmainリポジトリでレビューし、ゲーム実装と同じタイミングで記録する。

手元のsubmoduleにある内容だけを再反映する場合は次を使う。

```sh
npm run content:sync
npm run content:check
```

## 共有JSONの編集と検証

スタッフは共有コンテンツリポジトリを直接cloneするか、`content` 内で作業する。編集後はmainリポジトリのルートで次を実行する。

```sh
npm run content:validate
npm run portal:build
```

JSONは無関係な再整形を避け、変更理由が分かる単位でcommitする。`dist/` は生成物なのでGit管理しない。

## 共有画像の編集とゲーム用データ生成

`content/images` 以下のPNG/GIFを画像の正本とする。ゲーム用の `app/images` は直接編集せず、ルートから次を実行して生成する。

```sh
python3 -m pip install -r requirements-tools.txt
npm run images:build
```

`images:build` は生成前に `app/assets.pyxpal` を基準として全画像の色を検証し、成功した場合は1ピクセル1バイトのパレット番号を `app/images/graphics.bin` へ連結する。`app/images/manifest.json` には画像ID、寸法、バイナリ内のoffsetとlength、入力・パレット・bundleのSHA-256を記録する。画像IDは `content/images` からの拡張子なし相対パスで、例えば `background/bg_nector.png` は `background/bg_nector`、`characters/ch_battle.gif` は `characters/ch_battle` となる。

パレット番号1の `#FF0080` をプロジェクト全体の透過色として予約する。PNGの完全透明ピクセルはビルド時に色番号1へ変換する。GIFは論理背景色と完全透明ピクセルを色番号1へ変換する。不透明な `#FF0080` も色番号1として扱う。半透明ピクセルは使用せず、検出した場合は生成を失敗させる。ゲームで透過付き画像を描画するときは、Pyxelの `blt()` / `bltm()` に `colkey=1` を指定する。`#FF0080` とGIFの背景色を表示色として使用しない。

GIFは静止画だけを変換対象とする。アニメーションGIFはフレームのID、再生時間、disposalの実行時仕様が未定義なのでエラーとし、必要になった時点で専用manifestと変換方法を設計する。

パレット外色は、意図しない色変換を避けるため通常の生成を失敗させる。試作結果の確認に限り、次の明示的なオプションでパレット外色を最近傍色へ変換できる。このオプションで作ったデータは配布に使用しない。

```sh
npm run images:build:force
```

256×256を超える画像も入力できる。実行時にはmanifestから必要な矩形を読み、Scene開始時などに独立した `pyxel.Image` またはイメージバンクへ転送する。読み込みやバンク更新は `draw()` では行わない。フレーム分割とatlas生成は、具体的な画像仕様が決まった段階で同じビルド処理へ追加する。

## Google Sheetsとの同期

`texts.json`はGoogle Sheetsと同期せず、共有リポジトリ上のJSONだけを正本とする。`get-data`では既存の`texts.json`を保持したまま他データとの整合性を検証し、`put-data`では送信しない。

Google Sheetsから共有JSONへ取り込む場合:

```sh
npm run content:get-data
git -C content diff -- data
```

`content:get-data` は共有JSONの取得と検証に成功した後、`content:sync` を実行して
`app/data` も同じ内容へ更新する。取得または検証に失敗した場合は `app/data` を更新しない。

キャラクターシートの加入時装備は、順序依存の複数行セルではなく
`equip_right`、`equip_left`、`equip_head`、`equip_body`、`equip_arm` の5列で管理する。
空き部位は空文字とし、両手武器は `equip_right` に登録して `equip_left` を空にする。
二刀流では2本目の武器を `equip_left` に明示する。`skills` は引き続き複数行セルとして
JSON配列と相互変換する。

キャラクター固有の内部レベル補正は `lv_diff` 列で管理する。呪文データの習得レベルに
使用する `lv` とは意味が異なるため、キャラクターシートでは `lv` 列を使用しない。

武器・呪文適性は `eq_sword`、`eq_knife`、`eq_katana`、`eq_spear`、`eq_hammer`、
`eq_axe`、`eq_throwing`、`eq_rod`、`eq_wand`、`eq_shield`、`sp_mystic`、
`sp_sacred`、`sp_nether` の13列で管理する。値は0（使用不可）、1（通常）、
2（得意）の整数に限定し、現在レベルと熟練度は共有マスターではなくセーブ対象となる
Member状態で管理する。

アイテムのバトルステータス計算に使う `atk`、`hit`、`dfc`、`rst` は、すべて0以上の
整数として管理する。共有データの検証では欠損、文字列、負数をエラーとする。
`tolerance` は文字列とし、炎、冷、闇、眠、毒、麻、乱、黙、死、止をそれぞれ1種の
耐性として連結して記録する。`止` はスタン耐性であり、ゲームルールでは有効だが
ステータス画面には対応アイコンを表示しない。

共有JSONからGoogle Sheetsへ反映する場合は、まず送信内容だけを確認する。

```sh
npm run content:put-data:dry-run
npm run content:put-data
```

`put-data` は原則として、共有リポジトリの `master` がcleanであり、スタッフの変更をユーザーがレビュー済みのときだけ実行する。確認入力で正確に `YES` と入力するまで送信しない。CIやmainリポジトリの同期処理から自動実行しない。

## スタッフポータル

ポータルは `docs/da0.md`、`data/*.json`、`images/` から生成するWebサイトである。JSON由来の表と画像リファレンスはMarkdownへ手作業で転記せず、`docs/da0.md` 内の `portal:` マーカーへビルド時に挿入する。

キャラクター表では `face_x`、`face_y` の座標値を列として表示せず、表の左端に
`images/faces/faces_pc.png` から該当する32×32pxの顔を切り出して表示する。
概要表と熟練度・適性表はいずれも同じ顔座標を使用する。

```sh
npm run portal:build
```

出力は `dist/` に作られ、CSS、文書画像、ゲーム画像はそれぞれ `dist/assets`、`dist/pics`、`dist/images` として配信する。単体HTMLは生成しない。ローカル確認は `npm run portal:serve` を使い、`http://localhost:8000/`を開く。このコマンドは配信前にポータルを再生成する。`npm run portal:preview`も同じ処理の別名である。

Cloud Runへの配備はGitHub Actionsの `deploy-portal.yml` が担当し、Google認証にはCloud Run IAPを用いる。GCPプロジェクト、リージョン、Workload Identity Federation、閲覧許可ユーザーはリポジトリ設定で管理し、ソースへ埋め込まない。

## 禁止事項

- `app/data` を直接編集して正本に戻そうとしない。
- `app/images` を直接編集して正本に戻そうとしない。
- JSON変更を検証せずにGoogle Sheetsへ送信しない。
- `get-data` と `put-data` を同じ自動ジョブで連続実行しない。
- 認証情報、GCPサービスアカウントキー、スタッフのメールアドレスをGitへcommitしない。
- 共有リポジトリの確定前にmainのsubmoduleポインタだけを先行更新しない。
