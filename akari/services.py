"""The machine's services and its journal, for the Dienste app (accounts that manage).

systemd says what runs (systemctl list-units, list-unit-files, show) and keeps
what was said (journalctl). Read and changed as akarid, which is root: so only
accounts that manage see this at all, as with Docker.

A few units are kept out of reach of stop, restart and disable: akarid and
Caddy (stopping them cuts off the very page that asked), D-Bus, and systemd's
own. They still show, and their logs too."""

from __future__ import annotations

import contextlib
import json
import re
import subprocess

NAME = re.compile(r"^[A-Za-z0-9@._:-]{1,200}\.service$")
ACTIONS = ("start", "stop", "restart", "enable", "disable")
PROTECTED = re.compile(r"^(akarid|caddy|dbus|systemd-[a-z-]+|user@\d+|akari-session@[^.]+)\.service$")
PRIORITY = ("emerg", "alert", "crit", "err", "warning", "notice", "info", "debug")


class ServiceError(Exception):
    pass


def _run(*cmd: str, timeout: float = 15) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        raise ServiceError(f"{cmd[0]}: {e.__class__.__name__}") from None


def _json(*cmd: str) -> list:
    r = _run(*cmd)
    with contextlib.suppress(ValueError):
        return json.loads(r.stdout or "[]")
    return []


def _name(name: str) -> str:
    if not NAME.match(name or ""):
        raise ServiceError("Das ist kein Dienst.")
    return name


def protected(name: str) -> bool:
    return bool(PROTECTED.match(name))


def units() -> list[dict]:
    """Every service systemd knows that can be loaded: failed first, then what runs, then the rest."""
    files = {u.get("unit_file"): u.get("state") for u in _json("systemctl", "list-unit-files", "--type=service", "--output=json", "--no-pager")}
    seen, out = set(), []
    for u in _json("systemctl", "list-units", "--type=service", "--all", "--output=json", "--no-pager"):
        name = u.get("unit", "")
        if u.get("load") != "loaded" or not name.endswith(".service"):
            continue
        seen.add(name)
        base = re.sub(r"@[^.]+\.service$", "@.service", name)
        out.append({"name": name, "description": u.get("description", ""), "active": u.get("active"), "sub": u.get("sub"),
                    "enabled": files.get(name) or files.get(base), "protected": protected(name)})
    # what is installed but has not been loaded since boot (disabled and never started)
    for name, state in files.items():
        if name and name.endswith(".service") and "@" not in name and name not in seen and state not in ("masked", "static", "alias"):
            out.append({"name": name, "description": "", "active": "inactive", "sub": "dead", "enabled": state, "protected": protected(name)})
    rank = {"failed": 0, "active": 1, "activating": 1, "reloading": 1, "deactivating": 2}
    return sorted(out, key=lambda u: (rank.get(u["active"], 3), u["name"]))


def failed() -> list[str]:
    return [u["unit"] for u in _json("systemctl", "list-units", "--type=service", "--state=failed", "--output=json", "--no-pager")]


SHOW = ("Id", "Description", "ActiveState", "SubState", "UnitFileState", "LoadState", "MainPID", "MemoryCurrent", "CPUUsageNSec",
        "TasksCurrent", "NRestarts", "ActiveEnterTimestamp", "InactiveEnterTimestamp", "FragmentPath", "Result", "ExecMainStatus")


def detail(name: str) -> dict:
    r = _run("systemctl", "show", _name(name), "--no-pager", *(f"-p{p}" for p in SHOW))
    props = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    if props.get("LoadState") in (None, "not-found"):
        raise ServiceError("Diesen Dienst gibt es nicht.")
    num = lambda k: int(props[k]) if props.get(k, "").isdigit() else None     # "[not set]" and the like stay None
    return {"name": props.get("Id", name), "description": props.get("Description", ""), "active": props.get("ActiveState"),
            "sub": props.get("SubState"), "enabled": props.get("UnitFileState") or None, "pid": num("MainPID") or None,
            "memory": num("MemoryCurrent"), "cpu_ns": num("CPUUsageNSec"), "tasks": num("TasksCurrent"), "restarts": num("NRestarts"),
            "since": props.get("ActiveEnterTimestamp") or props.get("InactiveEnterTimestamp") or None,
            "path": props.get("FragmentPath") or None, "result": props.get("Result"), "status": num("ExecMainStatus"),
            "protected": protected(props.get("Id", name))}


def _entries(args: list[str], lines: int) -> list[dict]:
    r = _run("journalctl", *args, "-n", str(max(1, min(lines, 2000))), "-o", "json", "--no-pager", timeout=20)
    out = []
    for line in r.stdout.splitlines():
        with contextlib.suppress(ValueError):
            e = json.loads(line)
            msg = e.get("MESSAGE", "")
            if isinstance(msg, list):                          # bytes that were not text
                msg = bytes(msg).decode("utf-8", "replace")
            out.append({"t": int(e.get("__REALTIME_TIMESTAMP", 0)) // 1_000_000, "p": int(e.get("PRIORITY", 6) or 6),
                        "who": e.get("SYSLOG_IDENTIFIER") or e.get("_COMM") or "", "msg": str(msg)[:2000]})
    return out


def log(name: str, lines: int = 300) -> list[dict]:
    return _entries(["-u", _name(name)], lines)


def journal(priority: str = "warning", lines: int = 300, boot: bool = True) -> list[dict]:
    """The whole system's journal, from this level up (err: errors only, warning: warnings too, info: everything)."""
    if priority not in PRIORITY:
        raise ServiceError("Unbekannte Stufe.")
    return _entries(["-p", priority, *(["-b"] if boot else [])], lines)


def act(name: str, action: str) -> dict:
    name = _name(name)
    if action not in ACTIONS:
        raise ServiceError("Unbekannte Aktion.")
    if action in ("stop", "restart", "disable") and protected(name):
        raise ServiceError("Diesen Dienst braucht Akari selbst. Er lässt sich hier nicht anhalten.")
    cmd = ["systemctl", action, name] if action in ("start", "stop", "restart") else ["systemctl", action, "--now", name]
    r = _run(*cmd, timeout=60)
    if r.returncode:
        raise ServiceError((r.stderr or r.stdout).strip()[:300] or f"systemctl {action}: Fehler {r.returncode}")
    return detail(name)
