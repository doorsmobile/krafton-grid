# Mac 설치 · 실행 (Cursor / port 8002)

## 한 줄 요약

클라우드 에이전트가 준 `DOWNLOAD_URL` 로 받아서 `./run_mac.sh` 실행.

```bash
mkdir -p /Users/logan/code && cd /Users/logan/code
curl -fsSL -o dcim-cursor-vX.Y.tar.gz 'DOWNLOAD_URL'
rm -rf dcim-cursor-vX.Y
mkdir -p dcim-cursor-vX.Y && tar -xzf dcim-cursor-vX.Y.tar.gz -C dcim-cursor-vX.Y
cd dcim-cursor-vX.Y
chmod +x run_mac.sh
./run_mac.sh
```

브라우저: [http://127.0.0.1:8002](http://127.0.0.1:8002)

## 사전 조건 (최초 1회)

```bash
brew install python@3.12 redis
brew services start redis
```

## 런처

| 명령 | 동작 |
|------|------|
| `./run_mac.sh` | 이전 프로세스 종료 → venv/deps → Redis 확인 → 백그라운드 기동 |
| `./run_mac.sh stop` | 중지 |
| `./run_mac.sh status` | 헬스 체크 |

로그: `.run/uvicorn.log` · PID: `.run/uvicorn.pid`

## 에이전트 포트

| Agent | Port |
|-------|------|
| ChatGPT | 8001 |
| **Cursor (이 패키지)** | **8002** |
| Claude | 8003 |

다른 포트: `APP_PORT=8002 ./run_mac.sh`

## 이미 `/Users/logan/code/dcim-cursor-vX.Y` 가 있을 때

새 tarball을 같은 폴더로 덮어쓴 뒤:

```bash
cd /Users/logan/code/dcim-cursor-vX.Y
./run_mac.sh
```
