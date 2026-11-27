"""Docker on Akari OS: the engine, its containers and images, and Lucent on top.

Docker is not part of Akari; an account that manages installs it from
Debian with one click (docker.io, through host.py's apt unit). akarid then
talks to the engine over its socket, as root: whoever holds that socket is
root on the machine, so every route here is for accounts that manage only.

Lucent comes the way lucya.systems runs it on one machine: lucya-aio, the
helper that makes Lucent and, when Lucent asks, the tools, keeps them up to
date and backs them up. Akari starts the helper (as `docker run` in its
README would) and shows where Lucent is and its setup code. Lucent reaches
Akari back at http://<this machine>:8131, a door that Caddy opens only for
Lucent's tool API (/lucent/v1): Lucent checks TLS certificates, and Akari's
own are made by Caddy for the browser."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import struct
import time

import httpx

from . import console

SOCKET = os.environ.get("AKARI_DOCKER_SOCKET", "/var/run/docker.sock")
AIO_IMAGE = os.environ.get("AKARI_AIO_IMAGE", "ghcr.io/lucya-astralis/lucya-aio")
AIO_TAG = os.environ.get("AKARI_AIO_TAG", "stable")
AIO_NAME = "lucya-aio"
LUCENT_NAME = "lucya-lucent"
LUCENT_PORT = 8060
DOOR_PORT = 8131                       # Caddy: http, only /lucent/v1, for Lucent in its container
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class DockerError(Exception):
    pass


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(uds=SOCKET), base_url="http://docker/v1.43",
                             timeout=httpx.Timeout(30, connect=3))


async def _call(method: str, path: str, *, params=None, json_body=None, timeout: float | None = 30) -> httpx.Response:
    try:
        async with _client() as c:
            r = await c.request(method, path, params=params, json=json_body, timeout=timeout)
    except httpx.HTTPError as e:
        raise DockerError(f"Docker antwortet nicht ({e.__class__.__name__}).")
    if r.status_code >= 400:
        try:
            msg = r.json().get("message")
        except ValueError:
            msg = r.text
        raise DockerError(msg or f"Docker: Fehler {r.status_code}")
    return r


def _safe(cid: str) -> str:
    if not ID.match(cid or ""):
        raise DockerError("Unbekannter Container.")
    return cid


# ---------- the engine ----------

async def status() -> dict:
    installed = bool(shutil.which("dockerd") or shutil.which("docker"))
    out = {"installed": installed, "running": False, "version": None, "containers": 0, "images": 0}
    if not os.path.exists(SOCKET):
        return out
    with contextlib.suppress(DockerError):
        info = (await _call("GET", "/info", timeout=5)).json()
        out.update(running=True, version=info.get("ServerVersion"), containers=info.get("Containers", 0),
                   running_containers=info.get("ContainersRunning", 0), images=info.get("Images", 0),
                   root=info.get("DockerRootDir"), storage=info.get("Driver"))
    return out


async def containers() -> list[dict]:
    rows = (await _call("GET", "/containers/json", params={"all": "1"})).json()
    out = []
    for c in rows:
        labels = c.get("Labels") or {}
        # published ports once (Docker lists IPv4 and IPv6 apart), the address only when it narrows
        ports = sorted({(f"{p['IP']}:" if p.get("IP") not in (None, "", "0.0.0.0") else "") + f"{p['PublicPort']}→{p['PrivatePort']}"
                        for p in c.get("Ports") or [] if p.get("PublicPort") and p.get("IP") != "::"})
        out.append({
            "id": c["Id"][:12], "name": (c.get("Names") or ["/?"])[0].lstrip("/"), "image": c.get("Image", ""),
            "state": c.get("State", ""), "status": c.get("Status", ""), "created": c.get("Created"),
            "ports": ports, "project": labels.get("com.docker.compose.project")
            # Lucent, its tools and its helper: one stack
            or ("lucya.systems" if "systems.lucya.aio" in labels or labels.get("systems.lucya.akari") == "aio" else None),
        })
    return sorted(out, key=lambda c: (c["state"] != "running", c["name"]))


async def images() -> list[dict]:
    rows = (await _call("GET", "/images/json")).json()
    out = []
    for i in rows:
        tags = [t for t in (i.get("RepoTags") or []) if t != "<none>:<none>"]
        out.append({"id": i["Id"].split(":")[-1][:12], "tags": tags, "size": i.get("Size", 0), "created": i.get("Created"),
                    "used": i.get("Containers", -1)})
    return sorted(out, key=lambda i: (not i["tags"], i["tags"][0] if i["tags"] else ""))


async def act(cid: str, action: str) -> None:
    cid = _safe(cid)
    if action in ("start", "stop", "restart"):
        await _call("POST", f"/containers/{cid}/{action}", timeout=60)
    elif action == "remove":
        await _call("DELETE", f"/containers/{cid}", params={"force": "1"}, timeout=60)
    else:
        raise DockerError("Unbekannte Aktion.")


async def remove_image(iid: str) -> None:
    await _call("DELETE", f"/images/{_safe(iid)}", timeout=60)


async def pause(cid: str, on: bool) -> None:
    await _call("POST", f"/containers/{_safe(cid)}/{'pause' if on else 'unpause'}")


async def inspect(cid: str) -> dict:
    """One container in detail: what it runs, with what, where its data is, and what it uses now."""
    c = (await _call("GET", f"/containers/{_safe(cid)}/json")).json()
    cfg, hc, st = c.get("Config") or {}, c.get("HostConfig") or {}, c.get("State") or {}
    ports = []
    for priv, binds in ((c.get("NetworkSettings") or {}).get("Ports") or {}).items():
        for b in binds or []:
            if b.get("HostIp") != "::":
                ports.append({"host": f"{b.get('HostIp') or '0.0.0.0'}:{b.get('HostPort')}", "container": priv})
    out = {
        "id": c["Id"][:12], "name": c.get("Name", "").lstrip("/"), "image": cfg.get("Image"),
        "state": st.get("Status"), "started": st.get("StartedAt"), "exit": st.get("ExitCode"), "health": (st.get("Health") or {}).get("Status"),
        "restart": (hc.get("RestartPolicy") or {}).get("Name") or "no",
        "cmd": " ".join((cfg.get("Entrypoint") or []) + (cfg.get("Cmd") or [])),
        # environment: names, and values unless they look like secrets
        "env": [_env(e) for e in cfg.get("Env") or []],
        "mounts": [{"type": m.get("Type"), "source": m.get("Name") or m.get("Source"), "target": m.get("Destination"), "rw": m.get("RW")}
                   for m in c.get("Mounts") or []],
        "ports": ports,
        "networks": sorted(((c.get("NetworkSettings") or {}).get("Networks") or {}).keys()),
        "labels": {k: v for k, v in (cfg.get("Labels") or {}).items() if k.startswith(("com.docker.compose.project", "org.opencontainers.image.version", "org.opencontainers.image.source"))},
    }
    if st.get("Running"):
        with contextlib.suppress(DockerError):
            out["stats"] = _stats((await _call("GET", f"/containers/{_safe(cid)}/stats", params={"stream": "false"}, timeout=10)).json())
    return out


SECRET = re.compile(r"(PASS|SECRET|TOKEN|KEY|CREDENTIAL)", re.I)


def _env(e: str) -> dict:
    k, _, v = e.partition("=")
    return {"name": k, "value": "••••••" if SECRET.search(k) and v else v}


def _stats(s: dict) -> dict:
    cpu, pre = s.get("cpu_stats") or {}, s.get("precpu_stats") or {}
    d_cpu = (cpu.get("cpu_usage") or {}).get("total_usage", 0) - (pre.get("cpu_usage") or {}).get("total_usage", 0)
    d_sys = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
    cpus = cpu.get("online_cpus") or len((cpu.get("cpu_usage") or {}).get("percpu_usage") or []) or 1
    mem = s.get("memory_stats") or {}
    used = mem.get("usage", 0) - ((mem.get("stats") or {}).get("inactive_file", 0))
    net = s.get("networks") or {}
    return {"cpu": round(100 * d_cpu / d_sys * cpus, 1) if d_sys > 0 else 0.0, "mem": max(0, used), "mem_limit": mem.get("limit"),
            "rx": sum(n.get("rx_bytes", 0) for n in net.values()), "tx": sum(n.get("tx_bytes", 0) for n in net.values()),
            "pids": (s.get("pids_stats") or {}).get("current")}


async def volumes() -> list[dict]:
    vols = (await _call("GET", "/volumes")).json().get("Volumes") or []
    used: dict[str, list[str]] = {}
    for c in (await _call("GET", "/containers/json", params={"all": "1"})).json():
        for m in c.get("Mounts") or []:
            if m.get("Type") == "volume":
                used.setdefault(m.get("Name"), []).append((c.get("Names") or ["/?"])[0].lstrip("/"))
    return sorted(({"name": v["Name"], "driver": v.get("Driver"), "created": v.get("CreatedAt"), "used_by": used.get(v["Name"], []),
                    "project": (v.get("Labels") or {}).get("com.docker.compose.project")} for v in vols), key=lambda v: v["name"])


async def remove_volume(name: str) -> None:
    await _call("DELETE", f"/volumes/{_safe(name)}")


async def networks() -> list[dict]:
    rows = (await _call("GET", "/networks")).json()
    return sorted(({"id": n["Id"][:12], "name": n["Name"], "driver": n.get("Driver"), "internal": n.get("Internal", False),
                    "subnet": next((c.get("Subnet") for c in (n.get("IPAM") or {}).get("Config") or [] if c.get("Subnet")), None),
                    "builtin": n["Name"] in ("bridge", "host", "none")} for n in rows), key=lambda n: (n["builtin"], n["name"]))


async def remove_network(nid: str) -> None:
    await _call("DELETE", f"/networks/{_safe(nid)}")


async def prune() -> dict:
    """Clear away what nothing uses: stopped containers, dangling images, unused networks. Volumes stay (data)."""
    a = (await _call("POST", "/containers/prune", timeout=120)).json()
    b = (await _call("POST", "/images/prune", timeout=120)).json()
    await _call("POST", "/networks/prune", timeout=60)
    return {"containers": len(a.get("ContainersDeleted") or []), "images": len(b.get("ImagesDeleted") or []),
            "space": (a.get("SpaceReclaimed") or 0) + (b.get("SpaceReclaimed") or 0)}


# ---------- pulling and running: in the background, the app looks at _pulls ----------

_pulls: dict[str, dict] = {}            # image → {state: pulling|done|error, error, at}
IMAGE = re.compile(r"^[a-z0-9]+([._/-][a-z0-9]+)*(:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?$|^[a-z0-9.-]+(:[0-9]+)?/[a-z0-9._/-]+(:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?$")


def _split(ref: str) -> tuple[str, str]:
    ref = ref.strip()
    if not IMAGE.match(ref):
        raise DockerError("Das ist kein Image-Name (etwa nginx:latest oder ghcr.io/owner/app:1.0).")
    name, tag = (ref.rsplit(":", 1) if ":" in ref.rsplit("/", 1)[-1] else (ref, "latest"))
    return name, tag


async def _pull_bg(ref: str) -> None:
    name, tag = _split(ref)
    _pulls[ref] = {"state": "pulling", "at": time.time()}
    try:
        await _pull(name, tag)
        _pulls[ref] = {"state": "done", "at": time.time()}
    except DockerError as e:
        _pulls[ref] = {"state": "error", "error": str(e), "at": time.time()}


def pull(ref: str) -> None:
    _split(ref)
    if _pulls.get(ref, {}).get("state") == "pulling":
        raise DockerError("Dieses Image wird schon geladen.")
    asyncio.get_running_loop().create_task(_pull_bg(ref))


def pulls() -> dict:
    now = time.time()
    for k in [k for k, v in _pulls.items() if v["state"] != "pulling" and now - v["at"] > 300]:
        _pulls.pop(k)
    return _pulls


NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$")
# host folders a container from the form never gets: the system itself and the docker socket
# (a container with either is root on the machine). The Lucent helper gets the socket, as its README says.
SYSTEM_DIRS = ("/etc", "/root", "/boot", "/proc", "/sys", "/dev", "/usr", "/bin", "/sbin", "/lib", "/var/lib/docker", "/var/lib/akari")
SOCKETS = ("/var/run/docker.sock", "/run/docker.sock")


def _forbidden(path: str) -> bool:
    for p in {os.path.normpath(path), os.path.realpath(path)}:
        if p == "/" or p in SOCKETS or any(p == d or p.startswith(d + "/") for d in SYSTEM_DIRS):
            return True
    return False
RESTART = {"no", "always", "unless-stopped", "on-failure"}


def run_body(spec: dict) -> tuple[str, dict]:
    """A new container from the form: image, name, ports, environment, volumes, restart. Checked, nothing else."""
    image = spec.get("image", "").strip()
    _split(image)
    name = (spec.get("name") or "").strip()
    if name and not NAME.match(name):
        raise DockerError("Ein Name hat Buchstaben, Ziffern, _ . und -.")
    exposed, bindings = {}, {}
    for p in spec.get("ports") or []:
        m = re.match(r"^(?:(\d{1,3}(?:\.\d{1,3}){3}):)?(\d{1,5}):(\d{1,5})(?:/(tcp|udp))?$", str(p).strip())
        if not m or not (0 < int(m[2]) < 65536 and 0 < int(m[3]) < 65536):
            raise DockerError(f"Port „{p}“: so wie 8080:80 oder 127.0.0.1:8080:80.")
        key = f"{m[3]}/{m[4] or 'tcp'}"
        exposed[key] = {}
        bindings.setdefault(key, []).append({"HostIp": m[1] or "", "HostPort": m[2]})
    env = []
    for e in spec.get("env") or []:
        k, sep, _ = str(e).partition("=")
        if not sep or not re.match(r"^[A-Za-z_][A-Za-z0-9_.-]*$", k):
            raise DockerError(f"Umgebung „{e}“: so wie NAME=wert.")
        env.append(str(e))
    binds = []
    for v in spec.get("volumes") or []:
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*|/[^:]*):(/[^:]*)(?::(ro|rw))?$", str(v).strip())
        if not m:
            raise DockerError(f"Volume „{v}“: so wie daten:/data oder /srv/ordner:/data:ro.")
        if m[1].startswith("/") and _forbidden(m[1]):
            raise DockerError(f"„{m[1]}“ gibt Akari keinem Container.")
        binds.append(m[0])
    restart = spec.get("restart") or "unless-stopped"
    if restart not in RESTART:
        raise DockerError("Unbekannte Neustart-Regel.")
    body = {"Image": image if ":" in image.rsplit("/", 1)[-1] else f"{image}:latest", "Env": env, "ExposedPorts": exposed,
            "Labels": {"systems.lucya.akari": "app"},
            "HostConfig": {"PortBindings": bindings, "Binds": binds, "RestartPolicy": {"Name": restart}}}
    return name, body


async def run(spec: dict) -> str:
    name, body = run_body(spec)
    have = {t for i in (await _call("GET", "/images/json")).json() for t in i.get("RepoTags") or []}
    if body["Image"] not in have:
        await _pull(*_split(body["Image"]))
    r = await _call("POST", "/containers/create", params={"name": name} if name else None, json_body=body)
    cid = r.json()["Id"]
    await _call("POST", f"/containers/{cid}/start", timeout=60)
    return cid[:12]


def _demux(raw: bytes) -> str:
    """Docker's log stream: 8-byte frames (stream, size) unless the container has a TTY."""
    out, i = [], 0
    if len(raw) >= 8 and raw[0] in (0, 1, 2) and raw[1:4] == b"\0\0\0":
        while i + 8 <= len(raw):
            size = struct.unpack(">I", raw[i + 4:i + 8])[0]
            out.append(raw[i + 8:i + 8 + size])
            i += 8 + size
        raw = b"".join(out)
    return raw.decode("utf-8", "replace")


