#!/usr/bin/env python3
"""Akari-Cursor: zeichnet das Cursor-Set als SVG nach akari/static/assets/cursors/.

Formensprache wie das Zeichen „Schein“: gerade Kanten, schräge Balken im Winkel
des Zeichens (11 nach rechts auf 40 nach oben), ein Hauch Akzent. Jeder Cursor
ist dunkel gefüllt mit hellem Rand und weichem Schatten, so bleibt er auf hellem
wie auf dunklem Grund lesbar. 32 × 32, der Hotspot steht in HOTSPOTS; dieselbe
Tabelle nutzt das Xcursor-Thema (image/cursors/build.sh).

    python3 tools/cursors.py
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "akari" / "static" / "assets" / "cursors"

INK = "#151722"       # Füllung
EDGE = "#ffffff"      # Rand
ACC = "#5663f0"       # Akari-Indigo, zwischen hellem und dunklem Akzent von Facet
SW = 1.5              # Randstärke

# Hotspots in Pixeln des 32er-Bildes
HOTSPOTS = {
    "default": (4, 3), "pointer": (4, 3), "help": (4, 3), "progress": (4, 3),
    "text": (16, 16), "move": (16, 16), "grab": (16, 16), "grabbing": (16, 16),
    "ew-resize": (16, 16), "ns-resize": (16, 16), "nwse-resize": (16, 16), "nesw-resize": (16, 16),
    "wait": (16, 16), "not-allowed": (16, 16), "crosshair": (16, 16),
}


def svg(body: str) -> str:
    # Schatten: dieselbe Form, dunkel, leicht versetzt und weich
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">'
        '<defs><filter id="s" x="-20%" y="-20%" width="140%" height="140%">'
        '<feGaussianBlur stdDeviation=".9"/></filter></defs>'
        f'<g filter="url(#s)" opacity=".38" transform="translate(.6 1.2)">{shadowify(body)}</g>'
        f"{body}</svg>\n"
    )


def shadowify(body: str) -> str:
    return body.replace(f'fill="{INK}"', 'fill="#000"').replace(f'fill="{ACC}"', 'fill="#000"') \
               .replace(f'stroke="{EDGE}"', 'stroke="#000"')


def shape(d: str, fill: str = INK, extra: str = "") -> str:
    return (f'<path d="{d}" fill="{fill}" stroke="{EDGE}" stroke-width="{SW}" '
            f'stroke-linejoin="round" stroke-linecap="round"{extra}/>')


def flat(d: str, fill: str) -> str:
    return f'<path d="{d}" fill="{fill}"/>'


# Der Pfeil: Spitze oben links, der Schwanz als schräger Balken
ARROW = "M4 3L4 23.6L9 19.2L12.4 27.4L16.2 25.8L12.9 18L19.6 18Z"
# Akzent im Pfeil: ein schmaler Schein-Balken
ARROW_ACC = "M8.3 10.6L10.1 10.6L7.4 19.8L5.6 19.8Z"


def arrow(acc_body: bool = False) -> str:
    if acc_body:   # pointer: der Pfeil selbst leuchtet
        return shape(ARROW, ACC) + flat("M6.4 9.6L8 9.6L5.9 15L5.6 15L5.6 11.4Z", "#ffffff")
    return shape(ARROW) + flat(ARROW_ACC, ACC)


def badge(inner: str) -> str:
    # kleines rundes Abzeichen unten rechts (Hilfe, Arbeit im Hintergrund)
    return (f'<circle cx="23" cy="23" r="6.2" fill="{ACC}" stroke="{EDGE}" stroke-width="{SW}"/>' + inner)


def bars(xs, top: float, bot: float, w: float, fills) -> str:
    """Drei Schein-Balken: Parallelogramme, oben um 11/40 der Höhe nach rechts versetzt."""
    lean = (bot - top) * 11 / 40
    out = ""
    for x, f in zip(xs, fills):
        out += shape(f"M{x + lean:.2f} {top}L{x + lean + w:.2f} {top}L{x + w:.2f} {bot}L{x:.2f} {bot}Z", f)
    return out


def double_arrow(rot: int) -> str:
    # waagerechter Doppelpfeil, gedreht; in der Mitte ein schmaler Steg
    d = ("M3 16L9.5 9.6L9.5 13.6L22.5 13.6L22.5 9.6L29 16L22.5 22.4L22.5 18.4L9.5 18.4L9.5 22.4Z")
    return (f'<g transform="rotate({rot} 16 16)">' + shape(d)
            + flat("M15.2 14.4L17.6 14.4L16.8 17.6L14.4 17.6Z", ACC) + "</g>")


CURSORS = {
    "default": arrow(),
    "pointer": arrow(acc_body=True),
    "help": arrow() + badge(
        '<path d="M20.9 21.4a2.2 2.2 0 1 1 3.1 2c-.7.3-1 .7-1 1.4v.3" fill="none" stroke="#fff" '
        'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
        '<circle cx="23" cy="27" r=".95" fill="#fff"/>'),
    "progress": arrow() + badge(
        '<path d="M21.6 19.8L23.4 19.8L21.6 26.2L19.8 26.2Z" fill="#fff"/>'
        '<path d="M24.6 21.6L26.4 21.6L25.2 26.2L23.4 26.2Z" fill="#fff" opacity=".6"/>'),
    # Text: ein I-Balken mit Schein-Neigung
    "text": shape("M10.6 4.6L19.8 4.6L19.8 7.2L17.2 7.2L15.6 24.8L18.2 24.8L18.2 27.4L9 27.4L9 24.8L11.6 24.8"
                  "L13.2 7.2L10.6 7.2Z") + flat("M14.4 13L15.6 13L15.1 19L13.9 19Z", ACC),
    "move": shape("M16 2.5L20.6 7.4L17.6 7.4L17.6 14.4L24.6 14.4L24.6 11.4L29.5 16L24.6 20.6L24.6 17.6L17.6 17.6"
                  "L17.6 24.6L20.6 24.6L16 29.5L11.4 24.6L14.4 24.6L14.4 17.6L7.4 17.6L7.4 20.6L2.5 16L7.4 11.4"
                  "L7.4 14.4L14.4 14.4L14.4 7.4L11.4 7.4Z")
            + flat("M16 13.4L18.6 16L16 18.6L13.4 16Z", ACC),
    # Greifen: das Zeichen selbst, offen …
    "grab": bars([5.2, 12.2, 19.2], 6, 26, 4.4, [ACC, INK, INK]),
    # … und zugegriffen: die Balken rücken zusammen
    "grabbing": bars([7.6, 12.6, 17.6], 9, 24, 4.4, [ACC, INK, INK]),
    "ew-resize": double_arrow(0),
    "ns-resize": double_arrow(90),
    "nwse-resize": double_arrow(45),
    "nesw-resize": double_arrow(-45),
    # Warten: drei Balken, der erste leuchtet
    "wait": f'<circle cx="16" cy="16" r="12.5" fill="{INK}" stroke="{EDGE}" stroke-width="{SW}"/>'
            + flat("M13.4 8.6L15.6 8.6L11.6 23.4L9.4 23.4Z", ACC)
            + flat("M17.6 10.8L20.2 10.8L16.8 23.4L14.2 23.4Z", "#ffffff")
            + flat("M21.9 14.6L24.4 14.6L22 23.4L19.5 23.4Z", "#ffffff", ) .replace('/>', ' opacity=".45"/>'),
    "not-allowed": f'<circle cx="16" cy="16" r="11" fill="none" stroke="{EDGE}" stroke-width="6.5"/>'
                   f'<circle cx="16" cy="16" r="11" fill="none" stroke="{INK}" stroke-width="3.5"/>'
                   + shape("M21.5 6.2L24.3 8.6L10.5 25.8L7.7 23.4Z", ACC),
    "crosshair": shape("M14.8 3L17.2 3L17.2 12.5L14.8 12.5Z") + shape("M14.8 19.5L17.2 19.5L17.2 29L14.8 29Z")
                 + shape("M3 14.8L12.5 14.8L12.5 17.2L3 17.2Z") + shape("M19.5 14.8L29 14.8L29 17.2L19.5 17.2Z")
                 + f'<circle cx="16" cy="16" r="1.6" fill="{ACC}" stroke="{EDGE}" stroke-width="1"/>',
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, body in CURSORS.items():
        (OUT / f"{name}.svg").write_text(svg(body))
    # Hotspots für das Xcursor-Thema
    (OUT / "hotspots.txt").write_text("".join(f"{n} {x} {y}\n" for n, (x, y) in HOTSPOTS.items()))
    print(f"{len(CURSORS)} Cursor nach {OUT}")


if __name__ == "__main__":
    main()
