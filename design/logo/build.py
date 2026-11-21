"""Akari OS: Zeichen-Entwürfe.

Eine Geometrie, alles daraus: die SVGs je Konzept, die fastfetch-Texte und die
Vorschauseite. Aufruf aus diesem Ordner:

    python3 build.py

Die Wortmarke braucht fontTools (pip install fonttools). Fehlt es, bleiben die
vorhandenen Wortmarken-Dateien stehen.

Geometrie: jedes Zeichen steht in einem Feld 100 × 100. Schnitte laufen im
Nova-Winkel (22° gegen die Senkrechte), die Fuge ist 5 Einheiten breit wie bei
Lucent; das Favicon und der Text nehmen eine breitere Fuge, damit sie bei 16 px
und in Halbblöcken noch zu sehen ist.

Töne der Facetten (wie .f-mark in facet.css, plus das Licht):
  a  hellste Fläche     b  hell     c  mittel     d  Schatten     l  das Licht
"""
import base64, json, math, re, html
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]                       # /…/projects/ls
STATIC = ROOT / "akari" / "akari" / "static"
FONT_DIR = ROOT / "ls-branding" / "fonts"

T = math.tan(math.radians(22))               # Nova: 22° gegen die Senkrechte
GAP, GAP_SMALL, GAP_TEXT = 5, 9, 9

# --------------------------------------------------------------- Geometrie

def clip(poly, P, Q, inside, off=0.0):
    """Hälfte der Ebene an der Geraden P–Q, auf der Seite von `inside`,
    um `off` nach innen gerückt (die halbe Fuge)."""
    nx, ny = -(Q[1] - P[1]), Q[0] - P[0]
    ln = math.hypot(nx, ny); nx, ny = nx / ln, ny / ln
    if nx * (inside[0] - P[0]) + ny * (inside[1] - P[1]) < 0:
        nx, ny = -nx, -ny
    f = lambda X: nx * (X[0] - P[0]) + ny * (X[1] - P[1]) - off
    out = []
    for i, A in enumerate(poly):
        B = poly[(i + 1) % len(poly)]
        fa, fb = f(A), f(B)
        if fa >= 0: out.append(A)
        if (fa >= 0) != (fb >= 0):
            t = fa / (fa - fb); out.append((A[0] + t * (B[0] - A[0]), A[1] + t * (B[1] - A[1])))
    return out

def slant(x50):
    """Gerade im Nova-Winkel, oben nach rechts geneigt, durch (x50, 50)."""
    return (x50 + T * 50, 0.0), (x50 - T * 50, 100.0)

def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

def band(poly, xa, xb, g):
    """Der Streifen zwischen zwei Nova-Schnitten bei xa < xb."""
    A, B = slant(xa), slant(xb)
    p = clip(poly, *A, (100, 50), g / 2)
    return clip(p, *B, (-100, 50), g / 2)

def left_of(poly, x50, g):
    return clip(poly, *slant(x50), (-100, 50), g / 2)

def right_of(poly, x50, g):
    return clip(poly, *slant(x50), (200, 50), g / 2)

# --------------------------------------------------------------- Konzepte

def fenster(g):
    bar = rect(0, 0, 100, 19)
    body = rect(0, 19 + g, 100, 100)
    return [("c", bar), ("b", left_of(body, 42, g)), ("l", band(body, 42, 64, g)),
            ("d", right_of(body, 64, g))]

def a_splitter(g):
    tri = [(50, 0), (50 - T * 100, 100), (50 + T * 100, 100)]
    w = 18                                            # Beinbreite an der Grundlinie
    L = ((tri[1][0] + w + T * 100, 0), (tri[1][0] + w, 100))   # Innenkante links, im Nova-Winkel
    R = ((tri[2][0] - w - T * 100, 0), (tri[2][0] - w, 100))   # Innenkante rechts
    left = clip(tri, *L, (0, 100), g / 2)
    right = clip(clip(tri, *L, (100, 100), g / 2), *R, (100, 100))
    cy, h, wd = 78, 15, 7.5                           # der Funke als Querstrich
    spark = [(50, cy - h), (50 + wd, cy), (50, cy + h), (50 - wd, cy)]
    return [("b", left), ("d", right), ("l", spark)]

def laterne(g):
    top, bot = 10 + g, 90 - g
    body = [(28, top), (72, top), (86, top + 16), (86, bot - 16), (72, bot), (28, bot), (14, bot - 16), (14, top + 16)]
    return [("c", rect(32, 0, 68, 10)), ("l", left_of(body, 50, g)), ("d", right_of(body, 50, g)),
            ("c", rect(32, 90, 68, 100))]

def schein(g):
    gh = g / math.cos(math.radians(22))
    xs, out = T * 50, []
    for w, top, tone in ((11, 0, "l"), (24, 14, "b"), (24, 36, "d")):
        p = clip(clip(rect(-50, top, 150, 100), *slant(xs), (200, 50)), *slant(xs + w), (-200, 50))
        out.append((tone, p)); xs += w + gh
    return out

