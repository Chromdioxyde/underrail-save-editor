"""Renders assets/underrail-save-editor.svg to a multi-size .ico (Windows exe icon) and a 256 px PNG."""
import os
import sys

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(ROOT, 'assets', 'underrail-save-editor.svg')
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build')

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
app = QGuiApplication([])
os.makedirs(OUT, exist_ok=True)


def render(size):
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    QSvgRenderer(SVG).render(painter)
    painter.end()
    path = os.path.join(OUT, f'icon-{size}.png')
    img.save(path)
    return path


big = Image.open(render(256))
big.save(os.path.join(OUT, 'underrail-save-editor.ico'), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
big.save(os.path.join(OUT, 'underrail-save-editor.png'))
print(os.path.join(OUT, 'underrail-save-editor.ico'))
