#!/usr/bin/env python3
"""Underrail save editor GUI (PySide6)."""
import datetime
import os
import re
import sys

from PySide6.QtCore import (QFileSystemWatcher, QObject, QPointF, QRectF, QRunnable, QSize, Qt, QThreadPool, QTimer,
                            Signal)
from PySide6.QtGui import QAction, QBrush, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFrame,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGraphicsRectItem,
                               QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView, QGroupBox,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
                               QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from html import escape as html_escape

import gamedata
import i18n
import paths
import underrail_save as us
from i18n import tr

INT_MAX = 2**31 - 1
# The game doesn't cap component quality: stats scale with Q * f(Q), where f stops growing at 185
# (constants in its config class). 999 keeps it to three digits.
MAX_QUALITY = 999
QUALITY_CURVE_END = 185


class _WheelGuard(QObject):
    """Lets the mouse wheel scroll the surrounding table instead of changing an unfocused spinbox,
    so values can't change by accident while scrolling."""

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Wheel and not obj.hasFocus():
            event.ignore()
            return True
        return False


_wheel_guard = None


def spin_for(field, on_change, lo=0, hi=INT_MAX):
    """Spinbox bound to a Field; bold while it differs from the loaded value."""
    if field.is_float:
        sb = QDoubleSpinBox()
        sb.setDecimals(1)
        sb.setRange(float(lo), float(hi))
    else:
        sb = QSpinBox()
        sb.setRange(lo, hi)
    sb.setValue(field.value)
    sb.setFrame(False)
    global _wheel_guard
    if _wheel_guard is None:
        _wheel_guard = _WheelGuard()
    sb.setFocusPolicy(Qt.StrongFocus)  # no focus (and no value change) just by hovering + scrolling
    sb.installEventFilter(_wheel_guard)

    def changed(v):
        on_change(field, v)
        f = sb.font()
        f.setBold(abs(v - field.original) > 1e-6)
        sb.setFont(f)
    sb.valueChanged.connect(changed)
    return sb


def filter_box(placeholder, slot):
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    e.setClearButtonEnabled(True)
    e.textChanged.connect(slot)
    return e


class FieldTable(QTableWidget):
    """Name | value spinbox | optional info column, one row per Field."""

    def __init__(self, main, fields, lo=0, hi=INT_MAX, info_header=None, info=None, label=None, after=None,
                 hi_of=None):
        cols = [tr('Name'), tr('Value')] + ([tr(info_header)] if info_header else [])
        super().__init__(len(fields), len(cols))
        self.main, self.fields, self.info, self.after = main, fields, info, after
        self.setHorizontalHeaderLabels(cols)
        self.verticalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.setSelectionMode(QTableWidget.NoSelection)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        for row, f in enumerate(fields):
            self.setItem(row, 0, QTableWidgetItem(label(f) if label else tr(f.name)))
            if f.info:
                self.item(row, 0).setToolTip(f.info)
            top = hi_of(f) if hi_of else hi
            # never clamp a value the save already has above the limit
            self.setCellWidget(row, 1, spin_for(f, self.changed, lo, max(top, f.value) if top is not None else hi))
            if info:
                self.setItem(row, 2, QTableWidgetItem(str(info(f))))
        self.setColumnWidth(1, 120)
        if info:
            self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

    def changed(self, f, v):
        self.main.save.set(f, v)
        if self.info:
            self.item(self.fields.index(f), 2).setText(str(self.info(f)))
        self.main.on_change()
        if self.after:
            self.after()


# --- background work ----------------------------------------------------------------------

class _Signals(QObject):
    done = Signal(str, str)


_portrait_signals = None


def portrait_signals():
    # jobs outlive the dialog that started them, so the signal source must too
    global _portrait_signals
    if _portrait_signals is None:
        _portrait_signals = _Signals()
    return _portrait_signals


class IconJob(QRunnable):
    """Extracts item icons that aren't cached yet, then notifies the main window."""

    def __init__(self, vms, signals):
        super().__init__()
        self.vms, self.signals = vms, signals

    def run(self):
        try:
            gamedata.extract_icons(self.vms)
        except Exception:
            pass
        try:
            self.signals.done.emit('icons', '')
        except RuntimeError:
            pass  # app is shutting down


def cached_details(folder):
    """Save details only if already cached (never parses global.dat on the UI thread)."""
    import json
    try:
        with open(os.path.join(gamedata.CACHE, 'savedetails.json')) as fh:
            hit = json.load(fh).get(folder)
        if hit and hit['mtime'] == os.path.getmtime(os.path.join(folder, 'global.dat')) \
                and hit.get('v') == us.DETAILS_VERSION:
            return hit['details']
    except (OSError, ValueError, KeyError):
        pass
    return None


def item_icon(vm, category=None, cls=None, wtype=None):
    """(QIcon or None, is_placeholder) for a visual id, falling back to a category placeholder."""
    path = gamedata.icon_path(vm)
    if path:
        return QIcon(path), False
    if category:
        ph = gamedata.placeholder_icon(category, cls, wtype)
        if ph:
            return QIcon(ph), True
    return None, False


class DetailsJob(QRunnable):
    """Reads HP/XP/money of each save in the background (cached after the first run)."""

    def __init__(self, folders, signals):
        super().__init__()
        self.folders, self.signals = folders, signals

    def run(self):
        for folder in self.folders:
            try:
                us.save_details(folder)
                self.signals.done.emit('details', folder)
            except RuntimeError:
                return  # app is shutting down
            except Exception:
                continue


THUMB_W, THUMB_H = 224, 126  # card thumbnail (screenshots are cropped to 16:9)


def thumb_path(folder):
    """Cached thumbnail of a save's screenshot, keyed by folder and screenshot mtime."""
    import hashlib
    shot = os.path.join(folder, 'screenshot.png')
    try:
        key = f'{folder}|{os.path.getmtime(shot)}'
    except OSError:
        return None
    return os.path.join(gamedata.CACHE, 'thumbs', hashlib.sha1(key.encode()).hexdigest() + '.png')


