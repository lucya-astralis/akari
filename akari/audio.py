"""Music: the audio files in a person's home, for the Musik app. Runs in the agent.

  /api/audio/library   the audio files in ~/Musik (all the way down), and the
                       loose ones in ~/Downloads and ~/Schreibtisch; with title,
                       artist and album from their ID3 tags where there are
                       some, else from the file name ("Artist - Title.mp3")
  /api/audio/stream    one file, with Range, so the player can jump in it
  /api/audio/cover     the picture inside the file (ID3 APIC), or the folder's
                       cover.jpg / folder.jpg; 404 when there is none

Only files in HOME (files.target), only audio types, served with nosniff and a
sandbox, never as a page."""

from __future__ import annotations

import mimetypes
import os
import re
import stat
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from . import config
from .files import _rel, target

router = APIRouter(prefix="/api/audio")

TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg", ".oga": "audio/ogg",
         ".opus": "audio/ogg", ".flac": "audio/flac", ".wav": "audio/wav", ".webm": "audio/webm"}
LIMIT = 3000
CHUNK = 256 * 1024
HEAD = {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox", "Cache-Control": "private, max-age=300"}
_tags: dict[str, tuple[float, dict]] = {}       # path → (mtime, tags), so a library refresh reads each file once


# ---------- ID3v2: title, artist, album, picture ----------

def _syncsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _text(enc: int, raw: bytes) -> str:
    try:
        if enc == 0:
            s = raw.decode("latin-1")
        elif enc == 1:
            s = raw.decode("utf-16")
        elif enc == 2:
            s = raw.decode("utf-16-be")
        else:
            s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    return s.replace("\x00", " ").strip()


def _frames(path: Path, want_picture: bool = False):
    """The frames of an ID3v2.3/2.4 tag at the start of the file."""
    with open(path, "rb") as f:
        head = f.read(10)
        if len(head) < 10 or head[:3] != b"ID3" or head[3] not in (3, 4):
            return
        ver, size = head[3], _syncsafe(head[6:10])
        if size > 16 * 1024 * 1024:
            return
        data = f.read(size)
    i = 0
    while i + 10 <= len(data):
        fid = data[i:i + 4]
        if not fid.strip(b"\x00"):
            break
        n = _syncsafe(data[i + 4:i + 8]) if ver == 4 else int.from_bytes(data[i + 4:i + 8], "big")
        body = data[i + 10:i + 10 + n]
        i += 10 + n
        if n <= 0 or len(body) < n:
            break
        if fid == b"APIC" and not want_picture:
            continue
        yield fid.decode("latin-1", "replace"), body


def tags(path: Path) -> dict:
    out: dict = {}
    if path.suffix.lower() == ".mp3":
        try:
            for fid, body in _frames(path):
                if fid in ("TIT2", "TPE1", "TALB") and body:
                    out[{"TIT2": "title", "TPE1": "artist", "TALB": "album"}[fid]] = _text(body[0], body[1:])[:200]
                elif fid == "APIC":
                    out["picture"] = True
        except OSError:
            pass
    if not out.get("title"):
        stem = re.sub(r"^\d{1,3}[\s._-]+", "", path.stem)        # "01 - Title" → "Title"
        artist, sep, title = stem.partition(" - ")
        out.setdefault("title", (title if sep else stem).strip() or path.stem)
        if sep and not out.get("artist"):
            out["artist"] = artist.strip()
    return out


def _picture(path: Path) -> tuple[bytes, str] | None:
    try:
        for fid, body in _frames(path, want_picture=True):
            if fid != "APIC" or len(body) < 4:
                continue
            enc = body[0]
            mime_end = body.index(b"\x00", 1)
            mime = body[1:mime_end].decode("latin-1").lower() or "image/jpeg"
            rest = body[mime_end + 2:]                     # past the picture type
            term = b"\x00\x00" if enc in (1, 2) else b"\x00"
            j = rest.find(term)
            while enc in (1, 2) and j % 2:                 # UTF-16: the terminator starts on an even byte
                j = rest.find(term, j + 1)
            img = rest[j + len(term):]
            if img[:3] == b"\xff\xd8\xff":
                return img, "image/jpeg"
            if img[:8] == b"\x89PNG\r\n\x1a\n":
                return img, "image/png"
    except (OSError, ValueError):
        pass
    return None


# ---------- the library ----------

def _scan(folder: Path, deep: bool, out: list) -> None:
    if not folder.is_dir():
        return
    stack = [folder]
    while stack and len(out) < LIMIT:
        d = stack.pop()
        try:
            entries = sorted(os.scandir(d), key=lambda e: e.name.casefold())
        except OSError:
            continue
        for e in entries:
            if e.name.startswith("."):
                continue
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode):
                if deep:
                    stack.append(Path(e.path))
                continue
            p = Path(e.path)
            if not stat.S_ISREG(st.st_mode) or p.suffix.lower() not in TYPES:
                continue
            key = str(p)
            cached = _tags.get(key)
            t = cached[1] if cached and cached[0] == st.st_mtime else None
            if t is None:
                t = tags(p)
                _tags[key] = (st.st_mtime, t)
            out.append({"path": _rel(p), "folder": _rel(p.parent), "size": st.st_size, "mtime": int(st.st_mtime),
                        "title": t.get("title"), "artist": t.get("artist"), "album": t.get("album"),
                        "picture": bool(t.get("picture")) or _folder_cover(p.parent) is not None})