def funke(g):
    C = (50.0, 50.0)
    a = math.radians(22)
    u = (math.sin(a), -math.cos(a)); v = (math.cos(a), math.sin(a))
    P = lambda d, r: (C[0] + d[0] * r, C[1] + d[1] * r)
    nrm = lambda d: (d[0] / math.hypot(*d), d[1] / math.hypot(*d))
    add = lambda p, q, s=1: (p[0] + s * q[0], p[1] + s * q[1])
    neg = lambda d: (-d[0], -d[1])
    tips = [P(u, 50), P(v, 30), P(neg(u), 50), P(neg(v), 30)]       # oben, rechts, unten, links
    r = 10
    inner = [P(nrm(add(u, neg(v))), r), P(nrm(add(u, v)), r), P(nrm(add(v, neg(u))), r), P(nrm(add(neg(u), neg(v))), r)]
    tones, out = ["l", "d", "c", "a"], []
    for i in range(4):
        i0, i1 = inner[i], inner[(i + 1) % 4]
        k = [C, i0, tips[i], i1]
        k = clip(clip(k, C, i0, tips[i], g / 2), C, i1, tips[i], g / 2)
        out.append((tones[i], k))
    return out

CONCEPTS = [
    dict(id="fenster", name="Lichtfenster", fn=fenster,
         idea="Ein Fenster mit Titelleiste, durch das ein Streifen Licht im Nova-Winkel fällt. "
              "Es sagt am direktesten, was Akari ist: ein Schreibtisch mit Fenstern, und Licht darin.",
         small="Die Titelleiste und der helle Streifen bleiben auch bei 16 px getrennt; in der Kachel liest es sich wie ein App-Fenster. "
               "Als Viereck füllt es die Fläche am stärksten und wirkt neben runden Symbolen etwas schwer."),
    dict(id="a-splitter", name="A-Splitter", fn=a_splitter,
         idea="Das A von Akari aus zwei Splittern, beide Außenkanten genau im Nova-Winkel. Der linke Schenkel läuft durch bis zur Spitze, "
              "der rechte ist im selben Winkel abgeschnitten; statt eines Querstrichs steht ein Funke. Das Gegenstück zum Adler: dessen Flügel bilden ein V, Akari ein A.",
         small="Bei 16 px bleibt eine klare Dreiecksform mit einem hellen Punkt in der Mitte; der Schnitt verschwindet zuerst, die Form nicht. "
               "Verworfen: Ein A oder Dreieck liest sich sofort als Arch Linux, und unter Linux-Systemen ist das A schon vergeben."),
    dict(id="laterne", name="Laterne", fn=laterne,
         idea="Eine Papierlaterne (Akari heißt auch die Lampe aus Papier): oben und unten ein Rand, dazwischen der Körper, im Nova-Winkel in eine leuchtende und eine schattige Hälfte geteilt.",
         small="Groß hat es den meisten Charakter. Bei 16 px werden die Ränder zu Linien, und das Zeichen wird zu einem Achteck mit Strich; als Favicon ist es das schwächste."),
    dict(id="schein", name="Schein", fn=schein,
         idea="Nova im Kleinen: eine schmale Lichtkante und zwei Splitter, die von ihr wegfallen und kürzer werden. Licht von einer Kante, sonst nichts.",
         small="Drei schräge Balken halten sich bis 16 px gut. Es ist nah an Fila (drei kürzer werdende Balken) und Strata (drei Platten); deren Zeichen werden darum neu gemacht, damit Schein allein steht."),
    dict(id="funke", name="Funke", fn=funke,
         idea="Ein vierstrahliger Funke aus vier Facetten wie bei Lucent, die lange Achse um 22° geneigt, der obere Strahl ist das Licht. "
              "Am nächsten an Lucent, darum sofort als Familie erkennbar.",
         small="Bei 16 px wird es ein schräger Stern, gut lesbar. Ein Vierstrahl-Funke ist aber das gängige Zeichen für KI-Funktionen; Akari könnte damit für ein KI-Produkt gehalten werden."),
]
RECOMMENDED = "schein"

# --------------------------------------------------------------- Farben

PALETTES = {  # Silber für dunklen Grund, Ink für hellen; das Licht ist violett
    "silver": dict(a="#ffffff", b="#f2f2f4", c="#c6c8d7", d="#8b8b94", l="#5865f2"),
    "ink":    dict(a="#121216", b="#2b2b34", c="#5b5b66", d="#8b8b94", l="#404ee7"),
}

def fmt(n):
    s = f"{n:.2f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s

def d_attr(poly):
    return "M" + "L".join(f"{fmt(x)} {fmt(y)}" for x, y in poly) + "Z"

