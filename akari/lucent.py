"""Lucent, connector contract 1 (lucent/CONNECTOR.md). Runs in akarid.

Lucent manages Akari OS; Akari keeps its own interface and keeps working
when Lucent is gone. What Lucent gets is only this contract:

  pairing            an admin enters Lucent's one-time code in Einstellungen
                     → Lucent (or `python -m akari --lucent-join URL CODE`).
                     The pairing lives in /var/lib/akari/lucent.json, root only:
                     the OIDC client secret and a hash of the connector secret.
  /lucent/v1/*       manifest, status, two maintenance actions and three pages
                     Lucent draws itself (Übersicht, Konten, System), each
                     request with the connector secret as Bearer.
  /auth/lucent       "Mit Lucent anmelden": OIDC code flow with PKCE, ID token
                     HS256 checked with the client secret.

Who is who: an Akari account is a Linux user, so Lucent never makes one by
signing in. A person links their account once, signed in to Akari, under
Einstellungen → Konto ("Mit Lucent verknüpfen"); after that the login screen
lets them in with Lucent. Writes from Lucent's pages (accounts, SSH) carry
the Lucent person; Akari does them only when that person is linked to an
Akari admin, whatever Lucent itself allowed."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import sys
import shutil
import time
import urllib.parse

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel

from . import accounts, agents, auth, config, host, ssh

CONTRACT = 1
FILE = config.SYSTEM / "lucent.json"
STATE_COOKIE = "akari_lucent"
PENDING_TTL = 600.0
SKEW = 60

router = APIRouter()
_pending: dict[str, dict] = {}

# the Schein mark, in fills Lucent keeps (no classes, no styles)
ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 95.64 100">'
        '<path fill="#7c5cff" d="M40.4 0L51.4 0L11 100L0 100Z"/>'
        '<path fill="#8f8ca3" d="M51.14 14L75.14 14L40.39 100L16.39 100Z"/>'
        '<path fill="#5b5970" d="M71.64 36L95.64 36L69.79 100L45.79 100Z"/></svg>')


class LucentError(RuntimeError):
    pass


# ---------- the pairing file ----------

def pairing() -> dict | None:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(data: dict) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, FILE)


def _backchannel(p: dict) -> str:
    """Where akarid calls Lucent: the address it joined with (maybe an inside one)."""
    return (p.get("lucent_url") or p["issuer"]).rstrip("/")


async def _post(url: str, *, json_body: dict | None = None, form: dict | None = None,
                basic: tuple[str, str] | None = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": f"akari-os/{config.VERSION}"}) as c:
            r = await c.post(url, json=json_body, data=form, auth=basic)
    except httpx.HTTPError as e:
        raise LucentError(f"Lucent ist unter {url} nicht erreichbar ({type(e).__name__}).") from None
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code >= 400:
        detail = body.get("detail") or body.get("error_description") or body.get("error") or r.reason_phrase
        raise LucentError(f"Lucent antwortet {r.status_code}: {detail}")
    return body


async def join(lucent_url: str, code: str, ui_url: str, base_url: str | None = None) -> dict:
    if pairing():
        raise LucentError("Akari ist schon mit Lucent gekoppelt. Zuerst entkoppeln.")
    lucent_url, ui_url = lucent_url.strip().rstrip("/"), ui_url.strip().rstrip("/")
    base_url = (base_url or ui_url).strip().rstrip("/")
    for u in (lucent_url, ui_url, base_url):
        if not u.startswith(("http://", "https://")):
            raise LucentError("Adressen beginnen mit http:// oder https://.")
    secret = secrets.token_urlsafe(32)
    answer = await _post(f"{lucent_url}/api/connect/pair", json_body={
        "code": code.strip().upper(), "kind": "akari", "name": config.OS_NAME, "base_url": base_url,
        "ui_url": ui_url, "version": config.VERSION, "redirect_uris": [f"{ui_url}/auth/lucent/callback"],
        "connector_secret": secret, "id_token_alg": "HS256"})
    data = {"issuer": str(answer["issuer"]).rstrip("/"), "lucent_url": lucent_url, "tool_id": answer.get("tool_id"),
            "client_id": answer["client_id"], "client_secret": answer["client_secret"],
            "connector_secret_sha256": hashlib.sha256(secret.encode()).hexdigest(),
            "ui_url": ui_url, "base_url": base_url, "paired_at": int(time.time())}
    _write(data)
    return data


def leave() -> bool:
    try:
        FILE.unlink()
    except FileNotFoundError:
        return False
    return True


def info() -> dict | None:
    p = pairing()
    if not p:
        return None
    return {"issuer": p["issuer"], "ui_url": p["ui_url"], "base_url": p["base_url"], "since": p["paired_at"]}


# ---------- the connector API: Lucent asks ----------

def _require(request: Request) -> dict:
    p = pairing()
    if not p:
        raise HTTPException(404, "Akari ist nicht mit Lucent gekoppelt.")
    header = request.headers.get("authorization", "")
    sent = header[7:] if header.lower().startswith("bearer ") else ""
    if not sent or not hmac.compare_digest(hashlib.sha256(sent.encode()).hexdigest(), p["connector_secret_sha256"]):
        raise HTTPException(401, "Falsches Connector-Geheimnis.")
    return p


def _who(p: dict, by) -> accounts.Account | None:
    """The Akari account of the Lucent person a write comes from, if linked."""
    if isinstance(by, dict) and by.get("sub"):
        return accounts.by_lucent(f"{p['issuer']}#{by['sub']}")
    if isinstance(by, str) and by.startswith("lucent:"):      # manifest actions name only the e-mail
        mail = by[7:].strip().lower()
        return next((a for a in accounts.all() if a.lucent_email and a.lucent_email.lower() == mail), None)
    return None


def _need_admin(p: dict, by) -> accounts.Account:
    a = _who(p, by)
    if not a or not a.admin:
        raise HTTPException(403, "Das geht nur für Lucent-Personen, die mit einem Akari-Konto verknüpft sind, das verwalten darf "
                                 "(in Akari: Einstellungen → Konto → Mit Lucent verknüpfen).")
    return a


def _gb(n: float) -> str:
    return f"{n / 1024 ** 3:.1f}".replace(".", ",")


def _uptime() -> str:
    try:
        up = int(float(open("/proc/uptime").read().split()[0]))
    except OSError:
        return "–"
    d, h, m = up // 86400, up % 86400 // 3600, up % 3600 // 60
    return f"{d} T {h} h" if d else f"{h} h {m} min"


def _os() -> str:
    try:
        for line in open("/etc/os-release", encoding="utf-8"):
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return config.OS_NAME


async def _figures() -> dict:
    from . import stats
    cpu, _ = await stats._cpu()
    mem = stats._mem()
    disk = shutil.disk_usage("/")
    return {"cpu": cpu, "mem": mem, "disk": disk, "load": os.getloadavg()}


def _signed_in() -> list[accounts.Account]:
    return [a for a in accounts.all() if agents.running(a.uid)]


@router.get("/lucent/v1/manifest")
def manifest(request: Request) -> dict:
    p = _require(request)
    return {
        "contract": CONTRACT, "kind": "akari", "name": config.OS_NAME, "version": config.VERSION,
        "ui_url": p["ui_url"], "description": "Desktop im Browser mit einem echten Debian darunter", "icon": ICON,
        "actions": [
            {"id": "logout-all", "label": "Alle abmelden", "danger": True,
             "description": "Beendet die Sitzungen und Programme aller Konten. Dateien bleiben."},
            {"id": "updates", "label": "Updates installieren", "danger": False,
             "description": "Bringt alle Pakete mit apt auf den neuen Stand. Wird Akari selbst aktualisiert, startet es neu."},
        ],
        "pages": [
            {"id": "uebersicht", "label": "Übersicht", "icon": "chart", "after": "start"},
            {"id": "konten", "label": "Konten", "icon": "users"},
            {"id": "system", "label": "System", "icon": "server"},
        ],
    }


@router.get("/lucent/v1/status")
async def status(request: Request) -> dict:
    _require(request)
    f = await _figures()
    accts = accounts.all()
    on = _signed_in()
    mem_pct = 100 * f["mem"]["used"] / max(1, f["mem"]["total"])
    disk_pct = 100 * f["disk"].used / max(1, f["disk"].total)
    warn = disk_pct > 90 or mem_pct > 92
    sshd = await ssh.info()
    upgradable = await asyncio.to_thread(host.upgradable)
    linked = sum(1 for a in accts if a.lucent_sub)
    return {
        "state": "warn" if warn else "ok",
        "summary": f"{len(accts)} Konten, {len(on)} angemeldet",
        "cards": [
            {"label": "Konten", "value": str(len(accts)), "unit": None, "state": None,
             "note": f"{sum(a.admin for a in accts)} verwalten"},
            {"label": "Angemeldet", "value": str(len(on)), "unit": None, "state": None,
             "note": ", ".join(a.name for a in on) or "niemand"},
            {"label": "CPU", "value": f"{f['cpu']:.0f}", "unit": "%", "state": None,
             "note": f"Last {f['load'][0]:.2f}".replace(".", ",")},
            {"label": "Speicherplatz", "value": f"{disk_pct:.0f}", "unit": "%", "state": "warn" if disk_pct > 90 else None,
             "note": f"{_gb(f['disk'].used)} von {_gb(f['disk'].total)} GB"},
        ],
        "facts": [
            {"label": "System", "value": _os()},
            {"label": "Version", "value": config.VERSION},
            {"label": "Rechner", "value": config.HOSTNAME},
            {"label": "Kernel", "value": os.uname().release},
            {"label": "Läuft seit", "value": _uptime()},
            {"label": "SSH", "value": f"an, Port {sshd['port']}" if sshd["enabled"] else "aus"},
            {"label": "Updates", "value": f"{len(upgradable)} verfügbar" if upgradable else "aktuell"},
            {"label": "Mit Lucent verknüpft", "value": f"{linked} von {len(accts)} Konten"},
        ],
    }


class ActionIn(BaseModel):
    by: str | dict | None = None


@router.post("/lucent/v1/actions/{aid}")
async def action(aid: str, body: ActionIn, request: Request) -> dict:
    _require(request)
    if aid == "logout-all":
        n = 0
        for a in accounts.all():
            if agents.running(a.uid):
                n += 1
            auth.end_all(a.name)
            await agents.stop(a.uid)
        return {"ok": True, "message": f"{n} Konten abgemeldet." if n else "Es war niemand angemeldet."}
    if aid == "updates":
        n = len(await asyncio.to_thread(host.upgradable))
        if not n:
            return {"ok": True, "message": "Alles ist aktuell."}
        try:
            await asyncio.to_thread(host.start, "install")
        except host.HostError as e:
            return {"ok": False, "message": str(e)}
        return {"ok": True, "message": f"apt installiert {n} Updates."}
    raise HTTPException(404, "Diese Aktion gibt es nicht.")


# ---------- pages Lucent draws ----------

def _badges(a: accounts.Account) -> list[dict]:
    out = []
    if a.admin:
        out.append({"label": "Verwaltet", "tone": "acc"})
    if agents.running(a.uid):
        out.append({"label": "Angemeldet", "tone": "ok"})
    if a.lucent_sub:
        out.append({"label": "Lucent"})
    if a.ssh_password:
        out.append({"label": "SSH-Passwort", "tone": "warn"})
    return out


def _initials(a: accounts.Account) -> str:
    parts = (a.fullname or a.name).split()
    return "".join(x[0] for x in parts[:2]).upper() or a.name[:1].upper()


async def _page_overview() -> dict:
    f = await _figures()
    on = _signed_in()
    mem = f["mem"]
    return {
        "title": "Übersicht", "lead": f"{_os()} auf {config.HOSTNAME}, läuft seit {_uptime()}.",
        "sections": [
            {"id": "zahlen", "title": "Jetzt", "kind": "stats", "items": [
                {"label": "CPU", "value": f"{f['cpu']:.0f} %", "note": f"Last {f['load'][0]:.2f}".replace(".", ",")},
                {"label": "Arbeitsspeicher", "value": f"{_gb(mem['used'])} GB", "note": f"von {_gb(mem['total'])} GB"},
                {"label": "Speicherplatz", "value": f"{_gb(f['disk'].used)} GB", "note": f"von {_gb(f['disk'].total)} GB",
                 "tone": "warn" if f["disk"].used / max(1, f["disk"].total) > .9 else None},
                {"label": "Angemeldet", "value": str(len(on)), "note": f"von {len(accounts.all())} Konten"},
            ]},
            {"id": "angemeldet", "title": "Wer angemeldet ist", "kind": "rows", "size": "half",
             "empty": "Gerade ist niemand angemeldet.",
             "items": [{"title": a.fullname, "sub": a.name, "initials": _initials(a),
                        **({"thumb": f"avatar/{a.name}"} if a.avatar else {}),
                        "meta": f"{sum(1 for s in auth.SESSIONS.values() if s.name == a.name)} Browser",
                        "actions": [{"id": "abmelden", "label": "Abmelden", "danger": True, "icon": "x",
                                     "confirm": f"{a.fullname} abmelden? Offene Programme werden beendet.",
                                     "values": {"name": a.name}}]} for a in on]},
            {"id": "speicher", "title": "Speicher", "kind": "ring", "size": "half", "unit": "GB",
             "center": f"{100 * f['disk'].used / max(1, f['disk'].total):.0f} %", "sub": "belegt", "ranked": False,
             "items": [{"label": "Belegt", "value": round(f["disk"].used / 1024 ** 3, 1)},
                       {"label": "Frei", "value": round(f["disk"].free / 1024 ** 3, 1), "tone": "ok"}]},
        ],
    }


def _page_accounts() -> dict:
    accts = accounts.all()
    first = not accts       # a fresh Akari from the store: the first account is made here
    return {
        "title": "Konten",
        "lead": ("Noch gibt es kein Konto. Das erste darf verwalten und ist gleich mit deinem Lucent-Konto verknüpft: "
                 "danach meldest du dich in Akari mit Lucent an.") if first
                else "Jedes Konto ist ein Linux-Benutzer mit eigenem Home. Verwalten heißt: sudo und apt.",
        "sections": [{"id": "konten", "title": "Konten", "kind": "cards", "shape": "square", "items": [{
            "title": a.fullname, "sub": a.name, "initials": _initials(a), "badges": _badges(a),
            **({"img": f"avatar/{a.name}", "img_alt": a.fullname} if a.avatar else {}),
            "facts": [{"label": "UID", "value": str(a.uid)},
                      {"label": "Seit", "value": time.strftime("%d.%m.%Y", time.localtime(a.created))}]
                     + ([{"label": "Lucent", "value": a.lucent_email}] if a.lucent_email else []),
            "actions": [
                {"id": "admin", "label": "Verwalten entziehen" if a.admin else "Verwalten erlauben", "icon": "users",
                 "values": {"name": a.name, "admin": "0" if a.admin else "1"}},
                {"id": "passwort", "label": "Passwort setzen", "icon": "edit", "values": {"name": a.name},
                 "fields": [{"name": "password", "label": "Neues Passwort", "type": "password", "required": True,
                             "help": f"Mindestens {accounts.PW_MIN} Zeichen. Gilt auch für sudo und SSH."}]},
                {"id": "abmelden", "label": "Abmelden", "icon": "x", "danger": True, "values": {"name": a.name},
                 "confirm": f"{a.fullname} abmelden? Offene Programme werden beendet."},
                {"id": "loeschen", "label": "Löschen", "icon": "trash", "danger": True, "values": {"name": a.name},
                 "confirm": f"Das Konto {a.name}, sein Home und alles darin sind danach weg."},
            ]} for a in accts]}],
        "actions": [{"id": "neu", "label": "Erstes Konto anlegen" if first else "Konto anlegen", "icon": "plus", "submit": "Anlegen",
                     "fields": [
            {"name": "fullname", "label": "Name", "type": "text", "placeholder": "So, wie die Person heißt"},
            {"name": "name", "label": "Benutzername", "type": "text", "required": True,
             "help": "Kleinbuchstaben, Ziffern, - und _. So heißt das Konto im Terminal."},
            {"name": "password", "label": "Passwort", "type": "password", "required": True,
             "help": f"Mindestens {accounts.PW_MIN} Zeichen. Für die Anmeldung ohne Lucent, sudo und SSH."},
        ] + ([] if first else [{"name": "admin", "label": "Darf verwalten (sudo, apt, Konten)", "type": "checkbox"}])}],
    }


async def _page_system() -> dict:
    sshd = await ssh.info()
    up = await asyncio.to_thread(host.updates)
    p = pairing() or {}
    return {
        "title": "System",
        "sections": [
            {"id": "system", "title": "System", "kind": "kv", "size": "half", "items": [
                {"label": "System", "value": _os()}, {"label": "Akari", "value": config.VERSION},
                {"label": "Rechner", "value": config.HOSTNAME}, {"label": "Kernel", "value": os.uname().release},
                {"label": "Läuft seit", "value": _uptime()},
                {"label": "Lucent", "value": f"gekoppelt seit {time.strftime('%d.%m.%Y', time.localtime(p.get('paired_at', 0)))}"},
            ]},
            {"id": "ssh", "title": "SSH", "kind": "kv", "size": "half",
             "lead": "Anmelden mit Schlüssel; mit Passwort nur, wo das Konto es erlaubt.",
             "items": [{"label": "Zustand", "value": "an" if sshd["enabled"] else "aus", "tone": "ok" if sshd["running"] else None},
                       {"label": "Port", "value": str(sshd["port"])}]
                      + ([{"label": "Von außen", "value": sshd["public"]}] if sshd.get("public") else [])
                      + [{"label": "Schlüssel des Rechners", "value": fp} for fp in sshd["fingerprints"]],
             "actions": [{"id": "ssh", "label": "SSH ausschalten" if sshd["enabled"] else "SSH einschalten",
                          "icon": "server", "danger": bool(sshd["enabled"]), "values": {"on": "0" if sshd["enabled"] else "1"}}]},
            {"id": "updates", "title": "Updates", "kind": "rows",
             "lead": "Was apt auf den neuen Stand bringen würde. Installieren: Aktion „Updates installieren“.",
             "empty": "Alles ist aktuell.",
             "meta": {"install": "wird installiert …", "check": "sucht …"}.get(up["running"] or "", ""),
             "items": [{"title": x["name"], "meta": f"{x['from']} → {x['to']}"} for x in up["packages"]]},
        ],
    }


@router.get("/lucent/v1/pages/{pid}")
async def page(pid: str, request: Request) -> dict:
    _require(request)
    if pid == "uebersicht":
        return await _page_overview()
    if pid == "konten":
        return _page_accounts()
    if pid == "system":
        return await _page_system()
    raise HTTPException(404, "Diese Seite gibt es nicht.")


@router.get("/lucent/v1/pages/{pid}/file/{path:path}")
def page_file(pid: str, path: str, request: Request) -> FileResponse:
    """Pictures the pages name: account pictures (re-rendered PNGs, never an upload as it came)."""
    _require(request)
    from . import avatars
    kind, _, name = path.partition("/")
    if kind != "avatar" or not accounts.NAME_RE.match(name) or not avatars.path(name).is_file():
        raise HTTPException(404, "Gibt es nicht.")
    return FileResponse(avatars.path(name), media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


class DoIn(BaseModel):
    values: dict = {}
    files: list = []
    by: str | dict | None = None


async def _end(name: str) -> None:
    a = accounts.get(name)
    if not a:
        raise HTTPException(422, "Dieses Konto gibt es nicht.")
    auth.end_all(a.name)
    await agents.stop(a.uid)


async def _first_account(p: dict, body: "DoIn") -> dict:
    """An Akari installed from Lucent's store has no setup link anyone could
    read from its log. So while it has no account at all, the Lucent person
    who may change it (Lucent checks that) makes the first one: it may manage,
    and it is linked to that person, who then signs in with Lucent."""
    by = body.by if isinstance(body.by, dict) else {}
    if not by.get("sub"):
        raise HTTPException(403, "Das erste Konto legt eine Lucent-Person an, die Lucent nennt.")
    v = {k: str(x) for k, x in (body.values or {}).items()}
    try:
        a = await asyncio.to_thread(accounts.create, v.get("name", ""), v.get("fullname", ""), v.get("password", ""), True)
        await asyncio.to_thread(accounts.set_lucent, a.name, f"{p['issuer']}#{by['sub']}", by.get("email"))
    except accounts.AccountError as e:
        raise HTTPException(422, str(e)) from None
    return {"notice": f"Erstes Konto {a.name} angelegt. Es darf verwalten und ist mit deinem Lucent-Konto verknüpft: "
                      "in Akari „Mit Lucent anmelden“."}


@router.post("/lucent/v1/pages/{pid}/do/{aid}")
async def do(pid: str, aid: str, body: DoIn, request: Request) -> dict:
    p = _require(request)
    if pid == "konten" and aid == "neu" and accounts.needs_setup():
        return await _first_account(p, body)
    me = _need_admin(p, body.by)
    v = {k: str(x) for k, x in (body.values or {}).items()}
    name = v.get("name", "")
    try:
        if aid == "abmelden" and pid in ("uebersicht", "konten"):
            await _end(name)
            return {"notice": f"{name} ist abgemeldet."}
        if pid == "konten" and aid == "neu":
            a = await asyncio.to_thread(accounts.create, v.get("name", ""), v.get("fullname", ""), v.get("password", ""), v.get("admin") == "1")
            return {"notice": f"Konto {a.name} angelegt."}
        if pid == "konten" and aid == "admin":
            a = await asyncio.to_thread(accounts.update, name, admin=v.get("admin") == "1")
            return {"notice": f"{a.name} darf jetzt verwalten." if a.admin else f"{a.name} verwaltet nicht mehr."}
        if pid == "konten" and aid == "passwort":
            await asyncio.to_thread(accounts.update, name, password=v.get("password", ""))
            await ssh.reload()
            return {"notice": f"Neues Passwort für {name} gesetzt."}
        if pid == "konten" and aid == "loeschen":
            if name == me.name:
                raise HTTPException(422, "Das eigene Konto löscht man nicht aus Lucent.")
            from . import avatars
            await _end(name)
            await asyncio.to_thread(avatars.remove, name)
            await asyncio.to_thread(accounts.delete, name)
            return {"notice": f"Konto {name} gelöscht."}
        if pid == "system" and aid == "ssh":
            await ssh.set_enabled(v.get("on") == "1")
            return {"notice": "SSH ist an." if v.get("on") == "1" else "SSH ist aus."}
    except accounts.AccountError as e:
        raise HTTPException(422, str(e)) from None
    raise HTTPException(404, "Diese Aktion gibt es nicht.")


# ---------- sign in with Lucent ----------

def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def verify_id_token(token: str, p: dict, nonce: str) -> dict:
    try:
        h64, b64, s64 = token.split(".")
        header, claims, sig = json.loads(_unb64u(h64)), json.loads(_unb64u(b64)), _unb64u(s64)
    except (ValueError, TypeError):
        raise LucentError("Das ID-Token ist kein JWT.") from None
    if header.get("alg") != "HS256":
        raise LucentError("Unerwarteter Algorithmus im ID-Token.")
    want = hmac.new(p["client_secret"].encode(), f"{h64}.{b64}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(want, sig):
        raise LucentError("Die Signatur des ID-Tokens stimmt nicht.")
    now, aud = time.time(), claims.get("aud")
    if claims.get("iss") != p["issuer"]:
        raise LucentError("Das ID-Token kommt von einem anderen Aussteller.")
    if aud != p["client_id"] and not (isinstance(aud, list) and p["client_id"] in aud):
        raise LucentError("Das ID-Token ist für einen anderen Client.")
    if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] < now - SKEW:
        raise LucentError("Das ID-Token ist abgelaufen.")
    if not isinstance(claims.get("iat"), (int, float)) or claims["iat"] > now + SKEW:
        raise LucentError("Das ID-Token kommt aus der Zukunft.")
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise LucentError("Die Nonce des ID-Tokens stimmt nicht.")
    if not claims.get("sub"):
        raise LucentError("Das ID-Token nennt niemanden.")
    return claims


def _sweep(now: float) -> None:
    for k in [k for k, v in _pending.items() if now - v["at"] > PENDING_TTL]:
        _pending.pop(k, None)


@router.get("/auth/lucent", include_in_schema=False)
def sign_in(request: Request, link: int = 0):
    p = pairing()
    if not p:
        raise HTTPException(404, "Akari ist nicht mit Lucent gekoppelt.")
    linking = None
    if link:   # linking needs the Akari session that asks (the strict cookie comes along: same site)
        s = auth.current(request)
        if not s:
            return RedirectResponse("/", status_code=303)
        linking = s.name
    now = time.time()
    _sweep(now)
    state, nonce, browser = (secrets.token_urlsafe(24) for _ in range(3))
    verifier = secrets.token_urlsafe(48)        # PKCE: 43 to 128 characters
    _pending[state] = {"nonce": nonce, "verifier": verifier, "browser": browser, "at": now, "link": linking}
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": p["client_id"], "redirect_uri": f"{p['ui_url']}/auth/lucent/callback",
        "scope": "openid email profile", "state": state, "nonce": nonce,
        "code_challenge": _b64u(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256"})
    r = RedirectResponse(f"{p['issuer']}/oidc/authorize?{q}", status_code=303)
    r.set_cookie(STATE_COOKIE, browser, max_age=int(PENDING_TTL), httponly=True, samesite="lax",
                 secure=request.url.scheme == "https", path="/auth/lucent")
    return r


def _hop(to: str, cookie: tuple[str, str] | None = None, request: Request | None = None) -> HTMLResponse:
    """Back into Akari. Not a redirect: the chain began on Lucent, so the browser
    would hold back Akari's SameSite=Strict cookie. A page of Akari's own that
    moves on is a navigation from this site, and the cookie comes along."""
    to_h = html.escape(to, quote=True)
    r = HTMLResponse(f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={to_h}">'
                     f'<title>Akari OS</title><a href="{to_h}">Weiter zu Akari OS</a>')
    r.delete_cookie(STATE_COOKIE, path="/auth/lucent")
    if cookie and request:
        r.set_cookie(cookie[0], cookie[1], httponly=True, samesite="strict", path="/", secure=request.url.scheme == "https")
    return r


@router.get("/auth/lucent/callback", include_in_schema=False)
async def callback(request: Request, code: str = "", state: str = "", error: str = "", iss: str = ""):
    p = pairing()
    pending = _pending.pop(state, None) if state else None
    if not p or not pending or time.time() - pending["at"] > PENDING_TTL:
        return _hop("/?lucent=abgelaufen")
    if not hmac.compare_digest(request.cookies.get(STATE_COOKIE, ""), pending["browser"]):
        return _hop("/?lucent=browser")
    if error or (iss and iss.rstrip("/") != p["issuer"]):
        return _hop("/?lucent=abgelehnt")
    try:
        answer = await _post(f"{_backchannel(p)}/oidc/token", form={
            "grant_type": "authorization_code", "code": code, "code_verifier": pending["verifier"],
            "redirect_uri": f"{p['ui_url']}/auth/lucent/callback"}, basic=(p["client_id"], p["client_secret"]))
        claims = verify_id_token(answer.get("id_token", ""), p, pending["nonce"])
    except LucentError as e:
        print(f"akari: Anmelden mit Lucent gescheitert: {e}", file=sys.stderr, flush=True)
        return _hop("/?lucent=fehler")
    sub = f"{p['issuer']}#{claims['sub']}"
    if pending["link"]:
        try:
            await asyncio.to_thread(accounts.set_lucent, pending["link"], sub, claims.get("email"))
        except accounts.AccountError:
            return _hop("/?lucent=vergeben")
        return _hop("/?lucent=verknuepft")
    acct = accounts.by_lucent(sub)
    if not acct:
        return _hop("/?lucent=unbekannt")
    try:
        await agents.ensure(acct)
    except RuntimeError:
        return _hop("/?lucent=fehler")
    auth.end(request.cookies.get(auth.COOKIE))
    s = auth.start(acct.name)
    return _hop("/", (auth.COOKIE, s.token), request)


# ---------- for Akari's own pages (signed in) ----------

def _session_account(request: Request) -> accounts.Account:
    s = auth.current(request)
    a = s and accounts.get(s.name)
    if not a:
        raise HTTPException(401, "Nicht angemeldet.")
    return a


@router.get("/api/lucent")
def state(request: Request) -> dict:
    a = _session_account(request)
    return {"paired": info(), "admin": a.admin, "me": {"linked": bool(a.lucent_sub), "email": a.lucent_email},
            "suggest_ui": str(request.base_url).rstrip("/")}


class PairIn(BaseModel):
    lucent_url: str
    code: str
    ui_url: str
    base_url: str | None = None


@router.post("/api/lucent/pair")
async def pair(body: PairIn, request: Request) -> dict:
    a = _session_account(request)
    if not a.admin:
        raise HTTPException(403, "Koppeln dürfen nur Konten, die verwalten.")
    try:
        await join(body.lucent_url, body.code, body.ui_url, body.base_url or None)
    except LucentError as e:
        raise HTTPException(400, str(e)) from None
    return {"paired": info()}


@router.delete("/api/lucent")
def unpair(request: Request) -> dict:
    a = _session_account(request)
    if not a.admin:
        raise HTTPException(403, "Entkoppeln dürfen nur Konten, die verwalten.")
    leave()
    return {"paired": None}


@router.delete("/api/lucent/link")
def unlink(request: Request) -> dict:
    a = _session_account(request)
    accounts.set_lucent(a.name, None)
    return {"ok": True}
