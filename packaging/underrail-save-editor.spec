# PyInstaller spec: one-folder GUI build (used for the Windows .exe).
#   python packaging/make_icon.py build
#   pyinstaller --noconfirm --distpath build/dist --workpath build/work packaging/underrail-save-editor.spec
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
ICON = os.path.join(ROOT, 'build', 'underrail-save-editor.ico')

a = Analysis(
    [os.path.join(ROOT, 'underrail_gui.py')],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, 'assets', 'underrail-save-editor.svg'), 'assets'),
           (os.path.join(ROOT, 'data', '*.json'), 'data')],
    hiddenimports=['PySide6.QtSvg'],  # SVG icon rendering
    excludes=['tkinter', 'unittest', 'PySide6.QtWebEngineCore', 'PySide6.QtQml', 'PySide6.QtQuick'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='UnderrailSaveEditor',
    console=False,
    icon=ICON if os.path.exists(ICON) else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name='UnderrailSaveEditor')
