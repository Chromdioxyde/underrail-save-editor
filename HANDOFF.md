# Handoff – status 2026-10-10

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
- Blueprint list (`PC1:B`) is a SortedList read via binary search; insertion order matters.

## exe analysis
Python only: venv with `dnfile` + `dncil` (in the scratchpad, not in the repo). Item instance = class
`coh` (field `k` = `II:D`); durability factor `coh::afc` = 0.15 + 0.85·min(1, D/max); max = `bk3::yj`
(item level `bk3::e` = `I:L`, constants in `dwh::.cctor`: c=200, d=120, e=60, f=5, g=30); weapons
`bke::yj` double for `WI:WT` 9/10. Approach: find the method with `ldstr "II:D"`, follow the field.
