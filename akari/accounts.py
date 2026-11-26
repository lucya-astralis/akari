"""Accounts: the system's own users.

An account is a Linux user like any other: in /etc/passwd with a uid from
UID_MIN to UID_MAX (/etc/login.defs), a login shell, and a password in
/etc/shadow. Akari makes and changes them with useradd, usermod, chpasswd,
gpasswd and userdel, and checks passwords with PAM (service "akari"), so an
account made in the installer, with adduser or here is the same thing.
Accounts that manage are the members of the group sudo.

What Linux has no place for lives in /var/lib/akari/accounts.json (root,
0600), by name: when the account came to Akari, its picture, the Lucent
person it is linked to, whether it may use its password over ssh.

The login screen shows only accounts that can sign in with a password: a
user whose password is locked ('!', '*', as for a key-only admin) can't."""

from __future__ import annotations

import grp
import hmac
import json
import os
import pwd
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import config

FILE = config.SYSTEM / "accounts.json"
NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}\Z")     # \Z, not $: "ada\n" is no name
ADMIN_GROUP = "sudo"
PAM_SERVICE = "akari"
SHELL = "/bin/zsh"
PW_MIN = 8
NO_LOGIN = ("/usr/sbin/nologin", "/sbin/nologin", "/bin/false", "/usr/bin/false")

_lock = threading.RLock()


class AccountError(ValueError):
    pass


def _login_defs() -> tuple[int, int]:
    lo, hi = 1000, 59999
    try:
        for line in Path("/etc/login.defs").read_text().splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == "UID_MIN":
                lo = int(parts[1])
            elif len(parts) == 2 and parts[0] == "UID_MAX":
                hi = int(parts[1])
    except (OSError, ValueError):
        pass
    return lo, hi


UID_MIN, UID_MAX = _login_defs()


@dataclass
class Account:
    name: str
    fullname: str
    uid: int
    admin: bool
    created: int
    home: Path
    ssh_password: bool = False     # may this account sign in over ssh with its password?
    avatar: int = 0                # when the picture last changed (0: none, the initial is shown)
    lucent_sub: str | None = None  # the Lucent person this account is linked to ("<issuer>#<sub>")
    lucent_email: str | None = None

    def public(self) -> dict:
        return {"name": self.name, "fullname": self.fullname, "admin": self.admin,
                "initial": (self.fullname.strip() or self.name)[0].upper(),
                "avatar": f"/api/avatars/{self.name}?v={self.avatar}" if self.avatar else None}


# ---------- what Akari keeps on top ----------

EXTRAS = ("created", "ssh_password", "avatar", "lucent_sub", "lucent_email")


def _load() -> dict[str, dict]:
    try:
        raw = json.loads(FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save(extras: dict[str, dict]) -> None:
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(extras, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, FILE)


def _set_extra(name: str, **values) -> None:
    with _lock:
        extras = _load()
        extras.setdefault(name, {}).update(values)
        _save(extras)


# ---------- reading the system ----------

def _locked() -> set[str]:
    """Users whose shadow entry holds no usable password. Unreadable shadow (tests, no root): none."""
    try:
        lines = Path("/etc/shadow").read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    out = set()
    for line in lines:
        f = line.split(":")
        if len(f) > 1 and (not f[1] or f[1][0] in "!*"):
            out.add(f[0])
    return out


def _admins() -> set[str]:
    try:
        g = grp.getgrnam(ADMIN_GROUP)
    except KeyError:
        return set()
    return set(g.gr_mem) | {p.pw_name for p in pwd.getpwall() if p.pw_gid == g.gr_gid}


def _humans() -> list[pwd.struct_passwd]:
    return [p for p in pwd.getpwall()
            if UID_MIN <= p.pw_uid <= UID_MAX and p.pw_shell not in NO_LOGIN and NAME_RE.match(p.pw_name)]


def _account(p: pwd.struct_passwd, admins: set[str], extras: dict[str, dict]) -> Account:
    x = extras.get(p.pw_name, {})
    home = Path(p.pw_dir)
    created = x.get("created")
    if not created:
        try:
            created = int(home.stat().st_ctime)
        except OSError:
            created = 0
    return Account(name=p.pw_name, fullname=p.pw_gecos.split(",", 1)[0].strip() or p.pw_name, uid=p.pw_uid,
                   admin=p.pw_name in admins, created=created, home=home,
                   **{k: x[k] for k in EXTRAS if k in x and k != "created"})


def all() -> list[Account]:  # noqa: A001 - the module reads as accounts.all()
    """The accounts that can sign in, by uid."""
    with _lock:
        admins, extras, locked = _admins(), _load(), _locked()
        return sorted((_account(p, admins, extras) for p in _humans() if p.pw_name not in locked), key=lambda a: a.uid)


def get(name: str) -> Account | None:
    return next((a for a in all() if a.name == name), None)


def by_uid(uid: int) -> Account | None:
    return next((a for a in all() if a.uid == uid), None)


def needs_setup() -> bool:
    return not all()


def init() -> None:
    """At start: Akari's folder, root only."""
    config.SYSTEM.mkdir(parents=True, exist_ok=True)
    os.chmod(config.SYSTEM, 0o700)
    if FILE.exists():
        os.chmod(FILE, 0o600)


# ---------- passwords ----------

def verify(name: str, password: str) -> bool:
    """The password, checked by PAM as at any other login."""
    import pam   # python3-pampy; only akarid (root) needs it
    return bool(pam.pam().authenticate(name or "", password or "", service=PAM_SERVICE))


def authenticate(name: str, password: str) -> Account | None:
    """An account and its password. PAM is asked about every name, so a wrong
    name and a wrong password take the same time; only accounts get in (never root)."""
    name = (name or "").strip().lower()
    ok = verify(name, password) if NAME_RE.match(name) else False
    acct = get(name) if ok else None
    return acct


# ---------- changes ----------

def _run(*cmd: str, stdin: str | None = None) -> None:
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True)
    if r.returncode != 0:
        raise AccountError(f"{cmd[0]}: {(r.stderr or r.stdout).strip() or f'Fehler {r.returncode}'}")


