"""SSH into Akari OS: the system's own OpenSSH (ssh.service, port 22).

An admin turns it on and off in Einstellungen → SSH (systemctl enable/disable
--now ssh). Akari writes /etc/ssh/sshd_config.d/akari.conf: no root, no
passwords, except for accounts that chose to allow theirs (a Match block).
Keys come from each account's ~/.ssh/authorized_keys, as anywhere else.
Debian makes the host keys when openssh-server is installed."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
from pathlib import Path

from . import accounts

UNIT = "ssh.service"
ETC = Path(os.environ.get("AKARI_SSH_ETC", "/etc/ssh"))
CONF = ETC / "sshd_config.d" / "akari.conf"
PORT = int(os.environ.get("AKARI_SSH_PORT", "22"))
PUBLIC = os.environ.get("AKARI_SSH_PUBLIC", "")       # how it is reached from outside, e.g. 127.0.0.1:2223
KEYS = ("ed25519", "ecdsa", "rsa")

_lock = asyncio.Lock()


async def _systemctl(*args: str) -> tuple[int, str]:
    p = await asyncio.create_subprocess_exec("systemctl", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await p.communicate()
    return p.returncode or 0, out.decode(errors="replace").strip()


def fingerprints() -> list[str]:
    out = []
    for k in KEYS:
        pub = ETC / f"ssh_host_{k}_key.pub"
        try:
            kind, blob = pub.read_text().split()[:2]
        except (OSError, ValueError):
            continue
        digest = base64.b64encode(hashlib.sha256(base64.b64decode(blob)).digest()).decode().rstrip("=")
        out.append(f"{kind} SHA256:{digest}")
    return out


def config_text() -> str:
    users = accounts.ssh_password_users()
    return "\n".join([
        "# Akari OS: written by akarid (Einstellungen → SSH); changes here do not last.",
        "# sshd takes the first value it reads, and this file comes before sshd_config.",
        "PermitRootLogin no",
        "PasswordAuthentication no",
        "KbdInteractiveAuthentication no",
        "PermitEmptyPasswords no",
        # Match goes last: it holds until the end of this file
        *([f"Match User {','.join(users)}", "    PasswordAuthentication yes"] if users else []),
        "",
    ])


def write_config() -> bool:
    """akari.conf as the accounts want it. True if it changed."""
    text = config_text()
    try:
        if CONF.read_text() == text:
            return False
    except OSError:
        pass
    CONF.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONF.with_suffix(".tmp")
    tmp.write_text(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, CONF)
    return True


async def state() -> tuple[bool, bool]:
    """(enabled at boot, running now)"""
    _, enabled = await _systemctl("is-enabled", UNIT)
    code, _ = await _systemctl("is-active", "--quiet", UNIT)
    return enabled.splitlines()[-1:] == ["enabled"], code == 0


async def reload() -> None:
    """New config (who may use passwords): sshd reads it again on reload."""
    async with _lock:
        if write_config():
            await _systemctl("try-reload-or-restart", UNIT)


async def set_enabled(on: bool) -> None:
    async with _lock:
        write_config()
        code, out = await _systemctl("enable" if on else "disable", "--now", UNIT)
        if code != 0:
            raise RuntimeError(f"ssh ließ sich nicht {'einschalten' if on else 'ausschalten'}: {out}")


async def boot() -> None:
    """At akarid's start: akari.conf follows the accounts (one may have gone meanwhile)."""
    await reload()


async def info() -> dict:
    enabled, running = await state()
    return {"enabled": enabled, "running": running, "port": PORT, "public": PUBLIC or None,
            "fingerprints": fingerprints()}
