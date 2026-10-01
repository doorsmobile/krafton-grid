from fastapi import APIRouter, Request

from ..data import need, rm
from ..templating import render

router = APIRouter()


@router.get("/facility", include_in_schema=False)
def page_overview(request: Request):
    return render(request, "facility/overview.html", "Facility", rm.view("facility"))


@router.get("/api/facility", tags=["facility"], summary="Facility overview: site, halls, power & cooling stages, energy flow")
def api_overview():
    return rm.view("facility")


@router.get("/facility/power", include_in_schema=False)
def page_power(request: Request):
    return render(request, "facility/power.html", "Power", rm.view("power"))


@router.get("/api/facility/power", tags=["facility"], summary="2N power chain: utility, TX, UPS A/B, busways, gensets")
def api_power():
    return rm.view("power")


@router.get("/facility/power/{device_id}", include_in_schema=False)
def page_power_device(request: Request, device_id: str):
    d = need(rm.entity("power_device", device_id), "power device")
    return render(request, "facility/power_device.html", d["device"]["id"], d)


@router.get("/api/facility/power/{device_id}", tags=["facility"], summary="One power device with parent/children and peer path")
def api_power_device(device_id: str):
    return need(rm.entity("power_device", device_id), "power device")


@router.get("/facility/cooling", include_in_schema=False)
def page_cooling(request: Request):
    return render(request, "facility/cooling.html", "Cooling", rm.view("cooling"))


@router.get("/api/facility/cooling", tags=["facility"], summary="Liquid-first cooling: rows, CDUs, chillers, towers, CRAHs")
def api_cooling():
    return rm.view("cooling")


@router.get("/facility/cooling/{device_id}", include_in_schema=False)
def page_cooling_device(request: Request, device_id: str):
    d = need(rm.entity("cooling_device", device_id), "cooling device")
    return render(request, "facility/cooling_device.html", d["device"]["id"], d)


@router.get("/api/facility/cooling/{device_id}", tags=["facility"], summary="One cooling device (CDU, chiller, tower, CRAH)")
def api_cooling_device(device_id: str):
    return need(rm.entity("cooling_device", device_id), "cooling device")


@router.get("/facility/capacity", include_in_schema=False)
def page_capacity(request: Request):
    return render(request, "facility/capacity.html", "Capacity", rm.view("capacity"))


@router.get("/api/facility/capacity", tags=["facility"], summary="M1–M5 build-out, hall headroom, expansion planner")
def api_capacity():
    return rm.view("capacity")


@router.get("/facility/hall/{hall_id}", include_in_schema=False)
def page_hall(request: Request, hall_id: str):
    d = need(rm.entity("hall", hall_id.upper()), "hall")
    return render(request, "facility/hall.html", d["hall"]["name"], d)


@router.get("/api/facility/hall/{hall_id}", tags=["facility"], summary="One data hall: rows, racks, CRAHs, UPS")
def api_hall(hall_id: str):
    return need(rm.entity("hall", hall_id.upper()), "hall")


@router.get("/facility/energy", include_in_schema=False)
def page_energy(request: Request):
    return render(request, "facility/energy.html", "Energy & ESG", rm.view("energy"))


@router.get("/api/facility/energy", tags=["facility"], summary="PUE · WUE · CUE, energy flow sankey, carbon, TOU")
def api_energy():
    return rm.view("energy")
