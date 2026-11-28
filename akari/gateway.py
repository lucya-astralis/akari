"""akarid: the door of Akari OS. A system service (akarid.service), root with
a narrow set of capabilities, on 127.0.0.1 behind Caddy.

  /                  the desktop when signed in, else the login screen
  /api/login/*       who can sign in, sign in, first-time setup (public)
  /api/session       who is signed in here
  /api/logout        switch user (keep the apps) or sign out (end everything)
  /api/accounts/*    the own account; all accounts for admins
  /api/host/*        the machine: name, network, time, updates, power (host.py)
  /api/docker/*      Docker and Lucent on it, for admins (docker.py)
  everything else under /api is the signed-in person's session agent,
  passed through as it is (HTTP and websockets)."""

from __future__ import annotations

import asyncio
import contextlib
import mimetypes
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask
from websockets.asyncio.client import unix_connect
from websockets.exceptions import ConnectionClosed

from . import accounts, agents, auth, avatars, config, console, docker, host, lucent, roles, services, software, ssh

# style-src allows inline styles: xterm.js writes its theme into a <style> element.
CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
AGENT_PATHS = ("/api/fs", "/api/prefs", "/api/welcome", "/api/weather", "/api/system", "/api/display", "/api/term", "/api/desktops", "/api/ssh/keys", "/api/stats", "/api/procs", "/api/wallpaper", "/api/media", "/api/audio")
DESKTOP_HEADER = "X-Akari-Desktop"
PASS_HEADERS = ("content-type", "content-length", "content-disposition", "content-security-policy", "x-content-type-options", "cache-control",
                "accept-ranges", "content-range")   # the music player jumps within a track


@asynccontextmanager
async def lifespan(_app: FastAPI):
    accounts.init()
    await ssh.boot()
    watch = asyncio.create_task(console.watch())
    yield
    watch.cancel()
    # sessions are units of their own and outlive a restart of akarid


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
# the web app's manifest (installing Akari on a phone's home screen); Python does not know the type
mimetypes.add_type("application/manifest+json", ".webmanifest")
app.include_router(lucent.router)     # /lucent/v1 (Lucent asks), /auth/lucent (sign-in), /api/lucent


