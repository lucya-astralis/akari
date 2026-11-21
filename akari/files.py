"""Files: the home folder and nothing outside it.

Paths from the browser are relative to HOME. A path that would leave HOME
(through "..", an absolute path or a symlink pointing out) is refused.
Deleting moves to the trash (~/.local/share/Trash/files), as a desktop does.

A file is never served inline: an HTML file in someone's home, opened on
this origin, would run with their session. Downloads are attachments with
nosniff; the editor reads text through /api/fs/text as JSON."""

from __future__ import annotations

import mimetypes
import os
import shutil
import stat
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from starlette.datastructures import UploadFile   # what request.form() returns, not fastapi.UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config

router = APIRouter(prefix="/api/fs")
TEXT_MAX = 2 * 1024 * 1024
UPLOAD_MAX = 512 * 1024 * 1024


def _home() -> Path:
    return config.HOME.resolve()


def _rel(p: Path) -> str:
    r = p.relative_to(_home()).as_posix()
    return "" if r == "." else r


def _inside(p: Path) -> bool:
    h = _home()
    return p == h or h in p.parents


def place(rel: str) -> Path:
    """The path itself (a symlink stays a symlink), checked to sit in HOME."""
    p = Path(os.path.normpath(_home() / rel.lstrip("/")))
    if not _inside(p) or not _inside(p.parent.resolve() if p != _home() else p):
        raise HTTPException(403, "Außerhalb des Home-Verzeichnisses.")
    return p


def target(rel: str) -> Path:
    """Where the path leads, following links; must still be in HOME."""
    p = place(rel).resolve()
    if not _inside(p):
        raise HTTPException(403, "Der Link zeigt aus dem Home-Verzeichnis hinaus.")
    return p


def _name(name: str) -> str:
    name = name.strip()
    if not name or name in (".", "..") or "/" in name or "\0" in name or len(name) > 255:
        raise HTTPException(400, "Dieser Name geht nicht.")
    return name


def _free(p: Path) -> Path:
    """'Bericht.pdf' taken → 'Bericht (2).pdf'."""
    if not p.exists() and not p.is_symlink():
        return p
    stem, suf = (p.name, "") if p.is_dir() else (p.stem, p.suffix)
    n = 2
    while True:
        q = p.with_name(f"{stem} ({n}){suf}")
        if not q.exists() and not q.is_symlink():
            return q
        n += 1


def _kind(p: Path, st: os.stat_result) -> str:
    if stat.S_ISDIR(st.st_mode):
        return "dir"
    mime = mimetypes.guess_type(p.name)[0] or ""
    for prefix, kind in (("image/", "image"), ("text/", "text"), ("audio/", "audio"), ("video/", "video")):
        if mime.startswith(prefix):
            return kind
    if mime in ("application/json", "application/xml", "application/javascript", "application/x-sh") or p.suffix in (".md", ".py", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".log", ".sh", ".css", ".js", ".ts"):
        return "text"
    if mime == "application/pdf":
        return "pdf"
    if mime in ("application/zip", "application/gzip", "application/x-tar", "application/x-7z-compressed"):
        return "archive"
    return "file"


@router.get("")
def listing(path: str = "") -> dict:
    d = target(path)
    if not d.is_dir():
        raise HTTPException(404, "Kein Ordner.")
    entries = []
    with os.scandir(d) as it:
        for e in it:
            try:
                st = e.stat(follow_symlinks=True)
            except OSError:
                continue
            p = Path(e.path)
            entries.append({
                "name": e.name, "kind": _kind(p, st), "dir": stat.S_ISDIR(st.st_mode),
                "size": None if stat.S_ISDIR(st.st_mode) else st.st_size, "mtime": int(st.st_mtime),
                "link": e.is_symlink(), "hidden": e.name.startswith("."),
            })
    entries.sort(key=lambda x: (not x["dir"], x["name"].casefold()))
    return {"path": _rel(d), "entries": entries, "trash": d == config.TRASH.resolve()}


