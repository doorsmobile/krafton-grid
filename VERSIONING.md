# Versioning & local path

Project slug: **grid-claude**
Current version: <!-- VERSION:START --> 2.0 <!-- VERSION:END -->
Release name: <!-- RELEASE:START --> grid-claude-v2.0 <!-- RELEASE:END -->
Local checkout: `/Users/logan/Code/grid-claude-v2.0`

## Scheme

Two-part versions **`X.Y`** where **Y is a single digit 0–9**:

```
1.8 → 1.9 → 2.0 → 2.1 → … → 2.9 → 3.0
```

Never `1.10` / `2.11`. After `x.9` the next bump is `(x+1).0`. The release name always contains **claude**: `grid-claude-vX.Y`.

## Workflow

1. `python3 scripts/bump_version.py` — minor bump with wrap (`--major`, `--set X.Y`, `--check` also available)
2. The script rewrites `VERSION` and the `<!-- VERSION -->` / `<!-- RELEASE -->` markers plus mentions of the current
   release in `README.md`, `VERSIONING.md` and `docs/REQUIREMENTS.md`. Older releases named in changelogs are left alone.
3. Keep `docs/REQUIREMENTS.md` (canonical spec), `README.md` and the Tech Spec page in sync with menu names,
   Cloud order (**AWS → GCP → NHN**) and feature changes.
4. Copy the tree to `/Users/logan/Code/grid-claude-vX.Y` for the new release; the app reads its version from `VERSION`.
5. Local ports by agent: ChatGPT 8001 · Cursor 8002 · **Claude 8003**.

## History

| Version | Notes |
|---|---|
| 1.0 | First Claude build from the AIDC requirements MD; later aligned with the shared v1.8 spec |
| 2.0 | Full rewrite: physics twin, SSE, causal scenarios + incidents, PromQL/LogQL, Claude Mission Control, job console, Energy & ESG, Budget workflow |
