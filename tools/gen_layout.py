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
                        "header": "Weapons",
                        "dock": "top",
                        "content": {
                            "type": "itemgrid",
                            "item_size": 40,
                            "item_margin": 3,
                            "rows": [
                                ["shotgun", "chaingun", "rpg", "pipebomb",
                                 "shrinker", "devastator", "tripmine",
                                 "freezethrower", "expander"],
                                ["shotgun_capacity", "chaingun_capacity",
                                 "rpg_capacity", "pipebomb_capacity",
                                 "shrinker_capacity", "devastator_capacity",
                                 "tripmine_capacity", "freezethrower_capacity",
                                 "expander_capacity"],
                            ],
                        },
                    },
                    {
                        "type": "group",
                        "header": "Inventory",
                        "dock": "top",
                        "content": {
                            "type": "itemgrid",
                            "item_size": 40,
                            "item_margin": 3,
                            "rows": [
                                ["steroids", "scuba_gear", "jetpack",
                                 "holo_duke", "night_vision_goggles",
                                 "first_aid_kit", "protective_boots"],
                                ["steroids_capacity", "scuba_gear_capacity",
                                 "jetpack_capacity", "armor", "sturdy_armor",
                                 "heavy_armor", "_"],
                            ],
                        },
                    },
                    {
                        "type": "group",
                        "header": "Abilities",
                        "dock": "top",
                        "content": {
                            "type": "itemgrid",
                            "item_size": 40,
                            "item_margin": 3,
                            "rows": [
                                ["jump", "crouch", "sprint", "dive",
                                 "open", "use"],
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
