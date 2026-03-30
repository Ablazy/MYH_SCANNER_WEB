#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$SCRIPT_DIR/../bin}"
TARGET_DIR="$(cd "$(dirname "$TARGET_DIR")" && pwd)/$(basename "$TARGET_DIR")"
TARGET_FFMPEG="$TARGET_DIR/ffmpeg"
TARGET_FFPROBE="$TARGET_DIR/ffprobe"

if [[ -x "$TARGET_FFMPEG" ]]; then
  echo "ffmpeg already exists at: $TARGET_FFMPEG"
  exit 0
fi

if [[ -n "${FFMPEG_DOWNLOAD_URL:-}" ]]; then
  DOWNLOAD_URL="$FFMPEG_DOWNLOAD_URL"
else
  OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
  ARCH="$(uname -m)"

  if [[ "$OS" != "linux" ]]; then
    echo "automatic ffmpeg download currently supports Linux only." >&2
    echo "Please set FFMPEG_COMMAND manually, or provide FFMPEG_DOWNLOAD_URL." >&2
    exit 1
  fi

  case "$ARCH" in
    x86_64|amd64)
      DOWNLOAD_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
      ;;
    aarch64|arm64)
      DOWNLOAD_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
      ;;
    armv7l|armhf)
      DOWNLOAD_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-armhf-static.tar.xz"
      ;;
    *)
      echo "unsupported Linux architecture: $ARCH" >&2
      echo "Please set FFMPEG_DOWNLOAD_URL to a compatible archive URL." >&2
      exit 1
      ;;
  esac
fi

if command -v curl >/dev/null 2>&1; then
  DOWNLOADER="curl"
elif command -v wget >/dev/null 2>&1; then
  DOWNLOADER="wget"
else
  echo "curl/wget not found. Please install one of them first." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ARCHIVE_PATH="$TMP_DIR/ffmpeg.tar.xz"
echo "downloading ffmpeg archive..."
echo "url: $DOWNLOAD_URL"

if [[ "$DOWNLOADER" == "curl" ]]; then
  curl -L --fail --retry 3 --connect-timeout 15 "$DOWNLOAD_URL" -o "$ARCHIVE_PATH"
else
  wget -O "$ARCHIVE_PATH" "$DOWNLOAD_URL"
fi

mkdir -p "$TARGET_DIR"
tar -xJf "$ARCHIVE_PATH" -C "$TMP_DIR"

SRC_FFMPEG="$(find "$TMP_DIR" -type f -name ffmpeg | head -n 1 || true)"
if [[ -z "$SRC_FFMPEG" ]]; then
  echo "cannot find ffmpeg binary in downloaded archive." >&2
  exit 1
fi

install -m 0755 "$SRC_FFMPEG" "$TARGET_FFMPEG"

SRC_FFPROBE="$(find "$TMP_DIR" -type f -name ffprobe | head -n 1 || true)"
if [[ -n "$SRC_FFPROBE" ]]; then
  install -m 0755 "$SRC_FFPROBE" "$TARGET_FFPROBE"
fi

echo "ffmpeg installed at: $TARGET_FFMPEG"