class ThumbJob(QRunnable):
    """Scales save screenshots down to card thumbnails off the UI thread."""

    def __init__(self, folders, signals):
        super().__init__()
        self.folders, self.signals = folders, signals

    def run(self):
        from PySide6.QtGui import QImage
        for folder in self.folders:
            out = thumb_path(folder)
            if not out or os.path.exists(out):
                continue
            img = QImage(os.path.join(folder, 'screenshot.png'))
            if img.isNull():
                continue
            # fill the 16:9 box, cropping the wide in-game screenshots in the middle
            img = img.scaled(THUMB_W, THUMB_H, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            img = img.copy((img.width() - THUMB_W) // 2, (img.height() - THUMB_H) // 2, THUMB_W, THUMB_H)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            img.save(out)
            try:
                self.signals.done.emit('thumb', folder)
            except RuntimeError:
                return  # app is shutting down


class SaveCard(QWidget):
    """One save in the list: screenshot on the left, structured info on the right."""

    STYLE = """
        QFrame#card { border: 1px solid palette(mid); border-radius: 8px; background: palette(base); }
        QFrame#card[selected="true"] { border: 2px solid palette(highlight); background: palette(alternate-base); }
        QLabel#thumb { border-radius: 4px; background: palette(window); }
        QLabel#title { font-weight: bold; font-size: 11pt; }
        QLabel#dim { color: palette(placeholder-text); }
        QLabel#badge { color: palette(highlighted-text); background: palette(highlight);
                       border-radius: 4px; padding: 1px 6px; }
    """

    def __init__(self, name, folder, info):
        super().__init__()
        self.folder, self.info = folder, info
        self.frame = QFrame(objectName='card')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 3, 4, 3)
        outer.addWidget(self.frame)
        self.setStyleSheet(self.STYLE)
        row = QHBoxLayout(self.frame)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(10)
        self.thumb = QLabel(objectName='thumb', alignment=Qt.AlignCenter)
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        row.addWidget(self.thumb)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = QLabel(name, objectName='title')
        self.title.setWordWrap(True)
        self.setMinimumWidth(THUMB_W + 160)
        text.addWidget(self.title)
        if info:
            when = datetime.datetime.fromtimestamp(info['mtime']).strftime('%Y-%m-%d %H:%M')
            text.addWidget(QLabel(f"{info['name']} · {tr('Level')} {info['level']}"))
            loc = QLabel(info['location'] or '', objectName='dim')
            loc.setWordWrap(True)
            text.addWidget(loc)
            meta = []
            if info.get('hours') is not None:
                h = info['hours']
                meta.append(f'⏱ {int(h)}h {int(h * 60) % 60:02d}m')
            if info.get('difficulty') is not None:
                meta.append(tr(str(info['difficulty'])))
            text.addWidget(QLabel(' · '.join(meta), objectName='dim'))
            text.addWidget(QLabel(when, objectName='dim'))
            dlcs = ', '.join(info.get('dlcs') or []) or '–'
            self.setToolTip(tr('Game time is the in-game world clock stored in the save.') + '\n'
                            + tr('DLCs: {dlcs}', dlcs=dlcs))
        else:
            text.addWidget(QLabel(tr('(unreadable info)'), objectName='dim'))
        self.stats = QLabel()
        self.money = QLabel(objectName='dim')
        self.unspent = QLabel(objectName='badge')
        self.unspent.hide()
        text.addWidget(self.stats)
        text.addWidget(self.money)
        badge_row = QHBoxLayout()
        badge_row.addWidget(self.unspent)
        badge_row.addStretch()
        text.addLayout(badge_row)
        text.addStretch()
        row.addLayout(text, 1)
        self.set_thumb()

    def set_thumb(self):
        p = thumb_path(self.folder)
        if p and os.path.exists(p):
            self.thumb.setPixmap(QPixmap(p))
        else:
            self.thumb.setText('…')

    def set_details(self, d):
        if not d:
            self.stats.setText(tr('loading…'))
            return
        parts = []
        if d.get('hp') is not None:
            parts.append(f"❤ {d['hp']:.0f}/{d['hp_max']:.0f}")
        if d.get('xp') is not None:
            parts.append(f"XP {d['xp']:,}")
        self.stats.setText('   '.join(parts))
        money = [f'{v:,} {tr(k)}' for k, v in (d.get('money') or {}).items()]
        # two currencies per line keeps the card narrow
        self.money.setText('\n'.join(' · '.join(money[i:i + 2]) for i in range(0, len(money), 2))
                           or tr('no money'))
        unspent = {k: v for k, v in (d.get('unspent') or {}).items() if v}
        if unspent:
            labels = {'PC1:BAPC': tr('attr.'), 'PC1:SPC': tr('skill'), 'PC1:FC': tr('feat'), 'PC1:SP': tr('spec')}
            self.unspent.setText(tr('unspent') + ': ' + ', '.join(f'{v} {labels.get(k, k)}' for k, v in unspent.items()))
            self.unspent.show()
        else:
            self.unspent.hide()

    def set_selected(self, on):
        self.frame.setProperty('selected', on)
        self.frame.style().unpolish(self.frame)
        self.frame.style().polish(self.frame)


class PortraitJob(QRunnable):
    def __init__(self, pid, path, signals):
        super().__init__()
        self.pid, self.path, self.signals = pid, path, signals

    def run(self):
        try:
            png = gamedata.portrait_png(self.pid, self.path)
        except Exception:
            png = ''
        try:
            self.signals.done.emit(self.pid, png)
        except RuntimeError:
            pass  # app is shutting down


# --- dialogs ------------------------------------------------------------------------------

class PortraitDialog(QDialog):
    def __init__(self, parent, current):
        super().__init__(parent)
        self.setWindowTitle(tr('Choose portrait'))
        self.resize(900, 650)
        self.selected = current
        self.portraits = gamedata.portraits()
        self.signals = portrait_signals()
        self.signals.done.connect(self.loaded)
        self.finished.connect(lambda _: self.signals.done.disconnect(self.loaded))
        self.items = {}

        self.group = QComboBox()
        for g in ('all', 'male', 'female', 'genderless', 'custom'):
            self.group.addItem(tr(g), g)
        self.group.currentTextChanged.connect(self.refilter)
        self.search = filter_box(tr('Filter by id…'), self.refilter)
        imp = QPushButton(tr('Import PNG…'))
        imp.clicked.connect(self.import_png)
        top = QHBoxLayout()
        top.addWidget(self.group); top.addWidget(self.search, 1); top.addWidget(imp)

        self.view = QListWidget()
        self.view.setViewMode(QListWidget.IconMode)
        self.view.setIconSize(QSize(100, 100))
        self.view.setGridSize(QSize(120, 135))
        self.view.setResizeMode(QListWidget.Adjust)
        self.view.setMovement(QListWidget.Static)
        self.view.itemDoubleClicked.connect(lambda _: self.accept())
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(top); lay.addWidget(self.view, 1); lay.addWidget(buttons)
        self.populate()

    def populate(self):
        self.view.clear()
        self.items = {}
        pool = QThreadPool.globalInstance()
        for pid, (group, path) in sorted(self.portraits.items(), key=lambda x: (x[1][0] != 'custom', x[0])):
            it = QListWidgetItem(pid)
            it.setData(Qt.UserRole, pid)
            it.setToolTip(f'{pid} ({group})')
            self.view.addItem(it)
            self.items[pid] = it
            if pid == self.selected:
                self.view.setCurrentItem(it)
            pool.start(PortraitJob(pid, path, self.signals))
        self.refilter()

    def loaded(self, pid, png):
        it = self.items.get(pid)
        if it is not None and png:
            it.setIcon(QIcon(png))

    def refilter(self, *_):
        g, q = self.group.currentData(), self.search.text().lower()
        for pid, it in self.items.items():
            it.setHidden(bool((g != 'all' and self.portraits[pid][0] != g) or (q and q not in pid.lower())))

    def import_png(self):
        path, _ = QFileDialog.getOpenFileName(self, tr('Portrait image'), os.path.expanduser('~'),
                                              tr('Images (*.png *.jpg *.jpeg *.webp *.bmp)'))
        if not path:
            return
        existing = [p for p, (g, _) in self.portraits.items() if g == 'custom']
        n = 1
        while f'custom{n}' in existing:
            n += 1
        pid, ok = QInputDialog.getText(self, tr('Portrait id'), tr('Id (letters, digits, underscore):'),
                                       text=f'custom{n}')
        # the game lower-cases custom portrait ids when it scans the folder
        pid = (pid or '').strip().lower()
        if not ok or not re.fullmatch(r'[a-z0-9_]+', pid):
            return
        if pid in self.portraits and self.portraits[pid][0] != 'custom':
            QMessageBox.warning(self, tr('Portrait id'), tr('"{pid}" is a built-in portrait id.', pid=pid))
            return
        gamedata.import_portrait(path, pid)
        self.portraits = gamedata.portraits()
        self.selected = pid
        self.populate()
        QMessageBox.information(self, tr('Portrait imported'), tr(
            'Saved as "{pid}" in the CustomPortraits folder. Underrail reads custom portraits when it starts, '
            'so restart the game after saving.', pid=pid))

    def accept(self):
        it = self.view.currentItem()
        if it is not None:
            self.selected = it.data(Qt.UserRole)
        super().accept()


class CategoryFilter(QWidget):
    """Category filter in up to three steps: a category, optionally one of its subcategories (item path
    folders), and for vehicle parts their build size. The extra steps start at "all" and only show when
    the category offers a choice."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.cat = QComboBox()
        self.sub = QComboBox()
        self.size = QComboBox()
        for c in (self.sub, self.size):
            c.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        for c in (self.cat, self.sub, self.size):
            lay.addWidget(c)
        self.subs, self.sizes = {}, {}
        self.cat.currentIndexChanged.connect(self.fill_subs)
        self.sub.currentIndexChanged.connect(lambda _: self.changed.emit())
        self.size.currentIndexChanged.connect(lambda _: self.changed.emit())

    def set_categories(self, subs, sizes=None):
        """subs: {category: {subcategory, …}} ('' = none); sizes: {category: {build size, …}}.
        Keeps the current choice where possible."""
        cur_cat, cur_sub, cur_size = self.value()
        self.subs, self.sizes = subs, sizes or {}
        self.cat.blockSignals(True)
        self.cat.clear()
        self.cat.addItem(tr('all categories'), None)
        for c in sorted(subs):
            self.cat.addItem(c, c)
        self.cat.setCurrentIndex(max(0, self.cat.findData(cur_cat)) if cur_cat else 0)
        self.cat.blockSignals(False)
        self.fill_subs(keep=(cur_sub, cur_size))

    def fill_subs(self, _=None, keep=(None, None)):
        c = self.cat.currentData()
        names = sorted(self.subs.get(c, set()) - {''}, key=lambda s: tr(s).lower()) if c else []
        self.sub.blockSignals(True)
        self.sub.clear()
        self.sub.addItem(tr('all subcategories'), None)
        for s in names:
            self.sub.addItem(tr(s), s)
        self.sub.setCurrentIndex(max(0, self.sub.findData(keep[0])) if keep[0] else 0)
        self.sub.blockSignals(False)
        self.sub.setVisible(len(names) > 1)
        sizes = sorted(self.sizes.get(c, set()) - {None}) if c else []
        self.size.blockSignals(True)
        self.size.clear()
        self.size.addItem(tr('all sizes'), None)
        for s in sizes:
            self.size.addItem(tr(SIZES.get(s, str(s))), s)
        self.size.setCurrentIndex(max(0, self.size.findData(keep[1])) if keep[1] else 0)
        self.size.blockSignals(False)
        self.size.setVisible(len(sizes) > 1)
        self.changed.emit()

    def value(self):
        # a lone option isn't offered (count = 'all' + options)
        return (self.cat.currentData(), self.sub.currentData() if self.sub.count() > 2 else None,
                self.size.currentData() if self.size.count() > 2 else None)

    def matches(self, category, sub, size=None):
        c, s, z = self.value()
        return (c is None or category == c) and (s is None or (sub or '') == s) and (z is None or size == z)


# item rarity (I:Q) colours as in the game: common white (= default text colour here), uncommon green,
# rare blue, unique purple; junk grey; the quest-item tier gold
RARITY_COLORS = {0: (128, 128, 128), 2: (40, 160, 40), 3: (50, 110, 230), 4: (150, 70, 210), 5: (215, 150, 0)}
SIZES = {1: 'small', 2: 'medium', 3: 'large'}


def rarity_color(q):
    """QColor for an item rarity, or None for common items (default text colour)."""
    rgb = RARITY_COLORS.get(q)
    if rgb is None:
        return None
    c = QColor(*rgb)
    # brighter on dark themes
    if QApplication.palette().base().color().lightness() < 128:
        c = c.lighter(140)
    return c


def item_details(info):
    """Short extra attributes of a library item: build size and power of vehicle parts, item level."""
    parts = []
    if info.get('size'):
        parts.append(tr('size: {s}', s=tr(SIZES.get(info['size'], str(info['size'])))))
    if info.get('power'):
        parts.append(tr('power {p}', p=info['power']))
    if info.get('level'):
        parts.append(tr('level {level}', level=info['level']))
    return ', '.join(parts)


SIZE_WORDS = {1: 'small klein kleine kleinen kleiner kleines', 2: 'medium mittel mittlere mittleren mittlerer mittleres',
              3: 'large groß gross große großen großer großes grosse grossen'}


def search_text(info):
    """Everything a search can match for a library item: names, path, category and type (English and in the
    UI language), rarity, details with size words in all forms, and the game description."""
    if info is None:
        return ''
    sub = info.get('sub') or ''
    q = gamedata.QUALITY.get(info.get('quality'), '')
    parts = [info['name'], info['path'], info['category'], sub, tr(sub), q, tr(q) if q else '', item_details(info),
             SIZE_WORDS.get(info.get('size'), ''), info.get('desc') or '']
    return ' '.join(parts).lower()


def search_match(query, text):
    """All words of the query occur in the text; a word also matches without a German/English ending
    ("motoren" -> "motor")."""
    for word in query.lower().split():
        if word in text:
            continue
        for end in ('en', 'er', 'es', 'em', 'e', 'n', 's'):
            if word.endswith(end) and len(word) - len(end) >= 3 and word[:-len(end)] in text:
                break
        else:
            return False
    return True


class AddItemDialog(QDialog):
    def __init__(self, parent, save):
        super().__init__(parent)
        self.setWindowTitle(tr('Add item'))
        self.resize(980, 660)
        self.save = save
        self.db = sorted(gamedata.items().values(), key=lambda i: (i['name'].lower(), i['path'].lower()))
        self.texts = {i['path']: search_text(i) for i in self.db}

        # category, then optionally a subcategory (item path folder)
        self.cat = CategoryFilter()
        subs, sizes = {}, {}
        for i in self.db:
            subs.setdefault(i['category'], set()).add(i.get('sub') or '')
            if i.get('size'):
                sizes.setdefault(i['category'], set()).add(i['size'])
        self.cat.set_categories(subs, sizes)
        self.cat.changed.connect(self.refilter)
        self.search = filter_box(tr('Search name, type, size, rarity, description…'), self.refilter)
        top = QHBoxLayout()
        top.addWidget(self.cat); top.addWidget(self.search, 1)

        cols = [tr('Name'), tr('Category'), tr('Type'), tr('Rarity'), tr('Details'), tr('Path')]
        self.table = QTableWidget(len(self.db), len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setIconSize(QSize(33, 33))
        self.table.verticalHeader().setDefaultSectionSize(36)
        for row, i in enumerate(self.db):
            cell = SortItem(i['name'])
            cell.setData(Qt.UserRole, row)
            icon, placeholder = item_icon(i.get('vm'), i['category'], i['cls'], i.get('wtype'))
            tip = f"<b>{html_escape(i['name'])}</b>"
            q = gamedata.QUALITY.get(i['quality'])
            if q:
                tip += f' · {html_escape(tr(q))}'
            details = item_details(i)
            if details:
                tip += f'<br>{html_escape(details)}'
            if i['desc']:
                tip += f"<p>{html_escape(i['desc'])}</p>"
            if icon:
                cell.setIcon(icon)
                if placeholder:
                    tip += '<p><i>' + html_escape(tr('(placeholder icon – the game has no icon for this item)')) + '</i></p>'
            cell.setToolTip(tip)
            color = rarity_color(i['quality'])
            if color:
                cell.setForeground(color)
            self.table.setItem(row, 0, cell)
            self.table.setItem(row, 1, SortItem(i['category']))
            self.table.setItem(row, 2, SortItem(tr(i.get('sub') or '')))
            rc = SortItem(tr(q) if q else '', i['quality'] if i['quality'] is not None else -1)
            if color:
                rc.setForeground(color)
            self.table.setItem(row, 3, rc)
            self.table.setItem(row, 4, SortItem(details, (i.get('size') or 0, i.get('power') or 0, i.get('level') or 0)))
            self.table.setItem(row, 5, SortItem(i['path']))
        self.table.resizeColumnsToContents()
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        # the path is long and rarely needed; keep it narrow so names have room
        head.setSectionResizeMode(5, QHeaderView.Interactive)
        self.table.setColumnWidth(5, 200)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.AscendingOrder)
        self.table.itemSelectionChanged.connect(self.selected)
        self.table.doubleClicked.connect(lambda _: self.accept())

        self.desc = QLabel(wordWrap=True)
        self.count_label = QLabel(tr('Stack size'))
        self.count = QSpinBox(); self.count.setRange(1, INT_MAX)
        self.dur = QDoubleSpinBox(); self.dur.setRange(0, 1e7); self.dur.setDecimals(1)
        self.dur_hint = QLabel()
        self.quality = QSpinBox(); self.quality.setRange(0, MAX_QUALITY)
        self.quality.setToolTip(tr('Component quality. The game has no upper limit; above {n} the quality bonus '
                                   'curve stops rising, but higher values still scale the stats linearly.',
                                   n=QUALITY_CURVE_END))
        self.quality_label = QLabel(tr('Quality'))
        self.quality_hint = QLabel()
        form = QFormLayout()
        form.addRow(self.count_label, self.count)
        dl = QHBoxLayout(); dl.addWidget(self.dur); dl.addWidget(self.dur_hint, 1)
        form.addRow(tr('Durability'), dl)
        ql = QHBoxLayout(); ql.addWidget(self.quality); ql.addWidget(self.quality_hint, 1)
        form.addRow(self.quality_label, ql)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr('Add'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(top); lay.addWidget(self.table, 1); lay.addWidget(self.desc)
        lay.addLayout(form); lay.addWidget(buttons)

    def refilter(self, *_):
        q = self.search.text().lower()
        if not hasattr(self, 'table'):
            return
        for row in range(self.table.rowCount()):
            i = self.db[self.table.item(row, 0).data(Qt.UserRole)]
            hide = not self.cat.matches(i['category'], i.get('sub'), i.get('size')) or (q and not search_match(q, self.texts[i['path']]))
            self.table.setRowHidden(row, bool(hide))

    def current(self):
        rows = self.table.selectionModel().selectedRows()
        return self.db[self.table.item(rows[0].row(), 0).data(Qt.UserRole)] if rows else None

    def stackable(self):
        i = self.current()
        return bool(i and i['stack'] and i['stack'] > 1)

    def default_quality(self, i):
        """Quality for a new component: the best of the same item the character already has, else 100 for
        components whose stats scale with quality (0 for the rest, which ignore it)."""
        have = [f.value for it in self.save.inventory() if it.path and it.path.lower() == i['path'].lower()
                for f in it.fields() if f.name == 'Quality']
        if have and max(have) > 0:
            return max(have), tr('like the one you have')
        if i.get('quality_scaled'):
            return 100, tr('typical value')
        return 0, tr('quality has no effect on this item')

    def selected(self):
        i = self.current()
        if not i:
            return
        q = gamedata.QUALITY.get(i['quality'], '')
        details = item_details(i)
        self.desc.setText(f"<b>{html_escape(i['name'])}</b> {('· ' + html_escape(tr(q))) if q else ''}"
                          f"{(' · ' + html_escape(details)) if details else ''} · "
                          f"{tr('max stack {n}', n=i['stack'])}<br>{html_escape(i['desc'])}")
        # non-stackable items are added as separate copies instead of one oversized stack
        self.count_label.setText(tr('Stack size') if self.stackable() else tr('Copies'))
        self.count.setMaximum(i['stack'] if self.stackable() else 50)
        d = self.save.default_durability(i['path'])
        self.dur.setEnabled(d is not None)
        self.dur.setValue(d or 0.0)
        self.dur_hint.setText(tr('full = {d}', d=f'{d:g}') if d is not None else tr("doesn't wear down"))
        comp = us.INSTANCE_CLASS.get(i['cls']) == 'CII'
        self.quality.setEnabled(comp)
        self.quality_label.setEnabled(comp)
        if comp:
            value, why = self.default_quality(i)
            self.quality.setValue(value)
            self.quality_hint.setText(why)
        else:
            self.quality.setValue(0)
            self.quality_hint.setText('')


class FoldersDialog(QDialog):
    """Choose the Underrail installation and the user folder (the one containing Saves)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr('Game folders'))
        self.resize(760, 220)
        game, user = paths.resolve()
        self.game = QLineEdit(game or '')
        self.user = QLineEdit(user or '')
        self.game_ok, self.user_ok = QLabel(), QLabel()
        form = QFormLayout()
        for label, edit, ok, title in ((tr('Game installation'), self.game, self.game_ok,
                                        tr('Folder containing underrail.exe')),
                                       (tr('User folder'), self.user, self.user_ok,
                                        tr('Folder containing "Saves" (Documents/My Games/Underrail)'))):
            row = QHBoxLayout()
            row.addWidget(edit, 1)
            browse = QPushButton(tr('Browse…'))
            browse.clicked.connect(lambda _=False, e=edit, t=title: self.browse(e, t))
            row.addWidget(browse)
            form.addRow(label, row)
            form.addRow('', ok)
            edit.textChanged.connect(self.validate)
        auto = QPushButton(tr('Detect automatically'))
        auto.clicked.connect(self.detect)
        hint = QLabel(tr('Steam (also on Steam Deck / SD cards / Flatpak), GOG and Proton/Wine prefixes are '
                         'searched automatically. Pick the folders yourself if they are somewhere else.'))
        hint.setWordWrap(True)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(hint); lay.addLayout(form); lay.addWidget(auto); lay.addWidget(self.buttons)
        self.validate()

    def browse(self, edit, title):
        d = QFileDialog.getExistingDirectory(self, title, edit.text() or os.path.expanduser('~'))
        if d:
            edit.setText(d)

    def detect(self):
        g, u = paths.detect()
        if g:
            self.game.setText(g)
        if u:
            self.user.setText(u)
        self.validate()

    def validate(self, *_):
        g_ok, u_ok = paths.is_game_dir(self.game.text()), paths.is_user_dir(self.user.text())
        self.game_ok.setText('✓ ' + tr('found') if g_ok else '✗ ' + tr('underrail.exe not found here'))
        self.user_ok.setText('✓ ' + tr('found') if u_ok else '✗ ' + tr('no "Saves" folder here'))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(g_ok and u_ok)

    def accept(self):
        paths.set_dirs(self.game.text(), self.user.text())
        gamedata.configure()
        super().accept()


