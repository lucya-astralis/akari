"""Linux GUI apps in Akari windows. Runs in the session agent, as the user.

Every app gets a display of its own: an Xvnc server (TigerVNC) the size of
its Akari window, a window manager that keeps the app filling it (matchbox:
one window at a time, dialogs centred on top), and the app. The browser
draws the display with noVNC; the stream reaches it through akarid and this
agent, never through a published port.

Several accounts share the container, so nobody may reach another's display:
  - VNC listens only on a Unix socket in the user's 0700 run folder
    (-rfbport -1, -rfbunixpath, mode 0600), never on TCP;
  - the X server only takes clients with the user's MIT cookie (-auth), so
    another account cannot connect to :N and read the screen or the keys.

When the app exits, its display goes with it. Closing the window ends the app."""

from __future__ import annotations

import asyncio
import contextlib
import os
import secrets
import shutil
import signal
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from . import config, desktopfiles, desktops, media

router = APIRouter(prefix="/api/display")

# The apps Akari knows how to start. Only these: the browser names an id, never a command.
APPS: dict[str, dict] = {
    "firefox": {"title": "Firefox", "cmd": ["firefox-esr"], "single": True},
    # Akari has its own terminal: XTerm only shows when "Alle Programme zeigen" is on
    "xterm": {"title": "XTerm", "cmd": ["xterm", "-fa", "JetBrains Mono,DejaVu Sans Mono", "-fs", "11"], "single": False, "extra": True},
}

FIRST, LAST = 10, 199


@dataclass
class Session:
    id: str
    app: str
    desktop: str
    display: int
    sock: Path
    xauth: Path
    procs: list[asyncio.subprocess.Process] = field(default_factory=list)
    ended: asyncio.Event = field(default_factory=asyncio.Event)
    viewer: asyncio.Event | None = None      # one viewer per app: a newer one takes over
    kind: str = "app"                         # "app": one app, its own display; "default": the desktop's display
    windows: list[dict] = field(default_factory=list)   # default display: the X windows open on it
    active: str | None = None


SESSIONS: dict[str, Session] = {}


def _run() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or config.user_run(os.getuid()))


# an Akari tile for a program without a picture of its own, by what it is
ART = [("TerminalEmulator", "xterm"), ("WebBrowser", "web"), ("TextEditor", "editor"), ("FileManager", "files"),
       ("Monitor", "monitor"), ("Settings", "settings"), ("System", "settings")]


def _art(cats: list[str]) -> str:
    return next((a for c, a in ART if c in cats), "window")


def available() -> list[dict]:
    """Akari's own Linux apps, then every installed program with a .desktop file ("d:<id>")."""
    out = [{"id": k, "title": v["title"], "single": v["single"], "extra": v.get("extra", False)}
           for k, v in APPS.items() if shutil.which(v["cmd"][0])]
    for did, e in sorted(desktopfiles.apps().items(), key=lambda kv: kv[1]["title"].casefold()):
        out.append({"id": f"d:{did}", "title": e["title"], "comment": e["comment"], "single": False, "terminal": e["terminal"],
                    "icon": f"/api/display/icon/{did}" if desktopfiles.icon(e["icon"]) else None,
                    "art": _art(e["categories"]), "keywords": e["keywords"], "extra": e["extra"]})
    return out


def _spec(app: str) -> dict | None:
    if app in APPS:
        return APPS[app] if shutil.which(APPS[app]["cmd"][0]) else None
    if app.startswith("d:"):
        e = desktopfiles.apps().get(app[2:])
        if e and not e["terminal"]:
            return {"title": e["title"], "cmd": e["cmd"], "single": False}
    return None


def _title(s: "Session") -> str:
    spec = _spec(s.app) if s.app != "desktop" else None
    return spec["title"] if spec else "Linux-Apps"


def _taken(n: int) -> bool:
    # displays are shared across the container (abstract X sockets, lock files in /tmp)
    return any(s.display == n for s in SESSIONS.values()) or os.path.exists(f"/tmp/.X{n}-lock")


def _log(name: str):
    config.CACHE.mkdir(parents=True, exist_ok=True)
    return open(config.CACHE / f"{name}.log", "ab", buffering=0)


async def _spawn(cmd: list[str], env: dict, log: str) -> asyncio.subprocess.Process:
    with _log(log) as fh:
        return await asyncio.create_subprocess_exec(
            *cmd, env=env, cwd=config.HOME, stdin=asyncio.subprocess.DEVNULL,
            stdout=fh, stderr=fh, start_new_session=True)


