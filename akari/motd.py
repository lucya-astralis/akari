#!/usr/bin/python3 -I
"""The welcome after signing in at the console or over SSH: Akari's mark, and
beside it what is worth knowing at a glance, as Ubuntu's sysinfo does.

pam_motd runs /etc/update-motd.d/* as root at every login; 10-akari runs
this file. It stands alone (no akari imports, standard library only) and
asks nothing slow: the update count is what akarid last found (apt.json),
Docker is asked over its socket with a short timeout. Whatever is not there
is left out rather than shown as an error.

    python3 motd.py            the welcome, coloured
    NO_COLOR=1 python3 motd.py without colour
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path("/var/lib/akari")

# the mark: wings in Facet's violet, head and tail white (the fastfetch logo, smaller)
LOGO = [
    "     \x01▄█\x02",
    "    \x01▄█▀\x02 ▄▄▄▄",
    "   \x01▄█▀\x02 ▄███▀",
    "  \x01▄█▀\x02 ▄███▀ ▄▄▄▄",
    " \x01▄█▀\x02 ▄███▀ ▄███▀",
    "\x01▄█▀\x02 ▄███▀ ▄███▀",
]
WIDTH = 16

COLOUR = not os.environ.get("NO_COLOR")
VIOLET, WHITE, DIM, KEY, OK, WARN, RESET = (
    ("\033[38;5;141m", "\033[97m", "\033[38;5;245m", "\033[38;5;141m", "\033[38;5;114m", "\033[38;5;221m", "\033[0m")
    if COLOUR else ("",) * 7)


def _run(*cmd: str, timeout: float = 2) -> str:
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    return ""


def _json(path: Path) -> dict:
    with contextlib.suppress(OSError, ValueError):
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def version() -> str:
    with contextlib.suppress(OSError):
        m = re.search(r'^VERSION = "([^"]+)"', (HERE / "config.py").read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    return ""


def debian() -> str:
    with contextlib.suppress(OSError):
        v = Path("/etc/debian_version").read_text().strip()
        code = re.search(r"^VERSION_CODENAME=(\S+)", Path("/etc/os-release").read_text(), re.M)
        return f"Debian {v}" + (f" ({code.group(1)})" if code else "")
    return ""


def address() -> str | None:
    out = _run("ip", "-4", "-o", "route", "get", "1.1.1.1").split()
    if "src" in out:
        return out[out.index("src") + 1]
    for line in _run("ip", "-4", "-o", "addr", "show", "scope", "global").splitlines():
        parts = line.split()
        if "inet" in parts:
            return parts[parts.index("inet") + 1].split("/")[0]
    return None


def _gb(n: float) -> str:
    return f"{n / 1e9:.1f}".replace(".", ",") + " GB"


def _bar(frac: float) -> str:
    """A percentage, coloured by how full."""
    pct = round(frac * 100)
    c = OK if pct < 75 else WARN if pct < 90 else "\033[38;5;203m" if COLOUR else ""
    return f"{c}{pct} %{RESET}"


def uptime() -> str:
    with contextlib.suppress(OSError, ValueError):
        s = int(float(Path("/proc/uptime").read_text().split()[0]))
        d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
        parts = ([f"{d} {'Tag' if d == 1 else 'Tage'}"] if d else []) + ([f"{h} Std."] if h else []) + ([f"{m} Min."] if not d else [])
        return ", ".join(parts) or "gerade eben"
    return ""


def load() -> str:
    with contextlib.suppress(OSError):
        one, five, fifteen = os.getloadavg()
        cpus = os.cpu_count() or 1
        return f"{one:.2f} {five:.2f} {fifteen:.2f}".replace(".", ",") + f"{DIM} · {cpus} {'Kern' if cpus == 1 else 'Kerne'}{RESET}"
    return ""


def memory() -> str:
    with contextlib.suppress(OSError, ValueError, KeyError):
        info = {l.split(":")[0]: int(l.split()[1]) * 1024 for l in Path("/proc/meminfo").read_text().splitlines()}
        total, avail = info["MemTotal"], info["MemAvailable"]
        return f"{_gb(total - avail)} / {_gb(total)}  {_bar((total - avail) / total)}"
    return ""


def disk(path: str = "/") -> str:
    with contextlib.suppress(OSError):
        u = shutil.disk_usage(path)
        return f"{_gb(u.used)} / {_gb(u.total)}  {_bar(u.used / u.total)}"
    return ""


def updates() -> str:
    s = _json(STATE / "apt.json")
    n = s.get("count")
    if n is None:
        return ""
    return f"{WARN}{n} verfügbar{RESET}{DIM} · Einstellungen → Updates{RESET}" if n else f"{OK}aktuell{RESET}"


def docker() -> str:
    """Running containers, over the socket (no docker CLI needed, nothing slow)."""
    path = "/var/run/docker.sock"
    if not os.path.exists(path):
        return ""
    with contextlib.suppress(OSError, ValueError), socket.socket(socket.AF_UNIX) as s:
        s.settimeout(1)
        s.connect(path)
        s.sendall(b"GET /v1.43/info HTTP/1.0\r\nHost: docker\r\n\r\n")
        raw = b""
        while chunk := s.recv(65536):
            raw += chunk
        info = json.loads(raw.split(b"\r\n\r\n", 1)[1])
        on, all_ = info.get("ContainersRunning", 0), info.get("Containers", 0)
        return f"{on} von {all_} Containern laufen" if all_ else "keine Container"
    return ""


def lucent() -> str:
    p = _json(STATE / "lucent.json")
    if not p.get("issuer"):
        return ""
    # a Lucent on this machine (from the Docker app) has an inside address: say where it is instead
    if re.match(r"^https?://(0\.0\.0\.0|127\.|localhost|lucya-lucent)", p.get("lucent_url") or p["issuer"]):
        return f"gekoppelt{DIM} · auf diesem Rechner, Port 8060{RESET}"
    return f"gekoppelt{DIM} · {p['issuer']}{RESET}"


def accounts() -> str:
    """Who is in the desktop right now (akari-session@<name> units)."""
    out = _run("systemctl", "list-units", "--state=active", "--no-legend", "--plain", "akari-session@*.service")
    names = sorted({m.group(1) for m in re.finditer(r"akari-session@(.+?)\.service", out)})
    return ", ".join(names) if names else ""


def lines() -> list[str]:
    ip = address()
    v = version()
    rows = [
        ("", f"{WHITE}Akari OS{RESET} {v}{DIM} · {debian()}{RESET}" if v else f"{WHITE}Akari OS{RESET}"),
        ("", ""),
        ("Im Browser", f"{WHITE}https://{ip}/{RESET}" if ip else f"{WARN}keine Netzwerkadresse{RESET}"),
        ("Läuft seit", uptime()),
        ("Last", load()),
        ("Speicher", memory()),
        ("Platte", disk("/")),
        ("Updates", updates()),
        ("Im Desktop", accounts()),
        ("Docker", docker()),
        ("Lucent", lucent()),
    ]
    info = [(f"{KEY}{k:<11}{RESET} {v}" if k else v) for k, v in rows if v or not k]
    logo = [l.replace("\x01", VIOLET).replace("\x02", WHITE) + RESET for l in LOGO]
    plain = [l.replace("\x01", "").replace("\x02", "") for l in LOGO]
    out = [""]
    for i in range(max(len(logo), len(info))):
        mark = (" " + logo[i] + " " * (WIDTH - len(plain[i]))) if i < len(logo) else " " * (WIDTH + 1)
        out.append(f"{mark}  {info[i] if i < len(info) else ''}".rstrip())
    return out + [""]


if __name__ == "__main__":
    # a clean screen first: the login prompt and the QR code above it are done with
    if COLOUR:
        print("\033[H\033[2J", end="")
    print("\n".join(lines()))