def _folder_cover(d: Path) -> Path | None:
    for n in ("cover.jpg", "cover.png", "folder.jpg", "folder.png", "front.jpg", "Cover.jpg", "Folder.jpg"):
        c = d / n
        if c.is_file():
            return c
    return None


@router.get("/library")
def library() -> dict:
    home = config.HOME
    out: list = []
    _scan(home / "Musik", True, out)
    for loose in ("Downloads", "Schreibtisch"):
        _scan(home / loose, False, out)
    return {"tracks": out, "folder": "Musik", "more": len(out) >= LIMIT}


def _audio(path: str) -> Path:
    p = target(path)
    if not p.is_file() or p.suffix.lower() not in TYPES:
        raise HTTPException(404, "Keine Audiodatei.")
    return p


@router.get("/stream")
def stream(path: str, request: Request) -> Response:
    p = _audio(path)
    size = p.stat().st_size
    kind = TYPES[p.suffix.lower()]
    start, end = 0, size - 1
    rng = request.headers.get("range", "")
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng.strip())
    partial = bool(m and (m.group(1) or m.group(2)))
    if partial:
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        else:                                            # the last n bytes
            start = max(0, size - int(m.group(2)))
        if start >= size or start > end:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}", **HEAD})

    def chunks():
        with open(p, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                b = f.read(min(CHUNK, left))
                if not b:
                    break
                left -= len(b)
                yield b

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(end - start + 1), **HEAD}
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(chunks(), status_code=206 if partial else 200, media_type=kind, headers=headers)


@router.get("/cover")
def cover(path: str) -> Response:
    p = _audio(path)
    pic = _picture(p) if p.suffix.lower() == ".mp3" else None
    if not pic:
        c = _folder_cover(p.parent)
        if c and c.stat().st_size <= 8 * 1024 * 1024:
            kind = mimetypes.guess_type(c.name)[0] or "image/jpeg"
            pic = (c.read_bytes(), kind)
    if not pic:
        raise HTTPException(404, "Kein Cover.")
    return Response(pic[0], media_type=pic[1], headers=HEAD)


# ---------- a Subsonic server (Navidrome, Airsonic, Gonic …) ----------
# The browser may only talk to Akari (CSP), so the agent asks the server. It
# keeps no password: Subsonic signs in with md5(password + salt) and the salt,
# and that pair is what ~/.config/akari/subsonic.json holds (0600).

import hashlib                                     # noqa: E402
import json                                        # noqa: E402
import secrets                                     # noqa: E402

import httpx                                       # noqa: E402
from pydantic import BaseModel                     # noqa: E402
from starlette.background import BackgroundTask    # noqa: E402

SUB = config.CONFIG / "subsonic.json"
API = "1.16.1"


def _sub() -> dict | None:
    try:
        return json.loads(SUB.read_text())
    except (OSError, ValueError):
        return None


def _auth(s: dict) -> dict:
    return {"u": s["user"], "t": s["token"], "s": s["salt"], "v": API, "c": "akari", "f": "json"}


async def _call(s: dict, method: str, **params) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.get(f"{s['url']}/rest/{method}", params={**_auth(s), **params})
    except httpx.HTTPError:
        raise HTTPException(502, "Der Musik-Server antwortet nicht.") from None
    try:
        body = r.json()["subsonic-response"]
    except (ValueError, KeyError):
        raise HTTPException(502, "Das ist kein Subsonic-Server.") from None
    if body.get("status") != "ok":
        err = body.get("error") or {}
        if err.get("code") in (40, 41, 44):
            raise HTTPException(403, "Benutzer oder Passwort stimmen nicht.")   # not 401: that means "signed out of Akari"
        raise HTTPException(502, f"Der Musik-Server sagt: {err.get('message') or 'Fehler'}")
    return body


