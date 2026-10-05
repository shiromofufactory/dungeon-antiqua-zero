# AGENTS.md

## 適用範囲

このファイルの指示は、リポジトリ全体に適用する。下位ディレクトリに追加の `AGENTS.md` がある場合は、より具体的な下位の指示を優先する。

## プロジェクト概要

このリポジトリは、Pyxel製RPG「Dungeon Antiqua ZERO」の開発プロジェクトである。過去作Dungeon Antiqua 1・2と世界観およびゲームシステム上のつながりを持つ一方、ZERO固有のフリーシナリオ、戦闘回数に応じた世界変化、魔力減衰、種族・武器・呪文ごとの成長を実装する予定である。

現在は設計・データ準備を進めている段階である。`content/data` にはキャラクター、アイテム、モンスター、店、スキル、呪文の正本となるJSONがあり、`app/data` はそこから生成する実行時コピーである。`app/fonts` には使用予定のフォントがある。既存データはユーザーの制作物として扱い、依頼に関係のない修正や再整形をしない。

## 基本文書

- `content/docs/da0.md`: ゲーム内容、世界設定、シナリオ、主要なゲームルールのベースドキュメント。イラスト・PVを含む制作スタッフとの共有を兼ねるため、座標、Window寸法、文言キーなど実装向けの詳細は置かない。
- `docs/features/README.md`: 機能仕様書の責務、記載基準、機能一覧。
- `docs/features/*.md`: 機能ごとの詳細な操作、UI、状態遷移、境界値、受け入れ条件。対象機能の文書がある場合は実装前に参照する。
- `docs/program-architecture.md`: ZEROのプログラム構造、責務分割、状態管理、Scene、Overlay、イベント構造の設計基準。実装・リファクタリングでは必ず参照する。
- `docs/content-workflow.md`: 共有コンテンツ、Google Sheets、ゲーム用データ、スタッフポータルの責務と同期手順。

文書に矛盾がある場合は、ゲーム内容と体験の方向性は `content/docs/da0.md`、機能の詳細な振る舞いとUIは `docs/features/*.md`、ソフトウェア構造は `docs/program-architecture.md`、コンテンツ運用は `docs/content-workflow.md` を基準とする。表示文言の正本は `content/data/texts.json`、マスターデータの正本は対応する `content/data/*.json` とする。ユーザーの最新の明示指示は常に文書より優先する。

## 現在の主要ディレクトリ

- `app/`: ゲーム本体、生成済みゲームデータ、フォントを置く。旧名は `packages/`。
- `app/data/`: 実行時に利用する生成済みJSON。Git管理対象外で、直接編集しない。
- `app/fonts/`: Pyxelで利用するフォント。
- `content/`: スタッフ共有コンテンツのprivate Git submodule。JSON、企画文書、ポータル生成・Sheets同期処理を所有する。
- `docs/`: ゲーム本体の機能仕様、プログラム設計、運用文書。
- `scripts/`: submoduleからゲーム用JSONを生成するローカル同期スクリプト。
- `tmp/`: 一時資料。正式な仕様の根拠にする前に `docs/` の内容と照合する。

`packages/` から `app/` への改名はユーザーが行った変更である。削除と新規追加に見えるGit差分を勝手に戻さない。

## リファレンスプロジェクト

同じ親ディレクトリに過去作がある。

### Dungeon Antiqua 1

- パス: `../dungeon-antiqua`
- 主な実装: `../dungeon-antiqua/app`
- 特徴: `main.py` に主要なゲーム進行を集中させた構造。
- 参照用途: 初代のゲームルール、画面、データ、演出、プラットフォーム対応、ビルド方法の確認。
- 注意点: 巨大な `App.update()` をZEROへそのまま移植しない。

### Dungeon Antiqua 2

- パス: `../dungeon-antiqua2`
- 主な実装: `../dungeon-antiqua2/app`
- 特徴: `main.py`、`update.py`、`draw.py` に分割。`Field` と `Battle` は自身の更新・描画を持つ。
- 参照用途: 改良された戦闘・フィールド処理、データ形式、UI、サウンド、モバイル対応、ビルド方法の確認。
- 注意点: `main.py` と `update.py` は共有するApp状態が多く密結合である。ゲーム全体の `update.py`、巨大な `win_main()`、イベントIDを横断する巨大な条件分岐をZEROへ移植しない。

