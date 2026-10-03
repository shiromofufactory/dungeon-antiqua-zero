#!/usr/bin/env bash
set -euo pipefail

# audio_wav/ の全 wav を ../output/mp3/ に変換する。
# NO_LOOP_TRACKS の曲は MP3 に変換し、それ以外の曲はループ、フェード、無音を付ける。
# LEAD_IN_TRACKS の短いジングルは、再生開始時の音切れ対策として冒頭に無音を付ける。
#
# 構成: 全長 = 元の長さ × LOOPS + FADE 秒 + PAD 秒。
#   例) da3-field (85.97s) → 85.97×2 + 2 + 2 ≈ 175.9s
#       （0〜171.9s 音楽、171.9〜173.9s フェードアウト、173.9〜175.9s 無音）
#
# 仕組み: -stream_loop -1 で無限ループ化し、入力側 -t で「音楽＋フェード」分だけ
#         読み込み、afade で末尾をフェードアウト、apad で PAD 秒の無音を付加。
#
# 出力名: 元のファイル名 + _YYYYMMDD.mp3 （例: da3-battle1_20260815.mp3）
# WAV の内容と変換設定が前回と同じで、出力が残っていれば再生成しない。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/audio_wav"
OUT_DIR="$SCRIPT_DIR/../output/mp3"

LOOPS=2          # 完全再生する周回数
FADE=2           # フェードアウト秒数
PAD=2            # 末尾に付ける無音秒数
BITRATE=192k     # mp3 ビットレート

# ループしない曲名（拡張子なし）。ここに追加した曲はフェードや無音も付けない。
NO_LOOP_TRACKS=(
  da3-opening
  da3-encount
  da3-lvup
  da3-win
)

LEAD_IN_MS=200  # 短いジングルの冒頭に付ける無音（ミリ秒）
LEAD_IN_TRACKS=(
  da3-encount
  da3-lvup
  da3-win
)

DATE="$(date +%Y%m%d)"   # 実行日を全ファイル共通で使う

mkdir -p "$OUT_DIR"

shopt -s nullglob
found=0
for src in "$SRC_DIR"/*.wav; do
  found=1
  name="$(basename "${src%.wav}")"
  out="$OUT_DIR/${name}_${DATE}.mp3"
  state="$OUT_DIR/.${name}.make-loop-mp3.state"

  mode=loop
  for no_loop_name in "${NO_LOOP_TRACKS[@]}"; do
    if [[ "$name" == "$no_loop_name" ]]; then
      mode=plain
      break
    fi
  done

  lead_in_ms=0
  if [[ "$mode" == plain ]]; then
    for lead_in_name in "${LEAD_IN_TRACKS[@]}"; do
      if [[ "$name" == "$lead_in_name" ]]; then
        lead_in_ms="$LEAD_IN_MS"
        break
      fi
    done
  fi

  source_hash="$(shasum -a 256 "$src" | awk '{print $1}')"
  if [[ "$mode" == plain ]]; then
    settings="plain:$BITRATE"
    if (( lead_in_ms > 0 )); then
      settings="${settings}:lead-in:${lead_in_ms}"
    fi
  else
    settings="loop:$LOOPS:$FADE:$PAD:$BITRATE"
  fi
  fingerprint="$(printf '%s\n%s\n' "$source_hash" "$settings" | shasum -a 256 | awk '{print $1}')"

  previous_fingerprint=
  previous_output=
  if [[ -f "$state" ]]; then
    {
      IFS= read -r previous_fingerprint || true
      IFS= read -r previous_output || true
    } < "$state"
  fi
  if [[ "$fingerprint" == "$previous_fingerprint" && -s "$OUT_DIR/$previous_output" ]]; then
    printf '[%s] 変更なし → %s\n' "$name" "$previous_output"
    continue
  fi

  tmp_out="$(mktemp "$OUT_DIR/.${name}.XXXXXX")"
  tmp_state="$(mktemp "$OUT_DIR/.${name}.state.XXXXXX")"
  trap 'rm -f "${tmp_out:-}" "${tmp_state:-}"' EXIT

  if [[ "$mode" == plain ]]; then
    if (( lead_in_ms > 0 )); then
      printf '[%s] ループなし・冒頭無音 %dms → %s\n' "$name" "$lead_in_ms" "$(basename "$out")"
      ffmpeg -y -hide_banner -loglevel error \
        -i "$src" -af "adelay=${lead_in_ms}:all=1" \
        -b:a "$BITRATE" -f mp3 "$tmp_out"
    else
      printf '[%s] ループなし → %s\n' "$name" "$(basename "$out")"
      ffmpeg -y -hide_banner -loglevel error \
        -i "$src" -b:a "$BITRATE" -f mp3 "$tmp_out"
    fi
  else
    dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$src")"
    fade_start="$(awk "BEGIN{print $dur*$LOOPS}")"
    body="$(awk "BEGIN{print $dur*$LOOPS+$FADE}")"
    total="$(awk "BEGIN{print $dur*$LOOPS+$FADE+$PAD}")"

    printf '[%s] %.2fs ×%d + %ds + 無音%ds → %.2fs\n' \
      "$name" "$dur" "$LOOPS" "$FADE" "$PAD" "$total"

    ffmpeg -y -hide_banner -loglevel error \
      -stream_loop -1 -t "$body" -i "$src" \
      -af "afade=t=out:st=${fade_start}:d=${FADE},apad=pad_dur=${PAD}" \
      -b:a "$BITRATE" -f mp3 "$tmp_out"
  fi

  mv -f "$tmp_out" "$out"
  printf '%s\n%s\n' "$fingerprint" "$(basename "$out")" > "$tmp_state"
  mv -f "$tmp_state" "$state"
  trap - EXIT
done

if [ "$found" -eq 0 ]; then
  echo "wav が見つからない: $SRC_DIR" >&2
  exit 1
fi

echo "完了。出力先: $OUT_DIR"
