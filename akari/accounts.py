"""Accounts, and the Linux users behind them.

The truth is /data/system/accounts.json (root, 0600): name, full name, uid,
admin, password hash. From it akarid writes /data/system/{passwd,group,shadow},
which /etc/passwd, /etc/group and /etc/shadow point to: the image's own system
users first, then one line per account. Every account is a real Linux user
with its own uid and a home of its own (0700).

Passwords are checked by Akari (scrypt), not by PAM: the shadow entry is
locked ('!'), and su/sudo cannot work anyway under no-new-privileges."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config

FILE = config.SYSTEM / "accounts.json"
NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,31}$")
UID_MIN, UID_MAX = 1000, 59999
PW_MIN = 8
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}

_lock = threading.RLock()


class AccountError(ValueError):
    pass


@dataclass
class Account:
    name: str
    fullname: str
    uid: int
    admin: bool
    pw: str
    created: int
    ssh_pw: str | None = None      # crypt hash of the password for /etc/shadow (sudo checks it, sshd too)
    ssh_password: bool = False     # may this account sign in over ssh with that password?
    avatar: int = 0                # when the picture last changed (0: none, the initial is shown)
    lucent_sub: str | None = None  # the Lucent person this account is linked to ("<issuer>#<sub>")
    lucent_email: str | None = None

    @property
    def home(self) -> Path:
        return config.HOMES / self.name

    def public(self) -> dict:
        return {"name": self.name, "fullname": self.fullname, "admin": self.admin,
                "initial": (self.fullname.strip() or self.name)[0].upper(),
                "avatar": f"/api/avatars/{self.name}?v={self.avatar}" if self.avatar else None}


# ---------- passwords ----------

def hash_pw(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${salt.hex()}${dk.hex()}"


def check_pw(password: str, stored: str) -> bool:
    try:
        _alg, n, r, p, salt, want = stored.split("$")
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), dklen=32, n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), want)


def crypt_pw(password: str) -> str:
    """SHA-512 crypt for /etc/shadow, which sshd checks itself (no PAM here).
    Python 3.13 has no crypt module; openssl reads the password from stdin."""
    import subprocess
    out = subprocess.run(["openssl", "passwd", "-6", "-stdin"], input=password.encode(), capture_output=True, check=True)
    return out.stdout.decode().strip()


# a hash to compare against when the name does not exist, so a wrong name and
# a wrong password take the same time
_DUMMY = hash_pw(secrets.token_urlsafe(12))


# ---------- the store ----------

def _load() -> dict[str, Account]:
    try:
        raw = json.loads(FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    out = {}
    for a in raw:
        if a.get("ssh_pw") and "ssh_password" not in a:
            a["ssh_password"] = True      # 0.3: a hash meant "ssh passwords allowed"
        out[a["name"]] = Account(**a)
    return out


def _save(accts: dict[str, Account]) -> None:
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps([asdict(a) for a in accts.values()], ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, FILE)


def all() -> list[Account]:  # noqa: A001 - the module reads as accounts.all()
    with _lock:
        return sorted(_load().values(), key=lambda a: a.uid)


def get(name: str) -> Account | None:
    with _lock:
        return _load().get(name)


def by_uid(uid: int) -> Account | None:
    return next((a for a in all() if a.uid == uid), None)


def needs_setup() -> bool:
    return not all()


# ---------- /etc/passwd and friends ----------

def _seed(name: str) -> list[str]:
    try:
        return [l for l in (config.ETC_SEED / name).read_text().splitlines() if l.strip()]
    except FileNotFoundError:
        return []


def _system_names() -> set[str]:
    return {l.split(":", 1)[0] for l in _seed("passwd")} | {l.split(":", 1)[0] for l in _seed("group")}


def _write(name: str, lines: list[str], mode: int, gid: int = 0) -> None:
    path = config.SYSTEM / name
    tmp = path.with_name(f".{name}.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(tmp, mode)
    os.chown(tmp, 0, gid)
    os.replace(tmp, path)


def sync() -> None:
    """Write passwd/group/shadow from the accounts. Called at start and after every change."""
    accts = all()
    days = int(time.time() // 86400)
    shadow_gid = next((int(l.split(":")[2]) for l in _seed("group") if l.startswith("shadow:")), 0)
    _write("passwd", _seed("passwd") + [
        f"{a.name}:x:{a.uid}:{a.uid}:{a.fullname},,,:{a.home}:/bin/zsh" for a in accts], 0o644)
    admins = ",".join(a.name for a in accts if a.admin)
    group = [f"{l}{admins}" if l.startswith("akari-admin:") and l.endswith(":") else l for l in _seed("group")]
    _write("group", group + [f"{a.name}:x:{a.uid}:" for a in accts], 0o644)
    # the crypt hash (for sudo; sshd only takes it from accounts that allow it, see ssh.py),
    # '*' until the account has signed in once since 0.4: not locked, so ssh keys still work
    _write("shadow", _seed("shadow") + [f"{a.name}:{a.ssh_pw or '*'}:{days}:0:99999:7:::" for a in accts], 0o640, shadow_gid)
    _write("gshadow", _seed("gshadow") + [f"{a.name}:!::" for a in accts], 0o640, shadow_gid)


def init() -> None:
    """At start: the system folders with the right modes, and the files in sync."""
    config.SYSTEM.mkdir(parents=True, exist_ok=True)
    os.chmod(config.SYSTEM, 0o711)          # users must read passwd, never list or read the rest
    config.HOMES.mkdir(parents=True, exist_ok=True)
    os.chmod(config.HOMES, 0o711)
    config.RUN.mkdir(parents=True, exist_ok=True)
    os.chmod(config.RUN, 0o711)
    if FILE.exists():
        os.chmod(FILE, 0o600)
    adopt_etc()
    sync()


ETC = Path("/etc")


def adopt_etc() -> bool:
    """Put /etc/passwd and friends back into Akari's hands after dpkg.

    A package that makes a system user (polkitd, messagebus …) has useradd
    write /etc/passwd, and that replaces the link into /data/system with a
    plain file: accounts made afterwards are unknown to Linux. Here the new
    system entries go into the image's seed, the links come back, and the
    files are written again. Called at start, after software is put back,
    and by the apt hook after every dpkg run."""
    akari = {a.name for a in all()}
    changed = False
    for name in ("passwd", "group", "shadow", "gshadow"):
        path = ETC / name
        if path.is_symlink() or not path.exists():
            continue
        seed_file = config.ETC_SEED / name
        seed = _seed(name)
        known = {l.split(":", 1)[0] for l in seed}
        extra = [l for l in path.read_text(encoding="utf-8").splitlines()
                 if l.strip() and l.split(":", 1)[0] not in known and l.split(":", 1)[0] not in akari]
        if extra and seed_file.exists():
            st = seed_file.stat()
            tmp = seed_file.with_name(f".{name}.tmp")
            tmp.write_text("\n".join(seed + extra) + "\n", encoding="utf-8")
            os.chmod(tmp, st.st_mode & 0o777)
            os.chown(tmp, st.st_uid, st.st_gid)
            os.replace(tmp, seed_file)
        link = path.with_name(f".{name}.akari-link")
        with contextlib.suppress(FileNotFoundError):
            link.unlink()
        os.symlink(config.SYSTEM / name, link)
        os.replace(link, path)
        changed = True
    if changed:
        sync()
    return changed


# ---------- changes ----------

def _clean_fullname(s: str, fallback: str) -> str:
    s = re.sub(r"[:,\n\r\t\0]", " ", s or "").strip()[:64]
    return s or fallback


def _chown_tree(root: Path, uid: int) -> None:
    os.chown(root, uid, uid)
    for d, dirs, files in os.walk(root):
        for n in dirs + files:
            os.chown(os.path.join(d, n), uid, uid, follow_symlinks=False)


def create(name: str, fullname: str, password: str, admin: bool = False) -> Account:
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        raise AccountError("Der Name: 2 bis 32 Zeichen, Kleinbuchstaben, Ziffern, - und _, vorne ein Buchstabe.")
    if len(password or "") < PW_MIN:
        raise AccountError(f"Das Passwort braucht mindestens {PW_MIN} Zeichen.")
    with _lock:
        accts = _load()
        if name in accts or name in _system_names():
            raise AccountError("Diesen Namen gibt es schon.")
        used = {a.uid for a in accts.values()}
        uid = next(u for u in range(UID_MIN, UID_MAX) if u not in used)
        acct = Account(name=name, fullname=_clean_fullname(fullname, name), uid=uid,
                       admin=admin or not accts, pw=hash_pw(password), created=int(time.time()),
                       ssh_pw=crypt_pw(password))
        home = acct.home
        if home.exists():
            shutil.rmtree(home)
        shutil.copytree(config.SKEL, home, symlinks=True) if config.SKEL.is_dir() else home.mkdir()
        _chown_tree(home, uid)
        os.chmod(home, 0o700)
        accts[name] = acct
        _save(accts)
        sync()
        return acct


def update(name: str, *, fullname: str | None = None, password: str | None = None, admin: bool | None = None) -> Account:
    with _lock:
        accts = _load()
        acct = accts.get(name)
        if not acct:
            raise AccountError("Dieses Konto gibt es nicht.")
        if fullname is not None:
            acct.fullname = _clean_fullname(fullname, acct.name)
        if password is not None:
            if len(password) < PW_MIN:
                raise AccountError(f"Das Passwort braucht mindestens {PW_MIN} Zeichen.")
            acct.pw = hash_pw(password)
            acct.ssh_pw = crypt_pw(password)      # shadow follows the account's password
        if admin is not None and admin != acct.admin:
            if not admin and sum(a.admin for a in accts.values()) == 1:
                raise AccountError("Mindestens ein Konto muss verwalten dürfen.")
            acct.admin = admin
        _save(accts)
        sync()
        return acct


def set_ssh_password(name: str, allow: bool, password: str | None = None) -> Account:
    """Allow or forbid passwords over ssh. Allowing renews the shadow hash from the password."""
    with _lock:
        accts = _load()
        acct = accts.get(name)
        if not acct:
            raise AccountError("Dieses Konto gibt es nicht.")
        if password:
            acct.ssh_pw = crypt_pw(password)
        acct.ssh_password = allow
        _save(accts)
        sync()
        return acct


def set_avatar(name: str, version: int) -> Account:
    with _lock:
        accts = _load()
        acct = accts.get(name)
        if not acct:
            raise AccountError("Dieses Konto gibt es nicht.")
        acct.avatar = version
        _save(accts)
        return acct


def set_lucent(name: str, sub: str | None, email: str | None = None) -> Account:
    """Link an account to a Lucent person (sign-in with Lucent), or unlink it (sub None).
    One Lucent person is linked to one account at most."""
    with _lock:
        accts = _load()
        acct = accts.get(name)
        if not acct:
            raise AccountError("Dieses Konto gibt es nicht.")
        if sub:
            other = next((a for a in accts.values() if a.lucent_sub == sub and a.name != name), None)
            if other:
                raise AccountError(f"Diese Lucent-Person ist schon mit {other.name} verknüpft.")
        acct.lucent_sub, acct.lucent_email = (sub, email) if sub else (None, None)
        _save(accts)
        return acct


def by_lucent(sub: str) -> Account | None:
    return next((a for a in all() if a.lucent_sub and hmac.compare_digest(a.lucent_sub, sub)), None)


def ensure_shadow(name: str, password: str) -> None:
    """After a good sign-in: give an account from before 0.4 its shadow hash (sudo needs it)."""
    with _lock:
        accts = _load()
        acct = accts.get(name)
        if acct and not acct.ssh_pw:
            acct.ssh_pw = crypt_pw(password)
            _save(accts)
            sync()


def ssh_password_users() -> list[str]:
    return [a.name for a in all() if a.ssh_password and a.ssh_pw]


def delete(name: str) -> None:
    with _lock:
        accts = _load()
        acct = accts.get(name)
        if not acct:
            raise AccountError("Dieses Konto gibt es nicht.")
        if acct.admin and sum(a.admin for a in accts.values()) == 1:
            raise AccountError("Das letzte Konto, das verwalten darf, bleibt.")
        del accts[name]
        _save(accts)
        sync()
        shutil.rmtree(acct.home, ignore_errors=True)


def authenticate(name: str, password: str) -> Account | None:
    acct = get((name or "").strip().lower())
    ok = check_pw(password or "", acct.pw if acct else _DUMMY)
    return acct if acct and ok else None
