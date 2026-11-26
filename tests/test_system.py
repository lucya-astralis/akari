"""Akari on a real system: which users are accounts, sshd's file, the console."""
import grp
import pwd

import pytest

from akari import accounts, auth, console, ssh


def user(name, uid, shell="/bin/zsh", gecos="", gid=None):
    return pwd.struct_passwd((name, "x", uid, gid or uid, gecos, f"/home/{name}", shell))


SYSTEM = [
    user("root", 0, "/bin/bash"), user("daemon", 1, "/usr/sbin/nologin"),
    user("ada", 1000, gecos="Ada Lovelace,,,"), user("bob", 1001, "/bin/bash"),
    user("dev", 1002), user("svc", 1003, "/usr/sbin/nologin"), user("nobody", 65534, "/usr/sbin/nologin"),
]


@pytest.fixture()
def fake_system(tmp_path, monkeypatch):
    monkeypatch.setattr(pwd, "getpwall", lambda: SYSTEM)
    monkeypatch.setattr(grp, "getgrnam", lambda n: grp.struct_group(("sudo", "x", 27, ["ada"])) if n == "sudo" else (_ for _ in ()).throw(KeyError(n)))
    monkeypatch.setattr(accounts, "_locked", lambda: {"dev"})
    monkeypatch.setattr(accounts, "FILE", tmp_path / "accounts.json")


def test_accounts_are_the_people_who_can_sign_in(fake_system):
    got = accounts.all()
    assert [a.name for a in got] == ["ada", "bob"]          # no root, no system users, no locked dev, no nologin
    ada = got[0]
    assert ada.fullname == "Ada Lovelace" and ada.admin and not got[1].admin
    assert str(ada.home) == "/home/ada"


def test_extras_stay_beside_the_user(fake_system):
    accounts.set_avatar("bob", 42)
    accounts.set_lucent("bob", "https://lucent.test#7", "b@lucent.test")
    bob = accounts.get("bob")
    assert bob.avatar == 42 and bob.lucent_sub == "https://lucent.test#7" and accounts.by_lucent("https://lucent.test#7").name == "bob"
    with pytest.raises(accounts.AccountError):
        accounts.set_lucent("ada", "https://lucent.test#7")


def test_only_accounts_get_in_even_with_the_right_password(fake_system, monkeypatch):
    monkeypatch.setattr(accounts, "verify", lambda name, pw: True)       # PAM says yes to everyone
    assert accounts.authenticate("root", "x") is None
    assert accounts.authenticate("dev", "x") is None
    assert accounts.authenticate(" ADA ", "x").name == "ada"


def test_a_password_chpasswd_cannot_read_is_refused():
    with pytest.raises(accounts.AccountError):
        accounts._check_pw("lang-genug\nroot:x")
    with pytest.raises(accounts.AccountError):
        accounts._check_pw("kurz")


# ---- sshd -------------------------------------------------------------------------------------
def test_sshd_takes_passwords_only_from_who_allowed_them(monkeypatch):
    monkeypatch.setattr(accounts, "ssh_password_users", lambda: [])
    text = ssh.config_text()
    assert "PasswordAuthentication no" in text and "PermitRootLogin no" in text and "Match" not in text
    monkeypatch.setattr(accounts, "ssh_password_users", lambda: ["ada", "bob"])
    lines = ssh.config_text().strip().splitlines()
    assert lines[-2:] == ["Match User ada,bob", "    PasswordAuthentication yes"]     # Match last: it holds to the end


# ---- the console --------------------------------------------------------------------------------
def test_the_console_shows_the_address(monkeypatch):
    monkeypatch.setattr(accounts, "needs_setup", lambda: False)
    monkeypatch.setattr(console, "_qr", lambda t: "")
    assert "https://10.0.2.15/" in console.text("10.0.2.15") and auth.SETUP_TOKEN not in console.text("10.0.2.15")


def test_before_setup_the_console_shows_the_setup_link(monkeypatch):
    monkeypatch.setattr(accounts, "needs_setup", lambda: True)
    monkeypatch.setattr(console, "_qr", lambda t: "")
    assert f"https://10.0.2.15/?token={auth.SETUP_TOKEN}" in console.text("10.0.2.15")


def test_agetty_escapes_cannot_come_from_us(monkeypatch):
    monkeypatch.setattr(accounts, "needs_setup", lambda: False)
    monkeypatch.setattr(console, "_qr", lambda t: "\\n\\l")
    assert "\\\\n\\\\l" in console.text("10.0.2.15")


def test_the_address_without_a_default_route(monkeypatch):
    """A host-only network: no route to the world, but an address all the same."""
    answers = {("-4", "-o", "route", "get", "1.1.1.1"): "",
               ("-4", "-o", "addr", "show", "scope", "global"):
                   "2: enp0s3    inet 192.168.56.101/24 brd 192.168.56.255 scope global dynamic enp0s3\\       valid_lft 590sec"}
    monkeypatch.setattr(console, "_ip", lambda *a: answers.get(a, ""))
    assert console.address() == "192.168.56.101"


def test_the_address_from_the_default_route_comes_first(monkeypatch):
    monkeypatch.setattr(console, "_ip", lambda *a: "1.1.1.1 via 10.0.2.2 dev ens3 src 10.0.2.15 uid 0" if "route" in a
                        else "2: ens3 inet 10.9.9.9/24 scope global ens3")
    assert console.address() == "10.0.2.15"


def test_only_ipv6_gives_a_bracketed_address(monkeypatch):
    monkeypatch.setattr(console, "_ip", lambda *a: "2: ens3    inet6 2001:db8::5/64 scope global dynamic" if a[0] == "-6" else "")
    assert console.address() == "[2001:db8::5]"
