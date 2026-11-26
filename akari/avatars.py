"""Account pictures. akarid keeps them in /var/lib/akari/avatars/<name>.png.

Every upload is decoded with Pillow, cropped to a centred square, scaled to
256 px and written as a new PNG: what is served is always a plain picture
Akari made itself, without the uploader's metadata or anything smuggled in
the file. The login screen shows them before anyone signs in, so they are
served without a session (like any display manager shows its faces)."""

from __future__ import annotations

import io
import os

from PIL import Image, ImageOps

from . import config

DIR = config.SYSTEM / "avatars"
SIZE = 256
MAX_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 40_000_000      # a 40-megapixel photo is plenty; more is a decompression bomb


class AvatarError(ValueError):
    pass


def path(name: str):
    return DIR / f"{name}.png"


def save(name: str, data: bytes) -> None:
    if len(data) > MAX_BYTES:
        raise AvatarError("Das Bild ist größer als 10 MB.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in ("JPEG", "PNG", "WEBP", "GIF"):
                raise AvatarError("Bitte ein JPEG, PNG, WebP oder GIF.")
            im.seek(0)
            im = ImageOps.exif_transpose(im).convert("RGBA")
            im = ImageOps.fit(im, (SIZE, SIZE), Image.LANCZOS, centering=(0.5, 0.4))
            out = io.BytesIO()
            im.save(out, "PNG", optimize=True)
    except AvatarError:
        raise
    except Exception:
        raise AvatarError("Das ist kein Bild, das sich lesen lässt.")
    DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DIR, 0o700)
    tmp = path(name).with_suffix(".tmp")
    tmp.write_bytes(out.getvalue())
    os.replace(tmp, path(name))


def remove(name: str) -> None:
    try:
        path(name).unlink()
    except FileNotFoundError:
        pass
