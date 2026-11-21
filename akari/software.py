"""Software: what admins install with sudo apt, kept across image updates.

The image's own packages are listed at build time
(/usr/share/akari/apt/baseline.list). After every dpkg run an apt hook
(/usr/local/sbin/akari-apt-record) writes the packages installed on top of
that to /data/system/apt/packages.list, in the volume. When akarid starts on a
new image those packages are missing from the root filesystem; it installs
them again, in the background, and logs to /data/system/logs/apt-restore.log.

What this cannot keep: changes made by hand outside the package manager,
under /etc, /usr or /opt. Those belong in the home or in /data."""

from __future__ import annotations

import asyncio
import os
import time

from . import config

LIST = config.SYSTEM / "apt" / "packages.list"
LOG = config.SYSTEM / "logs" / "apt-restore.log"
STATE: dict = {"state": "idle", "missing": [], "at": None}


def wanted() -> list[str]:
    try:
        return [p.strip() for p in LIST.read_text().splitlines() if p.strip() and not p.startswith("#")]
    except FileNotFoundError:
        return []


async def _installed(pkgs: list[str]) -> set[str]:
    if not pkgs:
        return set()
    p = await asyncio.create_subprocess_exec("dpkg-query", "-W", "-f=${Package} ${Status}\\n", *pkgs,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await p.communicate()
    return {l.split()[0] for l in out.decode().splitlines() if l.endswith("install ok installed")}


def sudo_ready() -> dict:
    """Is real sudo possible in this container? (writable root, setuid allowed)"""
    nnp = False
    try:
        for line in open("/proc/self/status"):
            if line.startswith("NoNewPrivs:"):
                nnp = line.split()[1] == "1"
    except OSError:
        pass
    return {"sudo": os.path.exists("/usr/bin/sudo"), "writable": os.access("/usr/bin", os.W_OK), "setuid": not nnp}


async def _restore(missing: list[str]) -> None:
    STATE.update(state="restoring", missing=missing, at=int(time.time()))
    LOG.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
    with open(LOG, "ab", buffering=0) as log:
        log.write(f"\n== {time.strftime('%Y-%m-%d %H:%M:%S')} wieder einspielen: {' '.join(missing)}\n".encode())
        for cmd in (["apt-get", "update"], ["apt-get", "install", "-y", "--no-install-recommends", *missing]):
            p = await asyncio.create_subprocess_exec(*cmd, env=env, stdout=log, stderr=log, stdin=asyncio.subprocess.DEVNULL)
            if await p.wait() != 0:
                STATE.update(state="failed", at=int(time.time()))
                return
    from . import accounts
    await asyncio.to_thread(accounts.adopt_etc)     # packages may have made system users
    still = [x for x in missing if x not in await _installed(missing)]
    STATE.update(state="failed" if still else "done", missing=still, at=int(time.time()))


async def boot() -> None:
    """At akarid's start: put back what was installed before an image update."""
    want = wanted()
    ready = sudo_ready()
    if not want or not ready["writable"]:
        return
    missing = [p for p in want if p not in await _installed(want)]
    if missing:
        asyncio.create_task(_restore(missing))


async def info() -> dict:
    want = wanted()
    have = await _installed(want)
    return {**sudo_ready(), "packages": [{"name": p, "installed": p in have} for p in want], "restore": STATE}