def _clean_fullname(s: str, fallback: str) -> str:
    s = re.sub(r"[:,\n\r\t\0]", " ", s or "").strip()[:64]
    return s or fallback


def _check_pw(password: str | None) -> None:
    if len(password or "") < PW_MIN:
        raise AccountError(f"Das Passwort braucht mindestens {PW_MIN} Zeichen.")
    if "\n" in password or "\r" in password or "\0" in password:   # chpasswd reads one line per user
        raise AccountError("Das Passwort darf keinen Zeilenumbruch enthalten.")


def _set_password(name: str, password: str) -> None:
    _run("chpasswd", stdin=f"{name}:{password}\n")


def _exists(name: str) -> bool:
    for lookup in (pwd.getpwnam, grp.getgrnam):
        try:
            lookup(name)
            return True
        except KeyError:
            pass
    return False


def create(name: str, fullname: str, password: str, admin: bool = False) -> Account:
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        raise AccountError("Der Name: 2 bis 32 Zeichen, Kleinbuchstaben, Ziffern, - und _, vorne ein Buchstabe.")
    _check_pw(password)
    with _lock:
        if _exists(name):
            raise AccountError("Diesen Namen gibt es schon.")
        first = not all()
        _run("useradd", "--create-home", "--user-group", "--shell", SHELL,
             "--comment", _clean_fullname(fullname, name), *(["--groups", ADMIN_GROUP] if admin or first else []), name)
        try:
            _set_password(name, password)
        except AccountError:
            _run("userdel", "--remove", name)
            raise
        home = Path(pwd.getpwnam(name).pw_dir)
        os.chmod(home, 0o700)
        extras = _load()
        extras[name] = {"created": int(time.time())}      # a name used before starts afresh
        _save(extras)
        acct = get(name)
        assert acct
        return acct


def update(name: str, *, fullname: str | None = None, password: str | None = None, admin: bool | None = None) -> Account:
    with _lock:
        acct = get(name)
        if not acct:
            raise AccountError("Dieses Konto gibt es nicht.")
        if fullname is not None:
            _run("usermod", "--comment", _clean_fullname(fullname, acct.name), name)
        if password is not None:
            _check_pw(password)
            _set_password(name, password)
        if admin is not None and admin != acct.admin:
            if not admin and sum(a.admin for a in all()) == 1:
                raise AccountError("Mindestens ein Konto muss verwalten dürfen.")
            _run("gpasswd", "--add" if admin else "--delete", name, ADMIN_GROUP)
        acct = get(name)
        assert acct
        return acct


def set_ssh_password(name: str, allow: bool) -> Account:
    """Allow or forbid the account's password over ssh (sshd_config.d/akari.conf follows, see ssh.py)."""
    if not get(name):
        raise AccountError("Dieses Konto gibt es nicht.")
    _set_extra(name, ssh_password=bool(allow))
    acct = get(name)
    assert acct
    return acct


def set_avatar(name: str, version: int) -> Account:
    if not get(name):
        raise AccountError("Dieses Konto gibt es nicht.")
    _set_extra(name, avatar=version)
    acct = get(name)
    assert acct
    return acct


def set_lucent(name: str, sub: str | None, email: str | None = None) -> Account:
    """Link an account to a Lucent person (sign-in with Lucent), or unlink it (sub None).
    One Lucent person is linked to one account at most."""
    with _lock:
        if not get(name):
            raise AccountError("Dieses Konto gibt es nicht.")
        if sub:
            other = next((a for a in all() if a.lucent_sub == sub and a.name != name), None)
            if other:
                raise AccountError(f"Diese Lucent-Person ist schon mit {other.name} verknüpft.")
        _set_extra(name, lucent_sub=sub or None, lucent_email=email if sub else None)
        acct = get(name)
        assert acct
        return acct


def by_lucent(sub: str) -> Account | None:
    return next((a for a in all() if a.lucent_sub and hmac.compare_digest(a.lucent_sub, sub)), None)


def ssh_password_users() -> list[str]:
    return [a.name for a in all() if a.ssh_password]


def delete(name: str) -> None:
    """The user, its group, its home. Its processes end first (ssh, its user manager)."""
    with _lock:
        acct = get(name)
        if not acct:
            raise AccountError("Dieses Konto gibt es nicht.")
        if acct.admin and sum(a.admin for a in all()) == 1:
            raise AccountError("Das letzte Konto, das verwalten darf, bleibt.")
        subprocess.run(["loginctl", "terminate-user", name], capture_output=True)
        subprocess.run(["pkill", "-KILL", "-u", name], capture_output=True)
        for _ in range(20):
            if subprocess.run(["pgrep", "-u", name], capture_output=True).returncode != 0:
                break
            time.sleep(0.25)
        _run("userdel", "--remove", name)
        extras = _load()
        extras.pop(name, None)
        _save(extras)
