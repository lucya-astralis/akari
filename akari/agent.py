"""python -m akari.agent: one person's session, running as their Linux user.

Runs in akari-session@<name>.service. Serves terminal, files, apps and
preferences on a Unix socket only that user and root can open (its folder,
/run/user/<uid>/akari, is 0700). akarid checks who is signed in and
passes requests through; the agent trusts whoever reaches the socket, which
can only be its own user or root."""

from __future__ import annotations

import contextlib
import os
import signal
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from . import audio, config, desktops, display, files, media, sshkeys, stats, system, term


@asynccontextmanager
async def lifespan(_app: FastAPI):
    config.ensure_user_dirs()
    yield
    await display.stop_all()
    await media.stop_all()
    term.hangup_all()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(system.router)
app.include_router(desktops.router)
app.include_router(files.router)
app.include_router(display.router)
app.include_router(display.events)
app.include_router(term.router)
app.include_router(sshkeys.router)
app.include_router(stats.router)
app.include_router(media.router)
app.include_router(audio.router)


def main() -> None:
    if os.getuid() == 0:
        sys.exit("Der Agent läuft nie als root.")
    os.umask(0o077)
    sock = config.agent_socket(os.getuid())
    sock.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # what a desktop session sets for its programs; uploads spool in the home, not the small /tmp
    tmp = config.CACHE / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    os.environ.update(XDG_CURRENT_DESKTOP="Akari", TMPDIR=str(tmp), SHELL=config.SHELL)
    with contextlib.suppress(FileNotFoundError):
        sock.unlink()
    # SIGTERM from systemd: let uvicorn shut down cleanly, so lifespan ends the apps
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    uvicorn.run(app, uds=str(sock), log_level="warning", ws="websockets", server_header=False,
                timeout_graceful_shutdown=4)


if __name__ == "__main__":
    main()