# --- tabs ---------------------------------------------------------------------------------

class CharacterTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        s = main.save
        self.name = QLineEdit(s.name)
        self.name.editingFinished.connect(self.rename)
        self.portrait = QLabel()
        self.portrait.setFixedSize(100, 100)
        self.portrait_id = QLabel()
        change = QPushButton(tr('Change…'))
        change.clicked.connect(self.pick_portrait)
        pl = QHBoxLayout()
        pl.addWidget(self.portrait); pl.addWidget(self.portrait_id); pl.addWidget(change); pl.addStretch()
        form = QFormLayout()
        form.addRow(tr('Name'), self.name)
        form.addRow(tr('Level'), spin_for(s.level_field(), self.changed, 1, 100))
        form.addRow(tr('Portrait'), pl)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(QLabel(tr('Points / experience / vitals:')))
        lay.addWidget(FieldTable(main, s.points() + s.vitals()), 1)
        self.show_portrait()

    def changed(self, f, v):
        self.main.save.set(f, v)
        self.main.on_change()

    def rename(self):
        n = self.name.text().strip()
        if n and n != self.main.save.name:
            self.main.save.set_name(n)
            self.main.on_change()

    def show_portrait(self):
        pid = self.main.save.portrait
        self.portrait_id.setText(pid or '')
        p = gamedata.portraits().get(pid)
        pix = QPixmap()
        if p:
            try:
                pix = QPixmap(gamedata.portrait_png(pid, p[1]))
            except Exception:
                pass
        self.portrait.setPixmap(pix.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                if not pix.isNull() else QPixmap())
        if pix.isNull():
            self.portrait.setText(tr('(no preview)'))

    def pick_portrait(self):
        d = PortraitDialog(self, self.main.save.portrait)
        if d.exec() and d.selected and d.selected != self.main.save.portrait:
            self.main.save.set_portrait(d.selected)
            self.main.on_change()
            self.show_portrait()


def requirement_text(kind, d):
    """Human-readable form of one feat requirement (game terms stay as the game names them)."""
    feat = lambda f: gamedata.feat_name(f)
    if kind == 'attribute':
        return f"{d['attribute']} {d['min']}" + (f" ({tr('modified')})" if d.get('modified') else '')
    if kind == 'skill':
        return f"{(' ' + tr('or') + ' ').join(d['skills'])} {d['min']}" + \
            (f" ({tr('modified')})" if d.get('modified') else '')
    if kind == 'any_psi':
        return tr('Any psi skill {n}', n=d['min'])
    if kind == 'level':
        return tr('Level {n}', n=d['min'])
    if kind == 'feat':
        return tr('Feat: {names}', names=f" {tr('or')} ".join(feat(f) for f in d['feats']))
    if kind == 'not_feat':
        return tr('Not together with: {names}', names=', '.join(feat(f) for f in d['feats']))
    if kind == 'psi':
        return tr('Psi ability: {names}', names=f" {tr('or')} ".join(gamedata.split_camel(a) for a in d['abilities']))
    if kind == 'only_one_increased_base_ability':
        return tr('Only one "Increased <attribute>" feat')
    if kind == 'outside_leveling':
        return tr('Not available when leveling up (character creation, quests, trainers or events)')
    if kind == 'only_one_empowered_invocation':
        return tr('Only one "Empowered" invocation feat')
    return kind


def requirement_line(met, kind, d):
    text = requirement_text(kind, d)
    if not met and 'have' in d:
        text += ' – ' + tr('you have {n}', n=d['have'])
    if not met and d.get('clash'):
        text += ' – ' + tr('you have {names}', names=', '.join(gamedata.feat_name(f) for f in d['clash']))
    return ('✓ ' if met else '✗ ') + text


class ChecklistTab(QWidget):
    """Checkable list of everything in a game database; checked = present in the save. With `check`,
    entries whose requirements aren't met are marked and explained."""

    def __init__(self, main, db, owned, add, remove, note, learn_all=False, check=None):
        super().__init__()
        self.main, self.db, self.owned, self.add, self.remove = main, db, owned, add, remove
        self.check = check
        have = set(owned())
        self.count = QLabel()
        self.only = QCheckBox(tr('Only owned'))
        self.only.toggled.connect(self.refilter)
        self.available = QCheckBox(tr('Only available'))
        self.available.setToolTip(tr('Hide entries whose requirements your character does not meet'))
        self.available.toggled.connect(self.refilter)
        self.search = filter_box(tr('Filter…'), self.refilter)
        top = QHBoxLayout()
        top.addWidget(self.search, 1); top.addWidget(self.only)
        if check:
            top.addWidget(self.available)
        else:
            self.available.hide()
        if learn_all:
            btn = QPushButton(tr('Learn all'))
            btn.clicked.connect(self.learn_all)
            top.addWidget(btn)
        top.addWidget(self.count)
        self.list = QListWidget()
        name = lambda k: db[k][0] if k in db else k
        for key in sorted(set(db) | have, key=lambda k: name(k).lower()):
            it = QListWidgetItem(f'{name(key)}   ({key})')
            it.setData(Qt.UserRole, key)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if key in have else Qt.Unchecked)
            self.list.addItem(it)
        self.list.itemChanged.connect(self.toggled)
        self.list.currentItemChanged.connect(self.describe)
        self.desc = QTextBrowser()
        self.desc.setMaximumHeight(170)
        self.unmet = {}
        lay = QVBoxLayout(self)
        lay.addLayout(top); lay.addWidget(self.list, 1); lay.addWidget(self.desc)
        if note:
            lab = QLabel(tr(note))
            lab.setWordWrap(True)
            lay.addWidget(lab)
        self.update_count()
        self.update_marks()

    def update_marks(self):
        """Grey out entries whose requirements aren't met and explain why in the tooltip."""
        if not self.check:
            return
        self.list.blockSignals(True)
        grey = self.palette().color(self.palette().ColorGroup.Disabled, self.palette().ColorRole.Text)
        normal = self.palette().color(self.palette().ColorRole.Text)
        self.unmet = {}
        for i in range(self.list.count()):
            it = self.list.item(i)
            key = it.data(Qt.UserRole)
            res = self.check(key)
            missing = [requirement_line(*r) for r in res if not r[0]]
            name = self.db[key][0] if key in self.db else key
            if missing:
                self.unmet[key] = missing
                it.setText(f'⚠ {name}   ({key})')
                it.setForeground(grey)
                it.setToolTip(tr('Requirements not met:') + '\n' + '\n'.join(missing))
            else:
                it.setText(f'{name}   ({key})')
                it.setForeground(normal)
                it.setToolTip('\n'.join(requirement_line(*r) for r in res) if res else tr('No requirements'))
        self.list.blockSignals(False)
        self.refilter()
        cur = self.list.currentItem()
        if cur is not None:
            self.describe(cur, None)

    def showEvent(self, e):
        # attributes, skills or level may have changed on other tabs
        super().showEvent(e)
        self.update_marks()

    def update_count(self):
        self.count.setText(tr('{n} of {total} owned', n=len(self.owned()), total=len(self.db)))

    def refilter(self, *_):
        q, only, avail = self.search.text().lower(), self.only.isChecked(), self.available.isChecked()
        for i in range(self.list.count()):
            it = self.list.item(i)
            unavailable = it.data(Qt.UserRole) in self.unmet and it.checkState() != Qt.Checked
            it.setHidden(bool((only and it.checkState() != Qt.Checked) or (avail and unavailable)
                              or (q and q not in it.text().lower())))

    def describe(self, it, _):
        if it is not None:
            key = it.data(Qt.UserRole)
            text = self.db.get(key, (key, ''))[1] or tr('(no description)')
            if self.check:
                res = self.check(key)
                lines = [requirement_line(*r) for r in res]
                text += '\n\n' + tr('Requirements:') + ('\n' + '\n'.join(lines) if lines else ' ' + tr('none'))
            self.desc.setPlainText(text)

    def toggled(self, it):
        key = it.data(Qt.UserRole)
        owned = key in self.owned()
        try:
            if it.checkState() == Qt.Checked and not owned:
                self.add(key)
            elif it.checkState() != Qt.Checked and owned:
                self.remove(key)
            else:
                return
        except Exception as e:
            QMessageBox.warning(self, tr('Change failed'), str(e))
            return
        self.update_count()
        self.main.on_change()
        self.update_marks()  # feat prerequisites / exclusions depend on the owned feats

    def learn_all(self):
        # checking each item triggers toggled(), which adds the missing entries
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.Checked)


def feats_tab(main):
    s = main.save
    return ChecklistTab(main, gamedata.feats(), s.feats, s.add_feat, s.remove_feat,
                        'Feats marked ⚠ don\'t meet the game\'s requirements (checked against base values, '
                        'as the game does); they can still be added. Adding a feat only records it as learned.',
                        check=s.feat_check)


def blueprints_tab(main):
    s = main.save
    return ChecklistTab(main, gamedata.blueprints(), s.blueprints, s.add_blueprint, s.remove_blueprint,
                        'Known crafting blueprints. Blueprint items in the inventory are separate.',
                        learn_all=True)


