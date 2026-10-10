"""UI translations. English source strings are the keys; game terms (items, feats, skills…) stay
as the game names them. Language: saved choice, else the system locale."""
import re

from PySide6.QtCore import QLocale, QSettings

LANGUAGES = {'en': 'English', 'de': 'Deutsch'}

DE = {
    # main window
    'Saves': 'Spielstände',
    'Save': 'Speichern',
    'Revert': 'Verwerfen',
    'Unsaved changes': 'Ungespeicherte Änderungen',
    'No changes': 'Keine Änderungen',
    'Discard unsaved changes?': 'Ungespeicherte Änderungen verwerfen?',
    'Could not read save: {e}': 'Spielstand nicht lesbar: {e}',
    '{name} — level {level}': '{name} — Level {level}',
    '(unreadable info)': '(Info nicht lesbar)',
    'Underrail is running': 'Underrail läuft',
    'Underrail seems to be running. It may overwrite this save.\nWrite anyway?':
        'Underrail scheint zu laufen und könnte diesen Spielstand überschreiben.\nTrotzdem speichern?',
    'Save failed': 'Speichern fehlgeschlagen',
    'Saved. Backup: {path}': 'Gespeichert. Backup: {path}',
    'Language': 'Sprache',
    'System default': 'Systemsprache',
    'The language changes once the unsaved changes are saved or discarded and the editor is restarted.':
        'Die Sprache wechselt beim nächsten Start des Editors; zuerst ungespeicherte Änderungen speichern '
        'oder verwerfen.',
    # tabs
    'Character': 'Charakter',
    'Attributes': 'Attribute',
    'Skills': 'Skills',
    'Feats': 'Feats',
    'Specializations': 'Spezialisierungen',
    'Inventory': 'Inventar',
    'Blueprints': 'Baupläne',
    'Oddities': 'Oddities',
    # generic
    'Name': 'Name',
    'Value': 'Wert',
    'Filter…': 'Filtern…',
    'Effective (as saved)': 'Effektiv (gespeichert)',
    'Change failed': 'Änderung fehlgeschlagen',
    '(no description)': '(keine Beschreibung)',
    # character tab
    'Level': 'Level',
    'Portrait': 'Portrait',
    'Change…': 'Ändern…',
    '(no preview)': '(keine Vorschau)',
    'Points / experience / vitals:': 'Punkte / Erfahrung / Vitalwerte:',
    'Experience': 'Erfahrung',
    'Unspent attribute points': 'Freie Attributpunkte',
    'Unspent skill points': 'Freie Skillpunkte',
    'Unspent feat points': 'Freie Feat-Punkte',
    'Unspent specialization points': 'Freie Spezialisierungspunkte',
    'Health (current)': 'Lebenspunkte (aktuell)',
    # portrait dialog
    'Choose portrait': 'Portrait wählen',
    'all': 'alle',
    'male': 'männlich',
    'female': 'weiblich',
    'genderless': 'geschlechtslos',
    'custom': 'eigene',
    'Filter by id…': 'Nach Id filtern…',
    'Import PNG…': 'PNG importieren…',
    'Portrait image': 'Portrait-Bild',
    'Images (*.png *.jpg *.jpeg *.webp *.bmp)': 'Bilder (*.png *.jpg *.jpeg *.webp *.bmp)',
    'Portrait id': 'Portrait-Id',
    'Id (letters, digits, underscore):': 'Id (Buchstaben, Ziffern, Unterstrich):',
    '"{pid}" is a built-in portrait id.': '„{pid}“ ist bereits ein Portrait des Spiels.',
    # checklists
    'Only owned': 'Nur vorhandene',
    'Learn all': 'Alle lernen',
    '{n} of {total} owned': '{n} von {total} vorhanden',
    'Adding a feat only records it as learned. Feats that grant abilities may need other changes too – '
    'test on a copy of the save first.':
        'Ein hinzugefügter Feat wird nur als gelernt eingetragen. Feats, die Fähigkeiten freischalten, brauchen '
        'eventuell weitere Änderungen – erst an einer Kopie des Spielstands testen.',
    'Known crafting blueprints. Blueprint items in the inventory are separate.':
        'Bekannte Baupläne. Bauplan-Items im Inventar sind davon unabhängig.',
    # specs
    'Add': 'Hinzufügen',
    'Add:': 'Hinzufügen:',
    'Remove selected': 'Auswahl entfernen',
    '{n} specializations, {points} points total': '{n} Spezialisierungen, insgesamt {points} Punkte',
    # inventory
    'Category': 'Kategorie',
    'Stack': 'Anzahl',
    'Quality': 'Qualität',
    'Durability': 'Haltbarkeit',
    'Max': 'Max',
    'Battery': 'Batterie',
    'Max bat.': 'Max Bat.',
    'Crafted': 'Gecraftet',
    'Slot': 'Slot',
    'Equipped': 'Ausgerüstet',
    'Add item…': 'Item hinzufügen…',
    'Duplicate': 'Duplizieren',
    'Remove': 'Entfernen',
    'Repair': 'Reparieren',
    'Repair all': 'Alle reparieren',
    'Set durability of the selected items (inventory and equipped) to full':
        'Haltbarkeit der ausgewählten Items (Inventar und Ausrüstung) auf voll setzen',
    'all categories': 'alle Kategorien',
    'crafted item': 'gecraftetes Item',
    '(placeholder icon – the game has no icon for this item)':
        '(Platzhalter-Icon – das Spiel hat für dieses Item kein Icon)',
    'Remove items': 'Items entfernen',
    'Remove {names}?': '{names} entfernen?',
    'Repaired {n} item(s)': '{n} Item(s) repariert',
    ' – unsaved': ' – nicht gespeichert',
    'Head': 'Kopf',
    'Armor': 'Rüstung',
    'Belt': 'Gürtel',
    'Boots': 'Stiefel',
    'Shield emitter': 'Schildemitter',
    'Quick slot {n}': 'Schnellslot {n}',
    'Weapon {n}': 'Waffe {n}',
    # add item dialog
    'Add item': 'Item hinzufügen',
    'Search name or path…': 'Name oder Pfad suchen…',
    'Path': 'Pfad',
    'Stack size': 'Stapelgröße',
    'Copies': 'Exemplare',
    'level {level}': 'Level {level}',
    'max stack {n}': 'max. Stapel {n}',
    'full = {d}': 'voll = {d}',
    "doesn't wear down": 'nutzt sich nicht ab',
}

# labels with a number in them, e.g. 'Quick slot 3'
_PATTERNS = [(re.compile(r'Quick slot (\d+)$'), 'Quick slot {n}'), (re.compile(r'Weapon (\d+)$'), 'Weapon {n}')]

_lang = None


def settings():
    return QSettings('underrail-save-editor', 'gui')


def chosen():
    """'auto', 'en' or 'de' as stored in the settings."""
    return settings().value('language', 'auto')


def choose(lang):
    settings().setValue('language', lang)


def language():
    global _lang
    if _lang is None:
        c = chosen()
        _lang = c if c in LANGUAGES else ('de' if QLocale.system().name().startswith('de') else 'en')
    return _lang


def reset():
    global _lang
    _lang = None


def tr(text, **fmt):
    table = DE if language() == 'de' else {}
    out = table.get(text)
    if out is None:
        for pat, key in _PATTERNS:
            m = pat.match(text)
            if m and key in table:
                out, fmt = table[key], {'n': m.group(1)}
                break
    out = out if out is not None else text
    return out.format(**fmt) if fmt else out
