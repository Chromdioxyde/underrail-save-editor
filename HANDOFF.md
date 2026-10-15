# Handoff – status 2026-10-15

Underrail save editor: PySide6 GUI that edits Underrail saves (character, skills, feats, specs, inventory,
blueprints, oddities) and gives hints (item/merchant/creature locations on the game's own world map,
build-aware weapon/armor advice). Latest commit `daedde0`; branch `main`, no remote. README.md describes
features and file formats; this file is the working state.

## Working with the user
- User writes German; reply in German. Project language is English (code, short English comments, docs,
  commit messages); GUI strings are English source keys with German in `i18n.py` – add a translation for
  every new user-visible string. Unsupported system languages fall back to English.
- After every change: `./packaging/install.sh` (installs to `~/.local/share/underrail-save-editor/app`),
  then commit. Commit messages end with the Co-Authored-By / Claude-Session lines given by the harness.
- AppImage on request: `./packaging/build-appimage.sh` -> `build/Underrail_Save_Editor-<commit>-x86_64.AppImage`;
  user wants it copied to `$APPIMAGE_COPY_DIR/` (replace the older one there).
- The user tests in-game and reports back. Never touch the saves listed in `PROTECTED_SAVES` (`.env.local`).
  Test structural edits on a copy (e.g. `cp -r quicksave zz<name>`, delete it afterwards).
- Prefers data extracted from the game over invented/schematic visuals.
- Running-game warning applies only to quicksave/autosave (the game only rewrites those).

## Paths
- Repo `the repository`; game `$UNDERRAIL_GAME_DIR`; saves
  `$UNDERRAIL_SAVES_DIR`.
- Cache `~/.cache/underrail-save-editor/` (items-v6, map_index_v5, worldmap_v7, worldmap_*.png, maptex/,
  zone_links_v1.json, icons/, thumbs/, savedetails.json); invalidated by game file mtimes.
- Backups of written saves: `paths.BACKUP_DIR` (outside the save folder, so Steam Cloud ignores them).
- exe analysis needs a venv with `dnfile` + `dncil` (not in the repo; recreate in the scratchpad:
  `python3 -m venv venv && venv/bin/pip install dnfile dncil`). System python3 has PySide6 for the app.

## Latest changes (2026-10-15) – awaiting in-game confirmation
- New *Factions* tab (`factions.py`, `FactionsTab`): Faceless attitude score at Talos Outpost (game formula
  from IL method `dyk::ym`, job `DCFAC` started by `dc_flo_mindreader.udlg`), editable inputs (game variables
  via `Save.var/set_var`, creates missing `P` entries), kill counters of other factions (pirates, Protectorate
  jet skis, exosoldiers + `tooManyKilled` flag at 12), faction relations editor (`FS1:D` byte blob, byte-identical
  round trip) and personal overrides `C1:PA1`. Verified on a quicksave copy (edits re-read after writing).
  With the Tchortist scouting job started the commander takes the spy
  branch unless TC check passes) – the user should test the mindreading in-game.
- Attitude enum names 1 (wary) and 3 (friendly) are inferred; 0 hostile / 2 neutral default / 4 allied are
  backed by the IL and data.
- User report: after editing the score inputs the checkpoint guards still said "You may not pass" – the
  checkpoint (`dc_flcheckpoint.udlg`) decides once and stores `faction_faceless_allowPassCaves` /
  `faction_faceless_forbiddenPassCaves`. Added the *Checkpoints* section (set verdict
  or reset `dc_checkpointGuard_met` to decide again); verified on an autosave copy, awaiting in-game test.

## Changes 2026-10-12
1. Crash when the game saved while the editor had saves open (mostly the AppImage): Python's cyclic GC
   ran in a worker thread (DetailsJob parsing the new save) and finalized Qt widgets there -> segfault.
   Fix: `gc_on_gui_thread(app)` in underrail_gui.py. Reproduced and verified with a script that rewrites a
   save folder like the game (rename to "(previous)", write files) using the AppImage's Python/PySide6 6.12.
