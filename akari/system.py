"""The workspace about itself, and the desktop's preferences.

Preferences are the person's, so they live in the home folder and follow
them to any browser: one file per desktop
(~/.config/akari/desktops/<id>/prefs.json), so each desktop can look its own;
~/.config/akari/prefs.json is the account's fallback."""

from __future__ import annotations

import json
import os
import shutil
import time

from fastapi import APIRouter, HTTPException, Request

from . import config, desktops, display

router = APIRouter(prefix="/api")
PREFS_MAX = 16 * 1024


def _prefs_file(did: str | None):
    return (desktops.folder(did) if did else config.CONFIG) / "prefs.json"


def read_prefs(did: str | None) -> dict:
    for f in ([_prefs_file(did)] if did else []) + [_prefs_file(None)]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            continue
    return {}


def write_prefs(did: str | None, data: dict) -> None:
    f = _prefs_file(did)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


@router.get("/prefs")
def get_prefs(request: Request) -> dict:
    return read_prefs(desktops.current(request))


@router.put("/prefs")
async def put_prefs(request: Request) -> dict:
    raw = await request.body()
    if len(raw) > PREFS_MAX:
        raise HTTPException(413, "Zu viele Einstellungen.")
    try:
        data = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Kein JSON.")
    if not isinstance(data, dict):
        raise HTTPException(400, "Erwartet ein Objekt.")
    write_prefs(desktops.current(request), data)
    return {"ok": True}


def _du(path) -> int:
    total = 0
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def _os_name() -> str:
    try:
        for line in open("/etc/os-release", encoding="utf-8"):
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "Linux"


def _mem() -> dict:
    info = {}
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0]) * 1024
    except OSError:
        return {}
    return {"total": info.get("MemTotal"), "available": info.get("MemAvailable")}


@router.get("/system")
def system() -> dict:
    disk = shutil.disk_usage(config.HOME)
    return {
        "version": config.VERSION,
        "name": config.NAME,
        "hostname": config.HOSTNAME,
        "os": _os_name(),
        "kernel": os.uname().release,
        "home": str(config.HOME),
        "home_bytes": _du(config.HOME),
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
        "memory": _mem(),
        "uptime": int(time.time() - config.STARTED),
        "processes": sum(1 for p in os.listdir("/proc") if p.isdigit()),
        "apps": display.available(),
        "managed_by": os.environ.get("AKARI_MANAGED_BY") or None,
    }


# ---------- the desktop's own picture ----------
# Raster images only, recognised by their first bytes, never by the name: an
# SVG may carry script and would run with the session on this origin.

from starlette.datastructures import UploadFile                    # noqa: E402  (what request.form() returns)
from fastapi.responses import FileResponse, Response                # noqa: E402

WALL_MAX = 25 * 1024 * 1024
KINDS = ((b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG\r\n\x1a\n", "image/png"), (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"))


def _kind(head: bytes) -> str | None:
    for magic, mime in KINDS:
        if head.startswith(magic):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def _wall(did: str | None):
    return (desktops.folder(did) if did else config.CONFIG) / "wallpaper"


@router.post("/wallpaper")
async def put_wallpaper(request: Request) -> dict:
    form = await request.form(max_files=1)
    f = form.get("file")
    if not isinstance(f, UploadFile):
        raise HTTPException(400, "Kein Bild.")
    data = await f.read(WALL_MAX + 1)
    if len(data) > WALL_MAX:
        raise HTTPException(413, "Das Bild ist größer als 25 MB.")
    if not _kind(data[:16]):
        raise HTTPException(415, "Das ist kein Bild (JPEG, PNG, WebP oder GIF).")
    path = _wall(desktops.current(request))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return {"ok": True, "v": int(time.time())}


@router.get("/wallpaper")
def get_wallpaper(request: Request) -> Response:
    path = _wall(desktops.current(request))
    try:
        with open(path, "rb") as fh:
            mime = _kind(fh.read(16))
    except OSError:
        raise HTTPException(404, "Kein Bild.")
    if not mime:
        raise HTTPException(404, "Kein Bild.")
    return FileResponse(path, media_type=mime, headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox",
                                                        "Cache-Control": "private, max-age=31536000"})


@router.delete("/wallpaper")
def delete_wallpaper(request: Request) -> dict:
    try:
        _wall(desktops.current(request)).unlink()
    except FileNotFoundError:
        pass
    return {"ok": True}
