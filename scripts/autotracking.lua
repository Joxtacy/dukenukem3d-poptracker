-- autotracking.lua
-- Archipelago auto-tracking for Duke Nukem 3D.
-- Depends on autotracking_data.lua (auto-generated): ITEM_MAP, LOCATION_MAP,
-- LEVEL_PATH, LEVEL_TO_EPISODE, UNLOCK_ID_TO_PREFIX.

-- Goal item AP IDs and target counts, populated each onClear from slot_data.
GOAL_IDS = { exit = nil, secret = nil, boss = nil }
GOAL_TARGETS = { exit = 0, secret = 0, boss = 0 }
GOAL_CODES = { exit = "goal_exit", secret = "goal_secret", boss = "goal_boss" }

-- Active location IDs for the connected slot (subset of LOCATION_MAP).
ACTIVE_LOCATIONS = {}

-- ============================================================
-- Helpers
-- ============================================================

local function set_toggle(code, active)
    local obj = Tracker:FindObjectForCode(code)
    if obj then obj.Active = active end
end

local function reset_consumable(code, _max_quantity_unused, active)
    -- NOTE: PopTracker JsonItem doesn't expose MaxQuantity as a writable
    -- property at runtime. The cap from items.json (99) is fixed; the
    -- goal counter shows X/99 rather than X/<seed target>. Showing the
    -- real target needs a separate text-label widget (v0.2 layout work).
    local obj = Tracker:FindObjectForCode(code)
    if not obj then return end
    obj.AcquiredCount = 0
    if active ~= nil then obj.Active = active end
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

    -- 4. Ability/Interact gating from slot_data["settings"]["lock"].
    local lock = (slot_data and slot_data["settings"] and slot_data["settings"]["lock"]) or {}
    local ab_locked = lock["jump"] or lock["crouch"] or lock["run"] or lock["dive"]
    local int_locked = lock["open"] or lock["use"]
    set_toggle("ab_locked", ab_locked == true)
    set_toggle("int_locked", int_locked == true)

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
                obj.Active = false
            elseif obj.Type == "progressive" then
                obj.CurrentStage = 0
            elseif obj.Type == "consumable" then
                obj.AcquiredCount = 0
            end
        end
    end

    -- 7. Configure goal counter consumables: badge shows X/Y once MaxQuantity
    --    is set, and we hide the slot for goals not in this seed (count == 0).
    for kind, code in pairs(GOAL_CODES) do
        local target = GOAL_TARGETS[kind] or 0
        local max_q = target > 0 and target or 1
        reset_consumable(code, max_q, target > 0)
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
    -- Goal items: bump the matching consumable counter.
    for kind, goal_id in pairs(GOAL_IDS) do
        if goal_id and item_id == goal_id then
            local code = GOAL_CODES[kind]
            local obj = Tracker:FindObjectForCode(code)
            if obj then
                obj.AcquiredCount = obj.AcquiredCount + 1
            end
            return
        end
    end

    local code = ITEM_MAP[item_id]
    if not code then return end

    local obj = Tracker:FindObjectForCode(code)
    if not obj then return end

    if obj.Type == "toggle" or obj.Type == "toggle_badged" then
        obj.Active = true
    elseif obj.Type == "progressive" then
        obj.CurrentStage = obj.CurrentStage + 1
    elseif obj.Type == "consumable" then
        obj.AcquiredCount = obj.AcquiredCount + 1
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
