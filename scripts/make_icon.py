"""Draw the Robinhood Soccer HQ icon and write the platform icon files.

Outputs under build/icon/: icon-1024.png, icon.ico (Windows) and, on macOS, icon.icns
(via iconutil). Mirrors the app's favicon: dark rounded square, green ring, pentagon.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "icon"


def draw(size: int):
    from PIL import Image, ImageDraw

    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # background: rounded square with a subtle vertical gradient
    bg = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bg)
    top, bottom = (26, 42, 74), (11, 18, 32)
    for y in range(s):
        t = y / max(1, s - 1)
        bd.line([(0, y), (s, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=255)
    img.paste(bg, (0, 0), mask)
    green = (74, 222, 160, 255)
    cx = cy = s / 2
    r = s * 0.34
    w = max(2, int(s * 0.062))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=green, width=w)
    # pentagon (the ball's panel), pointing up
    import math

    pr = s * 0.15
    pts = [(cx + pr * math.cos(math.radians(-90 + 72 * k)), cy - s * 0.03 + pr * math.sin(math.radians(-90 + 72 * k))) for k in range(5)]
    d.polygon(pts, fill=green)
    return img


def main() -> int:
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("Pillow not installed; skipping icon generation (pip install pillow)", file=sys.stderr)
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    base = draw(1024)
    base.save(OUT / "icon-1024.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    base.save(OUT / "icon.ico", sizes=[(x, x) for x in sizes])
    print(f"wrote {OUT / 'icon.ico'}")
    if platform.system() == "Darwin" and shutil.which("iconutil"):
        iconset = OUT / "icon.iconset"
        iconset.mkdir(exist_ok=True)
        for px in (16, 32, 128, 256, 512):
            base.resize((px, px)).save(iconset / f"icon_{px}x{px}.png")
            base.resize((px * 2, px * 2)).save(iconset / f"icon_{px}x{px}@2x.png")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT / "icon.icns")], check=True)
        print(f"wrote {OUT / 'icon.icns'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
