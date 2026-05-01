-- logic.lua: helper functions used by access_rules in locations/*.json.
--
-- PopTracker invokes "$funcname" entries in access_rules by calling the
-- matching global Lua function. Each helper returns 1 (rule satisfied),
-- 0 (rule blocked), or a truthy/falsy value PopTracker treats accordingly.
--
-- The helpers exist so per-location rules stay short. Without them, every
-- "any of N items" check would have to be expanded combinatorially across
-- alternative rule strings, blowing up the JSON.

function has(code)
    return Tracker:ProviderCountForCode(code) > 0
end

local function bool(b)
    if b then return 1 else return 0 end
end

-- ---------- ability + interaction conditional gating ----------
-- Each ability (Jump/Crouch/Sprint/Dive) is "available" in two cases:
--   1) the abilities-locked YAML option is OFF for this seed, in which case
--      we set ab_unlocked at connect time and the player always has the
--      ability;
--   2) the abilities-locked option is ON and the player has received the
--      corresponding item.
-- Same pattern for Open/Use via int_unlocked / int_locked.

function can_jump()
    return bool(has("ab_unlocked") or has("jump"))
end

function can_crouch()
    return bool(has("ab_unlocked") or has("crouch"))
end

function can_sprint()
    return bool(has("ab_unlocked") or has("sprint"))
end

function can_dive()
    -- Per rules.py, can_dive also accepts having Scuba Gear (group).
    return bool(has("ab_unlocked") or has("dive")
        or has("scuba_gear") or has("progressive_scuba_gear"))
end

function can_open()
    return bool(has("int_unlocked") or has("open"))
end

function can_use()
    return bool(has("int_unlocked") or has("use"))
end

-- ---------- composed primitives ----------

local function has_group_jetpack()
    return has("jetpack") or has("progressive_jetpack")
end

local function has_group_steroids()
    return has("steroids") or has("progressive_steroids")
end

-- Fuel-aware jetpack / scuba helpers. Mirrors the apworld's
-- CanJetPack(fuel) / CanDiveTo(fuel) rules: gear + enough accumulated
-- fuel-per-pickup to cover the threshold. JETPACK_FUEL_TOTAL etc. are
-- maintained by autotracking.lua. In manual variant they're nil; we treat
-- "having the gear" as sufficient there since the user is checking by hand.
function has_jetpack_fuel(fuel)
    fuel = tonumber(fuel) or 0
    if not has_group_jetpack() then return 0 end
    if JETPACK_FUEL_TOTAL == nil then return 1 end
    return bool(JETPACK_FUEL_TOTAL >= fuel)
end

function can_dive_fuel(fuel)
    fuel = tonumber(fuel) or 0
    if can_dive() == 0 then return 0 end
    if SCUBA_FUEL_TOTAL == nil then return 1 end
    return bool(SCUBA_FUEL_TOTAL >= fuel)
end

-- Any "simple jump sequence": real jumping or a 50-fuel jetpack burst.
-- The apworld defines r.jump = can_jump | jetpack(50).
function jump()
    return bool(has("ab_unlocked") or has("jump") or has_jetpack_fuel(50) == 1)
end

-- Any sprint source. r.sprint = can_sprint | steroids.
function sprint()
    return bool(has("ab_unlocked") or has("sprint") or has_group_steroids())
end

-- r.fast_sprint = can_sprint & steroids (running fast enough to clear gaps).
function fast_sprint()
    local cs = has("ab_unlocked") or has("sprint")
    return bool(cs and has_group_steroids())
end

-- r.sr50 = sprint | difficulty("hard"). Kept symmetric with the apworld.
function sr50()
    return bool(sprint() == 1 or logic_hard() == 1)
end

-- ---------- glitched-logic gates ----------

function glitched()
    return bool(has("glitched_logic"))
end

-- All glitch sequences must AND in glitched_logic.
function crouch_jump()
    return bool(has("glitched_logic")
        and (has("ab_unlocked") or has("jump"))
        and (has("ab_unlocked") or has("crouch"))
        and sprint() == 1)
end

function fast_crouch_jump()
    return bool(has("glitched_logic")
        and (has("ab_unlocked") or has("jump"))
        and (has("ab_unlocked") or has("crouch"))
        and (has("ab_unlocked") or has("sprint"))
        and has_group_steroids())
end

function glitch_kick()
    return bool(has("glitched_logic") and (has("int_unlocked") or has("use")))
end

-- ---------- logic-difficulty thresholds ----------
-- Backed by a single progressive item ("Logic Difficulty") with four stages
-- mirroring the apworld option: 0=easy, 1=medium, 2=hard, 3=extreme.
-- loop=true on the item plus Active=true in init.lua and onClear means
-- right-click wraps stage 0 → stage 3 instead of dropping to inactive.

local function logic_stage()
    local obj = Tracker:FindObjectForCode("logic_difficulty")
    if obj and obj.CurrentStage then return obj.CurrentStage end
    return 1  -- medium
end

function logic_easy()    return 1 end                            -- always allowed
function logic_medium()  return bool(logic_stage() >= 1) end
function logic_hard()    return bool(logic_stage() >= 2) end
function logic_extreme() return bool(logic_stage() >= 3) end

-- ---------- boss-kill rules (per rules.py) ----------

local function has_group_rpg()
    return has("rpg") or has("progressive_rpg")
end
local function has_group_devastator()
    return has("devastator") or has("progressive_devastator")
end

function can_kill_boss_1()
    return bool(has_group_rpg())
end

function can_kill_boss_2()
    return bool(has_group_rpg() and has_group_devastator())
end

function can_kill_boss_3()
    -- rpg | devastator | (medium & ((can_jump & sprint) | jetpack(50)))
    if has_group_rpg() or has_group_devastator() then return 1 end
    local cj = has("ab_unlocked") or has("jump")
    return bool(logic_medium() == 1
        and ((cj and sprint() == 1) or has_jetpack_fuel(50) == 1))
end

function can_kill_boss_4()
    -- dive(400) & rpg & devastator
    return bool(can_dive_fuel(400) == 1
        and has_group_rpg() and has_group_devastator())
end
