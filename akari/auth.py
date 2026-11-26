"""Sessions in akarid: a browser signed in as an account.

A session is a random token in an HttpOnly, SameSite=Strict cookie, kept in
memory (a restart signs everyone out; their apps keep running until the
session ends). One browser holds one session; another account signs in
through the login screen ("Benutzer wechseln").

The setup token: while no account exists, the first one can only be made
with the token printed in the log, so whoever reaches the port first does
not get the machine."""

from __future__ import annotations

import hmac
import os
import secrets
import time
from dataclasses import dataclass, field

from starlette.requests import HTTPConnection

COOKIE = "akari_session"
IDLE = 12 * 3600
SETUP_TOKEN = os.environ.get("AKARI_TOKEN") or secrets.token_urlsafe(24)


@dataclass
class Session:
    token: str
    name: str
    desktop: str | None = None          # chosen after the password, on the login screen
    desktop_name: str = ""
    created: float = field(default_factory=time.time)
    seen: float = field(default_factory=time.time)


SESSIONS: dict[str, Session] = {}


def start(name: str) -> Session:
    s = Session(token=secrets.token_urlsafe(32), name=name)
    SESSIONS[s.token] = s
    return s


def end(token: str | None) -> None:
    if token:
        SESSIONS.pop(token, None)


def end_all(name: str) -> None:
    for t in [t for t, s in SESSIONS.items() if s.name == name]:
        SESSIONS.pop(t, None)


def current(conn: HTTPConnection) -> Session | None:
    token = conn.cookies.get(COOKIE)
    if not token:
        return None
    s = SESSIONS.get(token)
    if not s or not hmac.compare_digest(s.token, token):
        return None
    now = time.time()
    if now - s.seen > IDLE:
        SESSIONS.pop(token, None)
        return None
    s.seen = now
    return s


def setup_token_ok(value: str | None) -> bool:
    return bool(value) and hmac.compare_digest(value, SETUP_TOKEN)


def same_origin(conn: HTTPConnection) -> bool:
    origin, host = conn.headers.get("origin"), conn.headers.get("host")
    return bool(origin and host) and origin.split("://", 1)[-1] == host


# ---------- slowing down guessing ----------

_fails: dict[str, list[float]] = {}
WINDOW, FREE, STEP = 600.0, 5, 2.0


def delay_for(key: str) -> float:
    """After five wrong passwords in ten minutes, every further try waits longer."""
    now = time.time()
    tries = [t for t in _fails.get(key, []) if now - t < WINDOW]
    _fails[key] = tries
    return 0.0 if len(tries) < FREE else min(60.0, STEP * 2 ** (len(tries) - FREE))


def failed(key: str) -> None:
    _fails.setdefault(key, []).append(time.time())


def succeeded(key: str) -> None:
    _fails.pop(key, None)
