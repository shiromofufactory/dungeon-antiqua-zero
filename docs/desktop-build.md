# デスクトップ配布物のビルド

## Mac版

リポジトリルートの `build.sh` をmacOS上で実行する。DA2の `build.sh` と同じく
`pyxel package` → `pyxel app2exe` → アイコン差し替え → 署名 → ZIP化を行う。
Windows版の受け取りは後述の `npm run receive:win` で行う。

```sh
./build.sh                       # 通常版
./build.sh --mode exhibition     # 試遊版
./build.sh --mode demo           # 体験版
./build.sh --mode beta           # βテスト版
```

`npm run build:mac`、`npm run build:mac:exhibition`、`npm run build:mac:demo`、
`npm run build:mac:beta` も同じ入口を呼ぶ。`npm run build:mac -- --mode demo` の指定も可能。
スクリプトは別のカレントディレクトリから絶対パスで実行できる。

### 必要な環境とリソース

- Python 3.11以上、Pyxel、PyInstaller。PyxelとPyInstallerは同じPython環境へ入れ、
  `pyxel` と `pyinstaller` の両コマンドをPATHへ通す。
- Node.js 20以上。共有JSONの検証と同期状態の確認に使用する。
- macOSの `codesign`、`ditto`。
- 初期化済みの `content` submoduleと、生成済みのゲーム用リソース。
- `icons/icon.icns` があれば、Macアプリのアイコンへ使用する。

例として、ビルド用のPython環境を用意する場合は次を実行する。

```sh
python3 -m venv .venv-build
source .venv-build/bin/activate
python -m pip install pyxel pyinstaller -r requirements-tools.txt
```

ビルドはDA2と同様に現在の `app/` をパッケージ化する。ビルド時に正本や生成済みリソースを
書き換えない。制作データを変更した場合は、先に該当するリソースを生成する。

```sh
npm run sync
python3 -B scripts/build-images.py
npm run map-build
npm run events-build
npm run spell-effects:build
npm run attack-poses:build
```

