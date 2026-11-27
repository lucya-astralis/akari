"""Docker on Akari: what a new container may be, image names, Docker's log frames, secrets kept back."""
import struct

import pytest

from akari import docker


def test_a_container_from_the_form():
    name, body = docker.run_body({"image": "nginx", "name": "web", "ports": ["8080:80", "127.0.0.1:5353:53/udp"],
                                  "env": ["A=1"], "volumes": ["web-data:/data", "/srv/site:/usr/share/nginx/html:ro"], "restart": "always"})
    assert name == "web" and body["Image"] == "nginx:latest"
    assert body["HostConfig"]["PortBindings"] == {"80/tcp": [{"HostIp": "", "HostPort": "8080"}], "53/udp": [{"HostIp": "127.0.0.1", "HostPort": "5353"}]}
    assert body["HostConfig"]["Binds"] == ["web-data:/data", "/srv/site:/usr/share/nginx/html:ro"]
    assert body["HostConfig"]["RestartPolicy"] == {"Name": "always"}
    assert "Privileged" not in body["HostConfig"]


@pytest.mark.parametrize("spec", [
    {"image": "nginx; rm -rf /"},
    {"image": "nginx", "name": "../x"},
    {"image": "nginx", "ports": ["80"]},
    {"image": "nginx", "ports": ["99999:80"]},
    {"image": "nginx", "env": ["no equals"]},
    {"image": "nginx", "volumes": ["/:/host"]},
    {"image": "nginx", "volumes": ["/var/run/docker.sock:/var/run/docker.sock"]},
    {"image": "nginx", "volumes": ["/etc:/etc"]},
    {"image": "nginx", "restart": "sometimes"},
])
def test_what_the_form_refuses(spec):
    with pytest.raises(docker.DockerError):
        docker.run_body(spec)


def test_image_names():
    assert docker._split("nginx") == ("nginx", "latest")
    assert docker._split("ghcr.io/lucya-astralis/lucent:stable") == ("ghcr.io/lucya-astralis/lucent", "stable")
    assert docker._split("localhost:5000/app:1.2") == ("localhost:5000/app", "1.2")
    with pytest.raises(docker.DockerError):
        docker._split("Nginx Latest")


def test_log_frames_are_taken_apart():
    frame = lambda s, t: struct.pack(">BxxxI", s, len(t)) + t
    assert docker._demux(frame(1, b"hello\n") + frame(2, b"oops\n")) == "hello\noops\n"
    assert docker._demux(b"plain tty output\n") == "plain tty output\n"


def test_secrets_in_the_environment_stay_hidden():
    assert docker._env("DB_PASSWORD=hunter2")["value"] != "hunter2"
    assert docker._env("API_TOKEN=abc")["value"] != "abc"
    assert docker._env("TZ=Europe/Berlin") == {"name": "TZ", "value": "Europe/Berlin"}


def test_stats():
    s = {"cpu_stats": {"cpu_usage": {"total_usage": 300}, "system_cpu_usage": 2000, "online_cpus": 2},
         "precpu_stats": {"cpu_usage": {"total_usage": 100}, "system_cpu_usage": 1000},
         "memory_stats": {"usage": 500, "limit": 1000, "stats": {"inactive_file": 100}},
         "networks": {"eth0": {"rx_bytes": 5, "tx_bytes": 7}}}
    st = docker._stats(s)
    assert st["cpu"] == 40.0 and st["mem"] == 400 and st["rx"] == 5 and st["tx"] == 7


def test_lucya_aio_is_started_as_its_readme_says():
    b = docker.aio_body()
    assert "/var/run/docker.sock:/var/run/docker.sock" in b["HostConfig"]["Binds"]
    assert b["HostConfig"]["RestartPolicy"] == {"Name": "always"} and b["Image"].startswith("ghcr.io/lucya-astralis/lucya-aio:")


def test_who_looks_after_a_container():
    assert docker._owner({"systems.lucya.aio": "lucya-"}) == "lucent"
    assert docker._owner({"systems.lucya.akari": "aio"}) == "aio"
    assert docker._owner({"systems.lucya.akari": "app"}) is None
    assert docker._owner({"com.docker.compose.project": "web"}) is None


@pytest.mark.parametrize("url,local", [
    ("http://127.0.0.1:8060", True), ("http://10.0.2.15:8060", True), ("http://lucya-lucent:8060", True),
    ("https://lucent.example", False), ("http://192.168.1.9:8060", False), (None, False)])
def test_a_lucent_here_or_elsewhere(url, local):
    assert docker._local(url, "10.0.2.15") is local


def test_the_stack_is_lucents_to_change(monkeypatch):
    import asyncio

    async def owned(cid):
        return "lucent"
    monkeypatch.setattr(docker, "_owned", owned)
    with pytest.raises(docker.DockerError, match="Lucent"):
        asyncio.run(docker.act("abc123", "remove"))


def test_no_second_lucent_when_paired_elsewhere(monkeypatch):
    import asyncio
    monkeypatch.setattr(docker, "paired", lambda: "elsewhere")
    with pytest.raises(docker.DockerError, match="zweiter"):
        asyncio.run(docker.install_lucent())


def test_not_removed_while_paired_with_it(monkeypatch):
    import asyncio
    monkeypatch.setattr(docker, "paired", lambda: "here")
    with pytest.raises(docker.DockerError, match="entkoppeln"):
        asyncio.run(docker.remove_lucent())