def _secure(resp: Response) -> Response:
    resp.headers.setdefault("Content-Security-Policy", CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if resp.headers.get("content-type", "").startswith(("text/html", "application/json")):
        resp.headers.setdefault("Cache-Control", "no-store")
    else:
        resp.headers.setdefault("Cache-Control", "no-cache")   # revalidate: never mix old and new scripts
    return resp


@app.middleware("http")
async def door(request: Request, call_next):
    path = request.url.path
    if path in ("/", "/index.html"):
        s = auth.current(request)
        # the desktop only once a desktop is chosen; until then the login screen asks which
        page = "index.html" if s and s.desktop else "login.html"
        return _secure(FileResponse(config.STATIC / page, media_type="text/html"))
    if path == "/login.html":
        return _secure(FileResponse(config.STATIC / "login.html", media_type="text/html"))
    if path.startswith("/api/"):
        if request.method not in ("GET", "HEAD") and not auth.same_origin(request):
            return _secure(JSONResponse({"detail": "Fremde Herkunft."}, 403))
        if not path.startswith(("/api/login", "/api/avatars/")) and not auth.current(request):
            return _secure(JSONResponse({"detail": "Nicht angemeldet."}, 401))
    return _secure(await call_next(request))


def _me(request: Request) -> accounts.Account:
    s = auth.current(request)
    acct = s and accounts.get(s.name)
    if not acct:
        raise HTTPException(401, "Nicht angemeldet.")
    return acct


def _cookie(resp: Response, request: Request, token: str) -> Response:
    resp.set_cookie(auth.COOKIE, token, httponly=True, samesite="strict", path="/", secure=request.url.scheme == "https")
    return resp


def _os() -> str:
    try:
        for line in open("/etc/os-release", encoding="utf-8"):
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return config.OS_NAME


# ---------- login ----------

@app.get("/api/login/state")
def login_state(request: Request) -> dict:
    s = auth.current(request)
    acct = s and accounts.get(s.name)
    return {
        "setup": accounts.needs_setup(), "os": _os(), "hostname": config.HOSTNAME, "lucent": bool(lucent.pairing()),
        "signed_in": acct.public() if acct else None, "desktop": s.desktop if s else None,
        "accounts": [{**a.public(), "active": agents.running(a.uid)} for a in accounts.all()],
    }


class LoginIn(BaseModel):
    name: str
    password: str


@app.post("/api/login")
async def login(body: LoginIn, request: Request) -> Response:
    key = f"{(body.name or '').lower()}|{request.client.host if request.client else ''}"
    wait = auth.delay_for(key)
    if wait:
        await asyncio.sleep(wait)
    acct = await asyncio.to_thread(accounts.authenticate, body.name, body.password)
    if not acct:
        auth.failed(key)
        await asyncio.sleep(0.4)
        raise HTTPException(401, "Name oder Passwort stimmt nicht.")
    auth.succeeded(key)
    try:
        await agents.ensure(acct)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    auth.end(request.cookies.get(auth.COOKIE))
    s = auth.start(acct.name)
    return _cookie(JSONResponse({"ok": True, **acct.public()}), request, s.token)


class SetupIn(BaseModel):
    token: str
    name: str
    fullname: str = ""
    password: str


@app.post("/api/login/setup")
async def setup(body: SetupIn, request: Request) -> Response:
    if not accounts.needs_setup():
        raise HTTPException(409, "Akari OS ist schon eingerichtet.")
    if not auth.setup_token_ok(body.token):
        raise HTTPException(403, "Der Einrichtungslink stimmt nicht. Die Konsole des Rechners zeigt ihn (oder: journalctl -u akarid).")
    try:
        acct = await asyncio.to_thread(accounts.create, body.name, body.fullname, body.password, True)
    except accounts.AccountError as e:
        raise HTTPException(400, str(e))
    await agents.ensure(acct)
    s = auth.start(acct.name)
    return _cookie(JSONResponse({"ok": True, **acct.public()}), request, s.token)


@app.get("/api/session")
def session(request: Request) -> dict:
    acct = _me(request)
    s = auth.current(request)
    return {**acct.public(), "uid": acct.uid, "home": str(acct.home), "os": _os(), "hostname": config.HOSTNAME,
            "desktop": {"id": s.desktop, "name": s.desktop_name} if s and s.desktop else None}


async def _agent(acct: accounts.Account, method: str, path: str, json: dict | None = None, desktop: str | None = None) -> dict:
    """akarid asking the account's agent something itself (not passing a request through)."""
    await agents.ensure(acct)
    headers = {DESKTOP_HEADER: desktop} if desktop else {}
    r = await _client(acct.uid).request(method, path, json=json, headers=headers)
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 400:
        raise HTTPException(r.status_code, data.get("detail") or "Die Sitzung sagt nein.")
    return data


class DesktopIn(BaseModel):
    id: str | None = None
    name: str | None = None


@app.post("/api/session/desktop")
async def choose_desktop(body: DesktopIn, request: Request) -> dict:
    """Pick a desktop for this browser, or make a new one."""
    acct, s = _me(request), auth.current(request)
    if body.id:
        known = (await _agent(acct, "GET", "/api/desktops"))["desktops"]
        d = next((d for d in known if d["id"] == body.id), None)
        if not d:
            raise HTTPException(404, "Diesen Desktop gibt es nicht.")
    else:
        d = await _agent(acct, "POST", "/api/desktops", {"name": body.name or "Standard"}, desktop=s.desktop)
    await _agent(acct, "POST", f"/api/desktops/{d['id']}/touch")
    s.desktop, s.desktop_name = d["id"], d["name"]
    return {"ok": True, "desktop": {"id": d["id"], "name": d["name"]}}


class LogoutIn(BaseModel):
    # switch: another account signs in, this one keeps running
    # desktop: back to choosing a desktop, this one keeps running
    # end-desktop: end this desktop's apps, then choose
    # end: sign out completely, everything of this account ends
    mode: str = "switch"
    end: bool = False


@app.post("/api/logout")
async def logout(body: LogoutIn, request: Request) -> Response:
    acct, s = _me(request), auth.current(request)
    mode = "end" if body.end else body.mode
    if mode in ("desktop", "end-desktop"):
        if mode == "end-desktop" and s.desktop:
            await _agent(acct, "POST", f"/api/desktops/{s.desktop}/stop")
        s.desktop, s.desktop_name = None, ""
        return JSONResponse({"ok": True})
    auth.end(request.cookies.get(auth.COOKIE))
    if mode == "end":
        auth.end_all(acct.name)
        await agents.stop(acct.uid)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


# ---------- accounts ----------

class MeIn(BaseModel):
    fullname: str | None = None
    password: str | None = None
    old_password: str | None = None


@app.patch("/api/accounts/me")
async def update_me(body: MeIn, request: Request) -> dict:
    acct = _me(request)
    if body.password is not None and not await asyncio.to_thread(accounts.verify, acct.name, body.old_password or ""):
        raise HTTPException(403, "Das bisherige Passwort stimmt nicht.")
    try:
        acct = await asyncio.to_thread(accounts.update, acct.name, fullname=body.fullname, password=body.password)
    except accounts.AccountError as e:
        raise HTTPException(400, str(e))
    return acct.public()


@app.post("/api/accounts/me/avatar")
async def put_avatar(request: Request) -> dict:
    acct = _me(request)
    form = await request.form(max_files=1)
    f = form.get("file")
    if not hasattr(f, "read"):
        raise HTTPException(400, "Kein Bild.")
    data = await f.read(avatars.MAX_BYTES + 1)
    try:
        await asyncio.to_thread(avatars.save, acct.name, data)
    except avatars.AvatarError as e:
        raise HTTPException(400, str(e))
    acct = await asyncio.to_thread(accounts.set_avatar, acct.name, int(time.time()))
    return acct.public()


@app.delete("/api/accounts/me/avatar")
async def drop_avatar(request: Request) -> dict:
    acct = _me(request)
    await asyncio.to_thread(avatars.remove, acct.name)
    return (await asyncio.to_thread(accounts.set_avatar, acct.name, 0)).public()


@app.get("/api/avatars/{name}")
def get_avatar(name: str) -> Response:
    p = avatars.path(name)
    if not accounts.NAME_RE.match(name) or not p.is_file():
        raise HTTPException(404, "Kein Bild.")
    return FileResponse(p, media_type="image/png", headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox",
                                                              "Cache-Control": "public, max-age=31536000, immutable"})


