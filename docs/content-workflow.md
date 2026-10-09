# Dungeon Antiqua ZERO コンテンツ運用

## 目的

ゲームデータと企画文書を開発スタッフと安全に共有し、ゲーム本体、Google Sheets、スタッフ向け情報ポータルへ同じ内容を届けるための運用を定める。

## リポジトリの責務

### ゲーム本体リポジトリ（main）

- Pyxelゲーム本体、機能ごとの詳細仕様、プログラム設計文書を管理する。
- `content` 自体を共有コンテンツリポジトリのGit submoduleとして固定する。
- `app/data` はsubmoduleから生成する実行時コピーとし、Git管理しない。
- `app/images` は `content/images` から生成する実行時画像データとし、Git管理しない。
- `app/maps` は `content/maps` から生成する実行時マップデータとし、Git管理しない。
- `app/events` は `content/events` から生成する実行時イベントデータとし、Git管理しない。
- Google Sheetsやポータルへ直接接続しない。

### 共有コンテンツリポジトリ（sub）

- privateリポジトリ `shiromofufactory/dungeon-antiqua-zero-content` として独立した履歴を持つ。
- `data/*.json` と、制作スタッフ向けの企画文書 `docs/da0.md` の正本を管理する。
- ゲームとポータルで共有するPNG/GIF画像の正本を `images/` で管理する。
- 呪文エフェクトの制作設定をSheets同期外の `effects/` で管理する。
- タイルセットメタデータと制作用マップの正本を `maps/` で管理する。
- 通常イベント、グローバルフラグ宣言、ミッション、イベント・ミッション共通メッセージの正本を `events/` で管理する。
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
        └──→ mainのsync ──→ app/data ──→ Pyxelゲーム

Google Sheets ──→ GAS ──→ get-data.mjs ──→ Sheets同期対象JSON
                                            ↓
                                      diff確認・commit

共有リポジトリ texts.json（Sheets同期対象外）
        ├──→ portal:build ──→ スタッフポータル
        └──→ mainのsync ──→ app/data ──→ Pyxelゲーム
```

画像はGoogle Sheetsとは同期せず、次の経路で利用する。

```text
共有リポジトリ images/**/*.{png,gif}
        ├──→ portal:build ──→ dist/images ──→ スタッフポータル
        └──→ images:build ──→ app/images ──→ Pyxelゲーム
```

呪文エフェクト設定もGoogle Sheetsとは同期せず、次の経路で利用する。

```text
共有リポジトリ effects/spells.json
        └──→ spell effect compiler ──→ app/effects/spells.json ──→ Pyxelゲーム

共有リポジトリ battle/attack_poses.json
        └──→ attack pose compiler ──→ app/effects/attack_poses.json ──→ Pyxelゲーム
```

マップの空間データはGoogle Sheetsと同期せず、次の経路で利用する。

```text
共有リポジトリ maps/tilesets + maps/sources
        └──→ map compiler ──→ app/maps ──→ Pyxelゲーム
