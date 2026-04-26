#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10"]
# ///
"""Generate visually distinct placeholder PNGs for every icon and map referenced
by items.json + maps/eN_maps.json.

Each icon is a flat-colored 64x64 square with a 2-3 line label. Each map is a
512x384 rectangle labeled with the level prefix + name. This is enough for the
user to verify autotracking visually before sourcing real Duke 3D sprites.
"""
from __future__ import annotations

import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGES = REPO_ROOT / "images"
IMAGES.mkdir(exist_ok=True)

ICON_SIZE = (64, 64)
MAP_SIZE = (512, 384)

# Color palette (background, foreground) per item category.
PALETTE = {
    "weapon":     ((140, 28, 28),  (255, 255, 255)),  # dark red
    "ammo":       ((180, 80, 30),  (255, 240, 200)),  # orange
    "inventory":  ((30, 90, 140),  (255, 255, 255)),  # blue
    "armor":      ((90, 90, 110),  (240, 240, 240)),  # slate
    "ability":    ((50, 130, 50),  (255, 255, 255)),  # green
    "interact":   ((90, 130, 50),  (255, 255, 255)),  # olive
    "healing":    ((180, 50, 100), (255, 255, 255)),  # pink
    "automap":    ((40, 40, 60),   (200, 220, 255)),  # navy
    "unlock":     ((90, 70, 30),   (255, 220, 130)),  # bronze
    "key_blue":   ((30, 80, 200),  (255, 255, 255)),
    "key_red":    ((200, 30, 30),  (255, 255, 255)),
    "key_yellow": ((220, 200, 30), (40, 40, 40)),
    "goal_exit":  ((20, 120, 60),  (255, 255, 255)),  # green
    "goal_secret":((140, 60, 180), (255, 255, 255)),  # purple
    "goal_boss":  ((180, 30, 30),  (255, 255, 255)),  # blood red
    "map":        ((20, 20, 20),   (200, 200, 200)),
}

# (filename, label, palette key)
ICONS: list[tuple[str, str, str]] = [
    # Goal counters
    ("goal_exit.png",    "EXIT",   "goal_exit"),
    ("goal_secret.png",  "SECRET", "goal_secret"),
    ("goal_boss.png",    "BOSS",   "goal_boss"),

    # Weapons (no pistol icon needed: only pistol_ammo/capacity exist).
    ("pistol.png",         "PIST",  "weapon"),
    ("shotgun.png",        "SHOT",  "weapon"),
    ("chaingun.png",       "CHAIN", "weapon"),
    ("rpg.png",            "RPG",   "weapon"),
    ("pipebomb.png",       "PIPE",  "weapon"),
    ("shrinker.png",       "SHRNK", "weapon"),
    ("devastator.png",     "DEVS",  "weapon"),
    ("tripmine.png",       "TRIP",  "weapon"),
    ("freezethrower.png",  "FREEZ", "weapon"),
    ("expander.png",       "EXPND", "weapon"),

    # Weapon ammo (visually similar, slightly different tint via 'ammo' palette).
    ("pistol_ammo.png",        "PIST\nAMMO",  "ammo"),
    ("shotgun_ammo.png",       "SHOT\nAMMO",  "ammo"),
    ("chaingun_ammo.png",      "CHAIN\nAMMO", "ammo"),
    ("rpg_ammo.png",           "RPG\nAMMO",   "ammo"),
    ("pipebomb_ammo.png",      "PIPE\nAMMO",  "ammo"),
    ("shrinker_ammo.png",      "SHRNK\nAMMO", "ammo"),
    ("devastator_ammo.png",    "DEVS\nAMMO",  "ammo"),
    ("tripmine_ammo.png",      "TRIP\nAMMO",  "ammo"),
    ("freezethrower_ammo.png", "FREEZ\nAMMO", "ammo"),
    ("expander_ammo.png",      "EXPND\nAMMO", "ammo"),

    # Inventory
    ("steroids.png",             "STR",  "inventory"),
    ("scuba_gear.png",           "SCUBA","inventory"),
    ("jetpack.png",              "JET",  "inventory"),
    ("holo_duke.png",            "HOLO", "inventory"),
    ("night_vision_goggles.png", "NVG",  "inventory"),
    ("first_aid_kit.png",        "FAK",  "healing"),
    ("protective_boots.png",     "BOOT", "inventory"),

    # Armor
    ("armor.png",          "ARM",   "armor"),
    ("sturdy_armor.png",   "ARM+",  "armor"),
    ("heavy_armor.png",    "ARM++", "armor"),

    # Abilities
    ("jump.png",   "JUMP",   "ability"),
    ("dive.png",   "DIVE",   "ability"),
    ("crouch.png", "CRCH",   "ability"),
    ("sprint.png", "RUN",    "ability"),
    ("open.png",   "OPEN",   "interact"),
    ("use.png",    "USE",    "interact"),

    # Healing (consumables)
    ("atomic_health.png",    "ATOM",  "healing"),
    ("medpak.png",           "MED",   "healing"),
    ("bandage.png",          "BAND",  "healing"),
    ("pity_heal.png",        "PITY",  "healing"),
    ("ego_boost.png",        "EGO+",  "healing"),
    ("buff_up.png",          "BUFF",  "healing"),
    ("plutonium_health.png", "PLUT",  "healing"),
    ("uranium_health.png",   "URAN",  "healing"),

    # Per-level shared icons
    ("automap.png", "MAP",    "automap"),
    ("unlock.png",  "UNLK",   "unlock"),

    # Key cards
    ("key_blue.png",   "BLUE\nKEY",   "key_blue"),
    ("key_red.png",    "RED\nKEY",    "key_red"),
    ("key_yellow.png", "YELLOW\nKEY", "key_yellow"),
]


