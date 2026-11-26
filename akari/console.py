"""The console: where Akari OS is, shown before the login prompt.

Akari OS boots to a text console; the desktop is in the browser. So the
console says where: the address (https, through Caddy) and the same as a
QR code for a phone. While no account exists it shows the setup link
instead, token and all: whoever sits at the console owns the machine anyway.

agetty shows every file in /run/issue.d before its prompt; akarid writes
50-akari.issue there at start and again when the address changes, and
asks agetty to draw the prompt again (agetty --reload)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
from pathlib import Path

from . import accounts, auth, config

ISSUE = Path(os.environ.get("AKARI_ISSUE", "/run/issue.d/50-akari.issue"))


def address() -> str | None:
    """The IPv4 address the machine reaches the world from (its main one)."""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        out = subprocess.run(["ip", "-4", "-o", "route", "get", "1.1.1.1"], capture_output=True, text=True, timeout=3).stdout.split()
        if "src" in out:
            return out[out.index("src") + 1]
    return None


def _qr(text: str) -> str:
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        r = subprocess.run(["qrencode", "-t", "UTF8", "-m", "1", text], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout
    return ""


def text(ip: str | None) -> str:
    # agetty reads backslashes as escapes (\n is the hostname): none may come from us unescaped
    if not ip:
        body = ["  Noch keine Netzwerkadresse. Ist das Netzwerk verbunden?"]
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
    lines = ["", f"  {config.OS_NAME} {config.VERSION}", "", *body, ""]
    if qr:
        lines += ["  " + l for l in qr.rstrip("\n").splitlines()] + [""]
    return "\n".join(l.replace("\\", "\\\\") for l in lines) + "\n"


def write(ip: str | None) -> None:
    ISSUE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ISSUE.with_suffix(".tmp")
    tmp.write_text(text(ip), encoding="utf-8")
    os.chmod(tmp, 0o644 if not accounts.needs_setup() else 0o600)
    os.replace(tmp, ISSUE)
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(["agetty", "--reload"], capture_output=True, timeout=3)


async def watch() -> None:
    """Keep the console right: at start, and whenever the address or the setup state changes."""
    last = None
    while True:
        now = (await asyncio.to_thread(address), accounts.needs_setup())
        if now != last:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(write, now[0])
            last = now
        await asyncio.sleep(10)
