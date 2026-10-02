"""Host telemetry for Server Status — the machine the collector runs on (CPU, memory, disk, network,
our service processes, EC2 identity). Sampled by the collector every tick and published like any
other read model; the web tier only reads it back from the store.
"""
from __future__ import annotations

import os
import platform
import socket
import time
import urllib.request

import psutil

SERVICES = [  # (role, matcher on the command line)
    ("collector", lambda c: "app.collector" in c),
    ("web", lambda c: "uvicorn" in c and "app.main" in c),
    ("redis", lambda c: c.startswith("redis-server") or "/redis-server" in c),
    ("nginx", lambda c: c.startswith("nginx: master") or c.startswith("nginx: worker")),
]


def _imds() -> dict:
    """EC2 instance identity via IMDSv2 (empty off EC2 — fails fast)."""
    base = "http://169.254.169.254/latest"
    try:
        req = urllib.request.Request(f"{base}/api/token", method="PUT", headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"})
        token = urllib.request.urlopen(req, timeout=0.3).read().decode()
    except Exception:  # noqa: BLE001 — not on EC2
        return {}
    out = {}
    for key, path in (("instance_id", "instance-id"), ("instance_type", "instance-type"), ("az", "placement/availability-zone"),
                      ("region", "placement/region"), ("public_ip", "public-ipv4"), ("private_ip", "local-ipv4"), ("ami", "ami-id")):
        try:
            r = urllib.request.Request(f"{base}/meta-data/{path}", headers={"X-aws-ec2-metadata-token": token})
            out[key] = urllib.request.urlopen(r, timeout=0.5).read().decode()
        except Exception:  # noqa: BLE001
            pass
    return out


def _os_name() -> str:
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return f"{platform.system()} {platform.mac_ver()[0] or platform.release()}"


class HostMonitor:
    def __init__(self, disk_path: str = "/"):
        self.disk_path = disk_path
        mem = psutil.virtual_memory()
        self.static = {
            "hostname": socket.gethostname(), "os": _os_name(), "kernel": platform.release(), "arch": platform.machine(),
            "python": platform.python_version(), "cpus": psutil.cpu_count(logical=True),
            "cores": psutil.cpu_count(logical=False), "mem_total_gb": round(mem.total / 2**30, 1),
            "boot_time": psutil.boot_time(), **_imds(),
        }
        psutil.cpu_percent(None)
        psutil.cpu_percent(None, percpu=True)
        self._t = time.time()
        self._net = psutil.net_io_counters()
        self._dio = psutil.disk_io_counters()
        self._procs: dict[int, psutil.Process] = {}

    def _rates(self) -> dict:
        now, net, dio = time.time(), psutil.net_io_counters(), psutil.disk_io_counters()
        dt = max(now - self._t, 1e-3)
        out = {"net_rx_mbps": round((net.bytes_recv - self._net.bytes_recv) * 8 / dt / 1e6, 3),
               "net_tx_mbps": round((net.bytes_sent - self._net.bytes_sent) * 8 / dt / 1e6, 3),
               "disk_read_mbs": round((dio.read_bytes - self._dio.read_bytes) / dt / 1e6, 3) if dio and self._dio else 0.0,
               "disk_write_mbs": round((dio.write_bytes - self._dio.write_bytes) / dt / 1e6, 3) if dio and self._dio else 0.0}
        self._t, self._net, self._dio = now, net, dio
        return out

    def _processes(self) -> list[dict]:
        seen, rows = set(), []
        for p in psutil.process_iter(["pid", "cmdline", "name"]):
            try:
                cmd = " ".join(p.info["cmdline"] or []) or (p.info["name"] or "")
                role = next((r for r, match in SERVICES if match(cmd)), None)
                if role is None:
                    continue
                proc = self._procs.get(p.pid)
                if proc is None:                       # cpu_percent needs the same object across samples
                    proc = self._procs[p.pid] = p
                    proc.cpu_percent(None)
                seen.add(p.pid)
                with proc.oneshot():
                    rows.append({"role": role, "pid": p.pid, "cpu_pct": round(proc.cpu_percent(None), 1),
                                 "rss_mb": round(proc.memory_info().rss / 2**20, 1), "threads": proc.num_threads(),
                                 "user": proc.username(), "started": proc.create_time(), "cmd": cmd[:120]})
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        for pid in set(self._procs) - seen:
            self._procs.pop(pid, None)
        order = {r: i for i, (r, _) in enumerate(SERVICES)}
        return sorted(rows, key=lambda r: (order[r["role"]], r["pid"]))

    def sample(self) -> dict:
        mem, swap = psutil.virtual_memory(), psutil.swap_memory()
        disk = psutil.disk_usage(self.disk_path)
        load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        return {
            "cpu_pct": psutil.cpu_percent(None), "cpu_per_core": psutil.cpu_percent(None, percpu=True),
            "load": [round(x, 2) for x in load],
            "mem": {"total_gb": round(mem.total / 2**30, 2), "used_gb": round((mem.total - mem.available) / 2**30, 2),
                    "available_gb": round(mem.available / 2**30, 2), "pct": round(mem.percent, 1)},
            "swap": {"total_gb": round(swap.total / 2**30, 2), "used_gb": round(swap.used / 2**30, 2), "pct": round(swap.percent, 1)},
            "disk": {"path": self.disk_path, "total_gb": round(disk.total / 2**30, 1), "used_gb": round(disk.used / 2**30, 1),
                     "free_gb": round(disk.free / 2**30, 1), "pct": round(disk.percent, 1)},
            **self._rates(),
            "uptime_s": round(time.time() - self.static["boot_time"]),
            "processes": self._processes(),
        }