@router.get("/download")
def download(path: str) -> FileResponse:
    p = target(path)
    if not p.is_file():
        raise HTTPException(404, "Keine Datei.")
    return FileResponse(p, media_type="application/octet-stream", filename=p.name,
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


@router.get("/text")
def read_text(path: str) -> dict:
    p = target(path)
    if not p.is_file():
        raise HTTPException(404, "Keine Datei.")
    if p.stat().st_size > TEXT_MAX:
        raise HTTPException(413, "Die Datei ist zu groß für den Editor (mehr als 2 MB).")
    raw = p.read_bytes()
    if b"\0" in raw[:8192]:
        raise HTTPException(415, "Das ist keine Textdatei.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return {"path": _rel(p), "name": p.name, "text": text, "mtime": int(p.stat().st_mtime)}


class TextIn(BaseModel):
    path: str
    text: str


@router.put("/text")
def write_text(body: TextIn) -> dict:
    p = place(body.path)
    if len(body.text.encode("utf-8")) > TEXT_MAX:
        raise HTTPException(413, "Zu groß für den Editor.")
    if p.exists() and not p.is_file():
        raise HTTPException(409, "Da liegt ein Ordner.")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.akari-tmp")
    tmp.write_text(body.text, encoding="utf-8")
    os.replace(tmp, p)
    return {"path": _rel(p.resolve()), "mtime": int(p.stat().st_mtime)}


@router.post("/upload")
async def upload(request: Request, path: str = "") -> dict:
    d = target(path)
    if not d.is_dir():
        raise HTTPException(404, "Kein Ordner.")
    form = await request.form(max_files=200)
    saved = []
    for f in form.getlist("files"):
        if not isinstance(f, UploadFile):
            continue
        dest = _free(d / _name(Path(f.filename or "Datei").name))
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out, 1024 * 1024)
        saved.append(dest.name)
    return {"saved": saved}


class PathIn(BaseModel):
    path: str


class RenameIn(BaseModel):
    path: str
    name: str


@router.post("/mkdir")
def mkdir(body: PathIn) -> dict:
    p = _free(place(body.path))
    p.mkdir(parents=False)
    return {"path": _rel(p)}


@router.post("/rename")
def rename(body: RenameIn) -> dict:
    p = place(body.path)
    if p == _home() or not (p.exists() or p.is_symlink()):
        raise HTTPException(404, "Gibt es nicht.")
    q = p.with_name(_name(body.name))
    if q.exists() or q.is_symlink():
        raise HTTPException(409, "Diesen Namen gibt es hier schon.")
    p.rename(q)
    return {"path": _rel(q)}


class PasteIn(BaseModel):
    op: str                 # "copy" or "cut"
    paths: list[str]
    dest: str = ""


@router.post("/paste")
def paste(body: PasteIn) -> dict:
    """Copy or move entries into a folder. A name that is taken gets " (2)";
    a folder never goes into itself; links stay links."""
    if body.op not in ("copy", "cut") or not body.paths or len(body.paths) > 500:
        raise HTTPException(400, "Das geht so nicht.")
    dest = target(body.dest)
    if not dest.is_dir():
        raise HTTPException(404, "Das Ziel ist kein Ordner.")
    done = []
    for rel in body.paths:
        src = place(rel)
        if not (src.exists() or src.is_symlink()) or src == _home():
            raise HTTPException(404, f"„{rel}“ gibt es nicht mehr.")
        real = src.resolve()
        if src.is_dir() and not src.is_symlink() and (dest == real or real in dest.parents):
            raise HTTPException(400, f"„{src.name}“ kann nicht in sich selbst.")
        if body.op == "cut" and src.parent.resolve() == dest:
            done.append(src.name)          # already here
            continue
        to = _free(dest / src.name)
        if body.op == "cut":
            shutil.move(str(src), str(to))
        elif src.is_dir() and not src.is_symlink():
            shutil.copytree(src, to, symlinks=True)
        else:
            shutil.copy2(src, to, follow_symlinks=False)
        done.append(to.name)
    return {"done": done}


@router.post("/trash")
def trash(body: PathIn) -> dict:
    p = place(body.path)
    if p == _home() or not (p.exists() or p.is_symlink()):
        raise HTTPException(404, "Gibt es nicht.")
    if p == config.TRASH.resolve() or config.TRASH.resolve() in p.parents:
        # already in the trash: this one goes for good
        shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
        return {"gone": True}
    config.TRASH.mkdir(parents=True, exist_ok=True)
    shutil.move(str(p), str(_free(config.TRASH / p.name)))
    return {"gone": False}


@router.post("/empty-trash")
def empty_trash() -> dict:
    n = 0
    for e in config.TRASH.iterdir():
        shutil.rmtree(e) if e.is_dir() and not e.is_symlink() else e.unlink()
        n += 1
    return {"removed": n}
