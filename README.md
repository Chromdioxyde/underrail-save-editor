# Underrail Save Editor

Save game editor for Underrail (Steam/Proton on Linux) with a GUI (PySide6) and a small CLI.
Requires Python 3, PySide6 and Pillow. Game data (item names, feats, portraits) is read directly from
the Underrail installation.

## Usage

```
./underrail_gui.py                                   # GUI
./underrail_spec.py quicksave list                   # list specializations
./underrail_spec.py quicksave set GunNutDamage=8     # set a specialization
./underrail_spec.py quicksave unspent 2              # unspent specialization points
```

Quit Underrail before saving, otherwise the game may overwrite the save.
Before every save, `global.dat` and `info.dat` are copied to `backups/<save>/<timestamp>/`.
To roll back, copy both files back into the save folder.

The GUI is available in English and German. It follows the system language by default; the
*Language* menu overrides it (stored via QSettings). Game terms (items, feats, skills, attributes)
always appear as the game names them.

## Features (GUI)

- **Character:** name, level, portrait (gallery of all game portraits, import your own image as PNG),
  XP, unspent attribute/skill/feat/specialization points, current health
- **Attributes / Skills:** base values (the saved effective value is shifted by the same delta)
- **Feats:** all feats with descriptions, add/remove via checkbox
- **Specializations:** edit values, add/remove specializations
- **Inventory:** item icons, sortable (click a column header) and filterable by category; stack size, component
  quality, durability (with maximum, *Repair* / *Repair all*), battery; add items from all ~1460 game
  items, duplicate (crafted items too), remove; edit equipped items
- **Blueprints:** learn/forget known crafting blueprints (all 117 from the game data), *Learn all*
- **Oddities:** collection counters

Test structural changes (feats, specializations, blueprints, items, name, portrait) on a copy first.

## Custom portraits

The game reads `CustomPortraits/<id>_s.png`, `<id>_l.png`, `<id>_h.png` (50/100/200 px) from
`Documents/My Games/Underrail`. *Import PNG…* in the portrait dialog crops the image to a square and
writes the three sizes there.

## Item icons

Icons are cut out of the game's sprite sheets (`data/icons/*.xnb`) on first start (a few seconds,
cached in `~/.cache/underrail-save-editor/icons/`). An item's visual id (`I:VM`) is either a name from
`icons.iconset` (grid cell(s) per sheet; multi-part icons are layers with their own opacity) or
`<Sheet>.<n>` = cell n of a 10-column grid. Cells are 33 px on a 34 px pitch. About 95 % of the items
get an icon; crafted weapons with composite visuals (`sniper.4.frame` …) don't.

## Durability and quality

Maximum durability is not stored in the save; the game computes it from the item level `I:L`
(taken from `underrail.exe`): `120 + 60·L + 30·max(0, L−5)`, a flat 200 at level 0; light machine
guns and miniguns (`WI:WT` 9/10) get double. Applies to weapons, armor, helmets, boots and shield
emitters; belts don't wear down. Checked against the world data: 99 of 130 items match exactly, almost
all others are below (worn), two are above (probably templates changed by a game update).

Component quality is `CII:QL` (0 = component without a quality value). The editor caps it at 185, the
upper quality value in the game's configuration.

## Save format

`global.dat` = 24-byte header (GUID + version) + gzip-compressed .NET BinaryFormatter stream (MS-NRBF).
`nrbf.py` reads the stream into an object graph and writes it back – byte-identical when unchanged,
changed/new objects get their own class metadata. `xnb.py` decodes the LZX-compressed XNB portraits
(DXT1/3/5).

The player is `TG:PC` (class `P2`). Important members:

| Member | Content |
|---|---|
| `C1:N`, `C1:L`, `C1:P2` | name, level, portrait id (name/level also in `info.dat`: `SGI:CN`, `SGI:CL`) |
| `C1:BA` → `BA3:BA:i` | attributes (`S4:V` base, `S4:MV` effective, `BA2:N` name) |
| `C1:S` → `S3:S:i` | skills (unnamed, in in-game order) |
| `C1:F` → `F:F:i` | feats (`FR:FTN` = feat id from `data/knowledge/feats.k`) |
| `C1:SPC:i:Key/Value` | specializations (`SNF:V`, `SNF:M`, always set together) |
| `C1:B` → `IC:I:i` | inventory; item: `II:S` stack, `II:D` durability, `II:B` battery (capacity `I:MB` of the item data), `CII:QL` component quality, `II:DP` template (`LIDP:P` path under `data/rules/items`) or embedded data (`IIDP:D`, crafted) |
| `C1:G` | equipment slots (`IS:I` = item) |
| `C1:D2` → `CD1:H` | health (`BV:V`/`BV:MX`) |
| `PC1:E` | XP |
| `PC1:BAPC`, `PC1:SPC`, `PC1:FC`, `PC1:SP` | unspent attribute/skill/feat/specialization points |
| `PC1:O:i:Key/Value` | oddities |
| `PC1:B` | known blueprints: .NET `SortedList` name → `IBR` (`IBR:IBFTN` = lower-case id from `data/knowledge/itemblueprints.k`). Not re-sorted on load and read by binary search → entries are inserted in .NET culture order (`gamedata.sort_key`, verified against saved lists) |
