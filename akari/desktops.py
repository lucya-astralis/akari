"""Desktops: one account, several separate desktops ("Arbeit", "Spielwiese").
Runs in the session agent, as the user.

A desktop has its own running apps (its own Firefox, with its own profile:
two Firefox cannot share one), its own look (prefs) and its own windows.
akarid tells the agent which desktop a request belongs to with the header
X-Akari-Desktop; only akarid and the user can reach the agent at all."""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from . import config

router = APIRouter(prefix="/api/desktops")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,24}$")
MAX = 12


def _file() -> Path:
    return config.CONFIG / "desktops.json"


def folder(did: str) -> Path:
    return config.CONFIG / "desktops" / did


def load() -> list[dict]:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        return [d for d in data if isinstance(d, dict) and ID_RE.match(str(d.get("id", "")))]
    except (OSError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    config.CONFIG.mkdir(parents=True, exist_ok=True)
    tmp = _file().with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _file())


def current(request) -> str | None:
    """The desktop this request belongs to, if it is a known one."""
    did = request.headers.get("x-akari-desktop") or ""
    return did if ID_RE.match(did) and any(d["id"] == did for d in load()) else None


def need(request) -> str:
    did = current(request)
    if not did:
        raise HTTPException(409, "Kein Desktop gewählt.")
    return did


def _clean(name: str) -> str:
    name = re.sub(r"[\x00-\x1f]", "", name or "").strip()[:40]
    if not name:
        raise HTTPException(400, "Ein Desktop braucht einen Namen.")
    return name


class NameIn(BaseModel):
    name: str


@router.get("")
def listing() -> dict:
    from . import display      # what runs where
    running: dict[str, list[str]] = {}
    for s in display.SESSIONS.values():
        if s.kind == "default":       # the default display: whatever was started from a terminal
            running.setdefault(s.desktop, []).extend(w["title"] for w in s.windows)
        else:
            running.setdefault(s.desktop, []).append(display._title(s))
    items = sorted(load(), key=lambda d: -d.get("last", 0))
    return {"desktops": [{**d, "apps": running.get(d["id"], [])} for d in items]}


@router.post("")
def create(body: NameIn, request: Request) -> dict:
    items = load()
    if len(items) >= MAX:
        raise HTTPException(409, f"Mehr als {MAX} Desktops gehen nicht.")
    now = int(time.time())
    d = {"id": secrets.token_urlsafe(6).replace("-", "x").replace("_", "y"), "name": _clean(body.name), "created": now, "last": now}
    items.append(d)
    _save(items)
    # a new desktop starts with the look of the one it was made from, or the account's
    src = current(request)
    from . import system
    prefs = system.read_prefs(src) if src else system.read_prefs(None)
    if prefs:
        system.write_prefs(d["id"], prefs)
    return d


@router.patch("/{did}")
def rename(did: str, body: NameIn) -> dict:
    items = load()
    for d in items:
        if d["id"] == did:
            d["name"] = _clean(body.name)
            _save(items)
            return d
    raise HTTPException(404, "Diesen Desktop gibt es nicht.")


@router.post("/{did}/touch")
def touch(did: str) -> dict:
    items = load()
    for d in items:
        if d["id"] == did:
            d["last"] = int(time.time())
            _save(items)
            return d
    raise HTTPException(404, "Diesen Desktop gibt es nicht.")


@router.post("/{did}/stop")
async def stop(did: str) -> dict:
    """End every app running on this desktop; the desktop itself stays."""
    from . import display
    n = 0
    for s in [s for s in display.SESSIONS.values() if s.desktop == did]:
        await display.end(s)
        n += 1
    return {"stopped": n}


@router.delete("/{did}")
async def remove(did: str) -> dict:
    items = load()
    if not any(d["id"] == did for d in items):
        raise HTTPException(404, "Diesen Desktop gibt es nicht.")
    await stop(did)
    from . import media
    await media.stop(did)
    _save([d for d in items if d["id"] != did])
    import shutil
    shutil.rmtree(folder(did), ignore_errors=True)
    return {"ok": True}