def bbox(parts):
    xs = [x for _, p in parts for x, _ in p]; ys = [y for _, p in parts for _, y in p]
    return min(xs), min(ys), max(xs), max(ys)

def viewbox(parts, pad=0):
    x0, y0, x1, y1 = bbox(parts)
    return f"{fmt(x0 - pad)} {fmt(y0 - pad)} {fmt(x1 - x0 + 2 * pad)} {fmt(y1 - y0 + 2 * pad)}"

def svg_mark(parts, fill=None, palette=None, cls=False, pad=0):
    out = []
    for tone, p in parts:
        if cls: out.append(f'<path class="t-{tone}" d="{d_attr(p)}"/>')
        elif palette: out.append(f'<path fill="{palette[tone]}" d="{d_attr(p)}"/>')
        else: out.append(f'<path d="{d_attr(p)}"/>')
    g = "".join(out)
    if fill: g = f'<g fill="{fill}">{g}</g>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox(parts, pad)}">{g}</svg>'

def favicon(parts):
    """Ein Favicon, das dem Farbschema des Browsers folgt."""
    s, i = PALETTES["silver"], PALETTES["ink"]
    css = "".join(f".t-{k}{{fill:{i[k]}}}" for k in "abcdl") + "@media (prefers-color-scheme:dark){" + \
          "".join(f".t-{k}{{fill:{s[k]}}}" for k in "abcdl") + "}"
    body = "".join(f'<path class="t-{t}" d="{d_attr(p)}"/>' for t, p in parts)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox(parts, 4)}"><style>{css}</style>{body}</svg>'

# --------------------------------------------------------------- Halbblöcke (nach akari/tools/logo.py)

def inside(x, y, poly):
    c = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c

def halfblock(parts, rows=12, S=4, thr=.42):
    """$1 = das Licht (Akzent), $2 = alle anderen Facetten (weiß).
    Alle Zeichen bekommen dieselbe Höhe in Zeilen; der Adler hatte 11."""
    x0, y0, x1, y1 = bbox(parts)
    bw, bh = x1 - x0, y1 - y0
    H = rows * 2
    W = max(1, round(H * bw / bh))
    groups = {"$1": [p for t, p in parts if t == "l"], "$2": [p for t, p in parts if t != "l"]}
    def px(i, j):
        best, cov = None, 0
        for k, ps in groups.items():
            n = sum(inside(x0 + (i + (a + .5) / S) * bw / W, y0 + (j + (b + .5) / S) * bh / H, p)
                    for p in ps for a in range(S) for b in range(S))
            if n > cov: best, cov = k, n
        return best if cov >= S * S * thr else None
    grid = [[px(i, j) for i in range(W)] for j in range(H + (H % 2))]
    lines = []
    for r in range(0, len(grid), 2):
        line, cur = "", None
        for i in range(W):
            t, b = grid[r][i], grid[r + 1][i]
            if t and b and t != b: t = b = "$1"          # das Licht ist die kleinere Form, es gewinnt
            k = t or b
            ch = " " if not k else "█" if t and b else "▀" if t else "▄"
            if k and k != cur: cur = k; line += k
            line += ch
        lines.append(line.rstrip())
    return "\n".join(lines)

def halfblock_html(txt):
    out = []
    for line in txt.split("\n"):
        segs = re.split(r"(\$[12])", line)
        cur, s = None, ""
        for seg in segs:
            if seg in ("$1", "$2"):
                if cur: s += "</span>"
                cur = seg; s += f'<span class="tt{seg[1]}">'
            else: s += html.escape(seg)
        if cur: s += "</span>"
        out.append(s)
    return "\n".join(out)

# --------------------------------------------------------------- Wortmarke

def wordmark():
    """'Akari' in Space Grotesk Medium, 'OS' in Regular und leiser. Umrisse, kein Text."""
    try:
        from fontTools.ttLib import TTFont
        from fontTools.pens.svgPathPen import SVGPathPen
        from fontTools.pens.transformPen import TransformPen
    except ImportError:
        return None
    runs = [("Akari", "SpaceGroteskMedium-Regular.ttf", 1.0), ("OS", "SpaceGrotesk-Regular.ttf", .55)]
    x, paths, cap = 0.0, [], None
    for i, (text, file, op) in enumerate(runs):
        f = TTFont(FONT_DIR / file); gs = f.getGlyphSet(); cmap = f.getBestCmap()
        upm = f["head"].unitsPerEm; s = 100 / upm                      # 100 Einheiten = 1 em
        cap = cap or f["OS/2"].sCapHeight * s
        if i: x += f["hmtx"][cmap[ord(" ")]][0] * s * .9
        for ch in text:
            gn = cmap[ord(ch)]
            pen = SVGPathPen(gs)
            gs[gn].draw(TransformPen(pen, (s, 0, 0, -s, x, 0)))
            paths.append((op, pen.getCommands()))
            x += gs[gn].width * s - 0.6                                 # ein Hauch enger, wie Facets Titel
    return dict(width=x + 0.6, cap=cap, paths=paths)

