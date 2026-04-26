#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10"]
# ///
"""Generate recoloured variants of base sprites.

Reads images/atomic_health.png + images/armor.png and writes the four
randomizer-only variants by hue-rotating in HSV space. Alpha preserved.
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGES = REPO_ROOT / "images"


def hue_shift(src: Path, dst: Path, hue_delta: int, sat_scale: float = 1.0,
              val_scale: float = 1.0):
    """Rotate the H channel of every non-transparent pixel by hue_delta (0-255)
    and optionally scale S/V. Alpha is preserved."""
    img = Image.open(src).convert("RGBA")
    r, g, b, a = img.split()
    rgb = Image.merge("RGB", (r, g, b)).convert("HSV")
    h, s, v = rgb.split()

    h = h.point(lambda p: (p + hue_delta) % 256)
    if sat_scale != 1.0:
        s = s.point(lambda p: max(0, min(255, int(p * sat_scale))))
    if val_scale != 1.0:
        v = v.point(lambda p: max(0, min(255, int(p * val_scale))))

    out = Image.merge("HSV", (h, s, v)).convert("RGB")
    r2, g2, b2 = out.split()
    Image.merge("RGBA", (r2, g2, b2, a)).save(dst, optimize=True)


def main():
    atomic = IMAGES / "atomic_health.png"
    armor = IMAGES / "armor.png"

    # Atomic Health is green. Shift to:
    #   - plutonium: cyan/blue (Cherenkov-glow vibe), +120° hue
    #   - uranium:   yellow,                          -60°  hue, slight val boost
    hue_shift(atomic, IMAGES / "plutonium_health.png", hue_delta=85)   # ~+120°
    hue_shift(atomic, IMAGES / "uranium_health.png",   hue_delta=-43,  # ~-60°
              val_scale=1.05)

    # Armor is gray; pure hue rotation barely moves grays. Boost saturation hard
    # so the recoloured variants are unambiguous.
    hue_shift(armor, IMAGES / "sturdy_armor.png", hue_delta=170,  # ~+240° → blue
              sat_scale=4.0)
    hue_shift(armor, IMAGES / "heavy_armor.png",  hue_delta=37,   # ~+50° → gold
              sat_scale=4.0, val_scale=1.1)

    print("Wrote plutonium_health.png, uranium_health.png, "
          "sturdy_armor.png, heavy_armor.png")


if __name__ == "__main__":
    main()
