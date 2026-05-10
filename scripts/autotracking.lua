-- autotracking.lua
-- Archipelago auto-tracking for Duke Nukem 3D.
-- Depends on autotracking_data.lua (auto-generated): ITEM_MAP, LOCATION_MAP,
-- LEVEL_PATH, LEVEL_TO_EPISODE, UNLOCK_ID_TO_PREFIX.

-- Goal item AP IDs and target counts, populated each onClear from slot_data.
-- GOAL_COUNTS is the running progress per kind; rendered as "X/Y" via SetOverlay
-- in render_goal. We can't use consumable AcquiredCount here: PopTracker's
-- trackerview overrides the badge text with std::to_string(count) whenever
-- count > 0 (src/ui/trackerview.cpp), so a custom "X/Y" overlay would be
-- clobbered on every redraw. Toggles keep the user-set overlay intact.
GOAL_IDS = { exit = nil, secret = nil, boss = nil }
GOAL_TARGETS = { exit = 0, secret = 0, boss = 0 }
GOAL_COUNTS = { exit = 0, secret = 0, boss = 0 }
GOAL_CODES = { exit = "goal_exit", secret = "goal_secret", boss = "goal_boss" }

-- Active location IDs for the connected slot (subset of LOCATION_MAP).
ACTIVE_LOCATIONS = {}

-- Fuel-aware logic state. The apworld's `r.jetpack(N)` and `r.dive(N)` rules
-- depend on (1) having the gear and (2) having received enough total fuel.
-- Per-pickup fuel comes from slot_data.settings.dynamic (set per seed via the
-- YAML fuel_per_jetpack / fuel_per_scuba_gear options); total fuel is summed
-- in onItem. Defaults match the apworld defaults so manual variant + missing
-- slot_data still produce sensible numbers.
local function build_fuel_id_set(target_codes)
    local set = {}
    if type(ITEM_MAP) ~= "table" then return set end
    for ap_id, code in pairs(ITEM_MAP) do
        if target_codes[code] then set[ap_id] = true end
    end
    return set
end

JETPACK_ITEM_IDS = build_fuel_id_set({
    jetpack = true,
    jetpack_capacity = true,
    progressive_jetpack = true,
})
SCUBA_ITEM_IDS = build_fuel_id_set({
    scuba_gear = true,
    scuba_gear_capacity = true,
    progressive_scuba_gear = true,
})
STEROIDS_ITEM_IDS = build_fuel_id_set({
    steroids = true,
    steroids_capacity = true,
    progressive_steroids = true,
})
JETPACK_FUEL_PER_PICKUP = 100
SCUBA_FUEL_PER_PICKUP = 400
STEROIDS_FUEL_PER_PICKUP = 40
JETPACK_FUEL_TOTAL = 0
SCUBA_FUEL_TOTAL = 0
STEROIDS_FUEL_TOTAL = 0

-- Mode flag for the apworld's `progressive_weapons` YAML option. Read from
-- slot_data.settings.progressive_weapons at onClear; nil when slot_data
-- doesn't carry it (older apworlds, manual variant). Drives behavior that
-- depends on whether weapons arrive as separate Weapon + Capacity items
-- (false) or bundled Progressive items (true). Recommended apworld addition:
--     self.slot_data["settings"]["progressive_weapons"] = bool(self.options.progressive_weapons)
IS_PROGRESSIVE_WEAPONS = nil

-- Per-weapon ammo cap state. The displayed `<weapon>_max_start` value is the
-- player's CURRENT cap, which equals base (settings.maximum.<weapon>) plus the
-- sum of capacity bumps from received items. The bump-per-item value comes
-- from settings.dynamic[<capacity_item_ap_id>].capacity (set per seed by the
-- apworld). Defaults below match the items/__init__.py fallbacks for the
-- manual variant where no dynamic value is present.
WEAPON_KEYS = {
    "pistol", "shotgun", "chaingun", "rpg", "pipebomb",
    "shrinker", "devastator", "tripmine", "freezethrower", "expander",
}
WEAPON_CAPACITY_PER_PICKUP = {
    pistol = 20,
    shotgun = 10,
    chaingun = 50,
    rpg = 5,
    pipebomb = 3,
    shrinker = 3,
    devastator = 1,
    tripmine = 5,
    freezethrower = 20,
    expander = 3,
}

