#!/usr/bin/env bash
# Krafton Grid · grid-claude launcher (Claude port 8003)
#
#   data path:  collector process ──▶ Redis (read models) ──▶ web process (pages · APIs · SSE)
#
#   ./run_mac.sh            start / restart both processes in the background
#   ./run_mac.sh stop       stop both
#   ./run_mac.sh status     pids · health · collector heartbeat
#   ./run_mac.sh logs       follow both logs
#   ./run_mac.sh web        restart only the web process (collector keeps running — no simulation reset)
#
# Without Redis the web process runs the collector in-process on an in-memory store (same read path).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT="${APP_PORT:-8003}"
HOST="${APP_HOST:-127.0.0.1}"
PREFIX="${REDIS_PREFIX:-dcim:aidc100:claude}"
RUN_DIR="$ROOT/.run"
WEB_LOG="$RUN_DIR/uvicorn.log"
WEB_PID="$RUN_DIR/uvicorn.pid"
COL_LOG="$RUN_DIR/collector.log"
COL_PID="$RUN_DIR/collector.pid"
URL="http://${HOST}:${PORT}"
VERSION="$(tr -d '[:space:]' < VERSION 2>/dev/null || echo 0.0)"
RELEASE="grid-claude-v${VERSION}"
mkdir -p "$RUN_DIR"

say() { printf '[grid-claude] %s\n' "$*"; }

kill_pids() {  # kill_pids <label> <pid...>
  local label="$1"; shift
  local pids; pids="$(echo "$*" | xargs -n1 2>/dev/null | sort -u | xargs 2>/dev/null || true)"
  [[ -z "${pids// /}" ]] && return 0
  say "stopping $label pid(s): $pids"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  for _ in $(seq 1 15); do
    sleep 0.3
    # shellcheck disable=SC2086
    kill -0 $pids 2>/dev/null || return 0
  done
  # shellcheck disable=SC2086
  kill -9 $pids 2>/dev/null || true
}

stop_web() {
  local pids=""
  if command -v lsof >/dev/null 2>&1; then pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"; fi
  [[ -f "$WEB_PID" ]] && pids="$pids $(cat "$WEB_PID" 2>/dev/null || true)"
  kill_pids web $pids
  rm -f "$WEB_PID"
}

stop_collector() {
  local pids=""
  [[ -f "$COL_PID" ]] && pids="$(cat "$COL_PID" 2>/dev/null || true)"
  pids="$pids $(pgrep -f "python -m app.collector" 2>/dev/null | xargs 2>/dev/null || true)"
  kill_pids collector $pids
  rm -f "$COL_PID"
}

redis_ok() { command -v redis-cli >/dev/null 2>&1 && redis-cli ping >/dev/null 2>&1; }

ensure_redis() {
  if redis_ok; then say "redis: ok"; return 0; fi
  if command -v redis-server >/dev/null 2>&1; then
    say "starting redis-server (daemonized)"
    redis-server --daemonize yes >/dev/null 2>&1 || true
    sleep 0.5
  elif command -v brew >/dev/null 2>&1; then
    brew services start redis >/dev/null 2>&1 || true
    sleep 1
  fi
  if redis_ok; then say "redis: ok"; return 0; fi
  say "redis: not available — web will run the collector in-process on an in-memory store"
  return 1
}

healthy() { curl -s "$URL/healthz" 2>/dev/null | grep -q '"ok":true'; }

start_collector() {
  export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" GRID_STORE=redis
  nohup .venv/bin/python -m app.collector >>"$COL_LOG" 2>&1 &
  echo $! >"$COL_PID"
  local pid; pid="$(cat "$COL_PID")"
  for _ in $(seq 1 60); do   # the collector takes the lease first, then boots the engine (~2 s)
    if redis-cli --raw GET "$PREFIX:lease:collector" 2>/dev/null | grep -q ":$pid:"; then
      say "collector pid $pid holds the lease"; return 0
    fi
    kill -0 "$pid" 2>/dev/null || { say "ERROR: collector exited — last log lines:"; tail -n 30 "$COL_LOG"; exit 1; }
    sleep 0.25
  done
  say "WARNING: collector did not take the lease yet (a previous lease may still be expiring)"
}

start_web() {
  export APP_PORT="$PORT" APP_HOST="$HOST" PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
  nohup .venv/bin/python -m uvicorn app.main:app --host "$HOST" --port "$PORT" --no-access-log >>"$WEB_LOG" 2>&1 &
  echo $! >"$WEB_PID"
  for _ in $(seq 1 80); do
    if healthy; then
      say "web pid $(cat "$WEB_PID") · data flowing"
      return 0
    fi
    sleep 0.25
  done
  say "ERROR: web did not become healthy — last log lines:"
  tail -n 40 "$WEB_LOG" || true
  exit 1
}

case "${1:-start}" in
  stop) say "$RELEASE · stop"; stop_web; stop_collector; say "stopped"; exit 0 ;;
  status)
    say "$RELEASE · port $PORT · web pid $(cat "$WEB_PID" 2>/dev/null || echo none) · collector pid $(cat "$COL_PID" 2>/dev/null || echo none/embedded)"
    if healthy; then say "health: ok · $URL"; curl -s "$URL/healthz"; echo; else say "health: down"; curl -s "$URL/healthz" 2>/dev/null; echo; exit 1; fi
    exit 0 ;;
  logs) tail -f "$WEB_LOG" "$COL_LOG" ;;
  web)
    say "$RELEASE · restarting web only"
    stop_web; start_web
    say "open   $URL"; exit 0 ;;
  start|restart) ;;
  *) echo "usage: $0 [start|stop|status|logs|web]"; exit 2 ;;
esac

say "$RELEASE · port $PORT"
stop_web
stop_collector

if [[ ! -x .venv/bin/python ]]; then
  say "creating .venv"
  python3 -m venv .venv
fi
say "installing dependencies"
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt

if ensure_redis; then
  export GRID_STORE=redis GRID_COLLECTOR=auto
  start_collector
else
  export GRID_STORE=memory GRID_COLLECTOR=embedded
fi
start_web

say "open   $URL"
say "logs   $WEB_LOG · $COL_LOG"
say "stop   ./run_mac.sh stop"
