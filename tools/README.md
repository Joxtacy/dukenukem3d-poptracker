# Maintainer scripts

These scripts generate the bulk of the pack's data and assets. None of them ship in the released zip — `tools/` is excluded by `justfile` and the release workflow.

| Script | Run when |
|---|---|
| [`gen_pack_data.py`](#gen_pack_datapy) | The Duke3D apworld changes (new NBloodAP release). |
| [`gen_layout.py`](#gen_layoutpy) | The level list, episode count, or per-tab layout structure changes. Rare. |
| [`gen_maps.py`](#gen_mapspy) | First-time setup of real per-level top-down maps + pin coordinates, or after the apworld bumps the levels' `location_defs`. |
| [`gen_placeholders.py`](#gen_placeholderspy) | You want to wipe `images/` back to text-labeled placeholders, or a new icon was added. |
| [`gen_recolors.py`](#gen_recolorspy) | You changed `images/atomic_health.png` or `images/armor.png` and want to refresh the four randomizer-only variants. |

---

## `gen_pack_data.py`

The codegen that builds the bulk of the tracker's data files from the apworld source. Without it, you'd be hand-typing ~1900 entries.

**Reads**

- `levels/e?l*.py` (AST-parsed for each level's `name`, `levelnum`, `volumenum`, `keys`, `has_boss`, `must_dive`, `location_defs`)
- `resources/id_map.json` (the apworld's full table of item + location → short id; used to derive net IDs)
- The weapon / inventory / ability / healing item lists are hardcoded inside the script (mirroring `items/__init__.py` from the apworld) since those don't change often.

**Writes**

| File | Contents |
|---|---|
| `items/items.json` | All ~239 item entries — weapons + ammo + capacity + progressive variants, inventory, armor, abilities, healing, per-level Unlock + Automap + Keys, hidden setting toggles, goal counters. |
| `locations/e{1..4}_locations.json` | All ~1608 location sections, grouped by episode → level → section, with `access_rules` chains and `map_locations` pin coordinates. |
| `maps/e{1..4}_maps.json` | 40 per-level map stub definitions pointing at `images/eXlY_map.png`. |
| `scripts/autotracking_data.lua` | `ITEM_MAP` / `LOCATION_MAP` / `LEVEL_PATH` / `LEVEL_TO_EPISODE` / `UNLOCK_ID_TO_PREFIX` Lua tables (~2000 lines, all generated). |

**When to run**

Only when the apworld changes. Specifically:

- New release of [`randomcodegen/NBloodAP`](https://github.com/randomcodegen/NBloodAP) ships an updated `duke3d.apworld`.
- The apworld adds/removes locations, adds new items, or renumbers IDs.
- The apworld restructures something the tracker mirrors (level naming, episode count, key colours, etc.).

For everything else — fixing icons, tweaking the layout, editing `autotracking.lua`, adding new YAML option toggles — you don't touch this script.

**How to run**

```sh
# 1. Download the new apworld
curl -L -o /tmp/duke3d.apworld \
  https://github.com/randomcodegen/NBloodAP/releases/latest/download/duke3d.apworld

# 2. Extract it (the .apworld is a zip)
rm -rf /tmp/duke3d-apworld/extracted
unzip -q /tmp/duke3d.apworld -d /tmp/duke3d-apworld/extracted

# 3. Regenerate
python3 tools/gen_pack_data.py

# 4. Review the diff and commit
jj diff
jj describe -m "regen: bump duke3d apworld to vX.Y.Z"
```

After committing, cut a new tracker release via the GitHub Action.

**Flags**

```
--apworld-dir PATH   Path to the extracted apworld (default: /tmp/duke3d-apworld/extracted/duke3d)
--out PATH           Output repo root (default: this repo)
```

---

## `gen_layout.py`

Generates `layouts/tracker.json` — the top-level UI: the goal-counter status row, the per-episode tabs with item grids (Unlock + Automap + Blue/Red/Yellow Key columns), and the per-level map dock.

**Reads**

The level list is hardcoded inside the script (`LEVELS = [...]`) along with each level's display name and key colours. It's deliberately decoupled from `gen_pack_data.py` so layout tweaks don't require running the full codegen.

**Writes**

`layouts/tracker.json`

**When to run**

- The apworld adds or removes levels, or changes episode structure.
- You want to restructure the layout (different docks, new tabs, etc.).
- You change which items appear in the Status / Weapons / Inventory / Abilities groups.

**How to run**

```sh
python3 tools/gen_layout.py
```

For finer changes, edit the script's `status_tab()` / `episode_tab()` functions rather than the generated JSON, since the JSON is overwritten on every run.

---

## `gen_maps.py`

Renders top-down map PNGs for all 40 levels by parsing `duke3d.grp` directly, and extracts pixel-accurate pin coordinates for every sprite/sector location. Replaces the manual Mapster32 + image-editor workflow.

**Reads**

- `duke3d.grp` — the Atomic Edition GRP archive (Ken Silverman format). Contains all 40 `.MAP` files.
- The extracted apworld at `/tmp/duke3d-apworld/extracted/duke3d/` (uses the same level metadata that `gen_pack_data.py` reads, so we know which sprite/sector index corresponds to each tracker location).

**Writes**

- `images/eXlY_map.png` × 40 — vector top-down renders (1024×768; walls drawn as line segments; aspect-preserving fit with a small padding margin).
- `tools/map_pins.json` — `{ "E1L1": { "Bachelor RPG": [px, py], "Secret Bachelor Apartment": [px, py], … }, … }`. `gen_pack_data.py` reads this on its next run and bakes the coordinates into `map_locations[].x/.y` for every section. If the file is missing, all pins fall back to `(100, 100)` and stack on top of each other.

**When to run**

- One-time setup, after you've located your `duke3d.grp` (Atomic Edition, SHA1 `4fdef855…`).
- After an apworld bump that adds, removes, or renumbers `location_defs` for any level — sprite indices may shift.

**How to run**

```sh
tools/gen_maps.py --grp ~/Documents/Duke3D/duke3d.grp
# then regenerate locations to bake pins into map_locations
python3 tools/gen_pack_data.py
```

**Flags**

```
--grp PATH           Path to duke3d.grp (default: ~/Documents/Duke3D/duke3d.grp)
--apworld-dir PATH   Apworld extraction (default: /tmp/duke3d-apworld/extracted/duke3d)
--out-images PATH    Where to write per-level PNGs (default: images/)
--out-pins PATH      Where to write the pin lookup (default: tools/map_pins.json)
--skip-render        Only extract coords; don't write PNGs.
```

**Caveats**

- Exit-type locations don't correspond to a sprite or sector — their `id` is the lotag of the in-map exit trigger, which we can't trivially resolve. Pins for `Exit` and `Secret Exit` sections fall back to the bbox center as a soft hint; click via the location panel rather than the map.
- Sector centroids are computed as the unweighted average of the sector's wall vertices. For non-convex sectors the pin can land outside the sector polygon; close enough for a tracker pin.
- Map version 7 only (Duke3D Atomic). Build engine has older versions floating around but Duke3D-AP only supports Atomic.

---

## `gen_placeholders.py`

Generates a complete set of visually distinct text-labeled PNG placeholders for every item icon and per-level map referenced by the tracker. Used when bootstrapping the pack before real Duke 3D sprites are sourced.

Uses [Pillow](https://pillow.readthedocs.io/) via `uv run` (no global install needed) — the script declares its inline dependencies.

**Writes**

- 52 item icons at 64×64: goal counters, weapons, weapon ammo, inventory, armor, abilities, healing, automap, unlock, key cards.
- 40 per-level map placeholders at 512×384, each labeled with the level prefix + name (e.g. "E1L1 / Hollywood Holocaust").

**When to run**

- Bootstrapping a fresh pack and you don't have icons yet.
- A new icon code was added by `gen_pack_data.py` and you want a placeholder for it.
- You want to wipe `images/` back to a known clean state.

**How to run**

```sh
tools/gen_placeholders.py
# or: uv run tools/gen_placeholders.py
```

**Warning**: this overwrites every PNG it generates. If you've replaced icons with real sprites, those will be clobbered. List the icons you want to skip in the script's `ICONS` array, or comment out the `render_icon()` loop and keep the script just for the per-level maps.

---

## `gen_recolors.py`

Generates the four randomizer-only "tier" variants by hue-rotating two base sprites in HSV space. Alpha is preserved.

**Reads**

- `images/atomic_health.png` → produces `plutonium_health.png` (green→blue) + `uranium_health.png` (green→yellow)
- `images/armor.png` → produces `sturdy_armor.png` (gray→blue with saturation boost) + `heavy_armor.png` (gray→gold)

**Writes**

`images/plutonium_health.png`, `images/uranium_health.png`, `images/sturdy_armor.png`, `images/heavy_armor.png`

**When to run**

- You replaced `atomic_health.png` or `armor.png` with a new source sprite and want the variants refreshed.
- You want to dial in different hue / saturation values (edit the `hue_shift()` calls inside the script).

**How to run**

```sh
tools/gen_recolors.py
# or: uv run tools/gen_recolors.py
```

Tweak the hue values inside `main()` if the resulting colours don't read the way you want.