def wordmark_svg(wm, fill="currentColor"):
    g = "".join(f'<path{"" if op == 1 else f" fill-opacity=\"{op}\""} d="{d}"/>' for op, d in wm["paths"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {fmt(-wm["cap"] - 1)} {fmt(wm["width"])} {fmt(wm["cap"] + 2)}">'
            f'<g fill="{fill}">{g}</g></svg>')

def lockup_svg(parts, wm, palette=None, fill="currentColor"):
    """Zeichen links, Wortmarke rechts; das Zeichen ist 1,5 Versalhöhen hoch und
    steht mittig zur Versalhöhe, der Abstand ist eine halbe Zeichenhöhe."""
    x0, y0, x1, y1 = bbox(parts)
    h = wm["cap"] * 1.5; s = h / (y1 - y0); w = (x1 - x0) * s
    ty = -wm["cap"] / 2 - h / 2
    mark = "".join(f'<path{f" fill=\"{palette[t]}\"" if palette else ""} d="{d_attr([((x - x0) * s, (y - y0) * s + ty) for x, y in p])}"/>' for t, p in parts)
    gap = h * .42
    text_fill = palette["a"] if palette else fill
    words = "".join(f'<path{"" if op == 1 else f" fill-opacity=\"{op}\""} transform="translate({fmt(w + gap)} 0)" d="{d}"/>' for op, d in wm["paths"])
    W = w + gap + wm["width"]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {fmt(ty - 1)} {fmt(W)} {fmt(h + 2)}">'
            f'<g fill="{fill}">{mark}</g><g fill="{text_fill}">{words}</g></svg>')

# --------------------------------------------------------------- Bauen

def build():
    (HERE / "svg").mkdir(exist_ok=True); (HERE / "fastfetch").mkdir(exist_ok=True)
    wm = wordmark()
    if wm:
        (HERE / "svg" / "wordmark-mono.svg").write_text(wordmark_svg(wm))
        (HERE / "svg" / "wordmark-silver.svg").write_text(wordmark_svg(wm, PALETTES["silver"]["a"]))
        (HERE / "svg" / "wordmark-ink.svg").write_text(wordmark_svg(wm, PALETTES["ink"]["a"]))
        (HERE / "wordmark.json").write_text(json.dumps(wm))
    else:
        wm = json.loads((HERE / "wordmark.json").read_text())
    data = []
    for c in CONCEPTS:
        cid, parts, small, text = c["id"], c["fn"](GAP), c["fn"](GAP_SMALL), c["fn"](GAP_TEXT)
        d = HERE / "svg" / cid; d.mkdir(exist_ok=True)
        files = {
            f"{cid}-mono.svg": svg_mark(parts, fill="currentColor"),
            f"{cid}-silver.svg": svg_mark(parts, palette=PALETTES["silver"]),
            f"{cid}-ink.svg": svg_mark(parts, palette=PALETTES["ink"]),
            f"{cid}-favicon.svg": favicon(small),
            f"{cid}-lockup-mono.svg": lockup_svg(parts, wm),
            f"{cid}-lockup-silver.svg": lockup_svg(parts, wm, PALETTES["silver"]),
            f"{cid}-lockup-ink.svg": lockup_svg(parts, wm, PALETTES["ink"]),
        }
        for name, s in files.items(): (d / name).write_text(s + "\n")
        ff = halfblock(text)
        (HERE / "fastfetch" / f"{cid}.txt").write_text(ff + "\n")
        data.append(dict(c, parts=parts, tiny=small, ff=ff, files=files))
    (HERE / "index.html").write_text(page(data, wm, standalone=False))
    return data, wm

# --------------------------------------------------------------- Vorschauseite

def inline_mark(parts, cls="mk", pad=0, label=None):
    body = "".join(f'<path class="t-{t}" d="{d_attr(p)}"/>' for t, p in parts)
    aria = f'role="img" aria-label="{label}"' if label else 'aria-hidden="true"'
    return f'<svg class="{cls}" viewBox="{viewbox(parts, pad)}" {aria}>{body}</svg>'

def inline_lockup(parts, wm, cls="lockup"):
    s = lockup_svg(parts, wm)
    s = s.replace('xmlns="http://www.w3.org/2000/svg" ', f'class="{cls}" role="img" aria-label="Akari OS" ')
    # die Facetten bekommen die Töne der Seite
    tones = iter(t for t, _ in parts)
    return re.sub(r'<path d="', lambda m: f'<path class="t-{next(tones)}" d="', s, count=len(parts))

