"""GPU Platform live metric jitter."""

from __future__ import annotations

import math
import random
from typing import Any

def live_fractos_metrics(tick: int) -> dict[str, Any]:
    return {
        "fractos_gpu_util_pct": round(min(94.0, 62 + 14 * math.sin(tick / 16.0) + random.uniform(-3, 3)), 1),
        "fractos_cpu_util_pct": round(min(88.0, 48 + 10 * math.sin(tick / 18.0) + random.uniform(-3, 3)), 1),
        "fractos_mem_util_pct": round(min(90.0, 55 + 8 * math.sin(tick / 22.0) + random.uniform(-2, 2)), 1),
        "fractos_disk_util_pct": round(min(85.0, 42 + 6 * math.sin(tick / 35.0) + random.uniform(-2, 2)), 1),
        "fractos_net_gbps": round(90 + 40 * math.sin(tick / 12.0) + random.uniform(-8, 8), 1),
        "fractos_power_kw": round(48 + 8 * math.sin(tick / 14.0) + random.uniform(-1.5, 1.5), 1),
        "fractos_gpu_temp_c": round(58 + 6 * math.sin(tick / 20.0) + random.uniform(-1, 1), 1),
        "fractos_pods_running": int(86 + 10 * math.sin(tick / 25.0)),
    }

