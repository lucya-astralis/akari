"""The machine under Akari: what apt says, what a hostname may be, the network as ip tells it."""
import json

import pytest

from akari import host


def test_upgradable_reads_apt(monkeypatch):
    out = ("Listing...\n"
           "akari/stable 0.12.0 all [upgradable from: 0.11.1]\n"
           "libc6/stable-security 2.41-12+deb13u1 amd64 [upgradable from: 2.41-12]\n")
    monkeypatch.setattr(host, "_run", lambda *a, **k: out)
    assert host.upgradable() == [{"name": "akari", "to": "0.12.0", "from": "0.11.1"},
                                 {"name": "libc6", "to": "2.41-12+deb13u1", "from": "2.41-12"}]


@pytest.mark.parametrize("name", ["", "-akari", "akari-", "Akari OS", "a" * 64, "akari.local", "akari;reboot"])
def test_a_bad_hostname_is_refused(name, monkeypatch):
    monkeypatch.setattr(host, "_check", lambda *a, **k: pytest.fail("must not run"))
    with pytest.raises(host.HostError):
        host.set_hostname(name)


def test_power_only_knows_two_things():
    with pytest.raises(host.HostError):
        host.power("halt; rm")


def test_unknown_jobs_and_zones_are_refused(monkeypatch):
    with pytest.raises(host.HostError):
        host.start("dist-upgrade")
    monkeypatch.setattr(host, "timezones", lambda: ["Europe/Berlin", "UTC"])
    with pytest.raises(host.HostError):
        host.set_clock(timezone="../../etc/shadow")


def test_network_from_ip(monkeypatch):
    addr = [{"ifname": "lo", "link_type": "loopback", "addr_info": []},
            {"ifname": "ens3", "operstate": "UP", "address": "52:54:00:12:34:56", "flags": ["UP"],
             "addr_info": [{"local": "10.0.2.15", "prefixlen": 24, "scope": "global"}, {"local": "fe80::1", "prefixlen": 64, "scope": "link"}]}]
    route = [{"dst": "default", "gateway": "10.0.2.2", "dev": "ens3"}]
    monkeypatch.setattr(host, "_run", lambda *a, **k: json.dumps(route if "route" in a else addr))
    monkeypatch.setattr(host.console, "address", lambda: "10.0.2.15")
    n = host.network()
    assert n["interfaces"] == [{"name": "ens3", "up": True, "mac": "52:54:00:12:34:56", "addresses": ["10.0.2.15/24"]}]
    assert n["gateway"] == "10.0.2.2" and n["url"] == "https://10.0.2.15/"
