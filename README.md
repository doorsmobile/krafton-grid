# Krafton Grid — 100 MW AIDC DCIM Simulation

**Package:** `dcim-cursor-v3.1` · local path `/Users/logan/code/dcim-cursor-v3.1`  
**Release:** <!-- RELEASE:START --> dcim-cursor-v3.1 <!-- RELEASE:END -->  
**Version:** <!-- VERSION:START --> 3.1 <!-- VERSION:END -->

Python / Highcharts / Redis based **AI Data Center Infrastructure Management** simulator for a modular Krafton Grid campus (first center **20 MW**, full site **100 MW**).

## Brand

- Name: **Krafton Grid**
- CI: Krafton black `#000000` + brand red `#F9423A`
- Marks: `app/static/brand/` (SVG mark, wordmark, icon, favicons)

See `VERSIONING.md` for bump / sync workflow.

## What you get

### Campus Aerial
- Bird's-eye **campus master plan** under Main: Phase 1 active · Phases 2–5 future · Operation Room / Labs / Storage
- Download PNG · open full size

### Facility
- **Overview** `/facility` — Power · Cooling · Halls · Modules panels; click → detail pages
- Power / Cooling / Capacity full-list pages under Facility
- Live **Main** dashboard: **3×3** Facility · AI · Cloud cards → overview pages
- Dark black canvas · graphite cards · teal/gray charts (red = critical only)

### IT Cluster (Facility + IT unified)
- **GPU Monitoring** — Datadog-style Fleet Explorer (funnel · cost · OOTB monitors · provisioning/performance · device detail)
- **Storage** — IBM Storage **100 PB** · clusters + Top Talkers (IOPS) + cluster **detail pages**
- **Kubernetes** — Dell PowerEdge × **30** · hot nodes + node **detail pages**
- Shared UX: overview panels → click opens a **new page** (not popup/modal)

### Network (Arista-first)
- Single **IT Cluster → Network** overview: uplink · talkers · topology · inventory
- Click row/node → `/network/device/{id}` detail page (interface bps / errors / discards + 1h chart)
- Package: `app/sim/network/` · routes: `app/web/routers/network.py`

### GPU Platform
- **Overview** — console, projects, notices, live GPU util
- **Workloads** — jobs/schedule · partitioning · RCS · custom images
- **Ops** — projects/quota · nodes · resource monitor · ecosystem · usage reports

### Cloud
- **Overview** `/cloud` — AWS / GCP / NHN Top Talkers; click → instance/bucket/disk detail pages
- Order fixed: **AWS** GPUaaS → **GCP** Storage → **NHN** GPUaaS (API demo catalogs)

### Cost
- **Summary** — DC+Cloud KPIs, MoM, YTD, 12-month stacked trend
- **DC** — 전기요금 / 세금 / 관리비 / 인건비 + monthly line charts
- **Cloud** — AWS / GCP / NHN + monthly provider charts

### Observability
- Hub inspired by CoreWeave Observe™: **Explore · Metrics (PromQL) · Logs (LogQL) · Telemetry Relay · Resource Usage · Mission Control Agent**
- Operators use pages; developers consume the same telemetry via JSON APIs
- **API Catalog** `/developers/api` — every UI page mapped to an API (`GET /api/catalog`)

### Operations & Platform
- Unified **Inventory** + **Rack View** floor map
- Alarm console with **Slack** webhook/OAuth + generic webhook fan-out (`/alerts/integrations` · `/alerts/config`)
- **Vendors & API** (facility + IT + AWS → GCP → NHN)
- **Tech Spec** documentation page
- **Requirements** (`docs/REQUIREMENTS.md`) — canonical input/prompt spec, view + download
- **Simulation** console: modes, alert injection, Redis JSON export

## Stack

| Layer | Tech |
|-------|------|
| API / UI | FastAPI + Jinja2 |
| Charts | Highcharts (local vendor) |
| State | Redis |
| Sim engine | Background Python thread writing live + series keys |

## Run locally (Mac)

자세한 절차: [`MAC_INSTALL.md`](MAC_INSTALL.md)

```bash
cd /Users/logan/code/dcim-cursor-vX.Y
./run_mac.sh          # start/restart on :8002
./run_mac.sh status    # health check
./run_mac.sh stop      # stop
```

Open [http://127.0.0.1:8002](http://127.0.0.1:8002). Logs: `.run/uvicorn.log` · PID: `.run/uvicorn.pid`

Agent sync ships a tarball + download URL via `bash scripts/sync_local.sh`.

### Agent ports (Mac 동시 실행)

| Agent | Port |
|-------|------|
| ChatGPT | **8001** |
| Cursor (this repo default) | **8002** |
| Claude | **8003** |

### Manual / cloud

```bash
redis-server --daemonize yes
python3 -m pip install -r requirements.txt
python3 -m app.main
```

### Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis connection |
| `APP_PORT` | `8002` | HTTP port (Cursor). ChatGPT=8001, Claude=8003 |
| `SIM_INTERVAL_SEC` | `2.0` | Tick interval |
| `AUTH_PROVIDER` | `local` | Auth backend (`local` now · `krafton` reserved for SSO) |
| `AUTH_USERNAME` | `krafton` | Local demo ID |
| `AUTH_PASSWORD` | `krafton-grid` | Local demo password |
| `SESSION_SECRET` | (dev default) | Cookie signing secret — **set on Render** |
| `SESSION_HTTPS_ONLY` | `0` | Set `1` on HTTPS (Render) |

Login: `/login` · Logout: `/logout` · module: `app/auth/` (swap provider for Krafton account system later).

## Useful APIs

- `GET /api/catalog` — full page ↔ API map (developers)
- `GET /api/observability` — observability hub JSON
- `POST /api/observability/metrics/query` — PromQL-style
- `POST /api/observability/logs/query` — LogQL-style
- `GET /api/observability/relay` · `/usage` · `POST /api/observability/agent`
- `GET /api/alerts` · `/api/alerts/integrations` · `/api/alerts/config` · `/api/alerts/deliveries`
- `GET /api/live` — current snapshot (facility + IT metrics)
- `GET /api/facility` · `/api/facility/power` · `/cooling` · `/capacity` · stage/hall detail
- `GET /api/it` — IT fabric inventory + live slice
- `GET /api/cost` · `/api/cost/dc` · `/api/cost/cloud`
- `GET /api/cloud` · `/api/cloud/aws|gcp|nhn` (+ instance/bucket/disk detail)
- `GET /api/gpu-platform` — GPU Platform bundle (`/api/fractos` alias)
- `GET /api/series/{metric}` — chart series
- `GET /api/vendors` — vendor catalog + health
- `GET /api/vendor/{id}/sample` — simulated vendor API probe
- `POST /api/sim/mode` — `{ "mode": "normal|stress|maintenance|failover" }`
- `GET /api/sim/export.json` — full simulation dump
- `GET /platform/requirements.md` — download Requirements prompt MD

## Site model (summary)

- Full site / investment envelope: **100 MW** (5 × **20 MW** modular centers)
- First modular center (**M1**): **20 MW** online
- M2 commissioning · M3–M5 planned
- Topology: **Modular blocks / 2N power / N+1 cooling / liquid-first**
- Target PUE: **1.18**