-- Per-weapon ammo bookkeeping. Every weapon-related item the apworld delivers
-- carries some ammo with it: Ammo packs (static `ammo` field), Capacity items
-- (static or dynamic-overridable `ammo` bundled in), and Weapon items
-- (intrinsic `ammo` granted on first pickup; pistol has no Weapon item).
-- Display the running total on the `<weapon>_ammo` consumable badge so the
-- count means "rounds received over the run" instead of "packs picked up".
WEAPON_AMMO_PER_PICKUP = {
    pistol = 30, shotgun = 15, chaingun = 150,
    rpg = 10, pipebomb = 10, shrinker = 10,
    devastator = 50, tripmine = 5, freezethrower = 50,
    expander = 35,
}
WEAPON_CAPACITY_AMMO_PER_PICKUP = {
    pistol = 10, shotgun = 5, chaingun = 25,
    rpg = 2, pipebomb = 1, shrinker = 1,
    devastator = 10, tripmine = 1, freezethrower = 20,
    expander = 2,
}
WEAPON_INTRINSIC_AMMO = {
    pistol = 0,  -- no Pistol item; pistol weapon is always present
    shotgun = 15, chaingun = 75,
    rpg = 5, pipebomb = 4, shrinker = 3,
    devastator = 15, tripmine = 2, freezethrower = 25,
    expander = 15,
}

-- Reverse maps from ap_id to weapon key, built once at module load.
local function build_weapon_id_map(prefix, suffix)
    local map = {}
    if type(ITEM_MAP) ~= "table" then return map end
    for ap_id, code in pairs(ITEM_MAP) do
        for _, w in ipairs(WEAPON_KEYS) do
            if code == (prefix or "") .. w .. (suffix or "") then
                map[ap_id] = w
                break
            end
        end
    end
    return map
end
WEAPON_FOR_CAPACITY_ID = build_weapon_id_map(nil, "_capacity")
WEAPON_FOR_PROGRESSIVE_ID = build_weapon_id_map("progressive_", nil)
WEAPON_FOR_AMMO_ID = build_weapon_id_map(nil, "_ammo")
WEAPON_FOR_BASE_ID = build_weapon_id_map(nil, nil)

-- Reverse maps for the three dual-form inventory items (Steroids / Scuba
-- Gear / Jetpack). Mirrors the WEAPON_FOR_*_ID pattern. The *_capacity ids
-- have no items.json counterpart (entries dropped during the inventory
-- consolidation; ids stay in ITEM_MAP and in JETPACK_ITEM_IDS / SCUBA_ITEM_IDS
-- so fuel accumulation still fires). Progressive ids do have JsonItems but
-- are hidden from the layout.
local INVENTORY_KEYS = { "steroids", "scuba_gear", "jetpack" }
local function build_inventory_id_map(prefix, suffix)
    local map = {}
    if type(ITEM_MAP) ~= "table" then return map end
    for ap_id, code in pairs(ITEM_MAP) do
        for _, k in ipairs(INVENTORY_KEYS) do
            if code == (prefix or "") .. k .. (suffix or "") then
                map[ap_id] = k
                break
            end
        end
    end
    return map
end
INVENTORY_FOR_CAPACITY_ID    = build_inventory_id_map(nil,           "_capacity")
INVENTORY_FOR_PROGRESSIVE_ID = build_inventory_id_map("progressive_", nil)
INVENTORY_FOR_BASE_ID        = build_inventory_id_map(nil,           nil)

-- ============================================================
-- Helpers
-- ============================================================

local function set_toggle(code, active)
    local obj = Tracker:FindObjectForCode(code)
    if obj then obj.Active = active end
end

-- Set Active on a JsonItem and, for staged toggle_badged items, also sync
-- CurrentStage. Workaround for a PopTracker rendering quirk: standalone
-- toggle_badged items don't apply the disabled-image filter when Active=false
-- (src/ui/trackerview.cpp). Giving the item two stages in items.json (both
-- with the same image) makes PopTracker generate a properly dimmed disabled
-- stage at index 0 and an active stage at index 1; CurrentStage picks which
-- one shows. We sync it here so callers can keep writing obj.Active without
-- caring about the workaround.
local function set_active(obj, val)
    if not obj then return end
    obj.Active = val
    if obj.Type == "toggle_badged" then
        obj.CurrentStage = val and 1 or 0
    end
end