class SpecsTab(QWidget):
    """Specializations. Following the game's rules, a spec belongs to a feat and is only available
    while the character has that feat; each spec has a maximum number of points."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.db = gamedata.specs()
        self.rules = gamedata.spec_rules()
        lay = QVBoxLayout(self)
        self.lay = lay
        self.table = None
        self.total = QLabel()
        add = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        self.combo.currentIndexChanged.connect(self.describe)
        self.value = QSpinBox(); self.value.setRange(0, 100); self.value.setValue(1)
        btn = QPushButton(tr('Add'))
        btn.clicked.connect(self.add)
        rm = QPushButton(tr('Remove selected'))
        rm.clicked.connect(self.remove)
        add.addWidget(QLabel(tr('Add:'))); add.addWidget(self.combo, 1); add.addWidget(self.value); add.addWidget(btn)
        add.addWidget(rm)
        self.desc = QLabel(wordWrap=True)
        self.note = QLabel(wordWrap=True)
        self.build()
        lay.addWidget(self.total)
        lay.addLayout(add)
        lay.addWidget(self.desc)
        lay.addWidget(self.note)

    def spec_max(self, key):
        return (self.rules.get(key) or {}).get('max')

    def spec_feat(self, key):
        return (self.rules.get(key) or {}).get('feat')

    def build(self):
        s = self.main.save
        owned = set(s.feats())
        fields = s.specs()
        for f in fields:
            f.info = self.db.get(f.name, (None, None))[1]

        def info(f):
            feat, mx = self.spec_feat(f.name), self.spec_max(f.name)
            text = gamedata.feat_name(feat) if feat else '?'
            if mx is not None:
                text += f' · max {mx}'
            if feat and feat not in owned:
                text = '⚠ ' + text + ' – ' + tr('feat missing')
            return text
        table = FieldTable(self.main, fields, 0, 100, tr('Feat · max'), info,
                           label=lambda f: gamedata.split_camel(f.name), after=self.update_total,
                           hi_of=lambda f: self.spec_max(f.name) if self.spec_max(f.name) is not None else 100)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        if self.table is not None:
            self.lay.replaceWidget(self.table, table)
            self.table.deleteLater()
        else:
            self.lay.insertWidget(0, table, 1)
        self.table = table
        have = {f.name for f in fields}
        self.combo.clear()
        hidden = 0
        for key, (name, _) in sorted(self.db.items(), key=lambda x: x[1][0].lower()):
            if key in have:
                continue
            feat = self.spec_feat(key)
            if feat and feat not in owned:
                hidden += 1  # the game only unlocks a spec together with its feat
                continue
            self.combo.addItem(name, key)
        self.combo.lineEdit().setPlaceholderText(
            tr('All specializations of your feats are already present') if not self.combo.count() else '')
        orphaned = [f.name for f in fields if self.spec_feat(f.name) and self.spec_feat(f.name) not in owned]
        notes = [tr('{n} specializations are hidden because the character lacks their feat.', n=hidden)] if hidden else []
        if orphaned:
            notes.append(tr('Specializations marked ⚠ belong to a feat the character doesn\'t have; the game '
                            'only uses them together with the feat.'))
        self.note.setText(' '.join(notes))
        self.update_total()
        self.describe()

    def showEvent(self, e):
        # feats may have been added or removed on the feats tab
        super().showEvent(e)
        self.build()

    def update_total(self):
        fields = self.table.fields
        self.total.setText(tr('{n} specializations, {points} points total', n=len(fields),
                              points=sum(f.value for f in fields)))

    def describe(self, *_):
        key = self.combo.currentData()
        self.desc.setText(self.db.get(key, ('', ''))[1] if key else '')
        mx = self.spec_max(key) if key else None
        self.value.setMaximum(mx if mx is not None else 100)

    def add(self):
        key = self.combo.currentData()
        if not key:
            return
        self.main.save.add_spec(key, self.value.value())
        self.main.on_change()
        self.build()

    def remove(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        f = self.table.fields[rows[0].row()]
        self.main.save.remove_spec(f.name)
        self.main.on_change()
        self.build()


class SortItem(QTableWidgetItem):
    """Table cell sorted by a key (numbers numerically, text case-insensitively).
    Cells covered by a spinbox keep their key in sync via set_key."""

    def __init__(self, text='', key=None):
        super().__init__(text)
        self.set_key(text if key is None else key)

    def set_key(self, key):
        self.setData(Qt.UserRole + 1, key.lower() if isinstance(key, str) else key)

    def __lt__(self, other):
        a, b = self.data(Qt.UserRole + 1), other.data(Qt.UserRole + 1)
        if isinstance(a, str) != isinstance(b, str):
            return isinstance(a, str)  # blanks in numeric columns sort below every number
        return a < b


class ItemTable(QTableWidget):
    """Sortable item table; rows remember their Item via the first column."""

    def __init__(self, tab, cols, sortable=True):
        super().__init__(0, len(cols))
        self.tab, self.cols, self.sortable = tab, cols, sortable
        self.setHorizontalHeaderLabels([tr(c) for c in cols])
        self.verticalHeader().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.horizontalHeader().setSortIndicatorShown(sortable)
        self.setIconSize(QSize(33, 33))
        self.verticalHeader().setDefaultSectionSize(36)

    def fill(self, items):
        self.setSortingEnabled(False)
        # drop old rows first, otherwise stale cell widgets linger after a rebuild
        self.clearContents()
        self.setRowCount(0)
        self.setRowCount(len(items))
        self.items = items
        for row, it in enumerate(items):
            fields = {f.name: f for f in it.fields()}
            mx = it.max_durability
            mb = it.max_battery
            w = it.weight
            tw = None if w is None else w * it.stack
            cells = {'Slot': tr(it.slot) if it.slot else '', 'Name': it.name, 'Category': it.category,
                     'Max': '' if mx is None else f'{mx:g}', 'Max bat.': '' if mb is None else f'{mb:g}',
                     'Crafted': '✓' if it.crafted else '', 'Weight': '' if w is None else f'{w:g}',
                     'Total weight': '' if tw is None else f'{tw:.2f}'.rstrip('0').rstrip('.')}
            for col, name in enumerate(self.cols):
                if name in cells:
                    key = {'Max': mx, 'Max bat.': mb, 'Weight': w, 'Total weight': tw}.get(name)
                    key = cells[name] if key is None else key
                    cell = SortItem(cells[name], key)
                    if name == 'Name':
                        cell.setData(Qt.UserRole, row)
                        color = rarity_color(it.rarity)
                        if color:
                            cell.setForeground(color)
                        path, placeholder = it.icon()
                        tip = it.path or tr('crafted item')
                        q = gamedata.QUALITY.get(it.rarity)
                        if q:
                            tip = f'{tr(q)} · {tip}'
                        desc = it.info['desc'] if it.info else ''
                        if desc:
                            tip += '\n\n' + desc
                        if path:
                            cell.setIcon(QIcon(path))
                            if placeholder:
                                tip += '\n' + tr('(placeholder icon – the game has no icon for this item)')
                        cell.setToolTip(tip)
                    self.setItem(row, col, cell)
                    continue
                f = fields.get(name)
                if f is None or (name == 'Durability' and mx is None) or (name == 'Battery' and mb is None):
                    self.setItem(row, col, SortItem('', ''))
                    continue
                cell = SortItem('', f.value)
                self.setItem(row, col, cell)
                hi = MAX_QUALITY if name == 'Quality' else (10**7 if f.is_float else INT_MAX)
                self.setCellWidget(row, col, spin_for(f, lambda fld, v, c=cell: self.changed(fld, v, c), 0, hi))
        self.resizeColumnsToContents()
        for col, name in enumerate(self.cols):
            if name in ('Stack', 'Quality', 'Durability', 'Battery'):
                self.setColumnWidth(col, max(self.columnWidth(col), 100))
        self.horizontalHeader().setSectionResizeMode(self.cols.index('Name'), QHeaderView.Stretch)
        self.setSortingEnabled(self.sortable)

    def changed(self, f, v, cell):
        cell.set_key(v)
        self.tab.main.save.set(f, v)
        self.tab.main.on_change()
        if f.name == 'Stack' and 'Total weight' in self.cols:
            row = self.indexFromItem(cell).row()
            it = self.item_at(row)
            if it.weight is not None:
                tw = it.weight * v
                c = self.item(row, self.cols.index('Total weight'))
                c.setText(f'{tw:.2f}'.rstrip('0').rstrip('.'))
                c.set_key(tw)
            if hasattr(self.tab, 'update_weight'):
                self.tab.update_weight()

    def item_at(self, row):
        return self.items[self.item(row, self.cols.index('Name')).data(Qt.UserRole)]

    def selected(self):
        return [self.item_at(r.row()) for r in self.selectionModel().selectedRows()]

    def all_rows(self):
        return [(row, self.item_at(row)) for row in range(self.rowCount())]


def compare_html(save, item):
    """Stats of an item next to the equipped item(s) of its slot, with coloured differences."""
    import html
    import itemstats
    esc = html.escape
    r = itemstats.save_reader(item)
    if r is None:
        return ''
    skills, strength = itemstats.character(save)
    mine = itemstats.stats(r, skills, strength)
    if not mine:
        return f'<p>{esc(tr("No comparable stats for this item."))}</p>'
    slots = itemstats.SLOT_OF_CLASS.get(r.o.cls, [])
    others = [it for it in save.equipped() if it.slot in slots and it.obj is not item.obj]
    other_stats = [{s.key: s for s in itemstats.stats(itemstats.save_reader(it), skills, strength)} for it in others]
    h = [f'<h3>{esc(item.name)}</h3>']
    if item.slot:
        h.append(f'<p><i>{esc(tr("Equipped ({slot})", slot=tr(item.slot)))}</i></p>')
    elif not others:
        h.append(f'<p><i>{esc(tr("Nothing equipped in this slot."))}</i></p>')
    h.append('<table cellspacing="0" cellpadding="3" border="1"><tr><th></th>'
             f'<th>{esc(tr("This item"))}</th>' +
             ''.join(f'<th>{esc(it.name)}<br><small>{esc(tr(it.slot))}</small></th>' for it in others) + '</tr>')
    # rows of every stat any of the items has; missing protection counts as 0
    keys = [s.key for s in mine]
    for st in other_stats:
        keys += [k for k in st if k not in keys]
    keys.sort(key=itemstats.order)
    by_key = {s.key: s for s in mine}
    for k in keys:
        if k not in by_key:
            o = next(st[k] for st in other_stats if k in st)
            zero = k.startswith(('dr_', 'dt_'))
            by_key[k] = itemstats.Stat(k, o.label, 0 if zero else None,
                                       ('0%' if k.startswith('dr_') else '0') if zero else '–', o.better)
    pct = ('crit', 'precision', 'penalty') + tuple(k for k in keys if k.startswith('dr_'))
    for s in (by_key[k] for k in keys):
        row = f'<tr><td>{esc(tr(s.label))}</td><td align="right"><b>{esc(s.text)}</b></td>'
        for st in other_stats:
            o = st.get(s.key)
            if o is None and s.key.startswith(('dr_', 'dt_')):
                o = itemstats.Stat(s.key, s.label, 0, '0%' if s.key.startswith('dr_') else '0', s.better)
            if o is None:
                row += '<td></td>'
                continue
            cell = esc(o.text)
            if isinstance(s.value, (int, float)) and isinstance(o.value, (int, float)) and s.better:
                d = s.value - o.value
                if abs(d) > 1e-9:
                    good = d * s.better > 0
                    txt = f'{d * 100:+.0f}%' if s.key in pct else (f'{d:+.2f}' if isinstance(d, float) and
                                                                    d != int(d) else f'{d:+g}')
                    cell += f' <span style="color:{"#2a2" if good else "#d33"}">({txt})</span>'
            row += f'<td align="right">{cell}</td>'
        h.append(row + '</tr>')
    h.append('</table>')
    h.append(f'<p><small>{esc(tr("Differences: this item minus the equipped one; green = better. Your damage per AP uses your effective skill from the save."))}</small></p>')
    return '\n'.join(h)


class InventoryTab(QWidget):
    COLS = ['Name', 'Category', 'Stack', 'Weight', 'Total weight', 'Quality', 'Durability', 'Max', 'Battery',
            'Max bat.', 'Crafted']

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.search = filter_box(tr('Filter…'), self.refilter)
        self.cat = CategoryFilter()
        self.cat.changed.connect(self.refilter)
        add = QPushButton(tr('Add item…')); add.clicked.connect(self.add)
        dup = QPushButton(tr('Duplicate')); dup.clicked.connect(self.duplicate)
        rm = QPushButton(tr('Remove')); rm.clicked.connect(self.remove)
        rep = QPushButton(tr('Repair')); rep.clicked.connect(lambda: self.repair(False))
        rep.setToolTip(tr('Set durability of the selected items (inventory and equipped) to full'))
        rep_all = QPushButton(tr('Repair all')); rep_all.clicked.connect(lambda: self.repair(True))
        top = QHBoxLayout()
        top.addWidget(self.cat); top.addWidget(self.search, 1)
        for b in (add, dup, rm, rep, rep_all):
            top.addWidget(b)
        self.table = ItemTable(self, self.COLS)
        # equipped items keep the game's slot order
        self.equip = ItemTable(self, ['Slot', 'Name', 'Weight', 'Durability', 'Max', 'Battery', 'Max bat.'],
                               sortable=False)
        self.weight = QLabel()
        top.addWidget(self.weight)
        eq = QGroupBox(tr('Equipped'))
        QVBoxLayout(eq).addWidget(self.equip)
        split = QSplitter(Qt.Vertical)
        inv = QWidget()
        il = QVBoxLayout(inv); il.setContentsMargins(0, 0, 0, 0)
        il.addLayout(top); il.addWidget(self.table)
        split.addWidget(inv); split.addWidget(eq)
        split.setSizes([450, 180])
        # comparison of the selected item with what is equipped in its slot
        self.compare = QTextBrowser()
        self.compare.setPlaceholderText(tr('Select a weapon or armor piece to compare it with your equipment.'))
        side = QSplitter()
        side.addWidget(split)
        side.addWidget(self.compare)
        side.setSizes([900, 420])
        QVBoxLayout(self).addWidget(side)
        self.table.itemSelectionChanged.connect(lambda: self.show_compare(self.table))
        self.equip.itemSelectionChanged.connect(lambda: self.show_compare(self.equip))
        self.build()

    def build(self):
        items = self.main.save.inventory()
        subs, sizes = {}, {}
        for i in items:
            if i.category:
                subs.setdefault(i.category, set()).add((i.info or {}).get('sub') or '')
                if (i.info or {}).get('size'):
                    sizes.setdefault(i.category, set()).add(i.info['size'])
        self.cat.set_categories(subs, sizes)
        self.table.fill(items)
        self.equip.fill(self.main.save.equipped())
        self.update_weight()
        self.refilter()

    def update_weight(self):
        """Total weight carried: inventory stacks plus equipped items."""
        save = self.main.save
        total = sum((it.weight or 0) * it.stack for it in save.inventory())
        worn = sum(it.weight or 0 for it in save.equipped())
        self.weight.setText(tr('Weight: {total} (+{worn} equipped)', total=f'{total:.1f}', worn=f'{worn:.1f}'))
        self.weight.setToolTip(tr('Sort by "Total weight" to see what weighs you down. Stacks count weight × stack size.'))

    def show_compare(self, table):
        sel = table.selected()
        self.compare.setHtml(compare_html(self.main.save, sel[0]) if sel else '')

    def refilter(self, *_):
        q = self.search.text().lower()
        if not hasattr(self, 'table'):
            return
        for row, it in self.table.all_rows():
            hide = not self.cat.matches(it.category, (it.info or {}).get('sub'), (it.info or {}).get('size')) or \
                (q and not search_match(q, f'{it.name} {it.category} '.lower() + search_text(it.info)))
            self.table.setRowHidden(row, bool(hide))

    def add(self):
        d = AddItemDialog(self, self.main.save)
        if d.exec():
            i = d.current()
            if not i:
                return
            stack, copies = (d.count.value(), 1) if d.stackable() else (1, d.count.value())
            try:
                for _ in range(copies):
                    self.main.save.add_item(i['path'], stack, d.dur.value(), d.quality.value())
            except Exception as e:
                QMessageBox.warning(self, tr('Add item'), str(e))
                return
            self.main.on_change()
            self.build()

    def duplicate(self):
        for it in self.table.selected():
            self.main.save.duplicate_item(it)
        self.main.on_change()
        self.build()

    def remove(self):
        sel = self.table.selected()
        if not sel:
            return
        names = ', '.join(i.name for i in sel[:5]) + ('…' if len(sel) > 5 else '')
        if QMessageBox.question(self, tr('Remove items'), tr('Remove {names}?', names=names)) != QMessageBox.Yes:
            return
        for it in sel:
            self.main.save.remove_item(it)
        self.main.on_change()
        self.build()

    def repair(self, everything):
        items = ([it for _, it in self.table.all_rows()] + [it for _, it in self.equip.all_rows()]) if everything \
            else self.table.selected() + self.equip.selected()
        n = 0
        for it in items:
            mx = it.max_durability
            f = next((f for f in it.fields() if f.name == 'Durability'), None)
            if mx is not None and f is not None and f.value < mx:
                self.main.save.set(f, mx)
                n += 1
        if n:
            self.main.on_change()
            self.build()
        self.main.status.setText(tr('Repaired {n} item(s)', n=n) + (tr(' – unsaved') if n else ''))


class MapScanJob(QRunnable):
    """Indexes items placed in the game's maps (about a minute, then cached)."""

    def __init__(self, signals):
        super().__init__()
        self.signals = signals

    def run(self):
        import hints
        import worldmap
        try:
            hints.map_index()
            for page in worldmap.PAGES:  # pre-render the world map pages
                worldmap.page_image(page)
        except Exception:
            pass
        try:
            self.signals.done.emit('maps', '')
        except RuntimeError:
            pass  # app is shutting down


