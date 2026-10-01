"""Run the collector as its own process:  python -m app.collector

It needs Redis (GRID_STORE=redis is implied) — the in-process store only makes sense when the
collector runs inside the web process.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import time

os.environ.setdefault("GRID_STORE", "redis")

from .. import config  # noqa: E402
from ..store import StoreError, get_store  # noqa: E402
from . import Collector  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        store = get_store()
    except StoreError as e:
        print(f"[grid-collector] {e}", file=sys.stderr)
        return 2
    c = Collector(store, role="external").start()
    signal.signal(signal.SIGTERM, lambda *_: c.stop())
    print(f"[grid-collector] {config.RELEASE_NAME} · {c.owner} · waiting for lease on {store.url}", flush=True)
    try:
        while not c.stop_evt.is_set():
            if c.ready.is_set() and c.pub and c.pub.last.get("meta"):
                m = c.pub.last["meta"]
                if m["tick"] % 30 == 0:
                    print(f"[grid-collector] tick {m['tick']} · sim {m['tick_ms']} ms · build {m['build_ms']} ms · "
                          f"{m['bytes'] / 1e6:.2f} MB published", flush=True)
            time.sleep(2.0)
    except KeyboardInterrupt:
        pass
    finally:
        c.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
