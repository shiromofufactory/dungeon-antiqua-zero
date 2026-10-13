#!/bin/bash
# DA2と同じPyxelパッケージから、モード別のMac配布物を作る。
set -euo pipefail

usage() {
  cat <<'EOF'
使い方: ./build.sh [--mode normal|exhibition|demo|beta]

  normal      通常版（省略時）
  exhibition  試遊版
  demo        体験版
  beta        βテスト版

出力先: dist/mac/<mode>/（.app、Mac配布用ZIP）
環境変数: PYXEL=Pyxelコマンドのパス、CODESIGN_IDENTITY=署名ID（省略時はアドホック署名）
事前のリソース生成手順: docs/desktop-build.md
EOF
}

fail() {
  echo "$*" >&2
  exit 1
}

MODE=normal
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode)
      if [ "$#" -lt 2 ]; then
        echo '--mode の値を指定してください。' >&2
        exit 2
      fi
      MODE="$2"
      shift 2
      ;;
    --mode=*) MODE="${1#--mode=}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未対応のオプションです: $1" >&2; usage >&2; exit 2 ;;
  esac
done
case "$MODE" in
  normal|exhibition|demo|beta) ;;
  *) echo "未対応のモードです: $MODE" >&2; exit 2 ;;
esac

[ "$(uname -s)" = Darwin ] || fail 'Mac版はmacOS上でビルドしてください。'
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"
PYXEL="${PYXEL:-pyxel}"
for command_name in "$PYXEL" pyinstaller python3 node codesign ditto; do
  command -v "$command_name" >/dev/null 2>&1 || fail "必要なコマンドがありません: $command_name"
done
# 相対パスで指定したPyxelも、作業ディレクトリを移した後に呼べるようにする。
PYXEL="$(command -v "$PYXEL")"
case "$PYXEL" in /*) ;; *) PYXEL="$PROJECT_ROOT/$PYXEL" ;; esac

# DA2と同様に生成済みのappを配布する。JSONの同期漏れと未生成リソースを先に検出する。
node scripts/sync-content.mjs --check
for resource in \
  main.py assets.pyxres assets.pyxpal \
  data/characters.json data/items.json data/monsters.json data/shops.json \
  data/skills.json data/spells.json data/texts.json \
  images/manifest.json images/graphics.bin maps/worldmap.json \
  events/events.json events/messages.json \
  effects/spells.json effects/attack_poses.json audio/catalog.json; do
  [ -s "app/$resource" ] || fail "配布用リソースがありません: app/${resource}（docs/desktop-build.md を参照）"
done

APP_NAME=dungeon-antiqua-zero
if [ "$MODE" != normal ]; then
  APP_NAME="$APP_NAME-$MODE"
fi
OUTPUT_PARENT="$PROJECT_ROOT/dist/mac"
OUTPUT_DIR="$OUTPUT_PARENT/$MODE"
mkdir -p "$OUTPUT_PARENT"
STAGE_DIR="$(mktemp -d "$OUTPUT_PARENT/.build-$MODE.XXXXXX")"
cleanup() {
  # 成果物の入れ替えに失敗・中断した場合も、前回の配布物を復元する。
  if [ -d "$STAGE_DIR/previous" ] && [ ! -e "$OUTPUT_DIR" ]; then
    mv "$STAGE_DIR/previous" "$OUTPUT_DIR"
  fi
  rm -rf "$STAGE_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Mac版をビルドします: $MODE"
cp -R app "$STAGE_DIR/app"
find "$STAGE_DIR/app" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$STAGE_DIR/app" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '.DS_Store' \) -delete

# Pyxelのplay/app2exeは起動引数を渡さないため、配布物専用の起動口にモードを埋め込む。
# 開発用main.pyやSettings、SaveDataは変更しない。Windows版と同じ起動口・ビルド記録を使う。
python3 -B "$PROJECT_ROOT/scripts/desktop_build.py" --app-root "$STAGE_DIR/app" --mode "$MODE"

cd "$STAGE_DIR"
"$PYXEL" package app app/_desktop_main.py
[ -s app.pyxapp ] || fail 'Pyxelパッケージが生成されませんでした。'
mv app.pyxapp "$APP_NAME.pyxapp"
"$PYXEL" app2exe "$APP_NAME.pyxapp"
# Pyxelのapp2exeは内部のPyInstaller失敗を終了コードへ反映しない版がある。
[ -x "$APP_NAME.app/Contents/MacOS/$APP_NAME" ] || fail 'Macアプリが生成されませんでした。PyInstallerのログを確認してください。'

if [ -f "$PROJECT_ROOT/icons/icon.icns" ]; then
  cp "$PROJECT_ROOT/icons/icon.icns" "$APP_NAME.app/Contents/Resources/icon-windowed.icns"
  touch "$APP_NAME.app"
else
  echo 'icons/icon.icns がないため、Pyxel標準アイコンを使用します。' >&2
fi
codesign --deep --force --verify --verbose --sign "${CODESIGN_IDENTITY:--}" "$APP_NAME.app"
codesign --verify --deep --strict "$APP_NAME.app"

# dittoでMacアプリ内のリンク・リソースを維持する。pyxappは中間生成物としてだけ使う。
mkdir release
mv "$APP_NAME.app" release/
ditto -c -k --sequesterRsrc release "$APP_NAME-mac.zip"
[ -s "$APP_NAME-mac.zip" ] || fail 'Mac配布用ZIPが生成されませんでした。'
mv "$APP_NAME-mac.zip" release/

if [ -e "$OUTPUT_DIR" ]; then
  mv "$OUTPUT_DIR" "$STAGE_DIR/previous"
fi
mv release "$OUTPUT_DIR"
echo "生成完了: $OUTPUT_DIR"
echo "配布用ZIP: $OUTPUT_DIR/$APP_NAME-mac.zip"
