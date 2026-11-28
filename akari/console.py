"""The console: where Akari OS is, shown before the login prompt.

Akari OS boots to a text console; the desktop is in the browser. So the
console says where: the address (https, through Caddy) and the same as a
QR code for a phone. While no account exists it shows the setup link
instead, token and all: whoever sits at the console owns the machine anyway.

agetty shows every file in /run/issue.d before its prompt; akarid writes
50-akari.issue there at start and again when the address changes, and
asks agetty to draw the prompt again (agetty --reload).

kmscon (the console since 0.16, akari-shell) reads the files only when it
starts, and at boot it starts before akarid has an address to write: on a
machine that waits for DHCP the code came only after the first logout. So
when the text changes and nobody is signed in on tty1, akarid starts that
console again; someone signed in there (a logind session on VT 1) is never
interrupted."""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import sys
import time
from pathlib import Path

from . import accounts, auth, config, motd

ISSUE = Path(os.environ.get("AKARI_ISSUE", "/run/issue.d/50-akari.issue"))


def _ip(*args: str) -> str:
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        return subprocess.run(["ip", *args], capture_output=True, text=True, timeout=3).stdout
    return ""


def address() -> str | None:
    """The address the machine is reached at: the one it reaches the world from,
    else the first global IPv4 address it has (a network without a default
    route, as host-only networks of VMs), else a global IPv6 address."""
    out = _ip("-4", "-o", "route", "get", "1.1.1.1").split()
    if "src" in out:
        return out[out.index("src") + 1]
    for family in ("-4", "-6"):
        for line in _ip(family, "-o", "addr", "show", "scope", "global").splitlines():
            parts = line.split()
            if "inet" in parts or "inet6" in parts:
                addr = parts[parts.index("inet" if family == "-4" else "inet6") + 1].split("/")[0]
                if addr and "tentative" not in parts:
                    return addr if family == "-4" else f"[{addr}]"
    return None


QUIET = 2          # light modules round the code: enough for a phone, small enough for 25 rows


def _matrix(text: str) -> list[list[bool]]:
    """The code's modules, True for dark, without a margin (qrencode's ASCII: "##" dark, "  " light)."""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        r = subprocess.run(["qrencode", "-t", "ASCII", "-m", "0", text], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return [[line[i:i + 2] == "##" for i in range(0, len(line) - 1, 2)] for line in r.stdout.splitlines() if line]
    return []


def _qr(text: str) -> str:
    """The code in half blocks, two modules a character: light modules lit, dark ones the console's
    black, so it reads as a printed code. The quiet zone is the same on every side; with an odd
    number of rows the last half row is the console's black, so the margin below is no wider."""
    m = _matrix(text)
    if not m:
        return ""
    n = len(m) + 2 * QUIET
    light = [[True] * n for _ in range(QUIET)] + [[True] * QUIET + [not d for d in row] + [True] * QUIET for row in m] \
        + [[True] * n for _ in range(QUIET)]
    if len(light) % 2:
        light.append([False] * n)      # the console's black: a light half row here made the margin below wider
    glyph = {(True, True): "█", (True, False): "▀", (False, True): "▄", (False, False): " "}
    return "\n".join("".join(glyph[(a, b)] for a, b in zip(light[i], light[i + 1])) for i in range(0, len(light), 2)) + "\n"


def text(ip: str | None, waiting: bool = False) -> str:
    # agetty reads backslashes as escapes (\n is the hostname): none may come from us unescaped
    if not ip:
        body = ["  Warte auf das Netzwerk …" if waiting else "  Noch keine Netzwerkadresse. Ist das Netzwerk verbunden?"]
        qr = ""
    else:
        url = f"https://{ip}/"
        if accounts.needs_setup():
            link = f"{url}?token={auth.SETUP_TOKEN}"
            body = ["  Einrichten im Browser:", f"  {link}"]
            qr = _qr(link)
        else:
            body = ["  Im Browser:", f"  {url}"]
            qr = _qr(url)
    # Akari's mark beside the name and the address, as in the welcome after login (motd.py);
    # \n is the machine's name (agetty and kmscon both know it), added after escaping ours
    info = [f"{config.OS_NAME} {config.VERSION}", "\x00", "", *[l.strip() for l in body]]
    mark = [l.replace("\x01", "").replace("\x02", "") for l in motd.LOGO]
    lines = [""]
    for i in range(max(len(mark), len(info))):
        left = (mark[i] if i < len(mark) else "").ljust(motd.WIDTH)
        lines.append(f"  {left}  {info[i] if i < len(info) else ''}".rstrip())
    lines.append("")
    if qr:
        lines += ["  " + l for l in qr.rstrip("\n").splitlines()] + [""]
    out = "\n".join(l.replace("\\", "\\\\") for l in lines) + "\n"
    return out.replace("\x00", "\\n")


def _run(*cmd: str) -> str:
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
    return ""


def signed_in_on_tty1() -> bool:
    """Whether someone is signed in at the machine's first console (a user session on VT 1)."""
    for line in _run("loginctl", "list-sessions", "--no-legend").splitlines():
        sid = line.split()[0] if line.split() else ""
        props = dict(l.split("=", 1) for l in _run("loginctl", "show-session", sid, "-p", "VTNr", "-p", "Class").splitlines() if "=" in l)
        if props.get("VTNr") == "1" and props.get("Class") == "user":
            return True
    return False


def redraw() -> None:
    """Show the new text: agetty draws its prompt again; kmscon, which cannot, starts again
    on tty1 while nobody is signed in there."""
    _run("agetty", "--reload")
    if _run("systemctl", "is-active", "kmsconvt@tty1.service").strip() == "active" and not signed_in_on_tty1():
        _run("systemctl", "restart", "kmsconvt@tty1.service")


def write(ip: str | None, waiting: bool = False) -> None:
    new = text(ip, waiting)
    with contextlib.suppress(OSError):
        if ISSUE.read_text(encoding="utf-8") == new:
            return                     # akarid started again (an update): the console already says this
    ISSUE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ISSUE.with_suffix(".tmp")
    tmp.write_text(new, encoding="utf-8")
    os.chmod(tmp, 0o644 if not accounts.needs_setup() else 0o600)
    os.replace(tmp, ISSUE)
    redraw()


async def watch() -> None:
    """Keep the console right: at start, and whenever the address or the setup state changes."""
    last = None
    started = time.monotonic()
    while True:
        # right after boot the network may still be coming: look every second and
        # say so, for two minutes; after that every ten seconds
        early = time.monotonic() - started < 120
        try:
            now = (await asyncio.to_thread(address), accounts.needs_setup(), early)
            if now != last:
                await asyncio.to_thread(write, now[0], early)
                last = now
        except Exception as e:       # one bad round must not leave the console behind for good
            print(f"  Konsole: {e!r}", file=sys.stderr, flush=True)
        await asyncio.sleep(1 if early else 10)