リファレンスプロジェクトは原則として読み取り専用で扱う。ユーザーが明示的に依頼しない限り、過去作のファイルを変更しない。コードを参考にするときはコピー元を確認し、ZEROの設計とデータ仕様に合わせて再配置する。

## アーキテクチャ原則

- Pyxelの `update` / `draw` は実行時コールバックであり、ファイル分割の軸にしない。
- `main.py` は初期化、リソース読込、`Game` の生成、`px.run` への接続に限定する。
- タイトル、フィールド、街、戦闘などをSceneとして分け、各Sceneの `update()` と `draw()` は同じ機能内に置く。
- メニュー、メッセージ、選択肢、確認画面はOverlayとして扱い、入力は最上位のOverlayへ渡す。
- Scene遷移はTransitionとして明示し、文字列を各所から直接代入しない。
- Settings、SaveData、Scene固有の一時状態を分ける。
- Scene固有のタイマー、カーソル、演出状態をGame全体へ集めない。
- Domain ModelやSystemからGame、Scene、Windowへ逆参照しない。
- `Window.app` や巨大な汎用Contextをサービスロケータとして使わない。
- `draw()` は原則として状態を変更しない。タイマーや遷移は `update()` で進める。
- 通常イベントはデータとEventRunnerで表し、特殊イベントだけを個別のPythonハンドラーにする。
- 戦闘回数、敵強化、設備停止、魔力減衰はWorldProgression相当のSystemへ集約する。
- 共有されるという理由だけで処理を `util.py` へ移さず、対象となる状態の所有者へ置く。
- 行数だけを理由に細分化しない。異なる変更理由が混在したときに分割する。
- ZEROに必要性が確認される前に、ECS、汎用イベントバス、大規模なDIフレームワークを導入しない。

## データの扱い

`content/data/*.json` は配列形式のゲームデータの正本である。`app/data/*.json` は `npm run sync` で生成し、直接編集しない。識別に使用する英名・キーと表示文字列を区別し、既存キーを安易に変更しない。キー変更が必要な場合は、参照箇所、Google Sheets、セーブ互換性への影響を確認する。

データを変更するときは次を守る。

- ファイル全体の無関係な再整形を避ける。
- 数値と文字列を意図せず相互変換しない。
- 多言語用フィールドの配列構造を維持する。
- 既存レコードの並び順に意味がないと断定しない。
- ゲーム実装側で表示名を識別子として使わない。
- セーブデータに識別子を保存する場合は、将来も安定するキーを使う。

`content/scripts/get-data.mjs` と `content/scripts/put-data.mjs` はGAS経由でGoogle Sheetsと同期する。`get-data.mjs` は共有JSONを上書きし、`put-data.mjs` はGoogle Sheetsを変更するため、ユーザーが外部同期を明示的に依頼しない限り実行しない。検証目的ではルートから `npm run content:put-data:dry-run` のみ実行してよい。

スタッフは共有リポジトリのJSONを変更し、レビュー後にユーザーが `put-data.mjs` でGoogle Sheetsへ反映する。Google Sheetsから取り込む場合も、`get-data.mjs` 実行前に共有リポジトリがcleanであることを確認し、生成差分をレビューする。詳細は `docs/content-workflow.md` に従う。

## 実装時の進め方

新機能を実装する前に、次を確認する。

1. `content/docs/da0.md` で対応するゲーム内容と体験の方向性を確認する。
2. 対応する `docs/features/*.md` があれば、詳細な振る舞い、UI、受け入れ条件を確認する。
3. `docs/program-architecture.md` で状態の所有者と配置先を決める。
4. 過去作に類似処理があれば、両方を必要な範囲だけ調査する。
5. ZEROの仕様と構造に合わせて最小の縦方向の機能として実装する。
6. ゲームルール、保存、イベント、Scene遷移をリスクに応じて検証する。

過去作の関数名やクラス構造をそのまま正解とみなさない。特に `App` 全体を引数に渡す外部関数、Window名を横断するディスパッチ、Scene文字列への直接代入は、新しい所有者へ置き換える。

## 検証方針

- JSON変更時は少なくとも全対象ファイルをパースする。
- 共有JSON変更時は `npm run content:validate` と `npm run sync` を実行する。
- ゲーム用JSONが正本と一致するかは `node scripts/sync-content.mjs --check` で確認する。
  この検証コマンドは `package.json` のnpm scriptsへ復元しない。
