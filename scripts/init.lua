-- Duke Nukem 3D AP Tracker
-- init.lua: load items, locations, maps, layout, and AP autotracking.

Tracker:AddItems("items/items.json")

ScriptHost:LoadScript("scripts/logic.lua")

Tracker:AddLocations("locations/e1_locations.json")
Tracker:AddLocations("locations/e2_locations.json")
Tracker:AddLocations("locations/e3_locations.json")
Tracker:AddLocations("locations/e4_locations.json")

Tracker:AddMaps("maps/e1_maps.json")
Tracker:AddMaps("maps/e2_maps.json")
Tracker:AddMaps("maps/e3_maps.json")
Tracker:AddMaps("maps/e4_maps.json")

Tracker:AddLayouts("layouts/tracker.json")

-- Default the Logic Difficulty progressive at pack load. Four stages
-- (0=easy, 1=medium, 2=hard, 3=extreme) mirror the apworld option;
-- default to medium. Active=true keeps the icon rendered bright since
-- it's a settings dial, not a collectible item — onClear re-sets this
-- whenever AP reconnects.
local diff_obj = Tracker:FindObjectForCode("logic_difficulty")
if diff_obj then
    diff_obj.CurrentStage = 1  -- medium
    diff_obj.Active = true
end

-- Pistol is always present in Duke 3D (no Pistol weapon item exists in the
-- apworld). Force the toggle_badged on so the icon stays lit; only its
-- AcquiredCount badge — driven by onClear / onItem — varies.
local pistol_obj = Tracker:FindObjectForCode("pistol")
if pistol_obj then pistol_obj.Active = true end

if PopVersion and PopVersion >= "0.18.0" then
    ScriptHost:LoadScript("scripts/autotracking_data.lua")
    ScriptHost:LoadScript("scripts/autotracking.lua")
end
