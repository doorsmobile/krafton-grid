# Versioning & local path

Project slug: **dcim-cursor**  
Current version: <!-- VERSION:START --> 3.1 <!-- VERSION:END -->  
Release name: <!-- RELEASE:START --> dcim-cursor-v3.1 <!-- RELEASE:END -->  
Local checkout: `/Users/logan/code/dcim-cursor-v3.1`

## Scheme

Two-part versions **`X.Y`** where **Y is a single digit 0–9**:

```
0.8 → 0.9 → 1.0 → 1.1 → … → 1.9 → 2.0
```

Do **not** use `0.10` / `0.11` (that looks like 0.1×). After `0.9`, the next bump is **`1.0`**.

`scripts/bump_version.py` enforces this wrap automatically.

## Agent workflow

On every meaningful change:
1. `python3 scripts/bump_version.py` (default: minor; wraps 0.9→1.0)
2. Bump syncs **`dcim-cursor-vX.Y` + version markers** into all MD prompts:
   `README.md`, `VERSIONING.md`, `docs/REQUIREMENTS.md`, `app/static/brand/README.md`
3. `bash scripts/sync_local.sh` — writes `dist/dcim-cursor-vX.Y.tar.gz`, copies to artifacts, and prints a **litterbox** URL for the real Mac (`/Users/logan/code` inside the cloud VM is not your laptop).
4. Give the user the Mac `curl | tar | ./run_mac.sh` commands from that URL.
5. Keep **`docs/REQUIREMENTS.md`** (canonical prompt / 입력 조건), **`README.md`**, and Tech Spec in sync with menu names, Cloud order (**AWS → GCP → NHN**), and feature changes.
6. Local ports by agent: **ChatGPT 8001 · Cursor 8002 · Claude 8003** (this repo defaults to **8002**).
