#!/usr/bin/env python3
"""Fetch 2026 SpaceX launches from Launch Library 2 and write launches.json."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

YEAR = 2026
API = "https://ll.thespacedevs.com/2.2.0/launch/"
UA = "bennettwells-spacexdemo/1.0 (+https://bennettwells.net/spacexdemo)"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "launches.json"

FLOWN = {"Success": "success", "Failure": "failure", "Partial Failure": "partial"}


def get_json(url: str, retries: int = 4) -> dict:
    last = None
    for i in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            last = e
            wait = 8 * (i + 1) if e.code in (429, 500, 502, 503, 504) else None
            if wait is None:
                raise
            print(f"HTTP {e.code} — retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
        except TimeoutError as e:
            last = e
            time.sleep(5 * (i + 1))
    raise last  # type: ignore[misc]


def paginate(params: str) -> list[dict]:
    url = f"{API}?{params}&limit=100&mode=list&ordering=net"
    rows: list[dict] = []
    while url:
        data = get_json(url)
        rows.extend(data.get("results") or [])
        url = data.get("next")
        print(f"fetched {len(rows)}/{data.get('count')}", file=sys.stderr)
    return rows


def classify_vehicle(name: str) -> tuple[str, str]:
    head = (name or "").split("|")[0].strip()
    low = name.lower()
    if "falcon heavy" in low:
        return "falcon-heavy", head or "Falcon Heavy"
    if "starship" in low:
        return "starship", head or "Starship"
    if "falcon 9" in low:
        return "falcon9", head or "Falcon 9"
    return "other", head or "Unknown"


def mission_name(name: str, mission: str | None) -> str:
    if mission:
        return mission
    if "|" in (name or ""):
        return name.split("|", 1)[1].strip()
    return name or "Unknown"


def short_pad(pad: str | None) -> str:
    if not pad:
        return "—"
    p = pad
    p = p.replace("Space Launch Complex ", "SLC-")
    p = p.replace("Launch Complex ", "LC-")
    p = p.replace("Orbital Launch Pad ", "Pad ")
    return p


def estimate_payload_t(mission: str, vehicle: str) -> float:
    n = (mission or "").lower()
    if vehicle == "falcon-heavy":
        if "roman" in n:
            return 9.2
        if "viasat" in n:
            return 6.4
        return 8.0
    if vehicle == "starship":
        if "flight 13" in n:
            return 25.0
        return 0.0
    if "starlink" in n:
        if re.search(r"group\s*10", n) or re.search(r"group\s*6", n):
            return 16.7
        if re.search(r"group\s*15", n):
            return 15.5
        if re.search(r"group\s*17", n) or re.search(r"group\s*12", n):
            return 16.0
        return 15.5
    if "starshield" in n or "nrol" in n or "ussf" in n:
        return 8.0
    return 6.0


def status_of(abbrev: str) -> str:
    if abbrev in FLOWN:
        return FLOWN[abbrev]
    return "upcoming"


def normalize(row: dict) -> dict:
    name = row.get("name") or ""
    vehicle, vehicle_label = classify_vehicle(name)
    mission = mission_name(name, row.get("mission"))
    abbrev = ((row.get("status") or {}).get("abbrev")) or "TBD"
    return {
        "id": row.get("id"),
        "net": row.get("net"),
        "name": mission,
        "vehicle": vehicle,
        "vehicle_label": vehicle_label,
        "pad": short_pad(row.get("pad")),
        "site": row.get("location") or "—",
        "status": status_of(abbrev),
        "status_label": (row.get("status") or {}).get("name") or abbrev,
        "orbit": row.get("orbit"),
        "mission_type": row.get("mission_type") or "",
        "payload_t": estimate_payload_t(mission, vehicle),
        "image": row.get("image"),
    }


def world_success_count(now: datetime) -> int | None:
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (
        f"{API}?net__gte={YEAR}-01-01T00:00:00Z&net__lte={end}"
        f"&status=3&limit=1&mode=list&include_suborbital=true"
    )
    try:
        data = get_json(url)
        return int(data.get("count") or 0)
    except Exception as e:
        print(f"world count failed: {e}", file=sys.stderr)
        return None


def main() -> int:
    now = datetime.now(timezone.utc)
    rows = paginate(
        f"lsp__name=SpaceX&net__gte={YEAR}-01-01T00:00:00Z"
        f"&net__lte={YEAR}-12-31T23:59:59Z&include_suborbital=true"
    )
    launches = [normalize(r) for r in rows]
    launches.sort(key=lambda x: x.get("net") or "")

    flown = [l for l in launches if l["status"] in ("success", "failure", "partial")]
    upcoming = [l for l in launches if l["status"] == "upcoming"]
    sx_mass = round(sum(l["payload_t"] for l in flown), 1)

    world = world_success_count(now)
    row_launches = None
    row_mass = None
    if world is not None:
        row_launches = max(0, world - len(flown))
        row_mass = round(row_launches * 2.8, 0)

    payload = {
        "source": "Launch Library 2 (thespacedevs.com)",
        "source_url": "https://ll.thespacedevs.com/2.2.0/swagger/",
        "year": YEAR,
        "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {
            "flown": len(flown),
            "success": sum(1 for l in flown if l["status"] == "success"),
            "failure": sum(1 for l in flown if l["status"] == "failure"),
            "partial": sum(1 for l in flown if l["status"] == "partial"),
            "falcon9": sum(1 for l in flown if l["vehicle"] == "falcon9"),
            "starship": sum(1 for l in flown if l["vehicle"] == "starship"),
            "falcon_heavy": sum(1 for l in flown if l["vehicle"] == "falcon-heavy"),
            "upcoming": len(upcoming),
        },
        "mass": {
            "spacex_t": sx_mass,
            "row_t": row_mass,
            "world_success_launches": world,
            "row_launches": row_launches,
            "note": "SpaceX tons are demo estimates from typical Starlink/FH payloads, not telemetry.",
        },
        "launches": launches,
    }

    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    OUT.write_text(text)
    print(
        f"wrote {OUT} flown={len(flown)} F9={payload['counts']['falcon9']} "
        f"SS={payload['counts']['starship']} FH={payload['counts']['falcon_heavy']} "
        f"upcoming={len(upcoming)} sx_t={sx_mass} row_t={row_mass}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
