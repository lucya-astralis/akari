"""Where things are.

Two processes share this module:
  akarid (python -m akari)        root, a system service (akarid.service): login,
                                   accounts, sessions, the static files, and a proxy
                                   to each person's session agent. Listens on
                                   127.0.0.1; Caddy in front of it speaks HTTPS.
  agent  (python -m akari.agent)  one per signed-in account, as that Linux user,
                                   in its own unit (akari-session@<name>.service):
                                   terminal, files, apps, preferences.

Accounts are the system's own users (/etc/passwd, PAM). What Akari keeps
about them on top lives in /var/lib/akari, root only."""

from __future__ import annotations

import os
import pwd
import time
from pathlib import Path

VERSION = "0.12.0"
OS_NAME = "Akari OS"
STARTED = time.time()

SYSTEM = Path(os.environ.get("AKARI_STATE", "/var/lib/akari"))   # extras for accounts, avatars, Lucent (root only)
RUN = Path(os.environ.get("AKARI_RUN", "/run/user"))   # each user's runtime dir (logind), the agent's socket in it

PORT = int(os.environ.get("AKARI_PORT", "8130"))
HOST = os.environ.get("AKARI_BIND", "127.0.0.1")
HOSTNAME = os.environ.get("AKARI_HOSTNAME") or os.uname().nodename

STATIC = Path(__file__).parent / "static"
VENDOR = {
    "xterm": Path("/usr/share/javascript/xterm"),
    "novnc": Path("/usr/share/novnc"),
    "meslo": Path("/usr/share/fonts/truetype/meslo-nf"),     # p10k's font, for the web terminal
}

# --- inside an agent: whose session this is -------------------------------
def _gecos(name: str) -> str:
    try:
        return pwd.getpwnam(name).pw_gecos.split(",", 1)[0].strip() or name
    except KeyError:
        return name


HOME = Path(os.environ.get("HOME", "/tmp"))
NAME = os.environ.get("USER", "akari")
FULLNAME = os.environ.get("AKARI_FULLNAME") or _gecos(NAME)
SHELL = os.environ.get("SHELL", "/bin/zsh")
CONFIG = HOME / ".config" / "akari"
CACHE = HOME / ".cache" / "akari"
TRASH = HOME / ".local" / "share" / "Trash" / "files"


def user_run(uid: int) -> Path:
    """Akari's folder in the user's runtime dir (/run/user/<uid>/akari, 0700)."""
    return RUN / str(uid) / "akari"


def agent_socket(uid: int) -> Path:
    return user_run(uid) / "agent.sock"


def ensure_user_dirs() -> None:
    """In the agent: the folders a desktop expects, every start (cheap, idempotent)."""
    for d in (CONFIG, CACHE, CACHE / "tmp", TRASH, HOME / "Dokumente", HOME / "Downloads", HOME / "Bilder", HOME / "Musik", HOME / "Schreibtisch"):
        d.mkdir(parents=True, exist_ok=True)
