# 로딩 지연 분석 & 데이터 경로 개편 — grid-claude-v2.0

> 증상: 일부 메뉴(대표적으로 `/facility`)에서 페이지가 뜨기까지 **5초 이상** 걸림.
> 요청: 원인 분석 + 수정, 그리고 "데모든 실데이터든 **취합 → Redis 적재 → Redis에서 읽어 표시**" 구조로 변경.
> 측정 환경: MacBook (Apple Silicon) · Python 3.14 · Redis 7 로컬 · Chrome 계열 브라우저 · 2026-10-01

---

## 1. 결론 요약

| 질문 | 답 |
|---|---|
| 데모 데이터가 너무 많아서 느렸나? | **아니오.** 서버가 페이지를 만드는 데 중앙값 1.2 ms, 가장 무거운 페이지(`/gpu-platform/ops`)도 9 ms. `/facility`는 0.4 ms. |
| 그럼 원인은? | **브라우저 연결 고갈.** 모든 탭이 실시간 스트림(SSE, `/api/stream`)을 1개씩 **계속 열어둠** → 크롬은 HTTP/1.1에서 **호스트당 동시 연결 6개**까지만 허용 → 탭이 6개 쌓이면 새 페이지의 HTML·JS·API 요청이 빈 연결을 **무기한 대기**. 다른 탭이 이동하거나 닫혀 연결이 풀릴 때 비로소 로딩 → "특정 메뉴에서 5초+"로 체감. |
| 재현됐나? | 예. SSE 6개를 연 상태에서 `/api/facility` 요청이 **12초 동안 응답을 못 받고 타임아웃**. 같은 요청이 평소엔 1.5 ms. |
| 무엇을 바꿨나? | ① 브라우저당 SSE **1개만** 쓰도록 변경(탭끼리 공유) ② 데이터 경로를 **수집기 → Redis → 웹**으로 분리 ③ 정적 파일 캐시·폰트 비차단 로딩·병렬 조회 등 부수 개선 |
| 결과 | 탭 7개 상태에서 `/facility` 전체 로드 **46 ms**(이전: 무기한 대기). 서버 SSE 연결은 브라우저당 1개. 모든 페이지·API·SSE·에이전트가 **Redis만 읽음**(테스트로 강제). |

---

## 2. 측정 — 무엇이 느리지 *않았는지*부터

### 2.1 서버 렌더 시간 (수정 전, 페이지당 4회 중앙값)

| 페이지 | 시간 | HTML |
|---|---:|---:|
| `/gpu-platform/ops` (노드 625행) | 8.6 ms | 270 KB |
| `/platform/requirements` | 6.5 ms | 41 KB |
| `/inventory` (자산 ~900행) | 5.8 ms | 300 KB |
| `/platform/simulation` | 5.3 ms | 43 KB |
| `/gpu-platform/workloads` | 4.3 ms | 200 KB |
| … `/facility` | **0.4 ms** | 41 KB |
| **전체 페이지 중앙값** | **1.2 ms** | |

뷰 모델 26개를 한 번씩 모두 계산해도 **14 ms**, JSON으로 약 1 MB. API(`/api/facility`, `/api/series/*`, `/api/live`)는 1–2 ms.
→ 데이터 양이나 서버 계산은 5초의 원인이 될 수 없습니다.

### 2.2 브라우저 — 탭 1개일 때

`/facility`: TTFB 7 ms · DOMContentLoaded 63 ms · load 117 ms, 요청 15개 모두 2–13 ms. **빠름.**

### 2.3 재현 — 탭 여러 개일 때

```js
// 같은 브라우저에서 SSE 6개(= 앱 탭 6개와 같은 상태)를 연 뒤
for (let i = 0; i < 5; i++) new EventSource('/api/stream');   // + 현재 탭 1개 = 6
await fetch('/api/facility');                                  // → 12,001 ms 후 AbortError (응답 없음)
```

같은 시점 서버는 한가했고(틱 13 ms), 요청은 **서버에 도달조차 못 한 채 브라우저 큐에서 대기**했습니다.

---

