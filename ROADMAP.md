# Roadmap

Living list of what's shipped, what's next, and what's deliberately deferred. Update as we go.

## v0.1 — shipped

- Single "All Episodes" variant; episode rows hidden via `epN` toggles when an episode isn't in the seed.
- 239 items: weapons + ammo + capacity + progressive variants, inventory, armor, abilities, healing, per-level Unlock + Automap + colour Key Cards, hidden setting toggles, goal counters.
- 1608 locations across 40 levels (Exit + Secret Exit, sector secrets, every sprite pickup including density-5 MP-only spots).
- Goal counter (Exit / Secret / Boss). Ticks correctly; currently displays as `X/99` because PopTracker's `JsonItem.MaxQuantity` is read-only at runtime — see v0.2.
- Autotracker: derives active episodes from `slot_data["levels"]`, ability/interact gating from `slot_data["settings"]["lock"]`, secrets toggle from active location names, E1L7 from active levels.
- Simplified access rules (`epN,eXlY_unlock`, plus `secrets` for sector checks). Sections show as accessible the moment the level unlocks.
- Tooling: `gen_pack_data.py`, `gen_layout.py`, `gen_placeholders.py`, `gen_recolors.py` (see [`tools/README.md`](tools/README.md)).
- Release workflow at `.github/workflows/release.yml` (manual trigger; bumps version, generates changelog, builds zip, updates `versions.json`, tags + creates GitHub release).

## v0.2 — next iteration

Polish pass focused on real visual tracking and tighter logic.

- **Per-level top-down maps + pin coordinates.** Two paths, both driven by [`tools/gen_maps.py`](tools/gen_maps.py):
  - **Vector renders (default)**: parse each `.MAP` file from `duke3d.grp` and render a wireframe top-down PNG plus accurate sprite/sector pin coordinates. Already wired; run `tools/gen_maps.py --grp <path>` then `python3 tools/gen_pack_data.py`.
  - **Manual / wiki images via calibration**: drop your own per-level PNGs into `images/eXlY_map.png`, then run `tools/gen_maps.py --init-calibration` to generate `tools/map_calibration.json` with three auto-picked reference sprites per level. Fill in pixel coords in any image editor that shows cursor position, re-run `gen_maps.py`, and a 3-point affine transform produces pins aligned to your manual images. Mix and match per-level. Full workflow in [`tools/README.md`](tools/README.md#calibration-mode-use-a-manual-map-image-instead-of-the-vector-render).
- **Per-key access_rules gating.** Heuristic first pass: any location whose name mentions a door / colour gates on the matching key card. Cleaner second pass: encode the apworld's region requirements per level.
- **Dynamic goal target display.** Replace the static `X/99` badge with a text-label widget that reads `GOAL_TARGETS` and renders `X / <slot target>`. Layout tweak.
- **Real icons for remaining placeholders.** Whatever still ships as text-labelled stubs in `images/`.

## v0.3+ — future / nice-to-have

Bigger lifts; revisit after v0.2.

- **Full region-graph access rules.** Mirror the apworld's per-level Lua-style logic (jump, dive, explosives, jetpack fuel, glitch tricks). This is the gap Universal Tracker exposes — UT uses the real graph, our tracker uses a simplified `level-unlock` model.
- **Auto map-tab switching.** When the player enters E2L4 in-game, the tracker switches to the Episode 2 tab and the E2L4 map tab. Needs NBloodAP to write a DataStorage key like `duke3d_current_level_<slot>`; if missing, propose an upstream PR. `tools/test_map_switch.py` (adapted from Keen) already exists as a testing harness.
- **Multiplayer-only pickup tracking.** Currently included in the location pool; could surface a setting toggle that gates the `MP …` density-5 sections so they hide unless `include_multiplayer_items: true`.
- **Trap notifications.** Surface trap items (Celebration / Shrink / Death / Caffeine / etc.) as a transient chat overlay or counter.
- **Broadcast / map-only variant.** A second variant in `manifest.json` for streaming overlays — minimal item dock + map only. Mirrors the Doom II tracker's split.
- **Difficulty / max-ammo visualization.** Read `slot_data["settings"]["maximum"]` and show each weapon's starting cap inline.

## Known limitations (acceptable)

- Trap items aren't tracked. They arrive as silent items and fire in-game effects; not surfaced in the UI.
- Healing items are tracked as "received" counters, not as current HP. Persistent HP cap upgrades (`Ego Boost`, `Buff Up`) accumulate but the tracker doesn't compute resulting max HP.
- The codegen requires the apworld extracted to `/tmp/duke3d-apworld/extracted/duke3d/`; no auto-bump from a remote URL.

## How this list moves

When something ships, move it into the relevant version section above. When the version is cut as a release, archive its bullet list under a "## Released" heading at the bottom (or in a `CHANGELOG.md` if you'd prefer separate files).
