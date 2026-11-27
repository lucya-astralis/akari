"""The console font gets ▀ and ▄ in place of spare glyphs (consolefont.py), and nothing else changes."""
import struct

import pytest

from akari import consolefont as cf


def psf1(codes):
    """A 256-glyph PSF 1 font, 16 rows, glyph i filled with byte i, with the given code points per glyph."""
    body = b"".join(bytes([i % 256]) * 16 for i in range(256))
    table = b"".join(b"".join(struct.pack("<H", u) for u in codes.get(i, [0xE000 + i])) + b"\xff\xff" for i in range(256))
    return b"\x36\x04\x02\x10" + body + table


def test_the_half_blocks_take_the_shades():
    raw = psf1({0xB0: [0x2591], 0xB2: [0x2593], 0xDB: [0x2588]})
    f = cf.Font(raw)
    assert cf.Font(raw).dump() == raw            # read and written back, byte for byte
    assert f.patch() is True
    g = cf.Font(f.dump())
    up = next(i for i, c in enumerate(g.codes) if c == [0x2580])
    low = next(i for i, c in enumerate(g.codes) if c == [0x2584])
    assert (up, low) == (0xB0, 0xB2)
    assert g.glyphs[up] == b"\xff" * 8 + b"\x00" * 8 and g.glyphs[low] == b"\x00" * 8 + b"\xff" * 8
    assert g.has(0x2588) and g.glyphs[0x41] == bytes([0x41]) * 16
    assert g.patch() is False                    # once is enough


def test_a_font_with_them_is_left_alone():
    assert cf.Font(psf1({1: [0x2580], 2: [0x2584]})).patch() is False


def test_no_spare_glyph_no_change():
    with pytest.raises(cf.FontError):
        cf.Font(psf1({})).patch()
