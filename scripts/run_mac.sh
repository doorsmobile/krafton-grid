#!/usr/bin/env bash
# Thin wrapper — real launcher lives at repo root.
set -euo pipefail
exec "$(cd "$(dirname "$0")/.." && pwd)/run_mac.sh" "$@"
