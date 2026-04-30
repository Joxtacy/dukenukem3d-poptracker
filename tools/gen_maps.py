#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "numpy>=1.26"]
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
import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
from gen_pack_data import load_levels  # noqa: E402

# BUILD .MAP v7 record sizes (bytes)
SECTOR_SIZE = 40
WALL_SIZE = 32
SPRITE_SIZE = 44

RENDER_MAX_DIM = 2048      # longer axis of the output PNG
RENDER_MIN_DIM = 512       # shortest allowed dimension (very narrow maps)
PAD_RATIO = 0.02           # 2% padding around map content
DEFAULT_GRP = Path.home() / "Documents" / "Duke3D" / "duke3d.grp"


def render_size_for(bbox: tuple[int, int, int, int]) -> tuple[int, int]:
    """Pick a per-level output size that matches the map's aspect ratio so
    we don't waste pixels on letterboxing. Longer axis is RENDER_MAX_DIM."""
    minx, miny, maxx, maxy = bbox
    bw = max(maxx - minx, 1)
    bh = max(maxy - miny, 1)
    if bw >= bh:
        w = RENDER_MAX_DIM
        h = max(int(round(RENDER_MAX_DIM * bh / bw)), RENDER_MIN_DIM)
    else:
        h = RENDER_MAX_DIM
        w = max(int(round(RENDER_MAX_DIM * bw / bh)), RENDER_MIN_DIM)
    return (w, h)


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
        # picnum lives at offset 14 within the 44-byte sprite struct
        # (after x/y/z and cstat).
        picnum = struct.unpack_from("<h", data, pos + 14)[0]
        sprites.append({"x": x, "y": y, "z": z, "picnum": picnum})
        pos += SPRITE_SIZE

    return {"sectors": sectors, "walls": walls, "sprites": sprites}


# Duke 3D "NUKEBUTTON" — the level-end lever sprite. Both regular and secret
# exits use this picnum; we count them and match to the apworld's exit-type
# locations (declared in order: Exit, then Secret Exit when present).
NUKEBUTTON_PICNUM = 142


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