async def logs(cid: str, tail: int = 300) -> str:
    r = await _call("GET", f"/containers/{_safe(cid)}/logs", params={"stdout": "1", "stderr": "1", "tail": str(max(1, min(tail, 2000)))})
    return _demux(r.content)


# ---------- Lucent, through lucya-aio ----------

_job: dict = {}                 # the running setup: step, error


async def _find(name: str) -> dict | None:
    rows = (await _call("GET", "/containers/json", params={"all": "1", "filters": json.dumps({"name": [f"^/{name}$"]})})).json()
    return rows[0] if rows else None


def _code(text: str) -> str | None:
    m = re.findall(r"Einrichtungscode:\s*(\S+)", text)
    return m[-1] if m else None


async def lucent() -> dict:
    out = {"aio": None, "lucent": None, "job": _job.get("step"), "error": _job.get("error"), "port": LUCENT_PORT, "door": DOOR_PORT}
    with contextlib.suppress(DockerError):
        aio, luc = await _find(AIO_NAME), await _find(LUCENT_NAME)
        if aio:
            out["aio"] = {"state": aio.get("State"), "status": aio.get("Status"), "id": aio["Id"][:12]}
            out["code"] = _code(await logs(aio["Id"][:12], 400))
        if luc:
            out["lucent"] = {"state": luc.get("State"), "status": luc.get("Status"), "id": luc["Id"][:12]}
    ip = console.address()
    out["url"] = f"http://{ip}:{LUCENT_PORT}" if ip else None
    out["akari_base"] = f"http://{ip}:{DOOR_PORT}" if ip else None
    return out


