#!/usr/bin/env python3
"""Underrail save editor GUI (PySide6)."""
import datetime
import os
import re
import sys

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
                               QTextBrowser, QVBoxLayout, QWidget)

import gamedata
import i18n
import underrail_save as us
from i18n import tr

INT_MAX = 2**31 - 1
MAX_QUALITY = 185  # upper bound of component quality in the game's config


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

    def __init__(self, main, fields, lo=0, hi=INT_MAX, info_header=None, info=None, label=None, after=None):
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
            self.setCellWidget(row, 1, spin_for(f, self.changed, lo, hi))
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
        if not ok or not re.fullmatch(r'[A-Za-z0-9_]+', pid or ''):
            return
        if pid in self.portraits and self.portraits[pid][0] != 'custom':
            QMessageBox.warning(self, tr('Portrait id'), tr('"{pid}" is a built-in portrait id.', pid=pid))
            return
        gamedata.import_portrait(path, pid)
        self.portraits = gamedata.portraits()
        self.selected = pid
        self.populate()

    def accept(self):
        it = self.view.currentItem()
        if it is not None:
            self.selected = it.data(Qt.UserRole)
        super().accept()


class AddItemDialog(QDialog):
    def __init__(self, parent, save):
        super().__init__(parent)
        self.setWindowTitle(tr('Add item'))
        self.resize(820, 620)
        self.save = save
        self.db = sorted(gamedata.items().values(), key=lambda i: (i['name'].lower(), i['path'].lower()))

        self.cat = QComboBox()
        self.cat.addItem(tr('all categories'), 'all')
        for c in sorted({i['category'] for i in self.db}):
            self.cat.addItem(c, c)
        self.cat.currentTextChanged.connect(self.refilter)
        self.search = filter_box(tr('Search name or path…'), self.refilter)
        top = QHBoxLayout()
        top.addWidget(self.cat); top.addWidget(self.search, 1)

        self.table = QTableWidget(len(self.db), 3)
        self.table.setHorizontalHeaderLabels([tr('Name'), tr('Category'), tr('Path')])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for row, i in enumerate(self.db):
            self.table.setItem(row, 0, QTableWidgetItem(i['name']))
            self.table.setItem(row, 1, QTableWidgetItem(i['category']))
            self.table.setItem(row, 2, QTableWidgetItem(i['path']))
        self.table.itemSelectionChanged.connect(self.selected)
        self.table.doubleClicked.connect(lambda _: self.accept())

        self.desc = QLabel(wordWrap=True)
        self.count_label = QLabel(tr('Stack size'))
        self.count = QSpinBox(); self.count.setRange(1, INT_MAX)
        self.dur = QDoubleSpinBox(); self.dur.setRange(0, 1e7); self.dur.setDecimals(1)
        self.dur_hint = QLabel()
        self.quality = QSpinBox(); self.quality.setRange(0, MAX_QUALITY)
        self.quality_label = QLabel(tr('Quality'))
        form = QFormLayout()
        form.addRow(self.count_label, self.count)
        dl = QHBoxLayout(); dl.addWidget(self.dur); dl.addWidget(self.dur_hint, 1)
        form.addRow(tr('Durability'), dl)
        form.addRow(self.quality_label, self.quality)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr('Add'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(top); lay.addWidget(self.table, 1); lay.addWidget(self.desc)
        lay.addLayout(form); lay.addWidget(buttons)

    def refilter(self, *_):
        c, q = self.cat.currentData(), self.search.text().lower()
        for row, i in enumerate(self.db):
            hide = (c != 'all' and i['category'] != c) or (q and q not in i['name'].lower() and q not in i['path'].lower())
            self.table.setRowHidden(row, bool(hide))

    def current(self):
        rows = self.table.selectionModel().selectedRows()
        return self.db[rows[0].row()] if rows else None

    def stackable(self):
        i = self.current()
        return bool(i and i['stack'] and i['stack'] > 1)

    def selected(self):
        i = self.current()
        if not i:
            return
        q = gamedata.QUALITY.get(i['quality'], '')
        self.desc.setText(f"<b>{i['name']}</b> {('· ' + q) if q else ''} · {tr('level {level}', level=i.get('level', 0))} · "
                          f"{tr('max stack {n}', n=i['stack'])}<br>{i['desc']}")
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


class ChecklistTab(QWidget):
    """Checkable list of everything in a game database; checked = present in the save."""

    def __init__(self, main, db, owned, add, remove, note, learn_all=False):
        super().__init__()
        self.main, self.db, self.owned, self.add, self.remove = main, db, owned, add, remove
        have = set(owned())
        self.count = QLabel()
        self.only = QCheckBox(tr('Only owned'))
        self.only.toggled.connect(self.refilter)
        self.search = filter_box(tr('Filter…'), self.refilter)
        top = QHBoxLayout()
        top.addWidget(self.search, 1); top.addWidget(self.only)
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
        self.desc.setMaximumHeight(140)
        lay = QVBoxLayout(self)
        lay.addLayout(top); lay.addWidget(self.list, 1); lay.addWidget(self.desc)
        if note:
            lab = QLabel(tr(note))
            lab.setWordWrap(True)
            lay.addWidget(lab)
        self.update_count()

    def update_count(self):
        self.count.setText(tr('{n} of {total} owned', n=len(self.owned()), total=len(self.db)))

    def refilter(self, *_):
        q, only = self.search.text().lower(), self.only.isChecked()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool((only and it.checkState() != Qt.Checked) or (q and q not in it.text().lower())))

    def describe(self, it, _):
        if it is not None:
            key = it.data(Qt.UserRole)
            self.desc.setPlainText(self.db.get(key, (key, ''))[1] or tr('(no description)'))

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

    def learn_all(self):
        # checking each item triggers toggled(), which adds the missing entries
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.Checked)


