#!/bin/zsh
set -euo pipefail

ROOT_DIR="${0:A:h}"
APP_DIR="$ROOT_DIR/NCM 解码.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

swiftc "$ROOT_DIR/macos-app/NCMDecoderApp.swift" \
  -o "$MACOS_DIR/NCMDecoder" \
  -framework AppKit

cp "$ROOT_DIR/macos-app/Info.plist" "$CONTENTS_DIR/Info.plist"
cp "$ROOT_DIR/ncmdump_mac.py" "$RESOURCES_DIR/ncmdump_mac.py"
chmod +x "$MACOS_DIR/NCMDecoder" "$RESOURCES_DIR/ncmdump_mac.py"
codesign --force --deep --sign - "$APP_DIR" >/dev/null

echo "Built: $APP_DIR"