async def _pull(image: str, tag: str) -> None:
    try:
        async with _client() as c:
            async with c.stream("POST", "/images/create", params={"fromImage": image, "tag": tag}, timeout=None) as r:
                if r.status_code >= 400:
                    raise DockerError((await r.aread()).decode("utf-8", "replace")[:300])
                async for line in r.aiter_lines():
                    with contextlib.suppress(ValueError):
                        msg = json.loads(line)
                        if msg.get("error"):
                            raise DockerError(msg["error"])
    except httpx.HTTPError as e:
        raise DockerError(f"Das Image ließ sich nicht laden ({e.__class__.__name__}).")


def aio_body() -> dict:
    """lucya-aio as its README starts it: the socket, its data, the backups, restart always."""
    return {
        "Image": f"{AIO_IMAGE}:{AIO_TAG}",
        "Env": [f"LUCYA_PORT={LUCENT_PORT}", "LUCYA_BIND=0.0.0.0", "LUCYA_CHANNEL=stable", f"TZ={_tz()}"],
        "Labels": {"systems.lucya.akari": "aio"},
        "HostConfig": {
            "Binds": ["/var/run/docker.sock:/var/run/docker.sock", "lucya-aio-data:/data", "lucya-backups:/backups"],
            "RestartPolicy": {"Name": "always"},
            "NetworkMode": "bridge",
        },
    }