class WorldMapView(QGraphicsView):
    """The game's world map (rendered from its own sprites), one page at a time. Marked zones are tinted
    and labelled; the rest of the map is dimmed while anything is marked. Wheel zooms, dragging pans,
    clicking a zone emits its marker index."""
    zone_clicked = Signal(int)

    def __init__(self):
        super().__init__()
        import worldmap
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QColor(12, 12, 16))
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.world = worldmap.world()
        self.page = None
        self.region = None
        self.cache = {}
        self.sel_items = []
        self.marks = {}
        self.selected = set()
        self.items_ = []
        self.press = None

    def set_page(self, page):
        """Show one map page: 'main' (Underrail) or 'sea' (Expedition's Black Sea)."""
        if page == self.page:
            return
        self.page = page
        self.redraw()

    def highlight(self, marks):
        """marks: {marker index: (QColor, count text, name)}"""
        self.marks = marks
        self.redraw()

    def page_data(self):
        """Per page, computed once: background pixmap and each zone's sprite (pixmap, PIL image, position)."""
        import worldmap
        from PIL.ImageQt import ImageQt
        key = (self.page, self.region)
        if key not in self.cache:
            path, origin = worldmap.page_image(self.page, self.region)
            sprites = {}
            for n, z in enumerate(self.world['zones']):
                if z['page'] != self.page or (self.region and worldmap.region(z['ids'][0]) != self.region):
                    continue
                r = worldmap.zone_sprite(n, origin)
                if r is not None:
                    img, (x, y) = r
                    sprites[n] = (QPixmap.fromImage(ImageQt(img)), img, x, y)
            self.cache[key] = (QPixmap(path), sprites)
        return self.cache[key]

    def redraw(self):
        import hints
        import worldmap
        from PIL.ImageQt import ImageQt
        if self.page is None:
            return
        self.scene_.clear()
        self.sel_items = []
        self.zone_items = {}
        pix, sprites = self.page_data()
        self.scene_.addPixmap(pix)
        self.setSceneRect(QRectF(pix.rect()))
        on_page = {n: m for n, m in self.marks.items() if self.world['zones'][n]['page'] == self.page}
        focus = set()
        on_page = {n: m for n, m in on_page.items() if n in sprites}
        if on_page:
            shade = self.scene_.addRect(QRectF(pix.rect()), QPen(Qt.NoPen), QColor(0, 0, 0, 150))
            shade.setZValue(1)
        for n, (spix, img, x, y) in sprites.items():
            z = self.world['zones'][n]
            reg = worldmap.region(z['ids'][0])
            names = sorted({hints.zone_name(i) for i in z['ids']})
            tip = '\n'.join(names + ([z['title']] if z['title'] else []) + [f'[{tr(reg)}]'])
            mark = on_page.get(n)
            if mark or n in focus:
                # the zone itself, undimmed
                sprite = self.scene_.addPixmap(spix)
                sprite.setPos(x, y); sprite.setZValue(2)
            if mark:
                color, text, name = mark
                # coloured tint over the zone's shape
                tint = img.copy()
                tint.paste((color.red(), color.green(), color.blue(), 255), (0, 0, *img.size))
                tint.putalpha(img.getchannel('A').point(lambda v: v * 0.55))
                t = self.scene_.addPixmap(QPixmap.fromImage(ImageQt(tint)))
                t.setPos(x, y); t.setZValue(3)
                cx, cy = x + img.width / 2, y + img.height / 2
                for label, size, dy in ((text, 13, 0), (name, 10, 18)):
                    if label:
                        self.label(label, size - 2, cx, cy, dy * 0.8, QColor(255, 255, 255), 5)
            # invisible hit area for tooltips and clicks; marked zones lie on top
            hit = self.scene_.addRect(QRectF(x + img.width * 0.15, y + img.height * 0.2,
                                             img.width * 0.7, img.height * 0.6), QPen(Qt.NoPen))
            hit.setZValue(6 if mark else 1.5)
            hit.setData(0, n)
            hit.setToolTip(tip)
            self.zone_items[n] = (x, y, img.width, img.height)
        self.draw_selection()

    def label(self, text, size, x, y, dy, color, zvalue):
        """Text centred on a scene point that keeps its size on screen at any zoom level."""
        lt = QGraphicsSimpleTextItem(text)
        f = lt.font(); f.setPointSize(size); f.setBold(True); lt.setFont(f)
        lt.setBrush(color)
        lt.setPen(QPen(QColor(0, 0, 0), 0.6))
        lt.setFlag(QGraphicsSimpleTextItem.ItemIgnoresTransformations)
        b = lt.boundingRect()
        lt.setPos(x, y)
        lt.setTransform(lt.transform().translate(-b.width() / 2, -b.height() / 2 + dy))
        lt.setZValue(zvalue)
        lt.setAcceptedMouseButtons(Qt.NoButton)
        self.scene_.addItem(lt)
        return lt

    def draw_selection(self):
        for it in self.sel_items:
            self.scene_.removeItem(it)
        self.sel_items = []
        for n in self.selected:
            if n in self.zone_items:
                x, y, w, h = self.zone_items[n]
                r = self.scene_.addRect(QRectF(x, y, w, h), QPen(QColor(255, 255, 255), 3))
                r.setZValue(4)
                self.sel_items.append(r)

    def set_region(self, region):
        """Show only one area (layer) of the world, None = everything."""
        import worldmap
        self.region = region
        slow = not worldmap.area_ready(self.page, region)
        if slow:  # the first view of an area renders it (cached afterwards)
            QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.redraw()
        finally:
            if slow:
                QApplication.restoreOverrideCursor()

    def select(self, indexes):
        """Outline the given markers and bring them into view."""
        self.selected = set(indexes)
        self.draw_selection()
        if indexes:
            self.show_markers(indexes, zoom=False)

    def show_markers(self, indexes, zoom=True):
        """Bring markers into view: zoom=True fits them (not closer than 1:1), otherwise keep the zoom
        level and only pan, zooming out if they don't fit."""
        rect = QRectF()
        for n in indexes:
            if n in self.zone_items:
                rect = rect.united(QRectF(*self.zone_items[n]))
        if rect.isNull():
            return
        rect = rect.adjusted(-150, -150, 150, 150)
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        if zoom or rect.width() > visible.width() or rect.height() > visible.height():
            vp = self.viewport().rect()
            if rect.width() < vp.width() and rect.height() < vp.height():
                rect = QRectF(rect.center() - QPointF(vp.width() / 2, vp.height() / 2), QSize(vp.width(), vp.height()))
            self.fitInView(rect, Qt.KeepAspectRatio)
        else:
            self.centerOn(rect.center())

    def fit_all(self):
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    def wheelEvent(self, e):
        f = 1.15 ** (e.angleDelta().y() / 120)
        self.scale(f, f)

    def mousePressEvent(self, e):
        self.press = e.position()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self.press is not None and (e.position() - self.press).manhattanLength() < 5:
            for it in self.items(e.position().toPoint()):
                if isinstance(it, QGraphicsRectItem) and it.data(0) is not None:
                    self.zone_clicked.emit(it.data(0))
                    break
        self.press = None