def _admin(request: Request) -> accounts.Account:
    acct = _me(request)
    if not acct.admin:
        raise HTTPException(403, "Nur Konten, die verwalten dürfen.")
    return acct


@app.get("/api/accounts")
def list_accounts(request: Request) -> dict:
    _admin(request)
    return {"accounts": [{**a.public(), "uid": a.uid, "active": agents.running(a.uid), "created": a.created} for a in accounts.all()]}


class NewIn(BaseModel):
    name: str
    fullname: str = ""
    password: str
    admin: bool = False


@app.post("/api/accounts")
async def new_account(body: NewIn, request: Request) -> dict:
    _admin(request)
    try:
        acct = await asyncio.to_thread(accounts.create, body.name, body.fullname, body.password, body.admin)
    except accounts.AccountError as e:
        raise HTTPException(400, str(e))
    return acct.public()


class AdminIn(BaseModel):
    admin: bool | None = None
    password: str | None = None


@app.patch("/api/accounts/{name}")
async def change_account(name: str, body: AdminIn, request: Request) -> dict:
    _admin(request)
    try:
        acct = await asyncio.to_thread(accounts.update, name, admin=body.admin, password=body.password)
    except accounts.AccountError as e:
        raise HTTPException(400, str(e))
    return acct.public()


@app.delete("/api/accounts/{name}")
async def delete_account(name: str, request: Request) -> dict:
    me = _admin(request)
    if name == me.name:
        raise HTTPException(400, "Das eigene Konto löscht man nicht von innen.")
    acct = accounts.get(name)
    if not acct:
        raise HTTPException(404, "Dieses Konto gibt es nicht.")
    auth.end_all(name)
    await agents.stop(acct.uid)
    await asyncio.to_thread(avatars.remove, name)
    try:
        await asyncio.to_thread(accounts.delete, name)
    except accounts.AccountError as e:
        raise HTTPException(400, str(e))
    await ssh.reload()          # its Match line goes
    return {"ok": True}


