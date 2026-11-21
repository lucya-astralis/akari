"""What plays on a desktop, for the media section in the taskbar. Runs in the agent.

Linux players announce themselves over D-Bus (MPRIS): Firefox does for every
tab with sound, so do mpv, VLC, Spotify. Each desktop gets a session bus of
its own (a socket in the user's 0700 run folder), and every app and terminal
started on that desktop gets its address. playerctl follows the players on it;
what it reports goes to the desktop's page as an event "media", and the
taskbar's buttons come back here as playerctl commands.

The cover is served from here, never as the player's own URL: a file:// cover
only when it belongs to this user and is an image, an http(s) one fetched
with a size limit. Sound itself does not reach the browser yet."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from . import config, desktops

router = APIRouter(prefix="/api/media")

BUSES: dict[str, asyncio.subprocess.Process] = {}
WATCHERS: dict[str, asyncio.Task] = {}
STATE: dict[str, dict] = {}            # desktop → what plays (or {"playing": None})
_lock = asyncio.Lock()
ART_MAX = 5 * 1024 * 1024
FMT = "\t".join(("{{playerName}}", "{{status}}", "{{xesam:title}}", "{{xesam:artist}}", "{{xesam:album}}", "{{mpris:artUrl}}"))
ACTIONS = {"play-pause", "next", "previous", "play", "pause"}


def _bus_path(did: str) -> Path:
    return config.user_run(os.getuid()) / f"bus-{did}"


def _address(did: str) -> str:
    return f"unix:path={_bus_path(did)}"


async def env(did: str | None) -> dict:
    """DBUS_SESSION_BUS_ADDRESS for something started on this desktop; starts the bus if needed."""
    if not did or not shutil.which("dbus-daemon"):
        return {}
    async with _lock:
        p = BUSES.get(did)
        if not p or p.returncode is not None:
            path = _bus_path(did)
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
            p = await asyncio.create_subprocess_exec(
                "dbus-daemon", "--session", f"--address={_address(did)}", "--nofork", "--nopidfile", "--nosyslog",
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(config.HOME)})
            BUSES[did] = p
            for _ in range(50):           # the socket appears within a few milliseconds
                if path.exists():
                    break
                await asyncio.sleep(0.02)
        if did not in WATCHERS or WATCHERS[did].done():
            WATCHERS[did] = asyncio.create_task(_follow(did))
    return {"DBUS_SESSION_BUS_ADDRESS": _address(did)}


def _parse(line: str) -> dict:
    parts = line.rstrip("\n").split("\t")
    if len(parts) < 6 or not parts[0]:
        return {"playing": None}
    player, status, title, artist, album, art = parts[:6]
    if status not in ("Playing", "Paused"):
        return {"playing": None}
    return {"playing": {
        "player": player, "status": status.lower(), "title": title, "artist": artist, "album": album,
        "art": hashlib.sha1(art.encode()).hexdigest()[:12] if art else None,
        "_art": art,
    }}


def public(state: dict) -> dict:
    p = state.get("playing")
    return {"playing": {k: v for k, v in p.items() if not k.startswith("_")} if p else None}


async def _follow(did: str) -> None:
    """playerctl follows the players on this desktop's bus; it restarts if it ends."""
    if not shutil.which("playerctl"):
        return
    e = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(config.HOME), "DBUS_SESSION_BUS_ADDRESS": _address(did)}
    while did in BUSES and BUSES[did].returncode is None:
        p = await asyncio.create_subprocess_exec(
            "playerctl", "--follow", "metadata", "--format", FMT,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=e)
        try:
            async for raw in p.stdout:
                st = _parse(raw.decode(errors="replace"))
                if st != STATE.get(did):
                    STATE[did] = st
                    from . import display
                    display._publish(did, {"type": "media", **public(st)})
        finally:
            with contextlib.suppress(ProcessLookupError):
                p.kill()
            await p.wait()
        await asyncio.sleep(1.0)


def current(did: str | None) -> dict:
    return public(STATE.get(did or "", {"playing": None}))


@router.post("/{action}")
async def control(action: str, request: Request) -> dict:
    if action not in ACTIONS:
        raise HTTPException(404, "Gibt es nicht.")
    did = desktops.need(request)
    if did not in BUSES or not shutil.which("playerctl"):
        raise HTTPException(409, "Hier spielt nichts.")
    p = await asyncio.create_subprocess_exec(
        "playerctl", action, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "DBUS_SESSION_BUS_ADDRESS": _address(did)})
    await p.wait()
    return {"ok": p.returncode == 0}


@router.get("/art")
async def art(request: Request) -> Response:
    from .system import _kind
    did = desktops.need(request)
    url = ((STATE.get(did) or {}).get("playing") or {}).get("_art") or ""
    u = urlparse(url)
    data = b""
    if u.scheme == "file":
        path = Path(unquote(u.path))
        try:
            st = path.stat()
            if path.is_file() and st.st_uid == os.getuid() and st.st_size <= ART_MAX:
                data = path.read_bytes()
        except OSError:
            pass
    elif u.scheme in ("http", "https"):
        import httpx
        with contextlib.suppress(Exception):
            async with httpx.AsyncClient(timeout=6, follow_redirects=True) as c:
                async with c.stream("GET", url) as r:
                    if r.status_code == 200:
                        async for chunk in r.aiter_bytes():
                            data += chunk
                            if len(data) > ART_MAX:
                                data = b""
                                break
    kind = _kind(data[:16]) if data else None
    if not kind:
        raise HTTPException(404, "Kein Cover.")
    return Response(data, media_type=kind, headers={
        "Cache-Control": "private, max-age=3600", "Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"})


async def stop(did: str) -> None:
    t = WATCHERS.pop(did, None)
    p = BUSES.pop(did, None)
    if t:
        t.cancel()
    if p and p.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            p.terminate()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(p.wait(), 2)
    STATE.pop(did, None)
    with contextlib.suppress(FileNotFoundError):
        _bus_path(did).unlink()


async def stop_all() -> None:
    for did in list(BUSES):
        await stop(did)