- ポータルに関係する変更は `npm run portal:build` を実行し、生成ページを目視確認する。
- ゲームルールは可能な範囲でPyxel非依存のテストを用意する。
- オートバトルの判断・予測・Scene接続は `python3 -B -m unittest tests.test_auto_battle` で回帰検証する。
- 戦闘設定とコマンド記憶は `python3 -B -m unittest tests.test_battle_preferences tests.test_state tests.test_settings_system tests.test_game` で設定互換性・即時保存・復元を回帰検証する。
- セーブ形式と戦闘コマンド記憶の永続化は `python3 -B -m unittest tests.test_save_system tests.test_battle_preferences tests.test_game` でスロット保存・ロード・旧形式互換を回帰検証する。
- ミッションの検証・条件判定・情報メニュー表示は `python3 -B -m unittest tests.test_missions tests.test_information_menu tests.test_event_editor_server tests.test_editor_server`、エディタ操作は `node --test tests/test_mission_editor.mjs` で回帰検証する。
- セーブ形式を変更した場合は保存・復元と旧データ移行を検証する。
- 強制割り込みゲームメニューは `python3 -B -m unittest tests.test_game_menu tests.test_input tests.test_audio_resources` で停止・復帰・BGM保持を回帰検証する。
- SceneやOverlayを変更した場合は、遷移元・遷移先・キャンセル復帰を確認する。
- フィールド待機時の操作ナビは `python3 -B -m unittest tests.test_field_menu_guide` で待機時間・入力種別・表示抑止を回帰検証する。
- フロア別のエンカウント有無・編成・設定保存は `python3 -B -m unittest tests.test_encounter tests.test_game tests.test_map_source tests.test_map_resources tests.test_map_editor_server tests.test_debug_menu`、エディタの設定切替・値保持・Undoは `node --test tests/test_map_editor_encounters.mjs` で回帰検証する。
- Pyxel描画に関わる変更は、起動確認に加えて該当画面を目視確認する。
- マップエディタのオブジェクト操作は `node --test tests/test_map_editor_objects.mjs`、制作用マップの検証・生成は `python3 -B -m unittest tests.test_map_source` で回帰検証する。
- マップエディタの地面外周保護・矩形塗り・Undoは `node --test tests/test_map_editor_grounds.mjs` で回帰検証する。
- マップチップ・マップ・イベント間およびマップ・タイルセット選択時の未保存変更の確認と切替、各エディタのブラウザ標準右クリックメニュー抑止は `node --test tests/test_editor_navigation.mjs` で回帰検証する。
- マップチップエディタのオブジェクト一覧・レイヤー絞り込み・新規作成・並び替えは `node --test tests/test_mapchip_objects.mjs` で回帰検証する。
- ビルドや配布物の生成は、ユーザーが依頼した範囲でのみ行う。

ゲーム本体のテスト基盤はまだ確定していない。上記コンテンツ用コマンド以外について、存在しない標準コマンドを仮定しない。実装が追加されたら、このファイルまたは下位の `AGENTS.md` に正式なコマンドを追記する。

## Gitと既存変更

- 作業開始時と終了時に `git status --short` を確認する。
- ユーザーの未コミット変更を保持し、無関係なファイルを変更しない。
- `packages/` から `app/` への移動を巻き戻さない。
- `tmp/`、過去作リポジトリを勝手に整理・削除しない。
- 明示的な依頼がない限り、コミット、push、外部同期、配布を行わない。
- 破壊的なGit操作や広範囲な自動整形を行わない。

## 文書化

プロジェクト固有の設計判断は日本語で `docs/` に記録する。コードと文書が食い違う変更では、同じ作業内で該当文書も更新する。

画面座標、Window寸法、表示件数、カーソル挙動、文言キー、モック固有動線などの詳細は `docs/features/` に置き、`content/docs/da0.md` へ追記しない。`da0.md` には、制作スタッフがゲーム内容や演出意図を理解するために必要な概要と主要ルールだけを残す。実際の表示文言は機能仕様書へ複製せず、`content/data/texts.json` のキーを参照する。`program-architecture.md` と `tools/README.md` にも機能仕様を重複させず、責務や操作入口から該当する機能仕様書へリンクする。

新しい正式文書を追加した場合は、このファイルの「基本文書」または関連文書から参照できるようにする。`tmp/` の資料だけを正式仕様の根拠にしない。
