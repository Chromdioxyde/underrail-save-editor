#!/usr/bin/env bash
# Removes what packaging/install.sh installed. Save backups and the cache are kept:
#   ~/.local/share/underrail-save-editor/backups   (your save game backups)
#   ~/.cache/underrail-save-editor                 (item DB, icons, portraits; safe to delete)
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"

rm -rf "$DATA_HOME/underrail-save-editor/app"
rm -f "$HOME/.local/bin/underrail-save-editor" "$HOME/.local/bin/underrail-spec"
rm -f "$DATA_HOME/icons/hicolor/scalable/apps/underrail-save-editor.svg"
rm -f "$DATA_HOME/applications/underrail-save-editor.desktop"

command -v update-desktop-database >/dev/null && update-desktop-database "$DATA_HOME/applications" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f "$DATA_HOME/icons/hicolor" 2>/dev/null || true

echo "Uninstalled. Backups kept in $DATA_HOME/underrail-save-editor/backups"
