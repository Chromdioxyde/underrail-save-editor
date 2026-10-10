#!/usr/bin/env bash
# Installs Underrail Save Editor for the current user (no root needed):
# program files to ~/.local/share/underrail-save-editor/app, launchers to ~/.local/bin,
# icon and .desktop entry to ~/.local/share/{icons,applications}.
# Re-run to update. packaging/uninstall.sh removes everything except backups.
set -euo pipefail

cd "$(dirname "$0")/.."

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_DIR="$DATA_HOME/underrail-save-editor/app"
BACKUP_DIR="$DATA_HOME/underrail-save-editor/backups"
BIN_DIR="$HOME/.local/bin"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
DESKTOP_DIR="$DATA_HOME/applications"

# dependencies (package names of Arch-based distributions)
missing=()
python3 -c 'import PySide6' 2>/dev/null || missing+=(pyside6)
python3 -c 'import PIL' 2>/dev/null || missing+=(python-pillow)
if [ ${#missing[@]} -gt 0 ]; then
    echo "Missing Python dependencies: ${missing[*]}"
    echo "Install them with: sudo pacman -S ${missing[*]}"
    exit 1
fi

mkdir -p "$APP_DIR/assets" "$BACKUP_DIR" "$BIN_DIR" "$ICON_DIR" "$DESKTOP_DIR"

# replace program files, keep nothing stale from older versions
rm -f "$APP_DIR"/*.py
install -m 644 ./*.py "$APP_DIR/"
chmod 755 "$APP_DIR/underrail_gui.py" "$APP_DIR/underrail_spec.py"
install -m 644 assets/underrail-save-editor.svg "$APP_DIR/assets/"

# backups made while running from the repo checkout (copied, never overwritten)
if [ -d backups ]; then
    cp -rn backups/. "$BACKUP_DIR/" 2>/dev/null || true
fi

cat > "$BIN_DIR/underrail-save-editor" <<EOF
#!/bin/sh
exec python3 "$APP_DIR/underrail_gui.py" "\$@"
EOF
cat > "$BIN_DIR/underrail-spec" <<EOF
#!/bin/sh
exec python3 "$APP_DIR/underrail_spec.py" "\$@"
EOF
chmod 755 "$BIN_DIR/underrail-save-editor" "$BIN_DIR/underrail-spec"

install -m 644 assets/underrail-save-editor.svg "$ICON_DIR/underrail-save-editor.svg"
install -m 644 packaging/underrail-save-editor.desktop "$DESKTOP_DIR/underrail-save-editor.desktop"

command -v update-desktop-database >/dev/null && update-desktop-database "$DESKTOP_DIR" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f "$DATA_HOME/icons/hicolor" 2>/dev/null || true

echo "Installed to $APP_DIR"
echo "Backups go to $BACKUP_DIR"
echo "Start it from the application menu ('Underrail Save Editor') or run: underrail-save-editor"
