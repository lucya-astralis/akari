#!/usr/bin/env python3
"""LSV-01 Astralis as a wireframe, two wallpapers in SVG: astralis.svg (dark) and
astralis-plan.svg (a light plan on paper).

    python3 design/wallpapers/station.py EDGES.json

EDGES.json comes from station-wire.html: it builds the station from
sc-branding's own station/js/parts.js (copy that js folder next to the page
and serve the folder), takes every edge where the hull folds, projects them
from a three-quarter view and posts them back, sorted near to far into four
paths. This script only lays them out: a ground, a fine grid, the ship, and a
title block. Everything that matters sits inside what a 4:3 screen still shows (x 640 to
3200); the ground and grid go on to every edge, so wider screens see more
of them and nothing is cut.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "akari/static/assets/wallpapers"
W, H = 3840, 2160
MONO = "ui-monospace, SFMono-Regular, Menlo, monospace"


def grid(minor: str, major: str) -> list[str]:
    o = [f'<g fill="none" stroke="{minor}" stroke-width="1">']
    o += [f'<path d="{"".join(f"M{x} 0V{H}" for x in range(0, W + 1, 48))}{"".join(f"M0 {y}H{W}" for y in range(0, H + 1, 48))}"/>']
    o.append("</g>")
    o.append(f'<g fill="none" stroke="{major}" stroke-width="1.4">')
    o.append(f'<path d="{"".join(f"M{x} 0V{H}" for x in range(0, W + 1, 240))}{"".join(f"M0 {y}H{W}" for y in range(0, H + 1, 240))}"/>')
    o.append("</g>")
    return o


def wallpaper(paths: list[str], length: float, dark: bool) -> str:
    if dark:
        bg0, bg1, minor, major, ink, dim = "#0c1430", "#04060f", "#1b2650", "#25336a", "#a9c2ff", "#6f83c4"
        alphas = (.95, .62, .38, .2)
    else:
        bg0, bg1, minor, major, ink, dim = "#f4f2ea", "#e6e2d4", "#dcd8ca", "#cbc6b3", "#1d2b66", "#5a6694"
        alphas = (.9, .6, .38, .22)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice">',
         f'<defs><radialGradient id="bg" cx="50%" cy="48%" r="72%"><stop offset="0" stop-color="{bg0}"/><stop offset="1" stop-color="{bg1}"/></radialGradient></defs>',
         f'<rect width="{W}" height="{H}" fill="url(#bg)"/>']
    o += grid(minor, major)
    # a frame round the drawing
    o.append(f'<g fill="none" stroke="{dim}" stroke-opacity=".7" stroke-width="1.4">'
             f'<rect x="640" y="440" width="2560" height="1260" stroke-dasharray="10 12"/>'
             f'</g>')
    # the ship, far edges first
    o.append(f'<g fill="none" stroke="{ink}" stroke-width="1.5" stroke-linecap="round">')
    for d, a in reversed(list(zip(paths, alphas))):
        o.append(f'<path stroke-opacity="{a}" d="{d}"/>')
    o.append("</g>")
    # the title block, bottom left of the frame
    o.append(f'<g font-family="{MONO}" fill="{ink}">'
             f'<text x="640" y="1780" font-size="44" letter-spacing="10" font-weight="600">LSV-01 ASTRALIS</text>'
             f'<text x="640" y="1832" font-size="26" letter-spacing="6" fill="{dim}">LONG-RANGE STATION · ORIKAIA PRIME · SHINSEI CONCORDIA</text>'
             f'<text x="3200" y="1780" font-size="26" letter-spacing="6" fill="{dim}" text-anchor="end">2 RINGS · 24 MODULES · 1 G AT 3.7 RPM</text>'
             f'<text x="3200" y="1832" font-size="26" letter-spacing="6" fill="{dim}" text-anchor="end">LENGTH {round(length)} M · SHEET 1 / 1</text>'
             f'</g>')
    o.append("</svg>")
    return "\n".join(o)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    shots = json.loads(Path(sys.argv[1]).read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    for name, dark in (("astralis", True), ("astralis-plan", False)):
        (OUT / f"{name}.svg").write_text(wallpaper(shots["side"], shots["length"], dark), encoding="utf-8")
        print(name, (OUT / f"{name}.svg").stat().st_size // 1024, "KB")
