# Technical details

How the editor reads and writes Underrail's files, where its game data comes from, and how to build it.
For using the editor see the [README](../README.md).

## Save format

`global.dat` = 24-byte header (GUID + version) + gzip-compressed .NET BinaryFormatter stream (MS-NRBF).
`nrbf.py` reads the stream into an object graph and writes it back – byte-identical when unchanged,
changed/new objects get their own class metadata. `info.dat` (the save list summary) has the same format.
`xnb.py` decodes the LZX-compressed XNB textures (portraits, icon sheets; DXT1/3/5).

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
| `C1:SA`, `C1:SA1` | attacks and abilities granted by feats (`CR:CFTN`), SortedLists ordered by the ability's order value, then its name |
| `C1:SPC:i:Key/Value` | specializations (`SNF:V`, `SNF:M`, always set together); only specializations with points are stored |
| `C1:B` → `IC:I:i` | inventory; item: `II:S` stack, `II:D` durability, `II:B` battery (capacity `I:MB` of the item data), `CII:QL` component quality, `II:DP` template (`LIDP:P` path under `data/rules/items`) or embedded data (`IIDP:D`, crafted) |
| `C1:G` | equipment slots (`IS:I` = item) |
| `C1:D2` → `CD1:H` | health (`BV:V`/`BV:MX`) |
| `PC1:E` | XP |
| `PC1:BAPC`, `PC1:SPC`, `PC1:FC`, `PC1:SP` | unspent attribute/skill/feat/specialization points |
| `PC1:O:i:Key/Value` | oddities |
| `PC1:B` | known blueprints: .NET `SortedList` name → `IBR` (`IBR:IBFTN` = lower-case id from `data/knowledge/itemblueprints.k`). Not re-sorted on load and read by binary search → entries are inserted in .NET culture order (`gamedata.sort_key`, verified against saved lists) |
| `C1:PA1:i:Key/Value` | the character's own attitude overrides per faction id (`eATTI`); they win over the faction relation |

Attributes and skills are edited as base values; the saved effective value is shifted by the same delta.
`info.dat` `SGI:V` is the game version that wrote the save (shown under *Help → About*).

Game variables (quest flags, counters) are the `P` objects (`P:N` name, `P:V` value) of the property
collection `TG:GP` (`PC:P:i`); an unset variable reads as false/0. Faction relations are `TG:F` → `FSW:FS` →
`FS1:D`, a byte array the game writes with a `BinaryWriter` (layout in `factions.py`): per faction its id, name
and `{target faction: attitude}`. Attitudes: 0 hostile, 2 neutral (the default without a relation), 4 allied
(SGS toward a member); 1 and 3 aren't named in the game data – the editor calls them wary and friendly.

## The Faceless (factions tab)

- **Checkpoints** (`dc_flcheckpoint.udlg`): the guards decide at the first meeting and store
  `faction_faceless_allowPassCaves` or `faction_faceless_forbiddenPassCaves`; later meetings only read it.
  They let you pass if the Foundry recon quest is finished and those Faceless aren't hostile to you, or if the
  Rail Crossing mindreader left safely. The guard starts the dialog on his own (map AI property
  `AutoDialogInit` = `dc_checkpointGuard_met`, within 6 units) until that flag is set, so a stored verdict needs
  the flag too. Without the pass the Talos Outpost entrance guard attacks.
- **Mindreading score** at Talos Outpost: the job started by the mindreading dialog
  (`dc_flo_mindreader.udlg`) computes `loc_dc_flo_attitudeCalculation`: +1 Foundry recon finished and not
  hostile to those Faceless, +1 Rail Crossing mindreader left safely, +1 injured Faceless in Core City released
  unharmed, −1 mindreader died; set to −5 if the injured Faceless was attacked or killed or you are hostile to
  the Foundry Faceless; set to −5 for more than 10 Faceless killed (both counters), otherwise one point per 6/4/3/2
  kills after the first (Easy/Normal/Hard/Dominating). A passed Thought Control check cancels every penalty. The
  commander's dialog: 3+ allies, 1–2 friendly, 0 neutral, below 0 hostile; the Tchortists' scouting job makes
  him call you a spy unless the check passed.
- *Skip the mindreading* sets the score plus `loc_dc_flo_mindreading`, `loc_dc_flo_endMindreading`,
  `npc_dc_flCommander_met`, `faction_faceless_allowPassBase`, `dc_flo_entrance_met`.
- **Kill counters:** pirates (`faction_xpbl_pirates_totalPiratesKilled`; dialogs at 30, 50, 60, attack events
  skipped from 50), Protectorate jet skis (`faction_protectorate_coreCity_jetSkiersKilled`; dialogs from 10),
  exosoldiers (`faction_xphw_exoBase_exosoldiers_killed`; at 12 the game sets `…_tooManyKilled`, the editor
  keeps it in sync).

## Item icons

