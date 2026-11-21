"""Where things are.

Two processes share this module:
  akarid (python -m akari)        root in the container, a handful of capabilities:
                                   login, accounts, sessions, the static files, and a
                                   proxy to each person's session agent.
  agent  (python -m akari.agent)  one per signed-in account, running as that Linux
                                   user: terminal, files, apps, preferences.

Everything lives in the one volume, /data. The root filesystem is read-only;
/etc/passwd, /etc/group and /etc/shadow are symlinks into /data/system."""

from __future__ import annotations

import os
import time
from pathlib import Path

VERSION = "0.6.1"
OS_NAME = "Akari OS"
STARTED = time.time()

DATA = Path(os.environ.get("AKARI_DATA", "/data"))
SYSTEM = DATA / "system"          # accounts, passwd, group, shadow (root only)
HOMES = DATA / "homes"            # one home per account, 0700
RUN = Path(os.environ.get("AKARI_RUN", "/tmp/akari"))   # sockets, one dir per uid, 0700
SKEL = Path("/etc/skel")
ETC_SEED = Path("/usr/share/akari/etc")   # the image's own passwd/group/shadow

PORT = int(os.environ.get("AKARI_PORT", "8130"))
HOST = os.environ.get("AKARI_BIND", "0.0.0.0")
HOSTNAME = os.environ.get("AKARI_HOSTNAME") or os.uname().nodename

STATIC = Path(__file__).parent / "static"
VENDOR = {
    "xterm": Path("/usr/share/javascript/xterm"),
    "novnc": Path("/usr/share/novnc"),
    "meslo": Path("/usr/share/fonts/truetype/meslo-nf"),     # p10k's font, for the web terminal
}

# --- inside an agent: whose session this is -------------------------------
HOME = Path(os.environ.get("HOME", "/tmp"))
NAME = os.environ.get("USER", "akari")
FULLNAME = os.environ.get("AKARI_FULLNAME", NAME)
SHELL = os.environ.get("SHELL", "/bin/zsh")
CONFIG = HOME / ".config" / "akari"
CACHE = HOME / ".cache" / "akari"
TRASH = HOME / ".local" / "share" / "Trash" / "files"


def user_run(uid: int) -> Path:
    return RUN / str(uid)


def agent_socket(uid: int) -> Path:
    return user_run(uid) / "agent.sock"


def ensure_user_dirs() -> None:
    """In the agent: the folders a desktop expects, every start (cheap, idempotent)."""
    for d in (CONFIG, CACHE, CACHE / "tmp", TRASH, HOME / "Dokumente", HOME / "Downloads", HOME / "Bilder", HOME / "Schreibtisch"):
        d.mkdir(parents=True, exist_ok=True)
