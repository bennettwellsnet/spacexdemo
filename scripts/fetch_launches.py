#!/usr/bin/env python3
"""Fetch 2026 SpaceX launches from Launch Library 2 and write launches.json."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

YEAR = 2026
API = "https://ll.thespacedevs.com/2.2.0/launch/"
PAYLOAD_FLIGHTS = "https://ll.thespacedevs.com/2.3.0/payload_flights/"
XAI_RESPONSES = "https://api.x.ai/v1/responses"
BRIEF_MODEL = "grok-4.6"
UA = "bennettwells-spacexdemo/1.0 (+https://bennettwells.net/spacexdemo)"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "launches.json"
ROW_T_PER_LAUNCH = 2.8

FLOWN = {"Success": "success", "Failure": "failure", "Partial Failure": "partial"}


def get_json(url: str, retries: int = 6) -> dict:
    last = None
    for i in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                raise
            retry_after = e.headers.get("Retry-After") if e.headers else None
            try:
                wait = int(retry_after) if retry_after else 45 * (i + 1)
            except ValueError:
                wait = 45 * (i + 1)
            wait = min(max(wait, 8), 180)
            print(f"HTTP {e.code} — retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
        except TimeoutError as e:
            last = e
            time.sleep(5 * (i + 1))
    raise last  # type: ignore[misc]


def paginate_url(url: str) -> list[dict]:
    rows: list[dict] = []
    while url:
        data = get_json(url)
        rows.extend(data.get("results") or [])
        url = data.get("next")
        print(f"fetched {len(rows)}/{data.get('count')}", file=sys.stderr)
    return rows


def paginate(params: str) -> list[dict]:
    return paginate_url(f"{API}?{params}&limit=100&mode=list&ordering=net")


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


def _float(val: object) -> float | None:
    if val is None or val == "":
        return None
    try:
        n = float(val)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return n


def payload_flight_kg(pf: dict) -> float | None:
    payload = pf.get("payload")
    mass = _float(payload.get("mass") if isinstance(payload, dict) else None)
    if mass is None:
        return None
    amount = _float(pf.get("amount")) or 1.0
    return mass * amount


def launch_ref(obj: object) -> dict:
    if isinstance(obj, dict):
        return obj
    return {}


def lsp_name(launch: dict) -> str:
    lsp = launch.get("launch_service_provider")
    if isinstance(lsp, dict):
        return (lsp.get("name") or lsp.get("abbrev") or "").strip()
    return (launch.get("lsp_name") or "").strip()


def net_year(net: str | None) -> int | None:
    if not net or len(net) < 4 or not net[:4].isdigit():
        return None
    return int(net[:4])


def is_flown_launch(launch: dict, now: datetime) -> bool:
    status = launch.get("status") or {}
    abbrev = status.get("abbrev") if isinstance(status, dict) else None
    if abbrev in FLOWN:
        return True
    if abbrev:
        return False
    net = parse_net(launch.get("net"))
    return bool(net and net <= now)


def parse_net(net: str | None) -> datetime | None:
    if not net:
        return None
    try:
        return datetime.fromisoformat(net.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_payload_masses(now: datetime) -> dict[str, dict]:
    """Launch id -> {kg, lsp, flown} from LL2 2.3 payload flights (sparse catalog)."""
    rows = paginate_url(f"{PAYLOAD_FLIGHTS}?limit=100&mode=detailed")
    by_id: dict[str, dict] = {}
    for pf in rows:
        launch = launch_ref(pf.get("launch"))
        lid = launch.get("id")
        if not lid or net_year(launch.get("net")) != YEAR:
            continue
        kg = payload_flight_kg(pf)
        if kg is None:
            continue
        slot = by_id.setdefault(
            lid,
            {"kg": 0.0, "lsp": lsp_name(launch), "flown": is_flown_launch(launch, now)},
        )
        slot["kg"] += kg
        if not slot["lsp"]:
            slot["lsp"] = lsp_name(launch)
    print(f"payload flights with mass in {YEAR}: {len(by_id)}", file=sys.stderr)
    return by_id


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


def normalize(row: dict, mass_by_id: dict[str, dict]) -> dict:
    name = row.get("name") or ""
    vehicle, vehicle_label = classify_vehicle(name)
    mission = mission_name(name, row.get("mission"))
    abbrev = ((row.get("status") or {}).get("abbrev")) or "TBD"
    lid = row.get("id")
    api = mass_by_id.get(lid) if lid else None
    if api and api.get("kg"):
        payload_t = round(api["kg"] / 1000.0, 2)
        source = "api"
    else:
        payload_t = estimate_payload_t(mission, vehicle)
        source = "estimate"
    return {
        "id": lid,
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
        "payload_t": payload_t,
        "payload_source": source,
        "image": row.get("image"),
    }


def line_for(launch: dict) -> str:
    bits = [
        launch.get("name") or "Unknown",
        launch.get("net") or "NET TBA",
        launch.get("vehicle_label") or "",
        launch.get("pad") or "",
        launch.get("status_label") or launch.get("status") or "",
    ]
    return " · ".join(b for b in bits if b)


def previous_brief() -> dict | None:
    if not OUT.exists():
        return None
    try:
        old = json.loads(OUT.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    brief = old.get("brief")
    if isinstance(brief, dict) and (brief.get("text") or "").strip():
        return brief
    return None


def response_text(data: dict) -> str:
    chunks: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                text = (part.get("text") or "").strip()
                if text:
                    chunks.append(text)
    return "\n".join(chunks).strip()


def generate_brief(flown: list[dict], upcoming: list[dict], counts: dict, now: datetime) -> dict | None:
    key = (os.environ.get("XAI_API_KEY") or "").strip()
    if not key:
        print("XAI_API_KEY not set — skipping SpaceXAI brief", file=sys.stderr)
        return None
    last = flown[-1] if flown else None
    nxt = []
    for launch in upcoming:
        net = parse_net(launch.get("net"))
        if not net or net >= now:
            nxt.append(launch)
        if len(nxt) >= 3:
            break
    facts = [
        f"As of {now.strftime('%Y-%m-%dT%H:%MZ')} UTC.",
        (
            f"SpaceX 2026 YTD: {counts.get('flown', 0)} flown "
            f"({counts.get('falcon9', 0)} Falcon 9, {counts.get('starship', 0)} Starship, "
            f"{counts.get('falcon_heavy', 0)} Falcon Heavy); "
            f"{counts.get('upcoming', 0)} still listed as upcoming."
        ),
    ]
    if last:
        facts.append("Last flown: " + line_for(last))
    if nxt:
        facts.append("Next: " + line_for(nxt[0]))
        if len(nxt) > 1:
            facts.append("Then: " + "; ".join(line_for(l) for l in nxt[1:]))
    prompt = (
        "Write a 2–3 sentence launch-board brief for a public demo page. "
        "Use ONLY the facts below. Do not add missions, dates, pads, or outcomes "
        "that are not listed. Neutral tone. No hype. Not an official SpaceX statement.\n\n"
        + "\n".join(facts)
    )
    body = {
        "model": BRIEF_MODEL,
        "input": prompt,
        "store": False,
        "max_output_tokens": 400,
        "temperature": 0.3,
        "search_parameters": {"mode": "off"},
    }
    req = urllib.request.Request(
        XAI_RESPONSES,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.load(resp)
    except Exception as e:
        print(f"SpaceXAI brief failed: {e}", file=sys.stderr)
        return None
    text = response_text(data)
    if not text:
        print("SpaceXAI brief empty", file=sys.stderr)
        return None
    return {
        "text": text,
        "model": data.get("model") or BRIEF_MODEL,
        "provider": "SpaceXAI",
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    mass_by_id = fetch_payload_masses(now)
    rows = paginate(
        f"lsp__name=SpaceX&net__gte={YEAR}-01-01T00:00:00Z"
        f"&net__lte={YEAR}-12-31T23:59:59Z&include_suborbital=true"
    )
    launches = [normalize(r, mass_by_id) for r in rows]
    launches.sort(key=lambda x: x.get("net") or "")

    flown = [l for l in launches if l["status"] in ("success", "failure", "partial")]
    upcoming = [l for l in launches if l["status"] == "upcoming"]
    sx_api = [l for l in flown if l.get("payload_source") == "api"]
    sx_est = [l for l in flown if l.get("payload_source") != "api"]
    sx_api_t = round(sum(l["payload_t"] for l in sx_api), 1)
    sx_est_t = round(sum(l["payload_t"] for l in sx_est), 1)
    sx_mass = round(sx_api_t + sx_est_t, 1)

    world = world_success_count(now)
    row_launches = None
    row_mass = None
    row_api_t = 0.0
    row_api_n = 0
    sx_ids = {l["id"] for l in launches}
    for lid, info in mass_by_id.items():
        if lid in sx_ids or not info.get("flown"):
            continue
        row_api_t += info["kg"] / 1000.0
        row_api_n += 1
    row_api_t = round(row_api_t, 1)
    if world is not None:
        row_launches = max(0, world - len(flown))
        row_est_n = max(0, row_launches - row_api_n)
        row_mass = round(row_api_t + row_est_n * ROW_T_PER_LAUNCH, 0)

    payload = {
        "source": "Launch Library 2 (thespacedevs.com)",
        "source_url": "https://ll.thespacedevs.com/2.3.0/",
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
            "spacex_api_t": sx_api_t,
            "spacex_estimate_t": sx_est_t,
            "spacex_api_launches": len(sx_api),
            "spacex_estimate_launches": len(sx_est),
            "row_api_t": row_api_t,
            "row_api_launches": row_api_n,
            "note": (
                f"SpaceX tons use Launch Library 2 payload mass for {len(sx_api)} flown "
                f"mission(s) ({sx_api_t} t); the other {len(sx_est)} use class estimates "
                f"(Starlink ~15.5–16.7 t). Rest-of-world mixes API payload mass "
                f"({row_api_t} t on {row_api_n} flight(s)) with ~{ROW_T_PER_LAUNCH} t "
                "per remaining orbital success. Not official telemetry."
            ),
        },
        "launches": launches,
    }
    brief = generate_brief(flown, upcoming, payload["counts"], now) or previous_brief()
    if brief:
        payload["brief"] = brief

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
