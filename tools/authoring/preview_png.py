"""Render a scenario JSON to a coloured PNG for eyeballing against the reference.

Authoring aid only (not shipped, not imported by the engine). Colours mirror the
Qt renderer's flat terrain fills (ui/tile_render.py) so the preview reads like the
app. Sites are drawn as dots with labels; regions can be outlined.

    python tools/authoring/preview_png.py                 # -> scratch/arda_preview.png
    python tools/authoring/preview_png.py out.png --scale 8
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Tuple

from PIL import Image, ImageDraw, ImageFont

# Flat terrain fills, copied from ui/tile_render.py _TERRAIN_RGB.
TERRAIN_RGB: Dict[str, Tuple[int, int, int]] = {
    "plains": (124, 168, 86),
    "forest": (74, 122, 60),
    "mountain": (128, 122, 118),
    "hills": (150, 158, 96),
    "marsh": (92, 116, 92),
    "barren": (176, 150, 108),
    "river": (90, 140, 196),
    "lake": (86, 148, 200),
    "sea": (58, 108, 168),
    "road": (156, 130, 96),
}

SITE_RGB = {
    "city": (250, 240, 120),
    "town": (245, 225, 160),
    "fort": (230, 160, 90),
    "ruin": (170, 170, 170),
    "volcano": (230, 90, 60),
    "gate": (210, 120, 80),
    "gateway": (120, 200, 220),
}

SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "src" / "arda_sim" / "scenarios" / "arda_ta2965.json"
)


def _font(size: int):
    for name in ("Arial.ttf", "DejaVuSans.ttf", "Helvetica.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(scenario: Dict, scale: int = 7, labels: bool = True) -> Image.Image:
    w, h = scenario["width"], scenario["height"]
    legend = scenario["terrain_legend"]
    rows = scenario["terrain"]

    img = Image.new("RGB", (w * scale, h * scale), (0, 0, 0))
    px = img.load()
    for row in range(h):
        line = rows[row]
        for col in range(w):
            rgb = TERRAIN_RGB[legend[line[col]]]
            for dy in range(scale):
                for dx in range(scale):
                    px[col * scale + dx, row * scale + dy] = rgb

    draw = ImageDraw.Draw(img)
    font = _font(max(9, scale + 3))
    for s in scenario.get("sites", []):
        cx, cy = s["col"] * scale + scale // 2, s["row"] * scale + scale // 2
        color = SITE_RGB.get(s["kind"], (255, 255, 255))
        r = scale // 2 + 1
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color, outline=(20, 20, 20))
        if labels:
            draw.text((cx + r + 1, cy - r), s["name"], fill=(15, 15, 15), font=font)
    return img


def main(argv) -> int:
    out = Path(argv[0]) if argv and not argv[0].startswith("--") else (
        Path(__file__).resolve().parents[2] / "scratch_preview" / "arda_preview.png"
    )
    scale = 7
    labels = "--no-labels" not in argv
    if "--scale" in argv:
        scale = int(argv[argv.index("--scale") + 1])
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    img = render(scenario, scale=scale, labels=labels)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    sys.stderr.write(f"wrote {out} ({img.width}x{img.height})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
