"""Software: what the system has, and how admins add to it.

Akari OS is a Debian system; programs come with apt, as anywhere else.
The page in Einstellungen says who may use sudo and how many packages
the system has."""

from __future__ import annotations

import asyncio
import os


async def _count() -> int:
    try:
        p = await asyncio.create_subprocess_exec("dpkg-query", "-W", "-f=${db:Status-Abbrev}\\n",
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    except FileNotFoundError:
        return 0
    out, _ = await p.communicate()
    return sum(1 for l in out.decode().splitlines() if l.startswith("ii"))


async def info() -> dict:
    return {"sudo": os.path.exists("/usr/bin/sudo"), "packages": await _count()}
