"""Session agents: one process per signed-in account, running as that Linux
user (like systemd --user). akarid starts it at sign-in and talks to it over
a Unix socket in /tmp/akari/<uid>/ (0700, the user's own): only that user
and root can reach it, so the agent needs no login of its own.

"Abmelden" ends the agent, everything it started, and then every process
left with that uid. "Benutzer wechseln" only ends the browser's session:
the agent and its apps keep running."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from pathlib import Path

from . import config
from .accounts import Account

AGENTS: dict[int, asyncio.subprocess.Process] = {}
_starting: dict[int, asyncio.Lock] = {}
LOGS = config.SYSTEM / "logs"


def running(uid: int) -> bool:
    p = AGENTS.get(uid)
    return bool(p and p.returncode is None)


async def _socket_up(sock: Path, timeout: float = 10.0) -> bool:
    for _ in range(int(timeout / 0.1)):
        if sock.exists():
            with contextlib.suppress(OSError):
                _r, w = await asyncio.open_unix_connection(str(sock))
                w.close()
                return True
        await asyncio.sleep(0.1)
    return False


async def ensure(acct: Account) -> Path:
    """The account's agent socket, starting the agent if it is not running."""
    sock = config.agent_socket(acct.uid)
    lock = _starting.setdefault(acct.uid, asyncio.Lock())
    async with lock:
        if running(acct.uid) and sock.exists():
            return sock
        run = config.user_run(acct.uid)
        run.mkdir(parents=True, exist_ok=True)
        os.chown(run, acct.uid, acct.uid)
        os.chmod(run, 0o700)
        with contextlib.suppress(FileNotFoundError):
            sock.unlink()
        LOGS.mkdir(parents=True, exist_ok=True)
        os.chmod(LOGS, 0o700)
        env = {
            "HOME": str(acct.home), "USER": acct.name, "LOGNAME": acct.name, "SHELL": "/bin/zsh",
            "AKARI_FULLNAME": acct.fullname, "AKARI_HOSTNAME": config.HOSTNAME, "AKARI_RUN": str(config.RUN),
            "LANG": os.environ.get("LANG", "C.UTF-8"), "PATH": "/usr/local/bin:/usr/bin:/bin",
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
            "XDG_RUNTIME_DIR": str(run), "XDG_CURRENT_DESKTOP": "Akari", "XDG_SESSION_TYPE": "x11",
            # uploads are spooled here, not in the small /tmp
            "TMPDIR": str(acct.home / ".cache" / "akari" / "tmp"),
        }
        with open(LOGS / f"{acct.name}.log", "ab", buffering=0) as log:
            # setpriv becomes the user before the agent starts: uid, gid, the groups
            # from /etc/group (akari-admin for sudo), no capabilities left
            p = await asyncio.create_subprocess_exec(
                "setpriv", f"--reuid={acct.uid}", f"--regid={acct.uid}", "--init-groups", "--reset-env",
                "--", "/usr/bin/env", *[f"{k}={v}" for k, v in env.items()], sys.executable, "-m", "akari.agent",
                env={}, cwd=acct.home,
                stdin=asyncio.subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        AGENTS[acct.uid] = p
        if not await _socket_up(sock):
            await stop(acct.uid)
            raise RuntimeError("Die Sitzung ließ sich nicht starten.")
        return sock


def _uid_pids(uid: int) -> list[int]:
    pids = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/status") as f:
                for line in f:
                    if line.startswith("Uid:"):
                        if int(line.split()[1]) == uid:
                            pids.append(int(d))
                        break
        except OSError:
            continue
    return pids


async def stop(uid: int) -> None:
    """End a session completely: the agent cleans up after itself, then
    nothing with this uid is left running."""
    p = AGENTS.pop(uid, None)
    if p and p.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            p.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(p.wait(), 6)
        except asyncio.TimeoutError:
            pass
    for sig in (signal.SIGTERM, signal.SIGKILL):
        pids = _uid_pids(uid)
        if not pids:
            break
        for pid in pids:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(pid, sig)
        await asyncio.sleep(1.0)
    if p and p.returncode is None:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(p.wait(), 2)


async def stop_all() -> None:
    await asyncio.gather(*(stop(uid) for uid in list(AGENTS)))