2. Feats added by the editor didn't give their attack/ability (an added Snipe had nothing in the quick
   menu). Now `add_feat`/`remove_feat` update the capability sets, and saving runs
   `Save.sync_feat_abilities()` for all feats (fixes feats added by older versions). The GUI shows the
   missing ones in the status bar after loading and enables Save. Verified on a quicksave copy (Execute
   and Snipe added in the game's order, file re-reads); still to be confirmed in-game.
   Details below under "Feat attacks/abilities".

## Open / next steps
- In-game confirmation of the two fixes above.
- Not done, offered: read the save's per-zone state (`bulk.map`, `chunk*.dat/.map` in the save folder)
  to mark looted containers / killed NPCs on the map; format not yet examined. The map index itself
  comes from game files and is the same for every playthrough (random loot/stock rolled per game;
  conditional `.uzl` layers for difficulty/DLC/quests are all included).
- Offered, not requested: maps of individual zones/dungeons (static `dun_*.uz`; needs the tile grid
  `A6:T`/`A6:T1`, editor-marker filtering, scale calibration).
- Windows build untested; Windows folder detection untested.
- Vehicle frame fields `VFI:C/D/T/S/N` unknown; exe damage formula `c4r::a` not decoded (wiki formula
  used); melee Strength bonus not modelled; no hostility/faction data in the map index.
- The hidden region combo in `LocationsDialog` (legacy `REGIONS`/`SEA_PREFIXES` in worldmap.py) can be removed.
- Rarity tier 5 (quest item) gold colour is our choice, not the game's.
- Possible additions: factions (`C1:PA1`, eATTI), psi abilities (`C1:PA`), difficulty (`TG:D`).

## Modules
`nrbf.py` (.NET binary serialization reader/writer), `xnb.py` (textures), `paths.py` (folder detection,
game_running), `gamedata.py` (game data, item DB, icons, extracted JSON loaders), `underrail_save.py`
(Save model and edits), `underrail_gui.py` (GUI), `i18n.py`, `hints.py` (map index, locations),
`worldmap.py` (global map rendering), `builds.py`, `itemstats.py`, `tools/extract_*.py` (exe ->
`data/*.json`: feat requirements + ammo icons, crafted weapon icons, feat abilities), `packaging/*`.

## Foundations (verified earlier)
- `nrbf.py`: byte-identical round trip for all save files and all 1463 `.item` files; writer drops
  unreachable objects and re-emits changed objects with new class metadata.
- In-game verified: spec point editing; added items (after the object-id fix below).

## Hints / world map
- Map index (`hints.map_index()`, cache `map_index_v5.json`) is keyed by zone id (map file name without
  the `_l<n>` layer suffix); display names come from `southunderrail.world`. Also indexes merchants
  (`MEA1:S` store id -> zones + NPC name).
- `worldmap.py` renders the in-game world map from `globalmap.uz` sprites (see README). 76 zone ids (dungeons, DLC interiors) have no
  marker. `LocationsDialog` in the GUI lists all sources and marks them on `WorldMapView`.
- Unplaced merchants (no map NPC, probably events): gc_fsh, gc_gypsy, dun_diedrick, ezra,
  jackquicksilver, oldjonas, cc_jkkquartermaster.

## World map areas (latest)
Map pages = the global map's areas (`Z:A`, entity lists `A6:E`). Done: area pages in both dialogs.
Merchants/creatures can be written on the zones (WorldMapDialog toggles; objects like rocks/barrels
filtered via hints.is_object). Hostility isn't known (no faction data in the index). The old
prefix-based `REGIONS`/area combobox in LocationsDialog is hidden and can be removed; check SGS inset.

## Zones without a marker
`worldmap.linked()` maps them to a marked zone their own .uz file references (cache zone_links_v1.json,
built in MapScanJob, ~1 min) or to Core City for cc dungeons. Still unplaced: lup-grampus (Grampus),
xpbl_ww_dragndrop (Mixer Jessie) – nothing references them.

## Builds
`builds.py`: archetypes with weapon families (from `WI:WT` + visual model `WI:WVM`: k knife, s sledgehammer,
c crowbar, '' fist, xpbls spear, xpblm sword, ep/ap energy pistol), attributes, skills, feat ids and armor
profile; `detect(save)` scores skills + owned key feats + equipped weapon family. Worn armor penalty = sum
of `AI1:E`. `itemstats.py` reads weapon/armor stats from save items and item files alike (used by the Weapons sub-tab and
the inventory comparison). Skill damage factor from the wiki (0.7 / 0.5 light); the exe's `euf::s` returns
`WI:SB` or 1.0/0.8/0.6 by category – not identified yet (maybe stealth/noise), Strength bonus for melee
not modelled.

## Packaging
- `packaging/install.sh` (per-user Linux install), `build-appimage.sh` (portable AppImage, tested on
  Ubuntu 22.04/Debian 12 in Docker; Debian 11 is too old for PySide6's libstdc++), PyInstaller spec +
  GitHub Actions workflow for Windows (Windows build not tested yet – no Windows machine, repo not on GitHub).
- `paths.py` detects folders on Linux/Steam Deck/Windows; Windows detection is untested.

## Findings
- `SNF:M` is not the maximum (in-game test with V=M=8 allowed distributing points) → keep V and M in sync.
- Item instance class depends on the template class (`INSTANCE_CLASS` in underrail_save.py).
  Unequipped weapons have an empty `WII:A` list.
- Feat abbreviations without a confirmed name: qr, st. `im` = Execute, `ds` = Marksman (inferred).
- Object ids: .NET uses ONE counter for objects (negative = value types) and libraries, so every
  absolute value is unique; Mono fails with "An object cannot be registered twice" otherwise. New ids
  come from a single counter over abs values; `File.repair_ids()` fixes saves from older versions.
  Value types must be written inline, never referenced. Both found via in-game tests.
- Blueprint list (`PC1:B`) is a SortedList read via binary search; insertion order matters.

## Feat requirements
`tools/extract_feat_requirements.py` -> `data/feat_requirements.json` (239 feats). Feat id = custom
attribute on the feat class; requirement classes recognised by their diagnostic strings; checks use
base values (Stat.S4:V) unless a requirement's "modified" flag is set; "selectable" = the feat base
method the tooltip uses for "acquired outside leveling". `Save.feat_check()` evaluates them.

## Feat attacks/abilities
Feats like Snipe or Sprint also grant a capability: the feat's on-added method calls
`character.<set>.Add(Registry.Get<AbilityClass>())`. Saves store them as `CR` objects (`CR:CFTN` = the
ability class's id attribute lowercased, e.g. `snipeattack`) in two SortedLists: `C1:SA` "Attacks" and
`C1:SA1` "Abilities" (`C1:PA` psi, `C1:QC` gear). Ordered by the ability's order value (`bh`), then its
display name. `tools/extract_feat_abilities.py` -> `data/feat_abilities.json`. `add_feat`/`remove_feat`
keep them in sync; saving adds the ones missing for feats added by editor versions before 2026-10-12.

## Background jobs and GC
Python's cyclic GC ran inside worker threads (save parsing) and finalized Qt widgets there -> segfault
when the game rewrote an open save (seen with the AppImage's PySide6 6.12). `gc_on_gui_thread()` disables
automatic GC and collects from a GUI-thread timer.

## exe analysis
Python only: venv with `dnfile` + `dncil` (in the scratchpad, not in the repo). Item instance = class
`coh` (field `k` = `II:D`); durability factor `coh::afc` = 0.15 + 0.85·min(1, D/max); max = `bk3::yj`
(item level `bk3::e` = `I:L`, constants in `dwh::.cctor`: c=200, d=120, e=60, f=5, g=30); weapons
`bke::yj` double for `WI:WT` 9/10. Approach: find the method with `ldstr "II:D"`, follow the field.
