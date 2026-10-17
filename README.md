# Underrail Save Editor

> **Unofficial fan project.** This editor is not made, endorsed or supported by Stygian Software, the
> developer of Underrail, and is not affiliated with them in any way. Underrail and its assets belong to
> Stygian Software. Back up your saves; use at your own risk.

Save game editor for Underrail with a graphical interface: change your character, feats, specializations,
inventory, blueprints and faction standings, and look up builds, gear and where to find items. Names, icons
and values come straight from your Underrail installation. Runs on Linux (incl. Steam Deck) and Windows.

How it works inside (save format, game data, building): [docs/TECHNICAL.md](docs/TECHNICAL.md).

## Download and run

- **Linux / Steam Deck:** the AppImage bundles everything it needs. Make it executable and run it
  (on the Steam Deck: Desktop Mode, right-click → Properties → Permissions → executable, then double-click).
  Needs SteamOS 3, Ubuntu 22.04, Debian 12, Fedora 35 or newer.
- **Windows:** unzip `UnderrailSaveEditor-…-windows-x64.zip` and start `UnderrailSaveEditor.exe`.

The game and save folders are found automatically (Steam incl. SD cards and Flatpak Steam, GOG on Windows).
If nothing is found, choose them under *Settings → Game folders…*.

## Install from source (Linux)

Needs Python 3, PySide6 and Pillow (on Arch-based systems: `sudo pacman -S pyside6 python-pillow`).

```
./packaging/install.sh      # per-user, no root; re-run to update
./packaging/uninstall.sh    # removes the app, keeps backups
```

This adds the `underrail-save-editor` command to `~/.local/bin` and an entry to the application menu.
Without installing: `./underrail_gui.py`.

## Usage

The game can keep running while you edit. Load the save in the game afterwards to see the changes; the game's
next quicksave or autosave replaces an edited quicksave/autosave. Every save made by the editor first backs up
the original to `~/.local/share/underrail-save-editor/backups/<save>/<timestamp>/`; to roll back, copy both
files from there back into the save folder. Try bigger changes (feats, items, name, portrait) on a copy of a
save first.

The editor is available in English and German (*Language* menu; follows the system language by default).
Game terms (items, feats, skills) always appear as the game names them.

## Features

- **Save list:** every save with its screenshot, character, location, play time, health, XP and money;
  updates when the game saves. Open/close it with the handle at its edge, *View → Save list* or Ctrl+L.
- **Character:** name, level, portrait (all game portraits, or import your own picture – restart the game
  to see it), attributes, XP, unspent points, health.
- **Skills:** all skill values.
- **Feats:** every feat with its icon and description; add or remove with a checkbox. Shows what each feat
  requires and marks the ones your character doesn't qualify for. Feats that grant an ability (Snipe,
  Sprint, …) bring it along.
- **Specializations:** like the game's character screen – every specialization of your feats with its points
  and maximum.
- **Inventory:** items with icons, rarity colours, weight and stats; sort, filter, change stack size, quality,
  durability and battery, repair, duplicate or remove items, and edit equipped gear. Selecting an item shows
  a card that compares it with what you have equipped. *Add item…* adds any of the game's ~1460 items.
- **Blueprints:** learn or forget crafting blueprints, or learn all.
- **Oddities:** collection counters.
- **Factions:**
  - *The Faceless*: whether the checkpoint guards let you pass, and a live preview of the score the
    Faceless commander computes when he reads your mind, with everything that feeds into it; *Skip the
    mindreading* for when that scene hangs.
  - *Kill counters* the game reacts to (Expedition pirates and jet ski patrols, Heavy Duty exosoldiers).
  - *Attitudes* of every faction toward you and back.
- **Hints:** pick a build (or let the editor detect it) and see its key attributes, skills and feats, the
  best weapons for your skill, the best armor combinations for your Strength, and where to buy or find
  everything.
- **World map:** the game's own world map with merchants, creatures and loot per zone (button next to the
  save title, or Ctrl+M); *where to find* lists for any item are shown on it too.
- **Repair broken locations:** fixes saves where entering a location fails with "Failed to load locale"
  (*File → Repair broken locations…*).

## Screenshots

Taken with the first save of a playthrough (South Gate Station, level 1).

**Save list and character**
![Save list and character](docs/screenshots/save-list-character.png)

**Skills**
![Skills](docs/screenshots/skills.png)

**Feats** – game icons, filled-in descriptions, requirements
![Feats](docs/screenshots/feats.png)

**Specializations**
![Specializations](docs/screenshots/specializations.png)

**Inventory** – item card with the comparison to the equipped weapons
![Inventory](docs/screenshots/inventory.png)

**Add item**
![Add item](docs/screenshots/add-item.png)

**Blueprints**
![Blueprints](docs/screenshots/blueprints.png)

**Oddities**
![Oddities](docs/screenshots/oddities.png)

**Factions** – the Faceless (checkpoints, mindreading score), kill counters, attitudes
![Factions: the Faceless](docs/screenshots/factions-faceless.png)
![Factions: kill counters](docs/screenshots/factions-kill-counters.png)
![Factions: attitudes](docs/screenshots/factions-attitudes.png)

**Hints** – weapons for the build, build and armor combinations
![Hints: weapons](docs/screenshots/hints-weapons.png)
![Hints: build and armor](docs/screenshots/hints-build-and-armor.png)

**World map**
![World map](docs/screenshots/world-map.png)

**Where to find an item**
![Item locations](docs/screenshots/item-locations.png)

**Help → About**
![About](docs/screenshots/about.png)

## License

Copyright (C) Chromdioxyde. This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software Foundation, either version 3
of the License, or (at your option) any later version (GPL-3.0-or-later). It is distributed WITHOUT ANY
WARRANTY; see [LICENSE](LICENSE) for the full text.

The AppImage and the Windows build bundle Python (PSF license), PySide6/Qt (LGPL-3.0) and Pillow (MIT-CMU
license) under their own licenses. Underrail and its data (names and values read from the game's files)
belong to Stygian Software; this is an unofficial fan project, not affiliated with them.