# ---------- software ----------

@app.get("/api/software")
async def software_info(request: Request) -> dict:
    acct = _me(request)
    return {**await software.info(), "admin": acct.admin}


# ---------- ssh ----------

@app.get("/api/ssh")
async def ssh_info(request: Request) -> dict:
    acct = _me(request)
    return {**await ssh.info(), "me": {"name": acct.name, "password": acct.ssh_password}, "admin": acct.admin}


class SshIn(BaseModel):
    enabled: bool


@app.put("/api/ssh")
async def ssh_switch(body: SshIn, request: Request) -> dict:
    _admin(request)
    try:
        await ssh.set_enabled(body.enabled)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return await ssh.info()


class SshPwIn(BaseModel):
    allow: bool
    password: str | None = None


@app.post("/api/ssh/password")
async def ssh_password(body: SshPwIn, request: Request) -> dict:
    """An account allows its password over ssh (it confirms with the password) or forbids it."""
    acct = _me(request)
    if body.allow and not await asyncio.to_thread(accounts.verify, acct.name, body.password or ""):
        raise HTTPException(403, "Das Passwort stimmt nicht.")
    acct = await asyncio.to_thread(accounts.set_ssh_password, acct.name, body.allow)
    await ssh.reload()
    return {"password": acct.ssh_password}


# ---------- the machine (host.py): everyone reads, admins change ----------

def _host_call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except host.HostError as e:
        raise HTTPException(400, str(e))


@app.get("/api/host")
async def host_info(request: Request) -> dict:
    acct = _me(request)
    return {**await asyncio.to_thread(host.info), "admin": acct.admin}


class HostnameIn(BaseModel):
    hostname: str


@app.put("/api/host/hostname")
async def host_name(body: HostnameIn, request: Request) -> dict:
    _admin(request)
    name = await asyncio.to_thread(_host_call, host.set_hostname, body.hostname)
    return {"hostname": name}


class PowerIn(BaseModel):
    action: str


@app.post("/api/host/power")
async def host_power(body: PowerIn, request: Request) -> dict:
    _admin(request)
    await asyncio.to_thread(_host_call, host.power, body.action)
    return {"ok": True}


@app.get("/api/host/network")
async def host_network(request: Request) -> dict:
    _me(request)
    return await asyncio.to_thread(host.network)


@app.get("/api/host/time")
async def host_time(request: Request) -> dict:
    acct = _me(request)
    return {**await asyncio.to_thread(host.clock), "admin": acct.admin}


@app.get("/api/host/timezones")
async def host_timezones(request: Request) -> dict:
    _me(request)
    return {"zones": await asyncio.to_thread(host.timezones)}


class TimeIn(BaseModel):
    timezone: str | None = None
    ntp: bool | None = None


@app.put("/api/host/time")
async def host_set_time(body: TimeIn, request: Request) -> dict:
    acct = _admin(request)
    await asyncio.to_thread(_host_call, host.set_clock, body.timezone, body.ntp)
    return {**await asyncio.to_thread(host.clock), "admin": acct.admin}


