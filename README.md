# Krafton Grid · AIDC DCIM — Claude edition

Release <!-- RELEASE:START --> grid-claude-v2.0 <!-- RELEASE:END --> · Version <!-- VERSION:START --> 2.0 <!-- VERSION:END --> · port **8003**

A digital twin and operations console for the Krafton Grid 100 MW AI data center campus (5 × 20 MW modules, M1 live).
Facility (2N power, N+1 liquid-first cooling), 5,000 NVIDIA B300 GPUs under Slurm + CubeFlow, IBM Storage Scale 100 PB,
Arista + Quantum-2 fabrics, Dell Kubernetes, AWS → GCP → NHN cloud, KEPCO TOU cost and FY budget — computed every 2 s
from physical and operational models, streamed live to every page, and queryable by API, PromQL, LogQL or Claude.

The canonical spec is [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) (also at **Platform → Requirements**).

## Run (macOS)

```bash
cd /Users/logan/Code/grid-claude-v2.0 && ./run_mac.sh
```

Open http://127.0.0.1:8003. The launcher creates `.venv`, installs `requirements.txt`, makes sure Redis is running, then starts
two background processes:

```
collector  (python -m app.collector)  ──write──▶  Redis dcim:aidc100:claude:*  ◀──read──  web  (uvicorn app.main:app)
```

The collector gathers state (today: the physics simulator as demo data), aggregates it into one read model per page and per
detail entity, and publishes everything to Redis every tick. The web process reads **only** Redis — pages, JSON APIs, the SSE
stream and the Mission Control agent — and sends every action (job submit, drain, scenario, alert ack, budget approval …) to the
collector over a Redis command bus. Without Redis the web process runs the collector in-process on an in-memory store; the read
path is identical. Why and how: [docs/PERFORMANCE.md](docs/PERFORMANCE.md).

| Command | |
|---|---|
| `./run_mac.sh` | start / restart both processes in the background |
| `./run_mac.sh web` | restart only the web process — the simulation, alerts and budget state keep running |
| `./run_mac.sh status` | pids, health, collector heartbeat |
| `./run_mac.sh logs` | follow `.run/uvicorn.log` and `.run/collector.log` |
| `./run_mac.sh stop` | stop both |

Python changes need a restart (web-only changes: `./run_mac.sh web`); template and static changes are picked up on reload.

## Configuration

| Variable | Default | |
|---|---|---|
| `APP_PORT` | `8003` | ChatGPT 8001 · Cursor 8002 · **Claude 8003** |
| `REDIS_URL` / `REDIS_PREFIX` | `redis://127.0.0.1:6379/0` / `dcim:aidc100:claude` | the read-model store |
| `GRID_STORE` | `auto` | `redis` · `memory` (no Redis) |
| `GRID_COLLECTOR` | `auto` | use a running collector, else start one inside the web process · `embedded` · `external` |
| `ENTITY_EVERY_TICKS` / `HEAVY_EVERY_TICKS` | `5` / `3` | publish cadence of detail entities / large list views |
| `ANTHROPIC_API_KEY` | — | enables Claude in Mission Control (otherwise the built-in analyst answers) |
| `MISSION_CONTROL_MODEL` / `MISSION_CONTROL_MODE` | `claude-opus-5-5` / `auto` | `auto` · `claude` · `offline` |
| `ALERTS_LIVE_DELIVERY` + `SLACK_WEBHOOK_URL` | off | alerts are rendered and logged as dry-run until both are set |
| `AUTH_ENABLED` + `AUTH_USERNAME` / `AUTH_PASSWORD` | off | optional session login for shared deployments |
| `SIM_TICK_SEC` / `SIM_SEED` | `2.0` / `20260930` | simulation cadence and seed |

## Menu

```
Main · Campus Aerial
Facility ………… Overview / Power / Cooling / Capacity / Energy & ESG
IT Cluster …… GPU Monitoring / Storage / Network / Kubernetes
GPU Platform … Overview / Workloads / Ops
Cloud …………… Overview / AWS GPUaaS / GCP Storage / NHN GPUaaS
Observability … Overview / Explore / Metrics / Logs / Telemetry Relay / Resource Usage / Mission Control
Operations …… Inventory / Rack View / Alerts / Slack·Webhooks / Alert Config
Developers …… API Catalog
Platform ……… Tech Spec / Vendors & API / Simulation / Requirements
Cost …………… Summary / DC / Cloud / Budget
```

Every page has a JSON twin — see **Developers → API Catalog** or `GET /api/catalog`; OpenAPI at `/docs`.

## What to try first

1. **Platform → Simulation** → start *CDU pump failure · Row A2*. Watch row A2 coolant climb, the spare CDU take over,
   GPUs throttle, and four alerts correlate into one incident on **Operations → Alerts**.
2. **Observability → Mission Control** → ask “지금 캠퍼스에 문제 있어?” while the scenario runs.
3. **GPU Platform** → submit a 64-node pretrain job and follow it into the queue, onto nodes, or out to AWS.
4. **Cost → Budget** → raise a 예산 증액 request for an item that is forecast over budget and approve it through the chain.
5. Press **⌘K** anywhere and type a rack (`R12`), node (`kg-r07-n03`) or device (`CDU-B3`).

## Layout

```
app/collector/  collector process — lease, tick → publish, command bus handlers
app/readmodel/  aggregation — collected state → one dict per page / detail entity (runs in the collector only)
app/store.py    Redis contract (key layout, lease, command bus) + in-memory fallback
app/sim/        demo collector source — topology, fleet physics + scheduler, facility, IT infra, cloud, cost/budget,
                alerts/incidents, scenarios, TSDB + PromQL/LogQL, engine
app/web/        read path (data.py), Mission Control agent, nav, templating, routers per domain
app/templates   Jinja pages · app/static  grid.css · grid.js (one SSE per browser) · charts.js · heat.js · local Highcharts 13
docs/           REQUIREMENTS.md (canonical) · PERFORMANCE.md (load-time analysis & data path)
scripts/        bump_version.py · smoke.py
tests/          pytest suite (incl. an architecture guard: the web tier must read only the store)
```

## Deploying

**EC2 / any Ubuntu host:** `deploy/setup_ec2.sh` installs Redis, the collector and web as systemd services and nginx in front —
see [deploy/README.md](deploy/README.md). Re-running it deploys the latest `main`.

**Render (PaaS):**

Start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (one worker). With `REDIS_URL` set, the web process takes the
collector lease and publishes into Redis itself (~15 MB of keys, fits a 25 MB plan); if Redis is full it falls back to the
in-memory store and says so in `/healthz` (`store_note`). Keep `AUTH_ENABLED=1` on public URLs. Details: docs/PERFORMANCE.md §9.

## Tests

```bash
cd /Users/logan/Code/grid-claude-v2.0 && .venv/bin/python -m pytest -q
```

## Versioning

`X.Y` with a single-digit minor (1.9 → 2.0). See [VERSIONING.md](VERSIONING.md).
