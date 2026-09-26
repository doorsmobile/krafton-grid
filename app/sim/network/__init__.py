"""Arista-first network fabric — devices, ifaces, topology, 1-min metrics."""

from app.sim.network.constants import NET_HISTORY_LEN, NET_SAMPLE_INTERVAL_SEC
from app.sim.network.devices import build_network_devices_rich
from app.sim.network.interfaces import build_all_interfaces, build_device_interfaces
from app.sim.network.metrics import (
    parse_redis_sample,
    sample_iface_metrics,
    seed_iface_history,
    serialize_sample_for_redis,
)
from app.sim.network.ranking import (
    compact_latest,
    device_detail_payload,
    format_bps,
    rank_top_talkers,
    search_devices,
)
from app.sim.network.topology import build_topology

__all__ = [
    "NET_HISTORY_LEN",
    "NET_SAMPLE_INTERVAL_SEC",
    "build_all_interfaces",
    "build_device_interfaces",
    "build_network_devices_rich",
    "build_topology",
    "compact_latest",
    "device_detail_payload",
    "format_bps",
    "parse_redis_sample",
    "rank_top_talkers",
    "sample_iface_metrics",
    "search_devices",
    "seed_iface_history",
    "serialize_sample_for_redis",
]
