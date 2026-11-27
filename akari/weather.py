"""The weather for the clock widget, from Open-Meteo (open-meteo.com: free, no key).

Runs in the account's agent. Where: a place the person typed (?place=), else
the city in the system's time zone (Europe/Berlin → Berlin), found with
Open-Meteo's geocoding. Nothing else leaves the machine: no address, no
account, only that name and then its coordinates. Places are kept for the
agent's life, the weather for fifteen minutes; when Open-Meteo cannot be
reached the widget simply shows no weather."""

from __future__ import annotations

import contextlib
import os
import time

import httpx
from fastapi import APIRouter

from . import config

router = APIRouter(prefix="/api")
GEO = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
TTL = 15 * 60
_places: dict[str, dict | None] = {}
_weather: dict[tuple, tuple[float, dict]] = {}

# WMO weather codes (Open-Meteo) → what the widget draws
KINDS = [((0,), "clear"), ((1, 2), "partly"), ((3,), "cloudy"), ((45, 48), "fog"),
         ((51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82), "rain"),
         ((71, 73, 75, 77, 85, 86), "snow"), ((95, 96, 99), "storm")]


def kind(code: int) -> str:
    return next((k for codes, k in KINDS if code in codes), "cloudy")


def zone_city(zone: str | None = None) -> str | None:
    """Europe/Berlin → Berlin, America/New_York → New York; UTC and the like → None."""
    if zone is None:
        with contextlib.suppress(OSError):
            zone = os.path.realpath("/etc/localtime").split("/zoneinfo/", 1)[1]
    if not zone or "/" not in zone or zone.startswith(("Etc/", "posix/", "right/")):
        return None
    return zone.rsplit("/", 1)[1].replace("_", " ")


async def _place(c: httpx.AsyncClient, name: str) -> dict | None:
    if name not in _places:
        r = await c.get(GEO, params={"name": name, "count": 1, "format": "json"})
        hit = (r.json().get("results") or [None])[0] if r.status_code == 200 else None
        _places[name] = hit and {"name": hit.get("name") or name, "lat": hit["latitude"], "lon": hit["longitude"]}
    return _places[name]


@router.get("/weather")
async def weather(place: str = "") -> dict:
    name = place.strip()[:80] or zone_city()
    if not name:
        return {"ok": False}
    try:
        async with httpx.AsyncClient(timeout=12, headers={"User-Agent": f"akari-os/{config.VERSION}"}) as c:
            p = await _place(c, name)
            if not p:
                return {"ok": False, "place": name}
            key = (round(p["lat"], 2), round(p["lon"], 2))
            hit = _weather.get(key)
            if not hit or time.time() - hit[0] > TTL:
                r = await c.get(FORECAST, params={"latitude": p["lat"], "longitude": p["lon"], "timezone": "auto",
                                                  "current": "temperature_2m,weather_code,is_day"})
                r.raise_for_status()
                cur = r.json()["current"]
                hit = (time.time(), {"temp": round(cur["temperature_2m"]), "kind": kind(int(cur["weather_code"])), "day": bool(cur.get("is_day", 1))})
                _weather[key] = hit
    except (httpx.HTTPError, ValueError, KeyError):
        return {"ok": False, "place": name}
    return {"ok": True, "place": p["name"], **hit[1]}
