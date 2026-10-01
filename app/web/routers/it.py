from fastapi import APIRouter, Body, HTTPException, Request

from ..data import need, rm
from ..templating import render

router = APIRouter()
HEAT = ("util", "temp", "power", "mem", "sm")


# ------------------------------------------------------------------ GPU
@router.get("/gpu-fleet", include_in_schema=False)
def page_fleet(request: Request):
    return render(request, "it/gpu_fleet.html", "GPU Monitoring", rm.view("gpu_fleet"))


@router.get("/api/gpu/fleet", tags=["gpu"], summary="Fleet explorer: funnel, idle cost, monitors, recommendations, partitions, projects")
def api_fleet():
    return rm.view("gpu_fleet")


@router.get("/api/gpu/heatmap", tags=["gpu"], summary="5,000-GPU grid (40 racks × 16 slots × 8 GPUs) for util|temp|power|mem|sm")
def api_heatmap(metric: str = "util"):
    return rm.view(f"heatmap:{metric if metric in HEAT else 'util'}")


@router.get("/api/gpu/nodes", tags=["gpu"], summary="Slurm + CubeFlow per-node table (util, mem, power, temp, job, user)")
def api_nodes(q: str = "", state: str = "", partition: str = "", rack: str = "", sort: str = "id", limit: int = 700):
    return rm.gpu_nodes(q, state, partition, rack, sort, min(limit, 700))


@router.get("/gpu-fleet/node/{node_id}", include_in_schema=False)
def page_node(request: Request, node_id: str):
    d = need(rm.entity("gpu_node", node_id.lower()), "node")
    return render(request, "it/gpu_node.html", d["node"]["id"], d)


@router.get("/api/gpu/node/{node_id}", tags=["gpu"], summary="HGX node: GPUs, jobs, fabric, cooling, power path, events")
def api_node(node_id: str):
    return need(rm.entity("gpu_node", node_id.lower()), "node")


@router.post("/api/gpu/node/{node_id}/drain", tags=["gpu"], summary="Drain a node in Slurm (running jobs are requeued)")
def api_drain(node_id: str, payload: dict = Body(default={})):
    return rm.cmd("gpu.node.drain", id=node_id, reason=(payload or {}).get("reason", "operator drain"))


@router.post("/api/gpu/node/{node_id}/resume", tags=["gpu"], summary="Resume a drained node")
def api_resume(node_id: str):
    return rm.cmd("gpu.node.resume", id=node_id)


@router.get("/gpu-fleet/device/{gpu_id}", include_in_schema=False)
def page_device(request: Request, gpu_id: str):
    d = need(rm.gpu_device(gpu_id), "GPU")
    return render(request, "it/gpu_device.html", d["gpu"]["id"], d)


@router.get("/api/gpu/device/{gpu_id}", tags=["gpu"], summary="One B300: util, SM, HBM, power, temps, clocks, ECC, XID, MIG")
def api_device(gpu_id: str):
    return need(rm.gpu_device(gpu_id), "GPU")


@router.post("/api/gpu/device/{gpu_id}/xid", tags=["gpu"], summary="Inject an XID event on a GPU (simulation)")
def api_xid(gpu_id: str, payload: dict = Body(default={})):
    return rm.cmd("gpu.xid", id=gpu_id, code=int((payload or {}).get("code", 79)))


@router.get("/gpu-fleet/job/{job_id}", include_in_schema=False)
def page_job(request: Request, job_id: str):
    d = need(rm.entity("gpu_job", str(job_id)), "job")
    return render(request, "it/gpu_job.html", f"Job {job_id}", d)


@router.get("/api/gpu/job/{job_id}", tags=["gpu"], summary="Slurm / CubeFlow job with per-node telemetry")
def api_job(job_id: str):
    return need(rm.entity("gpu_job", str(job_id)), "job")


@router.get("/gpu-fleet/pod/{pod}", include_in_schema=False)
def page_pod(request: Request, pod: str):
    d = need(rm.entity("gpu_pod", pod), "pod")
    return render(request, "it/gpu_pod.html", pod, d)


