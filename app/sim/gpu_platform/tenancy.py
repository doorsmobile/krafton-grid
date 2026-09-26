"""Projects and users."""

from __future__ import annotations

from typing import Any

def build_projects() -> list[dict[str, Any]]:
    return [
        {
            "id": "PRJ-01",
            "name": "llm-foundation",
            "owner": "team-nlp",
            "status": "active",
            "quota": {"gpu": 128, "cpu": 512, "mem_tb": 8, "storage_tb": 200},
            "used": {"gpu": 96, "cpu": 380, "mem_tb": 5.2, "storage_tb": 142},
            "members": 12,
            "jobs_running": 4,
        },
        {
            "id": "PRJ-02",
            "name": "vision-rl",
            "owner": "team-cv",
            "status": "active",
            "quota": {"gpu": 64, "cpu": 256, "mem_tb": 4, "storage_tb": 80},
            "used": {"gpu": 40, "cpu": 180, "mem_tb": 2.1, "storage_tb": 55},
            "members": 8,
            "jobs_running": 2,
        },
        {
            "id": "PRJ-03",
            "name": "speech-asr",
            "owner": "team-speech",
            "status": "review",
            "quota": {"gpu": 32, "cpu": 128, "mem_tb": 2, "storage_tb": 40},
            "used": {"gpu": 8, "cpu": 40, "mem_tb": 0.6, "storage_tb": 12},
            "members": 5,
            "jobs_running": 1,
        },
        {
            "id": "PRJ-04",
            "name": "game-ai-npc",
            "owner": "krafton-rnd",
            "status": "active",
            "quota": {"gpu": 96, "cpu": 384, "mem_tb": 6, "storage_tb": 120},
            "used": {"gpu": 72, "cpu": 290, "mem_tb": 4.4, "storage_tb": 88},
            "members": 15,
            "jobs_running": 5,
        },
        {
            "id": "PRJ-05",
            "name": "sandbox-edu",
            "owner": "platform",
            "status": "deleted",
            "quota": {"gpu": 16, "cpu": 64, "mem_tb": 1, "storage_tb": 10},
            "used": {"gpu": 0, "cpu": 0, "mem_tb": 0, "storage_tb": 2},
            "members": 0,
            "jobs_running": 0,
        },
    ]

def build_users() -> list[dict[str, Any]]:
    roles = ["admin", "operator", "developer", "viewer"]
    return [
        {
            "id": f"USR-{i:03d}",
            "name": f"user{i:02d}",
            "email": f"user{i:02d}@krafton.com",
            "role": roles[i % len(roles)],
            "projects": [f"PRJ-{(i % 4) + 1:02d}"],
            "status": "active" if i < 18 else "disabled",
            "last_login": f"2026-09-{10 + (i % 14):02d}T0{(i % 9)}:12:00Z",
        }
        for i in range(1, 21)
    ]


# ---- Jobs / Scheduling / Batch ----

