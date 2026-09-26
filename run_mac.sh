#!/usr/bin/env bash
# Mac launcher for Krafton Grid DCIM (Cursor port 8002).
# Usage: ./run_mac.sh          # start / restart in background
#        ./run_mac.sh stop     # stop only
#        ./run_mac.sh status   # show pid / url / health
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT="${APP_PORT:-8002}"
HOST="${APP_HOST:-127.0.0.1}"
LOG_DIR="${ROOT}/.run"
LOG_FILE="${LOG_DIR}/uvicorn.log"
PID_FILE="${LOG_DIR}/uvicorn.pid"
URL="http://${HOST}:${PORT}"
VERSION="$(tr -d '[:space:]' < VERSION 2>/dev/null || echo unknown)"
RELEASE="dcim-cursor-v${VERSION}"

mkdir -p "$LOG_DIR"

cmd="${1:-start}"

stop_existing() {
  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  fi
  if [[ -f "${PID_FILE}" ]]; then
    local old
    old="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [[ -n "${old}" ]]; then
      pids="${pids} ${old}"
    fi
  fi
  if [[ -z "${pids}" ]] && command -v pgrep >/dev/null 2>&1; then
    pids="$(pgrep -f "uvicorn app.main:app.*${PORT}" 2>/dev/null || true)"
  fi
  if [[ -n "${pids}" ]]; then
    echo "[dcim] stopping: ${pids}"
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 1
    # shellcheck disable=SC2086
    kill -9 ${pids} 2>/dev/null || true
  fi
  rm -f "${PID_FILE}"
}

ensure_redis() {
  if command -v redis-cli >/dev/null 2>&1; then
    if redis-cli ping >/dev/null 2>&1; then
      echo "[dcim] redis: ok"
      return 0
    fi
    if command -v redis-server >/dev/null 2>&1; then
      echo "[dcim] starting redis-server"
      redis-server --daemonize yes
      sleep 0.5
      if redis-cli ping >/dev/null 2>&1; then
        echo "[dcim] redis: started"
        return 0
      fi
    fi
    if command -v brew >/dev/null 2>&1; then
      echo "[dcim] trying: brew services start redis"
      brew services start redis >/dev/null 2>&1 || true
      sleep 1
      if redis-cli ping >/dev/null 2>&1; then
        echo "[dcim] redis: brew service ok"
        return 0
      fi
    fi
  else
    echo "[dcim] warn: redis-cli missing — install with: brew install redis"
  fi
  echo "[dcim] warn: Redis not reachable at 127.0.0.1:6379 (app may fail to start)"
}

status() {
  echo "[dcim] release=${RELEASE}  port=${PORT}"
  if [[ -f "${PID_FILE}" ]]; then
    echo "[dcim] pid=$(cat "${PID_FILE}")"
  else
    echo "[dcim] pid=(none)"
  fi
  if curl -sf -o /dev/null "${URL}/api/live" 2>/dev/null; then
    echo "[dcim] health=ok  url=${URL}"
  else
    echo "[dcim] health=down  url=${URL}"
    return 1
  fi
}

case "${cmd}" in
  stop)
    echo "[dcim] release=${RELEASE}  stop"
    stop_existing
    echo "[dcim] stopped"
    exit 0
    ;;
  status)
    status
    exit $?
    ;;
  start|restart|"")
    ;;
  *)
    echo "usage: $0 [start|stop|status]"
    exit 2
    ;;
esac

echo "[dcim] release=${RELEASE}  port=${PORT}"
stop_existing

if [[ ! -d .venv ]]; then
  echo "[dcim] creating .venv"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "[dcim] installing deps"
python -m pip install -q -U pip
python -m pip install -q -r requirements.txt

ensure_redis

export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
export APP_PORT="${PORT}"
export APP_HOST="${HOST}"

nohup python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" \
  >>"${LOG_FILE}" 2>&1 &
echo $! >"${PID_FILE}"
PID="$(cat "${PID_FILE}")"

ok=0
for _ in $(seq 1 25); do
  if curl -sf -o /dev/null "${URL}/api/live" 2>/dev/null; then
    ok=1
    break
  fi
  sleep 0.4
done

if [[ "${ok}" -eq 1 ]]; then
  echo "[dcim] started pid=${PID}"
  echo "[dcim] open  ${URL}"
  echo "[dcim] log   ${LOG_FILE}"
  echo "[dcim] stop  ./run_mac.sh stop"
else
  echo "[dcim] ERROR: server did not become healthy — see ${LOG_FILE}"
  tail -n 40 "${LOG_FILE}" || true
  exit 1
fi