-- Render a goal toggle's "X/Y" badge from GOAL_COUNTS / GOAL_TARGETS. Hides the
-- icon (Active=false, blank overlay) when the goal isn't in this seed, and
-- turns the count green once the target is hit.
local function render_goal(kind)
    local code = GOAL_CODES[kind]
    local obj = code and Tracker:FindObjectForCode(code)
    if not obj then return end
    local target = GOAL_TARGETS[kind] or 0
    local current = GOAL_COUNTS[kind] or 0
    if target > 0 then
        obj.Active = true
        obj:SetOverlay(string.format("%d/%d", current, target))
        obj:SetOverlayColor(current >= target and "#1FFF1F" or "#DCDCDC")
    else
        obj.Active = false
        obj:SetOverlay("")
    end
end

-- ============================================================
-- Handlers
-- ============================================================

function onClear(slot_data)
    -- 1. Read goal IDs and targets.
    if slot_data and slot_data["goal"] then
        local g = slot_data["goal"]
        if g["Exit"] then
            GOAL_IDS.exit = g["Exit"]["id"]
            GOAL_TARGETS.exit = g["Exit"]["count"] or 0
        end
        if g["Secret"] then
            GOAL_IDS.secret = g["Secret"]["id"]
            GOAL_TARGETS.secret = g["Secret"]["count"] or 0
        end
        if g["Boss"] then
            GOAL_IDS.boss = g["Boss"]["id"]
            GOAL_TARGETS.boss = g["Boss"]["count"] or 0
        end
    else
        GOAL_TARGETS = { exit = 0, secret = 0, boss = 0 }
    end

    -- 2. Build ACTIVE_LOCATIONS set from slot_data.
    ACTIVE_LOCATIONS = {}
    if slot_data and type(slot_data["locations"]) == "table" then
        for _, loc_id in ipairs(slot_data["locations"]) do
            ACTIVE_LOCATIONS[loc_id] = true
        end
    end

    -- 3. Derive active episodes from slot_data["levels"]. Each entry is a
    --    level Unlock item ID. Map back to episode via UNLOCK_ID_TO_PREFIX.
    local active_episodes = { [1] = false, [2] = false, [3] = false, [4] = false }
    local active_levels = {}
    if slot_data and type(slot_data["levels"]) == "table" then
        for _, item_id in ipairs(slot_data["levels"]) do
            local prefix = UNLOCK_ID_TO_PREFIX[item_id]
            if prefix then
                active_levels[prefix] = true
                local ep = LEVEL_TO_EPISODE[prefix]
                if ep then active_episodes[ep] = true end
            end
        end
    end
    for ep = 1, 4 do
        set_toggle("ep" .. ep, active_episodes[ep])
    end
    set_toggle("e1l7_enabled", active_levels["E1L7"] == true)

    -- 4. Ability/Interact gating from slot_data["settings"]["lock"]. Each
    --    pair (ab_locked / ab_unlocked, int_locked / int_unlocked) is set
    --    as the inverse of the other so access_rules can express
    --    "always-have-X OR have-X-as-item" without negation, which
    --    PopTracker doesn't natively support.
    local lock = (slot_data and slot_data["settings"] and slot_data["settings"]["lock"]) or {}
    local ab_locked = lock["jump"] or lock["crouch"] or lock["run"] or lock["dive"]
    local int_locked = lock["open"] or lock["use"]
    set_toggle("ab_locked", ab_locked == true)
    set_toggle("int_locked", int_locked == true)
    set_toggle("ab_unlocked", ab_locked ~= true)
    set_toggle("int_unlocked", int_locked ~= true)

    -- 4a. Logic-difficulty stage on the progressive `logic_difficulty` item
    --     (0=easy, 1=medium, 2=hard, 3=extreme — same as the apworld).
    --     Default to medium (the apworld's default) since slot_data
    --     doesn't currently carry this. Active=true keeps the icon bright.
    local diff = 1
    if slot_data and slot_data["settings"]
            and slot_data["settings"]["logic_difficulty"] ~= nil then
        diff = slot_data["settings"]["logic_difficulty"]
    end
    local diff_obj = Tracker:FindObjectForCode("logic_difficulty")
    if diff_obj then
        diff_obj.CurrentStage = diff
        diff_obj.Active = true
    end

    -- 4b. Glitched logic. Defaults off (apworld's default).
    local glitched = false
    if slot_data and slot_data["settings"] then
        glitched = slot_data["settings"]["glitch_logic"] == true
    end
    set_toggle("glitched_logic", glitched)

    -- 4d. Seed info badges (display-only, no effect on access rules).
    --     skill_level: progressive item with 4 stages mirroring the apworld
    --     option (0=Piece of Cake → 3=Damn I'm Good). Default to apworld
    --     default (1=Let's Rock) when slot_data is missing the field.
    local skill = 1
    if slot_data and slot_data["settings"]
            and slot_data["settings"]["difficulty"] ~= nil then
        skill = slot_data["settings"]["difficulty"]
    end
    local skill_obj = Tracker:FindObjectForCode("skill_level")
    if skill_obj then
        skill_obj.CurrentStage = skill
        skill_obj.Active = true
    end

    -- no_save: simple toggle; apworld field is settings.no_save (the inverse
    -- of allow_saving). Defaults off when slot_data is missing the field.
    local no_save = false
    if slot_data and slot_data["settings"] then
        no_save = slot_data["settings"]["no_save"] == true
    end
    set_toggle("no_save", no_save)

    -- Mode: progressive weapons. Stored globally for use elsewhere (currently
    -- the base-toggle drive in onItem). Stays nil when slot_data omits it,
    -- which is harmless because in non-progressive mode no progressive_<weapon>
    -- items arrive (so the toggle-flip path doesn't fire).
    IS_PROGRESSIVE_WEAPONS = nil
    if slot_data and slot_data["settings"]
            and slot_data["settings"]["progressive_weapons"] ~= nil then
        IS_PROGRESSIVE_WEAPONS = slot_data["settings"]["progressive_weapons"] == true
    end

    -- 4e. Per-weapon ammo cap. settings.maximum.<weapon> is the seed's BASE
    --     cap; the in-game cap grows by `capacity_per` each time a Capacity
    --     (or progressive-stage-2+) item is received. The cap is displayed
    --     as the toggle_badged AcquiredCount on the weapon icon itself.
    --     Don't pre-seed unreceived weapons with the base cap — PopTracker
    --     renders the badge text on a toggle_badged even when Active=false,
    --     which made every weapon icon read as "owned" the moment AP
    --     connected. Cache the base caps in WEAPON_BASE_CAP and only stamp
    --     them onto the badge in onItem when the corresponding weapon
    --     actually arrives (base item in non-progressive mode, or
    --     progressive stage 1 in progressive mode). Pistol is always
    --     present, so re-light it explicitly and seed its cap immediately.
    local maximum = (slot_data and slot_data["settings"]
            and slot_data["settings"]["maximum"]) or {}
    WEAPON_BASE_CAP = {}
    for _, w in ipairs(WEAPON_KEYS) do
        WEAPON_BASE_CAP[w] = tonumber(maximum[w]) or 0
        local obj = Tracker:FindObjectForCode(w)
        if obj then obj.AcquiredCount = 0 end
    end
    local pistol_obj = Tracker:FindObjectForCode("pistol")
    if pistol_obj then
        set_active(pistol_obj, true)
        pistol_obj.AcquiredCount = WEAPON_BASE_CAP["pistol"] or 0
    end

    -- 4d. Inventory toggle_badged badge reset. The 3 dual-form inventory
    --     items (Steroids / Scuba Gear / Jetpack) need explicit AcquiredCount
    --     clearing because the generic toggle_badged reset below only zeroes
    --     Active. The 3 derived fuel-total consumables (steroids_fuel /
    --     scuba_fuel / jetpack_fuel) carry no AP id so they're invisible
    --     to the ITEM_MAP-driven reset — clear them explicitly here. onItem
    --     will re-bump these as items stream back in after reconnect. (The
    --     4 plain consumables Holo Duke / NVG / First Aid Kit / Protective
    --     Boots are reset by the generic consumable branch in the ITEM_MAP
    --     loop.)
    for _, code in ipairs({ "steroids", "scuba_gear", "jetpack" }) do
        local obj = Tracker:FindObjectForCode(code)
        if obj then obj.AcquiredCount = 0 end
    end
    for _, code in ipairs({ "steroids_fuel", "jetpack_fuel", "scuba_fuel" }) do
        local obj = Tracker:FindObjectForCode(code)
        if obj then obj.AcquiredCount = 0 end
    end

    -- 4c. Fuel-aware logic: read per-pickup capacities for jetpack, scuba,
    --     and steroids from slot_data.settings.dynamic. The apworld writes
    --     the same `capacity` value to every entry in a fuel group, so first
    --     match wins. Reset accumulated totals; onItem will bump them as
    --     items stream back in after reconnect.
    JETPACK_FUEL_PER_PICKUP = 100
    SCUBA_FUEL_PER_PICKUP = 400
    STEROIDS_FUEL_PER_PICKUP = 40
    JETPACK_FUEL_TOTAL = 0
    SCUBA_FUEL_TOTAL = 0
    STEROIDS_FUEL_TOTAL = 0
    local dynamic = slot_data and slot_data["settings"]
            and slot_data["settings"]["dynamic"]
    if type(dynamic) == "table" then
        for ap_id_str, entry in pairs(dynamic) do
            local ap_id = tonumber(ap_id_str)
            if ap_id and type(entry) == "table" then
                if entry.capacity then
                    if JETPACK_ITEM_IDS[ap_id] then
                        JETPACK_FUEL_PER_PICKUP = entry.capacity
                    elseif SCUBA_ITEM_IDS[ap_id] then
                        SCUBA_FUEL_PER_PICKUP = entry.capacity
                    elseif STEROIDS_ITEM_IDS[ap_id] then
                        STEROIDS_FUEL_PER_PICKUP = entry.capacity
                    end
                    local weapon = WEAPON_FOR_CAPACITY_ID[ap_id]
                    if weapon then
                        WEAPON_CAPACITY_PER_PICKUP[weapon] = entry.capacity
                    end
                end
                -- Capacity items also carry bundled `ammo` (apworld defaults
                -- ceil(capacity_per/2) when overriding capacity).
                if entry.ammo then
                    local weapon = WEAPON_FOR_CAPACITY_ID[ap_id]
                    if weapon then
                        WEAPON_CAPACITY_AMMO_PER_PICKUP[weapon] = entry.ammo
                    end
                end
            end
        end
    end

    -- 5. Detect "include_secrets" by scanning ACTIVE_LOCATIONS for any
    --    location whose path contains "/Secret " (i.e. a sector check).
    local has_secrets = false
    for loc_id in pairs(ACTIVE_LOCATIONS) do
        local path = LOCATION_MAP[loc_id]
        if path and path:find("/Secret ", 1, true) then
            has_secrets = true
            break
        end
    end
    set_toggle("secrets", has_secrets)

    -- 6. Reset every tracked item.
    for _, code in pairs(ITEM_MAP) do
        local obj = Tracker:FindObjectForCode(code)
        if obj then
            if obj.Type == "toggle" or obj.Type == "toggle_badged" then
                set_active(obj, false)
            elseif obj.Type == "progressive" then
                obj.CurrentStage = 0
            elseif obj.Type == "consumable" then
                obj.AcquiredCount = 0
            end
        end
    end

    -- 6a. Pistol ammo baseline. The mod's ap_set_default_inv() (Duke3DAP
    --     source/rr/src/ap_integration.cpp) gives the player a flat 96 pistol
    --     rounds on every level entry, clamped to max_ammo[pistol] (= base
    --     cap). This is independent of skill_level and stacks with AP-
    --     delivered ammo. Seed it here so the badge mirrors the actual
    --     level-start ammo; onItem then adds AP-received ammo on top.
    local PISTOL_BASELINE_AMMO = 96
    local base_pistol_cap = tonumber(maximum["pistol"]) or PISTOL_BASELINE_AMMO
    local pistol_ammo_obj = Tracker:FindObjectForCode("pistol_ammo")
    if pistol_ammo_obj then
        pistol_ammo_obj.AcquiredCount = math.min(PISTOL_BASELINE_AMMO, base_pistol_cap)
    end

    -- 7. Reset goal progress and render the X/Y badges. Goals not in this
    --    seed (target == 0) are deactivated by render_goal.
    GOAL_COUNTS = { exit = 0, secret = 0, boss = 0 }
    for kind, _ in pairs(GOAL_CODES) do
        render_goal(kind)
    end

    -- 8. Reset all locations. Inactive ones get AvailableChestCount = 0 so
    --    they visually drop out (no native PopTracker hide-by-id for sections).
    for loc_id, loc_path in pairs(LOCATION_MAP) do
        local loc = Tracker:FindObjectForCode("@" .. loc_path)
        if loc then
            if ACTIVE_LOCATIONS[loc_id] then
                loc.AvailableChestCount = loc.ChestCount
            else
                loc.AvailableChestCount = 0
            end
        end
    end
end

function onItem(index, item_id, item_name, player_number)
    -- Fuel-aware accumulation. A single item can grant fuel even if it's also
    -- the goal/regular item path below — handle these in parallel rather than
    -- inside the dispatch chain. (No jetpack/scuba item is also a goal item.)
    if JETPACK_ITEM_IDS[item_id] then
        JETPACK_FUEL_TOTAL = JETPACK_FUEL_TOTAL + JETPACK_FUEL_PER_PICKUP
        local fuel_obj = Tracker:FindObjectForCode("jetpack_fuel")
        if fuel_obj then fuel_obj.AcquiredCount = JETPACK_FUEL_TOTAL end
    elseif SCUBA_ITEM_IDS[item_id] then
        SCUBA_FUEL_TOTAL = SCUBA_FUEL_TOTAL + SCUBA_FUEL_PER_PICKUP
        local fuel_obj = Tracker:FindObjectForCode("scuba_fuel")
        if fuel_obj then fuel_obj.AcquiredCount = SCUBA_FUEL_TOTAL end
    elseif STEROIDS_ITEM_IDS[item_id] then
        STEROIDS_FUEL_TOTAL = STEROIDS_FUEL_TOTAL + STEROIDS_FUEL_PER_PICKUP
        local fuel_obj = Tracker:FindObjectForCode("steroids_fuel")
        if fuel_obj then fuel_obj.AcquiredCount = STEROIDS_FUEL_TOTAL end
    end

    -- Goal items: bump the matching counter and re-render its X/Y badge.
    for kind, goal_id in pairs(GOAL_IDS) do
        if goal_id and item_id == goal_id then
            GOAL_COUNTS[kind] = (GOAL_COUNTS[kind] or 0) + 1
            render_goal(kind)
            return
        end
    end

    local code = ITEM_MAP[item_id]
    if not code then return end

    -- obj may be nil for items that exist in ITEM_MAP (auto-generated from
    -- the apworld) but have no items.json entry (e.g. <weapon>_capacity
    -- since the dedicated capacity row was retired). Guard the dispatch
    -- and let the per-weapon cap/ammo bumps below run regardless — those
    -- only depend on WEAPON_FOR_*_ID maps (keyed by ap_id).
    local obj = Tracker:FindObjectForCode(code)
    local ammo_pack_weapon = WEAPON_FOR_AMMO_ID[item_id]

    local prev_stage = nil
    if obj then
        if obj.Type == "toggle" or obj.Type == "toggle_badged" then
            set_active(obj, true)
        elseif obj.Type == "progressive" then
            prev_stage = obj.CurrentStage
            obj.CurrentStage = prev_stage + 1
        elseif obj.Type == "consumable" then
            if ammo_pack_weapon then
                -- Ammo-pack count badge displays total ammo received, not pack count.
                obj.AcquiredCount = obj.AcquiredCount
                        + (WEAPON_AMMO_PER_PICKUP[ammo_pack_weapon] or 1)
            else
                obj.AcquiredCount = obj.AcquiredCount + 1
            end
        end
    end

    -- Helper: bump <weapon>_ammo running total by `amount` rounds.
    local function bump_ammo_total(weapon, amount)
        if not weapon or not amount or amount <= 0 then return end
        local ammo_obj = Tracker:FindObjectForCode(weapon .. "_ammo")
        if ammo_obj then
            ammo_obj.AcquiredCount = ammo_obj.AcquiredCount + amount
        end
    end

    -- Helper: bump the <weapon> toggle_badged AcquiredCount, which is the
    -- on-icon current ammo cap badge.
    local function bump_cap(weapon, amount)
        if not weapon or not amount or amount <= 0 then return end
        local cap_obj = Tracker:FindObjectForCode(weapon)
        if cap_obj then
            cap_obj.AcquiredCount = cap_obj.AcquiredCount + amount
        end
    end

    -- Base weapon item (only non-pistol weapons exist; pistol is always
    -- present). Grants the weapon, seeds the cap badge with the seed's
    -- base cap (deferred from onClear so unreceived weapons stay badge-
    -- less), and grants intrinsic ammo for it.
    local base_weapon = WEAPON_FOR_BASE_ID[item_id]
    if base_weapon then
        bump_cap(base_weapon, (WEAPON_BASE_CAP and WEAPON_BASE_CAP[base_weapon]) or 0)
        bump_ammo_total(base_weapon, WEAPON_INTRINSIC_AMMO[base_weapon] or 0)
    end

    -- Per-weapon ammo cap: every <weapon> Capacity bumps the cap. For
    -- Progressive Pistol every stage is a Pistol Capacity (pistol weapon is
    -- always present, so items=[Pistol Capacity]); for other progressives
    -- only stage 2+ delivers a Capacity sub-item (stage 1 is the weapon).
    local cap_weapon = WEAPON_FOR_CAPACITY_ID[item_id]
    if cap_weapon then
        bump_cap(cap_weapon, WEAPON_CAPACITY_PER_PICKUP[cap_weapon] or 0)
        bump_ammo_total(cap_weapon, WEAPON_CAPACITY_AMMO_PER_PICKUP[cap_weapon] or 0)
    else
        local prog_weapon = WEAPON_FOR_PROGRESSIVE_ID[item_id]
        if prog_weapon then
            -- First Progressive <non-pistol> grants the weapon itself; light
            -- the base toggle and seed the base cap badge so "owned" reads
            -- off the same row regardless of progressive_weapons mode.
            -- (Pistol is forced Active + seeded in onClear.)
            if prev_stage == 0 and prog_weapon ~= "pistol" then
                set_active(Tracker:FindObjectForCode(prog_weapon), true)
                bump_cap(prog_weapon, (WEAPON_BASE_CAP and WEAPON_BASE_CAP[prog_weapon]) or 0)
                bump_ammo_total(prog_weapon, WEAPON_INTRINSIC_AMMO[prog_weapon] or 0)
            end
            -- Cap bump: every Progressive Pistol carries a Pistol Capacity;
            -- other Progressives carry Capacity only at stage 2+.
            if prog_weapon == "pistol" or (prev_stage and prev_stage >= 1) then
                bump_cap(prog_weapon, WEAPON_CAPACITY_PER_PICKUP[prog_weapon] or 0)
                bump_ammo_total(prog_weapon, WEAPON_CAPACITY_AMMO_PER_PICKUP[prog_weapon] or 0)
            end
        end
    end

    -- Inventory cap/progressive bumps (dual-form items: steroids / scuba_gear /
    -- jetpack). Mirrors the weapon block above. Each capacity stage delivered
    -- bumps the base toggle_badged AcquiredCount by 1, regardless of whether
    -- the apworld delivered it as the base item, a *_capacity item, or a
    -- progressive_* stage. Unlike weapons, the base inventory item itself
    -- carries a capacity stage (the apworld counts it as a fuel-pickup via
    -- JETPACK_ITEM_IDS / SCUBA_ITEM_IDS membership), so a base receipt also
    -- bumps the badge. There is no pistol-equivalent always-on inventory
    -- item, so progressives obey the non-pistol pattern unconditionally.
    local function bump_inv_cap(key)
        if not key then return end
        local obj_inv = Tracker:FindObjectForCode(key)
        if obj_inv then
            obj_inv.AcquiredCount = obj_inv.AcquiredCount + 1
        end
    end

    local cap_inv = INVENTORY_FOR_CAPACITY_ID[item_id]
    if cap_inv then
        bump_inv_cap(cap_inv)
    else
        local prog_inv = INVENTORY_FOR_PROGRESSIVE_ID[item_id]
        if prog_inv then
            if prev_stage == 0 then
                local toggle_obj = Tracker:FindObjectForCode(prog_inv)
                if toggle_obj then
                    set_active(toggle_obj, true)
                    toggle_obj.AcquiredCount = toggle_obj.AcquiredCount + 1
                end
            end
            if prev_stage and prev_stage >= 1 then
                bump_inv_cap(prog_inv)
            end
        end
    end

    local base_inv = INVENTORY_FOR_BASE_ID[item_id]
    if base_inv then
        bump_inv_cap(base_inv)
    end
end

function onLocation(location_id, location_name)
    local loc_path = LOCATION_MAP[location_id]
    if not loc_path then return end

    local loc = Tracker:FindObjectForCode("@" .. loc_path)
    if loc then
        loc.AvailableChestCount = loc.AvailableChestCount - 1
    end
end

-- Register AP handlers
Archipelago:AddClearHandler("duke3d_clear_handler", onClear)
Archipelago:AddItemHandler("duke3d_item_handler", onItem)
Archipelago:AddLocationHandler("duke3d_location_handler", onLocation)
