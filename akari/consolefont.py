#!/usr/bin/python3 -I
"""The console's font gets the two half blocks ▀ and ▄.

Akari draws its mark and the QR code at the console with ▀ ▄ █ (console.py,
motd.py). The kernel's own font has all three, but Debian's console fonts,
which the installer sets up (console-setup: Lat15, Uni2, … in Fixed,
Terminus or VGA), have only █: the QR code came out as a field of diamonds.

So at boot, after console-setup, akari-console-font.service takes the font
that is loaded, gives two glyphs nobody at a Linux console misses (the light
and dark shade ░ ▓, else ⌂ ¤ ⌐) to ▀ and ▄, and loads it again, on every
console. A font that has them already (the kernel's, one chosen by hand) is
left as it is. The rest of the font, and which font it is, stays the choice
of whoever set it up.

    python3 consolefont.py IN OUT    patch a font file (PSF 1 or 2)
    python3 consolefont.py --apply   as the service does: tty1 to tty6
"""

from __future__ import annotations

import gzip
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

UPPER, LOWER = 0x2580, 0x2584
SPARE = (0x2591, 0x2593, 0x2302, 0x00A4, 0x2310)      # ░ ▓ ⌂ ¤ ⌐, in the order they are given up

PSF1 = b"\x36\x04"
PSF2 = b"\x72\xb5\x4a\x86"


class FontError(ValueError):
    pass


class Font:
    """A console font: glyph bitmaps and, per glyph, the code points it stands for
    (sequences, which only a few fonts have, are kept as they are)."""

    def __init__(self, raw: bytes):
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        if raw[:2] == PSF1:
            self.v, mode, self.charsize = 1, raw[2], raw[3]
            self.count, self.height, self.width = (512 if mode & 1 else 256), self.charsize, 8
            off, has_table = 4, bool(mode & 6)
            self.mode = mode
        elif raw[:4] == PSF2:
            _, _, hsize, flags, self.count, self.charsize, self.height, self.width = struct.unpack("<4sIIIIIII", raw[:32])
            self.v, off, has_table = 2, hsize, bool(flags & 1)
        else:
            raise FontError("kein PSF-Font")
        self.glyphs = [raw[off + i * self.charsize: off + (i + 1) * self.charsize] for i in range(self.count)]
        self.codes: list[list[int]] = [[] for _ in range(self.count)]
        self.seqs: list[bytes] = [b"" for _ in range(self.count)]
        if not has_table:
            raise FontError("der Font hat keine Unicode-Tabelle")
        self._read_table(raw[off + self.count * self.charsize:])

    def _read_table(self, t: bytes) -> None:
        i = pos = 0
        if self.v == 1:
            while i < self.count and pos + 1 < len(t):
                while pos + 1 < len(t) and (u := struct.unpack_from("<H", t, pos)[0]) not in (0xFFFF, 0xFFFE):
                    self.codes[i].append(u)
                    pos += 2
                sq = pos
                while pos + 1 < len(t) and struct.unpack_from("<H", t, pos)[0] != 0xFFFF:
                    pos += 2
                self.seqs[i] = t[sq:pos]
                pos += 2
                i += 1
        else:
            for i, entry in enumerate(t.split(b"\xff")[: self.count]):
                single = entry.split(b"\xfe", 1)[0]
                self.codes[i] = [ord(c) for c in single.decode("utf-8", "replace")]
                self.seqs[i] = entry[len(single):]

    def has(self, cp: int) -> bool:
        return any(cp in c for c in self.codes)

    def _row_bytes(self) -> int:
        return (self.width + 7) // 8

    def _half(self, upper: bool) -> bytes:
        rb, h = self._row_bytes(), self.height
        rows = [b"\xff" * rb if (r < h // 2) == upper else b"\x00" * rb for r in range(h)]
        return b"".join(rows).ljust(self.charsize, b"\x00")

    def patch(self) -> bool:
        """Give spare glyphs to ▀ and ▄; False when there is nothing to do."""
        want = [cp for cp in (UPPER, LOWER) if not self.has(cp)]
        if not want:
            return False
        spare = [i for cp in SPARE for i, c in enumerate(self.codes) if c == [cp] and not self.seqs[i]]
        if len(spare) < len(want):
            raise FontError("kein freier Platz im Font")
        for cp, i in zip(want, spare):
            self.glyphs[i] = self._half(cp == UPPER)
            self.codes[i] = [cp]
        return True

    def dump(self) -> bytes:
        body = b"".join(self.glyphs)
        if self.v == 1:
            table = b"".join(b"".join(struct.pack("<H", u) for u in c) + s + b"\xff\xff" for c, s in zip(self.codes, self.seqs))
            return PSF1 + bytes([self.mode | 2, self.charsize]) + body + table
        table = b"".join("".join(map(chr, c)).encode() + s + b"\xff" for c, s in zip(self.codes, self.seqs))
        return struct.pack("<4sIIIIIII", PSF2, 0, 32, 1, self.count, self.charsize, self.height, self.width) + body + table


def apply() -> int:
    """tty1 to tty6 (console-setup's ACTIVE_CONSOLES): the font each has, with the two half blocks."""
    done = 0
    with tempfile.TemporaryDirectory() as d:
        for n in range(1, 7):
            tty, cur, new = f"/dev/tty{n}", Path(d, f"{n}.psf"), Path(d, f"{n}.new.psf")
            try:
                if subprocess.run(["setfont", "-C", tty, "-O", str(cur)], capture_output=True).returncode or not cur.exists():
                    continue
            except FileNotFoundError:             # no kbd, so no console-setup either: the kernel's font has them
                return done
            try:
                f = Font(cur.read_bytes())
                if not f.patch():
                    continue
            except FontError as e:
                print(f"{tty}: {e}", file=sys.stderr)
                continue
            new.write_bytes(f.dump())
            if subprocess.run(["setfont", "-C", tty, str(new)], capture_output=True).returncode == 0:
                done += 1
    return done


if __name__ == "__main__":
    if sys.argv[1:] == ["--apply"]:
        print(f"Halbblöcke auf {apply()} Konsolen")
    elif len(sys.argv) == 3:
        f = Font(Path(sys.argv[1]).read_bytes())
        f.patch()
        Path(sys.argv[2]).write_bytes(f.dump())
    else:
        sys.exit(__doc__)
