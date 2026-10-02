# Krafton Grid AIDC DCIM — 요구사항 / 입력 조건 정리 (Claude edition)

> 본 문서는 지금까지 요청·확정된 **시스템 조건, 메뉴, 인벤토리, 운영 요구**를 정리한 **단일 기준(prompt) 문서**입니다.
> 코드·UI·다른 MD(README / VERSIONING) / Tech Spec 은 본 문서와 **항상 동기화**합니다.
> **Source baseline:** 공유 요구사항 (`dcim-cursor-v3.1` docs/REQUIREMENTS.md) + Claude 추가 기능 · **Release:** <!-- RELEASE:START --> grid-claude-v2.0 <!-- RELEASE:END --> · **Version:** <!-- VERSION:START --> 2.0 <!-- VERSION:END -->
> Package: `grid-claude-v2.0` · Brand: **Krafton Grid** · CI: `#000000` / `#F9423A`

---

## 1. 프로젝트 목표

- **100 MW AIDC** 캠퍼스용 **DCIM 디지털 트윈** (Facility + IT + Cloud + Cost 통합)
- 모듈형: **첫 센터 M1 20 MW → 전체 5 × 20 MW = 100 MW**
- 스택: **Python / FastAPI / Jinja / Highcharts / Redis** (+ numpy 물리 시뮬레이션, SSE 실시간 스트림)
- Mac 실행: `./run_mac.sh` (기존 프로세스 종료 후 **백그라운드** 기동, `start | stop | status | logs`)
- 데모 데이터는 “그럴듯한 난수”가 아니라 **물리·운영 모델에서 계산**: 전력 → 발열 → 냉각 → GPU 온도 → 스로틀 → 잡 속도 → 알림 → 비용
- Tech Spec + 벤더 API 프로브 + **Requirements MD 보기/다운로드** 포함

---

## 2. 브랜드 / UX

| 항목 | 내용 |
|------|------|
| 이름 | Krafton Grid |
| CI | Black `#000000` + graphite surfaces; Krafton Red `#F9423A`는 오류·critical 상태와 소량의 브랜드 포인트에 한정 |
| Main | **3열 × 3행** 카드: Facility(Power / Capacity / Cooling), AI(GPU / K8s / Storage), Cloud(AWS / GCP / NHN). 카드 클릭 → 상세 메뉴. **Cost 카드는 Main에서 제외** |
| Campus Aerial | Main 바로 아래. 캠퍼스 조감도 + **라이브 핫스팟** (Phase 1 ACTIVE · Phase 2–5 · NOC · Labs · Storage · Gate) + build-out 타임라인 |
| Main 시각화 | 상단 KPI, mini gauge, progress bar, sparkline, 성능 그래프. 일반 추이선은 청록·회색 계열 |
| Sidebar | 메뉴 그룹 **기본 접힘** — 현재 페이지가 속한 그룹만 펼침, 그룹 머리글 클릭 또는 상단 **펼치기/접기** 버튼으로 전체 토글, 선택 상태 기억. 주 메뉴 굵은 흰색, 서브메뉴 일반 두께 흰색. 로고 아래에는 버전만 표시(`v2.0`) |
| Surface | 페이지 배경 검정, 카드·그래프 패널 짙은 회색(graphite) |
| 상태 색상 | Info 파랑 · Warning 황색 · Error/Critical만 빨강 · 정상은 녹색/청록 |
| Hero / 부제 | 제거 (site-code / capacity subtitle 없음) |
| 공통 | ⌘K / `/` 커맨드 팔레트, 실시간 토스트(신규 알림), 모든 표 정렬·필터·CSV, 행 클릭 → 상세 페이지(모달 아님) |

---

## 3. 사이트 용량 모델 (Facility)

| 항목 | 값 |
|------|-----|
| 모듈 블록 | **20 MW** critical IT |
| 모듈 수 | **5** (M1 live 2026-03 · M2 construction RFS 2027-06 · M3 design · M4/M5 planned) |
| 전체 envelope | **100 MW** |
| Phase-1 | M1 online — Hall A/B (GPU, liquid) · Hall C (storage/network/K8s, air) · Hall D (reserved) |
| 토폴로지 | Modular / **2N power** / **N+1 cooling** / liquid-first |
| Target PUE | **1.18** |