class LocationsDialog(QDialog):
    """All known sources of an item (merchants, spots in the game world, creatures to harvest) as a list
    and on the world map."""
    COLORS = {'merchant': QColor(80, 160, 255), 'found': QColor(255, 175, 50), 'creature': QColor(110, 210, 110)}

    def __init__(self, parent, info):
        super().__init__(parent)
        import hints
        import worldmap
        self.setWindowTitle(tr('Where to get {item}', item=info['name']))
        self.resize(1300, 800)
        loc = hints.locations(info)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr('Where'), tr('How'), tr('Count')])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.map = WorldMapView()
        self.by_marker = {}  # marker index -> tree items
        marks = {}  # marker index -> (kind, count)

        def zone_label(zid):
            m = worldmap.marker(zid)
            title = self.map.world['zones'][m]['title'] if m is not None else None
            name = hints.zone_name(zid)
            return f'{name} – {title}' if title and title != name else name

        def add(group, kind, text, how, count, zones):
            it = QTreeWidgetItem(group, [text, how, str(count) if count else ''])
            idx = sorted({m for m in (worldmap.marker(z) for z in zones) if m is not None})
            it.setData(0, Qt.UserRole, idx)
            if not idx:
                it.setToolTip(0, tr('This zone has no marker on the world map (dungeon or interior).') if zones
                              else tr('Location unknown: not placed in any map (appears through an event or quest).'))
                it.setForeground(0, QColor(140, 140, 140))
            for m in idx:
                self.by_marker.setdefault(m, []).append(it)
                k, c, names = marks.get(m, (kind, 0, []))  # first kind wins: merchants, found spots, creatures
                if k == kind:
                    c += sum(n for z, n in zones.items() if worldmap.marker(z) == m)
                    if kind == 'merchant':
                        names = names + [text.split(' (')[0]]
                marks[m] = (k, c, names)
            return it

        def merged(rows):
            """[(zone id, how, n)] -> [(label, how, n, {zone id: n})], zones with the same label combined"""
            out = {}
            for zid, how, n in rows:
                key = (zone_label(zid), how)
                total, zones = out.get(key, (0, {}))
                zones[zid] = zones.get(zid, 0) + n
                out[key] = (total + n, zones)
            return sorted(((lbl, how, n, z) for (lbl, how), (n, z) in out.items()), key=lambda r: -r[2])

        def group(text, n):
            g = QTreeWidgetItem(self.tree, [f'{text} ({n})'])
            f = g.font(0); f.setBold(True); g.setFont(0, f)
            g.setFirstColumnSpanned(True)
            g.setExpanded(True)
            return g

        if loc['merchants']:
            g = group(tr('Merchants'), len(loc['merchants']))
            for name, fixed, zones in loc['merchants']:
                add(g, 'merchant', name, tr('always in stock') if fixed else tr('random stock'), 0, zones)
        if loc['found']:
            # keeps the order of found_spots: fixed spots before random loot
            rows = merged(loc['found'])
            rows.sort(key=lambda r: hints.KIND_ORDER.index(r[1]) if r[1] in hints.KIND_ORDER else 9)
            g = group(tr('Found'), len(rows))
            for lbl, kind, cnt, zones in rows:
                add(g, 'found', lbl, tr(kind), cnt, zones)
        if loc['creature_zones']:
            rows = merged((z, '', n) for z, n in loc['creature_zones'].items())
            g = group(tr('Harvest from {creature}', creature=loc['creature']), len(rows))
            for lbl, _, cnt, zones in rows:
                add(g, 'creature', lbl, '', cnt, zones)
        if not hints.map_index_ready():
            QTreeWidgetItem(self.tree, [tr('Map locations: scanning…')])
        elif self.tree.topLevelItemCount() == 0:
            QTreeWidgetItem(self.tree, [tr('not placed in the game world (crafted, quest or event)')])
        for c in range(3):
            self.tree.resizeColumnToContents(c)
        self.tree.setColumnWidth(0, min(self.tree.columnWidth(0), 380))

        # zone names next to the markers only while they don't crowd the map; merchants are few
        crowded = len(marks) > 12
        self.map.highlight({m: (self.COLORS[k], str(c) if k != 'merchant' and c > 1 else '',
                                ', '.join(names) if names else
                                '' if crowded else hints.zone_name(self.map.world['zones'][m]['ids'][0]))
                            for m, (k, c, names) in marks.items()})
        self.marked = sorted(marks)
        self.tree.currentItemChanged.connect(self.picked)
        self.map.zone_clicked.connect(self.clicked)

        legend = QLabel('  '.join(f'<span style="color:{self.COLORS[k].name()}">■</span> {tr(t)}' for k, t in
                                  (('merchant', 'Merchant'), ('found', 'Found in the world'),
                                   ('creature', 'Creature'))) +
                        '  —  ' + tr('Numbers: how many. Wheel zooms, drag pans, click a zone for its entries.') +
                        ' ' + tr('Zones without a place on the world map (dungeons, interiors) are greyed out in the list.'))
        legend.setWordWrap(True)
        # one button per map page, with how many marked zones it has
        zones = self.map.world['zones']
        per_page = {p: sum(1 for m in self.marked if zones[m]['page'] == p) for p in worldmap.PAGES}
        pages = QHBoxLayout()
        self.page_buttons = {}
        for p, label in (('main', 'Underrail'), ('sea', tr('Black Sea (Expedition)'))):
            b = QPushButton(f'{label} ({per_page[p]})')
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, p=p: (self.region.setCurrentIndex(0), self.show_page(p)))
            pages.addWidget(b)
            self.page_buttons[p] = b
        pages.addStretch(1)
        # focus one area of the world: the rest of the map is dimmed and its name highlighted
        self.region = QComboBox()
        self.region.addItem(tr('All areas'), None)
        per_area = {}
        for m in self.marked:
            a = worldmap.region(zones[m]['ids'][0])
            per_area[a] = per_area.get(a, 0) + 1
        for name in sorted({n for _, n in worldmap.REGIONS}, key=lambda n: tr(n)):
            self.region.addItem(tr(name) + (f' ({per_area[name]})' if name in per_area else ''), name)
        self.region.currentIndexChanged.connect(self.pick_region)
        pages.addWidget(QLabel(tr('Area:')))
        pages.addWidget(self.region)
        self.start_page = 'sea' if per_page['sea'] > per_page['main'] else 'main'
        self.show_page(self.start_page, fit=False)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addLayout(pages)
        rl.addWidget(self.map, 1)
        rl.addWidget(legend)
        split = QSplitter()
        split.addWidget(self.tree)
        split.addWidget(right)
        split.setSizes([450, 850])
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(split, 1)
        lay.addWidget(buttons)

    def showEvent(self, e):
        super().showEvent(e)
        # fit once the view has its real size
        QTimer.singleShot(0, lambda: self.show_page(self.start_page))

    def pick_region(self, _):
        import worldmap
        name = self.region.currentData()
        zones = self.map.world['zones']
        idx = [n for n, z in enumerate(zones) if name and worldmap.region(z['ids'][0]) == name]
        if idx:
            page = max(worldmap.PAGES, key=lambda p: sum(1 for n in idx if zones[n]['page'] == p))
            if page != self.map.page:
                self.show_page(page, fit=False)
        self.map.set_region(name)
        if idx:
            self.map.show_markers(idx)

    def show_page(self, page, fit=True):
        self.map.set_page(page)
        for p, b in self.page_buttons.items():
            b.setChecked(p == page)
        if fit:
            on_page = [m for m in self.marked if self.map.world['zones'][m]['page'] == page]
            if on_page:
                self.map.show_markers(on_page)
            else:
                self.map.fit_all()

    def picked(self, cur, _prev):
        idx = cur.data(0, Qt.UserRole) if cur is not None else None
        idx = set(idx or [])
        pages = {self.map.world['zones'][m]['page'] for m in idx}
        if idx and self.map.page not in pages:
            self.show_page(pages.pop(), fit=False)
        self.map.select(idx)

    def clicked(self, m):
        items = self.by_marker.get(m)
        if items:
            self.tree.setCurrentItem(items[0])
            self.tree.scrollToItem(items[0])
            # other entries of the same zone stay visible as a selection
            for it in items:
                it.setSelected(True)


