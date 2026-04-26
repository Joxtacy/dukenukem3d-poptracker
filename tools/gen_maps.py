#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10"]
# ///
"""Render per-level top-down map PNGs from duke3d.grp and extract pin
coordinates for every sprite/sector location.

Reads:
  - duke3d.grp (Atomic Edition; --grp <path>) — contains all 40 .MAP files
  - The extracted apworld at /tmp/duke3d-apworld/extracted/duke3d (for level
    metadata; --apworld-dir overrides)

Writes:
  - images/eXlY_map.png × 40   — vector top-down renders
  - tools/map_pins.json        — { "E1L1": { "Bachelor RPG": [px, py], ... } }

`gen_pack_data.py` reads `map_pins.json` if present and uses the coordinates
when emitting `locations/eN_locations.json`. If it's missing, all pins fall
back to (100, 100) like before.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
from gen_pack_data import load_levels  # noqa: E402

# BUILD .MAP v7 record sizes (bytes)
SECTOR_SIZE = 40
WALL_SIZE = 32
SPRITE_SIZE = 44

RENDER_SIZE = (1024, 768)
PAD_RATIO = 0.04
DEFAULT_GRP = Path.home() / "Documents" / "Duke3D" / "duke3d.grp"


# ---------------------------------------------------------------------------
# GRP parsing (Ken Silverman's archive format)
# ---------------------------------------------------------------------------

def parse_grp(grp_path: Path) -> dict[str, bytes]:
    data = grp_path.read_bytes()
    if data[:12] != b"KenSilverman":
        raise ValueError(f"Not a KenSilverman GRP file: {grp_path}")
    (numfiles,) = struct.unpack_from("<I", data, 12)
    table_start = 16
    file_offset = table_start + numfiles * 16
    files: dict[str, bytes] = {}
    for i in range(numfiles):
        entry = table_start + i * 16
        name_bytes = data[entry:entry + 12]
        (size,) = struct.unpack_from("<I", data, entry + 12)
        name = name_bytes.rstrip(b"\x00 ").decode("ascii", errors="replace").upper()
        files[name] = data[file_offset:file_offset + size]
        file_offset += size
    return files


# ---------------------------------------------------------------------------
# .MAP parsing — only fields we need
# ---------------------------------------------------------------------------

def parse_map(data: bytes) -> dict:
    pos = 0
    (mapversion,) = struct.unpack_from("<I", data, pos); pos += 4
    if mapversion != 7:
        # Duke3D Atomic uses 7. Older / newer ports may differ; warn but try.
        print(f"  WARNING: unexpected map version {mapversion}", file=sys.stderr)
    pos += 12  # posx, posy, posz
    pos += 4   # ang, cursectnum

    (numsectors,) = struct.unpack_from("<H", data, pos); pos += 2
    sectors = []
    for _ in range(numsectors):
        wallptr, wallnum = struct.unpack_from("<HH", data, pos)
        sectors.append({"wallptr": wallptr, "wallnum": wallnum})
        pos += SECTOR_SIZE

    (numwalls,) = struct.unpack_from("<H", data, pos); pos += 2
    walls = []
    for _ in range(numwalls):
        x, y = struct.unpack_from("<ii", data, pos)
        (point2,) = struct.unpack_from("<H", data, pos + 8)
        walls.append({"x": x, "y": y, "point2": point2})
        pos += WALL_SIZE

    (numsprites,) = struct.unpack_from("<H", data, pos); pos += 2
    sprites = []
    for _ in range(numsprites):
        x, y, z = struct.unpack_from("<iii", data, pos)
        sprites.append({"x": x, "y": y, "z": z})
        pos += SPRITE_SIZE

    return {"sectors": sectors, "walls": walls, "sprites": sprites}


# ---------------------------------------------------------------------------
# Coordinate transform
# ---------------------------------------------------------------------------

def compute_bbox(walls: list[dict]) -> tuple[int, int, int, int]:
    if not walls:
        return (0, 0, 1, 1)
    xs = [w["x"] for w in walls]
    ys = [w["y"] for w in walls]
    return (min(xs), min(ys), max(xs), max(ys))


def world_to_pixel(x: int, y: int, bbox, size, pad):
    minx, miny, maxx, maxy = bbox
    bw = max(maxx - minx, 1)
    bh = max(maxy - miny, 1)
    # aspect-preserving fit with padding
    inner_w = size[0] * (1 - 2 * pad)
    inner_h = size[1] * (1 - 2 * pad)
    scale = min(inner_w / bw, inner_h / bh)
    px = (x - minx) * scale + (size[0] - bw * scale) / 2
    py = (y - miny) * scale + (size[1] - bh * scale) / 2
    return (px, py)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

BG = (18, 18, 26)
WALL_COLOR = (190, 190, 220)
SPRITE_COLOR = (255, 200, 80)
SECTOR_PIN = (120, 220, 255)


def render_map(parsed: dict, size=RENDER_SIZE, pad=PAD_RATIO) -> Image.Image:
    bbox = compute_bbox(parsed["walls"])
    img = Image.new("RGB", size, BG)
    draw = ImageDraw.Draw(img)
    walls = parsed["walls"]
    for w in walls:
        p2 = w["point2"]
        if p2 >= len(walls):
            continue
        w2 = walls[p2]
        a = world_to_pixel(w["x"], w["y"], bbox, size, pad)
        b = world_to_pixel(w2["x"], w2["y"], bbox, size, pad)
        draw.line([a, b], fill=WALL_COLOR, width=2)
    return img


# ---------------------------------------------------------------------------
# Pin extraction
# ---------------------------------------------------------------------------

def sector_centroid(sector_idx: int, parsed: dict) -> tuple[float, float] | None:
    if sector_idx >= len(parsed["sectors"]):
        return None
    s = parsed["sectors"][sector_idx]
    wp, wn = s["wallptr"], s["wallnum"]
    if wp + wn > len(parsed["walls"]) or wn == 0:
        return None
    xs = [parsed["walls"][i]["x"] for i in range(wp, wp + wn)]
    ys = [parsed["walls"][i]["y"] for i in range(wp, wp + wn)]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def extract_pins(level, parsed: dict, size=RENDER_SIZE, pad=PAD_RATIO) -> dict:
    bbox = compute_bbox(parsed["walls"])
    pins: dict[str, list[int]] = {}
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2  # fallback: center

    for loc in level.location_defs:
        loc_name = loc["name"]
        loc_type = loc["type"]
        loc_id = loc["id"]

        wx, wy = None, None
        if loc_type == "sprite":
            if loc_id < len(parsed["sprites"]):
                sp = parsed["sprites"][loc_id]
                wx, wy = sp["x"], sp["y"]
        elif loc_type == "sector":
            c = sector_centroid(loc_id, parsed)
            if c is not None:
                wx, wy = c
        elif loc_type == "exit":
            # Exit's `id` is a lotag, not a sprite/sector index. We don't
            # try to disambiguate — the user clicks the section panel,
            # and we drop a pin at the bbox center as a soft hint.
            wx, wy = cx, cy

        if wx is None:
            wx, wy = cx, cy
        px, py = world_to_pixel(wx, wy, bbox, size, pad)
        pins[loc_name] = [int(round(px)), int(round(py))]

    return pins


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grp", type=Path, default=DEFAULT_GRP,
                        help=f"Path to duke3d.grp (default: {DEFAULT_GRP})")
    parser.add_argument("--apworld-dir", type=Path,
                        default=Path("/tmp/duke3d-apworld/extracted/duke3d"))
    parser.add_argument("--out-images", type=Path,
                        default=REPO_ROOT / "images")
    parser.add_argument("--out-pins", type=Path,
                        default=REPO_ROOT / "tools" / "map_pins.json")
    parser.add_argument("--skip-render", action="store_true",
                        help="Only extract pin coordinates; don't write PNGs")
    args = parser.parse_args()

    if not args.grp.exists():
        print(f"GRP not found: {args.grp}\nUse --grp to point at duke3d.grp.",
              file=sys.stderr)
        sys.exit(1)

    grp_files = parse_grp(args.grp)
    print(f"Parsed GRP: {len(grp_files)} files")

    levels = load_levels(args.apworld_dir)
    print(f"Parsed {len(levels)} levels from apworld")

    args.out_images.mkdir(parents=True, exist_ok=True)
    pins_all: dict[str, dict[str, list[int]]] = {}
    rendered = 0
    missing = []

    for level in levels:
        map_name = f"{level.prefix}.MAP"
        if map_name not in grp_files:
            missing.append(map_name)
            continue
        parsed = parse_map(grp_files[map_name])
        if not args.skip_render:
            img = render_map(parsed)
            img.save(args.out_images / f"{level.prefix.lower()}_map.png",
                     optimize=True)
            rendered += 1
        pins_all[level.prefix] = extract_pins(level, parsed)
        print(f"  {level.prefix}: {len(pins_all[level.prefix])} pins, "
              f"{len(parsed['walls'])} walls, "
              f"{len(parsed['sprites'])} sprites")

    args.out_pins.parent.mkdir(parents=True, exist_ok=True)
    args.out_pins.write_text(json.dumps(pins_all, indent=2) + "\n")
    print(f"\nRendered {rendered} maps.")
    print(f"Wrote {args.out_pins}.")
    if missing:
        print(f"WARNING: {len(missing)} maps missing from GRP: {missing}")


if __name__ == "__main__":
    main()
