"""IT Cluster domain — GPU, storage, k8s, basic network catalog, racks."""

from app.sim.it.constants import *
from app.sim.it.gpu import build_gpu_pods
from app.sim.it.inventory import build_asset_rows
from app.sim.it.kubernetes import build_k8s_nodes
from app.sim.it.network_catalog import build_network_devices
from app.sim.it.racks import build_rack_map
from app.sim.it.storage import build_storage_clusters
from app.sim.it.summary import build_inventory_summary

__all__ = [
    "GPU_COUNT",
    "STORAGE_CAPACITY_PB",
    "build_asset_rows",
    "build_gpu_pods",
    "build_inventory_summary",
    "build_k8s_nodes",
    "build_network_devices",
    "build_rack_map",
    "build_storage_clusters",
]