画像生成は配布用の厳密なパレット検証を使用する。色の不一致を許す試作生成は
[`content-workflow.md`](./content-workflow.md#共有画像の編集とゲーム用データ生成) の運用に従う。
BGMを変更した場合は、WAVとffmpeg・ffprobeを用意して `npm run audio:build` も実行する。
変換元のBGM WAVは配布物へ含めない。

ビルド開始前に `node scripts/sync-content.mjs --check` で共有JSONと `app/data` の一致を確認し、
主要な実行時リソースの存在も確認する。不一致や未生成の場合は終了する。
画像、マップ、イベント、エフェクト、音声の更新有無はこのスクリプトでは判定しない。

### モードと出力

| モード | 出力先 | ファイル名の基部 |
|---|---|---|
| `normal` | `dist/mac/normal/` | `dungeon-antiqua-zero` |
| `exhibition` | `dist/mac/exhibition/` | `dungeon-antiqua-zero-exhibition` |
| `demo` | `dist/mac/demo/` | `dungeon-antiqua-zero-demo` |
| `beta` | `dist/mac/beta/` | `dungeon-antiqua-zero-beta` |

各ディレクトリへ `<基部>.app`、`<基部>-mac.zip` を生成する。
ZIPの直下には `.app` だけが入り、単独の `.pyxapp` とPyInstallerの作業ファイルは含めない。
`.pyxapp` は実行形式への変換に必要な中間ファイルとして一時ディレクトリで生成し、
ビルド後に削除する。Pyxelが `.app` の内部へ格納するゲームデータはそのまま保持する。
`dist/` はGit管理外とする。同じモードの再ビルドでは、そのディレクトリを完成後に置き換える。
途中で失敗した場合は、前回の成果物を保持する。

モードは一時コピー内の `_desktop_main.py` に埋め込み、Finderからダブルクリックした場合も
指定モードで起動する。
配布物の起動引数ではモードを変更せず、別モードが必要な場合はビルドし直す。
開発用 `app/main.py` の `--mode` の仕様は変更しない。
ゲーム内の挙動は [`features/launch-modes.md`](./features/launch-modes.md) を参照する。
起動口とコード・データのハッシュ記録は `scripts/desktop_build.py` を両OSで共有する。

### 署名

DA2と同じく、初期設定ではアドホック署名を行う。署名IDを指定する場合は次を使う。

```sh
CODESIGN_IDENTITY='署名ID' ./build.sh --mode demo
```

署名後に `codesign --verify --deep --strict` を実行する。公証、インストーラー作成、
Intel／Apple Silicon間のクロスビルドは行わない。ビルド環境のアーキテクチャ向けの配布物となる。
`PYXEL=/path/to/pyxel` で使用するPyxelコマンドを指定できる。

## Windows版

Windowsマシンで次を実行する。`build.bat` はPython製ビルド処理の入口とし、
バッチの文字コード、空白を含むパス、エラー処理に依存する部分を減らす。

```bat
build.bat
build.bat --mode exhibition
build.bat --mode demo
build.bat --mode beta
```

`npm run build:win`、`npm run build:win:exhibition`、`npm run build:win:demo`、
`npm run build:win:beta` も利用できる。リポジトリは事前に任意の方法で更新する。
DA2にあった `git pull` はビルド処理に含めず、現在の作業内容をそのままビルドする。

Windows版は既定で、ビルド前に共有データの同期（`sync-content.mjs`）と、Git管理外の
実行時リソース（画像・マップ・イベント・呪文エフェクト・攻撃ポーズ）の生成を行う。
そのため、clone直後でも `git submodule update --init` 済みであれば `build.bat` だけで完結する。
画像は配布用の厳密なパレット検証で生成する。BGMの変換（`npm run audio:build`）は
変換元WAVが必要なため含めない。

```bat
build.bat --mode exhibition --skip-prepare             :: 同期・生成を省き、現在のappをそのままビルド
build.bat --mode exhibition --allow-palette-mismatch   :: パレット外の色を最近傍色へ変換（確認用）
```

`--allow-palette-mismatch` で作った配布物はMacの厳密な生成結果と一致しない場合がある。
取り出し専用の `receive:win` では差分を表示して保管する。現在のMacの内容との一致を
必須とする確認には、後述のPythonスクリプトを直接使う。

### 環境

Python 3.11以上、Node.js 20以上と生成済みリソースが必要。
リソースの生成方法と同期チェックはMac版と同じ。例としてcmdで次を実行する。

```bat
python -m venv .venv-build
call .venv-build\Scripts\activate.bat
python -m pip install pyxel pyinstaller -r requirements-tools.txt
```

`python` はこの環境のものを使用する。PyxelとPyInstallerを同じPythonから呼び出す。
`icons/icon.ico` があればPyInstallerの `--icon` でexeへ埋め込む。
パレットは画像manifestが生バイトのハッシュを照合するため、`.gitattributes` で
`app/assets.pyxpal` の改行をLFへ固定し、Windowsでの画像再生成時も同じ値になるようにする。

DA2と同じく、既定では `signtool` で署名する。Windows SDKのSignToolと、
署名に使える証明書をWindows側へ用意する。PATHへ通すか次のように指定する。

```bat
set "SIGNTOOL=C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe"
build.bat --mode exhibition
```

SDKのバージョン部分はインストール済みのパスに合わせる。署名は証明書を `/a` で選び、
SHA256とRFC 3161タイムスタンプを使用する。署名後に `signtool verify /pa` を実行する。
署名できない場合はエラーで終了する。ローカル確認で署名を省略する場合は明示的に指定する。

```bat
build.bat --mode exhibition --no-sign
```

### 生成処理と出力

DA2と同じPyxelパッケージを作り、`app2exe` と同じ起動口と依存モジュール解析で
PyInstallerを呼ぶ。直接呼ぶ理由は、Windowsアイコンを指定でき、PyInstallerの失敗を
確実に検出できるようにするためである。通常版のファイル名は `dungeon-antiqua-zero`、
ほかの版はMac版と同じモード接尾辞を付ける。

`dist/windows/<mode>/` に次を生成する。

- `<基部>.exe` と `_internal/`: Windowsでの起動確認用。
- `<基部>-win.zip`: ZIPの直下にexeと `_internal/` がある配布物。
- `<基部>-win.zip.sha256`: ZIP全体のSHA256。

単独の `.pyxapp` は同梱しない。Pyxelが実行時に必要とする
`_internal/<基部>.pyxapp` は残す。署名・ZIP・内容検証まで完了してから、同じモードの
前回の出力を置き換える。同期チェック、PyInstaller、署名などの失敗時は前回の出力を保持する。
実行形式はWindowsでビルドしたPythonのアーキテクチャ向けとなる。

## DropboxでWindowsからMacへ受け渡す

大量のexe・DLLを直接同期するDA2の方式から、**Windows側でZIPを完成させてから同期する方式**
へ変更する。Macで再圧縮する必要がなく、配布できるZIPがそのまま届く。

Windowsのビルド終了後、既定では次へZIPとチェックサムをコピーする。

```text
~/Dropbox/public/tmp/dungeon-antiqua-zero/<mode>/
    <基部>-win-<UTC日時>-<ZIPハッシュ先頭12桁>.zip
    <同名>.zip.sha256
```

ZIPを一時名でコピーして内容を確認し、完成名へ変更してからチェックサムを作る。
コピー中の `.partial` はMac側の候補に含めない。ZIPとチェックサムの同期順が逆転しても、
チェックサムがない・一致しない場合は受け取りを失敗させる。古いビルドへ自動で戻らない。
各回のファイル名を変え、以前の受け渡し物を上書きしない。

Dropboxの場所が異なる場合は `--dropbox-dir` または `DA0_DROPBOX_DIR` で基部を指定する。
指定先の下にモードのディレクトリを作る。

```bat
build.bat --mode exhibition --dropbox-dir "D:\Dropbox\public\tmp\dungeon-antiqua-zero"
build.bat --mode exhibition --no-dropbox
```

MacでDropboxの同期が完了したら、ルートの `receive-windows.sh` で取り出しと片付けを行う。
`npm run receive:win` も同じ入口を呼ぶ。

```sh
./receive-windows.sh --mode exhibition
npm run receive:win -- --mode exhibition
```

既定の受け渡しディレクトリ内で、更新日時が最も新しい指定モードのZIPを選ぶ。
任意のZIPを選ぶ場合やDropbox以外で受け取る場合は、同じ場所に `.zip.sha256` を置いて指定する。

```sh
./receive-windows.sh --mode exhibition --source /path/to/build.zip
npm run receive:win -- --mode exhibition --dropbox-dir /path/to/Dropbox/inbox
```

受け取り時には一時コピーを作り、ZIP全体のチェックサム、exeヘッダー、ZIPの構成・破損、
起動モード、埋め込んだコード・データとビルド記録の一致を確認する。
取り出し専用の入口では、Mac上の現在の `app/` とWindows版に違いがある場合も、
差分のファイル名を表示してWindows版の内容をそのまま保管する。
Mac側のゲームデータは書き換えない。改行のLF／CRLF差だけは同一として扱う。
パレットは生バイトの一致を必要とする。
照合はコミットIDだけでなく、未コミットの変更と生成物も含めて行う。

`dist/windows/<mode>/` へ、固定名のZIPとチェックサムに加え、展開したexeと `_internal/` を置く。
ZIPはWindowsで署名したものをそのまま保存し、展開したファイルも起動・再署名しない。
検証と展開を一時ディレクトリで終えてから保存先を置き換える。失敗時は前回の出力と原本を保持する。
Steamへのアップロードなどの配布処理は含めない。

保存完了後、Dropboxの原本ZIPとチェックサムが受け取り時の内容と一致することを再確認し、
その2ファイルだけを削除する。古い受け渡し物、別モード、他のファイル、同期途中の
`.partial` は削除しない。既定の受け渡し先で空になったモードディレクトリは取り除き、
共有の `tmp` と基部ディレクトリは残す。原本が受け取り中に更新された場合は削除を中止し、
受け取り済みZIPは保持したままエラーにする。

原本を残し、現在のMacのコード・データとの一致を必須にしてZIPだけを保管したい場合は、
Pythonスクリプトを直接使う。

```sh
python3 -B scripts/import_windows_build.py --mode exhibition
```

この直接起動では、Windows側にもMacと同じ生成済み画像・マップ・イベント・音声が必要になる。
Pythonスクリプトの `--extract` は展開、`--cleanup` は原本の片付け、
`--allow-source-differences` は現在のMacとの差分を表示して保管する指定である。
保存先 `dist/windows/<mode>/` 内のZIPを原本に指定することは拒否する。
Windows側でのDropboxコピーに失敗した場合も、完成済みのローカル配布物は残る。

## 運用の選択肢

現在の運用では、Windows側でZIP化してDropboxへ渡す方式が変更量を抑えられる。
Windowsの署名証明書をそのまま使えて、Macでは受け取りコマンドを実行するだけで済む。

将来ビルドの起動も自動化する場合は、GitHub ActionsのWindows runnerでビルドし、
workflow artifactをMacへダウンロードする構成が候補になる。
既存のWindowsマシンをself-hosted runnerにすれば、そのマシンの証明書と素材を利用できる。
GitHub-hosted runnerを使う場合は、private submoduleへのアクセス、Git管理外の音声素材、
署名環境を別途用意する必要がある。現時点ではworkflowとrunnerの登録は行わない。

- [GitHubのrunner指定](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)
- [ビルド成果物の受け渡し](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)
- [self-hosted runner](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)

## 検証

```sh
python3 -B -m unittest tests.test_desktop_build tests.test_windows_build
```

一時リポジトリと代替コマンドを使い、全モードの起動口、パッケージとZIPの内容、アイコン・署名の
処理順、失敗時の成果物保持を検証する。Windows処理はMac上でも代替コマンドで検証できるが、
実行形式の生成・証明書を使う署名・exeの起動はWindows実機で確認する必要がある。
実際の配布前には両OSでゲームを起動し、該当モードのタイトルからの開始経路と
リソース読込を確認する。
