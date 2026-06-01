#!/bin/bash
# download_fonts.sh — Download DejaVu fonts for profile card generation
# Run once: bash download_fonts.sh

set -e
FONTS_DIR="$(dirname "$0")/assets/fonts"
mkdir -p "$FONTS_DIR"

echo "Downloading DejaVu fonts..."
BASE="https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37"
FILE="dejavu-fonts-ttf-2.37.tar.bz2"

cd /tmp
curl -L "$BASE/$FILE" -o "$FILE"
tar -xjf "$FILE"
cp dejavu-fonts-ttf-2.37/ttf/DejaVuSans.ttf "$FONTS_DIR/"
cp dejavu-fonts-ttf-2.37/ttf/DejaVuSans-Bold.ttf "$FONTS_DIR/"
rm -rf "$FILE" dejavu-fonts-ttf-2.37

echo "Fonts installed to $FONTS_DIR"
ls "$FONTS_DIR"
