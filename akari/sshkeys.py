"""The account's own ssh keys: ~/.ssh/authorized_keys. Runs in the session
agent, so the file belongs to the user (sshd's StrictModes wants ~/.ssh 0700
and the file 0600, which is what the agent's umask gives)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import config

router = APIRouter(prefix="/api/ssh/keys")
TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
         "sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com")


def _file():
    return config.HOME / ".ssh" / "authorized_keys"


def _parse(line: str) -> dict | None:
    """One key line: type, base64 blob, comment. Options in front are kept but not shown."""
    parts = line.strip().split()
    for i, p in enumerate(parts):
        if p in TYPES and i + 1 < len(parts):
            try:
                blob = base64.b64decode(parts[i + 1], validate=True)
            except (binascii.Error, ValueError):
                return None
            fp = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
            return {"type": p, "fingerprint": f"SHA256:{fp}", "comment": " ".join(parts[i + 2:]), "line": line.strip()}
    return None


def _read() -> list[str]:
    try:
        return [l for l in _file().read_text(encoding="utf-8").splitlines() if l.strip() and not l.lstrip().startswith("#")]
    except FileNotFoundError:
        return []


def _write(lines: list[str]) -> None:
    d = _file().parent
    d.mkdir(mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)
    tmp = _file().with_suffix(".tmp")
    tmp.write_text("".join(l + "\n" for l in lines), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, _file())


@router.get("")
def listing() -> dict:
    return {"keys": [{k: v for k, v in key.items() if k != "line"} for l in _read() if (key := _parse(l))]}


class KeyIn(BaseModel):
    key: str


@router.post("")
def add(body: KeyIn) -> dict:
    line = re.sub(r"\s+", " ", body.key.strip())
    if "\n" in body.key.strip() or len(line) > 16384:
        raise HTTPException(400, "Bitte genau einen Schlüssel, eine Zeile.")
    key = _parse(line)
    if not key or not line.startswith(key["type"]):
        raise HTTPException(400, "Das ist kein öffentlicher SSH-Schlüssel (ssh-ed25519 …, ssh-rsa …, ecdsa-sha2-… ).")
    lines = _read()
    if any((k := _parse(l)) and k["fingerprint"] == key["fingerprint"] for l in lines):
        raise HTTPException(409, "Diesen Schlüssel gibt es hier schon.")
    _write(lines + [line])
    return {k: v for k, v in key.items() if k != "line"}


@router.delete("/{fingerprint:path}")
def remove(fingerprint: str) -> dict:
    lines = _read()
    keep = [l for l in lines if not ((k := _parse(l)) and k["fingerprint"] == fingerprint)]
    if len(keep) == len(lines):
        raise HTTPException(404, "Diesen Schlüssel gibt es hier nicht.")
    _write(keep)
    return {"ok": True}