async def _wait_socket(sock: Path, proc: asyncio.subprocess.Process, timeout: float = 8.0) -> bool:
    for _ in range(int(timeout / 0.1)):
        if proc.returncode is not None:
            return False
        if sock.exists():
            with contextlib.suppress(OSError):
                _r, w = await asyncio.open_unix_connection(str(sock))
                w.close()
                return True
        await asyncio.sleep(0.1)
    return False


async def _stop(s: Session) -> None:
    for p in reversed(s.procs):            # app first, then the window manager, then X
        if p.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(p.pid, signal.SIGTERM)
    for p in reversed(s.procs):
        try:
            await asyncio.wait_for(p.wait(), 3)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(p.pid, signal.SIGKILL)
            await p.wait()
    SESSIONS.pop(s.id, None)
    for f in (s.sock, s.xauth):
        with contextlib.suppress(FileNotFoundError):
            f.unlink()
    s.ended.set()


async def _watch(s: Session, app: asyncio.subprocess.Process) -> None:
    await app.wait()
    await _stop(s)


async def _xauth(path: Path, n: int) -> None:
    cookie = secrets.token_hex(16)
    path.touch(mode=0o600)
    p = await asyncio.create_subprocess_exec("xauth", "-q", "-f", str(path), "add", f":{n}", "MIT-MAGIC-COOKIE-1", cookie,
                                             stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    if await p.wait() != 0:
        raise HTTPException(500, "Das X-Cookie ließ sich nicht anlegen.")


class LaunchIn(BaseModel):
    w: int = 1024
    h: int = 700


@router.get("/apps")
def apps(request: Request) -> dict:
    did = desktops.current(request)
    return {"apps": available(),
            "running": [{"id": s.id, "app": s.app} for s in SESSIONS.values() if s.desktop == did and s.kind == "app"],
            "default": _state(next((s for s in SESSIONS.values() if s.desktop == did and s.kind == "default"), None))}


@router.get("/icon/{did}")
def app_icon(did: str):
    """A program's picture from the icon theme. Served sandboxed: an SVG could carry script."""
    from fastapi.responses import FileResponse
    e = desktopfiles.apps().get(did)
    p = desktopfiles.icon(e["icon"]) if e else None
    if not p:
        raise HTTPException(404, "Kein Symbol.")
    return FileResponse(p, media_type="image/svg+xml" if p.suffix == ".svg" else "image/png",
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox", "Cache-Control": "private, max-age=86400"})


@router.get("/{sid}")
def state(sid: str) -> dict:
    s = SESSIONS.get(sid)
    return {"running": bool(s), "viewed": bool(s and s.viewer)}


async def _start_display(s: Session, w: int, h: int, env: dict) -> bool:
    await _xauth(s.xauth, s.display)
    x = await _spawn([
        "Xvnc", f":{s.display}", "-geometry", f"{w}x{h}", "-depth", "24",
        "-auth", str(s.xauth), "-nolisten", "tcp",
        "-rfbport", "-1", "-rfbunixpath", str(s.sock), "-rfbunixmode", "0600",
        "-SecurityTypes", "None", "-AlwaysShared", "-desktop", _title(s), "-FrameRate", "60",
        # only a real copy (CLIPBOARD) reaches Akari, not every selection (PRIMARY)
        "-SendPrimary=0",
    ], env, f"xvnc-{s.display}")
    s.procs.append(x)
    if await _wait_socket(s.sock, x):
        return True
    await _stop(s)
    return False


@router.post("/{app}")
async def launch(app: str, body: LaunchIn, request: Request) -> dict:
    spec = _spec(app)
    if not spec:
        raise HTTPException(404, "Diese App gibt es hier nicht.")
    did = desktops.need(request)
    if spec["single"]:      # once per desktop
        for s in SESSIONS.values():
            if s.app == app and s.desktop == did:
                return {"id": s.id, "app": app, "title": spec["title"], "running": True}
    cmd = list(spec["cmd"])
    if app == "firefox":    # each desktop its own profile: two Firefox cannot share one
        profile = desktops.folder(did) / "firefox"
        profile.mkdir(parents=True, exist_ok=True)
        cmd += ["--profile", str(profile), "--no-remote"]
    w, h = max(320, min(body.w, 3840)), max(240, min(body.h, 2160))
    run = _run()
    env = {
        "HOME": str(config.HOME), "USER": config.NAME, "LOGNAME": config.NAME, "SHELL": config.SHELL,
        "LANG": os.environ.get("LANG", "C.UTF-8"), "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "XDG_RUNTIME_DIR": str(run), "XDG_CACHE_HOME": str(config.HOME / ".cache"),
        "XDG_CURRENT_DESKTOP": "Akari", "XDG_SESSION_TYPE": "x11",
        "MOZ_ENABLE_WAYLAND": "0", "NO_AT_BRIDGE": "1",
        **await media.env(did),     # players on this desktop show in its taskbar
    }
    # a display number another account grabbed between our check and Xvnc's start: take the next
    for n in range(FIRST, LAST + 1):
        if _taken(n):
            continue
        sid = secrets.token_urlsafe(9)
        s = Session(id=sid, app=app, desktop=did, display=n, sock=run / f"vnc-{n}.sock", xauth=run / f"xauth-{n}")
        SESSIONS[sid] = s
        env_x = {**env, "DISPLAY": f":{n}", "XAUTHORITY": str(s.xauth)}
        try:
            if not await _start_display(s, w, h, env_x):
                continue
            if shutil.which("matchbox-window-manager"):
                s.procs.append(await _spawn(["matchbox-window-manager", "-use_titlebar", "no", "-use_cursor", "yes"], env_x, f"wm-{n}"))
            app_proc = await _spawn(cmd, env_x, app)
            s.procs.append(app_proc)
        except BaseException:
            await _stop(s)
            raise
        asyncio.create_task(_watch(s, app_proc))
        return {"id": s.id, "app": app, "title": spec["title"], "running": False}
    raise HTTPException(503, "Kein Display mehr frei. Mehr in ~/.cache/akari.")


@router.delete("/{sid}")
async def close(sid: str) -> dict:
    s = SESSIONS.get(sid)
    if s and s.kind == "default":
        await _end_clients(s)        # the programs go, the display stays for the next one
    elif s:
        await _stop(s)
    return {"ok": True}


@router.websocket("/{sid}/ws")
async def stream(ws: WebSocket, sid: str) -> None:
    """VNC over the websocket, both ways, bytes untouched."""
    s = SESSIONS.get(sid)
    if not s:
        await ws.close(code=4404)
        return
    proto = "binary" if "binary" in ws.scope.get("subprotocols", []) else None
    await ws.accept(subprotocol=proto)
    try:
        reader, writer = await asyncio.open_unix_connection(str(s.sock))
    except OSError:
        await ws.close(code=1011)
        return

    async def up() -> None:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            writer.write(msg.get("bytes") or (msg.get("text") or "").encode())
            await writer.drain()

    async def down() -> None:
        while (data := await reader.read(65536)):
            await ws.send_bytes(data)

    if s.viewer:
        s.viewer.set()            # the previous viewer lets go
    mine = s.viewer = asyncio.Event()
    tasks = [asyncio.create_task(up()), asyncio.create_task(down()),
             asyncio.create_task(s.ended.wait()), asyncio.create_task(mine.wait())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:
            t.cancel()
        if s.viewer is mine:
            s.viewer = None
        writer.close()
        with contextlib.suppress(Exception):
            await ws.close(code=4000 if s.ended.is_set() else 1000)


async def end(s: Session) -> None:
    await _stop(s)


# ---------- the desktop's default display ----------
# Every terminal on a desktop has DISPLAY set to it, so whatever starts there
# with a window (firefox, gimp, xeyes) shows up in Akari: the desktop opens a
# window "Linux-Apps" as soon as an X window maps, and closes it when the
# last one goes.

EVENTS: dict[str, set[asyncio.Queue]] = {}
_default_lock = asyncio.Lock()


def _state(s: Session | None) -> dict | None:
    if not s:
        return None
    return {"sid": s.id, "display": s.display, "windows": s.windows, "active": s.active}


def _publish(did: str, msg: dict) -> None:
    for q in list(EVENTS.get(did, ())):
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(msg)


def _x_env(s: Session) -> dict:
    return {"DISPLAY": f":{s.display}", "XAUTHORITY": str(s.xauth)}


async def _xprop(s: Session, *args: str) -> str:
    env = {**os.environ, **_x_env(s)}
    p = await asyncio.create_subprocess_exec("xprop", *args, env=env, stdout=asyncio.subprocess.PIPE,
                                             stderr=asyncio.subprocess.DEVNULL)
    out, _ = await p.communicate()
    return out.decode(errors="replace")


def _ids(line: str) -> list[str]:
    return [w.strip() for w in line.split("#", 1)[1].split(",") if w.strip().startswith("0x")] if "#" in line else []


async def _windows(s: Session) -> tuple[list[dict], str | None]:
    root = await _xprop(s, "-root", "_NET_CLIENT_LIST", "_NET_ACTIVE_WINDOW")
    ids, active = [], None
    for line in root.splitlines():
        if line.startswith("_NET_CLIENT_LIST"):
            ids = _ids(line)
        elif line.startswith("_NET_ACTIVE_WINDOW"):
            a = _ids(line)
            active = a[0] if a and a[0] != "0x0" else None
    wins = []
    for wid in ids:
        out = await _xprop(s, "-id", wid, "_NET_WM_NAME", "WM_NAME")
        title = ""
        for line in out.splitlines():
            if "=" in line and ("_NET_WM_NAME" in line or ("WM_NAME" in line and not title)):
                title = line.split("=", 1)[1].strip().strip('"')
                if "_NET_WM_NAME" in line:
                    break
        wins.append({"id": wid, "title": title or "Fenster"})
    return wins, active


async def _watch_default(s: Session) -> None:
    """Which X windows are open on the default display; tell the desktop when that changes."""
    last = None
    while not s.ended.is_set():
        try:
            wins, active = await _windows(s)
        except Exception:
            wins, active = s.windows, s.active
        now = (tuple((w["id"], w["title"]) for w in wins), active)
        if now != last:
            last = now
            s.windows, s.active = wins, active
            _publish(s.desktop, {"type": "xdisplay", **_state(s)})
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(s.ended.wait(), 1.0)


async def ensure_default(did: str, w: int = 1280, h: int = 800) -> Session:
    async with _default_lock:
        for s in SESSIONS.values():
            if s.desktop == did and s.kind == "default" and not s.ended.is_set():
                return s
        run = _run()
        env = {
            "HOME": str(config.HOME), "USER": config.NAME, "LANG": os.environ.get("LANG", "C.UTF-8"),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "XDG_RUNTIME_DIR": str(run),
            **await media.env(did),
        }
        for n in range(FIRST, LAST + 1):
            if _taken(n):
                continue
            s = Session(id=secrets.token_urlsafe(9), app="desktop", desktop=did, display=n,
                        sock=run / f"vnc-{n}.sock", xauth=run / f"xauth-{n}", kind="default")
            SESSIONS[s.id] = s
            if not await _start_display(s, w, h, {**env, **_x_env(s)}):
                continue
            if shutil.which("matchbox-window-manager"):
                s.procs.append(await _spawn(["matchbox-window-manager", "-use_titlebar", "no", "-use_cursor", "yes"],
                                            {**env, **_x_env(s)}, f"wm-{n}"))
            asyncio.create_task(_watch_default(s))
            return s
        raise RuntimeError("Kein Display mehr frei.")


def default_env(did: str | None) -> dict:
    """DISPLAY and XAUTHORITY for a shell on this desktop, if its default display runs."""
    for s in SESSIONS.values():
        if s.desktop == did and s.kind == "default" and not s.ended.is_set():
            return _x_env(s)
    return {}


async def _end_clients(s: Session) -> None:
    """End every program showing on this display (not the X server, not the window manager)."""
    keep = {p.pid for p in s.procs}
    mine = os.getuid()
    want = f"DISPLAY=:{s.display}".encode()
    victims = []
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) in keep or int(d) == os.getpid():
            continue
        try:
            if os.stat(f"/proc/{d}").st_uid != mine:
                continue
            with open(f"/proc/{d}/environ", "rb") as f:
                if want in f.read().split(b"\0"):
                    victims.append(int(d))
        except OSError:
            continue
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in victims:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(pid, sig)
        await asyncio.sleep(1.0)
        victims = [p for p in victims if os.path.exists(f"/proc/{p}")]
        if not victims:
            break


class RaiseIn(BaseModel):
    id: str


@router.post("/{sid}/raise")
async def raise_window(sid: str, body: RaiseIn) -> dict:
    s = SESSIONS.get(sid)
    if not s or s.kind != "default" or not body.id.startswith("0x"):
        raise HTTPException(404, "Gibt es nicht.")
    p = await asyncio.create_subprocess_exec("wmctrl", "-i", "-a", body.id, env={**os.environ, **_x_env(s)},
                                             stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    await p.wait()
    return {"ok": True}


events = APIRouter()


@events.websocket("/api/events")
async def event_stream(ws: WebSocket) -> None:
    """What happens on this desktop, pushed to its page: for now, the default display's windows."""
    did = desktops.current(ws)
    await ws.accept()
    if not did:
        await ws.close(code=4409)
        return
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    EVENTS.setdefault(did, set()).add(q)
    s = next((x for x in SESSIONS.values() if x.desktop == did and x.kind == "default"), None)
    if s:
        await ws.send_json({"type": "xdisplay", **_state(s)})
    await media.env(did)
    await ws.send_json({"type": "media", **media.current(did)})
    recv = asyncio.create_task(ws.receive())
    try:
        while True:
            get = asyncio.create_task(q.get())
            done, _ = await asyncio.wait({get, recv}, return_when=asyncio.FIRST_COMPLETED)
            if recv in done:
                get.cancel()
                break
            await ws.send_json(get.result())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        recv.cancel()
        EVENTS.get(did, set()).discard(q)


async def stop_all() -> None:
    for s in list(SESSIONS.values()):
        await _stop(s)