> 참고: M1은 20 MW 설계 용량이지만 B300 5,000장 실부하는 **IT ≈ 6 MW** (GPU 1.1 kW TDP · 노드 base 2.35 kW 물리 모델 기준). 나머지는 확장 여유이며 Capacity 플래너에서 증설 가능량으로 표시.

Facility 메뉴: **Overview / Power / Cooling / Capacity / Energy & ESG**

### Facility UX 패턴

- **Overview** `/facility` — Power · Cooling · Halls · Modules 요약
- **Power** `/facility/power` — 라이브 단선도(SLD): KEPCO 154 kV ×2 → TR A/B → MV → UPS A/B (hall별) → busway → rack, 발전기 10대
- **Cooling** `/facility/cooling` — 루프 다이어그램: CDU(N+1, spare 자동 인계) → FWS → 냉각탑/프리쿨링 HX, CRAH → CHW → 칠러
- **Capacity** `/facility/capacity` — 모듈 build-out xrange + **증설 플래너**(전력·냉각·공간 제약으로 추가 가능 랙 계산)
- **Energy & ESG** `/facility/energy` — PUE/WUE/CUE, 에너지 Sankey, 탄소
- 행 클릭 → 상세 (`/facility/power/{id}` · `/facility/cooling/{id}` · `/facility/hall/{id}`)

---

## 4. IT 인프라 인벤토리 (확정)

| 도메인 | 조건 |
|--------|------|
| **GPU** | **NVIDIA B300 × 5,000** (HGX 8 GPU/node → **625 nodes** · 40 racks: R01–R25 ×16 + R26–R40 ×15) |
| **Storage** | **IBM Storage Scale 100 PB** (ss-hot 16 PB · ss-capacity 64 PB · ss-archive 20 PB) |
| **Ethernet** | **Arista** spine/leaf (7800R3 × 8, 7060X6 × 48) |
| **InfiniBand** | **NVIDIA Quantum-2 QM9700** (spine 6 + leaf 10 = 16, leaf당 GPU 랙 4개) |
| **Kubernetes** | **Dell × 30** (3 control plane + 27 workers) |
| Slurm 파티션 | train R01–R30 · infer R31–R35 (MIG) · dev R36–R38 · batch R39–R40 |

IT Cluster 메뉴: **GPU Monitoring / Storage / Network / Kubernetes**

### IT Cluster UX 패턴 (공통)

- 도메인별 **단일 overview** + 행 클릭 시 **새 상세 페이지**
- Network: `/network` 한 화면에 Uplink · Top Talkers · Topology · Inventory 요약 → `/network/uplinks` · `/network/toptalkers` · `/network/inventory` · `/network/device/{id}` (interface 전체, bps/errors/discards, 1 h 차트)
- Storage: `/storage` → `/storage/cluster/{id}` (volume IOPS · R/W · latency · throughput) · `/storage/toptalkers`
- Kubernetes: `/kubernetes` → `/kubernetes/node/{id}` (workloads · CPU/mem/pods 1 h)

### GPU Monitoring (Datadog GPU Monitoring 컨셉)

- **Fleet Explorer** `/gpu-fleet` — funnel (total → allocated → active → effective, idle-allocated) · idle 비용 · OOTB monitors · recommendations
- **5,000-GPU 캔버스 히트맵** (util / SM / temp / power / HBM 전환, 스로틀·drain·failed 표시, 클릭 → 디바이스)
- Tabs: **Provisioning** · **Performance** · **Inventory (Slurm + CubeFlow)** · **Connected entities**
- 상세: `/gpu-fleet/device/{id}` · `/gpu-fleet/node/{id}` (drain/resume) · `/gpu-fleet/job/{id}` · `/gpu-fleet/pod/{id}`
- XID/ECC 건강도, MIG 레이아웃, XID 수동 주입

---

## 5. Cloud (API 연동 데모)

**메뉴·카드·Cost·Vendors 표시 순서 고정:**

1. **AWS** — GPUaaS (EC2 / Capacity Blocks, 온프렘 대기열 **burst** 대상)
2. **GCP** — Storage (GCS + PD/Hyperdisk, 체크포인트 DR)
3. **NHN Cloud** — GPUaaS (국내 서빙)

