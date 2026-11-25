"""Tests run without a container, a root user or real accounts.

config reads the home and the data folders when it is imported, so they
point into a fresh folder before any akari module is loaded; each test then
gets a home of its own (the `home` fixture)."""
import os
import sys
import tempfile
from pathlib import Path

_base = Path(tempfile.mkdtemp(prefix="akari-tests-"))
os.environ.setdefault("AKARI_DATA", str(_base / "data"))
os.environ.setdefault("AKARI_RUN", str(_base / "run"))
os.environ["HOME"] = str(_base / "home")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from akari import config  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """An empty home for the account the agent runs as."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setattr(config, "HOME", h)
    monkeypatch.setattr(config, "CONFIG", h / ".config" / "akari")
    return h
