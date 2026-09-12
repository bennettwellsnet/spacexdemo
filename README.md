# SpaceX 2026 live launch board

Live 2026 SpaceX launch counter for [bennettwells.net/spacexdemo](https://bennettwells.net/spacexdemo).

Launch rows come from [Launch Library 2](https://thespacedevs.com). A GitHub Action refreshes `launches.json` once a day. The pages are static HTML plus `board.js`.

## Local

```bash
python3 scripts/fetch_launches.py
python3 -m http.server 8080
# open http://127.0.0.1:8080/
```

## Data

- `scripts/fetch_launches.py` — paginates LL2 for SpaceX 2026 (including suborbital Starship)
- `launches.json` — fetched snapshot used by the site
- Payload mass uses Launch Library 2 `payload_flights` when a mass is published; Starlink and other gaps still use class estimates (not telemetry)
- SpaceXAI brief: set repo secret `XAI_API_KEY` (from [console.x.ai](https://console.x.ai)). The refresh Action writes a 2–3 sentence snapshot brief into `launches.json`. Local: `XAI_API_KEY=... python3 scripts/fetch_launches.py`

## Deploy

Pushes to `main` copy `*.html`, `board.js`, and `launches.json` into `bennettwellsnet/bennettwells-website` via `.github/workflows/sync-to-website.yml`.
