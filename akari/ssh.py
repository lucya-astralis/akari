"""SSH into Akari OS. akarid runs sshd as a child when an admin turns it on.

  /data/system/ssh/          host keys (made once per volume), sshd_config, settings
  port 2222 in the container (no NET_BIND_SERVICE needed for 22)

Who gets in: every account, with a key from its own ~/.ssh/authorized_keys;
with its password only if the account chose that (accounts.set_ssh_password
writes a crypt hash into shadow, otherwise the entry is '*'). No root, no
forwarding, no X11. sshd's privilege separation needs SYS_CHROOT and a /run
it can write (a tmpfs in compose.yaml)."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import signal
from pathlib import Path

from . import accounts, config

DIR = config.SYSTEM / "ssh"
SETTINGS = DIR / "settings.json"
CONF = DIR / "sshd_config"
PORT = int(os.environ.get("AKARI_SSH_PORT", "2222"))
PUBLIC = os.environ.get("AKARI_SSH_PUBLIC", "")       # how it is reached from outside, e.g. 127.0.0.1:2222
KEYS = ("ed25519", "rsa")

_proc: asyncio.subprocess.Process | None = None
_lock = asyncio.Lock()


def enabled() -> bool:
    try:
        return bool(json.loads(SETTINGS.read_text()).get("enabled"))
    except (OSError, ValueError):
        return False


def running() -> bool:
    return bool(_proc and _proc.returncode is None)


def _write_settings(on: bool) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DIR, 0o700)
    SETTINGS.write_text(json.dumps({"enabled": on}))


def fingerprints() -> list[str]:
    out = []
    for k in KEYS:
        pub = DIR / f"ssh_host_{k}_key.pub"
        try:
            kind, blob = pub.read_text().split()[:2]
        except (OSError, ValueError):
            continue
        digest = base64.b64encode(hashlib.sha256(base64.b64decode(blob)).digest()).decode().rstrip("=")
        out.append(f"{kind} SHA256:{digest}")
    return out


async def _run(*cmd: str) -> int:
    p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    return await p.wait()


async def _prepare() -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DIR, 0o700)
    for k in KEYS:
        key = DIR / f"ssh_host_{k}_key"
        if not key.exists():
            extra = ["-b", "3072"] if k == "rsa" else []
            await _run("ssh-keygen", "-q", "-t", k, *extra, "-N", "", "-C", f"akari-{k}", "-f", str(key))
    CONF.write_text("\n".join([
        "# written by akarid at every start; changes here do not last",
        f"Port {PORT}",
        *[f"HostKey {DIR}/ssh_host_{k}_key" for k in KEYS],
        "PidFile /run/akari-sshd.pid",
        "UsePAM no",
        "PermitRootLogin no",
        "PubkeyAuthentication yes",
        "AuthorizedKeysFile .ssh/authorized_keys",
        # every account has a hash in shadow (sudo needs it); sshd takes it only from those that allow it
        "PasswordAuthentication no",
        "PermitEmptyPasswords no",
        "KbdInteractiveAuthentication no",
        "StrictModes yes",
        "MaxAuthTries 4",
        "LoginGraceTime 30",
        "X11Forwarding no",
        "AllowTcpForwarding no",
        "AllowAgentForwarding no",
        "PermitTunnel no",
        "PrintMotd no",
        "PrintLastLog no",
        "AcceptEnv LANG LC_*",
        "Subsystem sftp internal-sftp",
        *([f"Match User {','.join(users)}", "    PasswordAuthentication yes"] if (users := accounts.ssh_password_users()) else []),
        "",
    ]))
    os.chmod(CONF, 0o600)
    Path("/run/sshd").mkdir(mode=0o755, exist_ok=True)


async def start() -> None:
    global _proc
    async with _lock:
        if running():
            return
        await _prepare()
        logs = config.SYSTEM / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        with open(logs / "sshd.log", "ab", buffering=0) as log:
            _proc = await asyncio.create_subprocess_exec("/usr/sbin/sshd", "-D", "-e", "-f", str(CONF),
                                                         stdout=log, stderr=log, start_new_session=True)
        await asyncio.sleep(0.4)
        if _proc.returncode is not None:
            raise RuntimeError("sshd ist nicht gestartet. Mehr in /data/system/logs/sshd.log.")


async def stop() -> None:
    global _proc
    async with _lock:
        p, _proc = _proc, None
        if p and p.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                p.send_signal(signal.SIGTERM)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(p.wait(), 4)


async def reload() -> None:
    """New config (who may use passwords), read by the running sshd on SIGHUP."""
    if running():
        await _prepare()
        with contextlib.suppress(ProcessLookupError):
            _proc.send_signal(signal.SIGHUP)


async def set_enabled(on: bool) -> None:
    _write_settings(on)
    await (start() if on else stop())


async def boot() -> None:
    """At akarid's start: sshd again if it was on."""
    if enabled():
        with contextlib.suppress(RuntimeError):
            await start()


def info() -> dict:
    return {"enabled": enabled(), "running": running(), "port": PORT, "public": PUBLIC or None,
            "fingerprints": fingerprints()}
