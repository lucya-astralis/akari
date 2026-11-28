#!/usr/bin/env python3
"""Star charts as wallpapers, drawn as SVG: sharp at any size, small.

    python3 design/wallpapers/charts.py

Writes akari/static/assets/wallpapers/sternenkarte.svg (dark) and
himmelsatlas.svg (light), plus a 320×180 thumbnail of each next to it. The
chart is the sky of Orikaia Prime (Shinsei Concordia): a polar projection,
circles of declination every 15°, hours of right ascension, a band of the
galaxy, stars by magnitude and constellations with the worldbuilding's
names. The chart's middle sits in the middle of the screen and the drawing
goes on past every edge, so any screen shape cuts it, none crops it badly.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "akari/static/assets/wallpapers"
W, H = 3840, 2160
CX, CY = W / 2, H / 2
R = 1720                     # 90° from the pole: well past the top and bottom, inside the sides

# constellations: name, (ra in hours, dec in degrees) of the stars in drawing order
FIGURES = [
    ("Lantern", [(1.2, 62), (1.9, 58), (2.4, 63), (1.8, 68), (1.2, 62), (1.5, 52), (2.2, 49)]),
    ("Crane", [(5.1, 40), (5.8, 46), (6.6, 44), (7.4, 49), (6.6, 44), (6.4, 36), (6.9, 30)]),
    ("Reika", [(9.4, 70), (10.3, 74), (11.0, 69), (10.2, 64), (9.4, 70)]),
    ("The Warden", [(13.0, 34), (13.6, 41), (14.3, 47), (15.2, 44), (14.3, 47), (14.6, 55), (15.4, 59)]),
    ("The Gate", [(17.2, 20), (17.9, 26), (18.6, 21), (18.0, 14), (17.2, 20)]),
    ("Crown", [(20.1, 52), (20.6, 57), (21.3, 59), (22.0, 56), (22.4, 50)]),
    ("Far Shore", [(22.9, 30), (23.6, 24), (0.4, 27), (0.9, 20), (1.6, 23)]),
    ("Anchor", [(3.4, 12), (3.9, 18), (4.4, 12), (3.9, 18), (3.9, 26)]),
]


def xy(ra_h: float, dec: float) -> tuple[float, float]:
    """Polar projection: the pole in the middle, declination outwards, hours round."""
    r = (90 - dec) / 90 * R
    a = ra_h / 24 * 2 * math.pi - math.pi / 2
    return CX + r * math.cos(a), CY + r * math.sin(a)


def f(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def chart(dark: bool) -> str:
    rnd = random.Random(1311)
    if dark:
        bg0, bg1, line, faint, star, label, band = "#0d1330", "#05070f", "#8fa6ff", "#5b6aa8", "#eef2ff", "#aab6e8", "#6d6fd8"
    else:
        bg0, bg1, line, faint, star, label, band = "#f6f4ee", "#ebe7dc", "#2b3a78", "#8c93b8", "#172040", "#3a4680", "#9aa3d8"
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice">',
         "<defs>",
         f'<radialGradient id="bg" cx="50%" cy="50%" r="75%"><stop offset="0" stop-color="{bg0}"/><stop offset="1" stop-color="{bg1}"/></radialGradient>',
         f'<radialGradient id="glow" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{band}" stop-opacity="{.22 if dark else .18}"/><stop offset="1" stop-color="{band}" stop-opacity="0"/></radialGradient>',
         "</defs>",
         f'<rect width="{W}" height="{H}" fill="url(#bg)"/>']
    # the galaxy: a soft band across the sky
    o.append(f'<ellipse cx="{CX}" cy="{CY}" rx="{R * 1.25}" ry="{R * .32}" transform="rotate(-24 {CX} {CY})" fill="url(#glow)"/>')
    # the grid: declination every 15°, hours every 1h (every 3h a stronger line)
    g = [f'<g fill="none" stroke="{faint}" stroke-opacity="{.55 if dark else .6}">']
    for dec in range(75, -91, -15):
        g.append(f'<circle cx="{CX}" cy="{CY}" r="{f((90 - dec) / 90 * R)}" stroke-width="{2 if dec == 0 else 1.2}"/>')
    for h in range(24):
        x0, y0 = xy(h, 75)
        x1, y1 = xy(h, -90)
        g.append(f'<line x1="{f(x0)}" y1="{f(y0)}" x2="{f(x1)}" y2="{f(y1)}" stroke-width="{1.6 if h % 3 == 0 else .8}"/>')
    # the ecliptic, tilted
    pts = []
    for i in range(0, 361, 3):
        lam = math.radians(i)
        dec = math.degrees(math.asin(math.sin(math.radians(23.4)) * math.sin(lam)))
        pts.append(xy(i / 15, dec))
    g.append(f'<polyline points="{" ".join(f"{f(x)},{f(y)}" for x, y in pts)}" stroke="{line}" stroke-opacity=".5" stroke-width="1.6" stroke-dasharray="14 10"/>')
    g.append("</g>")
    o += g
    # labels: hours on the 30° circle, declinations along hour 0
    o.append(f'<g font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="26" fill="{label}" fill-opacity=".8" text-anchor="middle">')
    for h in range(0, 24, 2):
        x, y = xy(h, 32)
        o.append(f'<text x="{f(x)}" y="{f(y)}" dominant-baseline="middle">{h}h</text>')
    for dec in (60, 45, 30, 15, 0, -15):
        x, y = xy(6, dec)
        o.append(f'<text x="{f(x + 14)}" y="{f(y - 10)}" text-anchor="start">{"+" if dec > 0 else ""}{dec}°</text>')
    o.append("</g>")
    # stars: many faint, few bright, thicker along the galaxy
    s = [f'<g fill="{star}">']
    for _ in range(2600):
        ra, dec = rnd.random() * 24, math.degrees(math.asin(rnd.uniform(-.95, 1)))
        x, y = xy(ra, dec)
        if not (-40 < x < W + 40 and -40 < y < H + 40):
            continue
        # the band: keep more stars near it
        bx = (x - CX) * math.cos(math.radians(24)) + (y - CY) * math.sin(math.radians(24))
        by = -(x - CX) * math.sin(math.radians(24)) + (y - CY) * math.cos(math.radians(24))
        near = math.exp(-(by / (R * .28)) ** 2)
        if rnd.random() > .35 + .65 * near:
            continue
        mag = rnd.random() ** 3.2
        r = .9 + mag * 4.6
        s.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(r)}" fill-opacity="{f(.35 + .65 * min(1, mag * 2))}"/>')
    s.append("</g>")
    o += s
    # constellations: lines, bright stars with a halo, the name in small caps
    c = [f'<g stroke="{line}" stroke-width="2.4" stroke-opacity=".75" fill="none" stroke-linecap="round" stroke-linejoin="round">']
    names = [f'<g font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="30" letter-spacing="6" fill="{label}" text-anchor="middle">']
    for name, figure in FIGURES:
        pts = [xy(ra, dec) for ra, dec in figure]
        c.append(f'<polyline points="{" ".join(f"{f(x)},{f(y)}" for x, y in pts)}"/>')
        for x, y in dict.fromkeys(pts):
            c.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="11" stroke-width="1.4" stroke-opacity=".5"/>')
            c.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="5.5" fill="{star}" stroke="none"/>')
        mx = sum(p[0] for p in pts) / len(pts)
        my = max(p[1] for p in pts) + 58
        names.append(f'<text x="{f(mx)}" y="{f(my)}">{name.upper()}</text>')
    c.append("</g>")
    names.append("</g>")
    o += c + names
    # Orikaia's sun at the pole: a ringed mark in the middle of the screen
    o.append(f'<g fill="none" stroke="{line}" stroke-opacity=".9"><circle cx="{CX}" cy="{CY}" r="9" fill="{star}" stroke="none"/>'
             f'<circle cx="{CX}" cy="{CY}" r="26" stroke-width="2"/><circle cx="{CX}" cy="{CY}" r="44" stroke-width="1" stroke-dasharray="4 8"/></g>')
    o.append(f'<text x="{CX}" y="{CY + 92}" font-family="ui-monospace, SFMono-Regular, Menlo, monospace" font-size="26" letter-spacing="8" fill="{label}" text-anchor="middle">ORIKAIA PRIME · NORTH POLE</text>')
    o.append("</svg>")
    return "\n".join(o)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, dark in (("sternenkarte", True), ("himmelsatlas", False)):
        (OUT / f"{name}.svg").write_text(chart(dark), encoding="utf-8")
        print(name, (OUT / f"{name}.svg").stat().st_size // 1024, "KB")