```

イベント定義もGoogle Sheetsとは同期せず、次の経路で利用する。

```text
共有リポジトリ events/*.json
        └──→ event compiler ──→ app/events/events.json ──→ Pyxelゲーム
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
npm run sync
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

## 呪文エフェクト制作データとゲーム用データ生成

`content/effects/spells.json`は呪文エフェクト設定ツールが編集する正本とし、
Google Sheetsとの同期対象にしない。呪文の表示名、効果、対象範囲は従来どおり
`content/data/spells.json`が所有し、描画画像、位置、フラッシュ色、SEの設定を混在させない。

ゲーム用の`app/effects/spells.json`は、正本の保存時または非対話ビルド時に、呪文キー、
画像範囲、パレット番号、SE IDを検証して生成する。ゲーム本体は`content/effects`を直接読まず、
生成済みデータだけを読む。保存形式とツール操作は
[`features/spell-effect-editor.md`](./features/spell-effect-editor.md)を参照する。

呪文エフェクト設定ツールでPyxel Soundまたは`app/se`のWAVへ安定IDを付けた場合は、
ゲーム本体が直接読む`app/audio/catalog.json`へ追加する。Sound本体は`assets.pyxres`、
SE用WAVは`app/se`で管理し、ツールは音源自体を変更しない。定義形式は
[`features/sound-effects.md`](./features/sound-effects.md)を参照する。

攻撃ポーズは `content/battle/attack_poses.json` を正本とし、エディタ保存時、`npm start` 時、
または `npm run attack-poses:build` で `app/effects/attack_poses.json` を生成する。
アイテムの `weapon_img` と枝番1・2を通常攻撃の
振り上げ・振り下ろしへ対応させる。ゲームと単独戦闘テストは生成済みデータだけを読み、制作JSONを
直接参照しない。

## マップ制作データとゲーム用データ生成

`content/maps/tilesets` はマップチップメタデータ設定ツール、`content/maps/sources` は
マップエディタが編集する正本とする。どちらもGoogle Sheets同期の対象にせず、空間構造を
維持したJSONとしてGitでレビューする。地面、境界、表示候補、オブジェクト、通行設定の仕様は
[`features/map-chip-metadata-tool.md`](./features/map-chip-metadata-tool.md) を参照する。

ゲーム用の `app/maps` は、マップ保存時に同じ検証・コンパイル処理から生成する。境界選択、
重み付き表示候補、地面合成、オブジェクト展開、通行グリッドを事前解決した生成物であり、
直接編集またはGit管理しない。保存済みの全制作用マップを非対話で再生成する場合は
`npm run maps:build` を実行する。

タイルセットメタデータだけを非対話で検証する場合は次を実行する。画像のパレット不一致は
警告として表示され、メタデータの構造エラーがある場合だけ終了コードを失敗にする。

```sh
npm run maps:validate
npm run maps:build
```

## イベント制作データとゲーム用データ生成

`content/events/<namespace>.json` はイベントエディタまたは人が編集する通常イベントの正本、
`content/events/flags.json` は全イベントから共有するグローバルフラグ宣言の正本、
`content/events/messages.json` はイベント専用の多言語メッセージの正本とする。
イベントメッセージの任意の顔グラフィック指定も同じレコードが所有し、イベントコマンドには
`message_id` だけを保存する。
いずれもGoogle Sheetsとは同期しない。形式と編集操作は
[`features/events.md`](./features/events.md) を参照する。

ゲーム用の `app/events/events.json` は全イベントを完全IDで索引化し、
`app/events/messages.json` は制作メモを除いた会話文を収録する生成物である。どちらも直接編集
またはGit管理しない。次のコマンドで非対話の検証と生成を行う。

```sh
npm run events:validate
npm run events:build
```

イベント、宣言済みグローバルフラグ、マスターデータ、イベントメッセージ、音声、マップトリガー、actorの
参照を横断して検証する。通常UI用の `content/data/texts.json` はイベントmessageコマンドから
参照しない。`content:validate` にも同じイベント検証を含め、エラー時は既存のゲーム用生成物を
更新しない。

## Google Sheetsとの同期

`texts.json`はGoogle Sheetsと同期せず、共有リポジトリ上のJSONだけを正本とする。`get-data`では既存の`texts.json`を保持したまま他データとの整合性を検証し、`put-data`では送信しない。

Google Sheetsから共有JSONへ取り込む場合:

```sh
npm run content:get-data
git -C content diff -- data
```

`content:get-data` は共有JSONの取得と検証に成功した後、`sync` を実行して
`app/data` も同じ内容へ更新する。取得または検証に失敗した場合は `app/data` を更新しない。

キャラクターシートの加入時装備は、順序依存の複数行セルではなく
`equip_right`、`equip_left`、`equip_head`、`equip_body`、`equip_arm` の5列で管理する。
空き部位は空文字とし、両手武器は `equip_right` に登録して `equip_left` を空にする。
二刀流では2本目の武器を `equip_left` に明示する。`skills` は引き続き複数行セルとして
JSON配列と相互変換する。

キャラクター固有の内部レベル補正は `lv_diff` 列で管理する。呪文データの習得レベルに
使用する `lv` とは意味が異なるため、キャラクターシートでは `lv` 列を使用しない。

呪文データの `type` は文字列enumで管理し、元素呪文は `mystic`、神聖呪文は
`sacred`、暗黒呪文は `nether`、アイテム効果は `item` とする。旧形式の数値
`1`、`2`、`3`、`0` は使用しない。

武器・呪文適性は `eq_sword`、`eq_knife`、`eq_katana`、`eq_spear`、`eq_hammer`、
`eq_axe`、`eq_throwing`、`eq_rod`、`eq_wand`、`eq_shield`、`sp_mystic`、
`sp_sacred`、`sp_nether` の13列で管理する。値は0（使用不可）、1（通常）、
2（得意）の整数に限定し、現在レベルと熟練度は共有マスターではなくセーブ対象となる
Member状態で管理する。

アイテムのバトルステータス計算に使う `atk`、`hit`、`dfc`、`rst` は、すべて0以上の
整数として管理する。共有データの検証では欠損、文字列、負数をエラーとする。
攻撃属性の `attr` は空文字、炎、冷、闇、追加効果の `extra` は空文字、眠、乱、死、黙、
吸、止、毒、麻、破のいずれかとする。`止` はスタン、`破` は防御低下を表す。
種族特効の `race` は空文字、`ANIMAL`、`UNDEAD`、`GOBLIN`、`HUMAN`、`MAGE`、
`GIANT`、`DRAGON`、`ANIMATED`、`DEMON` のいずれかとし、`DEAMON` は使用しない。
`tolerance` は文字列とし、炎、冷、闇、眠、毒、麻、乱、黙、死、止をそれぞれ1種の
耐性として連結して記録する。`止` はスタン耐性であり、ゲームルールでは有効だが
ステータス画面には対応アイコンを表示しない。
アイテムの `use` は空文字または `spells.json` の既存 `name_en` キー、`break` は0か1、
`price` は0以上の整数、`source` は文字列とする。呪文を発動する本は `type1=ITEM`、
`type2=BOOK` とし、通常の消耗品の `type2=ITEM` と区別する。価格と入手元は店画面だけが
使用する表示データである。
`special` は空文字または `ATK_REDUCE_WT`、`COUNTER_STUN`、`DUAL_WIELD`、
`GAIN_TWICE`、`LURE`、`POWER_HIT`、`REFLECT`、`SPL_REDUCE_WT`、
`TWO_HANDED`、`VIGILANCE` のいずれかとする。各値には
`item.detail.special.<special>` の表示キーを必ず用意する。

モンスターの最大MP `mmp`、物理戦闘に使う `attack`、`hit`、`defense`、`evasion`、
行動順に使う `agi`、思考の知恵 `int` は、すべて0以上の整数として管理する。共有データの
検証では欠損、文字列、負数をエラーとする。回避率は `agi` から導出せず、`evasion` の値を
直接使用する。
モンスターの `special` は改行を含まない文字列とし、日本語1文字を1種類の特殊行動キーとして
区切りなしで連結する。`extra` はアイテムと同じ許容値を使う。`spells` は空文字、または
`spells.json` の既存 `name_en` キーを改行で区切った文字列とし、空行を含めない。
モンスターの `treasure_item` は `items.json` に存在する空でない `name_en` キー、
`treasure_rate` は0から16の整数とする。ドロップ確率は `treasure_rate / 16` で表す。

`texts.json` の各言語フィールドは1行の文字列または複数行の文字列配列を使用する。
意味上1つの文言は表示行数によらず1つの `text_key` にまとめ、配列の各要素を1表示行とする。
ゲーム側は文字数や表示幅による自動改行を行わず、データで指定された行境界を維持する。
改行が必要な文言は、正本データ側で文字列配列の要素を分けて明示する。
属性、状態、種族など複数画面で共有する用語は `term.*` に置く。同じ文型で用語だけが
変わる文言は完成文を列挙せず、文型側の `$ITEM$`、`$ATTRIBUTE$` など意味を表す
名前付きプレースホルダへ共通用語を代入する。プレースホルダ名は
`UPPER_SNAKE_CASE` とし、`%FIRE%` などの表示・アイコンタグとは区別する。
`text_ja` は空でない文字列、または少なくとも1つの空でない行を含む文字列配列を必須とする。
文言の入力待ちとしてキーだけを先に予約する場合は `pending: true` を付けることで、
各言語を空文字にできる。文言を入力した時点で `pending` を削除する。
DA2準拠の画面語彙について、
DA2の辞書に対応訳が見つからない場合は実装者が英語・簡体字中国語を新たに翻訳せず、
`text_en`、`text_zhcn` を空文字で登録する。両フィールドは文字列または文字列配列を
必須とするが、空文字を許可する。複数行の対応訳がある場合は文字列配列を使用できる。
表示時の代替言語はゲーム本体の `Localizer` が決定する。
表示文中の `%COL_BLUE%` は文字色を青（Pyxel色13）へ変更し、`%COL_END%` は
白（Pyxel色5）へ戻す。青の色番号は `app/ui/colors.py` の `BLUE_TEXT_COLOR` で
一元管理し、両タグは表示幅を持たない。

共有JSONからGoogle Sheetsへ反映する場合は、まず送信内容だけを確認する。

```sh
npm run content:put-data:dry-run
npm run content:put-data
```

`put-data` は原則として、共有リポジトリの `master` がcleanであり、スタッフの変更をユーザーがレビュー済みのときだけ実行する。確認入力で正確に `YES` と入力するまで送信しない。CIやmainリポジトリの同期処理から自動実行しない。

## スタッフポータル

ポータルはイラスト、PVなどを含む制作スタッフとの情報共有を目的とし、`docs/da0.md`、
`data/*.json`、`images/` から生成する。ゲーム本体側の `docs/features/` に置く画面座標、Window寸法、
カーソル挙動、文言キーなどの実装向け詳細仕様はポータルへ掲載しない。

`docs/da0.md` には世界観、シナリオ、ゲーム体験、主要なゲームルールを記載する。機能単位の
詳細仕様を同じファイルへ埋め込んだり、ポータル生成時だけ非表示にしたりせず、ゲーム本体側の
`docs/features/` へ物理的に分離する。実際の表示文言は `data/texts.json` を正本とする。

JSON由来の表と画像リファレンスはMarkdownへ手作業で転記せず、`docs/da0.md` 内の
`portal:` マーカーへビルド時に挿入する。

キャラクター表では `face_x`、`face_y` の座標値を列として表示せず、表の左端に
`images/faces/faces.png` から該当する32×32pxの顔を切り出して表示する。
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
