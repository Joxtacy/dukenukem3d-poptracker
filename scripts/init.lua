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

if PopVersion and PopVersion >= "0.18.0" then
    ScriptHost:LoadScript("scripts/autotracking_data.lua")
    ScriptHost:LoadScript("scripts/autotracking.lua")
end
