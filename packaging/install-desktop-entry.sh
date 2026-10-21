#!/usr/bin/env bash
# Install (or remove) the Kalshi Hunter desktop entry and icon FOR THE CURRENT USER ONLY.
#
#   ./install-desktop-entry.sh            dry run: show exactly what would be written
#   ./install-desktop-entry.sh --yes      do it (writes only under ~/.local/share)
#   ./install-desktop-entry.sh --uninstall  remove what this script installed
#
# No sudo, no system-wide files, no daemon, no scanner. This is deliberately NOT run automatically:
# adding a menu entry is a user-visible change and needs the owner's go-ahead.
set -eu
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor"
SIZES='16 24 32 48 64 128 256 512'

if [ "${1:-}" = '--uninstall' ]; then
    rm -f "$APPS/kalshi-hunter.desktop"
    for s in $SIZES; do rm -f "$ICONS/${s}x${s}/apps/kalshi-hunter.png"; done
    rm -f "$ICONS/scalable/apps/kalshi-hunter.svg"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" 2>/dev/null || true
    echo "Removed the Kalshi Hunter menu entry and icons for $USER. The application itself is untouched."
    exit 0
fi

echo "Repository:  $ROOT"
echo "Exec line:   $ROOT/launch.sh"
echo "Would write: $APPS/kalshi-hunter.desktop (with Exec/Path pointed at this checkout)"
for s in $SIZES; do echo "             $ICONS/${s}x${s}/apps/kalshi-hunter.png"; done
echo "             $ICONS/scalable/apps/kalshi-hunter.svg"

if [ "${1:-}" != '--yes' ]; then
    echo
    echo "Dry run. Re-run with --yes to install (user-level only), or --uninstall to remove it."
    exit 0
fi

mkdir -p "$APPS"
sed -e "s|^Exec=.*|Exec=$ROOT/launch.sh|" -e "s|^Path=.*|Path=$ROOT|" \
    "$ROOT/packaging/kalshi-hunter.desktop" > "$APPS/kalshi-hunter.desktop"
for s in $SIZES; do
    mkdir -p "$ICONS/${s}x${s}/apps"
    cp "$ROOT/packaging/icons/kalshi-hunter-$s.png" "$ICONS/${s}x${s}/apps/kalshi-hunter.png"
done
mkdir -p "$ICONS/scalable/apps"
cp "$ROOT/packaging/icons/kalshi-hunter.svg" "$ICONS/scalable/apps/kalshi-hunter.svg"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t -f "$ICONS" 2>/dev/null || true
echo "Installed for $USER. Remove later with: $0 --uninstall"