## 3. 원인 상세

1. **SSE는 끊기지 않는 HTTP 요청**입니다. 탭마다 `new EventSource('/api/stream')`이 연결을 하나씩 **영구 점유**했습니다.
2. 크롬·엣지·사파리는 HTTP/1.1에서 **같은 호스트(`127.0.0.1:8003`)당 6개**까지만 동시 연결을 엽니다. 이 한도는 탭별이 아니라 **브라우저(프로필) 전체** 기준입니다.
3. 대시보드 특성상 여러 메뉴를 탭으로 띄워두기 쉽습니다 → 탭 5개면 나머지 모든 요청이 **연결 1개를 줄서서** 쓰고, 6개면 **완전 정지**. 한 페이지 로딩에는 HTML + 정적 파일 12개 + 시계열 API 3–15개가 필요합니다.
4. 대기가 풀리는 건 다른 탭이 이동·종료해서 SSE가 닫힐 때 → 사용자 입장에선 "어떤 메뉴는 5초 넘게 걸린다"로 보입니다. `/facility`는 가장 먼저·자주 여는 메뉴라 대표 사례로 체감됐을 가능성이 큽니다.
5. 증폭 요인(부차적):
   - 정적 파일 12개에 캐시 헤더가 없어 **이동할 때마다 재검증(304) 요청**을 보냄 → 연결 경쟁을 키움
   - Google Fonts CSS가 **렌더 차단** 방식 → 외부망이 느리면 첫 화면이 늦어짐
   - `/facility` 스파크라인 3개를 **순차 await**로 조회

---

## 4. 변경 1 — 브라우저당 SSE 1개 (연결 고갈 제거)

`app/static/js/grid.js`

```
탭 A (leader)  ── EventSource /api/stream ──▶ 서버        ← 브라우저 전체에서 1개
   │  BroadcastChannel("grid-live-v1")로 스냅샷 재전송
   ├──▶ 탭 B (follower)
   ├──▶ 탭 C (follower)
   └──▶ …
```

- **Web Locks API**로 탭끼리 리더를 선출. 리더 탭만 SSE를 열고, 받은 스냅샷을 **BroadcastChannel**로 다른 탭에 전달.
- 리더 탭이 닫히거나 다른 페이지로 이동하면 잠금이 풀리고 **다음 탭이 자동으로 리더를 승계**.
- 팔로워는 7초 이상 방송이 없으면 `/api/live`를 짧게 폴링(짧은 요청이라 연결을 점유하지 않음).
- 두 API를 지원하지 않는 브라우저는 기존 방식(탭별 SSE)으로 폴백.

검증(브라우저 탭 7개): 리더 1 · 팔로워 6 → 서버 SSE 연결은 이 브라우저에서 1개. 팔로워 탭도 매 틱 갱신(tick 38 → 41 / 5 s). 리더 탭을 닫자 다른 탭이 즉시 리더가 되고 갱신 계속.

부수 개선:
- `/static/*` 캐시: `vendor/`와 `?v=` 지문이 붙은 파일은 `max-age=1년, immutable` → 이동 시 재검증 요청 0건. 우리 JS/CSS 지문은 `릴리스.최종수정시각`이라 파일을 고치면 자동으로 새로 받음.
- Google Fonts를 비차단 로딩(`media="print" onload`).
- `/facility` 스파크라인 3개를 `Promise.all`로 병렬 조회.

---

## 5. 변경 2 — 데이터 경로: 수집기 → Redis → 웹

### 5.1 구조