@router.get("/api/gpu/pod/{pod}", tags=["gpu"], summary="Pod connected to GPUs (MIG inference slice or K8s pod)")
def api_pod(pod: str):
    return need(rm.entity("gpu_pod", pod), "pod")


# ---------------------------------------------------------------- storage
@router.get("/storage", include_in_schema=False)
def page_storage(request: Request):
    return render(request, "it/storage.html", "Storage", rm.view("storage"))


@router.get("/api/storage", tags=["storage"], summary="IBM Storage Scale: clusters, capacity, throughput, top talkers")
def api_storage():
    return rm.view("storage")


@router.get("/storage/cluster/{cluster_id}", include_in_schema=False)
def page_storage_cluster(request: Request, cluster_id: str):
    d = need(rm.entity("storage_cluster", cluster_id), "cluster")
    return render(request, "it/storage_cluster.html", d["cluster"]["name"], d)


@router.get("/api/storage/cluster/{cluster_id}", tags=["storage"], summary="One Scale cluster: filesets, NSD servers, IOPS/latency")
def api_storage_cluster(cluster_id: str):
    return need(rm.entity("storage_cluster", cluster_id), "cluster")


@router.get("/storage/toptalkers", include_in_schema=False)
def page_storage_tt(request: Request):
    return render(request, "it/storage_toptalkers.html", "Storage top talkers", rm.view("storage_toptalkers"))


@router.get("/api/storage/toptalkers", tags=["storage"], summary="Filesets ranked by throughput")
def api_storage_tt():
    return rm.view("storage_toptalkers")


# ---------------------------------------------------------------- network
@router.get("/network", include_in_schema=False)
def page_network(request: Request):
    return render(request, "it/network.html", "Network", rm.view("network"))


@router.get("/api/network", tags=["network"], summary="Fabrics: uplinks, top talkers, topology, inventory, flows")
def api_network():
    return rm.view("network")


@router.get("/network/{view}", include_in_schema=False)
def page_network_view(request: Request, view: str):
    if view not in ("uplinks", "toptalkers", "inventory"):
        raise HTTPException(404, "view not found")
    titles = {"uplinks": "Network uplinks", "toptalkers": "Network top talkers", "inventory": "Network inventory"}
    return render(request, "it/network_list.html", titles[view], rm.view("network"), view=view)


@router.get("/network/device/{device_id}", include_in_schema=False)
def page_network_device(request: Request, device_id: str):
    d = need(rm.entity("network_device", device_id), "device")
    return render(request, "it/network_device.html", device_id, d)


@router.get("/api/network/device/{device_id}", tags=["network"], summary="Switch detail with every interface (bps, errors, discards)")
def api_network_device(device_id: str):
    return need(rm.entity("network_device", device_id), "device")


@router.get("/api/network/topology", tags=["network"], summary="Spine-leaf + IB fat-tree graph with link utilization")
def api_topology():
    return rm.view("topology")


# ------------------------------------------------------------- kubernetes
@router.get("/kubernetes", include_in_schema=False)
def page_k8s(request: Request):
    return render(request, "it/kubernetes.html", "Kubernetes", rm.view("kubernetes"))


@router.get("/api/kubernetes", tags=["kubernetes"], summary="Dell XE9680 × 30 cluster: nodes, namespaces, problem pods, events")
def api_k8s():
    return rm.view("kubernetes")


@router.get("/kubernetes/node/{node_id}", include_in_schema=False)
def page_k8s_node(request: Request, node_id: str):
    d = need(rm.entity("k8s_node", node_id), "node")
    return render(request, "it/k8s_node.html", node_id, d)


@router.get("/api/kubernetes/node/{node_id}", tags=["kubernetes"], summary="One K8s node: pods, conditions, hardware")
def api_k8s_node(node_id: str):
    return need(rm.entity("k8s_node", node_id), "node")