Icons are cut out of the game's sprite sheets (`data/icons/*.xnb`) on first start (a few seconds,
cached in `~/.cache/underrail-save-editor/icons/`). An item's visual id (`I:VM`) is either a name from
`icons.iconset` (grid cell(s) per sheet; multi-part icons are layers with their own opacity) or
`<Sheet>.<n>` = cell n of a 10-column grid. Bullets are registered by the game at runtime from the
`AmmoType` enum (value v → column `v % 100 − 1`, row `v // 100 − 1` on the Ammo sheet); that mapping
is extracted into `data/ammo_icons.json`. Crafted weapons and armor have composite visuals (`sledgehammer.2`,
`sniper.4.frame`, `knife.1.2.m1`, `shieldEmitter.p2.s1.e1`, riot gear, tabi boots) that each recipe class
registers at startup in loops over grid cells; `tools/extract_crafted_icons.py` runs those methods in a small
IL interpreter and writes the ~9900 definitions (layers of sheet, cell, opacity) to `data/crafted_icons.json`.
Cells are 33 px on a 34 px pitch. Items still without an icon get a faded placeholder: the icon of a typical
item of the same category, item class and weapon type, or the game's generic weapon icon.

Feat icons are the iconset entries `Feat.<class name>`, matched by the feat's display name (238 of 239 feats).

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

Vehicle parts show their build size (`VPI:S`, small/medium/large) and engine power (`VEI:P`). Stack sizes are
limited to the item's maximum stack `I:MS`.

## Weapon and armor numbers (hints, item card)

Damage per AP with the character's skill follows the game wiki: `damage × (1 + 0.7 × skill / 100)`, 0.5 for
pistols and knives, with the effective skill stored in the save; burst weapons count all shots. Armor
protection and penalty use the game's formulas; worn armor penalty is the sum of `AI1:E`. Builds weigh the
penalty by an armor profile (light: counts a lot, max 15 %; medium: max 40 %; heavy: protection first) and
only offer what the character's Strength can wear. Where items lie in the world comes from a one-time scan
of the map files (containers, ground, NPCs, job rewards, random container loot).

## World map

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

## Custom portraits

At startup the game scans `Documents/My Games/Underrail/CustomPortraits` for `*_l.png` and loads
`<id>_h.png`, `<id>_l.png`, `<id>_s.png` (200/100/50 px), using the lower-cased file name as portrait
id (verified in `underrail.exe`). *Import PNG…* in the portrait dialog crops an image to a square and
writes the three sizes there.

## Data extracted from underrail.exe

The files in `data/` are generated from the game's executable by the tools in `tools/` (need
`pip install dnfile dncil`; re-run after game updates). Class and member names are obfuscated, so the tools
find classes by their strings and signatures, and run small parts of the game's IL in an interpreter.

- `data/feat_requirements.json` (`tools/extract_feat_requirements.py`): each feat class's requirement
  method – attribute and skill minimums (compared against base values like the game does), required and
  excluded feats, character level, any psi skill, known psi abilities, and whether the level-up screen offers
  the feat at all; plus every specialization class: the feat it belongs to and its maximum points.
- `data/feat_abilities.json` (`tools/extract_feat_abilities.py`): the attacks/abilities a feat grants; adding a
  feat adds them to the character as the game does on level-up.
- `data/feat_descriptions.json` (`tools/extract_feat_descriptions.py`): the values the game inserts into the
  `{0}`… placeholders of feat and specialization descriptions (all 221 feats and 208 specializations with
  placeholders resolve; none depends on the character). The *Specializations* tab adds the total for the
  character's points to "… for each specialization point" descriptions.
- `data/crafted_icons.json`, `data/ammo_icons.json`: see *Item icons*.

## Building

```
./packaging/build-appimage.sh          # -> build/Underrail_Save_Editor-<version>-x86_64.AppImage
```

The AppImage uses a portable CPython (python-build-standalone) and manylinux wheels, so it doesn't depend
on the build machine's libraries. If `.env.local` (see `.env.example`) sets `APPIMAGE_COPY_DIR`, the script
copies the result there. The Windows build uses PyInstaller and has to run on Windows:

```
python -m pip install pyinstaller PySide6-Essentials pillow
python packaging/make_icon.py build
pyinstaller --noconfirm --distpath build/dist --workpath build/work packaging/underrail-save-editor.spec
```

## Releases (GitHub Actions)

`.github/workflows/build.yml` builds the AppImage (Ubuntu runner) and the Windows zip (Windows runner,
PyInstaller) on every push to `main`, every pull request and on demand (*Actions → build → Run workflow*);
the files are attached to the run as artifacts for 14 days. To publish a release:

1. Set `VERSION` in `version.py` (e.g. `1.1.0`) and commit.
2. Tag and push: `git tag v1.1.0 && git push origin v1.1.0`.

The tag build then creates a GitHub release named after the tag with both files and generated release
notes; it fails if the tag doesn't match `VERSION`. The file names carry `git describe --tags`, i.e. the
tag for release builds and `<tag>-<n>-g<commit>` (or just the commit) otherwise.