def render_map(parsed: dict, size: tuple[int, int],
               pad=PAD_RATIO) -> Image.Image:
    bbox = compute_bbox(parsed["walls"])
    img = Image.new("RGB", size, BG)
    draw = ImageDraw.Draw(img)
    walls = parsed["walls"]
    # Wall thickness scales with image so very large maps stay readable.
    line_w = max(2, min(size) // 400)
    for w in walls:
        p2 = w["point2"]
        if p2 >= len(walls):
            continue
        w2 = walls[p2]
        a = world_to_pixel(w["x"], w["y"], bbox, size, pad)
        b = world_to_pixel(w2["x"], w2["y"], bbox, size, pad)
        draw.line([a, b], fill=WALL_COLOR, width=line_w)
    return img


# ---------------------------------------------------------------------------
# Calibration (use a manual image instead of the vector render)
# ---------------------------------------------------------------------------

CALIBRATION_PATH = REPO_ROOT / "tools" / "map_calibration.json"


def pick_reference_sprites(level, parsed: dict) -> list[tuple[str, int, int]]:
    """Pick up to three sprite locations spread across the map for a stable
    affine fit. Falls back to fewer if the level has very few sprites."""
    candidates: list[tuple[str, int, int]] = []
    for loc in level.location_defs:
        if loc["type"] == "sprite" and loc["id"] < len(parsed["sprites"]):
            sp = parsed["sprites"][loc["id"]]
            candidates.append((loc["name"], sp["x"], sp["y"]))

    if len(candidates) < 3:
        return candidates

    # Pick three points that maximize spread:
    #  1) furthest northwest (smallest x + y)
    #  2) point with greatest distance from #1
    #  3) point with greatest distance from the line through #1 and #2
    p1 = min(candidates, key=lambda c: c[1] + c[2])

    def sq_dist(a, b):
        return (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2

    p2 = max((c for c in candidates if c is not p1), key=lambda c: sq_dist(c, p1))

    dx, dy = p2[1] - p1[1], p2[2] - p1[2]
    seg_len_sq = dx * dx + dy * dy or 1

    def line_dist_sq(c):
        return ((c[1] - p1[1]) * dy - (c[2] - p1[2]) * dx) ** 2 / seg_len_sq

    p3 = max(
        (c for c in candidates if c is not p1 and c is not p2),
        key=line_dist_sq,
    )
    return [p1, p2, p3]


def init_calibration(levels, grp_files, path: Path) -> None:
    """Write a starter map_calibration.json with auto-picked reference sprites
    per level. The user fills in image_xy for each."""
    out = {}
    for level in levels:
        map_name = f"{level.prefix}.MAP"
        if map_name not in grp_files:
            continue
        parsed = parse_map(grp_files[map_name])
        refs = pick_reference_sprites(level, parsed)
        out[level.prefix] = {
            "image": f"images/{level.prefix.lower()}_map.png",
            "reference_points": [
                {
                    "name": name,
                    "world_xy": [wx, wy],
                    "image_xy": [None, None],
                }
                for (name, wx, wy) in refs
            ],
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"Wrote {path} with {len(out)} levels.")
    print("Next: drop your manual PNGs into images/, fill in image_xy for "
          "each reference_point in the JSON, then re-run gen_maps.py.")


def load_calibration(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def calibration_filled(entry: dict) -> bool:
    """All reference_points have non-null image_xy with two valid numbers."""
    pts = entry.get("reference_points", [])
    if len(pts) < 2:
        return False
    for p in pts:
        ixy = p.get("image_xy")
        if not ixy or len(ixy) != 2 or any(v is None for v in ixy):
            return False
    return True


def compute_affine(world_pts, img_pts) -> tuple[float, ...]:
    """Least-squares affine fit. Returns (a, b, c, d, e, f) with:
        img_x = a*world_x + b*world_y + c
        img_y = d*world_x + e*world_y + f
    """
    n = len(world_pts)
    A = np.zeros((2 * n, 6))
    b = np.zeros(2 * n)
    for i, ((wx, wy), (ix, iy)) in enumerate(zip(world_pts, img_pts)):
        A[2 * i] = [wx, wy, 1, 0, 0, 0]
        A[2 * i + 1] = [0, 0, 0, wx, wy, 1]
        b[2 * i] = ix
        b[2 * i + 1] = iy
    z, *_ = np.linalg.lstsq(A, b, rcond=None)
    return tuple(float(v) for v in z.tolist())


def apply_affine(transform, x, y) -> tuple[float, float]:
    a, b, c, d, e, f = transform
    return (a * x + b * y + c, d * x + e * y + f)


def extract_pins_calibrated(level, parsed: dict, cal_entry: dict) -> dict:
    """Use the manual-image calibration to compute per-location pin coords."""
    refs = cal_entry["reference_points"]
    world_pts = [tuple(p["world_xy"]) for p in refs]
    img_pts = [tuple(p["image_xy"]) for p in refs]
    transform = compute_affine(world_pts, img_pts)

    pins: dict[str, list[int]] = {}
    bbox = compute_bbox(parsed["walls"])
    cx_w = (bbox[0] + bbox[2]) / 2
    cy_w = (bbox[1] + bbox[3]) / 2

    # Same exit handling as extract_pins (see above).
    exit_sprites = [
        (sp["x"], sp["y"]) for sp in parsed["sprites"]
        if sp.get("picnum") == NUKEBUTTON_PICNUM
    ]
    exit_iter = iter(exit_sprites)

    for loc in level.location_defs:
        loc_name = loc["name"]
        loc_type = loc["type"]
        loc_id = loc["id"]

        wx = wy = None
        if loc_type == "sprite":
            if loc_id < len(parsed["sprites"]):
                sp = parsed["sprites"][loc_id]
                wx, wy = sp["x"], sp["y"]
        elif loc_type == "sector":
            c = sector_centroid(loc_id, parsed)
            if c is not None:
                wx, wy = c
        elif loc_type == "exit":
            try:
                wx, wy = next(exit_iter)
            except StopIteration:
                wx, wy = cx_w, cy_w

        if wx is None:
            wx, wy = cx_w, cy_w
        ix, iy = apply_affine(transform, wx, wy)
        pins[loc_name] = [int(round(ix)), int(round(iy))]
    return pins


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


def extract_pins(level, parsed: dict, size: tuple[int, int],
                 pad=PAD_RATIO) -> dict:
    bbox = compute_bbox(parsed["walls"])
    pins: dict[str, list[int]] = {}
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2  # fallback: center

    # Collect NUKEBUTTON sprites in sprite-index order so we can match them
    # to the level's exit-type locations one-by-one. The apworld declares
    # exits in a consistent order (Exit first, Secret Exit when present),
    # which lines up with sprite-index order in the .MAP files I've seen.
    exit_sprites = [
        (sp["x"], sp["y"]) for sp in parsed["sprites"]
        if sp.get("picnum") == NUKEBUTTON_PICNUM
    ]
    exit_iter = iter(exit_sprites)

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
            # Use the next available NUKEBUTTON sprite. Boss-only levels
            # (which trigger end-of-level by killing the boss, not by
            # pressing a button) get the bbox-center fallback.
            try:
                wx, wy = next(exit_iter)
            except StopIteration:
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
    parser.add_argument("--init-calibration", action="store_true",
                        help="Write a starter tools/map_calibration.json with "
                             "auto-picked reference sprites per level, then "
                             "exit. Fill in image_xy and re-run.")
    parser.add_argument("--calibration", type=Path, default=CALIBRATION_PATH,
                        help=f"Calibration JSON path (default: {CALIBRATION_PATH})")
    args = parser.parse_args()

    if not args.grp.exists():
        print(f"GRP not found: {args.grp}\nUse --grp to point at duke3d.grp.",
              file=sys.stderr)
        sys.exit(1)

    grp_files = parse_grp(args.grp)
    print(f"Parsed GRP: {len(grp_files)} files")

    levels = load_levels(args.apworld_dir)
    print(f"Parsed {len(levels)} levels from apworld")

    if args.init_calibration:
        init_calibration(levels, grp_files, args.calibration)
        return

    calibration = load_calibration(args.calibration)

    args.out_images.mkdir(parents=True, exist_ok=True)
    pins_all: dict[str, dict[str, list[int]]] = {}
    rendered = 0
    calibrated = 0
    missing = []

    for level in levels:
        map_name = f"{level.prefix}.MAP"
        if map_name not in grp_files:
            missing.append(map_name)
            continue
        parsed = parse_map(grp_files[map_name])

        cal_entry = (calibration or {}).get(level.prefix)
        if cal_entry and calibration_filled(cal_entry):
            # Calibration mode: use the user's manual image. Don't render.
            pins_all[level.prefix] = extract_pins_calibrated(level, parsed, cal_entry)
            calibrated += 1
            print(f"  {level.prefix}: {len(pins_all[level.prefix])} pins "
                  f"(calibrated against manual image)")
            continue

        # Vector render fallback
        bbox = compute_bbox(parsed["walls"])
        size = render_size_for(bbox)
        if not args.skip_render:
            img = render_map(parsed, size)
            img.save(args.out_images / f"{level.prefix.lower()}_map.png",
                     optimize=True)
            rendered += 1
        pins_all[level.prefix] = extract_pins(level, parsed, size)
        print(f"  {level.prefix}: {len(pins_all[level.prefix])} pins, "
              f"{len(parsed['walls'])} walls, "
              f"{len(parsed['sprites'])} sprites, "
              f"size {size[0]}x{size[1]}")

    args.out_pins.parent.mkdir(parents=True, exist_ok=True)
    args.out_pins.write_text(json.dumps(pins_all, indent=2) + "\n")
    if calibrated:
        print(f"\n{calibrated} levels used manual-image calibration.")
    if rendered:
        print(f"Rendered {rendered} vector maps.")
    print(f"Wrote {args.out_pins}.")
    if missing:
        print(f"WARNING: {len(missing)} maps missing from GRP: {missing}")


if __name__ == "__main__":
    main()
