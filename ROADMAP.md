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
- ~~**Per-key access_rules gating.**~~ Done — heuristic regex in `gen_pack_data.py` matches `<Color> Door/Room/Gate/Basement/Storage/Boat/Auction/Cashier` and `near <Color> Door/Gate` patterns and appends `<level>_<color>_key` to the access rule. Catches 24 sections across all four episodes, all confirmed correct against the apworld region graph. Ability/explosive/jetpack-fuel gating moves to v0.3.
- **Dynamic goal target display.** Replace the static `X/99` badge with a text-label widget that reads `GOAL_TARGETS` and renders `X / <slot target>`. Layout tweak.
- **Real icons for remaining placeholders.** Whatever still ships as text-labelled stubs in `images/`.

## v0.3+ — future / nice-to-have

Bigger lifts; revisit after v0.2.

- **Fuel-aware logic + randomizer Difficulty option.** Today `r.jetpack(50)` and `r.jetpack(200)` both collapse to "has jetpack." A proper implementation would count Jetpack Capacity items (and Scuba Capacity / Steroids Capacity) and verify the player has enough fuel for the rule's threshold. This is also where the apworld's `Difficulty` option starts mattering to the tracker — it controls `DIFF_TO_REQ_MAPPING` (per-difficulty fuel-required thresholds) and the per-weapon ammo-capacity counts. Until then, `Difficulty` does nothing in the tracker (only `LogicDifficulty` and `GlitchLogic` affect gating).
- **Slot data: logic_difficulty / glitch_logic.** The apworld doesn't currently transmit these in slot_data (`fill_slot_data` only emits skill_level under `settings.difficulty`, lock, no_save, steroids_duration). Tracker defaults to medium-no-glitch and exposes them as a Settings panel in the Status tab. Upstream PR could add them to `fill_slot_data` so the tracker auto-syncs.

### Apworld terminology cheat sheet

Four YAML options have similar names; only two affect tracker logic today:

| YAML option | What it controls | In slot_data? | Tracker handling |
|---|---|---|---|
| `skill_level` | In-game enemy density (Piece of Cake → Damn I'm Good) | ✅ as `settings.difficulty` | Ignored — doesn't gate locations |
| `difficulty` | Randomizer pool tuning + per-difficulty fuel thresholds | ❌ | Ignored today; matters once fuel-aware logic ships (above) |
| `logic_difficulty` | Which logical tricks count (`r.difficulty("medium")` etc.) | ❌ | Settings panel (`Logic Difficulty` progressive item) |
| `glitch_logic` | Whether glitch tricks (`r.glitched`, `r.crouch_jump`) count | ❌ | Settings panel (`Glitched Logic` toggle) |
- **Apworld stragglers**: ~17 locations (E2L10 Alpha, E2L2 Beta, E1L7 MP Side Room, E4L10 DukeTag, etc.) aren't picked up by `parse_level_logic.py` because they're added via patterns the AST walker doesn't model (`add_location` inside loops, conditional regions, etc.). Fall back to the v0.2 heuristic. Would need targeted parser extensions per pattern.

- ~~**Full region-graph access rules.**~~ Done — `tools/parse_level_logic.py` AST-walks each level's `main_region()`, builds the region DAG, translates `r.jump`/`r.can_open`/`r.explosives`/`r.jetpack(N)`/`self.<color>_key`/`self.event(...)`/etc. into PopTracker access_rules using `$func` Lua helpers (`scripts/logic.lua`), and emits DNF per location. Complementary `ab_unlocked`/`int_unlocked` toggles handle the YAML `unlock_abilities`/`unlock_interact` cases. Logic-difficulty thresholds and glitch-logic flag are runtime toggles set in `onClear`. Covers 1591 of 1608 locations end-to-end; the remaining ~17 (DukeMatch / Beta / Alpha edge-case names) fall back to the v0.2 key-name heuristic. Fuel-amount granularity (`r.jetpack(50)` vs `r.jetpack(200)`) is collapsed to "has jetpack at all" — fuel-aware tracking is a future improvement.
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
