-- logic.lua: small helpers for access rules.
-- Most rules are expressed as comma-separated codes inside the JSON
-- access_rules; this file is a placeholder for future Lua-side helpers.

function has(code)
    return Tracker:ProviderCountForCode(code) > 0
end