class WeaponsPanel(QWidget):
    """All weapons with their base stats and the character's damage per AP: library weapons plus the
    character's own (crafted ones too). Sortable by every column, filterable by family, text, Strength
    and ownership."""
    COLS = [('name', 'Weapon'), ('family', 'Type'), ('damage', 'Damage'), ('ap', 'AP'), ('per_ap', 'Dmg/AP'),
            ('your_per_ap', 'Your dmg/AP'), ('crit', 'Crit'), ('crit_dmg', 'Crit dmg'), ('precision', 'Precision'),
            ('strength', 'Strength'), ('range', 'Range'), ('max_range', 'Max range'), ('magazine', 'Magazine'),
            ('level', 'Level'), ('weight', 'Weight'), ('owned', 'Owned')]

    def __init__(self, hints_tab):
        super().__init__()
        self.tab = hints_tab
        self.family = QComboBox()
        self.family.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.family.currentIndexChanged.connect(self.refilter)
        self.search = filter_box(tr('Filter…'), self.refilter)
        self.usable = QCheckBox(tr('Only usable with my Strength'))
        self.usable.toggled.connect(self.refilter)
        self.owned = QCheckBox(tr('Only my weapons'))
        self.owned.toggled.connect(self.refilter)
        where = QPushButton(tr('Where to get…'))
        where.clicked.connect(self.where)
        top = QHBoxLayout()
        for w in (self.family, self.search):
            top.addWidget(w)
        top.addWidget(self.usable); top.addWidget(self.owned); top.addWidget(where)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels([tr(c) for _, c in self.COLS])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setIconSize(QSize(33, 33))
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.doubleClicked.connect(lambda _: self.where())
        note = QLabel(tr('Your dmg/AP = damage × (1 + 0.7 × effective skill / 100), 0.5 for pistols and knives '
                         '(game wiki), with the effective skill stored in the save. Burst weapons count all shots; '
                         'ammo, feats and precision are left out. ⚠ = Strength too low (less precision).'))
        note.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addLayout(top); lay.addWidget(self.table, 1); lay.addWidget(note)
        self.rows = None

    def load(self):
        """Collect rows once: library weapons and the character's own."""
        import builds
        import itemstats
        save = self.tab.main.save
        skills, self.strength = itemstats.character(save)
        rows, seen = [], set()
        own = []
        if save:
            own = [(it, 'equipped') for it in save.equipped() if it.category == 'weapons'] + \
                  [(it, 'inventory') for it in save.inventory() if it.category == 'weapons']
        for it, where in own:
            r = itemstats.save_reader(it)
            if r is None or r.o.cls != 'WI':
                continue
            rows.append({'name': it.name, 'info': it.info, 'item': it, 'owned': tr(where),
                         'family': itemstats.weapon_family(r),
                         'stats': {s.key: s for s in itemstats.stats(r, skills, self.strength)}})
        for info in gamedata.items().values():
            if info['cls'] != 'WI' or info['name'] in seen:
                continue
            seen.add(info['name'])
            fam = builds.library_family(info)
            if fam is None:
                continue  # creature weapons
            r = itemstats.library_reader(info)
            if r is None:
                continue
            rows.append({'name': info['name'], 'info': info, 'item': None, 'owned': '', 'family': fam,
                         'stats': {s.key: s for s in itemstats.stats(r, skills, self.strength)}})
        self.rows = rows
        families = sorted({r['family'] for r in rows if r['family']})
        self.family.blockSignals(True)
        self.family.clear()
        self.family.addItem(tr('Weapons of the build'), 'build')
        self.family.addItem(tr('All weapons'), None)
        for f in families:
            self.family.addItem(tr(f), f)
        self.family.blockSignals(False)
        self.fill()

    def fill(self):
        t = self.table
        t.setSortingEnabled(False)
        t.clearContents()
        t.setRowCount(len(self.rows))
        for row, r in enumerate(self.rows):
            for col, (key, _) in enumerate(self.COLS):
                if key == 'name':
                    cell = SortItem(r['name'])
                    cell.setData(Qt.UserRole, row)
                    vm = r['item'].visual if r['item'] else (r['info'] or {}).get('vm')
                    path = gamedata.icon_path(vm)
                    if path:
                        cell.setIcon(QIcon(path))
                elif key == 'family':
                    cell = SortItem(tr(r['family'] or ''))
                elif key == 'owned':
                    cell = SortItem(r['owned'])
                else:
                    s = r['stats'].get(key)
                    cell = SortItem(s.text if s else '', s.value if s and s.value is not None else '')
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if key == 'strength' and s and '⚠' in s.text:
                        cell.setForeground(QColor(220, 90, 40))
                    if key in ('per_ap', 'your_per_ap'):
                        f = cell.font(); f.setBold(True); cell.setFont(f)
                if r['owned']:
                    cell.setBackground(QColor(80, 160, 255, 40))
                t.setItem(row, col, cell)
        t.resizeColumnsToContents()
        t.setSortingEnabled(True)
        t.sortItems([k for k, _ in self.COLS].index('your_per_ap'), Qt.DescendingOrder)
        self.refilter()

    def refilter(self, *_):
        import builds
        if self.rows is None:
            return
        fam = self.family.currentData()
        if fam == 'build':
            build = builds.BY_ID.get(self.tab.build.currentData())
            allowed = set(build['families']) if build and build['families'] else None
        else:
            allowed = {fam} if fam else None
        q = self.search.text().lower()
        for row in range(self.table.rowCount()):
            r = self.rows[self.table.item(row, 0).data(Qt.UserRole)]
            s = r['stats'].get('strength')
            hide = (allowed is not None and r['family'] not in allowed) or \
                (q and q not in r['name'].lower() and q not in tr(r['family'] or '').lower()) or \
                (self.usable.isChecked() and s and s.value and self.strength is not None and s.value > self.strength) or \
                (self.owned.isChecked() and not r['owned'])
            self.table.setRowHidden(row, bool(hide))

    def where(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        r = self.rows[self.table.item(rows[0].row(), 0).data(Qt.UserRole)]
        if not r['info']:
            QMessageBox.information(self, tr('Where to get…'), tr('Crafted weapons only come from crafting.'))
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            dlg = LocationsDialog(self, r['info'])
        finally:
            QApplication.restoreOverrideCursor()
        dlg.exec()


class HintsTab(QWidget):
    """Best weapons and armor combinations computed from the game data, with merchants that sell them
    and where they lie in the game world."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self.open_link)
        self.links = []  # item infos behind the "loc:<n>" links of the current page
        self.build = QComboBox()
        self.build.setToolTip(tr('The build decides which weapons are listed and how armor penalty is weighed. '
                                 'Auto picks it from skills, feats and equipped weapons.'))
        self.build.currentIndexChanged.connect(lambda _: self.built and (self.refresh(), self.weapons.refilter()))
        top = QHBoxLayout()
        top.addWidget(QLabel(tr('Build:')))
        top.addWidget(self.build)
        top.addStretch(1)
        self.weapons = WeaponsPanel(self)
        self.sub = QTabWidget()
        self.sub.addTab(self.weapons, tr('Weapons'))
        self.sub.addTab(self.view, tr('Build and armor'))
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.sub)
        self.fill_builds()
        self.built = False
        self.scanning = False
        portrait_signals().done.connect(self.scanned)

    def showEvent(self, e):
        super().showEvent(e)
        if not self.built:  # computed on first view only
            self.built = True
            import hints
            import worldmap
            if not (hints.map_index_ready() and worldmap.pages_ready()) and not self.scanning:
                self.scanning = True
                QThreadPool.globalInstance().start(MapScanJob(portrait_signals()))
            self.refresh()
            self.weapons.load()

    def fill_builds(self):
        import builds
        detected = builds.detect(self.main.save)[0][0] if self.main.save else None
        self.build.blockSignals(True)
        self.build.clear()
        if detected:
            self.build.addItem(tr('Auto: {build}', build=tr(detected['name'])), detected['id'])
        for b in builds.BUILDS:
            self.build.addItem(tr(b['name']), b['id'])
        self.build.blockSignals(False)

    def refresh(self):
        try:
            bar = self.view.verticalScrollBar().value()
            self.view.setHtml(self.render())
            self.view.verticalScrollBar().setValue(bar)
        except Exception as ex:
            self.view.setPlainText(tr('Could not compute hints: {e}', e=ex))

    def scanned(self, kind, _):
        if kind == 'maps':
            self.scanning = False
            if self.built:
                self.refresh()

    def sellers(self, info, limit=6):
        import html
        import hints
        self.links.append(info)
        href = f'loc:{len(self.links) - 1}'

        def more(n):
            return f'<a href="{href}">{html.escape(tr("+{n} more", n=n))}</a>'
        fixed, random_ = hints.where_to_buy(info)
        parts = [f'<b>{html.escape(n)}</b>' for n in fixed]
        rest = random_[:max(0, limit - len(parts))]
        parts += [html.escape(n) for n in rest]
        hidden = len(fixed) + len(random_) - len(parts)
        if hidden > 0:
            parts.append(more(hidden))
        text = (tr('Merchants') + ': ' + ', '.join(parts)) if parts else tr('No merchant')
        found = hints.where_found(info)
        if found is None:
            text += '<br><i>' + html.escape(tr('Map locations: scanning…')) + '</i>'
        else:
            rows, total = found
            if rows:
                spots = [f'{html.escape(z)} ({html.escape(tr(k))}{" ×" + str(c) if c > 1 else ""})' for z, k, c in rows]
                if total > len(rows):
                    spots.append(more(total - len(rows)))
                text += '<br>' + tr('Found') + ': ' + ', '.join(spots)
            elif not parts:
                text += '<br>' + html.escape(tr('not placed in the game world (crafted, quest or event)'))
            creature = hints.source_creature(info) if info.get('category') == 'components' else None
            if creature:
                zones, total = hints.creature_zones(creature)
                if zones:
                    spots = [f'{html.escape(z)}{" ×" + str(c) if c > 1 else ""}' for z, c in zones]
                    if total > len(zones):
                        spots.append(more(total - len(zones)))
                    text += '<br>' + tr('Harvest from {creature}', creature=html.escape(creature)) + ': ' + ', '.join(spots)
            text += f'<br><a href="{href}">{html.escape(tr("All locations on the map…"))}</a>'
        return text

    def open_link(self, url):
        s = url.toString()
        if s.startswith('loc:'):
            try:
                info = self.links[int(s[4:])]
            except (ValueError, IndexError):
                return
            QApplication.setOverrideCursor(Qt.WaitCursor)  # the first map render takes a while
            try:
                dlg = LocationsDialog(self, info)
            finally:
                QApplication.restoreOverrideCursor()
            dlg.exec()

    def build_section(self, build, profile):
        """The chosen build: what defines it and how the character measures up."""
        import html
        import builds
        esc = html.escape
        save = self.main.save
        h = [f'<h2>{esc(tr("Build: {build}", build=tr(build["name"])))}</h2>', f'<p>{esc(tr(build["note"]))}</p>']
        if save is None:
            return h
        attrs = {f.name: f.value for f in save.attributes()}
        skills = {f.name: f.value for f in save.skills()}
        feats = set(save.feats())
        names = gamedata.feats()
        h.append('<table cellpadding="2">')
        h.append(f'<tr><td><b>{esc(tr("Main attributes"))}</b></td><td>' +
                 ', '.join(f'{esc(a)} {attrs.get(a, "?")}' for a in build['attributes']) + '</td></tr>')
        h.append(f'<tr><td><b>{esc(tr("Key skills"))}</b></td><td>' +
                 ', '.join(f'{esc(s)} {skills.get(s, "?")}' for s in build['skills']) + '</td></tr>')
        marks = []
        for fid in build['feats']:
            name = esc(names.get(fid, (fid,))[0])
            if fid in feats:
                marks.append(f'<span style="color:#3a3">✓ {name}</span>')
            else:
                unmet = any(not met for met, kind, _ in save.feat_check(fid) if kind != 'outside_leveling')
                marks.append(f'{name} ⚠' if unmet else name)
        h.append(f'<tr><td valign="top"><b>{esc(tr("Key feats"))}</b></td><td>{", ".join(marks)}</td></tr>')
        # equipment check: weapons of the build's families, total armor penalty within the profile
        weapons = [(it.name, builds.item_family(it)) for it in save.equipped()
                   if it.category == 'weapons' and it.slot and it.slot.startswith('Weapon')]
        if weapons:
            txt = ', '.join(f'{esc(n)} ({esc(tr(f or "?"))})' for n, f in weapons)
            fits = any(f in build['families'] for _, f in weapons) or not build['families']
            txt += ' – ' + (esc(tr('fits the build')) if fits else
                            f'<span style="color:#c60">{esc(tr("no weapon of this build equipped"))}</span>')
            h.append(f'<tr><td><b>{esc(tr("Equipped weapons"))}</b></td><td>{txt}</td></tr>')
        penalty = equipped_armor_penalty(save)
        cap = profile['max_penalty']
        txt = f'{penalty * 100:.0f}%'
        if cap is not None and penalty > cap + 1e-9:
            txt += f' – <span style="color:#c60">{esc(tr("above the {cap}% this build usually accepts", cap=round(cap * 100)))}</span>'
        h.append(f'<tr><td><b>{esc(tr("Armor penalty worn"))}</b></td><td>{txt}</td></tr>')
        h.append('</table>')
        h.append(f'<p><i>{esc(tr("Builds are the archetypes players commonly describe (Steam guides, underrail.info, RPG Codex); ⚠ = requirements not met yet."))}</i></p>')
        return h

    def render(self):
        import html
        import builds
        import hints
        esc = html.escape
        self.links = []
        build = builds.BY_ID.get(self.build.currentData()) or builds.BUILDS[0]
        profile = builds.ARMOR_PROFILES[build['armor']]
        h = [f'<p>{esc(tr("Computed from your game files with the formulas the game uses. Armor values at component quality {q}; merchants in bold always stock the item, the others may roll it in their random stock.", q=hints.QUALITY))}</p>']
        if not hints.map_index_ready():
            h.append(f'<p><b>{esc(tr("Scanning the game maps for item locations (about a minute, only once)…"))}</b></p>')
        else:
            h.append(f'<p><i>{esc(tr("Found: where the item lies in the game world – in a container, on the ground, carried by an NPC (loot when defeated), as a job reward, or as possible random loot of a container."))}</i></p>')
        h += self.build_section(build, profile)
        feats = set(self.main.save.feats()) if self.main.save else set()
        notes = []
        if 'armorsloping' in feats:
            notes.append(tr('You have Armor Sloping: metal plates cost you about 35% less armor penalty than listed (more with its specialization).'))
        if 'ballistics' in feats:
            notes.append(tr('You have Ballistics: carrier vests add extra mechanical damage threshold.'))
        if 'juggernaut' in feats:
            notes.append(tr('You have Juggernaut: +25% health only while the armor penalty of your suit is at least 50%.'))
        if notes:
            h.append('<ul>' + ''.join(f'<li>{esc(n)}</li>' for n in notes) + '</ul>')

        h.append(f'<p><i>{esc(tr("Weapons: see the Weapons tab – sortable by every stat and filtered to this build."))}</i></p>')
        comps = hints.components()
        strength = None
        if self.main.save:
            strength = {f.name: f.value for f in self.main.save.attributes()}.get('Strength')
        h.append(f'<h2>{esc(tr("Best armor combinations (protection vs. armor penalty)"))}</h2>')
        cap = profile['max_penalty']
        h.append(f'<p>{esc(tr({"light": "Light armor build: armor penalty weighs heavily, combinations above {cap}% are left out.", "medium": "Balanced: protection and armor penalty both count, combinations above {cap}% are left out.", "heavy": "Heavy armor build: protection first, armor penalty counts little."}[build["armor"]], cap=round((cap or 0) * 100)))}'
                 + (' ' + esc(tr('Only combinations your Strength ({s}) can wear.', s=strength)) if strength else '') + '</p>')
        h.append(f'<p><i>{esc(tr("Armor penalty doesn\'t depend on quality – quality only raises protection. Penalties of worn pieces add up. Values: resistance %/threshold."))}</i></p>')
        used = {}
        for recipe in profile['recipes']:
            res_list = hints.armor_combos(recipe, 3, comps, weight=profile['weight'], max_penalty=cap,
                                          max_strength=strength)
            h.append(f'<h3>{esc(tr(recipe))}</h3>')
            if not res_list:
                h.append(f'<p>{esc(tr("No combination fits this build."))}</p>')
                continue
            h.append('<table border="1" cellspacing="0" cellpadding="3">')
            h.append('<tr>' + ''.join(f'<th>{esc(tr(x))}</th>' for x in ('Components', 'Penalty', 'Strength', 'Protection')) + '</tr>')
            for res in res_list:
                parts = '<br>'.join(f'{esc(tr(slot))}: <b>{esc(name)}</b>' for slot, name in res['parts'])
                for _, name in res['parts']:
                    used[name] = comps[name]['info']
                h.append(f"<tr><td>{parts}</td><td>{res['penalty'] * 100:.0f}%</td>"
                         f"<td>{res['strength'] or '–'}</td><td>{esc(hints.fmt_prot(res['prot']))}</td></tr>")
            h.append('</table>')

        h.append(f'<h2>{esc(tr("Where to get the components"))}</h2><table border="1" cellspacing="0" cellpadding="3">')
        h.append(f'<tr><th>{esc(tr("Component"))}</th><th>{esc(tr("Where to get"))}</th></tr>')
        for name in sorted(used):
            h.append(f'<tr><td>{esc(name)}</td><td>{self.sellers(used[name], 8)}</td></tr>')
        h.append('</table>')
        h.append(f'<p><i>{esc(tr("Leathers, carapaces and similar animal parts also come from skinning the creature with Skinner/Hunter; metal sheets and plates also drop as loot."))}</i></p>')
        return '\n'.join(h)


def equipped_armor_penalty(save):
    """Sum of the armor penalty (AI1:E) of everything worn."""
    import hints
    total = 0.0
    for it in save.equipped():
        if it.category != 'armor':
            continue
        if it.data is not None:
            v = save.g.val(it.data.get('AI1:E')) if 'AI1:E' in it.data else 0
        elif it.info:
            try:
                p, o = hints._item_root(it.info)
                v = hints._val(p, o, 'AI1:E')
            except Exception:
                v = 0
        else:
            v = 0
        total += v or 0
    return total


class FilteredFieldTab(QWidget):
    def __init__(self, main, fields, label=None, lo=0, hi=INT_MAX):
        super().__init__()
        self.table = FieldTable(main, fields, lo, hi, label=label)
        search = filter_box(tr('Filter…'), self.refilter)
        lay = QVBoxLayout(self)
        lay.addWidget(search); lay.addWidget(self.table)

    def refilter(self, q):
        q = q.lower()
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, bool(q) and q not in self.table.item(row, 0).text().lower())


# --- main window --------------------------------------------------------------------------

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Underrail Save Editor')
        self.resize(1400, 850)
        self.save = None
        self.dirty = False

        self.saves = QListWidget()
        self.saves.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        # cards always take the list's width; text wraps instead of scrolling sideways
        self.saves.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.saves.setResizeMode(QListWidget.Adjust)
        self.saves.setSpacing(0)
        # the cards draw their own selection; hide the list's highlight behind them
        self.saves.setStyleSheet('QListWidget::item:selected, QListWidget::item:hover { background: transparent; }')
        self.saves.currentItemChanged.connect(self.pick)
        self.cards = {}
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(QLabel(tr('Saves')), 1)
        refresh = QPushButton(QIcon.fromTheme('view-refresh'), tr('Refresh'))
        refresh.setToolTip(tr('Reload the save list (F5). The list also updates by itself when the game saves.'))
        refresh.clicked.connect(self.refresh_list)
        head.addWidget(refresh)
        lv.addLayout(head)
        lv.addWidget(self.saves, 1)

        self.title = QLabel()
        f = self.title.font(); f.setPointSize(f.pointSize() + 3); f.setBold(True)
        self.title.setFont(f)
        self.tabs = QTabWidget()
        self.status = QLabel()
        self.btn_save = QPushButton(tr('Save'))
        self.btn_save.clicked.connect(self.write)
        self.btn_revert = QPushButton(tr('Revert'))
        self.btn_revert.clicked.connect(self.reload)
        bar = QHBoxLayout()
        bar.addWidget(self.status, 1)
        bar.addWidget(self.btn_revert)
        bar.addWidget(self.btn_save)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(self.title)
        rv.addWidget(self.tabs, 1)
        rv.addLayout(bar)

        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([480, 900])
        self.setCentralWidget(split)

        settings = self.menuBar().addMenu(tr('Settings'))
        folders = QAction(tr('Game folders…'), self)
        folders.triggered.connect(self.choose_folders)
        settings.addAction(folders)

        menu = self.menuBar().addMenu(tr('Language'))
        current = i18n.chosen()
        for code, label in [('auto', tr('System default'))] + list(i18n.LANGUAGES.items()):
            act = QAction(label, self, checkable=True, checked=(code == current))
            act.triggered.connect(lambda _=False, c=code: self.set_language(c))
            menu.addAction(act)
        self.lang_actions = menu.actions()

        # watch the save folders so new/overwritten saves show up without a manual refresh;
        # the game writes several files per save, so changes are debounced
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.saves_changed)
        self.watcher.fileChanged.connect(self.saves_changed)
        self.refresh_timer = QTimer(self, singleShot=True, interval=2000, timeout=self.refresh_list)
        self.loaded_mtime = None
        portrait_signals().done.connect(self.details_done)
        portrait_signals().done.connect(self.icons_done)

        self.addAction(QAction(self, shortcut=QKeySequence.Save, triggered=self.write))
        self.addAction(QAction(self, shortcut=QKeySequence.Refresh, triggered=self.refresh_list))
        if gamedata.GAME and gamedata.USERDIR:
            self.refresh_list()
        else:
            # nothing detected: ask once the window is up
            QTimer.singleShot(0, self.choose_folders)

    def choose_folders(self):
        if self.dirty and not self.confirm_discard():
            return
        if FoldersDialog(self).exec():
            self.save = None
            self.dirty = False
            self.tabs.clear()
            self.refresh_list()
        elif not (gamedata.GAME and gamedata.USERDIR):
            self.status.setText(tr('Underrail was not found. Choose its folders under Settings → Game folders…'))

    def refresh_list(self):
        current = self.save.folder if self.save else None
        self.saves.blockSignals(True)
        self.saves.clear()
        self.cards = {}
        pending, thumbs = [], []
        for name, folder, info in us.list_saves():
            details = cached_details(folder)
            if details is None:
                pending.append(folder)
            card = SaveCard(name, folder, info)
            card.set_details(details)
            if not (thumb_path(folder) and os.path.exists(thumb_path(folder))):
                thumbs.append(folder)
            it = QListWidgetItem()
            it.setData(Qt.UserRole, folder)
            it.setSizeHint(card.sizeHint())
            self.saves.addItem(it)
            self.saves.setItemWidget(it, card)
            self.cards[folder] = card
            card.item = it
            if folder == current:
                self.saves.setCurrentItem(it)
        self.saves.blockSignals(False)
        if not current and self.saves.count():
            self.saves.setCurrentRow(0)
        self.mark_selected()
        self.watch_saves()
        self.check_loaded_changed()
        pool = QThreadPool.globalInstance()
        if thumbs:
            pool.start(ThumbJob(thumbs, portrait_signals()))
        if pending:
            pool.start(DetailsJob(pending, portrait_signals()))

    def mark_selected(self):
        cur = self.saves.currentItem()
        sel = cur.data(Qt.UserRole) if cur else None
        for folder, card in self.cards.items():
            card.set_selected(folder == sel)

    def watch_saves(self):
        saves = us.saves_dir()
        paths = ([saves] if saves else []) + [f for _, f, _ in us.list_saves()]
        paths += [os.path.join(f, 'global.dat') for f in paths[1:]]
        old = self.watcher.directories() + self.watcher.files()
        if old:
            self.watcher.removePaths(old)
        self.watcher.addPaths([p for p in paths if os.path.exists(p)])

    def saves_changed(self, _path):
        self.refresh_timer.start()

    def check_loaded_changed(self):
        """Hint when the game overwrote the save that is open in the editor."""
        if not self.save or self.loaded_mtime is None:
            return
        try:
            changed = os.path.getmtime(self.save.path) != self.loaded_mtime
        except OSError:
            changed = True
        if changed:
            self.status.setText(tr('This save was changed on disk (by the game?). Revert/reselect it to reload; '
                                   'saving now would overwrite the game\'s version.'))
            self.btn_revert.setEnabled(True)

    def details_done(self, kind, folder):
        card = self.cards.get(folder)
        if card is None:
            return
        if kind == 'details':
            card.set_details(cached_details(folder))
            card.item.setSizeHint(card.sizeHint())  # details can add lines
        elif kind == 'thumb':
            card.set_thumb()

    def pick(self, item, prev):
        if not item:
            return
        folder = item.data(Qt.UserRole)
        prev_folder = prev.data(Qt.UserRole) if prev else None
        if self.dirty and not self.confirm_discard():
            self.select_folder(prev_folder)
            return
        # saving from the prompt rebuilds the list, so select by folder rather than by the old item
        self.select_folder(folder)
        self.mark_selected()
        self.load(folder)

    def select_folder(self, folder):
        self.saves.blockSignals(True)
        for row in range(self.saves.count()):
            if self.saves.item(row).data(Qt.UserRole) == folder:
                self.saves.setCurrentRow(row)
                break
        self.saves.blockSignals(False)

    def confirm_discard(self):
        """Ask what to do with unsaved edits before leaving the save; True = go on."""
        name = os.path.basename(self.save.folder) if self.save else ''
        box = QMessageBox(QMessageBox.Warning, tr('Unsaved changes'),
                          tr('"{name}" has unsaved changes. Save them before continuing?', name=name),
                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, self)
        box.setDefaultButton(QMessageBox.Save)
        answer = box.exec()
        if answer == QMessageBox.Save:
            self.write()
            return not self.dirty  # writing can be cancelled or fail
        return answer == QMessageBox.Discard

    def load(self, folder):
        tab = self.tabs.currentIndex()
        self.tabs.clear()
        try:
            self.save = us.Save(folder)
        except Exception as e:
            self.save = None
            self.title.setText(os.path.basename(folder))
            self.status.setText(tr('Could not read save: {e}', e=e))
            return
        s = self.save
        self.loaded_mtime = os.path.getmtime(s.path)
        self.update_title()

        # attribute and skill names are game terms and stay as the game shows them
        self.tabs.addTab(CharacterTab(self), tr('Character'))
        self.tabs.addTab(FieldTable(self, s.attributes(), 1, 100, 'Effective (as saved)',
                                    lambda f: f.extra[0].value, label=lambda f: f.name), tr('Attributes'))
        self.tabs.addTab(FieldTable(self, s.skills(), 0, 1000, 'Effective (as saved)',
                                    lambda f: f.extra[0].value, label=lambda f: f.name), tr('Skills'))
        self.tabs.addTab(feats_tab(self), tr('Feats'))
        self.tabs.addTab(SpecsTab(self), tr('Specializations'))
        self.tabs.addTab(InventoryTab(self), tr('Inventory'))
        self.tabs.addTab(blueprints_tab(self), tr('Blueprints'))
        self.tabs.addTab(FilteredFieldTab(self, s.oddities(), label=lambda f: gamedata.split_camel(
            f.name.split('.', 1)[-1])), tr('Oddities'))
        self.tabs.addTab(HintsTab(self), tr('Hints'))
        if 0 <= tab < self.tabs.count():
            self.tabs.setCurrentIndex(tab)
        self.dirty = False
        self.update_status()
        fixed = s.g.repaired + (s.info.repaired if s.info else 0)
        if fixed:
            # not a user edit: no "discard changes?" prompt, but saving is possible and recommended
            self.btn_save.setEnabled(True)
            self.status.setText(tr('This save had {n} broken object id(s) from an older editor version; '
                                   'they were repaired – save to fix the file.', n=fixed))
        self.fetch_icons()

    def fetch_icons(self):
        """Extract missing item icons in the background (first run takes a few seconds)."""
        vms = {i.get('vm') for i in gamedata.items().values()}
        vms |= {it.visual for it in self.save.inventory() + self.save.equipped()}
        missing = {v for v in vms if v and not gamedata.icon_path(v)} - getattr(self, 'icons_tried', set())
        if not missing:
            return
        self.icons_tried = getattr(self, 'icons_tried', set()) | missing
        QThreadPool.globalInstance().start(IconJob(missing, portrait_signals()))

    def icons_done(self, kind, _):
        if kind != 'icons':
            return
        inv = next((self.tabs.widget(i) for i in range(self.tabs.count())
                    if isinstance(self.tabs.widget(i), InventoryTab)), None)
        if inv is not None:
            inv.build()

    def update_title(self):
        s = self.save
        loc = s.location()
        self.title.setText(f'{tr("{name} — level {level}", name=s.name, level=s.level)}{(" · " + loc) if loc else ""}   '
                           f'({os.path.basename(s.folder)})')

    def on_change(self):
        self.dirty = True
        self.update_title()
        self.update_status()

    def update_status(self):
        repaired = bool(self.save and (self.save.g.repaired or (self.save.info and self.save.info.repaired)))
        self.btn_save.setEnabled(self.dirty or repaired)
        self.btn_revert.setEnabled(self.dirty)
        self.status.setText(tr('Unsaved changes') if self.dirty else tr('No changes'))

    def reload(self):
        if self.save:
            self.load(self.save.folder)

    def write(self):
        repaired = self.save and (self.save.g.repaired or (self.save.info and self.save.info.repaired))
        if not self.save or not (self.dirty or repaired):
            return
        # the game never rewrites a named save after creating it; only quick-/autosaves get replaced
        rolling = os.path.basename(self.save.folder).lower().startswith(('quicksave', 'autosave'))
        if rolling and us.game_running():
            if QMessageBox.warning(self, tr('Underrail is running'),
                                   tr('Underrail is running and replaces quicksaves/autosaves on its own, '
                                      'which would discard these edits.\nWrite anyway?'),
                                   QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
        try:
            on_disk = os.path.getmtime(self.save.path)
        except OSError:
            on_disk = None
        if on_disk != self.loaded_mtime and QMessageBox.warning(
                self, tr('Save changed on disk'),
                tr('The game has changed this save since you opened it. Saving overwrites those changes '
                   '(a backup is made first).\nSave anyway?'),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            bak = self.save.write()
        except Exception as e:
            QMessageBox.critical(self, tr('Save failed'), str(e))
            return
        self.load(self.save.folder)
        self.refresh_list()
        self.status.setText(tr('Saved. Backup: {path}', path=bak))

    def set_language(self, code):
        i18n.choose(code)
        for act, c in zip(self.lang_actions, ['auto'] + list(i18n.LANGUAGES)):
            act.setChecked(c == code)
        if self.dirty:
            QMessageBox.information(self, tr('Language'), tr(
                'The language changes once the unsaved changes are saved or discarded and the editor is restarted.'))
            return
        # rebuild the window in the new language, keeping the selected save and tab
        i18n.reset()
        w = Main()
        if self.save:
            w.load(self.save.folder)
            w.refresh_list()
            w.tabs.setCurrentIndex(self.tabs.currentIndex())
        w.resize(self.size())
        w.move(self.pos())
        w.show()
        QApplication.instance().main_window = w
        self.close()

    def closeEvent(self, e):
        if self.dirty and not self.confirm_discard():
            e.ignore()
        else:
            e.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Underrail Save Editor')
    # matches the .desktop file so launchers/taskbars (Wayland app_id) show the right icon
    app.setDesktopFileName('underrail-save-editor')
    icon = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'underrail-save-editor.svg')
    app.setWindowIcon(QIcon.fromTheme('underrail-save-editor', QIcon(icon)))

    def stop_jobs():
        pool = QThreadPool.globalInstance()
        pool.clear()
        pool.waitForDone()
    app.aboutToQuit.connect(stop_jobs)
    w = Main()
    app.main_window = w
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