- Overview `/cloud` — provider 카드, burn rate, MTD/forecast, **GPU·h 단가 비교(온프렘 TCO vs AWS vs NHN)**
- Provider `/cloud/aws` · `/cloud/gcp` · `/cloud/nhn`
- 상세 `/cloud/aws/instance/{id}` · `/cloud/gcp/bucket/{id}` · `/cloud/gcp/disk/{id}` · `/cloud/nhn/instance/{id}`

---

## 6. Cost (맨 아래 메뉴)

순서: **Summary / DC / Cloud / Budget**

- **Summary** `/cost` — MTD · forecast · MoM · YTD · 12개월 stacked trend · mix · 원장 · unit economics(₩/GPU·h)
- **DC** `/cost/dc` — 전기요금(KEPCO 산업용(을) 고압C **TOU를 tick마다 과금**) / 세금 / 관리비 / 인건비, 24 h 요율·부하 차트, 요금표
- **Cloud** `/cost/cloud` — AWS → GCP → NHN 월별 · live burn
- **Budget** `/cost/budget` — (아래 §13-7)

---

## 7. GPU Platform

메뉴 이름 **AI Factory 사용 금지** → **GPU Platform**. 3개 그룹:

| 그룹 | 경로 | 포함 기능 |
|------|------|-----------|
| Overview | `/gpu-platform` | 콘솔 · **잡 제출(원클릭 노트북 / 멀티노드 학습 / 배치)** · 프로젝트 쿼터 · 파티션 · LLM 카탈로그 · 공지 |
| Workloads | `/gpu-platform/workloads` | Jobs & Schedule · MIG Partitioning · RCS · Images (`?tab=`) |
| Ops | `/gpu-platform/ops` | Projects/Quota/RBAC · Nodes · Resource Monitor · Ecosystem · Usage Reports(차지백) |

API: `GET /api/gpu-platform` (legacy alias `GET /api/fractos`) · `POST /api/gpu-platform/jobs`. 구 `/fractos/*` → redirect.

---

## 8. Observability (CoreWeave Observe™ 컨셉)

용어는 **observability** 기본.

- **Overview** `/observability` — solutions hub + 텔레메트리 파이프라인
- **Explore** `/observability/explore` — PromQL 메트릭 + LogQL 로그 볼륨 + 이벤트 스트림을 **한 시간축**에 상관 분석
- **Metrics** `/observability/metrics` — PromQL-lite (`=`,`!=`,`=~`,`!~`, `sum/avg/max/min/count by`, `topk/bottomk`, `rate/irate/increase/delta`, `*_over_time`, 산술) · `POST /api/observability/metrics/query`
- **Logs** `/observability/logs` — LogQL-lite (`|=`,`!=`,`|~`,`!~`, `count_over_time`, `rate`) + live tail · `POST /api/observability/logs/query`
- **Telemetry Relay** `/observability/telemetry-relay` — Grafana Cloud OTLP · Datadog · Splunk HEC · GCS 아카이브 on/off
- **Resource Usage** `/observability/resource-usage` — 프로젝트별 compute / storage / network + cost signal
- **Mission Control** `/observability/mission-control` — **Claude 에이전트** (13개 read-only 도구, 근거 링크) · 키 없으면 내장 분석기

---

## 9. Operations · Developers · Platform

- **Operations**: Inventory `/inventory` · Rack View `/rack-view` · Rack `/rack/{id}` (U 엘리베이션) · Alerts `/alerts` · Slack·Webhooks `/alerts/integrations` · Alert Config `/alerts/config`
- **Alerts → Slack**: in-app + Slack(Block Kit) + generic webhook + PagerDuty(옵션). 라우팅 테이블, 전송 로그 `GET /api/alerts/deliveries`, 기본 **dry-run** (`ALERTS_LIVE_DELIVERY=1` + `SLACK_WEBHOOK_URL` 설정 시 실제 전송)
- **Developers**: API Catalog `/developers/api` · `GET /api/catalog` — **모든 페이지는 JSON API 페어 필수**, Try-it 포함
- **Platform**: Tech Spec · Vendors & API (AWS→GCP→NHN, 샘플 프로브) · Simulation (시나리오·모드·알림 주입·Redis·Export) · **Requirements (본 MD 보기/다운로드)**

---

## 10. 전체 메뉴 구조

