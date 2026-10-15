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

- **Save list:** cards with screenshot, character, location, play time, HP/XP, money; updates when the game
  saves. It closes once you pick a save, so the editor gets the whole window; *Saves* (next to the title),
  *View → Save list* or Ctrl+L open it again.
- **Character:** name, level, portrait (gallery of all game portraits, import your own image as PNG),
  attributes, XP, unspent attribute/skill/feat/specialization points, current health
- **Attributes / Skills:** base values (the saved effective value is shifted by the same delta)
- **Feats:** all feats with descriptions, add/remove via checkbox; feats whose requirements your
  character doesn't meet (or that can't be picked when leveling up) are marked with the reasons, and
  *Only available* hides them
- **Specializations:** edit values (up to the game's maximum per specialization), add/remove; only
  specializations of feats the character has are offered, like in the game
- **Inventory:** weight and total weight (weight × stack) columns plus the total carried, to find what
  makes you encumbered; rarity tiers coloured like in the game (common white/plain, uncommon green, rare blue,
  unique purple, the quest-item tier gold; broken junk grey); category filter in steps
  (category, then optionally a subcategory and, for vehicle parts, the build size – all by default); the game's description in the tooltip. *Add item…* stays open after adding (double-click or *Add*, with a short confirmation) and searches names, type, size, rarity, details and the game
  description in English and German, word by word ("mittlerer Motor", "large engine"), and shows type, rarity and details
  (vehicle parts: build size small/medium/large from `VPI:S`, engine power `VEI:P`), presets durability
  (full), batteries (full) and component quality (your own item's, else 100; locked to 0 for components
  without a quality).
  Selecting a weapon or armor piece compares it with what is equipped in its slot (both
  weapon slots for weapons): damage, AP, damage per AP and your damage per AP, crit, precision,
  Strength, range, magazine, resistances/thresholds per damage type, armor penalty, level, durability,
  weight – differences green/red like in Diablo. Item icons, sortable (click a column header) and filterable by category; stack size, component
  quality, durability (with maximum, *Repair* / *Repair all*), battery; add items from all ~1460 game
  items, duplicate (crafted items too), remove; edit equipped items
- **Blueprints:** learn/forget known crafting blueprints (all 117 from the game data), *Learn all*
- **Oddities:** collection counters
- **Factions:**
  - *The Faceless*: the checkpoint guards at the edge of Faceless territory decide once, at the first meeting,
    whether you may pass (Foundry recon finished and those Faceless not hostile to you, or the Rail Crossing
    mindreader left safely) and only repeat that verdict afterwards; without the pass the Talos Outpost entrance
    guard attacks. The editor shows the stored verdict and can set it, or let the next meeting decide again.
    Then the attitude score the Faceless commander at Talos Outpost (Deep Caverns) computes when
    he has your mind read, using the game's own calculation (read from its IL). The breakdown updates live
    while you edit its inputs: Faceless kill counters (more than 10 kills set the score to -5; below that the
    loss per kill depends on the difficulty), what happened with the Foundry recon group, the Rail Crossing
    mindreader and the injured Faceless in Core City, the Thought Control check, and your attitude toward the
    Foundry Faceless. It shows the outcome (3+ allies, 1–2 friendly, 0 neutral, below 0 hostile) and warns
    when the Tchortists' scouting job will get you called a spy anyway. Once the score has been calculated
    it can be edited directly.
  - *Kill counters*: other faction kill counters the game checks (Expedition pirates and Protectorate jet ski
    patrols, Heavy Duty exosoldiers), with what they affect.
  - *Attitudes*: every faction's attitude toward the player and back, plus your character's own overrides;
    filter, *Only hostile*.
- **Hints:** tailored to a build (assault rifle, sniper, SMG, pistol, shotgun, heavy guns, crossbow,
  stealth knife, unarmed/psi monk, sledgehammer, spear, sword, throwing, psi – the archetypes players
  commonly describe in Steam guides, on underrail.info and RPG Codex). The build is detected from skills,
  feats and equipped weapons or picked by hand; it shows the build's key attributes, skills and feats
  (owned ✓, unmet requirements ⚠), checks the equipped weapons and worn armor penalty, lists only its
  weapon family and weighs armor penalty by the build's armor profile (light: penalty counts a lot, max
  15 %; medium: max 40 %; heavy: protection first), limited to what the character's Strength can wear.
  The *Weapons* sub-tab lists every weapon (library weapons plus the character's own, crafted ones
  included) with all base stats and the damage per AP with the character's effective skill
  (`damage × (1 + 0.7 × skill / 100)`, 0.5 for pistols and knives, from the game wiki); every column
  sorts, and it filters by family (default: the build's), text, Strength and ownership.
  *Build and armor*: best and the best armor/helmet/boot component
  combinations by protection versus armor penalty (computed with the game's formulas), with the merchants
  that sell them (fixed shipments or random stock), where they lie in the game world (scanned once from
  the map files: containers, ground, NPCs, job rewards, random container loot), for animal parts the
  zones where their creature is placed, and notes on the
  character's crafting feats. *All locations on the map…* (or *+N more*) opens a list of every source
  with the game's world map that marks the zones (merchants blue, spots in the world orange, creatures
  green; click a row to find it on the map, click a zone to find its rows)

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
is extracted into `data/ammo_icons.json`. Crafted weapons have composite visuals (`sledgehammer.2`,
`sniper.4.frame`, `knife.1.2.m1`) that each weapon recipe class registers at startup in loops over grid
cells; `tools/extract_weapon_icons.py` runs those methods in a small IL interpreter and writes the
~9700 definitions (layers of sheet, cell, opacity) to `data/weapon_icons.json`. Cells are 33 px on a
34 px pitch. Items still without an icon get a faded placeholder: the icon of a typical item of the
same category, item class and weapon type, or the game's generic weapon icon.

## Durability and quality

Maximum durability is not stored in the save; the game computes it from the item level `I:L`
(taken from `underrail.exe`): `120 + 60·L + 30·max(0, L−5)`, a flat 200 at level 0; light machine
guns and miniguns (`WI:WT` 9/10) get double. Applies to weapons, armor, helmets, boots and shield
emitters; belts don't wear down. Checked against the world data: 99 of 130 items match exactly, almost
all others are below (worn), two are above (probably templates changed by a game update).

Component quality is `CII:QL`. Only components whose template adds value per quality point
(`CI:AVPQ` > 0) have one – leathers, plates, weapon frames (pistol, SMG, rifle…), emitters and so on.
All others (barrels, energy and chemical pistol frames, goggles/headband frames, scopes, chemicals)
always carry 0; the game hides quality 0 in the tooltip, and a non-zero value would multiply the
crafting skill requirement (`CSR:F` is then a per-quality factor instead of a fixed skill value). The
editor shows and edits quality only for the former (or for a stray non-zero value). The game doesn't
cap it: stats scale with `Q · (0.77 + 0.35 · min(1, max(0, Q−15)/170)^1.35)`, so the bonus curve
flattens at 185 but higher values still count. The editor allows up to 999.

## World map

*World map* (button next to *Refresh*, *View → World map…*, Ctrl+M) opens the map on its own: one page
per area, a zone search, a *Layers* menu (the game's icons for creatures,
plants and merchants/doctors as separate layers; labels from the scanned data: merchant names, most
common creatures/characters, loot count), and for a clicked zone its merchants, characters/creatures and the items lying
there (click an item for all its locations).

The world map is the game's own: `data/maps/world/globalmap.uz` is a zone whose entities are map markers
with sprites. `ZMEA` = a zone (`ZMEA:R` zone ids, `ZMEA:CN` title), `TRSMA` = a transition, `DELMA` =
decoration/icon; each has a sprite aspect `SEA` (`SEA:M` = materialization under
`data/meta/materialization/locale`, `SEA:F` = frame). The `.mu` file names the texture (`MU:T`, e.g.
`data/locale/maps/mapzones.xnb`), frame size `MU:S`, sheet offset `MU:UO` and draw origin `MU:TO`.
`worldmap.py` projects the entity positions isometrically (x = (X−Y)·50, y = (X+Y)·25 − Z·30), draws the
sprites back to front and caches the result as `worldmap_main.png` / `worldmap_sea.png`. Expedition's
Black Sea shares the coordinate space with the caves, so it's a separate page. The file actually holds
separate maps (`Z:A` areas: up, lu, lux, lc, dc, lup, fo, sgs, bs), each with its own coordinates and
entity list (`A6:E`); every area is rendered as its own page. Marked zones are drawn
undimmed with a tint over their own sprite. South Gate Station's levels (`ZMEA:I` = 1, an inset) are
shown at the station's outer marker; dungeons and interiors without a marker are greyed out in the list.
Merchants are located through the merchant aspect `MEA1:S` (store id) of the NPC that trades, which
also gives their real name.

## Save format

`global.dat` = 24-byte header (GUID + version) + gzip-compressed .NET BinaryFormatter stream (MS-NRBF).
`nrbf.py` reads the stream into an object graph and writes it back – byte-identical when unchanged,
changed/new objects get their own class metadata. `xnb.py` decodes the LZX-compressed XNB portraits
(DXT1/3/5).

Per-location state lives next to it: `bulk.map` (NRBF, `BSM:I:n:Key/Value`) indexes entries
`lmaps\<zone>.uzdm`, `<zone>_l1.uzl`, `<zone>.ap` as chunk file / start / length; every entry in `chunk*.dat`
starts with the same 24-byte header as `global.dat`. The game has been seen writing the index without the
matching chunk data; entering such a location then fails with "Failed to load locale". The editor checks this
when opening a save and *File → Repair broken locations…* drops all entries of the affected zones (backup first),
so the game rebuilds them as never visited.

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
| `C1:PA1:i:Key/Value` | the character's own attitude overrides per faction id (`eATTI`); they win over the faction relation |

Game variables (quest flags, counters) are the `P` objects (`P:N` name, `P:V` value) of the property
collection `TG:GP` (`PC:P:i`); an unset variable reads as false/0. Faction relations are `TG:F` → `FSW:FS` →
`FS1:D`, a byte array the game writes with a `BinaryWriter` (layout in `factions.py`): per faction its id, name
and `{target faction: attitude}`. Attitudes: 0 hostile, 2 neutral (the default without a relation), 4 allied
(SGS toward a member); 1 and 3 aren't named in the game data – the editor calls them wary and friendly.

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

Feats that grant an attack or ability (Snipe, Sprint, …) get it added to the character as well, as the
game does on level-up; `data/feat_abilities.json` comes from `tools/extract_feat_abilities.py`.

`data/feat_requirements.json` is generated from `underrail.exe` by `tools/extract_feat_requirements.py`
(needs `pip install dnfile dncil`; re-run after game updates). The tool reads each feat class's
requirement method: attribute and skill minimums (compared against base values like the game does),
required and excluded feats, character level, any psi skill, known psi abilities, and whether the
level-up screen offers the feat at all. It also reads every specialization class: the feat it belongs
to and its maximum points.
