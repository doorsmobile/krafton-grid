#!/usr/bin/env bash
# Package this release as dist/dcim-cursor-vX.Y.tar.gz and upload for Mac download.
# Cloud Agents: /Users/logan/code is not the laptop — use the printed curl URL.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
NAME="dcim-cursor-v${VERSION}"
LOCAL_ROOT="${LOCAL_CODE_ROOT:-/Users/logan/code}"
DEST="${LOCAL_ROOT}/${NAME}"
DIST_DIR="${ROOT}/dist"
ARCHIVE="${DIST_DIR}/${NAME}.tar.gz"

mkdir -p "$DIST_DIR"

echo "[sync] packing ${NAME}"
tar -C "$ROOT" -czf "$ARCHIVE" \
  --exclude='.git' \
  --exclude='dist' \
  --exclude='dump.rdb' \
  --exclude='*.rdb' \
  --exclude='__pycache__' \
  --exclude='.venv' \
  --exclude='venv' \
  --exclude='terminals' \
  --exclude='.run' \
  --exclude='.pytest_cache' \
  --exclude='app/static/downloads' \
  .

BYTES="$(wc -c < "$ARCHIVE" | tr -d ' ')"
echo "[sync] archive=${ARCHIVE}  bytes=${BYTES}"

if [[ -d "$LOCAL_ROOT" || -w "$(dirname "$LOCAL_ROOT" 2>/dev/null || echo /)" ]]; then
  if [[ -d "$LOCAL_ROOT" ]]; then
    rm -rf "$DEST"
    mkdir -p "$DEST"
    tar -xzf "$ARCHIVE" -C "$DEST"
    chmod +x "$DEST/run_mac.sh" "$DEST/scripts/"*.sh 2>/dev/null || true
    echo "[sync] synced local ${DEST}"
  fi
else
  echo "[sync] local path unavailable here: ${DEST}"
fi

if [[ -d /opt/cursor/artifacts ]]; then
  cp -f "$ARCHIVE" "/opt/cursor/artifacts/${NAME}.tar.gz"
  echo "[sync] artifacts=/opt/cursor/artifacts/${NAME}.tar.gz"
fi

upload_url=""
try_litterbox() {
  curl -sS --max-time 180 \
    -F "reqtype=fileupload" \
    -F "time=72h" \
    -F "fileToUpload=@${ARCHIVE}" \
    https://litterbox.catbox.moe/resources/internals/api.php 2>/dev/null || true
}
try_uguu() {
  # returns JSON { url: "https://..." }
  curl -sS --max-time 180 \
    -F "files[]=@${ARCHIVE}" \
    https://uguu.se/upload 2>/dev/null || true
}
try_0x0() {
  curl -sS --max-time 180 -F "file=@${ARCHIVE}" https://0x0.st 2>/dev/null || true
}

echo "[sync] uploading…"
upload_url="$(try_litterbox)"
if [[ -z "${upload_url}" || "${upload_url}" != http* ]]; then
  raw="$(try_uguu)"
  upload_url="$(python3 -c 'import json,sys
try:
 d=json.load(sys.stdin)
 print((d.get("files") or [{}])[0].get("url") or d.get("url") or "")
except Exception:
 print("")
' <<<"${raw}" 2>/dev/null || true)"
fi
if [[ -z "${upload_url}" || "${upload_url}" != http* ]]; then
  upload_url="$(try_0x0)"
fi

chmod +x "$ROOT/run_mac.sh" "$ROOT/scripts/"*.sh 2>/dev/null || true

echo "VERSION=${VERSION}"
echo "RELEASE=${NAME}"
echo "ARCHIVE=${ARCHIVE}"

if [[ -n "${upload_url}" && "${upload_url}" == http* ]]; then
  echo "DOWNLOAD_URL=${upload_url}"
  cat <<EOF

======== Mac install (Cursor · port 8002) ========
mkdir -p /Users/logan/code && cd /Users/logan/code
curl -fsSL -o ${NAME}.tar.gz '${upload_url}'
rm -rf ${NAME}
mkdir -p ${NAME} && tar -xzf ${NAME}.tar.gz -C ${NAME}
cd ${NAME}
chmod +x run_mac.sh
./run_mac.sh
# open http://127.0.0.1:8002
# stop: ./run_mac.sh stop
==================================================
EOF
else
  echo "DOWNLOAD_URL=(upload failed)"
  echo "[sync] use local artifact: /opt/cursor/artifacts/${NAME}.tar.gz or ${ARCHIVE}"
  exit 1
fi
