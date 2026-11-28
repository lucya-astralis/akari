"""Server roles, as Windows Server has them: what a machine is for, added and taken away as a whole.

A role is an apt metapackage, akari-role-<id> (debian/control), that brings
what the role needs; adding one is installing it, taking one away is removing
it with what came only for it (apt's autoremove). Data stays: Docker's
volumes, Samba's shares, a game's worlds. Both run as host.py's apt job, in
the unit that also does updates, so it outlives akarid and its log is there.

Here: which roles there are, what each brings and shows (its services, its
ports, the app that manages it), and whether it is on this machine. A role
counts as there when its metapackage is, or when everything it brings is
already installed by hand (Docker from before 0.23): adding it then only
installs the metapackage, nothing else changes.

Roles that are planned but not built yet are listed with soon=True: the
Server-Manager shows them, greyed, so the idea of the machine is visible."""

from __future__ import annotations

import re
import subprocess

from . import host


class RoleError(Exception):
    pass


ROLES = [
    {"id": "container", "name": "Container-Host", "icon": "app-docker",
     "summary": "Docker und Compose: Dienste in Containern, neben dem Desktop.",
     "packages": ["docker.io", "docker-compose"], "services": ["docker.service", "containerd.service"],
     "ports": [], "app": "docker",
     "remove_note": "Docker hält an, alle Container stoppen. Images, Volumes und Container bleiben in /var/lib/docker."},
    {"id": "files", "name": "Dateiserver", "icon": "app-files",
     "summary": "Samba: Ordner im Netz freigeben, für Windows, macOS und Linux.",
     "packages": ["samba", "wsdd2"], "services": ["smbd.service", "nmbd.service", "wsdd2.service"],
     "ports": ["445/tcp", "139/tcp", "5357/tcp", "3702/udp"], "app": None,
     "remove_note": "Freigaben sind danach nicht mehr erreichbar. Die Ordner und /etc/samba bleiben."},
    {"id": "gaming", "name": "Spieleserver", "icon": "app-window", "soon": True,
     "summary": "Spieleserver mit einem bewährten Panel (Pelican, Crafty), in Containern."},
    {"id": "cloudgaming", "name": "Cloud Gaming", "icon": "app-window", "soon": True,
     "summary": "Sunshine und Steam: spielen per Moonlight auf jedem Gerät. Begleitete Einrichtung je nach GPU."},
    {"id": "media", "name": "Medienserver", "icon": "app-music", "soon": True,
     "summary": "Jellyfin: Filme, Serien und Musik für alle Geräte im Haus."},
    {"id": "vpn", "name": "VPN", "icon": "app-window", "soon": True,
     "summary": "WireGuard: von unterwegs ins eigene Netz, das Handy per QR-Code."},
]
BY_ID = {r["id"]: r for r in ROLES}
ID = re.compile(r"^[a-z]{2,20}$")


def _role(rid: str) -> dict:
    r = BY_ID.get(rid) if ID.match(rid or "") else None
    if not r:
        raise RoleError("Diese Rolle gibt es nicht.")
    if r.get("soon"):
        raise RoleError("Diese Rolle kommt noch.")
    return r


def meta(rid: str) -> str:
    return f"akari-role-{rid}"


def _installed(names: list[str]) -> dict[str, bool]:
    if not names:
        return {}
    r = subprocess.run(["dpkg-query", "-W", "-f=${Package} ${db:Status-Status}\\n", *names], capture_output=True, text=True, timeout=15)
    found = {line.split()[0]: line.split()[1] == "installed" for line in r.stdout.splitlines() if len(line.split()) == 2}
    return {n: found.get(n, False) for n in names}


def _active(units: list[str]) -> dict[str, str]:
    if not units:
        return {}
    r = subprocess.run(["systemctl", "is-active", *units], capture_output=True, text=True, timeout=15)
    states = r.stdout.split()
    return {u: (states[i] if i < len(states) else "unknown") for i, u in enumerate(units)}


def roles() -> list[dict]:
    """Every role, with whether it is here: its metapackage, or all it brings, installed."""
    names = sorted({n for r in ROLES if not r.get("soon") for n in [meta(r["id"]), *r["packages"]]})
    have = _installed(names)
    units = sorted({u for r in ROLES if not r.get("soon") for u in r["services"]})
    active = _active(units)
    job = host.updates().get("running") or ""
    out = []
    for r in ROLES:
        if r.get("soon"):
            out.append({**r, "state": "soon"})
            continue
        own, parts = have.get(meta(r["id"])), all(have.get(p) for p in r["packages"])
        state = "installed" if own or parts else "absent"
        if job.startswith(f"role:{r['id']}:"):
            state = "adding" if job.endswith(":add") else "removing"
        out.append({**r, "state": state, "adopted": bool(parts and not own),
                    "services": [{"name": u, "active": active.get(u, "unknown")} for u in r["services"]]})
    return out


def command(rid: str, action: str) -> list[str]:
    """apt's command for adding or taking away a role (host.start runs it in its unit)."""
    r = _role(rid)
    if action == "add":
        return ["apt-get", "-y", "-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold", "install", meta(rid)]
    if action == "remove":
        # the metapackage and what it brought; also the role's packages by name, should they have been
        # installed by hand before there were roles. Data and configuration stay (remove, not purge).
        return ["apt-get", "-y", "remove", "--autoremove", meta(rid), *r["packages"]]
    raise RoleError("Unbekannte Aktion.")


def change(rid: str, action: str) -> None:
    host.start(f"role:{rid}:{action}", command(rid, action))