def find_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_icon(filename: str, label: str, palette_key: str):
    bg, fg = PALETTE[palette_key]
    img = Image.new("RGBA", ICON_SIZE, bg + (255,))
    draw = ImageDraw.Draw(img)

    # Border
    draw.rectangle([0, 0, ICON_SIZE[0] - 1, ICON_SIZE[1] - 1], outline=(255, 255, 255), width=1)

    lines = label.split("\n")
    # Pick font size based on longest line and number of lines
    longest = max(len(l) for l in lines)
    if len(lines) == 1:
        size = max(10, min(28, int(ICON_SIZE[0] / max(longest, 1) * 1.4)))
    else:
        size = max(8, min(20, int(ICON_SIZE[1] / (len(lines) + 0.5) * 0.85)))
    font = find_font(size)

    # Measure each line
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))
    total_h = sum(h for _, h in line_heights) + 2 * (len(lines) - 1)
    y = (ICON_SIZE[1] - total_h) // 2
    for line, (lw, lh) in zip(lines, line_heights):
        x = (ICON_SIZE[0] - lw) // 2
        draw.text((x, y), line, font=font, fill=fg + (255,))
        y += lh + 2

    img.save(IMAGES / filename, optimize=True)


def render_map(filename: str, prefix: str, name: str):
    bg, fg = PALETTE["map"]
    img = Image.new("RGBA", MAP_SIZE, bg + (255,))
    draw = ImageDraw.Draw(img)
    draw.rectangle(
        [0, 0, MAP_SIZE[0] - 1, MAP_SIZE[1] - 1],
        outline=(80, 80, 80), width=2,
    )
    title_font = find_font(54)
    sub_font = find_font(28)

    bbox = draw.textbbox((0, 0), prefix, font=title_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((MAP_SIZE[0] - tw) // 2, MAP_SIZE[1] // 2 - th),
        prefix, font=title_font, fill=fg + (255,),
    )
    bbox = draw.textbbox((0, 0), name, font=sub_font)
    sw, sh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((MAP_SIZE[0] - sw) // 2, MAP_SIZE[1] // 2 + 10),
        name, font=sub_font, fill=(180, 180, 180, 255),
    )
    draw.text(
        (10, 10),
        "(stub map — replace with top-down)",
        font=find_font(14), fill=(120, 120, 120, 255),
    )
    img.save(IMAGES / filename, optimize=True)


# Levels list for map placeholders (mirrors gen_layout.LEVELS)
LEVELS: list[tuple[str, str]] = [
    ("E1L1", "Hollywood Holocaust"), ("E1L2", "Red Light District"),
    ("E1L3", "Death Row"), ("E1L4", "Toxic Dump"),
    ("E1L5", "The Abyss"), ("E1L6", "Launch Facility"),
    ("E1L7", "Faces of Death"),
    ("E2L1", "Spaceport"), ("E2L2", "Incubator"),
    ("E2L3", "Warp Factor"), ("E2L4", "Fusion Station"),
    ("E2L5", "Occupied Territory"), ("E2L6", "Tiberius Station"),
    ("E2L7", "Lunar Reactor"), ("E2L8", "Dark Side"),
    ("E2L9", "Overlord"), ("E2L10", "Spin Cycle"),
    ("E2L11", "Lunatic Fringe"),
    ("E3L1", "Raw Meat"), ("E3L2", "Bank Roll"),
    ("E3L3", "Flood Zone"), ("E3L4", "L.A. Rumble"),
    ("E3L5", "Movie Set"), ("E3L6", "Rabid Transit"),
    ("E3L7", "Fahrenheit"), ("E3L8", "Hotel Hell"),
    ("E3L9", "Stadium"), ("E3L10", "Tier Drops"),
    ("E3L11", "Freeway"),
    ("E4L1", "It's Impossible"), ("E4L2", "Duke-Burger"),
    ("E4L3", "Shop-N-Bag"), ("E4L4", "Babe Land"),
    ("E4L5", "Pigsty"), ("E4L6", "Going Postal"),
    ("E4L7", "XXX-Stacy"), ("E4L8", "Critical Mass"),
    ("E4L9", "Derelict"), ("E4L10", "The Queen"),
    ("E4L11", "Area 51"),
]


def main():
    for filename, label, palette_key in ICONS:
        render_icon(filename, label, palette_key)
    print(f"Wrote {len(ICONS)} item icons.")

    for prefix, name in LEVELS:
        render_map(f"{prefix.lower()}_map.png", prefix, name)
    print(f"Wrote {len(LEVELS)} map placeholders.")


if __name__ == "__main__":
    main()
