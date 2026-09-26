#!/usr/bin/env python3
"""Bump project VERSION and print the new release folder name.

Supports X.Y (preferred, matches dcim-cursor-v0.1) or X.Y.Z.
Default bump: minor for X.Y, patch for X.Y.Z.

Also syncs version markers and `dcim-cursor-vX.Y` names into all
project markdown files (README, VERSIONING, docs/REQUIREMENTS, brand README).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"

# Markdown files that must carry the release name / version markers
DOC_PATHS = [
    ROOT / "README.md",
    ROOT / "VERSIONING.md",
    ROOT / "docs" / "REQUIREMENTS.md",
    ROOT / "app" / "static" / "brand" / "README.md",
]


def parse(v: str) -> tuple[int, ...]:
    m = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", v.strip())
    if not m:
        raise ValueError(f"invalid version: {v!r}")
    major, minor = int(m.group(1)), int(m.group(2))
    if m.group(3) is None:
        return major, minor
    return major, minor, int(m.group(3))


def format_v(parts: tuple[int, ...]) -> str:
    return ".".join(str(p) for p in parts)


def bump(parts: tuple[int, ...], kind: str) -> tuple[int, ...]:
    """Bump version.

    X.Y scheme uses a single decimal digit for Y (0–9). After 0.9 the next
    minor bump becomes 1.0 (not 0.10). Same for 1.9 → 2.0, etc.
    """
    if len(parts) == 2:
        major, minor = parts
        if kind == "major":
            return major + 1, 0
        # minor or patch both advance Y; wrap 9 → next major
        if minor >= 9:
            return major + 1, 0
        return major, minor + 1
    major, minor, patch = parts
    if kind == "major":
        return major + 1, 0, 0
    if kind == "minor":
        if minor >= 9:
            return major + 1, 0, 0
        return major, minor + 1, 0
    return major, minor, patch + 1


def sync_docs(version: str) -> list[str]:
    release = f"dcim-cursor-v{version}"
    touched: list[str] = []
    for path in DOC_PATHS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        updated = text
        if "<!-- VERSION:START -->" in updated:
            updated = re.sub(
                r"(<!-- VERSION:START -->).*?(<!-- VERSION:END -->)",
                rf"\1 {version} \2",
                updated,
                count=1,
                flags=re.S,
            )
        if "<!-- RELEASE:START -->" in updated:
            updated = re.sub(
                r"(<!-- RELEASE:START -->).*?(<!-- RELEASE:END -->)",
                rf"\1 {release} \2",
                updated,
                count=1,
                flags=re.S,
            )
        updated = re.sub(
            r"/Users/logan/code/dcim-cursor-v\d+(?:\.\d+)+",
            f"/Users/logan/code/{release}",
            updated,
        )
        updated = re.sub(r"`dcim-cursor-v\d+(?:\.\d+)+`", f"`{release}`", updated)
        # Plain Package: dcim-cursor-vX.Y without requiring backticks (REQUIREMENTS header)
        updated = re.sub(
            r"(Package:\s*`?)dcim-cursor-v\d+(?:\.\d+)+(`?)",
            rf"\1{release}\2",
            updated,
        )
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            touched.append(str(path.relative_to(ROOT)))
    return touched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("patch", "minor", "major"), nargs="?", default="minor")
    parser.add_argument("--set", dest="set_version", help="Set exact version (e.g. 0.1 or 0.1.0)")
    parser.add_argument("--sync-only", action="store_true", help="Only sync docs to current VERSION")
    args = parser.parse_args()

    current = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "0.0"
    if args.sync_only:
        new = format_v(parse(current))
    elif args.set_version:
        new = format_v(parse(args.set_version))
        VERSION_FILE.write_text(new + "\n", encoding="utf-8")
    else:
        new = format_v(bump(parse(current), args.kind))
        VERSION_FILE.write_text(new + "\n", encoding="utf-8")

    release = f"dcim-cursor-v{new}"
    touched = sync_docs(new)
    if args.sync_only:
        print(f"sync-only version={new}")
    else:
        print(f"{current} -> {new}")
    print(f"release={release}")
    print(f"local_path=/Users/logan/code/{release}")
    if touched:
        print("synced=" + ",".join(touched))
    return 0


if __name__ == "__main__":
    sys.exit(main())
