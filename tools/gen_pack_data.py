#!/usr/bin/env python3
"""Generate items.json, locations/eN_locations.json, and scripts/autotracking_data.lua
from the extracted Duke3D apworld.

Usage:
    python3 tools/gen_pack_data.py [--apworld-dir PATH]

Default --apworld-dir is /tmp/duke3d-apworld/extracted/duke3d.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APWORLD = Path("/tmp/duke3d-apworld/extracted/duke3d")

EPISODE_NAMES = {
    1: "L.A. Meltdown",
    2: "Lunar Apocalypse",
    3: "Shrapnel City",
    4: "The Birth",
}

# net_id encoding: 0xB17D0800 | short_id (for short_id < 0x800).
NET_ID_BASE = 0xB17D0800

# Base IDs from items/__init__.py.
AUTOMAP_BASE = 1600
UNLOCK_BASE = 1700
KEYCARD_BASE = 1800

KEY_FLAG_ORDER = ("Blue", "Red", "Yellow")  # iteration order in items/__init__.py


def net_id(short_id: int) -> int:
    return NET_ID_BASE | (short_id & 0x7FF)


@dataclass
class LevelData:
    prefix: str  # "E1L1"
    name: str
    levelnum: int  # 0-indexed
    volumenum: int  # 0-indexed
    keys: list[str] = field(default_factory=list)
    has_boss: bool = False
    must_dive: bool = False
    location_defs: list[dict[str, Any]] = field(default_factory=list)

    @property
    def episode(self) -> int:
        return self.volumenum + 1

    @property
    def level_num_in_ep(self) -> int:
        return self.levelnum + 1

    @property
    def code_prefix(self) -> str:
        return self.prefix.lower()  # "e1l1"


def parse_level_file(path: Path) -> LevelData:
    src = path.read_text()
    tree = ast.parse(src)
    cls = next(
        node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    )
    fields_: dict[str, Any] = {}
    for stmt in cls.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target = stmt.targets[0]
            if isinstance(target, ast.Name):
                try:
                    fields_[target.id] = ast.literal_eval(stmt.value)
                except (ValueError, SyntaxError):
                    pass

    levelnum = fields_["levelnum"]
    volumenum = fields_["volumenum"]
    return LevelData(
        prefix=f"E{volumenum + 1}L{levelnum + 1}",
        name=fields_.get("name", "?"),
        levelnum=levelnum,
        volumenum=volumenum,
        keys=list(fields_.get("keys", [])),
        has_boss=bool(fields_.get("has_boss", False)),
        must_dive=bool(fields_.get("must_dive", False)),
        location_defs=list(fields_.get("location_defs", [])),
    )


def load_levels(apworld_dir: Path) -> list[LevelData]:
    files = sorted((apworld_dir / "levels").glob("e?l*.py"))
    levels = [parse_level_file(p) for p in files if p.name != "__init__.py"]
    levels.sort(key=lambda lv: (lv.volumenum, lv.levelnum))
    return levels


# ---------------------------------------------------------------------------
# Static items table (mirrors duke3d/items/__init__.py — short_ids hardcoded
# rather than imported because Archipelago is not installed locally).
# Each entry: short_id, code, display_name, type, image, optional max_quantity.
# Type aligns with PopTracker item types.
# ---------------------------------------------------------------------------

WEAPONS = [
    # (short_id_weapon, short_id_capacity, short_id_progressive, short_id_ammo,
    #  code_root, display_root)
    (None, 221, 241, 261, "pistol", "Pistol"),
    (202, 222, 242, 262, "shotgun", "Shotgun"),
    (203, 223, 243, 263, "chaingun", "Chaingun"),
    (204, 224, 244, 264, "rpg", "RPG"),
    (205, 225, 245, 265, "pipebomb", "Pipebomb"),
    (206, 226, 246, 266, "shrinker", "Shrinker"),
    (207, 227, 247, 267, "devastator", "Devastator"),
    (208, 228, 248, 268, "tripmine", "Tripmine"),
    (209, 229, 249, 269, "freezethrower", "Freezethrower"),
    (211, 231, 251, 271, "expander", "Expander"),
]

INVENTORY = [
    # (short_id_base, short_id_capacity, short_id_progressive, code_root, display)
    (300, 320, 340, "steroids", "Steroids"),
    (302, 322, 342, "scuba_gear", "Scuba Gear"),
    (304, 324, 344, "jetpack", "Jetpack"),
]

# Standalone inventory items without capacity/progressive variants.
INVENTORY_SOLO = [
    (303, "holo_duke", "Holo Duke", "consumable"),
    (307, "night_vision_goggles", "Night Vision Goggles", "consumable"),
    (309, "first_aid_kit", "First Aid Kit", "consumable"),
    (310, "protective_boots", "Protective Boots", "consumable"),
]

ARMOR = [
    (301, "armor", "Armor", "consumable"),
    (321, "sturdy_armor", "Sturdy Armor", "consumable"),
    (341, "heavy_armor", "Heavy Armor", "consumable"),
]

ABILITIES = [
    (350, "jump", "Jump"),
    (351, "dive", "Dive"),
    (352, "crouch", "Crouch"),
    (353, "sprint", "Sprint"),
    (354, "open", "Open"),
    (355, "use", "Use"),
]

HEALING = [
    (400, "atomic_health", "Atomic Health"),
    (401, "medpak", "Medpak"),
    (402, "bandage", "Bandage"),
    (403, "pity_heal", "Pity Heal"),
    (404, "ego_boost", "Ego Boost"),
    (405, "buff_up", "Buff Up"),
    (406, "plutonium_health", "Plutonium Health"),
    (407, "uranium_health", "Uranium Health"),
]

GOAL_ITEMS = [
    (100, "goal_exit", "Exits"),
    (101, "goal_secret", "Secrets"),
    (102, "goal_boss", "Bosses"),
]


def build_items_json(levels: list[LevelData]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def add(name: str, code: str, type_: str, img: str, *,
            extra: dict[str, Any] | None = None,
            short_id: int | None = None):
        codes = [code]
        if short_id is not None:
            codes.append(f"d3d_{net_id(short_id)}")
        entry: dict[str, Any] = {
            "name": name,
            "type": type_,
            "img": img,
            "codes": ",".join(codes),
        }
        if extra:
            entry.update(extra)
        items.append(entry)

    # --- spacer / placeholder ---
    add("Blank", "_", "static", "images/blank.png")

    # --- hidden setting toggles (driven by onClear from slot_data) ---
    for ep in (1, 2, 3, 4):
        add(f"Episode {ep}", f"ep{ep}", "toggle", "images/blank.png")
    add("Include Secrets", "secrets", "toggle", "images/blank.png")
    add("Unlock Abilities", "ab_locked", "toggle", "images/blank.png")
    add("Unlock Interact", "int_locked", "toggle", "images/blank.png")
    add("Abilities Unlocked", "ab_unlocked", "toggle", "images/blank.png")
    add("Interact Unlocked", "int_unlocked", "toggle", "images/blank.png")
    add("Area Maps Unlockable", "maps_unlockable", "toggle", "images/blank.png")
    add("E1L7 Enabled", "e1l7_enabled", "toggle", "images/blank.png")
    # Logic difficulty: a single progressive item that cycles
    # easy → medium → hard → extreme. logic.lua's $logic_X helpers read
    # the CurrentStage to answer the apworld's `r.difficulty("X")` checks.
    # Surfaced in the layout's Settings group; click to advance, since the
    # apworld doesn't currently transmit logic_difficulty in slot_data.
    # Four stages mirroring the apworld's logic_difficulty option
    # (0=easy, 1=medium, 2=hard, 3=extreme). loop=true so right-click at
    # stage 0 wraps to stage 3 instead of dropping to inactive/greyed.
    # init.lua + onClear keep Active=true so the icon never renders greyed.
    items.append({
        "name": "Logic Difficulty",
        "type": "progressive",
        "img": "images/logic_medium.png",
        "codes": "logic_difficulty",
        "loop": True,
        "stages": [
            {"img": "images/logic_easy.png",    "codes": "logic_difficulty"},
            {"img": "images/logic_medium.png",  "codes": "logic_difficulty"},
            {"img": "images/logic_hard.png",    "codes": "logic_difficulty"},
            {"img": "images/logic_extreme.png", "codes": "logic_difficulty"},
        ],
    })
    add("Glitched Logic", "glitched_logic", "toggle", "images/glitched_logic.png")

    # --- goal counters (consumables, max set dynamically in onClear) ---
    for sid, code, display in GOAL_ITEMS:
        add(
            display,
            code,
            "consumable",
            f"images/{code}.png",
            extra={"max_quantity": 99, "increment": 1, "initial_quantity": 0},
            short_id=sid,
        )

    # --- weapons + capacity + progressive + ammo ---
    for w in WEAPONS:
        weapon_id, cap_id, prog_id, ammo_id, root, display = w
        if weapon_id is not None:
            add(display, root, "toggle", f"images/{root}.png", short_id=weapon_id)
        else:
            # Pistol: no AP item (Duke starts with it). Render as a static
            # always-on icon so the weapons row column doesn't have a gap.
            add(display, root, "static", f"images/{root}.png")
        add(
            f"{display} Capacity",
            f"{root}_capacity",
            "consumable",
            f"images/{root}.png",
            extra={"max_quantity": 10, "increment": 1, "initial_quantity": 0},
            short_id=cap_id,
        )
        add(
            f"Progressive {display}",
            f"progressive_{root}",
            "progressive",
            f"images/{root}.png",
            short_id=prog_id,
        )
        add(
            f"{display} Ammo",
            f"{root}_ammo",
            "consumable",
            f"images/{root}_ammo.png",
            extra={"max_quantity": 99, "increment": 1, "initial_quantity": 0},
            short_id=ammo_id,
        )

    # --- inventory with capacity/progressive variants ---
    for base_id, cap_id, prog_id, root, display in INVENTORY:
        add(display, root, "toggle", f"images/{root}.png", short_id=base_id)
        add(
            f"{display} Capacity",
            f"{root}_capacity",
            "consumable",
            f"images/{root}.png",
            extra={"max_quantity": 10, "increment": 1, "initial_quantity": 0},
            short_id=cap_id,
        )
        add(
            f"Progressive {display}",
            f"progressive_{root}",
            "progressive",
            f"images/{root}.png",
            short_id=prog_id,
        )

    # --- standalone inventory ---
    for sid, code, display, _ in INVENTORY_SOLO:
        add(
            display,
            code,
            "consumable",
            f"images/{code}.png",
            extra={"max_quantity": 99, "increment": 1, "initial_quantity": 0},
            short_id=sid,
        )

    # --- armor ---
    for sid, code, display, _ in ARMOR:
        add(
            display,
            code,
            "consumable",
            f"images/{code}.png",
            extra={"max_quantity": 10, "increment": 1, "initial_quantity": 0},
            short_id=sid,
        )

    # --- abilities ---
    for sid, code, display in ABILITIES:
        add(display, code, "toggle", f"images/{code}.png", short_id=sid)

    # --- healing (consumables) ---
    for sid, code, display in HEALING:
        add(
            display,
            code,
            "consumable",
            f"images/{code}.png",
            extra={"max_quantity": 99, "increment": 1, "initial_quantity": 0},
            short_id=sid,
        )

    # --- per-level items (Unlock, Automap, Key Cards) ---
    automap_id = AUTOMAP_BASE
    unlock_id = UNLOCK_BASE
    keycard_id = KEYCARD_BASE
    for level in levels:
        cp = level.code_prefix
        add(
            f"{level.prefix} Automap",
            f"{cp}_automap",
            "toggle",
            "images/automap.png",
            short_id=automap_id,
        )
        automap_id += 1

        add(
            f"{level.prefix} Unlock",
            f"{cp}_unlock",
            "toggle",
            "images/unlock.png",
            short_id=unlock_id,
        )
        unlock_id += 1

        for color in KEY_FLAG_ORDER:
            if color in level.keys:
                add(
                    f"{level.prefix} {color} Key Card",
                    f"{cp}_{color.lower()}_key",
                    "toggle",
                    f"images/key_{color.lower()}.png",
                    short_id=keycard_id,
                )
                keycard_id += 1

    return items


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def load_map_pins(repo_root: Path) -> dict[str, dict[str, list[int]]]:
    """Read tools/map_pins.json if present, else return empty dict."""
    p = repo_root / "tools" / "map_pins.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def load_level_rules(apworld_dir: Path) -> dict[str, dict[str, list[str]]]:
    """Use parse_level_logic to compute per-location access_rules from each
    level's region graph. Returns {prefix: {loc_name: [rule_string, ...]}}."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from parse_level_logic import compute_all_level_rules
    return compute_all_level_rules(apworld_dir)