@app.get("/api/host/updates")
async def host_updates(request: Request) -> dict:
    acct = _me(request)
    return {**await asyncio.to_thread(host.updates), "admin": acct.admin}


class JobIn(BaseModel):
    job: str


@app.post("/api/host/updates")
async def host_update(body: JobIn, request: Request) -> dict:
    acct = _admin(request)
    await asyncio.to_thread(_host_call, host.start, body.job)
    await asyncio.sleep(.3)
    return {**await asyncio.to_thread(host.updates), "admin": acct.admin}


@app.get("/api/host/summary")
async def host_summary(request: Request) -> dict:
    acct = _me(request)
    out = await asyncio.to_thread(host.summary)
    # which services failed is root's business; how many is everyone's
    if not acct.admin:
        out["failed"] = len(out.get("failed") or [])
    return {**out, "admin": acct.admin}


@app.get("/api/host/autoupdates")
async def host_auto(request: Request) -> dict:
    acct = _me(request)
    return {**await asyncio.to_thread(host.auto_updates), "admin": acct.admin}


class OnIn(BaseModel):
    on: bool


@app.put("/api/host/autoupdates")
async def host_set_auto(body: OnIn, request: Request) -> dict:
    acct = _admin(request)
    return {**await asyncio.to_thread(_host_call, host.set_auto_updates, body.on), "admin": acct.admin}


@app.get("/api/host/keyboard")
async def host_keyboard(request: Request) -> dict:
    acct = _me(request)
    return {**await asyncio.to_thread(host.keyboard), "admin": acct.admin}


class KeyboardIn(BaseModel):
    layout: str


@app.put("/api/host/keyboard")
async def host_set_keyboard(body: KeyboardIn, request: Request) -> dict:
    acct = _admin(request)
    return {**await asyncio.to_thread(_host_call, host.set_keyboard, body.layout), "admin": acct.admin}


# ---------- server roles (roles.py): what the machine is for; everyone sees, admins change ----------

@app.get("/api/roles")
async def roles_list(request: Request) -> dict:
    acct = _me(request)
    return {"roles": await asyncio.to_thread(roles.roles), "admin": acct.admin, "apt": await asyncio.to_thread(host.updates)}


class RoleIn(BaseModel):
    action: str


@app.post("/api/roles/{rid}")
async def roles_change(rid: str, body: RoleIn, request: Request) -> dict:
    _admin(request)
    try:
        await asyncio.to_thread(roles.change, rid, body.action)
    except (roles.RoleError, host.HostError) as e:
        raise HTTPException(400, str(e))
    await asyncio.sleep(.3)
    return {"roles": await asyncio.to_thread(roles.roles)}


# ---------- services and the journal (services.py): root's view, so admins only ----------

def _sv(fn, *a):
    try:
        return fn(*a)
    except services.ServiceError as e:
        raise HTTPException(400, str(e))


@app.get("/api/services")
async def services_list(request: Request) -> dict:
    _admin(request)
    return {"services": await asyncio.to_thread(_sv, services.units)}


@app.get("/api/services/journal")
async def services_journal(request: Request, priority: str = "warning", lines: int = 300, boot: bool = True) -> dict:
    _admin(request)
    return {"entries": await asyncio.to_thread(_sv, services.journal, priority, lines, boot)}


@app.get("/api/services/{name}")
async def services_detail(name: str, request: Request) -> dict:
    _admin(request)
    return await asyncio.to_thread(_sv, services.detail, name)


@app.get("/api/services/{name}/log")
async def services_log(name: str, request: Request, lines: int = 300) -> dict:
    _admin(request)
    return {"entries": await asyncio.to_thread(_sv, services.log, name, lines)}


class ServiceActIn(BaseModel):
    action: str


@app.post("/api/services/{name}")
async def services_act(name: str, body: ServiceActIn, request: Request) -> dict:
    _admin(request)
    return await asyncio.to_thread(_sv, services.act, name, body.action)


# ---------- Docker (docker.py): the socket is root, so admins only ----------

