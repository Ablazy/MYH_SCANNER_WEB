#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

AUTO_DOWNLOAD_FFMPEG="${AUTO_DOWNLOAD_FFMPEG:-1}"
LOCAL_FFMPEG="$SCRIPT_DIR/bin/ffmpeg"

if [[ -z "${FFMPEG_COMMAND:-}" ]]; then
  if [[ -x "$LOCAL_FFMPEG" ]]; then
    export FFMPEG_COMMAND="$LOCAL_FFMPEG"
  elif [[ "$AUTO_DOWNLOAD_FFMPEG" == "1" ]]; then
    if "$SCRIPT_DIR/scripts/download_ffmpeg.sh" "$SCRIPT_DIR/bin"; then
      if [[ -x "$LOCAL_FFMPEG" ]]; then
        export FFMPEG_COMMAND="$LOCAL_FFMPEG"
      fi
    else
      echo "warning: ffmpeg auto-download failed; fallback to system ffmpeg/opencv." >&2
    fi
  fi
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
