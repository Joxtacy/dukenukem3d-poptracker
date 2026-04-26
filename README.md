# Duke Nukem 3D - Archipelago PopTracker Pack

A PopTracker pack for the [Duke Nukem 3D Archipelago randomizer](https://github.com/randomcodegen/NBloodAP) (Atomic Edition, episodes 1-4).

## Features

- Item tracking for weapons, inventory, abilities, key cards, and per-level automaps
- Location tracking for sprite pickups, secret sectors, and level exits across all 40 maps
- Goal-progress panel showing Exit / Secret / Boss completion vs. the configured target
- UI gating driven by slot data: hides episodes / sections that are not part of the seed
- Archipelago auto-tracking via AP connection (no game memory reads required)

## Installation

1. Download the latest release zip (or zip this folder yourself with `just zip`).
2. Place it in your PopTracker `packs` directory:
   - Windows: `Documents/PopTracker/packs/`
   - Linux: `~/PopTracker/packs/`
   - macOS: `~/PopTracker/packs/`
3. Open PopTracker, pick "Duke Nukem 3D AP Tracker".

## Auto-Tracking

Click "AP" in PopTracker's menu bar, enter the Archipelago server address and your slot name. Items received and locations checked will sync automatically.

## Images

This early version ships with simple placeholder icons. Drop replacement PNGs into `images/` if you want a nicer look.

## Maintenance

The `tools/` directory contains scripts for regenerating items / locations / layout / placeholder images from the apworld source. See [`tools/README.md`](tools/README.md) for what each script does and when to run it. The most important one is `gen_pack_data.py` — re-run it whenever the upstream apworld is updated.

Releases are cut via the **Release** workflow in the GitHub Actions tab.

What's planned for upcoming versions lives in [`ROADMAP.md`](ROADMAP.md).

## Credits

- **apworld + engine**: [randomcodegen/NBloodAP](https://github.com/randomcodegen/NBloodAP) (fork of [LLCoolDave/Duke3DAP](https://github.com/LLCoolDave/Duke3DAP))
- **PopTracker**: [black-sliver/PopTracker](https://github.com/black-sliver/PopTracker)
- **Duke Nukem 3D**: 3D Realms / Apogee
