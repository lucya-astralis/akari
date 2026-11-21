"""Builds "Akari Symbols": a tiny font with the Akari OS mark on U+F0000, so
the mark can stand in a terminal prompt like any character.

  python3 tools/symbols.py     (needs fonttools and brotli)

Writes image/rootfs/usr/share/fonts/truetype/akari/AkariSymbols.ttf (for Linux
apps, fc-cache) and akari/static/assets/fonts/AkariSymbols.woff2 (for the web
terminal, as a fallback after MesloLGS NF). The geometry is the "Schein" mark
from design/logo: a light edge and two shards falling at 22°."""

from __future__ import annotations

from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT = Path(__file__).resolve().parent.parent
CODE = 0xF0000
# the mark, viewBox 0 0 95.64 100
SHAPES = [
    [(40.4, 0), (51.4, 0), (11, 100), (0, 100)],
    [(51.14, 14), (75.14, 14), (40.39, 100), (16.39, 100)],
    [(71.64, 36), (95.64, 36), (69.79, 100), (45.79, 100)],
]
UPM, ADVANCE = 1000, 600           # one terminal cell is about 0.6 em wide
HEIGHT, BASE = 640, -70            # the mark's height in units, and where its foot sits


def glyph():
    pen = TTGlyphPen(None)
    scale = HEIGHT / 100
    width = 95.64 * scale
    dx = (ADVANCE - width) / 2
    for poly in SHAPES:
        pts = [(round(dx + x * scale), round(BASE + (100 - y) * scale)) for x, y in poly]
        pen.moveTo(pts[0])
        for p in pts[1:]:
            pen.lineTo(p)
        pen.closePath()
    return pen.glyph()


def build(path: Path, flavor: str | None = None) -> None:
    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder([".notdef", "akari"])
    fb.setupCharacterMap({CODE: "akari"})
    empty = TTGlyphPen(None).glyph()
    fb.setupGlyf({".notdef": empty, "akari": glyph()})
    fb.setupHorizontalMetrics({".notdef": (ADVANCE, 0), "akari": (ADVANCE, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Akari Symbols", "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    path.parent.mkdir(parents=True, exist_ok=True)
    if flavor:
        fb.font.flavor = flavor
    fb.save(str(path))
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    build(ROOT / "image/rootfs/usr/share/fonts/truetype/akari/AkariSymbols.ttf")
    build(ROOT / "akari/static/assets/fonts/AkariSymbols.woff2", "woff2")
