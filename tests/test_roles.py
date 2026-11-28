"""Server roles (roles.py): what adding and taking away asks apt, and when a role counts as there."""
import subprocess

import pytest

from akari import host, roles


def test_adding_is_installing_the_metapackage():
    cmd = roles.command("files", "add")
    assert cmd[:2] == ["apt-get", "-y"] and cmd[-2:] == ["install", "akari-role-files"]


def test_taking_away_removes_what_came_with_it_and_keeps_data():
    cmd = roles.command("container", "remove")
    assert "remove" in cmd and "--autoremove" in cmd and "purge" not in cmd
    assert cmd[-3:] == ["akari-role-container", "docker.io", "docker-compose"]


@pytest.mark.parametrize("rid,action", [("nope", "add"), ("Files", "add"), ("files; rm", "add"), ("gaming", "add"), ("files", "purge")])
def test_what_is_refused(rid, action):
    with pytest.raises(roles.RoleError):
        roles.command(rid, action)


def test_a_role_is_there_with_its_metapackage_or_its_packages(monkeypatch):
    status = {"akari-role-container": "not-installed", "docker.io": "installed", "docker-compose": "installed",
              "akari-role-files": "not-installed", "samba": "installed", "wsdd2": "not-installed"}

    def run(cmd, **kw):
        if cmd[0] == "dpkg-query":
            out = "".join(f"{n} {status.get(n, 'not-installed')}\n" for n in cmd[3:])
        else:
            out = "\n".join("active" for _ in cmd[2:]) + "\n"
        return subprocess.CompletedProcess(cmd, 0, out, "")
    monkeypatch.setattr(roles.subprocess, "run", run)
    monkeypatch.setattr(host, "updates", lambda: {"running": "role:files:add"})
    by = {r["id"]: r for r in roles.roles()}
    assert by["container"]["state"] == "installed" and by["container"]["adopted"] is True
    assert by["files"]["state"] == "adding"
    assert by["gaming"]["state"] == "soon"
    assert by["container"]["services"][0] == {"name": "docker.service", "active": "active"}