# Heuristic: location names that strongly indicate gating by a colored key
# card. Two patterns:
#   1) "<Color> <Keyword>" where Keyword is a noun for a colored door / room
#      (e.g. "Blue Door Tripmine 1", "Red Storage Holo Duke")
#   2) "near <Color> Door" / "near <Color> Gate" — proximity to a colored
#      access barrier (e.g. "MP Chaingun near Red Door")
# Excludes "<Color> Key Card" (the card itself), descriptive uses
# ("<Color> Waterfall", "<Color> Vent", "<Color> Fruit"), and ambiguous
# bare adjectives ("Red Medkit"). See ROADMAP for the full v0.3 path.
KEY_GATE_PATTERNS = re.compile(
    r"\b(Red|Blue|Yellow)\s+"
    r"(Door|Room|Gate|Basement|Storage|Boat|Auction|Cashier)\b"
    r"|\bnear\s+(Red|Blue|Yellow)\s+(Door|Gate)\b",
    re.IGNORECASE,
)


def detect_key_gates(name: str) -> set[str]:
    """Return the lowercase colour names ('red'/'blue'/'yellow') that gate
    this location based on the heuristic. Empty set means no gate."""
    if "Key Card" in name:
        return set()
    colors: set[str] = set()
    for m in KEY_GATE_PATTERNS.finditer(name):
        c = m.group(1) or m.group(3)
        if c:
            colors.add(c.lower())
    return colors


