#!/usr/bin/env python3
"""Akari's stock wallpapers, 1920×1080 WebP plus a 320×180 thumbnail each.

    python3 design/wallpapers/make.py SRC

All of them are drawn here, from shapes and Facet's colours; no photos, no
renders. SRC holds only two vector pieces of Shinsei Concordia (the owner's
worldbuilding, lucya.sh), rendered from their SVGs with rsvg-convert: flag.png
(for its blue) and emblem.png.

The list of wallpapers the desktop offers is WALLS in akari/static/desk.js;
an id there is a file name here.
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "akari/static/assets/wallpapers"
W, H = 1920, 1080


def save(img: Image.Image, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img = img.convert("RGB")
    img.save(OUT / f"{name}.webp", "WEBP", quality=80, method=6)
    img.resize((320, 180), Image.LANCZOS).save(OUT / f"{name}-t.webp", "WEBP", quality=78, method=6)
    print(f"{name}: {(OUT / f'{name}.webp').stat().st_size // 1024} KB")


def cover(img: Image.Image) -> Image.Image:
    return ImageOps.fit(img.convert("RGB"), (W, H), Image.LANCZOS, centering=(.5, .5))


def gradient(stops: list[tuple[float, tuple[int, int, int]]], angle: float = 115) -> Image.Image:
    """A linear gradient across the screen, like CSS linear-gradient(angle, …)."""
    a = math.radians(angle - 90)
    dx, dy = math.cos(a), math.sin(a)
    span = abs(W * dx) + abs(H * dy)
    small = Image.new("RGB", (W // 8, H // 8))
    px = small.load()
    for y in range(small.height):
        for x in range(small.width):
            t = ((x * 8 - W / 2) * dx + (y * 8 - H / 2) * dy) / span + .5
            t = min(max(t, 0), 1)
            for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                if t0 <= t <= t1:
                    f = (t - t0) / (t1 - t0 or 1)
                    px[x, y] = tuple(round(c0[i] + (c1[i] - c0[i]) * f) for i in range(3))
                    break
    return small.resize((W, H), Image.BICUBIC)


def blobs(base: Image.Image, spots: list[tuple[float, float, float, tuple[int, int, int], float]], blur: int = 160) -> Image.Image:
    """Soft light: each spot (x, y, radius, colour, strength) screened over the base."""
    layer = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x, y, r, col, k in spots:
        d.ellipse([x * W - r * W, y * H - r * W, x * W + r * W, y * H + r * W], fill=tuple(round(c * k) for c in col))
    return ImageChops.screen(base, layer.filter(ImageFilter.GaussianBlur(blur)))


def rays(img: Image.Image, colour: tuple[int, int, int], alpha: int, lines: list[tuple[float, float, float, float, int]]) -> Image.Image:
    """Nova's light: thin slanted strokes, softened."""
    layer = Image.new("RGBA", (W, H), (*colour, 0))     # transparent in the strokes' colour: a blur adds no dark fringe
    d = ImageDraw.Draw(layer)
    for x0, y0, x1, y1, w in lines:
        d.line([(x0 * W, y0 * H), (x1 * W, y1 * H)], fill=(*colour, alpha), width=w)
    layer = layer.filter(ImageFilter.GaussianBlur(2))
    glow = layer.filter(ImageFilter.GaussianBlur(18))
    out = img.convert("RGBA")
    out.alpha_composite(glow)
    out.alpha_composite(layer)
    return out.convert("RGB")


