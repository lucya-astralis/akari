"""The Linux programs that are installed: their .desktop files, as any Linux
desktop reads them (freedesktop Desktop Entry spec). Runs in the session
agent, as the user, so it also sees ~/.local/share/applications.

What counts: Type=Application, not NoDisplay or Hidden, not reserved for
another desktop (OnlyShowIn without Akari, NotShowIn with it), its TryExec
present, and something to run. Handlers without a window of their own
(URL schemes, D-Bus helpers) say NoDisplay or have no Name; they stay out.
Programs that run in a terminal (htop, vim) open in Akari's terminal."""

from __future__ import annotations

import configparser
import os
import re
import shlex
import shutil
from pathlib import Path

from . import config

DIRS = [Path("/usr/share/applications"), Path("/usr/local/share/applications")]
THEMES = ["hicolor", "Adwaita", "breeze", "Papirus", "default"]
SIZES = ["scalable", "256x256", "192x192", "128x128", "96x96", "64x64", "48x48", "32x32"]
FIELD = re.compile(r"%[fFuUdDnNickvm]")
# programs Akari already has a place for, and entries that are not apps
SKIP = {"firefox-esr", "debian-xterm", "debian-uxterm", "python3", "python3.13"}
# the settings of other desktops: they configure KDE or GNOME, not Akari
OTHER_DESKTOPS = {"KDE", "GNOME", "XFCE", "LXQt", "MATE", "Cinnamon", "X-XFCE-SettingsDialog"}
DESKTOP = "Akari"

_cache: tuple[tuple, dict] | None = None


def _dirs() -> list[Path]:
    return DIRS + [config.HOME / ".local" / "share" / "applications"]


def _lang() -> list[str]:
    lang = os.environ.get("LANG", "C").split(".")[0]           # de_DE
    return [lang, lang.split("_")[0]] if lang not in ("C", "POSIX") else []


def _read(path: Path) -> dict | None:
    cp = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",))
    cp.optionxform = str                                        # keys are case-sensitive
    try:
        cp.read(path, encoding="utf-8")
        e = cp["Desktop Entry"]
    except (configparser.Error, KeyError, UnicodeDecodeError, OSError):
        return None
    def get(key):
        for l in _lang():
            if f"{key}[{l}]" in e:
                return e[f"{key}[{l}]"]
        return e.get(key)
    if e.get("Type") != "Application" or e.get("NoDisplay") == "true" or e.get("Hidden") == "true":
        return None
    only = [x for x in e.get("OnlyShowIn", "").split(";") if x]
    if only and DESKTOP not in only:
        return None
    if DESKTOP in e.get("NotShowIn", "").split(";"):
        return None
    if e.get("TryExec") and not shutil.which(os.path.expanduser(e["TryExec"])):
        return None
    try:
        cmd = [a for a in shlex.split(FIELD.sub("", e.get("Exec", ""))) if a]
    except ValueError:
        return None
    name = get("Name")
    if not cmd or not name or not shutil.which(cmd[0]):
        return None
    cats = [c for c in e.get("Categories", "").split(";") if c]
    terminal = e.get("Terminal") == "true"
    foreign_settings = "Settings" in cats and bool(OTHER_DESKTOPS & set(cats))
    return {"title": name, "comment": get("Comment") or get("GenericName") or "", "cmd": cmd,
            "terminal": terminal, "icon": e.get("Icon", ""), "categories": cats,
            "keywords": [k for k in (get("Keywords") or "").split(";") if k],
            # not in the start menu unless asked for: terminal programs (one starts them in a
            # terminal) and the settings of other desktops (they do nothing for Akari)
            "extra": terminal or foreign_settings}


def apps() -> dict[str, dict]:
    """id (the file name without .desktop) → entry. A user's own file wins over the system's."""
    global _cache
    stamp = tuple((str(d), d.stat().st_mtime) for d in _dirs() if d.is_dir())
    if _cache and _cache[0] == stamp:
        return _cache[1]
    out: dict[str, dict] = {}
    for d in _dirs():                                           # later dirs (the user's) override
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.desktop")):
            if f.stem in SKIP:
                continue
            entry = _read(f)
            if entry:
                out[f.stem] = entry
            else:
                out.pop(f.stem, None)                            # a user file can hide a system app
    _cache = (stamp, out)
    return out


def icon(name: str) -> Path | None:
    """The best picture for an Icon= value: an absolute path, or a name in the icon themes."""
    if not name:
        return None
    if name.startswith("/"):
        p = Path(name)
        return p if p.suffix in (".png", ".svg") and p.is_file() else None
    if "/" in name or name.startswith("."):
        return None
    roots = [config.HOME / ".local" / "share" / "icons", Path("/usr/share/icons")]
    for root in roots:
        for theme in THEMES:
            for size in SIZES:
                for ext in (".svg", ".png") if size == "scalable" else (".png", ".svg"):
                    p = root / theme / size / "apps" / f"{name}{ext}"
                    if p.is_file():
                        return p
    for ext in (".png", ".svg"):
        p = Path("/usr/share/pixmaps") / f"{name}{ext}"
        if p.is_file():
            return p
    return None