def build_episode_locations(
    levels: list[LevelData], episode: int,
    pins: dict[str, dict[str, list[int]]] | None = None,
    level_rules: dict[str, dict[str, list[str]]] | None = None,
) -> list[dict[str, Any]]:
    """Build the locations JSON for a single episode.

    Structure mirrors keen{N}_locations.json: a single top-level group named
    "Episode N: <Name>" with one child per level; each child has a single
    map_locations entry pointing to the per-level stub map and sections
    (Exit, Secret-*, sprite picks) gated by access_rules.
    """
    # Three-layer structure (group → level → location → section). The pin
    # lives on the location (grandchild) so each sprite/secret renders its
    # own marker on the level map. PopTracker silently ignores map_locations
    # on leaf sections; it has to be on a container.
    children = []
    ep_levels = [lv for lv in levels if lv.episode == episode]
    for level in ep_levels:
        cp = level.code_prefix
        map_name = f"{cp}_map"
        level_pins = (pins or {}).get(level.prefix, {})
        loc_children: list[dict[str, Any]] = []

        # Build access-rule prefix for this level: epN, level_unlock.
        base_rule = f"ep{episode},{cp}_unlock"
        if level.episode == 1 and level.levelnum == 6:
            base_rule = f"ep1,e1l7_enabled,{cp}_unlock"

        level_key_codes = {k.lower() for k in level.keys}
        computed = (level_rules or {}).get(level.prefix, {})
        for loc in level.location_defs:
            loc_name: str = loc["name"]
            loc_type: str = loc["type"]

            if loc_type == "sector":
                # Sector secrets carry the include_secrets gate on top of
                # whatever the region graph requires.
                slot_prefix = f"{base_rule},secrets"
            else:
                slot_prefix = base_rule

            # Prefer the AST-computed region-graph rules; fall back to the
            # v0.2 heuristic for the ~20 locations parse_level_logic doesn't
            # currently catch.
            comp_alts = computed.get(loc_name)
            if comp_alts is None:
                gate_colours = detect_key_gates(loc_name) & level_key_codes
                if gate_colours:
                    extra = ",".join(
                        f"{cp}_{c}_key" for c in sorted(gate_colours)
                    )
                    rule_alts = [f"{slot_prefix},{extra}"]
                else:
                    rule_alts = [slot_prefix]
            else:
                # Combine the slot prefix with each computed alternative.
                # Empty string from compute means "always reachable past
                # the slot prefix", so just use the prefix alone.
                rule_alts = []
                for alt in comp_alts:
                    if alt:
                        rule_alts.append(f"{slot_prefix},{alt}")
                    else:
                        rule_alts.append(slot_prefix)
                if not rule_alts:
                    # FALSE per the parser; encode as a never-satisfied rule
                    # so the section visibly stays unreachable.
                    rule_alts = [f"{slot_prefix},__never__"]

            pin = level_pins.get(loc_name, [100, 100])
            loc_children.append(
                {
                    "name": loc_name,
                    "map_locations": [
                        {"map": map_name, "x": pin[0], "y": pin[1]}
                    ],
                    "sections": [
                        {
                            # Section name matches the location name so the
                            # PopTracker path used by autotracking is
                            # "<group>/<level>/<loc>/<loc>".
                            "name": loc_name,
                            "item_count": 1,
                            "access_rules": rule_alts,
                        }
                    ],
                }
            )

        children.append(
            {
                "name": f"{level.prefix}: {level.name}",
                "access_rules": [base_rule],
                "children": loc_children,
            }
        )

    return [
        {
            "name": f"Episode {episode}: {EPISODE_NAMES[episode]}",
            "children": children,
        }
    ]


