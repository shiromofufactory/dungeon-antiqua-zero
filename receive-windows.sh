#!/bin/bash
# Windowsの受け渡しZIPを保管・展開し、受け取った分だけDropboxから片付ける。
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 -B "$PROJECT_ROOT/scripts/import_windows_build.py" \
  --extract --cleanup --allow-source-differences "$@"
