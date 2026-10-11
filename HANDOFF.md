# Handoff – status 2026-10-11 (evening)

Goal: GUI editor with as many features as possible (inventory, portrait, everything editable).
Project language is English (docs, code, commit messages); the GUI additionally has a German translation.

## Done (tested on copies of `Saves/test` / `Saves/quicksave`, not in-game unless noted)
- `nrbf.py`: full reader/writer, byte-identical round trip for all 64 save files (global.dat/info.dat)
  and all 1463 `.item` files. The writer drops unreachable objects, writes changed objects with new
  class metadata and re-emits objects whose inline parent is gone.
- `xnb.py`: LZX decoder + DXT1/3/5 for portrait previews (cached in `~/.cache/underrail-save-editor/portraits/`).
- `gamedata.py`: item DB (`data/rules/items`, incl. level, weapon type, battery capacity), feat/spec/
  blueprint names and descriptions (`data/knowledge/*.k` + strings from `underrail.exe`), portrait list,
  PNG import as custom portrait, durability formula, .NET culture sort key.
- `underrail_save.py`: name/level (+info.dat), portrait, XP/points, current health, attributes, skills,
  oddities, specializations, feats, blueprints, inventory (list, equipped, stack/durability/battery/
  quality, remove, duplicate with new GUID, add from item DB with full durability).
- `underrail_gui.py`: tabs for all of the above, sortable/filterable inventory, repair, portrait gallery.
- `i18n.py`: English/German UI, system language by default, *Language* menu override.
- In-game verified: spec point editing (V=M=8 allowed redistributing points); a bug with added items
  ("An object cannot be registered twice": GUID struct written as reference) was found in-game and fixed.

## Open / next steps
1. User tests in-game (on `test` save): name/portrait, adding feat/spec/blueprint, adding items
   (e.g. robe), duplicate/remove items, durability/quality edits. Treat structural edits as unverified
   until then.
2. Item icons extracted from sprite sheets (see README); ~72 library items (plus crafted items with
   composite visuals) use faded category placeholders.
3. Possible additions: factions (`C1:PA1`, eATTI), psi abilities (`C1:PA`), difficulty (`TG:D`).
4. Offered, not requested: warn about specs without their feat, spec maxima as upper bound. Real feat
   requirements only exist in the (obfuscated) code.

## Hints / world map
- Map index (`hints.map_index()`, cache `map_index_v5.json`) is keyed by zone id (map file name without
  the `_l<n>` layer suffix); display names come from `southunderrail.world`. Also indexes merchants
  (`MEA1:S` store id -> zones + NPC name).
- `worldmap.py` renders the in-game world map from `globalmap.uz` sprites (see README). 76 zone ids (dungeons, DLC interiors) have no
  marker. `LocationsDialog` in the GUI lists all sources and marks them on `WorldMapView`.
- Unplaced merchants (no map NPC, probably events): gc_fsh, gc_gypsy, dun_diedrick, ezra,
  jackquicksilver, oldjonas, cc_jkkquartermaster.

## Open from the latest requests
- Vehicle frames have more fields (VFI:C/D/T/S/N) whose meaning isn't known; only size/power are shown.
- Skill damage factor (0.7/0.5) from the wiki; `c4r::a` in the exe computes (ac[x] + skill * ad[x]) * y –
  probably the real formula, not decoded yet.

## World map areas (latest)
Map pages = the global map's areas (`Z:A`, entity lists `A6:E`). Done: area pages in both dialogs.
Merchants/creatures can be written on the zones (WorldMapDialog toggles; objects like rocks/barrels
filtered via hints.is_object). Hostility isn't known (no faction data in the index). The old
prefix-based `REGIONS`/area combobox in LocationsDialog is hidden and can be removed; check SGS inset.

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

## exe analysis
Python only: venv with `dnfile` + `dncil` (in the scratchpad, not in the repo). Item instance = class
`coh` (field `k` = `II:D`); durability factor `coh::afc` = 0.15 + 0.85·min(1, D/max); max = `bk3::yj`
(item level `bk3::e` = `I:L`, constants in `dwh::.cctor`: c=200, d=120, e=60, f=5, g=30); weapons
`bke::yj` double for `WI:WT` 9/10. Approach: find the method with `ldstr "II:D"`, follow the field.