def _tz() -> str:
    with contextlib.suppress(OSError):
        return os.path.realpath("/etc/localtime").split("/zoneinfo/", 1)[1]
    return "UTC"


async def _setup() -> None:
    try:
        _job.update(step="pull", error=None)
        await _pull(AIO_IMAGE, AIO_TAG)
        _job["step"] = "start"
        if not await _find(AIO_NAME):
            r = await _call("POST", "/containers/create", params={"name": AIO_NAME}, json_body=aio_body())
            await _call("POST", f"/containers/{r.json()['Id']}/start")
        else:
            await _call("POST", f"/containers/{AIO_NAME}/start")
        # the helper makes Lucent itself: wait until it is there (its image is pulled first)
        _job["step"] = "lucent"
        for _ in range(180):
            luc = await _find(LUCENT_NAME)
            if luc and luc.get("State") == "running":
                break
            await asyncio.sleep(2)
        else:
            raise DockerError("Lucent ist nach sechs Minuten noch nicht da. Die Protokolle von lucya-aio sagen mehr.")
        _job.clear()
    except DockerError as e:
        _job.update(step=None, error=str(e))
    except Exception as e:                      # noqa: BLE001  (a setup must never hang in a step)
        _job.update(step=None, error=repr(e))


_task: asyncio.Task | None = None


async def install_lucent() -> None:
    global _task
    st = await status()
    if not st["running"]:
        raise DockerError("Docker läuft nicht.")
    if _task and not _task.done():
        raise DockerError("Lucent wird schon eingerichtet.")
    _job.update(step="pull", error=None, at=time.time())
    _task = asyncio.create_task(_setup())


async def remove_lucent() -> None:
    """The helper goes, and with it Lucent and the tools it made; their volumes stay."""
    rows = (await _call("GET", "/containers/json", params={"all": "1", "filters": json.dumps({"label": ["systems.lucya.aio"]})})).json()
    for c in rows:
        await _call("DELETE", f"/containers/{c['Id']}", params={"force": "1"}, timeout=60)
    with contextlib.suppress(DockerError):
        await _call("DELETE", f"/containers/{AIO_NAME}", params={"force": "1"}, timeout=60)