def grain(img: Image.Image, amount: int = 6) -> Image.Image:
    """A little noise, so large gradients do not band."""
    rnd = random.Random(7)
    noise = Image.frombytes("L", (W // 2, H // 2), bytes(rnd.randrange(128 - amount, 128 + amount) for _ in range(W // 2 * H // 2)))
    noise = noise.resize((W, H)).convert("RGB")
    return ImageChops.add(ImageChops.subtract(img, Image.new("RGB", (W, H), (128,) * 3)), noise, scale=1, offset=0) if False else \
        Image.blend(img, ImageChops.overlay(img, noise), .5)


def stars(img: Image.Image, n: int, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    d = ImageDraw.Draw(img)
    for _ in range(n):
        x, y, b = rnd.random() * W, rnd.random() * H, rnd.randrange(90, 230)
        r = rnd.choice((.6, .8, 1, 1, 1.4))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(b, b, min(255, b + 20)))
    return img


def orikaia() -> Image.Image:
    """Reika II rising over the sea of Orikaia Prime: a banded giant with its rings, a moon, the horizon."""
    sky = gradient([(0, (8, 12, 34)), (.55, (14, 22, 58)), (.78, (34, 40, 92)), (1, (12, 16, 40))], 180)
    sky = stars(sky, 260, 5)
    img = sky.convert("RGBA")
    cx, cy, r = int(W * .66), int(H * .34), int(H * .34)
    # the planet: bands across, light from the upper left, the night side to the lower right
    disc = Image.new("RGBA", (2 * r, 2 * r), (0, 0, 0, 0))
    bands = Image.new("RGB", (2 * r, 2 * r))
    bd = ImageDraw.Draw(bands)
    rnd = random.Random(4)
    y = 0
    while y < 2 * r:
        h = rnd.randint(10, 46)
        t = rnd.random()
        bd.rectangle([0, y, 2 * r, y + h], fill=(int(178 + 62 * t), int(192 + 50 * t), int(222 + 30 * t)))
        y += h
    bands = bands.filter(ImageFilter.GaussianBlur(7)).rotate(-14, resample=Image.BICUBIC, expand=False, fillcolor=(180, 195, 225))
    shade = Image.new("L", (2 * r, 2 * r))
    sp = shade.load()
    for yy in range(0, 2 * r, 2):
        for xx in range(0, 2 * r, 2):
            dx, dy = (xx - r * .55) / r, (yy - r * .5) / r
            v = max(40, min(255, int(268 - 118 * math.hypot(dx, dy))))
            sp[xx, yy] = v
            if xx + 1 < 2 * r: sp[xx + 1, yy] = v
            if yy + 1 < 2 * r: sp[xx, yy + 1] = v; sp[min(xx + 1, 2 * r - 1), yy + 1] = v
    lit = ImageChops.multiply(bands, Image.merge("RGB", (shade, shade, shade)))
    mask = Image.new("L", (2 * r, 2 * r))
    ImageDraw.Draw(mask).ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
    disc.paste(lit, (0, 0), mask)
    # the rings: thin ellipses, tilted, the far half behind the planet
    def ring_layer(front: bool) -> Image.Image:
        layer = Image.new("RGBA", (W, H), (210, 220, 245, 0))
        d = ImageDraw.Draw(layer)
        for k, (rx, a) in enumerate([(2.05, 70), (2.15, 110), (2.28, 60), (2.42, 90), (2.5, 40)]):
            box = [cx - r * rx, cy - r * rx * .22, cx + r * rx, cy + r * rx * .22]
            d.arc(box, 0 if front else 180, 180 if front else 360, fill=(225, 232, 252, min(255, a + 70)), width=3 + k % 2 * 3)
        return layer.rotate(-14, center=(cx, cy), resample=Image.BICUBIC).filter(ImageFilter.GaussianBlur(1))
    img.alpha_composite(ring_layer(False))
    glow = Image.new("RGBA", (W, H), (120, 150, 255, 0))
    ImageDraw.Draw(glow).ellipse([cx - r * 1.12, cy - r * 1.12, cx + r * 1.12, cy + r * 1.12], fill=(120, 150, 255, 70))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40)))
    img.alpha_composite(disc, (cx - r, cy - r))
    img.alpha_composite(ring_layer(True))
    # a moon, and the sea below the horizon with the giant's light on it
    d = ImageDraw.Draw(img)
    d.ellipse([W * .2 - 26, H * .22 - 26, W * .2 + 26, H * .22 + 26], fill=(226, 214, 180, 255))
    sea_top = int(H * .74)
    sea = gradient([(0, (10, 16, 44)), (1, (4, 6, 18))], 180).crop((0, 0, W, H - sea_top))
    img.paste(sea.resize((W, H - sea_top)), (0, sea_top))
    shine = Image.new("RGBA", (W, H), (150, 175, 255, 0))
    sd = ImageDraw.Draw(shine)
    for i in range(40):
        yy = sea_top + 6 + i * (H - sea_top) / 40
        w = 30 + i * 9
        sd.line([(cx - w, yy), (cx + w, yy)], fill=(160, 185, 255, max(0, 110 - i * 3)), width=2)
    img.alpha_composite(shine.filter(ImageFilter.GaussianBlur(3)))
    d.line([(0, sea_top), (W, sea_top)], fill=(90, 110, 190, 255), width=1)
    return grain(img.convert("RGB"))


