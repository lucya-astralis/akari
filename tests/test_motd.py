"""The welcome after login (motd.py): the mark beside the facts, nothing missing shown as an error."""
from akari import motd


def test_the_welcome_has_the_mark_and_the_version(monkeypatch):
    monkeypatch.setattr(motd, "COLOUR", False)
    monkeypatch.setattr(motd, "address", lambda: "10.0.2.15")
    out = "\n".join(motd.lines())
    assert "Akari OS" in out and "https://10.0.2.15/" in out and "▄█▀" in out
    assert "\x01" not in out and "\x02" not in out


def test_what_is_not_there_is_left_out(monkeypatch, tmp_path):
    monkeypatch.setattr(motd, "STATE", tmp_path)
    assert motd.updates() == "" and motd.lucent() == ""
    (tmp_path / "apt.json").write_text('{"count": 0}')
    assert "aktuell" in motd.updates()
