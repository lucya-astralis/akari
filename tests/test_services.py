"""The Dienste app's backend (services.py): what may be asked, what is kept out of reach, what systemd says."""
import json
import subprocess

import pytest

from akari import services


def fake(monkeypatch, outputs: dict):
    ran = []

    def run(*cmd, timeout=15):
        ran.append(cmd)
        out = next((v for k, v in outputs.items() if " ".join(cmd).startswith(k)), "")
        return subprocess.CompletedProcess(cmd, 0, out, "")
    monkeypatch.setattr(services, "_run", run)
    return ran


@pytest.mark.parametrize("name", ["", "nginx", "../x.service", "a b.service", "x.service; reboot", "foo.socket"])
def test_only_service_names(name):
    with pytest.raises(services.ServiceError):
        services._name(name)


def test_akari_cannot_cut_itself_off(monkeypatch):
    ran = fake(monkeypatch, {})
    for name in ("akarid.service", "caddy.service", "dbus.service", "systemd-journald.service", "akari-session@lucya.service"):
        for action in ("stop", "restart", "disable"):
            with pytest.raises(services.ServiceError):
                services.act(name, action)
    assert ran == []
    assert not services.protected("nginx.service") and not services.protected("docker.service")


def test_a_list_with_the_failed_first(monkeypatch):
    fake(monkeypatch, {
        "systemctl list-unit-files": json.dumps([{"unit_file": "nginx.service", "state": "enabled"}, {"unit_file": "cron.service", "state": "enabled"},
                                                  {"unit_file": "old.service", "state": "disabled"}, {"unit_file": "getty@.service", "state": "enabled"}]),
        "systemctl list-units": json.dumps([
            {"unit": "cron.service", "load": "loaded", "active": "active", "sub": "running", "description": "cron"},
            {"unit": "nginx.service", "load": "loaded", "active": "failed", "sub": "failed", "description": "web"},
            {"unit": "getty@tty1.service", "load": "loaded", "active": "active", "sub": "running", "description": "getty"},
            {"unit": "gone.service", "load": "not-found", "active": "inactive", "sub": "dead", "description": ""}]),
    })
    u = services.units()
    assert [x["name"] for x in u] == ["nginx.service", "cron.service", "getty@tty1.service", "old.service"]
    assert u[2]["enabled"] == "enabled" and u[3]["active"] == "inactive"


def test_the_journal_as_entries(monkeypatch):
    lines = "\n".join(json.dumps(e) for e in [
        {"__REALTIME_TIMESTAMP": "1700000000000000", "PRIORITY": "3", "SYSLOG_IDENTIFIER": "nginx", "MESSAGE": "bind failed"},
        {"__REALTIME_TIMESTAMP": "1700000001000000", "PRIORITY": "6", "_COMM": "x", "MESSAGE": [104, 105]}])
    ran = fake(monkeypatch, {"journalctl": lines})
    e = services.log("nginx.service", 50)
    assert e == [{"t": 1700000000, "p": 3, "who": "nginx", "msg": "bind failed"}, {"t": 1700000001, "p": 6, "who": "x", "msg": "hi"}]
    assert ran[-1][:3] == ("journalctl", "-u", "nginx.service")
    with pytest.raises(services.ServiceError):
        services.journal("loud")