def glas() -> Image.Image:
    """Akari's mark, three rays, drawn huge across a light ground as frosted panes."""
    base = gradient([(0, (240, 240, 250)), (.6, (246, 242, 252)), (1, (250, 240, 246))], 120)
    base = blobs(base, [(.25, .3, .25, (60, 70, 160), .25), (.8, .75, .25, (140, 60, 120), .18)], 200)
    img = base.convert("RGBA")
    # the mark's three parallelograms (index.html #am), 95.64 × 100 units, scaled to the screen height and beyond
    rays_ = [((40.4, 0), (51.4, 0), (11, 100), (0, 100)), ((51.14, 14), (75.14, 14), (40.39, 100), (16.39, 100)),
             ((71.64, 36), (95.64, 36), (69.79, 100), (45.79, 100))]
    k, ox, oy = H * 1.5 / 100, W * .2, -H * .25
    for i, (quad, fill) in enumerate(zip(rays_, [(97, 110, 243, 70), (255, 255, 255, 150), (150, 150, 190, 60)])):
        layer = Image.new("RGBA", (W, H), (*fill[:3], 0))
        pts = [(ox + x * k, oy + y * k) for x, y in quad]
        ImageDraw.Draw(layer).polygon(pts, fill=fill)
        edge = Image.new("RGBA", (W, H), (255, 255, 255, 0))
        ImageDraw.Draw(edge).line(pts + [pts[0]], fill=(255, 255, 255, 170), width=2)
        img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(1.5)))
        img.alpha_composite(edge.filter(ImageFilter.GaussianBlur(.8)))
    return grain(img.convert("RGB"))


def main(src: Path) -> None:
    # Orikaia Prime, drawn: Reika II, the ringed giant, over the night sea of the ocean moon
    save(orikaia(), "orikaia")

    # Glas (light): Akari's three rays, very large, as panes of frosted glass on Facet's light
    save(glas(), "glas")

    # Concordia: the flag's blue, deepening to the night of the Expanse, the emblem large and quiet
    flagblue = Image.open(src / "flag.png").convert("RGB").getpixel((8, 8))
    base = gradient([(0, tuple(min(255, int(c * 1.15)) for c in flagblue)), (.5, flagblue), (1, (6, 14, 48))], 125)
    base = blobs(base, [(.78, .42, .3, (120, 160, 255), .35)], 220)
    emblem = Image.open(src / "emblem.png").convert("RGBA")
    emblem.thumbnail((int(H * .9), int(H * .9)), Image.LANCZOS)
    r, g, b, a = emblem.split()
    white = Image.merge("RGBA", (r.point(lambda _: 255), g.point(lambda _: 255), b.point(lambda _: 255), a.point(lambda v: v * 22 // 100)))
    out = base.convert("RGBA")
    out.alpha_composite(white, (int(W * .74 - emblem.width / 2), int(H / 2 - emblem.height / 2)))
    save(grain(rays(stars(out.convert("RGB"), 160, 3), (190, 210, 255), 60,
                    [(.05, 1.1, .38, -.1, 3), (.14, 1.1, .47, -.1, 2), (.26, 1.1, .59, -.1, 2)])), "concordia")

    # Aurora (light): Facet's violet and a rose dawn, soft
    aurora = gradient([(0, (236, 234, 252)), (.5, (244, 238, 250)), (1, (252, 236, 242))], 120)
    aurora = ImageChops.multiply(aurora, ImageChops.invert(blobs(Image.new("RGB", (W, H)),
        [(.12, .18, .26, (150, 140, 20), 1), (.5, .95, .32, (20, 150, 90), .9), (.92, .1, .22, (140, 60, 0), .7)], 200)))
    save(grain(rays(aurora, (255, 255, 255), 170, [(.1, 1.1, .45, -.1, 4), (.2, 1.1, .55, -.1, 2), (.62, 1.1, .97, -.1, 3)])), "aurora")

    # Mitternacht (dark): deep navy, violet light from the left, a few stars
    night = gradient([(0, (22, 20, 46)), (.6, (10, 10, 24)), (1, (6, 6, 14))], 120)
    night = blobs(night, [(.12, .25, .26, (97, 110, 243), .5), (.4, 1, .25, (170, 90, 220), .25)], 200)
    save(grain(rays(stars(night, 220, 11), (170, 160, 255), 90, [(.04, 1.1, .4, -.1, 3), (.13, 1.1, .49, -.1, 2), (.25, 1.1, .61, -.1, 2)])), "mitternacht")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else sys.exit(__doc__))
