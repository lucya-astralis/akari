"""Music: names from files, ID3 tags and covers, and streaming with Range."""
import struct

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from akari import audio

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60


def id3(frames: dict[str, bytes], picture: bytes | None = None) -> bytes:
    """A small ID3v2.3 tag: text frames in UTF-8 (encoding 3), and an APIC."""
    body = b""
    for fid, text in frames.items():
        data = b"\x03" + text
        body += fid.encode() + struct.pack(">I", len(data)) + b"\x00\x00" + data
    if picture:
        data = b"\x00" + b"image/jpeg\x00" + b"\x03" + b"\x00" + picture
        body += b"APIC" + struct.pack(">I", len(data)) + b"\x00\x00" + data
    size = len(body)
    syncsafe = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F])
    return b"ID3\x03\x00\x00" + syncsafe + body


@pytest.mark.parametrize("name, title, artist", [
    ("01 Geo22 - Magic.mp3", "Magic", "Geo22"),
    ("Geo22 - Magic.wav", "Magic", "Geo22"),
    ("Schein.wav", "Schein", None),
    ("07_Lanterns.ogg", "Lanterns", None),
])
def test_names_come_from_the_file_name_without_tags(home, name, title, artist):
    p = home / name
    p.write_bytes(b"\x00" * 16)
    t = audio.tags(p)
    assert t["title"] == title and t.get("artist") == artist


def test_id3_gives_title_artist_album_and_the_picture(home):
    p = home / "x.mp3"
    p.write_bytes(id3({"TIT2": "Magic".encode(), "TPE1": "Geo22".encode(), "TALB": "Nights".encode()}, JPEG) + b"\xff\xfb" * 100)
    t = audio.tags(p)
    assert (t["title"], t["artist"], t["album"], t["picture"]) == ("Magic", "Geo22", "Nights", True)
    assert audio._picture(p) == (JPEG, "image/jpeg")


@pytest.fixture()
def client(home):
    app = FastAPI()
    app.include_router(audio.router)
    (home / "Musik").mkdir()
    (home / "Musik" / "song.wav").write_bytes(bytes(range(256)) * 4)      # 1024 bytes
    (home / "Musik" / "notes.txt").write_text("not music")
    return TestClient(app)


def test_the_library_finds_the_music(client):
    tracks = client.get("/api/audio/library").json()["tracks"]
    assert [t["path"] for t in tracks] == ["Musik/song.wav"]


def test_a_whole_file_says_it_takes_ranges(client):
    r = client.get("/api/audio/stream", params={"path": "Musik/song.wav"})
    assert r.status_code == 200 and len(r.content) == 1024
    assert r.headers["accept-ranges"] == "bytes" and r.headers["content-type"] == "audio/wav"
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("rng, start, end", [("bytes=10-19", 10, 19), ("bytes=1000-", 1000, 1023), ("bytes=-5", 1019, 1023)])
def test_a_range_gives_just_that_part(client, rng, start, end):
    r = client.get("/api/audio/stream", params={"path": "Musik/song.wav"}, headers={"Range": rng})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes {start}-{end}/1024"
    assert r.content == (bytes(range(256)) * 4)[start:end + 1]


def test_a_range_past_the_end_is_refused(client):
    r = client.get("/api/audio/stream", params={"path": "Musik/song.wav"}, headers={"Range": "bytes=2000-"})
    assert r.status_code == 416 and r.headers["content-range"] == "bytes */1024"


@pytest.mark.parametrize("path, code", [("Musik/notes.txt", 404), ("../etc/passwd", 403), ("Musik/none.wav", 404)])
def test_only_audio_in_the_home_is_streamed(client, path, code):
    assert client.get("/api/audio/stream", params={"path": path}).status_code == code