```
Main
Campus Aerial
Facility ………… Overview / Power / Cooling / Capacity / Energy & ESG
IT Cluster …… GPU Monitoring / Storage / Network / Kubernetes
GPU Platform … Overview / Workloads / Ops
Cloud …………… Overview / AWS GPUaaS / GCP Storage / NHN GPUaaS
Observability … Overview / Explore / Metrics / Logs / Telemetry Relay / Resource Usage / Mission Control
Operations …… Inventory / Rack View / Alerts / Slack·Webhooks / Alert Config
Developers …… API Catalog
Platform ……… Tech Spec / Vendors & API / Simulation / Requirements
Cost …………… Summary / DC / Cloud / Budget
Server Status … 이 서버의 CPU · 메모리 · 디스크 · 네트워크 · 서비스 프로세스 + Redis 사용량 · 기본 정보
```

---

## 11. 데이터 경로 (필수) — 수집 → Redis → 표시

데모 데이터든 실데이터든 **수집기가 취합·집계해 Redis에 올리고, 웹은 Redis만 읽어 표시**한다.

```
collector 프로세스 ──write──▶ Redis dcim:aidc100:claude:* ◀──read── web 프로세스 (페이지 · API · SSE · 에이전트)
   (시뮬레이터 = 데모 수집기)            ▲                                    │
                                        └──────── 명령 버스 cmd / reply:{id} ◀─┘
```

| 규칙 | 내용 |
|---|---|
| 읽기 | 웹 계층은 `app/web/data.py`(`rm`)로만 데이터를 읽는다 — `live` · `view:{page}` · `ent:{kind}` · `ts:{metric}` · `logs` · `meta`. 시뮬레이터 객체 import 금지(`tests/test_architecture.py`가 강제) |
| 쓰기 | 상태를 바꾸는 모든 동작(잡 제출·드레인·XID·시나리오·알림 ack·룰/라우팅·릴레이·예산 결재·벤더 프로브)은 명령 버스로 수집기에 요청. 수집기는 실행 → 재발행 → 응답 순서 |
| 발행 주기 | 매 틱(2 s): `live` + 페이지 뷰 44종 + 히트맵 · 3틱: 대형 목록 4종 · 5틱: 상세 엔티티 14종 · 시계열은 티어 주기 |
| 실시간 | 웹은 Redis `live` 채널을 1회 구독해 SSE로 분배. 브라우저는 탭 간 리더 선출로 **브라우저당 SSE 1개** (HTTP/1.1 호스트당 6연결 한도 고갈 방지) |
| 단일 작성자 | `lease:collector` 리스를 가진 수집기 1개만 발행 · 웹이 5초마다 리스를 감시해 비면 수집기를 기동(재배포 인계) |
| 서버 상태 | 수집기가 호스트(psutil)와 Redis(INFO)를 매 틱 수집해 `view:server` + `host_*`/`store_*` 시계열로 발행 → **Server Status** 페이지 |
| 데이터 프로필 | `GRID_DATA_PROFILE=large`(EC2): 2 s 데이터 3 h · 노드/GPU 12 h · 추세선 7 d · 로그 3만 줄 · 지난 7일 장애 이력 (Redis ~130 MB) |
| Redis 없음·용량 부족 | 인메모리 스토어 + 웹 내장 수집기로 동작 (읽기 경로 동일) · 뷰/엔티티는 압축 저장해 Redis ~15 MB |

상세 분석·측정: `docs/PERFORMANCE.md`

## 11b. 코드 구조

