# Krafton Grid AIDC DCIM — 요구사항 / 입력 조건 정리

> 본 문서는 지금까지 대화에서 요청·확정된 **시스템 조건, 메뉴, 인벤토리, 운영 요구**를 정리한 **단일 기준(prompt) 문서**입니다.  
> 코드·UI·다른 MD(README / VERSIONING) / Tech Spec 은 본 문서와 **항상 동기화**합니다.  
> **Source baseline:** uploaded Requirements (ChatGPT fork) · **Release:** <!-- RELEASE:START --> dcim-cursor-v3.1 <!-- RELEASE:END --> · **Version:** <!-- VERSION:START --> 3.1 <!-- VERSION:END -->  
> Package: `dcim-cursor-v3.1` · Brand: **Krafton Grid** · CI: `#000000` / `#F9423A`

---

## 1. 프로젝트 목표

- **100 MW AIDC** 캠퍼스용 **DCIM 시뮬레이션** (Facility + IT 통합)
- 모듈형: **첫 센터 20 MW → 전체 5×20 MW = 100 MW**
- 스택: **Python / FastAPI / Jinja / Highcharts / Redis**
- Mac에서 실행 (`./run_mac.sh` — 기존 프로세스 종료 후 **백그라운드** 기동)
- 데모 데이터 + Tech Spec + 벤더 API 프로브 + **Requirements MD 보기/다운로드** 포함

---

## 2. 브랜드 / UX

| 항목 | 내용 |
|------|------|
| 이름 | Krafton Grid |
| CI | Black `#000000` + graphite surfaces; Krafton Red `#F9423A`는 오류·critical 상태와 소량의 브랜드 포인트에 제한 |
| 사이드바 | Overview → **Main** 로 변경. 검정에 가까운 중립색과 은은한 붉은 기운만 적용 |
| Hero | 제거 |
| 사이드바 부제 | site-code / capacity subtitle 제거 |
| Main | **3열 × 3행** 카드: Facility(Power / Capacity / Cooling), AI(GPU / K8s / Storage), Cloud(AWS / GCP / NHN). 카드를 누르면 상세 메뉴로 이동. Cost 카드는 Main에서 제외 |
| Campus Aerial | Main 바로 아래 메뉴. 캠퍼스 **조감도** (`/campus-aerial`) — Phase 1 ACTIVE · Phase 2–5 FUTURE · Operation Room / Labs / Storage / Gate. 이미지 다운로드·전체 보기 제공 |
| Main 시각화 | 상단 KPI, mini gauge, progress bar, sparkline 및 성능 그래프를 제공. 일반 추이선은 청록·회색 계열 |
| Sidebar | 메뉴 그룹은 모두 펼쳐 표시. 주 메뉴는 굵은 흰색, 서브메뉴는 일반 두께의 흰색 |
| Surface | 전체 페이지 배경은 검정, 카드와 그래프 패널은 짙은 회색(graphite) |
| 상태 색상 | Info는 파랑, Warning은 황색, Error/Critical만 빨강. 정상 상태는 녹색·청록 계열 |

---

## 3. 사이트 용량 모델 (Facility)

| 항목 | 값 |
|------|-----|
| 모듈 블록 | **20 MW** |
| 모듈 수 | **5** (M1–M5) |
| 전체 envelope | **100 MW** |
| Phase-1 | M1 online (critical IT ~20 MW) |
| 토폴로지 | Modular / 2N power / N+1 cooling / liquid-first |
| Target PUE | **1.18** |

Facility 메뉴: **Overview / Power / Cooling / Capacity**

### Facility UX 패턴

- **Overview** `/facility` — Power · Cooling · Halls · Modules 요약 패널
- 행 클릭 → **상세 페이지** (`/facility/power/stage/{id}` · `/facility/cooling/stage/{id}` · `/facility/hall/{id}`)
- Power / Cooling / Capacity 는 full-list 페이지 (동일 컨셉)

