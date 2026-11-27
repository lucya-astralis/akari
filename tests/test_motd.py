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


def test_the_qr_code_has_the_same_margin_on_every_side(monkeypatch):
    from akari import console
    # a 3×3 code: dark corners, light centre
    monkeypatch.setattr(console, "_matrix", lambda text: [[True, False, True], [False, False, False], [True, False, True]])
    rows = console._qr("x").splitlines()
    n = 3 + 2 * console.QUIET
    assert all(len(r) == n for r in rows) and len(rows) == (n + 1) // 2
    assert rows[0] == "█" * n                                   # two light rows above: one full character
    assert rows[1][console.QUIET:console.QUIET + 3] == "▄█▄"    # dark corners on top, light below
    assert all(r[:console.QUIET] == r[-console.QUIET:] for r in rows[1:])  # left margin = right margin


def test_kmscon_starts_again_only_when_nobody_is_signed_in_on_tty1(monkeypatch):
    from akari import console
    ran = []
    sessions = {"5": "VTNr=1\nClass=user\n", "7": "VTNr=0\nClass=user\n"}

    def run(*cmd):
        ran.append(cmd)
        if cmd[:2] == ("loginctl", "list-sessions"):
            return "".join(f"{s} 1002 x seat0 1 user pts/0 no -\n" for s in sessions)
        if cmd[:2] == ("loginctl", "show-session"):
            return sessions[cmd[2]]
        if cmd[:2] == ("systemctl", "is-active"):
            return "active\n"
        return ""
    monkeypatch.setattr(console, "_run", run)
    console.redraw()
    assert ("systemctl", "restart", "kmsconvt@tty1.service") not in ran      # someone at the console
    sessions.pop("5"); ran.clear()
    console.redraw()
    assert ("systemctl", "restart", "kmsconvt@tty1.service") in ran


def test_the_same_text_is_not_written_again(monkeypatch, tmp_path):
    from akari import accounts, console
    monkeypatch.setattr(console, "ISSUE", tmp_path / "50-akari.issue")
    monkeypatch.setattr(console, "_matrix", lambda text: [])
    monkeypatch.setattr(accounts, "needs_setup", lambda: False)
    drawn = []
    monkeypatch.setattr(console, "redraw", lambda: drawn.append(1))
    console.write("10.0.2.15"); console.write("10.0.2.15")
    assert drawn == [1]
    console.write("10.0.2.16")
    assert drawn == [1, 1]