```
app/
  main.py                  # web: lifespan(SSE 허브 · 필요 시 내장 수집기) · auth gate · 정적 캐시 · 오류/워밍업 페이지
  config.py                # port 8003 · Redis prefix · GRID_STORE · GRID_COLLECTOR · 발행 주기
  store.py                 # Redis 계약(키 레이아웃 · 리스 · 명령 버스) + 인메모리 대체 구현
  fmt.py                   # 숫자 · ₩ · 시간 포맷 (공용)
  collector/               # 수집기 프로세스 (python -m app.collector)
    __init__.py            # 리스 · tick → 발행 · 명령 처리
    publisher.py           # read model 발행 스케줄 · 엔티티 · 시계열 · 로그
    commands.py            # 명령 핸들러 (상태 변경의 유일한 경로)
  readmodel/               # 집계: 수집 상태 → 페이지/상세 화면별 dict (수집기에서만 실행)
  sim/                     # 데모 수집 소스 = 디지털 트윈
    topology.py            # 캠퍼스·홀·랙·노드·전력/냉각 체인·패브릭·스토리지·K8s
    fleet.py               # 5,000 GPU 벡터 물리 · Slurm 스케줄러 · MIG · XID/ECC
    facility.py            # 2N 전력 · N+1 액체냉각 · PUE/WUE/CUE · 발전기 · 에너지
    itinfra.py             # Storage Scale · Arista/Quantum-2 · Kubernetes
    cloud.py · cost.py     # AWS→GCP→NHN · burst · KEPCO TOU · 예산 워크플로
    alerts.py · scenarios.py  # 룰 · 인시던트 상관 · Slack fan-out · 15개 인과 시나리오
    tsdb.py · promql.py · logs.py  # 4-tier TSDB(열 우선 인코딩) · PromQL-lite · LogQL-lite
    engine.py              # tick 루프 · 기록 · 액션 · post-tick 훅
  web/
    data.py                # 읽기 경로: rm.view · rm.entity · RemoteTSDB · rm.logs · rm.cmd · LiveHub(SSE)
    agent.py               # Mission Control (Claude tool-use + offline analyst) — read model만 사용
    nav.py · templating.py
    routers/               # 도메인별 page + API 라우터
  templates/ · static/     # Jinja · grid.css · grid.js(브라우저당 SSE 1개) · charts.js · heat.js · Highcharts(local)
```

---

## 12. 기술 스택 · 포트 · 버전

| Layer | Choice |
|-------|--------|
| Language | Python 3.14 |
| Web | FastAPI + Uvicorn + Jinja2 · **Server-Sent Events** (`/api/stream`, 폴링 폴백) |
| Simulation | numpy 벡터화 · 2 s tick (≈ 4–6 ms 계산) |
| Charts | Highcharts 13 (**local** `app/static/vendor/highcharts/`) + canvas 히트맵 |
| State | **Redis read model** (`dcim:aidc100:claude:*`) — 수집기가 쓰고 웹이 읽음 · Redis 없으면 인메모리 |
| AI | Anthropic SDK · `claude-opus-5-5` · adaptive thinking |
| Mac run | `./run_mac.sh` — Redis 확인 → collector → web (백그라운드, **Claude :8003**) · `./run_mac.sh web` 웹만 재시작 |

### Agent별 로컬 포트 (필수 · 충돌 방지)

| Agent | Port | URL |
|-------|------|-----|
| ChatGPT | 8001 | http://127.0.0.1:8001 |
| Cursor | 8002 | http://127.0.0.1:8002 |
| **Claude** (본 레포) | **8003** | http://127.0.0.1:8003 |

### 버전 규칙

- 형식 **`X.Y`**, Y는 **한 자리(0–9)** · `1.9` 다음은 `2.0` (절대 `1.10` 금지)
- 릴리스 이름 `grid-claude-vX.Y` (**claude 포함 필수**)
- `scripts/bump_version.py` 가 wrap과 문서 마커 동기화를 강제

### 주요 API

- `GET /api/live` · `/api/stream` (SSE) · `/api/meta` (수집기 하트비트) · `/api/series/{metric}` · `/api/search` · `/api/catalog`
- `GET /api/gpu-platform` · `POST /api/gpu-platform/jobs` · `GET /api/cloud` · `GET /api/cost` · `GET /api/cost/budget`
- `POST /api/observability/metrics/query` · `/api/observability/logs/query` · `GET /api/observability/agent/stream`
- `POST /api/sim/mode` · `/api/sim/scenario/{id}/start` · `/api/sim/alert`
- `GET /platform/requirements.md` — 본 문서 다운로드

### 문서 동기화 규칙 (필수)

기능·메뉴·순서·이름을 바꾸면 함께 갱신: `docs/REQUIREMENTS.md`(본 문서) · `README.md` · `VERSIONING.md` · Tech Spec 화면 · 내비/실제 UI.
`scripts/bump_version.py` 가 `<!-- VERSION -->` / `<!-- RELEASE -->` / `` `grid-claude-vX.Y` `` 를 일괄 갱신.

---

## 13. Claude edition 추가 기능 (v2.0)

