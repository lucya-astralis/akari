"""Draws the lucya.systems eagle as half-block text for fastfetch.
python3 tools/logo.py [width] > image/rootfs/usr/share/akari/fastfetch/logo.txt
Wings in $1 (the accent), head and tail in $2 (white): fastfetch colour slots."""
import re, sys

PATHS = {  # from assets/logo/lucya_logo.svg, viewBox 0 0 964 543
    "wing": ["M112,148L260,217L409.69,379.66L467.26,264.53L400,222.08L400,204.02L0,0L112,148Z",
             "M964,0L564,204.02L564,222.08L496.74,264.53L554.31,379.66L704,217L852,148L964,0Z",
             "M172.93,266.68L315.8,308.65L247.36,234.28L59.81,146.84L172.93,266.68Z",
             "M904.19,146.84L716.64,234.28L648.2,308.65L791.07,266.68L904.19,146.84Z",
             "M289.78,367.82L400.19,400.35L343.4,338.64L191.3,293.96L289.78,367.82Z",
             "M772.7,293.96L620.6,338.64L563.81,400.35L674.22,367.82L772.7,293.96Z"],
    "body": ["M518,67L415,100L403,120L454,122L421,210.5L482,249L543,210.5L538,85L518,67Z",
             "M482,282L544.5,407L482,543L419.5,407L482,282Z"],
}
polys = {k: [[tuple(map(float, p.split(","))) for p in re.findall(r"[\d.]+,[\d.]+", d)] for d in v] for k, v in PATHS.items()}

def inside(x, y, poly):
    c = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c

W = int(sys.argv[1]) if len(sys.argv) > 1 else 40
H = round(W * 543 / 964)          # pixels; two per text row
S = 4                              # supersampling
def px(i, j):
    best, cov = None, 0
    for kind, ps in polys.items():
        n = sum(inside((i + (a + .5) / S) * 964 / W, (j + (b + .5) / S) * 543 / H, p) for p in ps for a in range(S) for b in range(S))
        if n > cov:
            best, cov = kind, n
    return best if cov >= S * S * .42 else None

grid = [[px(i, j) for i in range(W)] for j in range(H + (H % 2))]
COL = {"wing": "$1", "body": "$2"}
out = []
for r in range(0, len(grid), 2):
    line, cur = "", None
    for i in range(W):
        t, b = grid[r][i], grid[r + 1][i]
        if t and b and t != b:     # two colours in one cell: the body wins, it is the smaller shape
            t = b = "body"
        kind = t or b
        ch = " " if not kind else "█" if t and b else "▀" if t else "▄"
        if kind and COL[kind] != cur:
            cur = COL[kind]; line += cur
        line += ch
    out.append(line.rstrip())
print("\n".join(out))
