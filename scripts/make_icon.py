"""Generate the app icon: src/print_explosion_3d/assets/icon.svg (source) and icon.png (1024 px).

A retro starburst behind an isometric, layer-lined cube on a warm macOS-style tile.
Rasterized with AppKit (macOS 14+ reads SVG natively), so no extra dependencies.

    uv run python scripts/make_icon.py
"""

from __future__ import annotations

import math
from pathlib import Path

import AppKit
import Foundation

ASSETS = Path(__file__).resolve().parents[1] / "src" / "print_explosion_3d" / "assets"
SIZE = 1024


def _pts(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def build_svg() -> str:
    cx, cy = SIZE / 2, SIZE / 2

    # Starburst: alternating outer/inner radii.
    spikes, r_out, r_in = 14, 330, 248
    burst = [
        (
            cx + (r_out if i % 2 == 0 else r_in) * math.cos(math.pi * i / spikes - math.pi / 2),
            cy + (r_out if i % 2 == 0 else r_in) * math.sin(math.pi * i / spikes - math.pi / 2),
        )
        for i in range(2 * spikes)
    ]

    # Isometric cube, edge a, centered on (cx, cy).
    a = 168
    dx, dy = a * math.cos(math.pi / 6), a / 2
    top = [(cx, cy - a), (cx + dx, cy - dy), (cx, cy), (cx - dx, cy - dy)]
    left = [(cx - dx, cy - dy), (cx, cy), (cx, cy + a), (cx - dx, cy + dy)]
    right = [(cx, cy), (cx + dx, cy - dy), (cx + dx, cy + dy), (cx, cy + a)]

    # 3D-printer layer lines across both side faces.
    layers = []
    for k in range(1, 7):
        t = a * k / 7
        layers.append(
            f'<line x1="{cx - dx:.1f}" y1="{cy - dy + t:.1f}" x2="{cx:.1f}" y2="{cy + t:.1f}"/>'
        )
        layers.append(
            f'<line x1="{cx:.1f}" y1="{cy + t:.1f}" x2="{cx + dx:.1f}" y2="{cy - dy + t:.1f}"/>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" viewBox="0 0 {SIZE} {SIZE}">
  <defs>
    <linearGradient id="tile" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffc47e"/>
      <stop offset="1" stop-color="#ec8236"/>
    </linearGradient>
  </defs>
  <rect x="100" y="100" width="824" height="824" rx="186" fill="url(#tile)"/>
  <polygon points="{_pts(burst)}" fill="#fff4e4"/>
  <polygon points="{_pts(top)}" fill="#f7b46a"/>
  <polygon points="{_pts(left)}" fill="#c76d2a"/>
  <polygon points="{_pts(right)}" fill="#e08840"/>
  <g stroke="#000" stroke-opacity="0.13" stroke-width="5" stroke-linecap="round">
    {"".join(layers)}
  </g>
  <polyline points="{_pts([top[3], top[2], top[1]])}" fill="none" stroke="#fff" stroke-opacity="0.35" stroke-width="4"/>
</svg>
"""


def rasterize(svg: str, out: Path) -> None:
    data = Foundation.NSData.dataWithBytes_length_(svg.encode(), len(svg.encode()))
    image = AppKit.NSImage.alloc().initWithData_(data)
    if image is None:
        raise SystemExit("AppKit could not read the SVG (needs macOS 14+).")
    rep = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, SIZE, SIZE, 8, 4, True, False, AppKit.NSDeviceRGBColorSpace, 0, 0
    )
    rep.setSize_((SIZE, SIZE))
    AppKit.NSGraphicsContext.saveGraphicsState()
    AppKit.NSGraphicsContext.setCurrentContext_(
        AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    )
    image.drawInRect_(((0, 0), (SIZE, SIZE)))
    AppKit.NSGraphicsContext.restoreGraphicsState()
    png = rep.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, {})
    out.write_bytes(bytes(png))


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    svg = build_svg()
    (ASSETS / "icon.svg").write_text(svg)
    rasterize(svg, ASSETS / "icon.png")
    print(f"Wrote {ASSETS / 'icon.svg'} and icon.png")


if __name__ == "__main__":
    main()
