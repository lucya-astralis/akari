#!/usr/bin/env python3
"""Akari's app icons in Facet's glass, drawn from one recipe.

Every icon is the same object: a tile in the app's colour with Nova's ray
across it, and on it the motif in two panes of glass, one frosted behind
(white, see-through, a hairline round it) and one clear in front (white,
lit from above, a soft shadow under it). Sheen from the top, a rim that is
bright above and fades below. Only the colour and the motif change.

    python3 design/icons/apps.py            writes design/icons/apps.svg (a preview sheet)
    python3 design/icons/apps.py --patch    also puts the symbols into akari/static/index.html

Raw colours belong here and only here: an icon is an object, the same in
both themes, not chrome.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "akari/static/index.html"

TILE = 'x="2" y="2" width="60" height="60" rx="15"'

# name: (top-left colour, bottom-right colour)
COLOURS = {
    "files":    ("#6fb3ff", "#2450d6"),
    "terminal": ("#4c4c5c", "#121218"),
    "music":    ("#ff7a98", "#8236ec"),
    "editor":   ("#ffd666", "#ee7c0e"),
    "web":      ("#ffa44f", "#6f4cf6"),
    "xterm":    ("#7d7d90", "#30303d"),
    "settings": ("#a3a9bf", "#4b5166"),
    "tasks":    ("#a796ff", "#4f38d8"),
    "monitor":  ("#55e3a6", "#0c8a5e"),
    "window":   ("#48e2c8", "#0a7f7b"),
}

BACK = 'fill="#fff" fill-opacity=".24" stroke="#fff" stroke-opacity=".5" stroke-width=".8"'
FRONT = 'fill="url(#ag-front)" filter="url(#ag-drop)"'
LINE = 'fill="none" stroke="url(#ag-front)" stroke-linecap="round" stroke-linejoin="round" filter="url(#ag-drop)"'

MOTIF = {
    # a folder: the back as frosted glass, the front clear
    "files": f'''<path d="M13 22a3.5 3.5 0 0 1 3.5-3.5h9.6l4.2 4.4h17.2a3.5 3.5 0 0 1 3.5 3.5V42H13z" {BACK}/>
    <path d="M11 30.5a3.5 3.5 0 0 1 3.5-3.5h35a3.5 3.5 0 0 1 3.5 3.8l-1.5 13.6a3.6 3.6 0 0 1-3.6 3.2H16.1a3.6 3.6 0 0 1-3.6-3.2z" {FRONT}/>''',
    # a pane of glass with a prompt on it
    "terminal": f'''<rect x="11" y="15" width="42" height="34" rx="6" {BACK}/>
    <path d="M19 25.5l7.5 6.5-7.5 6.5" fill="none" stroke="#5ee8a4" stroke-width="4.2" stroke-linecap="round" stroke-linejoin="round" filter="url(#ag-drop)"/>
    <rect x="30" y="36" width="14" height="4.4" rx="2.2" {FRONT}/>''',
    # a disc behind, the note in front
    "music": f'''<circle cx="32" cy="32" r="20" {BACK}/>
    <path d="M27.5 41.5V21l16-3.4v19.8" {LINE} stroke-width="3.4"/>
    <circle cx="23" cy="41.8" r="5.4" {FRONT}/><circle cx="39" cy="37.8" r="5.4" {FRONT}/>''',
    # a sheet behind, the lines and a pen in front
    "editor": f'''<rect x="15" y="11" width="30" height="40" rx="4.5" {BACK} transform="rotate(-6 30 31)"/>
    <path d="M20.5 21.5h17M20.5 28h17M20.5 34.5h10" {LINE} stroke-width="3" transform="rotate(-6 30 31)"/>
    <path d="M47.6 27.2l3.2 3.2-14.6 14.6-5 1.8 1.8-5z" {FRONT}/>''',
    # a globe: the disc frosted, the meridians clear
    "web": f'''<circle cx="32" cy="32" r="18" {BACK}/>
    <g {LINE} stroke-width="2.8"><ellipse cx="32" cy="32" rx="7.5" ry="18"/><path d="M15 26h34M15 38h34"/><circle cx="32" cy="32" r="18"/></g>''',
    # an X window: a frame behind, its bar and the X in front
    "xterm": f'''<rect x="11" y="14" width="42" height="36" rx="6" {BACK}/>
    <path d="M11 20a6 6 0 0 1 6-6h30a6 6 0 0 1 6 6v3H11z" {FRONT}/>
    <path d="M24 31l8 9M32 31l-8 9" stroke="#ffc65a" stroke-width="3.6" stroke-linecap="round" filter="url(#ag-drop)"/>
    <rect x="36" y="37.5" width="9" height="3.6" rx="1.8" {FRONT}/>''',
    # a gear: a frosted ring behind, the wheel clear in front
    "settings": f'''<circle cx="32" cy="32" r="20" {BACK}/>
    <path d="M29.6 12h4.8l1 5.1 3.4 1.4 4.3-2.9 3.4 3.4-2.9 4.3 1.4 3.4 5.1 1v4.8l-5.1 1-1.4 3.4 2.9 4.3-3.4 3.4-4.3-2.9-3.4 1.4-1 5.1h-4.8l-1-5.1-3.4-1.4-4.3 2.9-3.4-3.4 2.9-4.3-1.4-3.4-5.1-1v-4.8l5.1-1 1.4-3.4-2.9-4.3 3.4-3.4 4.3 2.9 3.4-1.4zM32 25.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13z" fill-rule="evenodd" {FRONT}/>''',
    # rows: two frosted, the first clear, each with its mark
    "tasks": f'''<rect x="13" y="15" width="38" height="9" rx="4.5" {FRONT}/>
    <rect x="13" y="27.5" width="38" height="9" rx="4.5" {BACK}/>
    <rect x="13" y="40" width="38" height="9" rx="4.5" {BACK}/>
    <circle cx="45.5" cy="19.5" r="2.2" fill="#4f38d8"/>''',
    # bars frosted behind, the line clear in front
    "monitor": f'''<rect x="13" y="34" width="8" height="15" rx="2.5" {BACK}/><rect x="24" y="28" width="8" height="21" rx="2.5" {BACK}/>
    <rect x="35" y="31" width="8" height="18" rx="2.5" {BACK}/><rect x="46" y="22" width="5" height="27" rx="2.5" {BACK}/>
    <path d="M12 33l9-9 7 5 10-13 7 8 7-6" {LINE} stroke-width="4"/>''',
    # any other program: a window
    "window": f'''<rect x="12" y="15" width="40" height="34" rx="6" {BACK}/>
    <path d="M12 21a6 6 0 0 1 6-6h28a6 6 0 0 1 6 6v4H12z" {FRONT}/>
    <rect x="18" y="31" width="16" height="4" rx="2" {FRONT}/><rect x="18" y="39" width="22" height="4" rx="2" fill="#fff" fill-opacity=".55"/>''',
}

DEFS = '''<defs>
    <!-- the clear glass in front: white, lit from above -->
    <linearGradient id="ag-front" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity=".82"/></linearGradient>
    <filter id="ag-drop" x="-30%" y="-30%" width="160%" height="170%"><feDropShadow dx="0" dy="1.4" stdDeviation="1.3" flood-color="#000" flood-opacity=".22"/></filter>
    <!-- sheen from the top, Nova's ray across, a rim bright above and faint below -->
    <linearGradient id="ag-sheen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".34"/><stop offset=".48" stop-color="#fff" stop-opacity="0"/></linearGradient>
    <linearGradient id="ag-ray" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".16"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
    <linearGradient id="ag-rim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".6"/><stop offset=".55" stop-color="#fff" stop-opacity=".12"/><stop offset="1" stop-color="#fff" stop-opacity=".22"/></linearGradient>
    <clipPath id="ag-tile"><rect {TILE}/></clipPath>
{grads}
  </defs>'''


def symbol(name: str) -> str:
    return f'''  <symbol id="app-{name}" viewBox="0 0 64 64">
    <rect {TILE} fill="url(#ag-{name})"/>
    <path d="M30 2h13L21 62H8z" fill="url(#ag-ray)" clip-path="url(#ag-tile)"/>
    {MOTIF[name]}
    <rect {TILE} fill="url(#ag-sheen)"/>
    <rect x="2.6" y="2.6" width="58.8" height="58.8" rx="14.4" fill="none" stroke="url(#ag-rim)" stroke-width="1.2"/>
  </symbol>'''


def sprite() -> str:
    grads = "\n".join(f'    <linearGradient id="ag-{n}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient>'
                      for n, (a, b) in COLOURS.items())
    head = ("  <!-- App icons (design/icons/apps.py, do not edit here): a tile in the app's colour with\n"
            "       Nova's ray, the motif in two panes of glass. Raw colours are allowed here and only here. -->\n  ")
    return head + DEFS.replace("{TILE}", TILE).replace("{grads}", grads) + "\n" + "\n".join(symbol(n) for n in COLOURS)


def sheet() -> str:
    uses = "".join(f'<use href="#app-{n}" x="{16 + i % 5 * 80}" y="{16 + i // 5 * 80}" width="64" height="64"/>' for i, n in enumerate(COLOURS))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="416" height="176" viewBox="0 0 416 176">\n'
            f'<rect width="416" height="176" fill="#16161a"/>\n{sprite()}\n{uses}\n</svg>\n')


def patch() -> None:
    s = INDEX.read_text(encoding="utf-8")
    start = s.index("  <!-- App icons")
    end = s.index("</symbol>", s.index('<symbol id="app-window"')) + len("</symbol>")
    INDEX.write_text(s[:start] + sprite() + s[end:], encoding="utf-8")


if __name__ == "__main__":
    out = Path(__file__).with_name("apps.svg")
    out.write_text(sheet(), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
    if "--patch" in sys.argv:
        patch()
        print(f"patched {INDEX.relative_to(ROOT)}")
