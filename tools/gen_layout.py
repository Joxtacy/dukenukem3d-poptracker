#!/usr/bin/env python3
"""Generate layouts/tracker.json from level data.

Run after gen_pack_data.py so the codes referenced here exist in items.json.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# (prefix, level_name, keys_in_apworld_order)
LEVELS = [
    ("E1L1", "Hollywood Holocaust", ["Red"]),
    ("E1L2", "Red Light District", ["Blue", "Red", "Yellow"]),
    ("E1L3", "Death Row", ["Blue", "Red", "Yellow"]),
    ("E1L4", "Toxic Dump", ["Blue", "Red"]),
    ("E1L5", "The Abyss", ["Blue"]),
    ("E1L6", "Launch Facility", ["Blue", "Red"]),
    ("E1L7", "Faces of Death", ["Blue"]),
    ("E2L1", "Spaceport", ["Blue", "Red"]),
    ("E2L2", "Incubator", ["Yellow"]),
    ("E2L3", "Warp Factor", ["Blue", "Yellow"]),
    ("E2L4", "Fusion Station", []),
    ("E2L5", "Occupied Territory", ["Blue", "Red"]),
    ("E2L6", "Tiberius Station", ["Blue", "Red"]),
    ("E2L7", "Lunar Reactor", ["Blue", "Red", "Yellow"]),
    ("E2L8", "Dark Side", ["Blue", "Yellow"]),
    ("E2L9", "Overlord", []),
    ("E2L10", "Spin Cycle", []),
    ("E2L11", "Lunatic Fringe", []),
    ("E3L1", "Raw Meat", ["Blue", "Red"]),
    ("E3L2", "Bank Roll", ["Blue", "Red"]),
    ("E3L3", "Flood Zone", ["Blue", "Red", "Yellow"]),
    ("E3L4", "L.A. Rumble", ["Blue", "Red"]),
    ("E3L5", "Movie Set", ["Blue", "Red", "Yellow"]),
    ("E3L6", "Rabid Transit", ["Blue", "Red"]),
    ("E3L7", "Fahrenheit", ["Blue", "Red", "Yellow"]),
    ("E3L8", "Hotel Hell", ["Blue", "Yellow"]),
    ("E3L9", "Stadium", []),
    ("E3L10", "Tier Drops", []),
    ("E3L11", "Freeway", ["Blue", "Red"]),
    ("E4L1", "It's Impossible", ["Blue", "Red"]),
    ("E4L2", "Duke-Burger", ["Blue", "Red"]),
    ("E4L3", "Shop-N-Bag", ["Blue", "Red", "Yellow"]),
    ("E4L4", "Babe Land", ["Red", "Blue"]),
    ("E4L5", "Pigsty", ["Blue", "Red", "Yellow"]),
    ("E4L6", "Going Postal", ["Red", "Blue", "Yellow"]),
    ("E4L7", "XXX-Stacy", ["Red", "Blue"]),
    ("E4L8", "Critical Mass", ["Red", "Blue", "Yellow"]),
    ("E4L9", "Derelict", ["Red", "Blue", "Yellow"]),
    ("E4L10", "The Queen", ["Red", "Blue", "Yellow"]),
    ("E4L11", "Area 51", ["Red", "Blue", "Yellow"]),
]


def status_tab():
    # Weapon order: pistol always first; columns line up across rows so
    # capacity / progressive / ammo for the same weapon share a column.
    WEAPON_ORDER = [
        "pistol", "shotgun", "chaingun", "rpg", "pipebomb",
        "shrinker", "devastator", "tripmine", "freezethrower", "expander",
    ]
    weapon_row = list(WEAPON_ORDER)  # pistol is a static item, always lit
    capacity_row = [f"{w}_capacity" for w in WEAPON_ORDER]
    progressive_row = [f"progressive_{w}" for w in WEAPON_ORDER]
    ammo_row = [f"{w}_ammo" for w in WEAPON_ORDER]

    return {
        "title": "Status",
        "content": {
            "type": "container",
            "background": "#000000",
            "content": {
                "type": "dock",
                "dock_direction": "vertical",
                "content": [
                    {
                        "type": "group",
                        "header": "Weapons (base / capacity / progressive / ammo)",
                        "dock": "top",
                        "content": {
                            "type": "itemgrid",
                            "item_size": 36,
                            "item_margin": 3,
                            "rows": [
                                weapon_row,
                                capacity_row,
                                progressive_row,
                                ammo_row,
                            ],
                        },
                    },
                    {
                        "type": "group",
                        "header": "Inventory",
                        "dock": "top",
                        "content": {
                            "type": "itemgrid",
                            "item_size": 36,
                            "item_margin": 3,
                            "rows": [
                                ["steroids", "scuba_gear", "jetpack",
                                 "holo_duke", "night_vision_goggles",
                                 "first_aid_kit", "protective_boots"],
                                ["steroids_capacity", "scuba_gear_capacity",
                                 "jetpack_capacity", "_", "_", "_", "_"],
                                ["progressive_steroids",
                                 "progressive_scuba_gear",
                                 "progressive_jetpack",
                                 "_", "_", "_", "_"],
                            ],
                        },
                    },
                    {
                        "type": "group",
                        "header": "Armor & Abilities",
                        "dock": "top",
                        "content": {
                            "type": "itemgrid",
                            "item_size": 36,
                            "item_margin": 3,
                            "rows": [
                                ["armor", "sturdy_armor", "heavy_armor", "_",
                                 "jump", "crouch", "sprint", "dive",
                                 "open", "use"],
                            ],
                        },
                    },
                    {
                        "type": "group",
                        "header": "Healing",
                        "dock": "top",
                        "content": {
                            "type": "itemgrid",
                            "item_size": 36,
                            "item_margin": 3,
                            "rows": [
                                ["atomic_health", "plutonium_health",
                                 "uranium_health", "medpak", "bandage",
                                 "pity_heal", "ego_boost", "buff_up"],
                            ],
                        },
                    },
                    {
                        # Logic settings. The apworld currently doesn't
                        # transmit logic_difficulty / glitch_logic in
                        # slot_data, so onClear defaults to medium-no-glitch
                        # and the player adjusts here if their seed differs.
                        # Click `logic_difficulty` to cycle easy → medium →
                        # hard → extreme; right-click `glitched_logic` to
                        # toggle. NOTE: the in-game `skill_level` and the
                        # randomizer pool `difficulty` options have no
                        # effect on tracker access rules — only the two
                        # below do.
                        "type": "group",
                        "header": "Logic settings (click to cycle / right-click to toggle)",
                        "dock": "top",
                        "content": {
                            "type": "itemgrid",
                            "item_size": 40,
                            "item_margin": 4,
                            "rows": [
                                ["logic_difficulty", "glitched_logic"],
                            ],
                        },
                    },
                ],
            },
        },
    }


def episode_tab(ep: int) -> dict:
    ep_levels = [lv for lv in LEVELS if lv[0].startswith(f"E{ep}")]

    # Item rows: one row per level, columns are [unlock, automap, blue, red, yellow]
    rows = []
    for prefix, _, keys in ep_levels:
        cp = prefix.lower()
        row = [f"{cp}_unlock", f"{cp}_automap"]
        for color in ("Blue", "Red", "Yellow"):
            row.append(f"{cp}_{color.lower()}_key" if color in keys else "_")
        rows.append(row)

    map_tabs = []
    for prefix, name, _ in ep_levels:
        cp = prefix.lower()
        map_tabs.append(
            {
                "title": f"{prefix}: {name}",
                "content": {"type": "map", "maps": [f"{cp}_map"]},
            }
        )

    return {
        "title": f"Episode {ep}",
        "content": {
            "type": "container",
            "background": "#000000",
            "content": {
                "type": "dock",
                "content": [
                    {
                        "type": "dock",
                        "dock": "left",
                        "content": [
                            {
                                "type": "group",
                                "header": (
                                    f"Episode {ep} - Levels (Unlock, Automap, "
                                    f"Blue/Red/Yellow Keys)"
                                ),
                                "dock": "top",
                                "content": {
                                    "type": "itemgrid",
                                    "item_size": 36,
                                    "item_margin": 2,
                                    "rows": rows,
                                },
                            }
                        ],
                    },
                    {
                        "type": "dock",
                        "content": {
                            "type": "tabbed",
                            "tabs": map_tabs,
                        },
                    },
                ],
            },
        },
    }


def main():
    layout = {
        "tracker_default": {
            "type": "container",
            "background": "#000000",
            "content": {
                "type": "dock",
                "dock_direction": "vertical",
                "content": [
                    {
                        "type": "group",
                        "header": "Goal",
                        "dock": "top",
                        "content": {
                            "type": "itemgrid",
                            "item_size": 48,
                            "item_margin": 4,
                            "rows": [
                                ["goal_exit", "goal_secret", "goal_boss"]
                            ],
                        },
                    },
                    {
                        "type": "tabbed",
                        "tabs": [
                            status_tab(),
                            episode_tab(1),
                            episode_tab(2),
                            episode_tab(3),
                            episode_tab(4),
                        ],
                    },
                ],
            },
        }
    }

    out = REPO_ROOT / "layouts" / "tracker.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(layout, indent=2) + "\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