공유 요구사항(§1–12)을 모두 충족하면서 아래를 추가했다.

1. **물리 기반 디지털 트윈** — GPU P = 145 W + 955 W·util^0.9, T = T_coolant + 0.0275 °C/W·P, 87 °C 스로틀; 노드·랙·홀·UPS η 곡선·칠러 스테이징·프리쿨링(습구온도)까지 한 tick에 계산
2. **인과 시나리오 15종 + 인시던트 상관** — CDU 펌프 고장 → 행 냉각수 상승 → spare CDU 인계(~24 s) → GPU 스로틀 → 잡 속도 저하 → 알림 4건이 **하나의 인시던트**로 묶임 (root cause · impact · runbook · timeline · MTTA/MTTR)
3. **실시간 SSE** — 2초마다 전 화면 KPI·차트·토스트 갱신 (폴링 폴백)
4. **PromQL-lite / LogQL-lite 엔진 + Explore 상관 분석**
5. **Mission Control = Claude 에이전트** — 13개 read-only 도구, 도구 호출마다 근거 페이지 링크, 세션 대화 유지, 키가 없으면 결정론적 내장 분석기로 동일 UI 동작
6. **GPU 잡 제출 콘솔** — 원클릭 노트북 / 멀티노드 학습 / 배치 → 토폴로지 인지 배치 또는 AWS Capacity Block burst를 실시간 추적
7. **Budget 워크플로** `/cost/budget` — 공유된 사내 양식 이미지(예산 이관 신청서 · 예산 증액 신청서 · 예산 환입 신청서 · 예산항목 생성 요청서)를 **해석해** 구현: 예산 항목별 budget / actual(실측 DC·Cloud 비용 연동) / forecast / variance, 요청 4종 작성 → 상신 → 팀장 승인 → 재무 검토 → 최종 승인/반려, 승인 즉시 예산 반영. (결재자는 역할명만 사용 — 실명 미사용)
8. **Energy & ESG** — PUE/WUE/CUE, 에너지 Sankey, 탄소 배출
9. **Capacity 증설 플래너** — 전력·냉각·공간 제약 중 병목 기준 추가 가능 랙 수
10. **Rack U 엘리베이션** — 52U 전면도, 노드별 GPU 8칸 util/temp
11. **⌘K 커맨드 팔레트** — 페이지·랙·노드·GPU·장비·알림 검색 + 시나리오 실행 액션
12. **옵션 로그인 게이트** (`AUTH_ENABLED=1`) · 모든 표 CSV Export · 전체 시뮬레이션 JSON Export
13. **수집기 / 웹 분리** — 수집 → Redis read model → 표시, 명령 버스, 수집기 리스, 브라우저당 SSE 1개 (§11)

---

## 14. 변경 이력 (입력 기준)

1. AIDC 100 MW DCIM (Python/Highcharts/Redis), modular 20→100, Krafton CI — `grid-claude-v1.0`
2. v1.8 공유 스펙 반영: 포트 8003, Cloud 순서 AWS→GCP→NHN, GPU Platform 3그룹, 로컬 Highcharts
3. **v2.0 전면 재작성** (최상위 모델): 공유 스펙 `dcim-cursor-v3.1` 기준 전 메뉴 + §13 추가 기능
4. Cost 메뉴에 **Budget** 추가 (사내 예산 양식 이미지 해석)
5. Facility 메뉴에 **Energy & ESG** 추가
6. **로딩 지연 수정 + 데이터 경로 개편**: 탭별 SSE가 브라우저 호스트당 6연결을 고갈시켜 5 s+ 대기 → 브라우저당 SSE 1개 · 수집기 → Redis → 웹 구조로 분리 · 정적 캐시/폰트 비차단 (`docs/PERFORMANCE.md`)
8. **사이드바 기본 접힘 + 펼치기 버튼, 버전만 표시, Server Status 메뉴, large 데이터 프로필(EC2), 지난 장애 이력 시드**
7. **Render 배포 안정화**: Redis 사용량 51 → 15 MB(압축·float16), 수집기 재시도·감시·인계, Redis 용량 부족 시 인메모리 자동 전환, /healthz 진단, URL 비밀번호 마스킹

---

*Generated for Krafton Grid AIDC DCIM · view in Platform → Requirements · download `/platform/requirements.md`*