FF_INFO = [("", "lucya@akari"), ("rule", ""), ("System", "Debian GNU/Linux 13 (trixie) x86_64"), ("Kernel", "6.12.48"),
           ("Desktop", "Akari · Facet 1.8"), ("Shell", "zsh 5.9"), ("Läuft seit", "3 Stunden, 12 Minuten"),
           ("Pakete", "412 (dpkg)"), ("Speicher", "1,21 GiB / 7,66 GiB (16 %)")]

def fastfetch_block(ff):
    logo = halfblock_html(ff).split("\n")
    rows = max(len(logo), len(FF_INFO) + 1)
    lines = []
    for i in range(rows):
        l = logo[i] if i < len(logo) else ""
        vis = re.sub(r"<[^>]+>", "", l)
        pad = " " * (26 - len(html.unescape(vis)))
        j = i - 1
        if 0 <= j < len(FF_INFO):
            k, v = FF_INFO[j]
            info = (f'<span class="tt2">{v}</span>' if k == "" else '<span class="ttr">────────────────────────────</span>' if k == "rule"
                    else f'<span class="tt1">{k:<11}</span>  {html.escape(v)}')
        else: info = ""
        lines.append(" " + l + pad + "  " + info)
    return "\n".join(lines)

def page(data, wm, standalone):
    if standalone:
        css = (STATIC / "facet.css").read_text()
        def font(m):
            p = STATIC / m.group(1)
            return "url('data:font/woff2;base64," + base64.b64encode(p.read_bytes()).decode() + "')"
        css = re.sub(r"url\('(assets/fonts/(?:SpaceGrotesk|JetBrainsMono)-(?:400|500|600)\.woff2)'\)", font, css)
        css = re.sub(r"@font-face\{[^}]*-700\.woff2[^}]*\}", "", css)
        head_css = f"<style>{css}</style>"
    else:
        head_css = '<link rel="stylesheet" href="../../akari/static/facet.css">'
    rec = next(c for c in data if c["id"] == RECOMMENDED)

    def tile(c, size):
        return f'<span class="tile" style="--sz:{size}px">{inline_mark(c["parts"], "mk mk--tile")}</span>'

    def favtab(c):
        return (f'<div class="tab"><span class="tab__fav">{inline_mark(c["tiny"], "mk", 4)}</span>'
                f'<span class="tab__t">Akari · Schreibtisch</span></div>')

    def raster(c, ground):
        return f'<canvas class="px" width="16" height="16" data-c="{c["id"]}" data-g="{ground}" aria-label="16-px-Raster, {ground}"></canvas>'

    overview_rows = []
    for c in data:
        cells = []
        for g in ("dark", "light"):
            cells.append(f'<td class="g-{g}"><div class="cellrow">{raster(c, g)}'
                         f'<span class="real16">{inline_mark(c["tiny"], "mk", 4)}</span>'
                         f'<span class="bar16">{inline_mark(c["tiny"], "mk")}<b>Akari OS</b></span></div></td>')
            cells.append(f'<td class="g-{g}">{tile(c, 44)}</td>')
            cells.append(f'<td class="g-{g}">{inline_mark(c["parts"], "mk mk--64")}</td>')
        star = ' <span class="f-badge rec">Empfehlung</span>' if c["id"] == RECOMMENDED else ""
        overview_rows.append(f'<tr><th scope="row"><a href="#{c["id"]}">{c["name"]}</a>{star}</th>{"".join(cells)}</tr>')

    sections = []
    for n, c in enumerate(data, 1):
        nova = lambda mode, mirror="": (
            f'<div class="nova f-nova {mirror}" style="color-scheme:{mode}"><div class="nova__in">'
            f'{inline_mark(c["parts"], "mk mk--hero")}'
            f'<div class="nova__name">Akari OS</div><div class="nova__clock">20:14</div></div>'
            f'<span class="f-label nova__tag">{"Dunkel" if mode == "dark" else "Hell"}</span></div>')
        docks = "".join(
            f'<div class="dock g-{g}"><div class="dock__row">{tile(c, 56)}{tile(c, 44)}{tile(c, 36)}'
            f'<span class="dock__sep"></span><span class="other"></span><span class="other"></span></div></div>' for g in ("dark", "light"))
        favs = "".join(f'<div class="g-{g} favs">{favtab(c)}<div class="favs__px">{raster(c, g)}<span class="f-dim">16 px, vierfach</span></div></div>' for g in ("dark", "light"))
        rec_badge = '<span class="f-badge rec">Empfehlung</span>' if c["id"] == RECOMMENDED else ""
        files = " · ".join(f'<a href="svg/{c["id"]}/{c["id"]}-{v}.svg">{v}</a>' for v in ("mono", "silver", "ink", "favicon", "lockup-mono"))
        sections.append(f'''
<section class="concept f-card" id="{c["id"]}">
  <header class="concept__head">
    <div class="concept__mark g-auto">{inline_mark(c["parts"], "mk mk--48")}</div>
    <div class="concept__title"><span class="f-label">Konzept {n}</span><h2>{c["name"]} {rec_badge}</h2></div>
  </header>
  <div class="concept__text">
    <p>{c["idea"]}</p>
    <p class="f-dim"><b>In klein:</b> {c["small"]}</p>
  </div>
  <div class="stage">
    <figure class="fig fig--nova"><figcaption class="f-label">Anmeldung auf Nova</figcaption><div class="novas">{nova("dark")}{nova("light", "f-nova--mirror")}</div></figure>
    <figure class="fig"><figcaption class="f-label">Dock, getönte Kachel · 56 / 44 / 36 px</figcaption>{docks}</figure>
    <figure class="fig"><figcaption class="f-label">Favicon</figcaption><div class="favgrid">{favs}</div></figure>
    <figure class="fig fig--ff"><figcaption class="f-label">fastfetch · Halbblöcke, 24 Spalten</figcaption><pre class="term">{fastfetch_block(c["ff"])}</pre></figure>
  </div>
  {"" if standalone else f'<p class="files f-dim">Dateien: {files} · <a href="fastfetch/{c["id"]}.txt">fastfetch</a></p>'}
</section>''')

    raster_svgs = {c["id"]: {g: svg_mark(c["tiny"], palette=PALETTES["silver" if g == "dark" else "ink"], pad=4) for g in ("dark", "light")} for c in data}

    doc = "" if standalone else '<!doctype html>\n<html lang="de">\n<meta charset="utf-8">\n'
    return doc + f'''<title>Akari OS Zeichen</title>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
{head_css}
<style>
/* Layout: eine Spalte; oben der Vergleich aller Konzepte, darunter je Konzept eine Karte
   mit den vier Einsätzen (Nova, Dock, Favicon, fastfetch), am Ende die Empfehlung. */
:root{{
  /* die Töne des Zeichens, wie .f-mark: Silber auf dunkel, Ink auf hell; das Licht violett */
  --t-a: light-dark(#121216, #ffffff);
  --t-b: light-dark(#2b2b34, #f2f2f4);
  --t-c: light-dark(#5b5b66, #c6c8d7);
  --t-d: light-dark(#8b8b94, #8b8b94);
  --t-l: light-dark(#404ee7, #5865f2);
  --term-bg: #0b0b10; --term-fg: #d6d6dc; --term-1: #af87ff; --term-2: #ffffff; --term-rule: #585858;
}}
body{{ background:var(--bg); color:var(--text) }}
.wrap{{ max-width:1320px; margin:0 auto; padding-block:var(--s-7, 40px) var(--s-8, 64px);
  padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px));
  display:grid; gap:var(--s-6, 32px) }}
.g-dark{{ color-scheme:dark }} .g-light{{ color-scheme:light }}
.g-dark, .g-light{{ background:var(--bg); color:var(--text) }}
.mk{{ display:block; flex:none }}
.mk .t-a{{ fill:var(--t-a) }} .mk .t-b{{ fill:var(--t-b) }} .mk .t-c{{ fill:var(--t-c) }} .mk .t-d{{ fill:var(--t-d) }} .mk .t-l{{ fill:var(--t-l) }}
.mk--64{{ height:64px; width:auto; margin:auto }} .mk--48{{ height:48px; width:auto }}
.hero{{ display:grid; gap:var(--s-4, 16px) }}
.hero h1{{ margin:0; font-size:clamp(28px, 4vw, 40px); line-height:1.1; letter-spacing:-.01em; text-wrap:balance }}
.hero p{{ margin:0; max-width:68ch; color:var(--text-dim) }}
h2{{ margin:0; font-size:var(--fs-600, 20px); line-height:1.25; font-weight:600; display:flex; align-items:center; gap:10px; flex-wrap:wrap }}
.rec{{ background:var(--acc-soft); color:var(--acc); font:500 11px/1 var(--mono); letter-spacing:.06em; text-transform:uppercase; padding:5px 8px; border-radius:var(--r-pill, 999px) }}

/* Vergleich */
.cmp{{ overflow-x:auto; border:var(--hair, 1px) solid var(--stroke-2); border-radius:var(--r-lg, 8px); background:var(--card) }}
.cmp table{{ border-collapse:collapse; width:100%; min-width:900px }}
.cmp th, .cmp td{{ padding:14px 16px; text-align:center; vertical-align:middle; border-bottom:var(--hair, 1px) solid var(--stroke-3) }}
.cmp tr:last-child > *{{ border-bottom:0 }}
.cmp thead th{{ font:500 11px/1.3 var(--mono); letter-spacing:.06em; text-transform:uppercase; color:var(--text-dim); background:var(--surface) }}
.cmp tbody th{{ text-align:left; font-weight:600; white-space:nowrap }}
.cmp tbody th a{{ color:var(--text); text-decoration:none }}
.cmp tbody th a:hover{{ color:var(--acc) }}
.cellrow{{ display:flex; align-items:center; justify-content:center; gap:14px }}
.real16 .mk{{ width:16px; height:16px }}
.bar16{{ display:flex; align-items:center; gap:7px; font-weight:600; font-size:13px; white-space:nowrap }}
.bar16 .mk{{ height:16px; width:auto }}
canvas.px{{ width:64px; height:64px; image-rendering:pixelated; border-radius:4px; background:var(--bg); outline:1px solid var(--stroke-3) }}

/* Kachel */
.tile{{ width:var(--sz); height:var(--sz); border-radius:calc(var(--sz) * .26); display:inline-grid; place-items:center; flex:none;
  background:linear-gradient(160deg, light-dark(oklch(.6 .2 277), oklch(.5 .2 277)), var(--acc-fill));
  box-shadow:inset 0 1px 0 rgba(255,255,255,.22), 0 1px 2px rgba(0,0,0,.25) }}
.mk--tile{{ height:58%; width:auto; max-width:64% }}
.mk--tile .t-a, .mk--tile .t-b, .mk--tile .t-l{{ fill:#ffffff }} /* Weiß auf --acc-fill, wie Facets Ausnahme */
.mk--tile .t-c{{ fill:rgba(255,255,255,.72) }} .mk--tile .t-d{{ fill:rgba(255,255,255,.52) }}
.mk--tile .t-b{{ fill:rgba(255,255,255,.86) }}

/* Konzept-Karte */
.concept{{ display:grid; gap:var(--s-5, 24px); padding:var(--s-6, 28px); scroll-margin-top:16px }}
.concept__head{{ display:flex; align-items:center; gap:16px }}
.concept__title{{ display:grid; gap:4px }}
.concept__text{{ display:grid; gap:8px; max-width:78ch }} .concept__text p{{ margin:0 }}
.stage{{ display:grid; grid-template-columns:repeat(12, minmax(0, 1fr)); gap:var(--s-5, 20px) }}
.fig{{ margin:0; display:grid; gap:10px; align-content:start; min-width:0 }}
.fig--nova{{ grid-column:span 7 }} .fig:nth-child(2){{ grid-column:span 5 }}
.fig:nth-child(3){{ grid-column:span 5 }} .fig--ff{{ grid-column:span 7 }}
@media (max-width:980px){{ .stage > .fig{{ grid-column:1 / -1 !important }} }}
.novas{{ display:grid; grid-template-columns:1fr 1fr; gap:10px }}
@media (max-width:560px){{ .novas{{ grid-template-columns:1fr }} }}
.nova{{ position:relative; aspect-ratio:4 / 3; border-radius:var(--r-lg, 8px); color:var(--text); max-width:100% }}
.nova__in{{ position:relative; z-index:1; height:100%; display:grid; place-content:center; justify-items:center; gap:10px }}
.mk--hero{{ height:clamp(56px, 9vw, 96px); width:auto }}
.nova__name{{ font-weight:600; font-size:17px; letter-spacing:-.005em }}
.nova__clock{{ font:500 11px/1 var(--mono); letter-spacing:.08em; color:var(--text) }}
.nova__tag{{ position:absolute; z-index:1; left:10px; top:8px; color:var(--text) }}
.dock{{ border-radius:var(--r-lg, 8px); padding:18px 14px; display:grid; place-items:center;
  background:linear-gradient(68deg, var(--nova-a), var(--nova-b) 40%, var(--nova-c) 75%) }}
.dock + .dock{{ margin-top:10px }}
.dock__row{{ display:flex; align-items:center; gap:10px; padding:8px; border-radius:16px; background:var(--glass-hi); border:1px solid var(--glass-line);
  box-shadow:0 8px 24px rgba(0,0,0,.18) }}
.dock__sep{{ width:1px; align-self:stretch; background:var(--stroke-2) }}
.other{{ width:44px; height:44px; border-radius:11px; background:var(--surface-3) }}
.favgrid{{ display:grid; gap:10px }}
.favs{{ border-radius:var(--r-lg, 8px); padding:12px; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:12px; border:1px solid var(--stroke-2) }}
.tab{{ display:flex; align-items:center; gap:8px; padding:7px 12px; background:var(--surface-3); border-radius:8px 8px 0 0; min-width:0 }}
.tab__fav .mk{{ width:16px; height:16px }}
.tab__t{{ font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis }}
.favs__px{{ display:flex; align-items:center; gap:10px; font-size:12px }}
.term{{ margin:0; padding:14px 6px; overflow-x:auto; background:var(--term-bg); color:var(--term-fg); border-radius:var(--r-lg, 8px);
  font:12px/1 var(--mono); color-scheme:dark }}
.tt1{{ color:var(--term-1) }} .tt2{{ color:var(--term-2); font-weight:600 }} .ttr{{ color:var(--term-rule) }}
.files{{ margin:0; font-size:12px }} .files a{{ color:var(--acc) }}

/* Empfehlung */
.recsec{{ display:grid; gap:var(--s-5, 24px); padding:var(--s-6, 28px) }}
.lockups{{ display:grid; grid-template-columns:1fr 1fr; gap:10px }}
@media (max-width:760px){{ .lockups{{ grid-template-columns:1fr }} }}
.lockups > div{{ border-radius:var(--r-lg, 8px); padding:48px 24px; display:grid; place-items:center; border:1px solid var(--stroke-2) }}
.lockup{{ height:56px; width:auto; max-width:100% }}
.lockup .t-a{{ fill:var(--t-a) }} .lockup .t-b{{ fill:var(--t-b) }} .lockup .t-c{{ fill:var(--t-c) }} .lockup .t-d{{ fill:var(--t-d) }} .lockup .t-l{{ fill:var(--t-l) }}
.lockup > g:last-child{{ fill:var(--t-a) }}
.lockup--s{{ height:22px }}
.why{{ margin:0; padding-left:20px; display:grid; gap:6px; max-width:78ch }}
</style>

<main class="wrap">
  <header class="hero">
    <span class="f-label">Akari OS · Facet 1.8 · Entwurf</span>
    <h1>Ein eigenes Zeichen für Akari OS</h1>
    <p>Fünf Konzepte, jedes in denselben Lagen: 16 px als Favicon und in der Menüleiste, als Kachel im Dock, groß auf Nova bei der Anmeldung, hell und dunkel, und als Halbblock-Text für fastfetch. Akari heißt Licht, Schein; darum hat jedes Zeichen eine Facette, die das Licht ist, und sie ist violett.</p>
  </header>

  <section aria-label="Vergleich" class="cmp">
    <table>
      <thead><tr><th scope="col">Konzept</th>
        <th scope="col">Dunkel · 16 px, Raster und Menüleiste</th><th scope="col">Dock</th><th scope="col">64 px</th>
        <th scope="col">Hell · 16 px, Raster und Menüleiste</th><th scope="col">Dock</th><th scope="col">64 px</th></tr></thead>
      <tbody>{"".join(overview_rows)}</tbody>
    </table>
  </section>

  {"".join(sections)}

  <section class="recsec f-card" id="empfehlung">
    <div class="concept__title"><span class="f-label">Empfehlung</span><h2>Schein, mit der Wortmarke</h2></div>
    <div class="lockups">
      <div class="g-dark">{inline_lockup(rec["parts"], wm)}</div>
      <div class="g-light">{inline_lockup(rec["parts"], wm)}</div>
    </div>
    <ol class="why">
      <li><b>Es ist Nova.</b> Licht von einer Kante, Splitter im 22°-Winkel, die von ihr wegfallen: die Grammatik der Hausgrafik, auf drei Flächen gebracht. Wer den Anmeldebildschirm sieht, sieht dasselbe im Zeichen.</li>
      <li><b>Es ist das Licht.</b> Die schmale violette Kante ist Akari, der Schein; die beiden Splitter sind, was sie beleuchtet. Im Hellen wie im Dunkeln bleibt sie die eine farbige Fläche.</li>
      <li><b>Es trägt klein.</b> Drei schräge Flächen bleiben bei 16 px, in der Menüleiste und als Halbblock-Text getrennt; es braucht keine Details, die verschwinden.</li>
      <li><b>Es ist frei.</b> Kein A (Arch), kein Fenster, kein Stern, keine Lampe. Fila und Strata sprechen heute eine ähnliche Strich-Sprache und bekommen eigene, neue Zeichen.</li>
    </ol>
    <p class="f-dim" style="margin:0;max-width:78ch">Wortmarke: „Akari“ in Space Grotesk Medium, „OS“ in Regular mit 55 % Deckkraft, als Umrisse. Das Zeichen ist anderthalb Versalhöhen hoch und steht mittig zu den Versalien. Klein in der Menüleiste: <span class="g-auto" style="display:inline-block;vertical-align:middle">{inline_lockup(rec["parts"], wm, "lockup lockup--s")}</span></p>
  </section>
</main>

<script>
const SVGS = {json.dumps(raster_svgs)};
for (const cv of document.querySelectorAll("canvas.px")) {{
  const img = new Image();
  img.onload = () => {{ const x = cv.getContext("2d"); x.clearRect(0, 0, 16, 16); x.drawImage(img, 0, 0, 16, 16); }};
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(SVGS[cv.dataset.c][cv.dataset.g]);
}}
</script>
'''

if __name__ == "__main__":
    import sys
    data, wm = build()
    if "--standalone" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--standalone") + 1])
        out.write_text(page(data, wm, standalone=True))
        print("standalone:", out)
    for c in data:
        print(f"\n{c['id']}\n{c['ff']}")