async def _dk(coro):
    try:
        return await coro
    except docker.DockerError as e:
        raise HTTPException(400, str(e))


@app.get("/api/docker")
async def docker_status(request: Request) -> dict:
    acct = _me(request)
    if not acct.admin:
        return {"admin": False}
    st = await docker.status()
    out = {**st, "admin": True, "lucent": await docker.lucent() if st["running"] else None}
    if st["running"]:
        out["containers_list"] = await _dk(docker.containers())
    return out


@app.get("/api/docker/images")
async def docker_images(request: Request) -> dict:
    _admin(request)
    return {"images": await _dk(docker.images())}


@app.post("/api/docker/install")
async def docker_install(request: Request) -> dict:
    _admin(request)
    await asyncio.to_thread(_host_call, host.start, "docker")
    return {"ok": True}


class DockerActIn(BaseModel):
    action: str


@app.post("/api/docker/containers/{cid}")
async def docker_act(cid: str, body: DockerActIn, request: Request) -> dict:
    _admin(request)
    await _dk(docker.act(cid, body.action))
    return {"ok": True}


@app.get("/api/docker/containers/{cid}/logs")
async def docker_logs(cid: str, request: Request, tail: int = 300) -> dict:
    _admin(request)
    return {"text": await _dk(docker.logs(cid, tail))}


@app.delete("/api/docker/images/{iid}")
async def docker_rmi(iid: str, request: Request) -> dict:
    _admin(request)
    await _dk(docker.remove_image(iid))
    return {"ok": True}


@app.get("/api/docker/containers/{cid}")
async def docker_inspect(cid: str, request: Request) -> dict:
    _admin(request)
    return await _dk(docker.inspect(cid))


class PauseIn(BaseModel):
    paused: bool


@app.post("/api/docker/containers/{cid}/pause")
async def docker_pause(cid: str, body: PauseIn, request: Request) -> dict:
    _admin(request)
    await _dk(docker.pause(cid, body.paused))
    return {"ok": True}


class RunIn(BaseModel):
    image: str
    name: str = ""
    ports: list[str] = []
    env: list[str] = []
    volumes: list[str] = []
    restart: str = "unless-stopped"


@app.post("/api/docker/run")
async def docker_run(body: RunIn, request: Request) -> dict:
    _admin(request)
    return {"id": await _dk(docker.run(body.model_dump()))}


class PullIn(BaseModel):
    image: str


@app.post("/api/docker/pull")
async def docker_pull(body: PullIn, request: Request) -> dict:
    _admin(request)
    try:
        docker.pull(body.image)
    except docker.DockerError as e:
        raise HTTPException(400, str(e))
    return {"pulls": docker.pulls()}


@app.get("/api/docker/pulls")
async def docker_pulls(request: Request) -> dict:
    _admin(request)
    return {"pulls": docker.pulls()}


@app.get("/api/docker/volumes")
async def docker_volumes(request: Request) -> dict:
    _admin(request)
    return {"volumes": await _dk(docker.volumes())}


@app.delete("/api/docker/volumes/{name}")
async def docker_rmv(name: str, request: Request) -> dict:
    _admin(request)
    await _dk(docker.remove_volume(name))
    return {"ok": True}


@app.get("/api/docker/networks")
async def docker_networks(request: Request) -> dict:
    _admin(request)
    return {"networks": await _dk(docker.networks())}


@app.delete("/api/docker/networks/{nid}")
async def docker_rmn(nid: str, request: Request) -> dict:
    _admin(request)
    await _dk(docker.remove_network(nid))
    return {"ok": True}


@app.post("/api/docker/prune")
async def docker_prune(request: Request) -> dict:
    _admin(request)
    return await _dk(docker.prune())


@app.post("/api/docker/lucent")
async def docker_lucent(request: Request) -> dict:
    _admin(request)
    await _dk(docker.install_lucent())
    return await docker.lucent()


