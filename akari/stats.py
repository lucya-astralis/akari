"""What the machine is doing: load, memory, network, and the processes.
Runs in the session agent, as the user.

Everything comes from /proc. CPU shares are the difference between two
looks, so the first answer after a pause covers a short sample. The numbers
are the whole machine's, shared by every account on it.

Everyone sees every process (as on any Linux without hidepid); a process can
only be ended by its own user, which the kernel checks anyway."""

from __future__ import annotations

import asyncio
import os
import pwd
import shutil
import signal
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import config

router = APIRouter(prefix="/api")
HZ = os.sysconf("SC_CLK_TCK")
PAGE = os.sysconf("SC_PAGE_SIZE")
_cpu_last: tuple[float, list[tuple[int, int]]] | None = None
_proc_last: tuple[float, dict[int, int]] = (0.0, {})
_net_last: tuple[float, int, int] | None = None
_names: dict[int, str] = {}


def _cpu_times() -> list[tuple[int, int]]:
    """(busy, total) for all cores together, then each core."""
    out = []
    with open("/proc/stat") as f:
        for line in f:
            if not line.startswith("cpu"):
                break
            v = [int(x) for x in line.split()[1:]]
            idle = v[3] + (v[4] if len(v) > 4 else 0)
            out.append((sum(v) - idle, sum(v)))
    return out


async def _cpu() -> tuple[float, list[float]]:
    global _cpu_last
    now = time.time()
    if not _cpu_last or now - _cpu_last[0] > 5:
        _cpu_last = (now, _cpu_times())
        await asyncio.sleep(0.25)
    a, b = _cpu_last[1], _cpu_times()
    _cpu_last = (time.time(), b)
    pct = [round(100 * (b1 - a1) / max(1, t1 - t0), 1) for (a1, t0), (b1, t1) in zip(a, b)]
    return (pct[0] if pct else 0.0), pct[1:]


def _mem() -> dict:
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0]) * 1024
    total, avail = info.get("MemTotal", 0), info.get("MemAvailable", 0)
    return {"total": total, "used": total - avail, "available": avail,
            "swap_total": info.get("SwapTotal", 0), "swap_used": info.get("SwapTotal", 0) - info.get("SwapFree", 0)}


def _net() -> dict:
    global _net_last
    rx = tx = 0
    with open("/proc/net/dev") as f:
        for line in f.readlines()[2:]:
            name, rest = line.split(":", 1)
            if name.strip() == "lo":
                continue
            v = rest.split()
            rx += int(v[0]); tx += int(v[8])
    now = time.time()
    out = {"rx": 0, "tx": 0}
    if _net_last and now > _net_last[0]:
        dt = now - _net_last[0]
        out = {"rx": max(0, int((rx - _net_last[1]) / dt)), "tx": max(0, int((tx - _net_last[2]) / dt))}
    _net_last = (now, rx, tx)
    return out


@router.get("/stats")
async def stats() -> dict:
    cpu, cores = await _cpu()
    disk = shutil.disk_usage(config.HOME)
    with open("/proc/uptime") as f:
        up = float(f.read().split()[0])
    return {
        "cpu": cpu, "cores": cores, "load": list(os.getloadavg()), "mem": _mem(), "net": _net(),
        "disk": {"total": disk.total, "used": disk.used},
        "uptime": int(up), "procs": sum(1 for p in os.listdir("/proc") if p.isdigit()), "at": int(time.time()),
    }


def _user(uid: int) -> str:
    if uid not in _names:
        try:
            _names[uid] = pwd.getpwuid(uid).pw_name
        except KeyError:
            _names[uid] = str(uid)
    return _names[uid]


@router.get("/procs")
def procs() -> dict:
    global _proc_last
    now = time.time()
    last_t, last = _proc_last
    dt = now - last_t if last_t else 0
    seen, out = {}, []
    mine = os.getuid()
    with open("/proc/uptime") as f:
        up = float(f.read().split()[0])
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        pid = int(d)
        try:
            with open(f"/proc/{pid}/stat") as f:
                raw = f.read()
            name = raw[raw.index("(") + 1:raw.rindex(")")]
            rest = raw[raw.rindex(")") + 2:].split()
            state, ticks = rest[0], int(rest[11]) + int(rest[12])
            start, rss = int(rest[19]) / HZ, int(rest[21]) * PAGE
            uid = os.stat(f"/proc/{pid}").st_uid
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd = f.read().replace(b"\0", b" ").decode(errors="replace").strip()
            except OSError:
                cmd = ""
        except (OSError, ValueError, IndexError):
            continue
        seen[pid] = ticks
        cpu = round(100 * (ticks - last[pid]) / HZ / dt, 1) if dt and pid in last else 0.0
        out.append({"pid": pid, "name": name, "cmd": cmd[:300] or f"[{name}]", "user": _user(uid), "mine": uid == mine,
                    "state": state, "cpu": max(0.0, cpu), "rss": rss, "age": int(up - start)})
    _proc_last = (now, seen)
    return {"procs": out, "me": _user(mine), "agent": os.getpid()}


class SignalIn(BaseModel):
    sig: str = "TERM"


@router.post("/procs/{pid}/signal")
def send(pid: int, body: SignalIn) -> dict:
    sig = {"TERM": signal.SIGTERM, "KILL": signal.SIGKILL, "STOP": signal.SIGSTOP, "CONT": signal.SIGCONT}.get(body.sig)
    if not sig:
        raise HTTPException(400, "Dieses Signal gibt es hier nicht.")
    if pid in (os.getpid(), os.getppid(), 1):
        raise HTTPException(403, "Das ist die Sitzung selbst.")
    try:
        if os.stat(f"/proc/{pid}").st_uid != os.getuid():
            raise HTTPException(403, "Das ist nicht dein Prozess.")
        os.kill(pid, sig)
    except FileNotFoundError:
        raise HTTPException(404, "Diesen Prozess gibt es nicht mehr.")
    except PermissionError:
        raise HTTPException(403, "Das ist nicht dein Prozess.")
    return {"ok": True}
