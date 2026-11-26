"""Session agents: one per signed-in account, as that Linux user.

Each is a systemd unit, akari-session@<name>.service (User=<name>,
PAMName=akari): PAM opens a real logind session for it, with
/run/user/<uid> and the user's own systemd. The agent listens on
/run/user/<uid>/akari/agent.sock (0700, the user's own); only that user
and root can reach it.

"Abmelden" stops the unit (the agent ends its apps), then ends the logind
session PAM opened for it, and with it anything the desktop left behind (it
all runs in that session's scope). The user's other logins (ssh, a console)
are other sessions and are not touched.
"Benutzer wechseln" only ends the browser's session: the unit keeps running.
akarid restarting does not end sessions either."""

from __future__ import annotations

import asyncio
import contextlib
import json
import pwd
import time
from pathlib import Path

from . import config
from .accounts import Account

UNIT = "akari-session@{}.service"
_starting: dict[int, asyncio.Lock] = {}
_active: tuple[float, set[str]] = (0.0, set())


def _name(uid: int) -> str | None:
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return None


def _active_units() -> set[str]:
    """Names with a running session, from one systemctl call, kept for a second."""
    global _active
    at, names = _active
    if time.monotonic() - at < 1.0:
        return names
    import subprocess
    r = subprocess.run(["systemctl", "list-units", "--plain", "--no-legend", "--state=active", "akari-session@*.service"],
                       capture_output=True, text=True)
    names = {line.split()[0][len("akari-session@"):-len(".service")] for line in r.stdout.splitlines() if line.strip()}
    _active = (time.monotonic(), names)
    return names


def _forget() -> None:
    global _active
    _active = (0.0, set())


def running(uid: int) -> bool:
    name = _name(uid)
    return bool(name and name in _active_units())


async def _systemctl(*args: str) -> tuple[int, str]:
    p = await asyncio.create_subprocess_exec("systemctl", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await p.communicate()
    _forget()
    return p.returncode or 0, out.decode(errors="replace").strip()


async def _socket_up(sock: Path, timeout: float = 15.0) -> bool:
    for _ in range(int(timeout / 0.1)):
        if sock.exists():
            with contextlib.suppress(OSError):
                _r, w = await asyncio.open_unix_connection(str(sock))
                w.close()
                return True
        await asyncio.sleep(0.1)
    return False


async def ensure(acct: Account) -> Path:
    """The account's agent socket, starting its session if it is not running."""
    sock = config.agent_socket(acct.uid)
    lock = _starting.setdefault(acct.uid, asyncio.Lock())
    async with lock:
        if running(acct.uid) and sock.exists():
            return sock
        code, out = await _systemctl("start", UNIT.format(acct.name))
        if code != 0 or not await _socket_up(sock):
            await stop(acct.uid)
            raise RuntimeError(f"Die Sitzung ließ sich nicht starten. Mehr mit: journalctl -u {UNIT.format(acct.name)}")
        return sock


async def _akari_sessions(uid: int) -> list[str]:
    """The user's logind sessions opened by PAM service "akari" (not ssh, not a console)."""
    p = await asyncio.create_subprocess_exec("loginctl", "list-sessions", "--json=short",
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await p.communicate()
    try:
        ids = [s["session"] for s in json.loads(out or b"[]") if s.get("uid") == uid and s.get("class") == "user"]
    except (ValueError, TypeError, KeyError):
        return []
    mine = []
    for sid in ids:
        q = await asyncio.create_subprocess_exec("loginctl", "show-session", sid, "-p", "Service", "--value",
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        svc, _ = await q.communicate()
        if svc.decode().strip() == "akari":
            mine.append(sid)
    return mine


async def stop(uid: int) -> None:
    """End a session completely: the agent cleans up after itself when its
    unit stops, then logind ends whatever is left in the session."""
    name = _name(uid)
    if not name:
        return
    await _systemctl("stop", UNIT.format(name))
    for sid in await _akari_sessions(uid):
        p = await asyncio.create_subprocess_exec("loginctl", "terminate-session", sid,
                                                 stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await p.wait()


async def stop_all() -> None:
    names = _active_units()
    if names:
        await _systemctl("stop", *(UNIT.format(n) for n in names))