def feats_tab(main):
    s = main.save
    return ChecklistTab(main, gamedata.feats(), s.feats, s.add_feat, s.remove_feat,
                        'Adding a feat only records it as learned. Feats that grant abilities may need '
                        'other changes too – test on a copy of the save first.')


def blueprints_tab(main):
    s = main.save
    return ChecklistTab(main, gamedata.blueprints(), s.blueprints, s.add_blueprint, s.remove_blueprint,
                        'Known crafting blueprints. Blueprint items in the inventory are separate.',
                        learn_all=True)


class SpecsTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.db = gamedata.specs()
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
        self.build()
        lay.addWidget(self.total)
        lay.addLayout(add)
        lay.addWidget(self.desc)

    def build(self):
        s = self.main.save
        fields = s.specs()
        for f in fields:
            f.info = self.db.get(f.name, (None, None))[1]
        table = FieldTable(self.main, fields, 0, 100, label=lambda f: gamedata.split_camel(f.name),
                           after=self.update_total)
        table.setSelectionMode(QTableWidget.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        if self.table is not None:
            self.lay.replaceWidget(self.table, table)
            self.table.deleteLater()
        else:
            self.lay.addWidget(table, 1)
        self.table = table
        have = {f.name for f in fields}
        self.combo.clear()
        for key, (name, _) in sorted(self.db.items(), key=lambda x: x[1][0].lower()):
            if key not in have:
                self.combo.addItem(name, key)
        self.update_total()

    def update_total(self):
        fields = self.table.fields
        self.total.setText(tr('{n} specializations, {points} points total', n=len(fields),
                              points=sum(f.value for f in fields)))

    def describe(self, *_):
        key = self.combo.currentData()
        self.desc.setText(self.db.get(key, ('', ''))[1] if key else '')

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
            cells = {'Slot': tr(it.slot) if it.slot else '', 'Name': it.name, 'Category': it.category,
                     'Max': '' if mx is None else f'{mx:g}', 'Max bat.': '' if mb is None else f'{mb:g}',
                     'Crafted': '✓' if it.crafted else ''}
            for col, name in enumerate(self.cols):
                if name in cells:
                    key = {'Max': mx, 'Max bat.': mb}.get(name)
                    key = cells[name] if key is None else key
                    cell = SortItem(cells[name], key)
                    if name == 'Name':
                        cell.setData(Qt.UserRole, row)
                        cell.setToolTip(it.path or tr('crafted item'))
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

    def item_at(self, row):
        return self.items[self.item(row, self.cols.index('Name')).data(Qt.UserRole)]

    def selected(self):
        return [self.item_at(r.row()) for r in self.selectionModel().selectedRows()]

    def all_rows(self):
        return [(row, self.item_at(row)) for row in range(self.rowCount())]


class InventoryTab(QWidget):
    COLS = ['Name', 'Category', 'Stack', 'Quality', 'Durability', 'Max', 'Battery', 'Max bat.', 'Crafted']

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.search = filter_box(tr('Filter…'), self.refilter)
        self.cat = QComboBox()
        self.cat.currentIndexChanged.connect(self.refilter)
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
        self.equip = ItemTable(self, ['Slot', 'Name', 'Durability', 'Max', 'Battery', 'Max bat.'], sortable=False)
        eq = QGroupBox(tr('Equipped'))
        QVBoxLayout(eq).addWidget(self.equip)
        split = QSplitter(Qt.Vertical)
        inv = QWidget()
        il = QVBoxLayout(inv); il.setContentsMargins(0, 0, 0, 0)
        il.addLayout(top); il.addWidget(self.table)
        split.addWidget(inv); split.addWidget(eq)
        split.setSizes([450, 180])
        QVBoxLayout(self).addWidget(split)
        self.build()

    def build(self):
        items = self.main.save.inventory()
        cats = sorted({i.category for i in items if i.category})
        current = self.cat.currentData()
        self.cat.blockSignals(True)
        self.cat.clear()
        self.cat.addItem(tr('all categories'), None)
        for c in cats:
            self.cat.addItem(c, c)
        self.cat.setCurrentIndex(max(0, self.cat.findData(current)) if current in cats else 0)
        self.cat.blockSignals(False)
        self.table.fill(items)
        self.equip.fill(self.main.save.equipped())
        self.refilter()

    def refilter(self, *_):
        q, c = self.search.text().lower(), self.cat.currentData()
        for row, it in self.table.all_rows():
            hide = (c is not None and it.category != c) or \
                (q and q not in it.name.lower() and q not in it.category.lower())
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
        self.resize(1200, 780)
        self.save = None
        self.dirty = False

        self.saves = QListWidget()
        self.saves.currentItemChanged.connect(self.pick)
        self.shot = QLabel(alignment=Qt.AlignCenter)
        self.shot.setMinimumHeight(160)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel(tr('Saves')))
        lv.addWidget(self.saves, 1)
        lv.addWidget(self.shot)

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
        split.setSizes([330, 870])
        self.setCentralWidget(split)

        menu = self.menuBar().addMenu(tr('Language'))
        current = i18n.chosen()
        for code, label in [('auto', tr('System default'))] + list(i18n.LANGUAGES.items()):
            act = QAction(label, self, checkable=True, checked=(code == current))
            act.triggered.connect(lambda _=False, c=code: self.set_language(c))
            menu.addAction(act)
        self.lang_actions = menu.actions()

        self.addAction(QAction(self, shortcut=QKeySequence.Save, triggered=self.write))
        self.addAction(QAction(self, shortcut=QKeySequence.Refresh, triggered=self.refresh_list))
        self.refresh_list()

    def refresh_list(self):
        current = self.save.folder if self.save else None
        self.saves.blockSignals(True)
        self.saves.clear()
        for name, folder, info in us.list_saves():
            if info:
                cn, lvl, loc, mt = info
                when = datetime.datetime.fromtimestamp(mt).strftime('%Y-%m-%d %H:%M')
                text = f'{name}\n    {cn} L{lvl} · {loc} · {when}'
            else:
                text = f'{name}\n    {tr("(unreadable info)")}'
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, folder)
            self.saves.addItem(it)
            if folder == current:
                self.saves.setCurrentItem(it)
        self.saves.blockSignals(False)
        if not current and self.saves.count():
            self.saves.setCurrentRow(0)

    def pick(self, item, prev):
        if not item:
            return
        if self.dirty and not self.confirm_discard():
            self.saves.blockSignals(True)
            self.saves.setCurrentItem(prev)
            self.saves.blockSignals(False)
            return
        self.load(item.data(Qt.UserRole))

    def confirm_discard(self):
        return QMessageBox.question(self, tr('Unsaved changes'), tr('Discard unsaved changes?')) == QMessageBox.Yes

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
        pix = QPixmap(os.path.join(folder, 'screenshot.png'))
        self.shot.setPixmap(pix.scaledToWidth(320, Qt.SmoothTransformation) if not pix.isNull() else QPixmap())
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
        if 0 <= tab < self.tabs.count():
            self.tabs.setCurrentIndex(tab)
        self.dirty = False
        self.update_status()

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
        self.btn_save.setEnabled(self.dirty)
        self.btn_revert.setEnabled(self.dirty)
        self.status.setText(tr('Unsaved changes') if self.dirty else tr('No changes'))

    def reload(self):
        if self.save:
            self.load(self.save.folder)

    def write(self):
        if not self.save or not self.dirty:
            return
        if us.game_running():
            if QMessageBox.warning(self, tr('Underrail is running'),
                                   tr('Underrail seems to be running. It may overwrite this save.\nWrite anyway?'),
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
