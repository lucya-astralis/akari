"""The terminal: a login shell on a pseudo-terminal, carried over a websocket.
Runs in the session agent, so the shell, the pty and everything started from
it belong to the signed-in user.

Frames: the browser sends keystrokes as binary frames and a resize as a text
frame {"t": "r", "c": cols, "r": rows}; the server sends the terminal's
output as binary frames. When the socket closes the shell's whole process
group gets SIGHUP, as when a real terminal window closes."""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
import os
import pty
import signal
import struct
import termios
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import config, desktopfiles, desktops, display, media

router = APIRouter()
SHELLS: set[int] = set()


def hangup_all() -> None:
    for pid in list(SHELLS):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGHUP)


def _winsize(fd: int, cols: int, rows: int) -> None:
    cols, rows = max(2, min(cols, 1000)), max(2, min(rows, 500))
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            n = os.write(fd, view)
            view = view[n:]
        except BlockingIOError:
            # a large paste: the line discipline is full, give it a moment
            time.sleep(0.005)


async def _reap(pid: int) -> None:
    """End the shell and everything it started; never leave a zombie."""
    for sig, wait in ((signal.SIGHUP, 1.0), (signal.SIGKILL, 1.0)):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, sig)
        for _ in range(int(wait / 0.05)):
            done, _status = os.waitpid(pid, os.WNOHANG)
            if done:
                return
            await asyncio.sleep(0.05)


@router.websocket("/api/term")
async def term(ws: WebSocket) -> None:
    await ws.accept()

    def num(key: str, default: int) -> int:
        try:
            return int(ws.query_params.get(key, default))
        except ValueError:
            return default

    # the desktop's default display: whatever starts here with a window shows up in Akari
    xenv = {}
    did = desktops.current(ws)
    if did:
        with contextlib.suppress(Exception):
            await display.ensure_default(did)
            xenv = display.default_env(did)
        with contextlib.suppress(Exception):
            xenv = {**xenv, **await media.env(did)}

    # a terminal program from its .desktop file (htop, vim): the browser names the
    # file, never a command; the shell runs it as a login shell would, then ends
    run = ws.query_params.get("run") or ""
    argv = [config.SHELL, "-l"]
    if run:
        entry = desktopfiles.apps().get(run)
        if not entry or not entry["terminal"]:
            await ws.close(code=4404)
            return
        import shlex
        argv = [config.SHELL, "-lc", shlex.join(entry["cmd"])]

    pid, fd = pty.fork()
    if pid == 0:  # the child: become the shell (pty.fork made it a session leader)
        try:
            os.chdir(config.HOME)
            env = {
                "HOME": str(config.HOME), "USER": config.NAME, "LOGNAME": config.NAME,
                "SHELL": config.SHELL, "TERM": "xterm-256color", "COLORTERM": "truecolor",
                "TERM_PROGRAM": "Akari Terminal", "TERM_PROGRAM_VERSION": config.VERSION,
                "LANG": os.environ.get("LANG", "C.UTF-8"), "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", "/tmp"),
                "XDG_CURRENT_DESKTOP": "Akari", "XDG_SESSION_TYPE": "x11",
                **xenv,
            }
            os.execvpe(config.SHELL, argv, env)
        finally:
            os._exit(127)

    SHELLS.add(pid)
    _winsize(fd, num("cols", 80), num("rows", 24))
    os.set_blocking(fd, False)
    loop = asyncio.get_running_loop()
    out: asyncio.Queue[bytes] = asyncio.Queue()

    def readable() -> None:
        try:
            data = os.read(fd, 65536)
        except BlockingIOError:
            return
        except OSError:  # EIO: the shell has gone
            data = b""
        out.put_nowait(data)
        if not data:
            loop.remove_reader(fd)

    loop.add_reader(fd, readable)

    async def pump() -> None:
        while (data := await out.get()):
            await ws.send_bytes(data)
        with contextlib.suppress(Exception):
            await ws.close(code=1000)

    task = asyncio.create_task(pump())
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes"):
                _write_all(fd, msg["bytes"])
            elif msg.get("text"):
                with contextlib.suppress(ValueError, TypeError, KeyError):
                    ctl = json.loads(msg["text"])
                    if ctl.get("t") == "r":
                        _winsize(fd, int(ctl["c"]), int(ctl["r"]))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        with contextlib.suppress(Exception):
            loop.remove_reader(fd)
        task.cancel()
        await _reap(pid)
        SHELLS.discard(pid)
        with contextlib.suppress(OSError):
            os.close(fd)
