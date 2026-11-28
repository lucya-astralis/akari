"""The machine under Akari: a real Debian, so Einstellungen can show and change it.

Read for everyone signed in: name, hardware, disks, network, time, updates.
Changed only by accounts that manage (sudo): the machine's name, time zone and
network time, updates, restart and power off.

akarid runs as root but with few capabilities (akarid.service), so it changes
nothing here by itself: hostnamectl, timedatectl and systemctl ask systemd over
D-Bus, and apt runs as a unit of its own (systemd-run), which also outlives
akarid when an update replaces Akari itself."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import config, console

UNIT = "akari-apt"                      # the unit apt runs in (systemd-run)
APT_STATE = Path(os.environ.get("AKARI_APT_STATE", "/var/lib/akari/apt.json"))
HOSTNAME = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
REAL_FS = {"ext2", "ext3", "ext4", "xfs", "btrfs", "f2fs", "vfat", "exfat", "ntfs", "ntfs3", "zfs"}


def _run(*cmd: str, timeout: float = 10) -> str:
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return r.stdout
    return ""


def _check(*cmd: str, timeout: float = 30) -> None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        raise HostError(f"{cmd[0]}: {e}")
    if r.returncode != 0:
        raise HostError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else f"{cmd[0]} ist fehlgeschlagen.")


class HostError(Exception):
    pass


# ---------- the machine ----------

def _cpu() -> dict:
    model, cores = "", 0
    with contextlib.suppress(OSError):
        for line in open("/proc/cpuinfo", encoding="utf-8"):
            if line.startswith("model name") and not model:
                model = re.sub(r"\s+", " ", line.split(":", 1)[1]).strip()
            if line.startswith("processor"):
                cores += 1
    return {"model": model or os.uname().machine, "cores": cores or os.cpu_count() or 1, "arch": os.uname().machine}


def _virt() -> str | None:
    v = _run("systemd-detect-virt").strip()
    return None if v in ("", "none") else v


def _boot() -> int | None:
    with contextlib.suppress(OSError, ValueError):
        return int(time.time() - float(open("/proc/uptime").read().split()[0]))
    return None


def disks() -> list[dict]:
    """Every real filesystem once (by device), largest first."""
    seen, out = set(), []
    with contextlib.suppress(OSError):
        for line in open("/proc/mounts", encoding="utf-8"):
            dev, mnt, fs = line.split()[:3]
            mnt = mnt.replace("\\040", " ")
            if fs not in REAL_FS or dev in seen:
                continue
            seen.add(dev)
            with contextlib.suppress(OSError):
                u = shutil.disk_usage(mnt)
                out.append({"mount": mnt, "device": dev, "fs": fs, "total": u.total, "used": u.used, "free": u.free})
    return sorted(out, key=lambda d: (d["mount"] != "/", -d["total"]))


def info() -> dict:
    return {
        "hostname": os.uname().nodename,
        "pretty": _run("hostnamectl", "--pretty").strip() or None,
        "cpu": _cpu(),
        "virt": _virt(),
        "boot": _boot(),
        "disks": disks(),
        "akari": config.VERSION,
    }


def set_hostname(name: str) -> str:
    name = name.strip().lower()
    if not HOSTNAME.match(name):
        raise HostError("Ein Gerätename hat 1 bis 63 Zeichen: Kleinbuchstaben, Ziffern und -, nicht am Anfang oder Ende.")
    old = os.uname().nodename
    _check("hostnamectl", "set-hostname", name)
    # Debian names the machine in /etc/hosts too (127.0.1.1), else sudo waits for DNS
    with contextlib.suppress(OSError):
        hosts = Path("/etc/hosts")
        text = hosts.read_text(encoding="utf-8")
        lines = text.splitlines()
        found = False
        for i, l in enumerate(lines):
            if l.startswith("127.0.1.1"):
                lines[i] = f"127.0.1.1\t{name}"
                found = True
        if not found:
            lines.insert(1 if lines else 0, f"127.0.1.1\t{name}")
        if old != name or not found:
            tmp = hosts.with_suffix(".akari")
            tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.chmod(tmp, 0o644)
            os.replace(tmp, hosts)
    return name


def power(action: str) -> None:
    if action not in ("reboot", "poweroff"):
        raise HostError("Nur Neustarten oder Ausschalten.")
    # a moment later, so the answer still reaches the browser
    subprocess.Popen(["systemd-run", "--on-active=2", "--timer-property=AccuracySec=100ms", "systemctl", action],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------- network ----------

def network() -> dict:
    links, routes = [], []
    with contextlib.suppress(ValueError):
        links = json.loads(_run("ip", "-j", "addr") or "[]")
    with contextlib.suppress(ValueError):
        routes = json.loads(_run("ip", "-j", "route", "show", "default") or "[]")
    out = []
    for l in links:
        if l.get("link_type") == "loopback":
            continue
        out.append({
            "name": l.get("ifname"),
            "up": l.get("operstate") == "UP" or (l.get("operstate") == "UNKNOWN" and "UP" in l.get("flags", [])),
            "mac": l.get("address"),
            "addresses": [f"{a['local']}/{a['prefixlen']}" for a in l.get("addr_info", []) if a.get("scope") == "global"],
        })
    dns = []
    with contextlib.suppress(OSError):
        for line in open("/etc/resolv.conf", encoding="utf-8"):
            p = line.split()
            if len(p) >= 2 and p[0] == "nameserver":
                dns.append(p[1])
    ip = console.address()
    return {
        "interfaces": out,
        "gateway": next((r.get("gateway") for r in routes if r.get("gateway")), None),
        "dns": dns,
        "url": f"https://{ip}/" if ip else None,
    }


# ---------- time ----------

def _timedate() -> dict:
    out = {}
    for line in _run("timedatectl", "show").splitlines():
        k, _, v = line.partition("=")
        out[k] = v
    return out


def clock() -> dict:
    t = _timedate()
    return {
        "timezone": t.get("Timezone") or "UTC",
        "ntp": t.get("NTP") == "yes",
        "synced": t.get("NTPSynchronized") == "yes",
        "can_ntp": t.get("CanNTP") == "yes",
        "now": time.time(),
    }


def timezones() -> list[str]:
    return [z for z in _run("timedatectl", "list-timezones").splitlines() if z]


def set_clock(timezone: str | None = None, ntp: bool | None = None) -> None:
    if timezone is not None:
        if timezone not in timezones():
            raise HostError("Diese Zeitzone kennt das System nicht.")
        _check("timedatectl", "set-timezone", timezone)
    if ntp is not None:
        _check("timedatectl", "set-ntp", "true" if ntp else "false")


# ---------- updates ----------
# apt runs in a unit of its own: `check` refreshes the lists, `install` brings
# everything up to date. Its output stays in the journal; what is upgradable
# is asked again afterwards (apt list --upgradable reads the lists only).

ENV = ["--setenv=DEBIAN_FRONTEND=noninteractive", "--setenv=APT_LISTCHANGES_FRONTEND=none"]
JOBS = {
    "check": ["apt-get", "update"],
    "install": ["apt-get", "-y", "-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold",
                "upgrade", "--with-new-pkgs"],
    # Docker from Debian, for the Docker app (docker.py): the engine and compose
    "docker": ["apt-get", "-y", "install", "docker.io", "docker-compose"],
    # automatic updates, where the installer left them out
    "auto": ["apt-get", "-y", "install", "unattended-upgrades"],
}


def _state() -> dict:
    with contextlib.suppress(OSError, ValueError):
        return json.loads(APT_STATE.read_text(encoding="utf-8"))
    return {}


def _save(**kw) -> None:
    s = {**_state(), **kw}
    with contextlib.suppress(OSError):
        APT_STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = APT_STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(s), encoding="utf-8")
        os.replace(tmp, APT_STATE)


def _unit() -> dict:
    out = {}
    for line in _run("systemctl", "show", UNIT, "-p", "ActiveState,Result,ExecMainStatus").splitlines():
        k, _, v = line.partition("=")
        out[k] = v
    return out


def upgradable() -> list[dict]:
    """What apt would bring up to date: name, the version now and the new one."""
    out = []
    for line in _run("apt", "list", "--upgradable", timeout=30).splitlines():
        # name/suite version arch [upgradable from: old]
        m = re.match(r"^([^/\s]+)/\S+\s+(\S+)\s+\S+\s+\[[^:]+:\s*([^\]]+)\]", line)
        if m:
            out.append({"name": m[1], "to": m[2], "from": m[3].strip()})
    return out


def updates() -> dict:
    u, s = _unit(), _state()
    running = u.get("ActiveState") in ("active", "activating", "deactivating")
    job = s.get("job") if running else None
    if not running and s.get("job"):            # it has ended since it was last looked at
        ok = u.get("Result", "success") == "success" and u.get("ExecMainStatus", "0") in ("0", "")
        _save(job=None, last={"job": s["job"], "ok": ok, "at": time.time()},
              **({"checked": time.time()} if s["job"] == "check" and ok else {}))
        s = _state()
    # what apt itself wrote (not systemd about it), in this run only
    since = s.get("started")
    log = _run("journalctl", f"_SYSTEMD_UNIT={UNIT}.service", f"--since=@{int(since)}", "-n", "14", "-o", "cat", "--no-pager").splitlines() if since else []
    packages = [] if running else upgradable()
    if not running and s.get("count") != len(packages):
        _save(count=len(packages))             # for the welcome at the console (motd.py), which asks apt nothing
    return {
        "running": job,
        "checked": s.get("checked"),
        "last": s.get("last"),
        "packages": packages,
        "log": log[-14:],
    }


def start(job: str) -> None:
    if job not in JOBS:
        raise HostError("Unbekannte Aufgabe.")
    if _unit().get("ActiveState") in ("active", "activating"):
        raise HostError("apt arbeitet schon.")
    _run("systemctl", "reset-failed", UNIT)
    # no --collect: a failed run stays (Result=exit-code) until the next one, so it can be told
    _check("systemd-run", f"--unit={UNIT}", "--quiet", "--service-type=exec",
           "--property=Nice=10", *ENV, *JOBS[job])
    _save(job=job, started=time.time() - 1)


# ---------- automatic updates ----------
# unattended-upgrades does the work, every day; Akari only says whether. Its own
# file (Debian's 20auto-upgrades stays as the installer wrote it) comes last, so
# it wins. What it installs (Debian's security and updates, Akari's archive) is
# set by the package (/etc/apt/apt.conf.d/52akari-unattended-upgrades).

AUTO = Path(os.environ.get("AKARI_AUTO_UPGRADES", "/etc/apt/apt.conf.d/99akari-auto-upgrades"))


def _periodic(key: str) -> str | None:
    m = re.search(rf'APT::Periodic::{key} "([^"]*)"', _run("apt-config", "dump", f"APT::Periodic::{key}"))
    return m.group(1) if m else None


def auto_updates() -> dict:
    installed = bool(shutil.which("unattended-upgrade"))
    return {"installed": installed, "on": installed and _periodic("Unattended-Upgrade") not in (None, "0", "")}


def set_auto_updates(on: bool) -> dict:
    if on and not shutil.which("unattended-upgrade"):
        raise HostError("unattended-upgrades fehlt. Erst installieren.")
    v = "1" if on else "0"
    AUTO.parent.mkdir(parents=True, exist_ok=True)
    tmp = AUTO.with_suffix(".tmp")
    tmp.write_text("// Akari OS: Einstellungen → Updates → Automatisch (host.py)\n"
                   f'APT::Periodic::Update-Package-Lists "{v}";\nAPT::Periodic::Unattended-Upgrade "{v}";\n', encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, AUTO)
    return auto_updates()


# ---------- the keyboard ----------
# The system's layout, /etc/default/keyboard, as Debian's installer writes it:
# the console on the machine (kmscon reads it when it starts) and new X
# sessions. Written here, not through localectl: Debian's systemd-localed keeps
# it in /etc/vconsole.conf and makes a wrong console keymap of it. Model and
# options stay as they are. The desktop in the browser types with the
# browser's own keyboard.

KEYBOARD = Path(os.environ.get("AKARI_KEYBOARD", "/etc/default/keyboard"))

LAYOUTS = [("de", "Deutsch"), ("ch", "Deutsch (Schweiz)"), ("at", "Deutsch (Österreich)"), ("us", "Englisch (USA)"),
           ("gb", "Englisch (UK)"), ("fr", "Französisch"), ("es", "Spanisch"), ("it", "Italienisch"), ("nl", "Niederländisch"),
           ("pl", "Polnisch"), ("se", "Schwedisch"), ("no", "Norwegisch"), ("dk", "Dänisch"), ("fi", "Finnisch"),
           ("pt", "Portugiesisch"), ("cz", "Tschechisch"), ("jp", "Japanisch"), ("ru", "Russisch")]
_LAYOUT = re.compile(r"^[a-z]{2,3}$")


def _keyboard_file() -> str:
    with contextlib.suppress(OSError):
        return KEYBOARD.read_text(encoding="utf-8")
    return ""


def keyboard() -> dict:
    m = re.search(r'^XKBLAYOUT="?([^"\n]*)"?', _keyboard_file(), re.M)
    return {"layout": m.group(1).split(",")[0] if m and m.group(1) else None, "layouts": [{"id": i, "name": n} for i, n in LAYOUTS]}


def set_keyboard(layout: str) -> dict:
    if not _LAYOUT.match(layout or "") or layout not in dict(LAYOUTS):
        raise HostError("Unbekanntes Tastaturlayout.")
    text = _keyboard_file() or 'XKBMODEL="pc105"\nXKBLAYOUT=""\nXKBVARIANT=""\nXKBOPTIONS=""\nBACKSPACE="guess"\n'
    for key, value in (("XKBLAYOUT", layout), ("XKBVARIANT", "")):
        line = f'{key}="{value}"'
        text = re.sub(rf"^{key}=.*$", line, text, flags=re.M) if re.search(rf"^{key}=", text, re.M) else text.rstrip("\n") + f"\n{line}\n"
    tmp = KEYBOARD.with_suffix(".akari.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, KEYBOARD)
    console.redraw()            # the console takes it on its next start, which happens now if nobody is signed in there
    return keyboard()