class SubIn(BaseModel):
    url: str
    user: str
    password: str


@router.get("/subsonic")
def sub_state() -> dict:
    s = _sub()
    return {"url": s["url"], "user": s["user"], "name": s.get("name")} if s else {}


@router.put("/subsonic")
async def sub_connect(body: SubIn) -> dict:
    url = body.url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    salt = secrets.token_hex(8)
    s = {"url": url, "user": body.user.strip(), "salt": salt,
         "token": hashlib.md5((body.password + salt).encode()).hexdigest()}   # noqa: S324 (what Subsonic asks for)
    ping = await _call(s, "ping")
    s["name"] = ping.get("type") or "Subsonic"
    SUB.parent.mkdir(parents=True, exist_ok=True)
    tmp = SUB.with_suffix(".tmp")
    tmp.write_text(json.dumps(s))
    os.chmod(tmp, 0o600)
    os.replace(tmp, SUB)
    return sub_state()


@router.delete("/subsonic")
def sub_forget() -> dict:
    SUB.unlink(missing_ok=True)
    return {}


def _need() -> dict:
    s = _sub()
    if not s:
        raise HTTPException(404, "Kein Musik-Server verbunden.")
    return s


@router.get("/subsonic/library")
async def sub_library(q: str = "") -> dict:
    s = _need()
    songs = []
    body = await _call(s, "search3", query=q.strip(), songCount=500, albumCount=0, artistCount=0)
    songs = (body.get("searchResult3") or {}).get("song") or []
    if not songs and not q.strip():                   # servers that want a word: a random handful instead
        body = await _call(s, "getRandomSongs", size=300)
        songs = (body.get("randomSongs") or {}).get("song") or []
    tracks = [{"source": "subsonic", "id": str(x["id"]), "path": f"subsonic:{x['id']}", "title": x.get("title") or "?",
               "artist": x.get("artist"), "album": x.get("album"), "folder": x.get("album") or "",
               "picture": bool(x.get("coverArt")), "cover": str(x.get("coverArt") or ""), "duration": x.get("duration")}
              for x in songs if not x.get("isVideo")]
    return {"tracks": tracks, "server": s.get("name"), "url": s["url"]}


@router.get("/subsonic/stream")
async def sub_stream(id: str, request: Request) -> Response:  # noqa: A002
    s = _need()
    headers = {k: v for k, v in request.headers.items() if k in ("range", "if-range")}
    c = httpx.AsyncClient(timeout=httpx.Timeout(15, read=None), follow_redirects=True)
    req = c.build_request("GET", f"{s['url']}/rest/stream", params={**_auth(s), "id": id}, headers=headers)
    try:
        r = await c.send(req, stream=True)
    except httpx.HTTPError:
        await c.aclose()
        raise HTTPException(502, "Der Musik-Server antwortet nicht.") from None
    kind = r.headers.get("content-type", "")
    if r.status_code >= 400 or not kind.startswith("audio/"):
        await r.aclose(); await c.aclose()
        raise HTTPException(502, "Der Musik-Server liefert diesen Titel nicht.")

    async def close():
        await r.aclose()
        await c.aclose()
    out = {k: v for k, v in r.headers.items() if k in ("content-length", "content-range", "accept-ranges")}
    return StreamingResponse(r.aiter_raw(), status_code=r.status_code, media_type=kind, headers={**out, **HEAD},
                             background=BackgroundTask(close))


@router.get("/subsonic/cover")
async def sub_cover(id: str) -> Response:  # noqa: A002
    s = _need()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.get(f"{s['url']}/rest/getCoverArt", params={**_auth(s), "id": id, "size": 400})
    except httpx.HTTPError:
        raise HTTPException(502, "Der Musik-Server antwortet nicht.") from None
    kind = r.headers.get("content-type", "").split(";")[0]
    if r.status_code != 200 or kind not in ("image/jpeg", "image/png", "image/webp", "image/gif") or len(r.content) > 8 * 1024 * 1024:
        raise HTTPException(404, "Kein Cover.")
    return Response(r.content, media_type=kind, headers=HEAD)