```
┌──────────────── collector 프로세스 (python -m app.collector) ────────────────┐
│  수집: 지금은 물리 시뮬레이터(데모) · 실운영은 DCGM/Redfish/SNMP/Modbus/클라우드 API │
│  집계: app/readmodel/*  → 페이지·상세 화면별 read model(dict)                     │
│  발행: app/collector/publisher.py → Redis 파이프라인 1회 + PUBLISH live           │
│  명령: cmd 리스트를 BLPOP → 실행 → 재발행 → reply:{id}                            │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                ▼
┌──────────────────── Redis  dcim:aidc100:claude:* ────────────────────────────┐
│ live · view:{page} · ent:{kind} (hash) · ts:{metric} (binary) · ts:catalog     │
│ logs · meta(heartbeat) · lease:collector · cmd / reply:{id}                    │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                ▼
┌──────────────── web 프로세스 (uvicorn app.main:app) ─────────────────────────┐
│ app/web/data.py 만 데이터 접근: rm.view / rm.entity / rm.tsdb / rm.logs / rm.cmd │
│ 페이지·JSON API·SSE(구독 1개를 모든 클라이언트에 분배)·Mission Control 에이전트    │
│ 시뮬레이터 객체 import 금지 — tests/test_architecture.py 가 강제                │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Redis 키

| 키 | 타입 | 내용 | 갱신 |
|---|---|---|---|
| `live` | string JSON (6 KB) | 전 화면 공통 실시간 스냅샷 + `PUBLISH live` | 매 틱(2 s) |
| `view:{name}` | string JSON | 페이지 read model 44종 (main, facility, power, cooling, gpu_fleet, heatmap:{5종}, cloud_*, alerts, cost_*, budget …) | 매 틱 |
| `view:{gpu_nodes, workloads, gpu_ops, inventory}` | string JSON (140–160 KB) | 대형 목록 | 3틱(6 s) |
| `ent:{kind}` | hash (id → JSON) | 상세 화면 14종: gpu_node 625 · gpu_pod 800 · gpu_job · rack 94 · power/cooling device · hall · storage_cluster · network_device 72 · k8s_node · aws/gcp/nhn 리소스 | 5틱(10 s) + 관련 명령 직후 |
| `ts:{metric}` | binary | 링 스냅샷: 헤더(n, width) · ts float64[n] · 값 float32 **열 우선** | 티어 주기(2 s / 10 s / 30 s / 60 s) |
| `ts:catalog` | string JSON | 메트릭 88종 이름·라벨·단위·티어 | 수집기 시작 시 1회 |
| `logs` | list | 로그 라인(최대 20,000) | 매 틱 신규분 RPUSH + LTRIM |
| `meta` | string JSON | 하트비트: tick, 시뮬 ms, 빌드 ms, 발행 바이트, owner | 매 틱 |
| `lease:collector` | string (PX 10 s) | 쓰기 권한을 가진 수집기 1개 | 매 틱 갱신 |
| `cmd`, `reply:{id}` | list | 명령 버스 | 요청 시 |

설계 포인트
- **열 우선(column-major) 시계열**: GPU 1장 그래프는 5,000열 링 전체(2.4 MB) 대신 `GETRANGE`로 그 열(480 B)만 읽음 → 1.7 ms.
- **원자성**: 해시는 임시키에 쓰고 `RENAME`, 시계열 조각은 `MULTI/EXEC`로 읽어 반쯤 쓰인 데이터를 보지 않음.
- **명령 후 즉시 반영**: 수집기는 명령 실행 → 영향받은 read model 재발행 → **그다음** 응답. 그래서 버튼 클릭 뒤 새로고침하면 Redis에 이미 새 상태가 있음.
- **리스(lease)**: 수집기는 동시에 1개만 씀. 두 번째 수집기는 대기(standby).
- **Redis가 없을 때**: 같은 계약을 구현한 인메모리 스토어로 웹 프로세스 안에서 수집기를 돌림 — 읽기 경로는 동일.

### 5.3 요청별 흐름

| 요청 | 이전 | 이후 |
|---|---|---|
| 페이지 `/facility` | 요청마다 엔진 객체에서 뷰 계산 | `GET view:facility` → 템플릿 |
| 상세 `/gpu-fleet/device/{id}` | 엔진에서 계산 | `HGET ent:gpu_node {node}` 에서 해당 GPU 투영 |
| 그래프 `/api/series/*` | 프로세스 메모리 TSDB | `GETRANGE ts:{metric}` (필요한 열만) |
| PromQL / LogQL | 엔진 TSDB/로그 | Redis 시계열·로그를 웹에서 평가 |
| 실시간 `/api/stream` | 엔진 → 탭별 큐 | Redis `SUBSCRIBE live` 1개 → 클라이언트 분배 |
| 버튼(잡 제출·드레인·결재·시나리오…) | 엔진 메서드 직접 호출 | `RPUSH cmd` → 수집기 실행 → `reply:{id}` |
| Mission Control 도구 13개 | 엔진 내부 배열 | 같은 read model(히트맵·엔티티·시계열·로그) |

---

## 6. 결과 (수정 후, 분리 배포 · Redis)

| 항목 | 값 |
|---|---|
| 탭 7개 열린 상태에서 `/facility` 로드 | TTFB 17 ms · load **46 ms** · 요청 18개 중 8개 캐시 적중 · 최장 5 ms |
| 서버 SSE 연결 | 브라우저당 **1개** (탭 수와 무관) |
| 페이지 응답 (Redis 읽기 + 렌더) | `/facility` 2.4 ms · `/` 2.7 ms · `/gpu-fleet` 2.6 ms · `/inventory` 7.9 ms · `/gpu-platform/ops` 10.3 ms |
| 시계열 1열 (`gpu_temp_c`, 5,000열 중 1열) | 1.7 ms |
| 명령 왕복 (잡 제출·시나리오·결재) | ~40 ms · 노드 드레인 ~155 ms(노드 엔티티 625개 재발행 포함) |
| 수집기 발행 비용 | 일반 틱: 빌드 32 ms · 3.2 MB / 엔티티 틱(10 s): 빌드 161 ms · 21 MB |
| Redis 메모리 | 51 MB · 키 155개 |
| 프로세스 | collector RSS 145 MB · CPU 4% / web RSS 117 MB · CPU 0.1% |
| 테스트 | pytest 23개 통과 (아키텍처 가드·명령 왕복·시계열/PromQL/LogQL 포함) · 전 라우트 스모크 통과 |

---

## 7. 운영

```bash
cd /Users/logan/Code/grid-claude-v2.0 && ./run_mac.sh          # Redis 확인 → collector → web
./run_mac.sh status                                            # 두 프로세스 pid + 하트비트
./run_mac.sh web                                               # 웹만 재시작 (시뮬레이션 상태 유지)
./run_mac.sh logs                                              # .run/uvicorn.log + .run/collector.log
```

| 환경변수 | 기본 | 설명 |
|---|---|---|
| `GRID_STORE` | `auto` | `redis` · `memory`(Redis 없을 때) |
| `GRID_COLLECTOR` | `auto` | 실행 중인 수집기 사용, 없으면 웹 프로세스 안에서 기동 · `embedded` · `external` |
| `ENTITY_EVERY_TICKS` / `HEAVY_EVERY_TICKS` | 5 / 3 | 상세 엔티티 / 대형 목록 발행 주기 |
| `COLLECTOR_LEASE_S` | 10 | 수집기 리스 TTL |

실데이터 연결: `app/sim/*` 엔진 대신 수집 어댑터가 같은 상태를 채우면 됩니다. `app/readmodel/*`(집계), 발행 스케줄, Redis 키, 웹 계층은 그대로입니다.

`./run_mac.sh web`처럼 웹만 재시작해도 이제 시뮬레이션·결재·알림 상태가 유지됩니다(수집기가 별도 프로세스이기 때문).

---

## 8. 남은 개선 여지

- **시계열 쓰기량**: 링을 주기마다 통째로 다시 씀(평균 ~1.6 MB/s, 로컬 Redis엔 부담 없음). 규모가 커지면 새 샘플 위치만 `SETRANGE`로 갱신하거나 RedisTimeSeries/Prometheus remote-write로 바꿀 것.
- **상세 엔티티 신선도**: 최대 10 s 지연(실시간 KPI는 `live`/SSE로 2 s마다 갱신됨). `ENTITY_EVERY_TICKS`로 조정 가능.
- **HTTP/2**: 리버스 프록시(Caddy/nginx)로 h2를 쓰면 호스트당 연결 한도 문제 자체가 사라짐 — 공유 배포 시 권장.
