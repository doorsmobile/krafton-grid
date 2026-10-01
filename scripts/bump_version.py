#!/usr/bin/env python3
"""Bump the grid-claude version and sync every doc marker.

Versions are X.Y with a single-digit minor: 1.8 → 1.9 → 2.0 (never 1.10).

    python3 scripts/bump_version.py            # minor bump (wraps 9 → next major)
    python3 scripts/bump_version.py --major    # X+1.0
    python3 scripts/bump_version.py --set 2.3  # explicit
    python3 scripts/bump_version.py --check    # verify docs match VERSION, no writes
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLUG = "grid-claude"
DOCS = [ROOT / "README.md", ROOT / "VERSIONING.md", ROOT / "docs" / "REQUIREMENTS.md"]
VER_RE = re.compile(r"^(\d+)\.(\d)$")


def parse(v: str) -> tuple[int, int]:
    m = VER_RE.match(v.strip())
    if not m:
        raise SystemExit(f"invalid version {v!r}: expected X.Y with a single-digit minor (e.g. 2.0)")
    return int(m.group(1)), int(m.group(2))


def bump(v: str, major: bool = False) -> str:
    x, y = parse(v)
    if major or y == 9:
        return f"{x + 1}.0"
    return f"{x}.{y + 1}"


def sync(text: str, old: str, new: str) -> str:
    """Rewrite the markers and every mention of the *current* release; older releases in changelogs are left alone."""
    rel = f"{SLUG}-v{new}"
    text = re.sub(r"<!-- VERSION:START -->.*?<!-- VERSION:END -->", f"<!-- VERSION:START --> {new} <!-- VERSION:END -->", text)
    text = re.sub(r"<!-- RELEASE:START -->.*?<!-- RELEASE:END -->", f"<!-- RELEASE:START --> {rel} <!-- RELEASE:END -->", text)
    return re.sub(rf"{re.escape(SLUG)}-v{re.escape(old)}(?![\d])", rel, text)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--major", action="store_true")
    g.add_argument("--set", metavar="X.Y")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args()
    vfile = ROOT / "VERSION"
    cur = vfile.read_text().strip()
    parse(cur)
    if a.check:
        bad = [p.name for p in DOCS if p.exists() and sync(p.read_text(encoding="utf-8"), cur, cur) != p.read_text(encoding="utf-8")]
        print(f"{SLUG}-v{cur}: " + ("docs in sync" if not bad else "out of sync → " + ", ".join(bad)))
        return 1 if bad else 0
    new = a.set if a.set else bump(cur, a.major)
    parse(new)
    vfile.write_text(new + "\n")
    for p in DOCS:
        if p.exists():
            p.write_text(sync(p.read_text(encoding="utf-8"), cur, new), encoding="utf-8")
    print(f"{SLUG}-v{cur} → {SLUG}-v{new}")
    print("note: the project folder name is not renamed automatically; copy to "
          f"/Users/logan/Code/{SLUG}-v{new} when you cut the release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