def build_episode_maps(
    levels: list[LevelData], episode: int
) -> list[dict[str, Any]]:
    """Per-level map stubs for one episode. v0.1 uses a single placeholder
    image for every level; per-level top-down screenshots are backfilled
    later."""
    maps: list[dict[str, Any]] = []
    for level in (lv for lv in levels if lv.episode == episode):
        cp = level.code_prefix
        maps.append(
            {
                "name": f"{cp}_map",
                "img": f"images/{cp}_map.png",
                "location_size": 14,
                "location_border_thickness": 2,
            }
        )
    return maps


def lua_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_autotracking_data_lua(
    levels: list[LevelData], id_map: dict[str, Any]
) -> str:
    """Emit ITEM_MAP and LOCATION_MAP Lua tables for autotracking.lua."""
    level_path: dict[str, str] = {
        lv.prefix: f"Episode {lv.episode}: {EPISODE_NAMES[lv.episode]}/{lv.prefix}: {lv.name}"
        for lv in levels
    }

    lines: list[str] = []
    lines.append("-- AUTO-GENERATED by tools/gen_pack_data.py — do not edit by hand.")
    lines.append("-- Re-run codegen after bumping the apworld version.")
    lines.append("")
    lines.append("ITEM_MAP = {}")
    lines.append("LOCATION_MAP = {}")
    lines.append("")

    def emit_item(short_id: int, code: str, comment: str = ""):
        c = f"  -- {comment}" if comment else ""
        lines.append(f"ITEM_MAP[{net_id(short_id)}] = \"{code}\"{c}")

    # goal items
    for sid, code, _ in GOAL_ITEMS:
        emit_item(sid, code)

    # weapons
    for w in WEAPONS:
        weapon_id, cap_id, prog_id, ammo_id, root, _ = w
        if weapon_id is not None:
            emit_item(weapon_id, root)
        emit_item(cap_id, f"{root}_capacity")
        emit_item(prog_id, f"progressive_{root}")
        emit_item(ammo_id, f"{root}_ammo")

    # inventory
    for base_id, cap_id, prog_id, root, _ in INVENTORY:
        emit_item(base_id, root)
        emit_item(cap_id, f"{root}_capacity")
        emit_item(prog_id, f"progressive_{root}")
    for sid, code, _, _ in INVENTORY_SOLO:
        emit_item(sid, code)
    for sid, code, _, _ in ARMOR:
        emit_item(sid, code)

    # abilities
    for sid, code, _ in ABILITIES:
        emit_item(sid, code)

    # healing
    for sid, code, _ in HEALING:
        emit_item(sid, code)

    # per-level items
    automap_id = AUTOMAP_BASE
    unlock_id = UNLOCK_BASE
    keycard_id = KEYCARD_BASE
    lines.append("")
    lines.append("-- per-level items")
    for level in levels:
        cp = level.code_prefix
        emit_item(automap_id, f"{cp}_automap", f"{level.prefix} Automap")
        automap_id += 1
        emit_item(unlock_id, f"{cp}_unlock", f"{level.prefix} Unlock")
        unlock_id += 1
        for color in KEY_FLAG_ORDER:
            if color in level.keys:
                emit_item(
                    keycard_id,
                    f"{cp}_{color.lower()}_key",
                    f"{level.prefix} {color} Key Card",
                )
                keycard_id += 1

    # Build LOCATION_MAP from id_map.json. Path matches the JSON tree:
    #   "Episode N: Name/EXLY: Level/<Location>/<Location>"
    # i.e. group/level-child/location-grandchild/section, with the section
    # name reusing the location name (see build_episode_locations).
    lines.append("")
    lines.append("-- per-location paths, derived from apworld id_map.json")
    locations_with_secrets: list[str] = []
    for loc_name, short_id in id_map.get("locations", {}).items():
        # loc_name like "E1L1 Bachelor RPG" / "E1L1 Exit" / "E1L1 Secret Behind ..."
        prefix, _, section = loc_name.partition(" ")
        if not prefix or not section or prefix not in level_path:
            continue
        path = f"{level_path[prefix]}/{section}/{section}"
        lines.append(f"LOCATION_MAP[{net_id(short_id)}] = {lua_str(path)}")
        if section.startswith("Secret "):
            locations_with_secrets.append(prefix)

    # LEVEL_PATH: prefix -> "Ep group/Level child" (used to resolve unknown sections).
    lines.append("")
    lines.append("LEVEL_PATH = {}")
    for prefix, path in level_path.items():
        lines.append(f"LEVEL_PATH[{lua_str(prefix)}] = {lua_str(path)}")

    # Per-episode lookup used to derive ep1..4 toggles from active levels.
    lines.append("")
    lines.append("LEVEL_TO_EPISODE = {}")
    for level in levels:
        lines.append(f"LEVEL_TO_EPISODE[{lua_str(level.prefix)}] = {level.episode}")

    # Net IDs of the level Unlock items, by prefix. Used to read slot_data['levels']
    # and figure out which episodes/levels are active.
    lines.append("")
    lines.append("UNLOCK_ID_TO_PREFIX = {}")
    unlock_id = UNLOCK_BASE
    for level in levels:
        lines.append(
            f"UNLOCK_ID_TO_PREFIX[{net_id(unlock_id)}] = {lua_str(level.prefix)}"
        )
        unlock_id += 1

    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apworld-dir", type=Path, default=DEFAULT_APWORLD)
    parser.add_argument("--out", type=Path, default=REPO_ROOT)
    args = parser.parse_args()

    apworld_dir: Path = args.apworld_dir
    out: Path = args.out

    if not apworld_dir.exists():
        print(f"apworld dir not found: {apworld_dir}", file=sys.stderr)
        sys.exit(1)

    levels = load_levels(apworld_dir)
    print(f"Parsed {len(levels)} levels.")

    map_pins = load_map_pins(out)
    if map_pins:
        n = sum(len(v) for v in map_pins.values())
        print(f"Loaded {n} pin coordinates from tools/map_pins.json")
    else:
        print("No tools/map_pins.json found; pins will all be (100, 100). "
              "Run tools/gen_maps.py first if you want real coordinates.")

    print("Computing per-location access rules from apworld region graph...")
    level_rules = load_level_rules(apworld_dir)
    n_rules = sum(len(v) for v in level_rules.values())
    print(f"Computed rules for {n_rules} locations across {len(level_rules)} levels.")

    id_map_path = apworld_dir / "resources" / "id_map.json"
    id_map = json.loads(id_map_path.read_text())
    print(
        f"Loaded id_map.json: {len(id_map['items'])} items, "
        f"{len(id_map['locations'])} locations."
    )

    # items.json
    items = build_items_json(levels)
    items_path = out / "items" / "items.json"
    items_path.parent.mkdir(parents=True, exist_ok=True)
    items_path.write_text(json.dumps(items, indent=2) + "\n")
    print(f"Wrote {items_path} ({len(items)} entries).")

    # locations/eN_locations.json + maps/eN_maps.json
    for ep in (1, 2, 3, 4):
        loc_data = build_episode_locations(levels, ep, pins=map_pins,
                                           level_rules=level_rules)
        loc_path = out / "locations" / f"e{ep}_locations.json"
        loc_path.parent.mkdir(parents=True, exist_ok=True)
        loc_path.write_text(json.dumps(loc_data, indent=2) + "\n")
        sections = sum(
            len(loc_child["sections"])
            for group in loc_data
            for level_child in group["children"]
            for loc_child in level_child.get("children", [])
        )
        print(f"Wrote {loc_path} ({sections} sections).")

        map_data = build_episode_maps(levels, ep)
        map_path = out / "maps" / f"e{ep}_maps.json"
        map_path.parent.mkdir(parents=True, exist_ok=True)
        map_path.write_text(json.dumps(map_data, indent=2) + "\n")
        print(f"Wrote {map_path} ({len(map_data)} maps).")

    # scripts/autotracking_data.lua
    lua_path = out / "scripts" / "autotracking_data.lua"
    lua_path.parent.mkdir(parents=True, exist_ok=True)
    lua_path.write_text(build_autotracking_data_lua(levels, id_map))
    print(f"Wrote {lua_path}.")


if __name__ == "__main__":
    main()
