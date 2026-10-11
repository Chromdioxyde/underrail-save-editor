# Underrail Save Editor

Save game editor for Underrail (Steam/Proton on Linux) with a GUI (PySide6) and a small CLI.
Requires Python 3, PySide6 and Pillow. Game data (item names, feats, portraits) is read directly from
the Underrail installation.

## Download and run

- **Linux / Steam Deck:** the AppImage bundles Python, Qt and Pillow. Make it executable and run it
  (on the Steam Deck: Desktop Mode, right-click → Properties → Permissions → executable, then double-click).
  Needs glibc ≥ 2.28 and libstdc++ from GCC 11+ (SteamOS 3, Ubuntu 22.04, Debian 12, Fedora 35 or newer).
- **Windows:** unzip `UnderrailSaveEditor-…-windows-x64.zip` and start `UnderrailSaveEditor.exe`.

The game and save folders are detected automatically: all Steam libraries (incl. SD cards and Flatpak
Steam), GOG on Windows, the Proton prefix on Linux and `Documents\My Games\Underrail` on Windows. If
nothing is found, choose them under *Settings → Game folders…*.

## Install from source (Linux)

```
./packaging/install.sh      # per-user, no root; re-run to update
./packaging/uninstall.sh    # removes the app, keeps backups
```

Installs the program to `~/.local/share/underrail-save-editor/app`, the launchers `underrail-save-editor`
(GUI) and `underrail-spec` (CLI) to `~/.local/bin`, plus an icon and an application menu entry.
Dependencies: PySide6 and Pillow (on Arch-based systems: `sudo pacman -S pyside6 python-pillow`).

## Usage

```
./underrail_gui.py                                   # GUI
./underrail_spec.py quicksave list                   # list specializations
./underrail_spec.py quicksave set GunNutDamage=8     # set a specialization
./underrail_spec.py quicksave unspent 2              # unspent specialization points
```

Quit Underrail before saving, otherwise the game may overwrite the save.
Before every save, `global.dat` and `info.dat` are copied to
`~/.local/share/underrail-save-editor/backups/<save>/<timestamp>/`.
To roll back, copy both files back into the save folder.

The GUI is available in English and German. It follows the system language by default; the
*Language* menu overrides it (stored via QSettings). Game terms (items, feats, skills, attributes)
always appear as the game names them.

## Features (GUI)

- **Character:** name, level, portrait (gallery of all game portraits, import your own image as PNG),
  XP, unspent attribute/skill/feat/specialization points, current health
- **Attributes / Skills:** base values (the saved effective value is shifted by the same delta)
- **Feats:** all feats with descriptions, add/remove via checkbox; feats whose requirements your
  character doesn't meet (or that can't be picked when leveling up) are marked with the reasons, and
  *Only available* hides them
- **Specializations:** edit values (up to the game's maximum per specialization), add/remove; only
  specializations of feats the character has are offered, like in the game
- **Inventory:** item icons, sortable (click a column header) and filterable by category; stack size, component
  quality, durability (with maximum, *Repair* / *Repair all*), battery; add items from all ~1460 game
  items, duplicate (crafted items too), remove; edit equipped items
- **Blueprints:** learn/forget known crafting blueprints (all 117 from the game data), *Learn all*
- **Oddities:** collection counters

Test structural changes (feats, specializations, blueprints, items, name, portrait) on a copy first.

## Custom portraits

At startup the game scans `Documents/My Games/Underrail/CustomPortraits` for `*_l.png` and loads
`<id>_h.png`, `<id>_l.png`, `<id>_s.png` (200/100/50 px), using the lower-cased file name as portrait
id (verified in `underrail.exe`). *Import PNG…* in the portrait dialog crops an image to a square and
writes the three sizes there; restart the game afterwards.

## Item icons

Icons are cut out of the game's sprite sheets (`data/icons/*.xnb`) on first start (a few seconds,
cached in `~/.cache/underrail-save-editor/icons/`). An item's visual id (`I:VM`) is either a name from
`icons.iconset` (grid cell(s) per sheet; multi-part icons are layers with their own opacity) or
`<Sheet>.<n>` = cell n of a 10-column grid. Bullets are registered by the game at runtime from the
`AmmoType` enum (value v → column `v % 100 − 1`, row `v // 100 − 1` on the Ammo sheet); that mapping
is extracted into `data/ammo_icons.json`. Cells are 33 px on a 34 px pitch. About 95 % of the items
have their own icon. The rest (crafted weapons with composite visuals such as `sniper.4.frame`, some
ammo) get a faded placeholder: the icon of a typical item of the same category, item class and weapon
type, or the game's generic weapon icon.

## Durability and quality

Maximum durability is not stored in the save; the game computes it from the item level `I:L`
(taken from `underrail.exe`): `120 + 60·L + 30·max(0, L−5)`, a flat 200 at level 0; light machine
guns and miniguns (`WI:WT` 9/10) get double. Applies to weapons, armor, helmets, boots and shield
emitters; belts don't wear down. Checked against the world data: 99 of 130 items match exactly, almost
all others are below (worn), two are above (probably templates changed by a game update).

Component quality is `CII:QL` (0 = component without a quality value). The game doesn't cap it: stats
scale with `Q · (0.77 + 0.35 · min(1, max(0, Q−15)/170)^1.35)`, so the bonus curve flattens at 185 but
higher values still count. The editor allows up to 999.

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

## Building

```
./packaging/build-appimage.sh          # -> build/Underrail_Save_Editor-<version>-x86_64.AppImage
```

The AppImage uses a portable CPython (python-build-standalone) and manylinux wheels, so it doesn't depend
on the build machine's libraries. The Windows build uses PyInstaller and has to run on Windows:

```
python -m pip install pyinstaller PySide6-Essentials pillow
python packaging/make_icon.py build
pyinstaller --noconfirm --distpath build/dist --workpath build/work packaging/underrail-save-editor.spec
```

`.github/workflows/build.yml` builds both on every push and attaches them to a GitHub release for
`v*` tags.

## Feat requirements

`data/feat_requirements.json` is generated from `underrail.exe` by `tools/extract_feat_requirements.py`
(needs `pip install dnfile dncil`; re-run after game updates). The tool reads each feat class's
requirement method: attribute and skill minimums (compared against base values like the game does),
required and excluded feats, character level, any psi skill, known psi abilities, and whether the
level-up screen offers the feat at all. It also reads every specialization class: the feat it belongs
to and its maximum points.