@app.post("/api/docker/lucent/helper")
async def docker_helper_update(request: Request) -> dict:
    _admin(request)
    await _dk(docker.update_helper())
    return await docker.lucent()


@app.delete("/api/docker/lucent")
async def docker_lucent_remove(request: Request) -> dict:
    _admin(request)
    await _dk(docker.remove_lucent())
    return {"ok": True}


# ---------- the session agent, passed through ----------

_clients: dict[int, httpx.AsyncClient] = {}


def _client(uid: int) -> httpx.AsyncClient:
    c = _clients.get(uid)
    if not c or c.is_closed:
        c = _clients[uid] = httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds=str(config.agent_socket(uid))),
                                              base_url="http://agent", timeout=httpx.Timeout(None, connect=10))
    return c


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def to_agent(rest: str, request: Request) -> Response:
    path = request.url.path
    if not path.startswith(AGENT_PATHS):
        raise HTTPException(404, "Gibt es nicht.")
    acct, s = _me(request), auth.current(request)
    await agents.ensure(acct)
    c = _client(acct.uid)
    headers = {k: v for k, v in request.headers.items() if k in ("content-type", "content-length", "range", "if-range")}
    if s and s.desktop:
        headers[DESKTOP_HEADER] = s.desktop
    req = c.build_request(request.method, path, params=request.query_params, headers=headers, content=request.stream())
    try:
        resp = await c.send(req, stream=True)
    except httpx.HTTPError:
        raise HTTPException(502, "Die Sitzung antwortet nicht.")
    out = {k: v for k, v in resp.headers.items() if k in PASS_HEADERS}
    return StreamingResponse(resp.aiter_raw(), status_code=resp.status_code, headers=out, background=BackgroundTask(resp.aclose))


async def _ws_relay(ws: WebSocket, path: str) -> None:
    s = auth.current(ws)
    acct = s and accounts.get(s.name)
    if not acct or not auth.same_origin(ws):
        await ws.close(code=4401)
        return
    sock = await agents.ensure(acct)
    protos = ws.scope.get("subprotocols") or []
    query = ws.url.query
    try:
        upstream = await unix_connect(str(sock), f"ws://agent{path}{'?' + query if query else ''}",
                                      subprotocols=protos or None, max_size=None, ping_interval=None,
                                      additional_headers={DESKTOP_HEADER: s.desktop} if s.desktop else None)
    except (OSError, ConnectionClosed, Exception):
        await ws.close(code=1011)
        return
    await ws.accept(subprotocol=upstream.subprotocol)

    async def up() -> None:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            await upstream.send(msg["bytes"] if msg.get("bytes") is not None else msg.get("text", ""))

    async def down() -> None:
        async for data in upstream:
            await (ws.send_bytes(data) if isinstance(data, bytes) else ws.send_text(data))

    tasks = [asyncio.create_task(up()), asyncio.create_task(down())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        # close the agent's side first, whatever happens next: an open upstream keeps the shell alive
        with contextlib.suppress(Exception):
            await upstream.close()
        proto = getattr(upstream, "protocol", None)
        code = getattr(upstream, "close_code", None) or getattr(proto, "close_code", None) or 1000
        with contextlib.suppress(Exception):
            await ws.close(code=code if code >= 4000 or code == 1000 else 1000)


@app.websocket("/api/term")
async def term_ws(ws: WebSocket) -> None:
    await _ws_relay(ws, "/api/term")


@app.websocket("/api/events")
async def events_ws(ws: WebSocket) -> None:
    await _ws_relay(ws, "/api/events")


@app.websocket("/api/display/{sid}/ws")
async def display_ws(ws: WebSocket, sid: str) -> None:
    await _ws_relay(ws, f"/api/display/{sid}/ws")


for name, path in config.VENDOR.items():
    if path.is_dir():
        app.mount(f"/vendor/{name}", StaticFiles(directory=path), name=f"vendor-{name}")
app.mount("/", StaticFiles(directory=config.STATIC, html=False), name="static")
