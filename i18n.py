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
    'Underrail is running and replaces quicksaves/autosaves on its own, which would discard these edits.\nWrite anyway?':
        'Underrail läuft und ersetzt Quick- und Autosaves selbstständig, wodurch diese Änderungen verloren gingen.\n'
        'Trotzdem speichern?',
    'Save failed': 'Speichern fehlgeschlagen',
    'Saved. Backup: {path}': 'Gespeichert. Backup: {path}',
    'Added {n} missing attack(s)/ability(ies) of feats.': '{n} fehlende Angriffe/Fähigkeiten von Feats ergänzt.',
    'Feats without their attack/ability: {names} – they are added when saving.':
        'Feats ohne ihren Angriff/ihre Fähigkeit: {names} – werden beim Speichern ergänzt.',
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
    'Easy': 'Leicht',
    'Normal': 'Normal',
    'Hard': 'Schwer',
    'Dominating': 'Dominating',
    'Custom': 'Benutzerdefiniert',
    'Stygian': 'Stygian',
    'attr.': 'Attr.',
    'skill': 'Skill',
    'feat': 'Feat',
    'spec': 'Spez.',
    'unspent': 'frei',
    'Game time is the in-game world clock stored in the save.':
        'Die Spielzeit ist die im Spielstand gespeicherte Uhr der Spielwelt.',
    'DLCs: {dlcs}': 'DLCs: {dlcs}',
    'Refresh': 'Aktualisieren',
    'Only available': 'Nur verfügbare',
    'Hints': 'Tipps',
    'Merchants': 'Händler',
    'Harvest from {creature}': 'Gewinnen aus {creature}',
    'No merchant': 'Kein Händler',
    'Found': 'Fundorte',
    'Where to get': 'Wo bekommen',
    'Map locations: scanning…': 'Fundorte: werden gesucht…',
    'not placed in the game world (crafted, quest or event)': 'nicht in der Spielwelt platziert (Crafting, Quest oder Ereignis)',
    'Scanning the game maps for item locations (about a minute, only once)…':
        'Durchsuche die Spielkarten nach Fundorten (etwa eine Minute, nur einmal)…',
    'Found: where the item lies in the game world – in a container, on the ground, carried by an NPC (loot when defeated), as a job reward, or as possible random loot of a container.':
        'Fundorte: wo das Item in der Spielwelt liegt – in einem Behälter, auf dem Boden, bei einem NPC (Beute nach '
        'einem Kampf), als Auftragsbelohnung oder als mögliche Zufallsbeute eines Behälters.',
    'container': 'Behälter', 'on the ground': 'auf dem Boden', 'job reward': 'Auftragsbelohnung',
    'carried by an NPC': 'bei einem NPC', 'random loot': 'Zufallsbeute', 'other': 'sonstiges',
    'Could not compute hints: {e}': 'Tipps konnten nicht berechnet werden: {e}',
    '+{n} more': '+{n} weitere',
    'Location unknown: not placed in any map (appears through an event or quest).':
        'Ort unbekannt: in keiner Karte platziert (erscheint durch ein Ereignis oder eine Quest).',
    'Black Sea (Expedition)': 'Schwarzes Meer (Expedition)',
    'Zones without a place on the world map (dungeons, interiors) are greyed out in the list.':
        'Zonen ohne Platz auf der Weltkarte (Dungeons, Innenräume) sind in der Liste ausgegraut.',
    'Rendering the world map from the game files (once)…': 'Weltkarte wird aus den Spieldateien erstellt (einmalig)…',
    'Build:': 'Build:',
    'Auto: {build}': 'Automatisch: {build}',
    'Build: {build}': 'Build: {build}',
    'The build decides which weapons are listed and how armor penalty is weighed. Auto picks it from skills, feats and equipped weapons.': 'Der Build bestimmt, welche Waffen gelistet werden und wie stark der Rüstungsmalus zählt. Automatisch wählt ihn anhand von Skills, Feats und ausgerüsteten Waffen.',
    'Main attributes': 'Hauptattribute',
    'Key skills': 'Wichtige Skills',
    'Key feats': 'Wichtige Feats',
    'Equipped weapons': 'Ausgerüstete Waffen',
    'fits the build': 'passt zum Build',
    'no weapon of this build equipped': 'keine Waffe dieses Builds ausgerüstet',
    'Armor penalty worn': 'Getragener Rüstungsmalus',
    'above the {cap}% this build usually accepts': 'über den {cap} %, die dieser Build üblicherweise verträgt',
    'Builds are the archetypes players commonly describe (Steam guides, underrail.info, RPG Codex); ⚠ = requirements not met yet.': 'Die Builds sind die Archetypen, die Spieler häufig beschreiben (Steam-Guides, underrail.info, RPG Codex); ⚠ = Voraussetzungen noch nicht erfüllt.',
    'This build fights without weapons.': 'Dieser Build kämpft ohne Waffen.',
    'The game has no fixed (non-crafted) weapons of this kind; craft them or buy the parts.': 'Das Spiel hat keine festen (nicht gecrafteten) Waffen dieser Art; selbst bauen oder Teile kaufen.',
    'Base values without ammo, feats or precision; burst weapons count all shots. Only weapons that exist as fixed items – crafted weapons are often better.': 'Grundwerte ohne Munition, Feats oder Präzision; Feuerstöße zählen alle Schüsse. Nur Waffen, die als feste Items existieren – gecraftete Waffen sind oft besser.',
    'Light armor build: armor penalty weighs heavily, combinations above {cap}% are left out.': 'Build mit leichter Rüstung: Der Rüstungsmalus zählt stark, Kombinationen über {cap} % fallen weg.',
    'Balanced: protection and armor penalty both count, combinations above {cap}% are left out.': 'Ausgewogen: Schutz und Rüstungsmalus zählen beide, Kombinationen über {cap} % fallen weg.',
    'Heavy armor build: protection first, armor penalty counts little.': 'Build mit schwerer Rüstung: Schutz zuerst, der Rüstungsmalus zählt wenig.',
    'Only combinations your Strength ({s}) can wear.': 'Nur Kombinationen, die deine Stärke ({s}) tragen kann.',
    'No combination fits this build.': 'Keine Kombination passt zu diesem Build.',
    'Sniper': 'Scharfschütze',
    'Heavy guns': 'Schwere Waffen',
    'Crossbow': 'Armbrust',
    'Stealth knife': 'Schleich-Messer',
    'Unarmed / psi monk': 'Waffenlos / Psi-Mönch',
    'Sledgehammer': 'Vorschlaghammer',
    'Spear': 'Speer',
    'Sword': 'Schwert',
    'Throwing': 'Wurfwaffen',
    'Psi': 'Psi',
    'assault rifle': 'Sturmgewehr',
    'sniper rifle': 'Scharfschützengewehr',
    'smg': 'MP',
    'pistol': 'Pistole',
    'energy pistol': 'Energiepistole',
    'shotgun': 'Schrotflinte',
    'light machine gun': 'leichtes MG',
    'minigun': 'Minigun',
    'grenade launcher': 'Granatwerfer',
    'rocket launcher': 'Raketenwerfer',
    'crossbow': 'Armbrust',
    'knife': 'Messer',
    'fist': 'Faustwaffe',
    'sledgehammer': 'Vorschlaghammer',
    'crowbar': 'Brecheisen',
    'spear': 'Speer',
    'sword': 'Schwert',
    'melee': 'Nahkampf',
    'throwing': 'Wurfwaffe',
    'Bursts from the front line. Rifles need Strength; heavy metal armor with Armor Sloping is common.': 'Feuerstöße aus der ersten Reihe. Gewehre brauchen Stärke; schwere Metallrüstung mit Armor Sloping ist üblich.',
    'Big single shots from range, often opening from stealth. A tactical vest keeps the penalty moderate.': 'Starke Einzelschüsse auf Distanz, oft aus dem Schleichen heraus. Eine taktische Weste hält den Malus moderat.',
    'Cheap bursts, many attacks per turn. Low Strength needs, so light vests are enough.': 'Günstige Feuerstöße, viele Angriffe pro Runde. Wenig Stärke nötig, leichte Westen reichen.',
    'Fast, crit-heavy single shots (Gunslinger, Execute); energy pistols use Guns too.': 'Schnelle Einzelschüsse mit vielen Krits (Gunslinger, Execute); Energiepistolen nutzen ebenfalls Guns.',
    'Expedition shotguns: brutal at close range, so it pays to stand in heavy armor.': 'Schrotflinten aus Expedition: brutal auf kurze Distanz, daher lohnt schwere Rüstung.',
    'Heavy Duty machine guns and launchers: high Strength, heavy armor (Heavy Metal).': 'MGs und Werfer aus Heavy Duty: viel Stärke, schwere Rüstung (Heavy Metal).',
    'Special bolts and traps, usually played sneaky – keep the armor penalty low for Stealth.': 'Spezialbolzen und Fallen, meist schleichend gespielt – Rüstungsmalus wegen Stealth niedrig halten.',
    'Crits from stealth and many cheap stabs; relies on Dodge/Evasion, so light armor only.': 'Krits aus dem Schleichen und viele günstige Stiche; lebt von Dodge/Evasion, also nur leichte Rüstung.',
    'Fists (often mixed with psi): very cheap attacks, so armor penalty and AP matter a lot.': 'Fäuste (oft mit Psi gemischt): sehr günstige Angriffe, Rüstungsmalus und AP zählen viel.',
    'Slow, crushing hits in the thick of it: heavy metal armor, Juggernaut, Armor Sloping.': 'Langsame, vernichtende Schläge mitten im Getümmel: schwere Metallrüstung, Juggernaut, Armor Sloping.',
    'Expedition spears: reach and control; Iron Grip lets you wear more armor.': 'Speere aus Expedition: Reichweite und Kontrolle; Iron Grip erlaubt mehr Rüstung.',
    'Expedition swords and machetes: combos and counters.': 'Schwerter und Macheten aus Expedition: Kombos und Konter.',
    'Throwing knives and grenades; mostly a secondary skill, often next to knives or psi.': 'Wurfmesser und Granaten; meist Zweitskill, oft neben Messern oder Psi.',
    'Psi abilities instead of weapons. Psi Empathy costs health; armor penalty slows you, so light armor or a tactical vest is usual.': 'Psi-Fähigkeiten statt Waffen. Psi Empathy kostet Lebenspunkte; Rüstungsmalus bremst, daher sind leichte Rüstung oder eine taktische Weste üblich.',
    'Select a weapon or armor piece to compare it with your equipment.': 'Wähle eine Waffe oder ein Rüstungsteil, um es mit deiner Ausrüstung zu vergleichen.',
    'No comparable stats for this item.': 'Für dieses Item gibt es keine vergleichbaren Werte.',
    'Equipped ({slot})': 'Ausgerüstet ({slot})',
    'Nothing equipped in this slot.': 'In diesem Slot ist nichts ausgerüstet.',
    'This item': 'Dieses Item',
    'Differences: this item minus the equipped one; green = better. Your damage per AP uses your effective skill from the save.': 'Unterschiede: dieses Item minus das ausgerüstete; grün = besser. „Dein Schaden pro AP“ nutzt deinen effektiven Skill aus dem Spielstand.',
    'Action points': 'Aktionspunkte',
    'Damage per AP': 'Schaden pro AP',
    'Your damage per AP': 'Dein Schaden pro AP',
    'Critical chance': 'Kritische Trefferchance',
    'Critical damage': 'Kritischer Schaden',
    'Precision bonus': 'Präzisionsbonus',
    'Strength requirement': 'Benötigte Stärke',
    'Optimal range': 'Optimale Reichweite',
    'Maximum range': 'Maximale Reichweite',
    'Magazine': 'Magazin',
    'Item level': 'Item-Level',
    'Maximum durability': 'Maximale Haltbarkeit',
    'Weight': 'Gewicht',
    'Armor penalty': 'Rüstungsmalus',
    'Mechanical resistance': 'Mechanischer Widerstand',
    'Mechanical threshold': 'Mechanische Schwelle',
    'Energy resistance': 'Energie-Widerstand',
    'Energy threshold': 'Energie-Schwelle',
    'Heat resistance': 'Hitze-Widerstand',
    'Heat threshold': 'Hitze-Schwelle',
    'Electricity resistance': 'Elektrizitäts-Widerstand',
    'Electricity threshold': 'Elektrizitäts-Schwelle',
    'Cold resistance': 'Kälte-Widerstand',
    'Cold threshold': 'Kälte-Schwelle',
    'Acid resistance': 'Säure-Widerstand',
    'Acid threshold': 'Säure-Schwelle',
    'Bio resistance': 'Bio-Widerstand',
    'Bio threshold': 'Bio-Schwelle',
    'Your dmg/AP': 'Dein Schaden/AP',
    'Crit': 'Krit',
    'Crit dmg': 'Krit-Schaden',
    'Precision': 'Präzision',
    'Range': 'Reichweite',
    'Max range': 'Max. Reichweite',
    'Owned': 'Besitz',
    'Only usable with my Strength': 'Nur mit meiner Stärke nutzbar',
    'Only my weapons': 'Nur meine Waffen',
    'Where to get…': 'Wo bekommen…',
    'Weapons of the build': 'Waffen des Builds',
    'All weapons': 'Alle Waffen',
    'equipped': 'ausgerüstet',
    'inventory': 'Inventar',
    'Weapons': 'Waffen',
    'Build and armor': 'Build und Rüstung',
    'Crafted weapons only come from crafting.': 'Gecraftete Waffen gibt es nur durch Crafting.',
    'Your dmg/AP = damage × (1 + 0.7 × effective skill / 100), 0.5 for pistols and knives (game wiki), with the effective skill stored in the save. Burst weapons count all shots; ammo, feats and precision are left out. ⚠ = Strength too low (less precision).': 'Dein Schaden/AP = Schaden × (1 + 0,7 × effektiver Skill / 100), bei Pistolen und Messern 0,5 (Spiel-Wiki), mit dem effektiven Skill aus dem Spielstand. Feuerstöße zählen alle Schüsse; Munition, Feats und Präzision bleiben außen vor. ⚠ = Stärke zu niedrig (weniger Präzision).',
    'Weapons: see the Weapons tab – sortable by every stat and filtered to this build.': 'Waffen: siehe Tab „Waffen“ – nach jedem Wert sortierbar und auf diesen Build gefiltert.',
    'All areas': 'Alle Bereiche',
    'Area:': 'Bereich:',
    'South Gate Station': 'South Gate Station',
    'Foundry Mine': 'Foundry-Mine',
    'Lower Passages': 'Lower Passages',
    'Waterways': 'Wasserwege',
    'Caves': 'Höhlen',
    'Lower Underrail': 'Lower Underrail',
    'Upper Underrail': 'Upper Underrail',
    'Deep Caverns': 'Deep Caverns',
    'Institute of Tchort': 'Institut von Tchort',
    'Warehouses': 'Lagerhäuser',
    'GMS Compound': 'GMS-Komplex',
    'Black Sea': 'Schwarzes Meer',
    'Other': 'Sonstiges',
    'Core City': 'Core City',
    'Foundry': 'Foundry',
    'Junkyard': 'Junkyard',
    'Rail Crossing': 'Rail Crossing',
    'Total weight': 'Gesamtgewicht',
    'Weight: {total} (+{worn} equipped)': 'Gewicht: {total} (+{worn} ausgerüstet)',
    'Sort by "Total weight" to see what weighs you down. Stacks count weight × stack size.': 'Nach „Gesamtgewicht“ sortieren, um zu sehen, was dich belastet. Stapel zählen Gewicht × Anzahl.',
    '"{name}" has unsaved changes. Save them before continuing?': '„{name}“ hat ungespeicherte Änderungen. Vor dem Fortfahren speichern?',
    'Rarity': 'Seltenheit',
    'Details': 'Details',
    'size: {s}': 'Größe: {s}',
    'power {p}': 'Leistung {p}',
    'small': 'klein',
    'medium': 'mittel',
    'large': 'groß',
    'like the one you have': 'wie bei deinem vorhandenen',
    'typical value': 'typischer Wert',
    'this component has no quality': 'diese Komponente hat keine Qualität',
    'Junk': 'Schrott',
    'Common': 'Gewöhnlich',
    'Fine': 'Fein',
    'Good': 'Gut',
    'Superior': 'Überlegen',
    'Excellent': 'Exzellent',
    'Unique': 'Einzigartig',
    'engines': 'Motoren',
    'batteries': 'Batterien',
    'frames': 'Rahmen',
    'jet ski suspensions': 'Jetski-Federungen',
    'ammo': 'Munition',
    'weapons': 'Waffen',
    'chemicals': 'Chemikalien',
    'armors': 'Rüstungsteile',
    'bio': 'Bio',
    'animals': 'Tierteile',
    'containers': 'Behälter',
    'devices': 'Geräte',
    'plants': 'Pflanzen',
    'ammocase': 'Munitionshülsen',
    'metalarmorenhancements': 'Metallrüstungs-Verbesserungen',
    'medical': 'Medizin',
    'vest': 'Westen',
    'scraps': 'Schrott',
    'emitters': 'Emitter',
    'explosives': 'Sprengstoffe',
    'modulators': 'Modulatoren',
    'ballistic panels': 'Ballistische Platten',
    'armor plates': 'Panzerplatten',
    'energycores': 'Energiekerne',
    'Uncommon': 'Ungewöhnlich',
    'Rare': 'Selten',
    'Quest item': 'Quest-Gegenstand',
    'all subcategories': 'alle Unterkategorien',
    'Search name, type, size, rarity, description…': 'Name, Typ, Größe, Seltenheit, Beschreibung suchen…',
    'all sizes': 'alle Größen',
    'Points / experience / vitals': 'Punkte / Erfahrung / Vitalwerte',
    'World map': 'Weltkarte',
    'World map…': 'Weltkarte…',
    'View': 'Ansicht',
    "Open the game's world map (Ctrl+M)": 'Die Weltkarte des Spiels öffnen (Strg+M)',
    'Find a zone…': 'Zone suchen…',
    'Click a zone to see its merchants, creatures and the items lying there.': 'Klicke auf eine Zone, um ihre Händler, Kreaturen und die dort liegenden Items zu sehen.',
    'No zone found for {q}.': 'Keine Zone für „{q}“ gefunden.',
    'Characters and creatures': 'Charaktere und Kreaturen',
    'Items': 'Items',
    'Nothing recorded for this zone.': 'Für diese Zone ist nichts verzeichnet.',
    'Click an item to see everywhere it can be found.': 'Klicke auf ein Item, um alle Fundorte zu sehen.',
    'Upper Caves': 'Obere Höhlen',
    'Lower Caves': 'Untere Höhlen',
    'Close': 'Schließen',
    '{n}× {name} added': '{n}× {name} hinzugefügt',
    'Could not add {name}: {e}': '{name} konnte nicht hinzugefügt werden: {e}',
    'Creatures': 'Kreaturen',
    'The most common characters and creatures placed in each zone.': 'Die häufigsten Charaktere und Kreaturen je Zone.',
    'Loading {name}…': 'Lade {name}…',
    'Loaded {name} – {char}, level {level}': '{name} geladen – {char}, Level {level}',
    'File': 'Datei',
    'Quit': 'Beenden',
    'Your character is here.': 'Dein Charakter ist hier.',
    'Icons of the game': 'Icons des Spiels',
    'Plants': 'Pflanzen',
    'Merchants and doctors': 'Händler und Ärzte',
    'Labels from the game data': 'Beschriftungen aus den Spieldaten',
    'Merchant names': 'Händlernamen',
    'Creatures and characters': 'Kreaturen und Charaktere',
    'Loot (items lying there)': 'Beute (dort liegende Items)',
    'Layers': 'Ebenen',
    'Loot: {n}': 'Beute: {n}',
    'random': 'zufällig',
    '{n} items': '{n} Items',
    '{n} random': '{n} zufällig',
    'All locations on the map…': 'Alle Fundorte auf der Karte…',
    'Where to get {item}': 'Wo bekommt man {item}',
    'Where': 'Wo', 'How': 'Wie', 'Count': 'Anzahl',
    'always in stock': 'fest im Sortiment', 'random stock': 'Zufallssortiment',
    'Merchant': 'Händler', 'Found in the world': 'In der Spielwelt', 'Creature': 'Kreatur',
    'Numbers: how many. Wheel zooms, drag pans, click a zone for its entries.':
        'Zahlen: Anzahl. Mausrad zoomt, Ziehen verschiebt, Klick auf eine Zone zeigt ihre Einträge.',
    'This zone has no marker on the world map (dungeon or interior).':
        'Diese Zone hat keinen Marker auf der Weltkarte (Dungeon oder Innenraum).',
    'not sold by merchants (loot or quest)': 'nicht beim Händler (Beute oder Quest)',
    'Computed from your game files with the formulas the game uses. Armor values at component quality {q}; merchants in bold always stock the item, the others may roll it in their random stock.':
        'Berechnet aus deinen Spieldateien mit den Formeln des Spiels. Rüstungswerte bei Komponenten-Qualität {q}; '
        'fett gedruckte Händler führen das Item fest, die anderen können es im Zufallssortiment haben.',
    'You have Armor Sloping: metal plates cost you about 35% less armor penalty than listed (more with its specialization).':
        'Du hast Armor Sloping: Metallplatten kosten dich etwa 35 % weniger Rüstungsmalus als angegeben (mit Spezialisierung mehr).',
    'You have Ballistics: carrier vests add extra mechanical damage threshold.':
        'Du hast Ballistics: Trägerwesten geben zusätzliche mechanische Schadensschwelle.',
    'You have Juggernaut: +25% health only while the armor penalty of your suit is at least 50%.':
        'Du hast Juggernaut: +25 % Lebenspunkte nur, solange der Rüstungsmalus deiner Rüstung mindestens 50 % beträgt.',
    'Best weapons (damage per action point)': 'Beste Waffen (Schaden pro Aktionspunkt)',
    'Base values without ammo, feats or precision; burst weapons count all shots.':
        'Grundwerte ohne Munition, Feats oder Präzision; Feuerstoßwaffen zählen alle Schüsse.',
    'Weapon': 'Waffe', 'Type': 'Typ', 'Damage': 'Schaden', 'AP': 'AP', 'Burst': 'Feuerstoß', 'Dmg/AP': 'Schaden/AP',
    'Where to buy': 'Wo kaufen',
    'Pistol': 'Pistole', 'SMG': 'MP', 'Assault rifle': 'Sturmgewehr', 'Sniper rifle': 'Scharfschützengewehr',
    'Shotgun': 'Schrotflinte', 'Crossbow / special': 'Armbrust / Spezial', 'Melee': 'Nahkampf',
    'Grenade launcher': 'Granatwerfer', 'Heavy energy': 'Schwere Energiewaffe', 'Light machine gun': 'MG',
    'Minigun': 'Minigun', 'Rocket launcher': 'Raketenwerfer',
    'Best armor combinations (protection vs. armor penalty)': 'Beste Rüstungskombinationen (Schutz gegen Rüstungsmalus)',
    "Armor penalty doesn't depend on quality – quality only raises protection. Penalties of worn pieces add up. Values: resistance %/threshold.":
        'Der Rüstungsmalus hängt nicht von der Qualität ab – Qualität erhöht nur den Schutz. Die Mali getragener Teile '
        'addieren sich. Werte: Resistenz %/Schwelle.',
    'Tactical vest': 'Taktische Weste', 'Metal armor': 'Metallrüstung', 'Leather armor': 'Lederrüstung',
    'Metal helmet': 'Metallhelm', 'Boots': 'Stiefel', 'Greaves': 'Beinschienen',
    'Components': 'Komponenten', 'Penalty': 'Malus', 'Strength': 'Stärke', 'Protection': 'Schutz',
    'carrier vest': 'Trägerweste', 'ballistic panel': 'Ballistik-Panel', 'armor plate': 'Panzerplatte',
    'fabric': 'Stoff', 'metal plates': 'Metallplatten', 'leather': 'Leder', 'padding': 'Polsterung',
    'Where to get the components': 'Wo es die Komponenten gibt', 'Component': 'Komponente',
    'Leathers, carapaces and similar animal parts also come from skinning the creature with Skinner/Hunter; metal sheets and plates also drop as loot.':
        'Leder, Panzer und ähnliche Tierteile bekommt man auch durch Häuten der Kreatur (Skinner/Hunter); Metallbleche '
        'und -platten gibt es auch als Beute.',
    'Feat · max': 'Feat · Max',
    'feat missing': 'Feat fehlt',
    'All specializations of your feats are already present': 'Alle Spezialisierungen deiner Feats sind bereits vorhanden',
    '{n} specializations are hidden because the character lacks their feat.':
        '{n} Spezialisierungen sind ausgeblendet, weil dem Charakter der zugehörige Feat fehlt.',
    "Specializations marked ⚠ belong to a feat the character doesn't have; the game only uses them together with the feat.":
        'Mit ⚠ markierte Spezialisierungen gehören zu einem Feat, den der Charakter nicht hat; das Spiel nutzt sie nur '
        'zusammen mit dem Feat.',
    'Not available when leveling up (character creation, quests, trainers or events)':
        'Nicht beim Levelaufstieg wählbar (Charaktererstellung, Quests, Trainer oder Ereignisse)',
    'Hide entries whose requirements your character does not meet': 'Einträge ausblenden, deren Voraussetzungen der Charakter nicht erfüllt',
    'Requirements not met:': 'Voraussetzungen nicht erfüllt:',
    'Requirements:': 'Voraussetzungen:',
    'No requirements': 'Keine Voraussetzungen',
    'none': 'keine',
    'modified': 'effektiv',
    'or': 'oder',
    'Any psi skill {n}': 'Beliebiger Psi-Skill {n}',
    'Level {n}': 'Level {n}',
    'Feat: {names}': 'Feat: {names}',
    'Not together with: {names}': 'Nicht zusammen mit: {names}',
    'Psi ability: {names}': 'Psi-Fähigkeit: {names}',
    'Only one "Increased <attribute>" feat': 'Nur ein „Increased <Attribut>“-Feat',
    'Only one "Empowered" invocation feat': 'Nur ein „Empowered“-Feat',
    'you have {n}': 'du hast {n}',
    'you have {names}': 'du hast {names}',
    "Feats marked ⚠ don't meet the game's requirements (checked against base values, as the game does); they can still be added. Adding a feat only records it as learned.":
        'Mit ⚠ markierte Feats erfüllen die Voraussetzungen des Spiels nicht (geprüft gegen Grundwerte, wie im '
        'Spiel); hinzufügen lassen sie sich trotzdem. Ein hinzugefügter Feat wird nur als gelernt eingetragen.',
    'no money': 'kein Geld',
    'Component quality. The game has no upper limit; above {n} the quality bonus curve stops rising, but higher values still scale the stats linearly.':
        'Komponenten-Qualität. Das Spiel hat keine Obergrenze; über {n} steigt die Bonuskurve nicht weiter, '
        'höhere Werte skalieren die Werte aber weiterhin linear.',
    'This save had {n} broken object id(s) from an older editor version; they were repaired – save to fix the file.':
        'Dieser Spielstand hatte {n} fehlerhafte Objekt-Id(s) aus einer älteren Editor-Version; sie wurden '
        'repariert – zum Beheben speichern.',
    'loading…': 'lädt…',
    'Portrait imported': 'Portrait importiert',
    'Saved as "{pid}" in the CustomPortraits folder. Underrail reads custom portraits when it starts, so restart the game after saving.':
        'Als „{pid}“ im Ordner CustomPortraits gespeichert. Underrail liest eigene Portraits beim Start ein, '
        'also das Spiel nach dem Speichern neu starten.',
    'Settings': 'Einstellungen',
    'Game folders…': 'Spielordner…',
    'Game folders': 'Spielordner',
    'Game installation': 'Spielinstallation',
    'User folder': 'Benutzerordner',
    'Folder containing underrail.exe': 'Ordner mit underrail.exe',
    'Folder containing "Saves" (Documents/My Games/Underrail)': 'Ordner mit „Saves“ (Dokumente/My Games/Underrail)',
    'Browse…': 'Durchsuchen…',
    'Detect automatically': 'Automatisch erkennen',
    'Steam (also on Steam Deck / SD cards / Flatpak), GOG and Proton/Wine prefixes are searched automatically. Pick the folders yourself if they are somewhere else.':
        'Steam (auch Steam Deck / SD-Karte / Flatpak), GOG und Proton/Wine-Präfixe werden automatisch durchsucht. '
        'Liegen die Ordner woanders, hier selbst auswählen.',
    'found': 'gefunden',
    'underrail.exe not found here': 'underrail.exe hier nicht gefunden',
    'no "Saves" folder here': 'kein „Saves“-Ordner hier',
    'Underrail was not found. Choose its folders under Settings → Game folders…':
        'Underrail wurde nicht gefunden. Ordner unter Einstellungen → Spielordner… auswählen.',
    'Save changed on disk': 'Spielstand geändert',
    'The game has changed this save since you opened it. Saving overwrites those changes (a backup is made first).\nSave anyway?':
        'Das Spiel hat diesen Spielstand seit dem Öffnen geändert. Speichern überschreibt diese Änderungen '
        '(vorher wird ein Backup angelegt).\nTrotzdem speichern?',
    'Reload the save list (F5). The list also updates by itself when the game saves.':
        'Spielstand-Liste neu laden (F5). Die Liste aktualisiert sich auch selbst, wenn das Spiel speichert.',
    "This save was changed on disk (by the game?). Revert/reselect it to reload; saving now would overwrite the game's version.":
        'Dieser Spielstand wurde auf der Festplatte geändert (vom Spiel?). Mit „Verwerfen“ neu laden; '
        'Speichern würde die Version des Spiels überschreiben.',
    'Repair broken locations…': 'Defekte Orte reparieren…',
    'Repair broken locations': 'Defekte Orte reparieren',
    "The game can't load these locations of this save: {names}. File → Repair broken locations… resets them.":
        'Das Spiel kann diese Orte dieses Spielstands nicht laden: {names}. Datei → Defekte Orte reparieren… '
        'setzt sie zurück.',
    'The data of these locations is unreadable, the game cannot enter them: {names}.\n'
    'Repairing removes their stored state, so the game rebuilds them as if never visited '
    '(looted containers, killed enemies there are reset). A backup is made first.\nRepair?':
        'Die Daten dieser Orte sind unlesbar, das Spiel kann sie nicht betreten: {names}.\n'
        'Beim Reparieren wird ihr gespeicherter Zustand entfernt, das Spiel baut sie neu auf, als wärst du nie '
        'dort gewesen (geplünderte Behälter, getötete Gegner dort werden zurückgesetzt). '
        'Vorher wird ein Backup angelegt.\nReparieren?',
    'Underrail is running and may replace this save on its own, which would undo the repair.\nRepair anyway?':
        'Underrail läuft und kann diesen Spielstand selbst ersetzen, wodurch die Reparatur verloren ginge.\n'
        'Trotzdem reparieren?',
    'Repair failed': 'Reparatur fehlgeschlagen',
    'Repaired {names}. Backup: {path}': 'Repariert: {names}. Backup: {path}',
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
    # factions tab
    'Factions': 'Fraktionen',
    'The Faceless': 'Die Faceless',
    'Kill counters': 'Kill-Zähler',
    'Attitudes': 'Beziehungen',
    'Hostile': 'Feindlich',
    'Wary': 'Misstrauisch',
    'Neutral': 'Neutral',
    'Friendly': 'Freundlich',
    'Allied': 'Verbündet',
    'At Talos Outpost (Deep Caverns) the Faceless commander has your mind read and adds up a score from how you '
    'treated the Faceless before – the game\'s own calculation, shown here live. 3 or more: allies, 1–2: friendly, '
    '0: neutral, below 0: hostile. Change the kill counts or what happened to reach the score you want; it only '
    'counts before that conversation.':
        'Im Talos Outpost (Deep Caverns) lässt der Faceless-Kommandant deine Gedanken lesen und zählt einen Wert '
        'daraus zusammen, wie du die Faceless bisher behandelt hast – die Berechnung des Spiels, hier live. '
        'Ab 3: Verbündete, 1–2: freundlich, 0: neutral, unter 0: feindlich. Ändere die Kill-Zahlen oder die '
        'Ereignisse, um den gewünschten Wert zu erreichen; das zählt nur vor diesem Gespräch.',
    'Faceless killed': 'Getötete Faceless',
    "Faceless killed in Buzzer's shop (Rail Crossing)": 'Getötete Faceless in Buzzers Laden (Rail Crossing)',
    'Faceless recon near Foundry finished': 'Faceless-Aufklärung bei Foundry abgeschlossen',
    'Rail Crossing mindreader left safely': 'Gedankenleser in Rail Crossing ist sicher abgezogen',
    'Rail Crossing mindreader died': 'Gedankenleser in Rail Crossing ist gestorben',
    'Injured Faceless in Core City released': 'Verletzten Faceless in Core City freigelassen',
    'Injured Faceless in Core City killed': 'Verletzten Faceless in Core City getötet',
    'Injured Faceless in Core City attacked': 'Verletzten Faceless in Core City angegriffen',
    'Thought Control check at the mindreading passed': 'Thought-Control-Probe beim Gedankenlesen bestanden',
    'The game sets this when you pass the Thought Control check (120) during the mindreading; it cancels every '
    'penalty.':
        'Das Spiel setzt das, wenn du beim Gedankenlesen die Thought-Control-Probe (120) bestehst; '
        'sie hebt alle Abzüge auf.',
    'Your attitude toward the Faceless near Foundry': 'Deine Einstellung zu den Faceless bei Foundry',
    "Score already calculated (used by the commander's dialog)":
        'Bereits berechneter Wert (nutzt der Dialog des Kommandanten)',
    'Faceless recon near Foundry finished and you are not hostile to them':
        'Faceless-Aufklärung bei Foundry abgeschlossen und du bist ihnen nicht feindlich',
    'Injured Faceless in Core City released unharmed': 'Verletzten Faceless in Core City unversehrt freigelassen',
    'You are hostile to the Faceless near Foundry': 'Du bist den Faceless bei Foundry feindlich',
    'More than {limit} Faceless killed ({n})': 'Mehr als {limit} Faceless getötet ({n})',
    '{n} Faceless killed (one point per {per} after the first)':
        '{n} Faceless getötet (ein Punkt je {per} nach dem ersten)',
    'Nothing counts for or against you': 'Nichts zählt für oder gegen dich',
    'Score': 'Wert',
    'Allies – they share information and supplies': 'Verbündete – sie teilen Informationen und Vorräte',
    'Friendly – some information and supplies': 'Freundlich – etwas Information und Vorräte',
    'Neutral – free passage, nothing else': 'Neutral – freier Durchgang, sonst nichts',
    'Hostile – they attack after the mindreading': 'Feindlich – sie greifen nach dem Gedankenlesen an',
    'Faceless kills counted: {n} (both counters). More than {limit} sets the score to -5; below that one point is '
    'lost per {per} kills after the first on this difficulty.':
        'Gezählte Faceless-Kills: {n} (beide Zähler). Mehr als {limit} setzen den Wert auf -5; darunter kostet '
        'auf diesem Schwierigkeitsgrad jede {per}. Tötung nach der ersten einen Punkt.',
    "You started the Tchortists' job to scout Faceless positions: the commander calls you a spy whatever the "
    "score, unless the Thought Control check passes or the Deep Caverns Tchortists are hostile to you.":
        'Du hast den Auftrag der Tchortisten angenommen, Faceless-Stellungen auszukundschaften: Der Kommandant '
        'hält dich unabhängig vom Wert für einen Spion, außer die Thought-Control-Probe gelingt oder die '
        'Tchortisten in den Deep Caverns sind dir feindlich.',
    'Kill counters of other factions that the game checks. The Faceless ones are on their own page.':
        'Kill-Zähler anderer Fraktionen, die das Spiel prüft. Die der Faceless stehen auf ihrer eigenen Seite.',
    'Effect': 'Wirkung',
    'Pirates killed (Expedition)': 'Getötete Piraten (Expedition)',
    "Dialogs react at 30, 50 and 60; from 50 the game skips the pirates' attack events.":
        'Dialoge reagieren bei 30, 50 und 60; ab 50 überspringt das Spiel die Angriffs-Ereignisse der Piraten.',
    'Protectorate jet ski patrols killed (Expedition)': 'Getötete Jetski-Patrouillen des Protectorate (Expedition)',
    'From 10 people talk about the decimated patrols; the waterway scripts also check it.':
        'Ab 10 reden Leute über die dezimierten Patrouillen; auch die Skripte der Wasserwege prüfen den Wert.',
    'Exosoldiers killed (Heavy Duty)': 'Getötete Exosoldaten (Heavy Duty)',
    'Above 0 the psi commander answers differently; from 12 the game sets "too many killed".':
        'Über 0 antwortet der Psi-Kommandant anders; ab 12 setzt das Spiel „zu viele getötet“.',
    'Faction': 'Fraktion',
    'ID': 'ID',
    'Toward you': 'Zu dir',
    'Yours': 'Deine',
    'Your override': 'Eigene Vorgabe',
    'Only hostile': 'Nur feindliche',
    'Toward you: how the faction treats the player\'s faction. Yours: the player\'s faction toward them. Your '
    'override: your character\'s own attitude, which wins over "Yours". Make a faction peaceful by setting both '
    'directions (and the override) to Neutral or better. People you already fought in a place may keep their own '
    'grudge, which is stored with that place. Factions without a stored relation are Neutral.':
        'Zu dir: wie die Fraktion die Fraktion des Spielers behandelt. Deine: die Fraktion des Spielers ihr '
        'gegenüber. Eigene Vorgabe: die persönliche Einstellung deines Charakters, sie geht vor „Deine“. '
        'Friedlich wird eine Fraktion, wenn beide Richtungen (und die eigene Vorgabe) mindestens Neutral sind. '
        'Leute, mit denen du an einem Ort schon gekämpft hast, können ihren eigenen Groll behalten, der bei '
        'diesem Ort gespeichert ist. Fraktionen ohne gespeicherte Beziehung sind neutral.',
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
        system = QLocale.system().name().split('_')[0]  # e.g. 'de_AT' -> 'de'
        # explicit choice, else the system language if translated, else English
        _lang = c if c in LANGUAGES else (system if system in LANGUAGES else 'en')
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