---

## 4. IT 인프라 인벤토리 (확정)

| 도메인 | 조건 |
|--------|------|
| **GPU** | **NVIDIA B300 × 5,000** (HGX 8GPU/node → 625 nodes · ~40 racks) |
| **Storage** | **IBM Storage 100 PB** (초기 오타 IGM → **IBM** 로 정정) |
| **Ethernet** | **Arista** spine/leaf (데모: 7800R3×8, 7060X6×48) |
| **InfiniBand** | **NVIDIA** Quantum-2 QM9700 (데모 ×16) |
| **Kubernetes** | **Dell** 최근 서버 **×30** 에 K8s (3 CP + 27 workers, PowerEdge XE9680 클래스) |

IT Cluster 메뉴: **GPU Fleet / Storage / Network / Kubernetes**  

### IT Cluster UX 패턴 (공통)

- 각 도메인 **단일 overview** + 행 클릭 시 **새 상세 페이지** (팝업/모달 아님)
- Network · Storage · Kubernetes · GPU Fleet 동일 패턴

### Network (Arista-first) 상세 요구

- **단일 메뉴** `/network` — 한 화면에 Uplink · Top Talkers · Topology · Inventory **요약**
- 행/노드 클릭 → `/network/device/{id}` **상세 페이지** (장비 전체 interface · bps / errors / discards · 1h 차트)
- Full list → `/network/uplinks` · `/network/toptalkers` · `/network/inventory` (페이지)
- **Uplink** — leaf↔spine / IB uplink 대역폭 + in/out bps · util
- **Top Talkers** — window peak / avg · errors · discards (Redis 1h rings)
- **Topology** — spine–leaf + IB 맵
- **Inventory** — 장비 검색 · 선택 시 interface 상세 페이지
- **수집** — 1분 sample · 최근 1시간 Redis ring
- 코드: `app/sim/network/` · API: `/api/network/*` · Tech Spec §9b
- 구 `/network/topology` 는 `/network` 로 redirect

### Storage 상세 요구

- **단일 메뉴** `/storage` — Clusters · Top Talkers (IOPS) · capacity KPI
- 클러스터/볼륨 클릭 → `/storage/cluster/{id}` **상세 페이지** (volume IOPS · R/W · latency · throughput · queue · 1h chart)
- Full list → `/storage/toptalkers`
- **수집** — 1분 volume sample · Redis `…:st:hist:{volume}` 60 min ring
- API: `/api/storage/*`

### Kubernetes 상세 요구

- **단일 메뉴** `/kubernetes` — Hot nodes · inventory
- 노드 클릭 → `/kubernetes/node/{id}` **상세 페이지** (workloads · CPU/mem/pods 1h)
- API: `/api/kubernetes/*`

### GPU Fleet / GPU Monitoring 추가 요구

