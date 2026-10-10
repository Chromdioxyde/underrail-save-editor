#!/usr/bin/env bash
# Builds a self-contained AppImage (Linux x86_64, incl. Steam Deck) into build/.
# Uses a portable CPython from python-build-standalone plus manylinux wheels of PySide6 and
# Pillow, so the result runs on glibc >= 2.28 regardless of how new the build machine is.
# Needs: curl, tar, internet access. No root.
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
BUILD="$ROOT/build"
PY_VERSION="${PY_VERSION:-3.12}"
APPDIR="$BUILD/AppDir"
VERSION="$(git describe --tags --always 2>/dev/null || echo dev)"
OUT="$BUILD/Underrail_Save_Editor-$VERSION-x86_64.AppImage"

mkdir -p "$BUILD"

# portable Python (cached between builds)
PY_TGZ="$BUILD/python-$PY_VERSION.tar.gz"
if [ ! -f "$PY_TGZ" ]; then
    echo "Fetching python-build-standalone $PY_VERSION..."
    url=$(curl -fsSL https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest |
          grep -o "https://[^\"]*cpython-$PY_VERSION\.[0-9]*%2B[0-9]*-x86_64-unknown-linux-gnu-install_only_stripped\.tar\.gz" |
          head -1 || true)
    [ -n "$url" ] || { echo "No python-build-standalone download found for $PY_VERSION"; exit 1; }
    curl -fL "$url" -o "$PY_TGZ"
fi

# appimagetool (cached); run extracted so FUSE isn't required
TOOL="$BUILD/appimagetool-x86_64.AppImage"
if [ ! -f "$TOOL" ]; then
    echo "Fetching appimagetool..."
    curl -fL https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage -o "$TOOL"
    chmod +x "$TOOL"
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr"
tar -xzf "$PY_TGZ" -C "$APPDIR/usr"          # -> AppDir/usr/python
PY="$APPDIR/usr/python/bin/python3"

echo "Installing PySide6 and Pillow..."
"$PY" -m pip install --quiet --no-cache-dir --only-binary=:all: PySide6-Essentials pillow

# trim what the app never uses (tests, headers, pip caches, Qt translations/QML/designer)
rm -rf "$APPDIR/usr/python/include" "$APPDIR/usr/python/share"
find "$APPDIR/usr/python" -type d \( -name __pycache__ -o -name tests -o -name test \) -prune -exec rm -rf {} +
SP=$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
rm -rf "$SP/PySide6/Qt/translations" "$SP/PySide6/Qt/qml" "$SP/PySide6/include" \
       "$SP/PySide6/designer" "$SP/PySide6/typesystems" "$SP/PySide6/glue" "$SP"/pip*

# application
mkdir -p "$APPDIR/usr/app/assets"
cp ./*.py "$APPDIR/usr/app/"
cp assets/underrail-save-editor.svg "$APPDIR/usr/app/assets/"
cp -r data "$APPDIR/usr/app/"
cp assets/underrail-save-editor.svg "$APPDIR/underrail-save-editor.svg"
cp packaging/underrail-save-editor.desktop "$APPDIR/"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export PYTHONNOUSERSITE=1
unset PYTHONHOME PYTHONPATH
exec "$HERE/usr/python/bin/python3" "$HERE/usr/app/underrail_gui.py" "$@"
EOF
chmod +x "$APPDIR/AppRun"

echo "Packing $OUT..."
ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$OUT" >/dev/null
echo "Built $OUT ($(du -h "$OUT" | cut -f1))"
