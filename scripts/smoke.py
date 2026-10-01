"""Render every page and hit every API; print one line per failure."""
import sys
import traceback

from fastapi.testclient import TestClient

import app.main as m

PAGES = [p for p in sys.argv[1:]] or None


def run(paths):
    bad = 0
    with TestClient(m.app) as c:
        for p in paths:
            try:
                r = c.get(p, headers={"accept": "text/html" if not p.startswith("/api/") else "application/json"}, follow_redirects=False)
                ok = r.status_code in (200, 307, 308)
                if not ok:
                    bad += 1
                    print(f"FAIL {r.status_code} {p} :: {r.text[:300]}")
                else:
                    print(f"ok   {r.status_code} {p} ({len(r.content) // 1024} KB)")
            except Exception as e:  # noqa: BLE001
                bad += 1
                tb = traceback.extract_tb(e.__traceback__)
                where = next((f"{f.filename.split('app/')[-1]}:{f.lineno}" for f in reversed(tb) if "templates" in f.filename or "/app/" in f.filename), "?")
                print(f"ERR  {p} :: {type(e).__name__}: {str(e)[:220]} @ {where}")
    print(f"--- {len(paths) - bad}/{len(paths)} ok")
    return bad


if __name__ == "__main__":
    sys.exit(1 if run(PAGES or ["/"]) else 0)