- Datadog GPU Monitoring 컨셉 반영 ([docs](https://docs.datadoghq.com/gpu_monitoring/))
- **Fleet Explorer** `/gpu-fleet` — funnel (total/allocated/active/effective/idle) · cost · OOTB monitors · recommendations
- Tabs: **Provisioning** (allocation over time · provider/device mix) · **Performance** (SM/sat/mem · fabric/thermal)
- Inventory: hosts + devices (SM · saturation · mem · PCIe · NVLink · power · temp · ECC · XID)
- Connected entities: K8s pods · processes · Slurm jobs
- Detail pages: `/gpu-fleet/device/{id}` · `/gpu-fleet/node/{id}` · `/gpu-fleet/pod/{id}`
- Slurm + CubeFlow 노드 리소스 유지

Operations: **Inventory / Rack View / Alerts / Slack·Webhooks / Alert Config**

### Observability (CoreWeave Observe™ 컨셉)

용어는 **monitoring → observability** 를 기본으로 사용한다.

- **Overview** `/observability` — solutions hub (Explore · Metrics · Logs · Telemetry Relay · Resource Usage · Mission Control · Alerts→Slack)
- **Explore** `/observability/explore` — metrics + logs + events
- **Metrics** `/observability/metrics` — PromQL-style (`POST /api/observability/metrics/query`)
- **Logs** `/observability/logs` — LogQL-style (`POST /api/observability/logs/query`)
- **Telemetry Relay** `/observability/telemetry-relay` — external HTTPS / OTLP forwarding
- **Resource Usage** `/observability/resource-usage` — compute / storage / network + cost signals
- **Mission Control Agent** `/observability/mission-control` — conversational investigation + evidence

### Dual audience (운영자 페이지 · 개발자 API)

- 운영자: HTML 페이지로 day-2 운영
- 내/외부 개발자: 동일 데이터를 JSON API로 소비
- **모든 페이지는 API 페어 필수** — 카탈로그 `/developers/api` · `GET /api/catalog`
- Facility/Cloud detail · Cost · Inventory · Racks 포함 누락 API 보완

### Alerts → Slack

- 모든 alarm 은 in-app + **Slack** (webhook 또는 OAuth) + optional generic webhook
- Integrations `/alerts/integrations` · Config `/alerts/config` (카테고리별 라우팅)
- Deliveries log `GET /api/alerts/deliveries` · inject 시 자동 fan-out

---

## 5. Cloud (API 연동 데모)

**메뉴·카드·Cost·Vendors 표시 순서는 고정:**

1. **AWS** — GPUaaS (EC2 / Capacity Blocks)  
2. **GCP** — Storage (GCS + PD)  
3. **NHN Cloud** — GPUaaS  

### Cloud UX 패턴

- **Overview** `/cloud` — AWS / GCP / NHN Top Talkers 요약
- Provider 페이지 `/cloud/aws` · `/cloud/gcp` · `/cloud/nhn`
- 행 클릭 → **상세 페이지** (`/cloud/aws/instance/{id}` · `/cloud/nhn/instance/{id}` · `/cloud/gcp/bucket/{id}` · `/cloud/gcp/disk/{id}`)
- Vendors & API 패널에서 샘플 프로브 (동일 순서)
- Live 메트릭은 Redis 시뮬레이터로 공급 (`/api/cloud`)

---

## 6. Cost (맨 아래 메뉴)

순서: **Summary / DC / Cloud**

### Summary (`/cost`)
- DC + Cloud live KPIs, MoM, 12-month YTD
- Stacked monthly trend (DC vs Cloud) + mix pie + monthly table

### DC (`/cost/dc`)
- 전기요금 (Power) / 세금 (Tax) / 관리비 (Management) / 인건비 (Labor)
- Live mix + **월별 라인별 stacked trend** + total monthly + detail table

### Cloud (`/cost/cloud`)
- **AWS / GCP / NHN** 순 월간 비용 (KRW)
- Live mix + **월별 provider stacked trend** + total monthly + detail table

---

## 7. GPU Platform

샘플 GPU 관리 제품(FRACTOS)에서 가져온 기능을 **일반 이름**으로 정리.  
메뉴 이름 **AI Factory 사용 금지** → **GPU Platform**.  
기존 10개 서브메뉴를 **3개 그룹**으로 묶음:

| 그룹 | 경로 | 포함 기능 |
|------|------|-----------|
| Overview | `/gpu-platform` | GPU 콘솔 · 프로젝트 요약 · 공지 · live util |
| Workloads | `/gpu-platform/workloads` | Jobs/Schedule · Partitioning · RCS · Custom Images |
| Ops | `/gpu-platform/ops` | Projects/Quota/RBAC · Nodes · Resource Monitor · Ecosystem · Usage Reports |

API: `GET /api/gpu-platform` (legacy alias `GET /api/fractos`).  
구 `/fractos/*` 경로는 위 그룹으로 redirect.

---

## 8. Platform

| 페이지 | 내용 |
|--------|------|
| Tech Spec | 스택, 코드맵, Redis, REST, IT/Cloud/Cost/GPU Platform 문서 |
| Vendors & API | Facility + IT + Cloud(**AWS→GCP→NHN**) 벤더 카탈로그 / sample probe |
| Simulation | 시나리오 모드, alert inject, Redis dump |
| **Requirements (본 MD)** | 입력 조건 정리 · 화면 보기 · 다운로드 — **변경 시 본 파일 필수 갱신** |

---

## 9. 전체 메뉴 구조

```
Main
Campus Aerial … 조감도 (100 MW campus master plan)
Facility ………… Power / Cooling / Capacity
IT Cluster …… GPU Monitoring / Storage / Network / Kubernetes
GPU Platform … Overview / Workloads / Ops
Cloud …………… AWS GPUaaS / GCP Storage / NHN GPUaaS
Observability … Overview / Explore / Metrics / Logs / Telemetry Relay / Resource Usage / Mission Control
Operations …… Inventory / Rack View / Alerts / Slack·Webhooks / Alert Config
Developers …… API Catalog (page ↔ API)
Platform ……… Tech Spec / Vendors & API / Simulation / Requirements
Cost …………… Summary / DC / Cloud
```

---

## 9b. 코드 모듈 구조 (상세화용)

상세 메뉴(Network 등)를 계속 늘리려면 **도메인 패키지** 단위로 나눈다.

```
app/
  main.py                 # FastAPI entry only
  web/
    nav.py · deps.py
    routers/              # 페이지·API 를 도메인별 APIRouter
  sim/
    engine/               # tick · seed · bundles · network_store mixins
    facility/             # halls · vendors
    it/                   # gpu · storage · k8s · racks · inventory
    network/              # devices · interfaces · topology · metrics · ranking
    cloud/                # catalog · cost · slurm · live
    gpu_platform/         # partitions · workloads · tenancy · ops_catalog
    observability/        # catalog · PromQL/LogQL · relay · Slack alerts · agent · usage
```

규칙:
- **새 Network 화면/API** → `app/sim/network/` + `app/web/routers/network.py` (+ `api_network.py`)
- **새 Facility 메트릭** → `app/sim/facility/` + `routers/facility.py`
- 엔진 Redis 쓰기 → `app/sim/engine/` mixin (collector 는 도메인 패키지 함수 호출)
- 구 경로 `it_fabric.py` / `network_fabric.py` 등은 **shim** (재export only)

---

## 10. 기술 스택

| Layer | Choice |
|-------|--------|
| Language | Python 3 |
| Web | FastAPI + Uvicorn + Jinja2 |
| Charts | Highcharts 11 (**local** `app/static/vendor/highcharts/`) |
| State | Redis (`dcim:aidc100:cursor:*`) |
| Mac run | `./run_mac.sh` (기존 프로세스 종료 후 백그라운드 실행 — **Cursor 기본 :8002**) |
| Packaging | `dcim-cursor-vX.Y` release folder |

### Agent별 로컬 포트 (필수 · 충돌 방지)

여러 AI 에이전트가 같은 Mac에서 돌릴 때 **포트 고정**:

| Agent | Port | URL |
|-------|------|-----|
| **ChatGPT** | **8001** | http://127.0.0.1:8001 |
| **Cursor** (본 레포 기본) | **8002** | http://127.0.0.1:8002 |
| **Claude** | **8003** | http://127.0.0.1:8003 |

- 본 프로젝트(`dcim-cursor`) 기본값: `APP_PORT=8002` (`app/config.py`, `run_mac.sh`)
- 다른 에이전트 패키지는 각자 `APP_PORT` 또는 런처 기본값을 위 표에 맞출 것
- 다른 에이전트와 포트가 겹치지 않도록 본 앱은 **8002** 사용

### 버전 규칙

- 형식 **`X.Y`**, Y는 **한 자리(0–9)**  
- `0.9` 다음은 **`1.0`** (절대 `0.10` 금지). `1.9` → `2.0` 동일  
- `scripts/bump_version.py` 가 wrap 강제

### 주요 API

- `GET /api/live` · `/api/it` · `/api/cloud` · `/api/cost` · `/api/gpu-platform`
- `GET /api/series/{metric}` · `/api/vendors` · `/api/vendor/{id}/sample`
- `POST /api/sim/mode` · `/api/sim/alert`
- `GET /platform/requirements.md` — 본 문서 다운로드

---

## 11. 버전 / 배포 메모

- 작업 복사본은 `/Users/logan/code/dcim-cursor-vX.Y` 에 둡니다.
- 버전 갱신 시 `scripts/bump_version.py` 가 릴리스 이름과 문서를 동기화합니다.

```bash
cd /Users/logan/code/dcim-cursor-vX.Y && ./run_mac.sh
```

### 문서 동기화 규칙 (필수)

기능·메뉴·순서·이름을 바꾸면 **아래를 함께 갱신**:

1. `docs/REQUIREMENTS.md` ← **이 파일 (prompt / 입력 조건)** — 헤더에 **Release `dcim-cursor-vX.Y` + Version** 표기  
2. `README.md` · `VERSIONING.md` · `app/static/brand/README.md` (버전명 동일)  
3. Tech Spec 화면 (`app/templates/tech_spec.html`)  
4. 내비 / Main / Cost / Vendors 실제 UI  

`scripts/bump_version.py` 가 위 MD들의 `<!-- VERSION -->` / `<!-- RELEASE -->` / `` `dcim-cursor-vX.Y` `` 를 일괄 갱신합니다.

---

## 12. 변경 이력 (입력 기준)

1. AIDC 100MW DCIM (Python/Highcharts/Redis), modular 20→100, Krafton CI  
2. Platform 서브메뉴 (Tech Spec / Vendors / Simulation), hero·subtitle 제거  
3. Facility+IT 통합: B300×5000, storage, Arista, IB, Dell×30 K8s, inventory, rack  
4. Storage 벤더 **IGM → IBM** 정정  
5. Mac 전용 `run_mac.sh` bg + Overview→Main + IT 카드 혼합  
6. Main 클릭 이동 · Slurm/CubeFlow · Cloud · Cost DC/Cloud  
7. GPU 관리 기능 (샘플 FRACTOS 참고) → 이후 GPU Platform으로 일반화  
8. **Platform Requirements MD 보기/다운로드** (본 문서)  
9. AI Factory → **GPU Platform** · 서브메뉴 10개 → Overview / Workloads / Ops 3그룹  
10. Main 카드 **그래픽** (progress / gauge / sparkline) — 텍스트만 구성 금지  
11. Cloud 표시 순서 고정: **AWS → GCP → NHN** (내비·Main·Cost·Vendors·문서 전부)  
12. 버전 체계 `X.Y` 단일 자리 minor · `0.9`→`1.0` wrap
13. Main을 Facility / AI / Cloud 3×3 카드로 정리하고 Cost 항목 제거 · 검정 캔버스와 graphite 카드 적용
14. Sidebar 붉은 톤 축소 · 흰색 굵은 주 메뉴와 일반 두께의 흰 서브메뉴 적용
15. 일반 대시보드 그래프 색을 청록·회색으로 변경; Error / Critical 상태와 critical 임계선에만 빨강 사용
16. Agent 로컬 포트 고정: **ChatGPT 8001 / Cursor 8002 / Claude 8003**
17. Cursor 패키지 동기화: `dcim-cursor` · port **8002** · Redis `dcim:aidc100:cursor:*`  
18. **Campus Aerial (조감도)** 메뉴 — 100 MW campus master plan 이미지 보기/다운로드

---

*Generated for Krafton Grid AIDC DCIM simulation · view in Platform → Requirements*
